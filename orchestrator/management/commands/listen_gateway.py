import asyncio
import json
import requests
import time
import logging
from collections import defaultdict
from asgiref.sync import sync_to_async
import websockets
from django.conf import settings
from django.core.management.base import BaseCommand
from facade.models import Property
from facade.utils import format_influx_line
from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty
from datetime import datetime
from urllib.parse import urlparse

# Configuração básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

THINGSBOARD_WS_URL_TEMPLATE = "ws://{thingsboard_server}/api/ws/plugins/telemetry?token={your_jwt_token}"
INFLUXDB_URL = f"http://{settings.INFLUXDB_HOST}:{settings.INFLUXDB_PORT}/api/v2/write?org={settings.INFLUXDB_ORGANIZATION}&bucket={settings.INFLUXDB_BUCKET}&precision=ms"
INFLUXDB_TOKEN = settings.INFLUXDB_TOKEN
USE_INFLUX_TO_EVALUATE = settings.USE_INFLUX_TO_EVALUATE

headers = {
    "Authorization": f"Token {INFLUXDB_TOKEN}",
    "Content-Type": "text/plain"
}

class Command(BaseCommand):
    help = 'Starts WebSocket client to listen for ThingsBoard updates for all devices'

    def __init__(self):
        super().__init__()
        self.active_tasks = {}  # Armazena tarefas ativas por device_id
        # Failure counters and last-log timestamps to throttle noisy errors
        self.failure_counts = defaultdict(int)
        self.last_log_at = defaultdict(lambda: 0.0)
        # Token cache and per-gateway HTTP sessions to reduce auth/connection overhead
        self.token_cache = {}  # gateway_id -> {'token': str, 'expires_at': epoch_seconds}
        self.sessions = {}  # gateway_id -> requests.Session()
        # Concurrency semaphore will be set in handle() from CLI options
        self.sem = None

    async def get_jwt_token(self, device):
        gateway = device.gateway
        # Check token cache first
        gw_id = getattr(gateway, 'id', None)
        if gw_id is not None:
            cached = self.token_cache.get(gw_id)
            if cached and cached.get('token') and cached.get('expires_at', 0) > time.time():
                return cached['token']
        url = f"{gateway.url}/api/auth/login"
        payload = {
            "username": gateway.username,
            "password": gateway.password
        }
        headers = {
            "Content-Type": "application/json"
        }
        try:
            response = await sync_to_async(requests.post)(url, headers=headers, data=json.dumps(payload), timeout=5)
            # If login failed, log status and body to help debugging
            if response.status_code != 200:
                body = None
                try:
                    body = response.json()
                except Exception:
                    body = response.text
                logger.warning(f"Failed to authenticate to {url}: status={response.status_code}, body={body}")
                raise Exception(f"Auth failed: {response.status_code}")

            # reset failure counter on success
            self.failure_counts[device.id] = 0
            token = None
            try:
                token = response.json().get("token")
            except Exception:
                token = None

            if not token:
                logger.warning(f"Auth response from {url} did not provide a token: {response.text}")
                raise Exception("Empty token returned from auth endpoint")

            # cache token for 23 hours to avoid repeated logins
            if gw_id is not None:
                try:
                    self.token_cache[gw_id] = {
                        'token': token,
                        'expires_at': time.time() + (23 * 3600)
                    }
                except Exception:
                    pass

            return token
        except Exception as e:
            # exponential backoff: cap at 60s
            self.failure_counts[device.id] += 1
            retries = self.failure_counts[device.id]
            delay = min(60, 2 ** min(retries, 6))
            now = time.time()
            # throttle logging to once every 60s per device (avoid huge logs)
            if now - self.last_log_at[device.id] > 60:
                logger.warning(f"Failed to get JWT token for device {getattr(device, 'name', device.id)}: {str(e)}; will retry in {delay}s")
                self.last_log_at[device.id] = now
            # sleep here to slow down retry attempts
            await asyncio.sleep(delay)
            return None

    async def get_ws_url(self, device):
        # Obtain a valid JWT token first; if we couldn't get one, return None so
        # the caller skips creating a ws task for this device for now.
        jwt_token = await self.get_jwt_token(device)
        if not jwt_token:
            return None

        # Parse gateway URL and construct websocket URL properly (supports http/https)
        parsed = urlparse(device.gateway.url)
        netloc = parsed.netloc or parsed.path  # handle urls without scheme
        scheme = 'wss' if parsed.scheme == 'https' else 'ws'
        return f"{scheme}://{netloc}/api/ws/plugins/telemetry?token={jwt_token}"

    def add_arguments(self, parser):
        parser.add_argument(
            '--concurrency',
            type=int,
            help='Maximum concurrent HTTP requests when checking device status (defaults to unlimited)'
        )
        parser.add_argument(
            '--use-influxdb',
            action='store_true',
            default=None,
            help='Enable writing to InfluxDB (overrides default). If omitted, the setting USE_INFLUX_TO_EVALUATE is used.'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Polling interval in seconds to refresh device list and tasks (default: 5)'
        )

    async def listen(self):
        while True:
            dtinstanceproperties = await sync_to_async(list)(DigitalTwinInstanceProperty.objects.filter(
                device_property__isnull=False
            ).select_related('device_property__device__gateway'))
            
            # Iniciar ou atualizar tasks para novos dispositivos
            for dtinstanceproperty in dtinstanceproperties:
                device = dtinstanceproperty.device_property.device
                device_id = device.id
                if device_id not in self.active_tasks:
                    # Create a per-device task that will obtain/refresh JWTs as needed
                    self.active_tasks[device_id] = asyncio.create_task(
                        self.listen_to_device(device)
                    )
            
            # Remover tasks de dispositivos que não existem mais no banco
            active_device_ids = {d.device_property.device.id for d in dtinstanceproperties}
            for device_id in list(self.active_tasks.keys()):
                if device_id not in active_device_ids:
                    self.active_tasks[device_id].cancel()
                    del self.active_tasks[device_id]
                    logger.info(f"Stopped listening for device {device_id}")

            # Sleep using configured interval (default 5s for higher responsiveness)
            sleep_interval = getattr(self, 'poll_interval', 5)
            await asyncio.sleep(sleep_interval)

    async def listen_to_device(self, device):
        while True:
            try:
                # Obtain a fresh WS URL (with valid JWT) before each connection attempt
                ws_url = await self.get_ws_url(device)
                if not ws_url:
                    # Failed to get JWT (backoff already applied inside get_jwt_token)
                    await asyncio.sleep(5)
                    continue

                logger.debug(f"Attempting WebSocket connection to {ws_url} for device {device.name}")
                async with websockets.connect(ws_url, timeout=10) as websocket:
                    logger.info(f"Connected to ThingsBoard WebSocket for device {device.name}")
                    
                    # Subscribe to updates for the device
                    subscribe_message = {
                        "tsSubCmds": [
                            {
                                "entityType": "DEVICE",
                                "entityId": device.identifier,
                                "scope": "LATEST_TELEMETRY",
                                "cmdId": 1
                            }
                        ],
                        "historyCmds": [],
                        "attrSubCmds": []
                    }

                    await websocket.send(json.dumps(subscribe_message))

                    async for message in websocket:
                        data = json.loads(message)
                        await self.process_message(device, data)

            except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError, OSError) as e:
                # Throttle repeated connection error logs per device
                now = time.time()
                self.failure_counts[device.id] += 1
                retries = self.failure_counts[device.id]
                delay = min(60, 2 ** min(retries, 6))
                # If server returned a websocket close with code 1011 and message indicating
                # an invalid JWT, try to refresh token on the next loop iteration rather
                # than reconnecting immediately with the same (invalid) token.
                msg = str(e)
                if isinstance(e, websockets.exceptions.ConnectionClosed) and getattr(e, 'code', None) == 1011 and 'Invalid JWT' in msg:
                    logger.warning(f"Invalid JWT for device {device.name}; will refresh token and retry in {delay}s")
                else:
                    if now - self.last_log_at[device.id] > 60:
                        logger.warning(f"Connection error for device {device.name}: {str(e)}; reconnecting in {delay}s")
                        self.last_log_at[device.id] = now

                await asyncio.sleep(delay)
                continue

    async def check_device_status(self, device):
        """Verifica o status do dispositivo no ThingsBoard"""
        try:
            jwt_token = await self.get_jwt_token(device)
            url = f"{device.gateway.url}/api/plugins/telemetry/DEVICE/{device.identifier}/values/attributes"
            headers = {
                "Content-Type": "application/json",
                "X-Authorization": f"Bearer {jwt_token}"
            }
            # Use session per gateway to reuse connections
            gw_id = getattr(device.gateway, 'id', None)
            if gw_id not in self.sessions:
                self.sessions[gw_id] = requests.Session()
            session = self.sessions[gw_id]
            timeout_seconds = 3
            # If a semaphore was configured, acquire it to limit concurrency
            if self.sem is not None:
                async with self.sem:
                    response = await sync_to_async(session.get)(url, headers=headers, timeout=timeout_seconds)
            else:
                response = await sync_to_async(session.get)(url, headers=headers, timeout=timeout_seconds)
            if response.status_code == 200:
                attributes = response.json()
                # Verifica o atributo de status do dispositivo
                for attr in attributes:
                    if attr.get('key') == 'active':
                        return attr.get('value', False)
            return False
        except Exception as e:
            # Avoid noisy exception trace for transient errors; log once per minute
            now = time.time()
            if now - self.last_log_at[getattr(device, 'id', 'global')] > 60:
                logger.warning(f"Error checking device status for {getattr(device, 'name', device)}: {e}")
                self.last_log_at[getattr(device, 'id', 'global')] = now
            return False

    async def update_dt_instance_status(self, device, is_active):
        """Atualiza o status do DigitalTwinInstance e registra mudanças no InfluxDB"""
        dt_instances = await sync_to_async(list)(
            DigitalTwinInstance.objects.filter(
                digitaltwininstanceproperty__device_property__device=device
            ).distinct()
        )
        
        for dt_instance in dt_instances:
            current_state = await sync_to_async(lambda: dt_instance.active)()
            if current_state != is_active:
                current_timestamp = int(time.time() * 1000)  # Horário atual em milissegundos
                
                # Obtém o timestamp da última verificação
                last_check_timestamp = await sync_to_async(lambda: int(dt_instance.last_status_check.timestamp() * 1000))()
                
                # Calcula a duração da inatividade
                inactivity_duration = 0
                if not is_active:
                    # Se está ficando inativo agora, marca o início da inatividade
                    inactivity_duration = 0  # Não há inatividade ainda
                else:
                    # Se está voltando a ficar ativo, calcula o tempo que ficou inativo
                    inactivity_duration = current_timestamp - last_check_timestamp
                
                # Atualiza o estado no Django
                dt_instance.active = is_active
                dt_instance.last_status_check = datetime.fromtimestamp(current_timestamp / 1000)  # Salva em segundos
                await sync_to_async(dt_instance.save)()
                logger.info(f"Updated DT Instance {dt_instance.id} status to {'active' if is_active else 'inactive'}")
                
                # Envia os dados para o InfluxDB
                if self.use_influxdb and inactivity_duration > 0:
                    logger.info(f"Writing availability event to InfluxDB for device {device.identifier}")
                    try:
                        device_type_name = await sync_to_async(lambda: device.type.name if device.type else 'unknown')()
                        
                        tags = [
                            f"device={device.identifier}",
                            f"dt_instance={dt_instance.id}",
                            f"device_type={device_type_name}"
                        ]
                        
                        fields = [
                            f"active={1 if is_active else 0}i",
                            f"inactivity_duration={inactivity_duration}i"
                        ]
                        
                        measurement = f"device_availability,{','.join(tags)} {','.join(fields)} {current_timestamp}"
                        
                        response = await sync_to_async(requests.post)(
                            INFLUXDB_URL, 
                            headers=headers, 
                            data=measurement
                        )
                        
                        if response.status_code != 204:
                            logger.error(f"Failed to write availability event: {response.text}")
                            logger.error(f"Attempted measurement: {measurement}")
                        else:
                            logger.info(f"Device {device.identifier} {'activated' if is_active else 'deactivated'} " + 
                                        f"after {inactivity_duration / 1000:.2f} seconds of {'inactivity' if is_active else 'activity'}")
                        
                    except Exception as e:
                        logger.exception(f"Error writing availability to InfluxDB: {str(e)}")

    async def process_message(self, device, data):
        """Processa mensagens recebidas do ThingsBoard"""
        logger.info(f"Processing message for device {device.name}")
        
        # Verifica o status do dispositivo primeiro
        device_active = await self.check_device_status(device)
        await self.update_dt_instance_status(device, device_active)

        if not device_active:
            logger.warning(f"Device {device.name} is inactive, skipping telemetry update")
            return

        latest_values = data.get('data')
        if latest_values:
            for key, value in latest_values.items():
                try:
                    hora, valor = value[0]
                    # Atualiza a propriedade do dispositivo
                    await sync_to_async(Property.objects.filter(device=device, name=key).update)(value=valor)
                    
                    # Atualiza o DigitalTwinInstanceProperty apenas se o dispositivo estiver ativo
                    await sync_to_async(DigitalTwinInstanceProperty.objects.filter(
                        device_property__device=device,
                        property__name=key,
                        dtinstance__active=True
                    ).update)(value=valor)
                    
                    if self.use_influxdb and device_active:
                        timestamp = int(time.time() * 1000)
                        property = await sync_to_async(lambda: Property.objects.filter(device=device, name=key).first())()
                        # Do not append _i to the key. Force integer types for Boolean/Integer properties
                        if property:
                            try:
                                ptype = property.type
                            except Exception:
                                ptype = None
                            if ptype in ('Boolean', 'Integer'):
                                # ensure Python int so format_influx_line will render as integer (with i suffix)
                                try:
                                    property_value = int(property.get_value())
                                except Exception:
                                    # fallback: coerce from the raw telemetry value
                                    try:
                                        property_value = int(valor)
                                    except Exception:
                                        property_value = 0
                            elif ptype == 'Double':
                                try:
                                    property_value = float(property.get_value())
                                except Exception:
                                    property_value = property.get_value()
                            else:
                                property_value = property.get_value()
                        else:
                            # no local Property found — use the raw telemetry value
                            property_value = valor
                        
                        # Envia apenas o received_timestamp para o InfluxDB using safe formatter
                        # Prefer ThingsBoard internal id (thingsboard_id) when available to avoid
                        # conflicts with friendly names. Fall back to device.identifier.
                        sensor_id = device.identifier
                        tags = {"sensor": sensor_id, "source": "middts"}
                        # Ensure numeric types for booleans/ints; send explicit integer suffix for status-like fields
                        if key.lower() in ('status', 'active'):
                            # send as float 1.0/0.0 to avoid Influx integer/float conflicts
                            try:
                                pv = float(property_value)
                            except Exception:
                                pv = 1.0 if int(property_value) else 0.0
                            fields = {key: pv, "received_timestamp": timestamp}
                        else:
                            fields = {key: property_value, "received_timestamp": timestamp}
                        data = format_influx_line("device_data", tags, fields, timestamp=timestamp)
                        logger.debug(f"Posting to InfluxDB (middts listener): {data}")
                        response = requests.post(INFLUXDB_URL, headers=headers, data=data)
                        logger.info(f"Response Code: {response.status_code}, Response Text: {response.text} - Data Sent: {data}")
                        logger.info(f"Updated property for {device.name} - {key}: {valor} and sent to InfluxDB with received_timestamp")

                except Exception as e:
                    logger.exception(f"Error processing property {key} for device {device.name}: {e}")

    def handle(self, *args, **options):
        # CLI options: allow override of influx usage and concurrency
        concurrency = options.get('concurrency', None)
        # Determine whether to write to InfluxDB.
        # CLI flag (--use-influxdb) is explicit True when provided. We set its default to None so
        # we can differentiate "flag not provided" from "flag provided as false".
        cli_flag = options.get('use_influxdb', None)
        if cli_flag is None:
            # Respect the settings value. Settings may come from environment and could be a string.
            env_val = USE_INFLUX_TO_EVALUATE
            if isinstance(env_val, str):
                self.use_influxdb = env_val.strip().lower() in ('1', 'true', 'yes', 'y')
            else:
                self.use_influxdb = bool(env_val)
        else:
            # CLI flag explicitly provided => use it (True). Note: action='store_true' only sets True when passed.
            self.use_influxdb = bool(cli_flag)
        # polling interval in seconds for refreshing device list
        self.poll_interval = options.get('interval', 5)
        if concurrency:
            try:
                concurrency_val = int(concurrency)
                self.sem = asyncio.Semaphore(concurrency_val)
            except Exception:
                self.sem = None

        loop = asyncio.get_event_loop()
        try:
            logger.info("Starting WebSocket listener...")
            logger.info(f"Influx writes enabled: {self.use_influxdb}")
            loop.run_until_complete(self.listen())
        except KeyboardInterrupt:
            logger.info("Stopping WebSocket listener...")
            for task in self.active_tasks.values():
                task.cancel()

import asyncio
import json
import requests
import time
import logging
from asgiref.sync import sync_to_async
import websockets
from django.conf import settings
from django.core.management.base import BaseCommand
from facade.models import Property
from facade.utils import format_influx_line
from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty
from datetime import datetime

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

    async def get_jwt_token(self, device):
        gateway = device.gateway
        url = f"{gateway.url}/api/auth/login"
        payload = {
            "username": gateway.username,
            "password": gateway.password
        }
        headers = {
            "Content-Type": "application/json"
        }
        response = await sync_to_async(requests.post)(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json().get("token")

    async def get_ws_url(self, device):
        jwt_token = await self.get_jwt_token(device)
        return THINGSBOARD_WS_URL_TEMPLATE.format(
            thingsboard_server=device.gateway.url,
            your_jwt_token=jwt_token
        ).replace('http://', '')

    async def listen(self):
        while True:
            dtinstanceproperties = await sync_to_async(list)(DigitalTwinInstanceProperty.objects.filter(
                device_property__isnull=False
            ).select_related('device_property__device__gateway'))
            
            # Iniciar ou atualizar tasks para novos dispositivos
            for dtinstanceproperty in dtinstanceproperties:
                device_id = dtinstanceproperty.device_property.device.id
                if device_id not in self.active_tasks:
                    ws_url = await self.get_ws_url(dtinstanceproperty.device_property.device)
                    self.active_tasks[device_id] = asyncio.create_task(
                        self.listen_to_device(ws_url, dtinstanceproperty.device_property.device)
                    )
            
            # Remover tasks de dispositivos que não existem mais no banco
            active_device_ids = {d.device_property.device.id for d in dtinstanceproperties}
            for device_id in list(self.active_tasks.keys()):
                if device_id not in active_device_ids:
                    self.active_tasks[device_id].cancel()
                    del self.active_tasks[device_id]
                    logger.info(f"Stopped listening for device {device_id}")

            await asyncio.sleep(30)  # Verificar novos dispositivos a cada 10 minutos

    async def listen_to_device(self, ws_url, device):
        while True:
            try:
                logger.info(ws_url)
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

            except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError) as e:
                logger.error(f"Connection error for device {device.name}: {e}")
                logger.info("Reconnecting in 10 seconds...")
                await asyncio.sleep(10)  # Wait before reconnecting

    async def check_device_status(self, device):
        """Verifica o status do dispositivo no ThingsBoard"""
        try:
            jwt_token = await self.get_jwt_token(device)
            url = f"{device.gateway.url}/api/plugins/telemetry/DEVICE/{device.identifier}/values/attributes"
            headers = {
                "Content-Type": "application/json",
                "X-Authorization": f"Bearer {jwt_token}"
            }
            response = await sync_to_async(requests.get)(url, headers=headers)
            if response.status_code == 200:
                attributes = response.json()
                # Verifica o atributo de status do dispositivo
                for attr in attributes:
                    if attr.get('key') == 'active':
                        return attr.get('value', False)
            return False
        except Exception as e:
            logger.exception(f"Error checking device status: {e}")
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
                        if isinstance(property.get_value(), bool):
                            key = f'{key}_i'
                            property_value = int(property.get_value())
                        else:
                            property_value = property.get_value()
                        
                        # Envia apenas o received_timestamp para o InfluxDB using safe formatter
                        tags = {"sensor": device.identifier, "source": "middts"}
                        # Ensure numeric types for booleans/ints
                        fields = {key: property_value, "received_timestamp": timestamp}
                        data = format_influx_line("device_data", tags, fields, timestamp=timestamp)
                        response = requests.post(INFLUXDB_URL, headers=headers, data=data)
                        logger.info(f"Response Code: {response.status_code}, Response Text: {response.text}")
                        logger.info(f"Updated property for {device.name} - {key}: {valor} and sent to InfluxDB with received_timestamp")

                except Exception as e:
                    logger.exception(f"Error processing property {key} for device {device.name}: {e}")

    def handle(self, *args, **options):
        self.use_influxdb = USE_INFLUX_TO_EVALUATE  # Atualiza o parâmetro com o valor passado
        loop = asyncio.get_event_loop()
        try:
            logger.info("Starting WebSocket listener...")
            loop.run_until_complete(self.listen())
        except KeyboardInterrupt:
            logger.info("Stopping WebSocket listener...")
            for task in self.active_tasks.values():
                task.cancel()

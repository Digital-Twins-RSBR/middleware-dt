import random
import asyncio
from asgiref.sync import sync_to_async
import requests
import json
import logging
from django.core.management.base import BaseCommand
from facade.models import Device, Property, write_inactivity_event, InactivityType
from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty
from facade.api import get_jwt_token_gateway
from datetime import datetime, timedelta

# Configuração básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class JWTTokenManager:
    def __init__(self):
        self.tokens = {}  # {gateway_id: {'token': token, 'expires_at': datetime}}
        self.token_lifetime = timedelta(hours=23)  # Define um tempo de vida menor que 24h para ter margem de segurança

    def get_token(self, gateway_id):
        if gateway_id in self.tokens:
            token_data = self.tokens[gateway_id]
            if datetime.now() < token_data['expires_at']:
                return token_data['token']
            
        return None

    def set_token(self, gateway_id, token):
        self.tokens[gateway_id] = {
            'token': token,
            'expires_at': datetime.now() + self.token_lifetime
        }

class Command(BaseCommand):
    help = 'Periodically check device status in ThingsBoard and update local DigitalTwin status'

    def __init__(self):
        super().__init__()
        self.token_manager = JWTTokenManager()

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=10,
            help='Interval in seconds between status checks (default: 10)'
        )
        parser.add_argument(
            '--device-ids',
            nargs='+',
            type=int,
            help='List of Device IDs to monitor. If not provided, monitors all devices.'
        )

    def handle(self, *args, **options):
        interval = options['interval']
        device_ids = options['device_ids']
        loop = asyncio.get_event_loop()
        try:
            logger.info("Starting device status checker...")
            loop.run_until_complete(self.check_devices_status(interval, device_ids))
        except KeyboardInterrupt:
            logger.info("Stopping device status checker...")

    async def get_jwt_token(self, device):
        gateway_id = device.gateway_id
        cached_token = self.token_manager.get_token(gateway_id)
        if cached_token:
            logger.info(f"Using cached JWT token for gateway {gateway_id}")
            return cached_token

        logger.info(f"Requesting new JWT token for gateway {gateway_id}")
        response, status_code = await sync_to_async(get_jwt_token_gateway)(None, gateway_id)
        if status_code == 200:
            token = response['token']
            self.token_manager.set_token(gateway_id, token)
            return token
        logger.error(f"Failed to get JWT token for gateway {gateway_id}, status code: {status_code}")
        return None

    async def check_device_status(self, device):
        logger.info(f"Checking status for device {device.name} (ID: {device.id})")
        try:
            jwt_token = await self.get_jwt_token(device)
            if not jwt_token:
                logger.warning(f"Failed to get JWT token for device {device.name}")
                await sync_to_async(write_inactivity_event)(
                    device, 
                    InactivityType.CONNECTION_ERROR, 
                    "Failed to get JWT token"
                )
                return False

            url = f"{device.gateway.url}/api/plugins/telemetry/DEVICE/{device.identifier}/values/attributes"
            headers = {
                "Content-Type": "application/json",
                "X-Authorization": f"Bearer {jwt_token}"
            }
            
            try:
                response = await sync_to_async(requests.get)(url, headers=headers)
            except requests.exceptions.ConnectionError:
                logger.error(f"Connection error while checking status for device {device.name}")
                await sync_to_async(write_inactivity_event)(
                    device, 
                    InactivityType.CONNECTION_ERROR, 
                    "Connection error with ThingsBoard"
                )
                return False

            if response.status_code == 401:
                logger.warning(f"JWT token expired for device {device.name}, requesting a new one...")
                self.token_manager.set_token(device.gateway_id, None)
                jwt_token = await self.get_jwt_token(device)
                if jwt_token:
                    headers["X-Authorization"] = f"Bearer {jwt_token}"
                    response = await sync_to_async(requests.get)(url, headers=headers)

            if response.status_code == 200:
                attributes = response.json()
                is_active = False
                for attr in attributes:
                    if attr.get('key') == 'active':
                        is_active = attr.get('value', False)
                        break

                logger.info(f"Device {device.name} is {'active' if is_active else 'inactive'}")

                if not is_active:
                    await sync_to_async(write_inactivity_event)(
                        device, 
                        InactivityType.DEVICE_INACTIVE, 
                        "Device marked as inactive in ThingsBoard"
                    )

                dt_instances = await sync_to_async(list)(
                    DigitalTwinInstance.objects.filter(
                        digitaltwininstanceproperty__device_property__device=device
                    ).distinct()
                )

                for dt_instance in dt_instances:
                    current_active = await sync_to_async(lambda: dt_instance.active)()
                    if current_active != is_active:
                        logger.info(f"Updating DigitalTwinInstance {dt_instance.id} status to {'active' if is_active else 'inactive'}")
                        dt_instance.active = is_active
                        await sync_to_async(dt_instance.save)()

                return is_active
            else:
                logger.error(f"Failed to check status for device {device.name}, HTTP {response.status_code}: {response.text}")
                await sync_to_async(write_inactivity_event)(
                    device, 
                    InactivityType.CONNECTION_ERROR, 
                    f"HTTP {response.status_code}: {response.text}"
                )
                return False

        except Exception as e:
            logger.exception(f"Error while checking status for device {device.name}: {e}")
            await sync_to_async(write_inactivity_event)(
                device, 
                InactivityType.CONNECTION_ERROR, 
                str(e)
            )
            return False

    async def check_devices_status(self, interval, device_ids=None):
        logger.info(f"Starting periodic device status checks every {interval} seconds")
        while True:
            try:
                if device_ids:
                    devices = await sync_to_async(list)(Device.objects.filter(id__in=device_ids).select_related('gateway')) 
                else:
                    devices = await sync_to_async(list)(Device.objects.all().select_related('gateway'))

                logger.info(f"Found {len(devices)} devices to check")
                tasks = [self.check_device_status(device) for device in devices]
                await asyncio.gather(*tasks)

                await asyncio.sleep(interval)
            except Exception as e:
                logger.exception(f"Error in check_devices_status: {e}")
                await asyncio.sleep(interval)
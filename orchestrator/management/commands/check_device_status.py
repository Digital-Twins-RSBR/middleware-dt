import random
import asyncio
from asgiref.sync import sync_to_async
import requests
import json
from django.core.management.base import BaseCommand
from facade.models import Device, Property, write_inactivity_event, InactivityType
from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty
from facade.api import get_jwt_token_gateway
from datetime import datetime, timedelta

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
            default=30,
            help='Interval in seconds between status checks (default: 30)'
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
            loop.run_until_complete(self.check_devices_status(interval, device_ids))
        except KeyboardInterrupt:
            print("Stopping device status checker...")

    async def get_jwt_token(self, device):
        gateway_id = device.gateway_id
        cached_token = self.token_manager.get_token(gateway_id)
        if cached_token:
            return cached_token

        response, status_code = await sync_to_async(get_jwt_token_gateway)(None, gateway_id)
        if status_code == 200:
            token = response['token']
            self.token_manager.set_token(gateway_id, token)
            return token
        return None

    async def check_device_status(self, device):
        try:
            jwt_token = await self.get_jwt_token(device)
            if not jwt_token:
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
                await sync_to_async(write_inactivity_event)(
                    device, 
                    InactivityType.CONNECTION_ERROR, 
                    "Connection error with ThingsBoard"
                )
                return False

            if response.status_code == 401:
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
                        dt_instance.active = is_active
                        await sync_to_async(dt_instance.save)()

                return is_active
            else:
                await sync_to_async(write_inactivity_event)(
                    device, 
                    InactivityType.CONNECTION_ERROR, 
                    f"HTTP {response.status_code}: {response.text}"
                )
                return False

        except Exception as e:
            await sync_to_async(write_inactivity_event)(
                device, 
                InactivityType.CONNECTION_ERROR, 
                str(e)
            )
            return False

    async def check_devices_status(self, interval, device_ids=None):
        while True:
            try:
                if device_ids:
                    devices = await sync_to_async(list)(Device.objects.filter(id__in=device_ids).select_related('gateway')) 
                else:
                    devices = await sync_to_async(list)(Device.objects.all().select_related('gateway'))

                tasks = [self.check_device_status(device) for device in devices]
                await asyncio.gather(*tasks)

                # for device, is_active in zip(devices, results):
                #     print(f"Device {device.name} status: {'Active' if is_active else 'Inactive'}")

                await asyncio.sleep(interval)
            except Exception as e:
                print(f"Error in check_devices_status: {e}")
                await asyncio.sleep(interval)
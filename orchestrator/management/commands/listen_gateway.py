import asyncio
import json
import requests
from asgiref.sync import sync_to_async
import websockets
from django.core.management.base import BaseCommand
from facade.models import Property, Device
from orchestrator.models import DigitalTwinInstanceProperty

THINGSBOARD_WS_URL_TEMPLATE = "ws://{thingsboard_server}/api/ws/plugins/telemetry?token={your_jwt_token}"

class Command(BaseCommand):
    help = 'Starts WebSocket client to listen for ThingsBoard updates for all devices'

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
        dtinstanceproperties = await sync_to_async(list)(DigitalTwinInstanceProperty.objects.filter(device_property__isnull=False).select_related('device_property__device__gateway'))
        tasks = []

        for dtinstanceproperty in dtinstanceproperties:
            ws_url = await self.get_ws_url(dtinstanceproperty.device_property.device)
            tasks.append(self.listen_to_device(ws_url, dtinstanceproperty.device_property.device))

        await asyncio.gather(*tasks)

    async def listen_to_device(self, ws_url, device):
        while True:
            try:
                print(ws_url)
                async with websockets.connect(ws_url, timeout=10) as websocket:
                    print(f"Connected to ThingsBoard WebSocket for device {device.name}")
                    
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
                        print(f"Received data for device {device.name}: {data}")
                        await self.process_message(device, data)

            except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError) as e:
                print(f"Connection error for device {device.name}: {e}")
                print("Reconnecting in 10 seconds...")
                await asyncio.sleep(10)  # Wait before reconnecting

    async def process_message(self, device, data):
        latest_values = data.get('data')

        if latest_values:
            for key, value in latest_values.items():
                try:
                    hora, valor = value[0]
                    await sync_to_async(Property.objects.filter(device=device, name=key).update)(value = valor)
                    # Update the corresponding DigitalTwinInstanceProperty
                    print(f'{device} - {key} - {valor}')
                    await sync_to_async(DigitalTwinInstanceProperty.objects.filter(
                        device_property__device=device, 
                        property=key
                    ).update)(value=valor)

                except Property.DoesNotExist:
                    print(f"No property found for device {device.identifier} with name {key}")
                except DigitalTwinInstanceProperty.DoesNotExist:
                    print(f"No DigitalTwinInstanceProperty found for device {device.identifier} with property {key}")

    def handle(self, *args, **options):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.listen())

        while True:
            # Periodically check for new devices (every 10 minutes)
            print("Checking for new devices...")
            loop.run_until_complete(self.listen())
            asyncio.sleep(600)

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


    # async def listen(self):
    #     dtinstanceproperties = await sync_to_async(list)(DigitalTwinInstanceProperty.objects.filter(device_property__isnull=False).select_related('device_property__device__gateway'))
    #     tasks = []

    #     for dtinstanceproperty in dtinstanceproperties:
    #         ws_url = await self.get_ws_url(dtinstanceproperty.device_property.device)
    #         tasks.append(self.listen_to_device(ws_url, dtinstanceproperty.device_property.device))

    #     await asyncio.gather(*tasks)

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
                    print(f"Stopped listening for device {device_id}")

            await asyncio.sleep(30)  # Verificar novos dispositivos a cada 10 minutos

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
                    await sync_to_async(DigitalTwinInstanceProperty.objects.filter(
                        device_property__device=device, 
                        property__name=key
                    ).update)(value=valor)
                    print(f"Updated property for {device.name} - {key}: {valor}")

                except Property.DoesNotExist:
                    print(f"No property found for device {device.identifier} with name {key}")
                except DigitalTwinInstanceProperty.DoesNotExist:
                    print(f"No DigitalTwinInstanceProperty found for device {device.identifier} with property {key}")
                except Exception as e:
                    print(f"Error processing property {key} for device {device.name}: {e}")


    def handle(self, *args, **options):
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.listen())
        except KeyboardInterrupt:
            print("Stopping WebSocket listener...")
            for task in self.active_tasks.values():
                task.cancel()

        # while True:
        #     # Periodically check for new devices (every 10 minutes)
        #     print("Checking for new devices...")
        #     loop.run_until_complete(self.listen())
        #     asyncio.sleep(600)

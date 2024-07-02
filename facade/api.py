# facade/views.py
import json

from ninja import Query
from .models import Device, DeviceType, GatewayIOT
from .schemas import DeviceDiscoveryParams, DeviceRPCView, DeviceSchema, GatewayIOTSchema, TokenObtainPairView
import requests
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from rest_framework_simplejwt.tokens import RefreshToken
from ninja import Router

router = Router()


# @router.post("/token/", response={200: dict})
# def obtain_token_pair(request, payload: TokenObtainPairView):
#     user = authenticate(username=payload.username, password=payload.password)
#     if user is not None:
#         refresh = RefreshToken.for_user(user)
#         return {"refresh": str(refresh), "access": str(refresh.access_token)}
#     return router.create_response(request, {"error": "Invalid credentials"}, status=401)


@router.get("/devices/", response={200: list[DeviceSchema]}, tags=['Facade'])
def list_devices(request):
    user = request.user
    devices = Device.objects.filter(user=user)
    return devices

@router.get("/gatewayiot/{gateway_id}/jwt/", response={200: dict}, tags=['Facade'])
def get_jwt_token_gateway(request, gateway_id: int, user):
    gateway = get_object_or_404(GatewayIOT, id=gateway_id, user=user)
    url = f"{gateway.url}/api/auth/login"
    payload = {
        "username": gateway.username,
        "password": gateway.password
    }
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        return response.json().get("token")
    else:
        print(f"Error obtaining JWT token: {response.status_code}, {response.text}")
        return None

@router.post("/devices/{device_id}/rpc/", response={200: dict}, tags=['Facade'])
def call_device_rpc(request, device_id: int, payload: DeviceRPCView):
    user = request.user
    device = get_object_or_404(Device, id=device_id, user=user)
    gateway = device.gateway
    url = f"{gateway.url}/api/plugins/rpc/oneway/{device.identifier}"
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {gateway.password}",
    }
    response = requests.post(
        url, json={"method": payload.method, "params": payload.params}, headers=headers
    )
    if response.status_code == 200:
        return response.json()
    return router.create_response(request, response.json(), status=response.status_code)


@router.get("/gatewaysiot/{gateway_id}/discover-devices/", response={200: list[DeviceSchema]}, tags=['Facade'])
def discover_devices(request, gateway_id: int, params: DeviceDiscoveryParams = Query(...)):
    user = request.user
    token = get_jwt_token_gateway(request, gateway_id, user)
    gateway = get_object_or_404(GatewayIOT, id=gateway_id, user=user)
    headers = {
        'Content-Type': 'application/json',
        'X-Authorization': f"Bearer {token}"
    }
    url = f"{gateway.url}/api/tenant/devices"
    response = requests.get(url, headers=headers, params=params.dict())
    if response.status_code == 200:
        devices_data = response.json()['data']
        devices = []
        for device_data in devices_data:
            device, created = Device.objects.update_or_create(
                defaults={
                    'name': device_data['name'],
                    'identifier': device_data['id']['id'],
                    'status': 'unknown',
                    'type': DeviceType.objects.filter(name=device_data['type']).first(),
                    'gateway': gateway,
                    'user': user
                }
            )
            devices.append(device)
        return devices
    return router.create_response(request, response.json(), status=response.status_code)

@router.get("/devices/{device_id}/rpc-methods/", response={200: list}, tags=['Facade'])
def list_device_rpc_methods(request, device_id: int):
    user = request.auth
    device = get_object_or_404(Device, id=device_id, user=user)
    return device.type.rpc_methods


@router.post("/gatewaysiot/", response={201: GatewayIOTSchema}, tags=['Facade'])
def create_gateway(request, payload: GatewayIOTSchema):
    user = request.user
    payload_data = payload.dict()
    gateway = GatewayIOT.objects.create(user=user, **payload_data)
    return gateway


@router.get("/gatewaysiot/", response={200: list[GatewayIOTSchema]}, tags=['Facade'])
def list_gateways(request):
    user = request.user
    gateways = GatewayIOT.objects.filter(user=user)
    return gateways

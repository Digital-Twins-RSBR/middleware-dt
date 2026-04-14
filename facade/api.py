# facade/views.py
import json

from core.api import get_gateway_auth_headers
from ninja import Query
from core.models import GatewayIOT
from .models import Device, DeviceType
from .schemas import DeviceDiscoveryParams, DeviceRPCView, DeviceSchema
import requests
from django.shortcuts import get_object_or_404
from ninja import Router, NinjaAPI

router = Router()
api = NinjaAPI()


@router.get("/devices/", response={200: list[DeviceSchema]}, tags=['Facade'])
def list_devices(request):
    devices = Device.objects.all()
    return devices

@router.post("/devices/{device_id}/rpc/", response={200: dict}, tags=['Facade'])
def call_device_rpc(request, device_id: int, payload: DeviceRPCView):
    import uuid
    device = get_object_or_404(Device, id=device_id)
    gateway = device.gateway
    auth_response, status_code = get_gateway_auth_headers(request, gateway.id)
    if status_code != 200:
        return api.create_response(request, auth_response, status=status_code)
    url = f"{gateway.url}/api/plugins/rpc/oneway/{device.identifier}"
    headers = auth_response["headers"]
    # Gerar request_id único
    request_id = str(uuid.uuid4())
    # Incluir request_id no payload.params
    params = dict(payload.params) if payload.params else {}
    params["request_id"] = request_id
    # Chamar o RPC com request_id propagado
    response = requests.post(
        url, json={"method": payload.method, "params": params}, headers=headers
    )
    # Atribuir request_id ao device para uso posterior (ex: gravação sent_timestamp)
    setattr(device, 'request_id', request_id)
    if response.status_code == 200:
        return response.json()
    return api.create_response(request, response.json(), status=response.status_code)


@router.get("/gatewaysiot/{gateway_id}/discover-devices/", response={200: dict}, tags=['Facade'])
def discover_devices(request, gateway_id: int, params: DeviceDiscoveryParams = Query(...)):
    user = request.user
    auth_response, status_code = get_gateway_auth_headers(request, gateway_id)
    if status_code != 200:
        return api.create_response(request, auth_response, status=status_code)
    gateway = get_object_or_404(GatewayIOT, id=gateway_id)
    headers = auth_response["headers"]
    url = f"{gateway.url}/api/tenant/devices"
    response = requests.get(url, headers=headers, params=params.dict())
    if response.status_code == 200:
        devices_data = response.json()['data']
        created_objs = []
        updated_count = 0
        for device_data in devices_data:
            obj = Device.objects.filter(identifier=device_data['id']['id'], gateway=gateway).first()
            if obj:
                # Atualiza campos diretamente, sem chamar save customizado
                obj.name = device_data['name']
                obj.status = 'unknown'
                obj.type = DeviceType.objects.filter(name=device_data['type']).first()
                obj.user = user
                obj.save_base(raw=True)  # Bypass custom save
                updated_count += 1
            else:
                created_objs.append(Device(
                    name=device_data['name'],
                    identifier=device_data['id']['id'],
                    status='unknown',
                    type=DeviceType.objects.filter(name=device_data['type']).first(),
                    gateway=gateway,
                    user=user
                ))
        created_count = 0
        if created_objs:
            Device.objects.bulk_create(created_objs)
            created_count = len(created_objs)
        return {"created": created_count, "updated": updated_count}
    return api.create_response(request, response.json(), status=response.status_code)

@router.get("/devices/{device_id}/rpc-methods/", response={200: list}, tags=['Facade'])
def list_device_rpc_methods(request, device_id: int):
    # user = request.auth
    device = get_object_or_404(Device, id=device_id) #, user=user)
    rpc_methods = device.property_set.filter(rpc_read_method__isnull=False).values_list('name', 'rpc_read_method', 'rpc_write_method')
    return rpc_methods


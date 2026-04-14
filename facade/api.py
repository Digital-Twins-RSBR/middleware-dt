# facade/views.py
import json

from core.api import get_gateway_auth_headers
from ninja import Query
from core.models import GatewayIOT
from .models import Device, DeviceType, Property
from .schemas import DeviceDiscoveryParams, DeviceRPCView, DeviceSchema
import requests
from django.shortcuts import get_object_or_404
from ninja import Router, NinjaAPI
from django.contrib.auth import get_user_model
import json
from pathlib import Path
from django.conf import settings

# Load device type mappings (optional). If present, used as fallback to create
# properties and RPC metadata when ThingsBoard doesn't provide them. This can
# be disabled via the `DEVICE_TYPE_MAPPING_ENABLED` Django setting so the
# system falls back to telemetry-only inference.
_MAPPINGS_PATH = Path(__file__).resolve().parents[1] / "orchestrator" / "config" / "device_type_mappings.json"
if getattr(settings, 'DEVICE_TYPE_MAPPING_ENABLED', True):
    try:
        if _MAPPINGS_PATH.exists():
            with open(_MAPPINGS_PATH, 'r', encoding='utf-8') as _f:
                DEVICE_TYPE_MAPPINGS = json.load(_f)
        else:
            DEVICE_TYPE_MAPPINGS = {}
    except Exception:
        DEVICE_TYPE_MAPPINGS = {}
else:
    DEVICE_TYPE_MAPPINGS = {}

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
    User = get_user_model()
    # Allow anonymous API calls to trigger discovery for testing: fall back
    # to a system user (prefer a superuser) when the request is unauthenticated.
    if getattr(request, "user", None) and request.user.is_authenticated:
        user = request.user
    else:
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
    auth_response, status_code = get_gateway_auth_headers(request, gateway_id)
    if status_code != 200:
        return api.create_response(request, auth_response, status=status_code)
    gateway = get_object_or_404(GatewayIOT, id=gateway_id)
    headers = auth_response["headers"]
    url = f"{gateway.url}/api/tenant/devices"
    # Helper functions (defined here so they are available for both created and updated devices)
    def try_sync_telemetry_keys_to_properties(dev_obj):
        try:
            keys_url = f"{gateway.url.rstrip('/')}/api/plugins/telemetry/DEVICE/{dev_obj.identifier}/keys/timeseries"
            kresp = requests.get(keys_url, headers=headers, timeout=10)
            if kresp.status_code == 200:
                keys = kresp.json()
                for key in keys:
                    # create without side-effects
                    prop, created = Property.objects.get_or_create(device=dev_obj, name=key, defaults={"type": "Double"})
                    if created:
                        try:
                            prop.save_base(raw=True)
                        except Exception:
                            pass
        except Exception:
            pass

    def apply_type_mapping(dev_obj, dtype_name):
        try:
            mapping = DEVICE_TYPE_MAPPINGS.get(dtype_name) or DEVICE_TYPE_MAPPINGS.get(dtype_name.strip())
            if not mapping:
                return
            for p in mapping:
                # Create property without rpc methods first to avoid triggering RPC on save
                defaults = {"type": p.get("type", "Double")}
                prop, created = Property.objects.get_or_create(device=dev_obj, name=p["name"], defaults=defaults)
                # If mapping defines rpc methods, set them using raw save to avoid RPC side-effects
                updated = False
                if p.get("rpc_read_method") and prop.rpc_read_method != p.get("rpc_read_method"):
                    prop.rpc_read_method = p.get("rpc_read_method")
                    updated = True
                if p.get("rpc_write_method") and prop.rpc_write_method != p.get("rpc_write_method"):
                    prop.rpc_write_method = p.get("rpc_write_method")
                    updated = True
                if updated:
                    try:
                        prop.save_base(raw=True)
                    except Exception:
                        pass
        except Exception:
            pass

    def infer_properties_from_telemetry(dev_obj):
        try:
            keys_url = f"{gateway.url.rstrip('/')}/api/plugins/telemetry/DEVICE/{dev_obj.identifier}/keys/timeseries"
            kresp = requests.get(keys_url, headers=headers, timeout=10)
            if kresp.status_code != 200:
                return
            keys = kresp.json() or []
            if not keys:
                return
            for key in keys:
                val_url = f"{gateway.url.rstrip('/')}/api/plugins/telemetry/DEVICE/{dev_obj.identifier}/values/timeseries?keys={key}&limit=1"
                vresp = requests.get(val_url, headers=headers, timeout=10)
                if vresp.status_code != 200:
                    continue
                try:
                    vjson = vresp.json()
                except Exception:
                    continue
                val = None
                if isinstance(vjson, dict):
                    for k, arr in vjson.items():
                        if isinstance(arr, list) and arr:
                            val = arr[0].get("value")
                            break
                ptype = "String"
                if val is None:
                    ptype = "String"
                else:
                    s = str(val).lower()
                    if s in ("true", "false"):
                        ptype = "Boolean"
                    else:
                        try:
                            int(val)
                            ptype = "Integer"
                        except Exception:
                            try:
                                float(val)
                                ptype = "Double"
                            except Exception:
                                ptype = "String"
                Property.objects.get_or_create(device=dev_obj, name=key, defaults={"type": ptype})
        except Exception:
            pass

    response = requests.get(url, headers=headers, params=params.dict())
    if response.status_code == 200:
        devices_data = response.json()['data']
        created_objs = []
        updated_count = 0
        for device_data in devices_data:
            obj = Device.objects.filter(identifier=device_data['id']['id'], gateway=gateway).first()
            # Ensure device type exists (create if necessary)
            dtype_name = device_data.get('type') or 'Unknown'
            dtype, _ = DeviceType.objects.get_or_create(name=dtype_name)
            if obj:
                # Atualiza campos e persiste (usando update_fields para evitar bypass)
                obj.name = device_data['name']
                obj.status = 'unknown'
                obj.type = dtype
                obj.user = user
                try:
                    obj.save(update_fields=['name', 'status', 'type', 'user'])
                except Exception:
                    obj.save()
                updated_count += 1
                # Se não houver propriedades locais, sincroniza a partir do ThingsBoard
                try:
                    if not obj.property_set.exists():
                        obj.sync_properties_from_thingsboard()
                        obj.sync_metadata_from_thingsboard()
                        # Apply mapping fallback and telemetry inference if still empty
                        if not obj.property_set.exists():
                            apply_type_mapping(obj, dtype_name)
                        if not obj.property_set.exists():
                            try_sync_telemetry_keys_to_properties(obj)
                        if not obj.property_set.exists():
                            infer_properties_from_telemetry(obj)
                except Exception:
                    pass
            else:
                created_objs.append(Device(
                    name=device_data['name'],
                    identifier=device_data['id']['id'],
                    status='unknown',
                    type=dtype,
                    gateway=gateway,
                    user=user
                ))
        created_count = 0
        if created_objs:
            # Bulk create then post-process to sync properties/metadata
            Device.objects.bulk_create(created_objs)
            created_count = len(created_objs)
            # Requery created devices to trigger property/metadata sync
            identifiers = [d.identifier for d in created_objs]
            created_devices = list(Device.objects.filter(identifier__in=identifiers, gateway=gateway))
            for dev in created_devices:
                try:
                    # Ensure type exists (should already) and sync properties/metadata
                    dev.sync_properties_from_thingsboard()
                    dev.sync_metadata_from_thingsboard()
                except Exception:
                    # Don't fail the entire discovery if a device sync fails
                    pass
            # Apply mapping/inference for created devices
            for dev in created_devices:
                try:
                    # 1) attempt mapping by device type
                    dtype_name = dev.type.name if dev.type else ''
                    apply_type_mapping(dev, dtype_name)
                    # 2) if still no properties, try telemetry-based inference
                    if not dev.property_set.exists():
                        try_sync_telemetry_keys_to_properties(dev)
                    if not dev.property_set.exists():
                        infer_properties_from_telemetry(dev)
                except Exception:
                    pass
        # Final pass: ensure all devices for this gateway have properties via mapping/inference
        try:
            for dev in Device.objects.filter(gateway=gateway):
                try:
                    if not dev.property_set.exists():
                        dtype_name = dev.type.name if dev.type else ''
                        apply_type_mapping(dev, dtype_name)
                        if not dev.property_set.exists():
                            try_sync_telemetry_keys_to_properties(dev)
                        if not dev.property_set.exists():
                            infer_properties_from_telemetry(dev)
                except Exception:
                    pass
        except Exception:
            pass
        return {"created": created_count, "updated": updated_count}
    return api.create_response(request, response.json(), status=response.status_code)

@router.get("/devices/{device_id}/rpc-methods/", response={200: list}, tags=['Facade'])
def list_device_rpc_methods(request, device_id: int):
    # user = request.auth
    device = get_object_or_404(Device, id=device_id) #, user=user)
    rpc_methods = device.property_set.filter(rpc_read_method__isnull=False).values_list('name', 'rpc_read_method', 'rpc_write_method')
    return rpc_methods


# facade/serializers.py
from ninja import ModelSchema, Schema
from .models import Device


class DeviceRPCView(Schema):
    method: str
    params: dict

class DeviceSchema(ModelSchema):
    class Meta:
        model = Device
        fields = ('id', 'name', 'identifier', 'status', 'type', 'gateway', 'user')

class DeviceDiscoveryParams(Schema):
    pageSize: int
    page: int
    type: str = None
    textSearch: str = None
    sortProperty: str = None
    sortOrder: str = None

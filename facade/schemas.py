# facade/serializers.py
from ninja import ModelSchema, Schema
from .models import Device, GatewayIOT


class TokenObtainPairView(Schema):
    username: str
    password: str

class DeviceRPCView(Schema):
    method: str
    params: dict

class DeviceSchema(ModelSchema):
    class Meta:
        model = Device
        fields = ('device_id', 'name', 'identifier', 'status', 'type', 'gateway', 'user')

class GatewayIOTSchema(ModelSchema):
    class Meta:
        model = GatewayIOT
        fields = ('id', 'name', 'url', 'username', 'password', 'user')

class DeviceDiscoveryParams(Schema):
    pageSize: int
    page: int
    type: str = None
    textSearch: str = None
    sortProperty: str = None
    sortOrder: str = None

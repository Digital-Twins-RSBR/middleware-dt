# facade/serializers.py
from ninja import ModelSchema, Schema
from .models import Device, Property
from typing import List

class DeviceRPCView(Schema):
    method: str
    params: dict

class PropertySchema(ModelSchema):

    class Meta:
        model = Property
        fields = ('id', 'name', 'type', 'value', 'device')



class DeviceSchema(ModelSchema):
    type_name: str = None
    type_id: int = None
    properties: List[PropertySchema] = []

    class Meta:
        model = Device
        fields = ('id', 'name', 'identifier', 'status', 'type', 'gateway', 'user')

    @staticmethod
    def resolve_type_name(obj):
        return obj.type.name if obj.type else ''
    
    @staticmethod
    def resolve_type_id(obj):
        return obj.type_id if obj.type else 0
    
    @staticmethod
    def resolve_properties(obj):
        return Property.objects.filter(device=obj)

class DeviceDiscoveryParams(Schema):
    pageSize: int
    page: int
    type: str = None
    textSearch: str = None
    sortProperty: str = None
    sortOrder: str = None

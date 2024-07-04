from ninja import Router, Schema

class DTDLModelSchema(Schema):
    id: str
    name: str
    modelElements: list
    modelRelationships: list

class DigitalTwinInstanceSchema(Schema):
    id: int
    model: str
    device: str = None
    properties: list

class DigitalTwinPropertySchema(Schema):
    name: str
    value: str
    device_property: str

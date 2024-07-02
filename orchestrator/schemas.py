from ninja import Router, Schema

class DTDLModelSchema(Schema):
    id: str
    name: str
    modelElements: list
    modelRelationships: list
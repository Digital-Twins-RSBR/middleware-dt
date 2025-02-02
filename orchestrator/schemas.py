from ninja import Router, Schema, ModelSchema
from pydantic import BaseModel, Field
from facade.models import Property
from orchestrator.models import DigitalTwinInstanceRelationship, SystemContext, DTDLModel, DigitalTwinInstance, DigitalTwinInstanceProperty
from typing import Any, List, Optional, Dict

class CreateSystemContextSchema(ModelSchema):
    class Meta:
        model = SystemContext
        fields = ['name', 'description']

class SystemContextSchema(ModelSchema):
    class Meta:
        model = SystemContext
        fields = ['id','name', 'description']

class CreateDTDLModelSchema(ModelSchema):

    class Meta:
        model = DTDLModel
        fields = ['name', 'specification',]

class PutDTDLModelSchema(ModelSchema):

    class Meta:
        model = DTDLModel
        fields = ['id', 'dtdl_id', 'system', 'name', 'specification', ]

class DTDLModelSchema(ModelSchema):

    class Meta:
        model = DTDLModel
        fields = ['id', 'dtdl_id', 'system', 'name', 'specification', 'parsed_specification', ]



class CreateDTFromDTDLModelSchema(Schema):
    dtdl_model_id : int


class DigitalTwinPropertySchema(ModelSchema):
    class Meta:
        model = DigitalTwinInstanceProperty
        fields = ['id', 'dtinstance', 'property','value', 'device_property']

class DigitalTwinRelationshipSchema(ModelSchema):
    class Meta:
        model = DigitalTwinInstanceRelationship
        fields = ['id', 'source_instance', 'target_instance', 'relationship']

class DigitalTwinInstanceSchema(ModelSchema):
    digitaltwininstanceproperty_set: List[DigitalTwinPropertySchema] = []
    sourcerelationships: List[DigitalTwinRelationshipSchema] = []

    class Meta:
        model = DigitalTwinInstance
        fields = ['id', 'model']

    @staticmethod
    def resolve_digitaltwininstanceproperty_set(obj):
        # Retorna uma lista de propriedades associadas ao DigitalTwinInstance
        return DigitalTwinInstanceProperty.objects.filter(dtinstance=obj)

    @staticmethod
    def resolve_sourcerelationships(obj):
        # Retorna uma lista de relacionamentos associados ao DigitalTwinInstance como source
        return DigitalTwinInstanceRelationship.objects.filter(source_instance=obj)

class BindDTInstancePropertieDeviceSchema(Schema):
    property_id : int
    device_property_id : int

class DigitalTwinInstanceRelationshipSchema(Schema):
    relationship_name: str
    source_instance_id: int
    target_instance_id: int

    class Config:
        schema_extra = {
            "example": {
                "relationship_name": "contains",
                "source_instance_id": 1,    
                "target_instance_id": 2
            }
        }

class DigitalTwinPropertyUpdateSchema(Schema):
    value: Any

class DigitalTwinInstancePropertySchema(Schema):

    id: int
    property: str
    value: Any  # Aceita qualquer tipo para evitar erros de validação
    is_causal: bool

    @staticmethod
    def from_instance(instance):
        """
        Converte a instância de `DigitalTwinInstanceProperty` para o schema.
        """
        return DigitalTwinInstancePropertySchema(
            id=instance.id,
            property=instance.property.name,  # Certifique-se que `name` existe
            value=str(instance.value) if instance.value is not None else None,  # Converte para string
            is_causal=instance.causal,  # Chama o método da instância do Digital Twin
        )
    
class DTDLModelBatchSchema(Schema):
    name: str
    specification: dict

class DTDLModelIDSchema(Schema):
    dtdl_model_ids: List[int]

class CypherQuerySchema(BaseModel):
    query: str
    
    def serialize_node(node):
        return {
            "identity": node.id,
            "labels": list(node.labels),
            "properties": dict(node)
        }

class DTDLSpecificationSchema(BaseModel):
    context: List[str] = Field(..., alias='@context')
    id: str = Field(..., alias='@id')
    type: str = Field(..., alias='@type')
    displayName: str
    contents: List[Dict[str, Any]]

class CreateMultipleDTDLModelsSchema(BaseModel):
    specifications: List[DTDLSpecificationSchema]
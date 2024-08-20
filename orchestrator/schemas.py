from ninja import Router, Schema, ModelSchema
from orchestrator.models import SystemContext, DTDLModel, DTDLModelParsed, DigitalTwinInstance, DigitalTwinInstanceProperty

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
        fields = ['name', 'specification', 'parser_client']

class DTDLModelSchema(ModelSchema):

    class Meta:
        model = DTDLModel
        fields = ['id', 'system', 'name', 'specification', 'parser_client']

class DTDLModelParsedSchema(ModelSchema):

    class Meta:
        model = DTDLModelParsed
        fields = ['id', 'system', 'dtdl_id', 'name', 'specification']

class CreateDTDLModelParsedSchema(ModelSchema):

    class Meta:
        model = DTDLModelParsed
        fields = ['id', 'system', 'dtdl_id', 'name', 'specification']

class DigitalTwinInstanceSchema(ModelSchema):

    class Meta:
        model = DigitalTwinInstance
        fields = ['id', 'model',]

class DigitalTwinPropertySchema(ModelSchema):
    class Meta:
        model = DigitalTwinInstanceProperty
        fields = ['id', 'dtinstance', 'property','value', 'device_property']

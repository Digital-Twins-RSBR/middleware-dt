from ninja import Router, Schema, ModelSchema
from orchestrator.models import Application, DTDLModel, DTDLModelParsed, DigitalTwinInstance, DigitalTwinInstanceProperty

class CreateApplicationSchema(ModelSchema):
    class Meta:
        model = Application
        fields = ['name', 'description']

class ApplicationSchema(ModelSchema):
    class Meta:
        model = Application
        fields = ['id','name', 'description']

class CreateDTDLModelSchema(ModelSchema):

    class Meta:
        model = DTDLModel
        fields = ['name', 'application', 'specification', 'parser_client']

class DTDLModelSchema(ModelSchema):

    class Meta:
        model = DTDLModel
        fields = ['id', 'application', 'name', 'specification', 'parser_client']

class DTDLModelParsedSchema(ModelSchema):

    class Meta:
        model = DTDLModelParsed
        fields = ['id', 'application', 'dtdl_id', 'name', 'specification']

class CreateDTDLModelParsedSchema(ModelSchema):

    class Meta:
        model = DTDLModelParsed
        fields = ['id', 'application', 'dtdl_id', 'name', 'specification']

class DigitalTwinInstanceSchema(ModelSchema):

    class Meta:
        model = DigitalTwinInstance
        fields = ['id', 'model']

class DigitalTwinPropertySchema(ModelSchema):
    class Meta:
        model = DigitalTwinInstanceProperty
        fields = ['id', 'dtinstance', 'property','value', 'device_property']

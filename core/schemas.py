from ninja import ModelSchema
from .models import DTDLParserClient, GatewayIOT

class CreateGatewayIOTSchema(ModelSchema):
    class Meta:
        model = GatewayIOT
        fields = ('name', 'url', 'username', 'password')

class GatewayIOTSchema(ModelSchema):
    class Meta:
        model = GatewayIOT
        fields = ('id', 'name', 'url', 'username', 'password', 'user')

class CreateDTDLParserClientchema(ModelSchema):
    class Meta:
        model = DTDLParserClient
        fields = ('name', 'url', )

class DTDLParserClientchema(ModelSchema):
    class Meta:
        model = DTDLParserClient
        fields = ('id', 'name', 'url')
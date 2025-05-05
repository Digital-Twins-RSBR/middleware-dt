from ninja import ModelSchema
from pydantic import BaseModel

from .models import DTDLParserClient, GatewayIOT

class CreateGatewayIOTSchema(ModelSchema):
    class Meta:
        model = GatewayIOT
        fields = ('name', 'url', 'username', 'password')

class GatewayIOTSchema(ModelSchema):
    class Meta:
        model = GatewayIOT
        fields = ('id', 'name', 'url', 'username', 'password', )

class CreateDTDLParserClientchema(ModelSchema):
    class Meta:
        model = DTDLParserClient
        fields = ('name', 'url', )

class DTDLParserClientchema(ModelSchema):
    class Meta:
        model = DTDLParserClient
        fields = ('id', 'name', 'url')

class TokenSchema(BaseModel):
    token: str

class TokenPayloadSchema(BaseModel):
    user_id: int
    exp: int
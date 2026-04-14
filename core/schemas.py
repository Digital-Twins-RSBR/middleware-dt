from ninja import ModelSchema
from pydantic import BaseModel

from .models import GatewayIOT

class CreateGatewayIOTSchema(ModelSchema):
    class Meta:
        model = GatewayIOT
        fields = ('name', 'url', 'auth_method', 'username', 'password', 'api_key')

class GatewayIOTSchema(ModelSchema):
    class Meta:
        model = GatewayIOT
        fields = ('id', 'name', 'url', 'auth_method', 'username', 'password', 'api_key')

class TokenSchema(BaseModel):
    token: str

class TokenPayloadSchema(BaseModel):
    user_id: int
    exp: int
from ninja import ModelSchema
from pydantic import BaseModel

from .models import GatewayIOT, Organization


class CreateOrganizationSchema(ModelSchema):
    class Meta:
        model = Organization
        fields = ('name', 'description')


class OrganizationSchema(ModelSchema):
    class Meta:
        model = Organization
        fields = ('id', 'name', 'description')


class AddOrganizationMemberSchema(BaseModel):
    user_id: int
    role: str = 'member'


class CreateUserSchema(BaseModel):
    username: str
    password: str
    email: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    is_staff: bool = True
    organization_id: int | None = None
    role: str = 'member'

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
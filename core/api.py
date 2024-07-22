import json
from .models import DTDLParserClient, GatewayIOT
from .schemas import CreateDTDLParserClientchema, CreateGatewayIOTSchema, DTDLParserClientchema, GatewayIOTSchema
import requests
from django.shortcuts import get_object_or_404
from ninja import Router, NinjaAPI
from typing import List

router = Router()
api = NinjaAPI()

@router.post("/gatewaysiot/", response=GatewayIOTSchema, tags=['Core'])
def create_gateway(request, payload: CreateGatewayIOTSchema):
    user = request.user
    payload_data = payload.dict()
    gateway = GatewayIOT.objects.create(user=user, **payload_data)
    return gateway

@router.get("/gatewayiot/{gatewayiot_id}/", response=GatewayIOTSchema, tags=['Core'])
def get_gatewayiot(request, gatewayiot_id: int):
    gateway = get_object_or_404(GatewayIOT, id=gatewayiot_id, user=request.user)
    return gateway


@router.get("/gatewaysiot/", response=List[GatewayIOTSchema], tags=['Core'])
def list_gateways(request):
    user = request.user
    gateways = GatewayIOT.objects.filter(user=user)
    return gateways

@router.get("/gatewayiot/{gateway_id}/jwt/", response={200: dict, 400: dict}, tags=['Core'])
def get_jwt_token_gateway(request, gateway_id: int, user=None):
    user = user or request.user
    gateway = get_object_or_404(GatewayIOT, id=gateway_id, user=user)
    url = f"{gateway.url}/api/auth/login"
    payload = {
        "username": gateway.username,
        "password": gateway.password
    }
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        token = response.json().get("token")
        return {"token": token}, 200
    else:
        return {
            "error": f"Error obtaining JWT token: {response.status_code}, {response.text}"
        }, 400
    
@router.post("/dtdlparserclient/", response=DTDLParserClientchema, tags=['Core'])
def create_dtdlparserclient(request, payload: CreateDTDLParserClientchema):
    payload_data = payload.dict()
    dtdlparserclient = DTDLParserClient.objects.create(**payload_data)
    return dtdlparserclient

@router.get("/dtdlparserclient/{dtdlparserclient_id}/", response=DTDLParserClientchema, tags=['Core'])
def get_dtdlparserclient(request, dtdlparserclient_id: int):
    dtdlparserclient = get_object_or_404(DTDLParserClient, id=dtdlparserclient_id)
    return dtdlparserclient


@router.get("/dtdlparserclient/", response=List[DTDLParserClientchema], tags=['Core'])
def list_dtdlparserclient(request):
    user = request.user
    dtdlparserclients = DTDLParserClient.objects.all()
    return dtdlparserclients
import json
from django.conf import settings
from django.contrib.auth import authenticate
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from ninja import Router, NinjaAPI
from typing import List
import jwt
import requests
from datetime import datetime, timedelta
from .models import DTDLParserClient, GatewayIOT
from .schemas import CreateDTDLParserClientchema, CreateGatewayIOTSchema, DTDLParserClientchema, GatewayIOTSchema
from rest_framework_simplejwt.tokens import RefreshToken


router = Router()
api = NinjaAPI()

SECRET_KEY = settings.SECRET_KEY # Replace with your actual secret key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/token/", response=dict, tags=['Auth'])
def login(request, username: str, password: str):
    user = authenticate(request, username=username, password=password)
    if not user:
        return {"error": "Invalid credentials"}, 400
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/gatewaysiot/", response=GatewayIOTSchema, tags=['Core'])
def create_gateway(request, payload: CreateGatewayIOTSchema):
    payload_data = payload.dict()
    gateway = GatewayIOT.objects.create(**payload_data)
    return gateway

@router.get("/gatewayiot/{gatewayiot_id}/", response=GatewayIOTSchema, tags=['Core'])
def get_gatewayiot(request, gatewayiot_id: int):
    gateway = get_object_or_404(GatewayIOT, id=gatewayiot_id)
    return gateway

@router.get("/gatewaysiot/", response=List[GatewayIOTSchema], tags=['Core'])
def list_gateways(request):
    gateways = GatewayIOT.objects.all()
    return gateways

@router.get("/gatewayiot/{gateway_id}/jwt/", response={200: dict, 400: dict}, tags=['Core'])
def get_jwt_token_gateway(request, gateway_id: int):
    gateway = get_object_or_404(GatewayIOT, id=gateway_id)
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
    dtdlparserclients = DTDLParserClient.objects.all()
    return dtdlparserclients

# Middleware to validate JWT tokens will be implemented separately.

router = Router()
@router.post("/token/", tags=["Authentication"])
def obtain_token(request, username: str, password: str):
    user = authenticate(username=username, password=password)
    if user is not None:
        refresh = RefreshToken.for_user(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }
    return JsonResponse({"detail": "Invalid credentials"}, status=401)

@router.post("/token/refresh/", tags=["Authentication"])
def refresh_token(request, refresh: str):
    try:
        refresh_token = RefreshToken(refresh)
        return {
            "access": str(refresh_token.access_token),
        }
    except Exception:
        return JsonResponse({"detail": "Invalid refresh token"}, status=401)

@router.get("/protected-endpoint/", tags=["Protected"])
def protected_endpoint(request):
    return JsonResponse({"message": "This is a protected endpoint."})
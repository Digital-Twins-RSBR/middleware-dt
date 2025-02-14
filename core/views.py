from django.shortcuts import render
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.http import JsonResponse
from rest_framework_simplejwt.tokens import RefreshToken
from ninja import Router

def index(request):
    return render(request, 'index.html')

router = Router()

@router.post("/token/", tags=["Authentication"])
def obtain_token(request):
    username = request.data.get("username")
    password = request.data.get("password")
    user = authenticate(username=username, password=password)
    
    if user is not None:
        refresh = RefreshToken.for_user(user)
        return JsonResponse({
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        })
    return JsonResponse({"error": "Invalid credentials"}, status=400)

@router.get("/protected-endpoint/", tags=["Protected"])
def protected_endpoint(request):
    return JsonResponse({"message": "This is a protected endpoint."})
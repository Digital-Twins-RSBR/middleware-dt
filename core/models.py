from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from enum import Enum

# Create your models here.
# 
class GatewayIOT(models.Model):
    AUTH_METHOD_USER_PASSWORD = "user_password"
    AUTH_METHOD_API_KEY = "api_key"
    AUTH_METHOD_CHOICES = [
        (AUTH_METHOD_USER_PASSWORD, "Usuario e senha"),
        (AUTH_METHOD_API_KEY, "API Key"),
    ]

    name = models.CharField(max_length=255)
    url = models.URLField()
    auth_method = models.CharField(max_length=32, choices=AUTH_METHOD_CHOICES, default=AUTH_METHOD_USER_PASSWORD)
    username = models.CharField(max_length=255, blank=True, null=True)
    password = models.CharField(max_length=255, blank=True, null=True)
    api_key = models.CharField(max_length=512, blank=True, null=True)

    def clean(self):
        if self.auth_method == self.AUTH_METHOD_USER_PASSWORD:
            if not self.username or not self.password:
                raise ValidationError("Usuario e senha sao obrigatorios para auth por login.")
        elif self.auth_method == self.AUTH_METHOD_API_KEY:
            if not self.api_key:
                raise ValidationError("API Key e obrigatoria para auth por ApiKey.")
        else:
            raise ValidationError("Metodo de autenticacao invalido.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name
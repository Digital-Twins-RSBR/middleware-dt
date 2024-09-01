from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from enum import Enum

# Create your models here.
# 
class GatewayIOT(models.Model):
    name = models.CharField(max_length=255)
    url = models.URLField()
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    user = models.ForeignKey(User, related_name='gateways', on_delete=models.CASCADE)

    def __str__(self):
        return self.name
    
class DTDLParserClient(models.Model):
    name = models.CharField(max_length=255)
    url = models.CharField(max_length=255) # /api/DTDLModels/parse
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name
    
    @classmethod
    def get_active(cls):
        return DTDLParserClient.objects.filter(active=True).order_by('?').first()
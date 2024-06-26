# Create your models here.

# gateway/models.py
from django.db import models
from django.contrib.auth.models import User

class GatewayIOT(models.Model):
    name = models.CharField(max_length=255)
    url = models.URLField()
    username = models.CharField(max_length=255)
    password = models.CharField(max_length=255)
    user = models.ForeignKey(User, related_name='gateways', on_delete=models.CASCADE)

    def __str__(self):
        return self.name

class DeviceType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    rpc_methods = models.JSONField()

    def __str__(self):
        return self.name

class Device(models.Model):
    device_id = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    identifier = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
    type = models.ForeignKey(DeviceType, on_delete=models.CASCADE, null=True)
    gateway = models.ForeignKey(GatewayIOT, related_name='devices', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='devices', on_delete=models.CASCADE)

    def __str__(self):
        return self.name
    

# Properties




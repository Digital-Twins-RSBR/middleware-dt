# Create your models here.

# gateway/models.py
import requests
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

    def __str__(self):
        return self.name

class Device(models.Model):
    name = models.CharField(max_length=255)
    identifier = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
    type = models.ForeignKey(DeviceType, on_delete=models.CASCADE, null=True)
    gateway = models.ForeignKey(GatewayIOT, related_name='devices', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='devices', on_delete=models.CASCADE)

    def __str__(self):
        return self.name
    
    class Meta:
        unique_together = ('identifier', 'gateway')


class Property(models.Model):
    TYPE_CHOICES = (("Boolean", "Boolean"), ("Integer", "Integer", ),("Double", "Double",))
    device = models.ForeignKey(Device, null=False, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    type = models.CharField(choices=TYPE_CHOICES)
    value = models.CharField(max_length=255)
    # rpc_methods = models.JSONField() {"read", "checkStatus", "write": "setStatus"}
    # Eu pensei em colocar uma regra que seria chamado em cima do value da propriedade
    # policies = models.CharField()
    
    class Meta:
        unique_together = ('device', 'name')

    def __str__(self):
        return f'{self.name} - {self.device}'
    
    def save(self, *args, **kwargs):
        mensagem = self.call_rpc()
        if mensagem != 'Ok':
            self.value = None
        else:
            print(mensagem)
        super().save(*args, **kwargs)


    def call_rpc(self):
        device = self.device
        gateway = device.gateway
        from facade.api import get_jwt_token_gateway
        token = get_jwt_token_gateway(None, gateway.id, gateway.user)
        url = f"{gateway.url}/api/plugins/rpc/oneway/{device.identifier}"
        headers = {
            "Content-Type": "application/json",
            "X-Authorization": f"Bearer {token}",
        }
        valor = self.value == 'True'
        response = requests.post(
            url, json={"method": "switchLed", "params": valor}, headers=headers
        )
        if response.status_code == 200:
            return 'Ok'
        return f'{response.text} - status code: {response.status_code}'

    
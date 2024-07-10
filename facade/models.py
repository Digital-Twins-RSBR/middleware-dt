# Create your models here.

# gateway/models.py
from decimal import Decimal
import requests
from django.db import models
from django.contrib.auth.models import User
from enum import Enum

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
#ENUM para definir os tipos de chamada. Pode trocar por uma estratégia melhor, se for o caso
class RPCCallTypes(Enum):
    READ=1
    WRITE=2

class Property(models.Model):
    TYPE_CHOICES = (("Boolean", "Boolean"), ("Integer", "Integer", ),("Double", "Double",))
    device = models.ForeignKey(Device, null=False, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    type = models.CharField(choices=TYPE_CHOICES)
    value = models.CharField(max_length=255, blank=True, default='')
    rpc_read_method=models.CharField(max_length=255,blank=True, default='') #Nome do RPC de leitura. Deve retornar um valor compatível com self.value
    rpc_write_method=models.CharField(max_length=255,blank=True, default='') #Nome 
    # rpc_methods = models.JSONField() {"read", "checkStatus", "write": "setStatus"}
    # Eu pensei em colocar uma regra que seria chamado em cima do value da propriedade
    # policies = models.CharField()
    
    class Meta:
        unique_together = ('device', 'name')

    def __str__(self):
        return f'{self.name} - {self.device}'
    
    def save(self, *args, **kwargs):
        mensagem = self.call_rpc(RPCCallTypes.WRITE) 
        if mensagem != 'Ok':
            self.value = ''
        else:
            print(mensagem)
        super().save(*args, **kwargs)

    #Para leitura, seria necessário criar um mecanismos no middleware para chamar de forma assincrona esse método de todas as instâncias
    def call_rpc(self,rpc_type:RPCCallTypes):
        device = self.device
        gateway = device.gateway
        from facade.api import get_jwt_token_gateway
        token = get_jwt_token_gateway(None, gateway.id, gateway.user)
        url = f"{gateway.url}/api/plugins/rpc/oneway/{device.identifier}"
        headers = {
            "Content-Type": "application/json",
            "X-Authorization": f"Bearer {token}",
        }

        #Quando salvar e se tiver método write, executa a chamada
        if (rpc_type is RPCCallTypes.WRITE and self.rpc_write_method):

            response = requests.post(
                url, json={"method": self.rpc_write_method, "params": self.get_value()}, headers=headers
            )
        else:
            response = requests.post(
                url, json={"method": self.rpc_read_method}, headers=headers
            )
            #Precisa alterar self.value com o retorno da leitura. Sendo que eu também preciso modficar o atributo value da instância do digital twin. Essa lógica pode ficar no procedimento de registrar as chamadas
        if response.status_code == 200:
            return 'Ok'
        return f'{response.text} - status code: {response.status_code}'
    
    def get_value(self):
        if self.type == 'Boolean':
            return True if self.value in ['True', 'true', True] else False
        elif self.type == 'Integer':
            return int(self.value)
        elif self.type == 'Double':
            return Decimal(self.value)
        else:
            return self.value
        
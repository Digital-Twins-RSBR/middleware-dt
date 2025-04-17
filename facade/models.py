# Create your models here.

# gateway/models.py
import time
from decimal import Decimal
import requests
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from enum import Enum

from core.models import GatewayIOT
# INFLUX configuration
INFLUXDB_HOST = settings.INFLUXDB_HOST
INFLUXDB_PORT = settings.INFLUXDB_PORT
INFLUXDB_BUCKET = settings.INFLUXDB_BUCKET
INFLUXDB_ORGANIZATION = settings.INFLUXDB_ORGANIZATION
INFLUXDB_URL = f"http://{INFLUXDB_HOST}:{INFLUXDB_PORT}/api/v2/write?org={INFLUXDB_ORGANIZATION}&bucket={INFLUXDB_BUCKET}&precision=ms"
INFLUXDB_TOKEN = settings.INFLUXDB_TOKEN

USE_INFLUX_TO_EVALUATE = settings.USE_INFLUX_TO_EVALUATE


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
    
    def write_influx(self):
        timestamp = int(time.time() * 1000)  #
        headers = {
                "Authorization": f"Token {INFLUXDB_TOKEN}",
                "Content-Type": "text/plain"
            }
        # Envia os dados para o InfluxDB registrando o evento
        valor = self.get_value()
        if self.type == 'Boolean':
            valor = int(valor)
        data = f"device_data,sensor={self.device.identifier},source=middts {self.name}={valor},sent_timestamp={timestamp} {timestamp}"
        response = requests.post(INFLUXDB_URL, headers=headers, data=data)
        print(f"Response Code: {response.status_code}, Response Text: {response.text}")
    
    def save(self, *args, **kwargs):
        old_value = ''
        if self.id:
            old_value = Property.objects.get(id=self.id).value
        response = self.call_rpc(RPCCallTypes.WRITE)
        success = response.status_code == 200
        if success:
            response_json = response.json()
            self.value = str(response_json.get(self.name))
        else:
            self.value = old_value
        super().save(*args, **kwargs)
        if success and USE_INFLUX_TO_EVALUATE and INFLUXDB_TOKEN:
            self.write_influx()
            

    #Para leitura, seria necessário criar um mecanismos no middleware para chamar de forma assincrona esse método de todas as instâncias
    def call_rpc(self,rpc_type:RPCCallTypes):
        device = self.device
        gateway = device.gateway
        from facade.api import get_jwt_token_gateway
        response, status_code = get_jwt_token_gateway(None, gateway.id)
        if status_code == 200:
            token = response['token']
            # urloneway = f"{gateway.url}/api/rpc/oneway/{device.identifier}"
            urltwoway = f"{gateway.url}/api/rpc/twoway/{device.identifier}"
            headers = {
                "Content-Type": "application/json",
                "X-Authorization": f"Bearer {token}",
            }

            #Quando salvar e se tiver método write, executa a chamada
            if rpc_type is RPCCallTypes.WRITE and self.rpc_write_method:

                response = requests.post(
                    urltwoway, json={"method": self.rpc_write_method, "params": self.get_value()}, headers=headers
                )
            elif rpc_type is RPCCallTypes.READ and self.rpc_read_method:
                response = requests.post(
                    urltwoway, json={"method": self.rpc_read_method}, headers=headers
                )
            status_code = response.status_code
            #Precisa alterar self.value com o retorno da leitura. Sendo que eu também preciso modficar o atributo value da instância do digital twin. Essa lógica pode ficar no procedimento de registrar as chamadas
        return response
    
    def get_value(self):
        if self.type == 'Boolean':
            return True if self.value in ['True', 'true', True] else False
        elif self.type == 'Integer':
            return int(self.value)
        elif self.type == 'Double':
            return Decimal(self.value)
        else:
            return self.value
        
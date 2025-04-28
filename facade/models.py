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
    inactivityTimeout = models.IntegerField(
        null=True, 
        blank=True, 
        help_text="Timeout in seconds for device inactivity",
        default=getattr(settings, 'DEFAULT_INACTIVITY_TIMEOUT', 60)
    )

    def save(self, *args, **kwargs):
        if self.inactivityTimeout is None:
            self.inactivityTimeout = getattr(settings, 'DEFAULT_INACTIVITY_TIMEOUT', 60)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Device(models.Model):
    name = models.CharField(max_length=255)
    identifier = models.CharField(max_length=255)
    status = models.CharField(max_length=255)
    type = models.ForeignKey(DeviceType, on_delete=models.CASCADE, null=True)
    gateway = models.ForeignKey(GatewayIOT, related_name='devices', on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='devices', on_delete=models.CASCADE)
    inactivityTimeout = models.IntegerField(null=True, blank=True, help_text="Timeout in seconds for device inactivity. Overrides type's timeout")

    def __str__(self):
        return self.name
    
    class Meta:
        unique_together = ('identifier', 'gateway')

    def get_inactivity_timeout(self):
        """Returns the effective inactivity timeout for this device"""
        if self.inactivityTimeout is not None:
            return self.inactivityTimeout
        if self.type and self.type.inactivityTimeout is not None:
            return self.type.inactivityTimeout
        return None

    def sync_inactivity_timeout(self):
        """Syncs the inactivity timeout with ThingsBoard"""
        timeout = self.get_inactivity_timeout()
        if timeout is None:
            return  # Let ThingsBoard handle default timeout
            
        from facade.api import get_jwt_token_gateway
        response, status_code = get_jwt_token_gateway(None, self.gateway.id)
        
        if status_code == 200:
            token = response['token']
            url = f"{self.gateway.url}/api/plugins/telemetry/DEVICE/{self.identifier}/SERVER_SCOPE"
            headers = {
                "Content-Type": "application/json",
                "X-Authorization": f"Bearer {token}",
            }
            
            # Format payload as a dictionary
            payload = {
                "inactivityTimeout": str(timeout)  # Convert to string as ThingsBoard expects string values
            }
            
            try:
                response = requests.post(url, json=payload, headers=headers)
                if response.status_code != 200:
                    print(f"Failed to sync inactivity timeout for device {self.name}: {response.text}")
                return response.status_code == 200
            except Exception as e:
                print(f"Error syncing inactivity timeout for device {self.name}: {str(e)}")
                return False
        return False

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new or self.inactivityTimeout is not None:
            self.sync_inactivity_timeout()
    
#ENUM para definir os tipos de chamada. Pode trocar por uma estratégia melhor, se for o caso
class RPCCallTypes(Enum):
    READ=1
    WRITE=2

class InactivityType(Enum):
    DEVICE_INACTIVE = "device_inactive"  # Dispositivo marcado como inativo no ThingsBoard
    CONNECTION_ERROR = "connection_error"  # Erro de conexão com ThingsBoard
    TIMEOUT = "timeout"  # Tempo limite excedido sem resposta

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

def write_inactivity_event(device, inactivity_type: InactivityType, error_message=None):
    """
    Write device inactivity events to InfluxDB with proper formatting
    """
    if not USE_INFLUX_TO_EVALUATE or not INFLUXDB_TOKEN:
        return
        
    timestamp = int(time.time() * 1000)
    headers = {
        "Authorization": f"Token {INFLUXDB_TOKEN}",
        "Content-Type": "text/plain"
    }
    
    # Get timeout value, default to 0 if None
    timeout = device.get_inactivity_timeout() or 0
    
    # Build tags section - move type to tags for better querying
    tags = [
        f"device={device.identifier}",
        f"type={inactivity_type.value}"
    ]
    
    # Build fields section - use numeric fields for aggregation
    fields = [
        f"inactivity_timeout={timeout}i",
        "status=1i"  # Numeric status field for aggregation
    ]
    
    if error_message:
        escaped_message = error_message.replace('"', '\\"')
        fields.append(f'error_message="{escaped_message}"')
    
    # Construct measurement in proper InfluxDB line protocol format:
    # <measurement>,<tags> <fields> <timestamp>
    measurement = f"device_inactivity,{','.join(tags)} {','.join(fields)} {timestamp}"
    
    try:
        response = requests.post(INFLUXDB_URL, headers=headers, data=measurement)
        if response.status_code != 204:
            print(f"Failed to write inactivity event: {response.text}")
            print(f"Attempted measurement: {measurement}")
    except Exception as e:
        print(f"Error writing to InfluxDB: {str(e)}")

# Create your models here.

# gateway/models.py
import time
import os
from decimal import Decimal
import requests
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from enum import Enum
from facade.utils import format_influx_line, get_session_for_gateway
import traceback

from core.models import GatewayIOT
# INFLUX configuration
INFLUXDB_HOST = settings.INFLUXDB_HOST
INFLUXDB_PORT = settings.INFLUXDB_PORT
INFLUXDB_BUCKET = settings.INFLUXDB_BUCKET
INFLUXDB_ORGANIZATION = settings.INFLUXDB_ORGANIZATION
INFLUXDB_URL = f"http://{INFLUXDB_HOST}:{INFLUXDB_PORT}/api/v2/write?org={INFLUXDB_ORGANIZATION}&bucket={INFLUXDB_BUCKET}&precision=ms"
INFLUXDB_TOKEN = settings.INFLUXDB_TOKEN

USE_INFLUX_TO_EVALUATE = settings.USE_INFLUX_TO_EVALUATE

# Session helper moved to facade.utils.get_session_for_gateway


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
    metadata = models.TextField(blank=True, default='')  # Novo campo para armazenar metadados dos labels do ThingsBoard

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

    def sync_properties_from_thingsboard(self):
        """
        Busca atributos compartilhados do ThingsBoard e cria/atualiza Properties locais.
        Tenta GET em /api/plugins/telemetry/DEVICE/{deviceId}/SHARED_SCOPE e,
        se falhar, tenta POST em /api/plugins/telemetry/DEVICE/{deviceId}/values/attributes/SHARED_SCOPE.
        """
        from facade.api import get_jwt_token_gateway
        response, status_code = get_jwt_token_gateway(None, self.gateway.id)
        if status_code != 200:
            print(f"Erro ao obter token JWT para gateway {self.gateway}: {response}")
            return

        token = response['token']
        headers = {
            "Content-Type": "application/json",
            "X-Authorization": f"Bearer {token}",
        }
        # 1. Tenta GET (ThingsBoard padrão para shared attributes)
        url_get = f"{self.gateway.url}/api/plugins/telemetry/DEVICE/{self.identifier}/values/attributes/SHARED_SCOPE"
        try:
            resp = requests.get(url_get, headers=headers)
            if resp.status_code == 200:
                shared_attrs = resp.json()
                for attr in shared_attrs:
                    if attr.get("key") == "properties" and isinstance(attr.get("value"), dict):
                        props = attr["value"]
                        for prop_name, prop_data in props.items():
                            if not isinstance(prop_data, dict):
                                continue
                            defaults = {
                                "type": prop_data.get("type", "Boolean"),
                                "rpc_read_method": prop_data.get("rpc_read_method", ""),
                                "rpc_write_method": prop_data.get("rpc_write_method", ""),
                            }
                            Property.objects.update_or_create(
                                device=self,
                                name=prop_name,
                                defaults=defaults
                            )
        except Exception as e:
            print(f"Erro ao sincronizar propriedades do ThingsBoard: {str(e)}")

    def sync_metadata_from_thingsboard(self):
        """
        Busca os labels do ThingsBoard e popula o campo metadata.
        """
        from facade.api import get_jwt_token_gateway
        response, status_code = get_jwt_token_gateway(None, self.gateway.id)
        if status_code != 200:
            print(f"Erro ao obter token JWT para gateway {self.gateway}: {response}")
            return

        token = response['token']
        url = f"{self.gateway.url}/api/device/{self.identifier}"
        headers = {
            "Content-Type": "application/json",
            "X-Authorization": f"Bearer {token}",
        }
        try:
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                device_data = resp.json()
                # O ThingsBoard armazena labels em 'label' ou 'labels' (verifique conforme sua configuração)
                labels = device_data.get('label') or device_data.get('labels')
                if isinstance(labels, dict):
                    # Serializa dict para string
                    self.metadata = " ".join(f"{k}:{v}" for k, v in labels.items())
                elif isinstance(labels, list):
                    self.metadata = " ".join(str(l) for l in labels)
                elif isinstance(labels, str):
                    self.metadata = labels
                else:
                    self.metadata = ""
                super().save(update_fields=['metadata'])
            else:
                print(f"Erro ao buscar labels do ThingsBoard: {resp.text}")
        except Exception as e:
            print(f"Erro ao sincronizar labels do ThingsBoard: {str(e)}")

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        # Se não houver nenhuma propriedade associada, busca do ThingsBoard e cria
        if not Property.objects.filter(device=self).exists():
            self.sync_properties_from_thingsboard()
        # Sempre busca e atualiza metadados dos labels
        self.sync_metadata_from_thingsboard()
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
        key = self.name
        valor = self.get_value()
        # Normalize boolean/integer values to numeric floats to avoid Influx type conflicts
        if self.type == 'Boolean' or self.type == 'Integer':
            try:
                ival = int(valor)
            except Exception:
                if self.type == 'Boolean':
                    ival = 1 if str(valor).lower() in ('true', '1', 'yes') else 0
                else:
                    try:
                        ival = int(float(valor))
                    except Exception:
                        ival = 0
            # Use float representation (e.g., 1.0) to maintain consistent field type
            valor = float(ival)
        # Prefer ThingsBoard internal id (thingsboard_id) when available to avoid conflicts
        sensor_id = self.device.identifier
        tags = {"sensor": sensor_id, "source": "middts"}
        fields = {key: valor, "sent_timestamp": timestamp}
        data = format_influx_line("device_data", tags, fields, timestamp=timestamp)
        response = requests.post(INFLUXDB_URL, headers=headers, data=data)
        print(f"Response Code: {response.status_code}, Response Text: {response.text} - Data Sent: {data}")
    
    def save(self, *args, **kwargs):
        old_value = ''
        if self.id:
            old_value = Property.objects.get(id=self.id).value
        success = False
        if self.rpc_write_method:
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
                # Record sent_timestamp to Influx immediately when issuing a WRITE RPC.
                # This ensures we have a sent_timestamp even if the RPC response code
                # is not 200 or if other code paths don't trigger Property.write_influx().
                try:
                    if USE_INFLUX_TO_EVALUATE and INFLUXDB_TOKEN:
                        try:
                            send_ts = int(time.time() * 1000)
                            sensor_id = device.identifier
                            tags = {"sensor": sensor_id, "source": "middts"}
                            # Normalize value similar to write_influx to avoid type conflicts
                            field_value = self.get_value()
                            if self.type == 'Boolean' or self.type == 'Integer':
                                try:
                                    ival = int(field_value)
                                except Exception:
                                    if self.type == 'Boolean':
                                        ival = 1 if str(field_value).lower() in ('true', '1', 'yes') else 0
                                    else:
                                        try:
                                            ival = int(float(field_value))
                                        except Exception:
                                            ival = 0
                                # use float representation for consistency
                                field_value = float(ival)
                            fields = {self.name: field_value, "sent_timestamp": send_ts}
                            measurement = format_influx_line("device_data", tags, fields, timestamp=send_ts)
                            # best-effort POST, ignore failures (we still attempt the RPC)
                            try:
                                _resp = requests.post(INFLUXDB_URL, headers={"Authorization": f"Token {INFLUXDB_TOKEN}", "Content-Type": "text/plain"}, data=measurement, timeout=2)
                            except Exception:
                                pass
                        except Exception:
                            # non-fatal: continue to issue RPC
                            pass
                except Exception:
                    # keep RPC path functioning even if Influx recording fails
                    pass

                # Use a session with retries and a larger timeout for POST
                try:
                    session = get_session_for_gateway(gateway.id)
                    response = session.post(
                        urltwoway, json={"method": self.rpc_write_method, "params": self.get_value()}, headers=headers, timeout=8
                    )
                except requests.exceptions.ReadTimeout as te:
                    # Log and return a pseudo-response indicating timeout so callers can handle it
                    print(f"RPC timeout when calling {self.rpc_write_method} for device {device.identifier}: {te}")
                    class _R:
                        status_code = 504
                        text = str(te)
                    return _R()
                except Exception as e:
                    # For generic RPC errors, log traceback and return a 503-like pseudo-response
                    print(f"RPC error when calling {self.rpc_write_method} for device {device.identifier}: {e}")
                    traceback.print_exc()
                    class _R:
                        status_code = 503
                        text = str(e)
                    return _R()
            elif rpc_type is RPCCallTypes.READ and self.rpc_read_method:
                try:
                    session = get_session_for_gateway(gateway.id)
                    response = session.post(
                        urltwoway, json={"method": self.rpc_read_method}, headers=headers, timeout=6
                    )
                except requests.exceptions.ReadTimeout as te:
                    print(f"RPC read timeout when calling {self.rpc_read_method} for device {device.identifier}: {te}")
                    class _R:
                        status_code = 504
                        text = str(te)
                    return _R()
                except Exception as e:
                    print(f"RPC read error when calling {self.rpc_read_method} for device {device.identifier}: {e}")
                    traceback.print_exc()
                    class _R:
                        status_code = 503
                        text = str(e)
                    return _R()
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
    
    # Build fields section - use numeric floats for aggregation
    fields = [
        f"inactivity_timeout={float(int(timeout))}",
        f"status={float(1.0)}"
    ]
    
    if error_message:
        escaped_message = error_message.replace('"', '\\"')
        fields.append(f'error_message="{escaped_message}"')
    
    # Construct measurement in proper InfluxDB line protocol format using helper
    tags_dict = {"device": device.identifier, "type": inactivity_type.value}
    # Use numeric floats for fields to avoid conflicts (Influx will store as float)
    fields_dict = {"inactivity_timeout": float(int(timeout)), "status": float(1.0)}
    if error_message:
        fields_dict["error_message"] = error_message
    measurement = format_influx_line("device_inactivity", tags_dict, fields_dict, timestamp=timestamp)
    try:
        response = requests.post(INFLUXDB_URL, headers=headers, data=measurement)
        if response.status_code != 204:
            print(f"Failed to write inactivity event: {response.text}")
            print(f"Attempted measurement: {measurement}")
    except Exception as e:
        print(f"Error writing to InfluxDB: {str(e)}")

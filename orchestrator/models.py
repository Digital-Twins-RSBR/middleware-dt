from typing import Iterable
from django.db import models
from django.forms import JSONField

from facade.models import Device, Property,RPCCallTypes
import time
# models.py

class ParserClient(models.Model):
    name = models.CharField(max_length=255)
    url = models.CharField(max_length=255) # /api/DTDLModels/parse

    def __str__(self):
        return self.name

class DTDLModel(models.Model): # ModelParsed
    name = models.CharField(max_length=255)
    specification = models.JSONField() # Ler id para preencher o body da requisição
    parser_client = models.ForeignKey(ParserClient, on_delete=models.CASCADE)

    @classmethod
    def create_dtdl_model_parsed(cls, json_specification):
        dtdl_model, created = DTDLModelParsed.objects.update_or_create(
            dtdl_id=json_specification['id'],
            defaults={'name': json_specification['name'], 'specification' : json_specification}
        )
        for element_data in json_specification['modelElements']:
            ModelElement.objects.update_or_create(
                dtdl_parsed=dtdl_model,
                element_id=element_data['id'],
                defaults={
                    'element_type': element_data['type'],
                    'name': element_data['name'],
                    'schema': element_data.get('schema'),
                    'supplement_types': element_data.get('supplementTypes', [])
                }
            )
        for relationship_data in json_specification['modelRelationships']:
            ModelRelationship.objects.update_or_create(
                dtdl_parsed=dtdl_model,
                relationship_id=relationship_data['id'],
                defaults={
                    'name': relationship_data['name'],
                    'target': relationship_data['target']
                }
            )

class DTDLModelParsed(models.Model): # ModelParsed
    dtdl_id = models.CharField(max_length=255, unique=True)
    specification = models.JSONField()
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name
    
    def reload_model_parsed(self):
        DTDLModel.create_dtdl_model_parsed(self.specification)

class ModelElement(models.Model):
    dtdl_parsed = models.ForeignKey(DTDLModelParsed, related_name='model_elements', on_delete=models.CASCADE)
    element_id = models.IntegerField()
    element_type = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    schema = models.CharField(max_length=50, blank=True, null=True)
    supplement_types = models.JSONField(blank=True, null=True)

    def __str__(self):
        return self.name

class ModelRelationship(models.Model):
    dtdl_parsed = models.ForeignKey(DTDLModelParsed, related_name='model_relationships', on_delete=models.CASCADE)
    relationship_id = models.IntegerField()
    name = models.CharField(max_length=255)
    target = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class DigitalTwinInstance(models.Model):
    model = models.ForeignKey(DTDLModelParsed, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.model.name} - {self.id}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
                

class DigitalTwinInstanceProperty(models.Model):
    dtinstance = models.ForeignKey(DigitalTwinInstance, on_delete=models.CASCADE)
    property = models.CharField(max_length=255)
    # Adicionar Causal do Device
    causal = models.BooleanField(default=False)
    #Adicioando a propriedade schema, que é o tipo. Ela está em ModelElement.Schema
    schema=models.CharField(max_length=255)
    value = models.CharField(max_length=255, blank=True)
    device_property = models.ForeignKey(Property, on_delete=models.CASCADE, null=True)

    #Avaliar de colocar o registro no ThreadManager no __init__ ou em outro local
    
    def __str__(self):
        return f"{self.dtinstance}({self.device_property.device.name}) {self.property} {'(Causal)' if self.causal else ''} {self.value}"
    
    class Meta:
        unique_together = ('dtinstance', 'property', 'device_property')

    def save(self, *args, **kwargs):
        if self.id and self.causal and self.device_property:
            old = DigitalTwinInstanceProperty.objects.get(pk=self.id)
            if self.value != old.value:
                try:
                    device_property = self.device_property
                    device_property.value=self.value
                    device_property.save()
                except:
                    self.value = old.value
        super().save(*args, **kwargs)

    def periodic_read_call(self,interval=5):
        while True:
            self.device_property.call_rpc(RPCCallTypes.READ)
            self.value=self.device_property.value
            time.sleep(interval)
    
    @classmethod
    def periodic_read_call(cls, pk, interval=5):
        while True:
            dtinstanceproperty = DigitalTwinInstanceProperty.objects.filter(pk=pk).first()
            dtinstanceproperty.device_property.call_rpc(RPCCallTypes.READ)
            dtinstanceproperty.value=dtinstanceproperty.device_property.value
            time.sleep(interval)
# [
#     {
#       "id": "dtmi:housegen:Room;1",
#       "name": "Room",
#       "modelElements": [
#         {
#           "id": 1,
#           "type": "Property",
#           "name": "size",
#           "schema": "Double",
#           "supplementTypes": [
#             "dtmi:dtdl:extension:quantitativeTypes:v1:class:Area"
#           ]
#         },
#         {
#           "id": 2,
#           "type": "Telemetry",
#           "name": "temperature",
#           "schema": "Double",
#           "supplementTypes": [
#             "dtmi:dtdl:extension:quantitativeTypes:v1:class:Temperature"
#           ]
#         }
#       ],
#       "modelRelationships": [
#         {
#           "id": 1,
#           "name": "lights",
#           "target": "dtmi:housegen:LightBulb;1"
#         },
#         {
#           "id": 2,
#           "name": "airconditioner",
#           "target": "dtmi:housegen:AirConditioner;1"
#         }
#       ]
#     },
#     {
#       "id": "dtmi:housegen:LightBulb;1",
#       "name": "LightBulb",
#       "modelElements": [
#         {
#           "id": 3,
#           "type": "Property",
#           "name": "status",
#           "schema": "Boolean",
#           "supplementTypes": [
#             "dtmi:dtdl:extension:causal:v1:Causal"
#           ]
#         }
#       ],
#       "modelRelationships": []
#     },
#     {
#       "id": "dtmi:housegen:House;1",
#       "name": "House",
#       "modelElements": [
#         {
#           "id": 4,
#           "type": "Property",
#           "name": "Name",
#           "schema": "String",
#           "supplementTypes": []
#         },
#         {
#           "id": 5,
#           "type": "Property",
#           "name": "Address",
#           "schema": "String",
#           "supplementTypes": []
#         }
#       ],
#       "modelRelationships": [
#         {
#           "id": 3,
#           "name": "rooms",
#           "target": "dtmi:housegen:Room"
#         }
#       ]
#     },
#     {
#       "id": "dtmi:housegen:AirConditioner;1",
#       "name": "AirConditioner",
#       "modelElements": [
#         {
#           "id": 6,
#           "type": "Property",
#           "name": "temperature",
#           "schema": "Double",
#           "supplementTypes": [
#             "dtmi:dtdl:extension:causal:v1:Causal"
#           ]
#         },
#         {
#           "id": 7,
#           "type": "Property",
#           "name": "status",
#           "schema": "Boolean",
#           "supplementTypes": [
#             "dtmi:dtdl:extension:causal:v1:Causal"
#           ]
#         }
#       ],
#       "modelRelationships": []
#     }
#   ]
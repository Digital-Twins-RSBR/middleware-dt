from django.db import models

# Create your models here.
# Modelos
# Instancias

# models.py

class DTDLModel(models.Model):
    dtdl_id = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class ModelElement(models.Model):
    dtdl_model = models.ForeignKey(DTDLModel, related_name='model_elements', on_delete=models.CASCADE)
    element_id = models.IntegerField()
    element_type = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    schema = models.CharField(max_length=50, blank=True, null=True)
    supplement_types = models.JSONField(blank=True, null=True)

    def __str__(self):
        return self.name

class ModelRelationship(models.Model):
    dtdl_model = models.ForeignKey(DTDLModel, related_name='model_relationships', on_delete=models.CASCADE)
    relationship_id = models.IntegerField()
    name = models.CharField(max_length=255)
    target = models.CharField(max_length=255)

    def __str__(self):
        return self.name


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
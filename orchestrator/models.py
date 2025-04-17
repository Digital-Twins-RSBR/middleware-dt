from enum import unique
from pickle import FALSE
from typing import Iterable
from django.db import IntegrityError, models
import requests
from requests.exceptions import RequestException

from core.models import DTDLParserClient
from facade.models import Device, Property, RPCCallTypes
import time

# models.py


class SystemContext(models.Model): 
    name = models.CharField(max_length=255)
    description = models.TextField()

    class Meta:
        verbose_name = "System context"
        verbose_name_plural = "System contexts"
    
    def __str__(self):
        return self.name


class DTDLModel(models.Model):
    system = models.ForeignKey(SystemContext, on_delete=models.CASCADE)
    dtdl_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    specification = models.JSONField()
    parsed_specification = models.JSONField(null=True, blank=True)

    class Meta:
        verbose_name = "DTDL model"
        verbose_name_plural = "DTDL models"
        unique_together = ('system', 'dtdl_id')

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        create_parsed_specification = False
        if not self.pk or not self.parsed_specification:
            create_parsed_specification = True
        if self.pk:
            old_specification = DTDLModel.objects.filter(pk=self.pk).first().specification
            if self.specification != old_specification:
                create_parsed_specification = True
        if create_parsed_specification:
            self.create_parsed_specification()
        specification = self.specification
        self.dtdl_id = specification.get('@id')
        super().save(*args, **kwargs)
        self.create_dtdl_models()


    def create_parsed_specification(self):
        specification = self.specification
        spec_id = specification.get('@id')
        if not spec_id:
            raise ValueError(f"Model {self.name} has no '@id' in its specification.")
        payload = {
            "id": spec_id,
            "specification": specification
        }
        parser_client = DTDLParserClient.get_active()
        parser_url = parser_client.url
        try:
            response = requests.post(parser_url, json=payload)
            response.raise_for_status()  # Levanta um erro se o status code for 4xx/5xx
        except RequestException as e:
            # Logar o erro aqui, por exemplo:
            # logger.error(f"Failed to communicate with DTDL parser: {e}")
            raise ConnectionError(f"Failed to communicate with DTDL parser at {parser_url}: {e}")
        try:
            parsed_data = response.json()
        except ValueError:
            # Quando a resposta não é JSON ou está malformada
            raise ValueError(f"Failed to parse JSON response from DTDL parser at {parser_url}")

        self.parsed_specification = parsed_data
        return self

    def create_dtdl_models(self):
        for element_data in self.parsed_specification.get('modelElements', []):
            ModelElement.objects.update_or_create(
                dtdl_model=self,
                element_id=element_data['id'],
                defaults={
                    'element_type': element_data['type'],
                    'name': element_data['name'],
                    'schema': element_data.get('schema'),
                    'supplement_types': element_data.get('supplementTypes', [])
                }
            )
        # Criar ou atualizar relacionamentos do modelo
        for relationship_data in self.parsed_specification.get('modelRelationships', []):
            # Extraia os identificadores de origem e destino
            target_id = relationship_data.get('target')  # Deve ser o ID do modelo de destino
            
            # Busque o modelo de origem e destino baseado no ID fornecido
            source_model = DTDLModel.objects.filter(dtdl_id=self.dtdl_id).first()
            target_model = DTDLModel.objects.filter(dtdl_id__icontains=target_id).first()

            if source_model and target_model:
                # Cria ou atualiza o relacionamento entre os modelos
                try:
                    ModelRelationship.objects.update_or_create(
                        dtdl_model=self,
                        relationship_id= relationship_data['id'],
                        defaults={
                            'name': relationship_data['name'],
                            'source': self.dtdl_id,
                            'target': target_id,
                        }
                    )
                except IntegrityError:
                    existing_relationship = ModelRelationship.objects.get(
                        dtdl_model=self,
                        name=relationship_data['name'],
                        source=self.dtdl_id,
                        target=target_id
                    )
                    existing_relationship.relationship_id = relationship_data['id']
                    existing_relationship.save()
            else:
                # Caso não encontre o source_model ou target_model, pode-se logar ou levantar um erro
                print(f"Warning: Unable to find source or target models for relationship {relationship_data['id']}")

    # def reload_model_parsed(self):
    #     DTDLModel.create_dtdl_model_parsed_from_json(self, self.parsed_specification)
    
    def create_dt_instance(self, ):
        dt_instance = DigitalTwinInstance.objects.create(model=self)
        for element in self.model_elements.all():
            dti, created = DigitalTwinInstanceProperty.objects.update_or_create(
                dtinstance=dt_instance, 
                property=element
            )

        for relationship in self.model_relationships.all():
            source_instance = DigitalTwinInstance.objects.filter(model__name=relationship.source).first()
            target_instance = DigitalTwinInstance.objects.filter(model__name=relationship.target).first()
            if source_instance and target_instance:
                DigitalTwinInstanceRelationship.objects.update_or_create(
                    source_instance=source_instance,
                    target_instance=target_instance,
                    relationship=relationship
                )
        return dt_instance


class ModelElement(models.Model):
    dtdl_model = models.ForeignKey(DTDLModel, related_name='model_elements', on_delete=models.CASCADE)
    element_id =  models.CharField(max_length=255)
    element_type = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    schema = models.CharField(max_length=50, blank=True, null=True)
    supplement_types = models.JSONField(blank=True, null=True)

    class Meta:
        verbose_name = "Model element"
        verbose_name_plural = "Model elements"

    def __str__(self):
        return f'{self.name} - {self.dtdl_model.name}'
    
    def isCausal(self):
        if self.supplement_types:
            return "dtmi:dtdl:extension:causal:v1:Causal" in self.supplement_types
        return False

class ModelRelationship(models.Model):
    dtdl_model = models.ForeignKey(DTDLModel, related_name='model_relationships', on_delete=models.CASCADE)
    relationship_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    source = models.CharField(max_length=255)
    target = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Model relationship"
        verbose_name_plural = "Model relationships"
        unique_together = ('dtdl_model','name', 'source', 'target')

    def __str__(self):
        return self.name


class DigitalTwinInstance(models.Model):
    model = models.ForeignKey(DTDLModel, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Digital twin instance"
        verbose_name_plural = "Digital twins instances"

    def __str__(self):
        return f"{self.model.name} - {self.id}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        model = self.model
        for element in model.model_elements.all():
            DigitalTwinInstanceProperty.objects.update_or_create(dtinstance=self, property=element)
        for relationship in model.model_relationships.all():
            source_instance = DigitalTwinInstance.objects.filter(model=relationship.dtdl_model).first()
            target_instance = DigitalTwinInstance.objects.filter(model__dtdl_id__icontains=relationship.target).first()

            if source_instance and target_instance:
                DigitalTwinInstanceRelationship.objects.update_or_create(
                    source_instance=source_instance,
                    target_instance=target_instance,
                    relationship=relationship
                )

# Ajustando para que faça referência a model element
class DigitalTwinInstanceProperty(models.Model):
    dtinstance = models.ForeignKey(DigitalTwinInstance, on_delete=models.CASCADE)
    property = models.ForeignKey(ModelElement,on_delete=models.CASCADE)
    value = models.CharField(max_length=255, blank=True)
    device_property = models.ForeignKey(Property, on_delete=models.CASCADE, null=True)


    def __str__(self):
        return f"{self.dtinstance}({self.device_property.device.name if self.device_property else 'Sem dispositivo'}) {self.property} {'(Causal)' if self.property.isCausal() else ''} {self.value}"
    
    class Meta:
        unique_together = ('dtinstance', 'property', 'device_property')
        verbose_name = "Digital twin instance property"
        verbose_name_plural = "Digital twin instances properties"

    def save(self, *args, **kwargs):
        if not self.device_property:
            if self.property.isCausal():
                self.device_property = Property.objects.filter(device__name=self.property.dtdl_model.name, name=self.property.name, type=self.property.schema).first()
        old_value = DigitalTwinInstanceProperty.objects.get(pk=self.id).value if self.id else ''
        super().save(*args, **kwargs)
        if self.id and self.device_property and self.property.isCausal():
            device_property = self.device_property
            device_property.value = self.value
            device_property.save()
            if device_property.value != self.value:
                self.value = old_value if old_value else device_property.value if device_property.value else ''
                super().save(*args, **kwargs)

    def causal(self):
        return self.property.isCausal()

    @classmethod
    def periodic_read_call(cls, pk, interval=5):
        while True:
            dtinstanceproperty = DigitalTwinInstanceProperty.objects.filter(pk=pk).first()
            dtinstanceproperty.device_property.call_rpc(RPCCallTypes.READ)
            dtinstanceproperty.value=dtinstanceproperty.device_property.value
            time.sleep(interval)

class DigitalTwinInstanceRelationship(models.Model):
    source_instance = models.ForeignKey(DigitalTwinInstance, related_name='source_relationships', on_delete=models.CASCADE)
    target_instance = models.ForeignKey(DigitalTwinInstance, related_name='target_relationships', on_delete=models.CASCADE)
    relationship = models.ForeignKey(ModelRelationship, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Digital twin instance relationship"
        verbose_name_plural = "Digital twin instance relationships"
        unique_together = ('source_instance', 'target_instance', 'relationship')

    def __str__(self):
        return f"Relationship {self.relationship} from {self.source_instance} to {self.target_instance}"

    def clean(self):
        # Verify if the relationship is allowed between the models
        source_model = self.source_instance.model
        target_model = self.target_instance.model
        allowed_relationships = source_model.model_relationships.filter(relationship_id=self.relationship.relationship_id)
        if not allowed_relationships.exists():
            raise ValueError(f"Relationship from {source_model.name} to {target_model.name} is not allowed according to the DTDL models.")
        super().clean()

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
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

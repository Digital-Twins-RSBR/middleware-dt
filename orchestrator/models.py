from enum import unique
from pickle import FALSE
from typing import Iterable
from django.db import IntegrityError, models
import requests
from requests.exceptions import RequestException
from sentence_transformers import SentenceTransformer, util

from core.models import DTDLParserClient
from facade.models import Device, Property, RPCCallTypes
import time

from orchestrator.utils import normalize_name

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
        DigitalTwinInstanceProperty.associate_all_for_instance(dt_instance)
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
    name = models.CharField(max_length=255, blank=True, default='')
    active = models.BooleanField(default=True)
    last_status_check = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Digital twin instance"
        verbose_name_plural = "Digital twins instances"
        # unique_together = ('model', 'name')  # Garante unicidade do nome por modelo

    def __str__(self):
        base = f"{self.model.name} - {self.id} ({'Active' if self.active else 'Inactive'})"
        return f"{base} - {self.name}" if self.name else base

    def save(self, *args, **kwargs):
        # Se name não foi definido, gera automaticamente: <ModelName> <N>
        if not self.name:
            # Busca instâncias existentes para este modelo
            existing_names = (
                DigitalTwinInstance.objects
                .filter(model=self.model)
                .values_list('name', flat=True)
            )
            # Busca nomes no formato "<ModelName> <N>"
            import re
            pattern = re.compile(rf"^{re.escape(self.model.name)} (\d+)$")
            used_numbers = [
                int(m.group(1))
                for n in existing_names
                if (m := pattern.match(n or ""))
            ]
            next_number = max(used_numbers, default=0) + 1
            self.name = f"{self.model.name} {next_number}"
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

    def get_hierarchy(self):
        """
        Retorna a hierarquia de nomes do Digital Twin, do topo até este.
        Exemplo: ['House 77', 'Room 1', 'AirConditioner1_77']
        """
        names = []
        current = self
        visited = set()
        while current and current.id not in visited:
            visited.add(current.id)
            if current.name:
                names.append(current.name)
            parent_rel = DigitalTwinInstanceRelationship.objects.filter(target_instance=current).first()
            if parent_rel:
                current = parent_rel.source_instance
            else:
                break
        return list(reversed(names))

# Ajustando para que faça referência a model element
class DigitalTwinInstanceProperty(models.Model):

    dtinstance = models.ForeignKey(DigitalTwinInstance, on_delete=models.CASCADE)
    property = models.ForeignKey(ModelElement,on_delete=models.CASCADE)
    value = models.CharField(max_length=255, blank=True)
    device_property = models.ForeignKey(Property, on_delete=models.CASCADE, null=True)


    def __str__(self):
        return f"{self.dtinstance}({self.device_property.device.name if self.device_property else 'Sem dispositivo'}) {self.property} {'(Causal)' if self.property.isCausal() else ''} {self.value}"
    
    class Meta:
        # Ensure uniqueness per dtinstance + property. device_property may be nullable and
        # should not cause duplicate logical properties when associating devices.
        unique_together = ('dtinstance', 'property')
        verbose_name = "Digital twin instance property"
        verbose_name_plural = "Digital twin instances properties"


    def suggest_device_binding(self):
        if self.device_property is not None:
            return  # já está associado

        # Define modelo semântico
        model = SentenceTransformer("all-MiniLM-L6-v2")

        def extract_root_context(hierarchy):
            # Retorna o primeiro elemento da hierarquia, se existir
            return hierarchy[0].strip().lower() if hierarchy else None

        # Monta texto do digital twin property com contexto hierárquico
        hierarchy = self.get_hierarchy()
        norm_hierarchy = [normalize_name(h) for h in hierarchy]
        dt_text = " ".join(norm_hierarchy + [normalize_name(self.dtinstance.model.name), normalize_name(self.property.schema or "")])
        dt_root_context = extract_root_context(norm_hierarchy)

        dt_embedding = model.encode(dt_text, convert_to_tensor=True)

        best_device_text = ''
        best_match = None
        best_score = 0.0

        # Busca dispositivos sem associação

        for property in Property.objects.filter(digitaltwininstanceproperty__isnull=True):
            metadata = property.device.metadata or ""
            # Normaliza device name e extrai contexto
            device_name_norm = normalize_name(property.device.name)
            device_type_norm = normalize_name(property.device.type.name) if property.device.type else ''
            property_name_norm = normalize_name(property.name)
            property_type_norm = normalize_name(str(property.type))
            metadata_norm = normalize_name(metadata)
            # Extrai tokens do device name normalizado
            device_hierarchy_tokens = device_name_norm.split()
            # Descobre quantos tokens tem o root do DT (ex: 'house 1' -> 2 tokens)
            dt_root_tokens = dt_root_context.split() if dt_root_context else []
            num_root_tokens = len(dt_root_tokens)
            device_root_context = " ".join(device_hierarchy_tokens[:num_root_tokens]) if num_root_tokens > 0 else None

            # Só compara semanticamente se o contexto-raiz for igual
            if dt_root_context and device_root_context and dt_root_context != device_root_context:
                continue

            # device_text inclui device name, type, metadata, property name/type
            device_text = f"{device_name_norm} {device_type_norm} {metadata_norm} {property_name_norm} {property_type_norm}"

            device_embedding = model.encode(device_text, convert_to_tensor=True)
            score = float(util.cos_sim(dt_embedding, device_embedding)[0][0])

            # Debug: printa o score de todos os devices
            # print(f"[MIDDTS][DEBUG] DT: '{dt_text}' vs Device: '{device_text}' = {score:.4f}")

            if score > best_score:
                best_device_text = device_text
                best_match = property
                best_score = score
        if best_match and best_score >= 0.60:
            self.device_property = best_match
            print(f"[MIDDTS] Associação automática: '{self.property.name}' (DT: {dt_text}) → '{best_match.name}' (Device: {best_device_text}) (score: {best_score:.2f})")

    def save(self, *args, **kwargs):
        import time
        from datetime import datetime
        
        save_start = time.time()
        property_name = getattr(self.property, 'name', f'prop_{getattr(self, "id", "new")}')
        print(f"[{datetime.now().isoformat()}] 💾 SAVE START: Property '{property_name}' (DT: {getattr(self.dtinstance, 'id', 'unknown')})")
        
        # Allow callers to opt-out of propagating the DT property change to the
        # associated device/ThingsBoard. This avoids blocking network calls in
        # high-frequency/periodic updaters (e.g. update_causal_property).
        propagate_to_device = True
        if 'propagate_to_device' in kwargs:
            try:
                propagate_to_device = bool(kwargs.pop('propagate_to_device'))
                print(f"[{datetime.now().isoformat()}] 🔧 Propagate to device: {propagate_to_device}")
            except Exception:
                propagate_to_device = True

        # called_binding = False
        binding_start = time.time()
        if not self.device_property:
            if self.property.isCausal():
                print(f"[{datetime.now().isoformat()}] 🔗 Property '{property_name}' is causal but has no device binding")
                # self.suggest_device_binding()
                # called_binding = True
                pass
        else:
            print(f"[{datetime.now().isoformat()}] 🔗 Property '{property_name}' has device binding: {self.device_property.name}")
        binding_time = time.time() - binding_start

        # Get old value for comparison
        old_value_start = time.time()
        old_value = DigitalTwinInstanceProperty.objects.get(pk=self.id).value if self.id else ''
        old_value_time = time.time() - old_value_start
        print(f"[{datetime.now().isoformat()}] 📊 Property '{property_name}' value change: '{old_value}' → '{self.value}' (fetch_time: {old_value_time:.3f}s)")
        
        # Save to database
        db_save_start = time.time()
        super().save(*args, **kwargs)
        db_save_time = time.time() - db_save_start
        print(f"[{datetime.now().isoformat()}] 🗃️ Database save completed for '{property_name}' in {db_save_time:.3f}s")
        
        # Update device_property field if needed
        device_update_start = time.time()
        # Se a associação automática foi feita, garantir persistência
        # if called_binding and self.device_property:
        if self.device_property:
            # Salva novamente para garantir que o device_property seja persistido
            super().save(update_fields=["device_property"])
        device_update_time = time.time() - device_update_start
        print(f"[{datetime.now().isoformat()}] 🔗 Device property update for '{property_name}' took {device_update_time:.3f}s")

        # Only propagate to the device (which may trigger ThingsBoard RPCs) when
        # explicitly allowed. This avoids synchronous HTTP calls from periodic updaters.
        propagation_time = 0
        if propagate_to_device and self.id and self.device_property and self.property.isCausal():
            propagation_start = time.time()
            print(f"[{datetime.now().isoformat()}] 🚀 Starting device propagation for '{property_name}' to device '{self.device_property.name}'")
            
            device_property = self.device_property
            old_device_value = device_property.value
            device_property.value = self.value
            
            device_save_start = time.time()
            print(f"[{datetime.now().isoformat()}] 📤 Saving to device property: '{old_device_value}' → '{device_property.value}'")
            device_property.save()
            device_save_time = time.time() - device_save_start
            print(f"[{datetime.now().isoformat()}] ✅ Device property save completed in {device_save_time:.3f}s")
            
            # Check if device changed the value back
            verification_start = time.time()
            if device_property.value != self.value:
                print(f"[{datetime.now().isoformat()}] ⚠️ Device property value changed during save: '{self.value}' → '{device_property.value}'")
                self.value = old_value if old_value else device_property.value if device_property.value else ''
                super().save(*args, **kwargs)
            verification_time = time.time() - verification_start
            
            propagation_time = time.time() - propagation_start
            print(f"[{datetime.now().isoformat()}] 🏁 Device propagation completed for '{property_name}' in {propagation_time:.3f}s (device_save: {device_save_time:.3f}s, verification: {verification_time:.3f}s)")
        else:
            if not propagate_to_device:
                print(f"[{datetime.now().isoformat()}] ⏭️ Skipping device propagation for '{property_name}' (disabled)")
            elif not self.device_property:
                print(f"[{datetime.now().isoformat()}] ⏭️ Skipping device propagation for '{property_name}' (no device binding)")
            elif not self.property.isCausal():
                print(f"[{datetime.now().isoformat()}] ⏭️ Skipping device propagation for '{property_name}' (not causal)")

        total_save_time = time.time() - save_start
        print(f"[{datetime.now().isoformat()}] 💾 SAVE COMPLETE: Property '{property_name}' total time: {total_save_time:.3f}s (binding: {binding_time:.3f}s, db_save: {db_save_time:.3f}s, device_update: {device_update_time:.3f}s, propagation: {propagation_time:.3f}s)")
        
        # Log performance warnings
        if total_save_time > 1.0:
            print(f"[{datetime.now().isoformat()}] 🐌 SLOW SAVE WARNING: Property '{property_name}' took {total_save_time:.3f}s (threshold: 1.0s)")
        if propagation_time > 0.5:
            print(f"[{datetime.now().isoformat()}] 🐌 SLOW PROPAGATION WARNING: Property '{property_name}' propagation took {propagation_time:.3f}s (threshold: 0.5s)")

    @classmethod
    def dedupe_for_instance(cls, dtinstance):
        """Remove duplicate DigitalTwinInstanceProperty rows for the given instance.
        Keeps the row that has a non-null device_property if present, else keeps the first.
        Returns number of removed rows."""
        qs = cls.objects.filter(dtinstance=dtinstance).order_by('property_id', '-device_property_id', 'id')
        removed = 0
        seen = set()
        for row in qs:
            key = (row.property_id)
            if key in seen:
                # duplicate - delete
                try:
                    row.delete()
                    removed += 1
                except Exception:
                    pass
            else:
                seen.add(key)
        return removed

    def causal(self):
        return self.property.isCausal()

    @classmethod
    def periodic_read_call(cls, pk, interval=5):
        while True:
            dtinstanceproperty = DigitalTwinInstanceProperty.objects.filter(pk=pk).first()
            dtinstanceproperty.device_property.call_rpc(RPCCallTypes.READ)
            dtinstanceproperty.value=dtinstanceproperty.device_property.value
            time.sleep(interval)

    def get_hierarchy(self):
        """
        Retorna a hierarquia completa até a propriedade, incluindo o nome da propriedade.
        Exemplo: ['House 77', 'Room 1', 'AirConditioner1_77', 'temperature']
        """
        if self.dtinstance:
            return self.dtinstance.get_hierarchy() + [self.property.name]
        return [self.property.name]
    
    @classmethod
    def associate_all_for_instance(cls, dtinstance):
        for dtip in cls.objects.filter(dtinstance=dtinstance):
            if dtip.property.isCausal() and not dtip.device_property:
                dtip.suggest_device_binding()
                dtip.save(update_fields=["device_property"])

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

import json
from django.shortcuts import get_object_or_404

from orchestrator.schemas import DTDLModelSchema, DigitalTwinInstanceSchema

from ninja_extra import api_controller, http_get
from .models import DigitalTwinInstance, DigitalTwinInstanceProperty, DTDLModel, ModelElement, ModelRelationship
from ninja import Router

router = Router()


@router.post("/import-dtdl/", tags=['Orchestrator'])
def import_dtdl(request, payload: list[DTDLModelSchema]):
    for model_data in payload:
        dtdl_model, created = DTDLModel.objects.update_or_create(
            dtdl_id=model_data.id,
            defaults={'name': model_data.name}
        )
        for element_data in model_data.modelElements:
            ModelElement.objects.update_or_create(
                dtdl_model=dtdl_model,
                element_id=element_data['id'],
                defaults={
                    'element_type': element_data['type'],
                    'name': element_data['name'],
                    'schema': element_data.get('schema'),
                    'supplement_types': element_data.get('supplementTypes', [])
                }
            )
        for relationship_data in model_data.modelRelationships:
            ModelRelationship.objects.update_or_create(
                dtdl_model=dtdl_model,
                relationship_id=relationship_data['id'],
                defaults={
                    'name': relationship_data['name'],
                    'target': relationship_data['target']
                }
            )
    return {"success": True}


@router.get("/models/", tags=['Orchestrator'])
def list_models(request):
    models = DTDLModel.objects.all()
    return models


@router.get("/models/{dtdl_model_id}/", tags=['Orchestrator'])
def get_model(request, dtdl_model_id: int):
    model = get_object_or_404(DTDLModel, id=dtdl_model_id)
    return model


@router.get("/instances", response=list[DigitalTwinInstanceSchema], tags=['Orchestrator'])
def list_instances(request):
    instances = DigitalTwinInstance.objects.all()
    result = []
    for instance in instances:
        properties = DigitalTwinInstanceProperty.objects.filter(dtinstance=instance)
        result.append({
            "id": instance.id,
            "model": instance.model.name,
            "device": instance.device.name if instance.device else None,
            "properties": [{"name": prop.property, "value": prop.value, "device_property": prop.device_property.name} for prop in properties]
        })
    return result

@router.get("/instance/{instance_id}", response=DigitalTwinInstanceSchema, tags=['Orchestrator'])
def get_instance(request, instance_id: int):
    instance = DigitalTwinInstance.objects.get(id=instance_id)
    properties = DigitalTwinInstanceProperty.objects.filter(dtinstance=instance)
    result = {
        "id": instance.id,
        "model": instance.model.name,
        "device": instance.device.name if instance.device else None,
        "properties": [{"name": prop.property, "value": prop.value, "device_property": prop.device_property.name} for prop in properties]
    }
    return result

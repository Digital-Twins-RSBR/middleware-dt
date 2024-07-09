import json
from django.shortcuts import get_object_or_404

from orchestrator.schemas import DTDLModelSchema, DigitalTwinInstanceSchema

from .models import DigitalTwinInstance, DigitalTwinInstanceProperty, DTDLModel, ModelElement, ModelRelationship
from ninja import Router

router = Router()


@router.post("/import-dtdl/", tags=['Orchestrator'])
def import_dtdl(request, payload: list[DTDLModelSchema]):
    DTDLModel.create_dtdl_model_parsed(payload)
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

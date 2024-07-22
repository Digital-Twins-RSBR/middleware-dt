import json
from django.shortcuts import get_object_or_404

from core.models import DTDLParserClient
from orchestrator.schemas import ApplicationSchema, CreateApplicationSchema, CreateDTDLModelParsedSchema, CreateDTDLModelSchema, DTDLModelParsedSchema, DTDLModelSchema, DigitalTwinInstanceSchema

from .models import Application, DTDLModelParsed, DigitalTwinInstance, DigitalTwinInstanceProperty, DTDLModel, ModelElement, ModelRelationship
from ninja import Router

router = Router()

#Criar aplicação
@router.post("/application/", response=ApplicationSchema, tags=['Orchestrator'])
def create_application(request, payload: CreateApplicationSchema):
    payload_data = payload.dict()
    application = Application.objects.create(**payload_data)
    return application

@router.get("/application/{application_id}/", response=ApplicationSchema, tags=['Orchestrator'])
def get_application(request, application_id: int):
    application = get_object_or_404(Application, id=application_id)
    return application

@router.get("/application/", response=list[ApplicationSchema], tags=['Orchestrator'])
def list_application(request):
    applications = Application.objects.all()
    return applications

# @router.post("/import-dtdlmodel-fromjson/", tags=['Orchestrator'])
# def import_dtdl(request, payload: list[CreateDTDLModelSchema]):
#     DTDLModel.create_dtdl_model_parsed(payload)
#     return {"success": True}

@router.post("/dtdlmodel/", response=DTDLModelSchema, tags=['Orchestrator'])
def create_dtdlmodel(request, application_id, payload: CreateDTDLModelSchema):
    payload_data = payload.dict()
    payload_data['application'] = Application.objects.filter(id=application_id).first()
    payload_data['parser_client'] = DTDLParserClient.objects.filter(id=payload_data['parser_client']).first()
    dtdlmodel = DTDLModel.objects.create(**payload_data)
    return dtdlmodel

@router.get("/dtdlmodel/", response=list[DTDLModelSchema], tags=['Orchestrator'])
def list_dtdlmodels(request, application_id=None):
    queryset = DTDLModel.objects.all()
    if application_id:
        queryset = queryset.filter(application_id=application_id)
    return queryset


@router.get("/dtdlmodel/{dtdl_model_id}/", response=DTDLModelSchema, tags=['Orchestrator'])
def get_dtdlmodel(request, dtdl_model_id: int):
    dtdlmodel = get_object_or_404(DTDLModel, id=dtdl_model_id)
    return dtdlmodel

@router.get("/createdtdlmodelparsedfrommodel/{dtdl_model_id}/", response=DTDLModelParsedSchema, tags=['Orchestrator'])
def create_dtdlmodelparsedfrommodel(request, dtdl_model_id: int):
    dtdlmodel = get_object_or_404(DTDLModel, id=dtdl_model_id)
    return dtdlmodel.create_dtdl_model_parsed()

# @router.post("/dtdlmodelparsed/", response=DTDLModelParsedSchema, tags=['Orchestrator'])
# def create_dtdlmodelparsed(request, payload: CreateDTDLModelParsedSchema):
#     return DTDLModelParsed.objects.create(**payload.dict())

@router.get("/dtdlmodelparsed/", response=list[DTDLModelParsedSchema], tags=['Orchestrator'])
def list_dtdlmodelparsed(request, application_id=None):
    queryset = DTDLModelParsed.objects.all()
    if application_id:
        queryset = queryset.filter(application_id=application_id)
    return queryset

@router.get("/dtdlmodelparsed/{dtdl_model_parsed_id}/", response=DTDLModelParsedSchema, tags=['Orchestrator'])
def get_dtdlmodelparsed(request, dtdl_model_parsed_id: int):
    dtdlmodelparsed = get_object_or_404(DTDLModelParsed, id=dtdl_model_parsed_id)
    return dtdlmodelparsed

# @router.post("/import-dtdl/", tags=['Orchestrator'])
# def import_dtdl(request, payload: list[DTDLModelSchema]):
#     DTDLModel.create_dtdl_model_parsed(payload)
#     return {"success": True}

@router.post("/createdtdtinstance/{dtdl_model_parsed_id}/", response=DigitalTwinInstanceSchema, tags=['Orchestrator'])
def create_dtinstance(request, dtdl_model_parsed_id: int):
    dtdlmodelparsed = get_object_or_404(DTDLModelParsed, id=dtdl_model_parsed_id)
    dt_instance = dtdlmodelparsed.create_dt_instance()
    return dt_instance

@router.get("/dtinstance/", response=list[DigitalTwinInstanceSchema], tags=['Orchestrator'])
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

@router.get("/dtinstance/{dtinstance_id}", response=DigitalTwinInstanceSchema, tags=['Orchestrator'])
def get_instance(request, dtinstance_id: int):
    dtinstance = DigitalTwinInstance.objects.get(id=dtinstance_id)
    properties = DigitalTwinInstanceProperty.objects.filter(dtinstance=dtinstance)
    result = {
        "id": dtinstance.id,
        "model": dtinstance.model.name,
        "device": dtinstance.device.name if dtinstance.device else None,
        "properties": [{"name": prop.property, "value": prop.value, "device_property": prop.device_property.name} for prop in properties]
    }
    return result

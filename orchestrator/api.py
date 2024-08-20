import requests
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404

from core.models import DTDLParserClient
from orchestrator.schemas import SystemContextSchema, CreateSystemContextSchema, CreateDTDLModelParsedSchema, CreateDTDLModelSchema, DTDLModelParsedSchema, DTDLModelSchema, DigitalTwinInstanceSchema

from .models import SystemContext, DTDLModelParsed, DigitalTwinInstance, DigitalTwinInstanceProperty, DTDLModel, ModelElement, ModelRelationship
from ninja import Router

router = Router()

#Criar aplicação
@router.post("/system/", response=SystemContextSchema, tags=['Orchestrator'])
def create_system(request, payload: CreateSystemContextSchema):
    payload_data = payload.dict()
    system = SystemContext.objects.create(**payload_data)
    return system

@router.get("/system/{system_id}/", response=SystemContextSchema, tags=['Orchestrator'])
def get_system(request, system_id: int):
    system = get_object_or_404(SystemContext, id=system_id)
    return system

@router.get("/system/", response=list[SystemContextSchema], tags=['Orchestrator'])
def list_system(request):
    systems = SystemContext.objects.all()
    return systems

# @router.post("/import-dtdlmodel-fromjson/", tags=['Orchestrator'])
# def import_dtdl(request, payload: list[CreateDTDLModelSchema]):
#     DTDLModel.create_dtdl_model_parsed(payload)
#     return {"success": True}

@router.post("/system/{system_id}/dtdlmodel/", response=DTDLModelSchema, tags=['Orchestrator'])
def create_dtdlmodel(request, system_id, payload: CreateDTDLModelSchema):
    payload_data = payload.dict()
    payload_data['system'] = SystemContext.objects.filter(id=system_id).first()
    payload_data['parser_client'] = DTDLParserClient.objects.filter(id=payload_data['parser_client']).first()
    dtdlmodel = DTDLModel.objects.create(**payload_data)
    return dtdlmodel

@router.get("/system/{system_id}/dtdlmodel/", response=list[DTDLModelSchema], tags=['Orchestrator'])
def list_dtdlmodels(request, system_id: int):
    queryset = DTDLModel.objects.filter(system_id=system_id)
    return queryset


@router.get("/system/{system_id}/dtdlmodel/{dtdl_model_id}/", response=DTDLModelSchema, tags=['Orchestrator'])
def get_dtdlmodel(request, system_id: int, dtdl_model_id: int):
    dtdlmodel = DTDLModel.objects.filter(system_id=system_id, id=dtdl_model_id).first()
    if not dtdlmodel:
        raise Http404(f'No DTDLModel matches the given query.')
    return dtdlmodel

@router.post("/system/{system_id}/createdtdlmodelparsedfrommodel/{dtdl_model_id}/", response=DTDLModelParsedSchema, tags=['Orchestrator'])
def create_dtdlmodelparsedfrommodel(request, system_id: int, dtdl_model_id: int):
    dtdlmodel = DTDLModel.objects.filter(system_id=system_id, id=dtdl_model_id).first()
    if not dtdlmodel:
        raise Http404(f'No DTDLModel matches the given query.')

    try:
        # Chamando o método para criar o modelo DTDL parsed
        return dtdlmodel.create_dtdl_model_parsed()
        
    except requests.exceptions.RequestException as e:
        return JsonResponse({"detail": "Failed to connect to the parser service", "error": str(e)}, status=503)
    except Exception as e:
        return JsonResponse({"detail": str(e)}, status=500)
    

# @router.post("/dtdlmodelparsed/", response=DTDLModelParsedSchema, tags=['Orchestrator'])
# def create_dtdlmodelparsed(request, payload: CreateDTDLModelParsedSchema):
#     return DTDLModelParsed.objects.create(**payload.dict())

@router.get("/system/{system_id}/dtdlmodelparsed/", response=list[DTDLModelParsedSchema], tags=['Orchestrator'])
def list_dtdlmodelparsed(request, system_id: int):
    queryset = DTDLModelParsed.objects.filter(system_id=system_id)
    return queryset

@router.get("/system/{system_id}/dtdlmodelparsed/{dtdl_model_parsed_id}/", response=DTDLModelParsedSchema, tags=['Orchestrator'])
def get_dtdlmodelparsed(request, system_id: int, dtdl_model_parsed_id: int):
    dtdlmodelparsed = DTDLModelParsed.objects.filter(system_id=system_id, id=dtdl_model_parsed_id).first()
    if not dtdlmodelparsed:
        raise Http404(f'No DTDLModelParsed matches the given query.')
    return dtdlmodelparsed

# @router.post("/import-dtdl/", tags=['Orchestrator'])
# def import_dtdl(request, payload: list[DTDLModelSchema]):
#     DTDLModel.create_dtdl_model_parsed(payload)
#     return {"success": True}

@router.post("/system/{system_id}/createdtdtinstance/{dtdl_model_parsed_id}/", response=DigitalTwinInstanceSchema, tags=['Orchestrator'])
def create_dtinstance(request, system_id: int, dtdl_model_parsed_id: int):
    dtdlmodelparsed = DTDLModelParsed.objects.filter(system_id=system_id, id=dtdl_model_parsed_id).first()
    if not dtdlmodelparsed:
        raise Http404(f'No DTDLModelParsed matches the given query.')
    dt_instance = dtdlmodelparsed.create_dt_instance()
    return dt_instance

@router.get("/system/{system_id}/dtinstance/", response=list[DigitalTwinInstanceSchema], tags=['Orchestrator'])
def list_instances(request, system_id: int):
    instances = DigitalTwinInstance.objects.filter(model__system_id=system_id)
    result = []
    for instance in instances:
        properties = DigitalTwinInstanceProperty.objects.filter(dtinstance=instance)
        result.append({
            "id": instance.id,
            "model_id": instance.model_id,
            "model": instance.model.name,
            "properties": [{"name": prop.property, "value": prop.value, "device_property": prop.device_property.name if prop.device_property else ''} for prop in properties]
        })
    return result

@router.get("/system/{system_id}/dtinstance/{dtinstance_id}", response=DigitalTwinInstanceSchema, tags=['Orchestrator'])
def get_instance(request, system_id: int, dtinstance_id: int):
    dtinstance = DigitalTwinInstance.objects.filter(model__system_id=system_id, id=dtinstance_id).first()
    if not dtinstance:
        raise Http404(f'No DTInstance matches the given query.')
    properties = DigitalTwinInstanceProperty.objects.filter(dtinstance=dtinstance)
    result = {
        "id": dtinstance.id,
        "model_id": dtinstance.model_id,
        "model": dtinstance.model.name,
        "properties": [{"name": prop.property, "value": prop.value, "device_property": prop.device_property.name if prop.device_property else ''} for prop in properties]
    }
    return result

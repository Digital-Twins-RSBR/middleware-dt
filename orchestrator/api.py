from django.http import Http404, HttpResponseServerError
from django.shortcuts import get_object_or_404
from pydantic import ValidationError
from requests import RequestException

from core.models import DTDLParserClient
from facade.models import Property
from orchestrator.schemas import BindDTInstancePropertieDeviceSchema, CreateDTFromDTDLModelSchema, DigitalTwinInstanceRelationshipSchema, DigitalTwinPropertySchema, PutDTDLModelSchema, SystemContextSchema, CreateSystemContextSchema, CreateDTDLModelSchema, DTDLModelSchema, DigitalTwinInstanceSchema

from .models import DigitalTwinInstanceRelationship, SystemContext, DigitalTwinInstance, DigitalTwinInstanceProperty, DTDLModel, ModelElement, ModelRelationship
from ninja import Router

router = Router()

@router.post("/systems/", response=SystemContextSchema, tags=['Orchestrator'],)
def create_system(request, payload: CreateSystemContextSchema):
    payload_data = payload.dict()
    system = SystemContext.objects.create(**payload_data)
    return system


@router.get("/systems/{system_id}/", response=SystemContextSchema, tags=['Orchestrator'])
def get_system(request, system_id: int):
    system = get_object_or_404(SystemContext, id=system_id)
    return system


@router.get("/systems/", response=list[SystemContextSchema], tags=['Orchestrator'])
def list_system(request):
    systems = SystemContext.objects.all()
    return systems


@router.post("/systems/{system_id}/dtdlmodels/", response=DTDLModelSchema, tags=['Orchestrator'])
def create_dtdlmodel(request, system_id, payload: CreateDTDLModelSchema):
    payload_data = payload.dict()
    payload_data['system'] = SystemContext.objects.filter(id=system_id).first()
    dtdlmodel = DTDLModel.objects.create(**payload_data)
    return dtdlmodel

@router.put("/systems/{system_id}/dtdlmodels/{model_id}/", response=DTDLModelSchema, tags=['Orchestrator'])
def update_dtdlmodel(request, system_id: int, model_id: int, payload: PutDTDLModelSchema):
    dtdlmodel = DTDLModel.objects.filter(system_id=system_id, id=model_id).first()
    if not dtdlmodel:
        raise Http404(f'No DTDLModel matches the given query.')

    # Atualiza os campos do modelo DTDL
    for attr, value in payload.dict().items():
        setattr(dtdlmodel, attr, value)

    dtdlmodel.save()
    return dtdlmodel

@router.get("/systems/{system_id}/dtdlmodels/", response=list[DTDLModelSchema], tags=['Orchestrator'])
def list_dtdlmodels(request, system_id: int):
    queryset = DTDLModel.objects.filter(system_id=system_id)
    return queryset


@router.get("/systems/{system_id}/dtdlmodels/{dtdl_model_id}/", response=DTDLModelSchema, tags=['Orchestrator'])
def get_dtdlmodel(request, system_id: int, dtdl_model_id: int):
    dtdlmodel = DTDLModel.objects.filter(system_id=system_id, id=dtdl_model_id).first()
    if not dtdlmodel:
        raise Http404(f'No DTDLModel matches the given query.')
    return dtdlmodel


# @router.post("/systems/{system_id}/updated_parsed_specification/{dtdl_model_id}/", response=DTDLModelSchema, tags=['Orchestrator'])
# def update_parsed_specification_dtdlmodel(request, system_id: int, dtdl_model_id: int):
#     dtdlmodel = DTDLModel.objects.filter(system_id=system_id, id=dtdl_model_id).first()
#     if not dtdlmodel:
#         raise Http404(f'No DTDLModel matches the given query.')
#     dtdlmodel.save()
#     return dtdlmodel

# @router.post("/systems/{system_id}/createdtdtinstance/{dtdl_model_id}/", response=DigitalTwinInstanceSchema, tags=['Orchestrator'])
# def create_dtinstance(request, system_id: int, dtdl_model_id: int):
#     dtdlmodel = DTDLModel.objects.filter(system_id=system_id, id=dtdl_model_id).first()
#     if not dtdlmodel:
#         raise Http404(f'No DTDLModel matches the given query.')
#     dt_instance = dtdlmodel.create_dt_instance()
#     return dt_instance

@router.post("/systems/{system_id}/instances/", response=DigitalTwinInstanceSchema, tags=['Orchestrator'])
def create_dtinstance(request, system_id: int, payload: CreateDTFromDTDLModelSchema):
    payload_data = payload.dict()
    dtdl_model_id = payload_data.get("dtdl_model_id")
    if not dtdl_model_id:
        raise ValidationError({"detail": "dtdl_model_id is required in the payload."})

    dtdlmodel = DTDLModel.objects.filter(system_id=system_id, id=dtdl_model_id).first()
    if not dtdlmodel:
        raise Http404(f'No DTDLModel matches the given query.')

    dt_instance = dtdlmodel.create_dt_instance()
    return dt_instance

@router.get("/systems/{system_id}/instances/", response=list[DigitalTwinInstanceSchema], tags=['Orchestrator'])
def list_instances(request, system_id: int):
    return [dti for dti in DigitalTwinInstance.objects.filter(model__system_id=system_id)]

@router.get("/systems/{system_id}/instances/{dtinstance_id}", response=DigitalTwinInstanceSchema, tags=['Orchestrator'])
def get_instance(request, system_id: int, dtinstance_id: int):
    dtinstance = DigitalTwinInstance.objects.filter(model__system_id=system_id, id=dtinstance_id).first()
    if not dtinstance:
        raise Http404(f'No DTInstance matches the given query.')
    return dtinstance

@router.post("/systems/{system_id}/instances/{dtinstance_id}/bind/", response=DigitalTwinInstanceSchema, tags=['Orchestrator'])
def bind_dtinstance_device(request, system_id: int, dtinstance_id: int, payload: BindDTInstancePropertieDeviceSchema):
    dtinstance = DigitalTwinInstance.objects.filter(model__system_id=system_id, id=dtinstance_id).first()
    if not dtinstance:
        raise Http404(f'No DTInstance matches the given query.')
    payload_data = payload.dict()
    dtproperty = DigitalTwinInstanceProperty.objects.filter(id=payload_data['property_id'], dtinstance=dtinstance).first()
    dtproperty.device_property = Property.objects.filter(id=payload_data['device_property_id']).first()
    dtproperty.save()
    return dtinstance


@router.post("/systems/{system_id}/instances/relationships/", tags=['Orchestrator'])
def create_relationships(request, system_id: int, payload: list[DigitalTwinInstanceRelationshipSchema]):
    import ipdb; ipdb.set_trace()
    for relationship_data in payload:
        relationship_name = relationship_data.relationship_name
        source_instance_id = relationship_data.source_instance_id
        target_instance_id = relationship_data.target_instance_id

        # Verifica se o relacionamento é permitido pelo modelo
        model_relationship = ModelRelationship.objects.filter(
            dtdl_model__system_id=system_id,
            name=relationship_name
        ).first()

        if not model_relationship:
            raise ValidationError({"detail": f"Relationship '{relationship_name}' is not defined in the model for system {system_id}."})

        # Verifica se as instâncias digitais de origem e destino existem
        source_instance = DigitalTwinInstance.objects.filter(id=source_instance_id).first()
        target_instance = DigitalTwinInstance.objects.filter(id=target_instance_id).first()

        if not source_instance:
            raise Http404(f"Source Digital Twin Instance with ID {source_instance_id} does not exist.")
        if not target_instance:
            raise Http404(f"Target Digital Twin Instance with ID {target_instance_id} does not exist.")

        # Criar ou atualizar o relacionamento da instância digital
        DigitalTwinInstanceRelationship.objects.update_or_create(
            source_instance=source_instance,
            target_instance=target_instance,
            defaults={'model_relationship': model_relationship}
        )

    return {"detail": "Relationships created successfully."}

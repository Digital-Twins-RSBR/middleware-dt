from django.http import Http404
from django.shortcuts import get_object_or_404
import neo4j
import neo4j.exceptions
from pydantic import ValidationError

from facade.models import Property
from orchestrator.schemas import (
    BindDTInstancePropertieDeviceSchema,
    CreateDTFromDTDLModelSchema,
    CypherQuerySchema,
    DTDLModelBatchSchema,
    DTDLModelIDSchema,
    DigitalTwinInstancePropertySchema,
    DigitalTwinInstanceRelationshipSchema,
    DigitalTwinPropertyUpdateSchema,
    PutDTDLModelSchema,
    SystemContextSchema,
    CreateSystemContextSchema,
    CreateDTDLModelSchema,
    DTDLModelSchema,
    DigitalTwinInstanceSchema,
)

from .models import (
    DigitalTwinInstanceRelationship,
    SystemContext,
    DigitalTwinInstance,
    DigitalTwinInstanceProperty,
    DTDLModel,
    ModelRelationship,
)
from ninja import Router
from ninja.errors import HttpError

from neomodel import db
from typing import List

router = Router()


@router.post(
    "/systems/",
    response=SystemContextSchema,
    tags=["Orchestrator"],
)
def create_system(request, payload: CreateSystemContextSchema):
    payload_data = payload.dict()
    system = SystemContext.objects.create(**payload_data)
    return system


@router.get(
    "/systems/{system_id}/", response=SystemContextSchema, tags=["Orchestrator"]
)
def get_system(request, system_id: int):
    system = get_object_or_404(SystemContext, id=system_id)
    return system


@router.get("/systems/", response=list[SystemContextSchema], tags=["Orchestrator"])
def list_system(request):
    systems = SystemContext.objects.all()
    return systems


@router.post(
    "/systems/{system_id}/dtdlmodels/", response=DTDLModelSchema, tags=["Orchestrator"]
)
def create_dtdlmodel(request, system_id, payload: CreateDTDLModelSchema):
    payload_data = payload.dict()
    payload_data["system"] = SystemContext.objects.filter(id=system_id).first()
    dtdlmodel = DTDLModel.objects.create(**payload_data)
    return dtdlmodel


@router.put(
    "/systems/{system_id}/dtdlmodels/{model_id}/",
    response=DTDLModelSchema,
    tags=["Orchestrator"],
)
def update_dtdlmodel(
    request, system_id: int, model_id: int, payload: PutDTDLModelSchema
):
    dtdlmodel = DTDLModel.objects.filter(system_id=system_id, id=model_id).first()
    if not dtdlmodel:
        raise Http404("No DTDLModel matches the given query.")

    # Atualiza os campos do modelo DTDL
    for attr, value in payload.dict().items():
        setattr(dtdlmodel, attr, value)

    dtdlmodel.save()
    return dtdlmodel


@router.get(
    "/systems/{system_id}/dtdlmodels/",
    response=list[DTDLModelSchema],
    tags=["Orchestrator"],
)
def list_dtdlmodels(request, system_id: int):
    queryset = DTDLModel.objects.filter(system_id=system_id)
    return queryset


@router.get(
    "/systems/{system_id}/dtdlmodels/{dtdl_model_id}/",
    response=DTDLModelSchema,
    tags=["Orchestrator"],
)
def get_dtdlmodel(request, system_id: int, dtdl_model_id: int):
    dtdlmodel = DTDLModel.objects.filter(system_id=system_id, id=dtdl_model_id).first()
    if not dtdlmodel:
        raise Http404("No DTDLModel matches the given query.")
    return dtdlmodel


@router.post("/systems/{system_id}/dtdlmodels/batch/", tags=["Orchestrator"])
def create_dtdlmodels_batch(
    request, system_id: int, payload: List[DTDLModelBatchSchema]
):
    try:
        system = SystemContext.objects.get(id=system_id)
        created_models = []

        for model_data in payload:
            dtdl_model, created = DTDLModel.objects.update_or_create(
                system=system,
                name=model_data.name,
                defaults={"specification": model_data.specification},
            )
            created_models.append({"id": dtdl_model.id, "name": dtdl_model.name})

        return {"created_models": created_models}
    except SystemContext.DoesNotExist:
        return {"error": "System not found"}, 404
    except Exception as e:
        return {"error": str(e)}, 400


@router.post(
    "/systems/{system_id}/instances/",
    response=DigitalTwinInstanceSchema,
    tags=["Orchestrator"],
)
def create_dtinstance(request, system_id: int, payload: CreateDTFromDTDLModelSchema):
    payload_data = payload.dict()
    dtdl_model_id = payload_data.get("dtdl_model_id")
    if not dtdl_model_id:
        raise ValidationError({"detail": "dtdl_model_id is required in the payload."})

    dtdlmodel = DTDLModel.objects.filter(system_id=system_id, id=dtdl_model_id).first()
    if not dtdlmodel:
        raise Http404("No DTDLModel matches the given query.")

    dt_instance = dtdlmodel.create_dt_instance()
    return dt_instance


@router.post("/systems/{system_id}/instances/batch/", tags=["Orchestrator"])
def create_instances_batch(request, system_id: int, payload: DTDLModelIDSchema):
    try:
        created_instances = []
        for model_id in payload.dtdl_model_ids:
            dtdl_model = DTDLModel.objects.get(id=model_id, system_id=system_id)
            dt_instance = dtdl_model.create_dt_instance()
            created_instances.append(
                {"id": dt_instance.id, "model_name": dtdl_model.name, "properties": []}
            )
        return {"created_instances": created_instances}
    except DTDLModel.DoesNotExist:
        return {"error": f"Model with ID not found in system {system_id}"}, 404
    except Exception as e:
        return {"error": str(e)}, 400


@router.get(
    "/systems/{system_id}/instances/",
    response=list[DigitalTwinInstanceSchema],
    tags=["Orchestrator"],
)
def list_instances(request, system_id: int):
    return [
        dti for dti in DigitalTwinInstance.objects.filter(model__system_id=system_id)
    ]


@router.get(
    "/systems/{system_id}/instances/{dtinstance_id}",
    response=DigitalTwinInstanceSchema,
    tags=["Orchestrator"],
)
def get_instance(request, system_id: int, dtinstance_id: int):
    dtinstance = DigitalTwinInstance.objects.filter(
        model__system_id=system_id, id=dtinstance_id
    ).first()
    if not dtinstance:
        raise Http404("No DTInstance matches the given query.")
    return dtinstance


@router.post(
    "/systems/{system_id}/instances/{dtinstance_id}/bind/",
    response=DigitalTwinInstanceSchema,
    tags=["Orchestrator"],
)
def bind_dtinstance_device(
    request,
    system_id: int,
    dtinstance_id: int,
    payload: BindDTInstancePropertieDeviceSchema,
):
    dtinstance = DigitalTwinInstance.objects.filter(
        model__system_id=system_id, id=dtinstance_id
    ).first()
    if not dtinstance:
        raise Http404("No DTInstance matches the given query.")
    payload_data = payload.dict()
    dtproperty = DigitalTwinInstanceProperty.objects.filter(
        id=payload_data["property_id"], dtinstance=dtinstance
    ).first()
    dtproperty.device_property = Property.objects.filter(
        id=payload_data["device_property_id"]
    ).first()
    dtproperty.save()
    return dtinstance


@router.put(
    "/systems/{system_id}/instances/{dtinstance_id}/properties/{property_id}/",
    response=DigitalTwinInstancePropertySchema,
    tags=["Orchestrator"],
    summary="Update a causal property of a digital twin instance",
)
def update_causal_property(
    request,
    system_id: int,
    dtinstance_id: int,
    property_id: int,
    payload: DigitalTwinPropertyUpdateSchema,
):
    try:
        # Verifica se o gêmeo digital e a propriedade existem
        instance = get_object_or_404(
            DigitalTwinInstance, model__system_id=system_id, id=dtinstance_id
        )
        property_obj = get_object_or_404(
            DigitalTwinInstanceProperty, id=property_id, dtinstance=instance
        )

        # Verifica se a propriedade é causal
        if not property_obj.causal:
            raise HttpError(
                400,
                f"Property '{property_obj.name}' is not causal and cannot be updated.",
            )

        # # Valida o tipo do valor fornecido
        # expected_type = property_obj.property.type  # Supondo que a tabela Property tem o campo `type`
        # if not isinstance(payload.value, expected_type):
        #     raise HttpError(400, f"Invalid value type. Expected {expected_type}, got {type(payload.value)}.")

        # Atualiza o valor da propriedade
        property_obj.value = payload.value
        property_obj.save()
        return DigitalTwinInstancePropertySchema.from_instance(property_obj)

    except DigitalTwinInstanceProperty.DoesNotExist:
        return {"error": "Propriedade não encontrada."}, 404
    except ValueError:
        return {"error": "Tipo de dado inválido para a propriedade."}, 400


@router.post("/systems/{system_id}/instances/relationships/", tags=["Orchestrator"])
def create_relationships(
    request, system_id: int, payload: list[DigitalTwinInstanceRelationshipSchema]
):
    for relationship_data in payload:
        relationship_name = relationship_data.relationship_name
        source_instance_id = relationship_data.source_instance_id
        target_instance_id = relationship_data.target_instance_id

        # Verifica se o relacionamento é permitido pelo modelo
        model_relationship = ModelRelationship.objects.filter(
            dtdl_model__system_id=system_id, name=relationship_name
        ).first()

        if not model_relationship:
            return {"error": f"Relationship '{relationship_name}' is not defined in the model for system {system_id}."}, 400

        # Verifica se as instâncias digitais de origem e destino existem
        source_instance = DigitalTwinInstance.objects.filter(
            id=source_instance_id
        ).first()
        target_instance = DigitalTwinInstance.objects.filter(
            id=target_instance_id
        ).first()

        if not source_instance:
            return {"error": f"Source Digital Twin Instance with ID {source_instance_id} does not exist."}, 400
        if not target_instance:
            return {"error": f"Target Digital Twin Instance with ID {target_instance_id} does not exist."}, 400

        # Criar ou atualizar o relacionamento da instância digital
        DigitalTwinInstanceRelationship.objects.update_or_create(
            source_instance=source_instance,
            target_instance=target_instance,
            defaults={"model_relationship": model_relationship},
        )

    return {"detail": "Relationships created successfully."}


@router.post("/systems/{system_id}/instances/query/", tags=["Orchestrator"])
def execute_cypher_query(request, system_id: int, payload: CypherQuerySchema):
    try:
        query = payload.query
        results, meta = db.cypher_query(query)
        
        # Convert results to a list of dictionaries
        results_list = []
        for record in results:
            record_dict = {}
            if type(record) is list:
                for item in record:
                    if isinstance(item, neo4j.graph.Node):
                        record_dict = CypherQuerySchema.serialize_node(item)
                    else:
                        record_dict = item
            else:
                for key, value in record.items():
                    if isinstance(value, neo4j.graph.Node):
                        record_dict[key] = CypherQuerySchema.serialize_node(value)
                    else:
                        record_dict[key] = value
            results_list.append(record_dict)
        return {"results": results_list, "keys": meta}
    except neo4j.exceptions.ServiceUnavailable:
        return {"error": "Neo4j service is unavailable."}
    except Exception as e:
        return {"error": str(e)}, 400


# Exemplos de queries Cypher para o Neo4j:
# Listar todos os Digital Twins:
# {
#     "query": "MATCH (dt:DigitalTwin) RETURN dt"
# }
# Listar todas as propriedades de um Digital Twin específico:
# {
#     "query": "MATCH (dt:DigitalTwin {name: 'Light 1'})-[:HAS_PROPERTY]->(prop:TwinProperty) RETURN prop"
# }
# Listar todos os relacionamentos entre Digital Twins:
# {
#     "query": "MATCH (dt1:DigitalTwin)-[r]->(dt2:DigitalTwin) RETURN dt1, r, dt2"
# }
# Buscar um Digital Twin específico pelo nome:
# {
#     "query": "MATCH (dt:DigitalTwin {name: 'Light 1'}) RETURN dt"
# }
# Listar todas as propriedades e seus valores de um Digital Twin específico:
# {
#     "query": "MATCH (dt:DigitalTwin {name: 'TwinName'})-[:HAS_PROPERTY]->(prop:TwinProperty) RETURN prop.name, prop.value"
# }
# Listar todos os Digital Twins e suas propriedades:
# {
#     "query": "MATCH (dt:DigitalTwin)-[:HAS_PROPERTY]->(prop:TwinProperty) RETURN dt.name, prop.name, prop.value"
# }
# Listar todos os quartos e suas luzes:
# {
#     "query": "MATCH (room:DigitalTwin)-[:lights]->(light:DigitalTwin) RETURN room, light"
# }
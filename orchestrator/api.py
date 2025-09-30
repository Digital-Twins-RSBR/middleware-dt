from django.shortcuts import get_object_or_404
import neo4j
import neo4j.exceptions
from pydantic import ValidationError

from facade.models import Property
from orchestrator.schemas import (
    AssociatePropertySchema,
    AssociatedPropertySchema,
    BindDTInstancePropertieDeviceSchema,
    CreateDTFromDTDLModelSchema,
    CypherQuerySchema,
    DTDLModelBatchSchema,
    DTDLModelIDSchema,
    DTDLSpecificationSchema,
    DigitalTwinInstancePropertySchema,
    DigitalTwinInstanceRelationshipModelSchema,
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

from ninja import Router, Body
from ninja.errors import HttpError

from neomodel import db
from typing import List
from django.db import transaction
from ninja import Schema
from sentence_transformers import SentenceTransformer, util

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

@router.put(
    "/systems/{system_id}/",
    response=SystemContextSchema,
    tags=["Orchestrator"],
)
def update_system(request, system_id: int, payload: CreateSystemContextSchema):
    system = get_object_or_404(SystemContext, id=system_id)
    for attr, value in payload.dict().items():
        setattr(system, attr, value)
    system.save()
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

@router.post(
    "/systems/{system_id}/dtdlmodels/bulk/", response=List[DTDLModelSchema], tags=["Orchestrator"]
)
def create_multiple_dtdlmodels(request, system_id: int, payload: List[DTDLSpecificationSchema]):
    system = get_object_or_404(SystemContext, id=system_id)
    created_models = []
    for spec in payload:
        payload_data = {
            "system": system,
            "name": spec.displayName,
            "specification": {
                "@id": spec.id,
                "@type": spec.type,
                "@context": spec.context,
                "contents": spec.contents,
                "displayName": spec.displayName
            }
        }
        dtdlmodel = DTDLModel.objects.create(**payload_data)
        created_models.append(dtdlmodel)
    for dtdlmodel in created_models:
        dtdlmodel.create_dtdl_models()
    return created_models

@router.put(
    "/systems/{system_id}/dtdlmodels/{dtdlmodel_id}/",
    response=DTDLModelSchema,
    tags=["Orchestrator"],
)
def update_dtdlmodel(
    request, system_id: int, dtdlmodel_id: int, payload: PutDTDLModelSchema
):
    dtdlmodel = DTDLModel.objects.filter(system_id=system_id, id=dtdlmodel_id).first()
    if not dtdlmodel:
        raise HttpError(
                404,
                "No DTDLModel matches the given query.",
            )

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
        raise HttpError(
                404,
                "No DTDLModel matches the given query.",
            )
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
        raise HttpError(404, "System not found")
    except Exception as e:
        raise HttpError(400, str(e))


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
        raise HttpError(
                404,
                "No DTDLModel matches the given query.",
            )

    dt_instance = dtdlmodel.create_dt_instance()
    return dt_instance


@router.post("/systems/{system_id}/instances/batch/", tags=["Orchestrator"])
def create_instances_batch(request, system_id: int, payload: DTDLModelIDSchema):
    try:
        created_instances = []
        for id_model in payload.dtdl_model_ids:
            dtdl_model = DTDLModel.objects.get(id=id_model, system_id=system_id)
            dt_instance = dtdl_model.create_dt_instance()
            created_instances.append(
                {"id": dt_instance.id, "model_name": dtdl_model.name, "properties": []}
            )
        return {"created_instances": created_instances}
    except DTDLModel.DoesNotExist:
        raise HttpError(404, f"Model with ID not found in system {system_id}")
    except Exception as e:
        raise HttpError(400, str(e))


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
        raise HttpError(
                404,
                "No DTInstance matches the given query.",
            )
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
        raise HttpError(
                404,
                "No DTInstance matches the given query.",
            )
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
        
        # Captura timestamp de resposta M2S para correção de latência
        try:
            import time
            from facade.utils import format_influx_line
            from middleware_dt.settings import INFLUXDB_TOKEN, INFLUXDB_URL, USE_INFLUX_TO_EVALUATE
            
            if (USE_INFLUX_TO_EVALUATE and INFLUXDB_TOKEN and 
                property_obj.device_property and property_obj.device_property.device):
                response_timestamp = int(time.time() * 1000)
                sensor_id = property_obj.device_property.device.identifier
                tags = {"sensor": sensor_id, "source": "middts"}
                fields = {"sent_timestamp": response_timestamp}
                data = format_influx_line("device_data", tags, fields, timestamp=response_timestamp)
                
                import requests
                requests.post(
                    INFLUXDB_URL,
                    headers={"Authorization": f"Token {INFLUXDB_TOKEN}", "Content-Type": "text/plain"},
                    data=data,
                    timeout=0.1
                )
                print(f"M2S response timestamp logged for {sensor_id}")
        except Exception as e:
            print(f"M2S timestamp logging failed: {e}")
        
        return DigitalTwinInstancePropertySchema.from_instance(property_obj)

    except DigitalTwinInstanceProperty.DoesNotExist:
        raise HttpError(404, "Propriedade não encontrada.")
    except ValueError:
        raise HttpError(400, "Tipo de dado inválido para a propriedade.")


@router.get(
    "/systems/{system_id}/instances/{dtinstance_id}/properties/{property_id}/value/",
    response=dict,
    tags=["Orchestrator"],
    summary="Get the value of a property of a digital twin instance",
)
def get_property_value(
    request,
    system_id: int,
    dtinstance_id: int,
    property_id: int,
):
    try:
        # Verifica se o gêmeo digital e a propriedade existem
        instance = get_object_or_404(
            DigitalTwinInstance, model__system_id=system_id, id=dtinstance_id
        )
        property_obj = get_object_or_404(
            DigitalTwinInstanceProperty, id=property_id, dtinstance=instance
        )

        # Retorna o valor da propriedade
        return {"value": property_obj.value}
    except DigitalTwinInstance.DoesNotExist:
        raise HttpError(404, "Digital Twin Instance not found.")
    except DigitalTwinInstanceProperty.DoesNotExist:
        raise HttpError(404, "Property not found.")
    except Exception as e:
        raise HttpError(400, str(e))


@router.get("/systems/{system_id}/relationships/", tags=["Orchestrator"], response=List[DigitalTwinInstanceRelationshipModelSchema])
def list_relationships(request, system_id: int):
    try:
        system_context = get_object_or_404(SystemContext, pk=system_id)
        relationships = DigitalTwinInstanceRelationship.objects.filter(
            source_instance__model__system=system_context
        )
        return relationships
    except SystemContext.DoesNotExist:
        raise HttpError(404, f"SystemContext with ID {system_id} not found.")
    except Exception as e:
        raise HttpError(400, str(e))

@router.post("/systems/{system_id}/instances/relationships/", tags=["Orchestrator"])
def create_relationships(
    request, system_id: int, relationships: List[DigitalTwinInstanceRelationshipSchema]
): 
    try:
        system_context = get_object_or_404(SystemContext, pk=system_id)
        for relationship_data in relationships:
            relationship_name = relationship_data.relationship_name
            source_instance_id = relationship_data.source_instance_id
            target_instance_id = relationship_data.target_instance_id

            # Verifica se o relacionamento é permitido pelo modelo
            model_relationship = ModelRelationship.objects.filter(
                dtdl_model__system=system_context, name=relationship_name
            ).first()

            if not model_relationship:
                raise HttpError(400, f"Relationship '{relationship_name}' is not defined in the model for system {system_id}.")

            # Verifica se as instâncias digitais de origem e destino existem
            source_instance = DigitalTwinInstance.objects.filter(id=source_instance_id).first()
            target_instance = DigitalTwinInstance.objects.filter(id=target_instance_id).first()

            if not source_instance:
                raise HttpError(400, f"Source Digital Twin Instance with ID {source_instance_id} does not exist.")
            if not target_instance:
                raise HttpError(400, f"Target Digital Twin Instance with ID {target_instance_id} does not exist.")

            # Criar ou atualizar o relacionamento da instância digital
            DigitalTwinInstanceRelationship.objects.update_or_create(
                source_instance=source_instance,
                target_instance=target_instance,
                defaults={"relationship": model_relationship},
            )

        return {"detail": "Relationships created successfully."}
    except SystemContext.DoesNotExist:
        raise HttpError(404, f"SystemContext with ID {system_id} not found.")
    except Exception as e:
        raise HttpError(400, str(e))


@router.delete("/systems/{system_id}/relationships/", tags=["Orchestrator"])
def delete_relationships(request, system_id: int, relationships: List[DigitalTwinInstanceRelationshipSchema]):
    try:
        system_context = SystemContext.objects.get(pk=system_id)
        for rel in relationships:
            # Verifica se o relacionamento é permitido pelo modelo
            model_relationship = ModelRelationship.objects.filter(
                dtdl_model__system=system_context, name=rel.relationship_name
            ).first()

            if not model_relationship:
                raise HttpError(400, f"Relationship '{rel.relationship_name}' is not defined in the model for system {system_id}.")

            # Verifica se as instâncias digitais de origem e destino existem
            source_instance = DigitalTwinInstance.objects.filter(id=rel.source_instance_id).first()
            target_instance = DigitalTwinInstance.objects.filter(id=rel.target_instance_id).first()

            if not source_instance:
                raise HttpError(400, f"Source Digital Twin Instance with ID {rel.source_instance_id} does not exist.")
            if not target_instance:
                raise HttpError(400, f"Target Digital Twin Instance with ID {rel.target_instance_id} does not exist.")

            # Deletar o relacionamento da instância digital
            relationship = DigitalTwinInstanceRelationship.objects.filter(
                source_instance=source_instance,
                target_instance=target_instance,
                relationship=model_relationship
            ).first()

            if relationship:
                relationship.delete()

        return {"detail": "Relationships deleted successfully."}
    except SystemContext.DoesNotExist:
        raise HttpError(400, f"SystemContext with ID {system_id} not found.")
    except Exception as e:
        raise HttpError(400, str(e))

@router.get(
    "/systems/{system_id}/instances/properties/connected/",
    response=List[AssociatedPropertySchema],
    tags=["Orchestrator"],
)
def list_associated_properties(request, system_id: int):
    try:
        properties = DigitalTwinInstanceProperty.objects.filter(
            dtinstance__model__system_id=system_id, device_property__isnull=False
        )
        return properties
    except Exception as e:
        raise HttpError(400, str(e))


@router.post(
    "/systems/{system_id}/instances/{dtinstance_id}/properties/{property_id}/connect/",
    response=AssociatePropertySchema,
    tags=["Orchestrator"],
)
def associate_property(
    request,
    system_id: int,
    dtinstance_id: int,
    property_id: int,
    payload: BindDTInstancePropertieDeviceSchema,
):
    try:
        dtinstance = get_object_or_404(
            DigitalTwinInstance, model__system_id=system_id, id=dtinstance_id
        )
        dtproperty = get_object_or_404(
            DigitalTwinInstanceProperty, id=property_id, dtinstance=dtinstance
        )
        device_property = get_object_or_404(Property, id=payload.device_property_id)
        
        dtproperty.device_property = device_property
        dtproperty.save()
        
        return dtproperty
    except DigitalTwinInstance.DoesNotExist:
        raise HttpError(404, "Digital Twin Instance not found.")
    except DigitalTwinInstanceProperty.DoesNotExist:
        raise HttpError(404, "Digital Twin Instance Property not found.")
    except Property.DoesNotExist:
        raise HttpError(404, "Device Property not found.")
    except Exception as e:
        raise HttpError(400, str(e))


@router.post("/systems/{system_id}/instances/query/", tags=["Orchestrator"])
def execute_cypher_query(request, system_id: int, payload: CypherQuerySchema):
    def serialize_neo4j_value(value):
        if isinstance(value, neo4j.graph.Node):
            return {
                "identity": value.id,
                "labels": list(value.labels),
                "properties": dict(value),
                "elementId": value.element_id
            }
        elif isinstance(value, neo4j.graph.Relationship):
            return {
                "id": value.id,
                "type": value.type,
                "start_node": value.start_node.id,
                "end_node": value.end_node.id,
                "properties": dict(value),
                "elementId": value.element_id
            }
        elif isinstance(value, neo4j.graph.Path):
            return {
                "nodes": [serialize_neo4j_value(node) for node in value.nodes],
                "relationships": [serialize_neo4j_value(rel) for rel in value.relationships]
            }
        elif isinstance(value, list):
            return [serialize_neo4j_value(item) for item in value]
        elif isinstance(value, dict):
            return {key: serialize_neo4j_value(val) for key, val in value.items()}
        else:
            return value

    try:
        system_context = SystemContext.objects.get(pk=system_id)
        # Modifica a consulta Cypher para incluir o filtro system_id e trazer os relacionamentos
        filtered_query = f'''
        MATCH (system:SystemContext {{system_id: {system_context.system_id}}})-[:CONTAINS]->(dt_filter:DigitalTwin)
        WITH dt_filter
        {payload.query}
        '''
        results, meta = db.cypher_query(filtered_query)
        # Convert results to a list of dictionaries
        results_list = []
        for record in results:
            if isinstance(record, list):
                record_dict = [serialize_neo4j_value(item) for item in record]
            else:
                record_dict = {key: serialize_neo4j_value(value) for key, value in record.items()}
            results_list.append(record_dict)
        return {"results": results_list, "keys": meta}
    except neo4j.exceptions.CypherSyntaxError as e:
        raise HttpError(400, str(e))
    except neo4j.exceptions.ServiceUnavailable:
        raise HttpError(400, "Neo4j service is unavailable.")
    except Exception as e:
        raise HttpError(400, str(e))


@router.post("/systems/{system_id}/instances/hierarchical/", tags=["Orchestrator"])
def create_hierarchical_instances(request, system_id: int, data: dict = Body(...)):
    """
    Cria instâncias de Digital Twins a partir de um dicionário hierárquico.
    Cada chave é o nome do twin, e os valores são filhos.
    Exemplo de payload:
    {
        "House 1": {
            "Room 1": {
                "LightBulb 1": {},
                "Air conditioner 1": {}
            }
        }
    }
    """


    # Garante que o data é um dicionário (caso venha como JSON string)
    if not isinstance(data, dict):
        from django.http import JsonResponse
        return JsonResponse({"detail": "Payload deve ser um dicionário JSON."}, status=422)

    model = SentenceTransformer("paraphrase-MiniLM-L6-v2")
    dtdl_models = list(DTDLModel.objects.filter(system_id=system_id))
    model_names = [m.name for m in dtdl_models]
    created_instances = []

    def find_best_model(name):
        if not dtdl_models:
            return None, 0.0
        embeddings = model.encode(model_names, convert_to_tensor=True)
        query_emb = model.encode(name, convert_to_tensor=True)
        scores = util.cos_sim(query_emb, embeddings)[0]
        best_idx = int(scores.argmax())
        best_score = float(scores[best_idx])
        if best_score > 0.60:
            return dtdl_models[best_idx], best_score
        return None, best_score

    def recursive_create(tree, parent_instance=None):
        if not isinstance(tree, dict):
            return
        for twin_name, children in tree.items():
            best_model, score = find_best_model(twin_name)
            if not best_model:
                print(f"[MIDDTS] Nenhum modelo DTDL sugerido para '{twin_name}' (score={score:.2f})")
                continue
            dt_instance = DigitalTwinInstance.objects.create(model=best_model, name=twin_name)
            created_instances.append(dt_instance)
            if parent_instance:
                # Buscar relacionamento permitido entre os modelos
                # Corrigido: target pode ser apenas o prefixo do dtdl_id (ex: target='dtmi:housegen:Room', dtdl_id='dtmi:housegen:Room;1')
                rel = ModelRelationship.objects.filter(
                    dtdl_model=parent_instance.model,
                    target__in=[
                        best_model.dtdl_id,
                        best_model.dtdl_id.split(';')[0]
                    ]
                ).first()
                # Se não achou, tenta por prefixo (startswith)
                if not rel:
                    rel = ModelRelationship.objects.filter(
                        dtdl_model=parent_instance.model,
                        target__startswith=best_model.dtdl_id.split(';')[0]
                    ).first()
                if rel:
                    DigitalTwinInstanceRelationship.objects.create(
                        source_instance=parent_instance,
                        target_instance=dt_instance,
                        relationship=rel
                    )
                else:
                    print(f"[MIDDTS] Aviso: Sem relacionamento entre '{parent_instance.model.name}' e '{best_model.name}' (target esperado: '{best_model.dtdl_id.split(';')[0]}')")
            # Recursão para filhos
            if isinstance(children, dict) and children:
                recursive_create(children, dt_instance)
            DigitalTwinInstanceProperty.associate_all_for_instance(dt_instance)

    recursive_create(data)
    # Retorna lista de dicts com id e nome para facilitar debug/consumo
    return [{"id": inst.id, "name": inst.name, "model": inst.model.name} for inst in created_instances]


# Exemplos de queries Cypher para o Neo4j:
# Listar todos os Digital Twins:
# {
#     "query": "MATCH (n) RETURN n LIMIT 25"
# }
# {
#     "query": "MATCH (dt:DigitalTwin) RETURN dt"
# }
# Listar todas as propriedades de um Digital Twin específico:
# {
#     "query": "MATCH (dt:DigitalTwin {name: 'LightBulb'})-[:HAS_PROPERTY]->(prop:TwinProperty) RETURN prop"
# }
# Listar todos os relacionamentos entre Digital Twins:
# {
#     "query": "MATCH (dt1:DigitalTwin)-[r]->(dt2:DigitalTwin) RETURN dt1, r, dt2"
# }
# Buscar um Digital Twin específico pelo nome:
# {
#     "query": "MATCH (dt:DigitalTwin {name: 'LightBulb'}) RETURN dt"
# }
# Listar todas as propriedades e seus valores de um Digital Twin específico:
# {
#     "query": "MATCH (dt:DigitalTwin {name: 'LightBulb'})-[:HAS_PROPERTY]->(prop:TwinProperty) RETURN prop.name, prop.value"
# }
# Listar todos os Digital Twins e suas propriedades:
# {
#     "query": "MATCH (dt:DigitalTwin)-[:HAS_PROPERTY]->(prop:TwinProperty) RETURN dt.name, prop.name, prop.value"
# }
# Listar todos os Digital Twins do modelo LightBulb1 que possuem uma propriedade status = true:
# {
#     "query": "MATCH (dt:DigitalTwin {model_name: 'LightBulb1'})-[:HAS_PROPERTY]->(tp:TwinProperty {name: 'status', value: 'true'}) RETURN dt"
# }
# Listar todos os Digital Twins que possuem uma propriedade status = true:
# {
#     "query": "MATCH (dt:DigitalTwin)-[:HAS_PROPERTY]->(tp:TwinProperty {name: 'status', value: 'true'}) RETURN dt"
# }
# Listar Todos os AirConditioners com temperatura abaixo de 20
# {
#     "query": "MATCH (dt:DigitalTwin {model_name: 'AirConditioner'})-[:HAS_PROPERTY]->(tp:TwinProperty {name: 'temperature'}) WHERE toFloat(tp.value) < 20 RETURN dt"
# }
# Consulta todos os Digital Twins inativos
# MATCH (dt:DigitalTwin {active: false}) 
# RETURN dt

# # Consulta as últimas telemetrias de dispositivos inativos
# MATCH (dt:DigitalTwin {active: false})-[:HAS_PROPERTY]->(tp:TwinProperty)
# RETURN dt.name, tp.name, tp.value, tp.timestamp
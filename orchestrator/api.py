from django.shortcuts import get_object_or_404
import neo4j
import neo4j.exceptions
from pydantic import ValidationError
from core.models import Organization, OrganizationMembership

from facade.models import Property
from orchestrator.schemas import (
    AssociatePropertySchema,
    AutoBindingApplyRequestSchema,
    AutoBindingApplyResponseSchema,
    AutoBindingCandidateSchema,
    AutoBindingPreviewRequestSchema,
    AutoBindingPreviewResponseSchema,
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
    InfluxTemporalQueryResponseSchema,
    InfluxTemporalQuerySchema,
    PutDTDLModelSchema,
    SystemContextSchema,
    TemporalPointSchema,
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
from orchestrator.utils import normalize_name
from django.conf import settings
from django.utils.text import slugify
import csv
import io
import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

router = Router()

from .helpers import (
    _get_user_organizations,
    _resolve_current_organization,
    _scope_systems_to_organization,
    _get_scoped_system_or_404,
    _scope_properties_to_organization,
    _scope_system_properties,
    _filter_candidate_device_properties,
    _load_sentence_model,
    _build_dt_property_text,
    _build_device_property_text,
    _to_canonical_slug,
    _canonical_slug_similarity,
    _build_dt_property_canonical,
    _build_device_property_canonical,
    _tokenize_for_matching,
    _extract_identifier_tokens,
    _compute_hybrid_match_score,
    _suggest_autobinding_candidates,
    _parse_influx_csv_points,
    compute_similarity,
)


@router.post(
    "/systems/",
    response=SystemContextSchema,
    tags=["Orchestrator"],
)
def create_system(request, payload: CreateSystemContextSchema):
    payload_data = payload.dict()
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        raise HttpError(403, "Authentication required")
    organization = _resolve_current_organization(request)
    if not organization:
        raise HttpError(400, "Could not resolve organization for current user")
    payload_data['organization'] = organization
    payload_data['created_by'] = user
    system = SystemContext.objects.create(**payload_data)
    return system

@router.put(
    "/systems/{system_id}/",
    response=SystemContextSchema,
    tags=["Orchestrator"],
)
def update_system(request, system_id: int, payload: CreateSystemContextSchema):
    system = _get_scoped_system_or_404(request, system_id)
    for attr, value in payload.dict().items():
        setattr(system, attr, value)
    system.save()
    return system


@router.get(
    "/systems/{system_id}/", response=SystemContextSchema, tags=["Orchestrator"]
)
def get_system(request, system_id: int):
    system = _get_scoped_system_or_404(request, system_id)
    return system


@router.get("/systems/", response=list[SystemContextSchema], tags=["Orchestrator"])
def list_system(request):
    systems = _scope_systems_to_organization(SystemContext.objects.all(), request)
    return systems


@router.post(
    "/systems/{system_id}/dtdlmodels/", response=DTDLModelSchema, tags=["Orchestrator"]
)
def create_dtdlmodel(request, system_id, payload: CreateDTDLModelSchema):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        raise HttpError(403, "Authentication required")
    system = _get_scoped_system_or_404(request, system_id)
    payload_data = payload.dict()
    payload_data["system"] = system
    payload_data["created_by"] = user
    dtdlmodel = DTDLModel.objects.create(**payload_data)
    return dtdlmodel

@router.post(
    "/systems/{system_id}/dtdlmodels/bulk/", response=List[DTDLModelSchema], tags=["Orchestrator"]
)
def create_multiple_dtdlmodels(request, system_id: int, payload: List[DTDLSpecificationSchema]):
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        raise HttpError(403, "Authentication required")
    system = _get_scoped_system_or_404(request, system_id)
    created_models = []
    for spec in payload:
        payload_data = {
            "system": system,
            "name": spec.displayName,
            "created_by": user,
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
    _get_scoped_system_or_404(request, system_id)
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
    _get_scoped_system_or_404(request, system_id)
    queryset = DTDLModel.objects.filter(system_id=system_id)
    return queryset


@router.get(
    "/systems/{system_id}/dtdlmodels/{dtdl_model_id}/",
    response=DTDLModelSchema,
    tags=["Orchestrator"],
)
def get_dtdlmodel(request, system_id: int, dtdl_model_id: int):
    _get_scoped_system_or_404(request, system_id)
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
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        raise HttpError(403, "Authentication required")
    try:
        system = _get_scoped_system_or_404(request, system_id)
        created_models = []

        for model_data in payload:
            dtdl_model, created = DTDLModel.objects.update_or_create(
                system=system,
                name=model_data.name,
                defaults={"specification": model_data.specification, "created_by": user},
            )
            created_models.append({"id": dtdl_model.id, "name": dtdl_model.name})

        return {"created_models": created_models}
    except SystemContext.DoesNotExist:
        raise HttpError(404, "System not found")
    except Exception as e:
        raise HttpError(400, str(e))


@router.get(
    "/systems/{system_id}/neo4j/test/",
    tags=["Orchestrator"],
    summary="Quick Neo4j connectivity/test endpoint",
    description="Runs a small read Cypher query against Neo4j and returns a serialized sample of nodes/relationships. Useful to verify connectivity and inspect DB contents.",
)
def neo4j_test(request, system_id: int):
    try:
        _get_scoped_system_or_404(request, system_id)
        if not getattr(settings, 'USE_NEO4J', False):
            raise HttpError(400, "Neo4j integration is disabled (USE_NEO4J=False)")

        sample_query = "MATCH (n) RETURN n LIMIT 25"

        def _run_query(q):
            return db.cypher_query(q)

        timeout_val = getattr(settings, 'CYPHER_QUERY_TIMEOUT', 10)
        try:
            with ThreadPoolExecutor(max_workers=1) as _executor:
                future = _executor.submit(_run_query, sample_query)
                results, meta = future.result(timeout=timeout_val)
        except FuturesTimeout:
            try:
                future.cancel()
            except Exception:
                pass
            raise HttpError(504, f"Neo4j test query timed out after {timeout_val} seconds")

        def _serialize(value):
            if isinstance(value, neo4j.graph.Node):
                return {"identity": value.id, "labels": list(value.labels), "properties": dict(value)}
            if isinstance(value, neo4j.graph.Relationship):
                return {"id": value.id, "type": value.type, "start": value.start_node.id, "end": value.end_node.id, "properties": dict(value)}
            if isinstance(value, list):
                return [_serialize(v) for v in value]
            if isinstance(value, dict):
                return {k: _serialize(v) for k, v in value.items()}
            return value

        out = []
        for rec in results:
            if isinstance(rec, list):
                out.append([_serialize(it) for it in rec])
            elif isinstance(rec, dict):
                out.append({k: _serialize(v) for k, v in rec.items()})
            else:
                out.append(_serialize(rec))

        return {"results": out, "meta_keys": meta}
    except neo4j.exceptions.ServiceUnavailable:
        raise HttpError(400, "Neo4j service is unavailable.")
    except Exception as e:
        raise HttpError(400, str(e))


@router.get(
    "/orchestrator/debug-auth/",
    tags=["Orchestrator"],
    summary="Debug current request user",
)
def debug_auth(request):
    user = getattr(request, 'user', None)
    try:
        username = getattr(user, 'username', None)
        is_auth = getattr(user, 'is_authenticated', False)
        user_id = getattr(user, 'id', None)
    except Exception:
        username = None
        is_auth = False
        user_id = None
    return {"username": username, "is_authenticated": bool(is_auth), "user_id": user_id}


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

    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        raise HttpError(403, "Authentication required")
    _get_scoped_system_or_404(request, system_id)
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
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            raise HttpError(403, "Authentication required")
        _get_scoped_system_or_404(request, system_id)
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
    get_object_or_404(_scope_systems_to_organization(SystemContext.objects.all(), request), id=system_id)
    return [
        dti for dti in DigitalTwinInstance.objects.filter(model__system_id=system_id)
    ]


@router.get(
    "/systems/{system_id}/instances/{dtinstance_id}",
    response=DigitalTwinInstanceSchema,
    tags=["Orchestrator"],
)
def get_instance(request, system_id: int, dtinstance_id: int):
    get_object_or_404(_scope_systems_to_organization(SystemContext.objects.all(), request), id=system_id)
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
    _get_scoped_system_or_404(request, system_id)
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
    device_property = _scope_properties_to_organization(Property.objects.all(), request).filter(
        id=payload_data["device_property_id"]
    ).first()
    if not dtproperty or not device_property:
        raise HttpError(404, "Property binding target not found.")
    DigitalTwinInstanceProperty.objects.filter(pk=dtproperty.pk).update(device_property=device_property)
    dtproperty.device_property = device_property
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
        _get_scoped_system_or_404(request, system_id)
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

        # Atualiza o valor da propriedade a partir da RESPOSTA do dispositivo.
        # Não deve repropagar para o device (evita loop/eco de RPC e duplicação de sent_timestamp).
        property_obj.value = payload.value
        property_obj.save(
            propagate_to_device=False,
            correlation_id=getattr(payload, 'correlation_id', None)
        )
        
        # Captura timestamp de resposta M2S para correção de latência
        try:
            import time
            from facade.utils import format_influx_line
            from django.conf import settings as _dj_settings

            INFLUXDB_TOKEN = getattr(_dj_settings, 'INFLUXDB_TOKEN', None)
            INFLUXDB_URL = getattr(_dj_settings, 'INFLUXDB_URL', None)
            USE_INFLUX_TO_EVALUATE = getattr(_dj_settings, 'USE_INFLUX_TO_EVALUATE', False)
            ENABLE_INFLUX_LATENCY_MEASUREMENTS = getattr(_dj_settings, 'ENABLE_INFLUX_LATENCY_MEASUREMENTS', False)

            print(f"[DEBUG] M2S response received for property {property_obj.name}")
            print(f"[DEBUG] correlation_id from payload: {getattr(payload, 'correlation_id', None)}")

            if (USE_INFLUX_TO_EVALUATE and ENABLE_INFLUX_LATENCY_MEASUREMENTS and INFLUXDB_TOKEN and 
                property_obj.device_property and property_obj.device_property.device):
                response_timestamp = int(time.time() * 1000)
                sensor_id = property_obj.device_property.device.identifier
                correlation_id = getattr(payload, 'correlation_id', None)
                
                # Write received_timestamp to latency_measurement (same measurement as sent_timestamp)
                tags = {"sensor": sensor_id, "source": "middts", "direction": "M2S"}
                if correlation_id:
                    tags["correlation_id"] = str(correlation_id)
                
                # Include property value and timestamps
                fields = {
                    "received_timestamp": response_timestamp,
                    "status": 1.0 if payload.value else 0.0,
                    property_obj.name: (1.0 if payload.value else 0.0) if isinstance(payload.value, bool) else float(payload.value)
                }
                data = format_influx_line("latency_measurement", tags, fields, timestamp=response_timestamp)
                
                import requests
                resp = requests.post(
                    INFLUXDB_URL,
                    headers={"Authorization": f"Token {INFLUXDB_TOKEN}", "Content-Type": "text/plain"},
                    data=data,
                    timeout=0.5
                )
                if resp.status_code == 204:
                    print(f"[M2S-RESPONSE] ✅ Logged received_timestamp for {sensor_id} (correlation_id={correlation_id})")
                else:
                    print(f"[M2S-RESPONSE] ⚠️ Failed: {resp.status_code} - {resp.text}")
            else:
                print(f"[M2S-RESPONSE] SKIP - latency measurements disabled or missing data")
        except Exception as e:
            print(f"[ERROR] M2S timestamp logging failed: {e}")
            import traceback
            traceback.print_exc()
        
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
        _get_scoped_system_or_404(request, system_id)
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
        system_context = _get_scoped_system_or_404(request, system_id)
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
        system_context = _get_scoped_system_or_404(request, system_id)
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
            source_instance = DigitalTwinInstance.objects.filter(id=source_instance_id, model__system=system_context).first()
            target_instance = DigitalTwinInstance.objects.filter(id=target_instance_id, model__system=system_context).first()

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
        system_context = _get_scoped_system_or_404(request, system_id)
        for rel in relationships:
            # Verifica se o relacionamento é permitido pelo modelo
            model_relationship = ModelRelationship.objects.filter(
                dtdl_model__system=system_context, name=rel.relationship_name
            ).first()

            if not model_relationship:
                raise HttpError(400, f"Relationship '{rel.relationship_name}' is not defined in the model for system {system_id}.")

            # Verifica se as instâncias digitais de origem e destino existem
            source_instance = DigitalTwinInstance.objects.filter(id=rel.source_instance_id, model__system=system_context).first()
            target_instance = DigitalTwinInstance.objects.filter(id=rel.target_instance_id, model__system=system_context).first()

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
        _get_scoped_system_or_404(request, system_id)
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
    summary="Associate a DT property to a specific device property",
    description="Manual binding endpoint. Use this when you want deterministic association instead of semantic autobinding.",
)
def associate_property(
    request,
    system_id: int,
    dtinstance_id: int,
    property_id: int,
    payload: BindDTInstancePropertieDeviceSchema,
):
    try:
        _get_scoped_system_or_404(request, system_id)
        dtinstance = get_object_or_404(
            DigitalTwinInstance, model__system_id=system_id, id=dtinstance_id
        )
        dtproperty = get_object_or_404(
            DigitalTwinInstanceProperty, id=property_id, dtinstance=dtinstance
        )
        device_property = get_object_or_404(_scope_properties_to_organization(Property.objects.all(), request), id=payload.device_property_id)

        DigitalTwinInstanceProperty.objects.filter(pk=dtproperty.pk).update(device_property=device_property)
        dtproperty.device_property = device_property
        
        return dtproperty
    except DigitalTwinInstance.DoesNotExist:
        raise HttpError(404, "Digital Twin Instance not found.")
    except DigitalTwinInstanceProperty.DoesNotExist:
        raise HttpError(404, "Digital Twin Instance Property not found.")
    except Property.DoesNotExist:
        raise HttpError(404, "Device Property not found.")
    except Exception as e:
        raise HttpError(400, str(e))


@router.post(
    "/systems/{system_id}/instances/autobinding/preview/",
    response=AutoBindingPreviewResponseSchema,
    tags=["Orchestrator"],
    summary="Preview semantic autobinding suggestions",
    description="Runs semantic matching between DT causal properties and device properties without persisting changes.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "default": {
                            "value": {
                                "threshold": 0.65,
                                "only_unbound": True,
                                "causal_only": True,
                                "allow_device_property_reuse": False,
                                "gateway_ids": [1],
                                "limit": 50
                            }
                        }
                    }
                }
            }
        }
    },
)
def preview_autobinding(request, system_id: int, payload: AutoBindingPreviewRequestSchema):
    system_context = _get_scoped_system_or_404(request, system_id)
    candidates = _suggest_autobinding_candidates(system_context, payload)
    return AutoBindingPreviewResponseSchema(
        system_id=system_context.id,
        threshold=float(payload.threshold),
        candidates=candidates,
    )


@router.post(
    "/systems/{system_id}/instances/autobinding/apply/",
    response=AutoBindingApplyResponseSchema,
    tags=["Orchestrator"],
    summary="Apply semantic autobinding",
    description="Persists semantic autobinding suggestions according to threshold and overwrite rules.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "safe_apply": {
                            "value": {
                                "threshold": 0.70,
                                "only_unbound": True,
                                "causal_only": True,
                                "allow_device_property_reuse": False,
                                "overwrite_existing": False,
                                "gateway_ids": [1],
                                "limit": 100
                            }
                        }
                    }
                }
            }
        }
    },
)
def apply_autobinding(request, system_id: int, payload: AutoBindingApplyRequestSchema):
    system_context = _get_scoped_system_or_404(request, system_id)
    preview_payload = AutoBindingPreviewRequestSchema(
        threshold=payload.threshold,
        only_unbound=payload.only_unbound,
        causal_only=payload.causal_only,
        limit=payload.limit,
        allow_device_property_reuse=payload.allow_device_property_reuse,
        device_ids=payload.device_ids,
        gateway_ids=payload.gateway_ids,
    )
    candidates = _suggest_autobinding_candidates(system_context, preview_payload)

    evaluated = len(candidates)
    applied = 0
    skipped = 0
    applied_details = []

    with transaction.atomic():
        for candidate in candidates:
            dtip = DigitalTwinInstanceProperty.objects.filter(
                id=candidate.dt_property_id,
                dtinstance__model__system=system_context,
            ).first()
            device_property = _scope_system_properties(system_context).filter(
                id=candidate.device_property_id
            ).first()

            if not dtip or not device_property:
                skipped += 1
                continue

            if dtip.device_property_id and not payload.overwrite_existing:
                skipped += 1
                continue

            if (not payload.allow_device_property_reuse and
                DigitalTwinInstanceProperty.objects.filter(device_property=device_property).exclude(id=dtip.id).exists()):
                skipped += 1
                continue

            DigitalTwinInstanceProperty.objects.filter(pk=dtip.pk).update(device_property=device_property)
            dtip.device_property = device_property
            applied += 1
            applied_details.append(candidate)

    return AutoBindingApplyResponseSchema(
        system_id=system_context.id,
        threshold=float(payload.threshold),
        evaluated=evaluated,
        applied=applied,
        skipped=skipped,
        details=applied_details,
    )


@router.post(
    "/systems/{system_id}/timeseries/query/",
    response=InfluxTemporalQueryResponseSchema,
    tags=["Orchestrator"],
    summary="Query temporal data from InfluxDB",
    description="Queries time series with organization and system scope checks. Requires device_identifier for strict scoping.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "last_2h_temperature": {
                            "value": {
                                "device_identifier": "b6ac7f00-6f6c-11ef-987f-9f26ab123456",
                                "property_name": "temperature",
                                "measurement": "latency_measurement",
                                "last_minutes": 120,
                                "limit": 300
                            }
                        }
                        ,
                        "from_dt_property": {
                            "value": {
                                "dt_property_id": 42,
                                "measurement": "latency_measurement",
                                "last_minutes": 60,
                                "limit": 200
                            }
                        },
                        "from_dtinstance_and_property": {
                            "value": {
                                "dtinstance_id": 15,
                                "property_name": "status",
                                "measurement": "latency_measurement",
                                "last_minutes": 30,
                                "limit": 100
                            }
                        }
                    }
                }
            }
        }
    },
)
def query_temporal_data(request, system_id: int, payload: InfluxTemporalQuerySchema):
    system_context = _get_scoped_system_or_404(request, system_id)

    # Resolve device_identifier and property_name from DT-centric inputs when provided
    device_identifier = None
    property_name = payload.property_name

    if getattr(payload, 'dt_property_id', None):
        dtip = DigitalTwinInstanceProperty.objects.filter(
            id=payload.dt_property_id,
            dtinstance__model__system=system_context,
        ).select_related('device_property', 'device_property__device').first()
        if not dtip:
            raise HttpError(404, "DigitalTwinInstanceProperty not found in the given system")
        if not dtip.device_property or not getattr(dtip.device_property, 'device', None) or not getattr(dtip.device_property.device, 'identifier', None):
            raise HttpError(409, "Digital twin property is not bound to a device")
        device_identifier = dtip.device_property.device.identifier
        property_name = property_name or (dtip.property.name if dtip.property else None)
    elif getattr(payload, 'dtinstance_id', None) and getattr(payload, 'property_name', None):
        dtip = DigitalTwinInstanceProperty.objects.filter(
            dtinstance__model__system=system_context,
            dtinstance__id=payload.dtinstance_id,
            property__name=payload.property_name,
        ).select_related('device_property', 'device_property__device').first()
        if not dtip:
            raise HttpError(404, "DigitalTwinInstanceProperty not found for given dtinstance and property")
        if not dtip.device_property or not getattr(dtip.device_property, 'device', None) or not getattr(dtip.device_property.device, 'identifier', None):
            raise HttpError(409, "Digital twin property is not bound to a device")
        device_identifier = dtip.device_property.device.identifier
        property_name = payload.property_name
    else:
        device_identifier = payload.device_identifier

    if not device_identifier:
        raise HttpError(400, "device_identifier or dt_property_id or (dtinstance_id + property_name) is required for scoped temporal queries")

    scoped_props = _scope_system_properties(system_context).filter(device__identifier=device_identifier)
    if not scoped_props.exists():
        raise HttpError(404, "Device not found in the current organization scope")

    system_bound_props = DigitalTwinInstanceProperty.objects.filter(
        dtinstance__model__system=system_context,
        device_property__device__identifier=device_identifier,
    )
    if not system_bound_props.exists():
        raise HttpError(409, "Device is in the organization scope but is not currently bound to the requested system")

    influx_token = getattr(settings, "INFLUXDB_TOKEN", None)
    influx_org = getattr(settings, "INFLUXDB_ORGANIZATION", None)
    influx_bucket = getattr(settings, "INFLUXDB_BUCKET", None)
    influx_host = getattr(settings, "INFLUXDB_HOST", "influxdb")
    influx_port = int(getattr(settings, "INFLUXDB_PORT", 8086))
    if not influx_token or not influx_org or not influx_bucket:
        raise HttpError(400, "InfluxDB is not fully configured")

    measurement = payload.measurement or "latency_measurement"
    limit = max(1, min(int(payload.limit), 5000))
    if payload.start and payload.stop:
        range_clause = f'|> range(start: time(v: "{payload.start}"), stop: time(v: "{payload.stop}"))'
    else:
        last_minutes = max(1, int(payload.last_minutes))
        range_clause = f"|> range(start: -{last_minutes}m)"

    field_filter = ""
    if property_name:
        field_filter = f'|> filter(fn: (r) => r["_field"] == "{property_name}")'

    flux_query = (
        f'from(bucket: "{influx_bucket}")\n'
        f'{range_clause}\n'
        f'|> filter(fn: (r) => r["_measurement"] == "{measurement}")\n'
        f'|> filter(fn: (r) => r["sensor"] == "{payload.device_identifier}")\n'
        f'{field_filter}\n'
        f'|> sort(columns: ["_time"], desc: false)\n'
        f'|> limit(n: {limit})'
    )

    query_url = f"http://{influx_host}:{influx_port}/api/v2/query?org={influx_org}"
    response = requests.post(
        query_url,
        headers={
            "Authorization": f"Token {influx_token}",
            "Content-Type": "application/vnd.flux",
            "Accept": "text/csv",
        },
        data=flux_query,
        timeout=10,
    )
    if response.status_code != 200:
        raise HttpError(response.status_code, response.text)

    raw_points = _parse_influx_csv_points(response.text)
    points = []
    for row in raw_points:
        points.append(
            TemporalPointSchema(
                time=row.get("_time", ""),
                measurement=row.get("_measurement", ""),
                field=row.get("_field", ""),
                value=row.get("_value"),
                device_identifier=row.get("sensor"),
                tags={
                    "direction": row.get("direction"),
                    "source": row.get("source"),
                    "correlation_id": row.get("correlation_id"),
                },
            )
        )

    return InfluxTemporalQueryResponseSchema(
        system_id=system_context.id,
        device_identifier=payload.device_identifier,
        points=points,
    )


@router.post(
    "/systems/{system_id}/instances/query/",
    tags=["Orchestrator"],
    summary="Execute scoped Cypher query",
    description="Executes a Cypher query anchored on dt_filter nodes constrained to the requested system context.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "scoped_traversal": {
                            "value": {
                                "query": "MATCH (dt_filter)-[r]->(n) RETURN dt_filter, r, n LIMIT 25"
                            }
                        }
                    }
                }
            }
        }
    },
)
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
        system_context = _get_scoped_system_or_404(request, system_id)
        if "dt_filter" not in payload.query:
            raise HttpError(400, "Cypher query must reference alias 'dt_filter' to keep system scoping")

        filtered_query = f'''
        MATCH (system:SystemContext {{system_id: {system_context.id}}})-[:CONTAINS]->(dt_filter:DigitalTwin)
        WITH dt_filter
        {payload.query}
        '''

        def _run_query(q):
            return db.cypher_query(q)

        timeout_val = getattr(settings, 'CYPHER_QUERY_TIMEOUT', 10)
        max_rows = getattr(settings, 'CYPHER_QUERY_MAX_ROWS', 1000)
        try:
            with ThreadPoolExecutor(max_workers=1) as _executor:
                future = _executor.submit(_run_query, filtered_query)
                results, meta = future.result(timeout=timeout_val)
        except FuturesTimeout:
            try:
                future.cancel()
            except Exception:
                pass
            raise HttpError(504, f"Cypher query timed out after {timeout_val} seconds")
        # Convert results to a list of dictionaries
        results_list = []
        for record in results:
            if isinstance(record, list):
                record_dict = [serialize_neo4j_value(item) for item in record]
            else:
                record_dict = {key: serialize_neo4j_value(value) for key, value in record.items()}
            results_list.append(record_dict)
        # Enforce max rows configured to avoid returning huge result sets
        if len(results_list) > max_rows:
            results_list = results_list[:max_rows]

        return {"results": results_list, "keys": meta}
    except neo4j.exceptions.CypherSyntaxError as e:
        raise HttpError(400, str(e))
    except neo4j.exceptions.ServiceUnavailable:
        raise HttpError(400, "Neo4j service is unavailable.")
    except Exception as e:
        raise HttpError(400, str(e))


@router.post(
    "/systems/{system_id}/instances/hierarchical/",
    tags=["Orchestrator"],
    summary="Create hierarchical digital twin instances",
    description="Creates DT instances from a tree payload and infers the best DTDL model per node with configurable semantic threshold.",
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "house_tree": {
                            "value": {
                                "House 1": {
                                    "Room 1": {
                                        "LightBulb 1": {},
                                        "AirConditioner 1": {}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    },
)
def create_hierarchical_instances(
    request,
    system_id: int,
    data: dict = Body(...),
    similarity_threshold: float = 0.60,
):
    system_context = _get_scoped_system_or_404(request, system_id)
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

    if similarity_threshold < 0.0 or similarity_threshold > 1.0:
        raise HttpError(400, "similarity_threshold must be between 0.0 and 1.0")

    dtdl_models = list(DTDLModel.objects.filter(system=system_context))
    created_instances = []

    def find_best_model(name):
        if not dtdl_models:
            return None, 0.0
        best_idx = None
        best_score = 0.0
        for idx, m in enumerate(dtdl_models):
            score = float(compute_similarity(name, m.name))
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx is not None and best_score >= float(similarity_threshold):
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
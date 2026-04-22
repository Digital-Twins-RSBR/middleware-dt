from django.shortcuts import get_object_or_404
from ninja.errors import HttpError
from sentence_transformers import SentenceTransformer, util
from django.utils.text import slugify
from orchestrator.utils import normalize_name
from typing import List
from django.db import transaction
import csv
import io

from core.models import Organization
from facade.models import Property
from .models import (
    DigitalTwinInstanceProperty,
    SystemContext,
    DigitalTwinInstance,
    DTDLModel,
    ModelRelationship,
)
from orchestrator.schemas import AutoBindingCandidateSchema


def _get_user_organizations(user):
    if getattr(user, "is_superuser", False):
        return Organization.objects.all()
    if not user or not getattr(user, "is_authenticated", False):
        return Organization.objects.none()
    return Organization.objects.filter(memberships__user=user).distinct()


def _resolve_current_organization(request, organization_id: int = None):
    organizations = _get_user_organizations(getattr(request, "user", None))
    if organization_id is not None:
        return organizations.filter(id=organization_id).first()
    return organizations.first() if organizations.count() == 1 else None


def _scope_systems_to_organization(queryset, request):
    user = getattr(request, "user", None)
    if getattr(user, "is_superuser", False):
        return queryset
    if not user or not getattr(user, "is_authenticated", False):
        return queryset.none()
    return queryset.filter(organization__memberships__user=user).distinct()


def _get_scoped_system_or_404(request, system_id: int):
    return get_object_or_404(_scope_systems_to_organization(SystemContext.objects.all(), request), id=system_id)


def _scope_properties_to_organization(queryset, request):
    user = getattr(request, "user", None)
    if getattr(user, "is_superuser", False):
        return queryset
    if not user or not getattr(user, "is_authenticated", False):
        return queryset.none()
    return queryset.filter(device__organization__memberships__user=user).distinct()


def _scope_system_properties(system_context: SystemContext):
    queryset = Property.objects.all()
    if system_context.organization_id:
        return queryset.filter(device__organization_id=system_context.organization_id).distinct()
    return queryset.none()


def _filter_candidate_device_properties(queryset, payload):
    device_ids = getattr(payload, "device_ids", None) or []
    gateway_ids = getattr(payload, "gateway_ids", None) or []
    if device_ids:
        queryset = queryset.filter(device_id__in=device_ids)
    if gateway_ids:
        queryset = queryset.filter(device__gateway_id__in=gateway_ids)
    return queryset


def _load_sentence_model():
    return SentenceTransformer("all-MiniLM-L6-v2")


def _build_dt_property_text(dtip: DigitalTwinInstanceProperty):
    hierarchy = dtip.get_hierarchy()
    norm_hierarchy = [normalize_name(h) for h in hierarchy]
    model_name = normalize_name(dtip.dtinstance.model.name if dtip.dtinstance and dtip.dtinstance.model else "")
    schema_name = normalize_name(dtip.property.schema or "") if dtip.property else ""
    return " ".join(norm_hierarchy + [model_name, schema_name]).strip()


def _build_device_property_text(prop: Property):
    metadata = normalize_name(prop.device.metadata or "") if prop.device else ""
    device_name = normalize_name(prop.device.name if prop.device else "")
    dtype_name = normalize_name(prop.device.type.name if prop.device and prop.device.type else "")
    property_name = normalize_name(prop.name or "")
    property_type = normalize_name(str(prop.type or ""))
    return " ".join([device_name, dtype_name, metadata, property_name, property_type]).strip()


def _to_canonical_slug(text: str):
    normalized = normalize_name(text or "")
    return slugify(normalized, allow_unicode=False)


def _canonical_slug_similarity(left: str, right: str):
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_tokens = set(left.split("-"))
    right_tokens = set(right.split("-"))
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(left_tokens & right_tokens) / len(union)


def _build_dt_property_canonical(dtip: DigitalTwinInstanceProperty):
    hierarchy = " ".join(dtip.get_hierarchy()) if hasattr(dtip, "get_hierarchy") else ""
    prop_name = dtip.property.name if dtip.property else ""
    return _to_canonical_slug(f"{hierarchy} {prop_name}".strip())


def _build_device_property_canonical(prop: Property):
    device_name = prop.device.name if prop and prop.device else ""
    prop_name = prop.name if prop else ""
    return _to_canonical_slug(f"{device_name} {prop_name}".strip())


def _tokenize_for_matching(text: str):
    normalized = normalize_name(text)
    tokens = [t for t in normalized.split() if t]
    numeric = {t for t in tokens if t.isdigit()}
    lexical = set(tokens)
    return lexical, numeric


def _extract_identifier_tokens(name: str):
    tokens = [t for t in normalize_name(name).split() if t]
    identifiers = set()
    for token in tokens:
        has_digit = any(ch.isdigit() for ch in token)
        if has_digit:
            identifiers.add(token)
            continue
        if token.isalpha() and len(token) <= 2:
            identifiers.add(token)
    return identifiers


def _compute_hybrid_match_score(
    dt_text: str,
    device_text: str,
    semantic_score: float,
    dt_identifiers=None,
    device_identifiers=None,
    dt_canonical: str = "",
    device_canonical: str = "",
):
    dt_tokens, dt_numbers = _tokenize_for_matching(dt_text)
    dev_tokens, dev_numbers = _tokenize_for_matching(device_text)

    union = dt_tokens | dev_tokens
    lexical_score = (len(dt_tokens & dev_tokens) / len(union)) if union else 0.0
    canonical_score = _canonical_slug_similarity(dt_canonical, device_canonical)

    number_union = dt_numbers | dev_numbers
    numeric_score = (len(dt_numbers & dev_numbers) / len(number_union)) if number_union else 0.0

    numeric_penalty = 0.0
    if dt_numbers and dev_numbers and not (dt_numbers & dev_numbers):
        numeric_penalty = 0.20

    id_penalty = 0.0
    dt_ids = set(dt_identifiers or set())
    dev_ids = set(device_identifiers or set())
    if dt_ids and dev_ids and not (dt_ids & dev_ids):
        id_penalty = 0.12

    blended = (
        (0.68 * float(semantic_score))
        + (0.17 * lexical_score)
        + (0.05 * numeric_score)
        + (0.10 * canonical_score)
    )
    blended -= (numeric_penalty + id_penalty)
    return max(0.0, min(1.0, blended))


def _suggest_autobinding_candidates(system_context: SystemContext, payload):
    threshold = float(payload.threshold)
    if threshold < 0.0 or threshold > 1.0:
        raise HttpError(400, "threshold must be between 0.0 and 1.0")

    dt_props_qs = DigitalTwinInstanceProperty.objects.filter(
        dtinstance__model__system=system_context
    ).select_related("dtinstance", "dtinstance__model", "property", "device_property")

    if payload.only_unbound:
        dt_props_qs = dt_props_qs.filter(device_property__isnull=True)

    dt_props = list(dt_props_qs)
    if payload.causal_only:
        dt_props = [row for row in dt_props if row.property and row.property.isCausal()]

    scoped_device_props = _filter_candidate_device_properties(
        _scope_system_properties(system_context).select_related("device", "device__type", "device__gateway"),
        payload,
    )
    if not payload.allow_device_property_reuse:
        scoped_device_props = scoped_device_props.filter(digitaltwininstanceproperty__isnull=True)
    device_props = list(scoped_device_props)

    if not dt_props or not device_props:
        return []

    sentence_model = _load_sentence_model()
    device_texts = [_build_device_property_text(p) for p in device_props]
    device_canonicals = [_build_device_property_canonical(p) for p in device_props]
    device_embeddings = sentence_model.encode(device_texts, convert_to_tensor=True)

    candidate_pairs = []
    for dtip in dt_props:
        dt_text = _build_dt_property_text(dtip)
        if not dt_text:
            continue
        dt_identifiers = _extract_identifier_tokens(dtip.dtinstance.name if dtip.dtinstance else "")
        dt_canonical = _build_dt_property_canonical(dtip)
        dt_emb = sentence_model.encode(dt_text, convert_to_tensor=True)
        scores = util.cos_sim(dt_emb, device_embeddings)[0]
        for idx, raw_score in enumerate(scores):
            semantic_score = float(raw_score)
            device_text = device_texts[idx]
            device_name = device_props[idx].device.name if device_props[idx].device else ""
            device_identifiers = _extract_identifier_tokens(device_name)
            score = _compute_hybrid_match_score(
                dt_text,
                device_text,
                semantic_score,
                dt_identifiers=dt_identifiers,
                device_identifiers=device_identifiers,
                dt_canonical=dt_canonical,
                device_canonical=device_canonicals[idx],
            )
            if score < threshold:
                continue
            prop = device_props[idx]
            if not prop.device:
                continue
            candidate_pairs.append(
                (
                    score,
                    dtip.id,
                    prop.id,
                    AutoBindingCandidateSchema(
                        dt_property_id=dtip.id,
                        dt_instance_id=dtip.dtinstance_id,
                        dt_instance_name=dtip.dtinstance.name,
                        dt_property_name=dtip.property.name,
                        dt_model_name=dtip.dtinstance.model.name,
                        device_property_id=prop.id,
                        device_property_name=prop.name,
                        device_id=prop.device_id,
                        device_name=prop.device.name,
                        score=round(score, 4),
                    ),
                )
            )

    if not candidate_pairs:
        return []

    candidate_pairs.sort(key=lambda row: row[0], reverse=True)
    selected = []
    used_dt_property_ids = set()
    used_device_property_ids = set()
    allow_reuse = bool(payload.allow_device_property_reuse)
    max_results = max(0, int(payload.limit))

    for _, dt_property_id, device_property_id, candidate in candidate_pairs:
        if dt_property_id in used_dt_property_ids:
            continue
        if not allow_reuse and device_property_id in used_device_property_ids:
            continue
        selected.append(candidate)
        used_dt_property_ids.add(dt_property_id)
        if not allow_reuse:
            used_device_property_ids.add(device_property_id)
        if len(selected) >= max_results:
            break

    return selected


def _parse_influx_csv_points(response_text: str):
    points = []
    reader = csv.DictReader(io.StringIO("\n".join(
        line for line in response_text.splitlines() if line and not line.startswith("#")
    )))
    for row in reader:
        if not row:
            continue
        points.append(row)
    return points


def compute_similarity(text_a: str, text_b: str, model_name: str = None):
    """Compute semantic similarity between two texts using sentence-transformers.
    Falls back to lexical Jaccard if model is unavailable or encoding fails.
    """
    try:
        from sentence_transformers import SentenceTransformer, util
        model = SentenceTransformer(model_name or "all-MiniLM-L6-v2")
        emb_a = model.encode(text_a or "", convert_to_tensor=True)
        emb_b = model.encode(text_b or "", convert_to_tensor=True)
        return float(util.cos_sim(emb_a, emb_b)[0][0])
    except Exception:
        import re
        sa = set([t for t in re.split(r"\W+", (text_a or "").lower()) if t])
        sb = set([t for t in re.split(r"\W+", (text_b or "").lower()) if t])
        if not sa or not sb:
            return 0.0
        inter = sa.intersection(sb)
        union = sa.union(sb)
        return len(inter) / len(union)

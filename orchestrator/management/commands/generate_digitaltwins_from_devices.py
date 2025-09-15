"""Management command: generate DigitalTwin instances from existing facade Devices.

Behavior:
- Scans Devices for a given `system` context (optional) and builds a hierarchy
  of DigitalTwinInstance objects mapping device names / metadata into model
  elements.
- Heuristics:
  - Use Device.type.name to find a DTDLModel with same/contains name.
  - Use labels/metadata tokens to infer parent instances (e.g. house 1, room 2).
  - Create instance names from device.name and map properties by name.
- Arguments:
  --system-id: optional SystemContext id to limit which DTDLModel/system to use.
  --dry-run: print what would be created without persisting.

This is intentionally conservative: it will not overwrite existing instances but
will create missing ones and link properties where exact matches are found.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from facade.models import Device, Property
from orchestrator.models import SystemContext, DTDLModel, DigitalTwinInstance, ModelElement, DigitalTwinInstanceProperty, DigitalTwinInstanceRelationship, ModelRelationship
from orchestrator.utils import normalize_name
import re
import os
from django.conf import settings


def build_model_graph(system: SystemContext | None):
    """Return structures to navigate model relationships: (model_by_id, adjacency, incoming_count)
    model_by_id: {dtdl_id: DTDLModel}
    adjacency: {source_dtdl_id: [ (target_dtdl_id, ModelRelationship), ... ] }
    incoming_count: {dtdl_id: int}
    """
    models = DTDLModel.objects.filter(system=system) if system else DTDLModel.objects.all()
    model_by_id = {m.dtdl_id: m for m in models}
    adjacency = {}
    incoming_count = {m.dtdl_id: 0 for m in models}
    for rel in ModelRelationship.objects.filter(dtdl_model__in=models):
        src = rel.dtdl_model.dtdl_id
        tgt = rel.target
        adjacency.setdefault(src, []).append((tgt, rel))
        # increment incoming for target if the target model exists in our set
        if any(tgt in mid for mid in model_by_id.keys()):
            # if exact match not found, use substring match
            for mid in model_by_id.keys():
                if tgt in mid:
                    incoming_count[mid] = incoming_count.get(mid, 0) + 1
    return model_by_id, adjacency, incoming_count


def find_root_model(system: SystemContext | None):
    """Find a root model (no incoming relationships) preferring ones with 'house' in name."""
    model_by_id, adjacency, incoming = build_model_graph(system)
    roots = [model_by_id[mid] for mid, cnt in incoming.items() if cnt == 0]
    if not roots:
        return DTDLModel.objects.filter(system=system).first() if system else DTDLModel.objects.first()
    # prefer models that look like 'House' or 'Condominium'
    for r in roots:
        if 'house' in normalize_name(r.name) or 'condo' in normalize_name(r.name) or 'condominium' in normalize_name(r.name):
            return r
    return roots[0]


def extract_root_key(device: Device):
    """Extract a grouping key for a device, typically the house/condo/apartment number or unique top-level token.
    Returns a string key or device.name if nothing found.
    """
    name = device.name or ''
    metadata = device.metadata or ''
    text = f"{name} {metadata}".lower()
    # patterns like 'house 3', 'home-2', 'apt 12', 'condo 4', 'condominio 2'
    m = re.search(r"\b(house|home|apt|apartment|condo|condominium|unit)[\s_-]?(\d+)\b", text)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    # fallback: if the name contains a leading number or trailing number, use that
    m2 = re.search(r"(\d+)", name)
    if m2:
        return m2.group(1)
    # final fallback: use normalized prefix token
    tokens = [t for t in re.split(r"\W+", name) if t]
    return tokens[0] if tokens else name


def model_path_bfs(start_dtdl_id: str, target_dtdl_id: str, adjacency: dict, model_by_id: dict):
    """Find a model dtdl_id path from start to target using BFS. Returns list of dtdl_ids or empty if none."""
    from collections import deque
    q = deque()
    q.append((start_dtdl_id, [start_dtdl_id]))
    visited = set([start_dtdl_id])
    while q:
        cur, path = q.popleft()
        if cur == target_dtdl_id or (target_dtdl_id in cur):
            return path
        for (tgt, rel) in adjacency.get(cur, []):
            # resolve tgt into an actual key in model_by_id (substring match)
            for mid in model_by_id.keys():
                if tgt in mid and mid not in visited:
                    visited.add(mid)
                    q.append((mid, path + [mid]))
    return []


def compute_similarity(text_a: str, text_b: str):
    """Compute semantic similarity score between two texts. Try sentence-transformer, fallback to lexical Jaccard."""
    try:
        from sentence_transformers import SentenceTransformer, util
        model = SentenceTransformer(os.environ.get('ST_MODEL_NAME', 'all-MiniLM-L6-v2'))
        emb_a = model.encode(text_a, convert_to_tensor=True)
        emb_b = model.encode(text_b, convert_to_tensor=True)
        return float(util.cos_sim(emb_a, emb_b)[0][0])
    except Exception:
        # lexical Jaccard as fallback
        sa = set([t for t in re.split(r"\W+", text_a.lower()) if t])
        sb = set([t for t in re.split(r"\W+", text_b.lower()) if t])
        if not sa or not sb:
            return 0.0
        inter = sa.intersection(sb)
        union = sa.union(sb)
        return len(inter) / len(union)



def find_model_for_device(device: Device, system: SystemContext | None):
    """Heurística simples para escolher DTDLModel correspondente ao device type/name."""
    candidates = DTDLModel.objects.filter(system=system) if system else DTDLModel.objects.all()
    dev_type = normalize_name(device.type.name) if getattr(device, "type", None) and device.type and device.type.name else ''
    dev_name = normalize_name(device.name or '')
    # 1) match model name contains device type token
    for m in candidates:
        if dev_type and dev_type in normalize_name(m.name):
            return m
    # 2) match model name contains parts of device name
    dev_tokens = [t for t in re.split(r"\W+", dev_name) if t]
    for m in candidates:
        mn = normalize_name(m.name)
        if any(tok in mn for tok in dev_tokens):
            return m
    # 3) fallback: return first model in system
    return candidates.first()


def find_model_for_token(token: str, system: SystemContext | None):
    """Tenta mapear um token (como 'house', 'garden', 'pump') para um DTDLModel."""
    tok = normalize_name(re.sub(r"\d+", "", token)).strip()  # remove números para casar somente o tipo
    if not tok:
        return None
    candidates = DTDLModel.objects.filter(system=system) if system else DTDLModel.objects.all()
    # prioridade: nome contendo token (normalizado)
    for m in candidates:
        if tok in normalize_name(m.name):
            return m
    # fallback: contém token como palavra
    for m in candidates:
        if any(tok == normalize_name(part) for part in re.split(r"\W+", m.name) if part):
            return m
    return None


def find_or_create_hierarchy(root_tokens: list[str], system: SystemContext | None, dry_run=False):
    """Cria instâncias de hierarchy tokens ascendentes e retorna instância final.
    Ex: ['house 1', 'room 2', 'light 3'] cria/retorna instância para 'light 3'.
    """
    parent = None
    prev_parent = None
    created_instances = []
    for idx, token in enumerate(root_tokens):
        name = token
        # tenta encontrar instância existente com mesmo nome (normalizado)
        if system:
            existing = DigitalTwinInstance.objects.filter(name__iexact=name, model__system=system).first()
        else:
            existing = DigitalTwinInstance.objects.filter(name__iexact=name).first()
        if existing:
            parent = existing
            prev_parent = parent
            continue

        # seleciona modelo baseado no token (prioriza modelos do system)
        model = find_model_for_token(token, system)
        if not model:
            # último recurso: tenta achar model pelo device completo (se disponível)
            model = DTDLModel.objects.filter(system=system).first() if system else DTDLModel.objects.first()

        if dry_run:
            created_instances.append((name, model.name if model else None))
            parent = None
        else:
            # cria a instância com model (pode ser None — mas preferimos ter um model)
            if model is None:
                # tenta fallback geral (evita criar instância sem modelo que pode quebrar saves posteriores)
                model = DTDLModel.objects.filter(system=system).first() if system else DTDLModel.objects.first()
            # sanitize name: avoid creating instances with generic suffixes like
            # 'condominium' or with the exact model name (these cause confusing entries)
            try:
                model_norm = normalize_name(model.name) if model and model.name else ''
            except Exception:
                model_norm = ''
            name_norm = normalize_name(name) if name else ''
            if model_norm and (name_norm == model_norm or 'condominium' in name_norm or 'condominio' in name_norm):
                # leave name empty to let DigitalTwinInstance.save() generate a proper name
                inst = DigitalTwinInstance.objects.create(model=model)
            else:
                inst = DigitalTwinInstance.objects.create(model=model, name=name)
            created_instances.append((name, model.name if model else None))
            parent = inst

            # cria relação com parent anterior: tenta encontrar ModelRelationship entre os modelos
            if idx > 0 and prev_parent:
                try:
                    rel = None
                    if prev_parent.model and model:
                        # procura relacionamento cujo source = prev_parent.model e target corresponde ao model
                        rel = prev_parent.model.model_relationships.filter(target__icontains=(model.dtdl_id or normalize_name(model.name))).first()
                        if not rel:
                            rel = prev_parent.model.model_relationships.filter(name__icontains=normalize_name(model.name.split()[0])).first()
                    if rel:
                        DigitalTwinInstanceRelationship.objects.update_or_create(
                            source_instance=prev_parent,
                            target_instance=parent,
                            defaults={'relationship': rel}
                        )
                    else:
                        # Não criar DigitalTwinInstanceRelationship vazio — apenas logar
                        print(f"[WARN] No ModelRelationship found between {prev_parent.model.name if prev_parent.model else 'N/A'} -> {model.name if model else 'N/A'}; skipping instance relationship creation.")
                except Exception as e:
                    print(f"[ERROR] Failed creating relationship between instances {prev_parent} -> {parent}: {e}")
        prev_parent = parent
    return parent, created_instances


def create_full_topology(system: SystemContext | None, dry_run=False):
    """Create one DigitalTwinInstance per DTDLModel and wire ModelRelationships as instance relationships.
    Returns a mapping {dtdl_model.id: instance} (or names in dry-run).
    This is conservative: instances are created with empty names to let the save() generate unique names.
    """
    mapping = {}
    models = DTDLModel.objects.filter(system=system) if system else DTDLModel.objects.all()
    created = []
    # Create instances for all models
    for m in models:
        if dry_run:
            created.append((m.name, 'DRY'))
            mapping[m.id] = None
            continue
        inst = DigitalTwinInstance.objects.create(model=m)
        mapping[m.id] = inst
    # Create relationships between instances according to ModelRelationship
    if not dry_run:
        for rel in ModelRelationship.objects.filter(dtdl_model__in=models):
            source_model = rel.dtdl_model
            # try to resolve target model by dtdl_id or name
            target_model = DTDLModel.objects.filter(dtdl_id__icontains=rel.target, system=system).first() if system else DTDLModel.objects.filter(dtdl_id__icontains=rel.target).first()
            if not target_model:
                # fallback by name token
                target_model = DTDLModel.objects.filter(name__icontains=rel.target.split()[:1]).first()
            if source_model and target_model and mapping.get(source_model.id) and mapping.get(target_model.id):
                try:
                    DigitalTwinInstanceRelationship.objects.update_or_create(
                        source_instance=mapping[source_model.id],
                        target_instance=mapping[target_model.id],
                        defaults={'relationship': rel}
                    )
                except Exception as e:
                    print(f"[WARN] failed to create instance relationship for model rel {rel}: {e}")
    return mapping, created


class Command(BaseCommand):
    help = 'Generate DigitalTwin hierarchy from existing Devices'

    def add_arguments(self, parser):
        parser.add_argument('--system-id', type=int, help='SystemContext id to limit models')
        parser.add_argument('--dry-run', action='store_true', help='Do not persist changes')

    def handle(self, *args, **options):
        system = None
        if options.get('system_id'):
            system = SystemContext.objects.filter(pk=options['system_id']).first()
            if not system:
                self.stdout.write(self.style.ERROR(f"SystemContext {options['system_id']} not found"))
                return
        dry_run = options.get('dry_run', False)
        devices = Device.objects.all()
        created = 0
        skipped = 0
        # Group devices by inferred root key (e.g. house 1)
        groups = {}
        for d in devices:
            key = extract_root_key(d)
            groups.setdefault(key, []).append(d)

        # Build model graph to discover topology
        model_by_id, adjacency, incoming = build_model_graph(system)
        root_model = find_root_model(system)
        self.stdout.write(self.style.NOTICE(f"Root model chosen: {root_model.name if root_model else 'N/A'}"))
        # If there are no DigitalTwinInstance entries, create a full topology from the models
        any_instances = DigitalTwinInstance.objects.exists()
        instance_mapping = {}
        if not any_instances:
            self.stdout.write(self.style.NOTICE("No existing DigitalTwinInstance found — generating full topology from DTDL models."))
            mapping, created_list = create_full_topology(system, dry_run=dry_run)
            # mapping keys are model ids -> DigitalTwinInstance (or None in dry-run)
            instance_mapping = {}
            for model_pk, inst in mapping.items():
                m = DTDLModel.objects.filter(pk=model_pk).first()
                if m:
                    instance_mapping[m] = inst
            if dry_run:
                self.stdout.write(self.style.NOTICE(f"[DRY] Would create topology: {created_list}"))
        for d in devices:
            # heurística para extrair tokens hierárquicos de nome/metadata
            tokens = []
            # tenta extrair house/room patterns de metadata
            if d.metadata:
                tokens.extend([t for t in re.split(r"\W+", d.metadata) if t])
            # quebra name em palavras
            tokens.extend([t for t in re.split(r"\W+", d.name) if t])
            # simplifica tokens combinando adjacentes como 'house 1'
            combined = []
            i = 0
            while i < len(tokens):
                if i + 1 < len(tokens) and tokens[i].lower() in ('house', 'room', 'apartment') and tokens[i+1].isdigit():
                    combined.append(f"{tokens[i]} {tokens[i+1]}")
                    i += 2
                else:
                    combined.append(tokens[i])
                    i += 1
            # por fim, tenta achar modelo para o próprio dispositivo
            for group_key, dlist in groups.items():
                # For each group (e.g. house 1), determine the minimal set of instances to create
                self.stdout.write(self.style.NOTICE(f"Processing group {group_key} ({len(dlist)} devices)"))
                # find distinct device models in this group
                for d in dlist:
                    # For each device, decide which model it maps to
                    device_model = find_model_for_device(d, system)
                    # try to find path from root_model to device_model
                    path = []
                    if root_model and device_model:
                        path = model_path_bfs(root_model.dtdl_id, device_model.dtdl_id, adjacency, model_by_id)
                    # If path empty and device_model present, fallback to simple path [device_model]
                    if not path and device_model:
                        path = [device_model.dtdl_id]
                    # walk the path creating/finding instances for each model in order
                    parent_instance = None
                    created_list = []
                    for mid in path:
                        mdl = model_by_id.get(mid)
                        if not mdl:
                            continue
                        # try to find existing instance for this model and group_key
                        qname = None
                        # prefer instances whose hierarchy contains the group_key token
                        existing = DigitalTwinInstance.objects.filter(model=mdl)
                        found = None
                        for ex in existing:
                            if group_key and group_key.lower() in " ".join(ex.get_hierarchy()).lower():
                                found = ex
                                break
                        if found:
                            inst = found
                        else:
                            # create instance, give name to hint the group
                            if dry_run:
                                created_list.append((mdl.name, f"{group_key}"))
                                inst = None
                            else:
                                inst = DigitalTwinInstance.objects.create(model=mdl, name=f"{mdl.name} {group_key}")
                                created_list.append((mdl.name, inst.name))
                        # create relationship with parent
                        if parent_instance and inst:
                            # attempt to find ModelRelationship
                            rel = ModelRelationship.objects.filter(dtdl_model=parent_instance.model, target__icontains=mdl.dtdl_id).first()
                            if rel:
                                DigitalTwinInstanceRelationship.objects.update_or_create(
                                    source_instance=parent_instance,
                                    target_instance=inst,
                                    defaults={'relationship': rel}
                                )
                        parent_instance = inst

                    # After creating the chain, associate device properties to the last instance (device level)
                    instance = parent_instance
                    if dry_run:
                        self.stdout.write(self.style.NOTICE(f"[DRY] Device {d.name} -> would create/attach to instance {created_list}"))
                        skipped += 1
                        continue
                    if instance is None:
                        # fallback: try hierarchy approach
                        instance, created_list = find_or_create_hierarchy([d.name], system, dry_run=dry_run)
                    if instance is None:
                        self.stdout.write(self.style.WARNING(f"Could not determine instance for device {d.name}. Skipping."))
                        skipped += 1
                        continue
                    # conservative property binding: for each property, match to ModelElement by normalized name or by semantic similarity
                    with transaction.atomic():
                        for prop in Property.objects.filter(device=d):
                            if not prop.name:
                                continue
                            norm_prop = normalize_name(prop.name)
                            elems_qs = ModelElement.objects.filter(dtdl_model=instance.model) if instance and instance.model else ModelElement.objects.all()
                            el = None
                            # exact normalized name
                            for e in elems_qs:
                                if normalize_name(e.name) == norm_prop:
                                    el = e
                                    break
                            # semantic fallback
                            if not el:
                                # compute similarity between prop.name and element names and pick best above threshold
                                best = None
                                best_score = 0.0
                                for e in elems_qs:
                                    score = compute_similarity(prop.name, e.name)
                                    if score > best_score:
                                        best_score = score
                                        best = e
                                if best and best_score >= float(os.environ.get('ASSOC_SIM_THRESHOLD', 0.7)):
                                    el = best
                                else:
                                    print(f"[WARN] No ModelElement found for property '{prop.name}' in model '{instance.model.name if instance and instance.model else 'N/A'}' - skipping binding.")
                                    continue
                            dtip, created_flag = DigitalTwinInstanceProperty.objects.get_or_create(dtinstance=instance, property=el)
                            dtip.device_property = prop
                            dtip.save(update_fields=['device_property'])
                    created += 1
                    self.stdout.write(self.style.SUCCESS(f"Created/updated DT instance for device {d.name}: {instance}"))
            # end groups processing

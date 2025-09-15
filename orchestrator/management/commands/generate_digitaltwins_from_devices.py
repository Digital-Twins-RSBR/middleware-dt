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


def find_model_for_device(device: Device, system: SystemContext | None):
    """Heurística simples para escolher DTDLModel correspondente ao device type/name."""
    candidates = DTDLModel.objects.filter(system=system) if system else DTDLModel.objects.all()
    dev_type = (device.type.name if device.type else '').lower() if device else ''
    dev_name = (device.name or '').lower()
    # 1) match model name contains device type
    for m in candidates:
        if dev_type and dev_type in m.name.lower():
            return m
    # 2) match model name contains parts of device name
    for m in candidates:
        if any(tok in m.name.lower() for tok in re.split(r"\W+", dev_name) if tok):
            return m
    # 3) fallback: return first model in system
    return candidates.first()


def find_or_create_hierarchy(root_tokens: list[str], system: SystemContext | None, dry_run=False):
    """Cria instâncias de hierarchy tokens ascendentes e retorna instância final.
    Ex: ['house 1', 'room 2', 'light 3'] cria/retorna instância para 'light 3'.
    """
    parent = None
    prev_parent = None
    created_instances = []
    for idx, token in enumerate(root_tokens):
        name = token
        # tenta encontrar instância existente com mesmo nome
        # prefer match within same system if possible
        if system:
            existing = DigitalTwinInstance.objects.filter(name=name, model__system=system).first()
        else:
            existing = DigitalTwinInstance.objects.filter(name=name).first()
        if existing:
            parent = existing
            continue
        # tenta associar a um modelo baseado no token
        model = DTDLModel.objects.filter(name__icontains=token.split()[0], system=system).first() if system else DTDLModel.objects.filter(name__icontains=token.split()[0]).first()
        if not model:
            # se não achar, pega qualquer modelo do sistema
            model = DTDLModel.objects.filter(system=system).first() if system else DTDLModel.objects.first()
        if dry_run:
            created_instances.append((name, model.name if model else None))
            parent = None
        else:
            inst = DigitalTwinInstance.objects.create(model=model, name=name)
            created_instances.append((name, model.name if model else None))
            parent = inst
            # cria relação com parent anterior: tenta encontrar ModelRelationship entre os modelos
            if idx > 0 and prev_parent:
                try:
                    # busca relacionamento definido no modelo do parent cujo target casa com o dtdl_id do model
                    rel = prev_parent.model.model_relationships.filter(target__icontains=(model.dtdl_id or model.name)).first()
                    if not rel:
                        # fallback: buscar por nome
                        rel = prev_parent.model.model_relationships.filter(name__icontains=model.name.split()[0]).first()
                    if rel:
                        DigitalTwinInstanceRelationship.objects.update_or_create(source_instance=prev_parent, target_instance=parent, relationship=rel)
                    else:
                        # Não criar DigitalTwinInstanceRelationship vazio — apenas logar
                        print(f"[WARN] No ModelRelationship found between {prev_parent.model.name} -> {model.name}; skipping instance relationship creation.")
                except Exception as e:
                    print(f"[ERROR] Failed creating relationship between instances {prev_parent} -> {parent}: {e}")
                    # continua sem criar a relationship
        prev_parent = parent
    return parent, created_instances


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
            model = find_model_for_device(d, system)

            # cria/acha instâncias hierárquicas
            instance, created_list = find_or_create_hierarchy(combined + [d.name], system, dry_run=dry_run)
            if dry_run:
                self.stdout.write(self.style.NOTICE(f"[DRY] Device {d.name} -> would create instance {created_list}"))
                skipped += 1
                continue
            if instance is None:
                self.stdout.write(self.style.WARNING(f"Could not determine instance for device {d.name}. Skipping."))
                skipped += 1
                continue
            # Associa propriedades locais (por nome exato)
            for prop in Property.objects.filter(device=d):
                # tenta encontrar property element model
                el = ModelElement.objects.filter(name__iexact=prop.name).first()
                if el:
                    dtip, created_flag = DigitalTwinInstanceProperty.objects.update_or_create(dtinstance=instance, property=el)
                    if prop and dtip and prop.name:
                        dtip.device_property = prop
                        dtip.save(update_fields=['device_property'])
            created += 1
            self.stdout.write(self.style.SUCCESS(f"Created/updated DT instance for device {d.name}: {instance}"))

        self.stdout.write(self.style.SUCCESS(f"Done. created: {created} skipped: {skipped}"))

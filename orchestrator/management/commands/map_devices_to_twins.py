"""
Management command: Map Device Properties to Digital Twin Instance Properties

Comportamento:
1. Encontra todos os Devices cadastrados no sistema
2. Para cada Device, cria ou encontra um Digital Twin Instance
3. Para cada Device Property, cria uma Digital Twin Instance Property associada

Resultado:
- Todas as propriedades de devices estarão disponíveis para update_causal_property.py
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from facade.models import Device, Property
from orchestrator.models import (
    DigitalTwinInstance, DigitalTwinInstanceProperty,
    DTDLModel, ModelElement, SystemContext
)
from orchestrator.utils import normalize_name
import re


class Command(BaseCommand):
    help = 'Map all Device Properties to Digital Twin Instance Properties for RPC propagation'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show what would be created without persisting')
        parser.add_argument('--system-id', type=int, help='Specific system context to process')

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        system_id = options.get('system_id', None)

        print("[MAP] 🔍 Scanning devices and digital twin models...")

        # Get or create default system
        if system_id:
            try:
                system = SystemContext.objects.get(id=system_id)
            except SystemContext.DoesNotExist:
                self.stderr.write(f"System {system_id} not found")
                return
        else:
            system, _ = SystemContext.objects.get_or_create(
                name='Default', defaults={'description': 'Default system context'}
            )

        # Get all devices
        devices = Device.objects.all()
        self.stdout.write(f"[MAP] Found {len(devices)} devices")

        # Get available models
        models = DTDLModel.objects.filter(system=system)
        self.stdout.write(f"[MAP] Found {len(models)} DTDL models in system '{system.name}'")

        if not models:
            self.stderr.write(f"❌ No DTDL models found in system. Please create models first.")
            return

        created_twins = 0
        created_properties = 0
        associated_properties = 0

        with transaction.atomic():
            for device in devices:
                # Find best model for this device
                model = self._find_best_model(device, models)
                if not model:
                    self.stdout.write(f"⚠️  No model found for device '{device.name}'")
                    continue

                # Create or get Digital Twin Instance
                dt_instance, created = DigitalTwinInstance.objects.get_or_create(
                    name=f"{device.name} Instance",
                    model=model,
                    defaults={'active': True}
                )
                if created:
                    created_twins += 1
                    self.stdout.write(f"✅ Created DT Instance: {dt_instance.name}")
                else:
                    self.stdout.write(f"ℹ️  Found existing DT Instance: {dt_instance.name}")

                # Get device properties
                device_properties = device.property_set.all()
                
                # Get model elements (properties) with causal tag
                model_elements = ModelElement.objects.filter(
                    dtdl_model=model,
                    supplement_types__contains=["dtmi:dtdl:extension:causal:v1:Causal"]
                )

                if not model_elements:
                    # Fallback: get ANY property from model
                    model_elements = ModelElement.objects.filter(dtdl_model=model, element_type='Property')

                self.stdout.write(f"  📝 Device has {len(device_properties)} properties, model has {len(model_elements)} model elements")

                # Associate device properties to DT properties
                for device_prop in device_properties:
                    # Find matching model element
                    model_element = self._find_best_model_element(device_prop, model_elements)
                    
                    if not model_element:
                        self.stdout.write(f"  ⚠️  No matching model element for property '{device_prop.name}'")
                        continue

                    # Create or get Digital Twin Instance Property
                    dt_prop, created = DigitalTwinInstanceProperty.objects.get_or_create(
                        dtinstance=dt_instance,
                        property=model_element,
                        defaults={
                            'device_property': device_prop,
                            'value': device_prop.value or ''
                        }
                    )
                    
                    if created:
                        created_properties += 1
                        self.stdout.write(f"    ✅ Created DT Property: {model_element.name}")
                    else:
                        # Update device_property if not set
                        if not dt_prop.device_property:
                            # Use queryset update to avoid triggering model save side-effects
                            # (propagation/RPC) during bootstrap mapping.
                            DigitalTwinInstanceProperty.objects.filter(pk=dt_prop.pk).update(
                                device_property=device_prop
                            )
                            associated_properties += 1
                            self.stdout.write(f"    🔗 Associated device property to existing DT Property: {model_element.name}")
                        else:
                            self.stdout.write(f"    ℹ️  DT Property already exists: {model_element.name}")

        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] Changes not persisted"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n[MAP] ✅ Mapping complete!"))
            self.stdout.write(f"  Created {created_twins} Digital Twin Instances")
            self.stdout.write(f"  Created {created_properties} Digital Twin Instance Properties")
            self.stdout.write(f"  Associated {associated_properties} device properties")

    def _find_best_model(self, device, models):
        """Find the best DTDL model for a device using heuristics"""
        device_name = (device.name or '').lower()
        # Compatibility: some deployments use device.type (FK DeviceType)
        # while others may expose device.device_type
        dev_type_obj = getattr(device, 'type', None) or getattr(device, 'device_type', None)
        device_type = (getattr(dev_type_obj, 'name', '') or '').lower()

        # Exact match on device type
        for model in models:
            if device_type and device_type in model.name.lower():
                return model

        # Substring match on device name
        for model in models:
            if model.name.lower() in device_name or device_name in model.name.lower():
                return model

        # Generic match: prefer broader models like "House", "Room", "Device"
        for model in models:
            model_name = model.name.lower()
            if any(x in model_name for x in ['device', 'generic', 'base']):
                return model

        # Last resort: return first model
        return models.first()

    def _find_best_model_element(self, device_prop, model_elements):
        """Find the best ModelElement for a device property"""
        prop_name = (device_prop.name or '').lower()

        # Exact match
        for elem in model_elements:
            if elem.name.lower() == prop_name:
                return elem

        # Substring match
        for elem in model_elements:
            if prop_name in elem.name.lower() or elem.name.lower() in prop_name:
                return elem

        # Match by common patterns
        common_patterns = {
            'status': ['status', 'on', 'active'],
            'temperature': ['temp', 'temperature'],
            'humidity': ['humid', 'humidity'],
        }

        for pattern, keywords in common_patterns.items():
            if any(k in prop_name for k in keywords):
                for elem in model_elements:
                    if any(k in elem.name.lower() for k in keywords):
                        return elem

        # First available element as fallback
        return model_elements.first()

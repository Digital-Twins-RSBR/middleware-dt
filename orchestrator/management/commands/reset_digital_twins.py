"""
Django Management Command: Reset and recreate Digital Twins
Usage: python manage.py reset_digital_twins [--dry-run] [--system-id=N]
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from facade.models import Device, Property, DeviceType
from orchestrator.models import (
    DigitalTwinInstance, DigitalTwinInstanceProperty, DigitalTwinInstanceRelationship,
    DTDLModel, ModelElement, SystemContext
)
from orchestrator.utils import normalize_name
import re
import json
from pathlib import Path


class Command(BaseCommand):
    help = 'Reset all Digital Twins and recreate them automatically from devices with available DTDL modeling'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )
        parser.add_argument(
            '--system-id',
            type=int,
            help='Limit to specific SystemContext ID'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force deletion without confirmation'
        )

    def handle(self, *args, **options):
        self.dry_run = options.get('dry_run', False)
        self.force = options.get('force', False)
        
        system_id = options.get('system_id')
        self.system = None
        if system_id:
            try:
                self.system = SystemContext.objects.get(pk=system_id)
                self.stdout.write(f"🎯 Limiting to SystemContext: {self.system.name}")
            except SystemContext.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"SystemContext with ID {system_id} not found")
                )
                return
        
        # First, ensure devices have properties based on their types
        self.create_device_properties()

        self.stdout.write(self.style.SUCCESS("🚀 DIGITAL TWIN RESET & AUTO-CREATION"))
        self.stdout.write("=" * 60)

        try:
            # Step 1: Confirmation and deletion
            self.delete_existing_digital_twins()
            
            # Step 2: Create hierarchical elements (Houses, Rooms, Pools, Gardens)
            self.create_hierarchical_elements()
            
            # Step 3: Analysis
            devices_with_modeling, devices_without = self.analyze_devices()
            
            if not devices_with_modeling:
                self.stdout.write(
                    self.style.ERROR("❌ No devices with matching DTDL models found!")
                )
                return
            
            # Step 4: Creation of device Digital Twins
            created_count = self.create_digital_twins(devices_with_modeling)
            
            # Step 5: Create relationships (LAST STEP - after all Digital Twins exist)
            relationships_created = self.create_digital_twin_relationships()
            
            # Step 6: Summary
            self.print_summary(devices_with_modeling, devices_without, created_count, relationships_created)
            
            self.stdout.write("=" * 60)
            self.stdout.write(
                self.style.SUCCESS("✅ Digital Twin reset completed successfully!")
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"❌ Command failed: {e}")
            )
            import traceback
            traceback.print_exc()

    def create_device_properties(self):
        """
        Create/update properties using shared attributes as source of truth.
        Fallback mappings are applied only to fill missing values.
        """
        mappings = self._load_device_type_mappings()

        devices = Device.objects.all()
        properties_created = 0
        properties_updated = 0
        devices_updated = 0
        
        self.stdout.write("🔧 Syncing properties from shared attributes with fallback mapping...")
        
        for device in devices:
            if not device.type:
                continue

            device_changed = False
            device_type_name = device.type.name

            # 1) Source of truth: shared attributes from ThingsBoard
            try:
                if not self.dry_run:
                    before_count = Property.objects.filter(device=device).count()
                    device.sync_properties_from_thingsboard()
                    after_count = Property.objects.filter(device=device).count()
                    if after_count > before_count:
                        properties_created += (after_count - before_count)
                        device_changed = True
            except Exception as exc:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠️ Failed shared-attribute sync for '{device.name}': {exc}"
                    )
                )

            # 2) Fallback: type mapping from JSON, only to fill missing fields
            property_templates = self._get_type_mapping(mappings, device_type_name)
            device_properties_created = 0
            for prop_template in property_templates:
                if self.dry_run:
                    continue

                prop, created = Property.objects.get_or_create(
                    device=device,
                    name=prop_template['name'],
                    defaults={
                        'type': prop_template.get('type', 'Boolean'),
                        'value': 'false' if prop_template.get('type', 'Boolean') == 'Boolean' else '0',
                        'rpc_read_method': prop_template.get('rpc_read_method', '') or '',
                        'rpc_write_method': prop_template.get('rpc_write_method', '') or '',
                    }
                )

                if created:
                    properties_created += 1
                    device_properties_created += 1
                    device_changed = True
                    if not self.dry_run:
                        self.stdout.write(f"  ➕ Created property '{prop.name}' for device '{device.name}'")
                    continue

                changed_fields = []
                if not prop.rpc_read_method and prop_template.get('rpc_read_method'):
                    prop.rpc_read_method = prop_template['rpc_read_method']
                    changed_fields.append('rpc_read_method')
                if not prop.rpc_write_method and prop_template.get('rpc_write_method'):
                    prop.rpc_write_method = prop_template['rpc_write_method']
                    changed_fields.append('rpc_write_method')

                if changed_fields:
                    prop.save(update_fields=changed_fields)
                    properties_updated += 1
                    device_changed = True

            # Cleanup known legacy mapping artifacts that conflict with current simulator contract.
            if not self.dry_run and self._normalize_mapping_key(device_type_name) == 'lightbulb':
                removed_count, _ = Property.objects.filter(
                    device=device,
                    name='brightness',
                    rpc_read_method='getBrightness',
                    rpc_write_method='setBrightness',
                ).delete()
                if removed_count:
                    device_changed = True
                    self.stdout.write(
                        f"  🧹 Removed legacy property 'brightness' from device '{device.name}'"
                    )
            
            if device_properties_created > 0 or device_changed:
                devices_updated += 1
        
        if not self.dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Created {properties_created} properties, updated {properties_updated} properties across {devices_updated} devices"
                )
            )
        else:
            self.stdout.write(
                "[DRY RUN] Would sync properties from shared attributes and apply fallback mappings"
            )

    def _load_device_type_mappings(self):
        mappings_path = Path(__file__).resolve().parents[2] / 'config' / 'device_type_mappings.json'
        try:
            with mappings_path.open('r', encoding='utf-8') as mapping_file:
                return json.load(mapping_file)
        except Exception as exc:
            self.stdout.write(
                self.style.WARNING(f"⚠️ Failed to load {mappings_path}: {exc}")
            )
            return {}

    @staticmethod
    def _normalize_mapping_key(value):
        if value is None:
            return ''
        return str(value).strip().lower()

    def _get_type_mapping(self, mappings, dtype_name):
        if not dtype_name or not isinstance(mappings, dict):
            return []

        if dtype_name in mappings:
            return mappings[dtype_name]

        normalized_target = self._normalize_mapping_key(dtype_name)
        for key, value in mappings.items():
            if self._normalize_mapping_key(key) == normalized_target:
                return value

        return []

    def create_hierarchical_elements(self):
        """Create hierarchical Digital Twin elements (Houses, Rooms, Pools, Gardens) based on device structure"""
        self.stdout.write("🏗️ Creating hierarchical elements...")
        
        devices = Device.objects.all()
        hierarchical_elements = {}  # {element_type: {element_name: model}}
        
        # Analyze device names to extract hierarchical structure
        for device in devices:
            parts = device.name.split(' - ')
            if len(parts) >= 3:  # Ex: House 1 - Living Room - Light
                house_name = parts[0]  # House 1
                location_name = parts[1]  # Living Room, Pool, Garden
                
                # Add house
                hierarchical_elements.setdefault('House', {})[house_name] = None
                
                # Determine location type and add it
                location_type = self.determine_location_type(location_name)
                location_full_name = f"{house_name} - {location_name}"
                hierarchical_elements.setdefault(location_type, {})[location_full_name] = None
        
        # Map hierarchical elements to DTDL models
        model_mapping = {
            'House': 'dtmi:housegen:House;1',
            'Room': 'dtmi:housegen:Room;1', 
            'Pool': 'dtmi:housegen:Pool;1',
            'Garden': 'dtmi:housegen:Garden;1'
        }
        
        elements_created = 0
        
        for element_type, elements in hierarchical_elements.items():
            model_dtdl_id = model_mapping.get(element_type)
            if not model_dtdl_id:
                continue
                
            try:
                model = DTDLModel.objects.get(dtdl_id=model_dtdl_id)
            except DTDLModel.DoesNotExist:
                self.stdout.write(f"  ⚠️ Model {model_dtdl_id} not found for {element_type}")
                continue
            
            for element_name in elements:
                # Check if element already exists
                existing = DigitalTwinInstance.objects.filter(
                    name=element_name,
                    model=model
                ).first()
                
                if existing:
                    self.stdout.write(f"  ↺ {element_type} '{element_name}' already exists")
                    continue
                
                if not self.dry_run:
                    # Create the hierarchical element
                    dt_instance = DigitalTwinInstance.objects.create(
                        name=element_name,
                        model=model
                    )
                    
                    # Create properties for the element (based on model elements)
                    model_elements = ModelElement.objects.filter(dtdl_model=model)
                    for element in model_elements:
                        dt_prop, created = DigitalTwinInstanceProperty.objects.get_or_create(
                            dtinstance=dt_instance,
                            property=element,
                            defaults={'value': ''}  # Default empty value
                        )
                    
                    self.stdout.write(f"  ✅ Created {element_type}: '{element_name}'")
                    elements_created += 1
                else:
                    self.stdout.write(f"  [DRY RUN] Would create {element_type}: '{element_name}'")
                    elements_created += 1
        
        self.stdout.write(
            self.style.SUCCESS(f"🏗️ Created {elements_created} hierarchical elements")
        )
        
        return elements_created

    def determine_location_type(self, location_name):
        """Determine the type of location based on its name"""
        location_lower = location_name.lower()
        
        if 'pool' in location_lower or 'piscina' in location_lower:
            return 'Pool'
        elif 'garden' in location_lower or 'jardim' in location_lower:
            return 'Garden'
        else:
            # Default to Room for other locations (Living Room, Bedroom, etc.)
            return 'Room'

    def delete_existing_digital_twins(self):
        """Delete all existing Digital Twins"""
        dt_count = DigitalTwinInstance.objects.count()
        prop_count = DigitalTwinInstanceProperty.objects.count()
        rel_count = DigitalTwinInstanceRelationship.objects.count()

        if dt_count == 0:
            self.stdout.write("ℹ️ No existing Digital Twins found")
            return

        self.stdout.write(f"📋 Found {dt_count} Digital Twins, {prop_count} properties, {rel_count} relationships")

        if not self.force and not self.dry_run:
            confirm = input("⚠️ This will DELETE ALL Digital Twins. Continue? (yes/no): ")
            if confirm.lower() != 'yes':
                self.stdout.write("Operation cancelled")
                exit(1)

        if self.dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] Would delete all Digital Twins"))
            return

        with transaction.atomic():
            DigitalTwinInstanceRelationship.objects.all().delete()
            DigitalTwinInstanceProperty.objects.all().delete()
            DigitalTwinInstance.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(f"🗑️ Deleted {dt_count} Digital Twins and all related data")
        )

    def analyze_devices(self):
        """Analyze devices and identify which have available modeling"""
        self.stdout.write("📊 Analyzing devices and available DTDL models...")
        
        devices = Device.objects.all()
        models = DTDLModel.objects.filter(system=self.system) if self.system else DTDLModel.objects.all()
        
        self.stdout.write(f"📱 Total devices: {devices.count()}")
        self.stdout.write(f"🏗️ Available DTDL models: {models.count()}")

        devices_with_modeling = []
        devices_without_modeling = []

        for device in devices:
            matching_model = self.find_best_model_for_device(device, models)
            
            if matching_model:
                devices_with_modeling.append((device, matching_model))
                self.stdout.write(
                    f"✅ {device.name} ({device.type.name if device.type else 'No type'}) "
                    f"→ {matching_model.name}"
                )
            else:
                devices_without_modeling.append(device)
                self.stdout.write(
                    self.style.WARNING(
                        f"❌ {device.name} ({device.type.name if device.type else 'No type'}) "
                        f"→ No matching model"
                    )
                )

        self.stdout.write(f"✅ Devices WITH modeling: {len(devices_with_modeling)}")
        self.stdout.write(f"⚠️ Devices WITHOUT modeling: {len(devices_without_modeling)}")
        
        return devices_with_modeling, devices_without_modeling

    def find_best_model_for_device(self, device, models):
        """Find the best DTDL model for a device using heuristics"""
        device_type_name = normalize_name(device.type.name) if device.type else ""
        device_name = normalize_name(device.name or "")
        
        # 1. Exact match with device type
        for model in models:
            model_name = normalize_name(model.name)
            if device_type_name and device_type_name == model_name:
                return model
        
        # 2. Partial match with device type or name
        for model in models:
            model_name = normalize_name(model.name)
            if device_type_name and (device_type_name in model_name or model_name in device_type_name):
                return model
        
        # 3. Token matching from device name
        device_tokens = [t for t in re.split(r'\W+', device_name) if t and len(t) > 2]
        for model in models:
            model_name = normalize_name(model.name)
            for token in device_tokens:
                if token in model_name:
                    return model
        
        return None

    def create_digital_twins(self, devices_with_modeling):
        """Create Digital Twins for devices with modeling"""
        self.stdout.write("🏗️ Creating Digital Twins...")
        
        created_count = 0
        failed_count = 0

        if self.dry_run:
            for device, model in devices_with_modeling:
                self.stdout.write(
                    f"[DRY RUN] Would create Digital Twin for '{device.name}' "
                    f"using model '{model.name}'"
                )
                created_count += 1
            return created_count

        with transaction.atomic():
            for device, model in devices_with_modeling:
                try:
                    # Create Digital Twin Instance
                    dt_instance = DigitalTwinInstance.objects.create(
                        model=model,
                        name=device.name,
                        active=True
                    )
                    
                    # Map device properties
                    properties_mapped = self.map_device_properties(device, dt_instance)
                    
                    created_count += 1
                    self.stdout.write(
                        f"✅ Created Digital Twin '{dt_instance.name}' "
                        f"(model: {model.name}, properties: {properties_mapped})"
                    )
                    
                except Exception as e:
                    failed_count += 1
                    self.stdout.write(
                        self.style.ERROR(
                            f"❌ Failed to create Digital Twin for '{device.name}': {e}"
                        )
                    )

        if failed_count > 0:
            self.stdout.write(
                self.style.WARNING(f"⚠️ {failed_count} Digital Twins failed to create")
            )

        return created_count

    def create_digital_twin_relationships(self):
        """Create relationships between Digital Twin instances based on device hierarchy"""
        self.stdout.write("🔗 Creating Digital Twin relationships...")
        
        if self.dry_run:
            self.stdout.write("[DRY RUN] Would analyze device hierarchy and create relationships")
            return 0
        
        created_relationships = 0
        
        # Get all Digital Twin instances
        dt_instances = DigitalTwinInstance.objects.all()
        self.stdout.write(f"  📊 Processing {dt_instances.count()} Digital Twin instances")
        
        # Create mappings by name pattern and model type
        houses = {}          # {house_num: instance}
        locations = {}       # {house_num_location: instance} (Pool, Garden, Room)
        devices = {}         # {house_num_location_device: instance}
        
        # Parse all instances and categorize them
        for dt_instance in dt_instances:
            name = dt_instance.name
            model_name = dt_instance.model.name.lower()
            
            # Parse device name pattern: "House X - Location - Device"
            parts = [part.strip() for part in name.split(' - ')]
            
            if len(parts) >= 1:
                # Extract house number
                house_match = re.search(r'house\s+(\d+)', parts[0].lower())
                if not house_match:
                    continue
                house_num = house_match.group(1)
                
                if 'house' in model_name and len(parts) == 1:
                    # This is a House instance: "House X"
                    houses[house_num] = dt_instance
                    self.stdout.write(f"  🏠 Found house: {name}")
                    
                elif len(parts) >= 2:
                    location = parts[1].lower()
                    location_key = f"{house_num}_{location}"
                    
                    if any(loc_type in model_name for loc_type in ['room', 'pool', 'garden']) and len(parts) == 2:
                        # This is a Location instance: "House X - Location"
                        locations[location_key] = dt_instance
                        self.stdout.write(f"  🏗️ Found location: {name} (type: {model_name})")
                        
                    elif len(parts) >= 3:
                        # This is a Device instance: "House X - Location - Device"
                        device_name = parts[2].lower()
                        device_key = f"{house_num}_{location}_{device_name}"
                        devices[device_key] = dt_instance
                        self.stdout.write(f"  🔧 Found device: {name} (type: {model_name})")
        
        self.stdout.write(f"  📈 Categorized: {len(houses)} houses, {len(locations)} locations, {len(devices)} devices")
        
        # 1. Create House -> Location relationships
        for house_num, house_instance in houses.items():
            house_relationships = house_instance.model.model_relationships.all()
            
            # Find all locations for this house
            house_locations = {k: v for k, v in locations.items() if k.startswith(f"{house_num}_")}
            
            for location_key, location_instance in house_locations.items():
                location_model = location_instance.model.name.lower()
                
                # Determine the correct relationship type
                relationship_name = None
                if 'room' in location_model:
                    relationship_name = 'has_rooms'
                elif 'pool' in location_model:
                    relationship_name = 'has_pool'
                elif 'garden' in location_model:
                    relationship_name = 'has_gardens'
                
                if relationship_name:
                    rel = house_relationships.filter(name=relationship_name).first()
                    if rel:
                        try:
                            relationship, created = DigitalTwinInstanceRelationship.objects.get_or_create(
                                source_instance=house_instance,
                                target_instance=location_instance,
                                relationship=rel
                            )
                            if created:
                                created_relationships += 1
                                self.stdout.write(f"  ✅ {house_instance.name} → {location_instance.name} ({relationship_name})")
                        except Exception as e:
                            self.stdout.write(self.style.WARNING(f"⚠️ Failed to create relationship: {e}"))
        
        # 2. Create Location -> Device relationships  
        for location_key, location_instance in locations.items():
            location_relationships = location_instance.model.model_relationships.all()
            location_model = location_instance.model.name.lower()
            
            # Find all devices for this location
            house_num, location = location_key.split('_', 1)
            location_devices = {k: v for k, v in devices.items() if k.startswith(f"{house_num}_{location}_")}
            
            for device_key, device_instance in location_devices.items():
                device_model = device_instance.model.name.lower()
                
                # Determine the correct relationship type based on device and location types
                relationship_name = None
                
                if 'room' in location_model:
                    if 'lightbulb' in device_model:
                        relationship_name = 'has_lights'
                    elif 'airconditioner' in device_model:
                        relationship_name = 'has_airconditioner'
                elif 'pool' in location_model:
                    if 'pump' in device_model:
                        relationship_name = 'has_pump'  # May need to check actual relationship name in model
                elif 'garden' in location_model:
                    if 'irrigation' in device_model:
                        relationship_name = 'has_irrigationSystem'
                
                if relationship_name:
                    rel = location_relationships.filter(name=relationship_name).first()
                    if rel:
                        try:
                            relationship, created = DigitalTwinInstanceRelationship.objects.get_or_create(
                                source_instance=location_instance,
                                target_instance=device_instance,
                                relationship=rel
                            )
                            if created:
                                created_relationships += 1
                                self.stdout.write(f"  ✅ {location_instance.name} → {device_instance.name} ({relationship_name})")
                        except Exception as e:
                            self.stdout.write(self.style.WARNING(f"⚠️ Failed to create relationship: {e}"))
                    else:
                        self.stdout.write(f"  ⚠️ Relationship '{relationship_name}' not found in {location_model} model")
                else:
                    self.stdout.write(f"  ⚠️ No relationship mapping for {device_model} in {location_model}")
        
        self.stdout.write(f"✅ Created {created_relationships} Digital Twin relationships")
        return created_relationships

    def map_device_properties(self, device, dt_instance):
        """Map device properties to Digital Twin properties"""
        device_properties = Property.objects.filter(device=device)
        model_elements = ModelElement.objects.filter(dtdl_model=dt_instance.model)
        
        mapped_count = 0
        
        for device_prop in device_properties:
            # Find matching model element
            best_element = self.find_best_model_element(device_prop, model_elements)
            
            if best_element:
                # Create Digital Twin Instance Property
                dt_prop, created = DigitalTwinInstanceProperty.objects.get_or_create(
                    dtinstance=dt_instance,
                    property=best_element,
                    defaults={'value': device_prop.value}
                )
                
                # Associate with device property
                dt_prop.device_property = device_prop
                dt_prop.value = device_prop.value
                dt_prop.save()
                
                mapped_count += 1
                
                self.stdout.write(
                    f"  🔗 Mapped '{device_prop.name}' → '{best_element.name}'"
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  ⚠️ No model element found for property '{device_prop.name}'"
                    )
                )
        
        return mapped_count

    def find_best_model_element(self, device_property, model_elements):
        """Find the best ModelElement for a device Property"""
        prop_name = normalize_name(device_property.name)
        
        # 1. Exact name match
        for element in model_elements:
            if normalize_name(element.name) == prop_name:
                return element
        
        # 2. Partial name match
        for element in model_elements:
            element_name = normalize_name(element.name)
            if prop_name in element_name or element_name in prop_name:
                return element
        
        # 3. Type compatibility
        for element in model_elements:
            if self.types_compatible(device_property.type, element.schema):
                return element
        
        return None

    def types_compatible(self, device_type, element_schema):
        """Check if device property type is compatible with model element schema"""
        if not device_type or not element_schema:
            return False
            
        type_mapping = {
            'Boolean': ['boolean', 'bool'],
            'Integer': ['integer', 'int', 'long'],
            'Double': ['double', 'float', 'number']
        }
        
        compatible_types = type_mapping.get(device_type, [device_type.lower()])
        return any(t in element_schema.lower() for t in compatible_types)

    def print_summary(self, devices_with_modeling, devices_without, created_count, relationships_created=0):
        """Print final summary"""
        self.stdout.write("📊 FINAL SUMMARY:")
        
        total_devices = len(devices_with_modeling) + len(devices_without)
        dt_count = DigitalTwinInstance.objects.count() if not self.dry_run else created_count
        prop_count = DigitalTwinInstanceProperty.objects.count() if not self.dry_run else 0
        rel_count = DigitalTwinInstanceRelationship.objects.count() if not self.dry_run else relationships_created
        
        self.stdout.write(f"  📱 Total Devices: {total_devices}")
        self.stdout.write(f"  🏗️ Available Models: {DTDLModel.objects.count()}")
        self.stdout.write(f"  🎯 Digital Twins Created: {dt_count}")
        self.stdout.write(f"  🔗 Properties Mapped: {prop_count}")
        self.stdout.write(f"  🔄 Relationships Created: {rel_count}")
        
        if total_devices > 0:
            coverage = (len(devices_with_modeling) / total_devices) * 100
            self.stdout.write(f"  📈 Coverage: {len(devices_with_modeling)}/{total_devices} devices ({coverage:.1f}%)")
            
            if coverage >= 80:
                self.stdout.write(self.style.SUCCESS("🎉 Excellent coverage achieved!"))
            elif coverage >= 60:
                self.stdout.write(self.style.SUCCESS("👍 Good coverage achieved"))
            elif coverage >= 40:
                self.stdout.write(self.style.WARNING("⚠️ Moderate coverage - consider adding more DTDL models"))
            else:
                self.stdout.write(self.style.ERROR("❌ Low coverage - many devices lack appropriate DTDL models"))

        if devices_without:
            self.stdout.write("\n⚠️ Devices without modeling:")
            for device in devices_without[:5]:  # Show first 5
                device_type = device.type.name if device.type else "No type"
                self.stdout.write(f"    • {device.name} ({device_type})")
            if len(devices_without) > 5:
                self.stdout.write(f"    ... and {len(devices_without) - 5} more")
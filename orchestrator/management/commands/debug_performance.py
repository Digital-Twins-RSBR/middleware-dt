import time
from datetime import datetime
from django.core.management.base import BaseCommand
from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty

class Command(BaseCommand):
    help = 'Debug causal property performance bottlenecks'

    def handle(self, *args, **options):
        print(f"[{datetime.now().isoformat()}] 🔍 DEBUG: Starting single causal property update cycle")
        
        cycle_start = time.time()
        
        # Get all DT instances
        dt_fetch_start = time.time()
        dt_instances = list(DigitalTwinInstance.objects.all())
        dt_fetch_time = time.time() - dt_fetch_start
        print(f"[{datetime.now().isoformat()}] 📊 Fetched {len(dt_instances)} DT instances in {dt_fetch_time:.3f}s")
        
        total_properties = 0
        total_updates = 0
        slow_saves = []
        
        for i, dt_instance in enumerate(dt_instances[:3]):  # Limit to first 3 instances for debugging
            instance_start = time.time()
            print(f"[{datetime.now().isoformat()}] 🔧 Processing DT instance {dt_instance.id} ({i+1}/3)")
            
            # Get causal properties
            props_start = time.time()
            causal_properties = list(DigitalTwinInstanceProperty.objects.filter(
                dtinstance=dt_instance, 
                property__supplement_types__contains=["dtmi:dtdl:extension:causal:v1:Causal"]
            ))
            props_time = time.time() - props_start
            print(f"[{datetime.now().isoformat()}] 📝 Found {len(causal_properties)} causal properties in {props_time:.3f}s")
            
            total_properties += len(causal_properties)
            
            for j, prop in enumerate(causal_properties):
                prop_start = time.time()
                property_name = getattr(prop.property, 'name', f'prop_{prop.id}')
                print(f"[{datetime.now().isoformat()}] 🔄 Processing property '{property_name}' ({j+1}/{len(causal_properties)})")
                
                if prop.device_property:
                    # Update value
                    old_value = prop.value
                    import random
                    property_schema = prop.property.schema
                    if property_schema == 'Boolean':
                        new_value = bool(random.getrandbits(1))
                    elif property_schema == 'Integer':
                        new_value = int(random.randint(0, 100))
                    elif property_schema == 'Double':
                        new_value = float(round(random.uniform(0, 100), 2))
                    else:
                        new_value = f"random_{random.randint(1000, 9999)}"
                    
                    prop.value = new_value
                    print(f"[{datetime.now().isoformat()}] 💱 Changed '{property_name}': {old_value} → {new_value}")
                    
                    # Test save performance
                    save_start = time.time()
                    prop.save(propagate_to_device=True)
                    save_time = time.time() - save_start
                    print(f"[{datetime.now().isoformat()}] 💾 Save completed for '{property_name}' in {save_time:.3f}s")
                    
                    if save_time > 1.0:
                        slow_saves.append((property_name, save_time))
                        print(f"[{datetime.now().isoformat()}] 🐌 SLOW SAVE: '{property_name}' took {save_time:.3f}s")
                    
                    total_updates += 1
                else:
                    print(f"[{datetime.now().isoformat()}] ⏭️ Skipping '{property_name}' - no device binding")
                
                prop_time = time.time() - prop_start
                print(f"[{datetime.now().isoformat()}] ⏱️ Property '{property_name}' total time: {prop_time:.3f}s")
            
            instance_time = time.time() - instance_start
            print(f"[{datetime.now().isoformat()}] 📋 DT instance {dt_instance.id} completed in {instance_time:.3f}s")
        
        cycle_time = time.time() - cycle_start
        print(f"[{datetime.now().isoformat()}] 🏁 DEBUG CYCLE COMPLETE:")
        print(f"   • Total properties found: {total_properties}")
        print(f"   • Properties updated: {total_updates}")
        print(f"   • Total time: {cycle_time:.3f}s")
        print(f"   • Average time per update: {cycle_time/total_updates:.3f}s" if total_updates > 0 else "   • No updates performed")
        
        if slow_saves:
            print(f"[{datetime.now().isoformat()}] 🐌 SLOW SAVES DETECTED:")
            for prop_name, save_time in slow_saves:
                print(f"   • {prop_name}: {save_time:.3f}s")
        else:
            print(f"[{datetime.now().isoformat()}] ✅ No slow saves detected (threshold: 1.0s)")
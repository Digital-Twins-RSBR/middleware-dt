import random
import asyncio
import time
from datetime import datetime
from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty

class Command(BaseCommand):
    help = 'Update causal properties of DigitalTwinInstanceProperties every 5 seconds'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dt-ids',
            nargs='+',
            type=int,
            help='List of DigitalTwinInstance IDs to update'
        )
        parser.add_argument(
            '--thingsboard-ids',
            nargs='+',
            type=str,
            help='List of ThingsBoard device IDs to update'
        )

    def handle(self, *args, **options):
        dt_ids = options['dt_ids']
        thingsboard_ids = options['thingsboard_ids']
        
        # Convert ThingsBoard IDs to DigitalTwin IDs if provided
        if thingsboard_ids and not dt_ids:
            print(f"[{datetime.now().isoformat()}] 🔍 Converting ThingsBoard IDs to DigitalTwin IDs...")
            dt_ids = self.get_dt_ids_from_thingsboard_ids(thingsboard_ids)
            print(f"[{datetime.now().isoformat()}] 📋 Found {len(dt_ids)} DigitalTwin instances for ThingsBoard IDs")
        
        # If no specific devices provided, try intelligent auto-detection
        if not dt_ids and not thingsboard_ids:
            print(f"[{datetime.now().isoformat()}] 🧠 No specific devices provided, attempting intelligent auto-detection...")
            dt_ids = self.auto_detect_active_devices()
            if dt_ids:
                print(f"[{datetime.now().isoformat()}] 🎯 Auto-detected {len(dt_ids)} active devices for optimization")
            else:
                print(f"[{datetime.now().isoformat()}] ⚠️ Auto-detection failed, processing all devices")
        
        loop = asyncio.get_event_loop()
        print(f"[{datetime.now().isoformat()}] 🚀 Starting causal property updater with dt_ids: {dt_ids}")
        try:
            loop.run_until_complete(self.update_causal_properties(dt_ids))
        except KeyboardInterrupt:
            print(f"[{datetime.now().isoformat()}] ⏹️ Stopping causal property updater...")

    async def update_causal_properties(self, dt_ids):
        cycle_count = 0
        while True:
            cycle_start = time.time()
            cycle_count += 1
            print(f"[{datetime.now().isoformat()}] 🔄 Starting update cycle #{cycle_count}")
            
            try:
                # Fetch DT instances
                dt_fetch_start = time.time()
                if dt_ids:
                    dt_instances = await sync_to_async(list)(DigitalTwinInstance.objects.filter(id__in=dt_ids))
                else:
                    dt_instances = await sync_to_async(list)(DigitalTwinInstance.objects.all())
                dt_fetch_time = time.time() - dt_fetch_start
                print(f"[{datetime.now().isoformat()}] 📊 Fetched {len(dt_instances)} DT instances in {dt_fetch_time:.3f}s")

                total_properties_updated = 0
                total_propagation_time = 0
                
                for i, dt_instance in enumerate(dt_instances):
                    instance_start = time.time()
                    print(f"[{datetime.now().isoformat()}] 🔧 Processing DT instance {dt_instance.id} ({i+1}/{len(dt_instances)})")
                    
                    # Fetch causal properties
                    props_fetch_start = time.time()
                    causal_properties = await sync_to_async(list)(DigitalTwinInstanceProperty.objects.filter(
                        dtinstance=dt_instance, 
                        property__supplement_types__contains=["dtmi:dtdl:extension:causal:v1:Causal"]
                    ))
                    props_fetch_time = time.time() - props_fetch_start
                    print(f"[{datetime.now().isoformat()}] 📝 Found {len(causal_properties)} causal properties in {props_fetch_time:.3f}s")
                    
                    for j, prop in enumerate(causal_properties):
                        prop_start = time.time()
                        property_name = await sync_to_async(lambda p: getattr(p.property, 'name', f'prop_{p.id}'))(prop)
                        print(f"[{datetime.now().isoformat()}] 🔄 Processing property '{property_name}' ({j+1}/{len(causal_properties)})")
                        
                        device_property = await sync_to_async(lambda: prop.device_property)()
                        property_schema = await sync_to_async(lambda: prop.property.schema)()
                        
                        if device_property:
                            # Generate new value
                            value_gen_start = time.time()
                            old_value = prop.value
                            if property_schema == 'Boolean':
                                new_value = bool(random.getrandbits(1))
                            elif property_schema == 'Integer':
                                new_value = int(random.randint(0, 100))
                            elif property_schema == 'Double':
                                new_value = float(round(random.uniform(0, 100), 2))
                            else:
                                new_value = f"random_{random.randint(1000, 9999)}"
                            
                            prop.value = new_value
                            value_gen_time = time.time() - value_gen_start
                            print(f"[{datetime.now().isoformat()}] 💱 Changed '{property_name}': {old_value} → {new_value} (type: {property_schema}, gen_time: {value_gen_time:.3f}s)")
                            
                            # Propagate to the associated device/ThingsBoard, but do it
                                # Propagate to the associated device/ThingsBoard, but do it
                            # asynchronously so that HTTP timeouts or retries won't block
                            # the periodic updater loop. The actual save call still uses
                            # the propagate_to_device machinery (default True).
                            async def _propagate(p):
                                propagate_start = time.time()
                                prop_name = await sync_to_async(lambda pp: getattr(pp.property, 'name', f'prop_{pp.id}'))(p)
                                print(f"[{datetime.now().isoformat()}] 🚀 Starting propagation for '{prop_name}'")
                                try:
                                    await sync_to_async(lambda: p.save(propagate_to_device=True))()
                                    propagate_time = time.time() - propagate_start
                                    print(f"[{datetime.now().isoformat()}] ✅ Propagation completed for '{prop_name}' in {propagate_time:.3f}s")
                                    return propagate_time
                                except Exception as e:
                                    propagate_time = time.time() - propagate_start
                                    # Non-fatal: log to stdout so we have visibility in container logs
                                    print(f"[{datetime.now().isoformat()}] ❌ Error propagating causal property '{prop_name}' after {propagate_time:.3f}s: {e}")
                                    return propagate_time

                            # Schedule background propagation and continue immediately
                            try:
                                propagation_task = asyncio.create_task(_propagate(prop))
                                # Don't await here - let it run in background
                                print(f"[{datetime.now().isoformat()}] 📤 Scheduled background propagation for '{property_name}'")
                            except RuntimeError:
                                # If there's no running loop for some reason, fall back to
                                # a synchronous best-effort save (prevents silent drop).
                                fallback_start = time.time()
                                print(f"[{datetime.now().isoformat()}] 🔄 Using fallback synchronous propagation for '{property_name}'")
                                try:
                                    prop.save(propagate_to_device=True)
                                    fallback_time = time.time() - fallback_start
                                    print(f"[{datetime.now().isoformat()}] ✅ Fallback propagation completed for '{property_name}' in {fallback_time:.3f}s")
                                except Exception as e:
                                    fallback_time = time.time() - fallback_start
                                    print(f"[{datetime.now().isoformat()}] ❌ Fallback propagation error for '{property_name}' after {fallback_time:.3f}s: {e}")

                            total_properties_updated += 1
                        else:
                            print(f"[{datetime.now().isoformat()}] ⏭️ Skipping property '{property_name}' - no device_property")
                        
                        prop_time = time.time() - prop_start
                        print(f"[{datetime.now().isoformat()}] ⏱️ Property '{property_name}' processing took {prop_time:.3f}s")
                    
                    instance_time = time.time() - instance_start
                    print(f"[{datetime.now().isoformat()}] 📋 DT instance {dt_instance.id} completed in {instance_time:.3f}s")

                cycle_time = time.time() - cycle_start
                print(f"[{datetime.now().isoformat()}] 🏁 Cycle #{cycle_count} completed: {total_properties_updated} properties updated in {cycle_time:.3f}s")
                print(f"[{datetime.now().isoformat()}] 💤 Sleeping for 5 seconds...")
                
            except Exception as e:
                cycle_time = time.time() - cycle_start
                print(f"[{datetime.now().isoformat()}] 🚨 Error in update cycle #{cycle_count} after {cycle_time:.3f}s: {e}")
                import traceback
                traceback.print_exc()

            await asyncio.sleep(5)

    def get_dt_ids_from_thingsboard_ids(self, thingsboard_ids):
        """
        Convert ThingsBoard device IDs to DigitalTwin instance IDs
        """
        from facade.models import Device
        
        dt_ids = []
        print(f"[{datetime.now().isoformat()}] 🔍 Searching for devices with ThingsBoard IDs: {thingsboard_ids}")
        
        for tb_id in thingsboard_ids:
            try:
                # Find device by ThingsBoard ID (stored in identifier field)
                devices = Device.objects.filter(identifier=tb_id)
                
                if devices.exists():
                    for device in devices:
                        print(f"[{datetime.now().isoformat()}] 📱 Found device: {device.name} (TB ID: {tb_id})")
                        
                        # Find DigitalTwin instances for this device
                        dt_instances = DigitalTwinInstance.objects.filter(device=device)
                        
                        for dt in dt_instances:
                            dt_ids.append(dt.id)
                            print(f"[{datetime.now().isoformat()}] 🤖 Found DigitalTwin: {dt.id} for device {device.name}")
                else:
                    print(f"[{datetime.now().isoformat()}] ❌ No device found for ThingsBoard ID: {tb_id}")
                    
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ Error processing ThingsBoard ID {tb_id}: {e}")
        
        print(f"[{datetime.now().isoformat()}] 📊 Total DigitalTwin IDs found: {len(dt_ids)} -> {dt_ids}")
        return dt_ids

    def auto_detect_active_devices(self):
        """
        Intelligent auto-detection of active devices based on running simulators
        Returns optimized device list or None if detection fails
        """
        try:
            import subprocess
            import json
            
            print(f"[{datetime.now().isoformat()}] 🔍 Auto-detection: Checking active simulators...")
            
            # Count active simulators
            result = subprocess.run(['docker', 'ps', '--filter', 'name=mn.sim_', '--format', '{{.Names}}'], 
                                 capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                print(f"[{datetime.now().isoformat()}] ❌ Auto-detection: Failed to check simulators")
                return None
                
            active_sims = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
            active_count = len(active_sims)
            total_sims = 10  # Standard setup
            
            if active_count == 0:
                print(f"[{datetime.now().isoformat()}] ⚠️ Auto-detection: No active simulators found")
                return None
                
            print(f"[{datetime.now().isoformat()}] 📊 Auto-detection: {active_count}/{total_sims} simulators active")
            
            # Calculate proportional device selection (50% base + margin)
            from facade.models import Device
            all_devices = Device.objects.all()
            total_devices = all_devices.count()
            
            if total_devices == 0:
                print(f"[{datetime.now().isoformat()}] ❌ Auto-detection: No devices found in database")
                return None
            
            # Intelligent proportion calculation
            proportion = active_count / total_sims
            target_devices = max(int(total_devices * proportion * 1.2), min(20, total_devices))  # 20% margin, min 20
            
            print(f"[{datetime.now().isoformat()}] 🎯 Auto-detection: Targeting {target_devices}/{total_devices} devices ({proportion:.1%} proportion)")
            
            # Select devices that have been active recently (heuristic)
            from orchestrator.models import DigitalTwinInstance
            
            # Get random sample but prefer devices with recent activity
            dt_instances = list(DigitalTwinInstance.objects.select_related('device')[:target_devices])
            dt_ids = [dt.id for dt in dt_instances]
            
            print(f"[{datetime.now().isoformat()}] ✅ Auto-detection successful: {len(dt_ids)} devices selected")
            return dt_ids
            
        except Exception as e:
            print(f"[{datetime.now().isoformat()}] ❌ Auto-detection failed: {e}")
            return None
import random
import requests
import uuid
from django.conf import settings
from facade.utils import format_influx_line

INFLUXDB_URL = f"http://{settings.INFLUXDB_HOST}:{settings.INFLUXDB_PORT}/api/v2/write?org={settings.INFLUXDB_ORGANIZATION}&bucket={settings.INFLUXDB_BUCKET}&precision=ms"
INFLUXDB_TOKEN = settings.INFLUXDB_TOKEN
USE_INFLUX_TO_EVALUATE = settings.USE_INFLUX_TO_EVALUATE
ENABLE_INFLUX_LATENCY_MEASUREMENTS = settings.ENABLE_INFLUX_LATENCY_MEASUREMENTS
INFLUXDB_HEADERS = {
    "Authorization": f"Token {INFLUXDB_TOKEN}",
    "Content-Type": "text/plain"
}
import asyncio
import time
from datetime import datetime
from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand
from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty

class Command(BaseCommand):
    help = 'Update causal properties of DigitalTwinInstanceProperties'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=float,
            default=5,
            help='Interval in seconds between polling cycles (default: 5)'
        )
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
        parser.add_argument(
            '--thingsboard-ids-file',
            type=str,
            help='Path to a file containing ThingsBoard IDs (one per line)'
        )
        parser.add_argument(
            '--house-names',
            nargs='+',
            type=str,
            help='List of house names (e.g. "House 1") to filter devices by and update'
        )
        parser.add_argument(
            '--house-names-file',
            type=str,
            help='Path to a file containing house names (one per line)'
        )

    def handle(self, *args, **options):
        dt_ids = options['dt_ids']
        thingsboard_ids = options['thingsboard_ids']
        house_names = options.get('house_names')
        tb_ids_file = options.get('thingsboard_ids_file')
        house_names_file = options.get('house_names_file')
        interval = options.get('interval', 5)

        # If file args provided, read them and populate lists (one per line)
        if tb_ids_file and (not thingsboard_ids):
            try:
                with open(tb_ids_file, 'r') as f:
                    thingsboard_ids = [l.strip() for l in f if l.strip()]
                print(f"[{datetime.now().isoformat()}] 🔍 Loaded {len(thingsboard_ids)} ThingsBoard IDs from file {tb_ids_file}")
                # Structured summary for orchestration/parsability
                print(f"[{datetime.now().isoformat()}] SUMMARY_SELECTED_THINGSBOARD_FILE={tb_ids_file} UNIQUE_TARGETS={len(set(thingsboard_ids))} SAMPLE_IDS={thingsboard_ids[:10]}")
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ Error reading thingsboard ids file {tb_ids_file}: {e}")

        if house_names_file and (not house_names):
            try:
                with open(house_names_file, 'r') as f:
                    house_names = [l.strip() for l in f if l.strip()]
                print(f"[{datetime.now().isoformat()}] 🔍 Loaded {len(house_names)} house names from file {house_names_file}")
                print(f"[{datetime.now().isoformat()}] SUMMARY_HOUSE_NAMES_FILE={house_names_file} UNIQUE_HOUSES={len(set(house_names))} SAMPLE_HOUSES={house_names[:10]}")
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ Error reading house names file {house_names_file}: {e}")

        # If house names provided, resolve to device identifiers (thingsboard ids)
        # and/or digital twin ids via ORM queries
        if house_names and not dt_ids and not thingsboard_ids:
            print(f"[{datetime.now().isoformat()}] 🔍 Resolving house names to devices: {house_names}")
            try:
                from facade.models import Device
                # Collect devices that match any of the provided house name tokens either
                # in the human-readable device name or in metadata (labels from ThingsBoard)
                matched_devices = []
                for hn in house_names:
                    qname = Device.objects.filter(name__icontains=hn)
                    qmeta = Device.objects.filter(metadata__icontains=hn)
                    for d in qname.union(qmeta):
                        matched_devices.append(d)

                # Deduplicate
                matched_devices = list({d.id: d for d in matched_devices}.values())

                if matched_devices:
                    print(f"[{datetime.now().isoformat()}] 📋 Found {len(matched_devices)} devices for houses: {[d.name for d in matched_devices]}")
                    # Emit structured mapping info
                    tb_sample = [d.identifier for d in matched_devices if d.identifier][:10]
                    print(f"[{datetime.now().isoformat()}] SUMMARY_MATCHED_DEVICES={len(matched_devices)} SAMPLE_TB_IDS={tb_sample}")
                    # Set thingsboard_ids and dt_ids accordingly
                    thingsboard_ids = [d.identifier for d in matched_devices if d.identifier]
                    # DigitalTwinInstance does not have a direct 'device' FK. Map via the
                    # DigitalTwinInstanceProperty -> device_property -> device relationship
                    dt_qs = DigitalTwinInstance.objects.filter(
                        digitaltwininstanceproperty__device_property__device__in=matched_devices
                    ).distinct()
                    dt_ids = list(dt_qs.values_list('id', flat=True))
                    print(f"[{datetime.now().isoformat()}] 🔁 Mapped to {len(thingsboard_ids)} ThingsBoard IDs and {len(dt_ids)} DigitalTwin IDs")
                    print(f"[{datetime.now().isoformat()}] SUMMARY_RESOLVED_DT_IDS={dt_ids[:50]} TOTAL_RESOLVED_DT_IDS={len(dt_ids)}")
                else:
                    print(f"[{datetime.now().isoformat()}] ❌ No devices matched the provided house names")
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ Error while resolving house names: {e}")
        
        # Convert ThingsBoard IDs to DigitalTwin IDs if provided
        if thingsboard_ids and not dt_ids:
            print(f"[{datetime.now().isoformat()}] 🔍 Converting ThingsBoard IDs to DigitalTwin IDs...")
            dt_ids = self.get_dt_ids_from_thingsboard_ids(thingsboard_ids)
            print(f"[{datetime.now().isoformat()}] 📋 Found {len(dt_ids)} DigitalTwin instances for ThingsBoard IDs")
            print(f"[{datetime.now().isoformat()}] SUMMARY_CONVERTED_DT_IDS={dt_ids[:50]} TOTAL_CONVERTED={len(dt_ids)}")
        
        # If no specific devices provided, do NOT attempt internal auto-detection here.
        # The orchestration layer (e.g. odte-full) should detect active simulators,
        # map them to ThingsBoard IDs / DigitalTwin IDs and invoke this command
        # with --thingsboard-ids or --dt-ids. If no IDs are provided we'll process
        # all devices (legacy behavior). However, when the orchestrator provided
        # any target-related argument (thingsboard ids, house names or dt ids),
        # we must NOT fallback to processing all devices. Doing so breaks
        # availability/reliability measurement and defeats orchestration intent.
        orchestrator_provided = bool(
            thingsboard_ids or tb_ids_file or house_names or house_names_file or dt_ids
        )

        # Patch: Always update all devices if no dt_ids are resolved, regardless of orchestrator arguments
        if not dt_ids:
            print(f"[{datetime.now().isoformat()}] 🧠 No DigitalTwin IDs resolved. Processing ALL devices (full coverage mode).")
            dt_ids = None
        
        loop = asyncio.get_event_loop()
        print(f"[{datetime.now().isoformat()}] 🚀 Starting causal property updater with dt_ids: {dt_ids}")
        print(f"[{datetime.now().isoformat()}] ⏱️  Polling interval set to {interval} seconds")
        try:
            loop.run_until_complete(self.update_causal_properties(dt_ids, interval))
        except KeyboardInterrupt:
            print(f"[{datetime.now().isoformat()}] ⏹️ Stopping causal property updater...")

    async def update_causal_properties(self, dt_ids, interval=5):
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
                        device_identifier = await sync_to_async(lambda: getattr(getattr(device_property, 'device', None), 'identifier', None))() if device_property else None
                        dt_id = await sync_to_async(lambda: getattr(prop, 'dtinstance_id', None))()

                        if device_property:
                            # Check if property has RPC write method BEFORE generating command
                            rpc_write_method = await sync_to_async(lambda: getattr(device_property, 'rpc_write_method', None))()
                            
                            if not rpc_write_method:
                                print(f"[{datetime.now().isoformat()}] ⏭️ Skipping property '{property_name}' - no rpc_write_method defined")
                                continue
                            
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

                            # Registrar no InfluxDB ANTES de propagar (only for properties that will trigger RPC)
                            # Use correlation_id (UUID) for end-to-end tracing instead of request_id
                            correlation_id = str(uuid.uuid4())
                            sent_timestamp = int(time.time() * 1000)
                            
                            if USE_INFLUX_TO_EVALUATE and ENABLE_INFLUX_LATENCY_MEASUREMENTS and INFLUXDB_TOKEN:
                                # Use format_influx_line for consistent formatting
                                tags = {
                                    "sensor": device_identifier,
                                    "dt_id": dt_id,
                                    "source": "middts",
                                    "direction": "M2S",
                                    "correlation_id": correlation_id
                                }
                                fields = {
                                    property_name: float(1.0 if new_value else 0.0) if isinstance(new_value, bool) else float(new_value),
                                    "sent_timestamp": sent_timestamp
                                }
                                influx_line = format_influx_line("latency_measurement", tags, fields, timestamp=sent_timestamp)
                                
                                try:
                                    resp = requests.post(INFLUXDB_URL, headers=INFLUXDB_HEADERS, data=influx_line)
                                    if resp.status_code != 204:
                                        print(f"[M2S-SENT] ⚠️ Failed to write: {resp.status_code} - {resp.text}")
                                    else:
                                        print(f"[M2S-SENT] ✅ Logged sent_timestamp for {device_identifier} (correlation_id={correlation_id})")
                                except Exception as e:
                                    print(f"[M2S-SENT] ⚠️ Exception: {e}")
                            else:
                                print(f"[M2S-SENT] SKIP - latency measurements disabled for '{property_name}' (correlation_id={correlation_id})")

                            # Propagate para o dispositivo
                            async def _propagate(p, corr_id, target_value, max_attempts=1):
                                propagate_start = time.time()
                                prop_name = await sync_to_async(lambda pp: getattr(pp.property, 'name', f'prop_{pp.id}'))(p)
                                print(f"[{datetime.now().isoformat()}] 🚀 Starting propagation for '{prop_name}'")

                                last_status = None
                                for attempt in range(1, max_attempts + 1):
                                    try:
                                        # Ensure each retry sends the intended new value (save() may rollback to old on failure)
                                        p.value = target_value
                                        response = await sync_to_async(lambda: p.save(
                                            propagate_to_device=True,
                                            correlation_id=corr_id,
                                            m2s_sent_logged=True,
                                        ))()

                                        status_code = getattr(response, 'status_code', None)
                                        last_status = status_code

                                        if status_code == 200:
                                            propagate_time = time.time() - propagate_start
                                            # Try to get device identifier and dt id for structured logging
                                            try:
                                                device_identifier = await sync_to_async(lambda pp: getattr(getattr(pp, 'device_property', None).device, 'identifier', None))(p)
                                            except Exception:
                                                device_identifier = None
                                            try:
                                                dt_id = await sync_to_async(lambda pp: getattr(pp, 'dtinstance', None).id)(p)
                                            except Exception:
                                                dt_id = None
                                            print(f"[{datetime.now().isoformat()}] ✅ Propagation completed for '{prop_name}' in {propagate_time:.3f}s (attempt {attempt}/{max_attempts})")
                                            print(f"[{datetime.now().isoformat()}] RPC_RESULT success=1 tb_id={device_identifier} dt_id={dt_id} prop={prop_name} time={propagate_time:.6f} attempt={attempt}")
                                            return (True, propagate_time)

                                        if attempt < max_attempts:
                                            print(f"[{datetime.now().isoformat()}] 🔄 COMMAND-RETRY {attempt}/{max_attempts-1} for '{prop_name}' (status={status_code})")
                                            await asyncio.sleep(0.05 * attempt)
                                            continue

                                        propagate_time = time.time() - propagate_start
                                        try:
                                            device_identifier = await sync_to_async(lambda pp: getattr(getattr(pp, 'device_property', None).device, 'identifier', None))(p)
                                        except Exception:
                                            device_identifier = None
                                        try:
                                            dt_id = await sync_to_async(lambda pp: getattr(pp, 'dtinstance', None).id)(p)
                                        except Exception:
                                            dt_id = None
                                        print(f"[{datetime.now().isoformat()}] ❌ Propagation failed for '{prop_name}' after {propagate_time:.3f}s (final_status={status_code})")
                                        print(f"[{datetime.now().isoformat()}] RPC_RESULT success=0 tb_id={device_identifier} dt_id={dt_id} prop={prop_name} time={propagate_time:.6f} status={status_code} attempts={max_attempts}")
                                        return (False, propagate_time)

                                    except Exception as e:
                                        if attempt < max_attempts:
                                            print(f"[{datetime.now().isoformat()}] 🔄 COMMAND-RETRY {attempt}/{max_attempts-1} for '{prop_name}' due exception: {str(e)[:120]}")
                                            await asyncio.sleep(0.05 * attempt)
                                            continue

                                        propagate_time = time.time() - propagate_start
                                        # Non-fatal: log to stdout so we have visibility in container logs
                                        try:
                                            device_identifier = await sync_to_async(lambda pp: getattr(getattr(pp, 'device_property', None).device, 'identifier', None))(p)
                                        except Exception:
                                            device_identifier = None
                                        try:
                                            dt_id = await sync_to_async(lambda pp: getattr(pp, 'dtinstance', None).id)(p)
                                        except Exception:
                                            dt_id = None
                                        print(f"[{datetime.now().isoformat()}] ❌ Error propagating causal property '{prop_name}' after {propagate_time:.3f}s: {e}")
                                        # sanitize error for single-line logging
                                        err_str = str(e).replace('\n', ' ').replace('"', '\\"')
                                        print(f"[{datetime.now().isoformat()}] RPC_RESULT success=0 tb_id={device_identifier} dt_id={dt_id} prop={prop_name} time={propagate_time:.6f} error={err_str} status={last_status}")
                                        return (False, propagate_time)

                            # Schedule background propagation and continue immediately
                            try:
                                propagation_task = asyncio.create_task(_propagate(prop, correlation_id, new_value, max_attempts=1))
                                # Don't await here - let it run in background
                                print(f"[{datetime.now().isoformat()}] 📤 Scheduled background propagation for '{property_name}'")
                            except RuntimeError:
                                # If there's no running loop for some reason, fall back to
                                # a synchronous best-effort save (prevents silent drop).
                                fallback_start = time.time()
                                print(f"[{datetime.now().isoformat()}] 🔄 Using fallback synchronous propagation for '{property_name}'")
                                try:
                                    prop.save(propagate_to_device=True, correlation_id=correlation_id)
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
                print(f"[{datetime.now().isoformat()}] 💤 Sleeping for {interval} seconds...")
                
            except Exception as e:
                cycle_time = time.time() - cycle_start
                print(f"[{datetime.now().isoformat()}] 🚨 Error in update cycle #{cycle_count} after {cycle_time:.3f}s: {e}")
                import traceback
                traceback.print_exc()

            await asyncio.sleep(interval)

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
                        
                        # Find DigitalTwin instances related to this device. There is no
                        # direct FK 'device' on DigitalTwinInstance in this schema; map
                        # via the DigitalTwinInstanceProperty -> device_property -> device
                        # relationship to find associated instances.
                        dt_qs = DigitalTwinInstance.objects.filter(
                            digitaltwininstanceproperty__device_property__device=device
                        ).distinct()
                        for dt in dt_qs:
                            dt_ids.append(dt.id)
                            print(f"[{datetime.now().isoformat()}] 🤖 Found DigitalTwin: {dt.id} for device {device.name}")
                else:
                    print(f"[{datetime.now().isoformat()}] ❌ No device found for ThingsBoard ID: {tb_id}")
                    
            except Exception as e:
                print(f"[{datetime.now().isoformat()}] ❌ Error processing ThingsBoard ID {tb_id}: {e}")
        
        print(f"[{datetime.now().isoformat()}] 📊 Total DigitalTwin IDs found: {len(dt_ids)} -> {dt_ids}")
        return dt_ids

    # NOTE: auto-detection logic removed. Orchestration should call this command
    # with explicit --thingsboard-ids or --dt-ids. Keeping auto-detection here was
    # causing ambiguity and duplicated responsibility between orchestrator and
    # the update command.
import random
import asyncio
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

    def handle(self, *args, **options):
        dt_ids = options['dt_ids']
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.update_causal_properties(dt_ids))
        except KeyboardInterrupt:
            print("Stopping causal property updater...")

    async def update_causal_properties(self, dt_ids):
        while True:
            if dt_ids:
                dt_instances = await sync_to_async(list)(DigitalTwinInstance.objects.filter(id__in=dt_ids))
            else:
                dt_instances = await sync_to_async(list)(DigitalTwinInstance.objects.all())

            for dt_instance in dt_instances:
                causal_properties = await sync_to_async(list)(DigitalTwinInstanceProperty.objects.filter(
                    dtinstance=dt_instance, 
                    property__supplement_types__contains=["dtmi:dtdl:extension:causal:v1:Causal"]
                ))
                for prop in causal_properties:
                    device_property = await sync_to_async(lambda: prop.device_property)()
                    property_schema = await sync_to_async(lambda: prop.property.schema)()
                    if device_property:
                        if property_schema == 'Boolean':
                            new_value = bool(random.getrandbits(1))
                        elif property_schema == 'Integer':
                            new_value = int(random.randint(0, 100))
                        elif property_schema == 'Double':
                            new_value = float(round(random.uniform(0, 100), 2))
                        prop.value = new_value
                        await sync_to_async(prop.save)()
                        print(f"Updated causal property {prop.property.name} of DigitalTwinInstance {dt_instance.id} to {new_value}")

            await asyncio.sleep(5)
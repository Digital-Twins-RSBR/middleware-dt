from django.core.management.base import BaseCommand
import requests
import copy
import json

class Command(BaseCommand):
    help = "Replica e cria instâncias hierárquicas via API"

    def add_arguments(self, parser):
        parser.add_argument('--system-id', type=int, required=True)
        parser.add_argument('--template', type=str, required=True, help='Caminho para o arquivo JSON de template')
        parser.add_argument('--n-replicas', type=int, required=True)
        parser.add_argument('--api-url', type=str, required=True)
        parser.add_argument('--token', type=str, default=None)

    def handle(self, *args, **options):
        system_id = options['system_id']
        n_replicas = options['n_replicas']
        api_url = options['api_url'].rstrip('/')
        token = options['token']
        with open(options['template'], 'r') as f:
            template_json = json.load(f)

        for i in range(1, n_replicas + 1):
            replica = copy.deepcopy(template_json)
            root_name = list(replica.keys())[0]
            new_root = f"{root_name.split()[0]} {i}"
            replica[new_root] = replica.pop(root_name)
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            resp = requests.post(
                f"{api_url}/orchestrator/systems/{system_id}/instances/hierarchical/",
                json=replica,
                headers=headers
            )
            self.stdout.write(f"Replica {i}: status={resp.status_code}, response={resp.text}")


# python manage.py replicate_and_create_instances --system-id 1 --template template.json --n-replicas 100 --api-url http://localhost:8000/api
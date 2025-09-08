from django.core.management.base import BaseCommand
import copy
import json
from django.test import RequestFactory
from orchestrator.api import create_hierarchical_instances
from ninja.errors import HttpError

class Command(BaseCommand):
    help = "Replica e cria instâncias hierárquicas via API"

    def add_arguments(self, parser):
        parser.add_argument('--system-id', type=int, required=True)
        parser.add_argument('--template', type=str, required=True, help='Caminho para o arquivo JSON de template')
        parser.add_argument('--n-replicas', type=int, required=True)
        parser.add_argument('--token', type=str, default=None)

    def handle(self, *args, **options):
        system_id = options['system_id']
        n_replicas = options['n_replicas']
        token = options['token']
        with open(options['template'], 'r') as f:
            template_json = json.load(f)

        for i in range(1, n_replicas + 1):
            replica = copy.deepcopy(template_json)
            root_name = list(replica.keys())[0]
            new_root = f"{root_name.split()[0]} {i}"
            replica[new_root] = replica.pop(root_name)
            # Call the orchestrator view internally to avoid HTTP roundtrip.
            try:
                if token:
                    rf = RequestFactory()
                    # create a dummy POST request and inject Authorization header
                    req = rf.post("/orchestrator/internal/")
                    req.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'
                else:
                    req = None

                result = create_hierarchical_instances(req, system_id, replica)
                # If the view returns a Django HttpResponse-like object, try to stringify
                if hasattr(result, 'status_code'):
                    # likely an HttpResponse; extract content
                    try:
                        body = result.content.decode('utf-8')
                    except Exception:
                        body = str(result)
                    status = getattr(result, 'status_code', 'unknown')
                    self.stdout.write(f"Replica {i}: status={status}, response={body}")
                else:
                    # result is likely a Python object (list/dict)
                    self.stdout.write(f"Replica {i}: ok, created={json.dumps(result)}")
            except HttpError as e:
                # ninja.errors.HttpError exposes status_code and message
                try:
                    status = e.status_code
                except Exception:
                    status = 'error'
                self.stderr.write(f"Replica {i}: HttpError status={status}, detail={e}")
            except Exception as e:
                self.stderr.write(f"Replica {i}: unexpected error: {e}")


# python manage.py replicate_and_create_instances --system-id 1 --template template.json --n-replicas 100
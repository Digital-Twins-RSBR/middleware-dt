"""
Management command: discover_all_gateways
=====================================
Chama a API REST do próprio middleware para iterar sobre todos os
`GatewayIOT` cadastrados e invocar o endpoint de descoberta de
dispositivos por gateway: `/api/facade/gatewaysiot/{id}/discover-devices/`.

Uso:
    python manage.py discover_all_gateways
    python manage.py discover_all_gateways --base-url http://localhost:8000
    python manage.py discover_all_gateways --gateway-ids 1,2
    python manage.py discover_all_gateways --page-size 200 --dry-run

Equivalente via Make (dentro do container middleware):
    make discover-gateways
    make discover-gateways ARGS="--gateway-ids=1,2"

Observação: o comando chama os endpoints da API para exercitar o stack
HTTP/Ninja e garantir que a lógica de `discover_devices` é testada.
"""
import sys
import os
from django.core.management.base import BaseCommand, CommandError
import requests
from django.contrib.auth import get_user_model
from django.test import Client
from urllib.parse import urlsplit


class _DjangoClientSession:
    def __init__(self, client):
        self.client = client

    def _path(self, url, params=None):
        parsed = urlsplit(url)
        path = parsed.path or "/"
        query_parts = []
        if parsed.query:
            query_parts.append(parsed.query)
        if params:
            query_parts.extend(f"{key}={value}" for key, value in params.items())
        if query_parts:
            path = f"{path}?{'&'.join(query_parts)}"
        return path

    def get(self, url, params=None, timeout=None):
        return _DjangoClientResponse(self.client.get(self._path(url, params=params)))


class _DjangoClientResponse:
    def __init__(self, response):
        self.status_code = response.status_code
        self.text = response.content.decode("utf-8", errors="replace")

    def json(self):
        import json

        return json.loads(self.text or "null")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}: {self.text}")


class Command(BaseCommand):
    help = "Chama a API REST para descobrir dispositivos em todos os Gateways"

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            default="http://localhost:8000",
            help="URL base da API (default: http://localhost:8000)",
        )
        parser.add_argument(
            "--gateway-ids",
            default=None,
            help="Lista separada por vírgula de gateway ids a processar (ex: 1,2,3). Se omitido, processa todos.",
        )
        parser.add_argument(
            "--page-size",
            type=int,
            default=200,
            help="Valor pageSize passado ao endpoint de descoberta (default: 200)",
        )
        parser.add_argument(
            "--page",
            type=int,
            default=0,
            help="Número da página (0-index) a solicitar do ThingsBoard (default: 0)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Não faz chamadas que alterem o estado; apenas mostra o que faria",
        )
        parser.add_argument(
            "--username",
            default=os.getenv("DJANGO_SUPERUSER_USERNAME", "middts"),
            help="Usuário Django usado para autenticar as chamadas da API (default: DJANGO_SUPERUSER_USERNAME ou middts)",
        )

    def handle(self, *args, **options):
        base_url = options["base_url"].rstrip("/")
        gateway_ids = options["gateway_ids"]
        page_size = options["page_size"]
        page = options["page"]
        dry_run = options["dry_run"]
        username = options["username"]

        session = self._build_authenticated_session(username)

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== discover_all_gateways ==="))
        self.stdout.write(f"  API base URL : {base_url}")
        if gateway_ids:
            self.stdout.write(f"  Gateway IDs  : {gateway_ids}")
        self.stdout.write(f"  pageSize     : {page_size}")
        if dry_run:
            self.stdout.write(self.style.WARNING("  ** DRY RUN — nenhuma chamada de escrita será feita **"))

        # --- 1. Verificar API ---
        self._check_api(session, base_url)

        # --- 2. Obter lista de gateways via API ---
        gateways = self._list_gateways(session, base_url)
        if gateway_ids:
            wanted = set(int(x.strip()) for x in gateway_ids.split(",") if x.strip())
            gateways = [g for g in gateways if g.get("id") in wanted]

        if not gateways:
            self.stdout.write(self.style.WARNING("Nenhum Gateway encontrado para processar."))
            return

        # --- 3. Iterar e chamar endpoint de descoberta ---
        results = []
        for g in gateways:
            gid = g.get("id")
            gname = g.get("name") or str(gid)
            self.stdout.write(f"\nProcessando gateway {gname} (id={gid}) ...")

            discover_url = f"{base_url}/api/facade/gatewaysiot/{gid}/discover-devices/"
            params = {"pageSize": page_size, "page": page}

            if dry_run:
                self.stdout.write(self.style.WARNING(f"  [dry-run] GET {discover_url} params={params}"))
                results.append({"gateway": gid, "status": "dry-run"})
                continue

            try:
                resp = session.get(discover_url, params=params, timeout=30)
            except requests.ConnectionError as exc:
                self.stdout.write(self.style.ERROR(f"  ✗ Falha de conexão: {exc}"))
                results.append({"gateway": gid, "status": "conn-error", "detail": str(exc)})
                continue
            except requests.Timeout:
                self.stdout.write(self.style.ERROR("  ✗ Timeout ao chamar o endpoint de descoberta."))
                results.append({"gateway": gid, "status": "timeout"})
                continue

            if resp.status_code not in (200, 201):
                self.stdout.write(self.style.ERROR(f"  ✗ HTTP {resp.status_code}: {resp.text[:200]}"))
                results.append({"gateway": gid, "status": "http-error", "code": resp.status_code})
                continue

            try:
                data = resp.json()
            except Exception:
                data = None

            created = data.get("created") if isinstance(data, dict) else None
            updated = data.get("updated") if isinstance(data, dict) else None
            self.stdout.write(self.style.SUCCESS(f"  ✓ resultado: created={created} updated={updated}"))
            results.append({"gateway": gid, "status": "ok", "created": created, "updated": updated})

        # --- 4. Sumário ---
        self._print_summary(results)

    def _check_api(self, session, base_url):
        """Faz uma requisição GET simples em um endpoint estável para verificar que a API responde.

        Usamos `/api/orchestrator/systems/` pois é um endpoint conhecido existente no projeto.
        """
        url = f"{base_url}/api/orchestrator/systems/"
        self.stdout.write(f"Verificando API em {url} ...")
        try:
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            self.stdout.write(self.style.SUCCESS(f"  ✓ API acessível (HTTP {resp.status_code})"))
        except requests.ConnectionError as exc:
            raise CommandError(
                f"Não foi possível conectar à API em {base_url}. Certifique-se de que o middleware está rodando. Detalhe: {exc}"
            )
        except requests.HTTPError as exc:
            raise CommandError(f"API retornou erro: {exc}")

    def _list_gateways(self, session, base_url):
        url = f"{base_url}/api/core/gatewaysiot/"
        try:
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            # Fallback: obter gateways via ORM local. Isso garante que ainda
            # chamemos o endpoint de descoberta por gateway (via HTTP), mesmo
            # quando a listagem via API não estiver disponível.
            try:
                from core.models import GatewayIOT

                self.stdout.write(self.style.WARNING(
                    "  ⚠ listagem via API falhou — usando fallback local (ORM) para obter gateways"
                ))
                return list(GatewayIOT.objects.values("id", "name", "url"))
            except Exception as exc:
                raise CommandError(f"Falha ao listar gateways (API e ORM): {exc}")

    def _print_summary(self, results):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Sumário ==="))
        ok = [r for r in results if r["status"] == "ok"]
        errs = [r for r in results if r["status"] not in ("ok", "dry-run")]
        dry = [r for r in results if r["status"] == "dry-run"]
        self.stdout.write(f"  Gateways processados: {len(results)}")
        self.stdout.write(self.style.SUCCESS(f"  Sucesso: {len(ok)}"))
        if dry:
            self.stdout.write(self.style.WARNING(f"  Dry-run: {len(dry)}"))
        if errs:
            self.stdout.write(self.style.ERROR(f"  Erros: {len(errs)}"))
            for e in errs:
                self.stdout.write(self.style.ERROR(f"    - {e}"))
        self.stdout.write("")

    def _build_authenticated_session(self, username):
        user = get_user_model().objects.filter(username=username).first()
        if not user:
            raise CommandError(
                f"Usuário '{username}' não encontrado. Ajuste --username ou garanta que o superuser exista."
            )
        client = Client()
        client.force_login(user)
        return _DjangoClientSession(client)

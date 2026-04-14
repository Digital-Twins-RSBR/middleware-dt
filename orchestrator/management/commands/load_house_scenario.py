"""
Management command: load_house_scenario
========================================
Carrega o cenário House 2.0 no middleware-dt chamando os endpoints REST da
própria API, exercitando o stack completo:

  Django views → Ninja API → DTDLModel.save() → parser microservice (DTDL_PARSER_URL)

Uso:
    python manage.py load_house_scenario
    python manage.py load_house_scenario --base-url http://localhost:8000
    python manage.py load_house_scenario --force   # recria mesmo se já existir
    python manage.py load_house_scenario --system-name "Casa 2.0"

Equivalente via Make (dentro do container middleware):
    make seed-house
"""
import json
import sys
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError

# Ordem de criação garante que modelos sem dependências venham antes.
# O parser lida com relacionamentos entre modelos na mesma especificação,
# mas criamos na ordem lógica para facilitar depuração.
MODEL_ORDER = [
    "LightBulb.json",
    "AirConditioner.json",
    "Irrigation.json",
    "Pump.json",
    "Garden.json",
    "Pool.json",
    "Room.json",
    "House.json",
]

# commands/ -> management/ -> orchestrator/ -> <project_root>
SCENARIOS_DIR = Path(__file__).resolve().parents[3] / "scenarios" / "house2.0"

SYSTEM_NAME = "House 2.0 Condominium"
SYSTEM_DESCRIPTION = (
    "Cenário House 2.0 — modelos DTDL de condomínio residencial com cômodos, "
    "piscina, jardim, irrigação, iluminação e ar condicionado. "
    "Fonte: https://github.com/Digital-Twins-RSBR/HouseScenario/tree/main/models/House2.0"
)


class Command(BaseCommand):
    help = "Carrega o cenário House 2.0 (SystemContext + DTDLModels) via API REST"

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            default="http://localhost:8000",
            help="URL base da API (default: http://localhost:8000)",
        )
        parser.add_argument(
            "--system-name",
            default=SYSTEM_NAME,
            help=f"Nome do SystemContext a criar (default: '{SYSTEM_NAME}')",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Recria os DTDLModels mesmo se o sistema já existir",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o que seria criado sem fazer chamadas de escrita",
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        base_url = options["base_url"].rstrip("/")
        system_name = options["system_name"]
        force = options["force"]
        dry_run = options["dry_run"]
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== load_house_scenario ==="))
        self.stdout.write(f"  API base URL : {base_url}")
        self.stdout.write(f"  Sistema      : {system_name}")
        self.stdout.write(f"  Scenarios dir: {SCENARIOS_DIR}")
        if dry_run:
            self.stdout.write(self.style.WARNING("  ** DRY RUN — nenhuma escrita será feita **"))
        self.stdout.write("")

        # --- 1. Verificar acessibilidade da API ---
        self._check_api(session, base_url)

        # --- 2. Obter ou criar SystemContext ---
        system_id = self._get_or_create_system(
            session, base_url, system_name, force, dry_run
        )
        if dry_run and system_id is None:
            system_id = "<dry-run-id>"

        # --- 3. Carregar modelos DTDL ---
        results = self._load_models(
            session, base_url, system_id, force, dry_run
        )

        # --- 4. Sumário ---
        self._print_summary(results, dry_run)

    # ------------------------------------------------------------------
    def _check_api(self, session, base_url):
        """Faz uma requisição GET simples para verificar que a API responde."""
        url = f"{base_url}/api/orchestrator/systems/"
        self.stdout.write(f"Verificando API em {url} ...")
        try:
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            self.stdout.write(self.style.SUCCESS(f"  ✓ API acessível (HTTP {resp.status_code})"))
        except requests.ConnectionError as exc:
            raise CommandError(
                f"Não foi possível conectar à API em {base_url}. "
                f"Certifique-se de que o middleware está rodando. Detalhe: {exc}"
            )
        except requests.HTTPError as exc:
            raise CommandError(f"API retornou erro: {exc}")

    # ------------------------------------------------------------------
    def _get_or_create_system(self, session, base_url, name, force, dry_run):
        """Retorna o ID do sistema existente ou cria um novo."""
        list_url = f"{base_url}/api/orchestrator/systems/"
        resp = session.get(list_url, timeout=10)
        resp.raise_for_status()
        systems = resp.json()

        existing = next((s for s in systems if s["name"] == name), None)

        if existing:
            system_id = existing["id"]
            if force:
                self.stdout.write(
                    self.style.WARNING(
                        f"Sistema '{name}' já existe (id={system_id}). "
                        "--force ativo: modelos serão recriados."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Sistema '{name}' já existe (id={system_id}). "
                        "Use --force para recriar os modelos."
                    )
                )
            return system_id

        self.stdout.write(f"Criando SystemContext '{name}' ...")
        if dry_run:
            self.stdout.write(self.style.WARNING("  [dry-run] POST /api/orchestrator/systems/ ignorado"))
            return None

        payload = {"name": name, "description": SYSTEM_DESCRIPTION}
        resp = session.post(
            f"{base_url}/api/orchestrator/systems/",
            json=payload,
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            raise CommandError(
                f"Falha ao criar sistema: HTTP {resp.status_code} — {resp.text}"
            )
        system = resp.json()
        self.stdout.write(
            self.style.SUCCESS(f"  ✓ Sistema criado: {system['name']} (id={system['id']})")
        )
        return system["id"]

    # ------------------------------------------------------------------
    def _load_models(self, session, base_url, system_id, force, dry_run):
        """Itera sobre os JSONs e cria cada DTDLModel via API."""
        results = []

        for filename in MODEL_ORDER:
            json_path = SCENARIOS_DIR / filename
            if not json_path.exists():
                self.stdout.write(
                    self.style.WARNING(f"  ⚠ Arquivo não encontrado: {json_path} — pulando")
                )
                results.append({"file": filename, "status": "missing"})
                continue

            spec = json.loads(json_path.read_text())
            display_name = spec.get("displayName") or spec.get("@id", filename)

            self.stdout.write(f"\nProcessando {filename} ({display_name}) ...")

            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"  [dry-run] POST /api/orchestrator/systems/{system_id}/dtdlmodels/ ignorado"
                    )
                )
                results.append({"file": filename, "model": display_name, "status": "dry-run"})
                continue

            # Verifica se já existe (GET list) — evita duplicata quando --force não passado
            if not force:
                existing_id = self._find_existing_model(session, base_url, system_id, spec.get("@id"))
                if existing_id is not None:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  → já existe (id={existing_id}), pulando. Use --force para recriar."
                        )
                    )
                    results.append({"file": filename, "model": display_name, "status": "skipped", "id": existing_id})
                    continue

            payload = {"name": display_name, "specification": spec}
            url = f"{base_url}/api/orchestrator/systems/{system_id}/dtdlmodels/"

            try:
                resp = session.post(url, json=payload, timeout=30)
            except requests.Timeout:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ Timeout ao processar {filename}. Parser demorou demais?")
                )
                results.append({"file": filename, "model": display_name, "status": "timeout"})
                continue

            if resp.status_code not in (200, 201):
                self.stdout.write(
                    self.style.ERROR(
                        f"  ✗ HTTP {resp.status_code}: {resp.text[:300]}"
                    )
                )
                results.append(
                    {"file": filename, "model": display_name, "status": "error", "detail": resp.text[:300]}
                )
                continue

            model = resp.json()
            parsed = model.get("parsed_specification") or {}
            n_elements = len(parsed.get("modelElements", [])) if isinstance(parsed, dict) else "?"
            n_relations = len(parsed.get("modelRelationships", [])) if isinstance(parsed, dict) else "?"
            self.stdout.write(
                self.style.SUCCESS(
                    f"  ✓ {display_name} criado (id={model['id']}) — "
                    f"{n_elements} elements, {n_relations} relationships"
                )
            )
            results.append(
                {"file": filename, "model": display_name, "status": "created", "id": model["id"]}
            )

        return results

    # ------------------------------------------------------------------
    def _find_existing_model(self, session, base_url, system_id, dtdl_id):
        """Retorna o id do DTDLModel se já existir no sistema, ou None."""
        if not dtdl_id:
            return None
        url = f"{base_url}/api/orchestrator/systems/{system_id}/dtdlmodels/"
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code != 200:
                return None
            for m in resp.json():
                if m.get("dtdl_id") == dtdl_id:
                    return m["id"]
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    def _print_summary(self, results, dry_run):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Sumário ==="))
        counts = {"created": 0, "skipped": 0, "error": 0, "timeout": 0, "missing": 0, "dry-run": 0}
        for r in results:
            status = r["status"]
            counts[status] = counts.get(status, 0) + 1
            icon = {"created": "✓", "skipped": "→", "error": "✗", "timeout": "⏱", "missing": "⚠", "dry-run": "○"}.get(status, "?")
            colour = {
                "created": self.style.SUCCESS,
                "skipped": self.style.SUCCESS,
                "error": self.style.ERROR,
                "timeout": self.style.ERROR,
                "missing": self.style.WARNING,
                "dry-run": self.style.WARNING,
            }.get(status, str)
            self.stdout.write(colour(f"  {icon} [{status:8s}] {r.get('model', r['file'])}"))
        self.stdout.write("")
        self.stdout.write(f"  Total: {len(results)} modelos | "
                          f"criados={counts['created']} skipped={counts['skipped']} "
                          f"errors={counts['error'] + counts['timeout'] + counts['missing']}")
        if dry_run:
            self.stdout.write(self.style.WARNING("\n  (dry-run — nenhuma mudança persistida)"))
        elif counts["error"] + counts["timeout"] + counts["missing"] > 0:
            self.stdout.write(self.style.ERROR("\n  Atenção: alguns modelos falharam. Verifique os logs acima."))
            sys.exit(1)
        else:
            self.stdout.write(self.style.SUCCESS("\n  Cenário House 2.0 carregado com sucesso!"))

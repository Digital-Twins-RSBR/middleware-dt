from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Organization
from orchestrator.models import SystemContext
from neomodel import db


class Command(BaseCommand):
    help = "Seed a SystemContext id=2 and a DigitalTwin node in Neo4j"

    def handle(self, *args, **options):
        User = get_user_model()
        u = User.objects.filter(username="middts").first()
        if not u:
            self.stdout.write(self.style.ERROR("User 'middts' not found. Create the user first."))
            return

        org = Organization.objects.first()
        if not org:
            org = Organization.objects.create(name="SeedOrg", created_by=u)

        if not SystemContext.objects.filter(id=2).exists():
            sc = SystemContext.objects.create(id=2, name="SeedSystem", organization=org, created_by=u)
            created = True
        else:
            sc = SystemContext.objects.get(id=2)
            created = False

        self.stdout.write(self.style.SUCCESS(f"SystemContext id={sc.id} created={created}"))

        q = (
            "MERGE (s:SystemContext {system_id:%d}) "
            "MERGE (dt:DigitalTwin {name:'SeedTestDT', model_name:'SeedModel'}) "
            "MERGE (s)-[:CONTAINS]->(dt) RETURN s,dt" % sc.id
        )
        try:
            res, meta = db.cypher_query(q)
            self.stdout.write(self.style.SUCCESS(f"Neo4j seed result rows={len(res)} meta={meta}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Neo4j query failed: {e}"))

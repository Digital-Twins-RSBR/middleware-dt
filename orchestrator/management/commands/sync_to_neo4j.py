from django.core.management.base import BaseCommand
from orchestrator.models import DigitalTwinInstance, SystemContext as DjangoSystemContext
from orchestrator.neo4jmodels import DigitalTwin, TwinProperty, SystemContext as Neo4jSystemContext
from neomodel import db
from neomodel import config as neomodel_config
import socket
import traceback

class Command(BaseCommand):
    help = "Synchronize Digital Twins and their properties from PostgreSQL to Neo4j"

    def handle(self, *args, **options):
        self.stdout.write("Starting synchronization...")

        # Apaga todos os nós e relacionamentos do Neo4j
        self.stdout.write("Clearing all nodes and relationships from Neo4j...")
        try:
            with db.transaction:
                db.cypher_query("MATCH (n) DETACH DELETE n")
                self.stdout.write(self.style.WARNING("All nodes and relationships have been deleted."))
        except Exception as e:
            # Ajuda de diagnóstico quando o host/porta não resolvem
            self.stderr.write(self.style.ERROR("Failed to connect to Neo4j."))
            try:
                self.stderr.write(f"neomodel.DATABASE_URL = {neomodel_config.DATABASE_URL}")
            except Exception:
                pass
            # tenta extrair host/port da URL para dar dica
            try:
                # ex: bolt://user:pass@host:7687
                parts = neomodel_config.DATABASE_URL.split('@')[-1]
                hostport = parts.split('//')[-1]
                self.stderr.write(self.style.ERROR(f"Resolved host/port segment: {hostport}"))
            except Exception:
                pass
            self.stderr.write(self.style.ERROR(str(e)))
            self.stderr.write(self.style.ERROR("Check NEO4J_URL/NEO4J_USER/NEO4J_PASSWORD environment variables and that Neo4j is reachable from this container/host."))
            # print stack for more context
            traceback.print_exc()
            return
        # Sincroniza Digital Twins e Propriedades
        with db.transaction:
            for system_context in DjangoSystemContext.objects.filter(pk=2):
                # Cria ou obtém o SystemContext
                system = Neo4jSystemContext.nodes.get_or_none(system_id=system_context.id, name=system_context.name)
                if not system:
                    system = Neo4jSystemContext(system_id=system_context.id, name=system_context.name, description=system_context.description)
                system.save()
                self.stdout.write(self.style.SUCCESS(f"Synced SystemContext: {system.name}"))
                for twin_instance in DigitalTwinInstance.objects.filter(model__system=system_context):
                    # Cria ou obtém o Digital Twin
                    digital_twin_name = f'{twin_instance.model.name} - {twin_instance.id}'
                    twin = DigitalTwin.nodes.get_or_none(name=digital_twin_name)
                    if not twin:
                        twin = DigitalTwin(name=digital_twin_name, dt_id=twin_instance.id, model_name=twin_instance.model.name)
                    twin.description = f"Digital Twin Instance {digital_twin_name}"
                    twin.model_name = twin_instance.model.name  # Atualiza o model_name
                    twin.save()
                    if not system.digital_twins.is_connected(twin):
                        system.digital_twins.connect(twin)
                    self.stdout.write(self.style.SUCCESS(f"Synced Twin: {twin.name}"))

                    # Sincroniza as propriedades
                    for prop in twin_instance.digitaltwininstanceproperty_set.all():
                        # Busca ou cria a propriedade relacionada ao Twin
                        # Busca a propriedade via Cypher Query
                        query = """
                        MATCH (p:TwinProperty)<-[:HAS_PROPERTY]-(t:DigitalTwin)
                        WHERE t.name = $twin_name AND p.name = $property_name
                        RETURN p
                        """
                        results, _ = db.cypher_query(query, {"twin_name": twin.name, "property_name": prop.property.name})

                        # Verifica se a propriedade já existe
                        if results:
                            twin_property = TwinProperty.inflate(results[0][0])
                        else:
                            twin_property = TwinProperty(name=prop.property.name)
                        
                        twin_property.value = str(prop.value)
                        twin_property.property_id = prop.id
                        twin_property.type = prop.property.element_type
                        twin_property.save()

                        # Conecta a propriedade ao Twin sem duplicar
                        if not twin.properties.is_connected(twin_property):
                            twin.properties.connect(twin_property)

                        self.stdout.write(f" - Synced Property: {twin_property.name} = {twin_property.value}")
                    
                # Sincroniza os relacionamentos
                for twin_instance in DigitalTwinInstance.objects.filter(model__system=system_context):
                    for relationship in twin_instance.source_relationships.all():
                        dtsourcename = f'{relationship.source_instance.model.name} - {relationship.source_instance.id}'
                        dttargetname = f'{relationship.target_instance.model.name} - {relationship.target_instance.id}'
                        source_twin = DigitalTwin.nodes.get_or_none(name=dtsourcename)
                        target_twin = DigitalTwin.nodes.get_or_none(name=dttargetname)
                        if source_twin and target_twin:
                            # Verifica se ambos os twins pertencem ao mesmo sistema
                            if source_twin.system.single().name == system_context.name and target_twin.system.single().name == system_context.name:
                                if not source_twin.relationships.is_connected(target_twin):
                                    source_twin.relationships.connect(target_twin, {'relationship': relationship.relationship.name})
                                    self.stdout.write(f" - Synced Relationship: {source_twin.name} -> {target_twin.name}")
        self.stdout.write(self.style.SUCCESS("Synchronization completed successfully!"))

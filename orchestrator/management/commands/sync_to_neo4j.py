from django.core.management.base import BaseCommand
from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty, DigitalTwinInstanceRelationship, SystemContext as DjangoSystemContext
from orchestrator.neo4jmodels import DigitalTwin, TwinProperty, SystemContext as Neo4jSystemContext
from neomodel import db

class Command(BaseCommand):
    help = "Synchronize Digital Twins and their properties from PostgreSQL to Neo4j"

    def handle(self, *args, **options):
        self.stdout.write("Starting synchronization...")

        # Apaga todos os nós e relacionamentos do Neo4j
        self.stdout.write("Clearing all nodes and relationships from Neo4j...")
        with db.transaction:
            db.cypher_query("MATCH (n) DETACH DELETE n")
            self.stdout.write(self.style.WARNING("All nodes and relationships have been deleted."))
        # Sincroniza Digital Twins e Propriedades
        with db.transaction:
            for system_context in DjangoSystemContext.objects.all():
                # Cria ou obtém o SystemContext
                system = Neo4jSystemContext.nodes.get_or_none(name=system_context.name)
                if not system:
                    system = Neo4jSystemContext(name=system_context.name, description=system_context.description)
                system.save()
                self.stdout.write(self.style.SUCCESS(f"Synced SystemContext: {system.name}"))
                for twin_instance in DigitalTwinInstance.objects.filter(model__system=system_context):
                    # Cria ou obtém o Digital Twin
                    twin = DigitalTwin.nodes.get_or_none(name=twin_instance.model.name)
                    if not twin:
                        twin = DigitalTwin(name=twin_instance.model.name)
                    twin.description = f"Digital Twin Instance {twin_instance.id}"
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
                        twin_property.type = prop.property.element_type
                        twin_property.save()

                        # Conecta a propriedade ao Twin sem duplicar
                        if not twin.properties.is_connected(twin_property):
                            twin.properties.connect(twin_property)

                        self.stdout.write(f" - Synced Property: {twin_property.name} = {twin_property.value}")
                    
                # Sincroniza os relacionamentos
                for twin_instance in DigitalTwinInstance.objects.filter(model__system=system_context):
                    for relationship in twin_instance.source_relationships.all():
                        source_twin = DigitalTwin.nodes.get_or_none(name=relationship.source_instance.model.name)
                        target_twin = DigitalTwin.nodes.get_or_none(name=relationship.target_instance.model.name)
                        if source_twin and target_twin:
                            if not source_twin.relationships.is_connected(target_twin):
                                source_twin.relationships.connect(target_twin, {'relationship': relationship.relationship.name})
                                self.stdout.write(f" - Synced Relationship: {source_twin.name} -> {target_twin.name}")
        self.stdout.write(self.style.SUCCESS("Synchronization completed successfully!"))

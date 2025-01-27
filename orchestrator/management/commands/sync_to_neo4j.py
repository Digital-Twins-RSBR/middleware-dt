from django.core.management.base import BaseCommand
from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty, DigitalTwinInstanceRelationship
from orchestrator.neo4jmodels import DigitalTwin, TwinProperty
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
            for twin_instance in DigitalTwinInstance.objects.all():
                # Cria ou obtém o Digital Twin
                twin = DigitalTwin.nodes.get_or_none(name=twin_instance.model.name)
                if not twin:
                    twin = DigitalTwin(name=twin_instance.model.name)
                twin.description = f"Digital Twin Instance {twin_instance.id}"
                twin.save()
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
                # Sincroniza os relacionamentos
                for relationship in twin_instance.source_relationships.all():
                    target_twin = DigitalTwin.nodes.get_or_none(name=relationship.target_instance.model.name)
                    if target_twin:
                        twin.relationships.connect(target_twin, {'relationship': relationship.relationship.name})
                        self.stdout.write(f" - Synced Relationship: {twin.name} -> {target_twin.name}")
        self.stdout.write(self.style.SUCCESS("Synchronization completed successfully!"))

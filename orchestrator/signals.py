from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from orchestrator.models import DigitalTwinInstanceProperty, DigitalTwinInstanceRelationship
from orchestrator.neo4jmodels import DigitalTwin, TwinProperty, SystemContext as Neo4jSystemContext
from neomodel import db


### CREATE/UPDATE SIGNAL ###
@receiver(post_save, sender=DigitalTwinInstanceProperty)
def sync_property_to_neo4j(sender, instance, created, **kwargs):
    with db.transaction:
        system = Neo4jSystemContext.nodes.get_or_none(name=instance.dtinstance.model.system.name)
        if not system:
            system = Neo4jSystemContext(name=instance.dtinstance.model.system.name, description=instance.dtinstance.model.system.description)
            system.save()
        # Busca ou cria o Digital Twin
        twin = DigitalTwin.nodes.get_or_none(name=instance.dtinstance.model.name)
        if not twin:
            twin = DigitalTwin(name=instance.dtinstance.model.name)
            twin.description = f"Digital Twin Instance {instance.dtinstance.id}"
            twin.save()
        if not twin.is_connected(system):
            system.digital_twins.connect(twin)

        # Busca a propriedade via Cypher Query
        query = """
        MATCH (p:TwinProperty)<-[:HAS_PROPERTY]-(t:DigitalTwin)
        WHERE t.name = $twin_name AND p.name = $property_name
        RETURN p
        """
        results, _ = db.cypher_query(query, {
            "twin_name": twin.name,
            "property_name": instance.property.name
        })

        # Se existe, recupera; senão, cria uma nova propriedade
        if results:
            twin_property = TwinProperty.inflate(results[0][0])
        else:
            twin_property = TwinProperty(name=instance.property.name)

        # Atualiza os valores da propriedade
        twin_property.value = str(instance.value)
        twin_property.type = instance.property.element_type
        twin_property.save()

        # Conecta a propriedade ao Twin
        if not twin.properties.is_connected(twin_property):
            twin.properties.connect(twin_property)

        print(f"Synced Property: {twin_property.name} with value {twin_property.value}")


@receiver(post_save, sender=DigitalTwinInstanceRelationship)
def sync_relationship_to_neo4j(sender, instance, created, **kwargs):
    with db.transaction:
        # Busca ou cria o SystemContext
        system = Neo4jSystemContext.nodes.get_or_none(name=instance.source_instance.model.system.name)
        if not system:
            system = Neo4jSystemContext(name=instance.source_instance.model.system.name, description=instance.source_instance.model.system.description)
            system.save()
        # Busca ou cria o Digital Twin de origem
        source_twin = DigitalTwin.nodes.get_or_none(name=instance.source_instance.model.name)
        if not source_twin:
            source_twin = DigitalTwin(name=instance.source_instance.model.name)
            source_twin.description = f"Digital Twin Instance {instance.source_instance.id}"
            source_twin.save()
        if not source_twin.system.is_connected(system):
            system.digital_twins.connect(source_twin)

        # Busca ou cria o Digital Twin de destino
        target_twin = DigitalTwin.nodes.get_or_none(name=instance.target_instance.model.name)
        if not target_twin:
            target_twin = DigitalTwin(name=instance.target_instance.model.name)
            target_twin.description = f"Digital Twin Instance {instance.target_instance.id}"
            target_twin.save()
        if not target_twin.system.is_connected(system):
            system.digital_twins.connect(target_twin)
           
        # Conecta os Digital Twins com o relacionamento
        if not source_twin.relationships.is_connected(target_twin):
            source_twin.relationships.connect(target_twin, {'relationship': instance.relationship.name})

### DELETE SIGNAL ###
@receiver(post_delete, sender=DigitalTwinInstanceProperty)
def delete_property_from_neo4j(sender, instance, **kwargs):
    with db.transaction:
        # Busca o Digital Twin associado
        twin = DigitalTwin.nodes.get_or_none(name=instance.dtinstance.model.name)
        if not twin:
            print(f"No DigitalTwin found for {instance.dtinstance.model.name}. Skipping delete.")
            return

        # Busca a propriedade via Cypher Query
        query = """
        MATCH (p:TwinProperty)<-[:HAS_PROPERTY]-(t:DigitalTwin)
        WHERE t.name = $twin_name AND p.name = $property_name
        RETURN p
        """
        results, _ = db.cypher_query(query, {
            "twin_name": twin.name,
            "property_name": instance.property.name
        })

        # Se a propriedade existe, desconecta e deleta
        if results:
            twin_property = TwinProperty.inflate(results[0][0])
            twin.properties.disconnect(twin_property)
            twin_property.delete()
            print(f"Deleted Property: {twin_property.name}")


@receiver(post_delete, sender=DigitalTwinInstanceRelationship)
def delete_relationship_from_neo4j(sender, instance, **kwargs):
    with db.transaction:
        # Busca o Digital Twin de origem
        source_twin = DigitalTwin.nodes.get_or_none(name=instance.source_instance.model.name)
        if not source_twin:
            print(f"No source DigitalTwin found for {instance.source_instance.model.name}. Skipping delete.")
            return

        # Busca o Digital Twin de destino
        target_twin = DigitalTwin.nodes.get_or_none(name=instance.target_instance.model.name)
        if not target_twin:
            print(f"No target DigitalTwin found for {instance.target_instance.model.name}. Skipping delete.")
            return

        # Desconecta os Digital Twins
        if source_twin.relationships.is_connected(target_twin):
            source_twin.relationships.disconnect(target_twin)
            print(f"Deleted Relationship: {source_twin.name} -> {target_twin.name}")

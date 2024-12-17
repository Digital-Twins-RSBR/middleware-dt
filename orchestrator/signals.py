from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from orchestrator.models import DigitalTwinInstanceProperty
from orchestrator.neo4jmodels import DigitalTwin, TwinProperty
from neomodel import db

### CREATE/UPDATE SIGNAL ###
@receiver(post_save, sender=DigitalTwinInstanceProperty)
def sync_property_to_neo4j(sender, instance, created, **kwargs):
    with db.transaction:
        # Busca ou cria o Digital Twin
        twin = DigitalTwin.nodes.get_or_none(name=instance.dtinstance.model.name)
        if not twin:
            twin = DigitalTwin(name=instance.dtinstance.model.name)
            twin.description = f"Digital Twin Instance {instance.dtinstance.id}"
            twin.save()

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

from neomodel import StructuredNode, StringProperty, IntegerProperty, RelationshipTo, RelationshipFrom, StructuredRel

class SystemContext(StructuredNode):
    name = StringProperty(unique_index=True)
    description = StringProperty()
    system_id = IntegerProperty(unique_index=True)

    # Relacionamento: SystemContext contém vários DigitalTwins
    digital_twins = RelationshipTo("DigitalTwin", "CONTAINS")

class TwinProperty(StructuredNode):
    name = StringProperty()
    value = StringProperty()
    type = StringProperty()
    property_id = IntegerProperty()

    # Relacionamento reverso: Um TwinProperty pertence a um DigitalTwin
    twin = RelationshipFrom("DigitalTwin", "HAS_PROPERTY")

class RelationshipModel(StructuredRel):
    relationship = StringProperty()

class DigitalTwin(StructuredNode):
    name = StringProperty(unique_index=True)
    description = StringProperty()
    dt_id = IntegerProperty(unique_index=True)  # Garante unicidade dentro do sistema
    model_name = StringProperty()

    # Relacionamento: DigitalTwin possui várias propriedades
    properties = RelationshipTo("TwinProperty", "HAS_PROPERTY")
    # Relacionamento: DigitalTwin se relaciona com outros DigitalTwins dentro do mesmo `SystemContext`
    relationships = RelationshipTo("DigitalTwin", "HAS_RELATIONSHIP", model=RelationshipModel)
    # Relacionamento: DigitalTwin pertence a um SystemContextAdicionamos
    system = RelationshipFrom("SystemContext", "CONTAINS")

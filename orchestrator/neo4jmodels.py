from neomodel import StructuredNode, StringProperty, IntegerProperty, RelationshipTo, RelationshipFrom, StructuredRel


class SystemContext(StructuredNode):
    name = StringProperty(unique_index=True)
    description = StringProperty()
    system_id = IntegerProperty()

    # Relacionamento: SystemContext possui vários DigitalTwins
    digital_twins = RelationshipTo("DigitalTwin", "CONTAINS")

class TwinProperty(StructuredNode):
    name = StringProperty()
    value = StringProperty()
    type = StringProperty()
    property_id = IntegerProperty()  # Adiciona o campo property_id

    # Relacionamento reverso: Um TwinProperty pertence a um DigitalTwin
    twin = RelationshipFrom("DigitalTwin", "HAS_PROPERTY")

class RelationshipModel(StructuredRel):
    relationship = StringProperty()

class DigitalTwin(StructuredNode):
    name = StringProperty(unique_index=True)
    description = StringProperty()
    dt_id = IntegerProperty()  # Adiciona o campo dt_id
    model_name = StringProperty()  # Adiciona o campo model_name
    
    # Relacionamento: DigitalTwin possui várias propriedades
    properties = RelationshipTo("TwinProperty", "HAS_PROPERTY")
    # Relacionamento: DigitalTwin possui relacionamentos com outros DigitalTwins
    relationships = RelationshipTo("DigitalTwin", "HAS_RELATIONSHIP", model=RelationshipModel)
    # Relacionamento: DigitalTwin pertence a um SystemContext
    system = RelationshipFrom("SystemContext", "CONTAINS")

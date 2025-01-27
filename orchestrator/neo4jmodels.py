from neomodel import StructuredNode, StringProperty, RelationshipTo, RelationshipFrom, StructuredRel


class TwinProperty(StructuredNode):
    name = StringProperty()
    value = StringProperty()
    type = StringProperty()

    # Relacionamento reverso: Um TwinProperty pertence a um DigitalTwin
    twin = RelationshipFrom("DigitalTwin", "HAS_PROPERTY")

class RelationshipModel(StructuredRel):
    relationship = StringProperty()

class DigitalTwin(StructuredNode):
    name = StringProperty(unique_index=True)
    description = StringProperty()
    
    # Relacionamento: DigitalTwin possui várias propriedades
    properties = RelationshipTo("TwinProperty", "HAS_PROPERTY")
    # Relacionamento: DigitalTwin possui relacionamentos com outros DigitalTwins
    relationships = RelationshipTo("DigitalTwin", "HAS_RELATIONSHIP", model=RelationshipModel)

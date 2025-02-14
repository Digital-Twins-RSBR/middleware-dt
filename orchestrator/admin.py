import json
import requests
from django.contrib import admin
from django.urls import path
from orchestrator.forms import DigitalTwinInstanceAdminForm, DigitalTwinInstancePropertyAdminForm, DigitalTwinInstancePropertyInlineForm, DigitalTwinInstanceRelationshipInlineForm
from core.models import DTDLParserClient
from .models import DigitalTwinInstanceRelationship, SystemContext, DTDLModel, DigitalTwinInstance, DigitalTwinInstanceProperty, ModelElement, ModelRelationship


@admin.register(SystemContext)
class SystemContextAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    

class ModelElementInline(admin.TabularInline):
    model = ModelElement
    extra = 1

class ModelRelationshipInline(admin.TabularInline):
    model = ModelRelationship
    extra = 1

@admin.register(DTDLModel)
class DTDLModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'specification', 'parsed_specification')
    inlines = [ModelElementInline, ModelRelationshipInline]
    actions = ['send_specification_to_parser', 'reload_dtdl_specification']

    def send_specification_to_parser(self, request, queryset):
        for obj in queryset:
            specification = obj.specification
            try:
                # Parse the specification JSON to extract the ID
                spec_id = specification.get('@id')

                if not spec_id:
                    self.message_user(request, f"Model {obj.name} has no '@id' in its specification.", level='error')
                    continue

                # Construct the payload
                payload = {
                    "id": spec_id,
                    "specification": specification
                }
                # Send the POST request to the parser_client's URL
                parser_client = DTDLParserClient.get_active()
                parser_url = parser_client.url
                response = requests.post(parser_url, json=payload)

                if response.status_code in [200, 201]:
                    DTDLModel.create_dtdl_model_parsed_from_json(obj, response.json())
                    self.message_user(request, f"Specification sent successfully for model {obj.name}.")
                else:
                    self.message_user(request, f"{response.text}. Status code: {response.status_code}", level='error')

            except json.JSONDecodeError:
                self.message_user(request, f"Model {obj.name} has invalid JSON in specification.", level='error')

    send_specification_to_parser.short_description = "Send specification to parser client"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('send_specification/', self.admin_site.admin_view(self.send_specification_to_parser))
        ]
        return custom_urls + urls

@admin.register(ModelElement)
class ModelElementAdmin(admin.ModelAdmin):
    list_display = ('dtdl_model', 'element_id', 'element_type', 'name', 'schema', 'supplement_types')

@admin.register(ModelRelationship)
class ModelRelationshipAdmin(admin.ModelAdmin):
    list_display = ('dtdl_model', 'relationship_id', 'name', 'source', 'target')

class DigitalTwinInstancePropertyInline(admin.TabularInline):
    form = DigitalTwinInstancePropertyInlineForm
    model = DigitalTwinInstanceProperty
    extra = 1

class DigitalTwinInstanceRelationshipInline(admin.TabularInline):
    form = DigitalTwinInstanceRelationshipInlineForm
    fk_name = 'source_instance'
    model = DigitalTwinInstanceRelationship
    extra = 1

@admin.register(DigitalTwinInstance)
class DigitalTwinInstanceAdmin(admin.ModelAdmin):
    form = DigitalTwinInstanceAdminForm
    inlines = [DigitalTwinInstancePropertyInline, DigitalTwinInstanceRelationshipInline]

@admin.register(DigitalTwinInstanceProperty)
class DigitalTwinInstancePropertyAdmin(admin.ModelAdmin):
    list_display = ('property', 'get_causal', 'value', 'device_property')
    form = DigitalTwinInstancePropertyAdminForm

    def get_causal(request, obj):
        return obj.causal()
    
    get_causal.short_description = 'Causal'
    
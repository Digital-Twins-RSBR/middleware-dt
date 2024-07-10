import json
import requests
from django.contrib import admin
from django.urls import path
from orchestrator.forms import DigitalTwinInstanceAdminForm, DigitalTwinInstancePropertyAdminForm
from .models import DTDLModel, DTDLModelParsed, DigitalTwinInstance, DigitalTwinInstanceProperty, ModelElement, ModelRelationship, ParserClient


@admin.register(ParserClient)
class ParserClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'url')

@admin.register(DTDLModel)
class DTDLModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'specification', 'parser_client')
    actions = ['send_specification_to_parser']

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
                parser_url = obj.parser_client.url
                response = requests.post(parser_url, json=payload)

                if response.status_code in [200, 201]:
                    DTDLModel.create_dtdl_model_parsed(response.json())
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

class ModelElementInline(admin.TabularInline):
    model = ModelElement
    extra = 1

class ModelRelationshipInline(admin.TabularInline):
    model = ModelRelationship
    extra = 1


@admin.register(DTDLModelParsed)
class DTDLModelParsedAdmin(admin.ModelAdmin):
    list_display = ('dtdl_id', 'name', 'specification')
    inlines = [ModelElementInline, ModelRelationshipInline]

    actions = ['reload_dtdl_specification']
    def reload_dtdl_specification(self, request, queryset):
        for obj in queryset:
            obj.reload_model_parsed()
            self.message_user(request, f"Specification reload successfully for model {obj.name}.")
    reload_dtdl_specification.short_description = "Reload specification for parsed model"


class DigitalTwinInstancePropertyInline(admin.TabularInline):
    model = DigitalTwinInstanceProperty
    extra = 1

@admin.register(DigitalTwinInstance)
class DigitalTwinInstanceAdmin(admin.ModelAdmin):
    form = DigitalTwinInstanceAdminForm
    inlines = [DigitalTwinInstancePropertyInline,]

@admin.register(DigitalTwinInstanceProperty)
class DigitalTwinInstancePropertyAdmin(admin.ModelAdmin):
    list_display = ('property', 'causal', 'schema', 'value', 'device_property')
    form = DigitalTwinInstancePropertyAdminForm
    
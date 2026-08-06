import json
import requests
from django.contrib import admin
from django.urls import path
from core.models import Organization
from orchestrator.forms import DigitalTwinInstanceAdminForm, DigitalTwinInstancePropertyAdminForm, DigitalTwinInstancePropertyInlineForm, DigitalTwinInstanceRelationshipInlineForm
from core.parser_client import get_dtdl_parser_url
from .models import DigitalTwinInstanceRelationship, SystemContext, DTDLModel, DigitalTwinInstance, DigitalTwinInstanceProperty, ModelElement, ModelRelationship


def _filter_system_queryset(queryset, request, field_name='organization'):
    user = getattr(request, 'user', None)
    if getattr(user, 'is_superuser', False):
        return queryset
    if not user or not getattr(user, 'is_authenticated', False):
        return queryset.none()
    lookup = f'{field_name}__memberships__user' if field_name else 'organization__memberships__user'
    return queryset.filter(**{lookup: user}).distinct()


def _single_user_organization(request):
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'is_superuser', False):
        return None
    qs = Organization.objects.filter(memberships__user=user).distinct()
    return qs.first() if qs.count() == 1 else None


@admin.register(SystemContext)
class SystemContextAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'created_by', 'description')
    exclude = ('created_by',)

    def get_queryset(self, request):
        return _filter_system_queryset(super().get_queryset(request), request)

    def save_model(self, request, obj, form, change):
        if not obj.organization_id:
            obj.organization = _single_user_organization(request)
        if not obj.created_by_id:
            obj.created_by = getattr(request, 'user', None)
        super().save_model(request, obj, form, change)
    

class ModelElementInline(admin.TabularInline):
    model = ModelElement
    extra = 1

class ModelRelationshipInline(admin.TabularInline):
    model = ModelRelationship
    extra = 1

@admin.register(DTDLModel)
class DTDLModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'system', 'created_by', 'specification', 'parsed_specification')
    list_filter = ('system',)
    inlines = [ModelElementInline, ModelRelationshipInline]
    actions = ['send_specification_to_parser', 'reload_dtdl_specification']
    exclude = ('created_by',)

    def get_queryset(self, request):
        return _filter_system_queryset(super().get_queryset(request), request, field_name='system__organization')

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = getattr(request, 'user', None)
        super().save_model(request, obj, form, change)

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
                # Send the POST request to the internal parser service.
                parser_url = get_dtdl_parser_url()
                response = requests.post(parser_url, json=payload)
                
                if response.status_code in [200, 201]:
                    obj.parsed_specification = response.json()
                    obj.save()
                    self.message_user(request, f"Specification sent successfully for model {obj.name}.")
                else:
                    self.message_user(request, f"{response.text}. Status code: {response.status_code}", level='error')

            except json.JSONDecodeError:
                self.message_user(request, f"Model {obj.name} has invalid JSON in specification.", level='error')

    send_specification_to_parser.short_description = "Send specification to parser service"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('send_specification/', self.admin_site.admin_view(self.send_specification_to_parser))
        ]
        return custom_urls + urls

@admin.register(ModelElement)
class ModelElementAdmin(admin.ModelAdmin):
    list_display = ('dtdl_model', 'element_id', 'element_type', 'name', 'schema', 'supplement_types')
    list_filter = ('dtdl_model__system', 'dtdl_model', 'element_type')

    def get_queryset(self, request):
        return _filter_system_queryset(super().get_queryset(request), request, field_name='dtdl_model__system__organization')

@admin.register(ModelRelationship)
class ModelRelationshipAdmin(admin.ModelAdmin):
    list_display = ('dtdl_model', 'relationship_id', 'name', 'source', 'target')
    list_filter = ('dtdl_model__system', 'dtdl_model')

    def get_queryset(self, request):
        return _filter_system_queryset(super().get_queryset(request), request, field_name='dtdl_model__system__organization')

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
    list_filter = ('model__system', 'model', 'active')
    list_display = ('name', 'id', 'model', 'active', 'last_status_check')
    form = DigitalTwinInstanceAdminForm
    inlines = [DigitalTwinInstancePropertyInline, DigitalTwinInstanceRelationshipInline]

    def get_queryset(self, request):
        return _filter_system_queryset(super().get_queryset(request), request, field_name='model__system__organization')

@admin.register(DigitalTwinInstanceProperty)
class DigitalTwinInstancePropertyAdmin(admin.ModelAdmin):
    list_display = ('property', 'get_causal', 'value', 'device_property', 'dtinstance__active')
    list_filter = ('dtinstance__model__system', 'dtinstance__model')
    form = DigitalTwinInstancePropertyAdminForm

    def get_queryset(self, request):
        return _filter_system_queryset(super().get_queryset(request), request, field_name='dtinstance__model__system__organization')

    def get_causal(request, obj):
        return obj.causal()
    
    get_causal.short_description = 'Causal'

@admin.register(DigitalTwinInstanceRelationship)
class DigitalTwinInstanceRelationshipAdmin(admin.ModelAdmin):
    list_display = ('source_instance', 'relationship', 'target_instance')
    list_filter = ('source_instance__model__system', 'source_instance__model', 'relationship', 'target_instance__model__system', 'target_instance__model')

    def get_queryset(self, request):
        return _filter_system_queryset(super().get_queryset(request), request, field_name='source_instance__model__system__organization')
    
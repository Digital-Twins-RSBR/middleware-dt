# facade/admin.py
from django.contrib import admin

from core.models import GatewayIOT
from .models import Device, DeviceType, Property


def _filter_by_user_organizations(queryset, request, field_name='organization'):
    user = getattr(request, 'user', None)
    if getattr(user, 'is_superuser', False):
        return queryset
    if not user or not getattr(user, 'is_authenticated', False):
        return queryset.none()
    return queryset.filter(**{f'{field_name}__memberships__user': user}).distinct()


def _single_user_organization(request):
    user = getattr(request, 'user', None)
    if not user or not getattr(user, 'is_authenticated', False) or getattr(user, 'is_superuser', False):
        return None
    from core.models import Organization
    qs = Organization.objects.filter(memberships__user=user).distinct()
    return qs.first() if qs.count() == 1 else None

@admin.register(DeviceType)
class DeviceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'created_by')
    list_filter = ('organization',)
    search_fields = ('name', 'organization__name')
    exclude = ('created_by',)

    def get_queryset(self, request):
        return _filter_by_user_organizations(super().get_queryset(request), request)

    def save_model(self, request, obj, form, change):
        if not obj.organization_id:
            obj.organization = _single_user_organization(request)
        if not obj.created_by_id:
            obj.created_by = getattr(request, 'user', None)
        super().save_model(request, obj, form, change)

class PropertyInline(admin.TabularInline):
    model = Property
    extra = 1
    readonly_fields = ('value',)
    
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'identifier', 'status', 'type', 'organization', 'created_by', 'metadata', 'gateway', 'user')
    list_filter = ('organization', 'type', 'gateway')
    search_fields = ('name', 'identifier', 'metadata', 'organization__name')
    inlines = [PropertyInline,]
    exclude = ('created_by',)

    def get_queryset(self, request):
        return _filter_by_user_organizations(super().get_queryset(request), request)

    def save_model(self, request, obj, form, change):
        if obj.gateway_id and not obj.organization_id:
            obj.organization = obj.gateway.organization
        elif not obj.organization_id:
            obj.organization = _single_user_organization(request)
        if not obj.created_by_id:
            obj.created_by = getattr(request, 'user', None)
        super().save_model(request, obj, form, change)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('device', 'name', 'type', 'value')
    readonly_fields=('value',)

    def get_queryset(self, request):
        return _filter_by_user_organizations(super().get_queryset(request), request, field_name='device__organization')


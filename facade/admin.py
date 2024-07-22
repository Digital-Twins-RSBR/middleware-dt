# facade/admin.py
from django.contrib import admin

from core.models import GatewayIOT
from .models import Device, DeviceType, Property

@admin.register(DeviceType)
class DeviceTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)

class PropertyInline(admin.TabularInline):
    model = Property
    extra = 1
    readonly_fields = ('value',)
    
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'identifier', 'status', 'type', 'gateway', 'user')
    list_filter = ('type', 'gateway')
    inlines = [PropertyInline,]


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('device', 'name', 'type', 'value')
    readonly_fields=('value',)


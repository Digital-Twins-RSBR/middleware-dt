# facade/admin.py
from django.contrib import admin

from .models import Device, DeviceType, GatewayIOT, Property

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


@admin.register(GatewayIOT)
class GatewayAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'username', 'user')

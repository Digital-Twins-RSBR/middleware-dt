# facade/admin.py
from django.contrib import admin

from .models import Device, DeviceType, GatewayIOT, Property

@admin.register(DeviceType)
class DeviceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'rpc_methods')

class PropertyInline(admin.TabularInline):
    model = Property
    extra = 1
    
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('name', 'identifier', 'status', 'type', 'gateway', 'user')
    inlines = [PropertyInline,]


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('device', 'name', 'type', 'causal')


@admin.register(GatewayIOT)
class GatewayAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'username', 'user')

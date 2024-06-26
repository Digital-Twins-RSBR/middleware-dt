# facade/admin.py
from django.contrib import admin

from .models import Device, DeviceType, GatewayIOT

@admin.register(DeviceType)
class DeviceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'rpc_methods')

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('device_id', 'name', 'identifier', 'status', 'type', 'gateway', 'user')

@admin.register(GatewayIOT)
class GatewayAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'username', 'user')

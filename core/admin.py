from django.contrib import admin
from django.urls import path
from .models import GatewayIOT, DTDLParserClient


@admin.register(DTDLParserClient)
class DTDLParserClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'url')

@admin.register(GatewayIOT)
class GatewayAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'username')
from django.contrib import admin
from django.shortcuts import redirect, render

from facade.models import Device
from orchestrator.forms import DigitalTwinInstanceAdminForm, DigitalTwinInstancePropertyAdminForm
from .models import DTDLModel, DigitalTwinInstance, DigitalTwinInstanceProperty, ModelElement, ModelRelationship

class ModelElementInline(admin.TabularInline):
    model = ModelElement
    extra = 1

class ModelRelationshipInline(admin.TabularInline):
    model = ModelRelationship
    extra = 1


@admin.register(DTDLModel)
class DTDLModelAdmin(admin.ModelAdmin):
    inlines = [ModelElementInline, ModelRelationshipInline]


class DigitalTwinInstancePropertyInline(admin.TabularInline):
    model = DigitalTwinInstanceProperty
    extra = 1

@admin.register(DigitalTwinInstance)
class DigitalTwinInstanceAdmin(admin.ModelAdmin):
    form = DigitalTwinInstanceAdminForm
    inlines = [DigitalTwinInstancePropertyInline,]

@admin.register(DigitalTwinInstanceProperty)
class DigitalTwinInstancePropertyAdmin(admin.ModelAdmin):
    form = DigitalTwinInstancePropertyAdminForm
    
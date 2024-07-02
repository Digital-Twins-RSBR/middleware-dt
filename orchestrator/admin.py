from django.contrib import admin
from .models import DTDLModel, ModelElement, ModelRelationship

class ModelElementInline(admin.TabularInline):
    model = ModelElement
    extra = 1

class ModelRelationshipInline(admin.TabularInline):
    model = ModelRelationship
    extra = 1

@admin.register(DTDLModel)
class DTDLModelAdmin(admin.ModelAdmin):
    inlines = [ModelElementInline, ModelRelationshipInline]



from django import forms

from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty


class DigitalTwinInstanceAdminForm(forms.ModelForm):
    class Meta:
        model = DigitalTwinInstance
        fields = ['model', 'device',]

class DigitalTwinInstancePropertyAdminForm(forms.ModelForm):
    class Meta:
        model = DigitalTwinInstanceProperty
        fields = ['dtinstance', 'property', 'device_property', 'value']
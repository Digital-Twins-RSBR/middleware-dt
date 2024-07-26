

from django import forms

from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty


class DigitalTwinInstanceAdminForm(forms.ModelForm):
    class Meta:
        model = DigitalTwinInstance
        fields = ['model',]

class DigitalTwinInstancePropertyAdminForm(forms.ModelForm):
    class Meta:
        model = DigitalTwinInstanceProperty
        fields = ['dtinstance', 'property', 'device_property', 'value']

class DigitalTwinInstancePropertyInlineForm(forms.ModelForm):

    class Meta:
        model = DigitalTwinInstanceProperty
        fields = ['dtinstance', 'property', 'device_property', 'value']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['device_property'].required = False


from django import forms

from orchestrator.models import DigitalTwinInstance, DigitalTwinInstanceProperty, DigitalTwinInstanceRelationship


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


class DigitalTwinInstanceRelationshipInlineForm(forms.ModelForm):

    class Meta:
        model = DigitalTwinInstanceRelationship
        fields = ['source_instance', 'target_instance', 'relationship',]

    def save(self, commit=True):
        instance = super().save(commit=False)
        if DigitalTwinInstanceRelationship.objects.filter(
            source_instance=instance.source_instance,
            target_instance=instance.target_instance,
            relationship=instance.relationship
        ).exists():
            # Atualiza o relacionamento existente
            existing_instance = DigitalTwinInstanceRelationship.objects.get(
                source_instance=instance.source_instance,
                target_instance=instance.target_instance,
                relationship=instance.relationship
            )
            instance.id = existing_instance.id
        if commit:
            instance.save()
        return instance

from django.conf import settings
from django.db import migrations


def create_default_organization(apps, schema_editor):
    Organization = apps.get_model('core', 'Organization')
    OrganizationMembership = apps.get_model('core', 'OrganizationMembership')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))

    organization, _ = Organization.objects.get_or_create(
        name='Default',
        defaults={'description': 'Default organization created during bootstrap'},
    )

    user = User.objects.filter(username='middts').first()
    if user is None:
        user = User.objects.filter(is_superuser=True).order_by('id').first()
    if user is None:
        return

    OrganizationMembership.objects.get_or_create(
        user=user,
        organization=organization,
        defaults={'role': 'admin'},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_organizationmembership_organization_gatewayiot_organization'),
    ]

    operations = [
        migrations.RunPython(create_default_organization, noop_reverse),
    ]
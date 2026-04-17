from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_device_org_and_created_by(apps, schema_editor):
    Device = apps.get_model('facade', 'Device')
    DeviceType = apps.get_model('facade', 'DeviceType')

    for device in Device.objects.filter(organization__isnull=True).select_related('gateway'):
        if device.gateway_id and getattr(device.gateway, 'organization_id', None):
            device.organization = device.gateway.organization
            device.save(update_fields=['organization'])

    for device in Device.objects.filter(created_by__isnull=True, user__isnull=False):
        device.created_by = device.user
        device.save(update_fields=['created_by'])

    for device_type in DeviceType.objects.filter(organization__isnull=True):
        sample_device = Device.objects.filter(type=device_type, organization__isnull=False).order_by('id').first()
        if sample_device:
            device_type.organization = sample_device.organization
            device_type.save(update_fields=['organization'])

    for device_type in DeviceType.objects.filter(created_by__isnull=True):
        sample_device = Device.objects.filter(type=device_type, created_by__isnull=False).order_by('id').first()
        if sample_device:
            device_type.created_by = sample_device.created_by
            device_type.save(update_fields=['created_by'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0007_organization_gatewayiot_created_by'),
        ('facade', '0004_devicetype_device_organization'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_devices', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='devicetype',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_device_types', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(backfill_device_org_and_created_by, migrations.RunPython.noop),
    ]
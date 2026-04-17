from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_created_by(apps, schema_editor):
    SystemContext = apps.get_model('orchestrator', 'SystemContext')
    DTDLModel = apps.get_model('orchestrator', 'DTDLModel')
    OrganizationMembership = apps.get_model('core', 'OrganizationMembership')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))

    fallback_user = User.objects.filter(is_superuser=True).order_by('id').first()

    for system in SystemContext.objects.filter(created_by__isnull=True, organization__isnull=False):
        membership = OrganizationMembership.objects.filter(organization=system.organization).order_by('id').first()
        system.created_by = membership.user if membership else fallback_user
        if system.created_by_id:
            system.save(update_fields=['created_by'])

    for model in DTDLModel.objects.filter(created_by__isnull=True, system__created_by__isnull=False):
        model.created_by = model.system.created_by
        model.save(update_fields=['created_by'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0007_organization_gatewayiot_created_by'),
        ('orchestrator', '0008_systemcontext_organization'),
    ]

    operations = [
        migrations.AddField(
            model_name='dtdlmodel',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='systemcontext',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(backfill_created_by, migrations.RunPython.noop),
    ]
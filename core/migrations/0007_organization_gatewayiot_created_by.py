from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_created_by(apps, schema_editor):
    Organization = apps.get_model('core', 'Organization')
    OrganizationMembership = apps.get_model('core', 'OrganizationMembership')
    GatewayIOT = apps.get_model('core', 'GatewayIOT')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))

    fallback_user = User.objects.filter(is_superuser=True).order_by('id').first()

    for organization in Organization.objects.filter(created_by__isnull=True):
        membership = OrganizationMembership.objects.filter(organization=organization).order_by('id').first()
        organization.created_by = membership.user if membership else fallback_user
        if organization.created_by_id:
            organization.save(update_fields=['created_by'])

    for gateway in GatewayIOT.objects.filter(created_by__isnull=True, organization__isnull=False):
        membership = OrganizationMembership.objects.filter(organization=gateway.organization).order_by('id').first()
        gateway.created_by = membership.user if membership else fallback_user
        if gateway.created_by_id:
            gateway.save(update_fields=['created_by'])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0006_default_organization_membership'),
    ]

    operations = [
        migrations.AddField(
            model_name='gatewayiot',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='organization',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(backfill_created_by, migrations.RunPython.noop),
    ]
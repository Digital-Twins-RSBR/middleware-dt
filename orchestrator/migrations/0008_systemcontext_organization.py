from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_organizationmembership_organization_gatewayiot_organization'),
        ('orchestrator', '0007_alter_digitaltwininstanceproperty_unique_together'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemcontext',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.organization'),
        ),
    ]
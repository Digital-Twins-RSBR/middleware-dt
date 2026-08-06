from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_organizationmembership_organization_gatewayiot_organization'),
        ('facade', '0003_device_metadata_alter_devicetype_inactivitytimeout'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.organization'),
        ),
        migrations.AddField(
            model_name='devicetype',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='core.organization'),
        ),
    ]
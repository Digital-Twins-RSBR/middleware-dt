from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_gatewayiot_auth_method_api_key'),
    ]

    operations = [
        migrations.DeleteModel(
            name='DTDLParserClient',
        ),
    ]
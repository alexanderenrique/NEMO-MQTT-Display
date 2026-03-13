# Generated manually for server certificate fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("NEMO_mqtt_bridge", "0002_mqttconfiguration_ca_cert_content_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="mqttconfiguration",
            name="server_cert_content",
            field=models.TextField(
                blank=True,
                help_text="Server certificate content (PEM format) - for development broker",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="mqttconfiguration",
            name="server_key_content",
            field=models.TextField(
                blank=True,
                help_text="Server private key content (PEM format) - for development broker",
                null=True,
            ),
        ),
    ]

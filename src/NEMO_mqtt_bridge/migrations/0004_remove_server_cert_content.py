# Generated manually to remove server certificate content fields

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("NEMO_mqtt_bridge", "0003_add_server_certificates"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="mqttconfiguration",
            name="server_cert_content",
        ),
        migrations.RemoveField(
            model_name="mqttconfiguration",
            name="server_key_content",
        ),
    ]

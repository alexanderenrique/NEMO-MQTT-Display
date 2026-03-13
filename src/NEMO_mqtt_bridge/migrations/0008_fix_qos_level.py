# Fix QoS level: fixed at 1 (at least once), not configurable

from django.db import migrations, models


def set_qos_level_to_one(apps, schema_editor):
    MQTTConfiguration = apps.get_model("NEMO_mqtt_bridge", "MQTTConfiguration")
    MQTTConfiguration.objects.all().update(qos_level=1)


class Migration(migrations.Migration):

    dependencies = [
        ("NEMO_mqtt_bridge", "0007_replace_tls_with_hmac"),
    ]

    operations = [
        migrations.RunPython(set_qos_level_to_one, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="mqttconfiguration",
            name="qos_level",
            field=models.IntegerField(
                choices=[(1, "At least once")],
                default=1,
                help_text="Quality of Service level (fixed at 1 for reliable delivery)",
            ),
        ),
    ]

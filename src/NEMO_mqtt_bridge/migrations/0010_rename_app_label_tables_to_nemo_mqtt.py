# With app label NEMO_mqtt_bridge, CreateModel uses default table names
# nemo_mqtt_bridge_*. Models use explicit db_table nemo_mqtt_*.
# AlterModelTable renames physical tables to match model Meta.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("NEMO_mqtt_bridge", "0009_hmac_sha256_only"),
    ]

    operations = [
        migrations.AlterModelTable(
            name="MQTTConfiguration",
            table="nemo_mqtt_mqttconfiguration",
        ),
        migrations.AlterModelTable(
            name="MQTTMessageLog",
            table="nemo_mqtt_mqttmessagelog",
        ),
        migrations.AlterModelTable(
            name="MQTTEventFilter",
            table="nemo_mqtt_mqtteventfilter",
        ),
    ]

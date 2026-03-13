# Generated migration for MQTTEventQueue and MQTTBridgeStatus

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("NEMO_mqtt_bridge", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MQTTEventQueue",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("topic", models.CharField(max_length=500)),
                ("payload", models.TextField()),
                ("qos", models.IntegerField(default=1)),
                ("retain", models.BooleanField(default=False)),
                ("processed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "MQTT Event Queue",
                "verbose_name_plural": "MQTT Event Queues",
                "db_table": "nemo_mqtt_mqtt_eventqueue",
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="MQTTBridgeStatus",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "key",
                    models.CharField(
                        default="default",
                        help_text="Singleton key for bridge status",
                        max_length=20,
                        unique=True,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("connected", "Connected"),
                            ("disconnected", "Disconnected"),
                        ],
                        max_length=20,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "MQTT Bridge Status",
                "verbose_name_plural": "MQTT Bridge Statuses",
                "db_table": "nemo_mqtt_mqttbridgestatus",
            },
        ),
    ]

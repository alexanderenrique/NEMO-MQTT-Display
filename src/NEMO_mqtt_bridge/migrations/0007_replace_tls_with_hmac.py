# Replace TLS/SSL with HMAC message authentication

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("NEMO_mqtt_bridge", "0006_rename_db_tables_to_lowercase"),
    ]

    operations = [
        # Add HMAC fields
        migrations.AddField(
            model_name="mqttconfiguration",
            name="use_hmac",
            field=models.BooleanField(
                default=False,
                help_text="Sign MQTT payloads with HMAC for authenticity and integrity",
            ),
        ),
        migrations.AddField(
            model_name="mqttconfiguration",
            name="hmac_secret_key",
            field=models.CharField(
                blank=True,
                max_length=500,
                null=True,
                help_text="Shared secret key for HMAC signing (keep confidential)",
            ),
        ),
        migrations.AddField(
            model_name="mqttconfiguration",
            name="hmac_algorithm",
            field=models.CharField(
                choices=[
                    ("sha256", "SHA-256"),
                    ("sha384", "SHA-384"),
                    ("sha512", "SHA-512"),
                ],
                default="sha256",
                help_text="Hash algorithm for HMAC",
                max_length=20,
            ),
        ),
        # Remove TLS/SSL fields
        migrations.RemoveField(model_name="mqttconfiguration", name="use_tls"),
        migrations.RemoveField(model_name="mqttconfiguration", name="tls_version"),
        migrations.RemoveField(model_name="mqttconfiguration", name="ca_cert_path"),
        migrations.RemoveField(model_name="mqttconfiguration", name="client_cert_path"),
        migrations.RemoveField(model_name="mqttconfiguration", name="client_key_path"),
        migrations.RemoveField(model_name="mqttconfiguration", name="ca_cert_content"),
        migrations.RemoveField(
            model_name="mqttconfiguration", name="client_cert_content"
        ),
        migrations.RemoveField(
            model_name="mqttconfiguration", name="client_key_content"
        ),
        migrations.RemoveField(model_name="mqttconfiguration", name="insecure"),
    ]

# Generated manually to simplify TLS configuration

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("NEMO_mqtt_bridge", "0004_remove_server_cert_content"),
    ]

    operations = [
        # This migration is intentionally empty
        # The model changes have been made but we don't need to modify the database
        # since we removed the server certificate fields from the model
        migrations.RunSQL(
            "-- No database changes needed - fields were removed from model only",
            reverse_sql="-- No reverse operation needed",
        ),
    ]

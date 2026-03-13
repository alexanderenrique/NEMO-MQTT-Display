# Rename db_tables from NEMO_mqtt_* to nemo_mqtt_* for consistent lowercase naming
# Only renames if old tables exist (existing installs); fresh installs already use nemo_mqtt_*

from django.db import migrations


def _table_exists(connection, table_name):
    """Check if a table exists using Django's introspection"""
    return table_name in connection.introspection.table_names()


def rename_tables_forward(apps, schema_editor):
    """Rename tables from NEMO_mqtt_* to nemo_mqtt_* if they exist"""
    connection = schema_editor.connection
    renames = [
        ("NEMO_mqtt_mqttconfiguration", "nemo_mqtt_mqttconfiguration"),
        ("NEMO_mqtt_mqttmessagelog", "nemo_mqtt_mqttmessagelog"),
        ("NEMO_mqtt_mqtteventfilter", "nemo_mqtt_mqtteventfilter"),
    ]
    with connection.cursor() as cursor:
        for old_name, new_name in renames:
            if _table_exists(connection, old_name) and not _table_exists(
                connection, new_name
            ):
                cursor.execute(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"')


def rename_tables_reverse(apps, schema_editor):
    """Reverse: rename tables back to NEMO_mqtt_* if they exist"""
    connection = schema_editor.connection
    renames = [
        ("nemo_mqtt_mqttconfiguration", "NEMO_mqtt_mqttconfiguration"),
        ("nemo_mqtt_mqttmessagelog", "NEMO_mqtt_mqttmessagelog"),
        ("nemo_mqtt_mqtteventfilter", "NEMO_mqtt_mqtteventfilter"),
    ]
    with connection.cursor() as cursor:
        for old_name, new_name in renames:
            if _table_exists(connection, old_name) and not _table_exists(
                connection, new_name
            ):
                cursor.execute(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"')


class Migration(migrations.Migration):

    dependencies = [
        ("NEMO_mqtt_bridge", "0005_simplify_tls_config"),
    ]

    operations = [
        migrations.RunPython(rename_tables_forward, rename_tables_reverse),
    ]

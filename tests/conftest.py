"""
Pytest configuration for NEMO MQTT Plugin tests.
"""
import os
import sys

import django
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.test_settings')
django.setup()


@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    """Setup test database."""
    with django_db_blocker.unblock():
        from django.core.management import call_command
        call_command('migrate', verbosity=0, interactive=False)


@pytest.fixture
def mqtt_config():
    """Create a test MQTT configuration."""
    from NEMO_mqtt_bridge.models import MQTTConfiguration
    return MQTTConfiguration.objects.create(
        name='Test Config',
        enabled=True,
        broker_host='localhost',
        broker_port=1883,
        qos_level=1,
        retain_messages=False,
    )



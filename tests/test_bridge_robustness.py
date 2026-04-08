"""Tests for bridge publish semantics and Django bridge-run toggle."""
from unittest.mock import MagicMock, patch

import paho.mqtt.client as mqtt
import pytest

from NEMO_mqtt_bridge.apps import should_run_bridge_in_django
from NEMO_mqtt_bridge.models import MQTTEventQueue
from NEMO_mqtt_bridge.postgres_mqtt_bridge import PostgresMQTTBridge


@pytest.fixture
def bridge_no_lock():
    with patch("NEMO_mqtt_bridge.postgres_mqtt_bridge.acquire_lock", return_value=MagicMock()):
        with patch("NEMO_mqtt_bridge.postgres_mqtt_bridge.signal.signal"):
            yield PostgresMQTTBridge(auto_start=False)


def test_should_run_bridge_in_django_default(monkeypatch):
    monkeypatch.delenv("NEMO_MQTT_BRIDGE_RUN_IN_DJANGO", raising=False)
    assert should_run_bridge_in_django() is False


def test_should_run_bridge_in_django_env_off(monkeypatch):
    monkeypatch.setenv("NEMO_MQTT_BRIDGE_RUN_IN_DJANGO", "0")
    assert should_run_bridge_in_django() is False


def test_should_run_bridge_in_django_env_on(monkeypatch):
    monkeypatch.setenv("NEMO_MQTT_BRIDGE_RUN_IN_DJANGO", "1")
    assert should_run_bridge_in_django() is True


def test_publish_to_mqtt_false_when_not_connected(bridge_no_lock):
    bridge_no_lock.mqtt_client = None
    bridge_no_lock.config = None
    assert bridge_no_lock._publish_to_mqtt("t", "{}", 1, False) is False


def test_publish_to_mqtt_true_on_success(bridge_no_lock):
    bridge_no_lock.config = MagicMock(use_hmac=False, hmac_secret_key=None)
    client = MagicMock()
    client.is_connected.return_value = True
    ok = MagicMock()
    ok.rc = mqtt.MQTT_ERR_SUCCESS
    client.publish.return_value = ok
    bridge_no_lock.mqtt_client = client
    assert bridge_no_lock._publish_to_mqtt("topic", '{"x":1}', 1, False) is True
    client.publish.assert_called_once()


def test_publish_to_mqtt_false_on_bad_rc(bridge_no_lock):
    bridge_no_lock.config = MagicMock(use_hmac=False, hmac_secret_key=None)
    client = MagicMock()
    client.is_connected.return_value = True
    bad = MagicMock()
    bad.rc = mqtt.MQTT_ERR_NO_CONN
    client.publish.return_value = bad
    bridge_no_lock.mqtt_client = client
    assert bridge_no_lock._publish_to_mqtt("topic", "{}", 1, False) is False


@pytest.mark.django_db
def test_process_pending_leaves_row_unprocessed_on_publish_failure(bridge_no_lock):
    MQTTEventQueue.objects.create(
        topic="a", payload="{}", qos=1, retain=False, processed=False
    )
    MQTTEventQueue.objects.create(
        topic="b", payload="{}", qos=1, retain=False, processed=False
    )
    bridge_no_lock.config = MagicMock(use_hmac=False, hmac_secret_key=None)
    bridge_no_lock._publish_to_mqtt = MagicMock(return_value=False)
    bridge_no_lock._process_pending_events()
    assert MQTTEventQueue.objects.filter(processed=False).count() == 2


@pytest.mark.django_db
def test_process_pending_marks_rows_after_success(bridge_no_lock):
    MQTTEventQueue.objects.create(
        topic="a", payload="{}", qos=1, retain=False, processed=False
    )
    bridge_no_lock.config = MagicMock(use_hmac=False, hmac_secret_key=None)
    bridge_no_lock._publish_to_mqtt = MagicMock(return_value=True)
    bridge_no_lock._process_pending_events()
    assert MQTTEventQueue.objects.filter(processed=True).count() == 1


@pytest.mark.django_db
def test_invalid_queue_row_marked_processed_without_publish(bridge_no_lock):
    MQTTEventQueue.objects.create(
        topic="", payload="{}", qos=1, retain=False, processed=False
    )
    bridge_no_lock.config = MagicMock(use_hmac=False, hmac_secret_key=None)
    bridge_no_lock._publish_to_mqtt = MagicMock()
    bridge_no_lock._process_pending_events()
    assert MQTTEventQueue.objects.filter(processed=True).count() == 1
    bridge_no_lock._publish_to_mqtt.assert_not_called()

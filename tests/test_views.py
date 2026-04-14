"""
Tests for NEMO MQTT Plugin URLs (bridge status JSON, legacy monitor redirect).
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User

from NEMO_mqtt_bridge.models import MQTTBridgeStatus, MQTTConfiguration
from NEMO_mqtt_bridge.utils import mqtt_bridge_status_payload, update_mqtt_bridge_diagnostics


class MqttBridgeStatusViewTest(TestCase):
    """Bridge status JSON and legacy mqtt_monitor redirect."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
        )
        self.client = Client()
        MQTTConfiguration.objects.create(
            name="Test Config",
            enabled=True,
            broker_host="localhost",
            broker_port=1883,
        )

    def test_mqtt_bridge_status_requires_login(self):
        response = self.client.get("/mqtt/mqtt_bridge_status/")
        self.assertEqual(response.status_code, 302)

    def test_mqtt_bridge_status_json_shape(self):
        self.client.login(username="testuser", password="testpass123")
        MQTTBridgeStatus.objects.update_or_create(
            key="default",
            defaults={"status": "connected"},
        )
        response = self.client.get("/mqtt/mqtt_bridge_status/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "connected")
        self.assertIn("updated_at", data)
        self.assertEqual(data["bridge_status_row_updated_at"], data["updated_at"])
        self.assertIn("last_heartbeat", data)
        self.assertIn("diagnostics", data)
        self.assertIn("bridge_last_reload", data)
        self.assertIn("at", data["bridge_last_reload"])
        self.assertIn("reason", data["bridge_last_reload"])
        self.assertIn("mqtt_configuration", data)
        self.assertIsNotNone(data["mqtt_configuration"])
        self.assertIn("applied_mqtt_configuration", data)
        self.assertIn("queue", data)
        self.assertIn("pending_count", data["queue"])
        self.assertIn("package_version", data)
        self.assertIn("plugin_version", data)
        self.assertEqual(data["package_version"], data["plugin_version"])
        self.assertIsNotNone(data["package_version"])
        self.assertNotIn("applied_config_snapshot", data["diagnostics"])

    def test_mqtt_monitor_redirect_authenticated(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get("/mqtt/mqtt_monitor/", follow=False)
        self.assertEqual(response.status_code, 301)
        self.assertTrue(
            response["Location"].endswith("/mqtt/mqtt_bridge_status/")
        )

    def test_mqtt_monitor_redirect_requires_login(self):
        response = self.client.get("/mqtt/mqtt_monitor/", follow=False)
        self.assertEqual(response.status_code, 302)

    def test_payload_omits_applied_config_snapshot_after_legacy_write(self):
        update_mqtt_bridge_diagnostics(
            {
                "last_reload_reason": "test",
                "applied_config_snapshot": {"id": 1, "broker_host": "secret"},
            }
        )
        payload = mqtt_bridge_status_payload()
        self.assertNotIn("applied_config_snapshot", payload["diagnostics"])

    def test_mqtt_bridge_status_payload_matches_json_view(self):
        self.client.login(username="testuser", password="testpass123")
        update_mqtt_bridge_diagnostics({"last_reload_reason": "notify"})
        from_api = self.client.get("/mqtt/mqtt_bridge_status/").json()
        from_util = mqtt_bridge_status_payload()
        self.assertEqual(from_api.keys(), from_util.keys())
        self.assertEqual(from_api["diagnostics"], from_util["diagnostics"])

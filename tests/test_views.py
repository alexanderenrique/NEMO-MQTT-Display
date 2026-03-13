"""
Tests for NEMO MQTT Plugin views (mqtt_monitor, mqtt_monitor_api).
"""
import json
from unittest.mock import patch

from django.test import TestCase, Client
from django.contrib.auth.models import User

from NEMO_mqtt_bridge.models import MQTTConfiguration


class MQTTMonitorViewTest(TestCase):
    """Test MQTT monitor page and API views"""

    def setUp(self):
        """Set up test data"""
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

    def test_mqtt_monitor_requires_login(self):
        """Test that MQTT monitor page requires login"""
        response = self.client.get("/mqtt/monitor/")
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_mqtt_monitor_authenticated(self):
        """Test MQTT monitor page with authenticated user"""
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get("/mqtt/monitor/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"NEMO MQTT Monitor", response.content)

    def test_mqtt_monitor_api_requires_login(self):
        """Test that MQTT monitor API requires login"""
        response = self.client.get("/mqtt/monitor/api/")
        self.assertEqual(response.status_code, 302)  # Redirect to login

    @patch("NEMO_mqtt_bridge.db_publisher.db_publisher")
    def test_mqtt_monitor_api_returns_messages(self, mock_db_publisher):
        """Test MQTT monitor API returns messages from queue"""
        mock_db_publisher.get_monitor_messages.return_value = [
            {
                "id": 1,
                "timestamp": "2024-01-15T10:30:00Z",
                "source": "PostgreSQL",
                "topic": "nemo/tools/1/start",
                "payload": '{"event": "tool_usage_start"}',
                "qos": 1,
                "retain": False,
            }
        ]
        mock_db_publisher.get_bridge_status.return_value = "connected"

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get("/mqtt/monitor/api/")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["count"], 1)
        self.assertTrue(data["monitoring"])
        self.assertEqual(data["broker_connected"], "connected")
        self.assertEqual(data["messages"][0]["topic"], "nemo/tools/1/start")

    @patch("NEMO_mqtt_bridge.db_publisher.db_publisher")
    def test_mqtt_monitor_api_empty_messages(self, mock_db_publisher):
        """Test MQTT monitor API when no messages in queue"""
        mock_db_publisher.get_monitor_messages.return_value = []
        mock_db_publisher.get_bridge_status.return_value = None

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get("/mqtt/monitor/api/")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["messages"], [])
        self.assertEqual(data["count"], 0)
        self.assertTrue(data["monitoring"])

    @patch("NEMO_mqtt_bridge.db_publisher.db_publisher")
    def test_mqtt_monitor_api_handles_exception(self, mock_db_publisher):
        """Test MQTT monitor API handles DB errors gracefully"""
        mock_db_publisher.get_monitor_messages.side_effect = Exception("DB unavailable")

        self.client.login(username="testuser", password="testpass123")
        response = self.client.get("/mqtt/monitor/api/")

        self.assertEqual(response.status_code, 500)
        data = json.loads(response.content)
        self.assertEqual(data["messages"], [])
        self.assertEqual(data["count"], 0)
        self.assertFalse(data["monitoring"])
        self.assertIn("error", data)

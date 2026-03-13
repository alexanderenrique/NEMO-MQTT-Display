"""
Tests for NEMO MQTT Plugin DB publisher (PostgreSQL queue)
"""
from unittest.mock import Mock, patch

from django.test import TestCase

from NEMO_mqtt_bridge.db_publisher import DBPublisher


class DBPublisherTest(TestCase):
    """Test DB MQTT Publisher functionality"""

    def setUp(self):
        """Set up test data"""
        self.publisher = DBPublisher()

    @patch("NEMO_mqtt_bridge.db_publisher._is_postgresql")
    def test_check_available_postgresql(self, mock_pg):
        """Test publisher available when PostgreSQL"""
        mock_pg.return_value = True
        self.publisher._available = None
        self.assertTrue(self.publisher._check_available())
        self.assertTrue(self.publisher.is_available())

    @patch("NEMO_mqtt_bridge.db_publisher._is_postgresql")
    def test_check_available_sqlite(self, mock_pg):
        """Test publisher unavailable when SQLite"""
        mock_pg.return_value = False
        self.publisher._available = None
        self.assertFalse(self.publisher._check_available())
        self.assertFalse(self.publisher.is_available())

    @patch("NEMO_mqtt_bridge.db_publisher._is_postgresql", return_value=True)
    @patch("NEMO_mqtt_bridge.db_publisher.MQTTEventQueue")
    def test_publish_event_success(self, mock_queue_model, mock_pg):
        """Test successful event publishing"""
        mock_event = Mock()
        mock_event.id = 1
        mock_queue_model.objects.create.return_value = mock_event

        result = self.publisher.publish_event(
            topic="nemo/tools/1/start",
            payload='{"event": "tool_usage_start"}',
            qos=1,
            retain=False,
        )

        self.assertTrue(result)
        mock_queue_model.objects.create.assert_called_once_with(
            topic="nemo/tools/1/start",
            payload='{"event": "tool_usage_start"}',
            qos=1,
            retain=False,
            processed=False,
        )

    @patch("NEMO_mqtt_bridge.db_publisher._is_postgresql", return_value=False)
    def test_publish_event_no_postgresql(self, mock_pg):
        """Test publishing when PostgreSQL not available"""
        result = self.publisher.publish_event(
            topic="nemo/tools/1/start",
            payload='{"event": "tool_usage_start"}',
            qos=1,
            retain=False,
        )
        self.assertFalse(result)

    @patch("NEMO_mqtt_bridge.db_publisher._is_postgresql", return_value=True)
    @patch("NEMO_mqtt_bridge.db_publisher.MQTTEventQueue")
    def test_publish_event_db_error(self, mock_queue_model, mock_pg):
        """Test event publishing when DB operation fails"""
        mock_queue_model.objects.create.side_effect = Exception("DB error")

        result = self.publisher.publish_event(
            topic="nemo/tools/1/start",
            payload='{"event": "tool_usage_start"}',
            qos=1,
            retain=False,
        )
        self.assertFalse(result)

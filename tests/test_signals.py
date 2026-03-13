"""
Tests for NEMO MQTT Plugin signal handlers
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from NEMO_mqtt_bridge.models import MQTTConfiguration
from NEMO_mqtt_bridge.signals import signal_handler, NEMO_AVAILABLE


class MQTTSignalHandlerTest(TestCase):
    """Test MQTT signal handler functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.mqtt_config = MQTTConfiguration.objects.create(
            name='Test Config',
            enabled=True,
            broker_host='localhost',
            broker_port=1883,
            qos_level=1,
            retain_messages=False
        )
    
    @patch('NEMO_mqtt_bridge.signals.signal_handler.db_publisher')
    def test_publish_message_success(self, mock_db_publisher):
        """Test successful message publishing"""
        mock_db_publisher.publish_event.return_value = True
        
        topic = 'nemo/tools/1/start'
        data = {'event': 'tool_usage_start', 'tool_id': 1}
        
        signal_handler.publish_message(topic, data)
        
        mock_db_publisher.publish_event.assert_called_once()
        call_args = mock_db_publisher.publish_event.call_args
        self.assertEqual(call_args[0][0], topic)
        self.assertEqual(json.loads(call_args[0][1]), data)
        self.assertEqual(call_args[1]['qos'], 1)
        self.assertEqual(call_args[1]['retain'], False)
    
    @patch('NEMO_mqtt_bridge.signals.signal_handler.db_publisher')
    def test_publish_message_failure(self, mock_db_publisher):
        """Test failed message publishing"""
        mock_db_publisher.publish_event.return_value = False
        
        topic = 'nemo/tools/1/start'
        data = {'event': 'tool_usage_start', 'tool_id': 1}
        
        signal_handler.publish_message(topic, data)
        
        mock_db_publisher.publish_event.assert_called_once()
    
    @patch('NEMO_mqtt_bridge.signals.signal_handler.db_publisher', None)
    def test_publish_message_no_publisher(self):
        """Test message publishing when DB publisher is not available"""
        topic = 'nemo/tools/1/start'
        data = {'event': 'tool_usage_start', 'tool_id': 1}
        
        # Should not raise an exception
        signal_handler.publish_message(topic, data)
    
    def test_get_mqtt_config_enabled(self):
        """Test getting enabled MQTT configuration"""
        config = signal_handler._get_mqtt_config()
        self.assertEqual(config.qos_level, 1)
        self.assertFalse(config.retain_messages)
    
    def test_get_mqtt_config_no_config(self):
        """Test getting MQTT configuration when none exists - returns default object"""
        MQTTConfiguration.objects.all().delete()
        
        config = signal_handler._get_mqtt_config()
        self.assertIsNotNone(config)
        self.assertEqual(config.qos_level, 1)  # Default value
        self.assertFalse(config.retain_messages)  # Default value


@pytest.mark.skipif(not NEMO_AVAILABLE, reason="NEMO not installed or not in INSTALLED_APPS")
class ToolSignalsTest(TestCase):
    """Test tool-related signal handlers"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.mqtt_config = MQTTConfiguration.objects.create(
            name='Test Config',
            enabled=True,
            broker_host='localhost',
            broker_port=1883
        )
    
    @patch('NEMO_mqtt_bridge.signals.signal_handler.publish_message')
    def test_tool_saved_signal(self, mock_publish):
        """Test tool save signal handler"""
        from NEMO.models import Tool
        
        # Create a mock tool
        tool = Tool.objects.create(
            name='Test Tool',
            operational=True
        )
        
        # The signal should be triggered automatically
        # We need to manually trigger it for testing
        from NEMO_mqtt_bridge.signals import tool_saved
        tool_saved(Tool, tool, created=True)
        
        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        self.assertEqual(call_args[0][0], f'nemo/tools/{tool.id}')
        self.assertEqual(call_args[0][1]['event'], 'tool_created')
        self.assertEqual(call_args[0][1]['tool_id'], tool.id)
        self.assertEqual(call_args[0][1]['tool_name'], tool.name)


@pytest.mark.skipif(not NEMO_AVAILABLE, reason="NEMO not installed or not in INSTALLED_APPS")
class UsageEventSignalsTest(TestCase):
    """Test usage event signal handlers"""
    
    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.mqtt_config = MQTTConfiguration.objects.create(
            name='Test Config',
            enabled=True,
            broker_host='localhost',
            broker_port=1883
        )
    
    @patch('NEMO_mqtt_bridge.signals.signal_handler.publish_message')
    def test_usage_event_start_signal(self, mock_publish):
        """Test usage event start signal"""
        from NEMO.models import Tool, UsageEvent
        from datetime import datetime
        
        tool = Tool.objects.create(name='Test Tool', operational=True)
        
        # Create usage event without end time (start event)
        usage_event = UsageEvent.objects.create(
            user=self.user,
            tool=tool,
            start=datetime.now()
        )
        
        # Manually trigger the signal
        from NEMO_mqtt_bridge.signals import usage_event_saved
        usage_event_saved(UsageEvent, usage_event, created=True)
        
        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        self.assertEqual(call_args[0][0], f'nemo/tools/{tool.name}/start')
        self.assertEqual(call_args[0][1]['event'], 'tool_usage_start')
        self.assertEqual(call_args[0][1]['tool_name'], tool.name)
    
    @patch('NEMO_mqtt_bridge.signals.signal_handler.publish_message')
    def test_usage_event_end_signal(self, mock_publish):
        """Test usage event end signal"""
        from NEMO.models import Tool, UsageEvent
        from datetime import datetime
        
        tool = Tool.objects.create(name='Test Tool', operational=True)
        
        # Create usage event with end time (end event)
        usage_event = UsageEvent.objects.create(
            user=self.user,
            tool=tool,
            start=datetime.now(),
            end=datetime.now()
        )
        
        # Manually trigger the signal
        from NEMO_mqtt_bridge.signals import usage_event_saved
        usage_event_saved(UsageEvent, usage_event, created=True)
        
        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        self.assertEqual(call_args[0][0], f'nemo/tools/{tool.name}/end')
        self.assertEqual(call_args[0][1]['event'], 'tool_usage_end')
        self.assertEqual(call_args[0][1]['tool_name'], tool.name)

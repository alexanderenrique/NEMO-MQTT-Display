"""
Tests for NEMO MQTT Plugin Redis publisher
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from NEMO_mqtt_bridge.redis_publisher import RedisMQTTPublisher


class RedisMQTTPublisherTest(TestCase):
    """Test Redis MQTT Publisher functionality"""
    
    def setUp(self):
        """Set up test data"""
        self.publisher = RedisMQTTPublisher()
    
    @patch('redislite.Redis')
    def test_initialize_redis_success(self, mock_redis_class):
        """Test successful Redis initialization"""
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis_class.return_value = mock_redis
        
        self.publisher._initialize_redis()
        
        self.assertEqual(self.publisher.redis_client, mock_redis)
        mock_redis.ping.assert_called_once()
    
    @patch('redislite.Redis')
    def test_initialize_redis_failure_retry(self, mock_redis_class):
        """Test Redis initialization with retry logic"""
        mock_redis = Mock()
        mock_redis.ping.side_effect = [Exception("Connection failed"), True]
        mock_redis_class.return_value = mock_redis
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            self.publisher._initialize_redis()
        
        self.assertEqual(self.publisher.redis_client, mock_redis)
        self.assertEqual(mock_redis.ping.call_count, 2)
    
    @patch('redislite.Redis')
    def test_initialize_redis_max_retries_exceeded(self, mock_redis_class):
        """Test Redis initialization when max retries exceeded"""
        mock_redis = Mock()
        mock_redis.ping.side_effect = Exception("Connection failed")
        mock_redis_class.return_value = mock_redis
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            self.publisher._initialize_redis()
        
        self.assertIsNone(self.publisher.redis_client)
        self.assertEqual(mock_redis.ping.call_count, 5)  # Max retries
    
    @patch('NEMO_mqtt_bridge.redis_publisher.RedisMQTTPublisher._initialize_redis')
    def test_publish_event_no_redis(self, mock_initialize):
        """Test publishing event when Redis is not available"""
        self.publisher.redis_client = None
        mock_initialize.return_value = None  # Ensure reconnection fails
        
        result = self.publisher.publish_event(
            topic='nemo/tools/1/start',
            payload='{"event": "tool_usage_start"}',
            qos=1,
            retain=False
        )
        
        self.assertFalse(result)
    
    def test_publish_event_success(self):
        """Test successful event publishing"""
        mock_redis = Mock()
        mock_redis.lpush.return_value = 1
        self.publisher.redis_client = mock_redis
        
        result = self.publisher.publish_event(
            topic='nemo/tools/1/start',
            payload='{"event": "tool_usage_start"}',
            qos=1,
            retain=False
        )
        
        self.assertTrue(result)
        # lpush called twice: events list + monitor list
        self.assertEqual(mock_redis.lpush.call_count, 2)

        # Check the first call (events list)
        call_args = mock_redis.lpush.call_args_list[0][0]
        self.assertEqual(call_args[0], 'nemo_mqtt_events')
        
        # Check the event data
        event_data = json.loads(call_args[1])
        self.assertEqual(event_data['topic'], 'nemo/tools/1/start')
        self.assertEqual(event_data['payload'], '{"event": "tool_usage_start"}')
        self.assertEqual(event_data['qos'], 1)
        self.assertEqual(event_data['retain'], False)
        self.assertIn('timestamp', event_data)
    
    def test_publish_event_redis_error(self):
        """Test event publishing when Redis operation fails"""
        mock_redis = Mock()
        mock_redis.lpush.side_effect = Exception("Redis error")
        self.publisher.redis_client = mock_redis
        
        result = self.publisher.publish_event(
            topic='nemo/tools/1/start',
            payload='{"event": "tool_usage_start"}',
            qos=1,
            retain=False
        )
        
        self.assertFalse(result)
    
    def test_publish_event_with_timestamp(self):
        """Test event publishing includes timestamp"""
        mock_redis = Mock()
        mock_redis.lpush.return_value = 1
        self.publisher.redis_client = mock_redis
        
        with patch('time.time', return_value=1234567890.123):
            result = self.publisher.publish_event(
                topic='nemo/tools/1/start',
                payload='{"event": "tool_usage_start"}',
                qos=1,
                retain=False
            )
        
        self.assertTrue(result)
        
        # Check the event data includes timestamp
        call_args = mock_redis.lpush.call_args
        event_data = json.loads(call_args[0][1])
        self.assertEqual(event_data['timestamp'], 1234567890.123)
    
    def test_publish_event_different_qos_retain(self):
        """Test event publishing with different QoS and retain settings"""
        mock_redis = Mock()
        mock_redis.lpush.return_value = 1
        self.publisher.redis_client = mock_redis
        
        result = self.publisher.publish_event(
            topic='nemo/tools/1/end',
            payload='{"event": "tool_usage_end"}',
            qos=2,
            retain=True
        )
        
        self.assertTrue(result)
        
        # Check the event data
        call_args = mock_redis.lpush.call_args
        event_data = json.loads(call_args[0][1])
        self.assertEqual(event_data['qos'], 2)
        self.assertEqual(event_data['retain'], True)

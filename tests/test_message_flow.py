#!/usr/bin/env python3
"""
Simple test script to verify the MQTT message flow
Adds a test message to Redis and checks if it gets consumed
"""

import os
import sys
import time
import json
import redis
import logging

logger = logging.getLogger(__name__)

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_mqtt_flow():
    """Test the complete MQTT flow"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Testing MQTT Flow")
    logger.info("=" * 30)

    # Test Redis connection
    logger.info("Testing Redis connection...")
    try:
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        redis_client.ping()
        logger.info("Redis connection successful")
    except Exception as e:
        logger.error("Redis connection failed: %s", e)
        return False

    # Create a test event
    test_event = {
        'topic': 'nemo/test/tool_usage_start',
        'payload': json.dumps({
            "event": "tool_usage_start",
            "usage_id": 999,
            "user_id": 1,
            "user_name": "Test User",
            "tool_id": 1,
            "tool_name": "Test Tool",
            "start_time": "2024-01-01T12:00:00Z",
            "end_time": None,
            "timestamp": time.time()
        }),
        'qos': 0,
        'retain': False,
        'timestamp': time.time()
    }

    logger.info("Adding test event to Redis: %s", test_event['topic'])

    try:
        # Add to Redis list
        result = redis_client.lpush('nemo_mqtt_events', json.dumps(test_event))
        logger.info("Event added to Redis (list length: %s)", result)

        # Wait a moment for the MQTT service to process it
        logger.info("Waiting for MQTT service to process...")
        time.sleep(2)

        # Check if message was consumed
        list_length = redis_client.llen('nemo_mqtt_events')
        if list_length == 0:
            logger.info("Message was consumed by MQTT service!")
            logger.info("Check your MQTT monitor to see if the message was published")
        else:
            logger.warning("Message still in Redis (list length: %s)", list_length)
            logger.warning("   MQTT service may not be running or processing messages")

        return True
    except Exception as e:
        logger.error("Failed to add event to Redis: %s", e)
        return False

if __name__ == "__main__":
    test_mqtt_flow()

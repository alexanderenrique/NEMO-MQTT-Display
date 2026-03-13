#!/usr/bin/env python3
"""
Test script to verify the MQTT monitor API is working
"""

import os
import sys
import django
import json
import time
import logging

logger = logging.getLogger(__name__)

# Add the project directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'nemo-ce'))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'settings_dev')
django.setup()

from NEMO_mqtt_bridge.views import monitor
from NEMO_mqtt_bridge.redis_publisher import redis_publisher


def test_monitor():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Testing MQTT Monitor API")
    logger.info("=" * 50)

    # Test Redis connection
    logger.info("1. Testing Redis connection...")
    if redis_publisher.is_available():
        logger.info("   Redis is available")
    else:
        logger.error("   Redis is not available")
        return

    # Test monitor status
    logger.info("2. Testing monitor status...")
    logger.info("   Monitor running: %s", monitor.running)
    logger.info("   Messages count: %s", len(monitor.messages))

    # Start monitoring
    logger.info("3. Starting monitor...")
    monitor.start_monitoring()
    time.sleep(2)  # Give it time to connect
    logger.info("   Monitor running: %s", monitor.running)

    # Publish a test message
    logger.info("4. Publishing test message...")
    success = redis_publisher.publish_event(
        topic="nemo/test/monitor",
        payload='{"test": "message", "timestamp": "' + str(time.time()) + '"}',
        qos=0,
        retain=False
    )
    logger.info("   Message published: %s", success)

    # Wait a bit for the message to be processed
    logger.info("5. Waiting for message processing...")
    time.sleep(3)

    # Check messages
    logger.info("6. Checking messages...")
    messages = monitor.messages
    logger.info("   Total messages: %s", len(messages))

    if messages:
        logger.info("   Recent messages:")
        for i, msg in enumerate(messages[-3:], 1):
            logger.info("     %s. %s - %s - %s...", i, msg['source'], msg['topic'], msg['payload'][:50])
    else:
        logger.info("   No messages found")

    # Test API endpoint
    logger.info("7. Testing API endpoint...")
    from django.test import RequestFactory
    from NEMO_mqtt_bridge.views import mqtt_monitor_api

    factory = RequestFactory()
    request = factory.get('/monitor/api/')
    request.user = None  # Skip auth for test

    try:
        response = mqtt_monitor_api(request)
        data = json.loads(response.content)
        logger.info("   API response: %s messages, monitoring: %s", data['count'], data['monitoring'])
    except Exception as e:
        logger.error("   API error: %s", e)

    logger.info("Test completed!")

if __name__ == "__main__":
    test_monitor()

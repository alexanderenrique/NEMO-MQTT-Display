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

# Monitor view is mqtt_monitor / mqtt_monitor_api
from NEMO_mqtt_bridge.db_publisher import db_publisher


def test_monitor():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Testing MQTT Monitor API")
    logger.info("=" * 50)

    # Test DB publisher connection
    logger.info("1. Testing DB publisher...")
    if db_publisher.is_available():
        logger.info("   DB publisher is available (PostgreSQL)")
    else:
        logger.error("   DB publisher not available (requires PostgreSQL)")
        return

    # Publish a test message
    logger.info("2. Publishing test message...")
    success = db_publisher.publish_event(
        topic="nemo/test/monitor",
        payload='{"test": "message", "timestamp": "' + str(time.time()) + '"}',
        qos=0,
        retain=False
    )
    logger.info("   Message published: %s", success)

    # Wait a bit for the message to be processed
    logger.info("3. Waiting for message processing...")
    time.sleep(2)

    # Test API endpoint
    logger.info("4. Testing API endpoint...")
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

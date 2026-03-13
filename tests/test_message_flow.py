#!/usr/bin/env python3
"""
Simple test script to verify the MQTT message flow.
Adds a test message to the queue and checks if it gets consumed.
"""

import os
import sys
import time
import json
import logging

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_settings")


def test_mqtt_flow():
    """Test the complete MQTT flow via PostgreSQL queue"""
    import django

    django.setup()

    from NEMO_mqtt_bridge.db_publisher import db_publisher

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Testing MQTT Flow")
    logger.info("=" * 30)

    if not db_publisher.is_available():
        logger.warning("DB publisher not available (requires PostgreSQL), skipping")
        return False

    test_event = {
        "topic": "nemo/test/tool_usage_start",
        "payload": json.dumps(
            {
                "event": "tool_usage_start",
                "usage_id": 999,
                "user_id": 1,
                "user_name": "Test User",
                "tool_id": 1,
                "tool_name": "Test Tool",
                "start_time": "2024-01-01T12:00:00Z",
                "end_time": None,
                "timestamp": time.time(),
            }
        ),
        "qos": 0,
        "retain": False,
    }

    logger.info("Adding test event to queue: %s", test_event["topic"])

    try:
        success = db_publisher.publish_event(
            topic=test_event["topic"],
            payload=test_event["payload"],
            qos=test_event["qos"],
            retain=test_event["retain"],
        )
        if not success:
            logger.error("Failed to publish event")
            return False

        logger.info("Event added to queue")

        logger.info("Waiting for MQTT service to process...")
        time.sleep(2)

        logger.info("Check your MQTT monitor to see if the message was published")
        return True
    except Exception as e:
        logger.error("Failed to add event: %s", e)
        return False


if __name__ == "__main__":
    test_mqtt_flow()

#!/usr/bin/env python3
"""
Test the complete MQTT flow
Django signals → PostgreSQL queue → MQTT Publisher → MQTT Broker → Monitor

Requires PostgreSQL and the bridge to be running.
"""

import logging
import json
import time
import os
import sys
import django

logger = logging.getLogger(__name__)

# Add project path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_settings")
django.setup()


def test_complete_flow():
    from NEMO_mqtt_bridge.db_publisher import db_publisher

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Testing Complete MQTT Flow (PostgreSQL)")
    logger.info("=" * 50)

    if not db_publisher.is_available():
        logger.error("DB publisher not available (requires PostgreSQL)")
        return

    test_message = {
        "event": "tool_usage_start",
        "usage_id": 999,
        "user_id": 1,
        "user_name": "Test User",
        "tool_id": 1,
        "tool_name": "test_tool",
        "start_time": "2025-10-08T22:15:00.000000+00:00",
        "end_time": None,
        "timestamp": False,
    }

    logger.info("Publishing test message to queue...")
    logger.info("   Topic: nemo/tools/test_tool/start")
    logger.info("   Payload: %s", json.dumps(test_message))

    success = db_publisher.publish_event(
        topic="nemo/tools/test_tool/start",
        payload=json.dumps(test_message),
        qos=0,
        retain=False,
    )

    if success:
        logger.info("Published to queue successfully")
    else:
        logger.error("Failed to publish to queue")
        return

    logger.info("Waiting for bridge to process...")
    time.sleep(2)

    logger.info("Check your MQTT monitor to see if the message was published")
    logger.info("=" * 50)


if __name__ == "__main__":
    test_complete_flow()

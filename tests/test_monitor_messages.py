#!/usr/bin/env python3
"""
Test script to generate MQTT messages for testing the monitor.
Uses db_publisher (PostgreSQL queue) when available.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

# Django setup for db_publisher
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_settings")


def test_queue_messages():
    """Generate test messages via db_publisher (PostgreSQL queue)"""
    import django

    django.setup()

    from NEMO_mqtt_bridge.db_publisher import db_publisher
    from datetime import datetime

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if not db_publisher.is_available():
        logger.warning("DB publisher not available (requires PostgreSQL), skipping")
        return

    test_messages = [
        {
            "topic": "nemo/tool/test_tool_1",
            "payload": '{"action": "enabled", "tool_id": "test_tool_1", "user": "test_user"}',
            "qos": 0,
            "retain": False,
        },
        {
            "topic": "nemo/tool/test_tool_2",
            "payload": '{"action": "disabled", "tool_id": "test_tool_2", "user": "test_user"}',
            "qos": 0,
            "retain": False,
        },
        {
            "topic": "nemo/area/test_area",
            "payload": '{"area": "test_area", "status": "active", "users": 3}',
            "qos": 1,
            "retain": True,
        },
    ]

    for i, msg in enumerate(test_messages):
        success = db_publisher.publish_event(
            topic=msg["topic"],
            payload=msg["payload"],
            qos=msg["qos"],
            retain=msg["retain"],
        )
        if success:
            logger.info("Pushed message %s: %s", i + 1, msg["topic"])
        else:
            logger.warning("Failed to push message %s", i + 1)

    logger.info("Generated %s test messages", len(test_messages))


if __name__ == "__main__":
    test_queue_messages()

#!/usr/bin/env python3
"""
Simple test to verify DB publisher and message flow.
Uses db_publisher (PostgreSQL queue) when available.
"""

import logging
import json
import time
import os
import sys

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.test_settings")


def test_queue_and_mqtt():
    import django

    django.setup()

    from NEMO_mqtt_bridge.db_publisher import db_publisher

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Testing PostgreSQL Queue and MQTT Message Flow")
    logger.info("=" * 50)

    if not db_publisher.is_available():
        logger.warning("DB publisher not available (requires PostgreSQL), skipping")
        return

    logger.info("1. DB publisher is available (PostgreSQL)")

    logger.info("2. Publishing test message...")
    test_event = {
        "topic": "nemo/test/monitor",
        "payload": json.dumps(
            {"test": "message", "timestamp": time.time(), "source": "test_script"}
        ),
        "qos": 0,
        "retain": False,
    }

    success = db_publisher.publish_event(
        topic=test_event["topic"],
        payload=test_event["payload"],
        qos=test_event["qos"],
        retain=test_event["retain"],
    )
    if success:
        logger.info("   Test message published to queue")
    else:
        logger.error("   Failed to publish message")
        return

    messages = db_publisher.get_monitor_messages()
    logger.info("3. Messages in queue: %s", len(messages))
    if messages:
        for i, msg in enumerate(messages[:3], 1):
            logger.info(
                "     %s. %s - %s...",
                i,
                msg.get("topic", "unknown"),
                (msg.get("payload", "") or "")[:50],
            )

    logger.info("Test completed!")
    logger.info("Next steps:")
    logger.info("1. Make sure the bridge is running: python -m NEMO_mqtt_bridge.postgres_mqtt_bridge")
    logger.info("2. Check the web monitor page at /mqtt/monitor/")
    logger.info("3. Enable/disable a tool in NEMO to generate real messages")


if __name__ == "__main__":
    test_queue_and_mqtt()

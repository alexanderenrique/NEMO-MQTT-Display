#!/usr/bin/env python3
"""
Test the complete MQTT flow
Django signals → Redis → MQTT Publisher → MQTT Broker → Monitor
"""

import logging
import redis
import json
import time

logger = logging.getLogger(__name__)


def test_complete_flow():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Testing Complete MQTT Flow")
    logger.info("=" * 50)

    # Connect to Redis
    try:
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        redis_client.ping()
        logger.info("Connected to Redis")
    except Exception as e:
        logger.error("Redis connection failed: %s", e)
        return

    # Create a test message (simulating what Django signals do)
    test_message = {
        "topic": "nemo/tools/test_tool/start",
        "payload": json.dumps({
            "event": "tool_usage_start",
            "usage_id": 999,
            "user_id": 1,
            "user_name": "Test User",
            "tool_id": 1,
            "tool_name": "test_tool",
            "start_time": "2025-10-08T22:15:00.000000+00:00",
            "end_time": None,
            "timestamp": False
        }),
        "qos": 0,
        "retain": False,
        "timestamp": time.time()
    }

    logger.info("Publishing test message to Redis...")
    logger.info("   Topic: %s", test_message['topic'])
    logger.info("   Payload: %s", test_message['payload'])

    # Publish to Redis (this is what Django signals do)
    result = redis_client.lpush('nemo_mqtt_events', json.dumps(test_message))
    logger.info("Published to Redis (list length: %s)", result)

    # Wait a moment for the standalone service to process it
    logger.info("Waiting for standalone service to process...")
    time.sleep(2)

    # Check if Redis list is empty (meaning it was consumed)
    list_length = redis_client.llen('nemo_mqtt_events')
    logger.info("Redis list length after processing: %s", list_length)

    if list_length == 0:
        logger.info("Message was consumed by standalone service")
        logger.info("Check your MQTT monitor to see if the message was published to MQTT")
    else:
        logger.error("Message was not consumed by standalone service")

    logger.info("=" * 50)

if __name__ == "__main__":
    test_complete_flow()

#!/usr/bin/env python3
"""
Test script to generate MQTT messages for testing the monitor
"""

import logging
import redis
import json
import time
from datetime import datetime

logger = logging.getLogger(__name__)


def test_redis_messages():
    """Generate test messages in Redis"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        # Connect to Redis
        redis_client = redis.Redis(
            host='localhost',
            port=6379,
            db=0,
            decode_responses=True
        )
        redis_client.ping()
        logger.info("Connected to Redis")

        # Generate test messages
        test_messages = [
            {
                'timestamp': datetime.now().isoformat(),
                'topic': 'nemo/tool/test_tool_1',
                'payload': '{"action": "enabled", "tool_id": "test_tool_1", "user": "test_user"}',
                'qos': 0,
                'retain': False
            },
            {
                'timestamp': datetime.now().isoformat(),
                'topic': 'nemo/tool/test_tool_2',
                'payload': '{"action": "disabled", "tool_id": "test_tool_2", "user": "test_user"}',
                'qos': 0,
                'retain': False
            },
            {
                'timestamp': datetime.now().isoformat(),
                'topic': 'nemo/area/test_area',
                'payload': '{"area": "test_area", "status": "active", "users": 3}',
                'qos': 1,
                'retain': True
            }
        ]

        # Push messages to Redis
        for i, msg in enumerate(test_messages):
            redis_client.lpush('nemo_mqtt_events', json.dumps(msg))
            logger.info("Pushed message %s: %s", i + 1, msg['topic'])
            time.sleep(0.5)

        logger.info("Generated %s test messages in Redis", len(test_messages))

        # Check how many messages are in Redis
        count = redis_client.llen('nemo_mqtt_events')
        logger.info("Total messages in Redis: %s", count)

    except Exception as e:
        logger.error("Error: %s", e)

if __name__ == "__main__":
    test_redis_messages()

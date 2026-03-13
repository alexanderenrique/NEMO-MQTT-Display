#!/usr/bin/env python3
"""
Simple test to verify Redis connection and message publishing
"""

import logging
import redis
import json
import time

logger = logging.getLogger(__name__)


def test_redis_and_mqtt():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    logger.info("Testing Redis and MQTT Message Flow")
    logger.info("=" * 50)

    # Test Redis connection
    logger.info("1. Testing Redis connection...")
    try:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        r.ping()
        logger.info("   Redis is available")
    except Exception as e:
        logger.error("   Redis connection failed: %s", e)
        return

    # Check current messages
    logger.info("2. Checking current messages in Redis...")
    messages = r.lrange('nemo_mqtt_events', 0, -1)
    logger.info("   Current messages in queue: %s", len(messages))

    # Publish a test message
    logger.info("3. Publishing test message...")
    test_event = {
        'topic': 'nemo/test/monitor',
        'payload': json.dumps({
            'test': 'message',
            'timestamp': time.time(),
            'source': 'test_script'
        }),
        'qos': 0,
        'retain': False,
        'timestamp': time.time()
    }

    try:
        r.lpush('nemo_mqtt_events', json.dumps(test_event))
        logger.info("   Test message published to Redis")
    except Exception as e:
        logger.error("   Failed to publish message: %s", e)
        return

    # Check messages again
    logger.info("4. Checking messages after publish...")
    messages = r.lrange('nemo_mqtt_events', 0, -1)
    logger.info("   Messages in queue: %s", len(messages))

    if messages:
        logger.info("   Recent messages:")
        for i, msg in enumerate(messages[:3], 1):
            try:
                data = json.loads(msg)
                logger.info("     %s. %s - %s...", i, data.get('topic', 'unknown'), (data.get('payload', 'unknown') or '')[:50])
            except Exception:
                logger.info("     %s. Raw: %s...", i, (msg or '')[:50])

    # Test consuming a message
    logger.info("5. Testing message consumption...")
    try:
        consumed = r.rpop('nemo_mqtt_events')
        if consumed:
            data = json.loads(consumed)
            logger.info("   Consumed message: %s", data.get('topic', 'unknown'))
        else:
            logger.warning("   No messages to consume")
    except Exception as e:
        logger.error("   Failed to consume message: %s", e)

    logger.info("Test completed!")
    logger.info("Next steps:")
    logger.info("1. Make sure the external MQTT service is running")
    logger.info("2. Check the web monitor page")
    logger.info("3. Enable/disable a tool in NEMO to generate real messages")

if __name__ == "__main__":
    test_redis_and_mqtt()


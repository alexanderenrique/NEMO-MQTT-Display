#!/usr/bin/env python3
"""
Direct MQTT Test
Publishes test messages directly to MQTT broker to test monitor reception
"""

import logging
import paho.mqtt.client as mqtt
import json
import time
import uuid

logger = logging.getLogger(__name__)


def on_connect(client, userdata, flags, rc):
    logger.info("Connected with result code %s", rc)
    if rc == 0:
        logger.info("Connected to MQTT broker")


def on_publish(client, userdata, mid):
    logger.info("Message %s published successfully", mid)


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    # Create MQTT client
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_publish = on_publish

    try:
        # Connect to broker
        logger.info("Connecting to MQTT broker...")
        client.connect('localhost', 1883, 60)
        client.loop_start()

        # Wait for connection
        time.sleep(1)

        # Publish test messages
        test_messages = [
            {
                "event": "tool_usage_start",
                "usage_id": 999,
                "user_id": 1,
                "user_name": "Test User",
                "tool_id": 1,
                "tool_name": "test_tool",
                "start_time": "2025-10-09T16:00:00.000000+00:00",
                "end_time": None,
                "timestamp": False
            },
            {
                "event": "tool_usage_end",
                "usage_id": 999,
                "user_id": 1,
                "user_name": "Test User",
                "tool_id": 1,
                "tool_name": "test_tool",
                "start_time": "2025-10-09T16:00:00.000000+00:00",
                "end_time": "2025-10-09T16:00:05.000000+00:00",
                "timestamp": False
            },
            {
                "event": "tool_usage_start",
                "usage_id": 1000,
                "user_id": 1,
                "user_name": "Test User",
                "tool_id": 1,
                "tool_name": "test_tool",
                "start_time": "2025-10-09T16:01:00.000000+00:00",
                "end_time": None,
                "timestamp": False
            },
            {
                "event": "tool_usage_end",
                "usage_id": 1000,
                "user_id": 1,
                "user_name": "Test User",
                "tool_id": 1,
                "tool_name": "test_tool",
                "start_time": "2025-10-09T16:01:00.000000+00:00",
                "end_time": "2025-10-09T16:01:05.000000+00:00",
                "timestamp": False
            }
        ]

        logger.info("Publishing %s test messages...", len(test_messages))

        for i, message in enumerate(test_messages, 1):
            topic = f"nemo/tools/test_tool/{'start' if message['event'] == 'tool_usage_start' else 'end'}"
            payload = json.dumps(message)

            logger.info("Publishing message %s/%s", i, len(test_messages))
            logger.info("   Topic: %s", topic)
            logger.info("   Payload: %s...", payload[:100])

            result = client.publish(topic, payload, qos=0, retain=False)
            logger.info("   Result: %s (mid: %s)", result.rc, result.mid)

            # Small delay between messages
            time.sleep(0.5)

        logger.info("All test messages published")
        logger.info("Waiting 2 seconds for delivery...")
        time.sleep(2)

    except Exception as e:
        logger.error("Error: %s", e)
    finally:
        client.loop_stop()
        client.disconnect()
        logger.info("Disconnected from MQTT broker")

if __name__ == "__main__":
    main()

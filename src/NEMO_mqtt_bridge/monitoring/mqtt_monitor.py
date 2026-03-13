#!/usr/bin/env python3
"""
MQTT Message Monitor

This script monitors both Redis and MQTT messages to help debug the MQTT plugin.
Run it from your NEMO project root with a valid DJANGO_SETTINGS_MODULE, for example:

    export DJANGO_SETTINGS_MODULE=settings_dev  # or your NEMO settings module
    python -m NEMO_mqtt_bridge.monitoring.mqtt_monitor
"""

import os
import sys
import django
import redis
import paho.mqtt.client as mqtt
import json
import time
import threading
import signal
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Add the project directory to the Python path
sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
    ),
)

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings_dev")
django.setup()


class MQTTMonitor:
    def __init__(self):
        self.redis_client = None
        self.mqtt_client = None
        self.running = True
        self.redis_messages = []
        self.mqtt_messages = []

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("Received signal %s, shutting down...", signum)
        self.running = False
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        sys.exit(0)

    def connect_redis(self):
        """Connect to Redis"""
        try:
            self.redis_client = redis.Redis(
                host="localhost",
                port=6379,
                db=1,  # Same as plugin (redis_publisher) so we see the same events
                decode_responses=True,
            )
            self.redis_client.ping()
            logger.info("Connected to Redis")
            return True
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            return False

    def connect_mqtt(self):
        """Connect to MQTT broker"""
        try:
            self.mqtt_client = mqtt.Client()
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.on_message = self.on_mqtt_message
            self.mqtt_client.on_disconnect = self.on_mqtt_disconnect

            self.mqtt_client.connect("localhost", 1883, 60)
            self.mqtt_client.loop_start()
            return True
        except Exception as e:
            logger.error("Failed to connect to MQTT broker: %s", e)
            return False

    def on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            logger.info("Connected to MQTT broker")
            # Subscribe to all NEMO topics
            client.subscribe("nemo/#")
            logger.info("Subscribed to nemo/# topics")
        else:
            logger.error("MQTT connection failed with code %s", rc)

    def on_mqtt_message(self, client, userdata, msg):
        """MQTT message callback"""
        try:
            payload = msg.payload.decode("utf-8")
            message_data = {
                "timestamp": datetime.now().isoformat(),
                "topic": msg.topic,
                "payload": payload,
                "qos": msg.qos,
                "retain": msg.retain,
            }

            self.mqtt_messages.append(message_data)
            logger.info("MQTT Message Received: Topic=%s Payload=%s Time=%s", msg.topic, payload, message_data["timestamp"])
            logger.info("-" * 50)

        except Exception as e:
            logger.error("Error processing MQTT message: %s", e)

    def on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        logger.warning("MQTT disconnected with code %s", rc)

    def monitor_redis(self):
        """Monitor Redis for new messages"""
        logger.info("Monitoring Redis for messages...")

        while self.running:
            try:
                # Check for new messages in the Redis list
                message = self.redis_client.rpop("nemo_mqtt_events")
                if message:
                    try:
                        event_data = json.loads(message)
                        redis_message = {
                            "timestamp": datetime.now().isoformat(),
                            "redis_timestamp": event_data.get("timestamp", "unknown"),
                            "topic": event_data.get("topic", "unknown"),
                            "payload": event_data.get("payload", "unknown"),
                            "qos": event_data.get("qos", 0),
                            "retain": event_data.get("retain", False),
                        }

                        self.redis_messages.append(redis_message)
                        logger.info(
                            "Redis Message Received: Topic=%s Payload=%s Time=%s",
                            redis_message["topic"],
                            redis_message["payload"],
                            redis_message["timestamp"],
                        )
                        logger.info("-" * 50)

                    except json.JSONDecodeError as e:
                        logger.error("Error parsing Redis message: %s", e)
                        logger.error("   Raw message: %s", message)

                time.sleep(0.1)  # Small delay to prevent excessive CPU usage

            except Exception as e:
                logger.error("Error monitoring Redis: %s", e)
                time.sleep(1)

    def show_summary(self):
        """Show summary of captured messages"""
        logger.info("=" * 60)
        logger.info("MESSAGE SUMMARY")
        logger.info("=" * 60)

        logger.info("Redis Messages: %s", len(self.redis_messages))
        for i, msg in enumerate(self.redis_messages[-5:], 1):  # Show last 5
            logger.info("   %s. %s - %s", i, msg["timestamp"], msg["topic"])

        logger.info("MQTT Messages: %s", len(self.mqtt_messages))
        for i, msg in enumerate(self.mqtt_messages[-5:], 1):  # Show last 5
            logger.info("   %s. %s - %s", i, msg["timestamp"], msg["topic"])

        logger.info("=" * 60)

    def run(self):
        """Run the monitor"""
        logger.info("Starting MQTT Message Monitor")
        logger.info("=" * 60)

        # Connect to Redis
        if not self.connect_redis():
            return

        # Connect to MQTT
        if not self.connect_mqtt():
            return

        logger.info("Instructions:")
        logger.info("1. Enable/disable a tool in NEMO")
        logger.info("2. Watch for Redis and MQTT messages in logs")
        logger.info("3. Press Ctrl+C to stop monitoring")
        logger.info("=" * 60)

        # Start Redis monitoring in a separate thread
        redis_thread = threading.Thread(target=self.monitor_redis, daemon=True)
        redis_thread.start()

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False

        self.show_summary()
        logger.info("Monitor stopped")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
    )
    monitor = MQTTMonitor()
    monitor.run()


if __name__ == "__main__":
    main()

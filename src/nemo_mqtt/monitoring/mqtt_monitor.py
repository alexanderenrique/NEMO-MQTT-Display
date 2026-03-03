#!/usr/bin/env python3
"""
MQTT Message Monitor

This script monitors both Redis and MQTT messages to help debug the MQTT plugin.
Run it from your NEMO project root with a valid DJANGO_SETTINGS_MODULE, for example:

    export DJANGO_SETTINGS_MODULE=settings_dev  # or your NEMO settings module
    python -m NEMO_mqtt.monitoring.mqtt_monitor
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
from datetime import datetime

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
        print(f"\nReceived signal {signum}, shutting down...")
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
            print("[OK] Connected to Redis")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to connect to Redis: {e}")
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
            print(f"[ERROR] Failed to connect to MQTT broker: {e}")
            return False

    def on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            print("[OK] Connected to MQTT broker")
            # Subscribe to all NEMO topics
            client.subscribe("nemo/#")
            print("Subscribed to nemo/# topics")
        else:
            print(f"[ERROR] MQTT connection failed with code {rc}")

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
            print(f"\nMQTT Message Received:")
            print(f"   Topic: {msg.topic}")
            print(f"   Payload: {payload}")
            print(f"   Time: {message_data['timestamp']}")
            print("-" * 50)

        except Exception as e:
            print(f"[ERROR] Error processing MQTT message: {e}")

    def on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        print(f"WARNING: MQTT disconnected with code {rc}")

    def monitor_redis(self):
        """Monitor Redis for new messages"""
        print("Monitoring Redis for messages...")

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
                        print(f"\nRedis Message Received:")
                        print(f"   Topic: {redis_message['topic']}")
                        print(f"   Payload: {redis_message['payload']}")
                        print(f"   Time: {redis_message['timestamp']}")
                        print("-" * 50)

                    except json.JSONDecodeError as e:
                        print(f"[ERROR] Error parsing Redis message: {e}")
                        print(f"   Raw message: {message}")

                time.sleep(0.1)  # Small delay to prevent excessive CPU usage

            except Exception as e:
                print(f"[ERROR] Error monitoring Redis: {e}")
                time.sleep(1)

    def show_summary(self):
        """Show summary of captured messages"""
        print("\n" + "=" * 60)
        print("MESSAGE SUMMARY")
        print("=" * 60)

        print(f"\nRedis Messages: {len(self.redis_messages)}")
        for i, msg in enumerate(self.redis_messages[-5:], 1):  # Show last 5
            print(f"   {i}. {msg['timestamp']} - {msg['topic']}")

        print(f"\nMQTT Messages: {len(self.mqtt_messages)}")
        for i, msg in enumerate(self.mqtt_messages[-5:], 1):  # Show last 5
            print(f"   {i}. {msg['timestamp']} - {msg['topic']}")

        print("\n" + "=" * 60)

    def run(self):
        """Run the monitor"""
        print("Starting MQTT Message Monitor")
        print("=" * 60)

        # Connect to Redis
        if not self.connect_redis():
            return

        # Connect to MQTT
        if not self.connect_mqtt():
            return

        print("\nInstructions:")
        print("1. Enable/disable a tool in NEMO")
        print("2. Watch for Redis and MQTT messages below")
        print("3. Press Ctrl+C to stop monitoring")
        print("\n" + "=" * 60)

        # Start Redis monitoring in a separate thread
        redis_thread = threading.Thread(target=self.monitor_redis, daemon=True)
        redis_thread.start()

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False

        self.show_summary()
        print("\nMonitor stopped")


def main():
    monitor = MQTTMonitor()
    monitor.run()


if __name__ == "__main__":
    main()

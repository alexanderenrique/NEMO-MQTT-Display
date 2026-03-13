#!/usr/bin/env python3
"""
MQTT Message Monitor

Monitors both the PostgreSQL queue and MQTT messages to help debug the MQTT plugin.
Run from your NEMO project root with a valid DJANGO_SETTINGS_MODULE.
"""

import os
import sys
import django
import paho.mqtt.client as mqtt
import time
import threading
import signal
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
    ),
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings_dev")
django.setup()


class MQTTMonitor:
    def __init__(self):
        self.mqtt_client = None
        self.running = True
        self.queue_messages = []
        self.mqtt_messages = []
        self._last_queue_id = 0

        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        self.running = False
        if self.mqtt_client:
            self.mqtt_client.disconnect()
        sys.exit(0)

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
        if rc == 0:
            logger.info("Connected to MQTT broker")
            client.subscribe("nemo/#")
            logger.info("Subscribed to nemo/# topics")
        else:
            logger.error("MQTT connection failed with code %s", rc)

    def on_mqtt_message(self, client, userdata, msg):
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
            logger.info(
                "MQTT Message: Topic=%s Payload=%s Time=%s",
                msg.topic,
                payload[:80] + "..." if len(payload) > 80 else payload,
                message_data["timestamp"],
            )
            logger.info("-" * 50)
        except Exception as e:
            logger.error("Error processing MQTT message: %s", e)

    def on_mqtt_disconnect(self, client, userdata, rc):
        logger.warning("MQTT disconnected with code %s", rc)

    def monitor_queue(self):
        """Monitor PostgreSQL queue for new messages"""
        from NEMO_mqtt_bridge.models import MQTTEventQueue

        logger.info("Monitoring PostgreSQL queue for messages...")
        while self.running:
            try:
                new_events = MQTTEventQueue.objects.filter(id__gt=self._last_queue_id).order_by("id")
                for ev in new_events:
                    self._last_queue_id = ev.id
                    msg = {
                        "timestamp": ev.created_at.isoformat() if ev.created_at else "",
                        "topic": ev.topic,
                        "payload": ev.payload,
                        "qos": ev.qos,
                        "retain": ev.retain,
                    }
                    self.queue_messages.append(msg)
                    logger.info(
                        "Queue Message: Topic=%s Payload=%s Time=%s",
                        ev.topic,
                        (ev.payload[:80] + "...") if len(ev.payload) > 80 else ev.payload,
                        msg["timestamp"],
                    )
                    logger.info("-" * 50)
            except Exception as e:
                logger.error("Error monitoring queue: %s", e)
            time.sleep(0.1)

    def show_summary(self):
        logger.info("=" * 60)
        logger.info("MESSAGE SUMMARY")
        logger.info("=" * 60)
        logger.info("Queue Messages: %s", len(self.queue_messages))
        for i, msg in enumerate(self.queue_messages[-5:], 1):
            logger.info("   %s. %s - %s", i, msg["timestamp"], msg["topic"])
        logger.info("MQTT Messages: %s", len(self.mqtt_messages))
        for i, msg in enumerate(self.mqtt_messages[-5:], 1):
            logger.info("   %s. %s - %s", i, msg["timestamp"], msg["topic"])
        logger.info("=" * 60)

    def run(self):
        logger.info("Starting MQTT Message Monitor")
        logger.info("=" * 60)
        if not self.connect_mqtt():
            return
        logger.info("Instructions:")
        logger.info("1. Enable/disable a tool in NEMO")
        logger.info("2. Watch for queue and MQTT messages in logs")
        logger.info("3. Press Ctrl+C to stop")
        logger.info("=" * 60)
        queue_thread = threading.Thread(target=self.monitor_queue, daemon=True)
        queue_thread.start()
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

"""
Redis-based MQTT Event Publisher for NEMO
This module handles publishing events to Redis instead of directly to MQTT.
The external MQTT service will consume these events and publish them to the MQTT broker.
"""

import json
import logging
import redis
import time
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Redis list keys (use lowercase for consistency with package name)
EVENTS_LIST_KEY = "nemo_mqtt_events"
MONITOR_LIST_KEY = "nemo_mqtt_monitor"
MONITOR_LIST_MAXLEN = 100
BRIDGE_CONTROL_KEY = "NEMO_mqtt_bridge_control"
BRIDGE_STATUS_KEY = "NEMO_mqtt_bridge_status"
BRIDGE_STATUS_TTL = 90  # seconds; if bridge dies, status expires


class RedisMQTTPublisher:
    """Publishes MQTT events to Redis for consumption by external MQTT service"""

    def __init__(self):
        self.redis_client = None
        self._initialize_redis()

    def _initialize_redis(self):
        """Initialize Redis client with retry logic"""
        max_retries = 5
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                self.redis_client = redis.Redis(
                    host="localhost",
                    port=6379,
                    db=1,  # Use database 1 for plugin isolation
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                # Test connection
                self.redis_client.ping()
                logger.info("Connected to Redis for MQTT event publishing")
                return
            except Exception as e:
                logger.warning(
                    f"Redis connection attempt {attempt + 1}/{max_retries} failed: {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error(
                        f"Failed to connect to Redis after {max_retries} attempts: {e}"
                    )
                    self.redis_client = None

    def publish_event(
        self, topic: str, payload: str, qos: int = 0, retain: bool = False
    ) -> bool:
        """
        Publish an event to Redis for consumption by external MQTT service

        Args:
            topic: MQTT topic
            payload: Message payload
            qos: Quality of Service level
            retain: Whether to retain the message

        Returns:
            bool: True if published successfully, False otherwise
        """
        if not self.redis_client:
            logger.warning("Redis client not available, attempting to reconnect...")
            self._initialize_redis()
            if not self.redis_client:
                logger.error("Redis reconnection failed")
                return False

        try:
            self.redis_client.ping()
        except Exception as e:
            logger.warning("Redis ping failed, reinitializing: %s", e)
            self._initialize_redis()
            if not self.redis_client:
                logger.error("Redis reconnection failed")
                return False

        try:
            event = {
                "topic": topic,
                "payload": payload,
                "qos": qos,
                "retain": retain,
                "timestamp": time.time(),
            }

            # Publish to Redis list (consumed by bridge)
            self.redis_client.lpush(EVENTS_LIST_KEY, json.dumps(event))
            logger.debug("Published event to Redis: topic=%s qos=%s", topic, qos)

            # Copy to monitor list for web UI (stream of what NEMO publishes)
            self.redis_client.lpush(MONITOR_LIST_KEY, json.dumps(event))
            self.redis_client.ltrim(MONITOR_LIST_KEY, 0, MONITOR_LIST_MAXLEN - 1)

            return True

        except Exception as e:
            logger.error("Failed to publish event to Redis: %s", e)
            return False

    def get_monitor_messages(self) -> list:
        """
        Return recent events from the monitor list (what NEMO has published to Redis).
        Used by the web monitor to show a stream of plugin output without subscribing to MQTT.
        """
        if not self.redis_client:
            return []
        try:
            self.redis_client.ping()
        except Exception:
            return []
        raw = self.redis_client.lrange(MONITOR_LIST_KEY, 0, -1)
        messages = []
        for i, s in enumerate(raw):
            try:
                event = json.loads(s)
                ts = event.get("timestamp")
                if ts is not None:
                    timestamp = (
                        datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%S.%f")
                        + "Z"
                    )
                else:
                    timestamp = None
                messages.append(
                    {
                        "id": i + 1,
                        "timestamp": timestamp,
                        "source": "Redis",
                        "topic": event.get("topic", ""),
                        "payload": event.get("payload", ""),
                        "qos": event.get("qos", 0),
                        "retain": event.get("retain", False),
                    }
                )
            except (json.JSONDecodeError, TypeError):
                continue
        return messages

    def is_available(self) -> bool:
        """Check if Redis is available"""
        if not self.redis_client:
            return False

        try:
            self.redis_client.ping()
            return True
        except Exception:
            return False

    def get_bridge_status(self) -> Optional[str]:
        """
        Return the Redis-MQTT bridge status from Redis: "connected", "disconnected", or None (unknown).
        The bridge writes this key when it connects/disconnects from the broker.
        """
        if not self.redis_client:
            return None
        try:
            self.redis_client.ping()
        except Exception:
            return None
        try:
            value = self.redis_client.get(BRIDGE_STATUS_KEY)
            if value in ("connected", "disconnected"):
                return value
        except Exception:
            pass
        return None


# Global instance
redis_publisher = RedisMQTTPublisher()


def publish_mqtt_event(
    topic: str, payload: str, qos: int = 0, retain: bool = False
) -> bool:
    """
    Convenience function to publish MQTT events via Redis

    Args:
        topic: MQTT topic
        payload: Message payload
        qos: Quality of Service level
        retain: Whether to retain the message

    Returns:
        bool: True if published successfully, False otherwise
    """
    return redis_publisher.publish_event(topic, payload, qos, retain)


def notify_bridge_reload_config() -> bool:
    """
    Notify the Redis-MQTT bridge to reload configuration (disconnect and reconnect to broker).
    Call this after saving MQTT configuration so the running bridge picks up the new settings.
    """
    try:
        client = redis_publisher.redis_client
        if client is None:
            client = redis.Redis(
                host="localhost",
                port=6379,
                db=1,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        client.lpush(BRIDGE_CONTROL_KEY, "reload_config")
        logger.debug("Notified bridge to reload config")
        return True
    except Exception as e:
        logger.warning("Failed to notify bridge to reload config: %s", e)
        return False

"""
PostgreSQL-based MQTT Event Publisher for NEMO.

Django signals write events to MQTTEventQueue and use pg_notify to wake the bridge.
The bridge consumes via LISTEN and publishes to MQTT. Requires PostgreSQL.
"""

import logging
from datetime import datetime
from typing import Optional

from django.db import connection

from .models import MQTTEventQueue, MQTTBridgeStatus

logger = logging.getLogger(__name__)

NOTIFY_CHANNEL_EVENTS = "nemo_mqtt_events"
NOTIFY_CHANNEL_RELOAD = "nemo_mqtt_reload"
MONITOR_LIMIT = 100


def _is_postgresql() -> bool:
    """Check if the database is PostgreSQL (required for LISTEN/NOTIFY)."""
    return connection.vendor == "postgresql"


class DBPublisher:
    """Publishes MQTT events to PostgreSQL queue for consumption by the bridge."""

    def __init__(self):
        self._available = None

    def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        self._available = _is_postgresql()
        if not self._available:
            logger.warning("Database is not PostgreSQL; LISTEN/NOTIFY unavailable")
        return self._available

    def publish_event(
        self, topic: str, payload: str, qos: int = 0, retain: bool = False
    ) -> bool:
        """
        Publish an event to the queue for consumption by the bridge.

        Args:
            topic: MQTT topic
            payload: Message payload
            qos: Quality of Service level
            retain: Whether to retain the message

        Returns:
            bool: True if published successfully, False otherwise
        """
        if not self._check_available():
            return False

        try:
            event = MQTTEventQueue.objects.create(
                topic=topic,
                payload=payload,
                qos=qos,
                retain=retain,
                processed=False,
            )
            self._pg_notify(NOTIFY_CHANNEL_EVENTS, str(event.id))
            logger.debug("Published event to queue: topic=%s qos=%s", topic, qos)
            return True
        except Exception as e:
            logger.error("Failed to publish event to queue: %s", e)
            return False

    def _pg_notify(self, channel: str, payload: str = "") -> None:
        """Send a PostgreSQL NOTIFY."""
        if not _is_postgresql():
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_notify(%s, %s)",
                    [channel, payload],
                )
        except Exception as e:
            logger.debug("pg_notify failed: %s", e)

    def get_monitor_messages(self) -> list:
        """
        Return recent events from the queue (for monitor display).
        """
        if not self._check_available():
            return []
        try:
            events = (
                MQTTEventQueue.objects.order_by("-created_at")[:MONITOR_LIMIT]
                .values("id", "topic", "payload", "qos", "retain", "created_at")
            )
            messages = []
            for i, ev in enumerate(reversed(list(events)), 1):
                ts = ev.get("created_at")
                timestamp = (
                    ts.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
                    if ts
                    else None
                )
                messages.append(
                    {
                        "id": i,
                        "timestamp": timestamp,
                        "source": "PostgreSQL",
                        "topic": ev.get("topic", ""),
                        "payload": ev.get("payload", ""),
                        "qos": ev.get("qos", 0),
                        "retain": ev.get("retain", False),
                    }
                )
            return messages
        except Exception as e:
            logger.debug("get_monitor_messages failed: %s", e)
            return []

    def is_available(self) -> bool:
        """Check if the publisher is available (PostgreSQL)."""
        return self._check_available()

    def get_bridge_status(self) -> Optional[str]:
        """
        Return the bridge status from DB: "connected", "disconnected", or None.
        """
        if not self._check_available():
            return None
        try:
            status = MQTTBridgeStatus.objects.filter(key="default").first()
            if status and status.status in ("connected", "disconnected"):
                return status.status
        except Exception:
            pass
        return None


# Global instance
db_publisher = DBPublisher()


def publish_mqtt_event(
    topic: str, payload: str, qos: int = 0, retain: bool = False
) -> bool:
    """
    Convenience function to publish MQTT events via the queue.

    Args:
        topic: MQTT topic
        payload: Message payload
        qos: Quality of Service level
        retain: Whether to retain the message

    Returns:
        bool: True if published successfully, False otherwise
    """
    return db_publisher.publish_event(topic, payload, qos, retain)


def notify_bridge_reload_config() -> bool:
    """
    Notify the bridge to reload configuration via pg_notify.
    Call this after saving MQTT configuration.
    """
    if not _is_postgresql():
        return False
    try:
        db_publisher._pg_notify(NOTIFY_CHANNEL_RELOAD, "")
        logger.debug("Notified bridge to reload config")
        return True
    except Exception as e:
        logger.warning("Failed to notify bridge to reload config: %s", e)
        return False

"""
Django signal handlers for MQTT plugin.
These signals will trigger MQTT message publishing when NEMO events occur.
"""

import json
import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from django.core.cache import cache

from .models import MQTTConfiguration


# Check if NEMO is available
def _check_nemo_availability():
    """Check if NEMO is available and return the models if so"""
    try:
        from NEMO.models import (
            Tool,
            Area,
            User,
            Reservation,
            UsageEvent,
            AreaAccessRecord,
        )

        return True, Tool, Area, User, Reservation, UsageEvent, AreaAccessRecord
    except (ImportError, RuntimeError):
        return False, None, None, None, None, None, None


NEMO_AVAILABLE, Tool, Area, User, Reservation, UsageEvent, AreaAccessRecord = (
    _check_nemo_availability()
)

logger = logging.getLogger(__name__)


class MQTTSignalHandler:
    """Handles MQTT signal processing and message publishing via PostgreSQL queue"""

    def __init__(self):
        self.db_publisher = None
        self._initialize_db_publisher()

    def _initialize_db_publisher(self):
        """Initialize DB publisher for MQTT events"""
        try:
            from .db_publisher import db_publisher

            self.db_publisher = db_publisher
            logger.info("PostgreSQL MQTT publisher initialized")
        except Exception as e:
            logger.error(f"Failed to initialize DB publisher: {e}")
            self.db_publisher = None

    def _get_mqtt_config(self):
        """Get MQTT configuration from database"""
        try:
            config = MQTTConfiguration.objects.filter(enabled=True).first()
            if config:
                return config
            else:
                # Return default config if none found
                return MQTTConfiguration(
                    qos_level=1,  # Default to QoS 1 for reliability
                    retain_messages=False,
                )
        except Exception as e:
            logger.warning(f"Failed to get MQTT configuration: {e}")
            # Return default config on error
            return MQTTConfiguration(
                qos_level=1, retain_messages=False  # Default to QoS 1 for reliability
            )

    def publish_message(self, topic, data):
        """Publish a message via PostgreSQL queue to external MQTT service"""
        import uuid

        signal_id = str(uuid.uuid4())[:8]

        logger.debug(
            "Django Signal → DB Publisher: topic=%s data=%s",
            topic,
            json.dumps(data, indent=2),
        )

        if self.db_publisher:
            try:
                # Get MQTT configuration for QoS and retain settings
                config = self._get_mqtt_config()

                success = self.db_publisher.publish_event(
                    topic,
                    json.dumps(data),
                    qos=config.qos_level,
                    retain=config.retain_messages,
                )
                if success:
                    logger.debug(
                        "Successfully published to queue (signal_id=%s)",
                        signal_id,
                    )
                    logger.info(f"Successfully published to queue: {topic}")
                else:
                    logger.error(f"Failed to publish to queue: {topic}")
            except Exception as e:
                logger.error(f"Failed to publish MQTT message via queue: {e}")
        else:
            logger.warning("DB publisher not available")


# Global signal handler instance
logger.info("Initializing MQTT Signal Handler...")
signal_handler = MQTTSignalHandler()
logger.debug("MQTT Signal Handler initialized: %s", id(signal_handler))


# Only register signal handlers if NEMO is available
if NEMO_AVAILABLE:
    # Tool-related signals
    @receiver(post_save, sender=Tool)
    def tool_saved(sender, instance, created, **kwargs):
        """Signal handler for tool save events"""
        import uuid

        signal_id = str(uuid.uuid4())[:8]
        logger.debug(
            "Tool save event triggered: tool=%s (id=%s) created=%s operational=%s",
            instance.name,
            instance.id,
            created,
            instance.operational,
        )

        if signal_handler.db_publisher:
            action = "created" if created else "updated"
            data = {
                "event": f"tool_{action}",
                "tool_id": instance.id,
                "tool_name": instance.name,
                "tool_status": instance.operational,
                "timestamp": instance._state.adding,
            }
            logger.debug("Publishing tool_%s event (signal_id=%s)", action, signal_id)
            signal_handler.publish_message(f"nemo/tools/{instance.id}", data)
        else:
            logger.warning("DB publisher not available (tool_saved, signal_id=%s)", signal_id)

    @receiver(post_save, sender=Area)
    def area_saved(sender, instance, created, **kwargs):
        """Signal handler for area save events"""
        if signal_handler.db_publisher:
            action = "created" if created else "updated"
            data = {
                "event": f"area_{action}",
                "area_id": instance.id,
                "area_name": instance.name,
                "area_requires_reservation": instance.requires_reservation,
                "timestamp": instance._state.adding,
            }
            signal_handler.publish_message(f"nemo/areas/{instance.id}", data)

    # Reservation-related signals
    @receiver(post_save, sender=Reservation)
    def reservation_saved(sender, instance, created, **kwargs):
        """Signal handler for reservation save events"""
        if signal_handler.db_publisher:
            action = "created" if created else "updated"
            data = {
                "event": f"reservation_{action}",
                "reservation_id": instance.id,
                "user_id": instance.user.id,
                "user_name": instance.user.get_full_name(),
                "start_time": instance.start.isoformat() if instance.start else None,
                "end_time": instance.end.isoformat() if instance.end else None,
                "timestamp": instance._state.adding,
            }
            signal_handler.publish_message(f"nemo/reservations/{instance.id}", data)

    # Usage event signals — SINGLE SOURCE OF TRUTH for tool enable/disable
    # NEMO (and nemo-ce) does not emit tool_enabled/tool_disabled signals; enable = new UsageEvent
    # (no end), disable = UsageEvent.save() with end set. This handler publishes to queue for both.
    @receiver(post_save, sender=UsageEvent)
    def usage_event_saved(sender, instance, created, **kwargs):
        """Publish tool usage start/end to queue. This is the only source for tool enable/disable."""
        import uuid

        signal_id = str(uuid.uuid4())[:8]

        if not signal_handler.db_publisher:
            logger.warning("DB publisher not available (usage_event_saved, signal_id=%s)", signal_id)
            return

        # End time set = tool disabled (usage ended); no end = tool enabled (usage started)
        if instance.end is not None:
            # Tool disabled / usage ended — publish only .../disabled (no .../end to avoid duplicate/conflicting status)
            disabled_data = {
                "event": "tool_disabled",
                "tool_id": instance.tool.id,
                "tool_name": instance.tool.name,
                "usage_id": instance.id,
                "user_name": instance.user.get_full_name(),
                "end_time": instance.end.isoformat() if instance.end else None,
            }
            signal_handler.publish_message(
                f"nemo/tools/{instance.tool.id}/disabled", disabled_data
            )
            logger.debug("Disabled event published to queue (signal_id=%s)", signal_id)
        else:
            # Tool enabled / usage started — publish only .../enabled (no .../start to avoid duplicate status)
            logger.debug("No end time - publishing tool_enabled (signal_id=%s)", signal_id)

            enabled_data = {
                "event": "tool_enabled",
                "tool_id": instance.tool.id,
                "tool_name": instance.tool.name,
                "usage_id": instance.id,
                "user_name": instance.user.get_full_name(),
                "start_time": instance.start.isoformat() if instance.start else None,
            }
            signal_handler.publish_message(
                f"nemo/tools/{instance.tool.id}/enabled", enabled_data
            )
            logger.debug("Enabled event published to queue (signal_id=%s)", signal_id)

        logger.debug("Signal processing complete (signal_id=%s)", signal_id)
        logger.info(f"Published events for UsageEvent {instance.id}")

    # Area access signals
    @receiver(post_save, sender=AreaAccessRecord)
    def area_access_saved(sender, instance, created, **kwargs):
        """Signal handler for area access save events"""
        if signal_handler.db_publisher and created:
            data = {
                "event": "area_access",
                "access_id": instance.id,
                "user_id": instance.customer.id,
                "user_name": instance.customer.get_full_name(),
                "area_id": instance.area.id,
                "area_name": instance.area.name,
                "access_time": instance.start.isoformat() if instance.start else None,
                "timestamp": instance._state.adding,
            }
            signal_handler.publish_message(f"nemo/area_access/{instance.id}", data)

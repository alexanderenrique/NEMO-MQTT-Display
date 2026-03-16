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
from django.utils import timezone

from .models import MQTTConfiguration, MQTTEventFilter


def _event_filter_enabled(event_type: str) -> bool:
    """Return True if this event type should be published (default True if no filter row)."""
    try:
        filt = MQTTEventFilter.objects.get(event_type=event_type)
        return filt.enabled
    except (MQTTEventFilter.DoesNotExist, Exception):
        return True


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
            Task,
        )

        return True, Tool, Area, User, Reservation, UsageEvent, AreaAccessRecord, Task
    except (ImportError, RuntimeError):
        return False, None, None, None, None, None, None, None


(
    NEMO_AVAILABLE,
    Tool,
    Area,
    User,
    Reservation,
    UsageEvent,
    AreaAccessRecord,
    Task,
) = _check_nemo_availability()

# Try to import NEMO's custom tool operational signals.
try:
    from NEMO.signals import tool_enabled as nemo_tool_enabled, tool_disabled as nemo_tool_disabled
except (ImportError, RuntimeError):  # pragma: no cover - depends on NEMO being installed
    nemo_tool_enabled = None
    nemo_tool_disabled = None

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
        """Get MQTT configuration from database (uses guarded utils to avoid DB query during migrations)"""
        from .utils import get_mqtt_config

        config = get_mqtt_config()
        if config:
            return config
        # Return default config if none found or table not yet migrated
        return MQTTConfiguration(
            qos_level=1,  # Default to QoS 1 for reliability
            retain_messages=False,
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
        if not _event_filter_enabled("usage_event_save"):
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

    # Tool operational / non-operational signals (distinct from usage)
    if nemo_tool_enabled is not None and nemo_tool_disabled is not None:

        @receiver(nemo_tool_enabled, sender=Tool)
        def tool_operational(sender, instance: Tool, **kwargs):
            """
            Publish an event when a tool becomes operational again.
            This reflects tool.operational transitions (up/down), independent of usage.
            """
            if not signal_handler.db_publisher:
                logger.warning("DB publisher not available (tool_operational)")
                return
            if not _event_filter_enabled("tool_operational"):
                return

            data = {
                "event": "tool_operational",
                "tool_id": instance.id,
                "tool_name": instance.name,
                "operational": True,
                "timestamp": timezone.now().isoformat(),
            }

            topic = f"nemo/tools/{instance.id}/operational"
            logger.debug(
                "Publishing tool_operational event via queue: topic=%s data=%s",
                topic,
                json.dumps(data),
            )
            signal_handler.publish_message(topic, data)

    @receiver(post_save, sender=Task)
    def task_saved(sender, instance: Task, created: bool, **kwargs):
        """
        Publish per-tool task details (including problem_description) when tasks
        are created or updated. This runs for all tasks that are linked to a tool,
        regardless of force_shutdown or safety_hazard flags.

        This sends messages on a per-tool topic:
            nemo/tools/{tool_id}/tasks
        """
        if not signal_handler.db_publisher:
            logger.warning("DB publisher not available (task_saved)")
            return

        # Only consider tasks linked to a tool
        if not instance.tool_id:
            return

        # Check filter: task_created for new tasks, task_resolved for updates
        if created:
            if not _event_filter_enabled("task_created"):
                return
        else:
            if not _event_filter_enabled("task_resolved"):
                return

        # Determine event type:
        # - If the task forces shutdown or is a safety hazard, keep "task_shutdown"
        # - Otherwise, treat as a generic task update
        if instance.force_shutdown or instance.safety_hazard:
            event_type = "task_shutdown"
        else:
            event_type = "task_updated" if not created else "task_created"

        task = instance
        tool = task.tool

        data = {
            "event": event_type,
            "task_id": task.id,
            "tool_id": tool.id if tool else None,
            "tool_name": tool.name if tool else None,
            "problem_description": task.problem_description,
            "force_shutdown": bool(task.force_shutdown),
            "safety_hazard": bool(task.safety_hazard),
            "cancelled": bool(task.cancelled),
            "resolved": bool(task.resolved),
            "created_at": task.creation_time.isoformat() if task.creation_time else None,
            "updated_at": task.last_updated.isoformat() if task.last_updated else None,
        }

        topic = f"nemo/tools/{tool.id}/tasks" if tool else "nemo/tasks/unknown_tool"
        logger.debug(
            "Publishing task event via queue: topic=%s data=%s",
            topic,
            json.dumps(data),
        )
        signal_handler.publish_message(topic, data)

    if nemo_tool_enabled is not None and nemo_tool_disabled is not None:

        @receiver(nemo_tool_disabled, sender=Tool)
        def tool_non_operational(sender, instance: Tool, **kwargs):
            """
            Publish an event when a tool is marked non-operational (down).
            This is distinct from tool usage enable/disable and follows NEMO's
            operational status logic in determine_tool_status().
            """
            if not signal_handler.db_publisher:
                logger.warning("DB publisher not available (tool_non_operational)")
                return
            if not _event_filter_enabled("tool_non_operational"):
                return

            data = {
                "event": "tool_non_operational",
                "tool_id": instance.id,
                "tool_name": instance.name,
                "operational": False,
                "timestamp": timezone.now().isoformat(),
            }

            topic = f"nemo/tools/{instance.id}/non-operational"
            logger.debug(
                "Publishing tool_non_operational event via queue: topic=%s data=%s",
                topic,
                json.dumps(data),
            )
            signal_handler.publish_message(topic, data)

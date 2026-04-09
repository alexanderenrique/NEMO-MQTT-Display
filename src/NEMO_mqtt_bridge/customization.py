"""
MQTT Plugin Customization for NEMO.
"""

import logging

from NEMO.decorators import customization
from NEMO.views.customization import CustomizationBase
from .models import MQTTConfiguration, MQTTEventFilter, MQTTEventQueue, MQTTMessageLog

# Event types shown as checkboxes on the MQTT customization page.
# We keep the underlying event keys separate, but the UI groups some of them.
MQTT_EVENT_CHECKBOX_KEYS = [
    "usage_event_save",      # Enable/Disable (tool usage)
    "tool_operational",      # Operational (grouped with tool_non_operational)
    "tool_non_operational",  # Non-operational (grouped)
    "task_created",          # Task created (grouped with task_resolved)
    "task_resolved",         # Task resolved / updated (grouped)
]

logger = logging.getLogger(__name__)


def _log_config(
    config, broker_password: bool = False, hmac_key_set: bool = False
) -> None:
    """Log current MQTT configuration (sensitive values masked).

    The actual broker password and HMAC secret key are never logged; only whether they are set.
    """
    password_display = "***" if config.password else "(not set)"
    hmac_display = "***" if config.hmac_secret_key else "(not set)"
    lines = [
        "MQTT configuration saved",
        f"  name: {config.name}",
        f"  enabled: {config.enabled}",
        f"  broker_host: {config.broker_host}",
        f"  broker_port: {config.broker_port}",
        f"  keepalive: {config.keepalive}",
        f"  client_id: {config.client_id}",
        f"  username: {config.username or '(not set)'}",
        f"  password: {password_display}",
        f"  use_hmac: {config.use_hmac}",
        f"  hmac_secret_key: {hmac_display}",
        "  hmac_algorithm: sha256 (fixed)",
        f"  topic_prefix: {config.topic_prefix}",
        f"  qos_level: {config.qos_level}",
        f"  retain_messages: {config.retain_messages}",
        f"  clean_session: {config.clean_session}",
        f"  auto_reconnect: {config.auto_reconnect}",
        f"  reconnect_delay: {config.reconnect_delay}",
        f"  max_reconnect_attempts: {config.max_reconnect_attempts}",
        f"  log_messages: {config.log_messages}",
        f"  log_level: {config.log_level}",
    ]
    for line in lines:
        logger.info(line)


@customization("mqtt", "MQTT Plugin")
class MQTTCustomization(CustomizationBase):
    """
    Customization class for MQTT plugin configuration.
    """

    def template(self) -> str:
        """Return the template path for MQTT customization."""
        # Let the parent class handle template discovery automatically
        # This will look for templates in the plugin's templates directory first
        return super().template()

    def context(self) -> dict:
        """Return context data for the MQTT customization template."""
        # Get the base context from parent class
        context_dict = super().context()

        try:
            from . import __version__ as plugin_version
        except Exception:
            plugin_version = None

        # Get the single MQTT configuration (create one if none exists)
        import os
        import socket

        # Create unique client ID using hostname and process ID
        unique_client_id = f"nemo_{socket.gethostname()}_{os.getpid()}"

        config, created = MQTTConfiguration.objects.get_or_create(
            defaults={
                "name": "Default MQTT Configuration",
                "enabled": False,
                "broker_host": "localhost",
                "broker_port": 1883,
                "client_id": unique_client_id,
                "topic_prefix": "nemo/",
                "qos_level": 1,
                "retain_messages": False,
                "clean_session": True,
                "auto_reconnect": True,
                "reconnect_delay": 5,
                "max_reconnect_attempts": 10,
                "log_messages": True,
                "log_level": "INFO",
            }
        )

        recent_messages = MQTTMessageLog.objects.order_by("-sent_at")[:5]
        pending_queue_count = MQTTEventQueue.objects.filter(processed=False).count()
        pending_queue_oldest = (
            MQTTEventQueue.objects.filter(processed=False)
            .order_by("created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        pending_queue_newest = (
            MQTTEventQueue.objects.filter(processed=False)
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )
        recent_queue_events = (
            MQTTEventQueue.objects.order_by("-id").values(
                "id", "topic", "qos", "retain", "processed", "created_at"
            )[:5]
        )
        try:
            from .db_publisher import db_publisher

            bridge_status = db_publisher.get_bridge_status()
        except Exception:
            bridge_status = None

        bridge_last_heartbeat_iso = None
        try:
            from .models import MQTTBridgeStatus

            hb_row = MQTTBridgeStatus.objects.filter(key="default").first()
            if hb_row and hb_row.last_heartbeat:
                bridge_last_heartbeat_iso = hb_row.last_heartbeat.isoformat()
        except Exception:
            pass

        # Build dict of event_type -> enabled for checkbox event types (default True if no row)
        try:
            filters = {
                key: MQTTEventFilter.objects.filter(event_type=key).first()
                for key in MQTT_EVENT_CHECKBOX_KEYS
            }
            mqtt_event_filters = {
                key: filt.enabled if filt else True
                for key, filt in filters.items()
            }
        except Exception:
            mqtt_event_filters = {key: True for key in MQTT_EVENT_CHECKBOX_KEYS}

        context_dict.update(
            {
                "config": config,
                "recent_messages": recent_messages,
                "mqtt_event_filters": mqtt_event_filters,
                "bridge_status": bridge_status,
                "bridge_last_heartbeat_iso": bridge_last_heartbeat_iso,
                "pending_queue_count": pending_queue_count,
                "pending_queue_oldest": pending_queue_oldest,
                "pending_queue_newest": pending_queue_newest,
                "recent_queue_events": list(recent_queue_events),
                "plugin_version": plugin_version,
            }
        )

        return context_dict

    def validate(self, request) -> list:
        """Validate MQTT configuration data."""
        errors = []
        # Add any validation logic here if needed
        return errors

    def save(self, request, element=None):
        """Save MQTT configuration data."""
        from django.contrib import messages

        # Get the single MQTT configuration
        config, created = MQTTConfiguration.objects.get_or_create(
            defaults={"name": "Default MQTT Configuration"}
        )

        # Update configuration with form data
        config.name = request.POST.get("mqtt_name", config.name)
        config.enabled = request.POST.get("mqtt_enabled") == "enabled"
        config.broker_host = request.POST.get("mqtt_broker_host", config.broker_host)
        config.broker_port = int(
            request.POST.get("mqtt_broker_port", config.broker_port)
        )
        config.keepalive = int(request.POST.get("mqtt_keepalive", config.keepalive))
        config.client_id = request.POST.get("mqtt_client_id", config.client_id)
        config.username = (
            request.POST.get("mqtt_broker_username", config.username) or None
        )
        broker_password = request.POST.get("mqtt_broker_password", "")
        if broker_password:
            config.password = broker_password
        # else: leave config.password unchanged (blank in form = keep current)

        # HMAC message authentication
        config.use_hmac = request.POST.get("mqtt_use_hmac") == "enabled"
        hmac_key = request.POST.get("mqtt_hmac_secret_key", "")
        if hmac_key:
            config.hmac_secret_key = hmac_key
        config.hmac_algorithm = "sha256"  # Fixed; no longer configurable

        # Topic prefix is fixed to 'nemo/' for all events
        config.topic_prefix = "nemo/"
        config.qos_level = (
            1  # Fixed at 1 (at least once) for reliable delivery; not configurable
        )
        config.retain_messages = request.POST.get("mqtt_retain_messages") == "enabled"
        config.clean_session = request.POST.get("mqtt_clean_session") == "enabled"
        config.auto_reconnect = request.POST.get("mqtt_auto_reconnect") == "enabled"
        config.reconnect_delay = int(
            request.POST.get("mqtt_reconnect_delay", config.reconnect_delay)
        )
        config.max_reconnect_attempts = int(
            request.POST.get(
                "mqtt_max_reconnect_attempts", config.max_reconnect_attempts
            )
        )
        config.log_messages = request.POST.get("mqtt_log_messages") == "enabled"
        config.log_level = request.POST.get("mqtt_log_level", config.log_level)

        config.save()

        # Save event-type checkboxes (create or update MQTTEventFilter rows)
        try:
            # Enable/Disable (usage events) - single checkbox controls usage_event_save
            usage_enabled = request.POST.get("mqtt_event_usage_event_save") == "enabled"
            MQTTEventFilter.objects.update_or_create(
                event_type="usage_event_save",
                defaults={"enabled": usage_enabled},
            )

            # Operational / Non-operational - single checkbox controls both
            op_group_enabled = (
                request.POST.get("mqtt_event_operational_group") == "enabled"
            )
            for key in ("tool_operational", "tool_non_operational"):
                MQTTEventFilter.objects.update_or_create(
                    event_type=key,
                    defaults={"enabled": op_group_enabled},
                )

            # Task created / Task resolved - single checkbox controls both
            task_group_enabled = request.POST.get("mqtt_event_task_group") == "enabled"
            for key in ("task_created", "task_resolved"):
                MQTTEventFilter.objects.update_or_create(
                    event_type=key,
                    defaults={"enabled": task_group_enabled},
                )
        except Exception:
            # Table may not exist yet; ignore failures here
            pass

        messages.success(request, "MQTT configuration saved successfully!")

        # Display configuration via logging (sensitive fields masked)
        _log_config(
            config, broker_password=bool(broker_password), hmac_key_set=bool(hmac_key)
        )

        return {}

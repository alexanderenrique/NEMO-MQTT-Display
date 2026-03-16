"""
Models for MQTT plugin configuration and message history.
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


class MQTTConfiguration(models.Model):
    """Configuration settings for MQTT plugin"""

    name = models.CharField(max_length=100, unique=True, help_text="Configuration name")
    enabled = models.BooleanField(
        default=True, help_text="Whether this configuration is active"
    )

    # Broker connection settings
    broker_host = models.CharField(
        max_length=255, default="localhost", help_text="MQTT broker hostname or IP"
    )
    broker_port = models.IntegerField(default=1883, help_text="MQTT broker port")
    keepalive = models.IntegerField(
        default=60, help_text="Keep alive interval in seconds"
    )
    client_id = models.CharField(
        max_length=100, default="nemo-mqtt-client", help_text="MQTT client ID"
    )

    # Authentication settings
    username = models.CharField(
        max_length=100, blank=True, null=True, help_text="MQTT username"
    )
    password = models.CharField(
        max_length=100, blank=True, null=True, help_text="MQTT password"
    )

    # HMAC message authentication (Hash-based Message Authentication Code)
    use_hmac = models.BooleanField(
        default=False,
        help_text="Sign MQTT payloads with HMAC for authenticity and integrity",
    )
    hmac_secret_key = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Shared secret key for HMAC signing (keep confidential)",
    )
    hmac_algorithm = models.CharField(
        max_length=20,
        default="sha256",
        help_text="Hash algorithm for HMAC (fixed at SHA-256)",
    )

    # Message settings
    topic_prefix = models.CharField(
        max_length=100, default="nemo", help_text="Topic prefix for all messages"
    )
    qos_level = models.IntegerField(
        default=1,
        choices=[(1, "At least once")],
        help_text="Quality of Service level (fixed at 1 for reliable delivery)",
    )
    retain_messages = models.BooleanField(
        default=False, help_text="Retain messages on broker"
    )
    clean_session = models.BooleanField(
        default=True, help_text="Start with a clean session"
    )

    # Connection settings
    auto_reconnect = models.BooleanField(
        default=True, help_text="Automatically reconnect on connection loss"
    )
    reconnect_delay = models.IntegerField(
        default=5, help_text="Delay between reconnection attempts (seconds)"
    )
    max_reconnect_attempts = models.IntegerField(
        default=10, help_text="Maximum reconnection attempts (0 = unlimited)"
    )

    # Logging settings
    log_messages = models.BooleanField(
        default=True, help_text="Log all MQTT messages to database"
    )
    log_level = models.CharField(
        max_length=20,
        default="INFO",
        choices=[
            ("DEBUG", "DEBUG"),
            ("INFO", "INFO"),
            ("WARNING", "WARNING"),
            ("ERROR", "ERROR"),
        ],
        help_text="Logging level for MQTT operations",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nemo_mqtt_mqttconfiguration"
        verbose_name = "MQTT Configuration"
        verbose_name_plural = "MQTT Configurations"

    def __str__(self):
        return f"{self.name} ({'Enabled' if self.enabled else 'Disabled'})"


class MQTTMessageLog(models.Model):
    """Log of MQTT messages sent by the plugin"""

    topic = models.CharField(max_length=500, help_text="MQTT topic")
    payload = models.TextField(help_text="Message payload")
    qos = models.IntegerField(default=0, help_text="Quality of Service level")
    retained = models.BooleanField(
        default=False, help_text="Whether message was retained"
    )
    success = models.BooleanField(
        default=True, help_text="Whether message was sent successfully"
    )
    error_message = models.TextField(
        blank=True, null=True, help_text="Error message if sending failed"
    )
    sent_at = models.DateTimeField(auto_now_add=True, help_text="When message was sent")

    class Meta:
        db_table = "nemo_mqtt_mqttmessagelog"
        verbose_name = "MQTT Message Log"
        verbose_name_plural = "MQTT Message Logs"
        ordering = ["-sent_at"]

    def __str__(self):
        status = "Success" if self.success else "Failed"
        return f"{self.topic} - {status} ({self.sent_at})"


class MQTTEventQueue(models.Model):
    """Queue of MQTT events for the bridge to consume via PostgreSQL LISTEN/NOTIFY."""

    topic = models.CharField(max_length=500)
    payload = models.TextField()
    qos = models.IntegerField(default=1)
    retain = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "nemo_mqtt_mqtt_eventqueue"
        verbose_name = "MQTT Event Queue"
        verbose_name_plural = "MQTT Event Queues"
        ordering = ["id"]

    def __str__(self):
        return f"{self.topic} ({'processed' if self.processed else 'pending'})"


class MQTTBridgeStatus(models.Model):
    """Bridge connection status for the monitor page (single row)."""

    key = models.CharField(
        max_length=20,
        unique=True,
        default="default",
        help_text="Singleton key for bridge status",
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ("connected", "Connected"),
            ("disconnected", "Disconnected"),
        ],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nemo_mqtt_mqttbridgestatus"
        verbose_name = "MQTT Bridge Status"
        verbose_name_plural = "MQTT Bridge Statuses"

    def __str__(self):
        return f"{self.status} at {self.updated_at}"


class MQTTEventFilter(models.Model):
    """Filter configuration for which events to publish via MQTT"""

    EVENT_TYPES = [
        ("tool_save", "Tool Save"),
        ("tool_delete", "Tool Delete"),
        ("area_save", "Area Save"),
        ("area_delete", "Area Delete"),
        ("reservation_save", "Reservation Save"),
        ("reservation_delete", "Reservation Delete"),
        ("usage_event_save", "Usage Event Save"),
        ("area_access_save", "Area Access Save"),
        ("tool_operational", "Tool Operational"),
        ("tool_non_operational", "Tool Non-Operational"),
        ("task_shutdown", "Task Shutdown (per-tool tasks topic)"),
        ("task_created", "Task Created"),
        ("task_resolved", "Task Resolved"),
    ]

    event_type = models.CharField(
        max_length=50, choices=EVENT_TYPES, help_text="Type of event to filter"
    )
    enabled = models.BooleanField(
        default=True, help_text="Whether this event type is enabled"
    )
    topic_override = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Custom topic for this event type",
    )
    include_payload = models.BooleanField(
        default=True, help_text="Whether to include full payload data"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nemo_mqtt_mqtteventfilter"
        verbose_name = "MQTT Event Filter"
        verbose_name_plural = "MQTT Event Filters"
        unique_together = ["event_type"]

    def __str__(self):
        return f"{self.get_event_type_display()} ({'Enabled' if self.enabled else 'Disabled'})"


# Signal handlers to clear cache when MQTT configuration changes
@receiver(post_save, sender=MQTTConfiguration)
def clear_mqtt_config_cache_on_save(sender, instance, **kwargs):
    """Clear the MQTT configuration cache when a configuration is saved and notify bridge to reload."""
    cache.delete("mqtt_active_config")
    from .db_publisher import notify_bridge_reload_config

    notify_bridge_reload_config()


@receiver(post_delete, sender=MQTTConfiguration)
def clear_mqtt_config_cache_on_delete(sender, instance, **kwargs):
    """Clear the MQTT configuration cache when a configuration is deleted"""
    cache.delete("mqtt_active_config")

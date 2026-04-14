"""
Models for MQTT plugin configuration and message history.
"""

import logging

from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.db.models import Q
from django.dispatch import receiver

logger = logging.getLogger(__name__)


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
        constraints = [
            # Enforce: at most one enabled config row.
            # Partial unique index (PostgreSQL) on enabled=True.
            models.UniqueConstraint(
                fields=["enabled"],
                condition=Q(enabled=True),
                name="nemo_mqtt_unique_enabled_configuration",
            )
        ]

    def __str__(self):
        return f"{self.name} ({'Enabled' if self.enabled else 'Disabled'})"

    def clean(self):
        super().clean()
        if not self.enabled:
            return
        qs = MQTTConfiguration.objects.filter(enabled=True)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                {"enabled": "Only one MQTT configuration can be enabled at a time."}
            )


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
    """Bridge connection status for the JSON status API (single row)."""

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
    last_heartbeat = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set periodically by the bridge while the consumption loop runs; used for optional supervisor health checks",
    )
    bridge_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text="Last reload reason, applied config fingerprint, etc. (written by bridge; no secrets)",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "nemo_mqtt_mqttbridgestatus"
        verbose_name = "MQTT Bridge Status"
        verbose_name_plural = "MQTT Bridge Statuses"

    def __str__(self):
        return f"{self.status} at {self.updated_at}"


# Signal handlers to clear cache when MQTT configuration changes
@receiver(post_save, sender=MQTTConfiguration)
def clear_mqtt_config_cache_on_save(sender, instance, **kwargs):
    """Clear the MQTT configuration cache when a configuration is saved and notify bridge to reload."""
    from django.db import transaction

    cache.delete("mqtt_active_config")
    from .db_publisher import notify_bridge_reload_config

    u = instance.updated_at.isoformat() if instance.updated_at else None
    logger.debug(
        "MQTTConfiguration post_save pk=%s enabled=%s updated_at=%s cleared "
        "mqtt_active_config scheduling bridge notify on_commit",
        instance.pk,
        instance.enabled,
        u,
    )
    transaction.on_commit(notify_bridge_reload_config)


@receiver(post_delete, sender=MQTTConfiguration)
def clear_mqtt_config_cache_on_delete(sender, instance, **kwargs):
    """Clear the MQTT configuration cache when a configuration is deleted."""
    from django.db import transaction

    cache.delete("mqtt_active_config")
    from .db_publisher import notify_bridge_reload_config

    logger.debug(
        "MQTTConfiguration post_delete pk=%s had_enabled=%s cleared "
        "mqtt_active_config scheduling bridge notify on_commit",
        instance.pk,
        instance.enabled,
    )
    transaction.on_commit(notify_bridge_reload_config)

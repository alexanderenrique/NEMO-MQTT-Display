"""
Admin interface for MQTT plugin models.
"""

from django.contrib import admin
from .models import MQTTConfiguration, MQTTMessageLog, MQTTEventFilter


@admin.register(MQTTConfiguration)
class MQTTConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "enabled",
        "broker_host",
        "broker_port",
        "use_hmac",
        "connection_status",
        "created_at",
    ]
    list_filter = ["enabled", "use_hmac", "log_level", "created_at"]
    search_fields = ["name", "broker_host", "client_id"]
    readonly_fields = ["created_at", "updated_at", "connection_status"]

    fieldsets = (
        ("Basic Settings", {"fields": ("name", "enabled", "connection_status")}),
        (
            "Broker Connection",
            {"fields": ("broker_host", "broker_port", "keepalive", "client_id")},
        ),
        (
            "Authentication",
            {"fields": ("username", "password"), "classes": ("collapse",)},
        ),
        (
            "HMAC Message Authentication",
            {"fields": ("use_hmac", "hmac_secret_key"), "classes": ("collapse",)},
        ),
        (
            "Message Settings",
            {
                "fields": (
                    "topic_prefix",
                    "qos_level",
                    "retain_messages",
                    "clean_session",
                )
            },
        ),
        (
            "Connection Management",
            {
                "fields": (
                    "auto_reconnect",
                    "reconnect_delay",
                    "max_reconnect_attempts",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Logging",
            {"fields": ("log_messages", "log_level"), "classes": ("collapse",)},
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def connection_status(self, obj):
        """Display current connection status"""
        if not obj.enabled:
            return "Disabled"
        try:
            from .signals import signal_handler

            if signal_handler.db_publisher:
                if signal_handler.db_publisher.is_available():
                    return "PostgreSQL Connected (Bridge Required)"
                else:
                    return "PostgreSQL Unavailable"
            else:
                return "Not Initialized"
        except Exception:
            return "Unknown"

    connection_status.short_description = "Connection Status"


@admin.register(MQTTMessageLog)
class MQTTMessageLogAdmin(admin.ModelAdmin):
    list_display = ["topic", "success", "sent_at", "qos", "retained"]
    list_filter = ["success", "qos", "retained", "sent_at"]
    search_fields = ["topic", "payload", "error_message"]
    readonly_fields = ["sent_at"]
    date_hierarchy = "sent_at"

    def has_add_permission(self, request):
        return False  # Prevent manual creation of log entries


@admin.register(MQTTEventFilter)
class MQTTEventFilterAdmin(admin.ModelAdmin):
    list_display = [
        "event_type",
        "enabled",
        "topic_override",
        "include_payload",
        "updated_at",
    ]
    list_filter = ["enabled", "include_payload", "updated_at"]
    search_fields = ["event_type", "topic_override"]
    fieldsets = (
        ("Event Settings", {"fields": ("event_type", "enabled")}),
        ("Topic Configuration", {"fields": ("topic_override", "include_payload")}),
    )

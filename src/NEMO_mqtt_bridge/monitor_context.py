"""
Server-side context for the MQTT customization page (no NEMO customization imports).
"""

from .models import MQTTConfiguration

_MQTT_CONFIG_DEFAULTS = {
    "name": "Default MQTT Configuration",
    "enabled": False,
    "broker_host": "localhost",
    "broker_port": 1883,
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


def mqtt_config_context() -> dict:
    """Context for the MQTT customization form (config row + plugin version)."""
    try:
        from . import __version__ as plugin_version
    except Exception:
        plugin_version = None

    import os
    import socket

    unique_client_id = f"nemo_{socket.gethostname()}_{os.getpid()}"
    defaults = {**_MQTT_CONFIG_DEFAULTS, "client_id": unique_client_id}
    config, _created = MQTTConfiguration.objects.get_or_create(defaults=defaults)

    return {
        "config": config,
        "plugin_version": plugin_version,
    }

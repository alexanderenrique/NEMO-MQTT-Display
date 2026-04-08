import atexit
import logging
import os
import threading
import time

from django.apps import AppConfig

from .lifecycle_log import lifecycle_log_prefix

logger = logging.getLogger(__name__)

_bridge_atexit_registered = False


def should_run_bridge_in_django() -> bool:
    """
    When False, Django does not spawn the bridge thread; run
    python -m NEMO_mqtt_bridge.postgres_mqtt_bridge (or systemd) separately.

    Env ``NEMO_MQTT_BRIDGE_RUN_IN_DJANGO``: ``1``/``true``/``yes``/``on``
    enables in-process bridge; ``0``/``false``/``no``/``off`` disables.
    If unset, the Django setting ``NEMO_MQTT_BRIDGE_RUN_IN_DJANGO`` is used
    when present.

    Default is False (standalone bridge; recommended for Docker/production).
    Set env ``1`` or ``NEMO_MQTT_BRIDGE_RUN_IN_DJANGO = True`` in settings for
    simple local dev without a separate bridge process.
    """
    env_val = os.environ.get("NEMO_MQTT_BRIDGE_RUN_IN_DJANGO", "").strip().lower()
    if env_val in ("0", "false", "no", "off"):
        return False
    if env_val in ("1", "true", "yes", "on"):
        return True
    try:
        from django.conf import settings

        if hasattr(settings, "NEMO_MQTT_BRIDGE_RUN_IN_DJANGO"):
            return bool(settings.NEMO_MQTT_BRIDGE_RUN_IN_DJANGO)
    except Exception:
        pass
    return False


def _atexit_stop_mqtt_bridge():
    try:
        from .postgres_mqtt_bridge import get_mqtt_bridge

        bridge = get_mqtt_bridge()
        if bridge.running:
            bridge.stop()
    except Exception:
        pass


class MqttPluginConfig(AppConfig):
    name = "NEMO_mqtt_bridge"
    label = "NEMO_mqtt_bridge"
    verbose_name = "MQTT Plugin"
    default_auto_field = "django.db.models.AutoField"
    _initialized = False
    _auto_service_started = False

    def ready(self):
        """
        Initialize the MQTT plugin when Django starts.
        Registers signal handlers; may start the bridge in-process if enabled.
        """
        # Prevent multiple initializations during development auto-reload
        if self._initialized:
            logger.info(
                "%s MQTT plugin already initialized, skipping...",
                lifecycle_log_prefix(),
            )
            return

        if self.get_migration_args():
            logger.info(
                "%s Migration detected, skipping MQTT plugin initialization",
                lifecycle_log_prefix(),
            )
            return

        # Check for NEMO dependencies (like nemo-publications plugin)
        try:
            from NEMO.plugins.utils import check_extra_dependencies

            check_extra_dependencies(self.name, ["NEMO", "NEMO-CE"])
        except ImportError:
            # NEMO.plugins.utils might not be available in all versions
            pass

        # Import signal handlers to register them immediately
        try:
            from . import signals  # noqa: F401
        except Exception as e:
            logger.warning(f"Failed to import signals: {e}")

        # Import customization to register it immediately
        try:
            from . import customization  # noqa: F401
        except Exception as e:
            logger.warning(f"Failed to import customization: {e}")

        # Mark as initialized to prevent multiple calls
        self._initialized = True
        logger.info(
            "%s MQTT plugin initialization started",
            lifecycle_log_prefix(),
        )

        # DB publisher for MQTT; start in-process bridge only if configured
        try:
            from .utils import get_mqtt_config

            config = get_mqtt_config()
            logger.info("%s MQTT config result: %s", lifecycle_log_prefix(), config)
            if config and config.enabled:
                logger.info(
                    "%s MQTT plugin initialized with enabled config: %s",
                    lifecycle_log_prefix(),
                    config.name,
                )
                logger.info(
                    "%s MQTT events will be published via PostgreSQL to MQTT " "broker",
                    lifecycle_log_prefix(),
                )
            else:
                logger.info(
                    "%s MQTT plugin loaded without enabled configuration; "
                    "bridge will idle until MQTT is enabled in customization",
                    lifecycle_log_prefix(),
                )

            if should_run_bridge_in_django():
                self._start_external_mqtt_service()
            else:
                logger.info(
                    "%s NEMO_MQTT_BRIDGE_RUN_IN_DJANGO is disabled; start the "
                    "bridge separately (e.g. python -m "
                    "NEMO_mqtt_bridge.postgres_mqtt_bridge)",
                    lifecycle_log_prefix(),
                )

        except Exception as e:
            logger.error(
                "%s Failed to initialize MQTT plugin: %s",
                lifecycle_log_prefix(),
                e,
            )

        logger.info(
            "%s MQTT plugin: Signal handlers and customization registered. "
            "Events will be published via PostgreSQL.",
            lifecycle_log_prefix(),
        )

    def _start_external_mqtt_service(self):
        """Start the PostgreSQL-MQTT Bridge service in a daemon thread."""
        global _bridge_atexit_registered
        if self._auto_service_started:
            logger.info(
                "%s PostgreSQL-MQTT Bridge already started, skipping...",
                lifecycle_log_prefix(),
            )
            return

        try:
            logger.info(
                "%s Starting PostgreSQL-MQTT Bridge service in-process...",
                lifecycle_log_prefix(),
            )

            from .postgres_mqtt_bridge import get_mqtt_bridge

            mqtt_bridge = get_mqtt_bridge()

            def run_bridge_service():
                try:
                    mqtt_bridge.start()
                    while mqtt_bridge.running:
                        time.sleep(1)
                except Exception as e:
                    logger.error(
                        "%s PostgreSQL-MQTT Bridge error: %s",
                        lifecycle_log_prefix(),
                        e,
                    )

            mqtt_thread = threading.Thread(target=run_bridge_service, daemon=True)
            mqtt_thread.start()

            self._auto_service_started = True
            if not _bridge_atexit_registered:
                atexit.register(_atexit_stop_mqtt_bridge)
                _bridge_atexit_registered = True
            logger.info(
                "%s PostgreSQL-MQTT Bridge thread started",
                lifecycle_log_prefix(),
            )

        except Exception as e:
            logger.error(
                "%s Failed to start PostgreSQL-MQTT Bridge: %s",
                lifecycle_log_prefix(),
                e,
            )
            logger.info(
                "%s MQTT events will still be enqueued, but the bridge "
                "process/thread is not running",
                lifecycle_log_prefix(),
            )

    def get_migration_args(self):
        """CLI args for migrate, makemigrations, showmigrations, etc."""
        import sys

        return [
            arg
            for arg in sys.argv
            if "migrate" in arg or "makemigrations" in arg or "showmigrations" in arg
        ]

    def disconnect_mqtt(self):
        """Stop in-process bridge (lock, MQTT, PostgreSQL)."""
        try:
            from .postgres_mqtt_bridge import get_mqtt_bridge

            bridge = get_mqtt_bridge()
            if bridge.running:
                bridge.stop()
                logger.info(
                    "%s PostgreSQL-MQTT Bridge stopped",
                    lifecycle_log_prefix(),
                )
        except Exception as e:
            logger.debug("disconnect_mqtt: %s", e)

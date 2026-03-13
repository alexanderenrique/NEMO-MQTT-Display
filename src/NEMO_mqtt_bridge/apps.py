from django.apps import AppConfig
from django.conf import settings
import logging
import threading
import time

logger = logging.getLogger(__name__)


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
        This sets up signal handlers and starts the PostgreSQL-MQTT Bridge service.
        """
        # Prevent multiple initializations during development auto-reload
        if self._initialized:
            logger.info("MQTT plugin already initialized, skipping...")
            return

        if "migrate" in self.get_migration_args():
            logger.info("Migration detected, skipping MQTT plugin initialization")
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
            from . import signals
        except Exception as e:
            logger.warning(f"Failed to import signals: {e}")

        # Import customization to register it immediately
        try:
            from . import customization
        except Exception as e:
            logger.warning(f"Failed to import customization: {e}")

        # Mark as initialized to prevent multiple calls
        self._initialized = True
        logger.info("MQTT plugin initialization started")

        # Initialize DB publisher for MQTT events
        try:
            from .utils import get_mqtt_config
            from .signals import signal_handler

            config = get_mqtt_config()
            logger.info(f"MQTT config result: {config}")
            if config and config.enabled:
                logger.info(
                    f"MQTT plugin initialized successfully with config: {config.name}"
                )
                logger.info("MQTT events will be published via PostgreSQL to MQTT broker")

                # Start the PostgreSQL-MQTT Bridge service automatically
                self._start_external_mqtt_service()
            else:
                logger.info("MQTT plugin loaded but no enabled configuration found")
                # Force start the bridge anyway for development
                logger.info("Starting PostgreSQL-MQTT Bridge anyway for development...")
                self._start_external_mqtt_service()

        except Exception as e:
            logger.error(f"Failed to initialize MQTT plugin: {e}")

        logger.info(
            "MQTT plugin: Signal handlers and customization registered. Events will be published via PostgreSQL."
        )

    def _start_external_mqtt_service(self):
        """Start the PostgreSQL-MQTT Bridge service automatically"""
        # Prevent multiple service starts
        if self._auto_service_started:
            logger.info("PostgreSQL-MQTT Bridge already started, skipping...")
            return

        try:
            logger.info("Starting PostgreSQL-MQTT Bridge service automatically...")

            # Import and get the singleton bridge instance
            from .postgres_mqtt_bridge import get_mqtt_bridge

            mqtt_bridge = get_mqtt_bridge()

            # Start the service in a separate thread
            def run_bridge_service():
                try:
                    mqtt_bridge.start()

                    # Keep the service running
                    while mqtt_bridge.running:
                        time.sleep(1)

                except Exception as e:
                    logger.error(f"PostgreSQL-MQTT Bridge error: {e}")

            # Start the service in a daemon thread
            mqtt_thread = threading.Thread(target=run_bridge_service, daemon=True)
            mqtt_thread.start()

            # Mark as started
            self._auto_service_started = True
            logger.info("PostgreSQL-MQTT Bridge started successfully")

        except Exception as e:
            logger.error(f"Failed to start PostgreSQL-MQTT Bridge: {e}")
            logger.info(
                "MQTT events will still be published to queue, but bridge service is not running"
            )

    def get_migration_args(self):
        """Get migration-related command line arguments"""
        import sys

        return [arg for arg in sys.argv if "migrate" in arg or "makemigrations" in arg]

    def disconnect_mqtt(self):
        """Disconnect MQTT client when app is shutting down"""
        if hasattr(self, "mqtt_client") and self.mqtt_client:
            self.mqtt_client.disconnect()
            logger.info("MQTT client disconnected during app shutdown")

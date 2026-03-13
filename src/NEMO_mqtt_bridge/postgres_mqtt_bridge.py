#!/usr/bin/env python3
"""
PostgreSQL-MQTT Bridge Service for NEMO Plugin.

NEMO publishes events to MQTTEventQueue and uses pg_notify (see db_publisher.py).
This bridge:
  1. Connects to PostgreSQL (Django DATABASES) and LISTENs for notifications
  2. Connects to the MQTT broker (plugin config)
  3. For each event from the queue, publishes to the broker

Requires PostgreSQL. Modes:
  - AUTO: Starts Mosquitto for development
  - EXTERNAL: Connects to existing services (production)
"""
import json
import logging
import os
import signal
import sys
import threading
import time

import paho.mqtt.client as mqtt

if __name__ == "__main__":
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    )
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings_dev")
    import django

    django.setup()

try:
    from NEMO_mqtt_bridge.models import MQTTConfiguration, MQTTEventQueue, MQTTBridgeStatus
    from NEMO_mqtt_bridge.utils import get_mqtt_config
except ImportError:
    from NEMO.plugins.NEMO_mqtt_bridge.models import (
        MQTTConfiguration,
        MQTTEventQueue,
        MQTTBridgeStatus,
    )
    from NEMO.plugins.NEMO_mqtt_bridge.utils import get_mqtt_config

try:
    from NEMO_mqtt_bridge.connection_manager import ConnectionManager
    from NEMO_mqtt_bridge.bridge.process_lock import acquire_lock, release_lock
    from NEMO_mqtt_bridge.bridge.auto_services import (
        cleanup_existing_services,
        start_mosquitto,
    )
    from NEMO_mqtt_bridge.bridge.mqtt_connection import connect_mqtt
except ImportError:
    from NEMO.plugins.NEMO_mqtt_bridge.connection_manager import ConnectionManager
    from NEMO.plugins.NEMO_mqtt_bridge.bridge.process_lock import acquire_lock, release_lock
    from NEMO.plugins.NEMO_mqtt_bridge.bridge.auto_services import (
        cleanup_existing_services,
        start_mosquitto,
    )
    from NEMO.plugins.NEMO_mqtt_bridge.bridge.mqtt_connection import connect_mqtt

logger = logging.getLogger(__name__)

NOTIFY_CHANNEL_EVENTS = "nemo_mqtt_events"
NOTIFY_CHANNEL_RELOAD = "nemo_mqtt_reload"
BRIDGE_STATUS_REFRESH_INTERVAL = 30


def _get_pg_connection_params():
    """Get PostgreSQL connection params from Django settings."""
    from django.conf import settings

    db = settings.DATABASES.get("default", {})
    if "postgresql" not in (db.get("ENGINE") or ""):
        raise RuntimeError("Database must be PostgreSQL for LISTEN/NOTIFY")
    params = {
        "host": db.get("HOST") or "localhost",
        "port": int(db.get("PORT") or 5432),
        "dbname": db.get("NAME"),
        "user": db.get("USER"),
        "password": db.get("PASSWORD"),
    }
    options = db.get("OPTIONS", {})
    if options:
        params.update(options)
    return params


def _write_bridge_status(status: str):
    """Update bridge status in DB for monitor page."""
    try:
        MQTTBridgeStatus.objects.update_or_create(
            key="default",
            defaults={"status": status},
        )
    except Exception as e:
        logger.debug("Could not write bridge status: %s", e)


class PostgresMQTTBridge:
    """Bridges PostgreSQL queue events to MQTT broker."""

    def __init__(self, auto_start: bool = False):
        self.auto_start = auto_start
        self.mqtt_client = None
        self.pg_conn = None
        self.running = False
        self.config = None
        self.thread = None
        self.lock_file = None
        self.mosquitto_process = None
        self.broker_host = None
        self.broker_port = None
        self.connection_count = 0
        self.last_connect_time = None
        self.last_disconnect_time = None
        self._last_disconnect_log_time = 0
        self._last_disconnect_rc = None
        self._disconnect_log_interval = 5
        self._last_reconnect_fail_log_time = 0
        self._last_reconnect_fail_msg = None
        self._reconnect_fail_log_interval = 30
        self._last_reconnecting_log_time = 0
        self._reconnecting_log_interval = 15
        self._mqtt_has_connected_before = False
        self._last_bridge_status_write = 0

        self.mqtt_connection_mgr = None
        self.pg_connection_mgr = ConnectionManager(
            max_retries=None,
            base_delay=1,
            max_delay=30,
            failure_threshold=5,
            success_threshold=3,
            timeout=60,
        )

        self.lock_file = acquire_lock()
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        logger.info("Received signal %s, shutting down", signum)
        self.stop()
        sys.exit(0)

    def start(self):
        """Start the bridge service."""
        try:
            mode = "AUTO" if self.auto_start else "EXTERNAL"
            logger.info("Starting PostgreSQL-MQTT Bridge (%s mode)", mode)

            self.config = get_mqtt_config()
            if not self.config or not self.config.enabled:
                logger.error("No enabled MQTT configuration found")
                return False

            if self.auto_start:
                cleanup_existing_services(None)
                self.mosquitto_process = start_mosquitto(self.config)

            self._initialize_pg()
            self._initialize_mqtt()

            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

            logger.info("PostgreSQL-MQTT Bridge started successfully")
            return True
        except Exception as e:
            logger.error("Failed to start bridge: %s", e)
            return False

    def _initialize_pg(self):
        """Connect to PostgreSQL for LISTEN."""
        import psycopg2
        from psycopg2 import extensions

        def connect():
            params = _get_pg_connection_params()
            conn = psycopg2.connect(**params)
            conn.set_isolation_level(extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            return conn

        self.pg_conn = self.pg_connection_mgr.connect_with_retry(connect)
        self.pg_conn.cursor().execute(f"LISTEN {NOTIFY_CHANNEL_EVENTS}")
        self.pg_conn.cursor().execute(f"LISTEN {NOTIFY_CHANNEL_RELOAD}")
        logger.info("Connected to PostgreSQL, listening for events")

    def _initialize_mqtt(self):
        if self.mqtt_client is not None:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except Exception as e:
                logger.debug("Cleanup of previous MQTT client: %s", e)
            self.mqtt_client = None

        self.config = get_mqtt_config()
        if not self.config or not self.config.enabled:
            raise RuntimeError("No enabled MQTT configuration")

        max_retries = (
            self.config.max_reconnect_attempts if self.config.max_reconnect_attempts else None
        )
        base_delay = getattr(self.config, "reconnect_delay", 5) or 5
        self.mqtt_connection_mgr = ConnectionManager(
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=60,
            failure_threshold=5,
            success_threshold=3,
            timeout=60,
        )

        def connect():
            self.config = get_mqtt_config()
            if not self.config or not self.config.enabled:
                raise RuntimeError("No enabled MQTT configuration")
            self.broker_host = self.config.broker_host or "localhost"
            self.broker_port = self.config.broker_port or 1883
            return connect_mqtt(
                self.config,
                self._on_connect,
                self._on_disconnect,
                self._on_publish,
            )

        self.mqtt_client = self.mqtt_connection_mgr.connect_with_retry(connect)
        self.connection_count += 1
        self.last_connect_time = time.time()
        self._last_reconnect_fail_msg = None
        logger.info(
            "Connected to MQTT broker at %s:%s", self.broker_host, self.broker_port
        )

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            _write_bridge_status("connected")
            if self._mqtt_has_connected_before:
                logger.info(
                    "Successfully reconnected to MQTT broker at %s:%s",
                    self.broker_host,
                    self.broker_port,
                )
            else:
                logger.info(
                    "Connected to MQTT broker at %s:%s",
                    self.broker_host,
                    self.broker_port,
                )
                self._mqtt_has_connected_before = True
        else:
            _write_bridge_status("disconnected")
            errors = {
                1: "protocol",
                2: "client id",
                3: "unavailable",
                4: "bad auth",
                5: "unauthorized",
            }
            logger.error("MQTT connection failed: %s (rc=%s)", errors.get(rc, rc), rc)

    def _on_disconnect(self, client, userdata, rc):
        self.last_disconnect_time = time.time()
        _write_bridge_status("disconnected")
        if rc != 0:
            now = time.time()
            rc_changed = self._last_disconnect_rc != rc
            interval_elapsed = (
                now - self._last_disconnect_log_time
            ) >= self._disconnect_log_interval
            if rc_changed or interval_elapsed or self._last_disconnect_log_time == 0:
                logger.warning("MQTT disconnected (rc=%s)", rc)
                self._last_disconnect_log_time = now
                self._last_disconnect_rc = rc

    def _on_publish(self, client, userdata, mid):
        logger.debug("Published mid=%s", mid)

    def _ensure_mqtt_connected(self):
        if self.mqtt_client and self.mqtt_client.is_connected():
            return True
        now = time.time()
        if (now - self._last_reconnecting_log_time) >= self._reconnecting_log_interval:
            logger.warning("MQTT disconnected, reconnecting...")
            self._last_reconnecting_log_time = now
        try:
            self._initialize_mqtt()
            return True
        except Exception as e:
            msg = str(e)
            should_log = (
                (now - self._last_reconnect_fail_log_time)
                >= self._reconnect_fail_log_interval
                or msg != self._last_reconnect_fail_msg
            )
            if should_log:
                logger.error("Reconnection failed: %s", e)
                self._last_reconnect_fail_log_time = now
                self._last_reconnect_fail_msg = msg
            return False

    def _run(self):
        """Main loop: LISTEN for notifications, fetch events, publish to MQTT."""
        level_name = getattr(self.config, "log_level", None) or "INFO"
        logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))
        logger.info("Starting consumption loop")

        while self.running:
            try:
                if not self._ensure_mqtt_connected():
                    time.sleep(5)
                    continue

                now = time.time()
                if (now - self._last_bridge_status_write) >= BRIDGE_STATUS_REFRESH_INTERVAL:
                    _write_bridge_status("connected")
                    self._last_bridge_status_write = now

                # Poll PostgreSQL for notifications
                if self.pg_conn:
                    self.pg_conn.poll()
                    for notify in self.pg_conn.notifies:
                        if notify.channel == NOTIFY_CHANNEL_RELOAD:
                            logger.info(
                                "Config reload requested, reconnecting to broker"
                            )
                            try:
                                from django.core.cache import cache

                                cache.delete("mqtt_active_config")
                            except Exception as e:
                                logger.debug("Could not clear config cache: %s", e)
                            self.config = get_mqtt_config(force_refresh=True)
                            level_name = getattr(
                                self.config, "log_level", None
                            ) or "INFO"
                            logger.setLevel(
                                getattr(logging, level_name.upper(), logging.INFO)
                            )
                            self._initialize_mqtt()
                        elif notify.channel == NOTIFY_CHANNEL_EVENTS:
                            self._process_pending_events()
                    self.pg_conn.notifies.clear()

                time.sleep(0.01)
            except Exception as e:
                logger.error("Service loop error: %s", e)
                time.sleep(1)

        logger.info("Consumption loop stopped")

    def _process_pending_events(self):
        """Fetch unprocessed events and publish to MQTT."""
        try:
            events = MQTTEventQueue.objects.filter(processed=False).order_by("id")
            for event in events:
                self._process_event(event)
                event.processed = True
                event.save(update_fields=["processed"])
        except Exception as e:
            logger.error("Failed to process events: %s", e)

    def _process_event(self, event):
        """Process a single event and publish to MQTT."""
        topic = event.topic
        payload = event.payload
        qos = event.qos
        retain = event.retain
        _secret = (self.config.hmac_secret_key or "") if self.config else ""
        logger.debug(
            "HMAC debug: hmac_secret_key=%r, topic=%s, raw_payload=%r",
            _secret,
            topic,
            payload,
        )
        if topic and payload is not None:
            self._publish_to_mqtt(topic, payload, qos, retain)
        else:
            logger.warning("Invalid event: missing topic or payload")

    def _publish_to_mqtt(
        self, topic: str, payload: str, qos: int = 0, retain: bool = False
    ):
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            logger.warning("MQTT not connected, cannot publish")
            return
        try:
            out_payload = payload
            if (
                self.config
                and getattr(self.config, "use_hmac", False)
                and getattr(self.config, "hmac_secret_key", None)
            ):
                try:
                    from NEMO_mqtt_bridge.utils import sign_payload_hmac
                except ImportError:
                    from NEMO.plugins.NEMO_mqtt_bridge.utils import sign_payload_hmac
                try:
                    out_payload = sign_payload_hmac(
                        payload,
                        self.config.hmac_secret_key,
                    )
                except Exception as e:
                    logger.warning("HMAC signing failed, publishing unsigned: %s", e)
            result = self.mqtt_client.publish(
                topic, out_payload, qos=qos, retain=retain
            )
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.error("Publish failed: rc=%s", result.rc)
        except Exception as e:
            logger.error("Publish failed: %s", e)

    def stop(self):
        """Stop the bridge service."""
        logger.info("Stopping PostgreSQL-MQTT Bridge")
        self.running = False
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        if self.pg_conn:
            try:
                self.pg_conn.close()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        if self.auto_start:
            cleanup_existing_services(None)
        release_lock(self.lock_file)
        logger.info("Bridge stopped")


_mqtt_bridge_instance = None
_mqtt_bridge_lock = threading.Lock()


def get_mqtt_bridge():
    """Get or create the global bridge instance."""
    global _mqtt_bridge_instance
    with _mqtt_bridge_lock:
        if _mqtt_bridge_instance is None:
            _mqtt_bridge_instance = PostgresMQTTBridge(auto_start=True)
        return _mqtt_bridge_instance


def main():
    import argparse

    parser = argparse.ArgumentParser(description="PostgreSQL-MQTT Bridge Service")
    parser.add_argument(
        "--auto", action="store_true", help="AUTO mode: start Mosquitto"
    )
    args = parser.parse_args()

    service = PostgresMQTTBridge(auto_start=args.auto)
    try:
        if service.start():
            mode = "AUTO" if args.auto else "EXTERNAL"
            logger.info("Bridge running in %s mode. Ctrl+C to stop.", mode)
            while service.running:
                time.sleep(1)
        else:
            sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()


if __name__ == "__main__":
    main()

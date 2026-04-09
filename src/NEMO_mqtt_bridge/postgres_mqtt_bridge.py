#!/usr/bin/env python3
"""
PostgreSQL-MQTT Bridge Service for NEMO Plugin.

NEMO publishes events to MQTTEventQueue and uses pg_notify (see db_publisher.py).
This bridge:
  1. Connects to PostgreSQL (Django DATABASES) and LISTENs for notifications
  2. Connects to the MQTT broker (plugin config)
  3. For each event from the queue, publishes to the broker

LISTEN/NOTIFY can miss events (no listener yet, connection poolers in transaction mode, etc.).
The consumption loop therefore also polls the queue on an interval so pending rows are drained
reliably whenever MQTT is connected.

Config reload uses NOTIFY (nemo_mqtt_reload) and the same polling idea: the enabled row's
(id, updated_at) fingerprint is checked on the queue poll interval so broker settings apply
even when NOTIFY is missed.

Requires PostgreSQL. Modes:
  - AUTO: Starts embedded MQTT broker (mqttools, pure Python)
  - EXTERNAL: Connects to existing services (production)

The bridge thread calls django.db.close_old_connections() each loop iteration because it
uses the ORM outside Django's per-request lifecycle.
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
    from NEMO_mqtt_bridge.lifecycle_log import lifecycle_log_prefix
except ImportError:
    from NEMO.plugins.NEMO_mqtt_bridge.connection_manager import ConnectionManager
    from NEMO.plugins.NEMO_mqtt_bridge.bridge.process_lock import acquire_lock, release_lock
    from NEMO.plugins.NEMO_mqtt_bridge.bridge.auto_services import (
        cleanup_existing_services,
        start_mosquitto,
    )
    from NEMO.plugins.NEMO_mqtt_bridge.bridge.mqtt_connection import connect_mqtt
    from NEMO.plugins.NEMO_mqtt_bridge.lifecycle_log import lifecycle_log_prefix

logger = logging.getLogger(__name__)

NOTIFY_CHANNEL_EVENTS = "nemo_mqtt_events"
NOTIFY_CHANNEL_RELOAD = "nemo_mqtt_reload"
BRIDGE_STATUS_REFRESH_INTERVAL = 30
# Fallback when NOTIFY is unreliable: scan MQTTEventQueue for pending rows.
QUEUE_POLL_INTERVAL = 2.0
# Written from the consumption loop so an optional supervisor can detect a wedged process.
BRIDGE_HEARTBEAT_INTERVAL = 15.0


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


def _touch_bridge_heartbeat():
    """Bump last_heartbeat without changing connection status (supervisor / ops visibility)."""
    try:
        from django.utils import timezone

        now = timezone.now()
        obj, _ = MQTTBridgeStatus.objects.get_or_create(
            key="default",
            defaults={"status": "disconnected"},
        )
        MQTTBridgeStatus.objects.filter(pk=obj.pk).update(last_heartbeat=now)
    except Exception as e:
        logger.debug("Could not write bridge heartbeat: %s", e)


def read_mqtt_config_fingerprint():
    """
    Return (id, updated_at) for the enabled MQTT configuration row, or None if none.
    Used to detect DB config changes when NOTIFY is unreliable.
    """
    try:
        return MQTTConfiguration.objects.filter(enabled=True).values_list(
            "id", "updated_at"
        ).first()
    except Exception as e:
        logger.debug("read_mqtt_config_fingerprint: %s", e)
        return None


def mqtt_config_reload_needed(stored_fingerprint, current_fingerprint) -> bool:
    """True if the bridge should reload MQTT from the database."""
    return stored_fingerprint != current_fingerprint


class PostgresMQTTBridge:
    """Bridges PostgreSQL queue events to MQTT broker."""

    def __init__(self, auto_start: bool = False, lock_fatal: bool = True):
        self.auto_start = auto_start
        self._lock_fatal = lock_fatal
        self._bridge_signals_registered = False
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
        self._last_queue_poll_time = 0.0
        # Last (id, updated_at) successfully applied to the MQTT client (None = no enabled row).
        self._mqtt_config_fingerprint = None
        self._bridge_stop_done = False
        self._last_heartbeat_monotonic = 0.0
        # Interrupt backoff sleep when config changes (notify/config poll).
        self._mqtt_wakeup_event = threading.Event()

        self.mqtt_connection_mgr = None
        self.pg_connection_mgr = ConnectionManager(
            max_retries=None,
            base_delay=1,
            max_delay=30,
            failure_threshold=5,
            success_threshold=3,
            timeout=60,
        )

    def _signal_handler(self, signum, frame):
        logger.info(
            "%s Received signal %s, shutting down",
            lifecycle_log_prefix(),
            signum,
        )
        self.stop()
        sys.exit(0)

    def start(self):
        """Start the bridge service (PostgreSQL listener always; MQTT when config enabled)."""
        self._bridge_stop_done = False
        if self.lock_file is None:
            lf = acquire_lock(fatal_if_locked=self._lock_fatal)
            if lf is None:
                return False
            self.lock_file = lf
            if self._lock_fatal and not self._bridge_signals_registered:
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
                self._bridge_signals_registered = True
        try:
            mode = "AUTO" if self.auto_start else "EXTERNAL"
            logger.info(
                "%s Starting PostgreSQL-MQTT Bridge (%s mode)",
                lifecycle_log_prefix(),
                mode,
            )

            self._initialize_pg()

            self.config = get_mqtt_config()
            has_enabled = bool(self.config and self.config.enabled)

            if has_enabled and self.auto_start:
                cleanup_existing_services(None)
                self.mosquitto_process = start_mosquitto(self.config)
            elif not has_enabled:
                logger.info(
                    "%s No enabled MQTT configuration; bridge will idle until config is enabled",
                    lifecycle_log_prefix(),
                )
                self.config = None

            if has_enabled:
                try:
                    self._initialize_mqtt()
                except Exception as e:
                    logger.error("Initial MQTT connection failed: %s", e)
                    self._disconnect_mqtt_client()
            else:
                self._disconnect_mqtt_client()

            self._mqtt_config_fingerprint = read_mqtt_config_fingerprint()

            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

            logger.info(
                "%s PostgreSQL-MQTT Bridge started successfully",
                lifecycle_log_prefix(),
            )
            return True
        except Exception as e:
            logger.error("Failed to start bridge: %s", e)
            self.running = False
            if self.mqtt_client:
                try:
                    self.mqtt_client.loop_stop()
                    self.mqtt_client.disconnect()
                except Exception:
                    pass
                self.mqtt_client = None
            if self.pg_conn:
                try:
                    self.pg_conn.close()
                except Exception:
                    pass
                self.pg_conn = None
            release_lock(self.lock_file)
            self.lock_file = None
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
        logger.info(
            "%s Connected to PostgreSQL, listening for events",
            lifecycle_log_prefix(),
        )

    def _reconnect_pg_listener(self):
        """Close and recreate the LISTEN connection after errors or disconnect."""
        if self.pg_conn is not None:
            try:
                self.pg_conn.close()
            except Exception as e:
                logger.debug("Closing PostgreSQL listener: %s", e)
            self.pg_conn = None
        self._initialize_pg()

    def _poll_pg_notifications(self):
        """Consume NOTIFY payloads; reconnect the listener if poll fails."""
        try:
            if self.pg_conn is None or self.pg_conn.closed:
                self._reconnect_pg_listener()
            self.pg_conn.poll()
            for notify in self.pg_conn.notifies:
                if notify.channel == NOTIFY_CHANNEL_RELOAD:
                    self._reload_mqtt_config_and_reconnect(reason="notify")
                elif notify.channel == NOTIFY_CHANNEL_EVENTS:
                    self._process_pending_events()
            self.pg_conn.notifies.clear()
        except Exception as e:
            logger.warning("PostgreSQL listener error: %s", e)
            if self.pg_conn is not None:
                try:
                    self.pg_conn.close()
                except Exception:
                    pass
                self.pg_conn = None

    def _initialize_mqtt(self, force_immediate_once: bool = False):
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

        if force_immediate_once:
            # Bypass backoff/circuit-breaker once: a saved config should cause an
            # immediate connection attempt, even if we were previously waiting.
            try:
                self.mqtt_client = connect()
            except Exception as e:
                logger.info(
                    "%s Immediate reconnect attempt after config change failed: %s",
                    lifecycle_log_prefix(),
                    e,
                )
                self.mqtt_client = self.mqtt_connection_mgr.connect_with_retry(
                    connect, wakeup_event=self._mqtt_wakeup_event
                )
        else:
            self.mqtt_client = self.mqtt_connection_mgr.connect_with_retry(
                connect, wakeup_event=self._mqtt_wakeup_event
            )
        self.connection_count += 1
        self.last_connect_time = time.time()
        self._last_reconnect_fail_msg = None
        logger.info(
            "%s Connected to MQTT broker at %s:%s",
            lifecycle_log_prefix(),
            self.broker_host,
            self.broker_port,
        )

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            _write_bridge_status("connected")
            if self._mqtt_has_connected_before:
                logger.info(
                    "%s Successfully reconnected to MQTT broker at %s:%s",
                    lifecycle_log_prefix(),
                    self.broker_host,
                    self.broker_port,
                )
            else:
                logger.info(
                    "%s Connected to MQTT broker at %s:%s",
                    lifecycle_log_prefix(),
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

    def _disconnect_mqtt_client(self):
        """Stop the MQTT client without loading new config."""
        if self.mqtt_client is not None:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except Exception as e:
                logger.debug("MQTT disconnect: %s", e)
            self.mqtt_client = None

    def _reload_mqtt_config_and_reconnect(self, reason="unknown"):
        """
        Load MQTT settings from DB, reconnect or disconnect, drain queue on success.
        Updates self._mqtt_config_fingerprint only after a successful apply (including
        disabled/no-config: disconnect and idle).
        """
        logger.info(
            "%s MQTT config reload (%s), reconnecting to broker",
            lifecycle_log_prefix(),
            reason,
        )
        # If we are currently waiting on reconnect backoff, wake immediately so we
        # can attempt the new settings without waiting out the previous delay.
        try:
            self._mqtt_wakeup_event.set()
        except Exception:
            pass
        try:
            from django.core.cache import cache

            cache.delete("mqtt_active_config")
        except Exception as e:
            logger.debug("Could not clear config cache: %s", e)

        self.config = get_mqtt_config(force_refresh=True)

        if not self.config or not self.config.enabled:
            self._disconnect_mqtt_client()
            if self.auto_start and self.mosquitto_process is not None:
                try:
                    if hasattr(self.mosquitto_process, "shutdown"):
                        self.mosquitto_process.shutdown()
                except Exception as e:
                    logger.debug("Embedded broker shutdown: %s", e)
                self.mosquitto_process = None
            _write_bridge_status("disconnected")
            self._mqtt_config_fingerprint = read_mqtt_config_fingerprint()
            self._process_pending_events()
            return True

        if self.auto_start and self.mosquitto_process is None:
            try:
                cleanup_existing_services(None)
            except Exception as e:
                logger.debug("cleanup_existing_services: %s", e)
            self.mosquitto_process = start_mosquitto(self.config)

        level_name = getattr(self.config, "log_level", None) or "INFO"
        logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))
        try:
            self._initialize_mqtt(force_immediate_once=True)
        except Exception as e:
            logger.error("MQTT reconnect after config reload failed: %s", e)
            return False
        self._mqtt_config_fingerprint = read_mqtt_config_fingerprint()
        self._process_pending_events()
        return True

    def _run(self):
        """Main loop: LISTEN for notifications, fetch events, publish to MQTT."""
        level_name = (
            getattr(self.config, "log_level", None) or "INFO"
            if self.config
            else "INFO"
        )
        logger.setLevel(getattr(logging, level_name.upper(), logging.INFO))
        logger.info("%s Starting consumption loop", lifecycle_log_prefix())

        while self.running:
            try:
                from django.db import close_old_connections

                close_old_connections()

                now = time.time()
                now_m = time.monotonic()
                if (
                    now_m - self._last_heartbeat_monotonic
                ) >= BRIDGE_HEARTBEAT_INTERVAL:
                    _touch_bridge_heartbeat()
                    self._last_heartbeat_monotonic = now_m

                queue_poll_due = (
                    now - self._last_queue_poll_time
                ) >= QUEUE_POLL_INTERVAL

                self._poll_pg_notifications()

                # NOTIFY for config can be missed (same as events): poll DB fingerprint.
                if queue_poll_due:
                    current_fp = read_mqtt_config_fingerprint()
                    if mqtt_config_reload_needed(
                        self._mqtt_config_fingerprint, current_fp
                    ):
                        self._reload_mqtt_config_and_reconnect(reason="config_poll")
                    self._process_pending_events()
                    self._last_queue_poll_time = now

                if not self.config or not self.config.enabled:
                    time.sleep(0.01)
                    continue

                if not self._ensure_mqtt_connected():
                    time.sleep(5)
                    continue

                now_status = time.time()
                if (
                    now_status - self._last_bridge_status_write
                ) >= BRIDGE_STATUS_REFRESH_INTERVAL:
                    _write_bridge_status("connected")
                    self._last_bridge_status_write = now_status

                time.sleep(0.01)
            except Exception as e:
                logger.error("Service loop error: %s", e)
                time.sleep(1)

        logger.info("%s Consumption loop stopped", lifecycle_log_prefix())

    def _process_pending_events(self):
        """Fetch unprocessed events and publish to MQTT."""
        try:
            events = list(
                MQTTEventQueue.objects.filter(processed=False).order_by("id")
            )
            if not events:
                return
            logger.info(
                "Publishing %s pending MQTT queue event(s) to broker",
                len(events),
            )
            for event in events:
                if self._process_event(event):
                    event.processed = True
                    event.save(update_fields=["processed"])
                else:
                    break
        except Exception as e:
            logger.error("Failed to process events: %s", e)

    def _process_event(self, event) -> bool:
        """Publish one queue row. Returns True if done (published or permanently skipped)."""
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
        if not topic or payload is None:
            logger.warning("Invalid event: missing topic or payload")
            return True
        return self._publish_to_mqtt(topic, payload, qos, retain)

    def _publish_to_mqtt(
        self, topic: str, payload: str, qos: int = 0, retain: bool = False
    ) -> bool:
        if not self.mqtt_client or not self.mqtt_client.is_connected():
            logger.warning("MQTT not connected, cannot publish")
            return False
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
                return False
            return True
        except Exception as e:
            logger.error("Publish failed: %s", e)
            return False

    def stop(self):
        """Stop the bridge service."""
        if self._bridge_stop_done:
            return
        self._bridge_stop_done = True
        logger.info(
            "%s Stopping PostgreSQL-MQTT Bridge",
            lifecycle_log_prefix(),
        )
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
        if self.auto_start and self.mosquitto_process is not None:
            # Shut down embedded broker if we started one
            if hasattr(self.mosquitto_process, "shutdown"):
                try:
                    self.mosquitto_process.shutdown()
                except Exception as e:
                    logger.debug("Embedded broker shutdown: %s", e)
            self.mosquitto_process = None
        if self.auto_start:
            cleanup_existing_services(None)
        release_lock(self.lock_file)
        self.lock_file = None
        logger.info("%s Bridge stopped", lifecycle_log_prefix())


_mqtt_bridge_instance = None
_mqtt_bridge_lock = threading.Lock()


def _should_auto_start_mosquitto() -> bool:
    """
    Whether to start an embedded MQTT broker (AUTO mode).
    Default True for local dev; set NEMO_MQTT_BRIDGE_AUTO_START=0 for EXTERNAL mode.
    """
    env_val = os.environ.get("NEMO_MQTT_BRIDGE_AUTO_START", "").strip().lower()
    if env_val in ("0", "false", "no", "off"):
        return False
    try:
        from django.conf import settings

        if hasattr(settings, "NEMO_MQTT_BRIDGE_AUTO_START"):
            return bool(settings.NEMO_MQTT_BRIDGE_AUTO_START)
    except Exception:
        pass
    return True


def get_mqtt_bridge():
    """Get or create the global bridge instance."""
    global _mqtt_bridge_instance
    with _mqtt_bridge_lock:
        if _mqtt_bridge_instance is None:
            auto_start = _should_auto_start_mosquitto()
            _mqtt_bridge_instance = PostgresMQTTBridge(
                auto_start=auto_start, lock_fatal=False
            )
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

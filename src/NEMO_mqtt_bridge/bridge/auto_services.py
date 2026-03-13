"""
AUTO mode: start Redis and Mosquitto for development/testing.

Uses redis-wheel bundled binary when available (manylinux, macOS); falls back
to system redis-server otherwise.
"""

import logging
import subprocess
import time

import paho.mqtt.client as mqtt
import redis

logger = logging.getLogger(__name__)

# Redis server binary: prefer redis-wheel (bundled, manylinux/macOS), else system
_redis_server_path = None


def _get_redis_server_path() -> str:
    """Return path to redis-server binary (bundled or system)."""
    global _redis_server_path
    if _redis_server_path is not None:
        return _redis_server_path
    try:
        import redis_wheel

        _redis_server_path = redis_wheel.REDIS_SERVER_PATH
        logger.debug("Using bundled Redis from redis-wheel: %s", _redis_server_path)
        return _redis_server_path
    except ImportError:
        _redis_server_path = "redis-server"
        logger.debug("redis-wheel not available, using system redis-server")
        return _redis_server_path


def cleanup_existing_services(redis_process=None):
    """Clean up any existing Redis, MQTT broker, and bridge instances."""
    try:
        if redis_process:
            try:
                redis_process.terminate()
                redis_process.wait(timeout=5)
            except Exception:
                redis_process.kill()
        subprocess.run(["pkill", "-f", "mosquitto"], capture_output=True)
        subprocess.run(["pkill", "-9", "mosquitto"], capture_output=True)
        subprocess.run(["pkill", "-f", "redis_mqtt_bridge"], capture_output=True)
        time.sleep(2)
        logger.info("Cleaned up existing services")
    except Exception as e:
        logger.warning("Cleanup warning: %s", e)


def start_redis():
    """Start Redis server. Returns None if already running."""
    try:
        try:
            r = redis.Redis(host="localhost", port=6379, db=0)
            r.ping()
            logger.info("Redis already running")
            return None
        except redis.ConnectionError:
            pass

        redis_path = _get_redis_server_path()
        proc = subprocess.Popen(
            [redis_path, "--port", "6379", "--daemonize", "yes"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Allow Redis to daemonize, bind to 6379, and become ready
        time.sleep(1.5)

        for _ in range(15):
            try:
                r = redis.Redis(host="localhost", port=6379, db=0)
                r.ping()
                logger.info("Redis started successfully")
                return proc
            except redis.ConnectionError:
                time.sleep(1)
        raise RuntimeError("Redis failed to start within 15 seconds")
    except Exception as e:
        logger.error("Failed to start Redis: %s", e)
        raise


def start_mosquitto(config) -> subprocess.Popen:
    """Start Mosquitto broker (plain TCP, no TLS)."""
    broker_port = config.broker_port if config else 1883
    try:
        tc = mqtt.Client(client_id="mosquitto_check")
        tc.connect("localhost", broker_port, 5)
        tc.disconnect()
        logger.info("Mosquitto already running on port %s", broker_port)
        return None
    except Exception:
        pass

    proc = subprocess.Popen(
        ["mosquitto", "-p", str(broker_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    for i in range(20):
        try:
            tc = mqtt.Client(client_id=f"mosquitto_check_{i}")
            tc.connect("localhost", broker_port, 5)
            tc.loop_start()
            time.sleep(0.5)
            if tc.is_connected():
                tc.loop_stop()
                tc.disconnect()
                logger.info("Mosquitto started on port %s", broker_port)
                return proc
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"Mosquitto failed to start within 20 seconds")

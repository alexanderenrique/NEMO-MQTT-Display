#!/usr/bin/env python3
"""
Simple Redis Message Checker

This script checks for messages in Redis and shows recent activity.
Run it from your NEMO project root with a valid DJANGO_SETTINGS_MODULE, for example:

    export DJANGO_SETTINGS_MODULE=settings_dev  # or your NEMO settings module
    python -m NEMO_mqtt_bridge.monitoring.redis_checker
"""

import os
import sys
import django
import redis
import json
import time
import fcntl
import atexit
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Add the project directory to the Python path
sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
    ),
)

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings_dev")
django.setup()

# Global lock file handle
lock_file = None


def acquire_lock():
    """Acquire an exclusive lock to prevent multiple instances"""
    global lock_file
    lock_file_path = "/tmp/nemo_redis_monitor.lock"

    try:
        lock_file = open(lock_file_path, "w")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        logger.info("Redis monitor lock acquired")
        return True
    except (IOError, OSError):
        logger.error("Another Redis monitor is already running!")
        logger.error("   If you're sure no other monitor is running, delete:")
        logger.error("   rm %s", lock_file_path)
        return False


def release_lock():
    """Release the lock"""
    global lock_file
    if lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            os.unlink("/tmp/nemo_redis_monitor.lock")
            logger.info("Redis monitor lock released")
        except:
            pass
        lock_file = None


def check_redis_messages():
    """Check for messages in Redis"""
    try:
        # Connect to Redis
        r = redis.Redis(
            host="localhost", port=6379, db=1, decode_responses=True
        )  # Use database 1 for plugin isolation
        r.ping()
        logger.info("Connected to Redis")

        # Check current list length
        list_length = r.llen("nemo_mqtt_events")
        logger.info("Current messages in Redis list: %s", list_length)

        if list_length > 0:
            logger.info("Recent messages (last 10):")
            logger.info("-" * 60)

            # Get the last 10 messages (without removing them)
            messages = r.lrange("nemo_mqtt_events", -10, -1)

            for i, message in enumerate(messages, 1):
                try:
                    event_data = json.loads(message)
                    logger.info(
                        "%s. Topic: %s",
                        i,
                        event_data.get("topic", "unknown"),
                    )
                    logger.info("   Payload: %s", event_data.get("payload", "unknown"))
                    logger.info(
                        "   Timestamp: %s",
                        event_data.get("timestamp", "unknown"),
                    )
                    logger.info("   QoS: %s", event_data.get("qos", 0))
                    logger.info("   Retain: %s", event_data.get("retain", False))
                except json.JSONDecodeError as e:
                    logger.info("%s. Raw message: %s", i, message)
                    logger.info("   Error parsing JSON: %s", e)
        else:
            logger.info("No messages found in Redis list")
            logger.info("Tip: Try enabling/disabling a tool in NEMO to generate messages")

        return True

    except Exception as e:
        logger.error("Error connecting to Redis: %s", e)
        return False


def monitor_redis_realtime():
    """Monitor Redis in real-time without consuming messages"""
    try:
        r = redis.Redis(
            host="localhost", port=6379, db=1, decode_responses=True
        )  # Use database 1 for plugin isolation
        r.ping()
        logger.info("Connected to Redis")
        logger.info("Monitoring Redis for new messages...")
        logger.info("   (Press Ctrl+C to stop)")
        logger.info("-" * 60)

        last_count = r.llen("nemo_mqtt_events")

        while True:
            current_count = r.llen("nemo_mqtt_events")

            if current_count > last_count:
                new_messages = current_count - last_count
                logger.info("%s new message(s) detected!", new_messages)

                # Get the new messages without removing them
                messages = r.lrange("nemo_mqtt_events", -new_messages, -1)
                for i, message in enumerate(messages, 1):
                    try:
                        event_data = json.loads(message)
                        logger.info(
                            "  %s. Topic: %s",
                            i,
                            event_data.get("topic", "unknown"),
                        )
                        logger.info(
                            "     Payload: %s",
                            event_data.get("payload", "unknown"),
                        )
                        logger.info("     Time: %s", datetime.now().isoformat())
                    except json.JSONDecodeError as e:
                        logger.info("  %s. Raw message: %s", i, message)

                last_count = current_count
                logger.info("-" * 60)

            time.sleep(0.05)  # Check every 50ms for even faster response

    except KeyboardInterrupt:
        logger.info("Monitoring stopped")
    except Exception as e:
        logger.error("Error monitoring Redis: %s", e)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    logger.info("Redis Message Checker")
    logger.info("=" * 40)

    # Try to acquire lock
    if not acquire_lock():
        return

    # Register cleanup function
    atexit.register(release_lock)

    try:
        if not check_redis_messages():
            return

        logger.info("=" * 40)
        choice = input("Do you want to monitor in real-time? (y/n): ").lower().strip()

        if choice in ["y", "yes"]:
            monitor_redis_realtime()
        else:
            logger.info("Done!")

    except KeyboardInterrupt:
        logger.info("Monitoring stopped")
    finally:
        release_lock()


if __name__ == "__main__":
    main()

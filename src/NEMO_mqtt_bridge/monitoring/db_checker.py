#!/usr/bin/env python3
"""
Simple PostgreSQL Queue Checker

Checks for messages in MQTTEventQueue and shows recent activity.
Run from your NEMO project root with a valid DJANGO_SETTINGS_MODULE.
"""

import os
import sys
import django
import json
import time
import fcntl
import atexit
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

sys.path.insert(
    0,
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
    ),
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings_dev")
django.setup()

lock_file = None


def acquire_lock():
    """Acquire an exclusive lock to prevent multiple instances"""
    global lock_file
    lock_file_path = "/tmp/nemo_mqtt_db_monitor.lock"
    try:
        lock_file = open(lock_file_path, "w")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        logger.info("DB monitor lock acquired")
        return True
    except (IOError, OSError):
        logger.error("Another DB monitor is already running!")
        return False


def release_lock():
    """Release the lock"""
    global lock_file
    if lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            if os.path.exists("/tmp/nemo_mqtt_db_monitor.lock"):
                os.unlink("/tmp/nemo_mqtt_db_monitor.lock")
        except Exception:
            pass
        lock_file = None


def check_queue_messages():
    """Check for messages in MQTTEventQueue"""
    try:
        from NEMO_mqtt_bridge.models import MQTTEventQueue

        pending = MQTTEventQueue.objects.filter(processed=False).count()
        total = MQTTEventQueue.objects.count()
        logger.info("Pending messages in queue: %s (total: %s)", pending, total)

        if total > 0:
            logger.info("Recent messages (last 10):")
            logger.info("-" * 60)
            for i, ev in enumerate(
                MQTTEventQueue.objects.order_by("-created_at")[:10], 1
            ):
                logger.info("%s. Topic: %s", i, ev.topic)
                logger.info("   Payload: %s", ev.payload[:100] + "..." if len(ev.payload) > 100 else ev.payload)
                logger.info("   Created: %s", ev.created_at)
                logger.info("   Processed: %s", ev.processed)
        else:
            logger.info("No messages in queue")
            logger.info("Tip: Try enabling/disabling a tool in NEMO to generate messages")
        return True
    except Exception as e:
        logger.error("Error checking queue: %s", e)
        return False


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    logger.info("PostgreSQL Queue Checker")
    logger.info("=" * 40)
    if not acquire_lock():
        return
    atexit.register(release_lock)
    try:
        check_queue_messages()
    except KeyboardInterrupt:
        logger.info("Stopped")
    finally:
        release_lock()


if __name__ == "__main__":
    main()

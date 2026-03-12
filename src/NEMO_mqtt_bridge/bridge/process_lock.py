"""
Process lock to prevent multiple Redis-MQTT bridge instances.
"""

import fcntl
import logging
import os
import tempfile
import time

logger = logging.getLogger(__name__)

LOCK_PATH = os.path.join(tempfile.gettempdir(), "NEMO_mqtt_bridge.lock")


def acquire_lock():
    """Acquire lock file. Raises SystemExit if another instance is running."""
    import signal

    try:
        lock_file = open(LOCK_PATH, "w")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        os.fsync(lock_file.fileno())
        logger.info("Acquired bridge lock (PID: %s)", os.getpid())
        return lock_file
    except OSError:
        _cleanup_stale_lock()
        lock_file = open(LOCK_PATH, "w")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        os.fsync(lock_file.fileno())
        logger.info("Acquired bridge lock after cleanup (PID: %s)", os.getpid())
        return lock_file


def _cleanup_stale_lock():
    """Remove stale lock file if the process is dead."""
    import sys

    if not os.path.exists(LOCK_PATH):
        return
    try:
        with open(LOCK_PATH, "r") as f:
            pid_str = f.read().strip()
        if not pid_str:
            os.remove(LOCK_PATH)
            return
        old_pid = int(pid_str)
        try:
            os.kill(old_pid, 0)
            logger.warning(
                "Another bridge instance running (PID: %s), exiting", old_pid
            )
            sys.exit(1)
        except OSError:
            pass
        os.remove(LOCK_PATH)
        logger.info("Removed stale lock (PID %s was dead)", old_pid)
    except (ValueError, Exception) as e:
        logger.warning("Lock cleanup: %s", e)
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)


def release_lock(lock_file):
    """Release the lock file."""
    if lock_file is None:
        return
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
        if os.path.exists(LOCK_PATH):
            os.remove(LOCK_PATH)
        logger.info("Released bridge lock")
    except Exception as e:
        logger.error("Error releasing lock: %s", e)

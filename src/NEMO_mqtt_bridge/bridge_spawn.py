"""
Spawn postgres_mqtt_bridge (or bridge_supervisor) as a detached subprocess from Django
workers. Enabled by default; use launcher flock + jitter + PID check to limit duplicate
spawns. Disable with ``NEMO_MQTT_BRIDGE_SPAWN_SUBPROCESS=0`` (or Django setting).
"""

from __future__ import annotations

import fcntl
import logging
import os
import random
import subprocess
import sys
import tempfile
import time

from NEMO_mqtt_bridge.bridge.process_lock import bridge_process_running
from NEMO_mqtt_bridge.envutil import env_truthy

logger = logging.getLogger(__name__)

LAUNCHER_LOCK_PATH = os.path.join(
    tempfile.gettempdir(), "NEMO_mqtt_bridge.launcher.lock"
)


def should_spawn_bridge_subprocess() -> bool:
    """
    When True, AppConfig may start a daemon thread that spawns the bridge subprocess.

    **Default True** (external bridge). Set env ``NEMO_MQTT_BRIDGE_SPAWN_SUBPROCESS`` to
    ``0``/``false``/``no``/``off`` to disable and run the bridge manually. Affirmative env
    values keep spawn on. Django setting ``NEMO_MQTT_BRIDGE_SPAWN_SUBPROCESS`` is used
    when present and env is unset.
    """
    env_val = os.environ.get("NEMO_MQTT_BRIDGE_SPAWN_SUBPROCESS", "").strip().lower()
    if env_val in ("0", "false", "no", "off"):
        return False
    if env_val in ("1", "true", "yes", "on"):
        return True
    try:
        from django.conf import settings

        if hasattr(settings, "NEMO_MQTT_BRIDGE_SPAWN_SUBPROCESS"):
            return bool(settings.NEMO_MQTT_BRIDGE_SPAWN_SUBPROCESS)
    except Exception:
        pass
    return True


def should_spawn_use_supervisor() -> bool:
    """
    When True, the spawned command is ``bridge_supervisor`` (auto-restart) instead of
    ``postgres_mqtt_bridge`` directly.

    **Default True.** Set ``NEMO_MQTT_BRIDGE_SPAWN_USE_SUPERVISOR`` to ``0``/``false``/
    ``no``/``off`` to spawn the plain bridge module. Django setting
    ``NEMO_MQTT_BRIDGE_SPAWN_USE_SUPERVISOR`` applies when env is unset.
    """
    env_val = os.environ.get(
        "NEMO_MQTT_BRIDGE_SPAWN_USE_SUPERVISOR", ""
    ).strip().lower()
    if env_val in ("0", "false", "no", "off"):
        return False
    if env_val in ("1", "true", "yes", "on"):
        return True
    try:
        from django.conf import settings

        if hasattr(settings, "NEMO_MQTT_BRIDGE_SPAWN_USE_SUPERVISOR"):
            return bool(settings.NEMO_MQTT_BRIDGE_SPAWN_USE_SUPERVISOR)
    except Exception:
        pass
    return True


def should_skip_spawn_for_cli() -> bool:
    """Skip spawning during management commands and when NEMO_MQTT_BRIDGE_SPAWN_SKIP is set."""
    if env_truthy("NEMO_MQTT_BRIDGE_SPAWN_SKIP"):
        return True
    argv = sys.argv
    mi = None
    for i, a in enumerate(argv):
        if a == "manage.py" or a.endswith("/manage.py"):
            mi = i
            break
    if mi is None:
        return False
    cmd = argv[mi + 1].lower() if mi + 1 < len(argv) else ""
    skip = {
        "migrate",
        "makemigrations",
        "showmigrations",
        "squashmigrations",
        "collectstatic",
        "shell",
        "dbshell",
        "test",
        "dumpdata",
        "loaddata",
        "check",
        "createsuperuser",
        "changepassword",
        "compilemessages",
        "makemessages",
        "sendtestemail",
    }
    return cmd in skip


def _jitter_seconds() -> float:
    raw = os.environ.get("NEMO_MQTT_BRIDGE_SPAWN_JITTER_SEC", "1.0").strip()
    try:
        cap = float(raw)
    except ValueError:
        cap = 1.0
    if cap <= 0:
        return 0.0
    return random.uniform(0.0, cap)


def _try_acquire_launcher_lock_nonblock():
    """Return open lock file on success, None if another worker holds the launcher."""
    lf = None
    try:
        lf = open(LAUNCHER_LOCK_PATH, "w")
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lf.write(str(os.getpid()))
        lf.flush()
        os.fsync(lf.fileno())
        return lf
    except OSError:
        if lf is not None:
            try:
                lf.close()
            except OSError:
                pass
        return None


def _release_launcher_lock(lf) -> None:
    if lf is None:
        return
    try:
        fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
        lf.close()
        if os.path.exists(LAUNCHER_LOCK_PATH):
            os.remove(LAUNCHER_LOCK_PATH)
    except OSError as e:
        logger.debug("Launcher lock release: %s", e)


def _build_bridge_command() -> list:
    from NEMO_mqtt_bridge.postgres_mqtt_bridge import _should_auto_start_mosquitto

    if should_spawn_use_supervisor():
        cmd = [sys.executable, "-m", "NEMO_mqtt_bridge.bridge_supervisor"]
        if _should_auto_start_mosquitto():
            cmd.append("--auto")
        if env_truthy("NEMO_MQTT_SUPERVISOR_DB_HEALTH"):
            cmd.append("--db-health")
        return cmd

    cmd = [sys.executable, "-m", "NEMO_mqtt_bridge.postgres_mqtt_bridge"]
    if _should_auto_start_mosquitto():
        cmd.append("--auto")
    return cmd


def spawn_bridge_subprocess_if_needed() -> None:
    """
    Jitter sleep, try launcher lock, re-check bridge PID, spawn detached subprocess.
    Safe to call from a daemon thread once per worker startup.
    """
    delay = _jitter_seconds()
    if delay > 0:
        time.sleep(delay)

    launcher = _try_acquire_launcher_lock_nonblock()
    if launcher is None:
        logger.info(
            "%s Another worker holds the bridge launcher lock or bridge spawn in progress; skipping",
            _prefix(),
        )
        return

    try:
        if bridge_process_running():
            logger.info(
                "%s Bridge process already running (lock PID alive); not spawning",
                _prefix(),
            )
            return

        cmd = _build_bridge_command()
        logger.info("%s Spawning detached bridge: %s", _prefix(), " ".join(cmd))
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=None,
            stderr=None,
            start_new_session=True,
            close_fds=True,
        )
        # Keep launcher lock until the child takes the bridge lock so late workers
        # do not spawn a second process during slow Django imports.
        wait_cap = float(os.environ.get("NEMO_MQTT_BRIDGE_SPAWN_LOCK_WAIT_SEC", "15"))
        deadline = time.monotonic() + max(wait_cap, 1.0)
        while time.monotonic() < deadline:
            if bridge_process_running():
                break
            time.sleep(0.2)
        else:
            logger.warning(
                "%s Bridge subprocess started but bridge lock PID not seen within %ss",
                _prefix(),
                wait_cap,
            )
    except Exception as e:
        logger.error("%s Failed to spawn bridge subprocess: %s", _prefix(), e)
    finally:
        _release_launcher_lock(launcher)


def _prefix() -> str:
    try:
        from NEMO_mqtt_bridge.lifecycle_log import lifecycle_log_prefix

        return lifecycle_log_prefix()
    except Exception:
        return "[NEMO_mqtt_bridge]"

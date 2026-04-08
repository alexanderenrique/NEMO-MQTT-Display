"""Prefix for bridge/plugin lifecycle logs (pid and thread name)."""

import os
import threading


def lifecycle_log_prefix() -> str:
    tname = threading.current_thread().name
    return f"[NEMO_mqtt_bridge pid={os.getpid()} thread={tname}]"

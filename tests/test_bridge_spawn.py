"""Tests for opt-in Django subprocess bridge spawn."""
import sys
from unittest.mock import MagicMock, patch

import pytest

from NEMO_mqtt_bridge.bridge import process_lock as pl
from NEMO_mqtt_bridge.bridge_spawn import (
    _build_bridge_command,
    should_skip_spawn_for_cli,
    should_spawn_bridge_subprocess,
    should_spawn_use_supervisor,
    spawn_bridge_subprocess_if_needed,
)


def test_read_bridge_lock_pid_none(tmp_path, monkeypatch):
    monkeypatch.setattr(pl, "LOCK_PATH", str(tmp_path / "n.lock"))
    assert pl.read_bridge_lock_pid() is None


def test_bridge_process_running_false_when_dead_pid(tmp_path, monkeypatch):
    p = tmp_path / "n.lock"
    p.write_text("999999999\n", encoding="ascii")
    monkeypatch.setattr(pl, "LOCK_PATH", str(p))
    assert pl.bridge_process_running() is False


def test_should_spawn_subprocess_env_on(monkeypatch):
    monkeypatch.setenv("NEMO_MQTT_BRIDGE_SPAWN_SUBPROCESS", "1")
    assert should_spawn_bridge_subprocess() is True


def test_should_spawn_subprocess_env_off(monkeypatch):
    monkeypatch.setenv("NEMO_MQTT_BRIDGE_SPAWN_SUBPROCESS", "0")
    assert should_spawn_bridge_subprocess() is False


def test_should_spawn_subprocess_unset_defaults_true(monkeypatch):
    monkeypatch.delenv("NEMO_MQTT_BRIDGE_SPAWN_SUBPROCESS", raising=False)
    assert should_spawn_bridge_subprocess() is True


def test_should_spawn_use_supervisor_unset_defaults_true(monkeypatch):
    monkeypatch.delenv("NEMO_MQTT_BRIDGE_SPAWN_USE_SUPERVISOR", raising=False)
    assert should_spawn_use_supervisor() is True


def test_should_spawn_use_supervisor_env_off(monkeypatch):
    monkeypatch.setenv("NEMO_MQTT_BRIDGE_SPAWN_USE_SUPERVISOR", "0")
    assert should_spawn_use_supervisor() is False


def test_build_bridge_command_uses_supervisor_by_default(monkeypatch):
    monkeypatch.delenv("NEMO_MQTT_BRIDGE_SPAWN_USE_SUPERVISOR", raising=False)
    with patch(
        "NEMO_mqtt_bridge.postgres_mqtt_bridge._should_auto_start_mosquitto",
        return_value=False,
    ):
        cmd = _build_bridge_command()
    assert "NEMO_mqtt_bridge.bridge_supervisor" in cmd[2]


def test_build_bridge_command_plain_when_supervisor_off(monkeypatch):
    monkeypatch.setenv("NEMO_MQTT_BRIDGE_SPAWN_USE_SUPERVISOR", "0")
    with patch(
        "NEMO_mqtt_bridge.postgres_mqtt_bridge._should_auto_start_mosquitto",
        return_value=False,
    ):
        cmd = _build_bridge_command()
    assert cmd[2] == "NEMO_mqtt_bridge.postgres_mqtt_bridge"


def test_should_skip_spawn_skip_env(monkeypatch):
    monkeypatch.setenv("NEMO_MQTT_BRIDGE_SPAWN_SKIP", "1")
    monkeypatch.setattr(sys, "argv", ["python", "manage.py", "runserver"])
    assert should_skip_spawn_for_cli() is True


def test_should_skip_manage_py_test(monkeypatch):
    monkeypatch.delenv("NEMO_MQTT_BRIDGE_SPAWN_SKIP", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["/venv/bin/python", "/app/manage.py", "test", "tests"],
    )
    assert should_skip_spawn_for_cli() is True


def test_should_not_skip_runserver(monkeypatch):
    monkeypatch.delenv("NEMO_MQTT_BRIDGE_SPAWN_SKIP", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["python", "manage.py", "runserver"],
    )
    assert should_skip_spawn_for_cli() is False


def test_spawn_skips_when_bridge_running(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "NEMO_mqtt_bridge.bridge_spawn.LAUNCHER_LOCK_PATH",
        str(tmp_path / "launcher.lock"),
    )
    mock_lf = MagicMock()
    mock_lf.fileno.return_value = 9
    with patch(
        "NEMO_mqtt_bridge.bridge_spawn.bridge_process_running",
        return_value=True,
    ):
        with patch(
            "NEMO_mqtt_bridge.bridge_spawn._try_acquire_launcher_lock_nonblock",
            return_value=mock_lf,
        ):
            with patch("NEMO_mqtt_bridge.bridge_spawn.subprocess.Popen") as popen:
                with patch("NEMO_mqtt_bridge.bridge_spawn._jitter_seconds", return_value=0):
                    spawn_bridge_subprocess_if_needed()
                popen.assert_not_called()
    mock_lf.close.assert_called()


def test_spawn_calls_popen_when_not_running(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "NEMO_mqtt_bridge.bridge_spawn.LAUNCHER_LOCK_PATH",
        str(tmp_path / "launcher.lock"),
    )
    mock_lf = MagicMock()
    mock_lf.fileno.return_value = 9
    with patch(
        "NEMO_mqtt_bridge.bridge_spawn.bridge_process_running",
        side_effect=[False, True],
    ):
        with patch(
            "NEMO_mqtt_bridge.bridge_spawn._try_acquire_launcher_lock_nonblock",
            return_value=mock_lf,
        ):
            with patch(
                "NEMO_mqtt_bridge.bridge_spawn._build_bridge_command",
                return_value=["python", "-m", "NEMO_mqtt_bridge.postgres_mqtt_bridge"],
            ):
                with patch("NEMO_mqtt_bridge.bridge_spawn.subprocess.Popen") as popen:
                    with patch("NEMO_mqtt_bridge.bridge_spawn._jitter_seconds", return_value=0):
                        spawn_bridge_subprocess_if_needed()
                    popen.assert_called_once()
                    _, kwargs = popen.call_args
                    assert kwargs.get("start_new_session") is True

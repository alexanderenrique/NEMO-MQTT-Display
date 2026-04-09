import pytest


class _FakeWakeupEvent:
    """
    Minimal Event-like object for testing. Becomes set after N sleep ticks.
    """

    def __init__(self, ticks_until_set: int):
        self._ticks_until_set = ticks_until_set
        self._ticks = 0
        self._is_set = False

    def is_set(self) -> bool:
        return self._is_set

    def set(self) -> None:
        self._is_set = True

    def clear(self) -> None:
        self._is_set = False

    def on_sleep_tick(self) -> None:
        self._ticks += 1
        if self._ticks >= self._ticks_until_set:
            self.set()


def test_connection_manager_wakeup_interrupts_backoff_sleep(monkeypatch):
    """
    Proves that a wakeup event interrupts long backoff sleep so we can retry quickly.
    This is the mechanism used to make config-save reconnects responsive.
    """
    from NEMO_mqtt_bridge.connection_manager import ConnectionManager
    import NEMO_mqtt_bridge.connection_manager as cm

    monotonic_state = {"t": 0.0}
    slept = {"total": 0.0, "calls": 0}

    wakeup = _FakeWakeupEvent(ticks_until_set=2)  # interrupt after 2 sleep ticks

    def fake_monotonic():
        return monotonic_state["t"]

    def fake_sleep(dt: float):
        slept["total"] += dt
        slept["calls"] += 1
        monotonic_state["t"] += dt
        wakeup.on_sleep_tick()

    monkeypatch.setattr(cm.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(cm.time, "sleep", fake_sleep)

    mgr = ConnectionManager(
        max_retries=2,
        base_delay=10.0,
        max_delay=10.0,
        failure_threshold=999,  # keep circuit breaker CLOSED for this test
        timeout=60,
    )

    def always_fail():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        mgr.connect_with_retry(always_fail, wakeup_event=wakeup)

    # Without wakeup_event we'd sleep once for the full backoff (10.0s).
    # With wakeup_event, we should have slept only a couple short ticks.
    assert slept["calls"] >= 1
    assert slept["total"] < 10.0


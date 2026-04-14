# MQTT Bridge Monitoring Tools

This directory contains monitoring and debugging tools for the NEMO_mqtt_bridge plugin.

## Quick Start

From the NEMO project root directory:

```bash
# Full MQTT + queue monitoring
python -m NEMO_mqtt_bridge.monitoring.mqtt_monitor

# Queue checker (PostgreSQL)
python -m NEMO_mqtt_bridge.monitoring.db_checker
```

To generate test traffic, enable or disable a tool in the NEMO web interface; the monitor will show the corresponding queue and MQTT messages.

Or use the run_monitor runner (requires manage.py in cwd):

```bash
python -m NEMO_mqtt_bridge.monitoring.run_monitor mqtt
python -m NEMO_mqtt_bridge.monitoring.run_monitor db
python -m NEMO_mqtt_bridge.monitoring.run_monitor test
```

The `test` option runs `manage.py test_mqtt_api` if that management command exists in your NEMO project; otherwise use the NEMO UI to enable/disable tools and watch the monitor.

## Files

- **`mqtt_monitor.py`** - Full monitoring (PostgreSQL queue + MQTT)
- **`db_checker.py`** - PostgreSQL queue checker
- **`run_monitor.py`** - Runner with venv detection

## Web status (JSON)

Bridge connection, heartbeat, reload metadata, queue summary, and safe config metadata are returned as **JSON** from **`mqtt_bridge_status/`** (login required). With `path("mqtt/", include(...))` the URL is **`/mqtt/mqtt_bridge_status/`**. The old **`mqtt_monitor/`** path **redirects** to that JSON endpoint. MQTT broker settings are edited on the MQTT **customization** page. For local queue/MQTT inspection, use the CLI tools above.

## Bridge configuration reload

Saving or deleting MQTT configuration in Django triggers `pg_notify` on `nemo_mqtt_reload`, and the bridge also **polls** the enabled configuration row’s `updated_at` on the same schedule as the event queue (default 2s). Broker host, auth, and related settings therefore apply even if the reload notify is lost (for example with some pooler setups). After a successful reconnect, pending queue rows are published immediately.

### Stakeholders and NOTIFY (summary)

- **`nemo_mqtt_reload`** — `MQTTConfiguration` changed (committed). Bridge reloads broker settings from the database (plus fingerprint fallback).
- **`nemo_mqtt_events`** — New `MQTTEventQueue` row. Bridge publishes that payload to MQTT.
- **All implemented event types** are always published when MQTT is on; there is no separate “event filter” layer in the bridge.

**Django workers:** `mqtt_active_config` is cached; with LocMem per worker, use a shared cache if every Gunicorn/Uvicorn worker must immediately see broker edits. The bridge process reloads from PostgreSQL on its reload path.

## In-process bridge vs separate process

**Default (2.2.0+):** the bridge **does not** start from Django (`AppConfig.ready`). Run **`python -m NEMO_mqtt_bridge.postgres_mqtt_bridge`** as its own process (systemd, Compose service, etc.). Django still enqueues events and sends **`pg_notify`**; the standalone bridge **LISTEN**s and publishes to MQTT.

For **Docker Compose**, add a **second service** with the same image and DB-related env as NEMO (see the main [README.md](../../../README.md) Docker section). Use **one** bridge service; do **not** scale it to multiple replicas.

For **automatic restart** of the bridge process (exponential backoff; optional DB heartbeat watchdog), use **`python -m NEMO_mqtt_bridge.bridge_supervisor`** or **`nemo-mqtt-bridge-supervisor`** as the container command instead of `postgres_mqtt_bridge`—see the main README supervisor paragraph.

For **auto-spawn from Django** (default: single container, detached **`bridge_supervisor`**, not in Gunicorn workers), see **`NEMO_MQTT_BRIDGE_SPAWN_SUBPROCESS`** / **`NEMO_MQTT_BRIDGE_SPAWN_USE_SUPERVISOR`** in the main [README.md](../../../README.md).

To embed the bridge in the **same process** as Django (single-process dev only; avoid with multiple Gunicorn/Uvicorn workers), set **`NEMO_MQTT_BRIDGE_RUN_IN_DJANGO=1`** (or `true` / `yes` / `on`) in the environment, or **`NEMO_MQTT_BRIDGE_RUN_IN_DJANGO = True`** in Django settings. Use **`0`** / **`false`** / **`no`** / **`off`** to force the standalone-only behavior.

The bridge can start with MQTT disabled and connect when you enable configuration—no Django restart required.

## Usage

### Full MQTT Monitor
```bash
python -m NEMO_mqtt_bridge.monitoring.mqtt_monitor
```
- Polls MQTTEventQueue (PostgreSQL) and connects to the MQTT broker
- Subscribes to all `nemo/#` topics
- Shows real-time messages from both sources
- Press Ctrl+C to stop

### DB Checker
```bash
python -m NEMO_mqtt_bridge.monitoring.db_checker
```
- Connects to PostgreSQL (Django database)
- Shows pending and total message counts
- Displays recent messages from MQTTEventQueue

### Generating test traffic

To see messages in the monitor:

1. Enable or disable a tool in the NEMO web interface (Tool Control or similar).
2. Watch the full MQTT monitor or DB checker for `nemo/tools/{id}/enabled` and `nemo/tools/{id}/disabled` messages.

## Configuration Settings

### Keep Alive (seconds)

The **Keep Alive** setting (default: 60 seconds) controls how the MQTT client maintains its connection with the broker.

**What it does:**

1. **Heartbeat mechanism**: The client must send at least one packet (data or PING) to the broker within the keep-alive interval to prove it's still alive.

2. **Connection monitoring**: If the broker doesn't receive any packet within 1.5× the keep-alive interval (e.g., 90 seconds for a 60-second keep-alive), it considers the client disconnected and may close the connection.

3. **Prevents stale connections**: Helps detect and clean up dead or unresponsive connections automatically.

## Tool enable/disable: single source of truth (UsageEvent.post_save)

Tool "enable" and "disable" in NEMO (and nemo-ce) are **not** separate Django signals. They are:

- **Enable** = a new usage session starts → NEMO saves a **UsageEvent** with no `end` time.
- **Disable** = the session ends → NEMO saves the same **UsageEvent** with `end` set.

The plugin uses **`UsageEvent.post_save`** as the **single source of truth** for both. When a UsageEvent is saved:

| NEMO action | UsageEvent state | Events published |
|-------------|------------------|------------------|
| User enables tool (starts use)  | `end` is `None` | `tool_enabled` only |
| User disables tool (stops use)  | `end` is set    | `tool_disabled` only |

**Topics published:**

- **By tool id (enable/disable):**  
  `nemo/tools/{tool_id}/enabled`, `nemo/tools/{tool_id}/disabled`

## Troubleshooting

If you don't see messages:

1. **Check PostgreSQL**: Ensure NEMO uses PostgreSQL (required for LISTEN/NOTIFY)
2. **Check MQTT broker**: `lsof -i :1883`
3. **Check bridge service**: `pgrep -f postgres_mqtt_bridge` or `python -m NEMO_mqtt_bridge.postgres_mqtt_bridge` (with Compose: `docker compose logs nemo_mqtt_bridge` or your service name)
4. **Check Django logs** for signal handler errors (bridge logs are on the **bridge process**, not the web workers, unless you embed the bridge in Django)
5. **Verify MQTT plugin is enabled** in Django settings

If workers cycle or the external bridge drops unexpectedly, see the **Troubleshooting** subsection in the main [README.md](../../../README.md) (`RUN_IN_DJANGO`, `NEMO_MQTT_BRIDGE_DEV_PKILL`).

## Requirements

- Python 3.6+
- Django (configured)
- PostgreSQL (NEMO's database)
- MQTT broker (for full monitoring)
- paho-mqtt (for MQTT monitoring)
- psycopg2 (for PostgreSQL)

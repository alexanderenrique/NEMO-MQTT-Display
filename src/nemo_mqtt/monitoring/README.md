# MQTT Plugin Monitoring Tools

This directory contains monitoring and debugging tools for the NEMO MQTT plugin.

## Quick Start

From the NEMO project root directory:

```bash
# Full MQTT + Redis monitoring
python -m NEMO_mqtt.monitoring.mqtt_monitor

# Redis-only checking
python -m NEMO_mqtt.monitoring.redis_checker
```

To generate test traffic, enable or disable a tool in the NEMO web interface; the monitor will show the corresponding Redis and MQTT messages.

Or use the run_monitor runner (requires manage.py in cwd):

```bash
python -m NEMO_mqtt.monitoring.run_monitor mqtt
python -m NEMO_mqtt.monitoring.run_monitor redis
python -m NEMO_mqtt.monitoring.run_monitor test
```

The `test` option runs `manage.py test_mqtt_api` if that management command exists in your NEMO project; otherwise use the NEMO UI to enable/disable tools and watch the monitor.

## Files

- **`mqtt_monitor.py`** - Full monitoring (Redis + MQTT)
- **`redis_checker.py`** - Redis message checker
- **`run_monitor.py`** - Runner with venv detection

## Web monitor (Redis stream)

The plugin’s web dashboard at **`/mqtt/monitor/`** shows a **stream of what NEMO publishes**: it reads from the Redis list `nemo_mqtt_monitor` (last 100 events). This is the same pipeline that the Redis–MQTT bridge consumes; the monitor does not subscribe to the MQTT broker, so you only see events emitted by this plugin. The page auto-refreshes every 3 seconds.

## Usage

### Full MQTT Monitor
```bash
python -m NEMO_mqtt.monitoring.mqtt_monitor
```
- Connects to Redis (db=1, same as the plugin) and the MQTT broker
- Subscribes to all `nemo/#` topics
- Shows real-time messages from both sources
- Press Ctrl+C to stop

**Note:** The script consumes from the same Redis list (`nemo_mqtt_events`) as the Redis–MQTT bridge. If the bridge is running, only one of them will receive each message. For a non-consuming view of what the plugin publishes, use the web dashboard at `/mqtt/monitor/` or the Redis checker in read-only mode.

### Redis Checker
```bash
python -m NEMO_mqtt.monitoring.redis_checker
```
- Connects to Redis only (db=1, same as the plugin)
- Shows current message count
- Displays recent messages
- Option to monitor in real-time

### Generating test traffic

To see messages in the monitor:

1. Enable or disable a tool in the NEMO web interface (Tool Control or similar).
2. Watch the full MQTT monitor or Redis checker for `nemo/tools/{id}/enabled` and `nemo/tools/{id}/disabled` messages.

If your NEMO project provides a `test_mqtt_api` management command, you can run `python manage.py test_mqtt_api` instead; this plugin does not ship that command.

## Configuration Settings

### Keep Alive (seconds)

The **Keep Alive** setting (default: 60 seconds) controls how the MQTT client maintains its connection with the broker.

**What it does:**

1. **Heartbeat mechanism**: The client must send at least one packet (data or PING) to the broker within the keep-alive interval to prove it's still alive.

2. **Connection monitoring**: If the broker doesn't receive any packet within 1.5× the keep-alive interval (e.g., 90 seconds for a 60-second keep-alive), it considers the client disconnected and may close the connection.

3. **Prevents stale connections**: Helps detect and clean up dead or unresponsive connections automatically.

**In practice:**

- **Default (60 seconds)**: Works well for most NEMO deployments. The plugin sends messages regularly, so the keep-alive mainly acts as a safety net.
- **Increase (120-300 seconds)**: Useful for battery-constrained devices or when you want to reduce network traffic. Allows longer periods between messages.
- **Decrease (30 seconds)**: Provides faster detection of disconnections, useful in unstable network environments.

**Note**: The plugin publishes **tool enable/disable** events when users start or stop tool usage in NEMO. Those messages keep the connection active; the keep-alive interval mainly acts as a connection health check.

## Tool enable/disable: single source of truth (UsageEvent.post_save)

Tool “enable” and “disable” in NEMO (and nemo-ce) are **not** separate Django signals. They are:

- **Enable** = a new usage session starts → NEMO saves a **UsageEvent** with no `end` time.
- **Disable** = the session ends → NEMO saves the same **UsageEvent** with `end` set.

The plugin uses **`UsageEvent.post_save`** as the **single source of truth** for both. When a UsageEvent is saved:

| NEMO action | UsageEvent state | Events published to Redis |
|-------------|------------------|----------------------------|
| User enables tool (starts use)  | `end` is `None` | `tool_enabled` only |
| User disables tool (stops use)  | `end` is set    | `tool_disabled` only |

**Topics published:**

- **By tool id (enable/disable):**  
  `nemo/tools/{tool_id}/enabled`, `nemo/tools/{tool_id}/disabled`

All of these are emitted from the same **UsageEvent** handler, so you get consistent, instantaneous updates (same request as the NEMO enable/disable action).

## Testing Tool Enable/Disable

1. **Start monitoring**:
   ```bash
   python -m NEMO_mqtt.monitoring.mqtt_monitor
   ```

2. **Enable/disable a tool** in the NEMO web interface (e.g. “Enable” to start use, “Disable” / “Stop” to end use).

3. **Watch for messages**:
   - On **enable**: `nemo/tools/{id}/enabled` only
   - On **disable**: `nemo/tools/{id}/disabled` only
   - MQTT will show the same if the bridge is running.

## What to Look For

When you **enable** a tool (start use), you should see:

**Enabled**
- Topic: `nemo/tools/2/enabled` (example tool id)
- Payload includes: `"event": "tool_enabled"`, `tool_id`, `tool_name`, `usage_id`, `user_name`, `start_time`

When you **disable** a tool (stop use), you should see:

**Disabled**
- Topic: `nemo/tools/2/disabled`
- Payload includes: `"event": "tool_disabled"`, `tool_id`, `tool_name`, `usage_id`, `user_name`, `end_time`

## Troubleshooting

If you don't see messages:

1. **Check Redis**: `redis-cli ping`
2. **Check MQTT broker**: `lsof -i :1883`
3. **Check Redis-MQTT Bridge service**: `pgrep -f redis_mqtt_bridge` or `python -m NEMO_mqtt.redis_mqtt_bridge`
4. **Check Django logs** for signal handler errors
5. **Verify MQTT plugin is enabled** in Django settings

## Requirements

- Python 3.6+
- Django (configured)
- Redis server
- MQTT broker (for full monitoring)
- paho-mqtt (for MQTT monitoring)
- redis-py (for Redis monitoring)

The scripts automatically detect and use the project's virtual environment if available.

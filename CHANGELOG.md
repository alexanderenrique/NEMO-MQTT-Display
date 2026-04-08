# Changelog

All notable changes to this project will be documented in this file.

## [2.1.5] - 2026-04-08

- **Immediate MQTT reconnect after config save**: `MQTTConfiguration` changes now trigger the bridge reload notification on DB transaction commit (`transaction.on_commit()`), so the bridge begins reconnecting as soon as the configuration is actually saved (instead of waiting for a longer surrounding transaction to finish).
- **Faster bridge status updates in the UI**: Added a `/mqtt_bridge_status/` JSON endpoint and 2-second polling on the monitor page and MQTT customization page so “Connected / Disconnected” reflects the real bridge state quickly without manual refresh.

## [2.1.4] - 2026-04-07

- **Reliable MQTT config reload**: The PostgreSQL–MQTT bridge reapplies broker settings when `MQTTConfiguration` changes, not only via `LISTEN nemo_mqtt_reload`. On the same interval as the event queue poll (default 2s), it compares the enabled row’s `(id, updated_at)` to the last successful connection; if different, it reloads from the database, reconnects (or disconnects if disabled), and drains `MQTTEventQueue` once. This matches the queue’s NOTIFY+polling pattern and fixes missed reload notifications (e.g. connection poolers). `MQTTConfiguration` **delete** now also sends `nemo_mqtt_reload` (previously only the Django cache was cleared).
- - **Bridge lifecycle without restart**: The PostgreSQL–MQTT bridge always starts PostgreSQL `LISTEN` and the worker thread even when no MQTT configuration is enabled. It idles until settings are enabled, then connects (and starts the embedded broker in AUTO mode if needed) via the existing config fingerprint / reload path.
- **Queue durability**: Rows in `MQTTEventQueue` are marked `processed` only after a successful MQTT publish; failures leave the row pending for retry (batch stops at the first failure to preserve order). Invalid rows (missing topic or payload) are still marked processed without publishing.
- **PostgreSQL listener recovery**: If `poll()` on the listener connection fails, the connection is dropped and re-established on the next loop iteration (avoids wedging after DB/network blips).
- **Django ORM in the bridge thread**: Each consumption-loop iteration calls `django.db.close_old_connections()` to avoid stale database connections.
- **In-process bridge toggle**: Set environment variable `NEMO_MQTT_BRIDGE_RUN_IN_DJANGO=0` or Django setting `NEMO_MQTT_BRIDGE_RUN_IN_DJANGO = False` to skip spawning the bridge from `AppConfig.ready()` (run `python -m NEMO_mqtt_bridge.postgres_mqtt_bridge` separately). Default remains enabled for backward compatibility.
- **Shutdown**: `atexit` stops the in-process bridge on interpreter exit; `MqttPluginConfig.disconnect_mqtt()` now calls `get_mqtt_bridge().stop()`. `stop()` is idempotent (safe if called twice).

## [2.1.3] - 2026-03-24

- **PostgreSQL–MQTT bridge queue reliability**: The consumption loop polls `MQTTEventQueue` on a short interval (default 2s) in addition to `LISTEN`/`NOTIFY`, so pending rows are published even when notifications are missed (e.g. poolers in transaction mode, no listener at insert time). Logs at INFO when batch work runs: `Publishing N pending MQTT queue event(s) to broker`.
- **Tool operational / non-operational MQTT events**: The plugin now publishes per-tool **operational status** messages, distinct from usage (enable/disable).
  - Listens to NEMO’s custom `tool_enabled` and `tool_disabled` signals (emitted when `tool.operational` changes, e.g. when a task forces a shutdown or problems are cleared).
  - **Topics**: `nemo/tools/{id}/operational` when a tool becomes operational again; `nemo/tools/{id}/non-operational` when a tool is marked down.
  - Payload includes `event`, `tool_id`, `tool_name`, `operational` (boolean), and `timestamp` (ISO). Displays can use these topics to show “tool down” / “tool OK” indicators in real time, independent of who is using the tool.
  - Optional event filter types `tool_operational` and `tool_non_operational` in MQTT customization; documentation in README and `monitoring/README.md`.

## [2.1.2] - 2026-03-16

- **Monitor page / API**: Removed the `/mqtt_monitor/api/` endpoint and the live event feed on the monitor page. The monitor now shows only MQTT configuration status (HMAC, Authentication, Connection).
- Removed unusued logging from detailed admin
- Removed unused event configuration from detail admin (logic is still in codebase, not currently implemented)

## [2.1.1] - 2026-03-14

- **Monitor page path**: Monitor dashboard URL changed from `/monitor/` to **`/mqtt_monitor/`** (with manual URL include: `/mqtt/mqtt_monitor/`).


## [2.1.0] - 2026-03-14

- **Embedded MQTT broker**: AUTO mode uses mqttools (pure Python) as an in-process broker. No mosquitto binary required—works in Docker and single-container deployments.
- **Docker / production**: Added `NEMO_MQTT_BRIDGE_AUTO_START` env var and Django setting. Set to `0` or `false` to use EXTERNAL mode (connect to external broker). Fixes `[Errno 2] No such file or directory: 'mosquitto'` when running in containers.

## [2.0.0] - 2026-03-13

- **PostgreSQL LISTEN/NOTIFY**: Replaced Redis with PostgreSQL for the event queue.
  - Django signals insert into `MQTTEventQueue` and use `pg_notify` to wake the bridge.
  - Bridge uses `LISTEN` for instant event delivery (no polling).
  - Requires NEMO to use PostgreSQL 12+ (15, 16, 17, 18 tested); no Redis or redislite needed.
  - New models: `MQTTEventQueue`, `MQTTBridgeStatus`.
  - Run bridge: `python -m NEMO_mqtt_bridge.postgres_mqtt_bridge`
  - Dependencies: removed `redis`, `redislite`; added `psycopg2-binary`.

## [1.0.5] - 2026-03-13

- **macOS Redis fallback**: When redislite's bundled redis-server fails to start on macOS (common on Apple Silicon or due to Gatekeeper), the plugin now:
  1. Tries redislite with its bundled redis-server
  2. If that fails: patches redislite to use system redis-server from Homebrew (`/opt/homebrew/bin/redis-server` or `/usr/local/bin/redis-server`) and retries
  3. If that fails: falls back to `redis.Redis(host='localhost', port=6379)`, which requires system Redis to be running (`brew install redis && brew services start redis`)

## [1.0.4] - 2026-03-13

- Consolidated migrations for fresh installs: replaced 10 migrations (0001–0010) with a single `0001_initial` that creates the production schema directly.
  - Removed migrations that were only for local/testing evolution (TLS cert paths, server certs, table renames, TLS→HMAC transition, QoS fix).
  - Fresh installs now run one migration instead of 10.


## [1.0.3] - 2026-03-13

- Aligned Django app label with package name to fix migration mismatch:
  - App label changed from `nemo_mqtt` to `NEMO_mqtt_bridge` to match `INSTALLED_APPS`.
  - Use `python manage.py migrate NEMO_mqtt_bridge` (not `nemo_mqtt`).
  - Added migration 0010 to rename tables from `nemo_mqtt_bridge_*` to `nemo_mqtt_*` for consistency with model `db_table` values.
  - Updated admin URLs and documentation.
  - **Upgrade from &lt; 1.0.3:** If you previously ran migrations with `nemo_mqtt`, run: `UPDATE django_migrations SET app = 'NEMO_mqtt_bridge' WHERE app = 'nemo_mqtt';` before or after upgrading.
  - **redislite integration** for embedded Redis:
    - Replaced redis-wheel and system redis-server with `redislite` as a core dependency.
    - Uses embedded Redis in-process; no separate `redis-server` binary or subprocess required.
    - Enables running the plugin in a single container without a Redis sidecar.
    - Works on Python 3.9+ including 3.13.

## [1.0.2] - 2026-03-05

- Standardized project name to **NEMO_mqtt_bridge** everywhere:
  - Lock file: `nemo_mqtt_bridge.lock` → `NEMO_mqtt_bridge.lock` (process lock, tests, cleanup script).
  - Bridge Redis keys: `nemo_mqtt_bridge_control` and `nemo_mqtt_bridge_status` → `NEMO_mqtt_bridge_control` and `NEMO_mqtt_bridge_status`.
  - All display and prose references (README, test settings, CHANGELOG, package docstring, monitoring README) now use `NEMO_mqtt_bridge` instead of "NEMO MQTT Bridge" or lowercase variants.
  - Removed terminal outputs, everything goes to log

## [1.0.1] - 2026-03-03

- Standardized use of "NEMO" with capital letters throughout documentation and config files.
- Documented manual steps for plugin integration:
  - Add `'NEMO_mqtt_bridge.apps.MqttPluginConfig'` to your `INSTALLED_APPS`.
  - Include the plugin URL `path('mqtt/', include('NEMO_mqtt_bridge.urls'))` in your main `urls.py`.
- Clarified that NEMO MQTT must be added to an existing NEMO-CE or NEMO site and does not run standalone.

## [1.0.0] - 2026-02-27

- Initial public release of the NEMO_mqtt_bridge plugin.
- Full MQTT integration for NEMO tool, area, reservation, and usage events.
- Redis–MQTT bridge architecture for reliable event delivery.
- Web-based monitoring dashboard at `/mqtt/mqtt_monitor/`.
- Comprehensive configuration options via Django admin and customization UI.
- AUTO and EXTERNAL service modes for development and production.
- HMAC-SHA256 message authentication for payload integrity and authenticity.


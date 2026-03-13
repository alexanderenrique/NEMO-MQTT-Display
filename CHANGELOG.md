# Changelog

All notable changes to this project will be documented in this file.


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
- Web-based monitoring dashboard at `/mqtt/monitor/`.
- Comprehensive configuration options via Django admin and customization UI.
- AUTO and EXTERNAL service modes for development and production.
- HMAC-SHA256 message authentication for payload integrity and authenticity.


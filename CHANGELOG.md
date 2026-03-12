# Changelog

All notable changes to this project will be documented in this file.

## [1.0.2] - 2026-03-05

- Standardized project name to **NEMO_mqtt_bridge** everywhere:
  - Lock file: `nemo_mqtt_bridge.lock` → `NEMO_mqtt_bridge.lock` (process lock, tests, cleanup script).
  - Bridge Redis keys: `nemo_mqtt_bridge_control` and `nemo_mqtt_bridge_status` → `NEMO_mqtt_bridge_control` and `NEMO_mqtt_bridge_status`.
  - All display and prose references (README, test settings, CHANGELOG, package docstring, monitoring README) now use `NEMO_mqtt_bridge` instead of "NEMO MQTT Bridge" or lowercase variants.

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


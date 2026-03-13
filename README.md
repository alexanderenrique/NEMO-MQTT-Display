# NEMO_mqtt_bridge

[![PyPI version](https://badge.fury.io/py/nemo-mqtt-bridge.svg)](https://badge.fury.io/py/nemo-mqtt-bridge)
[![Python Support](https://img.shields.io/pypi/pyversions/nemo-mqtt-bridge.svg)](https://pypi.org/project/nemo-mqtt-bridge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Knowing a tool’s status (interlock enabled or disabled) is critical in most labs using NEMO, but many setups only indicate this via NEMO itself or a simple LED. This project enables NEMO to send MQTT messages to displays on each tool, providing detailed, real-time status information such as current user, start time, and previous user.

The hardware, firmware, and broker code associated with this project can be found at: https://github.com/alexanderenrique/NEMO-Tool-Display

This is a Django plugin that publishes NEMO tool usage events to MQTT (tool enable/disable, tool saves). Uses Redis as a buffer and a separate bridge process to keep broker connections out of Django.

## Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌──────────────────┐    ┌─────────────┐
│   Django NEMO   │───▶│    Redis     │───▶│ Redis–MQTT Bridge │───▶│ MQTT Broker │
│  (signals)      │    │  db=1        │    │  (standalone)     │    │             │
└─────────────────┘    └──────────────┘    └──────────────────┘    └─────────────┘
```

- **Django**: Signal handlers (Tool save, UsageEvent) publish JSON to Redis list `nemo_mqtt_events` (Redis DB 1).
- **Bridge**: Separate process runs `python -m NEMO_mqtt_bridge.redis_mqtt_bridge`; it consumes from Redis and publishes to the MQTT broker with QoS 1.
- **Topics**: `nemo/tools/{id}/enabled`, `nemo/tools/{id}/disabled`

Configuration is stored in Django (e.g. `/customization/mqtt/`) and loaded by the bridge on each connection.

## Installation

**Prerequisites:** Python 3.8+, Django 3.2+, NEMO-CE 4.0+, Redis, MQTT broker (e.g. Mosquitto).

**Simplified deployment:** The plugin package is `NEMO_mqtt_bridge`. Add `'NEMO_mqtt_bridge'` to `INSTALLED_APPS`, then run `python manage.py setup_nemo_integration` (use `--write-urls` to add the URL include to `NEMO/urls.py`) and `python manage.py migrate NEMO_mqtt_bridge`.

### From PyPI (recommended)

```bash
pip install nemo-mqtt-bridge
cd /path/to/your/nemo-ce
# Add 'NEMO_mqtt_bridge' to INSTALLED_APPS in your settings (see Manual below).
python manage.py setup_nemo_integration
python manage.py migrate NEMO_mqtt_bridge
```

**Local / testing:** The command above only prints integration steps (no file changes). Add `NEMO_mqtt_bridge` to `INSTALLED_APPS` and any logging config yourself. Use `--write-urls` to add the MQTT URL include to `NEMO/urls.py`.

**Production with GitLab/Ansible:** If your config is in version control and deployed by GitLab or Ansible, run with `--gitlab` so no files are changed on the server; the command will print the snippets to add to your repo:

```bash
python manage.py setup_nemo_integration --gitlab
# Add the printed snippets to your repo (INSTALLED_APPS and URLs; configure logging as needed for your environment), commit, and deploy. Then on the server:
python manage.py migrate NEMO_mqtt_bridge
```

### Manual

1. `pip install nemo-mqtt-bridge`
2. Add `'NEMO_mqtt_bridge'` to `INSTALLED_APPS` in your settings.
3. (Optional) If you use Django’s `LOGGING` setting, add a `NEMO_mqtt_bridge` logger with your preferred level and handlers (e.g. DEBUG in dev/test, INFO or WARNING in production). What and how you log is installation-dependent.
4. run `python manage.py setup_nemo_integration` to print integration steps, or add `path("mqtt/", include("NEMO_mqtt_bridge.urls"))` to `NEMO/urls.py` yourself. Use `--write-urls` to have the command add the URL include.
5. Run `python manage.py migrate NEMO_mqtt_bridge`.

### After install

1. **Configure**: Open `/customization/mqtt/` in NEMO, set broker host/port (and auth if needed), enable the config.
2. **Start NEMO** (e.g. `python manage.py runserver`). With the default AUTO mode, the plugin automatically starts Redis and the Redis–MQTT bridge (and a local Mosquitto broker for development).

**Production:** Use EXTERNAL mode so the plugin does not start or kill brokers: set `RedisMQTTBridge(auto_start=False)` in `NEMO_mqtt_bridge/apps.py`. Then start Redis and the MQTT broker yourself, and run the bridge separately (e.g. `python -m NEMO_mqtt_bridge.redis_mqtt_bridge` or as a systemd service).

---

- **Monitoring:** Event stream at `/mqtt/monitor/`; CLI tools in `NEMO_mqtt_bridge.monitoring` (see `src/NEMO_mqtt_bridge/monitoring/README.md`).
- **HMAC:** Optional payload signing
- **License:** MIT. [Issues](https://github.com/alexanderenrique/NEMO-MQTT-Plugin/issues) · [Discussions](https://github.com/alexanderenrique/NEMO-MQTT-Plugin/discussions)

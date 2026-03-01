# NEMO MQTT Plugin

[![PyPI version](https://badge.fury.io/py/nemo-mqtt-plugin.svg)](https://badge.fury.io/py/nemo-mqtt-plugin)
[![Python Support](https://img.shields.io/pypi/pyversions/nemo-mqtt-plugin.svg)](https://pypi.org/project/nemo-mqtt-plugin/)
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
- **Bridge**: Separate process runs `python -m nemo_mqtt.redis_mqtt_bridge`; it consumes from Redis and publishes to the MQTT broker with QoS 1.
- **Topics**: `nemo/tools/{id}/enabled`, `nemo/tools/{id}/disabled`

Configuration is stored in Django (e.g. `/customization/mqtt/`) and loaded by the bridge on each connection.

## Installation

**Prerequisites:** Python 3.8+, Django 3.2+, NEMO-CE 4.0+, Redis, MQTT broker (e.g. Mosquitto).

### From PyPI (recommended)

```bash
pip install nemo-mqtt-plugin
cd /path/to/your/nemo-ce
# Add 'nemo_mqtt' to INSTALLED_APPS first, then run setup to add URLs and logging
python manage.py setup_nemo_integration
python manage.py migrate nemo_mqtt
```

### Manual

1. `pip install nemo-mqtt-plugin`
2. Add `'nemo_mqtt'` to `INSTALLED_APPS`.
3. Add `path("mqtt/", include("nemo_mqtt.urls"))` to your root `urlpatterns`.
4. Run `python manage.py migrate nemo_mqtt`.

### After install

1. **Configure**: Open `/customization/mqtt/` in NEMO, set broker host/port (and auth if needed), enable the config.
2. **Start NEMO** (e.g. `python manage.py runserver`). With the default AUTO mode, the plugin automatically starts Redis and the Redis–MQTT bridge (and a local Mosquitto broker for development).

**Production:** Use EXTERNAL mode so the plugin does not start or kill brokers: set `RedisMQTTBridge(auto_start=False)` in `nemo_mqtt/apps.py`. Then start Redis and the MQTT broker yourself, and run the bridge separately (e.g. `python -m nemo_mqtt.redis_mqtt_bridge` or as a systemd service).

---

- **Monitoring:** Event stream at `/mqtt/monitor/`; CLI tools in `nemo_mqtt.monitoring` (see `src/nemo_mqtt/monitoring/README.md`).
- **HMAC:** Optional payload signing
- **License:** MIT. [Issues](https://github.com/alexanderenrique/NEMO-MQTT-Plugin/issues) · [Discussions](https://github.com/alexanderenrique/NEMO-MQTT-Plugin/discussions)

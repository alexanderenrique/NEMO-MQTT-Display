# NEMO_mqtt_bridge

[![PyPI version](https://badge.fury.io/py/nemo-mqtt-bridge.svg)](https://badge.fury.io/py/nemo-mqtt-bridge)
[![Python Support](https://img.shields.io/pypi/pyversions/nemo-mqtt-bridge.svg)](https://pypi.org/project/nemo-mqtt-bridge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Knowing a tool's status (interlock enabled or disabled) is critical in most labs using NEMO, but many setups only indicate this via NEMO itself or a simple LED. This project enables NEMO to send MQTT messages to displays on each tool, providing detailed, real-time status information such as current user, start time, and previous user.

The hardware, firmware, and broker code associated with this project can be found at: https://github.com/alexanderenrique/NEMO-Tool-Display

This is a Django plugin that publishes NEMO tool usage events to MQTT (tool enable/disable, tool saves). Uses PostgreSQL LISTEN/NOTIFY and a separate bridge process to keep broker connections out of Django.

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────┐    ┌─────────────┐
│   Django NEMO   │───▶│   PostgreSQL     │───▶│ PostgreSQL–MQTT      │───▶│ MQTT Broker │
│  (signals)      │    │  (event queue)   │    │ Bridge (standalone)  │    │             │
└─────────────────┘    └──────────────────┘    └─────────────────────┘    └─────────────┘
```

- **Django**: Signal handlers (Tool save, UsageEvent, Tool operational status) insert into `MQTTEventQueue` and use `pg_notify` to wake the bridge.
- **Bridge**: Separate process runs `python -m NEMO_mqtt_bridge.postgres_mqtt_bridge`; it LISTENs for notifications, fetches events, and publishes to the MQTT broker with QoS 1.
- **Topics (usage status)**: `nemo/tools/{id}/enabled`, `nemo/tools/{id}/disabled`
- **Topics (operational status)**: `nemo/tools/{id}/operational`, `nemo/tools/{id}/non-operational`

Configuration is stored in Django (e.g. `/customization/mqtt/`) and loaded by the bridge on each connection.

### Tool operational vs. down (per-tool status)

In addition to **usage** events (who enabled/disabled the tool), the plugin publishes **operational status** so displays can show when a tool is marked down or back up:

- **`nemo/tools/{id}/operational`** — emitted when the tool becomes operational again (e.g. problem cleared, forced-shutdown task resolved).
- **`nemo/tools/{id}/non-operational`** — emitted when the tool is marked non-operational (e.g. a task with “force shutdown” is created).

These events use NEMO’s `tool_enabled` / `tool_disabled` signals and are independent of who is currently using the tool. Payloads include `event`, `tool_id`, `tool_name`, `operational` (boolean), and `timestamp` (ISO). See `src/NEMO_mqtt_bridge/monitoring/README.md` for payload examples.

## Installation

**Prerequisites:** Python 3.8+, Django 3.2+, NEMO-CE 4.0+, MQTT broker (e.g. Mosquitto), **PostgreSQL 12+** (NEMO's database; 15, 16, 17, 18 tested). The plugin uses the same PostgreSQL database as NEMO; no Redis required.

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
3. (Optional) If you use Django's `LOGGING` setting, add a `NEMO_mqtt_bridge` logger with your preferred level and handlers (e.g. DEBUG in dev/test, INFO or WARNING in production). To correlate lines across **Gunicorn/Uvicorn workers**, include `%(process)d` (and optionally `%(thread)d`) in your log `format` string for the relevant handlers. Bridge lifecycle messages from this plugin also include a `[NEMO_mqtt_bridge pid=… thread=…]` prefix.
4. Add `path("mqtt/", include("NEMO_mqtt_bridge.urls"))` to `NEMO/urls.py` (or run `python manage.py setup_nemo_integration --write-urls`). **Skip this step for Docker/pip installs**—NEMO auto-includes plugin URLs (see [Plugin URLs](#plugin-urls)).
5. Run `python manage.py migrate NEMO_mqtt_bridge`.

### After install

1. **Configure**: Open `/customization/mqtt/` in NEMO, set broker host/port (and auth if needed), enable the config.
2. **Run the PostgreSQL–MQTT bridge** so queued events reach the broker. **By default the bridge does not start inside Django** (recommended for Docker and multi-worker servers). Start it as a **separate process**, e.g. `python -m NEMO_mqtt_bridge.postgres_mqtt_bridge` (second terminal, systemd unit, or a dedicated Docker Compose service—see [Docker](#docker) below). For **simple single-process dev** only, you may set `NEMO_MQTT_BRIDGE_RUN_IN_DJANGO=1` so `AppConfig.ready()` embeds the bridge in the same process as `runserver` (avoid with Gunicorn/Uvicorn and multiple workers).
3. **Start NEMO** (e.g. `python manage.py runserver`). With the default AUTO mode, the bridge can use an embedded MQTT broker (mqttools, pure Python) for development. No separate Mosquitto binary required in that mode.

**Production:** Use EXTERNAL mode so the plugin does not start or kill brokers. Set `NEMO_MQTT_BRIDGE_AUTO_START=0` (env) or `NEMO_MQTT_BRIDGE_AUTO_START = False` in Django settings. Then start the MQTT broker yourself, and run the bridge separately (e.g. `python -m NEMO_mqtt_bridge.postgres_mqtt_bridge` or as a systemd service).

**Bridge in Django vs separate process:** Django **writes to `MQTTEventQueue` and uses `pg_notify`** (via the DB publisher); it does not need a long-lived MQTT connection in the web workers. The **standalone bridge process** `LISTEN`s, drains the queue, and publishes to MQTT. **Default:** the bridge is **not** started inside Django. Set **`NEMO_MQTT_BRIDGE_RUN_IN_DJANGO=1`** (or `true` / `yes` / `on`) in the environment, or **`NEMO_MQTT_BRIDGE_RUN_IN_DJANGO = True`** in Django settings, to embed the bridge in-process (dev/simple installs). Set **`0`** / **`false`** / **`no`** / **`off`** to force off. The bridge can idle without an enabled MQTT config and pick up settings when you enable them, without restarting Django.

**Docker:** Use the **same image and env** as the web app for a **second service** that runs only the bridge, for example:

```yaml
services:
  nemo:
    image: your-nemo-image
    environment:
      DJANGO_SETTINGS_MODULE: settings
      # Optional explicit off (default since 2.2.0):
      NEMO_MQTT_BRIDGE_RUN_IN_DJANGO: "0"
    command: ["gunicorn", "..."]

  nemo_mqtt_bridge:
    image: your-nemo-image
    environment:
      DJANGO_SETTINGS_MODULE: settings
    command: ["python", "-m", "NEMO_mqtt_bridge.postgres_mqtt_bridge"]
    depends_on:
      - nemo
```

Adjust service names, `depends_on`, and database/network settings to match your stack. You can run in AUTO mode with the embedded broker (mqttools) or set `NEMO_MQTT_BRIDGE_AUTO_START=0` and point MQTT customization at an external broker (e.g. `broker_host=mqtt` for a Compose service named `mqtt`).

### Plugin URLs

The plugin exposes one URL:

| URL | Purpose |
|-----|---------|
| `/mqtt_monitor/` | Web dashboard (event feed disabled) |

**Where to find them** depends on how NEMO loads the plugin:

- **Docker / pip-installed NEMO:** NEMO auto-includes URLs from apps whose names start with `NEMO`. The plugin is mounted at the root, so use **`/mqtt_monitor/`**. No manual URL config needed.
- **Source install with `--write-urls`:** If you add `path("mqtt/", include("NEMO_mqtt_bridge.urls"))` to `NEMO/urls.py`, the URL is under `/mqtt/`: **`/mqtt/mqtt_monitor/`**.

Both paths require login. If you get a 404, check which URL scheme your NEMO uses (auto-include vs manual).

---

- **Robustness roadmap:** Phases 1–5 in [docs/ROBUSTNESS_PLAN.md](docs/ROBUSTNESS_PLAN.md) are implemented in 2.1.5 (idle bridge until MQTT enabled, processed-only-on-publish, LISTEN reconnect, `close_old_connections`, `NEMO_MQTT_BRIDGE_RUN_IN_DJANGO`). **2.2.0** changes the default so the bridge does not run in Django unless opted in. Phase 6 items in the robustness doc remain optional.
- **Monitoring:** Connection status at `/mqtt_monitor/` (Docker) or `/mqtt/mqtt_monitor/` (manual URL include); CLI tools in `NEMO_mqtt_bridge.monitoring` (see `src/NEMO_mqtt_bridge/monitoring/README.md`).
- **License:** MIT. [Issues](https://github.com/alexanderenrique/NEMO-MQTT-Plugin/issues) · [Discussions](https://github.com/alexanderenrique/NEMO-MQTT-Plugin/discussions)

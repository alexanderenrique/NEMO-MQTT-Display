"""
Views for MQTT plugin.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse


@login_required
def mqtt_monitor(request):
    """Web-based monitor: stream of messages NEMO publishes to queue (pre-MQTT)."""
    mqtt_config = None
    broker_connected = None
    try:
        from .utils import get_mqtt_config
        from .db_publisher import db_publisher

        mqtt_config = get_mqtt_config()
        broker_connected = db_publisher.get_bridge_status()
    except Exception:
        pass
    response = render(
        request,
        "nemo_mqtt/monitor.html",
        {
            "title": "NEMO MQTT Monitor",
            "mqtt_config": mqtt_config,
            "broker_connected": broker_connected,
        },
    )
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@login_required
def mqtt_bridge_status(request):
    """Return current bridge status from DB as JSON."""
    status = None
    updated_at = None
    try:
        from .models import MQTTBridgeStatus

        row = MQTTBridgeStatus.objects.filter(key="default").first()
        if row:
            status = row.status
            updated_at = row.updated_at.isoformat() if row.updated_at else None
    except Exception:
        pass
    return JsonResponse({"status": status, "updated_at": updated_at})

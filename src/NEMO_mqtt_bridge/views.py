"""
Views for MQTT plugin.
"""

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required


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
@require_http_methods(["GET"])
def mqtt_monitor_api(request):
    """API endpoint: recent messages from queue (what NEMO has published to the pipeline)."""
    try:
        from .db_publisher import db_publisher

        messages = db_publisher.get_monitor_messages()
        broker_connected = db_publisher.get_bridge_status()
        response_data = {
            "messages": messages,
            "count": len(messages),
            "monitoring": True,
            "broker_connected": broker_connected,
        }
        response = JsonResponse(response_data)
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"
        return response
    except Exception as e:
        return JsonResponse(
            {
                "error": str(e),
                "messages": [],
                "count": 0,
                "monitoring": False,
                "broker_connected": None,
            },
            status=500,
        )

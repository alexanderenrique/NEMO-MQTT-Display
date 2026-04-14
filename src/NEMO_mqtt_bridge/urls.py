"""
URL patterns for MQTT plugin.
"""

from django.contrib.auth.decorators import login_required
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "mqtt_plugin"

urlpatterns = [
    path(
        "mqtt_monitor/",
        login_required(
            RedirectView.as_view(
                pattern_name="mqtt_plugin:bridge_status",
                permanent=True,
            )
        ),
        name="monitor",
    ),
    path("mqtt_bridge_status/", views.mqtt_bridge_status, name="bridge_status"),
]

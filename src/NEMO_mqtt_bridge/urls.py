"""
URL patterns for MQTT plugin.
"""

from django.urls import path
from . import views

app_name = "mqtt_plugin"

urlpatterns = [
    # MQTT Monitoring Dashboard
    path("mqtt_monitor/", views.mqtt_monitor, name="monitor"),
    path("mqtt_bridge_status/", views.mqtt_bridge_status, name="bridge_status"),
]

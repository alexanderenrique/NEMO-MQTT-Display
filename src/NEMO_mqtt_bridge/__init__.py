"""
NEMO_mqtt_bridge

A Django plugin that provides MQTT integration for NEMO tool usage events.
This plugin enables real-time publishing of tool usage data to MQTT brokers.
"""

__version__ = "2.2.3"
__author__ = "Alex Denton"
__email__ = "alexdenton998@gmail.com"

default_app_config = "NEMO_mqtt_bridge.apps.MqttPluginConfig"

"""
Views for MQTT plugin.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse


@login_required
def mqtt_bridge_status(request):
    """
    Return current bridge status from the database as JSON.

    All timestamp strings in the payload are in UTC; see ``mqtt_bridge_status_payload``
    docstring in ``utils`` for field meanings.
    """
    from .utils import mqtt_bridge_status_payload

    response = JsonResponse(mqtt_bridge_status_payload())
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response

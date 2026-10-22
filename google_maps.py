"""Internal client for the Google Maps APIs"""
import os
from typing import Any, Dict

from external_api import ExternalApiError, get_json

GOOGLE_MAPS_BASE_URL = "https://maps.googleapis.com/maps/api"


def directions(origin: str, destination: str, mode: str, **params: Any) -> Dict[str, Any]:
    """The first route leg Google finds from origin to destination.

    Extra params (departure_time, transit_mode, ...) are passed straight to the Directions API.
    """
    data = get_json(
        "Google directions",
        f"{GOOGLE_MAPS_BASE_URL}/directions/json",
        params={
            "origin": origin,
            "destination": destination,
            "mode": mode,
            "key": os.environ["GOOGLE_MAPS_API_KEY"],
            **params,
        },
    )
    if data.get("status") != "OK":
        raise ExternalApiError(
            f"Google couldn't plan {mode} from '{origin}' to '{destination}' ({data.get('status')})"
        )
    return data["routes"][0]["legs"][0]

"""Internal client for the NS (Dutch railways) APIs"""
import os
from datetime import datetime
from typing import Any, Dict, List

from external_api import get_json

NS_BASE_URL = "https://gateway.apiportal.ns.nl"


def _headers() -> Dict[str, str]:
    return {"Ocp-Apim-Subscription-Key": os.environ["NS_API_KEY"], "Accept": "application/json"}


def get_stations() -> List[Dict[str, Any]]:
    """All NS stations, as code, name and coordinates"""
    data = get_json("NS stations", f"{NS_BASE_URL}/reisinformatie-api/api/v2/stations", headers=_headers())
    return [
        {
            "code": station.get("code"),
            "name": station.get("namen", {}).get("lang"),
            "lat": station.get("lat"),
            "lng": station.get("lng"),
        }
        for station in data.get("payload", [])
    ]


def get_trips(from_station: str, to_station: str, departure: datetime) -> List[Dict[str, Any]]:
    """Train trips between two stations around the given departure time"""
    data = get_json(
        "NS trips",
        f"{NS_BASE_URL}/reisinformatie-api/api/v3/trips",
        params={
            "fromStation": from_station,
            "toStation": to_station,
            "dateTime": departure.isoformat(),
            "searchForArrival": "false",
        },
        headers=_headers(),
    )
    return data.get("trips", [])

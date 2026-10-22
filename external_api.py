from typing import Any, Dict, Optional

import requests

REQUEST_TIMEOUT_SECONDS = 10


class ExternalApiError(Exception):
    """An external API (NS, Google Maps) failed or couldn't answer the question"""


def get_json(service: str, url: str, params: Optional[Dict[str, Any]] = None,
             headers: Optional[Dict[str, str]] = None) -> Any:
    try:
        response = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        # Don't pass str(e) on: it contains the request URL, which includes the Google API key
        status = getattr(e.response, "status_code", None)
        reason = f"HTTP {status}" if status else type(e).__name__
        raise ExternalApiError(f"{service} request failed ({reason})") from None

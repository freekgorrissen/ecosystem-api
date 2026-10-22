"""Only lets our own Google accounts call the API.

The client signs in with Google and sends its access token as `Authorization: Bearer <token>`.
Google's tokeninfo endpoint tells us which app the token was issued to and whose account it is.
"""
import os
import time
from typing import Dict, Optional, Tuple

import requests
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from external_api import REQUEST_TIMEOUT_SECONDS

GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"

bearer = HTTPBearer(auto_error=False)

# Access token -> (email, expires at). Saves a call to Google on every request.
_verified_tokens: Dict[str, Tuple[str, float]] = {}


def allowed_emails() -> set:
    return {email.strip().lower() for email in os.environ["ALLOWED_EMAILS"].split(",") if email.strip()}


def require_allowed_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> str:
    """FastAPI dependency: the signed-in user's email, or 401/403"""
    if credentials is None:
        raise _unauthorized("Sign in with Google to use this API")

    email = _email_for_token(credentials.credentials)
    if email not in allowed_emails():
        raise HTTPException(status_code=403, detail="This Google account isn't allowed to use this API")
    return email


def _email_for_token(token: str) -> str:
    now = time.time()
    cached = _verified_tokens.get(token)
    if cached and cached[1] > now:
        return cached[0]

    try:
        response = requests.get(GOOGLE_TOKENINFO_URL, params={"access_token": token}, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Couldn't reach Google to check the sign-in") from None
    if response.status_code != 200:
        raise _unauthorized("Google sign-in is invalid or expired")

    info = response.json()
    # A token issued to some other app must not work here, even for an allowed account
    if info.get("aud") != os.environ["GOOGLE_CLIENT_ID"]:
        raise _unauthorized("Google sign-in was issued to a different app")
    if str(info.get("email_verified")).lower() != "true" or not info.get("email"):
        raise _unauthorized("Google sign-in has no verified email address")

    email = info["email"].lower()
    for expired in [t for t, (_, expires_at) in _verified_tokens.items() if expires_at <= now]:
        del _verified_tokens[expired]
    _verified_tokens[token] = (email, now + int(info.get("expires_in", 0)))
    return email


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})

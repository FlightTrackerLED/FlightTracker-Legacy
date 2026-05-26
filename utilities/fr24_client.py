"""Authenticated Flightradar24 client factory.

The production FlightTrackerLED boxes pulled live aircraft from a *paid*
Flightradar24 API subscription. The subscription token is loaded from
``config.py`` (``FR24_API_TOKEN``) or the ``FR24_API_TOKEN`` environment
variable and is never committed to this repository.

If no token is configured the client falls back to anonymous feed access,
which still works for light use but is aggressively rate-limited. Add your own
token in ``config.py`` (see ``config.py.example``) to use the paid tier.
"""

import os

from FlightRadar24.api import FlightRadar24API

try:
    from config import FR24_API_TOKEN
except (ModuleNotFoundError, ImportError, NameError):
    FR24_API_TOKEN = ""

# Anything containing this marker is treated as an unset placeholder.
_PLACEHOLDER_HINT = "YOUR_"


def get_fr24_token():
    """Return the configured FR24 token, or "" when only a placeholder is set."""
    token = (os.environ.get("FR24_API_TOKEN") or FR24_API_TOKEN or "").strip()
    if not token or _PLACEHOLDER_HINT in token:
        return ""
    return token


def build_api():
    """Build a FlightRadar24API authenticated with the paid token when available."""
    api = FlightRadar24API()
    token = get_fr24_token()
    if token:
        # Attach the subscription token to the underlying request session so
        # feed calls are billed against the paid Flightradar24 tier.
        for attr in ("session", "_session"):
            session = getattr(api, attr, None)
            if session is not None and hasattr(session, "headers"):
                session.headers["Authorization"] = f"Bearer {token}"
                break
    return api

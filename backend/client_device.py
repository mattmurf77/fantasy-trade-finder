"""Which client sent a request, for the stamps the server writes itself (G-068).

G-068's rule: a missing client signal is stored as NULL, never as another
client's name. analytics-lead set it for `user_events.source` on 2026-10-31
(a closed set of client-declared values, NULL when nothing identifies the
client, no backfill). head-eng extended it the same day to the `device_type`
and `platform` stamps that server-written events and experiment targeting
used to guess as "web".

Mobile sends `X-Device` on every request (`mobile/src/api/client.ts`). Web
and the extension send no `X-Device`; they declare themselves by `X-Source`.

No backend imports, so any route module can use it without an import cycle.
"""
from __future__ import annotations

# Clients that identify themselves by `X-Source` instead of `X-Device`.
DECLARED_SOURCES = frozenset({"web", "extension"})

# Stored when no client identified itself. analytics-lead owns this value
# (NULL, decided 2026-10-31).
MISSING_DEVICE_TYPE = None

_IOS_DEVICES = frozenset({"iphone", "ipad", "macos"})


def declared_source(headers):
    """`X-Source`, lowercased and stripped, when it is in DECLARED_SOURCES; else None."""
    source = str(headers.get("X-Source") or "").strip().lower()
    return source if source in DECLARED_SOURCES else None


def event_device_type(headers):
    """`device_type` for a server-written `user_events` row. First match wins:
    the `X-Device` header, stripped (stored as sent, the value
    `g.device_info["device_type"]` holds), then a declared `X-Source`, then
    MISSING_DEVICE_TYPE."""
    device = str(headers.get("X-Device") or "").strip()
    return device or declared_source(headers) or MISSING_DEVICE_TYPE


def device_platform(device_type):
    """Client platform for a resolved device_type: ios | android | web | extension, else None."""
    if device_type in _IOS_DEVICES:
        return "ios"
    if device_type in ("android", "web", "extension"):
        return device_type
    return None

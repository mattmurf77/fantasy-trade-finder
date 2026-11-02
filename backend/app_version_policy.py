"""B8 minimum-version gate — the write-side guard on `app_min_version`.

A typo in the kill switch is an outage: 122000 (one zero too many) or an
unreleased 12300 locks out every gate-aware build, because the mobile client
is deliberately permissive (it blocks on any positive safe-integer min above
its own version). So the SERVER refuses implausible values before they are
written. This one validator is shared by both write paths:

  * PUT /api/admin/config/app_min_version (server.admin_config_update) → 400
    with the reason;
  * scripts/set_knob.py, which refuses before writing on --local and remote
    alike (the remote path then also meets the PUT's check).

Rules, in order (0 is always accepted: lifting the gate is never refused):
  1. the value must be 0 or decode as x.y.z under major*10000 + minor*100 +
     patch — a finite, whole, non-negative number (minor and patch are then
     0–99 by construction);
  2. it must be <= 99999;
  3. it must be <= the NEXT MINOR above the current `mobile/app.json`
     version (1.21.4 → 1.22.0 = 12200; 1.22.0 → 1.23.0 = 12300), read at call
     time. No build above that can exist yet. If app.json cannot be read
     (missing, unparseable), only rules 1–2 apply.

Stdlib only, so set_knob.py can import it without the Flask app.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

APP_JSON = Path(__file__).resolve().parents[1] / "mobile" / "app.json"
MAX_APP_MIN_VERSION = 99999

_VERSION_RE = re.compile(r"^(\d{1,4})\.(\d{1,2})\.(\d{1,2})$")


def version_int(version) -> int | None:
    """"1.22.0" → 12200. Mirrors mobile/src/utils/appVersion.ts versionInt
    (docs/cross-client-invariants.md § App version int); else None."""
    if not isinstance(version, str):
        return None
    m = _VERSION_RE.match(version.strip())
    if not m:
        return None
    return int(m.group(1)) * 10000 + int(m.group(2)) * 100 + int(m.group(3))


def version_str(n: int) -> str:
    """12200 → "1.22.0" (n is a non-negative int)."""
    return f"{n // 10000}.{n // 100 % 100}.{n % 100}"


def current_app_version_int(app_json: Path | None = None) -> int | None:
    """`expo.version` of mobile/app.json as a version int, or None when the
    file is missing or unreadable or the version does not parse."""
    try:
        data = json.loads((app_json or APP_JSON).read_text())
        return version_int(data["expo"]["version"])
    except Exception:
        return None


def next_minor_cap(app_int: int) -> int:
    """The next minor's .0 above `app_int` (1.22.4 → 1.23.0 = 12300). A minor
    of 99 carries into the major (1.99.0 → 2.0.0)."""
    return (app_int // 100 + 1) * 100


def validate_app_min_version(value, app_json: Path | None = None) -> str | None:
    """A refusal reason for writing `value` to app_min_version, or None."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"app_min_version {value!r} is not a number"
    if not math.isfinite(v) or v < 0 or v != int(v):
        return (f"app_min_version {value!r} is not 0 or a version int "
                "(major*10000 + minor*100 + patch, e.g. 1.22.1 = 12201)")
    n = int(v)
    if n == 0:
        return None
    if n > MAX_APP_MIN_VERSION:
        return (f"app_min_version {n} is above the {MAX_APP_MIN_VERSION} "
                "ceiling (a typo? 1.22.0 is 12200)")
    app_int = current_app_version_int(app_json)
    if app_int is not None:
        cap = next_minor_cap(app_int)
        if n > cap:
            return (f"app_min_version {n} ({version_str(n)}) is above {cap} "
                    f"({version_str(cap)}), the next minor after mobile/app.json "
                    f"{version_str(app_int)}; no such build can exist yet, so "
                    "this would lock out every gate-aware build")
    return None

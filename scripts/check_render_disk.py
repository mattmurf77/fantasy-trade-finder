"""Read actual Render volume bytes, including WAL; exit 1 at 70%, 2 on missing data."""
import datetime as dt
import http.client
import json
import math
import os
import re
import sys
from urllib.parse import urlencode


def samples(series):
    if len(series) != 1:
        raise ValueError("expected one metric series")
    return {dt.datetime.fromisoformat(v["timestamp"].replace("Z", "+00:00")): float(v["value"])
            for v in series[0]["values"]}


def usage_percent(used, capacity, now):
    u, c = samples(used), samples(capacity)
    overlap = u.keys() & c.keys()
    if not overlap:
        raise ValueError("no matching timestamps")
    t = max(overlap)
    if not 0 <= (now - t).total_seconds() <= 600:
        raise ValueError("stale metric")
    if not all(math.isfinite(n) for n in (u[t], c[t])) or u[t] < 0 or c[t] <= 0:
        raise ValueError("invalid disk sample")
    return 100 * u[t] / c[t]


def main():
    resource = os.environ.get("RENDER_POSTGRES_ID", "")
    token = os.environ.get("RENDER_METRICS_TOKEN")
    if not token or not re.fullmatch(r"dpg-[a-z0-9]+(?:-[a-z])?", resource):
        print("Set the Postgres resource ID and a metrics-read token.", file=sys.stderr)
        return 2
    def read(metric):
        conn = http.client.HTTPSConnection("api.render.com", timeout=20)
        try:
            conn.request("GET", "/v1/metrics/" + metric + "?" + urlencode({"resource": resource}),
                         headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
            response = conn.getresponse()
            if response.status != 200:
                raise ValueError(f"Render returned HTTP {response.status}")
            return json.load(response)
        finally:
            conn.close()
    try:
        percent = usage_percent(read("disk-usage"), read("disk-capacity"), dt.datetime.now(dt.timezone.utc))
    except (OSError, http.client.HTTPException, KeyError, TypeError, ValueError, OverflowError) as exc:
        print("Cannot verify disk usage (" + type(exc).__name__ + ").", file=sys.stderr)
        return 2
    print(f"Fleeced Postgres uses {percent:.2f}% of its volume (alert at 70%).")
    return int(percent >= 70)


if __name__ == "__main__":
    sys.exit(main())

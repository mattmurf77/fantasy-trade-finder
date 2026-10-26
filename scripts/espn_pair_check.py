#!/usr/bin/env python3
"""R1 check: does ESPN bind espn_s2 to the SWID? (platform sign-in, D4 step 4)

ESPN sign-in refuses everyone unless ESPN rejects a user's espn_s2 when it is
sent with a DIFFERENT member's SWID. This script looks, read-only, using the
operator's own cookies and one of the operator's PRIVATE leagues.

Reads the environment only (no files):
    ESPN_CHECK_S2      espn_s2 cookie
    ESPN_CHECK_SWID    SWID cookie
    ESPN_CHECK_LEAGUE  a PRIVATE ESPN league id you are in
    ESPN_CHECK_SEASON  season (default 2026)

    set -a; . ./secrets.local.env; set +a; python3 scripts/espn_pair_check.py

Makes four GET requests to ESPN's league-read API, nothing else:
    (a) espn_s2 + your SWID                    expect 200
    (b) no cookies                             expect 401/403
    (c) espn_s2 + another member's SWID        401/403 if bound
    (d) espn_s2 + a random SWID                401/403 if bound
Prints each HTTP status and one verdict line. Never prints a cookie, a SWID
or a response body. Writes no files. Standard library only; the URL, headers
and cookie forms match backend/espn_service.py (pinned by a test).
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

ESPN_READS_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
AUTH_REFUSED = (401, 403)


def league_url(league_id, season):
    return (f"{ESPN_READS_BASE}/seasons/{season}/segments/0/leagues/"
            f"{urllib.parse.quote(str(league_id))}"
            "?view=mTeam&view=mRoster&view=mSettings")


def canonical_espn_s2(value):
    v = (value or "").strip()
    if not v or urllib.parse.unquote(v) != v:
        return v
    return urllib.parse.quote(v, safe="")


def canonical_swid(value):
    v = (value or "").strip()
    if not v or (v.startswith("{") and v.endswith("}")):
        return v
    return "{" + v.strip("{}") + "}"


def read(url, espn_s2=None, swid=None):
    """One GET. Returns (status, body); status is an int or 'error:<Type>'."""
    headers = dict(HEADERS)
    if espn_s2 and swid:
        headers["Cookie"] = (f"espn_s2={canonical_espn_s2(espn_s2)}; "
                             f"SWID={canonical_swid(swid)}")
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return f"error:{type(e).__name__}", None


def other_member_swid(body, own_swid):
    """Another owner's/member's SWID from read (a)'s JSON, or None."""
    try:
        data = json.loads(body or b"")
    except ValueError:
        return None
    own = canonical_swid(own_swid).upper()
    seen = []
    for team in data.get("teams") or []:
        seen.append(team.get("primaryOwner") or "")
        seen.extend(team.get("owners") or [])
    seen.extend(m.get("id") or "" for m in data.get("members") or [])
    return next((s for s in seen if s and canonical_swid(s).upper() != own),
                None)


def verdict(a, b, c, d):
    if a == 200 and c in AUTH_REFUSED and d in AUTH_REFUSED:
        return "PAIR_BOUND"
    if a == 200 and b in AUTH_REFUSED and 200 in (c, d):
        return "PAIR_NOT_BOUND"
    return "INCONCLUSIVE"


def main(env=None):
    env = os.environ if env is None else env
    espn_s2 = (env.get("ESPN_CHECK_S2") or "").strip()
    swid = (env.get("ESPN_CHECK_SWID") or "").strip()
    league = (env.get("ESPN_CHECK_LEAGUE") or "").strip()
    season = (env.get("ESPN_CHECK_SEASON") or "2026").strip()
    if not (espn_s2 and swid and league.isdigit() and season.isdigit()):
        print("set ESPN_CHECK_S2, ESPN_CHECK_SWID and a numeric "
              "ESPN_CHECK_LEAGUE (ESPN_CHECK_SEASON optional)")
        return 2
    url = league_url(league, season)

    a, body = read(url, espn_s2, swid)
    print(f"(a) both cookies:           {a}")
    b, _ = read(url)
    print(f"(b) anonymous:              {b}")
    other = other_member_swid(body, swid) if a == 200 else None
    body = None
    c = read(url, espn_s2, other)[0] if other else "skipped (no other member)"
    print(f"(c) espn_s2 + other member: {c}")
    d, _ = read(url, espn_s2, "{" + str(uuid.uuid4()).upper() + "}")
    print(f"(d) espn_s2 + random SWID:  {d}")
    print(f"verdict: {verdict(a, b, c, d)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

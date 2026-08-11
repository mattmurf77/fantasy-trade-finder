#!/usr/bin/env python3
"""verify-mfl-send.py — OPERATOR-RUN live verification for "Send in MFL".

Claude does not run this — it authenticates with your MFL credentials, which
is operator-only. Run it yourself.

Automates the live-verification checklist in
docs/feedback/items/177-mfl-auth-link/send-in-mfl-scope.md (items 1-4 and the
revoke half of item 7). Self-contained: stdlib only, no backend imports.

Credentials come from `secrets.local.env` at the repo root (gitignored):

    MFL_USERNAME=...          # your MFL login
    MFL_PASSWORD=...          # your MFL password
    MFL_VERIFY_LEAGUE_ID=...  # a TEST league you own a franchise in

Usage:

    # Read-only verification (login, cookie auth check, host resolution,
    # User-Agent probe, pick encodings). No import/write call is made.
    python3 qa/verify-mfl-send.py

    # No-auth subset only (host resolution + User-Agent probe; no login):
    python3 qa/verify-mfl-send.py --public-only [--league 62846]

    # Fire ONE real tradeProposal, print the raw response verbatim, then
    # immediately revoke it (and probe the api. host with the already-revoked
    # trade id to answer the import-host question). ALL FOUR flags required:
    python3 qa/verify-mfl-send.py --send --offeredto 0005 \
        --give 13130,FP_0001_2027_1 [--receive 14085] --confirm

    # Revoke a specific pending trade id (cleanup, if auto-revoke failed):
    python3 qa/verify-mfl-send.py --revoke-id <TRADE_ID> --confirm

What each section answers (checklist item in brackets):
  A. Host resolution — the league's assigned wwwNN host.        [context §1]
  B. User-Agent probe — proves MFL blanks responses without a
     non-default UA, even on public READS (the UA is load-bearing).
  C. Login + cookie auth check — real MFL_USER_ID capture, then
     myleagues with the real cookie (works) and a garbage cookie
     (captures the dead-cookie failure shape).                        [4]
  D. Pick encodings — rosters + futureDraftPicks raw shapes and the
     FP_{originalPickFor}_{year}_{round} encodings derived from them. [3]
  E. --send only: tradeProposal fired at the wwwNN host — raw body
     printed VERBATIM (resolves "<status>OK</status> XML vs JSON=1
     JSON") — then pendingTrades, then tradeResponse RESPONSE=revoke
     (raw printed), then the same revoke replayed against the api.
     host to reveal whether imports work there at all.            [1, 2, 7]

Safety rails:
  * Without --confirm the script REFUSES to make any import (write) call.
  * --send requires --offeredto and --give too; there are no defaults.
  * The proposal is revoked immediately after capture.
  * The MFL_USER_ID cookie value is masked in all output.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_HOST = "api.myfantasyleague.com"
DEFAULT_YEAR = 2026
UA = "FantasyTradeFinder/1.0 (+https://fantasytradefinder.app)"
SPACING_S = 1.1          # MFL guidance: >=1s between requests
TIMEOUT = 20

_last_req = 0.0


def _pace():
    global _last_req
    wait = SPACING_S - (time.time() - _last_req)
    if wait > 0:
        time.sleep(wait)
    _last_req = time.time()


def http_get(url: str, *, ua: str | None = UA, cookie: str | None = None,
             follow_redirects: bool = True) -> tuple[int, str, dict]:
    """(status, body, headers). ua=None sends NO User-Agent header override
    (urllib's default Python-urllib/x.y goes out)."""
    _pace()
    headers = {"Accept": "*/*"}
    if ua is not None:
        headers["User-Agent"] = ua
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    if follow_redirects:
        opener = urllib.request.build_opener()
    else:
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                return None
        opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            return (getattr(resp, "status", 200),
                    resp.read().decode("utf-8", "replace"),
                    dict(resp.headers))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, body, dict(e.headers)


def http_post(url: str, data: dict) -> tuple[int, str]:
    _pace()
    payload = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={"User-Agent": UA,
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return getattr(resp, "status", 200), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception:
            return e.code, ""


def load_secrets() -> dict:
    """KEY=VALUE lines from secrets.local.env at the repo root."""
    root = Path(__file__).resolve().parent.parent
    path = root / "secrets.local.env"
    out: dict = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def mask(cookie: str) -> str:
    v = cookie.split("=", 1)[-1]
    return f"MFL_USER_ID={v[:6]}…({len(v)} chars)" if v else cookie


def hr(title: str):
    print(f"\n{'=' * 74}\n{title}\n{'=' * 74}")


def show(label: str, body: str, limit: int = 1500):
    trimmed = body if len(body) <= limit else body[:limit] + f"\n… [{len(body)} bytes total]"
    print(f"--- {label} (verbatim{'' if len(body) <= limit else ', trimmed'}) ---")
    print(trimmed if trimmed.strip() else "<EMPTY BODY>")
    print("--- end ---")


# ── Section A: host resolution ──────────────────────────────────────────────

def resolve_host(league_id: str, year: int) -> str:
    url = f"https://{API_HOST}/{year}/home/{league_id}"
    status, _, headers = http_get(url, follow_redirects=False)
    loc = headers.get("Location") or ""
    m = re.search(r"https?://([a-z0-9.-]*myfantasyleague\.com)", loc)
    host = m.group(1) if m else ""
    print(f"GET {url} -> HTTP {status}, Location: {loc or '<none>'}")
    if not host:
        sys.exit(f"FATAL: couldn't resolve a wwwNN host for league {league_id}")
    print(f"ANSWER [host]: league {league_id} lives on {host}")
    return host


# ── Section B: User-Agent probe (public read, no auth) ──────────────────────

def ua_probe(host: str, league_id: str, year: int):
    url = (f"https://{host}/{year}/export?"
           + urllib.parse.urlencode({"TYPE": "futureDraftPicks",
                                     "L": league_id, "JSON": "1"}))
    s1, b1, _ = http_get(url, ua=UA)
    s2, b2, _ = http_get(url, ua=None)     # urllib default (Python-urllib/3.x)
    s3, b3, _ = http_get(url, ua="")       # EMPTY UA — the 2026-08-11 finding
    print(f"with app User-Agent      : HTTP {s1}, {len(b1)} bytes")
    print(f"with default urllib UA   : HTTP {s2}, {len(b2)} bytes")
    print(f"with EMPTY User-Agent    : HTTP {s3}, {len(b3)} bytes")
    verdict = ("CONFIRMED — an empty UA gets a blanked/starved response"
               if len(b3) < len(b1) else
               "NOT reproduced right now — empty UA returned a similar body")
    print(f"ANSWER [UA load-bearing]: {verdict}")
    show("futureDraftPicks (app UA)", b1, 800)
    return b1


# ── Section C: login + cookie auth check ────────────────────────────────────

def login(username: str, password: str, year: int) -> str:
    status, body = http_post(f"https://{API_HOST}/{year}/login",
                             {"USERNAME": username, "PASSWORD": password,
                              "XML": "1"})
    m = re.search(r'MFL_USER_ID\s*=\s*"([^"]+)"', body)
    if not m:
        show("login response", body, 600)
        sys.exit(f"FATAL: MFL rejected the login (HTTP {status}).")
    cookie = f"MFL_USER_ID={m.group(1)}"
    print(f"login OK (HTTP {status}) -> {mask(cookie)}")
    return cookie


def cookie_auth_check(cookie: str, year: int):
    url = (f"https://{API_HOST}/{year}/export?"
           + urllib.parse.urlencode({"TYPE": "myleagues",
                                     "FRANCHISE_NAMES": "1", "JSON": "1"}))
    s_ok, b_ok, _ = http_get(url, cookie=cookie)
    print(f"myleagues with REAL cookie   : HTTP {s_ok}, {len(b_ok)} bytes")
    show("myleagues (real cookie)", b_ok, 800)
    s_bad, b_bad, _ = http_get(url, cookie="MFL_USER_ID=bogus_dead_cookie")
    print(f"myleagues with GARBAGE cookie: HTTP {s_bad}, {len(b_bad)} bytes")
    show("myleagues (garbage cookie) — the dead-cookie failure shape", b_bad, 600)
    print("ANSWER [cookie auth]: real cookie returns leagues; the garbage-"
          "cookie capture above is what mfl_auth_expired mapping must match.")


# ── Section D: pick encodings ───────────────────────────────────────────────

def pick_encodings(host: str, league_id: str, year: int, cookie: str | None,
                   fdp_body: str):
    url = (f"https://{host}/{year}/export?"
           + urllib.parse.urlencode({"TYPE": "rosters", "L": league_id,
                                     "JSON": "1"}))
    _, rosters, _ = http_get(url, cookie=cookie)
    show("rosters", rosters, 900)
    try:
        data = json.loads(fdp_body)
        picks = []
        for fr in (data.get("futureDraftPicks", {}) or {}).get("franchise", []):
            fid = fr.get("id")
            fps = fr.get("futureDraftPick", [])
            if isinstance(fps, dict):
                fps = [fps]
            for p in fps:
                picks.append((fid, p))
        print(f"parsed {len(picks)} future picks; first 5 with FP_ encodings:")
        for fid, p in picks[:5]:
            orig = str(p.get("originalPickFor", "")).zfill(4)
            enc = f"FP_{orig}_{p.get('year')}_{p.get('round')}"
            print(f"  holder {fid}: {json.dumps(p)}  ->  {enc}")
        print("ANSWER [encodings]: originalPickFor is 4-digit padded, round is "
              "1-based unpadded -> FP_{originalPickFor}_{year}_{round} inputs "
              "are correct. (DP_ current-year picks: confirm zero-basing via a "
              "--send that includes one, or in MFL's UI.)")
    except (ValueError, AttributeError) as e:
        print(f"could not parse futureDraftPicks JSON ({e}) — see raw above.")


# ── Section E: the one real send (+ immediate revoke) ───────────────────────

def find_trade_id(host: str, league_id: str, year: int, cookie: str) -> str | None:
    url = (f"https://{host}/{year}/export?"
           + urllib.parse.urlencode({"TYPE": "pendingTrades", "L": league_id,
                                     "JSON": "1"}))
    _, body, _ = http_get(url, cookie=cookie)
    show("pendingTrades", body, 1200)
    for pat in (r'"trade_id"\s*:\s*"?(\d+)', r'trade_id\s*=\s*"(\d+)"',
                r'"tradeid"\s*:\s*"?(\d+)', r'TRADE_ID["=\s:]+(\d+)'):
        m = re.findall(pat, body, re.IGNORECASE)
        if m:
            return m[-1]        # newest last, best-effort
    return None


def do_import(host: str, year: int, params: dict, cookie: str, label: str) -> str:
    url = f"https://{host}/{year}/import?" + urllib.parse.urlencode(params)
    print(f"GET {url}")
    status, body, _ = http_get(url, cookie=cookie)
    print(f"HTTP {status}")
    show(label, body, 2000)
    return body


def send_and_revoke(host: str, league_id: str, year: int, cookie: str,
                    offeredto: str, give: list, receive: list,
                    comments: str | None):
    hr("E1. tradeProposal — THE one real send (wwwNN host)")
    params = {"TYPE": "tradeProposal", "L": league_id,
              "OFFEREDTO": offeredto.zfill(4),
              "WILL_GIVE_UP": ",".join(give),
              "WILL_RECEIVE": ",".join(receive),
              "EXPIRES": str(int(time.time()) + 24 * 3600),   # 1 day, it dies fast
              "JSON": "1"}
    if comments:
        params["COMMENTS"] = comments[:512]
    body = do_import(host, year, params, cookie,
                     "tradeProposal response — ANSWER [response shape]: is this "
                     "<status>OK</status> XML or JSON=1 JSON?")

    hr("E2. locate TRADE_ID + revoke")
    trade_id = find_trade_id(host, league_id, year, cookie)
    if not trade_id:
        print("!! Couldn't auto-parse a TRADE_ID from pendingTrades (raw above).")
        print("!! REVOKE MANUALLY in MFL's UI, or re-run with "
              "--revoke-id <TRADE_ID> --confirm.")
        return
    print(f"newest TRADE_ID: {trade_id}")
    revoke_params = {"TYPE": "tradeResponse", "L": league_id,
                     "TRADE_ID": trade_id, "RESPONSE": "revoke", "JSON": "1"}
    do_import(host, year, revoke_params, cookie,
              "tradeResponse RESPONSE=revoke response")

    hr("E3. api.-host import probe (already-revoked trade id — cannot mutate)")
    do_import(API_HOST, year, revoke_params, cookie,
              "same revoke replayed at api.myfantasyleague.com — ANSWER "
              "[import host]: does the api. host process imports at all, or "
              "only wwwNN?")


# ── main ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Operator-run Send-in-MFL live verification")
    ap.add_argument("--year", type=int, default=DEFAULT_YEAR)
    ap.add_argument("--league", help="override MFL_VERIFY_LEAGUE_ID")
    ap.add_argument("--public-only", action="store_true",
                    help="no-auth subset: host resolution + UA probe only")
    ap.add_argument("--send", action="store_true",
                    help="fire ONE real tradeProposal then revoke it "
                         "(requires --offeredto, --give and --confirm)")
    ap.add_argument("--offeredto", help="counterparty franchise id, e.g. 0005")
    ap.add_argument("--give", help="comma-separated MFL asset ids you give "
                                   "(players / DP_RR_SS / FP_FFFF_YYYY_R)")
    ap.add_argument("--receive", default="",
                    help="comma-separated MFL asset ids you receive (optional)")
    ap.add_argument("--comments", default="FTF live verification — auto-revoked")
    ap.add_argument("--revoke-id", help="revoke this TRADE_ID and exit (needs --confirm)")
    ap.add_argument("--confirm", action="store_true",
                    help="required for ANY import (write) call")
    args = ap.parse_args()

    secrets = load_secrets()
    league = args.league or secrets.get("MFL_VERIFY_LEAGUE_ID") or ""
    if not league.isdigit():
        sys.exit("FATAL: set MFL_VERIFY_LEAGUE_ID in secrets.local.env "
                 "(or pass --league <id>).")

    if (args.send or args.revoke_id) and not args.confirm:
        sys.exit("REFUSING: --send/--revoke-id perform a real MFL write. "
                 "Add --confirm (plus --offeredto and --give for --send).")
    if args.send and not (args.offeredto and args.give):
        sys.exit("REFUSING: --send requires --offeredto AND --give AND "
                 "--confirm. No defaults.")

    hr(f"A. Host resolution (league {league}, {args.year})")
    host = resolve_host(league, args.year)

    hr("B. User-Agent probe (public read, no auth)")
    fdp_body = ua_probe(host, league, args.year)

    if args.public_only:
        print("\n--public-only: stopping before any authenticated call.")
        return

    username = secrets.get("MFL_USERNAME") or ""
    password = secrets.get("MFL_PASSWORD") or ""
    if not username or not password:
        sys.exit("FATAL: fill MFL_USERNAME / MFL_PASSWORD in secrets.local.env "
                 "(or use --public-only).")

    hr("C. Login + cookie auth check")
    cookie = login(username, password, args.year)
    cookie_auth_check(cookie, args.year)

    if args.revoke_id:
        hr(f"Revoke-only: TRADE_ID {args.revoke_id}")
        do_import(host, args.year,
                  {"TYPE": "tradeResponse", "L": league,
                   "TRADE_ID": args.revoke_id, "RESPONSE": "revoke",
                   "JSON": "1"}, cookie, "tradeResponse revoke response")
        return

    hr("D. Pick encodings (rosters + futureDraftPicks)")
    pick_encodings(host, league, args.year, cookie, fdp_body)

    if args.send:
        give = [a.strip() for a in args.give.split(",") if a.strip()]
        receive = [a.strip() for a in args.receive.split(",") if a.strip()]
        send_and_revoke(host, league, args.year, cookie,
                        args.offeredto, give, receive, args.comments)
    else:
        print("\nRead-only run complete. To resolve the import-host and "
              "response-shape questions, re-run with:\n"
              "  --send --offeredto FFFF --give <ids> --confirm")


if __name__ == "__main__":
    main()

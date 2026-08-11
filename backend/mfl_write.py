"""mfl_write.py — adapter for MFL's documented import API ("Send in MFL").

The write-side sibling of `mfl_service.py` (reads) and the MFL analogue of
`sleeper_write.py` (Sleeper's ToS-adverse write path). Unlike Sleeper, this
rides MyFantasyLeague's **official, sanctioned** import API
(`{host}/{year}/import?TYPE=tradeProposal&...`) — verified against
`api.myfantasyleague.com/2026/api_info?STATE=details` (2026-07-25 + 2026-08-11):

  - `import?TYPE=tradeProposal` params: `L` (league id), `OFFEREDTO` (target
    franchise id), `WILL_GIVE_UP` / `WILL_RECEIVE` (comma-separated asset ids),
    optional `COMMENTS`, `EXPIRES` (unix seconds; MFL default is one week).
    "Access restricted to league owners."
  - `import?TYPE=tradeResponse` params: `L`, `TRADE_ID`,
    `RESPONSE=accept|reject|revoke`, optional `COMMENTS`.
  - Auth: the `MFL_USER_ID` **session cookie** (the one #177 stores
    Fernet-encrypted in `mfl_credentials`). MFL's APIKEY works for exports
    only, "not imports or commissioner operations" — so writes MUST ride the
    cookie.
  - Asset id formats (documented): players = bare MFL player ids;
    current-year draft picks = `DP_RR_SS` (round/slot, ZERO-BASED — `DP_02_05`
    is "3rd round, 6th pick"); future picks = `FP_FFFF_YYYY_R`
    (ORIGINAL-owner franchise id, year, round — e.g. `FP_0005_2027_1`);
    blind-bid dollars = `BB_10.50` (not built here).

Host gotcha (same as reads, docs/integrations/mfl.md §1): league-scoped
requests hit the league's assigned `wwwNN.myfantasyleague.com` host, never
the `api.` host (which returns empty for league data on exports).

TODO(live-verify) — three things the docs do NOT pin down; confirm against a
real test league before flag graduation (checklist in
docs/feedback/items/177-mfl-auth-link/send-in-mfl-scope.md):
  1. Import success/error body shape — `<status>OK</status>` XML vs `JSON=1`
     JSON. `_parse_import_response` below accepts both and refuses anything
     it can't positively read as success.
  2. Whether imports enforce the `wwwNN` host like exports (we use it
     regardless — it is correct for both cases).
  3. `FP_`/`DP_` padding in practice (franchise 4-digit zero-pad, two-digit
     zero-based round/slot) — cross-check against the league's stored
     `futureDraftPicks` snapshot (`leagues.platform_future_picks`).

Design mirrors sleeper_write.py: pure module — no Flask/DB imports; the HTTP
call is injectable via `_opener` so tests never touch the network. The cookie
is a full-session credential: never logged, never an event property.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from backend.mfl_service import MFL_USER_AGENT

_HTTP_TIMEOUT = 15

#: MFL guidance: space requests ≥1s apart. Imports are single-shot per user
#: action, but a propose immediately after a pre-flight rosters export can
#: violate the spacing — the live path enforces it module-wide.
_REQUEST_SPACING_SECONDS = 1.0
_last_live_request_ts: float = 0.0

#: Default offer lifetime when the caller doesn't pass one: ~7 days, matching
#: MFL's own documented default ("default is one week") but stated explicitly
#: so FTF never depends on an undocumented server-side default changing.
DEFAULT_EXPIRES_SECONDS = 7 * 24 * 3600


# ---------------------------------------------------------------------------
# Errors — the route maps these to structured JSON error codes.
# ---------------------------------------------------------------------------

class MflWriteError(Exception):
    """A write to MFL failed. `kind` steers the caller's handling:
      'auth'    → cookie missing/expired/rejected → prompt MFL re-sign-in
      'network' → transport problem → retry / fallback
      'error'   → MFL refused the import (bad asset, trades disabled, …)
      'input'   → caller-side validation failure (never sent)
    """

    def __init__(self, message: str, *, kind: str = "error", detail: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.detail = detail


class MflWriteAuthError(MflWriteError):
    """MFL rejected the session cookie. Caller should drop the stored
    credential and prompt the user to sign in with MFL again."""

    def __init__(self, message: str = "MFL rejected the session cookie",
                 detail: str | None = None):
        super().__init__(message, kind="auth", detail=detail)


# ---------------------------------------------------------------------------
# Asset-id construction / validation
# ---------------------------------------------------------------------------

#: Bare MFL player id (numeric string, e.g. "13130").
_PLAYER_ID_RE = re.compile(r"^\d{1,6}$")
#: Current-year draft pick: DP_RR_SS, both zero-based ("DP_02_05" = R3 P6).
_DP_RE = re.compile(r"^DP_\d{1,2}_\d{1,2}$")
#: Future pick: FP_<orig franchise>_<year>_<round> ("FP_0005_2027_1").
_FP_RE = re.compile(r"^FP_\d{4}_\d{4}_\d{1,2}$")


def encode_current_year_pick(round_zero_based: int, slot_zero_based: int) -> str:
    """`DP_RR_SS` — round and slot are ZERO-BASED per MFL's docs
    ("DP_02_05 … 3rd round, 6th pick"), two-digit padded.
    TODO(live-verify): padding width unconfirmed against a live import."""
    r, s = int(round_zero_based), int(slot_zero_based)
    if r < 0 or s < 0:
        raise MflWriteError("pick round/slot must be zero-based non-negative",
                            kind="input")
    return f"DP_{r:02d}_{s:02d}"


def encode_future_pick(original_franchise_id: str, year: int, round_1_based: int) -> str:
    """`FP_FFFF_YYYY_R` — ORIGINAL-owner franchise id (4-digit zero-padded,
    matching the `originalPickFor` values in the futureDraftPicks export,
    e.g. "0005"), season year, 1-based round.
    TODO(live-verify): confirm the round is 1-based & unpadded ("FP_0005_2018_2"
    in MFL's docs) against a real pick-inclusive import."""
    fid = str(original_franchise_id).strip()
    if fid.isdigit():
        fid = fid.zfill(4)
    if not re.fullmatch(r"\d{4}", fid):
        raise MflWriteError(f"bad franchise id for future pick: {original_franchise_id!r}",
                            kind="input")
    y, r = int(year), int(round_1_based)
    if not (2000 <= y <= 2100) or r < 1:
        raise MflWriteError("bad year/round for future pick", kind="input")
    return f"FP_{fid}_{y}_{r}"


def is_valid_asset_id(asset: str) -> bool:
    """True for the three asset shapes a propose may carry: bare MFL player
    id, `DP_` current-year pick, `FP_` future pick."""
    a = str(asset)
    return bool(_PLAYER_ID_RE.match(a) or _DP_RE.match(a) or _FP_RE.match(a))


def is_pick_asset_id(asset: str) -> bool:
    """True only for the two PICK shapes (`DP_…` / `FP_…`) — what the route
    accepts in `give_pick_assets`/`receive_pick_assets` (player ids must ride
    the crosswalked player fields instead)."""
    a = str(asset)
    return bool(_DP_RE.match(a) or _FP_RE.match(a))


# ---------------------------------------------------------------------------
# propose_trade — request construction
# ---------------------------------------------------------------------------

@dataclass
class ProposeTradeRequest:
    league_id: str
    offered_to: str                 # counterparty franchise id, e.g. "0005"
    will_give_up: list = field(default_factory=list)   # MFL asset ids I send
    will_receive: list = field(default_factory=list)   # MFL asset ids I get
    comments: str | None = None
    expires: int | None = None      # unix seconds; None → now + 7 days


def normalize_franchise_id(fid) -> str:
    """MFL franchise ids are 4-digit zero-padded ("0005"). Stored/parsed ids
    sometimes arrive bare ("5") — normalize; refuse non-numeric."""
    s = str(fid).strip()
    if s.lower().startswith("f"):        # tolerate "f0005"
        s = s[1:]
    if not s.isdigit():
        raise MflWriteError(f"franchise id must be numeric, got {fid!r}", kind="input")
    return s.zfill(4)


def build_import_params(req: ProposeTradeRequest, *, now: float | None = None) -> dict:
    """The exact query params for `import?TYPE=tradeProposal`. Raises
    MflWriteError(kind='input') on anything malformed — nothing invalid is
    ever sent (the never-silently-drop-an-asset guarantee lives one level up:
    the route hard-blocks on unmapped assets before building this)."""
    lid = str(req.league_id).strip()
    if not lid.isdigit():
        raise MflWriteError("league_id must be numeric", kind="input")
    offered_to = normalize_franchise_id(req.offered_to)

    give = [str(a).strip() for a in (req.will_give_up or [])]
    receive = [str(a).strip() for a in (req.will_receive or [])]
    if not give and not receive:
        raise MflWriteError("trade has no assets on either side", kind="input")
    for a in give + receive:
        if not is_valid_asset_id(a):
            raise MflWriteError(f"invalid MFL asset id: {a!r}", kind="input")

    expires = int(req.expires if req.expires is not None
                  else (now if now is not None else time.time()) + DEFAULT_EXPIRES_SECONDS)

    params = {
        "TYPE": "tradeProposal",
        "L": lid,
        "OFFEREDTO": offered_to,
        "WILL_GIVE_UP": ",".join(give),
        "WILL_RECEIVE": ",".join(receive),
        "EXPIRES": str(expires),
        # TODO(live-verify): whether JSON=1 applies to imports like exports.
        # Harmless if ignored; _parse_import_response handles XML regardless.
        "JSON": "1",
    }
    comments = (req.comments or "").strip()
    if comments:
        params["COMMENTS"] = comments[:512]
    return params


def import_url(host: str, year: int, params: dict) -> str:
    """`https://{host}/{year}/import?...` — the league's assigned wwwNN host,
    same host rule as exports (docs/integrations/mfl.md §1)."""
    if not host or "myfantasyleague.com" not in str(host):
        raise MflWriteError(f"bad MFL host: {host!r}", kind="input")
    return f"https://{host}/{int(year)}/import?{urllib.parse.urlencode(params)}"


# ---------------------------------------------------------------------------
# Response parsing — the least-documented part of the surface.
# ---------------------------------------------------------------------------

_XML_STATUS_RE = re.compile(r"<status[^>]*>([^<]*)</status>", re.IGNORECASE)
_XML_ERROR_RE = re.compile(r"<error[^>]*>([^<]*)</error>", re.IGNORECASE)


def _parse_import_response(raw: str) -> dict:
    """Normalize an import response to {"status": "OK", "raw": <trimmed>}.

    TODO(live-verify): built from MFL's documented conventions, not a live
    capture. Accepts BOTH shapes MFL uses elsewhere:
      - XML: `<status>OK</status>` success / `<error>…</error>` failure
        (the login endpoint's convention)
      - JSON (if JSON=1 applies to imports): {"status": "OK"} / {"error": …}
    Anything that cannot be positively read as success raises — a send is
    never reported "proposed" on an ambiguous body.
    """
    text = (raw or "").strip()
    if not text:
        raise MflWriteError("empty response from MFL import", detail="")

    # JSON first (JSON=1 requested).
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        err = parsed.get("error")
        if err:
            _raise_import_error(str(err))
        status = str(parsed.get("status") or "").strip()
        if status.upper().startswith("OK"):
            return {"status": "OK", "raw": text[:500]}
        raise MflWriteError("unrecognized MFL import response",
                            detail=text[:500])

    # XML fallback.
    m = _XML_ERROR_RE.search(text)
    if m:
        _raise_import_error(m.group(1).strip())
    m = _XML_STATUS_RE.search(text)
    if m and m.group(1).strip().upper().startswith("OK"):
        return {"status": "OK", "raw": text[:500]}
    raise MflWriteError("unrecognized MFL import response", detail=text[:500])


def _raise_import_error(message: str):
    """MFL signals auth problems in bodies as often as in HTTP codes (its
    login endpoint 200s bad credentials with an <error> body)."""
    low = message.lower()
    if any(w in low for w in ("cookie", "logged in", "log in", "login",
                              "not authenticated", "permission", "owner")):
        raise MflWriteAuthError(detail=message[:500])
    raise MflWriteError("MFL rejected the import", detail=message[:500])


# ---------------------------------------------------------------------------
# HTTP issue. `_opener` is injectable so unit tests never hit the network.
# ---------------------------------------------------------------------------

def _issue_import(op: str, cookie: str, url: str, *, league_id: str,
                  host: str, _opener=None) -> dict:
    if not cookie:
        raise MflWriteAuthError("no MFL cookie available")

    headers = {"User-Agent": MFL_USER_AGENT, "Accept": "*/*", "Cookie": cookie}
    request = urllib.request.Request(url, headers=headers)
    opener = _opener or urllib.request.urlopen

    # Live-path politeness: ≥1s since the last live MFL write-module request
    # (mirrors mfl_service's spacing; skipped entirely under injected openers).
    global _last_live_request_ts
    if _opener is None:
        wait = _REQUEST_SPACING_SECONDS - (time.time() - _last_live_request_ts)
        if 0 < wait <= _REQUEST_SPACING_SECONDS:
            time.sleep(wait)
        _last_live_request_ts = time.time()

    # obs.api_events — status/latency/error kind only; the Cookie header value
    # is never an event property (docs/integrations/mfl.md §6 must-redact).
    from . import api_observability as _api_obs
    with _api_obs.observe_call("mfl", f"import.{op}", active=_opener is None,
                               league_id=league_id, host=host,
                               auth_mode="cookie") as _ob:
        try:
            with opener(request, timeout=_HTTP_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                body = ""
            if e.code in (401, 403):
                raise MflWriteAuthError(f"MFL rejected the cookie (HTTP {e.code})",
                                        detail=body[:500])
            if e.code == 429:
                raise MflWriteError("MFL throttled the request (HTTP 429)",
                                    kind="network", detail=body[:500])
            raise MflWriteError(f"MFL returned HTTP {e.code}", detail=body[:500])
        except urllib.error.URLError as e:
            raise MflWriteError("network error contacting MFL", kind="network",
                                detail=str(e))

        result = _parse_import_response(raw)
        _ob.ok(status=200, response_bytes=len(raw))
        return result


def propose_trade(cookie: str, host: str, year: int, req: ProposeTradeRequest,
                  *, _opener=None) -> dict:
    """Issue `import?TYPE=tradeProposal` against the league's wwwNN host.

    Returns {"status": "OK", "raw": <trimmed body>} on success. Raises
    MflWriteAuthError on a dead/rejected cookie, MflWriteError otherwise
    (kind 'input' = never sent; 'network' = transport/throttle; 'error' =
    MFL refused the import — e.g. trades disabled, bad asset id)."""
    params = build_import_params(req)
    url = import_url(host, year, params)
    return _issue_import("tradeProposal", cookie, url,
                         league_id=str(req.league_id), host=host, _opener=_opener)


def respond_trade(cookie: str, host: str, year: int, league_id: str,
                  trade_id: str, response: str, comments: str | None = None,
                  *, _opener=None) -> dict:
    """`import?TYPE=tradeResponse` — accept/reject/revoke a pending trade.

    Revoke is the near-term use (withdraw an offer FTF just sent); TRADE_ID
    comes from `export?TYPE=pendingTrades` (owner-restricted —
    mfl_service.fetch_pending_trades / GET /api/mfl/pending-trades). Routed
    via POST /api/trades/respond-mfl (same flag + gates as propose)."""
    lid = str(league_id).strip()
    if not lid.isdigit():
        raise MflWriteError("league_id must be numeric", kind="input")
    resp = str(response).strip().lower()
    if resp not in ("accept", "reject", "revoke"):
        raise MflWriteError("response must be accept|reject|revoke", kind="input")
    if not str(trade_id).strip():
        raise MflWriteError("trade_id is required", kind="input")
    params = {"TYPE": "tradeResponse", "L": lid, "TRADE_ID": str(trade_id).strip(),
              "RESPONSE": resp, "JSON": "1"}
    if comments and comments.strip():
        params["COMMENTS"] = comments.strip()[:512]
    url = import_url(host, year, params)
    return _issue_import("tradeResponse", cookie, url,
                         league_id=lid, host=host, _opener=_opener)

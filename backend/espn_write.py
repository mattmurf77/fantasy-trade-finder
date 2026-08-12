"""espn_write.py — adapter for ESPN's undocumented authenticated write API
("Send in ESPN").

The write-side sibling of `espn_service.py` (reads) and the ESPN analogue of
`mfl_write.py`. Rides the `lm-api-writes.fantasy.espn.com` transactions
endpoint the ESPN web client itself uses to propose trades.

Provenance of the payload spec — LIVE-VERIFIED FOR FOOTBALL 2026-08-11
----------------------------------------------------------------------
Two real TRADE_PROPOSALs were made by hand in a real 14-team `ffl` dynasty
league and read back via `?view=mPendingTransactions` (ESPN's own stored,
canonical representation). Full capture:
docs/plans/espn-send-live-capture-2026-08-11.md. Confirmed there:

  - endpoint : POST .../apis/v3/games/ffl/seasons/{yr}/segments/0/leagues/{id}/transactions/
  - envelope : type TRADE_PROPOSAL, executionType EXECUTE, teamId = the
               PROPOSING team (its teamActions entry is "ACCEPTED" at
               creation), memberId = the proposer's SWID WITH braces,
               isLeagueManager false, isActingAsTeamOwner false,
               bidAmount 0, rating 0, scoringPeriodId from league status
               (0 in the offseason — NEVER a hardcoded week),
               expirationDate in EPOCH MILLISECONDS (~proposedDate + 48h).
  - items[]  : {type:"TRADE", playerId, fromTeamId, toTeamId,
                fromLineupSlotId, toLineupSlotId:-1, isKeeper:false,
                overallPickNumber:0}. Give = fromTeamId:me → toTeamId:them;
               receive mirrored. CONFIRMED — do not invert.
  - player id: the DynastyProcess crosswalk's `espn_id` IS the write-API
               `playerId` — 4/4 live ids matched across both proposals.
  - headers  : cookies espn_s2 + SWID (same jar as reads), plus
               x-fantasy-platform: espn-fantasy-web / x-fantasy-source: kona
               and origin/referer https://fantasy.espn.com.
  - lifecycle: a proposal lands status PENDING, visible in
               mPendingTransactions, and is cancelable (executionType
               CANCEL, empty items, relatedTransactionId).

⚠️  TODO(live-verify) — THE FLAG-GRADUATION GATE (D-026): both captures came
from a full BROWSER session, so it is NOT proven that espn_s2 + SWID alone
authorize a server-side POST — ESPN may additionally require a CSRF/session
token the browser carried implicitly. Until a controlled live attempt (or a
raw request capture) settles this, the `espn.send` flag stays OFF and ABSENT
from config/features.json. A 401/403 from the write host surfaces as
EspnWriteAuthError — a clean structured error, never a crash.

TODO(live-verify), lesser:
  - `fromLineupSlotId` was 20 (bench) for every captured player (offseason).
    Whether a rostered STARTER requires its true slot id is unknown — callers
    should pass real slot ids from the roster read when available
    (`extract_lineup_slots`); this module falls back to 20.
  - Draft-pick assets in items[] are UNTESTED. This module is players-only by
    construction; the route hard-blocks pick assets before reaching it.
  - espn_s2 lifetime/refresh cadence.

Design (mirrors backend/mfl_write.py / sleeper_write.py)
--------------------------------------------------------
- Pure / offline-testable: the HTTP call is injected via `_opener`, so unit
  tests never touch the network (backend/tests/test_espn_write.py).
- No Flask / DB imports. Cookie VALUES arrive already-decrypted from the
  caller (the route decrypts `espn_credentials` exactly as the ESPN read path
  does) — this module never handles the Fernet key.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

# Reuse the read path's cookie normalization verbatim — the write jar is the
# SAME espn_s2 + SWID pair, so the 2026-08-09 encoded/decoded lesson applies
# identically (espn_service.canonical_espn_s2 / canonical_swid).
from backend.espn_service import canonical_espn_s2, canonical_swid

#: lm-api-WRITES host (reads use lm-api-reads). `ffl` = football —
#: live-verified 2026-08-11 (the football league's stored proposals live
#: under exactly this game/season/segment path).
ESPN_WRITES_BASE = "https://lm-api-writes.fantasy.espn.com/apis/v3/games/ffl"
_HTTP_TIMEOUT = 15

#: Default proposal validity window: 48h in EPOCH MILLISECONDS. Both live
#: captures showed expirationDate − proposedDate ≈ 172,800,000 ms.
DEFAULT_EXPIRATION_MS = 48 * 3600 * 1000

#: ESPN lineup slot id for the bench. Both captured items carried
#: fromLineupSlotId 20 (offseason rosters are fully benched).
#: TODO(live-verify): whether a rostered starter needs its true slot id.
BENCH_LINEUP_SLOT_ID = 20

# The x-fantasy-* headers are what the browser's own Propose Trade fetch
# carries; whether the server REQUIRES them (vs. just the cookies) is part of
# the auth unknown above — sending them costs nothing and matches the capture.
_WRITE_HEADERS = {
    "content-type": "application/json",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "accept": "application/json",
    "x-fantasy-platform": "espn-fantasy-web",
    "x-fantasy-source": "kona",
    "origin": "https://fantasy.espn.com",
    "referer": "https://fantasy.espn.com/",
}


# ---------------------------------------------------------------------------
# Errors — mirror mfl_write's kinds so the route maps them to the same
# structured HTTP responses + reconnect / fallback handling.
# ---------------------------------------------------------------------------

class EspnWriteError(Exception):
    """A write to ESPN failed. `kind` steers the caller's handling:
      'auth'    → cookies missing/expired/rejected → prompt reconnect (re-capture)
      'network' → transport problem → retry / clipboard-fallback
      'input'   → caller-side validation failure (never sent)
      'error'   → everything else → clipboard-fallback
    """

    def __init__(self, message: str, *, kind: str = "error", detail: str | None = None):
        super().__init__(message)
        self.kind = kind
        self.detail = detail


class EspnWriteAuthError(EspnWriteError):
    """Cookies missing / expired / rejected (HTTP 401/403 from the write
    host). Caller should drop the stored espn_credentials row and prompt the
    user to reconnect ESPN. NOTE: until the auth probe clears (module
    docstring), a 401/403 may also mean "cookies alone don't authorize a
    server-side write at all" — either way the clean handling is identical:
    structured error, credential drop, no crash."""

    def __init__(self, message: str = "ESPN rejected the write",
                 detail: str | None = None):
        super().__init__(message, kind="auth", detail=detail)


# ---------------------------------------------------------------------------
# Sleeper → ESPN player-id resolution.
#
# FTF is keyed on Sleeper player_ids end-to-end. espn_service's Crosswalk
# holds `by_espn_id` (espn_id → sleeper_id, the READ direction); a write
# needs the INVERSE. CONFIRMED 2026-08-11: the crosswalk's `espn_id` is the
# same id space the write API expects in items[].playerId (4/4 live ids
# matched — capture doc §Resolved 1).
# ---------------------------------------------------------------------------

def invert_espn_crosswalk(by_espn_id: dict) -> dict:
    """Build sleeper_id → espn_id from a Crosswalk.by_espn_id map.

    A collision (two espn_ids mapping to one sleeper_id) keeps the first
    seen, matching the forward map's own setdefault semantics."""
    out: dict[str, str] = {}
    for espn_id, sleeper_id in (by_espn_id or {}).items():
        if sleeper_id and espn_id and sleeper_id not in out:
            out[str(sleeper_id)] = str(espn_id)
    return out


def resolve_espn_player_ids(sleeper_ids, sleeper_to_espn: dict) -> list:
    """Map a list of Sleeper player_ids to ESPN playerIds, raising on any miss.

    A miss means the crosswalk has no ESPN id for that player — the write
    CANNOT proceed silently (unlike a read import, which skips + reports). A
    partial trade would send a DIFFERENT trade, so we fail loud; the route's
    422 hard block sits in front of this as the user-facing surface.
    """
    resolved: list[int] = []
    missing: list[str] = []
    for sid in sleeper_ids:
        espn_id = sleeper_to_espn.get(str(sid))
        if espn_id is None:
            missing.append(str(sid))
            continue
        try:
            resolved.append(int(espn_id))          # write-API playerId is an int
        except (TypeError, ValueError):
            missing.append(str(sid))
    if missing:
        raise EspnWriteError(
            f"no ESPN playerId for Sleeper id(s): {missing}", kind="input",
            detail="crosswalk gap — trade cannot be sent players-incomplete",
        )
    return resolved


# ---------------------------------------------------------------------------
# League-read helpers — pure parsers over the RAW mTeam+mRoster payload the
# route's pre-flight `espn_service.fetch_league` already returns.
# ---------------------------------------------------------------------------

def current_scoring_period(raw: dict) -> int:
    """The league's CURRENT scoring period, read from league status — never a
    hardcoded week. Both captures carried scoringPeriodId 0 (offseason).
    Falls back top-level → status.latestScoringPeriod → 0."""
    node = raw if isinstance(raw, dict) else {}
    for v in (node.get("scoringPeriodId"),
              (node.get("status") or {}).get("latestScoringPeriod")):
        try:
            if v is not None:
                return int(v)
        except (TypeError, ValueError):
            continue
    return 0


def extract_lineup_slots(raw: dict) -> dict:
    """{espn playerId (int) → lineupSlotId (int)} across every roster entry in
    a raw mRoster payload. Feeds items[].fromLineupSlotId with each player's
    REAL slot; players absent from the map fall back to BENCH_LINEUP_SLOT_ID
    (20) — TODO(live-verify): whether a starter's true slot is required."""
    slots: dict[int, int] = {}
    node = raw if isinstance(raw, dict) else {}
    for team in node.get("teams") or []:
        if not isinstance(team, dict):
            continue
        for entry in (team.get("roster") or {}).get("entries") or []:
            if not isinstance(entry, dict):
                continue
            pid = ((entry.get("playerPoolEntry") or {}).get("player") or {}).get("id")
            slot = entry.get("lineupSlotId")
            try:
                if pid is not None and slot is not None:
                    slots[int(pid)] = int(slot)
            except (TypeError, ValueError):
                continue
    return slots


# ---------------------------------------------------------------------------
# TRADE_PROPOSAL — payload construction (verbatim structure from the
# 2026-08-11 football capture).
# ---------------------------------------------------------------------------

@dataclass
class EspnTradeProposalRequest:
    league_id: str
    season: int                    # ffl season year, e.g. 2026 (the linked season)
    my_team_id: int                # the PROPOSING team's ESPN teamId (capture §4)
    their_team_id: int             # the counterparty's ESPN teamId
    member_swid: str               # proposer's SWID → body.memberId (braces-normalized)
    give_espn_player_ids: list     # ESPN playerIds I send    (my_team → their_team)
    receive_espn_player_ids: list  # ESPN playerIds I receive (their_team → my_team)
    #: The CURRENT scoring period from league status (current_scoring_period).
    #: 0 in the offseason — never hardcode a week.
    scoring_period_id: int = 0
    #: {espn playerId → lineupSlotId} from the pre-flight roster read
    #: (extract_lineup_slots). Missing players fall back to bench (20).
    lineup_slots: dict = field(default_factory=dict)
    #: Epoch-ms expiration; None → now + 48h (both captures' observed default).
    expiration_ms: int | None = None
    comment: str = ""              # optional note; key omitted when empty (not
    #                                observed in either football capture)
    is_league_manager: bool = False


def _item(player_id, from_team, to_team, lineup_slots: dict) -> dict:
    """One items[] entry, all seven captured fields."""
    pid = int(player_id)
    return {
        "playerId": pid,
        "type": "TRADE",
        "fromTeamId": int(from_team),
        "toTeamId": int(to_team),
        # TODO(live-verify): 20 (bench) matched both captures; a starter's
        # true slot id is sourced from the roster read when available.
        "fromLineupSlotId": int(lineup_slots.get(pid, BENCH_LINEUP_SLOT_ID)),
        "toLineupSlotId": -1,          # sentinel, constant across captures
        "isKeeper": False,
        "overallPickNumber": 0,        # players-only — picks are hard-blocked upstream
    }


def build_trade_proposal_body(req: EspnTradeProposalRequest, *,
                              now_ms: int | None = None) -> dict:
    """Build the exact JSON body for a TRADE_PROPOSAL transaction.

    Item direction (capture §3, CONFIRMED):
      - a player I GIVE     → {fromTeamId: me,   toTeamId: them}
      - a player I RECEIVE  → {fromTeamId: them, toTeamId: me}
    Every item is type "TRADE"; the transaction type is "TRADE_PROPOSAL".
    `expirationDate` is EPOCH MILLISECONDS (capture: ≈ proposedDate + 48h).
    """
    lid = str(req.league_id)
    if not lid.isdigit():
        raise EspnWriteError("league_id must be a numeric string", kind="input")
    if int(req.my_team_id) == int(req.their_team_id):
        raise EspnWriteError("cannot trade with your own team", kind="input")
    if not req.give_espn_player_ids and not req.receive_espn_player_ids:
        raise EspnWriteError("trade has no players on either side", kind="input")
    # Players-only by construction — ESPN pick assets are unverified and the
    # route hard-blocks them before this module is reached.

    slots = req.lineup_slots or {}
    items = (
        [_item(pid, req.my_team_id, req.their_team_id, slots)
         for pid in req.give_espn_player_ids]
        + [_item(pid, req.their_team_id, req.my_team_id, slots)
           for pid in req.receive_espn_player_ids]
    )

    if req.expiration_ms is not None:
        expiration = int(req.expiration_ms)
    else:
        base = int(now_ms) if now_ms is not None else int(time.time() * 1000)
        expiration = base + DEFAULT_EXPIRATION_MS

    body = {
        "isLeagueManager": bool(req.is_league_manager),
        "isActingAsTeamOwner": False,                     # capture: constant
        "teamId": int(req.my_team_id),                    # the PROPOSING team
        "type": "TRADE_PROPOSAL",
        "memberId": canonical_swid(req.member_swid),      # SWID with literal braces
        "scoringPeriodId": int(req.scoring_period_id),    # from league status
        "executionType": "EXECUTE",
        "bidAmount": 0,                                   # capture: constant
        "rating": 0,                                      # capture: constant
        "items": items,
        "expirationDate": expiration,                     # EPOCH MILLISECONDS
    }
    comment = (req.comment or "").strip()
    if comment:
        # Not observed in either football capture (neither proposal carried a
        # note) — included only when the user actually wrote one.
        body["comment"] = comment[:512]
    return body


def transactions_url(league_id, season: int) -> str:
    return (
        f"{ESPN_WRITES_BASE}/seasons/{int(season)}/segments/0/leagues/"
        f"{urllib.parse.quote(str(league_id))}/transactions/"
    )


# ---------------------------------------------------------------------------
# HTTP issue. `_opener` is injectable so unit tests never hit the network.
# ---------------------------------------------------------------------------

def _post_transaction(espn_s2: str, swid: str, url: str, body: dict, *,
                      op: str, _opener=None) -> dict:
    if not (espn_s2 and swid):
        raise EspnWriteAuthError("no ESPN cookies available (espn_s2 + SWID required)")

    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    for hk, hv in _WRITE_HEADERS.items():
        request.add_header(hk, hv)
    # Same cookie choke point as the read path: an already-encoded espn_s2
    # passes through byte-identical; a native-store (decoded) capture is
    # re-encoded; SWID gains braces only if pasted bare.
    request.add_header(
        "Cookie",
        f"espn_s2={canonical_espn_s2(espn_s2)}; SWID={canonical_swid(swid)}",
    )

    opener = _opener or urllib.request.urlopen
    # obs.api_events — instrument the REAL network path only (`_opener` is
    # test-injected). Cookie VALUES are NEVER an event prop — only the op
    # class, status, latency and error kind, exactly like the read path.
    from . import api_observability as _api_obs
    with _api_obs.observe_call("espn", f"write.{op}", method="POST",
                               active=_opener is None) as _ob:
        try:
            with opener(request, timeout=_HTTP_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")
                status = getattr(resp, "status", 200)
        except urllib.error.HTTPError as e:
            try:
                raw = e.read().decode("utf-8")
            except Exception:
                raw = ""
            if e.code in (401, 403):
                # TODO(live-verify): until the auth probe clears this may mean
                # "cookies alone never authorize a server-side write" rather
                # than "these cookies expired" — same clean handling either way.
                raise EspnWriteAuthError(
                    f"ESPN rejected the write (HTTP {e.code})", detail=raw[:500])
            raise EspnWriteError(f"ESPN returned HTTP {e.code}", detail=raw[:500])
        except urllib.error.URLError as e:
            raise EspnWriteError("network error contacting ESPN", kind="network",
                                 detail=str(e))

        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            raise EspnWriteError("non-JSON response from ESPN", detail=raw[:500])

        _ob.ok(status=status, response_bytes=len(raw))
        # A stored proposal reads back as {id, status:"PENDING", …} (capture
        # §5); the write response is expected to echo the same node. Surfaced
        # defensively — the id/status may be absent on shape drift.
        node = parsed if isinstance(parsed, dict) else {}
        return {
            "transaction_id": node.get("id"),
            "status": node.get("status"),   # "PENDING" on success (capture §5)
            "raw": node,
        }


def propose_trade(espn_s2: str, swid: str, req: EspnTradeProposalRequest, *,
                  _opener=None) -> dict:
    """Issue the captured TRADE_PROPOSAL transaction.

    Live use is gated on `espn.send` (OFF + absent from config/features.json
    until the auth probe clears — module docstring). Returns
    {transaction_id, status, raw}. Raises EspnWriteAuthError on 401/403,
    EspnWriteError otherwise.
    """
    return _post_transaction(
        espn_s2, swid,
        transactions_url(req.league_id, req.season),
        build_trade_proposal_body(req),
        op="trade_proposal", _opener=_opener,
    )


def build_cancel_body(req: EspnTradeProposalRequest, related_transaction_id) -> dict:
    """CANCEL body: same envelope, empty items, executionType CANCEL, plus
    relatedTransactionId. The 2026-08-11 capture confirms proposals are
    cancelable; accept/reject payloads were never captured and are NOT built
    here."""
    return {
        "isLeagueManager": bool(req.is_league_manager),
        "isActingAsTeamOwner": False,
        "teamId": int(req.my_team_id),
        "type": "TRADE_PROPOSAL",
        "memberId": canonical_swid(req.member_swid),
        "scoringPeriodId": int(req.scoring_period_id),
        "executionType": "CANCEL",
        "bidAmount": 0,
        "rating": 0,
        "items": [],
        "relatedTransactionId": str(related_transaction_id),
    }


def cancel_trade(espn_s2: str, swid: str, req: EspnTradeProposalRequest,
                 related_transaction_id, *, _opener=None) -> dict:
    """Cancel (revoke) a pending proposal. Same auth + host path as propose."""
    return _post_transaction(
        espn_s2, swid,
        transactions_url(req.league_id, req.season),
        build_cancel_body(req, related_transaction_id),
        op="trade_cancel", _opener=_opener,
    )

"""
espn_service.py — ESPN league linking (#101 / feedback #115)
=============================================================
Read-only adapter for ESPN Fantasy Football's unofficial v3 API
(`lm-api-reads.fantasy.espn.com`) plus the DynastyProcess player-ID
crosswalk that maps ESPN rosters into the app's Sleeper `player_id` space.

Status: **Phase 1 wired** — `server.py`'s `/api/espn/*` routes import this
module, gated by the `espn.link` feature flag (default OFF). See
docs/plans/espn-league-linking-plan-2026-07-11.md for the phased plan.

Design notes
------------
- Pure/offline-testable: the HTTP call is injected via `_opener`, mirroring
  `backend/sleeper_write.py`. Tests use recorded fixtures, never the network.
- Public leagues need no auth. Private leagues need the `espn_s2` + `SWID`
  cookies captured from a logged-in espn.com session. ESPN's API expects the
  exact wire shapes a browser jar holds: espn_s2 percent-ENCODED and SWID with
  its literal braces. Sources differ — browser paste is already encoded, but
  iOS's native cookie store (the in-app WebView capture, Phase 1b) surfaces
  espn_s2 percent-DECODED — so `canonical_espn_s2` / `canonical_swid`
  normalize either form before the Cookie header is built (2026-08-09 field
  failure: replaying the decoded form fails ESPN auth).
- Browser-signature headers, same lesson as the Sleeper write path
  (Cloudflare/edge filters ban the default urllib signature).
- Crosswalk: DynastyProcess `db_playerids.csv` (`espn_id` ↔ `sleeper_id`),
  with a normalised-name+position fallback for rows missing an `espn_id`.
  K and D/ST are outside the app's QB/RB/WR/TE pool and are reported
  separately, not counted as match failures.
"""

from __future__ import annotations

import csv
import io
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from backend.data_loader import normalise_name

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ESPN_READS_BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"

# ESPN edge filters reject bare urllib signatures (same as Sleeper's
# Cloudflare 1010 — see test_sleeper_write.py's browser-header regression).
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# ESPN defaultPositionId → position label
ESPN_POSITION_BY_ID = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}

# The app's ranking/trade pool is skill positions only (players table).
POOL_POSITIONS = {"QB", "RB", "WR", "TE"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class EspnError(Exception):
    """kind: 'auth' | 'not_found' | 'http' | 'parse' | 'input'"""

    def __init__(self, message: str, kind: str = "http"):
        super().__init__(message)
        self.kind = kind


class EspnAuthError(EspnError):
    def __init__(self, message: str = "ESPN rejected the request (private league or bad cookies)"):
        super().__init__(message, kind="auth")


# ---------------------------------------------------------------------------
# Fetch (live path — spike CLI only; tests inject _opener)
# ---------------------------------------------------------------------------

def league_url(league_id: str, season: int) -> str:
    return (
        f"{ESPN_READS_BASE}/seasons/{season}/segments/0/leagues/"
        f"{urllib.parse.quote(str(league_id))}?view=mTeam&view=mRoster&view=mSettings"
    )


def canonical_espn_s2(value: str) -> str:
    """espn_s2 exactly as ESPN's API expects it: the percent-ENCODED form.

    Ground truth from a live browser session (2026-08-09): a working jar holds
    espn_s2 percent-encoded (~350 chars with %XX escapes) — the form users
    paste from devtools and the only form ESPN's servers accept. iOS's native
    cookie store surfaces the SAME cookie percent-DECODED (the in-app WebView
    capture reads NSHTTPCookie.value via @react-native-cookies), and replaying
    the decoded form fails ESPN auth with a 401/403 — the "captured cookies in
    the fields but the league still says private" field failure.

    Accept either form. A value that unquotes differently than itself carries
    %XX escapes and IS the wire form — pass it through byte-identical, never
    double-encode. A value with no escapes is the decoded form — re-encode
    with safe='' so the base64 alphabet's '+', '/', '=' become %2B/%2F/%3D.
    (The decoded value space is base64-ish and never contains a bare '%', so
    the unquote check cleanly separates the two forms.)
    """
    v = (value or "").strip()
    if not v:
        return v
    if urllib.parse.unquote(v) != v:
        return v
    return urllib.parse.quote(v, safe="")


def canonical_swid(value: str) -> str:
    """SWID with its literal braces — '{…}' is the wire form ESPN expects.

    A braced value (what the native store and a devtools paste both yield)
    passes through byte-identical; braces are added only when missing
    entirely (a user pasting the bare GUID). No case or encoding changes.
    """
    v = (value or "").strip()
    if not v:
        return v
    if v.startswith("{") and v.endswith("}"):
        return v
    return "{" + v.strip("{}") + "}"


def fetch_league(
    league_id: str,
    season: int,
    espn_s2: str | None = None,
    swid: str | None = None,
    timeout: int = 15,
    _opener=None,
) -> dict:
    """Fetch one league's teams+rosters+settings JSON.

    Public leagues work with no cookies; private leagues need both espn_s2
    and SWID. Raises EspnAuthError on 401/403, EspnError(kind='not_found')
    on 404 (no such league in that season — ESPN purges old leagues).
    """
    if not str(league_id).strip().isdigit():
        raise EspnError(f"league_id must be numeric, got {league_id!r}", kind="input")

    headers = dict(BROWSER_HEADERS)
    if espn_s2 and swid:
        # Canonicalize to the wire forms ESPN accepts (see the functions
        # above): an already-encoded/browser-pasted espn_s2 passes through
        # byte-identical; a native-store (decoded) capture is re-encoded.
        # SWID gains braces only if pasted bare. This is the single choke
        # point for both first links and stored-cookie replays.
        headers["Cookie"] = (
            f"espn_s2={canonical_espn_s2(espn_s2)}; SWID={canonical_swid(swid)}"
        )

    req = urllib.request.Request(league_url(league_id, season), headers=headers)
    opener = _opener or urllib.request.urlopen
    # obs.api_events — the one ESPN endpoint (docs/integrations/espn.md §6.1).
    # Cookie SHAPE booleans only (s2_encoded / swid_braced — exactly the
    # fingerprint that would have caught the 2026-08-09 encoding mismatch);
    # the cookie VALUES never reach an event in any form.
    from . import api_observability as _api_obs
    _has_cookie = bool(espn_s2 and swid)
    with _api_obs.observe_call(
            "espn", "league_read", active=_opener is None,
            league_id=str(league_id), season=season,
            auth_mode="cookie" if _has_cookie else "public",
            s2_encoded=("%" in espn_s2) if _has_cookie else None,
            swid_braced=(swid.strip().startswith("{")
                         and swid.strip().endswith("}")) if _has_cookie else None,
    ) as _ob:
        try:
            with opener(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            _ob.ok(status=getattr(resp, "status", 200), response_bytes=len(raw))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise EspnAuthError() from e
            if e.code == 404:
                raise EspnError(
                    f"league {league_id} not found for season {season}", kind="not_found"
                ) from e
            raise EspnError(f"ESPN HTTP {e.code}", kind="http") from e

        try:
            return json.loads(raw)
        except ValueError as e:
            raise EspnError("ESPN returned non-JSON", kind="parse") from e


# ---------------------------------------------------------------------------
# Fan profile — "my leagues" (feedback: "can't we fetch all their ESPN
# leagues and let them pick, instead of asking for a league ID?")
# ---------------------------------------------------------------------------

# fan.api.espn.com is a SEPARATE host from the fantasy read API (§1 above) —
# ESPN's cross-sport "fan profile" service, keyed by SWID rather than a
# league id. Confirmed live (2026-08-09): an unauthenticated GET with a
# syntactically-valid-but-unknown SWID returns 404 {"message":"fan not
# found"} — the host resolves and answers JSON, so this is a real endpoint,
# not a guess. What the AUTHENTICATED shape looks like for a real fan is
# UNVERIFIED from this session (no live cookies available, and the endpoint
# is essentially undocumented outside community reverse-engineering) — see
# the UNVERIFIED SHAPE note on fetch_fan_leagues and
# docs/integrations/espn.md §1.7. Needs TestFlight confirmation against a
# real ESPN account before shipping the flag on in production.
FAN_API_BASE = "https://fan.api.espn.com/apis/v2/fans"


def fan_leagues_url(swid: str) -> str:
    return (
        f"{FAN_API_BASE}/{urllib.parse.quote(canonical_swid(swid))}"
        f"?showAirings=true&showFantasy=true"
    )


def fetch_fan_leagues(espn_s2: str, swid: str, timeout: int = 15,
                      _opener=None) -> list[dict]:
    """List every ESPN fantasy FOOTBALL league the signed-in fan belongs to.

    Returns `[{"league_id", "league_name", "season", "team_name"}]`, newest
    season first. Requires both cookies (this is inherently an
    authenticated-fan lookup — there is no "public" fan profile). Raises
    EspnAuthError on 401/403/404 (ESPN has no record for this SWID — the
    same practical failure as a rejected/expired session from FTF's point of
    view: paste/sign in again), EspnError(kind='parse') if the response
    isn't JSON, EspnError(kind='input') if either cookie is missing.

    UNVERIFIED SHAPE (2026-08-09): this fan-profile endpoint is not
    documented by ESPN. The parse below (`_parse_fan_leagues`) follows the
    best-known community-reverse-engineered shape — a top-level
    `preferences` array, each entry's `metaData.entry` carrying `groups[]`
    (one row per league/group the fan belongs to across ALL ESPN fantasy
    games), filtered to football via `entry.abbrev == "ffl"` (the same game
    slug FTF already uses at `apis/v3/games/ffl`, §1.1). This has NOT been
    confirmed against a live account from this build session — flagged for
    TestFlight verification (docs/feedback/items/espn-webview-escape/
    status.md). If the real shape differs, `_parse_fan_leagues` degrades to
    an empty/partial list rather than raising (never a 500) — see its
    docstring.
    """
    if not espn_s2 or not swid:
        raise EspnError("espn_s2 and swid are required", kind="input")

    headers = dict(BROWSER_HEADERS)
    headers["Cookie"] = (
        f"espn_s2={canonical_espn_s2(espn_s2)}; SWID={canonical_swid(swid)}"
    )
    req = urllib.request.Request(fan_leagues_url(swid), headers=headers)
    opener = _opener or urllib.request.urlopen

    # obs.api_events — same cookie-SHAPE-only booleans as league_read (§6.1);
    # the cookie values never reach an event in any form.
    from . import api_observability as _api_obs
    with _api_obs.observe_call(
            "espn", "fan_profile", active=_opener is None,
            auth_mode="cookie",
            s2_encoded=("%" in espn_s2),
            swid_braced=(swid.strip().startswith("{")
                         and swid.strip().endswith("}")),
    ) as _ob:
        try:
            with opener(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
            _ob.ok(status=getattr(resp, "status", 200), response_bytes=len(raw))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                # 404 here means "no fan record for this SWID" — from a
                # captured/pasted cookie pair that should always resolve to
                # a real fan, that's the same practical failure as a
                # rejected/expired session.
                raise EspnAuthError() from e
            raise EspnError(f"ESPN fan API HTTP {e.code}", kind="http") from e

        try:
            data = json.loads(raw)
        except ValueError as e:
            raise EspnError("ESPN fan API returned non-JSON", kind="parse") from e

    return _parse_fan_leagues(data)


def _parse_fan_leagues(data) -> list[dict]:
    """Defensive parse of the fan-profile payload — NEVER raises. An
    unrecognized shape (or a shape that only partially matches) returns
    whatever could be extracted, degrading toward an empty list rather than
    guessing or fabricating a row. See fetch_fan_leagues's UNVERIFIED SHAPE
    note — this is the one function that absorbs that risk."""
    out: list[dict] = []
    if not isinstance(data, dict):
        return out
    try:
        for pref in data.get("preferences") or []:
            if not isinstance(pref, dict):
                continue
            entry = ((pref.get("metaData") or {}).get("entry")) or {}
            if not isinstance(entry, dict):
                continue
            # Fan profiles span every ESPN fantasy game (baseball, hockey,
            # basketball, ...) — keep only football. A row with no `abbrev`
            # at all is kept rather than dropped (better a possibly-wrong
            # row surfaces than a real league silently vanishes).
            abbrev = entry.get("abbrev")
            if abbrev and abbrev != "ffl":
                continue
            groups = entry.get("groups")
            if not isinstance(groups, list) or not groups:
                continue
            team_name = ((entry.get("entryMetadata") or {}).get("teamName")
                         or entry.get("teamName") or "")
            for g in groups:
                if not isinstance(g, dict):
                    continue
                league_id = str(g.get("groupId") or "").strip()
                if not league_id.isdigit():
                    continue
                season = _int_or_none(g.get("seasonId") or entry.get("seasonId"))
                out.append({
                    "league_id": league_id,
                    "league_name": str(g.get("groupName") or "").strip()
                                   or f"ESPN league {league_id}",
                    "season": season,
                    "team_name": str(team_name).strip() or None,
                })
    except Exception:
        # Shape drift beyond what the checks above already tolerate — never
        # let a fan-API surprise become a 500. Whatever was successfully
        # extracted before the failure is still returned.
        pass
    out.sort(key=lambda r: r["season"] or 0, reverse=True)
    return out


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

@dataclass
class EspnPlayer:
    espn_id: str
    name: str
    position: str  # QB/RB/WR/TE/K/DST/?


@dataclass
class EspnTeam:
    team_id: int
    name: str
    owner_swid: str
    owner_display: str
    players: list[EspnPlayer] = field(default_factory=list)
    # ── Standings (ADDITIVE, all default None) ──────────────────────────
    # Read from the SAME `view=mTeam` response the roster import already
    # fetches — live-verified 2026-08-08 against league 11896 that mTeam
    # alone carries all three (docs/plans/draft-extensions/
    # espn-auto-draft-order-feasibility.md §6b). No extra `view=` token, no
    # extra request, and every pre-existing caller that ignores these
    # fields sees an unchanged object.
    wins: int | None = None
    losses: int | None = None
    ties: int | None = None
    points_for: float | None = None
    #: ESPN's final REGULAR-SEASON seed, 1..N, its own tiebreakers applied.
    playoff_seed: int | None = None
    #: ESPN's final POST-PLAYOFF rank, 1 = champion. Verified exact for
    #: playoff teams; for non-playoff teams it reflects ESPN's consolation
    #: ladder, which FTF deliberately does not use (see
    #: `derive_espn_draft_order`).
    rank_calculated_final: int | None = None


def _int_or_none(v) -> int | None:
    """`int(v)` for a real number, else None. `None`/''/non-numeric → None."""
    if v is None or isinstance(v, bool):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_league(raw: dict) -> dict:
    """Normalise the mTeam+mRoster payload into a small, stable shape."""
    display_by_swid = {
        m.get("id"): m.get("displayName") or "" for m in raw.get("members", [])
    }
    teams: list[EspnTeam] = []
    for t in raw.get("teams", []):
        # Older payloads split name into location/nickname; newer have `name`.
        name = t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip()
        swid = t.get("primaryOwner") or (t.get("owners") or [""])[0]
        players = []
        for entry in (t.get("roster") or {}).get("entries", []):
            p = (entry.get("playerPoolEntry") or {}).get("player") or {}
            if not p.get("id"):
                continue
            players.append(
                EspnPlayer(
                    espn_id=str(p["id"]),
                    name=p.get("fullName") or "",
                    position=ESPN_POSITION_BY_ID.get(p.get("defaultPositionId"), "?"),
                )
            )
        overall = (t.get("record") or {}).get("overall") or {}
        pf = overall.get("pointsFor")
        teams.append(
            EspnTeam(
                team_id=t.get("id"),
                name=name,
                owner_swid=swid,
                owner_display=display_by_swid.get(swid, ""),
                players=players,
                wins=_int_or_none(overall.get("wins")),
                losses=_int_or_none(overall.get("losses")),
                ties=_int_or_none(overall.get("ties")),
                points_for=(float(pf) if isinstance(pf, (int, float))
                            and not isinstance(pf, bool) else None),
                playoff_seed=_int_or_none(t.get("playoffSeed")),
                rank_calculated_final=_int_or_none(t.get("rankCalculatedFinal")),
            )
        )
    settings = raw.get("settings") or {}
    return {
        "league_id": str(raw.get("id", "")),
        "name": settings.get("name", ""),
        "season": raw.get("seasonId"),
        "total_teams": settings.get("size") or len(teams),
        "teams": teams,
        # Additive. `mSettings` is already requested; None when absent, which
        # `derive_espn_draft_order` treats as "cannot tell who made the
        # playoffs" and refuses to guess.
        "playoff_team_count": _int_or_none(
            (settings.get("scheduleSettings") or {}).get("playoffTeamCount")),
    }


# ---------------------------------------------------------------------------
# Derived rookie-draft order (draft-extensions, 2026-08-08)
# ---------------------------------------------------------------------------

def derive_espn_draft_order(teams, playoff_team_count) -> list[int] | None:
    """Standard dynasty rookie-draft order from ESPN's own final standings.

    Returns ESPN `team_id`s in PICK order — index 0 holds 1.01 — or `None`
    when the inputs cannot support an honest answer. **It never guesses.**

    ── The convention, as implemented ──────────────────────────────────────

    1. **Non-playoff teams pick FIRST**, ordered by INVERSE regular-season
       standings: worst record → 1.01. Sort key, ascending:

         (win percentage, points_for, -playoff_seed, team_id)

       i.e. worse record first; tie on record broken by FEWER points-for
       picking earlier; still tied broken by ESPN's own final regular-season
       seed (worse seed picks earlier), which is unique 1..N and therefore
       makes the order total; `team_id` is a belt-and-braces final key so the
       sort is deterministic even against a malformed payload.

       Win percentage counts a tie as half a win — `(w + t/2) / games` — which
       is how ESPN itself computes `record.overall.percentage`.

    2. **Playoff teams pick LAST**, in REVERSE `rankCalculatedFinal` order, so
       the champion (`rankCalculatedFinal == 1`) picks last. Ties broken by
       `team_id` for determinism, though ESPN's final rank is unique in
       practice.

    3. "Made the playoffs" is `playoff_seed <= playoff_team_count`. ESPN
       assigns a `playoffSeed` to EVERY team (it is the regular-season
       standing, 1..N), so the bracket size is the only thing that separates
       the two groups — which is why it is a required argument rather than
       something inferred.

    ── Why `rankCalculatedFinal` is used for ONE group only ────────────────

    Operator decision, 2026-08-08 (`docs/plans/draft-extensions/plan.md`;
    evidence in `espn-auto-draft-order-feasibility.md` §6c–d): the live probe
    of league 11896 confirmed `rankCalculatedFinal` is EXACTLY the
    post-playoff finish for the six playoff teams, but for the eight
    non-playoff teams it encodes ESPN's consolation-ladder result, which
    disagreed with inverse regular-season standings on 5 of 8. Most dynasty
    leagues treat those bottom-bracket games as meaningless for rookie picks
    — a 4-10 team should not pick 8th for winning the consolation ladder — so
    FTF uses `rankCalculatedFinal` for the playoff group only and the
    regular-season record for everyone else. It is never a whole-league sort
    key.

    ── Refusals (return `None`, never a fabricated order) ──────────────────

    New leagues, pre-season imports and auth-degraded reads all land here:

      • fewer than two teams, or no `playoff_team_count` in 1..len(teams)-1
      • ANY team missing wins / losses / ties / points_for / playoff_seed
      • duplicate or non-positive `playoff_seed` (standings unresolvable)
      • every team at 0-0-0 (the season has not been played)
      • ANY PLAYOFF team missing, non-positive, or duplicating
        `rankCalculatedFinal` (ESPN leaves it 0 until the playoffs finish)

    Note `rankCalculatedFinal` is required only of the playoff group, because
    that is the only group whose order reads it.
    """
    teams = list(teams or [])
    if len(teams) < 2:
        return None

    n_playoff = _int_or_none(playoff_team_count)
    if n_playoff is None or not (1 <= n_playoff < len(teams)):
        return None

    for t in teams:
        if None in (t.wins, t.losses, t.ties, t.points_for, t.playoff_seed):
            return None
        if t.playoff_seed < 1:
            return None

    seeds = [t.playoff_seed for t in teams]
    if len(set(seeds)) != len(seeds):
        return None

    # A season nobody has played yet carries a full, well-formed 0-0-0 grid.
    if all((t.wins + t.losses + t.ties) == 0 for t in teams):
        return None

    playoff = [t for t in teams if t.playoff_seed <= n_playoff]
    non_playoff = [t for t in teams if t.playoff_seed > n_playoff]
    if not playoff or not non_playoff:
        return None

    finals = [t.rank_calculated_final for t in playoff]
    if any(r is None or r < 1 for r in finals) or len(set(finals)) != len(finals):
        return None

    def _win_pct(t) -> float:
        games = t.wins + t.losses + t.ties
        return ((t.wins + t.ties / 2.0) / games) if games else 0.0

    non_playoff.sort(key=lambda t: (_win_pct(t), t.points_for,
                                    -t.playoff_seed, t.team_id))
    playoff.sort(key=lambda t: (-t.rank_calculated_final, t.team_id))
    return [t.team_id for t in non_playoff + playoff]


# ---------------------------------------------------------------------------
# Crosswalk (ESPN id → Sleeper id)
# ---------------------------------------------------------------------------

@dataclass
class Crosswalk:
    """Per-platform id → Sleeper-id maps built from one DynastyProcess fetch.

    The multi-platform league-linking plan
    (docs/plans/multi-platform-linking-plan-2026-07-17.md) generalized this
    from the original ESPN-only shape: every linked platform resolves its
    native roster ids to Sleeper player ids through the SAME cached DP file.
    `by_name_pos` is the position-strict fallback tier (#127 rule — a name
    hit whose position disagrees is NO match) shared by every platform.

    Which id map a platform uses:
      ESPN        → by_espn_id       (espn_id column)
      MFL         → by_mfl_sleeper   (mfl_id column — DP's own primary key)
      Fleaflicker → by_sportradar_id (sportradar_id from roster externalIds;
                    DP's fleaflicker_id column is a decoy — plan §3)
      Yahoo (future) → by_yahoo_id
    """
    by_espn_id: dict[str, str]                     # espn_id → sleeper_id
    by_name_pos: dict[tuple[str, str], str]        # (normalised name, pos) → sleeper_id
    # KTC/MFL id → (DP name, pos) — used by data_loader's KTC consensus blend
    # (#145) for id-based matching. Empty when the CSV lacks the columns
    # (e.g. the trimmed bundled snapshot) — callers fall back to name+pos.
    by_ktc_id: dict[str, tuple[str, str]] = field(default_factory=dict)
    by_mfl_id: dict[str, tuple[str, str]] = field(default_factory=dict)
    # Multi-platform linking id maps (external id → sleeper_id).
    by_mfl_sleeper: dict[str, str] = field(default_factory=dict)
    by_sportradar_id: dict[str, str] = field(default_factory=dict)
    by_yahoo_id: dict[str, str] = field(default_factory=dict)


def _parse_crosswalk_rows(reader) -> Crosswalk:
    """Build a Crosswalk from an iterable of DP db_playerids dict rows."""
    by_espn: dict[str, str] = {}
    by_name: dict[tuple[str, str], str] = {}
    by_ktc: dict[str, tuple[str, str]] = {}
    by_mfl: dict[str, tuple[str, str]] = {}
    by_mfl_sleeper: dict[str, str] = {}
    by_sportradar: dict[str, str] = {}
    by_yahoo: dict[str, str] = {}
    for row in reader:
        sid = (row.get("sleeper_id") or "").strip()
        eid = (row.get("espn_id") or "").strip()
        pos = (row.get("position") or "").strip().upper()
        # KTC/MFL entries join on the DP name (not sleeper_id), so collect
        # them before the sleeper_id guard below.
        raw_name = (row.get("name") or "").strip()
        mid = (row.get("mfl_id") or "").strip()
        if raw_name and pos:
            kid = (row.get("ktc_id") or "").strip()
            if kid not in ("", "NA"):
                by_ktc.setdefault(kid, (raw_name, pos))
            if mid not in ("", "NA"):
                by_mfl.setdefault(mid, (raw_name, pos))
        if sid in ("", "NA"):
            continue
        if eid not in ("", "NA"):
            by_espn[eid] = sid
        # Per-platform external-id → sleeper joins (multi-platform linking).
        if mid not in ("", "NA"):
            by_mfl_sleeper.setdefault(mid, sid)
        srid = (row.get("sportradar_id") or "").strip()
        if srid not in ("", "NA"):
            by_sportradar.setdefault(srid, sid)
        yid = (row.get("yahoo_id") or "").strip()
        if yid not in ("", "NA"):
            by_yahoo.setdefault(yid, sid)
        nm = normalise_name(row.get("merge_name") or row.get("name") or "")
        if nm and pos:
            by_name.setdefault((nm, pos), sid)
    return Crosswalk(by_espn_id=by_espn, by_name_pos=by_name,
                     by_ktc_id=by_ktc, by_mfl_id=by_mfl,
                     by_mfl_sleeper=by_mfl_sleeper,
                     by_sportradar_id=by_sportradar,
                     by_yahoo_id=by_yahoo)


def load_crosswalk(csv_path: str) -> Crosswalk:
    """Load a DynastyProcess db_playerids CSV (full or trimmed snapshot).

    Needs columns: sleeper_id, position, merge_name (or name), and whichever
    platform id columns a caller relies on (espn_id, mfl_id, sportradar_id,
    yahoo_id). 'NA' cells are treated as missing.
    """
    with open(csv_path, newline="", encoding="utf-8") as f:
        return _parse_crosswalk_rows(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Live crosswalk with cache — Phase 1 wiring
# ---------------------------------------------------------------------------
# The plan (§3) calls for the DP crosswalk to be refreshed "nightly + boot",
# mirroring how values-players.csv already works. We implement that as a
# lazy 24h TTL: the first import after boot fetches db_playerids.csv from
# the same DynastyProcess repo data_loader.py already trusts; subsequent
# imports reuse the in-memory copy until it is a day old. If the fetch
# fails we fall back to (a) the last good in-memory copy, then (b) the
# bundled snapshot fixture — an import is always possible, just possibly
# with a slightly stale crosswalk (new rookies may report as unmatched).

PLAYERIDS_URL = (
    "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
)
_SNAPSHOT_PATH = os.path.join(
    os.path.dirname(__file__), "tests", "fixtures",
    "dp_playerids_snapshot_2026-07-11.csv",
)
_CROSSWALK_TTL_SECONDS = 24 * 3600

_xwalk_lock = threading.Lock()
_xwalk_cache: Crosswalk | None = None
_xwalk_fetched_at: float = 0.0
_xwalk_is_snapshot: bool = False   # True when serving the bundled fallback


def fetch_crosswalk(timeout: int = 15, _opener=None) -> Crosswalk:
    """Fetch the live DP db_playerids CSV and parse it. Raises on failure."""
    req = urllib.request.Request(
        PLAYERIDS_URL, headers={"User-Agent": "FantasyTradeFinder/1.0"}
    )
    opener = _opener or urllib.request.urlopen
    # obs.api_events — GitHub egress, tagged source dynastyprocess NOT espn
    # (docs/integrations/espn.md §6.5). Public CSV: nothing to redact; the
    # row count is the cheapest schema-drift signal available.
    from . import api_observability as _api_obs
    with _api_obs.observe_call("dynastyprocess", "db_playerids",
                               active=_opener is None) as _ob:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        xwalk = _parse_crosswalk_rows(csv.DictReader(io.StringIO(raw)))
        _ob.ok(status=200, response_bytes=len(raw), rows=len(xwalk.by_espn_id))
    return xwalk


def get_crosswalk(_opener=None) -> Crosswalk:
    """Return the cached crosswalk, refreshing from DynastyProcess when the
    cache is empty or older than 24h. Never raises — falls back to the last
    good copy, then to the bundled snapshot fixture."""
    global _xwalk_cache, _xwalk_fetched_at, _xwalk_is_snapshot
    with _xwalk_lock:
        now = time.time()
        # Snapshot fallback retries hourly; a live copy is good for 24h.
        ttl = 3600 if _xwalk_is_snapshot else _CROSSWALK_TTL_SECONDS
        if _xwalk_cache is not None and (now - _xwalk_fetched_at) < ttl:
            return _xwalk_cache
        try:
            _xwalk_cache = fetch_crosswalk(_opener=_opener)
            _xwalk_fetched_at = now
            _xwalk_is_snapshot = False
        except Exception as e:
            print(f"⚠️  DP crosswalk fetch failed ({e}) — "
                  f"{'keeping previous copy' if _xwalk_cache else 'using bundled snapshot'}")
            if _xwalk_cache is None:
                _xwalk_cache = load_crosswalk(_SNAPSHOT_PATH)
                _xwalk_is_snapshot = True
            _xwalk_fetched_at = now   # don't hammer on every request; retry after TTL
        return _xwalk_cache


def map_rosters(teams: list[EspnTeam], xwalk: Crosswalk) -> dict:
    """Map each team's ESPN roster into Sleeper player_ids.

    Returns:
      {
        "rosters": {team_id: [sleeper_id, ...]},
        "report": {
          "pool_players":     skill-position players seen,
          "matched_by_id":    espn_id hit in the crosswalk,
          "matched_by_name":  recovered via normalised name+position,
          "unmatched":        [{"name", "position", "espn_id"}, ...],
          "out_of_pool":      K/DST/unknown-position count (not failures),
          "match_rate":       matched / pool_players (0.0 when pool empty),
        },
      }
    """
    rosters: dict[int, list[str]] = {}
    matched_id = matched_name = out_of_pool = 0
    unmatched: list[dict] = []

    for team in teams:
        ids: list[str] = []
        for p in team.players:
            if p.position not in POOL_POSITIONS:
                out_of_pool += 1
                continue
            sid = xwalk.by_espn_id.get(p.espn_id)
            if sid:
                matched_id += 1
            else:
                sid = xwalk.by_name_pos.get((normalise_name(p.name), p.position))
                if sid:
                    matched_name += 1
            if sid:
                ids.append(sid)
            else:
                unmatched.append(
                    {"name": p.name, "position": p.position, "espn_id": p.espn_id}
                )
        rosters[team.team_id] = ids

    pool = matched_id + matched_name + len(unmatched)
    return {
        "rosters": rosters,
        "report": {
            "pool_players": pool,
            "matched_by_id": matched_id,
            "matched_by_name": matched_name,
            "unmatched": unmatched,
            "out_of_pool": out_of_pool,
            "match_rate": (matched_id + matched_name) / pool if pool else 0.0,
        },
    }


# ---------------------------------------------------------------------------
# Generic per-platform roster crosswalk (MFL / Fleaflicker / future Yahoo)
# ---------------------------------------------------------------------------
# The same fetch → parse → crosswalk shape ESPN uses, factored so any
# platform's service can resolve its native roster ids into Sleeper player
# ids through one shared code path (plan §8). A platform supplies:
#   - team_key: an opaque per-team key (franchise id, team id, …)
#   - players:  list of (external_id, name, position) tuples
#   - id_map:   the Crosswalk id map for that platform's external ids
#               (xwalk.by_mfl_sleeper, xwalk.by_sportradar_id, …)
# The name+position fallback (#127 position-strict) is shared via
# xwalk.by_name_pos — identical rule on every platform.


def map_generic_rosters(teams: list[tuple], id_map: dict, xwalk: Crosswalk) -> dict:
    """Map external rosters into Sleeper player_ids for any platform.

    teams: [(team_key, [(external_id, name, position), ...]), ...]
    id_map: external_id → sleeper_id dict for this platform (e.g.
            xwalk.by_mfl_sleeper). name+pos fallback uses xwalk.by_name_pos.

    Returns the same {"rosters", "report"} shape as ESPN's map_rosters so the
    route/report code is platform-agnostic. K/DST and unknown positions are
    reported as out_of_pool, never as match failures.
    """
    rosters: dict = {}
    matched_id = matched_name = out_of_pool = 0
    unmatched: list[dict] = []

    for team_key, players in teams:
        ids: list[str] = []
        for external_id, name, position in players:
            pos = (position or "").upper()
            if pos not in POOL_POSITIONS:
                out_of_pool += 1
                continue
            sid = id_map.get(str(external_id)) if external_id else None
            if sid:
                matched_id += 1
            else:
                sid = xwalk.by_name_pos.get((normalise_name(name or ""), pos))
                if sid:
                    matched_name += 1
            if sid:
                ids.append(sid)
            else:
                unmatched.append(
                    {"name": name, "position": pos,
                     "external_id": str(external_id) if external_id else ""}
                )
        rosters[team_key] = ids

    pool = matched_id + matched_name + len(unmatched)
    return {
        "rosters": rosters,
        "report": {
            "pool_players": pool,
            "matched_by_id": matched_id,
            "matched_by_name": matched_name,
            "unmatched": unmatched,
            "out_of_pool": out_of_pool,
            "match_rate": (matched_id + matched_name) / pool if pool else 0.0,
        },
    }


# ---------------------------------------------------------------------------
# Spike CLI:  python3 -m backend.espn_service <league_id> [season]
# ---------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    import os

    if len(argv) < 2:
        print("usage: python3 -m backend.espn_service <league_id> [season] "
              "(set ESPN_S2 + SWID env vars for a private league)")
        return 2
    league_id = argv[1]
    season = int(argv[2]) if len(argv) > 2 else 2026

    raw = fetch_league(
        league_id, season,
        espn_s2=os.environ.get("ESPN_S2"), swid=os.environ.get("SWID"),
    )
    league = parse_league(raw)
    here = os.path.dirname(__file__)
    xwalk = load_crosswalk(
        os.path.join(here, "tests", "fixtures", "dp_playerids_snapshot_2026-07-11.csv")
    )
    out = map_rosters(league["teams"], xwalk)
    print(f"League: {league['name']} ({league['league_id']}, season {league['season']}, "
          f"{league['total_teams']} teams)")
    for team in league["teams"]:
        print(f"  {team.team_id}: {team.name} — {len(out['rosters'][team.team_id])} "
              f"pool players mapped")
    r = out["report"]
    print(f"Crosswalk: {r['matched_by_id']} by id + {r['matched_by_name']} by name "
          f"of {r['pool_players']} pool players → {r['match_rate']:.1%} "
          f"({r['out_of_pool']} K/DST out of pool)")
    for u in r["unmatched"]:
        print(f"  unmatched: {u['name']} {u['position']} espn:{u['espn_id']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys

    raise SystemExit(_main(sys.argv))

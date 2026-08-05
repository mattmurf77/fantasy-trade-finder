"""Per-league rookie-draft status detection (#207).

One shared detector so #228's owned-pick hiding and #207's year-explicit
pick-rung labels can never disagree about whether a league's CURRENT-season
rookie draft has happened.

Design (docs/feedback/items/207-rookie-draft-detection/plan.md §"Detection
algorithm"), grounded in the live API probes recorded in that folder's
research-platforms.md:

  * **Sleeper** — `GET /v1/league/<id>/drafts` is authoritative, but only for
    a *rookie-shaped* draft (`settings.player_type` is 0 even on a rookies-only
    draft — verified useless; the shape discriminator is the round count).
    `complete` + `last_picked` set ⇒ drafted/high. `pre_draft`/`drafting` ⇒
    not_drafted/high **unless** the roster heuristic screams drafted, in which
    case the rosters win (off-platform draft, imported league, deleted draft
    object). An EMPTY drafts list is ambiguous — a network flake and a league
    with no draft object are indistinguishable — so it is `unknown`, never
    `not_drafted` on its own.
  * **MFL** — `TYPE=draftResults` is authoritative and zero-auth. MFL
    pre-populates the whole grid before the draft, so completion is
    `count(player != "") == len(draftPick)`.
  * **ESPN / Fleaflicker / anything else** — heuristic only. ESPN's
    `mDraftDetail` is documented but was NOT verifiable against a live league,
    so nothing here is built on it (see the status doc's ESPN caveat).
  * **Rosters heuristic** — rookie test is `players.rookie_year == season`
    (falling back to `years_exp == 0 AND team IS NOT NULL` when the class year
    is unknown). Serves as both the fallback signal and the veto above.

**Fail-safe:** `unknown` (and any low-confidence read) is treated as
NOT drafted by `current_year_picks_visible()` — a phantom current-year pick is
a visible, self-correcting error; a silently hidden real asset produces no
artifact at all. This is the same asymmetry #228 chose ("a flaked drafts read
excludes nothing").

The module is dependency-free on purpose: callers fetch (server.py owns the
HTTP), this module decides. That keeps the whole conflict matrix unit-testable
without a network or a Flask app.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ── Verdicts ───────────────────────────────────────────────────────────────
DRAFTED = "drafted"
NOT_DRAFTED = "not_drafted"
UNKNOWN = "unknown"

# ── Confidence ─────────────────────────────────────────────────────────────
HIGH = "high"
MEDIUM = "medium"
LOW = "low"

# ── Sources ────────────────────────────────────────────────────────────────
SRC_SLEEPER = "sleeper_draft_status"
SRC_MFL = "mfl_draft_results"
SRC_ROSTERS = "rosters_heuristic"
SRC_NONE = "none"

# A rookie draft fills a handful of rounds; a startup fills a whole roster.
# `type` (snake/linear) correlates but is a league preference, not a
# guarantee — the round count is the discriminator (research §1.3).
ROOKIE_MAX_ROUNDS = 8
STARTUP_MIN_ROUNDS = 15


@dataclass(frozen=True)
class DraftStatus:
    """A verdict, how much we trust it, and what produced it."""
    status: str = UNKNOWN
    confidence: str = LOW
    source: str = SRC_NONE
    evidence: dict = field(default_factory=dict)

    @property
    def drafted(self) -> bool:
        """True only on a positive drafted verdict (never on `unknown`)."""
        return self.status == DRAFTED


def current_year_picks_visible(status: DraftStatus | None) -> bool:
    """THE fail-safe. Current-season picks stay visible unless we positively
    know the rookie draft happened. `None`/`unknown`/low-confidence all show.
    """
    return not (status is not None and status.drafted)


# ---------------------------------------------------------------------------
# Signal 3 — rookies on rosters (fallback AND veto)
# ---------------------------------------------------------------------------

def is_rookie_row(rookie_year: str | int | None, years_exp: int | None,
                  team: str | None, season: int) -> bool:
    """Rookie test for one `players` row, per research §2.5.

    `metadata.rookie_year` is the exact "class of YYYY" field (Sleeper's
    `years_exp` counts *accrued* seasons, so a 2023 UDFA who spent two years
    on practice squads reads `years_exp == 1` — it is not a class field). Fall
    back to `years_exp == 0 AND team IS NOT NULL` only when the class year is
    missing; the team requirement drops the teamless pre-NFL-draft prospect
    tail that would otherwise read as rookies every January.
    """
    ry = str(rookie_year).strip() if rookie_year is not None else ""
    if ry and ry not in ("0", "None"):
        return ry == str(int(season))
    return years_exp == 0 and bool(team)


def rosters_verdict(rookies_rostered: int, teams_with_rookie: int,
                    league_size: int, unclassifiable: int = 0) -> DraftStatus:
    """Rookies-on-rosters heuristic. Tops out at MEDIUM by design — it is
    circumstantial evidence, never authoritative (plan §"Detection algorithm"
    step 3).

    Thresholds are relative to league size so an 8-team 1-round draft is not
    penalised: even a single-round rookie draft produces exactly `N` rookies,
    so `>= N` across `>= ceil(N/2)` teams is the drafted bar. The team-spread
    half of the test is what kills the "one manager hoarded rookies off
    waivers" false positive.
    """
    n = max(1, int(league_size or 0) or 1)
    ev = {
        "rookies_rostered": rookies_rostered,
        "teams_with_rookie": teams_with_rookie,
        "league_size": n,
        "unclassifiable_rostered": unclassifiable,
    }
    if rookies_rostered >= n and teams_with_rookie >= math.ceil(n / 2):
        return DraftStatus(DRAFTED, MEDIUM, SRC_ROSTERS, ev)
    if rookies_rostered == 0:
        # A large unclassifiable tail means our player table is stale, not
        # that the league has no rookies — abstain rather than assert.
        if unclassifiable >= n:
            return DraftStatus(UNKNOWN, LOW, SRC_ROSTERS, ev)
        return DraftStatus(NOT_DRAFTED, MEDIUM, SRC_ROSTERS, ev)
    return DraftStatus(UNKNOWN, LOW, SRC_ROSTERS, ev)


# ---------------------------------------------------------------------------
# Signal 1 — Sleeper drafts chain
# ---------------------------------------------------------------------------

def _draft_rounds(draft: dict) -> int | None:
    try:
        r = (draft.get("settings") or {}).get("rounds")
        return int(r) if r is not None else None
    except (TypeError, ValueError, AttributeError):
        return None


def _is_rookie_shaped(draft: dict) -> bool | None:
    """True = rookie-sized, False = startup-sized, None = can't tell."""
    rounds = _draft_rounds(draft)
    if rounds is None or rounds <= 0:
        return None
    if rounds <= ROOKIE_MAX_ROUNDS:
        return True
    if rounds >= STARTUP_MIN_ROUNDS:
        return False
    return None


def sleeper_verdict(drafts: list[dict] | None, season: int,
                    rosters: DraftStatus | None = None) -> DraftStatus:
    """Sleeper signal ordering (plan step 1), with the rosters veto.

    `drafts is None` = the read failed. `drafts == []` = ambiguous (a flake and
    a genuinely draft-less league are indistinguishable today) — both fall
    through to the heuristic rather than asserting `not_drafted`.
    """
    if not drafts:
        return _fall_back(rosters, reason="no_drafts" if drafts == [] else "drafts_unavailable")

    season = int(season)
    matching: list[dict] = []
    for d in drafts:
        if not isinstance(d, dict):
            continue
        try:
            if int(d.get("season") or 0) == season:
                matching.append(d)
        except (TypeError, ValueError):
            continue
    if not matching:
        return _fall_back(rosters, reason="no_current_season_draft")

    rookie_drafts = [d for d in matching if _is_rookie_shaped(d) is not False]
    if not rookie_drafts:
        # Only a startup draft this season. A completed startup says nothing
        # about a still-pending rookie draft (research §1.3) — heuristic only.
        return _fall_back(rosters, reason="startup_shaped_draft_only")

    for d in rookie_drafts:
        if d.get("status") != "complete":
            continue
        ev = {"draft_status": "complete", "rounds": _draft_rounds(d),
              "last_picked": d.get("last_picked")}
        if not d.get("last_picked"):
            # Flipped to complete with zero picks made — not trustworthy.
            fb = _fall_back(rosters, reason="complete_without_picks")
            return DraftStatus(fb.status, fb.confidence, fb.source,
                               {**ev, **fb.evidence})
        if rosters is not None and rosters.status == NOT_DRAFTED:
            # Conflict rule 1: platform wins, but a completed rookie draft
            # with zero rookies rostered is near-impossible — usually stale
            # player data or a dropped crosswalk. Downgrade and record it.
            return DraftStatus(DRAFTED, MEDIUM, SRC_SLEEPER,
                               {**ev, "anomaly": "no_rookies_rostered",
                                **rosters.evidence})
        return DraftStatus(DRAFTED, HIGH, SRC_SLEEPER, ev)

    # Every current-season rookie-shaped draft is pre_draft / drafting.
    statuses = [d.get("status") for d in rookie_drafts]
    ev = {"draft_status": statuses[0], "draft_statuses": statuses,
          "rounds": _draft_rounds(rookie_drafts[0])}
    if rosters is not None and rosters.status == DRAFTED:
        # Conflict rule 2: rosters are ground truth. `status` is stale
        # whenever the draft ran off-platform or the object was deleted.
        return DraftStatus(DRAFTED, MEDIUM, SRC_ROSTERS,
                           {**ev, "veto": "rosters_show_rookie_class",
                            **rosters.evidence})
    return DraftStatus(NOT_DRAFTED, HIGH, SRC_SLEEPER, ev)


# ---------------------------------------------------------------------------
# Signal 2 — MFL draftResults
# ---------------------------------------------------------------------------

def _as_list(value) -> list:
    """MFL serves a bare dict when a collection has one member (mirrors
    mfl_service._as_list — duplicated so this module stays import-free)."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def mfl_verdict(draft_results: dict | None, league_size: int,
                rosters: DraftStatus | None = None) -> DraftStatus:
    """MFL `TYPE=draftResults`: `made == total` ⇒ drafted.

    MFL pre-populates the entire grid, so unmade picks come back with
    `player: ""`. `draftUnit` may be a LIST when a league drafts by
    division/conference — aggregate across units.
    """
    if not isinstance(draft_results, dict):
        return _fall_back(rosters, reason="mfl_export_unavailable")
    units = _as_list((draft_results.get("draftResults") or {}).get("draftUnit"))
    if not units:
        return _fall_back(rosters, reason="mfl_no_draft_unit")

    made = total = 0
    for u in units:
        if not isinstance(u, dict):
            continue
        for p in _as_list(u.get("draftPick")):
            if not isinstance(p, dict):
                continue
            total += 1
            if str(p.get("player") or "").strip():
                made += 1
    if total == 0:
        return _fall_back(rosters, reason="mfl_empty_grid")

    n = max(1, int(league_size or 0) or 1)
    rounds = total / n
    ev = {"made": made, "total": total, "rounds": round(rounds, 2),
          "league_size": n}
    if rounds > ROOKIE_MAX_ROUNDS:
        # Startup-sized grid — same reasoning as Sleeper's §1.3 branch.
        fb = _fall_back(rosters, reason="mfl_startup_shaped_grid")
        return DraftStatus(fb.status, fb.confidence, fb.source,
                           {**ev, **fb.evidence})
    if made >= total:
        if rosters is not None and rosters.status == NOT_DRAFTED:
            return DraftStatus(DRAFTED, MEDIUM, SRC_MFL,
                               {**ev, "anomaly": "no_rookies_rostered"})
        return DraftStatus(DRAFTED, HIGH, SRC_MFL, ev)
    # 0 <= made < total — unmade picks still exist, so the season's picks are
    # still real assets (an in-progress draft counts as NOT drafted here).
    if rosters is not None and rosters.status == DRAFTED and made == 0:
        return DraftStatus(DRAFTED, MEDIUM, SRC_ROSTERS,
                           {**ev, "veto": "rosters_show_rookie_class"})
    return DraftStatus(NOT_DRAFTED, HIGH, SRC_MFL, ev)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _fall_back(rosters: DraftStatus | None, reason: str) -> DraftStatus:
    """No usable platform signal → the heuristic, or `unknown`."""
    if rosters is None:
        return DraftStatus(UNKNOWN, LOW, SRC_NONE, {"reason": reason})
    return DraftStatus(rosters.status, rosters.confidence, rosters.source,
                       {**rosters.evidence, "reason": reason})


def detect(platform: str, season: int, league_size: int,
           sleeper_drafts: list[dict] | None = None,
           mfl_draft_results: dict | None = None,
           rosters: DraftStatus | None = None) -> DraftStatus:
    """Resolve one league's current-season rookie-draft status.

    `rosters` is the pre-computed heuristic verdict (build it with
    `rosters_verdict`) — pass None when rosters are unavailable so the
    conflict rules abstain instead of guessing.
    """
    plat = (platform or "sleeper").lower()
    if plat == "sleeper":
        return sleeper_verdict(sleeper_drafts, season, rosters)
    if plat == "mfl":
        return mfl_verdict(mfl_draft_results, league_size, rosters)
    # ESPN / Fleaflicker / unknown platforms: heuristic only.
    return _fall_back(rosters, reason=f"{plat}_heuristic_only")

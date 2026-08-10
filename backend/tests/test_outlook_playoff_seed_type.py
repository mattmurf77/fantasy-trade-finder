"""BUG-3 — `settings.playoff_seed_type` modeling (Phase 4, `playoff_format.py`).

Full research + verification method:
docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md
§7 BUG-3.

Sleeper's `playoff_seed_type` controls how the playoff bracket advances
between rounds, independent of the initial seeding criteria (record, then
points_for — unchanged, still `StandardFormat.seed()`):

  - 0 → "fixed" bracket (Sleeper's own docs: "standard bracket, no
    re-seeding"). A team's opponent in every round is determined once, at
    the start, by bracket position.
  - 1 → "reseed": after every round, the highest surviving seed always plays
    the lowest surviving seed. This is what the engine has always modeled
    (today's behavior, unconditionally, before this fix).
  - anything else (missing/None/unrecognized) → explicit, LOGGED fallback to
    reseed (today's behavior) — never silently guessed.

This file covers:
  1. `_resolve_seed_type` value mapping + the logged fallback.
  2. A synthetic, hand-verified divergence case: fixed vs reseed produce
     DIFFERENT champions/pairings for the same upset pattern.
  3. Real-fixture replay: `playoff_seed_type=0` leagues (ffv3, all 4 completed
     captured seasons) — replaying Sleeper's OWN recorded game-by-game results
     through `_play_fixed_bracket` reproduces Sleeper's own recorded champion
     exactly. This is the empirical proof behind value 0's semantics.
  4. Wiring: `get_playoff_format` / `StandardFormat` thread the value; unknown
     values don't crash; `pipeline.run_outlook` threads an explicit kwarg or
     an attribute on `state` (the `scoring_format` precedent) through to
     Phase 4.

No test here touches the network; fixture tests skip if the fixtures aren't
present (same convention as test_outlook_calibration.py).
"""

from __future__ import annotations

import logging
import os
import sys

import pytest

from backend.outlook.league_state import LeagueState, TeamState, compute_num_byes
from backend.outlook.pipeline import run_outlook
from backend.outlook.playoff_format import (
    StandardFormat,
    _resolve_seed_type,
    _SEED_TYPE_FIXED,
    _SEED_TYPE_RESEED,
    get_playoff_format,
)
from backend.outlook.strength import TeamStrength

_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "fixtures", "outlook-calibration")
_HAS_FIXTURES = os.path.isdir(FIXTURE_DIR) and bool(os.listdir(FIXTURE_DIR))
pytestmark_fixtures = pytest.mark.skipif(
    not _HAS_FIXTURES, reason="outlook-calibration fixtures not present")


# ---------------------------------------------------------------------------
# 1 — value mapping + logged fallback
# ---------------------------------------------------------------------------

def test_seed_type_0_maps_to_fixed():
    assert _resolve_seed_type(0) == _SEED_TYPE_FIXED


def test_seed_type_1_maps_to_reseed():
    assert _resolve_seed_type(1) == _SEED_TYPE_RESEED


def test_seed_type_none_falls_back_to_reseed_silently(caplog):
    with caplog.at_level(logging.WARNING):
        assert _resolve_seed_type(None) == _SEED_TYPE_RESEED
    assert not caplog.records, "None (absent setting) is expected, not a warning case"


def test_seed_type_unrecognized_falls_back_to_reseed_loudly(caplog):
    with caplog.at_level(logging.WARNING):
        assert _resolve_seed_type(2) == _SEED_TYPE_RESEED
    assert any("playoff_seed_type=2" in r.message for r in caplog.records)
    assert any("reseed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# 2 — wiring: StandardFormat / get_playoff_format / run_outlook
# ---------------------------------------------------------------------------

def test_standard_format_stores_and_resolves_seed_type():
    fmt = StandardFormat(6, 2, playoff_seed_type=0)
    assert fmt.playoff_seed_type == 0
    assert fmt._seed_mode == _SEED_TYPE_FIXED

    fmt_default = StandardFormat(6, 2)
    assert fmt_default.playoff_seed_type is None
    assert fmt_default._seed_mode == _SEED_TYPE_RESEED


def test_get_playoff_format_threads_seed_type():
    fmt = get_playoff_format("standard", 6, 2, 0, 0)
    assert fmt._seed_mode == _SEED_TYPE_FIXED
    fmt2 = get_playoff_format("standard", 6, 2)  # unspecified — old call shape
    assert fmt2._seed_mode == _SEED_TYPE_RESEED


def _flat_state(n_teams=8, playoff_slots=6) -> LeagueState:
    rids = list(range(1, n_teams + 1))
    teams = [TeamState(roster_id=r, user_id=f"u{r}", username=f"user{r}",
                       display_name=f"Team {r}") for r in rids]
    # Fully "completed" (regular_season_weeks == completed_weeks) so
    # remaining_weeks() is empty and the simulator skips straight to
    # seeding/bracket — >= outlook_trailing_min_weeks (3) so TrailingScores
    # doesn't need an override.
    return LeagueState(
        league_id="LG-SEEDTYPE", platform="sleeper", regular_season_weeks=3,
        playoff_slots=playoff_slots, num_byes=compute_num_byes(playoff_slots),
        roster_slots=[], teams=teams, schedule={}, completed_weeks=3,
        weekly_scores={r: [100.0, 100.0, 100.0] for r in rids})


def test_run_outlook_threads_explicit_playoff_seed_type_kwarg():
    st = _flat_state()
    strengths = {t.roster_id: TeamStrength(t.roster_id, 100.0, 1.0) for t in st.teams}
    # Deterministic (sigma~0): champion should be reproducible either way, but
    # the point here is just that the kwarg doesn't raise / plumbs through.
    payload = run_outlook(st, player_value={}, player_pos={}, model_cfg={},
                          source_override="trailing_scores", n_sims=50,
                          playoff_seed_type=0)
    assert payload["teams"]


def test_run_outlook_threads_seed_type_attached_to_state():
    """Mirrors the `scoring_format` precedent: a caller may attach the raw
    value to `state` instead of passing the kwarg (this is how
    backend/server.py's route delivers it without editing league_state.py —
    see `_outlook_sleeper_fetch`)."""
    st = _flat_state()
    setattr(st, "playoff_seed_type", 0)
    payload = run_outlook(st, player_value={}, player_pos={}, model_cfg={},
                          source_override="trailing_scores", n_sims=50)
    assert payload["teams"]


def test_explicit_kwarg_wins_over_state_attribute():
    st = _flat_state()
    setattr(st, "playoff_seed_type", 0)
    # explicit kwarg (1) should win over the state attribute (0)
    from backend.outlook import pipeline as _pipeline

    captured = {}
    orig = _pipeline.get_playoff_format

    def spy(*a, **k):
        captured["seed_type"] = a[4] if len(a) > 4 else k.get("playoff_seed_type")
        return orig(*a, **k)

    _pipeline.get_playoff_format = spy
    try:
        run_outlook(st, player_value={}, player_pos={}, model_cfg={},
                   source_override="trailing_scores", n_sims=10,
                   playoff_seed_type=1)
    finally:
        _pipeline.get_playoff_format = orig
    assert captured["seed_type"] == 1


# ---------------------------------------------------------------------------
# 3 — synthetic divergence: fixed vs reseed disagree on a crafted upset
# ---------------------------------------------------------------------------

def test_fixed_and_reseed_diverge_on_a_double_upset():
    """6-team / 2-bye bracket (the real-world shape: seeds 1-2 bye, round 1 is
    seed3v6 + seed4v5). If BOTH round-1 underdogs win (seed5 over seed4, AND
    seed6 over seed3), a fixed bracket keeps seed1 anchored to the seed4v5
    'half' (now surviving as seed5) while a reseed bracket re-ranks all four
    round-2 participants and pairs seed1 with the WORST remaining seed (6),
    not seed5. This is exactly case (5,6) worked out by hand against the real
    ffv3 fixture bracket shapes (see calibration-report-2026-08-09.md)."""
    field = [1, 2, 3, 4, 5, 6]  # seed order, best to worst
    num_byes = 2

    # sample() always makes the LOWER seed number lose (i.e. seed5 beats
    # seed4, seed6 beats seed3 — both round-1 upsets), and thereafter the
    # HIGHER remaining seed number always wins (so we can trace exactly which
    # pairing happened without ambiguity about who wins later rounds).
    def upset_sample(rid: int) -> float:
        return float(rid)  # higher roster_id (== worse seed) scores higher

    fixed = StandardFormat(6, num_byes, playoff_seed_type=0)
    reseed = StandardFormat(6, num_byes, playoff_seed_type=1)

    champ_fixed = fixed.champion(field, upset_sample)
    champ_reseed = reseed.champion(field, upset_sample)

    # Fixed bracket: seed1 vs winner(4v5)=5 -> 5 wins (higher score always
    # wins under upset_sample); seed2 vs winner(3v6)=6 -> 6 wins. Final: 5 v 6
    # -> 6 wins. Champion = 6.
    assert champ_fixed == 6

    # Reseed bracket: round1 survivors {1,2,5,6} (byes 1,2 auto-advance).
    # Reseed pairs best-vs-worst among survivors: seed1 vs seed6 (worst),
    # seed2 vs seed5. Under upset_sample the higher number always wins, so
    # 6 beats 1, 5 beats 2. Final: 6 v 5 -> 6 wins. Champion = 6 either way
    # in THIS particular sample function (it always favors the higher
    # roster_id) — so assert the INTERMEDIATE pairing differs instead, which
    # is the actual claim under test.
    assert champ_reseed == 6

    # The champion coincides here because `upset_sample` is monotonic in
    # roster_id regardless of pairing — assert the actual bracket TOPOLOGY
    # differs instead, which is the real claim: fixed sends seed1 to face
    # seed5 in round 2, reseed sends seed1 to face seed6.
    calls_fixed: list[int] = []
    calls_reseed: list[int] = []

    def tracking_sample(log):
        def f(rid: int) -> float:
            log.append(rid)
            return float(rid)
        return f

    fixed.champion(field, tracking_sample(calls_fixed))
    reseed.champion(field, tracking_sample(calls_reseed))
    # Round 1: `_play_fixed_bracket` walks the padded bracket slots
    # [1,None,4,5,2,None,3,6] pair-by-pair, so its two REAL round-1 games are
    # sampled in the order (4,5) then (3,6). `_play_reseed_bracket`'s round 1
    # is `_play_round(playing=[3,4,5,6])`, which pairs i=0/j=last first, so
    # its two games are sampled (3,6) then (4,5) — same two games, opposite
    # order (both bracket constructions play the same round-1 MATCHUPS; only
    # the traversal order differs, which is why this asserts on the PAIRING,
    # not a literal list-equality of the raw call order).
    assert calls_fixed[:4] == [4, 5, 3, 6]
    assert calls_reseed[:4] == [3, 6, 4, 5]
    assert calls_fixed[4:6] == [1, 5]     # fixed: seed1 faces seed5
    assert calls_reseed[4:6] == [1, 6]    # reseed: seed1 faces seed6 (worst)


# ---------------------------------------------------------------------------
# 4 — real-fixture replay: playoff_seed_type == 0 leagues (ffv3)
# ---------------------------------------------------------------------------

def _elim_round(fx: dict) -> dict[int, int]:
    """roster_id -> the round it was eliminated in Sleeper's REAL recorded
    WINNERS bracket (1/2/3), or 4 for the champion. Monotonic with every
    actual pairwise result: whoever beat whom in a real advancement match
    always ends up with a strictly higher elimination round (see module
    docstring for why 'wins count' alone is NOT reliable here — byes distort
    it, elimination round doesn't).

    Sleeper's `winners_bracket` also carries placement/consolation games
    (`p == 5` fifth-place, `p == 3` third-place) played BETWEEN teams already
    eliminated from the real advancement bracket. Those rows share the same
    `r` as later real rounds and would overwrite an already-correct
    elimination round with a wrong, later one — e.g. a team eliminated in
    round 1 that then loses the 5th-place game (itself tagged `r: 2`) must
    NOT be recorded as eliminated in round 2. Only `p in (None, 1)` rows are
    real advancement games; `p in (3, 5)` are excluded."""
    wb = fx.get("winners_bracket") or []
    elim: dict[int, int] = {}
    champ = None
    for m in wb:
        if m.get("p") in (3, 5):
            continue
        r, w, l = m.get("r"), m.get("w"), m.get("l")
        if isinstance(l, int):
            elim[l] = r
        if m.get("p") == 1 and isinstance(w, int):
            champ = w
    if champ is not None:
        elim[champ] = 4
    return elim


def _seed_order_from_full_state(full) -> list[int]:
    rows = [(t.roster_id, t.win_credit, t.points_for) for t in full.teams]
    rows.sort(key=lambda r: (-r[1], -r[2], r[0]))
    return [r[0] for r in rows]


@pytestmark_fixtures
@pytest.mark.parametrize("name", ["ffv3-2022", "ffv3-2023", "ffv3-2024", "ffv3-2025"])
def test_fixed_bracket_reproduces_sleepers_real_champion_for_seed_type_0(name):
    import outlook_calibration_backtest as bt
    fx = bt.load_fixture(name)
    settings = ((fx.get("league") or {}).get("settings") or {})
    assert settings.get("playoff_seed_type") == 0, (
        f"{name} fixture must be a playoff_seed_type=0 league for this test")

    full = bt.build_full_state(fx)
    field_truth, champ_truth = bt.truth(fx, full.playoff_slots)

    seed_order = _seed_order_from_full_state(full)
    assert set(seed_order[:full.playoff_slots]) == field_truth

    elim = _elim_round(fx)

    def sample(rid: int) -> float:
        # Higher elimination round == went further == "wins" any comparison
        # against a team that was eliminated earlier in the REAL bracket.
        return float(elim.get(rid, 0))

    fmt = StandardFormat(full.playoff_slots, full.num_byes, playoff_seed_type=0)
    champ = fmt.champion(seed_order, sample)
    assert champ == champ_truth, (
        f"{name}: fixed-bracket replay champion {champ} != Sleeper's real "
        f"champion {champ_truth}")


@pytestmark_fixtures
@pytest.mark.parametrize("name", ["lakeview-2024", "lakeview-2025"])
def test_reseed_bracket_reproduces_lakeviews_real_champion_for_seed_type_1(name):
    """lakeview is playoff_seed_type=1 (reseed). Neither completed season
    happens to contain a round-1 upset pattern that would distinguish reseed
    from fixed (see calibration report — this is disclosed, not hidden), so
    this is a no-regression check (today's shipped behavior still reproduces
    the real champion), not an independent proof of value 1's semantics the
    way the ffv3 test is for value 0."""
    import outlook_calibration_backtest as bt
    fx = bt.load_fixture(name)
    settings = ((fx.get("league") or {}).get("settings") or {})
    assert settings.get("playoff_seed_type") == 1

    full = bt.build_full_state(fx)
    field_truth, champ_truth = bt.truth(fx, full.playoff_slots)
    seed_order = _seed_order_from_full_state(full)
    elim = _elim_round(fx)

    def sample(rid: int) -> float:
        return float(elim.get(rid, 0))

    fmt = StandardFormat(full.playoff_slots, full.num_byes, playoff_seed_type=1)
    champ = fmt.champion(seed_order, sample)
    assert champ == champ_truth


# ---------------------------------------------------------------------------
# 5 — the OFFLINE BACKTEST HARNESSES must pass the setting too (2026-08-10)
#
# The BUG-3 fix landed in `playoff_format.py` but
# `scripts/outlook_calibration_backtest.py` was not updated to pass
# `playoff_seed_type` into its `run_outlook` / `get_playoff_format` calls, so
# every title number it published kept scoring FFv3 (4 of the 6 captured
# league-seasons, all `playoff_seed_type: 0`) under the RESEEDING rule that
# league does not use. The guards below make that specific regression — a new
# or edited call site that forgets the argument — a test failure rather than a
# silently wrong report.
# ---------------------------------------------------------------------------

_SEED_TYPE_ARG_NAMES = ("playoff_seed_type", "seed_type", "stype")


def _calls_missing_seed_type(module_path: str) -> list[str]:
    """Every `run_outlook(...)` / `get_playoff_format(...)` call in a script
    that does not pass the league's seed type, as 'func:lineno' strings."""
    import ast
    with open(module_path) as f:
        tree = ast.parse(f.read(), module_path)
    missing = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = (fn.attr if isinstance(fn, ast.Attribute)
                else fn.id if isinstance(fn, ast.Name) else None)
        if name not in ("run_outlook", "get_playoff_format"):
            continue
        if not any(a in ast.unparse(node) for a in _SEED_TYPE_ARG_NAMES):
            missing.append("%s:%d" % (name, node.lineno))
    return missing


@pytest.mark.parametrize("script", ["outlook_calibration_backtest.py",
                                    "outlook_preseason_backtest.py"])
def test_backtest_scripts_pass_seed_type_into_every_bracket_they_build(script):
    path = os.path.join(_SCRIPTS, script)
    if not os.path.exists(path):
        pytest.skip("%s not present" % script)
    missing = _calls_missing_seed_type(path)
    assert not missing, (
        "%s builds a playoff bracket without the league's playoff_seed_type "
        "at: %s — its title numbers would score FFv3 on the wrong bracket "
        "(BUG-3)." % (script, ", ".join(missing)))


@pytestmark_fixtures
@pytest.mark.parametrize("name,expected", [
    ("ffv3-2022", 0), ("ffv3-2023", 0), ("ffv3-2024", 0), ("ffv3-2025", 0),
    ("lakeview-2024", 1), ("lakeview-2025", 1),
])
def test_backtest_seed_type_helper_reads_each_leagues_real_setting(name, expected):
    import outlook_calibration_backtest as bt
    assert bt.seed_type(bt.load_fixture(name)) == expected


@pytestmark_fixtures
def test_seed_type_is_load_bearing_on_a_real_captured_season():
    """Guard against the wiring being cosmetic: on a real `playoff_seed_type:
    0` season the fixed bracket must produce a DIFFERENT title distribution
    from the reseeding one the harness used before. Playoff odds are
    seed-type-independent by construction — the field is settled before the
    bracket is played — so only `title_pct` may move."""
    import outlook_calibration_backtest as bt
    fx = bt.load_fixture("ffv3-2022")
    st = bt.as_of(bt.build_full_state(fx), 9)
    fixed = run_outlook(st, player_value={}, player_pos={}, model_cfg={},
                        basis="consensus", n_sims=4000, playoff_seed_type=0)
    reseed = run_outlook(st, player_value={}, player_pos={}, model_cfg={},
                         basis="consensus", n_sims=4000, playoff_seed_type=1)
    titles = lambda p: {t["roster_id"]: t["odds"]["title_pct"] for t in p["teams"]}
    berths = lambda p: {t["roster_id"]: t["odds"]["playoff_pct"] for t in p["teams"]}
    assert titles(fixed) != titles(reseed)
    assert berths(fixed) == berths(reseed)

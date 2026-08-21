"""trade.bakeoff — serving-path integration (Phase 3).

Spec: docs/plans/three-model-bakeoff/PLAN.md §3.4, §4, §5.
Scope block: docs/plans/three-model-bakeoff/scope-phase3.md.

Contract under test, in `server._run_trade_job`:

  • Flag OFF ⇒ the generation path is byte-identical to pre-bake-off
    `origin/main`. Proven against a CAPTURED golden
    (backend/tests/fixtures/bakeoff/flag_off_golden.json, originally produced
    by running backend/tests/support/bakeoff_harness.py inside a worktree at
    the pre-bake-off SHA), not against an assertion about ourselves. The only
    admitted difference is the two additive NULL columns.
    RE-CAPTURED 2026-08-21 (twice, same wave): (1) the operator-approved
    package-benchmark fix (`package_bench_trade_wide`, docs/reviews/
    2026-08-21-market-curve-comparison.md §3b) deliberately moved
    generation for every arm, so the flag-off deck moved with it (2 cards
    → 1 on this fixture — the receive side of the dropped 1-for-2 now
    prices out of band); (2) the gap auto-sweetener stamps a
    `gap_sweetener` key (null when unsweetened) on every impression row's
    features_json. The golden is the post-wave flag-off output; it still
    proves flag OFF serves exactly the non-bake-off path, which is its
    contract.
  • Phase 4 (dark, the default inside the flag): three arms generate and log,
    only arm `current` is served, and the served deck is still the flag-off
    deck.
  • Phase 5 (interleaved): the deck order is the interleaver's and NO
    post-generation layer may touch it (§3.4 Channel 2) — including the
    likes-you injector, which re-sorts by composite_score.
  • Every served card is attributed: deck_impressions.model_arm + .arm_rank,
    the arm encoded into policy_version, agreement in features_json, and one
    bakeoff_runs row per job.
  • §3.4 Channel 1: every fit-congruence K multiplier in the swipe paths runs
    through the bake-off Elo freeze.
"""

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

import backend.bakeoff_runner as bo
import backend.server as server
from backend.database import bakeoff_runs_table
from backend.tests.support import bakeoff_harness as H
from backend.trade_service import TradeCard


GOLDEN = (Path(__file__).parent / "fixtures" / "bakeoff"
          / "flag_off_golden.json")

#: The columns this change ADDS to deck_impressions. Everything else in a
#: flag-off row must equal the captured golden exactly.
NEW_COLUMNS = ("model_arm", "arm_rank", "fairness_threshold",
               "group_key", "group_rank", "lane_slot", "trade_intent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_new_columns(capture: dict) -> dict:
    out = dict(capture)
    out["impressions"] = [
        {k: v for k, v in row.items() if k not in NEW_COLUMNS}
        for row in capture["impressions"]
    ]
    return out


#: Phase 3's serving shape as knob KILL values: no group composition, no deck
#: cap, arm A in the roster. The tests written for Phase 3 keep asserting it,
#: which is what proves the kill values still restore it.
#:
#: D-095 adds `bakeoff_include_challenger` = 0 for the same reason the other
#: three are here: arm D joined the DEFAULT roster, and these tests are about
#: Phase 3's three-arm serving shape, not about which arms exist today. Its
#: presence here is itself the assertion that the challenger's kill knob
#: restores the pre-D-095 roster exactly (PRD §5 A1).
PHASE3_KNOBS = {"bakeoff_group_size": 0.0, "bakeoff_deck_limit": 0.0,
                "bakeoff_include_baseline": 1.0,
                "bakeoff_include_challenger": 0.0}


def _bakeoff_patches(*, enabled: bool, interleaved: bool = False,
                     composed: bool = False, **knob_overrides):
    """`composed=False` (the default) pins the Phase-3 fallback so the
    pre-composition tests keep testing what they were written for;
    `composed=True` runs the live 2026-08-18 defaults."""
    knobs = {"bakeoff_serve_interleaved": 1.0 if interleaved else 0.0}
    if not composed:
        knobs.update(PHASE3_KNOBS)
    knobs.update({k: float(v) for k, v in knob_overrides.items()})
    return [
        patch.object(bo, "bakeoff_enabled", lambda: enabled),
        patch.object(bo, "_cfg", lambda k, d: float(knobs.get(k, d))),
    ]


def _card(give, recv, target=H.OPP, composite=1.0):
    return TradeCard(
        trade_id=f"t_{'_'.join(give)}_{'_'.join(recv)}",
        league_id=H.LEAGUE,
        proposing_user_id=H.ME,
        target_user_id=target,
        target_username="opp",
        give_player_ids=list(give),
        receive_player_ids=list(recv),
        fairness_score=0.9,
        mismatch_score=50.0,
        composite_score=composite,
    )


def _stub_arms(a_cards, b_cards, c_cards):
    """Replace the three generators with fixed ranked lists so the expected
    interleave is exact. `generate_trades` distinguishes arm A from arm B by
    the thread-local overlay the runner enters."""
    from backend.trade_service import _cfg_local
    from backend.bakeoff_profiles import MODEL_A_PROFILE

    def fake_generate(self, *args, **kwargs):
        overlay = getattr(_cfg_local, "map", None) or {}
        is_a = all(overlay.get(k) == v for k, v in MODEL_A_PROFILE.items())
        return list(a_cards if is_a else b_cards)

    return [
        patch("backend.trade_service.TradeService.generate_trades",
              fake_generate),
        patch.object(bo, "gen_v2_cards", lambda svc, kw: list(c_cards)),
    ]


def _reordering_spy(name, calls):
    """A stand-in for a post-generation layer that REVERSES the deck. If any
    of them runs on a bake-off deck the served order changes visibly — which
    is precisely the silent failure §3.4 Channel 2 warns about."""
    def _spy(cards, *a, **kw):
        calls.append(name)
        return list(reversed(cards))
    return _spy


# ---------------------------------------------------------------------------
# Flag OFF — captured golden
# ---------------------------------------------------------------------------

def test_flag_off_is_byte_identical_to_the_captured_golden():
    golden = json.loads(GOLDEN.read_text())
    with patch.object(bo, "bakeoff_enabled", lambda: False):
        capture, _job, _eng = H.run_capture()

    assert _strip_new_columns(capture) == golden
    # …and every additive column is NULL on every row.
    for row in capture["impressions"]:
        for col in NEW_COLUMNS:
            assert row[col] is None, col


def test_flag_off_writes_no_bakeoff_run_row():
    with patch.object(bo, "bakeoff_enabled", lambda: False):
        _capture, _job, eng = H.run_capture()
    with eng.connect() as conn:
        assert conn.execute(select(bakeoff_runs_table)).fetchall() == []


# ---------------------------------------------------------------------------
# Phase 4 — dark validation
# ---------------------------------------------------------------------------

def test_dark_mode_serves_the_flag_off_deck():
    """All three arms generate; the user still sees exactly the flag-off
    deck, through the untouched presentation stack."""
    golden = json.loads(GOLDEN.read_text())
    with patch.object(bo, "bakeoff_enabled", lambda: False):
        pass
    capture, _job, _eng = H.run_capture(
        extra_patches=_bakeoff_patches(enabled=True, interleaved=False))
    assert capture["cards"] == golden["cards"]


def test_dark_mode_logs_three_arms_and_attributes_the_served_arm():
    capture, _job, eng = H.run_capture(
        extra_patches=_bakeoff_patches(enabled=True, interleaved=False))

    with eng.connect() as conn:
        runs = conn.execute(select(bakeoff_runs_table)).fetchall()
    assert len(runs) == 1
    run = runs[0]
    assert run.served_arm == "current"          # one arm served…
    arms = json.loads(run.arms_json)
    assert set(arms) == set(bo.ARMS)            # …three arms logged
    for arm in bo.ARMS:
        assert arms[arm]["gen_ms"] >= 0
        assert "empty" in arms[arm] and "forfeits" in arms[arm]
    assert json.loads(run.arm_order) and set(json.loads(run.arm_order)) == set(bo.ARMS)

    assert capture["impressions"], "dark mode still writes the F1 spine"
    for row in capture["impressions"]:
        assert row["model_arm"] == "current"
        assert row["arm_rank"] is not None
        assert row["policy_version"].endswith("/bo:current")


# ---------------------------------------------------------------------------
# Phase 5 — interleaved serving, §3.4 Channel 2
# ---------------------------------------------------------------------------

def test_interleaved_deck_is_the_team_draft_order():
    a = [_card(["qb1"], ["rb2"]), _card(["te1"], ["wr1"])]
    b = [_card(["rb1"], ["wr1"]), _card(["wr2"], ["rb2"])]
    c = [_card(["qb1"], ["rb3"])]
    order = ["current", "baseline", "gen_v2"]

    with patch.object(bo, "draft_order_for",
                      lambda parts, lid, wk=None: [p for p in order if p in parts]):
        capture, _job, eng = H.run_capture(
            extra_patches=_bakeoff_patches(enabled=True, interleaved=True)
            + _stub_arms(a, b, c))

    served = [(tuple(x["give"]), tuple(x["receive"])) for x in capture["cards"]]
    expected = [
        (("rb1",), ("wr1",)),      # current  rank 0
        (("qb1",), ("rb2",)),      # baseline rank 0
        (("qb1",), ("rb3",)),      # gen_v2   rank 0
        (("wr2",), ("rb2",)),      # current  rank 1
        (("te1",), ("wr1",)),      # baseline rank 1  (gen_v2 forfeits)
    ]
    # `give`/`receive` in the payload are player dicts, not ids — compare on
    # the impression rows' arm attribution instead, which is the real
    # contract, plus the deck length.
    assert len(capture["cards"]) == len(expected)
    arms = [(r["model_arm"], r["arm_rank"]) for r in capture["impressions"]]
    assert arms == [("current", 0), ("baseline", 0), ("gen_v2", 0),
                    ("current", 1), ("baseline", 1)]
    assert served  # payload still renders


def test_post_generation_rerankers_cannot_touch_the_merged_deck():
    """Every reordering layer is turned ON and replaced with a spy that
    REVERSES the deck. On a bake-off deck none of them may run: the served
    arm sequence must still be the interleaver's."""
    a = [_card(["qb1"], ["rb2"]), _card(["te1"], ["wr1"])]
    b = [_card(["rb1"], ["wr1"]), _card(["wr2"], ["rb2"])]
    c = [_card(["qb1"], ["rb3"])]
    calls: list[str] = []

    layers = [
        patch.object(server, "_deck_fatigue_enabled", lambda: True),
        patch.object(server, "_deck_taste_enabled", lambda: True),
        patch.object(server, "_deck_value_model_enabled", lambda: True),
        patch.object(server, "_deck_exploration_enabled", lambda: True),
        patch.object(server, "_deck_first_session_enabled", lambda: True),
        patch.object(server, "_deck_thompson_v2_enabled", lambda: True),
        patch.object(server, "_order_deck", _reordering_spy("order_deck", calls)),
        patch.object(server, "_apply_first_session_shaping",
                     _reordering_spy("first_session", calls)),
        patch.object(server, "_apply_exploration_slot",
                     lambda cards, pool, **kw: (list(reversed(cards)), None,
                                                {"deck_changed": True})),
        patch.object(server, "_deck_fatigue_multipliers",
                     lambda cards, **kw: calls.append("fatigue") or {}),
        patch.object(server, "_deck_value_scores",
                     lambda cards, **kw: calls.append("value_model") or {}),
        patch.object(server._taste_service, "taste_multipliers",
                     lambda cards, **kw: calls.append("taste") or {}),
        # Suppression only REMOVES cards, so it stays live by design — assert
        # it is still reached, and that it does not reorder.
        patch.object(server, "_apply_deck_suppression",
                     lambda cards, **kw: (calls.append("suppression")
                                          or (list(cards), None, set()))),
    ]
    order = ["baseline", "current", "gen_v2"]
    with patch.object(bo, "draft_order_for",
                      lambda parts, lid, wk=None: [p for p in order if p in parts]):
        capture, _job, _eng = H.run_capture(
            extra_patches=_bakeoff_patches(enabled=True, interleaved=True)
            + _stub_arms(a, b, c) + layers)

    arms = [(r["model_arm"], r["arm_rank"]) for r in capture["impressions"]]
    assert arms == [("baseline", 0), ("current", 0), ("gen_v2", 0),
                    ("baseline", 1), ("current", 1)]
    assert "suppression" in calls, "decline suppression must stay live"
    for reorderer in ("order_deck", "first_session", "fatigue", "taste",
                      "value_model"):
        assert reorderer not in calls, f"{reorderer} ran on a bake-off deck"


def test_rerankers_do_run_when_the_bakeoff_is_off():
    """The mirror image: the same spies, no bake-off — the layers must still
    be reached, so the bypass above is a bake-off property and not a
    broken harness."""
    calls: list[str] = []
    layers = [
        patch.object(server, "_deck_fatigue_enabled", lambda: True),
        patch.object(server, "_order_deck", _reordering_spy("order_deck", calls)),
        patch.object(server, "_deck_fatigue_multipliers",
                     lambda cards, **kw: calls.append("fatigue") or {}),
    ]
    with patch.object(bo, "bakeoff_enabled", lambda: False):
        H.run_capture(extra_patches=layers)
    assert "order_deck" in calls and "fatigue" in calls


def test_likes_you_injection_does_not_reorder_the_interleave():
    """The injector returns the deck RE-SORTED by composite_score. On a
    bake-off deck the injected card is pinned to the top and every arm card
    returns to its interleaved index."""
    a = [_card(["qb1"], ["rb2"], composite=0.1)]
    b = [_card(["rb1"], ["wr1"], composite=0.2)]
    c = []
    injected = _card(["te1"], ["rb3"], composite=99.0)
    injected.likes_you = True

    def fake_inject(cards, **kwargs):
        # What the real injector does: prepend + re-sort by composite desc.
        return sorted(list(cards) + [injected],
                      key=lambda x: x.composite_score, reverse=True)

    order = ["baseline", "current", "gen_v2"]
    with patch.object(bo, "draft_order_for",
                      lambda parts, lid, wk=None: [p for p in order if p in parts]):
        capture, _job, _eng = H.run_capture(
            extra_patches=_bakeoff_patches(enabled=True, interleaved=True)
            + _stub_arms(a, b, c)
            + [patch.object(server, "_inject_likes_you_cards", fake_inject)])

    arms = [(r["model_arm"], r["arm_rank"]) for r in capture["impressions"]]
    # Injection first (no arm produced it ⇒ NULL attribution), then the
    # interleaved order — NOT composite order, which would have put
    # `current` (0.2) ahead of `baseline` (0.1).
    assert arms == [(None, None), ("baseline", 0), ("current", 0)]
    # Regression guard: save_deck_impressions inserts with executemany, which
    # compiles from the FIRST row's keys — an unattributed leading card must
    # not strip attribution (or the arm-stamped policy_version) off the rest.
    pv = [r["policy_version"] for r in capture["impressions"]]
    assert pv[0] is None
    assert pv[1].endswith("/bo:baseline") and pv[2].endswith("/bo:current")


def test_interleaved_run_records_agreement_and_forfeits():
    dup_give, dup_recv = ["qb1"], ["rb2"]
    a = [_card(dup_give, dup_recv), _card(["te1"], ["wr1"])]
    b = [_card(dup_give, dup_recv), _card(["wr2"], ["rb3"])]
    c = []
    order = ["baseline", "current", "gen_v2"]

    with patch.object(bo, "draft_order_for",
                      lambda parts, lid, wk=None: [p for p in order if p in parts]):
        capture, _job, eng = H.run_capture(
            extra_patches=_bakeoff_patches(enabled=True, interleaved=True)
            + _stub_arms(a, b, c))

    # The shared trade is served ONCE, credited to the first picker, with the
    # agreement recorded on the impression.
    first = capture["impressions"][0]
    assert first["model_arm"] == "baseline"
    assert json.loads(first["features_json"])["also_proposed_by"] == ["current"]

    with eng.connect() as conn:
        run = conn.execute(select(bakeoff_runs_table)).fetchone()
    assert run.served_arm is None                       # interleaved
    assert json.loads(run.agreement_json) == {"baseline+current": 1}
    arms = json.loads(run.arms_json)
    assert arms["gen_v2"]["empty"] is True
    assert arms["gen_v2"]["forfeits"] >= 1              # recorded, not silent
    assert arms["gen_v2"]["cards"] == 0


def test_arm_c_runs_while_trade_gen_v2_stays_off():
    """`trade_gen.v2` gates the NORMAL serving path; the bake-off invokes the
    module regardless. Assert both halves in one run."""
    seen = {}

    def fake_gen_v2(svc, kw):
        from backend.feature_flags import is_enabled
        seen["flag"] = is_enabled("trade_gen.v2")
        seen["called"] = True
        return [_card(["qb1"], ["rb3"])]

    with patch.object(bo, "gen_v2_cards", fake_gen_v2):
        H.run_capture(extra_patches=_bakeoff_patches(enabled=True,
                                                     interleaved=True))
    assert seen.get("called") is True
    assert seen.get("flag") is False, \
        "the bake-off must not require (or flip) trade_gen.v2"


# ---------------------------------------------------------------------------
# §3.4 Channel 1 — swipe Elo freeze, structural guard
# ---------------------------------------------------------------------------

def test_every_swipe_k_multiplier_runs_through_the_elo_freeze():
    """A new swipe path that computes a fit-congruence K and forgets the
    freeze would silently let arms teach the shared board — with no visible
    symptom. Cheap structural invariant instead."""
    src = Path(server.__file__).read_text()
    assignments = [m.start() for m in
                   re.finditer(r"fit_mult = _trade_service_mod\.fit_congruence_mult",
                               src)]
    assert assignments, "swipe K sites moved — update this guard"
    # Each site's window runs to the NEXT site (or EOF), so a freeze belonging
    # to a different call site can never satisfy this one.
    bounds = assignments[1:] + [len(src)]
    for pos, end in zip(assignments, bounds):
        window = src[pos:end]
        assert "_bakeoff.elo_freeze_mult(fit_mult)" in window, (
            "a fit-congruence K site is missing the bake-off Elo freeze "
            f"(near offset {pos})")
        # …and it must land BEFORE the K is consumed.
        used = window.find("fit_mult   =")
        froze = window.find("_bakeoff.elo_freeze_mult(fit_mult)")
        assert used == -1 or froze < used, (
            f"the freeze runs after fit_mult is consumed (near offset {pos})")


# ---------------------------------------------------------------------------
# fairness_threshold capture (docs/reviews/2026-08-18-trade-logic-archaeology.md)
# ---------------------------------------------------------------------------

def test_served_cards_record_the_threshold_they_were_generated_under():
    """The job is run at fairness_threshold=0.75, but a DIVERGENCE card only
    ever had to clear min(0.75, fairness_floor_divergence). Recording the
    request would misdescribe every such card, which is why the effective
    value is resolved per card and per arm."""
    a = [_card(["qb1"], ["rb2"])]                       # basis defaults to divergence
    b = [_card(["rb1"], ["wr1"])]
    b[0].basis = "consensus"                            # consensus keeps the full bar
    c = [_card(["te1"], ["rb3"])]
    order = ["baseline", "current", "gen_v2"]

    with patch.object(bo, "draft_order_for",
                      lambda parts, lid, wk=None: [p for p in order if p in parts]):
        capture, _job, eng = H.run_capture(
            extra_patches=_bakeoff_patches(enabled=True, interleaved=True)
            + _stub_arms(a, b, c))

    by_arm = {r["model_arm"]: r["fairness_threshold"]
              for r in capture["impressions"]}
    assert by_arm["baseline"] == 0.55, "divergence card rides the floor"
    assert by_arm["current"] == 0.75, "consensus card keeps the client's bar"
    assert by_arm["gen_v2"] is None, "trade_gen_v2 takes no fairness_threshold"


def test_bakeoff_run_snapshots_the_config_each_arm_used():
    """`model_config` has no `updated_at`, so a knob's change date is
    unknowable after the fact. The run row carries the configuration instead."""
    from backend.bakeoff_profiles import MODEL_A_PROFILE

    _capture, _job, eng = H.run_capture(
        extra_patches=_bakeoff_patches(enabled=True, interleaved=True))
    with eng.connect() as conn:
        run = conn.execute(select(bakeoff_runs_table)).fetchone()

    arms = json.loads(run.arms_json)
    assert arms["baseline"]["fairness_threshold"] == 0.75
    assert arms["current"]["fairness_threshold"] == 0.75
    assert arms["gen_v2"]["fairness_threshold"] is None

    cfg = json.loads(run.config_json)
    assert cfg["base"]["fairness_floor_divergence"] == 0.55
    assert cfg["arm_delta"]["gen_v2"] == {}
    a_delta = cfg["arm_delta"]["baseline"]
    assert a_delta and set(a_delta) <= set(MODEL_A_PROFILE)


def test_threshold_clean_query_answers_itself_from_the_table():
    """PLAN.md §6 asks per-arm comparisons to be threshold-clean. With the
    column in place that is one GROUP BY, not archaeology — this test IS the
    documented query."""
    from sqlalchemy import func
    from backend.database import deck_impressions_table as di

    _capture, _job, eng = H.run_capture(
        extra_patches=_bakeoff_patches(enabled=True, interleaved=True))
    with eng.connect() as conn:
        rows = conn.execute(
            select(di.c.model_arm,
                   func.count(func.distinct(di.c.fairness_threshold)))
            .where(di.c.model_arm.isnot(None))
            .group_by(di.c.model_arm)
        ).fetchall()
    assert rows, "no attributed impressions to check"
    for arm, distinct_thresholds in rows:
        assert distinct_thresholds <= 1, (
            f"arm {arm} mixes fairness thresholds within one deck")


# ---------------------------------------------------------------------------
# Deck composition through the real serving path
# (operator decision 2026-08-18; scope-composition.md)
# ---------------------------------------------------------------------------

def _lane_card(give, recv, *, basis, lane, target=H.OPP, composite=1.0):
    c = _card(give, recv, target=target, composite=composite)
    c.basis = basis
    c.lane = lane
    return c


def test_served_deck_is_composed_of_groups_and_every_row_carries_its_group():
    """Groups 1 and 2 come from arm `current` at the two bases; group 3 is arm
    `gen_v2`. The impression rows must carry the group, the rank inside it and
    the lane slot — without them the analysis cannot separate "this group's
    quota" from "this arm" or from deck position."""
    cur = [_lane_card(["qb1"], ["rb2"], basis="divergence", lane="value"),
           _lane_card(["rb1"], ["wr1"], basis="divergence", lane="window"),
           _lane_card(["wr2"], ["rb3"], basis="consensus",  lane="value"),
           _lane_card(["te1"], ["wr3"], basis="consensus",  lane="window")]
    v2 = [_lane_card(["qb1"], ["wr3"], basis="divergence", lane="value"),
          _lane_card(["rb1"], ["rb3"], basis="divergence", lane="window")]
    order = ["current_divergence", "current_consensus", "gen_v2"]

    with patch.object(bo, "draft_order_for",
                      lambda parts, lid, wk=None: [p for p in order if p in parts]), \
            patch.object(bo, "outlook_leads_for", lambda *a, **k: False):
        capture, _job, eng = H.run_capture(
            extra_patches=_bakeoff_patches(enabled=True, interleaved=True,
                                           composed=True)
            + _stub_arms([], cur, v2))

    rows = capture["impressions"]
    assert [(r["model_arm"], r["group_key"], r["group_rank"], r["lane_slot"])
            for r in rows] == [
        ("current", "current_divergence", 0, "value"),
        ("current", "current_consensus",  0, "value"),
        ("gen_v2",  "gen_v2",             0, "value"),
        ("current", "current_divergence", 1, "outlook"),
        ("current", "current_consensus",  1, "outlook"),
        ("gen_v2",  "gen_v2",             1, "outlook"),
    ]
    # No group ever holds two consecutive deck slots.
    seq = [r["group_key"] for r in rows]
    assert all(a != b for a, b in zip(seq, seq[1:]))
    # basis + lane are already on the F1 spine — no duplicate taxonomy needed.
    feats = [json.loads(r["features_json"]) for r in rows]
    assert [f["basis"] for f in feats] == [
        "divergence", "consensus", "divergence"] * 2
    assert [f["lane"] for f in feats] == ["value"] * 3 + ["window"] * 3


def test_arm_baseline_never_reaches_a_served_deck():
    """Arm A is out of the roster: it must not generate, must not be drafted,
    and must not appear on any impression row.

    D-095: the engine now runs TWICE on the live default roster — once as
    `current`, once as `challenger` under `model_challenger()`. That is the
    fan-out cost the challenger's kill knob exists to give back, and it is
    asserted here rather than left implicit."""
    calls = []

    def fake_generate(self, *a, **kw):
        calls.append("engine")
        return [_lane_card(["qb1"], ["rb2"], basis="divergence", lane="value")]

    with patch("backend.trade_service.TradeService.generate_trades",
               fake_generate), \
            patch.object(bo, "gen_v2_cards", lambda svc, kw: []):
        capture, _job, eng = H.run_capture(
            extra_patches=_bakeoff_patches(enabled=True, interleaved=True,
                                           composed=True))

    assert len(calls) == 2, "the engine runs for `current` and `challenger`"
    assert all(r["model_arm"] != "baseline" for r in capture["impressions"])
    with eng.connect() as conn:
        run = conn.execute(select(bakeoff_runs_table)).fetchone()
    assert set(json.loads(run.arms_json)) == {"current", "challenger",
                                              "gen_v2"}


def test_the_challenger_generates_and_logs_but_is_never_served():
    """PRD G7 / §9.1 — the dark-mode contract, end to end. With the flag on
    and `bakeoff_serve_interleaved` = 0, arm D must appear in `arms_json` and
    `groups_json` while every served impression still reads `current`."""
    def fake_generate(self, *a, **kw):
        return [_lane_card(["qb1"], ["rb2"], basis="divergence", lane="value")]

    with patch("backend.trade_service.TradeService.generate_trades",
               fake_generate), \
            patch.object(bo, "gen_v2_cards", lambda svc, kw: []):
        capture, _job, eng = H.run_capture(
            extra_patches=_bakeoff_patches(enabled=True, interleaved=False,
                                           composed=True))

    assert capture["impressions"]
    assert all(r["model_arm"] == "current" for r in capture["impressions"]), \
        "a challenger card reached a user — bakeoff_serve_interleaved is 0"
    with eng.connect() as conn:
        run = conn.execute(select(bakeoff_runs_table)).fetchone()
    assert run.served_arm == "current"
    assert "challenger" in json.loads(run.arms_json)
    assert {"challenger_divergence", "challenger_consensus"} \
        <= set(json.loads(run.groups_json))
    # …and the config snapshot proves the overlay was actually entered.
    from backend.bakeoff_profiles import MODEL_CHALLENGER_PROFILE
    delta = json.loads(run.config_json)["arm_delta"]["challenger"]
    assert delta and set(delta) <= set(MODEL_CHALLENGER_PROFILE)
    for key, val in delta.items():
        assert val == MODEL_CHALLENGER_PROFILE[key], key


def test_run_row_records_the_per_group_under_fill_through_the_real_path():
    """Arm `gen_v2` produces only value-lane cards here — the case PLAN.md
    §3.2 warns about. The outlook shortfall must land in groups_json, not be
    quietly filled from the value lane."""
    cur = [_lane_card(["qb1"], ["rb2"], basis="divergence", lane="value"),
           _lane_card(["rb1"], ["wr1"], basis="divergence", lane="window")]
    v2 = [_lane_card(["wr2"], ["rb3"], basis="divergence", lane="value"),
          _lane_card(["te1"], ["wr3"], basis="divergence", lane="value")]

    capture, _job, eng = H.run_capture(
        extra_patches=_bakeoff_patches(enabled=True, interleaved=True,
                                       composed=True)
        + _stub_arms([], cur, v2))

    with eng.connect() as conn:
        run = conn.execute(select(bakeoff_runs_table)).fetchone()
    groups = json.loads(run.groups_json)
    assert groups["gen_v2"]["filled"] == {"value": 2, "outlook": 0, "fill": 0}
    assert groups["gen_v2"]["short"] == {"value": 3, "outlook": 5}
    assert groups["gen_v2"]["pool"] == {"value": 2, "window": 0, "(none)": 0}
    # …and nothing was substituted into an outlook slot.
    assert all(r["lane_slot"] != "fill" for r in capture["impressions"])
    # The consensus group had no supply at all — recorded, not an error.
    assert groups["current_consensus"]["composed"] == 0
    assert groups["current_consensus"]["short"] == {"value": 5, "outlook": 5}


def test_composition_is_bypassed_for_a_dark_mode_deck():
    """Dark validation still serves arm B's own list through the untouched
    presentation stack, so no group produced the served cards and the group
    columns are honestly NULL."""
    capture, _job, eng = H.run_capture(
        extra_patches=_bakeoff_patches(enabled=True, interleaved=False,
                                       composed=True))
    assert capture["impressions"]
    for row in capture["impressions"]:
        assert row["model_arm"] == "current"
        assert row["group_key"] is None and row["group_rank"] is None
        assert row["lane_slot"] is None
    # …but the composition IS still computed and its accounting written:
    # measuring the per-(group, lane) under-fill before Phase 5 lights
    # interleaved serving is exactly what dark validation is for.
    with eng.connect() as conn:
        run = conn.execute(select(bakeoff_runs_table)).fetchone()
    groups = json.loads(run.groups_json)
    assert set(groups) == {"current_divergence", "current_consensus",
                           "challenger_divergence", "challenger_consensus",
                           "gen_v2"}
    for summary in groups.values():
        assert set(summary["short"]) == {"value", "outlook"}


# ---------------------------------------------------------------------------
# trade_intent capture — the gate that APPLIED, not the one requested
# ---------------------------------------------------------------------------

def test_served_cards_record_the_effective_trade_intent():
    capture, _job, eng = H.run_capture(
        trade_intent="tier_up",
        extra_patches=_bakeoff_patches(enabled=True, interleaved=True,
                                       composed=True))
    assert capture["impressions"]
    for row in capture["impressions"]:
        assert row["trade_intent"] == "tier_up"
    with eng.connect() as conn:
        run = conn.execute(select(bakeoff_runs_table)).fetchone()
    arms = json.loads(run.arms_json)
    for arm in arms:
        assert arms[arm]["trade_intent"] == "tier_up"


def test_intent_records_null_when_the_flag_did_not_actually_apply_it():
    """The requested/effective divergence, and the reason this is recorded per
    row rather than assumed from the request: `_generate_trades_impl` resolves
    the intent to None whenever `trades.intent_modes` is off, so a client that
    sent `tier_up` was served an unfiltered deck."""
    with patch.object(bo, "is_enabled",
                      lambda key: False if key == "trades.intent_modes" else True):
        assert bo.effective_trade_intent("tier_up") is None
    # …and a value outside the three modes is not an intent, however it arrives.
    assert bo.effective_trade_intent("bogus") is None
    assert bo.effective_trade_intent(None) is None
    assert bo.effective_trade_intent("tier_up") == "tier_up"

    capture, _job, _eng = H.run_capture(
        extra_patches=_bakeoff_patches(enabled=True, interleaved=True,
                                       composed=True))
    assert capture["impressions"]
    assert all(r["trade_intent"] is None for r in capture["impressions"]), \
        "an unfiltered deck must record NULL, not a requested-but-unused mode"


def test_arm_c_is_filtered_by_the_same_intent_lens_as_the_engine_arms():
    """`_generate_trades_impl`'s v2 branch applies `_filter_by_trade_intent` to
    gen-v2's output; calling the module directly skipped it, which would have
    given groups 1/2 a filtered brief and group 3 an unfiltered one."""
    seen = {}
    real = bo.gen_v2_cards

    def spy(svc, kw):
        seen["intent"] = kw.get("trade_intent")
        return real(svc, kw)

    with patch.object(bo, "gen_v2_cards", spy):
        H.run_capture(trade_intent="consolidate",
                      extra_patches=_bakeoff_patches(enabled=True,
                                                     interleaved=True,
                                                     composed=True))
    assert seen.get("intent") == "consolidate", \
        "arm C must receive the job's intent, not a stripped kwarg set"


def test_arm_c_cards_carry_a_lane_so_group_3_can_fill_an_outlook_quota():
    """`classify_lane` runs after the v2 branch returns, so no gen-v2 card has
    ever carried a lane. Without stamping it here group 3's outlook quota
    would under-fill 100% of the time for a plumbing reason and read as "arm C
    cannot produce outlook ideas" — a false finding."""
    captured = {}
    real = bo.gen_v2_cards

    def spy(svc, kw):
        cards = real(svc, kw)
        captured["cards"] = cards
        return cards

    with patch.object(bo, "gen_v2_cards", spy):
        H.run_capture(extra_patches=_bakeoff_patches(
            enabled=True, interleaved=True, composed=True))

    cards = captured.get("cards")
    assert cards is not None, "arm C did not run"
    # The harness's user has no declared outlook, so the honest label is None
    # for every card — but the ATTRIBUTE must exist and be set deliberately,
    # never left absent.
    for c in cards:
        assert hasattr(c, "lane") and hasattr(c, "lane_shift")


def test_arm_c_lane_labels_match_the_engine_labeller_exactly():
    """Same labeller, same inputs, same answer — that parity is what makes the
    value/outlook comparison a comparison of generators rather than of which
    post-generation steps each arm happened to receive."""
    from backend.trade_service import classify_lane, elo_to_value

    players = {p.id: p for p in H._players()}
    svc_players = players
    seed = dict(H.SEED)
    vs = lambda pid: elo_to_value(seed.get(pid, 1500.0))

    made = []

    def fake_gen(**kw):
        return [_lane_card(["qb1"], ["rb2"], basis="divergence", lane=None)]

    with patch("backend.trade_gen_v2.generate_league_suggestions",
               lambda **kw: (fake_gen(), {})):
        from backend.trade_service import League, LeagueMember, TradeService
        svc = TradeService(players=svc_players)
        svc.add_league(League(
            league_id="L", name="t", platform="demo",
            members=[LeagueMember(user_id="opp", username="opp",
                                  roster=["rb2"], elo_ratings={})]))
        out = bo.gen_v2_cards(svc, {
            "league_id": "L", "user_id": "me", "user_elo": {},
            "user_roster": ["qb1"], "seed_elo": seed, "outlook": "contender",
            "scoring_format": "1qb_ppr",
        })
    assert len(out) == 1
    expected = classify_lane(["qb1"], ["rb2"], svc_players, "contender", vs)
    assert out[0].lane == expected


# ---------------------------------------------------------------------------
# "Was this comparison clean?" — the documented query, executed
# ---------------------------------------------------------------------------

def test_comparison_clean_query_answers_itself_from_the_table():
    """PLAN.md §6 asks per-arm comparisons to be threshold-clean; the trade
    settings staying visible for the bake-off means they must be INTENT-clean
    too. Both are one GROUP BY now, and this test IS the documented query
    (docs/data-dictionary.md §bakeoff_runs) so it cannot rot into
    documentation-only."""
    from sqlalchemy import func
    from backend.database import deck_impressions_table as di

    _capture, _job, eng = H.run_capture(
        trade_intent="tier_up",
        extra_patches=_bakeoff_patches(enabled=True, interleaved=True,
                                       composed=True))
    with eng.connect() as conn:
        rows = conn.execute(
            select(di.c.model_arm,
                   di.c.group_key,
                   func.count(func.distinct(di.c.fairness_threshold)),
                   func.count(func.distinct(di.c.trade_intent)),
                   func.count())
            .where(di.c.model_arm.isnot(None))
            .group_by(di.c.model_arm, di.c.group_key)
        ).fetchall()
    assert rows, "no attributed impressions to check"
    for arm, group_key, thresholds, intents, n in rows:
        assert thresholds <= 1, f"{arm}/{group_key} mixes fairness thresholds"
        assert intents <= 1, f"{arm}/{group_key} mixes trade intents"
        assert n > 0


# ---------------------------------------------------------------------------
# D-087 — arm-C forfeit accounting + per-stage diagnostics on arms_json
# ---------------------------------------------------------------------------

def test_forfeits_are_summed_over_an_arms_groups_not_looked_up_by_arm_name():
    """Once composition is on the draft's participants are GROUPS, and arm
    `current` owns two of them (`current_divergence` + `current_consensus`).
    The old `forfeits[arm]` lookup therefore missed on every engine arm and
    reported a flat 0 — which is what made arm C's real, non-zero forfeit
    count read as a property of arm C. Assert the sum, and assert that an arm
    whose groups DID forfeit can no longer record zero."""
    from backend.bakeoff_runner import BakeoffRun, DraftResult, ArmResult

    class _G:
        def __init__(self, arm):
            self.group = type("g", (), {"arm": arm})()

    run = BakeoffRun(
        run_id="r", arm_order=[], arms={},
        draft=DraftResult(forfeits={"current_divergence": 3,
                                    "current_consensus": 2,
                                    "gen_v2": 9}),
        served_arm=None, total_ms=0,
        groups={"current_divergence": _G("current"),
                "current_consensus": _G("current"),
                "gen_v2": _G("gen_v2")},
    )
    assert run.forfeits_for_arm("current") == 5      # was 0 before the fix
    assert run.forfeits_for_arm("gen_v2") == 9
    assert run.forfeits_for_arm("baseline") == 0     # not rostered

    # bakeoff_group_size = 0 — participants really are arms; direct lookup.
    plain = BakeoffRun(run_id="r", arm_order=[], arms={},
                       draft=DraftResult(forfeits={"current": 4, "gen_v2": 1}),
                       served_arm=None, total_ms=0, groups={})
    assert plain.forfeits_for_arm("current") == 4
    assert plain.forfeits_for_arm("gen_v2") == 1


def test_arm_c_diagnostics_reach_arms_json_and_name_the_starving_stage():
    """The point of the whole change: `cards: 0` on arm C must arrive with
    the stage that produced it. Arm C here is starved exactly as production
    league 62846 is — no boarded opponent — so the recorded diagnostics must
    say `no_boarded_opponents` and NOT blame a gate."""
    starved = {
        "S0_boarded_opponents": 0, "S0_unranked_opponents": 11,
        "S1_no_board_overlap": 0, "S1_no_centerpiece": 0,
        "S2_considered": 0, "S3c_dual_board_ir": 0,
        "S4_survivors": 0, "S6_emitted": 0,
        "starvation_reason": "no_boarded_opponents",
    }

    def fake_gen_v2(svc, kw):
        bo._gen2_diag.value = dict(starved)
        return []

    with patch.object(bo, "gen_v2_cards", fake_gen_v2):
        _capture, _job, eng = H.run_capture(
            extra_patches=_bakeoff_patches(enabled=True, interleaved=True))

    with eng.connect() as conn:
        run = conn.execute(select(bakeoff_runs_table)).fetchone()
    diag = json.loads(run.arms_json)["gen_v2"]["diagnostics"]
    assert diag["starvation_reason"] == "no_boarded_opponents"
    assert diag["S0_boarded_opponents"] == 0
    assert diag["S2_considered"] == 0, \
        "a starved arm must not be recorded as having been gated"


def test_gen_v2_diagnostics_are_drained_so_they_cannot_leak_between_runs():
    """Read-once semantics: a second run whose arm C reported nothing must
    not inherit the first run's counters."""
    bo._gen2_diag.value = {"S2_considered": 42}
    assert bo.last_gen_v2_diagnostics() == {"S2_considered": 42}
    assert bo.last_gen_v2_diagnostics() == {}


# ---------------------------------------------------------------------------
# PR-S — serving-readiness guards for the W1 re-light
# (fit-challenger PLAN-v2 §2 S1b + §5 W1; HLD finding F-6; LLD §6.2;
#  scope block docs/plans/fit-challenger/scope-serving.md)
#
# The 2026-08-18 shrink, inverted into a regression test. What happened: with
# interleaved serving lit under COMPOSITION, arm C zero-carded (`gen_v2:
# cards=0, forfeits=9` against `current: cards=40`) and the leave-short lane
# quotas turned that into a 10-card deck from a 40-card pool — see the
# `serve_interleaved()` docstring in bakeoff_runner.py. The W1 posture pins
# `bakeoff_group_size = 0` precisely so the live draft path is the plain
# per-arm `team_draft` fallback (HLD F-6: bakeoff_runner.py:1424-1427), where
# a zero-card arm forfeits its rotation slots and the surviving arms backfill
# the deck to `bakeoff_deck_limit`. These tests pin BOTH halves: the fallback
# fills (the guard), and composition today does not (the reason W1 is 0).
# ---------------------------------------------------------------------------

#: W1 fixture, inputs pinned as literals: the shape of the 08-18 incident.
#: One arm zero-cards; the other two hold 40 distinct trades — comfortably
#: more than `bakeoff_deck_limit` = 30 combined.
_W1_DECK_LIMIT = 30
_W1_CUR_CARDS  = 20
_W1_CHAL_CARDS = 20


def _w1_fixture():
    cur  = [_card([f"cur_g{i}"],  [f"cur_r{i}"])  for i in range(_W1_CUR_CARDS)]
    chal = [_card([f"chal_g{i}"], [f"chal_r{i}"]) for i in range(_W1_CHAL_CARDS)]
    v2: list = []                                  # the zero-card arm
    return cur, chal, v2


def _w1_run(*, group_size: float, interleave: bool = True):
    """`run_bakeoff` directly, stub generators (the challenger-test idiom),
    on the W1 roster (current + challenger + gen_v2) at the W1 knob values:
    `bakeoff_deck_limit = 30`, `bakeoff_group_size` as given. The same
    `generate` callable serves arms B and D; the thread-local overlay the
    runner enters is what distinguishes them, exactly as in production."""
    from backend.bakeoff_profiles import MODEL_CHALLENGER_PROFILE
    from backend.trade_service import _cfg_local

    cur, chal, v2 = _w1_fixture()

    def generate(**ov):
        overlay = getattr(_cfg_local, "map", None) or {}
        is_chal = bool(MODEL_CHALLENGER_PROFILE) and all(
            overlay.get(k) == v for k, v in MODEL_CHALLENGER_PROFILE.items())
        return list(chal if is_chal else cur)

    knobs = {"bakeoff_deck_limit": float(_W1_DECK_LIMIT),
             "bakeoff_group_size": float(group_size)}
    with patch.object(bo, "_cfg", lambda k, d: float(knobs.get(k, d))):
        return bo.run_bakeoff(
            generate=generate, gen_v2=lambda **ov: list(v2),
            league_id="league_w1", iso_week="2026-W34",
            interleave=interleave,
            roster=(bo.ARM_CURRENT, bo.ARM_CHALLENGER, bo.ARM_GEN_V2))


def test_zero_card_arm_deck_still_fills():
    """S1b — the regression guard for the W1 re-light. Under
    `bakeoff_group_size = 0` (the W1 posture; HLD F-6 says this makes the
    `team_draft` fallback the live path for the whole program), an arm that
    produces ZERO cards must cost the deck nothing: it forfeits its rotation
    slots — counted, on the record — and the surviving arms fill the deck all
    the way to `bakeoff_deck_limit`."""
    run = _w1_run(group_size=0)

    # F-6: this IS the team_draft fallback, not compose_deck.
    assert run.groups == {}, "group_size=0 must kill composition entirely"

    # The deck fills to the limit despite the zero-card arm.
    assert len(run.draft.deck) == _W1_DECK_LIMIT
    assert [id(c) for c in run.served_deck()] == \
        [id(c) for c in run.draft.deck], "interleaved serve = the draft deck"

    # The empty arm is DATA, never silence: recorded empty, forfeits counted.
    assert run.arms["gen_v2"].cards == []
    assert run.draft.forfeits["gen_v2"] > 0
    row = run.run_row(job_id="j", user_id="u", league_id="league_w1")
    arms = json.loads(row["arms_json"])
    assert arms["gen_v2"]["empty"] is True
    assert arms["gen_v2"]["cards"] == 0
    assert arms["gen_v2"]["forfeits"] > 0
    assert row["deck_size"] == _W1_DECK_LIMIT

    # Every served card came from a surviving arm.
    credited = {run.draft.attribution[id(c)][0] for c in run.draft.deck}
    assert credited == {bo.ARM_CURRENT, bo.ARM_CHALLENGER}


def test_zero_card_arm_composed_deck_shrinks_under_group_quotas():
    """The companion, same fixture, composition ON (`bakeoff_group_size` at
    its live default 10) — documenting WHY W1 pins it to 0.

    Under composition the per-group quota caps each group at `group_size`
    cards, and a group whose (arm, basis) pool is empty composes zero. Here
    the two engine arms' cards are all divergence-basis, so both consensus
    groups compose 0, the gen_v2 group composes 0, and the deck tops out at
    20 of its 30 slots — the 08-18 shrink in miniature (the operator's
    10-card deck from a 40-card arm-B pool). Not a bug in composition: the
    under-fill is recorded per group, by design (D-078). But it is the
    behavior the W1 screen round must NOT serve, which is what makes
    `group_size = 0` a load-bearing W1 knob value rather than a stylistic
    one. If this test ever starts filling to 30, composition's supply
    behavior changed and the W1 posture should be re-decided, not silently
    kept."""
    run = _w1_run(group_size=10)

    assert run.groups, "group_size=10 must compose groups"
    by_key = {k: gr.summary() for k, gr in run.groups.items()}
    assert by_key["current_divergence"]["composed"] == 10      # capped at size
    assert by_key["challenger_divergence"]["composed"] == 10   # capped at size
    assert by_key["current_consensus"]["composed"] == 0        # empty basis
    assert by_key["challenger_consensus"]["composed"] == 0     # empty basis
    assert by_key["gen_v2"]["composed"] == 0                   # zero-card arm

    # 20 composed cards < deck_limit 30: the same inputs that fill the
    # team-draft deck leave a third of the composed deck empty.
    assert len(run.draft.deck) == 20
    assert len(run.draft.deck) < _W1_DECK_LIMIT

    # …and the shrink is on the record, not silent (D-078's contract).
    assert by_key["current_consensus"]["short"] == {"value": 5, "outlook": 5}
    assert by_key["gen_v2"]["short"] == {"value": 5, "outlook": 5}


def test_run_row_serving_mode_is_served_arm_not_a_bypass_marker():
    """PR-S finding, pinned: an interleaved run carries NO dedicated
    re-ranker-bypass marker. The only serving-mode state the run row records
    is `served_arm` — NULL means interleaved (the interleaver owned the
    order, so `bypass_rerankers()` was True for every card of this deck),
    `'current'` means dark (the normal presentation stack ran). The M4
    "re-ranker bypass assertion" tripwire therefore has to key on
    `served_arm IS NULL`, joined against `deck_impressions.model_arm`
    distribution — asserted here so that contract cannot drift silently. If
    a dedicated marker is ever wanted, it is new schema, not a new test."""
    interleaved = _w1_run(group_size=0, interleave=True)
    row = interleaved.run_row(job_id="j", user_id="u", league_id="league_w1")
    assert row["served_arm"] is None

    dark = _w1_run(group_size=0, interleave=False)
    dark_row = dark.run_row(job_id="j", user_id="u", league_id="league_w1")
    assert dark_row["served_arm"] == bo.DARK_SERVED_ARM

    # No bypass-named key exists anywhere on the row — the finding itself.
    assert not any("bypass" in k for k in row), \
        "a bypass marker appeared on the run row — update the M4 tripwire " \
        "and scope-serving.md, which document served_arm as the only signal"


# ---------------------------------------------------------------------------
# Fit challenger (PR-F3) — serve-bit, runner API, T2 uniform columns, C7b
# ---------------------------------------------------------------------------

def _fit_stub_lists():
    """Stub lists for the fit-arm runner tests. Fit's first card duplicates
    arm B's first trade so `_agreement` has something to record for a dark
    fit."""
    cur = [_card([f"cur_g{i}"], [f"cur_r{i}"]) for i in range(4)]
    fit = [_card(["cur_g0"], ["cur_r0"]),          # the agreement duplicate
           _card(["fit_g1"], ["fit_r1"]),
           _card(["fit_g2"], ["fit_r2"])]
    return cur, fit


def _fit_run(*, serve_fit: float, group_size: float, gen_fit="stub",
             fit_diag=None):
    """`run_bakeoff` with fit rostered explicitly (the W1/challenger idiom).
    `gen_fit="stub"` binds a 3-card stub that also writes the diagnostics
    thread-local, the way the real adapter does; None passes no callable."""
    cur, fit = _fit_stub_lists()

    def fit_cb(**_ov):
        bo._fit_diag_tl.value = dict(fit_diag or {"enumerated": 9,
                                                  "scored": 3})
        return list(fit)

    kwargs = {}
    if gen_fit == "stub":
        kwargs["gen_fit"] = fit_cb
    elif gen_fit is not None:
        kwargs["gen_fit"] = gen_fit
    knobs = {"bakeoff_group_size": float(group_size),
             "bakeoff_deck_limit": 0.0,
             "bakeoff_serve_fit": float(serve_fit)}
    with patch.object(bo, "_cfg", lambda k, d: float(knobs.get(k, d))):
        run = bo.run_bakeoff(
            generate=lambda **ov: list(cur),
            gen_v2=lambda **ov: [],
            league_id="league_fit_bit", iso_week="2026-W34",
            interleave=True,
            roster=(bo.ARM_CURRENT, bo.ARM_GEN_V2, bo.ARM_FIT),
            **kwargs)
    return run, cur, fit


@pytest.mark.parametrize("group_size", [0, 10])
def test_serve_fit_bit_excludes_from_draft(group_size):
    """F5b / HLD F-6 — the serve-bit acts on BOTH draft paths. The F-6 leak
    lives on the `group_size = 0` path (the W1 posture: composition killed,
    `team_draft` fallback live), so both are parametrized here."""
    run, cur, fit = _fit_run(serve_fit=0, group_size=group_size)

    # Dark fit: generated and recorded…
    assert run.arms["fit"].cards == fit
    row = run.run_row(job_id="j", user_id="u", league_id="league_fit_bit")
    arms = json.loads(row["arms_json"])
    assert arms["fit"]["cards"] == 3
    assert arms["fit"]["diagnostics"] == {"enumerated": 9, "scored": 3}
    # …but absent from the rotation and the deck on THIS path.
    assert not any(p == "fit" or p.startswith("fit")
                   for p in run.arm_order)
    fit_ids = {id(c) for c in fit}
    assert not any(id(c) in fit_ids for c in run.draft.deck)
    assert not any(id(c) in fit_ids for c in run.served_deck())
    # A dark fit still registers agreement (LLD §8 R-a): the served copy of
    # the duplicated trade cites arm fit.
    dup = next(c for c in run.draft.deck
               if c.give_player_ids == ["cur_g0"])
    assert "fit" in run.also_proposed_by(dup)

    # Bit = 1: fit drafts like any arm, on the same path.
    run_on, _cur, fit_on = _fit_run(serve_fit=1, group_size=group_size)
    fit_on_ids = {id(c) for c in fit_on}
    assert any(id(c) in fit_on_ids for c in run_on.draft.deck)
    assert any(p == "fit" for p in run_on.arm_order)


def test_run_bakeoff_gen_fit_optional():
    """HLD F-3 — `gen_fit` is an additive keyword. Absent + fit unrostered:
    unchanged behavior. Absent + fit rostered: a RECORDED arm error, never a
    job failure."""
    cur = [_card(["qb1"], ["rb2"])]
    knobs = {"bakeoff_group_size": 0.0, "bakeoff_deck_limit": 0.0}
    with patch.object(bo, "_cfg", lambda k, d: float(knobs.get(k, d))):
        run = bo.run_bakeoff(
            generate=lambda **ov: list(cur), gen_v2=lambda **ov: [],
            league_id="league_fit_opt", interleave=True,
            roster=(bo.ARM_CURRENT, bo.ARM_GEN_V2))
    assert "fit" not in run.arms
    assert len(run.draft.deck) == 1

    run2, _cur, fit = _fit_run(serve_fit=1, group_size=0, gen_fit=None)
    assert run2.arms["fit"].error is not None
    assert "gen_fit callable" in run2.arms["fit"].error
    assert run2.arms["fit"].cards == []
    assert len(run2.draft.deck) > 0              # the job completed


def test_fit_fairness_threshold_none():
    """HLD F-7 — fit joins gen_v2's None: its fairness is a score, not a
    gate, and `basis` on a fit card means data-availability."""
    run, _cur, _fit = _fit_run(serve_fit=0, group_size=0)
    assert run.arms["fit"].fairness_threshold is None


def test_arm_roster_reads_bakeoff_include_fit():
    """LLD §2.1 — `bakeoff_include_fit` (default 0) is the roster bit."""
    with patch.object(bo, "_cfg", lambda k, d: float(d)):
        assert bo.ARM_FIT not in bo.arm_roster()          # default: off
    with patch.object(bo, "_cfg",
                      lambda k, d: 1.0 if k == "bakeoff_include_fit"
                      else float(d)):
        roster = bo.arm_roster()
    assert roster == (bo.ARM_CURRENT, bo.ARM_CHALLENGER, bo.ARM_GEN_V2,
                      bo.ARM_FIT)


def test_draft_rank_only():
    """C7b — sabotage 2. Multiply ONE arm's every composite_score ×100: the
    drafted deck is IDENTICAL, because the draft is a cursor walk over list
    ORDER. A magnitude-reading draft would reorder and fail this assert —
    which is what licenses fit's 0–200 composite scale next to the engine
    arms' scale."""
    def _deck_ids(scale):
        b = [_card([f"bg{i}"], [f"br{i}"], composite=(3.0 - i) * scale)
             for i in range(3)]
        c = [_card([f"cg{i}"], [f"cr{i}"], composite=(3.0 - i))
             for i in range(3)]
        knobs = {"bakeoff_group_size": 0.0, "bakeoff_deck_limit": 0.0}
        with patch.object(bo, "_cfg", lambda k, d: float(knobs.get(k, d))):
            run = bo.run_bakeoff(
                generate=lambda **ov: list(b), gen_v2=lambda **ov: list(c),
                league_id="league_rank_only", iso_week="2026-W34",
                interleave=True, roster=(bo.ARM_CURRENT, bo.ARM_GEN_V2))
        return [(tuple(x.give_player_ids), tuple(x.receive_player_ids))
                for x in run.served_deck()]

    assert _deck_ids(1.0) == _deck_ids(100.0)


def test_impressions_uniform_columns():
    """T2 — `save_deck_impressions` compiles its executemany statement from
    the FIRST row's keys. With the deck LED by an unattributed injection,
    every row must still carry the identical key set, and every
    features_json must decode with `fit` and `fit_diag` present (null
    allowed — absence is what the M4 null-share tripwire cannot survive)."""
    run, _cur, fit = _fit_run(serve_fit=1, group_size=0)
    # Give the drafted fit cards a real fit payload (the module half would
    # have); arm-B cards carry none — nulls must still serialize.
    for c in fit:
        c.fit = {"you": 61.0, "them": 55.5, "aggregate": 116.5,
                 "bucket": "both_ok", "boards": "both", "ver": "fit-1",
                 "r5_fail": False, "lenses": {}}
    injection = _card(["inj_g"], ["inj_r"])      # no arm produced this
    cards = [injection] + list(run.served_deck())

    seen = {}
    with patch.object(server, "save_deck_impressions",
                      lambda rows: seen.setdefault("rows", rows)), \
            patch.object(server, "load_board_state",
                         lambda *a, **kw: (0, None)), \
            patch.object(server, "_deck_fatigue_enabled", lambda: False), \
            patch.object(server, "_deck_taste_enabled", lambda: False):
        server._log_deck_signal_impressions(
            user_id=H.ME, league_id=H.LEAGUE, job_id="j-uniform",
            cards=cards, players_dict={}, capture=None,
            scoring_format="1qb_ppr", seed_map={}, bakeoff_run=run)

    rows = seen["rows"]
    assert len(rows) == len(cards)
    # One key set, batch-wide — the T2 contract.
    assert len({tuple(sorted(r)) for r in rows}) == 1
    feats = [json.loads(r["features_json"]) for r in rows]
    for f in feats:
        assert "fit" in f and "fit_diag" in f    # null allowed, never absent
    # The injection row is honestly unattributed, null-fit…
    assert rows[0]["model_arm"] is None
    assert feats[0]["fit"] is None
    # …and a served fit card carries its payload.
    fit_rows = [i for i, r in enumerate(rows) if r["model_arm"] == "fit"]
    assert fit_rows
    assert feats[fit_rows[0]]["fit"]["ver"] == "fit-1"

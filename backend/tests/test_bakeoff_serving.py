"""trade.bakeoff — serving-path integration (Phase 3).

Spec: docs/plans/three-model-bakeoff/PLAN.md §3.4, §4, §5.
Scope block: docs/plans/three-model-bakeoff/scope-phase3.md.

Contract under test, in `server._run_trade_job`:

  • Flag OFF ⇒ the generation path is byte-identical to pre-bake-off
    `origin/main`. Proven against a CAPTURED golden
    (backend/tests/fixtures/bakeoff/flag_off_golden.json, produced by running
    backend/tests/support/bakeoff_harness.py inside a worktree at the
    pre-bake-off SHA), not against an assertion about ourselves. The only
    admitted difference is the two additive NULL columns.
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
NEW_COLUMNS = ("model_arm", "arm_rank", "fairness_threshold")


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


def _bakeoff_patches(*, enabled: bool, interleaved: bool = False):
    knobs = {"bakeoff_serve_interleaved": 1.0 if interleaved else 0.0}
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

    with patch.object(bo, "arm_order_for", lambda lid, wk=None: list(order)):
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
    with patch.object(bo, "arm_order_for", lambda lid, wk=None: list(order)):
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
    with patch.object(bo, "arm_order_for", lambda lid, wk=None: list(order)):
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

    with patch.object(bo, "arm_order_for", lambda lid, wk=None: list(order)):
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

    with patch.object(bo, "arm_order_for", lambda lid, wk=None: list(order)):
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

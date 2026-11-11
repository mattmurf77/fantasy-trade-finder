"""backend/eval/acceptance_eval.py — the offline acceptance evaluation of the
bilateral support score (docs/plans/realtime-trade-engine/acceptance-eval.md).

Covers: the IRLS logistic fitter recovers known coefficients and matches the
closed-form MLE (log odds ratio) and a zero-gradient optimality check;
grouped CV never puts a group in both train and test and tests every row
once; small-cell suppression; extraction over an in-memory SQLite DB reads
both an inline row (bilateral proof by JSON path) and a packed card (ADR-025
pack, compact block only, no proof), joins counterparty mirror labels, and
applies the stage/demo/allowlist/redaction exclusions; the report carries no
raw identifier (and assert_aggregate refuses one that does); verdicts are
"insufficient_data" below the thresholds and "estimable" above them.
"""

import json
import math
import random
from dataclasses import asdict

import pytest
from sqlalchemy import create_engine, insert

from backend.database import (
    deck_evidence_packs_table, deck_impressions_table, deck_outcomes_table, metadata,
    suggestion_trade_links_table, trade_decisions_table, trade_matches_table,
    trade_pass_reasons_table, trade_proposals_table,
)
from backend.eval import acceptance_eval as ae
from backend.eval import evidence_pack as ep
from backend.eval.contract import card_impression_id

SERVED = "2026-10-01T12:00:00+00:00"


# ---------------------------------------------------------------------------
# The fitter
# ---------------------------------------------------------------------------

def test_fitter_recovers_known_coefficients():
    rng = random.Random(7)
    true = (-0.5, 1.2, -0.8)
    x, y = [], []
    for _ in range(6000):
        a, b = rng.gauss(0, 1), rng.gauss(0, 1)
        p = 1 / (1 + math.exp(-(true[0] + true[1] * a + true[2] * b)))
        x.append([a, b])
        y.append(1.0 if rng.random() < p else 0.0)
    w = ae.fit_logistic(x, y, l2=1e-6)
    for got, want in zip(w, true):
        assert abs(got - want) < 0.1


def test_fitter_matches_closed_form_log_odds_ratio():
    # One binary feature, no penalty: the MLE intercept is the log odds in
    # the x=0 group and the slope the log odds ratio.
    x = [[0.0]] * 100 + [[1.0]] * 100
    y = [1.0] * 30 + [0.0] * 70 + [1.0] * 60 + [0.0] * 40
    w = ae.fit_logistic(x, y, l2=0.0)
    assert w[0] == pytest.approx(math.log(30 / 70), abs=1e-8)
    assert w[1] == pytest.approx(math.log(60 / 40) - math.log(30 / 70), abs=1e-8)


def test_fitter_penalised_optimum_has_zero_gradient():
    rng = random.Random(3)
    x = [[rng.gauss(0, 1), rng.gauss(0, 1)] for _ in range(300)]
    y = [1.0 if rng.random() < 0.4 else 0.0 for _ in x]
    lam = 5.0
    w = ae.fit_logistic(x, y, l2=lam)
    ps = ae.predict(w, x)
    g0 = sum(p - t for p, t in zip(ps, y))
    g = [sum((p - t) * r[j] for p, t, r in zip(ps, y, x)) + lam * w[j + 1] for j in range(2)]
    assert abs(g0) < 1e-6 and all(abs(v) < 1e-6 for v in g)


def test_within_group_auc_ignores_between_group_level():
    # Within each group the score ranks perfectly; across groups the
    # low-scoring group has the higher like rate, so pooled AUC is lower.
    by_group = {"a": [(0.1, 0.0), (0.2, 1.0), (0.3, 1.0)],
                "b": [(0.7, 0.0), (0.8, 0.0), (0.9, 1.0)]}
    assert ae.within_auc(by_group) == 1.0
    pooled = [p for g in by_group.values() for p in g]
    assert ae.auc([s for s, _ in pooled], [y for _, y in pooled]) < 1.0


def test_auc_ties_and_degenerate():
    assert ae.auc([1, 2, 3, 4], [0, 0, 1, 1]) == 1.0
    assert ae.auc([1, 1, 1, 1], [0, 1, 0, 1]) == 0.5
    assert ae.auc([1, 2], [1, 1]) is None


# ---------------------------------------------------------------------------
# Grouped CV and suppression
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n_groups", [2, 3, 5, 9, 23])
def test_grouped_folds_never_share_a_group(n_groups):
    groups = [f"g{i % n_groups}" for i in range(200)]
    folds = ae.grouped_folds(groups, k=5)
    tested = []
    for train, test in folds:
        assert {groups[i] for i in train}.isdisjoint({groups[i] for i in test})
        tested += test
    assert sorted(tested) == list(range(200))


def test_cell_suppression():
    assert ae.cell(4, rate=0.5) == {"n": "<5", "rate": None}
    assert ae.cell(5, rate=0.5) == {"n": 5, "rate": 0.5}
    assert ae.small(3) == "<5" and ae.small(7) == 7
    head = ae.analyse(_synthetic_rows(3, 100), arms={ae.BILATERAL_ARM})["viewer_strong_head"]
    assert head["positives"] == "<5"
    rel = ae._reliability([(0.15, 1.0)] * 3 + [(0.85, 0.0)] * 6)
    small = [b for b in rel["bins"] if b["range"][0] == 0.1][0]
    assert small["n"] == "<5" and small["observed"] is None


# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

def test_verdict_thresholds():
    assert ae.verdict(100, 200, 3, 11) == "insufficient_data"        # 3 users
    assert ae.verdict(6, 200, 40, 11) == "insufficient_data"         # 6 positives
    assert ae.verdict(60, 200, 40, 11) == "mostly_prior"             # EPV < 10
    assert ae.verdict(200, 400, 40, 11) == "estimable"


def _synthetic_rows(n_users, per_user, seed=1):
    rng = random.Random(seed)
    rows = []
    for u in range(n_users):
        for k in range(per_user):
            vm = rng.uniform(-.3, .3)
            vp = rng.uniform(-.3, .3)
            p = 1 / (1 + math.exp(-(-0.4 + 3 * vm + 2 * vp)))
            v_sup = .45 * (.5 + vp) + .35 * (.5 + .5 * vm / .25) + .2 * .5
            row = {"impression_id": f"imp{u}-{k}", "user_id": f"user{u}", "league_id": f"lg{u % 4}",
                   "served_at": SERVED, "model_arm": ae.BILATERAL_ARM, "policy_version": "p",
                   "trade_concept_id": None, "partner": None, "card_index": k % 30,
                   "position": k % 30, "packed": False, "propensity": 1.0, "viewed": True,
                   "responded": True, "undone": False, "conflict": False,
                   "y_like": 1.0 if rng.random() < p else 0.0, "y_strong": 0.0,
                   "pass_reason": None, "match_other": [], "match_status": [], "executed": None,
                   "y_counterparty": None, "has_proof": True, "gen_version": "owner-v2-bilateral-2",
                   "shape": "1x1" if k % 2 else "2x1", "weaker_support": min(v_sup, .5),
                   "total_support": v_sup + .5, "v_support": v_sup, "c_support": .5,
                   "v_pref_c": .5 + vp, "v_market_c": .5 + vm, "v_plan_c": .5,
                   "c_pref_c": .5, "c_market_c": .5 - vm, "c_plan_c": .5, "v_net_pref": vp,
                   "v_market_gain": vm, "v_plan_gain": 0.0, "v_need": rng.uniform(0, .1),
                   "c_net_pref": 0.0, "c_market_gain": -vm, "c_plan_gain": 0.0, "c_need": 0.0,
                   "v_state": "known", "c_state": "unknown" if k % 3 else "known",
                   "v_outlook": "contender", "c_outlook": "rebuilder" if k % 2 else "contender",
                   "v_personal_gain": vp, "c_personal_gain": 0.0}
            rows.append(row)
    return rows


def test_analyse_insufficient_with_few_users_and_estimable_with_many():
    small = ae.analyse(_synthetic_rows(3, 100), arms={ae.BILATERAL_ARM})
    assert small["viewer_head"]["verdict"] == "insufficient_data"
    assert small["counterparty_head"]["verdict"] == "insufficient_data"
    big = ae.analyse(_synthetic_rows(30, 60), arms={ae.BILATERAL_ARM})
    head = big["viewer_head"]
    assert head["verdict"] == "estimable"
    cv = head["cv_by_user"]
    assert cv["folds"] == 5 and cv["heldout_n"] == 1800
    assert cv["fitted"]["auc"] > 0.65
    assert head["monotonicity"]["holds_full_fit"] is True


# ---------------------------------------------------------------------------
# Extraction: inline rows, packed cards, labels, exclusions, no identifiers
# ---------------------------------------------------------------------------

def _valuation(v_market=.1, c_market=-.1, c_state="unknown"):
    def side(market, state, outlook):
        return {"support": {"score": .55, "components": {"preference_fulfillment": .6,
                "market_acceptability": .5 + market, "team_plan": .5}},
                "intent": {"net_preference": .1}, "market_gain_fraction": market,
                "team_plan_gain": 0.0, "need_utility": .01, "personal_gain_fraction": .05,
                "preference_evidence": {"state": state}, "outlook": outlook}
    return {"generator": ae.BILATERAL_ARM, "generator_version": "owner-v2-bilateral-2",
            "bilateral": {"weaker_support": .5, "total_support": 1.05},
            "construction": {"shape": "2x1"},
            "viewer": side(v_market, "known", "contender"),
            "counterparty": side(c_market, c_state, "rebuilder")}


def _row(iid, user, league, job, idx, *, partner, concept=None, arm=ae.BILATERAL_ARM,
         features=None):
    return {"impression_id": iid, "user_id": user, "league_id": league, "deck_job_id": job,
            "card_index": idx, "trade_hash": f"h{idx}", "propensity": 1.0, "served_at": SERVED,
            "is_ghost": 0, "model_arm": arm, "policy_version": "owner-only-v1",
            "trade_concept_id": concept,
            "valuation_json": json.dumps(_valuation()) if arm == ae.BILATERAL_ARM else None,
            "features_json": json.dumps({"partner_user_id": partner, **(features or {})})}


def _engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    metadata.create_all(eng, tables=[
        deck_impressions_table, deck_outcomes_table, deck_evidence_packs_table,
        trade_decisions_table, trade_matches_table, trade_proposals_table,
        suggestion_trade_links_table, trade_pass_reasons_table])
    return eng


SECRET_USER, SECRET_PARTNER = "USER_SECRET_123456", "PARTNER_SECRET_7890"
SECRET_LEAGUE, SECRET_JOB = "LEAGUE_SECRET_4242", "JOB_SECRET_0001"


def _fixture():
    eng = _engine()
    with eng.begin() as c:
        # Two inline bilateral cards: one liked (and mirrored + liked by the
        # partner), one passed with a value_giving reason.
        c.execute(insert(deck_impressions_table), [
            _row("IMP_SECRET_A", SECRET_USER, SECRET_LEAGUE, SECRET_JOB, 0,
                 partner=SECRET_PARTNER, concept="CONCEPT_SECRET_1"),
            _row("IMP_SECRET_B", SECRET_USER, SECRET_LEAGUE, SECRET_JOB, 1,
                 partner=SECRET_PARTNER, concept="CONCEPT_SECRET_2"),
            # The partner's mirror of concept 1, liked.
            _row("IMP_SECRET_MIRROR", SECRET_PARTNER, SECRET_LEAGUE, "JOB_SECRET_0002", 3,
                 partner=SECRET_USER, concept="CONCEPT_SECRET_1"),
            # Excluded: a qa_ stage user, the demo league, a redacted partner.
            _row("IMP_QA_00001", "qa_user_1", SECRET_LEAGUE, "JOB_QA", 0, partner=SECRET_PARTNER),
            _row("IMP_DEMO_0001", SECRET_USER, "league_demo", "JOB_DEMO", 0, partner=SECRET_PARTNER),
            _row("IMP_REDACT_01", SECRET_USER, SECRET_LEAGUE, SECRET_JOB, 2,
                 partner="redacted:abcdef"),
            _row("IMP_ALLOW_001", "ALLOWED_TESTER_99", SECRET_LEAGUE, "JOB_ALLOW", 0,
                 partner=SECRET_PARTNER),
        ])
        # A packed deck: card 0 has an outcome but never got a full row.
        packed_card = {"user_id": SECRET_USER, "league_id": SECRET_LEAGUE,
                       "deck_job_id": "RUN_SECRET_9", "served_at": SERVED, "card_index": 0,
                       "trade_hash": "00000000000000ab", "propensity": 1.0, "model_arm": "value_core",
                       "policy_version": "value-core-4", "partner_user_id": SECRET_PARTNER,
                       "give_value": 100.0, "receive_value": 110.0, "fairness_score": .9,
                       "shape": "1x1", "shape_bucket": "1x1"}
        run = {"deliveries": [[0, SERVED]]}
        packed = ep.pack_run(run, [packed_card], card_count=1)
        c.execute(insert(deck_evidence_packs_table).values(
            run_id="RUN_SECRET_9", user_id=SECRET_USER, league_id=SECRET_LEAGUE,
            served_at=SERVED, created_at=SERVED, **asdict(packed)))
        outcomes = [("IMP_SECRET_A", "viewed"), ("IMP_SECRET_A", "like"),
                    ("IMP_SECRET_B", "viewed"), ("IMP_SECRET_B", "pass"),
                    ("IMP_SECRET_MIRROR", "like"),
                    ("IMP_QA_00001", "like"), ("IMP_DEMO_0001", "pass"),
                    ("IMP_REDACT_01", "like"), ("IMP_ALLOW_001", "pass"),
                    (card_impression_id("RUN_SECRET_9", 0), "pass")]
        c.execute(insert(deck_outcomes_table), [
            {"impression_id": i, "action": a, "acted_at": SERVED} for i, a in outcomes])
        c.execute(insert(trade_pass_reasons_table).values(
            impression_id="IMP_SECRET_B", user_id=SECRET_USER, league_id=SECRET_LEAGUE,
            key_source="impression", reason="value", detail="value_giving",
            created_at=SERVED, updated_at=SERVED))
    return eng


def test_extract_reads_inline_and_packed_and_labels():
    eng = _fixture()
    with eng.connect() as conn:
        got = ae.extract(conn, since=None, until=None, allowlist={"ALLOWED_TESTER_99"})
    rows = {r["impression_id"]: r for r in got["rows"]}
    a, b = rows["IMP_SECRET_A"], rows["IMP_SECRET_B"]
    assert a["has_proof"] and a["weaker_support"] == .5 and a["c_state"] == "unknown"
    assert a["v_market_gain"] == pytest.approx(.1) and a["shape"] == "2x1"
    assert a["y_like"] == 1.0 and b["y_like"] == 0.0
    assert a["y_counterparty"] == 1.0 and a["mirror_responded"] is True
    assert b["y_counterparty"] is None
    assert b["pass_reason"] == ("value", "value_giving")
    packed = rows[card_impression_id("RUN_SECRET_9", 0)]
    assert packed["packed"] and not packed["has_proof"] and packed["model_arm"] == "value_core"
    assert packed["y_like"] == 0.0
    ex = got["exclusions"]
    assert ex["stage_user"] == 1 and ex["demo_league"] == 1
    assert ex["partner_redacted"] == 1 and ex["tester_allowlist"] == 1
    # The mirror is a labelled card of the partner's own and is kept.
    assert "IMP_SECRET_MIRROR" in rows


def test_report_has_no_raw_identifiers():
    eng = _fixture()
    report, _rows = ae.run(eng, allowlist={"ALLOWED_TESTER_99"})
    blob = json.dumps(report)
    for secret in ("SECRET", "qa_user_1", "ALLOWED_TESTER", "redacted:abcdef", "league_demo"):
        assert secret not in blob
    assert report["volume"]["labelled_total"]["n"] == "<5" or isinstance(
        report["volume"]["labelled_total"]["n"], int)
    assert report["viewer_head"]["verdict"] == "insufficient_data"
    with pytest.raises(ValueError):
        ae.assert_aggregate({"leak": "x USER_SECRET_123456 y"}, {SECRET_USER})


def test_extract_path_refused_inside_repo():
    with pytest.raises(SystemExit):
        ae._outside_repo(str(ae.REPO / "rows.jsonl"))

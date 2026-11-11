"""Revision 4 as an additive arm of the outlook-v2-v3-1 Calibration round.

docs/plans/offer-learnings/plan.md §3 WS1 Calibration: "add new calibration trades
for all users and their linked leagues (additive to current calibration decks)".
Stub arms test orchestration (as test_outlook_calibration_service.py does); the
real-engine case reuses test_calibration_round_adapter_execution's capture.
"""
import copy
import json
from types import SimpleNamespace

import pytest

from backend import blind_grading as bg, database as db, feature_flags as ff, outlook_calibration as oc
from backend import outlook_calibration_adapter as adapter, trade_service as ts
from backend.tests.test_outlook_calibration_persistence import engine  # noqa: F401
from backend.tests.test_calibration_round_adapter_execution import captured  # noqa: F401
from backend.tests.test_owner_generator_routes import harness, owner_harness  # noqa: F401
from backend.tests.test_owner_only_routes import exclusive, large_exclusive  # noqa: F401

V4 = oc.EXTRA_ARMS["revision_4"]


@pytest.fixture
def flags(monkeypatch):
    cache = dict(ff.DEFAULT_FLAGS)
    monkeypatch.setattr(ff, "_flags_cache", cache)
    return cache


class Proof:
    def __init__(self, version):
        self.model_identity = ("owner", version)

    def matches(self, card):
        return True

    def as_dict(self):
        return {"model_version": self.model_identity[1]}


def offer(version, i):
    return SimpleNamespace(target_user_id="partner", give_player_ids=("g",), receive_player_ids=(f"r{i}",),
                           owner_evaluation=Proof(version))


def frozen_factory(*, v4_ids=(0, 1, 50, 51, 52), v4_fail=False):
    """v2 = r0..r11, v3 = r0..r2 + r40..r48; v4 shares r0/r1 and adds r50+."""
    calls = []
    assets = {i: {"name": i, "position": "WR", "nfl_team": "X", "age": 26, "value": 1000}
              for i in ["g"] + [f"r{i}" for i in range(100)]}
    catalog = bg.Catalog(assets=assets, partner_names={"partner": "Partner"},
                         holdings={"seat": frozenset({"g"}), "partner": frozenset(assets) - {"g"}})
    ids = {oc.MODEL_VERSIONS["current"]: list(range(12)),
           oc.MODEL_VERSIONS["value_core"]: [0, 1, 2] + list(range(40, 49)),
           V4: list(v4_ids)}

    def run(version, *, check_current=None):
        calls.append(version)
        if version == V4 and v4_fail:
            raise RuntimeError("v4 failed")
        rows = [offer(version, i) for i in ids[version]]
        return rows, {"native_count": len(rows), "final_count": len(rows)}
    return SimpleNamespace(source={}, catalog=catalog, run_arm=run), calls


def build(**kwargs):
    frozen, calls = frozen_factory(**kwargs)
    start = oc.start_session(user_id="account", league_user_id="seat", league_id="league", seed=91)
    sid = start["session"]["session_id"]
    oc.build_session(session_id=sid, capture=lambda **scope: frozen)
    return db.load_grading_session(sid), db.load_grading_cards(sid), calls


def keys(cards):
    return [json.loads(c["trade_json"])["receive"][0]["id"] for c in cards]


def pair_view(cards):
    """Paired cards in order, with their paired arm credits only."""
    out = []
    for c in cards:
        arms = {a: v for a, v in json.loads(c["arms_json"]).items() if a in oc.MODEL_VERSIONS}
        if arms:
            out.append((keys([c])[0], sorted(arms), c["partner_user_id"]))
    return out


def test_flag_off_build_never_runs_or_records_revision_4(engine, flags):
    row, cards, calls = build()
    assert V4 not in calls
    source, counts = json.loads(row["source_json"]), json.loads(row["counts_json"])
    assert "extra_arms" not in source and source["execution_order"] == [
        a for a in source["execution_order"] if a in oc.MODEL_VERSIONS]
    assert set(counts["arms"]) == set(oc.MODEL_VERSIONS.values())
    assert all("revision_4" not in json.loads(c["arms_json"]) for c in cards)


def test_flag_on_adds_revision_4_without_touching_the_pair(engine, flags):
    off_row, off_cards, _ = build()
    db.retire_grading_session(off_row["session_id"], "{}")
    flags["grading.revision4_arm"] = True
    row, cards, calls = build()
    assert calls[-1] == V4
    # The paired deck: same cards, same credits, same relative order, same counts.
    assert pair_view(cards) == pair_view(off_cards)
    counts, off_counts = json.loads(row["counts_json"]), json.loads(off_row["counts_json"])
    for key in ("shared", "inventory_shared", "comparison_available", "sample_size_status"):
        assert counts[key] == off_counts[key]
    for version in oc.MODEL_VERSIONS.values():
        assert counts["arms"][version]["selected"] == off_counts["arms"][version]["selected"]
    # Revision 4: two shared trades gain a credit, three new trades are inserted.
    v4 = counts["arms"][V4]
    assert v4["selected"] == 5 and v4["shared_with_pair"] == 2 and v4["inserted"] == 3
    assert v4["role"] == "additive" and v4["status"] == "complete"
    credited = {keys([c])[0] for c in cards if "revision_4" in json.loads(c["arms_json"])}
    assert credited == {"r0", "r1", "r50", "r51", "r52"}
    assert counts["total"] == len(cards) == len(off_cards) + 3
    assert sorted(c["position"] for c in cards) == list(range(1, len(cards) + 1))
    source = json.loads(row["source_json"])
    assert source["extra_arms"] == {"revision_4": V4}
    for c in cards:
        arms = json.loads(c["arms_json"])
        assert set(source["proofs"][c["card_id"]]) == set(arms)
        assert all(set(prov) == {"model_version", "rank", "proof_hash"} for prov in arms.values())
        assert "revision" not in c["trade_json"]  # Still blind.


def test_revision_4_selection_is_capped_at_the_pair_quota(engine, flags):
    flags["grading.revision4_arm"] = True
    row, cards, _ = build(v4_ids=range(50, 80))
    counts = json.loads(row["counts_json"])
    assert counts["arms"][V4]["selected"] == counts["arms"][oc.MODEL_VERSIONS["current"]]["selected"] == 12
    assert counts["arms"][V4]["unique_inventory"] == 30


def test_revision_4_failure_leaves_the_paired_deck_exactly(engine, flags):
    off_row, off_cards, _ = build()
    db.retire_grading_session(off_row["session_id"], "{}")
    flags["grading.revision4_arm"] = True
    row, cards, _ = build(v4_fail=True)
    assert row["status"] == "open"
    assert pair_view(cards) == pair_view(off_cards) and len(cards) == len(off_cards)
    assert [c["position"] for c in cards] == [c["position"] for c in off_cards]
    assert json.loads(row["counts_json"])["arms"][V4] == {
        "status": "error", "error_type": "RuntimeError", "selected": 0, "role": "additive"}


@pytest.mark.parametrize("exposed", [False, True])
def test_switching_on_retires_only_unexposed_unanswered_decks(engine, flags, monkeypatch, exposed):
    monkeypatch.setattr(adapter, "is_current", lambda *a, **k: True)
    row, cards, _ = build()
    sid = row["session_id"]
    if exposed:
        with db.engine.begin() as conn:
            conn.execute(db.grading_sessions_table.update().where(
                db.grading_sessions_table.c.session_id == sid).values(first_exposed_at="2026-11-10T00:00:00+00:00"))
        db.answer_grading_card(cards[0]["card_id"], "account", grade=4, skipped=False,
                               tags_json="[]", now="2026-11-10T00:00:01+00:00")
    resumed = oc.start_session(user_id="account", league_user_id="seat", league_id="league")
    assert resumed["session"]["session_id"] == sid  # Flag off: kept either way.
    flags["grading.revision4_arm"] = True
    again = oc.start_session(user_id="account", league_user_id="seat", league_id="league")
    if exposed:
        assert again["session"]["session_id"] == sid and again["resumed"]
        assert db.load_grading_cards(sid)[0]["grade"] == 4
    else:
        assert again["session"]["session_id"] != sid and again["needs_build"]
        assert json.loads(db.load_grading_session(sid)["error_json"]) == {"code": "comparison_stale"}


def test_results_and_report_attribute_revision_4_answers(engine, flags, monkeypatch):
    flags["grading.revision4_arm"] = True
    monkeypatch.setattr(oc, "connected_targets", lambda: ([], {"connected_pairs": 0}))
    row, cards, _ = build()
    with db.engine.begin() as conn:
        conn.execute(db.grading_sessions_table.update().where(
            db.grading_sessions_table.c.session_id == row["session_id"]).values(
                first_exposed_at="2026-11-10T00:00:00+00:00"))
    for c in cards:
        db.answer_grading_card(c["card_id"], "account", grade=5 if "revision_4" in c["arms_json"] else 3,
                               skipped=False, tags_json="[]", now="2026-11-10T00:00:01+00:00")
    out = oc.results(db.load_grading_session(row["session_id"]))
    assert out["arms"]["revision_4"]["n"] == 5 and out["arms"]["revision_4"]["mean"] == 5
    assert out["extra_model_versions"] == {"revision_4": V4}
    assert set(out["model_versions"]) == {"current", "value_core"}
    report = oc.report(include_open=True)
    group = report["completed"] if report["completed"]["sessions"] else report["partial"]
    assert group["additive_arms"][V4]["n"] == 5
    assert report["arm_inventory_totals"][V4]["selected"] == 5


def test_adapter_runs_revision_4_on_the_same_capture(captured):
    ts._cfg.update(owner_bilateral_enabled=1., owner_bilateral_revision_enabled=1.)
    before = copy.deepcopy(captured.owner_context)
    cards, diag = captured.run_arm(adapter.REVISION_4)
    assert cards and diag["model_version"] == adapter.REVISION_4
    assert {c.owner_evaluation.model_identity[1] for c in cards} == {adapter.REVISION_4}
    assert diag["presentment"]["generator_version"] == adapter.REVISION_4
    assert diag["presentment"]["eligible_count"] > 0
    assert captured.owner_context == before  # The frozen capture is never mutated.


@pytest.mark.parametrize("version", adapter.VERSIONS)
def test_serving_selector_cannot_turn_a_paired_arm_into_revision_4(captured, version):
    captured.owner_context["config"]["owner_bilateral_revision_4_enabled"] = 1.
    cards, _ = captured.run_arm(version)
    assert cards and {c.owner_evaluation.model_identity[1] for c in cards} == {version}

"""U6: receipts and the executed-trade matcher read viewed-or-first-30 cards.

analytics-lead's conditions on U6 (docs/plans/org-bringup/reports/analytics-lead.md
§ "I-2 send error codes and U6 receipts acceptance") and models-lead's R3 (U4
addendum), on ADR-025 C3 / R4.2 U6:
  * R-U6a: one eligibility predicate (database._evidence_shown) for the
    receipts queue and the matcher's was_recommended: a row written at build
    (evidence_tier NULL: legacy and flag-off rows, unchanged), or a
    deferred/packed deck's card in the first 30, or one with a first outcome
    of any kind joined by impression_id. R3: "viewed" comes from that
    outcome, never from the tier or from whether a full row exists. Ghost
    rows are unchanged (receipts skip them; the matcher's incrementality
    read links them).
  * R3: an acted-on card with no full row is reported, never silently
    dropped: per run, by cause (`restart_split` past the 90 stored cards for
    a row built from the pack, else `other`): a counter in the receipts
    metrics response and a log line from the matcher.
  * R-U6b: a `series_break` caveat on /api/admin/receipts/metrics once the
    flip day is set and the graded rows' serve dates span it; none while it
    is None.

Harness: isolated in-memory SQLite (backend/tests/CLAUDE.md pattern 1).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, insert, select

from backend import database as db
from backend import receipts_service as rs
from backend import suggestion_telemetry as st

LEAGUE, USER, PARTNER = "L-u6", "U-u6", "P-u6"
GRADER = "receipts-u6-test"


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    db.metadata.create_all(eng)
    with patch.object(db, "engine", eng):
        yield eng


def served(days_ago: float = 3) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def card(iid, *, tier, index=0, ghost=0, full=True, job="job-u6", days_ago=3.0):
    """One deck_impressions row: a full row carries assets_json, the pack-built
    miss row (R4.2 U4's fallback) doesn't."""
    with db.engine.begin() as conn:
        conn.execute(insert(db.deck_impressions_table).values(
            impression_id=iid, user_id=USER, league_id=LEAGUE, deck_job_id=job,
            card_index=index, propensity=1.0, served_at=served(days_ago), is_ghost=ghost,
            evidence_tier=tier, trade_hash=f"h-{iid}",
            features_json=json.dumps({"partner_user_id": PARTNER}),
            assets_json=(json.dumps({"give": ["p1"], "receive": ["p2"]}) if full else None)))
    return iid


def outcome(iid, action="viewed"):
    with db.engine.begin() as conn:
        conn.execute(insert(db.deck_outcomes_table).values(
            impression_id=iid, action=action, acted_at=served(1)))


def receipts_ids() -> set[str]:
    dates = [served(d)[:10] for d in range(0, 10)]
    return {r["impression_id"] for r in db.load_receipts_queue(28, GRADER, dates, 1000)}


def matcher_ids(*, ghosts=False) -> set[str]:
    rows = db.load_impressions_for_matching(LEAGUE, served(10), served(0))
    return {r["impression_id"] for r in rows if bool(r["is_ghost"]) == ghosts}


def eligible_ids() -> set[str]:
    """Every row the shared predicate admits (full or not)."""
    with db.engine.connect() as conn:
        return {r.impression_id for r in conn.execute(
            select(db.deck_impressions_table.c.impression_id).where(db._evidence_shown()))}


# ── R-U6a: eligibility = written at build, first 30, or acted on ────────────

def test_legacy_null_tier_rows_stay_eligible(engine):
    card("legacy", tier=None)
    assert receipts_ids() == matcher_ids() == {"legacy"}


def test_first30_is_eligible_without_an_outcome(engine):
    card("top", tier="first30", index=5)
    assert receipts_ids() == matcher_ids() == {"top"}


@pytest.mark.parametrize("tier", ["delivered", "full_interim", "archive", "viewed", "partial_run"])
def test_a_later_card_with_no_outcome_is_not_eligible(engine, tier):
    """'delivered' is sent, not seen; R3: not even a 'viewed' tier counts
    without its outcome."""
    card("unseen", tier=tier, index=40)
    assert receipts_ids() == matcher_ids() == set()


@pytest.mark.parametrize("tier", ["delivered", "full_interim", "archive", "viewed", "partial_run"])
@pytest.mark.parametrize("action", ["viewed", "like", "pass", "propose", "undo", "not_interested"])
def test_any_first_outcome_makes_a_later_card_eligible(engine, tier, action):
    card("acted", tier=tier, index=40)
    outcome("acted", action)
    assert receipts_ids() == matcher_ids() == {"acted"}


def test_delivered_with_a_like_is_eligible_and_without_is_not(engine):
    card("liked", tier="delivered", index=41)
    card("sent", tier="delivered", index=42)
    outcome("liked", "like")
    assert receipts_ids() == matcher_ids() == {"liked"}


def test_a_partial_run_row_counts_only_once_acted_on(engine):
    card("partial-acted", tier="partial_run", index=3)
    card("partial-quiet", tier="partial_run", index=4)
    outcome("partial-acted", "pass")
    assert receipts_ids() == matcher_ids() == {"partial-acted"}


def test_an_outcome_on_another_card_never_makes_this_one_eligible(engine):
    card("a", tier="delivered", index=50)
    card("b", tier="delivered", index=51)
    outcome("b-other-impression", "like")                 # joined by impression_id only
    assert receipts_ids() == matcher_ids() == set()


def test_ghost_rows_are_unchanged(engine):
    """Never a recommendation: receipts skip them, the matcher keeps them for
    its separate ghost link (the incrementality read)."""
    card("ghost", tier="ghost", index=7, ghost=1)
    assert receipts_ids() == set() and matcher_ids(ghosts=True) == {"ghost"}


def test_receipts_and_the_matcher_agree_on_a_mixed_deck(engine):
    rows = {"legacy": None, "top": "first30", "sent": "delivered", "liked": "delivered",
            "arch": "archive", "arch-viewed": "archive", "interim": "full_interim",
            "partial": "partial_run", "partial-acted": "partial_run", "v-tier-only": "viewed"}
    for n, (iid, tier) in enumerate(rows.items()):
        card(iid, tier=tier, index=30 + n)
    for iid in ("liked", "arch-viewed", "partial-acted"):
        outcome(iid, "viewed" if iid != "liked" else "like")
    expected = {"legacy", "top", "liked", "arch-viewed", "partial-acted"}
    assert receipts_ids() == matcher_ids() == expected
    assert eligible_ids() == expected


def test_the_outcome_check_is_an_indexed_exists():
    """On both dialects the outcome check is a correlated EXISTS on
    deck_outcomes.impression_id, which ix_deck_outcomes_impression covers."""
    from sqlalchemy.dialects import postgresql
    sql = str(select(db.deck_impressions_table.c.impression_id).where(db._evidence_shown())
              .compile(dialect=postgresql.dialect()))
    assert "EXISTS (SELECT" in sql
    assert "deck_outcomes.impression_id = deck_impressions.impression_id" in sql
    index = {ix.name: [c.name for c in ix.columns] for ix in db.deck_outcomes_table.indexes}
    assert index["ix_deck_outcomes_impression"] == ["impression_id"]


# ── R3: acted-on cards with no full row are reported, not dropped ──────────

def restart_split_miss(iid="miss-95", index=95, job="job-restart"):
    """A card delivered past the 90 stored ones before a restart and viewed
    after it: its row was built from the pack ('viewed', no assets)."""
    card(iid, tier="viewed", index=index, full=False, job=job)
    outcome(iid, "viewed")
    return iid


def test_a_viewed_card_with_no_full_row_is_eligible_and_reported_with_its_cause(engine):
    miss = restart_split_miss()
    early = card("miss-12", tier="viewed", index=12, full=False, job="job-other")
    outcome(early, "like")
    assert {miss, early} <= eligible_ids()                 # eligible by its outcome
    assert receipts_ids() == matcher_ids() == set()        # but no assets to grade or match
    assert db.load_viewed_without_full_row(league_id=LEAGUE) == {
        "job-restart": {"restart_split": 1, "other": 0},
        "job-other": {"restart_split": 0, "other": 1}}


def test_an_unacted_row_without_assets_is_not_reported(engine):
    card("quiet-miss", tier="delivered", index=95, full=False)
    card("pre-telemetry", tier=None, index=1, full=False)     # never assets: not R3's
    assert db.load_viewed_without_full_row() == {}


@pytest.fixture()
def flags_on(monkeypatch):
    import backend.feature_flags as ff
    monkeypatch.setattr(ff, "_flags_cache", dict(ff.DEFAULT_FLAGS, **{"receipts.grading": True}))
    yield
    ff._flags_cache = None


def grade(iid, days_ago):
    with db.engine.begin() as conn:
        conn.execute(insert(db.receipts_grades_table).values(
            impression_id=iid, window_days=28, grader_version=GRADER, status="graded",
            league_id=LEAGUE, user_id=USER, served_at=served(days_ago), graded_at=served(0),
            edge=1.0, edge_pct=0.1, shape_bucket="1x1", basis="consensus", model_arm="current"))


def test_receipts_metrics_report_the_viewed_cards_without_a_full_row(engine, flags_on):
    restart_split_miss()
    grade("graded-1", 5)
    with patch.object(rs, "max_grader_version", lambda versions: GRADER):
        out = rs.admin_metrics(window=28)
    assert out["viewed_without_full_row"] == {"restart_split": 1, "other": 0, "runs": 1}


def test_the_matcher_logs_the_viewed_cards_without_a_full_row(engine, caplog):
    restart_split_miss()
    trade = {"transaction_id": "tx-1", "traded_at": served(1), "synced_at": served(1)}
    caplog.set_level(logging.WARNING, logger=st.log.name)
    with patch.object(st, "load_unlinked_league_trades", lambda league_id: [trade]), \
         patch.object(st, "executed_trade_sides", lambda tr, roster_map: {"x": ["p1"]}), \
         patch.object(st, "save_suggestion_trade_links", lambda links: len(links)):
        assert st.match_league_trades(LEAGUE, roster_map={}) == 1
    assert [r.getMessage() for r in caplog.records
            if r.getMessage().startswith("[matcher] viewed without full row")] == [
        f"[matcher] viewed without full row league={LEAGUE} run=job-restart "
        f"restart_split=1 other=0"]
    assert {r.levelname for r in caplog.records
            if r.getMessage().startswith("[matcher] viewed without full row")} == {"WARNING"}


def test_the_matcher_logs_a_non_zero_other_at_error(engine, caplog):
    """U4-R2: `other` must be zero; a non-zero one is an ERROR, never a warning."""
    trade = {"transaction_id": "tx-1", "traded_at": served(1), "synced_at": served(1)}
    caplog.set_level(logging.WARNING, logger=st.log.name)
    with patch.object(st, "load_unlinked_league_trades", lambda league_id: [trade]), \
         patch.object(st, "executed_trade_sides", lambda tr, roster_map: {"x": ["p1"]}), \
         patch.object(st, "save_suggestion_trade_links", lambda links: len(links)), \
         patch.object(st, "load_viewed_without_full_row",
                      lambda **kw: {"job-x": {"restart_split": 0, "other": 2}}):
        st.match_league_trades(LEAGUE, roster_map={})
    lines = [r for r in caplog.records if r.getMessage().startswith("[matcher] viewed without full row")]
    assert [(r.levelname, r.getMessage()) for r in lines] == [
        ("ERROR", f"[matcher] viewed without full row league={LEAGUE} run=job-x restart_split=0 other=2")]


# ── R-U6b: the receipts series break at the flip ───────────────────────────

def test_no_caveat_while_the_flip_day_is_none(engine, flags_on, monkeypatch):
    monkeypatch.setattr(rs, "RECEIPTS_SERIES_BREAK_DAY", None)
    grade("g-old", 20)
    grade("g-new", 2)
    with patch.object(rs, "max_grader_version", lambda versions: GRADER):
        assert rs.admin_metrics(window=28)["caveats"] == []


def test_a_set_flip_day_inside_the_window_adds_one_caveat(engine, flags_on, monkeypatch):
    day = served(10)[:10]
    monkeypatch.setattr(rs, "RECEIPTS_SERIES_BREAK_DAY", day)
    grade("g-old", 20)
    grade("g-new", 2)
    with patch.object(rs, "max_grader_version", lambda versions: GRADER):
        assert rs.admin_metrics(window=28)["caveats"] == [{
            "code": "series_break", "scope": "receipts", "day": day,
            "detail": "U6/R-U6a: receipts move to viewed-or-first-30 cards at the "
                      "packed-evidence flip"}]


@pytest.mark.parametrize("days_ago", [30, 1])
def test_a_set_flip_day_outside_the_window_adds_none(engine, flags_on, monkeypatch, days_ago):
    monkeypatch.setattr(rs, "RECEIPTS_SERIES_BREAK_DAY", served(days_ago)[:10])
    grade("g-old", 20)
    grade("g-new", 2)
    with patch.object(rs, "max_grader_version", lambda versions: GRADER):
        assert rs.admin_metrics(window=28)["caveats"] == []


def test_the_flip_day_ships_unset():
    assert rs.RECEIPTS_SERIES_BREAK_DAY is None

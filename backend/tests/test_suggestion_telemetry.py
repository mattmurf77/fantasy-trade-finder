"""suggestion.telemetry — counterfactual logging, ghost holdout, executed-
trade tagging (docs/plans/matchmaking-engine/telemetry-scope.md).

Covers:
  • Round-trip: flag ON stamps policy_version / candidate_set_id +
    candidate_set_size / assets_json on every deck_impressions row and
    writes one matching deck_candidate_sets row; flag OFF leaves every new
    column NULL and writes zero candidate-set rows (byte-identical F1).
  • Ghost holdout: predicate determinism (same league+week+hash ⇒ same
    verdict; ~1-in-N frequency; ≤0 disables), and end-to-end withholding —
    ghosted cards never appear in the published job snapshot, never land in
    legacy trade_impressions, and are logged with is_ghost=1 at their
    would-have-been rank while exempt cards (likes-you) still serve.
  • Executed-trade matcher: exact / near-miss partial / no-match / ghost /
    lookback cases, generic-pick round relaxation, idempotency, and the
    per-league was_recommended ratio.

Harness: the test_deck_signal_v2 pattern — isolated in-memory SQLite
patched into backend.database, flag helpers patched directly.
"""

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select, text

import backend.database as db_module
import backend.server as server
import backend.suggestion_telemetry as st
from backend.database import (
    deck_candidate_sets_table,
    deck_impressions_table,
    metadata,
    save_suggestion_trade_links,
    suggestion_ratio_by_league,
    suggestion_trade_links_table,
    trade_impressions_table,
)
from backend.ranking_service import Player, RankingService
from backend.trade_service import League, LeagueMember, TradeService


LEAGUE = "888777666"          # numeric, like a real Sleeper league id
ME     = "user_me"
OPP    = "user_opp"
TOKEN  = "test-token-sugg-tel"
JOB_ID = "job-sugg-tel"
ROSTER_MAP = {"1": ME, "2": OPP}


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _signal(on: bool):
    return patch.object(server, "_deck_signal_v2_enabled", lambda: on)


def _telemetry(on: bool):
    return patch.object(server, "_suggestion_telemetry_enabled", lambda: on)


def _no_bakeoff():
    """Pin the bake-off OFF. These tests assert the UNSUFFIXED policy version
    and the normal presentation stack; `trade.bakeoff` (live true since
    2026-08-18) stamps `/bo:<arm>` onto every impression and hands deck order
    to the interleaver. Neither is what this file measures — the bake-off's
    own telemetry is covered in test_bakeoff_runner.py."""
    import backend.bakeoff_runner as _bo
    return patch.object(_bo, "bakeoff_enabled", lambda: False)


def _ghost_rate(one_in: int):
    """Patch the module-level rate read (server + matcher both resolve
    st.ghost_one_in at call time)."""
    return patch.object(st, "ghost_one_in", lambda: one_in)


# ---------------------------------------------------------------------------
# Job harness (test_deck_signal_v2 pattern)
# ---------------------------------------------------------------------------

@pytest.fixture()
def harness(mem_engine):
    pool = [Player(id=pid, name=pid.upper(), position="RB", team="AAA", age=25)
            for pid in ("g1", "g2", "r1", "r2")]
    service   = RankingService(players=list(pool))
    trade_svc = TradeService(players={p.id: p for p in pool})
    league = League(
        league_id=LEAGUE, name="Telemetry League", platform="sleeper",
        members=[
            LeagueMember(user_id=ME,  username="me",  roster=["g1", "g2"], elo_ratings={}),
            LeagueMember(user_id=OPP, username="opp", roster=["r1", "r2"], elo_ratings={}),
        ],
    )
    trade_svc.add_league(league)

    sess = {
        "user_id":       ME,
        "league":        league,
        "user_roster":   ["g1", "g2"],
        "players":       pool,
        "services":      {"1qb_ppr": service},
        "trade_svcs":    {"1qb_ppr": trade_svc},
        "service":       service,
        "trade_svc":     trade_svc,
        "active_format": "1qb_ppr",
        "last_active":   0.0,
    }
    job = {
        "job_id": JOB_ID, "key": (ME, LEAGUE, "1qb_ppr"), "status": "running",
        "started_at": time.monotonic(), "finished_at": None,
        "opponents_done": 0, "opponents_total": 1, "cards": [],
        "error": None, "fairness_threshold": 0.75,
        "outlook_value": None, "is_pinned": False,
    }

    server.app.config["TESTING"] = True
    client = server.app.test_client()

    with patch.object(server, "load_member_rankings", MagicMock(return_value={})), \
         patch.object(server, "load_league_preference", MagicMock(return_value=None)), \
         patch.object(server, "_likes_you_enabled", lambda: True), \
         patch.object(server, "_thompson_deck_enabled", lambda: True), \
         patch.object(server, "_deck_diversity_enabled", lambda: False), \
         patch.object(server, "create_notification", MagicMock()), \
         patch.object(server, "_send_typed_push", MagicMock()):
        with server._sessions_lock:
            server._sessions[TOKEN] = sess
        with server._trade_jobs_lock:
            server._trade_jobs[JOB_ID] = job
        try:
            yield client, job, trade_svc, mem_engine
        finally:
            with server._sessions_lock:
                server._sessions.pop(TOKEN, None)
            with server._trade_jobs_lock:
                server._trade_jobs.pop(JOB_ID, None)
                server._trade_jobs_by_key.pop((ME, LEAGUE, "1qb_ppr"), None)


def _insert_decision(conn, user_id, give_ids, recv_ids, decision, age_days=1):
    created = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    conn.execute(text(
        "INSERT INTO trade_decisions "
        "(user_id, league_id, give_player_ids, receive_player_ids, decision, created_at) "
        "VALUES (:uid, :lid, :give, :recv, :dec, :created)"
    ), {"uid": user_id, "lid": LEAGUE,
        "give": json.dumps(give_ids), "recv": json.dumps(recv_ids),
        "dec": decision, "created": created})


def _run_job(mem_engine, job):
    """Seed a likes-you source decision (guarantees ≥1 served card) and run
    the worker to completion."""
    with mem_engine.begin() as conn:
        _insert_decision(conn, OPP, ["r1"], ["g1"], "like")
    server._run_trade_job(JOB_ID, TOKEN, LEAGUE, 0.75, [])
    assert job["status"] == "complete", job.get("error")
    return job["cards"]


def _impressions(eng):
    with eng.connect() as conn:
        return conn.execute(
            select(deck_impressions_table)
            .order_by(deck_impressions_table.c.card_index)
        ).fetchall()


def _candidate_sets(eng):
    with eng.connect() as conn:
        return conn.execute(select(deck_candidate_sets_table)).fetchall()


# ---------------------------------------------------------------------------
# Round-trip: flag OFF is byte-identical, flag ON stamps + persists
# ---------------------------------------------------------------------------

def test_flag_off_leaves_columns_null_and_no_candidate_sets(harness):
    client, job, trade_svc, eng = harness
    with _no_bakeoff(), _signal(True), _telemetry(False):
        cards = _run_job(eng, job)
    rows = _impressions(eng)
    assert len(rows) == len(cards) >= 1
    for r in rows:
        assert r.is_ghost is None
        assert r.policy_version is None
        assert r.candidate_set_id is None
        assert r.candidate_set_size is None
        assert r.assets_json is None
    assert _candidate_sets(eng) == []


def test_flag_on_round_trip_stamps_and_persists(harness):
    client, job, trade_svc, eng = harness
    with _no_bakeoff(), _signal(True), _telemetry(True), _ghost_rate(0):
        cards = _run_job(eng, job)
    rows = _impressions(eng)
    assert len(rows) == len(cards) >= 1

    sets = _candidate_sets(eng)
    assert len(sets) == 1
    cs = sets[0]
    members = json.loads(cs.candidates_json)
    assert cs.size == len(members) >= len(rows)
    assert cs.deck_job_id == JOB_ID
    assert cs.user_id == ME and cs.league_id == LEAGUE
    member_hashes = {m["trade_hash"] for m in members}

    expected_policy = st.serving_policy_version()
    for r, card in zip(rows, cards):
        assert r.is_ghost == 0
        assert r.policy_version == expected_policy
        assert r.candidate_set_id == cs.candidate_set_id
        assert r.candidate_set_size == cs.size
        assets = json.loads(r.assets_json)
        assert set(assets) == {"give", "receive"}
        assert assets["give"] and assets["receive"]
        # every logged card is reconstructable from the candidate set
        assert r.trade_hash in member_hashes
        # snapshot still carries the impression id (serving unchanged)
        assert card["impression_id"] == r.impression_id


# ---------------------------------------------------------------------------
# Ghost predicate — determinism + rate
# ---------------------------------------------------------------------------

def test_ghost_predicate_deterministic_and_seeded_per_week():
    h = "abcd1234ef567890"
    a = st.is_ghost_suggestion("L1", h, week_key="2026-W33", one_in=10)
    for _ in range(50):
        assert st.is_ghost_suggestion("L1", h, week_key="2026-W33", one_in=10) == a
    # different league or week may flip the verdict; over many hashes the
    # withheld SETS must differ between weeks (rotation, not permanence)
    hashes = [f"hash{i:04d}" for i in range(400)]
    w1 = {x for x in hashes if st.is_ghost_suggestion("L1", x, week_key="2026-W33", one_in=10)}
    w2 = {x for x in hashes if st.is_ghost_suggestion("L1", x, week_key="2026-W34", one_in=10)}
    assert w1 and w2 and w1 != w2


def test_ghost_predicate_rate_and_disable():
    hashes = [f"hash{i:05d}" for i in range(3000)]
    n = sum(st.is_ghost_suggestion("L1", x, week_key="2026-W33", one_in=10)
            for x in hashes)
    assert 0.06 < n / len(hashes) < 0.15          # ~0.10, loose bounds
    assert not any(st.is_ghost_suggestion("L1", x, week_key="2026-W33", one_in=0)
                   for x in hashes[:100])
    assert all(st.is_ghost_suggestion("L1", x, week_key="2026-W33", one_in=1)
               for x in hashes[:100])


# ---------------------------------------------------------------------------
# Ghost holdout — end to end: withheld, logged, never rendered
# ---------------------------------------------------------------------------

def test_ghosts_logged_but_never_rendered(harness):
    client, job, trade_svc, eng = harness
    # one_in=1 ⇒ every ELIGIBLE (non-likes-you) organic card is withheld.
    with _no_bakeoff(), _signal(True), _telemetry(True), _ghost_rate(1):
        cards = _run_job(eng, job)

    rows = _impressions(eng)
    ghost_rows  = [r for r in rows if r.is_ghost == 1]
    served_rows = [r for r in rows if r.is_ghost == 0]
    assert ghost_rows, "with one_in=1 at least one organic card must ghost"

    # Every card in the published snapshot is likes-you (the exemption) and
    # maps 1:1 onto the served rows; no ghost impression id ever surfaces.
    assert len(cards) == len(served_rows)
    snapshot_iids = {c.get("impression_id") for c in cards}
    assert snapshot_iids == {r.impression_id for r in served_rows}
    for c in cards:
        assert c.get("likes_you"), "only exempt cards may serve at one_in=1"
    for g in ghost_rows:
        assert g.impression_id not in snapshot_iids
        assert g.assets_json    # fully logged
        assert g.policy_version == st.serving_policy_version()

    # Legacy trade_impressions ("every card SHOWN") excludes ghosts.
    with eng.connect() as conn:
        legacy = conn.execute(select(trade_impressions_table)).fetchall()
    assert len(legacy) == len(served_rows)

    # Served rows keep contiguous served positions (0..n-1); ghost rows
    # carry their would-have-been rank in the pre-withhold order.
    assert sorted(r.card_index for r in served_rows) == list(range(len(served_rows)))


def test_ghost_split_deterministic_across_runs(harness):
    client, job, trade_svc, eng = harness
    with _signal(True), _telemetry(True), _ghost_rate(2):
        _run_job(eng, job)
        first = {(r.trade_hash, r.is_ghost) for r in _impressions(eng)}
        # reset + rerun the same job in the same league-week
        with eng.begin() as conn:
            conn.execute(deck_impressions_table.delete())
            conn.execute(deck_candidate_sets_table.delete())
        with server._trade_jobs_lock:
            server._trade_jobs[JOB_ID].update(
                status="running", finished_at=None, cards=[])
        server._run_trade_job(JOB_ID, TOKEN, LEAGUE, 0.75, [])
        second = {(r.trade_hash, r.is_ghost) for r in _impressions(eng)}
    assert first == second


# ---------------------------------------------------------------------------
# Asset tokens
# ---------------------------------------------------------------------------

def test_asset_tokens():
    # players pass through
    assert st.suggestion_asset_token("4046", LEAGUE) == "4046"
    # owned pick pseudo-asset: "{league}_{season}_{round}_{orig_roster}"
    assert (st.suggestion_asset_token(f"{LEAGUE}_2027_1_5", LEAGUE)
            == "pick:2027:r1:5")
    # generic ladder pick → round-only token
    assert st.suggestion_asset_token("generic_pick_2_mid", LEAGUE) == "gpick:r2"
    # executed pick entry
    assert (st.executed_pick_token({"season": "2027", "round": 1,
                                    "roster_id": 5, "owner_id": 2,
                                    "previous_owner_id": 1})
            == "pick:2027:r1:5")


def test_score_match_generic_pick_relaxation():
    # suggested a generic 1st; executed trade moved a real 2027 1st
    mtype, overlap = st.score_match(
        ["p1", "gpick:r1"], ["p2"],
        ["p1", "pick:2027:r1:5"], ["p2"],
    )
    assert (mtype, overlap) == ("exact", 1.0)
    # wrong round does not pair
    mtype, overlap = st.score_match(
        ["p1", "gpick:r3"], ["p2"],
        ["p1", "pick:2027:r1:5"], ["p2"],
    )
    assert mtype == "partial" and overlap < 1.0


# ---------------------------------------------------------------------------
# Executed-trade matcher
# ---------------------------------------------------------------------------

def _seed_impression(eng, *, give, recv, partner=OPP, user=ME, is_ghost=0,
                     served_days_ago=2, iid=None):
    iid = iid or uuid.uuid4().hex
    served = (datetime.now(timezone.utc)
              - timedelta(days=served_days_ago)).isoformat()
    with eng.begin() as conn:
        conn.execute(deck_impressions_table.insert().values(
            impression_id=iid, user_id=user, league_id=LEAGUE,
            deck_job_id="job-x", card_index=0,
            trade_hash="th_" + iid[:8],
            features_json=json.dumps({"partner_user_id": partner}),
            propensity=1.0, served_at=served,
            is_ghost=is_ghost, policy_version="v3+ts@r1",
            assets_json=json.dumps({"give": give, "receive": recv}),
        ))
    return iid


def _seed_trade(eng, txid, *, adds, picks=None, traded_days_ago=1,
                roster_ids=(1, 2)):
    traded = (datetime.now(timezone.utc)
              - timedelta(days=traded_days_ago)).isoformat()
    with eng.begin() as conn:
        conn.execute(db_module.sleeper_trades_table.insert().values(
            transaction_id=txid, league_id=LEAGUE, week=1,
            traded_at=traded, synced_at=traded,
            roster_ids=json.dumps(list(roster_ids)),
            adds=json.dumps(adds), drops=json.dumps({}),
            draft_picks=json.dumps(picks or []),
            waiver_budget=json.dumps([]), raw=json.dumps({}),
        ))


def _links(eng):
    with eng.connect() as conn:
        return {r.transaction_id: r for r in conn.execute(
            select(suggestion_trade_links_table)).fetchall()}


def test_matcher_exact_partial_none_and_ghost(mem_engine):
    eng = mem_engine
    # ME (roster 1) ↔ OPP (roster 2).
    # exact: suggested give [g1] receive [r1]; executed g1→2, r1→1
    iid_exact = _seed_impression(eng, give=["g1"], recv=["r1"])
    _seed_trade(eng, "tx_exact", adds={"g1": 2, "r1": 1})
    # near-miss: suggested give [a1, a2] receive [b1]; executed only a1↔b1
    # (asset ids disjoint from the exact case so the best match is this one)
    iid_part = _seed_impression(eng, give=["a1", "a2"], recv=["b1"])
    _seed_trade(eng, "tx_partial", adds={"a1": 2, "b1": 1})
    # no-match: totally different assets
    _seed_impression(eng, give=["c1"], recv=["c2"])
    _seed_trade(eng, "tx_none", adds={"x9": 2, "y8": 1})
    # ghost: exact-matching but withheld suggestion
    iid_ghost = _seed_impression(eng, give=["g2"], recv=["r2"], is_ghost=1)
    _seed_trade(eng, "tx_ghost", adds={"g2": 2, "r2": 1})
    # stale: exact assets but served far outside the lookback
    _seed_impression(eng, give=["z1"], recv=["z2"], user=OPP, partner=ME,
                     served_days_ago=60)
    _seed_trade(eng, "tx_stale", adds={"z1": 1, "z2": 2})

    n = st.match_league_trades(LEAGUE, roster_map=ROSTER_MAP)
    assert n == 5
    links = _links(eng)

    ex = links["tx_exact"]
    assert ex.was_recommended == 1
    assert ex.match_type == "exact" and ex.overlap_score == 1.0
    assert ex.matched_impression_id == iid_exact
    assert ex.ghost_impression_id is None

    pa = links["tx_partial"]
    assert pa.was_recommended == 1
    assert pa.match_type == "partial"
    assert pa.matched_impression_id == iid_part
    assert 0.5 <= pa.overlap_score < 1.0

    no = links["tx_none"]
    assert no.was_recommended == 0
    assert no.match_type is None and no.matched_impression_id is None

    gh = links["tx_ghost"]
    assert gh.was_recommended == 0          # never rendered ⇒ can't have caused it
    assert gh.ghost_impression_id == iid_ghost
    assert gh.ghost_match_type == "exact"

    st_ = links["tx_stale"]
    assert st_.was_recommended == 0 and st_.matched_impression_id is None

    # idempotent: nothing new on a second pass
    assert st.match_league_trades(LEAGUE, roster_map=ROSTER_MAP) == 0

    # ratio: 2 of 5 executed trades were recommended; 1 ghost match
    rows = suggestion_ratio_by_league(LEAGUE)
    assert len(rows) == 1
    r = rows[0]
    assert r["executed"] == 5 and r["recommended"] == 2
    assert r["ratio"] == 0.4 and r["ghost_matches"] == 1


def test_matcher_best_match_prefers_exact(mem_engine):
    eng = mem_engine
    iid_partial = _seed_impression(eng, give=["g1", "g2"], recv=["r1"],
                                   served_days_ago=3)
    iid_exact = _seed_impression(eng, give=["g1"], recv=["r1"],
                                 served_days_ago=5)
    _seed_trade(eng, "tx1", adds={"g1": 2, "r1": 1})
    assert st.match_league_trades(LEAGUE, roster_map=ROSTER_MAP) == 1
    link = _links(eng)["tx1"]
    assert link.matched_impression_id == iid_exact
    assert link.match_type == "exact"
    assert iid_partial  # (documents that the partial candidate existed)


def test_matcher_multi_team_counts_in_denominator(mem_engine):
    eng = mem_engine
    _seed_trade(eng, "tx3way", adds={"a": 1, "b": 2, "c": 3},
                roster_ids=(1, 2, 3))
    assert st.match_league_trades(LEAGUE, roster_map=ROSTER_MAP) == 1
    link = _links(eng)["tx3way"]
    assert link.was_recommended == 0 and link.match_type is None
    rows = suggestion_ratio_by_league(LEAGUE)
    assert rows[0]["executed"] == 1 and rows[0]["recommended"] == 0


def test_matcher_direction_matters(mem_engine):
    eng = mem_engine
    # Suggestion has ME GIVING r1 and RECEIVING g1 — the executed trade
    # moved them the OPPOSITE way, so directional alignment must fail the
    # exact test and (with 0 give-side matches) the partial test too.
    _seed_impression(eng, give=["r1"], recv=["g1"])
    _seed_trade(eng, "tx_flip", adds={"g1": 2, "r1": 1})
    st.match_league_trades(LEAGUE, roster_map=ROSTER_MAP)
    link = _links(eng)["tx_flip"]
    assert link.was_recommended == 0 and link.matched_impression_id is None


def test_save_links_idempotent_on_txid(mem_engine):
    rows = [{
        "transaction_id": "tx_dup", "league_id": LEAGUE,
        "was_recommended": 0, "matched_impression_id": None,
        "match_type": None, "overlap_score": None,
        "ghost_impression_id": None, "ghost_match_type": None,
        "ghost_overlap_score": None, "traded_at": None,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }]
    assert save_suggestion_trade_links(rows) == 1
    assert save_suggestion_trade_links(rows) == 0


# ---------------------------------------------------------------------------
# Admin ratio route
# ---------------------------------------------------------------------------

def test_ratio_route_gated_and_served(mem_engine):
    server.app.config["TESTING"] = True
    client = server.app.test_client()
    with patch.object(server, "_require_cron_auth", lambda: None):
        with _telemetry(False):
            resp = client.get("/api/admin/suggestion-telemetry/ratio")
            assert resp.status_code == 404
            assert resp.get_json()["error"] == "feature_disabled"
        _seed_impression(mem_engine, give=["g1"], recv=["r1"])
        _seed_trade(mem_engine, "tx_r", adds={"g1": 2, "r1": 1})
        st.match_league_trades(LEAGUE, roster_map=ROSTER_MAP)
        with _telemetry(True):
            resp = client.get("/api/admin/suggestion-telemetry/ratio")
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["total"]["executed"] == 1
            assert body["total"]["recommended"] == 1
            assert body["total"]["ratio"] == 1.0

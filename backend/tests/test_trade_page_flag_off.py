"""P1 with `trade.first_page_store` off is today, byte for byte.

Scope: docs/plans/trade-time-to-suggestion/scope-eng-200ms.md §2 ("A test
pins flag-off = no page-store reads or writes") and §3
(`test_trade_page_flag_off.py`, release-lead's go/no-go evidence).

Pinned here, with the flag off:
  * paged and unpaged /generate (cache hit, running join, miss) and /status
    (with and without `cursor`) bodies are byte-identical to the stacked
    S0+E2 base: each body's sha256 equals a golden captured by running
    `test_bodies_match_the_s0_e2_base` on the base merge d826170f;
  * trade_page_store is never queried and never gains a row, through those
    routes, a real job's completion, the roster-change trigger, user- and
    league-scoped input invalidations, a board publish and the cleanup pass.

Harnesses: test_trade_responses_small's `e2` (seeded jobs) and
test_i1_serve_filter's `live` (a real synchronous worker).
"""
import hashlib
import uuid

import pytest
from sqlalchemy import event, func, select

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
from backend import roster_snapshot
from backend.tests.test_trade_responses_small import (  # noqa: F401  (fixtures)
    JOB_ID, card, e2, generate, harness, seed_job, status)
from backend.tests.test_i1_serve_filter import LEAGUE, TOKEN, UID, live  # noqa: F401

FLAG = "trade.first_page_store"

# sha256 of each body on the base merge d826170f (S0 + E2, before P1).
BASE_GOLDENS = {
    "status_legacy": "0a651cdfcede560dd15b78cbb257eba20e924408891fedfc78743873866d03b3",
    "status_cursor_0": "eecbbc063c456c2f2a8e40bf37fd5c954d53f1a0888a69e67db7b9846029a86f",
    "status_cursor_30": "b07c0dccb83ac921d71c21bffa26d917a1533276fb4a39dbbb51356f48019415",
    "status_cursor_60": "43230485a78981e98edd23d8607c36acf527392e4b41f3dd103221d4122b6884",
    "status_cursor_30_replacing": "88d82dfbba5f0b8a856c4610e34f20575b9fb31015ad83759008126c26e795c4",
    "generate_legacy_hit": "0a651cdfcede560dd15b78cbb257eba20e924408891fedfc78743873866d03b3",
    "generate_paged_hit": "2dbe4b3580b5b45712f0678c2a2d867992ee8a4cab95a38ced4708f8e8063664",
    "generate_paged_join": "f7abd802d54eb503ec93b5c14b94db9e25c82711fcd121df170c40a08818173e",
    "generate_legacy_miss": "a2ed0b37a1f95bd8939c7ea532a5eda2595656957f56c229a80de44ae58c1b73",
    "generate_paged_miss": "fd4e4e7368a6ada3354071d927d91d8928375c32086405c51c70b74db279e263",
}


@pytest.fixture()
def flag_off(e2, monkeypatch):
    monkeypatch.setitem(ff._flags_cache, FLAG, False)
    # Fixed job ids, so a new job's body is comparable byte for byte.
    ids = iter(uuid.UUID(int=n) for n in range(1, 100))
    monkeypatch.setattr(uuid, "uuid4", lambda: next(ids))
    yield e2


def bodies(client):
    """Every response shape the base serves, keyed for BASE_GOLDENS."""
    out = {}
    seed_job([card(i) for i in range(75)])                          # owner, append-only
    out["status_legacy"] = status(client).get_data()
    for cursor in (0, 30, 60):
        out[f"status_cursor_{cursor}"] = status(client, cursor).get_data()
    out["generate_legacy_hit"] = generate(client).get_data()
    out["generate_paged_hit"] = generate(client, page=1, search_id="s-1").get_data()
    seed_job([card(i, owner=False) for i in range(40)])             # re-sorting worker
    out["status_cursor_30_replacing"] = status(client, 30).get_data()
    seed_job([card(i) for i in range(12)], status="running")
    out["generate_paged_join"] = generate(client, page=1).get_data()
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    out["generate_legacy_miss"] = generate(client).get_data()
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    out["generate_paged_miss"] = generate(client, page=1, search_id="s-2").get_data()
    return out


def test_bodies_match_the_s0_e2_base(flag_off):
    client, *_ = flag_off
    got = {name: hashlib.sha256(body).hexdigest() for name, body in bodies(client).items()}
    assert got == BASE_GOLDENS


# ── The table is never touched ──────────────────────────────────────────────

@pytest.fixture()
def page_statements():
    seen = []

    def listener(conn, cursor, statement, *args):
        if "trade_page_store" in statement:
            seen.append(statement)

    engine = db_module.engine
    event.listen(engine, "before_cursor_execute", listener)
    yield seen
    event.remove(engine, "before_cursor_execute", listener)


def page_rows():
    with db_module.engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(db_module.trade_page_store_table)).scalar()


def test_seeded_job_routes_never_touch_the_table(flag_off, page_statements):
    client, *_ = flag_off
    bodies(client)
    assert page_statements == [] and page_rows() == 0


def test_a_real_job_trigger_and_cleanup_never_touch_the_table(live, monkeypatch, page_statements):
    client, _engine, _sess = live
    monkeypatch.setitem(ff._flags_cache, FLAG, False)
    job_id = server._kickoff_trade_job(sess_token=TOKEN, user_id=UID, league_id=LEAGUE,
                                       scoring_format="1qb_ppr", fairness_threshold=0.5,
                                       opponents_total=1, synchronous=True)
    job = server._trade_jobs[job_id]
    assert job["status"] == "complete"
    assert "page_scope" not in job and "page_built_at" not in job
    assert server._store_trade_page(job_id) is False
    headers = {"X-Session-Token": TOKEN}
    for body in ({}, {"page": 1}):
        response = client.post("/api/trades/generate", headers=headers,
                               json={"league_id": LEAGUE, "fairness_threshold": 0.5, **body})
        assert response.status_code == 200
        assert not {"serve_source", "freshness_state", "prefetch_remaining"} & set(response.get_json())
    for query in ("", "&cursor=0", "&cursor=30"):
        response = client.get(f"/api/trades/status?job_id={job_id}{query}", headers=headers)
        assert response.status_code == 200
        assert not {"serve_source", "freshness_state", "prefetch_remaining"} & set(response.get_json())
    roster_snapshot.on_roster_change(LEAGUE, "rfp1:old", "rfp1:new")
    server._invalidate_trade_jobs(user_id=UID)
    server._invalidate_trade_jobs(user_id=UID, league_id=LEAGUE)
    server._publish_member_rankings_for_trade_refresh(
        user_id=UID, league_id=LEAGUE, rankings=[{"player_id": "g1", "elo": 1500.0}],
        scoring_format="1qb_ppr")
    server._evict_trade_page_store()
    assert page_statements == [] and page_rows() == 0

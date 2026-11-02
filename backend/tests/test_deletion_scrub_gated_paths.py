"""Legal R28.26 #10 on the flag- and pack-gated paths, driven end to end
(#562 delta QA P3-C: these were pinned only by source). Adapted from
release-lead's QA probes (qa562w: test_qa562w_held.py p32, test_qa562w_pack.py,
test_qa562w_overhaul.py).

  • a standing offer created while the job lives stores the token;
  • the pack-fallback upgrade row (a restart, then a view) takes the token
    while the pack still names the person; with no deletion, the real id;
  • an overhaul offer to a partner whose job lives isn't minted, while the
    other partners' offers are.
"""
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import insert, select

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
import backend.tests.test_calc_trade_queue as tcq
from backend import accounts
from backend import database as db


@pytest.fixture(autouse=True)
def _fresh_cache():
    db.clear_deletion_tokens_cache()
    yield
    db.clear_deletion_tokens_cache()


def _live_job(ids, token):
    with db.engine.begin() as conn:
        conn.execute(insert(db.deletion_scrub_jobs_table).values(
            job_id=token[-32:], token=token, partner_ids_json=json.dumps(list(ids)),
            league_ids_json="[]", deleted_at=datetime.now(timezone.utc).isoformat()))
    db.clear_deletion_tokens_cache()


# ── Standing offers ─────────────────────────────────────────────────────────

def test_a_standing_offer_created_while_the_job_lives_stores_the_token(monkeypatch):
    gen = tcq._harness_ctx(caller_in_members=False)
    client, engine, *_ = next(gen)
    try:
        ff._flags_cache = {**ff._flags_cache, "trade.standing_offers": True}
        monkeypatch.setattr(server, "_standing_offers_enabled", lambda: True)
        monkeypatch.setattr(server, "league_pick_seasons", lambda **kw: [2027])
        saved = {}

        def create(**kw):
            saved.update(kw)
            return {"id": 1, **kw, "created_at": "2026-11-02T00:00:00+00:00",
                    "expires_at": "2026-11-09T00:00:00+00:00", "revoked_at": None}
        monkeypatch.setattr(server, "create_standing_offer", create)
        token = "redacted:" + "d" * 32
        _live_job([tcq.OPP], token)
        res = client.post("/api/trades/standing-offer", data=json.dumps({
            "league_id": tcq.LEAGUE, "player_id": "g1", "round": 1, "seasons": [2027],
            "team_user_ids": [tcq.OPP]}), content_type="application/json",
            headers={"X-Session-Token": tcq.TOKEN})
        assert res.status_code < 300, res.get_data(as_text=True)
        assert saved["team_user_ids"] == [token]
    finally:
        gen.close()


# ── The pack-fallback upgrade ───────────────────────────────────────────────

from backend.tests.test_i1_serve_filter import live  # noqa: E402,F401  (fixture)
from backend.tests.test_trade_page_store import p1, status  # noqa: E402,F401  (fixture)
from backend.tests.test_deferred_evidence import OPP, by_index, deferred  # noqa: E402,F401
from backend.tests.test_packed_evidence import packed_deck, restart, view  # noqa: E402


@pytest.mark.parametrize("deleted", [False, True])
def test_the_pack_fallback_upgrade_row_takes_a_live_deletions_token(deferred, deleted):
    client, engine, _ = deferred
    job_id, *_ = packed_deck(120)
    status(client, job_id, 0)
    status(client, job_id, 90)
    restart()                                       # no snapshot: the pack path
    token = None
    if deleted:
        accounts.delete_user_data(OPP)              # the scrub hasn't run: the pack names OPP
        db_module.clear_deletion_tokens_cache()
        with engine.connect() as conn:
            token = conn.execute(select(db_module.deletion_scrub_jobs_table.c.token)).scalar()
    view(job_id, 95)
    row = by_index(engine).get((0, 95))
    assert row is not None
    partner = json.loads(row["features_json"]).get("partner_user_id")
    if deleted:
        assert partner == token and OPP not in json.dumps(row, default=str)
    else:
        assert partner == OPP


# ── The overhaul mint ───────────────────────────────────────────────────────

from backend import overhaul_store as store  # noqa: E402
from backend.tests.test_overhaul_api import (  # noqa: E402,F401  (fixtures)
    LEAGUE, _create, _h, _settings, api, world)


def _gen(client, v):
    r = client.post(f"/api/overhauls/{v['overhaul_id']}/generate",
                    json={"revision": v["revision"]}, headers=_h())
    return r.status_code, r.get_json()


def test_no_overhaul_offer_is_minted_to_a_partner_whose_job_lives(api, world):
    _live_job(["o2", "o3"], "redacted:" + "f" * 32)
    v = _create(api)
    v = _settings(api, v["overhaul_id"], v["revision"], outlook="push_all_in",
                  eligible_asset_ids=["A", "B", "C", "D", "E"])
    code, _gen_body = _gen(api, v)
    assert code < 300
    partners = {o["counterparty_user_id"] for o in store.list_offers(v["overhaul_id"])}
    assert partners and not partners & {"o2", "o3"}   # the others' offers still mint

"""P2 server half: next pages across rebuilds, end of deck (flag `trade.first_page_store`).

Scope: docs/plans/trade-time-to-suggestion/scope-eng-200ms.md §6.3-§6.5 (on branch
plan/trades-200ms-eng-scope); the trades-eng P2 design draft §2-§4.

Pinned here, with the flag on:
  * organic paged responses name their deck (`deck_id`); pinned ones do not;
  * `/status?deck=D&cursor=K` resolves (a) D's stored pages, (b) D's live job
    past them, (c) `rebased` onto the scope's current deck from its first page,
    after a rebuild and after a restart, with dispositions and strict I-1;
  * `pool_exhausted` only for a complete deck asked past its last card with no
    newer or running deck for the scope and no stale row;
  * every page-store serve has a backing job, and the debounce stops stacking;
  * the kickoff's `append_only` marker decides over the card markers;
  * the legacy `job_id` + `cursor` form is unchanged; `deck` is validated.
With the flag off, `deck` is ignored and every body is byte-identical to P1's
base: each (status, body) sha256 equals a golden captured by running
`p2_flag_off_bodies` on 414357c6 (P1, before P2).

Harnesses: test_trade_page_store's `p1` (a real synchronous worker over stored
rosters, in-memory SQLite) and test_trade_responses_small's `e2` (seeded jobs).
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import delete, insert, update

import backend.database as db_module
import backend.feature_flags as ff
import backend.server as server
from backend import roster_snapshot
from backend.database import league_members_table
from backend.tests.test_i1_serve_filter import LEAGUE, UID, live  # noqa: F401  (fixture)
from backend.tests.test_trade_page_store import (  # noqa: F401  (fixtures)
    HEADERS, KEY, SCOPE, _vote, build_page, generate, ids, p1, page_card, run_job, set_row,
    spawned, status, stored)
from backend.tests.test_trade_responses_small import (  # noqa: F401  (fixtures)
    HEADERS as E2_HEADERS, JOB_ID, card, e2, generate as e2_generate, harness, seed_job,
    status as e2_status)

FLAG = "trade.first_page_store"


def deck_status(client, deck, cursor):
    return client.get(f"/api/trades/status?deck={deck}&cursor={cursor}", headers=HEADERS)


def build_deck():
    """P1's page (95 cards in the job, 90 stored) on an append-only job, as an
    owner-serve deck is."""
    deck = build_page()
    with server._trade_jobs_lock:
        server._trade_jobs[deck]["append_only"] = True
    return deck


def restart():
    """The daily worker kill: nothing in this process, the store survives."""
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()


def p1_ids(start, stop):
    return [f"p1-{i:03d}" for i in range(start, stop)]


# ── Page 1 names its deck ───────────────────────────────────────────────────

def test_a_store_served_page_one_names_its_deck(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    body = generate(client, page=1).get_json()
    assert body["serve_source"] == "page" and body["deck_id"] == body["job_id"] == deck
    assert not {"rebased", "pool_exhausted"} & set(body)


def test_a_job_served_page_one_names_its_deck_and_a_pinned_search_does_not(p1, spawned):
    client, engine, _ = p1
    job_id = run_job()
    with engine.begin() as conn:
        conn.execute(delete(db_module.trade_page_store_table))
    body = generate(client, page=1).get_json()             # the fresh job, no row
    assert "serve_source" not in body and body["deck_id"] == body["job_id"] == job_id
    forced = generate(client, page=1, force=True).get_json()  # the newest organic deck
    assert forced["deck_id"] == forced["job_id"] != job_id
    pinned = generate(client, page=1, pinned_give_players=["g2"]).get_json()
    assert "deck_id" not in pinned and "job_id" in pinned


# ── (a) and (b): one deck, paged ────────────────────────────────────────────

def test_deck_and_cursor_inside_the_stored_pages_slice_them(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    with server._trade_jobs_lock:                          # proves the slice is the row's
        server._trade_jobs[deck]["cards"] = []
    for cursor in (30, 60):
        body = deck_status(client, deck, cursor).get_json()
        assert ids(body["cards"]) == p1_ids(cursor, cursor + 30)
        assert (body["deck_id"], body["job_id"], body["cursor"], body["total_ready"]) == (
            deck, deck, cursor + 30, 90)
        assert (body["serve_source"], body["freshness_state"]) == ("page", "fresh")
        assert not {"rebased", "pool_exhausted"} & set(body)
    assert not spawned


def test_deck_continues_into_its_live_job_past_the_stored_pages(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    body = deck_status(client, deck, 90).get_json()
    assert ids(body["cards"]) == p1_ids(90, 95)
    assert (body["deck_id"], body["cursor"], body["total_ready"], body["replace"]) == (
        deck, 95, 95, False)
    assert "serve_source" not in body and body["prefetch_remaining"] == 50
    assert not {"rebased", "pool_exhausted"} & set(body)


def test_a_running_deck_pages_as_it_publishes(p1, spawned):
    client, _, _ = p1
    deck = run_job(synchronous=False)
    with server._trade_jobs_lock:
        job = server._trade_jobs[deck]
        job.update(cards=[page_card(i) for i in range(5)], append_only=True)
    body = deck_status(client, deck, 0).get_json()
    assert ids(body["cards"]) == p1_ids(0, 5) and body["status"] == "running"
    later = deck_status(client, deck, 5).get_json()
    assert later["cards"] == [] and later["cursor"] == 5 and later["deck_id"] == deck
    assert not {"rebased", "pool_exhausted"} & set(later)


# ── (c) rebased ─────────────────────────────────────────────────────────────

def _land_new_deck(offset=200):
    """A rebuild lands: a real forced job, its stored cards replaced by known ones."""
    new = run_job(force_fresh=True)
    with server._trade_jobs_lock:
        server._trade_jobs[new]["cards"] = [page_card(i + offset) for i in range(95)]
    assert server._store_trade_page(new)
    return new


def test_rebased_after_a_rebuild_moves_to_the_new_deck_from_its_first_card(p1, spawned):
    client, _, _ = p1
    old = build_deck()
    assert generate(client, page=1).get_json()["deck_id"] == old
    _vote(client)                                          # stale mark; the old job is revoked
    assert stored()["state"] == "stale"
    new = _land_new_deck()
    assert stored()["deck_job_id"] == new and stored()["state"] == "ready"
    body = deck_status(client, old, 30).get_json()
    assert body["rebased"] is True and body["deck_id"] == body["job_id"] == new
    assert ids(body["cards"]) == p1_ids(200, 230)          # the new deck from 0
    assert (body["cursor"], body["serve_source"], body["freshness_state"]) == (30, "page", "fresh")
    assert "pool_exhausted" not in body and not spawned    # the new deck's job backs it
    following = deck_status(client, new, body["cursor"]).get_json()
    assert ids(following["cards"]) == p1_ids(230, 260) and "rebased" not in following


def test_rebased_after_a_restart_serves_the_fresh_row_and_kicks_its_backing_job(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    restart()
    body = deck_status(client, "deck-before-restart", 30).get_json()
    assert body["rebased"] is True and body["deck_id"] == deck
    assert ids(body["cards"]) == p1_ids(0, 30) and body["cursor"] == 30
    assert (body["serve_source"], body["freshness_state"]) == ("page", "fresh")
    assert len(spawned) == 1                               # nothing here backed the row
    backing = server._trade_jobs_by_key[KEY]
    # The row's own deck past its stored pages: its job died with the process,
    # so the client moves to the backing job (joined, not kicked again).
    tail = deck_status(client, deck, 90).get_json()
    assert tail["rebased"] is True and tail["deck_id"] == tail["job_id"] == backing != deck
    assert (tail["status"], tail["cards"], tail["cursor"]) == ("running", [], 0)
    assert len(spawned) == 1


def test_a_deck_past_its_row_with_nothing_running_kicks_a_backing_job(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    restart()
    body = deck_status(client, deck, 90).get_json()
    assert len(spawned) == 1
    assert body["rebased"] is True and body["deck_id"] == server._trade_jobs_by_key[KEY] != deck
    assert server._trade_jobs[body["deck_id"]]["page_scope"] == SCOPE


def test_rebased_pages_apply_dispositions(p1, spawned):
    client, engine, _ = p1
    build_deck()
    restart()
    with engine.begin() as conn:                           # an exact pass on g2 -> r2
        conn.execute(insert(db_module.trade_decisions_table).values(
            user_id=UID, league_id=LEAGUE, trade_id="elsewhere",
            give_player_ids=json.dumps(["g2"]), receive_player_ids=json.dumps(["r2"]),
            decision="pass", created_at=datetime.now(timezone.utc).isoformat()))
    body = deck_status(client, "gone", 0).get_json()
    passed = {c["trade_id"] for c in (page_card(i) for i in range(30))
              if c["give"][0]["id"] == "g2" and c["receive"][0]["id"] == "r2"}
    assert body["rebased"] and passed and not passed & set(ids(body["cards"]))
    assert len(body["cards"]) == 30 - len(passed) and body["cursor"] == 30


def test_rebased_pages_apply_strict_i1(p1, spawned):
    client, engine, _ = p1
    build_deck()
    restart()
    with engine.begin() as conn:                           # g2 leaves the viewer's roster
        conn.execute(update(league_members_table).where(league_members_table.c.user_id == UID)
                     .values(roster_data=json.dumps([])))
    body = deck_status(client, "gone", 0).get_json()
    assert body["rebased"] and body["cards"] and body["cursor"] == 30
    assert all(c["give"][0]["id"] != "g2" for c in body["cards"])
    assert body["freshness_state"] == "updating"
    with engine.begin() as conn:                           # no stored rosters: strict fails
        conn.execute(delete(league_members_table))
    body = deck_status(client, "gone", 0).get_json()
    assert body["rebased"] and body["cards"] == [] and body["freshness_state"] == "updating"
    assert body["deck_id"] == body["job_id"] == server._trade_jobs_by_key[KEY]


def test_a_rebase_onto_a_job_is_strict_where_the_job_view_is_lenient(p1, spawned):
    """E2's job view passes a league with no stored rosters (S0, lenient); a
    rebased page never does (P1's strict rule)."""
    client, engine, _ = p1
    job_id = run_job()
    with server._trade_jobs_lock:
        server._trade_jobs[job_id]["cards"] = [page_card(i) for i in range(10)]
    with engine.begin() as conn:
        conn.execute(delete(db_module.trade_page_store_table))
        conn.execute(delete(league_members_table))
    assert len(status(client, job_id, 0).get_json()["cards"]) == 10
    body = deck_status(client, "gone", 0).get_json()
    assert body["rebased"] and body["deck_id"] == job_id
    assert body["cards"] == [] and body["freshness_state"] == "updating"


def test_another_users_deck_is_never_served(p1, spawned):
    client, _, _ = p1
    mine = build_deck()
    foreign = dict(server._trade_jobs[mine], job_id="foreign-deck",
                   key=("someone_else", LEAGUE, "1qb_ppr"),
                   cards=[page_card(i + 500) for i in range(40)])
    with server._trade_jobs_lock:
        server._trade_jobs["foreign-deck"] = foreign
    body = deck_status(client, "foreign-deck", 0).get_json()
    assert body["rebased"] is True and body["deck_id"] == mine
    assert ids(body["cards"]) == p1_ids(0, 30)


# ── End of deck ─────────────────────────────────────────────────────────────

def test_pool_exhausted_only_once_a_complete_deck_is_fully_delivered(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    assert "pool_exhausted" not in deck_status(client, deck, 60).get_json()   # (a)
    assert "pool_exhausted" not in deck_status(client, deck, 90).get_json()   # (b), cards left
    end = deck_status(client, deck, 95).get_json()
    assert end["pool_exhausted"] is True and end["cards"] == []
    assert (end["deck_id"], end["status"], end["cursor"]) == (deck, "complete", 95)
    assert "rebased" not in end and not spawned


def test_pool_exhausted_is_absent_while_the_deck_is_running(p1, spawned):
    client, _, _ = p1
    deck = run_job(synchronous=False)
    with server._trade_jobs_lock:
        server._trade_jobs[deck].update(cards=[page_card(i) for i in range(5)], append_only=True)
    assert "pool_exhausted" not in deck_status(client, deck, 5).get_json()


def test_pool_exhausted_is_absent_while_a_rebuild_runs(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    rebuild = run_job(synchronous=False, force_fresh=True)  # admitted after the deck completed
    assert server._trade_jobs[rebuild]["status"] == "running"
    body = deck_status(client, deck, 95).get_json()
    assert "pool_exhausted" not in body
    assert body["rebased"] is True and body["deck_id"] == rebuild


@pytest.mark.parametrize("how", ["vote", "marked_elsewhere"])
def test_a_stale_row_never_yields_pool_exhausted(p1, spawned, how):
    client, engine, _ = p1
    deck = build_deck()
    if how == "vote":
        _vote(client)                                     # marks stale and revokes the deck
    else:
        set_row(engine, state="stale")                    # e.g. another process's mark
    assert stored()["state"] == "stale"
    body = deck_status(client, deck, 95).get_json()
    assert "pool_exhausted" not in body
    if how == "vote":                                      # the rebuild is kicked and followed
        assert body["rebased"] is True and len(spawned) == 1
        assert body["deck_id"] == server._trade_jobs_by_key[KEY] != deck
    else:   # the deck is still fresh here, so it stays the deck: no end, no rebase, no stacking
        assert (body["deck_id"], body["cards"], body["cursor"]) == (deck, [], 95)
        assert "rebased" not in body and not spawned


def test_a_newer_deck_landing_after_the_end_is_followed(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    assert deck_status(client, deck, 95).get_json()["pool_exhausted"] is True
    new = _land_new_deck()                                 # a rebuild lands later
    body = deck_status(client, deck, 95).get_json()
    assert body["rebased"] is True and body["deck_id"] == new and "pool_exhausted" not in body
    assert ids(body["cards"]) == p1_ids(200, 230)


# ── A backing job is always alive ───────────────────────────────────────────

def test_an_all_equal_serve_with_no_job_in_process_kicks_the_backing_job(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    restart()
    body = generate(client, page=1).get_json()
    assert (body["serve_source"], body["freshness_state"], body["deck_id"]) == ("page", "fresh", deck)
    assert len(spawned) == 1
    backing = server._trade_jobs[server._trade_jobs_by_key[KEY]]
    assert backing["status"] == "running" and backing["page_scope"] == SCOPE
    assert backing["job_id"] != deck
    again = generate(client, page=1).get_json()
    assert again["deck_id"] == deck and len(spawned) == 1  # joined


def test_the_debounce_stops_repeated_taps_stacking_jobs(p1, spawned, monkeypatch):
    """A failed snapshot read never compares, so preserve_running alone would
    revoke the running job and start another on every tap."""
    client, _, _ = p1
    build_deck()
    restart()
    with patch.object(roster_snapshot, "snapshot_ids", MagicMock(side_effect=RuntimeError("db"))):
        first = generate(client, page=1).get_json()
        assert first["cards"] == [] and first["freshness_state"] == "updating"
        assert len(spawned) == 1
        for _ in range(3):
            assert generate(client, page=1).get_json()["job_id"] == first["job_id"]
        assert len(spawned) == 1 and not server._trade_jobs[first["job_id"]].get("superseded")
        monkeypatch.setitem(server._trade_service_mod._cfg, "trade_prebuild_debounce_s", 0.0)
        assert generate(client, page=1).get_json()["job_id"] != first["job_id"]
    assert len(spawned) == 2 and server._trade_jobs[first["job_id"]]["superseded"]


def test_the_debounce_never_delays_a_rebuild_after_an_input_change(p1, spawned):
    client, _, _ = p1
    build_deck()
    restart()
    generate(client, page=1)                               # kicks the backing job
    assert len(spawned) == 1
    _vote(client)                                          # revokes it, inside the window
    body = generate(client, page=1).get_json()
    assert body["freshness_state"] == "updating" and len(spawned) == 2


# ── The append_only marker ──────────────────────────────────────────────────

@pytest.fixture()
def e2_on(e2, monkeypatch):
    monkeypatch.setitem(ff._flags_cache, FLAG, True)
    yield e2


@pytest.mark.parametrize("marker, owner_cards, replaces", [
    (True, False, False),      # the marker says append-only: cards without the card marker page
    (False, True, True),       # the marker says re-sorting: card markers are not trusted
    (None, True, False),       # admitted before P2: E2's card check
    (None, False, True),
])
def test_the_append_only_marker_decides_over_the_card_markers(e2_on, marker, owner_cards, replaces):
    client, *_ = e2_on
    extra = {} if marker is None else {"append_only": marker}
    seed_job([card(i, owner=owner_cards) for i in range(75)], **extra)
    body = e2_status(client, 30).get_json()
    assert body["replace"] is replaces
    assert len(body["cards"]) == (75 if replaces else 30)


def test_job_level_append_only_markers_still_count(e2_on):
    client, *_ = e2_on
    seed_job([card(i, owner=False) for i in range(75)], append_only=False, value_core={"served": 75})
    body = e2_status(client, 30).get_json()
    assert body["replace"] is False and len(body["cards"]) == 30


@pytest.mark.parametrize("owner_serve", [True, False])
def test_the_kickoff_stamps_append_only_from_owner_serve(p1, spawned, monkeypatch, owner_serve):
    monkeypatch.setattr(server, "_owner_enabled", lambda league_id: owner_serve)
    monkeypatch.setattr(server._bakeoff, "serve_owner", lambda *a, **k: True)
    assert server._trade_jobs[run_job(synchronous=False)]["append_only"] is owner_serve


# ── trade_hash on every served card (the client's dedupe key) ───────────────

@pytest.mark.xfail(strict=True, reason="served cards carry no trade_hash yet: P2 brief point "
                   "reported to trades-eng, not built here")
def test_every_served_card_carries_its_trade_hash(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    served = (generate(client, page=1).get_json()["cards"]
              + deck_status(client, deck, 30).get_json()["cards"]
              + deck_status(client, deck, 90).get_json()["cards"])
    assert served
    for c in served:
        assert c["trade_hash"] == server._deck_trade_hash(
            [p["id"] for p in c["give"]], [p["id"] for p in c["receive"]], c["target_user_id"])


# ── Validation and the legacy form ──────────────────────────────────────────

@pytest.mark.parametrize("deck", ["", "bad!deck", "x" * 65, "sp ace"])
def test_a_bad_deck_is_400(p1, spawned, deck):
    client, _, _ = p1
    response = client.get("/api/trades/status", headers=HEADERS,
                          query_string={"deck": deck, "cursor": "0"})
    assert response.status_code == 400 and response.get_json()["error"] == "invalid_deck"


def test_deck_without_a_cursor_is_not_read(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    response = client.get(f"/api/trades/status?job_id={deck}&deck=bad!deck", headers=HEADERS)
    assert response.status_code == 200
    assert len(response.get_json()["cards"]) == 95 and "deck_id" not in response.get_json()


def test_the_job_id_form_is_unchanged(p1, spawned):
    client, _, _ = p1
    deck = build_deck()
    for cursor in (30, 90, 95):
        assert not {"deck_id", "rebased", "pool_exhausted"} & set(
            status(client, deck, cursor).get_json())
    restart()
    assert status(client, "unknown-job", 0).status_code == 404


# ── Flag off: `deck` is ignored, byte for byte ──────────────────────────────

# sha256 of "<status code> <body>" per request on 414357c6 (P1, before P2).
P1_BASE_GOLDENS = {
    "job_and_deck_cursor_0": "1d514e53da274bc9fdae65695685232fc0469b7019ef6f4ee7647c1fb874341d",
    "job_and_deck_cursor_30": "da7903d66a714425a303bdb14f83ac71508a7624ab3710e01e441e9aaafc8aa6",
    "job_and_other_deck_cursor_30": "da7903d66a714425a303bdb14f83ac71508a7624ab3710e01e441e9aaafc8aa6",
    "job_and_bad_deck_cursor_30": "da7903d66a714425a303bdb14f83ac71508a7624ab3710e01e441e9aaafc8aa6",
    "job_and_deck_no_cursor": "a15e13560efa2508750416b5e6cdb9c61d8c795ff1b0d795c175191e402dfdcb",
    "deck_only_cursor_30": "537dec5fd615061ba15eea3995d3dc5fb939ce69f9c92a3e4d1f8658d97cd85a",
    "deck_only_no_cursor": "537dec5fd615061ba15eea3995d3dc5fb939ce69f9c92a3e4d1f8658d97cd85a",
    "job_and_deck_past_end": "0eeea2c5e47ee54ede792992bebeef04c1bc78c5b08ea3b49f9dadcf9896a2ea",
    "generate_paged_hit": "f05deb92ef51789422f0d6cc01dfcee4ba06fcb49fa66ee78654e61e975dc0ab",
    "generate_paged_miss": "e6cb3afaee0a9db4177f5fb30d39572572cd84be19acaa739208c7b43194545d",
}


def p2_flag_off_bodies(client):
    """Requests carrying `deck`, which P1's base never reads."""
    seed_job([card(i) for i in range(75)])                          # owner, append-only
    queries = {
        "job_and_deck_cursor_0": f"job_id={JOB_ID}&deck={JOB_ID}&cursor=0",
        "job_and_deck_cursor_30": f"job_id={JOB_ID}&deck={JOB_ID}&cursor=30",
        "job_and_other_deck_cursor_30": f"job_id={JOB_ID}&deck=another-deck&cursor=30",
        "job_and_bad_deck_cursor_30": f"job_id={JOB_ID}&deck=bad%21deck&cursor=30",
        "job_and_deck_no_cursor": f"job_id={JOB_ID}&deck={JOB_ID}",
        "deck_only_cursor_30": f"deck={JOB_ID}&cursor=30",
        "deck_only_no_cursor": f"deck={JOB_ID}",
        "job_and_deck_past_end": f"job_id={JOB_ID}&deck={JOB_ID}&cursor=75",
    }
    out = {name: client.get(f"/api/trades/status?{query}", headers=E2_HEADERS)
           for name, query in queries.items()}
    out["generate_paged_hit"] = e2_generate(client, page=1, search_id="s-1")
    server._trade_jobs.clear()
    server._trade_jobs_by_key.clear()
    out["generate_paged_miss"] = e2_generate(client, page=1)
    return {name: f"{r.status_code} ".encode() + r.get_data() for name, r in out.items()}


@pytest.fixture()
def flag_off(e2, monkeypatch):
    monkeypatch.setitem(ff._flags_cache, FLAG, False)
    ids_ = iter(uuid.UUID(int=n) for n in range(1, 100))
    monkeypatch.setattr(uuid, "uuid4", lambda: next(ids_))
    yield e2


def test_flag_off_deck_is_ignored_byte_for_byte(flag_off):
    client, *_ = flag_off
    got = {name: hashlib.sha256(body).hexdigest() for name, body in p2_flag_off_bodies(client).items()}
    assert got == P1_BASE_GOLDENS
    assert not any("append_only" in job for job in server._trade_jobs.values())


def test_flag_off_kickoff_stamps_no_append_only(p1, spawned, monkeypatch):
    monkeypatch.setattr(ff, "_flags_cache", {**ff.flags_dict(), FLAG: False})
    assert "append_only" not in server._trade_jobs[run_job(synchronous=False)]


def test_flag_off_a_stamped_job_pages_by_its_card_markers(e2, monkeypatch):
    """A job admitted while the flag was on, paged after it is turned off: P1's rule."""
    client, *_ = e2
    monkeypatch.setitem(ff._flags_cache, FLAG, False)
    seed_job([card(i, owner=False) for i in range(75)], append_only=True)
    body = e2_status(client, 30).get_json()
    assert body["replace"] is True and len(body["cards"]) == 75

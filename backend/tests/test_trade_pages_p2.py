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


# ── Flag off: `deck` is ignored, byte for byte ──────────────────────────────

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

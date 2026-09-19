"""`save_deck_impressions` pages its INSERT so statement size is bounded.

Regression for the 2026-09-07 owner-only outage: a ~1,400-card deck at ~21 KB
per row rendered as one ~28 MB multi-row INSERT (insertmanyvalues pages at
1,000 rows) and OOM-killed the 256 MB production Postgres backend, which put
the database into recovery and failed every Find a Trade. See
docs/runbook.md § Common failure modes.
"""

from __future__ import annotations

import math
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, func, select

from backend import database as db_module
from backend.database import deck_impressions_table, metadata


@pytest.fixture()
def mem_engine():
    eng = create_engine("sqlite:///:memory:",
                        connect_args={"check_same_thread": False})
    metadata.create_all(eng)
    with patch.object(db_module, "engine", eng):
        yield eng


def _row(i: int, payload: str) -> dict:
    return {
        "impression_id": f"imp_{i:05d}",
        "user_id":       "me",
        "league_id":     "L",
        "deck_job_id":   "job_paging",
        "card_index":    i,
        "trade_hash":    f"trade_{i}",
        "features_json": payload,
        "propensity":    1.0,
        "base_score":    1.0,
        "final_score":   1.0,
        "archetype":     "value_move",
        "shape_bucket":  "1x1",
        "served_at":     db_module._now(),
    }


def _count(eng) -> int:
    with eng.connect() as conn:
        return conn.execute(
            select(func.count()).select_from(deck_impressions_table)).scalar_one()


def test_large_deck_is_inserted_in_bounded_pages(mem_engine, monkeypatch):
    """Every row lands, and no single INSERT carries more than the page."""
    monkeypatch.setattr(db_module, "DECK_IMPRESSION_INSERT_ROWS", 7)
    n = 250                                    # > one insertmanyvalues page? no —
    statements: list[int] = []                 # the point is the page cap holds

    @event.listens_for(mem_engine, "before_cursor_execute")
    def _capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT"):
            # Each rendered row binds `impression_id` once; count those.
            statements.append(statement.count("impression_id") - 1
                              if executemany is False else len(parameters))

    db_module.save_deck_impressions([_row(i, "{}") for i in range(n)])

    assert _count(mem_engine) == n
    assert len(statements) == math.ceil(n / 7)
    assert max(statements) <= 7


def test_default_page_bounds_statement_size(mem_engine):
    """At the production default, a 1,400-row deck of ~21 KB rows never
    renders a statement anywhere near the size that crashed Postgres."""
    payload = "x" * 21_000
    n = 1_400
    sizes: list[int] = []

    @event.listens_for(mem_engine, "before_cursor_execute")
    def _capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("INSERT"):
            params = parameters if executemany else [parameters]
            sizes.append(sum(len(str(v)) for p in params for v in
                             (p.values() if hasattr(p, "values") else p)))

    db_module.save_deck_impressions([_row(i, payload) for i in range(n)])

    assert _count(mem_engine) == n
    assert len(sizes) == math.ceil(n / db_module.DECK_IMPRESSION_INSERT_ROWS)
    # 100 rows x ~21 KB ≈ 2.1 MB per statement, against ~28 MB before.
    assert max(sizes) < 3_000_000


def test_empty_and_single_page_unchanged(mem_engine):
    db_module.save_deck_impressions([])
    assert _count(mem_engine) == 0
    db_module.save_deck_impressions([_row(0, "{}")])
    assert _count(mem_engine) == 1


def test_page_failure_rolls_back_whole_deck(mem_engine, monkeypatch):
    """All-or-nothing is preserved: a duplicate key on a later page leaves
    zero rows, exactly as the single-statement insert did."""
    monkeypatch.setattr(db_module, "DECK_IMPRESSION_INSERT_ROWS", 5)
    rows = [_row(i, "{}") for i in range(12)]
    rows[11]["impression_id"] = rows[0]["impression_id"]     # page 3 collides
    with pytest.raises(Exception):
        db_module.save_deck_impressions(rows)
    assert _count(mem_engine) == 0

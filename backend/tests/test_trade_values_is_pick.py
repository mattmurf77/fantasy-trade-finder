"""`GET /api/trade/values` — explicit pick identity on the wire (B3 follow-up).

WHY THIS EXISTS. The universal pool's 12 generic draft-pick rungs are stamped
with a **FAKE player position** (`_PICK_POS = {1:"RB",2:"WR",3:"TE",4:"QB"}`,
`build_universal_pool` in backend/server.py) so they distribute across the
trio/rank position tabs, and were marked as picks by `team == "PICK"` ALONE.
Five clients each re-derived pick identity from that magic string, and two
shipped bugs came out of getting it wrong: feedback #222 (picks leaking into
free agents) and the 2026-08-18 B3 sweep (the calculator's PICK filter matched
nothing while RB/WR/TE/QB wrongly listed picks).

`is_pick` makes the identity explicit. Two properties are load-bearing and
each has its own assertion below:

  1. It is DERIVED from the canonical predicate `trade_service.is_pick_asset`
     (backend/trade_service.py) — not a second implementation that can drift.
  2. It is ADDITIVE. `_PICK_POS` stays, `team == "PICK"` stays, and every
     pre-existing key keeps its exact pre-change value, so unmigrated clients
     and cached responses are byte-identical apart from the new key.

Run: python3 -m pytest backend/tests/test_trade_values_is_pick.py -q
"""

from dataclasses import dataclass

import pytest

import backend.server as srv

# Verbatim from `build_universal_pool` (backend/server.py, the `_PICK_POS`
# local). Re-declared here on purpose: the whole point of the bug is that a
# generic rung does NOT carry position "PICK", so the fixture has to reproduce
# the real, misleading shape rather than a convenient one.
_PICK_POS = {1: "RB", 2: "WR", 3: "TE", 4: "QB"}

# The pre-change response keys. If a future change drops or renames one of
# these, `test_existing_fields_are_byte_identical` fails loudly.
_LEGACY_KEYS = {"id", "name", "position", "team", "age", "value", "tier"}


@dataclass
class _P:
    id: str
    name: str
    position: str
    team: str | None = None
    age: int | None = None


# Real players — none of them a pick, including one whose team is genuinely
# absent (a free agent) so `team=None` can never be mistaken for pick-ness.
_REAL = [
    _P("stud",  "Stud Man",   "WR", "CIN", 26),
    _P("good",  "Good Guy",   "RB", "DET", 24),
    _P("bench", "Bench Body", "TE", None,  28),   # FA — team is None
    _P("qb1",   "Signal One", "QB", "BUF", 27),
]

# Every generic rung the real pool builds, in its real (fake-position) shape.
_RUNGS = [
    _P(f"generic_pick_{rnd}_{tier.lower()}",
       srv.generic_pick_label(rnd, tier),
       _PICK_POS.get(rnd, "QB"),
       "PICK", 0)
    for (rnd, tier) in srv.GENERIC_PICK_SEEDS
]

# Owned-pick pseudo-players (`server._owned_pick_assets`). The second one
# deliberately carries `team=None` so the predicate's `position == "PICK"`
# arm is exercised on its own — neither arm may be dropped.
_OWNED = [
    _P("L1_2027_1_5", "2027 1st", "PICK", "PICK", 0),
    _P("L1_2028_2_3", "2028 2nd", "PICK", None,   0),
]

_POOL = _REAL + _RUNGS + _OWNED

_SEED = {
    "stud": 1800.0, "good": 1650.0, "bench": 1350.0, "qb1": 1700.0,
    **{p.id: seed for p, seed in
       zip(_RUNGS, srv.GENERIC_PICK_SEEDS.values())},
    "L1_2027_1_5": 1620.0, "L1_2028_2_3": 1430.0,
}

_PICK_IDS = {p.id for p in _RUNGS} | {p.id for p in _OWNED}
_PLAYER_IDS = {p.id for p in _REAL}


@pytest.fixture(autouse=True)
def _pool(monkeypatch):
    monkeypatch.setattr(srv, "_ensure_universal_pools", lambda: None)
    monkeypatch.setitem(
        srv.g_universal_by_format, "1qb_ppr",
        {"players": _POOL, "seed": dict(_SEED)},
    )
    yield


def _rows(fmt="1qb_ppr"):
    with srv.app.test_client() as c:
        r = c.get(f"/api/trade/values?scoring_format={fmt}")
        assert r.status_code == 200
        return {row["id"]: row for row in r.get_json()["players"]}


# ── 1. The field exists, on every row, as a real bool ────────────────────

def test_every_row_carries_a_boolean_is_pick():
    rows = _rows()
    assert set(rows) == {p.id for p in _POOL}
    assert all(isinstance(r["is_pick"], bool) for r in rows.values()), \
        "is_pick must serialize as a JSON boolean, not a truthy string/int"


# ── 2. True for picks, false for players ─────────────────────────────────

def test_is_pick_true_for_every_generic_rung():
    rows = _rows()
    # All 12 rungs — each with its FAKE player position, marked only by team.
    assert len(_RUNGS) == len(srv.GENERIC_PICK_SEEDS) == 12
    for p in _RUNGS:
        assert rows[p.id]["is_pick"] is True, f"{p.id} ({p.position}) not flagged"
        # The magic string survives untouched — this is additive, not a fix.
        assert rows[p.id]["position"] == p.position != "PICK"
        assert rows[p.id]["team"] == "PICK"


def test_is_pick_true_for_owned_picks_including_teamless_rows():
    rows = _rows()
    for p in _OWNED:
        assert rows[p.id]["is_pick"] is True, f"{p.id} not flagged"
    # The `position == "PICK"` arm carries the teamless row on its own.
    assert rows["L1_2028_2_3"]["team"] is None


def test_is_pick_false_for_real_players_including_free_agents():
    rows = _rows()
    for pid in _PLAYER_IDS:
        assert rows[pid]["is_pick"] is False, f"{pid} wrongly flagged as a pick"
    assert rows["bench"]["team"] is None      # a missing team is not a pick


# ── 3. Derived from the CANONICAL predicate, not re-implemented ──────────

def test_is_pick_follows_trade_service_is_pick_asset(monkeypatch):
    """Sabotage-shaped: swap the canonical predicate for an inverted one. If
    the route derived pick-ness from its own copy of `position/team == 'PICK'`
    this test would not move — the whole point is that it does."""
    canonical = srv._trade_service_mod.is_pick_asset
    monkeypatch.setattr(srv._trade_service_mod, "is_pick_asset",
                        lambda p: not canonical(p))
    rows = _rows()
    for pid in _PICK_IDS:
        assert rows[pid]["is_pick"] is False
    for pid in _PLAYER_IDS:
        assert rows[pid]["is_pick"] is True


def test_is_pick_matches_the_canonical_predicate_row_for_row():
    rows = _rows()
    from backend.trade_service import is_pick_asset
    for p in _POOL:
        assert rows[p.id]["is_pick"] is bool(is_pick_asset(p))


# ── 4. ADDITIVE ONLY — nothing else on the wire moved ────────────────────

def test_response_keys_are_the_legacy_set_plus_is_pick_exactly():
    rows = _rows()
    for r in rows.values():
        assert set(r) == _LEGACY_KEYS | {"is_pick"}, \
            "the row shape gained or lost a key beyond `is_pick`"


def test_existing_fields_are_byte_identical():
    """Every pre-existing key still holds the value the pre-change serializer
    produced, computed here from the pool + seed independently of the route."""
    rows = _rows()
    e2v = srv._trade_service_mod.elo_to_value
    for p in _POOL:
        expected = {
            "id":       p.id,
            "name":     p.name,
            "position": p.position,
            "team":     p.team,
            "age":      p.age,
            "value":    round(e2v(_SEED[p.id]), 1),
            "tier":     srv.RankingService.tier_for_elo(
                _SEED[p.id], p.position, "1qb_ppr"),
        }
        got = {k: v for k, v in rows[p.id].items() if k != "is_pick"}
        assert got == expected, f"{p.id} drifted"


def test_ordering_and_envelope_unchanged():
    with srv.app.test_client() as c:
        r = c.get("/api/trade/values?scoring_format=1qb_ppr")
        body = r.get_json()
        assert set(body) == {"scoring_format", "players"}
        assert body["scoring_format"] == "1qb_ppr"
        vals = [row["value"] for row in body["players"]]
        assert vals == sorted(vals, reverse=True)      # still value-desc
        # ETag/304 revalidation still works (the payload changed, so the tag
        # rotates — that is the intended cache-bust, not a regression).
        etag = r.headers["ETag"]
        assert r.headers["Cache-Control"] == \
            "public, max-age=300, stale-while-revalidate=3600"
        r2 = c.get("/api/trade/values?scoring_format=1qb_ppr",
                   headers={"If-None-Match": etag})
        assert r2.status_code == 304

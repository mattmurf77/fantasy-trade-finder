"""Home's next move: ONE player and ONE action for the team's current direction.

Scope: docs/plans/home-next-move/scope.md (flag `league.next_move`, D-278).
Composed on the forecast read from three blocks that same read already
serves: `team_direction` (the direction, which follows the saved outlook and
the playoff chance), `max_pf_moves` (draft-pick direction: SELL its first
row) and `playoff_targets` (playoff direction: BUY its first row). No
simulation, nothing saved, no weekly-job work. Pure: callers check the flag
and pass the blocks in; nothing here reads a flag, the database or the
network.

The rule: never name a move the list it comes from would not show as its
first row right now, with its "Find trades" button, and with nothing in
front of it (the "Show moves" / "Show anyway" steps; the draft-order
question shows above the rows and hides nothing). Where the first row is not usable the answer is "none" with a
reason, never the second row. The one check the server cannot make is the
live roster (the forecast read never fetches rosters); the app makes it with
the same live rosters the lists use: the player still on the viewer's
roster (sell) or on `seller.roster_id`'s roster (buy).
"""
from __future__ import annotations

from . import team_direction

VERSION = 1


def _none(reason, direction=None):
    return {"version": VERSION, "state": "none", "reason": reason, "direction": direction, "action": None,
            "player": None, "rank": None, "seller": None, "captured_at": None, "playoff_probability": None,
            "playoff_proof": None, "pick": None, "most_likely_pick": None, "top3_probability": None}


def _first(rows):
    """The list's first row: the lowest rank, as the app's list sorts it."""
    rows = [r for r in rows or [] if isinstance(r, dict)]
    return min(rows, key=lambda r: r.get("rank") or 0) if rows else None


def _player(row):
    return {"player_id": str(row["player_id"]), "name": row["name"], "short_name": row["short_name"],
            "position": row["position"]}


def _proof(baseline):
    return {"playoff_clinched": bool((baseline or {}).get("playoff_clinched")),
            "playoff_eliminated": bool((baseline or {}).get("playoff_eliminated"))}


def _sell(block):
    """Draft-pick direction: the first Max PF moves row, or why not."""
    if not isinstance(block, dict) or block.get("state") != "ready":
        return _none("no_moves", "draft_pick")
    baseline = block.get("baseline") or {}
    # The owner gate: the list sits behind "Show anyway".
    if (block.get("pick_owner") or {}).get("owns_own_pick") is not True:
        return _none("pick_owned_elsewhere", "draft_pick")
    # The list starts collapsed behind "Show moves" (the section's own
    # default-open rule, which is the card's lean): the card fell back to the
    # draft pick only because the playoffs are not offered.
    probability = baseline.get("playoff_probability")
    if probability is None or team_direction.lean(probability, block.get("saved_outlook")) != "draft_pick":
        return _none("collapsed", "draft_pick")
    if baseline.get("playoff_clinched"):
        return _none("settled", "draft_pick")
    row = _first(block.get("rows"))
    if row is None:
        return _none("no_moves", "draft_pick")
    if row.get("keep"):
        return _none("keep", "draft_pick")
    if not row.get("passes_threshold"):
        return _none("below_threshold", "draft_pick")
    return {**_none(None, "draft_pick"), "state": "ready", "action": "sell", "player": _player(row),
            "rank": row["rank"], "captured_at": block.get("captured_at"),
            "playoff_probability": dict(row["playoff_probability"]), "playoff_proof": _proof(baseline),
            "pick": {"now": row["label"]["now"], "after": row["label"]["after"]},
            "most_likely_pick": row.get("most_likely_pick"),
            "top3_probability": dict(row["top3_probability"])}


def _buy(block):
    """Playoff direction: the first Playoff targets row, or why not."""
    if not isinstance(block, dict) or block.get("state") != "ready":
        return _none("no_targets", "playoffs")
    baseline = block.get("baseline") or {}
    if baseline.get("playoff_clinched") or baseline.get("playoff_eliminated"):
        return _none("settled", "playoffs")
    row = _first(block.get("rows"))
    if row is None:
        return _none("no_targets", "playoffs")
    if not row.get("passes_threshold"):
        return _none("below_threshold", "playoffs")
    seller = row.get("seller") or {}
    return {**_none(None, "playoffs"), "state": "ready", "action": "buy", "player": _player(row),
            "rank": row["rank"], "captured_at": block.get("captured_at"),
            "seller": {"roster_id": seller.get("roster_id"), "name": seller.get("name")},
            "playoff_probability": dict(row["playoff_probability"]), "playoff_proof": _proof(baseline)}


def compose(direction, max_pf_block=None, targets_block=None):
    """The `next_move` block served on the forecast read.

    direction      the `team_direction` block this same read serves, or None
                   (flag `league.direction_card` off)
    max_pf_block   the served `max_pf_moves` block, or None (flag off)
    targets_block  the served `playoff_targets` block, or None (flag off)
    """
    if not isinstance(direction, dict):
        return _none("direction_off")
    if direction.get("state") != "ready":
        return _none("unavailable")
    primary = direction.get("primary")
    if primary not in ("draft_pick", "playoffs"):
        return _none("no_direction")
    if not ((direction.get("options") or {}).get(primary) or {}).get("offered"):
        return _none("not_offered", primary)
    return _sell(max_pf_block) if primary == "draft_pick" else _buy(targets_block)


def read_failed():
    """The block when composing it failed: nothing suggested."""
    return _none("read_failed")

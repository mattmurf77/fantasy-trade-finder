"""Founders' review: the founder-only player label review (docs/plans/founder-review/design.md).

A leaf: no server, flag or database imports. `server.py` owns the access predicate, the
reads and the write; this module owns the vocabulary, the write validation and the
page's rows and summary, built from a revision 5 search (`trade_gen_bilateral_season`)
whose profile already carries the founder's overrides (`season_value.league_profile`).

Vocabulary and band order are a cross-client invariant (docs/cross-client-invariants.md;
mobile `src/utils/founderReview.ts` mirrors them, pinned by `check-founder-review.js`).
"""
from __future__ import annotations

from collections import Counter

from .season_value import OVERRIDE_LABELS, POSITIONS, SCOPE_ALL, override_scope, qb_scope

SCHEMA = "founder-label-review-1"
LABELS = OVERRIDE_LABELS                                  # what an override may hold
BANDS = ("cornerstone", "win_now", "rebuild", "depth", "none")   # the page's band order
MAX_ENTRIES = 1000


class InvalidRequest(ValueError):
    """A write the route answers 400 with `code` and `ids`; nothing is written."""

    def __init__(self, code, ids=()):
        super().__init__(code)
        self.code, self.ids = code, sorted(ids)


def parse_write(body, *, known, stored, slots):
    """Validate a write body into ({(player_id, scope): label}, [(player_id, scope)]).

    known: {player_id: position} of the league's player pool; stored: the (player_id,
    scope) keys with a row; slots: this league's lineup slots, which fix a QB's scope
    (`override_scope`: the league's QB format; `all` for RB / WR / TE). `set` ids must be
    QB/RB/WR/TE players in the pool (picks and unknown ids refused); `clear` ids must be
    pool players or have a stored row in a scope this league can see. Raises InvalidRequest."""
    if not isinstance(body, dict):
        raise InvalidRequest("body_must_be_an_object")
    to_set, to_clear = body.get("set") or {}, body.get("clear") or []
    if not isinstance(to_set, dict) or not isinstance(to_clear, list):
        raise InvalidRequest("set_must_be_an_object_and_clear_a_list")
    if len(to_set) + len(to_clear) > MAX_ENTRIES:
        raise InvalidRequest("too_many_entries")
    to_set = {str(pid): label for pid, label in to_set.items()}
    clear_ids = sorted({str(pid) for pid in to_clear})
    bad_label = [pid for pid, label in to_set.items() if label not in LABELS]
    if bad_label:
        raise InvalidRequest("unknown_label", bad_label)
    both = set(to_set) & set(clear_ids)
    if both:
        raise InvalidRequest("set_and_clear_overlap", both)
    visible = {SCOPE_ALL, qb_scope(slots)}
    unknown = [pid for pid in to_set if known.get(pid) not in POSITIONS]
    unknown += [pid for pid in clear_ids if known.get(pid) not in POSITIONS
                and not any((pid, scope) in stored for scope in visible)]
    if unknown:
        raise InvalidRequest("unknown_player", unknown)
    keys = {pid: ([override_scope(known[pid], slots)] if known.get(pid) in POSITIONS
                  else [scope for scope in sorted(visible) if (pid, scope) in stored])
            for pid in (*to_set, *clear_ids)}
    return ({(pid, keys[pid][0]): label for pid, label in to_set.items()},
            [(pid, scope) for pid in clear_ids for scope in keys[pid]])


def rows(search, stored, slots):
    """The page's player rows for one league: every rostered QB/RB/WR/TE (picks are
    always `rebuild` and are left out). `label` is the label the engine uses here (after
    any override), `engine_label` the rule's own, `override` the stored value in the scope
    this league reads for him (`all`, or the league's QB format for a QB; possibly set in
    another league), `movable_to` the bands a move may target here.
    stored: {(player_id, scope): label}."""
    profile, ppg = search._profile, search._season_ppg
    out = []
    for team in search.teams.values():
        for pid in sorted(team["roster"]):
            pos = search._position(pid)
            if pos not in POSITIONS:
                continue
            info = profile["players"].get(pid) or {}
            player = search.players[pid]
            label = info.get("label")
            startable = info.get("startable")
            out.append({
                "id": pid, "name": player.name, "position": pos,
                "team": getattr(player, "team", None), "age": player.age,
                "ppg": ppg.get(pid), "line": profile["line"].get(pos),
                "value": round(search.market.get(pid, 0.0), 1), "future": info.get("future"),
                "startable": startable, "label": label,
                "engine_label": info.get("engine_label", label),
                "override": stored.get((pid, override_scope(pos, slots))),
                "why_unlabelled": (None if label is not None else
                                   "unprojected" if pid not in ppg else "borderline"),
                "movable_to": movable_to(label, startable),
            })
    out.sort(key=lambda r: (-(r["value"] or 0.0), r["id"]))
    return out


def movable_to(label, startable):
    """design.md §2.2: a starter may be a cornerstone or a win-now piece; a bench player a
    rebuild piece or depth; a borderline or unprojected player cannot be moved here."""
    if label is None or startable is None:
        return []
    return ["cornerstone", "win_now"] if startable else ["rebuild", "depth"]


def summary(player_rows, overrides_total):
    """Aggregates only (design.md §6): per position, players moved here and the most
    common engine -> founder corrections. No player ids."""
    positions = {}
    for pos in POSITIONS:
        moved = Counter((r["engine_label"], r["label"]) for r in player_rows
                        if r["position"] == pos and r["label"] != r["engine_label"])
        positions[pos] = {"moved": sum(moved.values()),
                          "corrections": [{"from": a, "to": b, "count": n}
                                          for (a, b), n in sorted(moved.items(), key=lambda kv: (-kv[1], kv[0]))]}
    return {"positions": positions, "overrides_total": overrides_total,
            "overrides_here": sum(1 for r in player_rows if r["override"] is not None)}


def page(search, evidence, stored):
    """The read route's body. Without usable evidence: no rows, and `evidence` says why.
    `qb_scope`: the QB format this league's QB rows are read and written under."""
    shown = {"state": evidence.get("state"), "reason": evidence.get("reason"),
             "weeks": evidence.get("weeks") or [], "captured_at": evidence.get("captured_at")}
    slots = evidence.get("slots") or []
    player_rows = rows(search, stored, slots) if search is not None else []
    return {"schema": SCHEMA, "labels": list(LABELS), "bands": list(BANDS), "evidence": shown,
            "qb_scope": qb_scope(slots) if search is not None else None,
            "line": dict(search._profile["line"]) if search is not None else {},
            "players": player_rows, "summary": summary(player_rows, len(stored))}

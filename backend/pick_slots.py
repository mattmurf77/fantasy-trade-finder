"""Current-season draft-slot resolution for owned picks (D-090).

ONE job: turn an owned `draft_picks` row into the slot it actually occupies in
its league's draft, so a card can read **"2026 1.08"** instead of the generic
**"2026 1st"**. Display only — nothing here prices anything.

Why a slot is derivable at all
------------------------------
`draft_picks`' grain is ``(league, season, round, original_roster)``. A slot is
a pure function of ``(original_roster, round-1 order, order shape)``: the pick
that was originally roster R's sits at whatever position R holds in the draft
order. So the slot is not new information — it is the ORDER composed with a
column we already store.

**The order is stored; the slot never is.** This is the rule
``PickAssignmentScreen.tsx`` already follows for user-assigned ESPN boards
(D18): a commissioner reordering the draft must renumber every slot without
touching a single owner, which a denormalized ``draft_picks.slot`` would make
impossible to do correctly. `overall`/`slot` stay off the row; the order lives
on the league.

Two sources, both already paid for
----------------------------------
* **Sleeper** — ``GET /v1/league/<id>/drafts`` returns ``draft_order``
  (user_id -> slot) *on the list object itself*, and that call is already made
  by ``server._sync_sleeper_owned_picks`` for the #228 exclusion. Composed with
  the ``roster_id -> user_id`` map that same function already holds, it yields
  ``roster_id -> slot`` for **zero additional upstream egress**. Verified
  against the operator's league 2026-08-19: the composition reproduces Sleeper's
  own ``slot_to_roster_id`` exactly.
* **User-assigned (ESPN)** — ``leagues.pick_assignment_settings`` already
  persists ``{order: [user_id, ...], order_type, rounds}``. Index + 1 is the
  slot. Zero egress, and it makes a trade card agree with the very Pick
  Assignment screen the league typed the order into.

MFL is deliberately unsupported: its order lives in ``round1DraftOrder`` inside
an authed ``TYPE=draftResults`` fetch that the pick-sync path does not make, so
supporting it would mean buying a new upstream call for a label. An MFL league
keeps the generic label, honestly.

Three refusals, each one deliberate
-----------------------------------
1. **``slot_to_roster_id`` is never read** (the D5 rule in
   ``draft_board_service``). Pre-draft Sleeper returns the identity map
   ``{"1":1 … "12":12}``, which reads as a plausible order and is not one.
   ``draft_order`` is the only slot source; when it is null we say so.
2. **Future seasons never get a slot** (#273). Nobody knows 2027's order, so a
   slot there is fiction. The stored order is stamped with its season and
   :func:`slot_for` refuses any other one.
3. **A snake draft with ``reversal_round`` set gets no slot.** Same reasoning as
   ``draft_board_service._pick_no``: third-round reversal changes the parity in
   a way we have no live payload to verify against, and a wrong slot is worse
   than a generic round.

The module is dependency-free on purpose — no Flask, no ``database``, no HTTP.
Callers fetch and persist; this decides.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

log = logging.getLogger(__name__)

#: Bumped only if the stored blob's shape changes incompatibly. A row carrying
#: an unrecognised version is ignored rather than guessed at, which degrades to
#: today's generic label.
SCHEMA = 1

#: Provenance of a resolved order, for the record and for debugging.
SRC_SLEEPER_DRAFT_ORDER = "sleeper_draft_order"
SRC_ASSIGNMENT_SETTINGS = "assignment_settings"

TYPE_LINEAR = "linear"
TYPE_SNAKE = "snake"


def _int_or_none(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Building an order
# ---------------------------------------------------------------------------

def _order_blob(season: int, slots: dict[str, int], *, teams: int,
                draft_type: str, reversal_round: int, source: str) -> dict | None:
    """The stored shape, or None when the inputs cannot make an honest one."""
    if not slots or not teams or teams <= 0:
        return None
    return {
        "schema":         SCHEMA,
        "season":         int(season),
        "teams":          int(teams),
        "type":           draft_type,
        "reversal_round": int(reversal_round or 0),
        "slots":          {str(k): int(v) for k, v in slots.items()},
        "source":         source,
    }


def order_from_sleeper_drafts(drafts: Sequence[Any],
                              roster_id_to_user: Mapping[str, str],
                              season: int,
                              teams: int | None = None) -> dict | None:
    """``roster_id -> slot`` for `season`, from Sleeper's ``/league/<id>/drafts``.

    `drafts` is the raw list; `roster_id_to_user` is the map
    ``server._sync_sleeper_owned_picks`` already builds from the rosters read.

    Returns None — never a partial or invented order — when:
      * no draft object matches `season`;
      * that draft's ``draft_order`` is null (the order is genuinely unset, the
        common pre-draft state — see the D5 rule in the module docstring);
      * the composition resolves no rosters at all (every ``draft_order`` key is
        a user this league's rosters do not know).

    A PARTIAL resolution is kept: a co-owned team keyed in ``draft_order`` by a
    co-owner resolves no roster, and the honest answer is a slot for the eleven
    teams we can place and a generic label for the twelfth, not a generic label
    for all twelve. :func:`slot_for` returns None per missing roster.
    """
    user_to_roster: dict[str, str] = {}
    for rid, uid in (roster_id_to_user or {}).items():
        if uid:
            user_to_roster.setdefault(str(uid), str(rid))

    for d in drafts or []:
        if not isinstance(d, dict):
            continue
        if _int_or_none(d.get("season")) != int(season):
            continue
        draft_order = d.get("draft_order")
        if not isinstance(draft_order, dict) or not draft_order:
            return None                     # unset order — never invented (D5)
        settings = d.get("settings") if isinstance(d.get("settings"), dict) else {}
        n_teams = (_int_or_none(teams)
                   or _int_or_none(settings.get("teams"))
                   or len(user_to_roster) or None)
        slots: dict[str, int] = {}
        for uid, slot in draft_order.items():
            slot_i = _int_or_none(slot)
            rid = user_to_roster.get(str(uid))
            if slot_i and rid is not None:
                slots[rid] = slot_i
        if not slots or not n_teams:
            return None
        return _order_blob(
            season, slots,
            teams=n_teams,
            draft_type=str(d.get("type") or "") or TYPE_LINEAR,
            reversal_round=_int_or_none(settings.get("reversal_round")) or 0,
            source=SRC_SLEEPER_DRAFT_ORDER,
        )
    return None


def order_from_assignment_settings(settings: Mapping[str, Any] | None,
                                   season: int,
                                   user_to_roster: Mapping[str, str]) -> dict | None:
    """``roster_id -> slot`` from a league's stored user-entered numbering.

    `settings` is ``database.load_pick_assignment_settings``' blob
    (``{order: [user_id, ...], order_type, rounds}``); `user_to_roster` maps
    ``original_user_id -> original_roster_id`` for the season's rows, which is
    how an assigned board's ids reach the ``draft_picks`` grain.

    This is the ESPN path. `season` is stamped so the same #273 refusal applies:
    a typed-in order describes THIS year's board, not next year's.
    """
    if not isinstance(settings, Mapping):
        return None
    order = settings.get("order")
    if not isinstance(order, list) or not order:
        return None
    order_type = str(settings.get("order_type") or TYPE_LINEAR)
    slots: dict[str, int] = {}
    for i, uid in enumerate(order):
        rid = (user_to_roster or {}).get(str(uid))
        if rid is not None:
            slots[str(rid)] = i + 1
    return _order_blob(
        season, slots,
        teams=len(order),
        draft_type=TYPE_SNAKE if order_type == TYPE_SNAKE else TYPE_LINEAR,
        reversal_round=0,
        source=SRC_ASSIGNMENT_SETTINGS,
    )


# ---------------------------------------------------------------------------
# Reading an order
# ---------------------------------------------------------------------------

def slot_for(order: Mapping[str, Any] | None, season: Any, round_: Any,
             original_roster_id: Any) -> int | None:
    """The 1-based slot of one pick within its round, or None.

    None means "not resolvable, use the generic round label" and is returned for
    every case the module refuses (module docstring, refusals 1–3), plus the
    ordinary ones: a different season, an unknown roster, a malformed blob.

    Snake numbering reverses the EVEN rounds, exactly as
    ``PickAssignmentScreen.draftPosition`` does client-side — the two must agree
    or the picks screen and the trade card disagree about the same pick.
    """
    if not isinstance(order, Mapping):
        return None
    if _int_or_none(order.get("schema")) != SCHEMA:
        return None
    if _int_or_none(order.get("season")) != _int_or_none(season):
        return None                          # #273 — a future season has no order
    rnd = _int_or_none(round_)
    if not rnd or rnd < 1:
        return None
    slots = order.get("slots")
    if not isinstance(slots, Mapping):
        return None
    base = _int_or_none(slots.get(str(original_roster_id)))
    if not base or base < 1:
        return None
    teams = _int_or_none(order.get("teams")) or 0
    if teams and base > teams:
        return None
    draft_type = str(order.get("type") or TYPE_LINEAR)
    if draft_type == TYPE_SNAKE:
        if _int_or_none(order.get("reversal_round")):
            return None                      # unverifiable parity — refuse
        if not teams:
            return None
        if rnd % 2 == 0:
            return teams + 1 - base
    return base


def slot_suffix(round_: Any, slot: int) -> str:
    """``(1, 8)`` -> ``"1.08"``. The zero-padded form every other slot label in
    the app already uses (``PickAssignmentScreen.slotLabel``,
    ``DraftRows.slotLabel``, ``data_loader.pick_slot_label``)."""
    return f"{int(round_)}.{int(slot):02d}"

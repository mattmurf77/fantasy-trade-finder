"""Shared draft-pick value ladder — single source of truth for pick pricing.

Both `server.py` (universal pool, anchor wizard, calculator gap line) and
`database.py` (owned-pick sync via `sync_draft_picks`) need the generic-pick
Elo ladder and the value-space `pool_value` reconciliation. Historically the
ladder lived in `server.py`, but `database.py` must not import `server.py`
(import cycle), so the ladder moved here — imported by both. This is also the
home the pick-denominated-values item (#157) leans on, so the mapping can't
drift between features.

`elo_to_value` is imported lazily from `trade_service` inside the helper to
avoid any module-load import cycle (trade_service pulls in feature_flags /
trade_narrative at import time; keeping the dependency lazy keeps this module
import-safe from anywhere).
"""

# ── Generic draft-pick assets (shared constants) ───────────────────────────
# Elo seeds for the 12 generic Early/Mid/Late picks (rounds 1–4) injected into
# the universal pool, calibrated to typical dynasty trade values. Module-scoped
# because they double as the reference ladder for pick-denominated features:
# the pick-anchor wizard (/api/anchor/save) and the calculator's gap-to-pick
# equivalence (/api/trade/evaluate `gap`). The MID column of each round is the
# canonical "a 1st / a 2nd / …" anchor; a generic Mid 1st is the base unit.
GENERIC_PICK_SEEDS: dict[tuple[int, str], float] = {
    # (round, tier): elo_seed
    (1, "Early"):  1720,   # ~top-3 pick: elite rookie prospect
    (1, "Mid"):    1650,   # ~mid-1st: solid first-round value (BASE FIRST)
    (1, "Late"):   1580,   # ~late-1st: still premium but less certain
    (2, "Early"):  1520,   # ~early-2nd: solid starter potential
    (2, "Mid"):    1460,   # ~mid-2nd: depth/upside piece
    (2, "Late"):   1400,   # ~late-2nd: dart throw
    (3, "Early"):  1360,   # ~early-3rd: longshot upside
    (3, "Mid"):    1320,   # ~mid-3rd: roster filler
    (3, "Late"):   1280,   # ~late-3rd: minimal value
    (4, "Early"):  1260,   # ~early-4th: very speculative
    (4, "Mid"):    1240,   # ~mid-4th: low value
    (4, "Late"):   1220,   # ~late-4th: minimal
}
_PICK_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}

# Year discount applied to an owned pick's pool_value per season out. Mirrors
# database._PICK_YEAR_DISCOUNT (the legacy pick_value scale) so the two scales
# discount the future at the same rate — only the base scale differs.
YEAR_DISCOUNT = 0.85   # 15 % off per year out


def generic_pick_label(rnd: int, tier: str) -> str:
    """Display label matching the universal pool's pick naming."""
    return f"{tier} {_PICK_ORDINALS.get(rnd, str(rnd))} Round Pick"


# ── #207: year-explicit rung labels ────────────────────────────────────────
# The 12 rungs keep their stable, league-agnostic ids forever (see
# docs/feedback/items/207-rookie-draft-detection/plan.md, "Option A"); only
# the SERVED label and pick_value become year-explicit, per the active
# league's detected rookie-draft status. Which year "an early 1st" maps to
# depends on the league you are looking through, so the mapping lives at
# serialization time, never in the pool builder.

GENERIC_PICK_ID_PREFIX = "generic_pick_"


def parse_generic_pick_id(pick_id: str) -> tuple[int, str] | None:
    """`generic_pick_1_early` → `(1, "Early")`. None for anything else."""
    if not isinstance(pick_id, str) or not pick_id.startswith(GENERIC_PICK_ID_PREFIX):
        return None
    parts = pick_id[len(GENERIC_PICK_ID_PREFIX):].split("_")
    if len(parts) != 2 or not parts[0].isdigit():
        return None
    rnd, tier = int(parts[0]), parts[1].capitalize()
    if (rnd, tier) not in GENERIC_PICK_SEEDS:
        return None
    return rnd, tier


def year_pick_label(year: int, rnd: int, tier: str) -> str:
    """Year-explicit rung label — e.g. `year_pick_label(2026, 1, "Early")`
    → "2026 Early 1st". Shorter than the year-less form it replaces
    ("Early 1st Round Pick"), so no client name box gets tighter."""
    return f"{int(year)} {tier} {_PICK_ORDINALS.get(rnd, str(rnd))}"


def discount_pick_value(pick_value: float, years_out: int) -> float:
    """Apply the year discount to a rung's `pick_value` in VALUE space.

    `pick_value` is the universal pool's engine bridge — the pool builder
    sets it to `(seed_elo - 1200) / 6` and `dynasty_value` inverts it as
    `1200 + 6 * pick_value` (#185). Discounting has to happen on the value
    side of that bridge (the same round-trip `_owned_pick_assets` does), not
    on the linear pick_value scale, so a relabelled 2027 rung prices exactly
    like the owned 2027 pick of the same round: `pick_pool_value(r, 1)`.

    `years_out=0` is an exact no-op, which is what keeps a not-drafted
    league byte-identical to today's payload.
    """
    if years_out <= 0:
        return pick_value
    from .trade_service import elo_to_value as _e2v, value_to_elo as _v2e
    elo = 1200.0 + 6.0 * max(0.0, float(pick_value))
    discounted = _e2v(elo) * (YEAR_DISCOUNT ** int(years_out))
    return round(max(0.0, (_v2e(discounted) - 1200.0) / 6.0), 1)


def pick_pool_value(round_: int, years_out: int,
                    scoring_format: str = "1qb_ppr") -> float:
    """Generic-ladder Mid-tier value of a round, year-discounted in VALUE space.

    A league pick of `(round, years_out)` is priced at the generic ladder's
    **Mid** tier of that round (operator decision 2026-07-18 — we can't yet
    resolve a pick's slot), then discounted by `YEAR_DISCOUNT ** years_out` in
    value space (mirroring the anchor wizard's value→elo round-trip).

    `years_out=0` → exactly the generic 'Mid <round>' pool pick's value, so a
    league 1st reconciles with GENERIC_PICK_SEEDS[(1,'Mid')] by construction.

    `scoring_format` is plumbing for a future SF/2QB pick premium (Decision
    D3): pick value is format-agnostic in v1, so it is currently unused.
    """
    from .trade_service import elo_to_value as _e2v
    base_elo = GENERIC_PICK_SEEDS.get(
        (round_, "Mid"), GENERIC_PICK_SEEDS[(4, "Mid")])   # clamp deep rounds
    base_val = _e2v(base_elo)
    return round(base_val * (YEAR_DISCOUNT ** max(0, years_out)), 1)


# ═══════════════════════════════════════════════════════════════════════════
# M6b — market slot pricing (`trade.slot_pricing`, plan operator decision O2)
# ═══════════════════════════════════════════════════════════════════════════
#
# ⚠️  LLD/HLD-vs-OPERATOR CONFLICT, stated where the code lives.
# `hld.md` KD-9 and `lld.md` §4.7 record engine adoption of DynastyProcess
# slot values as **rejected** ("display-only"). Both predate the
# **Operator decisions — 2026-08-06** block at the bottom of
# `docs/plans/rookie-draft/plan.md`. Decision **O2 REVERSES them**: market
# slot values DO go into the trade engine, behind a #214-style per-user
# toggle, in this wave (M6b). Where those documents and the operator block
# disagree, the operator block wins. The same conflict is called out in
# `backend/data_loader.py`'s M6 section header and in
# `docs/plans/rookie-draft/build-m6b.md` §"LLD/HLD vs O2".
#
# WHAT THIS DOES NOT TOUCH — deliberately, and this is load-bearing:
#
#   * `GENERIC_PICK_SEEDS` is byte-unchanged in EVERY mode. The 12 generic
#     rungs are RANKABLE POOL ASSETS (users swipe them in matchups; their
#     seed Elo anchors tier colours) and tier bands are ABSOLUTE Elo mirrored
#     across five clients (docs/cross-client-invariants.md). Repricing the
#     rungs would repaint tier colours everywhere and move a shared,
#     process-global pool for a PER-USER setting. Generic rungs also never
#     appear on a roster, so they are not tradeable assets — they reach a
#     trade only through the manual calculator, where the user's own board
#     Elo already prices them.
#
#   * `draft_picks.pool_value` rows are never rewritten. That column is
#     persisted by a league-wide sync path and SHARED by every user of the
#     league; a per-user pricing mode that rewrote it would silently reprice
#     everyone else. The mode is resolved and applied at READ time, in the
#     request/job that prices the pick — see `priced_pool_value`.
#
# WHAT IT DOES: under `market_slots`, an owned pick's engine value comes from
# DynastyProcess's published market curve for that pick's ABSOLUTE season and
# round, instead of from `pick_pool_value`'s "Mid rung of the round, discounted
# YEAR_DISCOUNT ** years_out".
#
# Keying off the absolute season (not years_out) is intentional: DP publishes
# a distinct price per season, which already embeds the market's own time
# discount, and it makes the price immune to the #228 window where the current
# season's rows are deleted and a `min(season)` recovery of "current season"
# would silently shift every pick a year closer.

PICK_PRICING_MODES = ("tier_ladder", "market_slots")
PICK_PRICING_DEFAULT = "tier_ladder"        # today's behaviour, exactly

# DP publishes rounds 1–5. Our ladder stops at 4; deeper rounds clamp.
_MARKET_MAX_ROUND = 5
_MARKET_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}


# ── THE SLOT-MAPPING DECISION (change it HERE, not in a call site) ─────────
# DP prices per SLOT ("2026 Pick 1.07") for the current class. An owned
# `draft_picks` row carries only `(season, round)` — a slot exists only once
# the platform publishes a draft order, which is true for at most the current
# season and, per #228, only until that draft completes. So a round must map
# to a slot basis.
#
# Basis: the VALUE-SPACE MEAN OF THE ROUND'S MIDDLE TERCILE (slots 5–8 of a
# 12-team round). Two reasons, both checkable:
#   1. It is DP's OWN definition of a "Mid" rung — DP publishes Early/Mid/Late
#      for future seasons, and for 2027 its `Mid 1st` (Elo 1581.7) and its
#      round-generic `1st` (1584.1) agree to 2.4 Elo. Using the mid tercile
#      for the current class therefore makes current-year and future-year
#      prices mean the SAME thing, which a single-slot pick would not.
#   2. It is the market analogue of what ships today: `pick_pool_value` prices
#      every pick at the ladder's **Mid** rung (operator decision 2026-07-18).
#      Same semantics, different source.
# The alternative considered and rejected: the value-space mean of ALL 12
# slots. Round 1 is strongly convex (the 1.01 spike), so the all-slot mean
# (Elo 1658.6) sits ABOVE slot 1.06 (1636.5) — it prices "a 1st" as if you
# held a lottery ticket on the 1.01. The tercile mean (1624.1) does not.
#
# NOT DONE, deliberately: pricing a pick at its TRUE slot when the Draft Room
# has resolved the order. See `docs/plans/rookie-draft/build-m6b.md`
# §"Slot-mapping decision" — the extension point is `_market_round_value`,
# which would take an optional `slot` and skip the tercile.
UNKNOWN_SLOT_BASIS = "mid_tercile"
_TERCILE_TEAMS = 12          # DP publishes a 12-team grid; Early/Mid/Late = 4 slots each


def _basis_slots(round_: int) -> list[int]:
    """The slots whose value-space mean is the price of an unknown-slot pick
    of `round_`. Driven by `UNKNOWN_SLOT_BASIS` so the decision has exactly
    one home."""
    if UNKNOWN_SLOT_BASIS == "all_slots":
        return list(range(1, _TERCILE_TEAMS + 1))
    third = max(1, _TERCILE_TEAMS // 3)
    return list(range(third + 1, 2 * third + 1))      # 12-team → [5, 6, 7, 8]


def _market_round_value(slot_map: dict[str, float], season: int,
                        round_: int) -> float | None:
    """VALUE-space market price of `(season, round_)` from a DP label→Elo map,
    or None when DP publishes nothing for that season/round.

    Lookup order, most specific first:
      1. per-slot rows for the season  → mean over `_basis_slots` (value space)
      2. `"<season> Mid <ordinal>"`    → DP's own mid rung
      3. `"<season> <ordinal>"`        → DP's round-generic rung
    """
    from .trade_service import elo_to_value as _e2v
    ordinal = _MARKET_ORDINALS.get(round_)
    if ordinal is None:
        return None

    slot_elos = [slot_map[lab] for lab in
                 (f"{season} Pick {round_}.{s:02d}" for s in _basis_slots(round_))
                 if lab in slot_map]
    if slot_elos:
        return sum(_e2v(e) for e in slot_elos) / len(slot_elos)

    for label in (f"{season} Mid {ordinal}", f"{season} {ordinal}"):
        if label in slot_map:
            return _e2v(slot_map[label])
    return None


def market_pick_pool_value(season: int, round_: int,
                           scoring_format: str = "1qb_ppr") -> float | None:
    """Market (DynastyProcess) pool_value for one owned pick, or None.

    Same units as the stored `draft_picks.pool_value` — the engine value space
    `trade_service.elo_to_value` produces — so it is a drop-in substitute at
    every read site.

    None means "no market price": DP is unreachable (`load_pick_slot_values`
    fail-softs to `{}`), or the season predates DP's published window. Callers
    fall back to the shipped ladder rather than inventing a number.

    Seasons PAST DP's horizon (it publishes ~3 years out) are extrapolated from
    the deepest published season with the shipped `YEAR_DISCOUNT`, in value
    space — the same discount `pick_pool_value` uses, so the two curves stay
    on one clock out at 2029+ where DP has nothing to say.

    Format-aware by construction (O2/M6 §2.3: DP prices every pick higher in
    superflex — a 2026 1.01 is Elo 1864.3 in `sf_tep` vs 1816.5 in `1qb_ppr`).
    """
    from .data_loader import load_pick_slot_values
    try:
        season, round_ = int(season), max(1, min(int(round_), _MARKET_MAX_ROUND))
    except (TypeError, ValueError):
        return None
    slot_map = load_pick_slot_values(scoring_format)
    if not slot_map:
        return None

    direct = _market_round_value(slot_map, season, round_)
    if direct is not None:
        return round(direct, 1)

    published = set()
    for label in slot_map:
        head = label.split(" ", 1)[0]
        if head.isdigit():
            published.add(int(head))
    if not published:
        return None
    horizon = max(published)
    if season <= horizon:
        return None                    # a gap/past season — not extrapolable
    base = _market_round_value(slot_map, horizon, round_)
    if base is None:
        return None
    return round(base * (YEAR_DISCOUNT ** (season - horizon)), 1)


def priced_pool_value(row: dict, *, scoring_format: str = "1qb_ppr",
                      mode: str | None = None) -> float:
    """The engine value of ONE owned-pick row under the caller's pricing mode.

    THE read-time seam. `row` is a `draft_picks` row as `load_draft_picks`
    returns it; it is never mutated and never written back.

    * `tier_ladder` (default) → `float(row["pool_value"] or 0.0)`, i.e. the
      stored value, byte-identical to today. No DP read is attempted at all.
    * `market_slots` → `market_pick_pool_value(season, round)`, falling back to
      the stored value when DP has no price.

    `mode=None` resolves the thread-local pin (`trade_service`), so a caller
    that has already entered `pick_pricing_override(...)` need not thread it.
    """
    if mode is None:
        from .trade_service import current_pick_pricing_mode
        mode = current_pick_pricing_mode()
    stored = float(row.get("pool_value") or 0.0)
    if mode != "market_slots":
        return stored
    market = market_pick_pool_value(row.get("season"), row.get("round"),
                                    scoring_format)
    return stored if market is None else market

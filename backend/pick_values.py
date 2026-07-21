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

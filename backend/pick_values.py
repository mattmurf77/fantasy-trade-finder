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
    # ── D-084 (2026-08-19) — round 2 deflated toward market. ──────────
    # docs/reviews/2026-08-19-ktc-pick-value-comparison.md. On the only
    # scale-free measure (what player rank is a pick worth), our 1st round
    # was exact (Mid 1st = the 65th asset vs a market median of 66.5) while
    # our Mid 2nd sat at the 119th against a market median of the 141st —
    # 22 ranks too generous. KTC/FantasyCalc/DynastyProcess all agree once
    # read on a common scale. Was 1520/1460/1400; the Mid 2nd:1st ratio
    # falls 0.387 → 0.287 and the Mid 2nd lands at rank ≈136 vs 140.5.
    # DO NOT "fix" this from KTC's published ratio (0.697): that scale is
    # bottom-compressed, and transplanting it would price a mid-2nd as the
    # 86th-best dynasty asset, above George Kittle.
    # Rounds 1/3/4 are deliberately untouched — see the module note below.
    (2, "Early"):  1470,   # ~early-2nd: solid starter potential
    (2, "Mid"):    1400,   # ~mid-2nd: depth/upside piece
    (2, "Late"):   1370,   # ~late-2nd: dart throw (== `second` tier floor)
    (3, "Early"):  1360,   # ~early-3rd: longshot upside
    (3, "Mid"):    1320,   # ~mid-3rd: roster filler
    (3, "Late"):   1280,   # ~late-3rd: minimal value
    (4, "Early"):  1260,   # ~early-4th: very speculative
    (4, "Mid"):    1240,   # ~mid-4th: low value
    (4, "Late"):   1220,   # ~late-4th: minimal
}
_PICK_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}

# ── D-084 module note: what was NOT changed, and how to walk it back ──────
#
# ROUND 1 IS DELIBERATELY UNTOUCHED. It is the one part of the ladder the
# market fully endorses: Mid 1st = the 65th-best asset on our board against a
# market median of 66.5, Early/Late within 10 ranks. Do not "improve" it.
#
# ROUNDS 3 AND 4 ARE NOT FIXABLE HERE, and their apparent 50–70 rank error is
# mostly an artifact, not a pricing opinion. `data_loader.seed_elo_for_value`
# maps DP value 0 → Elo 1200, so the board has almost no resolution below
# rank ~200: measured on the checked-in snapshot, ranks 200→300 span 1262.9 →
# 1208.0 — 100 ranks inside 54.9 Elo points, one EIGHTH the per-rank
# resolution of ranks 50–100. The market-implied Elo for a Mid 4th (1207)
# falls INSIDE the current `waivers` band. Moving 3rd/4th seeds down cannot
# buy rank movement it does not have room for, and the memo measured it
# breaking `test_tier_occupancy.py` in three places when tried. If 3rd/4th
# rank-equivalence is ever revisited, the thing to open is the SEED MAP, not
# this ladder — re-logged as Q-021, and note it moves EVERY player's seed
# Elo, so it is an occupancy-and-deck change, not a pick change.
#
# ⚠️  D-088 (2026-08-19) — DO NOT REACH FOR THIS BLOCK TO EXPLAIN A WRONG
# PICK BADGE. Q-019 asked whether a current-year 3rd badging `second` meant
# the seed map had to be opened. It did not, and this note was cited in
# support of the wrong diagnosis. The badge on GET /api/league/picks was
# computed by inverting `pool_value` (elo_to_value units) with
# `seed_elo_for_value` (which inverts DynastyProcess's raw 0–10000 scale)
# instead of `trade_service.value_to_elo`. The two maps cross at exactly Elo
# 1548.0, so every rung below a mid-1st was inflated — Mid 3rd 1320 read as
# 1383.5, Mid 4th 1240 as 1339.3 — and 1383.5 cleared D-084's new 1370
# `second` floor. The seeds in this dict were never the problem: 1320 sits 45
# Elo INSIDE the `third` band. Fixed display-side; these seeds and every tier
# band are byte-unchanged. docs/reviews/2026-08-19-pick-badge-scale.md.
#
# The invariant that keeps the two honest, and the thing to re-check after ANY
# edit to this dict: a current-year pick of round R must badge exactly where
# GENERIC_PICK_SEEDS[(R, "Mid")] sits, because tier_config.json's
# `_calibration` DEFINES the band floors as these rungs. Equivalently
# `value_to_elo(pick_pool_value(R, 0)) == GENERIC_PICK_SEEDS[(R, "Mid")]`.
# Pinned by test_league_picks_tier.py::test_current_year_rungs_badge_their_own_round.
#
# THESE SEEDS ARE NOT CONFIG-DRIVEN, AND THAT IS DELIBERATE (D-084). The
# sibling change D-079 shipped `model_config` knobs so it could be reverted
# without a deploy; that is the right shape for a rate that prices an asset
# in isolation. It is the WRONG shape here, because the Late rung of each
# round IS that round's tier floor in tier_config.json (see its
# `_calibration`). A knob that moved the seeds without moving the bands
# would silently desynchronise the exact pair this change exists to keep in
# step. tier_config.json is itself read once at process start
# (ranking_service.TIER_CONFIG), so a band change needs a deploy regardless
# — a seeds-only knob would buy no revert speed, only a footgun.
#
# REVERT PATH (no knob — this is the documented alternative): revert the
# single D-084 commit and redeploy. It is self-contained: three seeds here,
# `second.min` / `third.max` across the 8 blocks of tier_config.json, the
# two client fallback mirrors (mobile/src/utils/tierBands.ts,
# web/positional-tiers.html), web/js/app.js's label ladder, and the pinned
# test targets. Render auto-deploys `main`; clients re-fetch /api/tier-config
# at boot, so no client release is required to pick the old bands back up.

# Year discount applied to an owned pick's pool_value per season out. Mirrors
# database._PICK_YEAR_DISCOUNT (the legacy pick_value scale) so the two scales
# discount the future at the same rate — only the base scale differs.
#
# ⚠️  SUPERSEDED AS A PRICING RATE by the per-round ladder below (D-079,
# 2026-08-19). It survives as (a) the round-2..4 default, and (b) the rate
# `market_pick_pool_value` uses to extrapolate PAST DynastyProcess's published
# horizon for rounds it has no per-round opinion about. Read the rate through
# `year_decay(round_)`, never this constant, at any site that prices a pick.
YEAR_DISCOUNT = 0.85   # 15 % off per year out


# ── D-079 — per-round year decay (model_config `pick_year_decay_r{1..4}`) ──
#
# THE DEFECT THIS FIXES (docs/reviews/2026-08-19-pick-year-valuation.md):
# one uniform 0.85/yr priced a 2029 1st at 61.4 % of a 2026 1st (2117.0 →
# 1300.1). That is low enough that the deck served "give Davante Adams,
# receive a 2029 1st" as near-parity (impression c67c2fd1e97cb6bf, prod
# 2026-08-19: give_value 1138.8 vs receive_value 1300.1), and it opened a
# pure YEAR ARBITRAGE between two picks that are the same asset — 99 of 2048
# served cards moved a 1st one way and a different-year 1st the other.
#
# THE MODEL (operator direction, 2026-08-19): "firsts should hold similar
# value YOY. Other picks can degrade the longer away they are." Round 1 is
# therefore FLAT (decay 1.0); rounds 2–4 keep decaying.
#
# ⚠️  ROUND 1 = 1.0 IS AN OPERATOR CALL, NOT A MARKET CALIBRATION, and the
# external evidence runs AGAINST it — every public source we could read
# discounts firsts, and three of four discount firsts HARDER than later
# rounds. DynastyProcess publishes an explicit rule ("80% of the current
# year's value", dynastyprocess.com/values) applied flat to every round;
# FantasyCalc's 2027→2029 CAGR is 0.80 for 1sts but 0.91/0.95/0.98 for
# rounds 2/3/4; KeepTradeCut's 1QB round means are 0.830/0.860/0.860/0.856.
# Nobody prices a far-out 3rd more steeply than a far-out 1st. The operator's
# direction still stands (it is a product decision about what THIS app should
# recommend, and it is what closes the year-arbitrage defect), but the
# disagreement is logged in D-079 / Q-018 and the knob exists so it is one
# config write to walk back. Full numbers and sources:
# docs/reviews/2026-08-19-pick-year-valuation.md.
#
# Rounds 2–4 hold the shipped 0.85 — which is NOT an accident of inertia:
# KTC's raw crowd rates for exactly those rounds are 0.860 / 0.860 / 0.856,
# so 0.85 is the incumbent AND the best-corroborated number available. DP
# (0.80) and FantasyCalc (0.91–0.98) bracket it on either side. Moving it
# would be an unforced repricing; this change stays on the reported defect.
#
# REVERT WITHOUT A DEPLOY: set `pick_year_decay_r1` back to 0.85 in
# model_config and POST /api/admin/config (which calls trade_service.
# reload_config). Every rate reads live through `trade_service._c`, so all
# four rates at 0.85 reproduce today's behaviour exactly, everywhere.
PICK_YEAR_DECAY_DEFAULTS: dict[int, float] = {
    1: 1.00,           # a first is a first — the uncertainty cuts both ways
    2: YEAR_DISCOUNT,
    3: YEAR_DISCOUNT,
    4: YEAR_DISCOUNT,
}
_DECAY_MIN_ROUND, _DECAY_MAX_ROUND = 1, 4


def year_decay_key(round_: int) -> str:
    """model_config key holding the per-year decay for `round_`. Rounds
    outside 1–4 clamp onto the nearest modelled round, exactly as
    `pick_pool_value` clamps deep rounds onto the (4, 'Mid') seed."""
    try:
        r = int(round_)
    except (TypeError, ValueError):
        r = _DECAY_MAX_ROUND
    return f"pick_year_decay_r{max(_DECAY_MIN_ROUND, min(r, _DECAY_MAX_ROUND))}"


def year_decay(round_: int) -> float:
    """Live per-year value multiplier for a pick of `round_`.

    Reads `model_config` through `trade_service._c` (the same live-config
    accessor every other engine knob uses, so a PUT to /api/admin/config takes
    effect on the next reload with no deploy). Clamped to [0, 1]: a rate above
    1 would make a further-out pick worth MORE, which no source supports and
    which would re-open the arbitrage in the other direction.
    """
    key = year_decay_key(round_)
    try:
        from .trade_service import _c
        rate = float(_c(key))
    except Exception:
        rate = PICK_YEAR_DECAY_DEFAULTS[
            int(key.rsplit("_r", 1)[1])]
    return max(0.0, min(1.0, rate))


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


def discount_pick_value(pick_value: float, years_out: int,
                        round_: int = 1) -> float:
    """Apply the year discount to a rung's `pick_value` in VALUE space.

    `pick_value` is the universal pool's engine bridge — the pool builder
    sets it to `(seed_elo - 1200) / 6` and `dynasty_value` inverts it as
    `1200 + 6 * pick_value` (#185). Discounting has to happen on the value
    side of that bridge (the same round-trip `_owned_pick_assets` does), not
    on the linear pick_value scale, so a relabelled 2027 rung prices exactly
    like the owned 2027 pick of the same round: `pick_pool_value(r, 1)`.

    `years_out=0` is an exact no-op, which is what keeps a not-drafted
    league byte-identical to today's payload. Under D-079 `round_=1` is a
    second exact no-op (decay 1.0), which is why the relabel path must pass
    the rung's real round — the caller (`server._apply_pick_rung_year_labels`)
    has already parsed it out of the rung id.
    """
    if years_out <= 0:
        return pick_value
    rate = year_decay(round_)
    if rate >= 1.0:
        return pick_value
    from .trade_service import elo_to_value as _e2v, value_to_elo as _v2e
    elo = 1200.0 + 6.0 * max(0.0, float(pick_value))
    discounted = _e2v(elo) * (rate ** int(years_out))
    return round(max(0.0, (_v2e(discounted) - 1200.0) / 6.0), 1)


def pick_pool_value(round_: int, years_out: int,
                    scoring_format: str = "1qb_ppr") -> float:
    """Generic-ladder Mid-tier value of a round, year-discounted in VALUE space.

    A league pick of `(round, years_out)` is priced at the generic ladder's
    **Mid** tier of that round (operator decision 2026-07-18 — we can't yet
    resolve a pick's slot), then decayed by `year_decay(round) ** years_out`
    in value space (mirroring the anchor wizard's value→elo round-trip).

    The decay rate is PER ROUND since D-079: round 1 is flat by default, so a
    2029 1st and a 2026 1st price identically and no year arbitrage exists
    between them. Rounds 2–4 keep the shipped 0.85.

    `years_out=0` → exactly the generic 'Mid <round>' pool pick's value, so a
    league 1st reconciles with GENERIC_PICK_SEEDS[(1,'Mid')] by construction.

    `scoring_format` is plumbing for a future SF/2QB pick premium (Decision
    D3): pick value is format-agnostic in v1, so it is currently unused.
    """
    from .trade_service import elo_to_value as _e2v
    base_elo = GENERIC_PICK_SEEDS.get(
        (round_, "Mid"), GENERIC_PICK_SEEDS[(4, "Mid")])   # clamp deep rounds
    base_val = _e2v(base_elo)
    return round(base_val * (year_decay(round_) ** max(0, years_out)), 1)


# ═══════════════════════════════════════════════════════════════════════════
# Market pick pricing — THE SHIPPED PRICE since 2026-08-21 (D-144)
# ═══════════════════════════════════════════════════════════════════════════
#
# Built as M6b behind the per-user toggle `pick_pricing_mode` and the flag
# `trade.slot_pricing` (plan operator decision O2). The **2026-08-21 operator
# ruling** removed both — *"Market slots should be default and not an opt-in or
# even an option to flip. Aligned that future picks stay default for now."* —
# so this is now the ONLY price an owned pick can get. See
# `trade_service.pick_pricing_mode_for_user`, which is where the ruling lives.
#
# ⚠️  LLD/HLD-vs-OPERATOR CONFLICT, stated where the code lives.
# `hld.md` KD-9 and `lld.md` §4.7 record engine adoption of DynastyProcess
# slot values as **rejected** ("display-only"). Both predate the
# **Operator decisions — 2026-08-06** block at the bottom of
# `docs/plans/rookie-draft/plan.md`. Decision **O2 REVERSED them** (engine
# adoption, behind a toggle); the 2026-08-21 ruling went further and made it
# unconditional. Where those documents and the operator rulings disagree, the
# rulings win. The same conflict is called out in `backend/data_loader.py`'s
# M6 section header and in `docs/plans/rookie-draft/build-m6b.md`.
#
# WHAT THIS DOES NOT TOUCH — deliberately, and this is load-bearing:
#
#   * `GENERIC_PICK_SEEDS` is byte-unchanged. The 12 generic rungs are
#     RANKABLE POOL ASSETS (users swipe them in matchups; their seed Elo
#     anchors tier colours) and tier bands are ABSOLUTE Elo mirrored across
#     five clients (docs/cross-client-invariants.md). Repricing the rungs
#     would repaint tier colours everywhere from a shared, process-global
#     pool. Generic rungs also never appear on a roster, so they are not
#     tradeable assets — they reach a trade only through the manual
#     calculator, where the user's own board Elo already prices them.
#     (Owned-pick BADGES do move: a badge reflects the SERVED value, D-320-2,
#     and the served value moved. The BANDS themselves did not.)
#
#   * `draft_picks.pool_value` rows are never rewritten. That column is
#     persisted by a league-wide sync path and SHARED by every user of the
#     league. Pricing is applied at READ time, in the request/job that prices
#     the pick — see `priced_pool_value`. Keeping it read-time is also what
#     leaves the ladder recoverable as a harness axis.
#
# WHAT IT DOES: an owned pick's engine value comes from DynastyProcess's
# published market curve for that pick's ABSOLUTE season and round, instead of
# from `pick_pool_value`'s "Mid rung of the round, discounted
# YEAR_DISCOUNT ** years_out".
#
# ROUND-LEVEL, NOT PER-SLOT. Read `UNKNOWN_SLOT_BASIS` below before assuming
# otherwise: a 2026 1st prices at the value-space mean of slots 1.05–1.08, the
# same number whether it is the 1.01 or the 1.12. D-090 resolves the real slot
# and it drives the LABEL only. True-slot pricing is the remaining, unbuilt
# half of Q-023.
#
# Keying off the absolute season (not years_out) is intentional: DP publishes
# a distinct price per season, which already embeds the market's own time
# discount, and it makes the price immune to the #228 window where the current
# season's rows are deleted and a `min(season)` recovery of "current season"
# would silently shift every pick a year closer.

PICK_PRICING_MODES = ("tier_ladder", "market_slots")
PICK_PRICING_DEFAULT = "market_slots"       # the shipped, only-reachable price

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
# THE TERCILE IS NOW THE FALLBACK, NOT THE ONLY ANSWER (2026-08-21, D-144).
# When D-090's order resolves a pick to a real slot, `market_pick_slot_value`
# prices it at THAT slot and the tercile is never consulted. Everything above
# still governs the case the operator called out — a pick whose slot nobody
# knows — which is every future-year pick and every league with no published
# order. See `market_pick_slot_value` for the resolved case.
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
    the deepest published season with the shipped per-round `year_decay`, in
    value space — the same rate `pick_pool_value` uses, so the two curves stay
    on one clock out at 2029+ where DP has nothing to say. Inside DP's window
    the market curve is unchanged by D-079: DP's own published year-over-year
    prices ARE the market's discount, and we do not re-discount them.

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
    return round(base * (year_decay(round_) ** (season - horizon)), 1)


def market_pick_slot_value(season: int, round_: int, slot: int,
                           scoring_format: str = "1qb_ppr") -> float | None:
    """Market price of ONE EXACT draft slot — "2026 Pick 1.03" — or None.

    THE PER-SLOT PRICE (2026-08-21, D-144). Operator ruling: each pick should
    hold *"real value rather than generic"*. Where `market_pick_pool_value`
    answers "what is a 2026 1st worth", this answers "what is the 1.03 worth",
    and the two are wildly different: in 1QB the 1.01 is 4867.1 against a
    round price of 1859.5, and the 1.12 is 820.8.

    Same units as `market_pick_pool_value` and the stored
    `draft_picks.pool_value` — the engine value space — so it is a drop-in at
    every read site.

    **None means "no per-slot price", and the caller must fall back**, in the
    order `priced_pool_value` implements: round curve, then the stored ladder.
    None is returned for all of:

      * DP publishes no per-slot row for that season+round+slot. In practice
        this is EVERY future season — DP prices individual slots only for the
        current class, because a slot only means something once an order
        exists. That is not a gap to paper over; it is the operator's "future
        picks stay default for now", falling out of the data by itself.
      * `slot` is None/0/garbage, i.e. the caller could not resolve an order.
      * DP is unreachable (`load_pick_slot_values` fail-softs to `{}`).

    Rounds are NOT clamped here, deliberately, unlike `market_pick_pool_value`
    (which clamps to DP's published round 5 so a round-9 pick still gets a
    price). A round-9 slot has no published row and no honest analogue, so it
    returns None and rides the round curve's clamp instead — one clamp, in one
    place, rather than two that could drift apart.

    The label is built by `data_loader.pick_slot_label`, the SAME formatter the
    Draft Room's display axis uses, so the engine and the board can never
    disagree about which DP row a slot means.
    """
    from .data_loader import load_pick_slot_values, pick_slot_label
    from .trade_service import elo_to_value as _e2v
    try:
        season, round_, slot = int(season), int(round_), int(slot)
    except (TypeError, ValueError):
        return None
    if round_ < 1 or slot < 1:
        return None
    slot_map = load_pick_slot_values(scoring_format)
    if not slot_map:
        return None
    elo = slot_map.get(pick_slot_label(season, round_, slot))
    return None if elo is None else round(_e2v(elo), 1)


def priced_pool_value(row: dict, *, scoring_format: str = "1qb_ppr",
                      mode: str | None = None, slot: int | None = None) -> float:
    """The engine value of ONE owned-pick row.

    THE read-time seam. `row` is a `draft_picks` row as `load_draft_picks`
    returns it; it is never mutated and never written back.

    **THE THREE-STEP WATERFALL** under `market_slots` — the only mode
    production reaches since the 2026-08-21 ruling. Each step falls to the
    next only when it has nothing honest to say:

      1. **`slot` resolved → the pick's OWN per-slot market price**
         (`market_pick_slot_value`). This is the operator's ruling: each pick
         holds *"real value rather than generic"*. A 2026 1.01 is 4867.1 in
         1QB where the 1.12 is 820.8 — a 5.9x spread the round curve erased.
      2. **no slot, or DP publishes none for it → the ROUND curve**
         (`market_pick_pool_value`, the mid-tercile basis). This is every
         future-year pick — DP prices slots only for the current class, so
         the operator's "future picks stay default for now" falls out of the
         data rather than out of a branch — and every league whose draft order
         is unpublished, unsupported, or unresolvable.
      3. **no market price at all → the stored ladder value.** DP unreachable,
         or a season DP neither publishes nor can extrapolate to. This is the
         whole safety net, and it degrades to exactly today's price rather
         than to a wrong number or an error.

    `slot` is PASSED IN, never resolved here. Resolution is D-090's job
    (`server._league_slot_order` → `pick_slots.slot_for`), it costs a DB read
    plus a cache lookup per LEAGUE, and this function runs per PICK. Passing
    it also keeps the price and the LABEL derived from one resolution, so a
    card cannot say "2026 1.03" while charging for a generic first.

    * `tier_ladder` (harness/test axis only) → `float(row["pool_value"] or
      0.0)`, the stored value verbatim. No DP read is attempted at all, and
      `slot` is ignored — the ladder has no per-slot concept to apply it to.

    `mode=None` resolves the thread-local pin (`trade_service`), so a caller
    that has already entered `pick_pricing_override(...)` need not thread it;
    an unpinned thread resolves to `market_slots`.
    """
    if mode is None:
        from .trade_service import current_pick_pricing_mode
        mode = current_pick_pricing_mode()
    stored = float(row.get("pool_value") or 0.0)
    if mode != "market_slots":
        return stored
    if slot:
        exact = market_pick_slot_value(row.get("season"), row.get("round"),
                                       slot, scoring_format)
        if exact is not None:
            return exact
    market = market_pick_pool_value(row.get("season"), row.get("round"),
                                    scoring_format)
    return stored if market is None else market

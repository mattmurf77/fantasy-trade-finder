# Trade-shape taxonomy — shared vocabulary (co-owned)

**Version:** 1.0.0 (seed)
**Date:** 2026-08-21
**Status:** draft — pending three-way reconciliation sign-off
**Co-owners:** Receipts (post-hoc suggestion scoring) · Negative-results memory (per-league priors feeding generation) · Counterparty breaker (partner-side objection scoring)
**Change rule:** no consumer changes this file unilaterally. A version bump requires a note in each consumer's plan directory (or an explicit "no impact" statement) before merge. Semver: patch = wording/citation fixes; minor = additive vocabulary; major = redefinition or removal of an existing term.

> **Purpose:** one shared vocabulary for describing the *shape* of a suggested trade, so
> three parallel efforts aggregate, learn from, and argue about the same buckets instead
> of inventing parallel labels. This file **documents what the code already stamps** —
> it does not introduce new labels. Every term below carries a file:line citation to the
> code that produces it. If code and this file drift, code wins and this file gets a
> version bump.

---

## 1. Identity primitives

| Term | Definition | Produced at | Stored at |
|---|---|---|---|
| `trade_hash` | sha256 of `sorted(give) \| sorted(receive) \| partner`, 16 hex chars — the stable card identity | `backend/server.py:3952` (`_deck_trade_hash`) | `deck_impressions.trade_hash` (`backend/database.py:505`) |
| `assets_json` | `{"give": [asset ids], "receive": [asset ids]}` — first-class asset bundle (hash can't be inverted) | serve-time stamp | `deck_impressions.assets_json` (`backend/database.py:539`) |
| asset token | Normalized comparison token: player ids pass through; owned picks → `pick:{season}:r{round}:{orig_roster}`; generic-ladder picks → `gpick:r{round}` | `backend/suggestion_telemetry.py:196` (`suggestion_asset_token`) | derived on read |

## 2. Shape dimensions (the taxonomy proper)

### 2.1 `shape` / `shape_bucket` — package cardinality
`"{len(give)}x{len(receive)}"` — e.g. `1x1`, `2x1`, `3x2`. Single definition at
`backend/server.py:3544` (`_card_shape`); frozen at serve into both
`features_json.shape` (`backend/server.py:4137`) and the `shape_bucket` column
(`backend/database.py:512`, "the Thompson arm"). Direction convention: **left side =
what the deck's user gives**, right = receives. Consumers that need the partner's
perspective (counterparty breaker) mirror by swapping — `2x1` for the user is `1x2`
for the partner; do not mint a separate partner-side label.

### 2.2 `basis` — which value board generated the card
`'divergence' | 'consensus'` — whether the card was found by board-vs-board
disagreement or by consensus values. Frozen at serve into `features_json.basis`
(`backend/server.py:4138`); also a column on `trade_impressions`
(`backend/database.py:468`) and `bad_trade_flags` (`backend/database.py:1239`).

### 2.3 `lane` — window alignment of the package
`'window' | 'value' | NULL` from `classify_lane` (`backend/trade_service.py:2694`):
value-weighted now-lean of the assets, signed by the user's window direction; `NULL`
when the user has no declared/inferred window. Frozen into `features_json.lane`
(`backend/server.py:4140`) and denormalized as the `archetype` column
(`backend/database.py:511`; `_card_archetype` at `backend/server.py:3660` — "lane is
today's closest archetype"). **Caveat inherited from the code:** `value` collapses
window-neutral and anti-window cards; consumers needing the distinction read
`lane_shift` (see `classify_lane`'s docstring).

### 2.4 `lane_slot` — deck-composition slot (distinct from 2.3)
`'value' | 'outlook' | 'fill'` — which composition-quota slot the card filled in the
bake-off group draft, NOT the card's own lane (`backend/database.py:595`, semantics in
the comment block `backend/database.py:584-604`, incl. the D-086 rule that lane
*reallocation* is not `'fill'`). Serving-history dimension; meaningless off the
bake-off path.

### 2.5 `model_arm` / `arm_rank` — producing model
`model_arm ∈ {'baseline','current','gen_v2','fit', NULL}` — the generator arm that
produced the card; NULL = pre-attribution rows or cards no arm produced (e.g. likes-you
injections) (`backend/database.py:552`, comment `:536-551`). `arm_rank` = rank within
the arm's own list (`backend/database.py:553`). `group_key`/`group_rank`
(`backend/database.py:593-594`) are the composition half.

### 2.6 `involves_pick` and value bands
`involves_pick`: any side contains a pick (`backend/server.py:4147`).
`give_value_band`/`receive_value_band`: 500-wide buckets of package value,
`_signal_value_band` (`backend/server.py:3943`), frozen at
`backend/server.py:4145-4146`. Raw `give_value`/`receive_value` ride alongside —
**their basis may be the user's personal board**; check `features_json.user_value_basis`
(`'personal' | 'consensus'`, `backend/server.py:4159`) before treating them as market
values.

### 2.7 `trade_intent` — effective intent lens
`'consolidate' | 'tier_up' | 'tier_down' | NULL` — the #172 intent filter the deck was
generated under (`backend/database.py:607`, semantics `:608-618`).

### 2.8 Fit buckets — dual-lens quality labels (partner-side aware)
`_BUCKETS = ('both_high','mixed','you_tilt','them_tilt','both_ok','weak')` from the fit
arm's dual 0–100 you/them scorer (`backend/trade_gen_fit.py:53`; bucket thresholds
`backend/trade_gen_fit.py:656-671`; per-team lens combine `:673`). This is the
vocabulary already in code for "how does this trade look from *each* seat" — the
counterparty-breaker effort should extend these buckets (or the underlying `them`
score) rather than inventing a parallel partner-objection scale.

## 3. Canonical aggregation key

For cross-effort metrics, the default trade-shape cell is the tuple
**(`shape_bucket`, `basis`, `involves_pick`)**, optionally refined by `lane` and
`model_arm` where the question is lane- or arm-specific. Rationale: these three are
stamped on every impression era (F1 onward), have bounded cardinality, and are frozen
at serve (no label-time recomputation). Consumers may aggregate coarser, never finer
than the stamped values, and must not re-derive any dimension from `assets_json` at
read time when a frozen stamp exists (preregistration discipline).

## 4. Consumer notes

- **Receipts** aggregates graded value-movement outcomes per cell (§3) — read-only
  consumer of every dimension.
- **Negative-results memory** keys per-league priors by cells; nothing here assumes a
  card was *served* (ghost rows carry the same stamps), so withheld/declined history is
  representable.
- **Counterparty breaker** mirrors §2.1's direction convention and extends §2.8; its
  generation-side hook is adjacent to the fit arm's `them` lens
  (`backend/trade_gen_fit.py:673-722`), not a new taxonomy dimension.

## 5. Objection vocabulary — RESERVED for 1.1.0 (contributed by counterparty-breaker; pending three-way sign-off)

Placeholder only — the counterparty-breaker session owns this text and will contribute it
as the taxonomy's first minor bump (1.0.0 → 1.1.0). Agreed shape per its PLAN §8
(`docs/plans/counterparty-breaker/PLAN.md`, on that session's branch): `trade_pass_reasons`
layer-2 codes as the anchor set, plus breaker extension candidates (`shape_aversion`,
`roster_crunch`) defined as per-class severities — explicitly NOT a second overall liking
scale (§2.8's no-parallel-scale rule). Converged shape (both siblings, 2026-08-21): the
vocabulary table carries a **producer column** per code — which plan/system emits each code —
so the negmem/breaker boundary is mechanically enforceable inside this file; converged
per-code assignments so far: `roster_crunch` → producer=breaker, `shape_aversion` →
producer=negmem. Sign-off state:
coordinator yes · negative-results memory yes (converged) · Receipts yes (this file's author). Do not author content here outside the
breaker session's contribution PR.

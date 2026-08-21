# Trade-shape taxonomy — shared vocabulary (co-owned)

**Version:** 1.1.1 — 1.1.0 (additive §5 objection vocabulary, breaker-authored) is **fully agreed three ways**: breaker yes · negmem yes (confirmed 2026-08-21, point-by-point) · Receipts yes. 1.1.1 is a patch-level footnote requested by negmem (wording only, non-normative; no-impact for breaker/Receipts). 1.0.0 seed content (§1–§4) unchanged.
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

## 5. Objection vocabulary (counterparty breaker · negative-results memory)

*Contributed by the counterparty-breaker session (LLD converged `59a5d23`); incorporated
verbatim by the file's author session, formatting only. negmem's explicit 1.1.0 sign-off
pending per the change rule.*

One vocabulary for "why a manager declines," anchored on the SHIPPED trade_pass_reasons
layer-2 codes (backend/database.py:5579-5583) — predictions (breaker) and observations
(negmem) use the same codes, differing only in tense. The PRODUCER column enforces the
present-state/historical boundary mechanically: a code with producer=negmem appearing in a
breaker output is a reviewable defect, and vice versa where marked.

| Code | Producer | Basis | Definition |
|---|---|---|---|
| fit_outlook | breaker (predicted) · negmem (observed) | present-state / historical | pushes against the counterparty's window; breaker quantity = unweighted _give_side_now_lean mean incl. picks at the −0.25 constant (XOR-coherent with _opponent_frame, LLD §3.3) |
| fit_new_weakness | breaker · negmem | as above | opens a starting hole they can't fill (mirrored lineup feasibility, their seat) |
| fit_duplicate | breaker · negmem | as above | stacks a position they're already deep at (their position_surplus; tier_basis marked) |
| value_giving | breaker · negmem | as above | from their seat they overpay — on their own board (board basis, narration-INELIGIBLE) or vs consensus optics (consensus basis) |
| other_player_keep | breaker · negmem | as above | asks for a player they've marked untouchable (private-state: stamps dark, never renders v1) |
| roster_crunch (EXTENSION) | breaker | present-state only | accepting is structurally costly from their seat: forced drop, lineup slot math, positional pile-up |
| shape_aversion (EXTENSION) | negmem | historical only | a manager's LEARNED resistance to a package shape; breaker may cite only via the future memory→breaker coupling |
| value_getting, value_other, fit_other, other_player_avoid | negmem (observed only) | historical | shipped codes with no v1 breaker predicate; predictions for them are a future minor bump |
| other_text | NONE | — | free-text bucket; excluded from both producers' coded vocabularies; calibration joins treat filed other_text rows as unmatched-by-construction |

Severity (breaker-only): per-class 0–1 from present-state margins (LLD §3), NOT a
partner-liking magnitude — that remains the fit arm's them-score (§2.8 rule upheld).

> **Footnote (1.1.1, negmem):** the producer column marks which side of the
> predicted/observed boundary a code lives on — it is **not** negmem's M1 evidence-admission
> list. Per negmem PRD R2, only the {value, fit} layer-1 families accrue M1 evidence;
> `other_player_avoid` / `value_other` / `fit_other` are negmem-domain codes that do NOT
> accrue. Do not read this table as the admission spec.

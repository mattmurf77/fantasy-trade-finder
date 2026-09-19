# 10. Key-asset package adjustment

> Tier 1 · #10 · ENH · Effort M · Sources: FPT / DD / FTF

## Summary

Industry consensus on the package problem is documented from two independent competitors: FPTrack's **Crown Asset** boost ("best asset gains value in 1-for-many deals" — a named rule in their published Value Boosts table) and Dynasty Daddy's **Value Adjustment** ("I wanted to make sure the fair trades weren't splitting a dollar into 100 pennies… the formula takes into consideration who is the key player in the trade and what proportion of the trade he accounts for") — see `docs/competitor-teardown-web-tools.md`. Both attack the same asymmetry from the same direction: in an N-for-1, the single side's asset is worth *more* than its sticker price because consolidation is scarce.

FTF's v2 engine already handles half of this. `package_value_v2` (amendment A2) discounts the depth side — each asset contributes `v · (0.15 + 0.85 · (v / v_max) ** package_adj_gamma)` with `package_adj_gamma` 1.5, so lesser assets bottom out at 15% of raw value ("four quarters ≠ a dollar"). The legacy path keeps fixed `package_weight_1..5` (1.00/0.75/0.55/0.40/0.28). What no path has is the *premium* side: an explicit key-asset multiplier scaled by the top asset's share of its own side's total, so the crown player in a consolidation trade is priced above his vacuum value. Adding it — carefully tuned against `package_adj_gamma` so the two mechanisms don't double-count the same spread — directly addresses the standing trade-engine-v2 watch item ("tune fairness_threshold / package_adj_gamma once real swipe data accumulates in trade_impressions — watch via GET /api/admin/engine-metrics"), and resolves it the way the teardowns recommend: explicit multiplier, not hard gate.

## PRD

### Problem & user story

*As a user being offered 3-for-1 for my stud*, the engine should recognize that my single elite asset commands a consolidation premium — quantity should not buy quality at face value. *As a user consolidating depth into a star*, the engine should not gate out realistic consolidation trades just because the raw sums look lopsided against me.

Concretely: the depth-side discount exists (γ), the crown-side premium doesn't. The fairness gate (`_fairness` in `_generate_for_pair_v2`: consensus `package_value_v2` ratio + range-overlap, against `fairness_threshold`) and both sides' surplus math therefore systematically misprice asymmetric-count trades relative to how the market (KTC, FPTrack, Dynasty Daddy) actually adjudicates them.

### Goals / Non-goals

**Goals**

- Explicit crown-asset multiplier: the top asset on a side gains value proportional to its share of that side's total raw value.
- Apply consistently wherever v2 package math runs: fairness (consensus space), user-side and opponent-side surpluses, and the v3 optimizer.
- Joint re-calibration with `package_adj_gamma` so combined behavior matches market reference points (no double-count).
- Neutral on 1-for-1 trades by construction (both sides' share = 1.0 → symmetric effect cancels in the fairness ratio).

**Non-goals**

- Touching the legacy `package_value` / `package_weight_1..5` path (retained untouched for the flag-off legacy engine, per the existing pattern).
- A fairness hard-gate redesign or threshold change (user-facing threshold control is #4).
- Pick-specific premiums (FPTrack's Solo Future 1st etc. — pick valuation work is #15).
- Star/QB tax reconciliation (`trade_math.star_tax`, `trade_math.qb_tax` are separate, already-flagged adjustments).

### Functional requirements

1. **FR1** — Extend the v2 package valuation with a crown term: the best asset of a side contributes `v_top · (1 + crown_rate · max(0, share − crown_share_floor) / (1 − crown_share_floor))` where `share = v_top / Σ raw side values`. Proposed defaults: `crown_rate` 0.12, `crown_share_floor` 0.50 — premium ramps from 0 at ≤50% share to `crown_rate` at 100% share. (Exact functional form may change during calibration; the *shape* — monotone in share, zero below floor — is the requirement.)
2. **FR2** — Lesser assets keep the existing γ treatment unchanged.
3. **FR3** — Applied in all three v2 value spaces for consistency: `_fairness` (consensus `seed_value`), user packages, opponent packages — in both `_generate_for_pair_v2` and `_generate_consensus_for_pair`, and in `trade_optimizer.generate_pair_trades_v3` *(verify its package call sites; it reuses `_ts._cfg` for sweetener keys so it reads module config directly)*.
4. **FR4** — Calibration deliverable: a one-off script in `backend/scripts/` (pattern: the elo_value calibration script from Tier 1) sweeping `crown_rate` × `package_adj_gamma` over fixture trades (1-for-1, 2-for-1, 3-for-1 at varying concentration) and reporting fairness ratios against chosen reference points (e.g. KTC's published formula from the `package_value_v2` docstring as the consensus anchor).
5. **FR5** — Flag OFF ⇒ byte-identical output (crown term multiplies by exactly 1.0).
6. **FR6** — New config keys live in `_DEFAULT_CFG` + `model_config` seed rows so post-launch tuning happens via `PUT /api/admin/config/<key>` without deploys.

### UX notes

- No direct UI. Indirect effects users see: deck composition shifts (more credible consolidation trades; fewer quantity-for-quality steals), and `fairness_score` values move on asymmetric cards.
- When `trade_math.human_explanations` is ON, append a reason string on affected cards ("Best asset priced up — key player carries this side") so #20's transparency page has a named rule to document, FPTrack-style.
- Web/mobile/extension: no changes required.

### Success metrics

- Engine-metrics (`GET /api/admin/engine-metrics`): like/pass rate by package shape (1-1 vs 2-1 vs 3-2 — shape breakdown already exists per `living-memory/CHANGELOG.md`) converging across shapes rather than depth-heavy shapes over-performing.
- Calibration script: fairness ratio on reference consolidation trades within a stated band of the KTC-formula answer.
- Closure of the v2 watch item with an ADR documenting chosen constants.

### Acceptance criteria

- [ ] 1-for-1 fixtures: fairness ratio and both surpluses unchanged vs flag OFF (neutrality property).
- [ ] 3-for-1 fixture with a dominant crown asset: crown side's package value rises by the expected premium; fairness ratio moves accordingly; property holds in all three value spaces.
- [ ] Calibration script committed under `backend/scripts/` with results recorded in the PR + ADR.
- [ ] Flag OFF golden-file parity across divergence, consensus, and v3 paths.
- [ ] `docs/config-reference.md` (new keys), `docs/cross-client-invariants.md` if `fairness_score` display semantics shift, new ADR in `docs/adr/`.

## HLD

### Components touched

- `backend/trade_service.py` — `package_value_v2` (or a wrapping `package_value_v2_crown`) + `_DEFAULT_CFG` keys; call sites in `_generate_for_pair_v2` (`_fairness`, `_consider`) and `_generate_consensus_for_pair`.
- `backend/trade_optimizer.py` — v3 package valuation call sites + sweetener classification (sweeteners are valued via consensus packages; a crown-boosted side changes which near-misses fall inside `sweetener_band`).
- `backend/database.py` — `model_config` seed rows for the new keys.
- `backend/scripts/` — calibration sweep script.

### Data flow

No flow changes — same `generate_trades` → `_generate_trades_v2` → per-pair enumeration. The crown term is a pure function of the per-side value lists already assembled in `_consider` (`uvals_give/recv`, `ovals_give/recv`) and `_fairness` (`gvals`/`rvals`). Waiver-slot cost (A3) and the surplus gates (`min_side_surplus` / `min_side_surplus_marginal`) apply after, unchanged in order.

### Flags & config interplay

- **New flag:** `trade.crown_asset`, default **false**.
- Interacts with `package_adj_gamma`: both widen the concentrated-vs-depth spread. The calibration sweep decides whether γ comes *down* (e.g. toward 1.2–1.3) when crown turns on; both knobs stay independently tunable in `model_config`.
- Interacts with `trade.marginal_value`: crown share should be computed on **raw** side values even when surpluses use marginal values — marginal values measure roster fit, not market consolidation scarcity *(design decision; see Open questions)*.
- Interacts with `sweetener_band` (Tier 3): re-run sweetener fixtures; the band is relative to `fairness_threshold`, which crown shifts on asymmetric trades.
- Kill switch: flag off restores current math exactly.

## LLD

### Engine changes

- `backend/trade_service.py`:
  - `package_value_v2(values, v_max)` gains an optional crown application — cleanest as a sibling `package_value_v2_crown(values, v_max, side_total_raw)` to keep the existing signature stable for the legacy/v3 imports, OR a module-level flag check inside; decide at implementation against call-site count.
  - New `_DEFAULT_CFG` keys: `crown_rate` (0.12), `crown_share_floor` (0.50). Matching seed tuples in `backend/database.py` config seeding.
  - `_fairness` in `_generate_for_pair_v2`: crown applied per side using each side's own `share` (note `v_max` there is the *trade-wide* best asset; crown share is per-side — the two must not be conflated).
  - `_consider`: same treatment for `give_val_user`/`recv_val_user`/`give_val_opp`/`recv_val_opp`.
  - `_generate_consensus_for_pair`: its fairness ratio (`fairness = min(gv, rv) / max(gv, rv)` over consensus packages) gets the same wrapper.
- `backend/trade_optimizer.py`: locate every `package_value_v2` use (enumeration scoring + the 3.4 sweetener pass) and route through the crown-aware form; verify `sweetener` classification fixtures.

### API changes

- None. `fairness_score`/`mismatch_score`/`composite_score` fields are unchanged in shape; values shift on asymmetric trades. Optional `reasons` string when `trade_math.human_explanations` is ON.

### Schema changes

- None (new `model_config` rows are data, not schema; seeded idempotently like existing keys).

### Client changes

- None required. Mobile fairness meter (`fairness_score` × 100) renders shifted values transparently.

### Rollout

- Flag `trade.crown_asset`, default `false`. Order: implement + unit fixtures → calibration sweep → pick constants, record ADR → enable in prod alongside an engine-metrics baseline snapshot so before/after like-rates by package shape are comparable. Kill switch = flag off.

### Open questions

1. **Crown in marginal space:** when `trade.marginal_value` is ON, surpluses use over-replacement values. Proposal above keeps crown share computed from raw values (market scarcity) while multiplying whichever value list the side is using — confirm this composes sensibly or restrict crown to the consensus fairness gate only in v1 (smaller blast radius, still fixes the gate watch item).
2. **Premium recipient:** boost only the single top asset (FPTrack Crown) vs. weight the whole side by key-asset proportion (Dynasty Daddy). Top-asset-only is proposed (simpler, more explainable for #20); calibration may say otherwise.
3. **Both-sides-multi trades:** in a 2-for-3, both sides get small crowns. Acceptable (symmetric-ish) or should crown require the *other* side to have more pieces? Current proposal: pure per-side share, no cross-side condition — the share floor naturally damps balanced packages.
4. **Exact watch-item closure:** the watch item couples `fairness_threshold` and `package_adj_gamma` tuning to real `trade_impressions` data; crown adds a third knob before that data is rich. Confirm with operator that shipping crown dark now, tuning all three together when telemetry lands, is the intended resolution.

## As-built (2026-06-11)

Shipped behind `trade.crown_asset` (default false). Decisions recorded in **[ADR-003](../../adr/adr-003-crown-asset-package-premium.md)**. Key points:
- Crown lives **inside `package_value_v2`** via a new optional `n_other` param (the other side's asset count). Premium fires only when `len(values) < n_other` — provably **neutral on equal-count trades** (1-for-1, 2-for-2) and on any caller that omits `n_other`. This resolves open question 3 (a pure per-side share would have fired on 1-for-1).
- Migrated all v2/consensus/v3 package call sites to pass `n_other` (give packages get `len(recv_ids)`, recv packages get `len(give_ids)`): `_fairness` + `_consider` in `_generate_for_pair_v2`, the consensus `_emit`, and `_consensus_packages` / `_fairness_v3` / `_surpluses` in `trade_optimizer.py`. Legacy `package_value` untouched.
- Top-asset-only, raw-share premium (open questions 1 & 2 → FPTrack model). Constants `crown_rate` 0.12 / `crown_share_floor` 0.50 in `_DEFAULT_CFG` + seeded into `model_config` for live tuning.
- **Calibration script deferred** (open question 4, operator-confirmed): shipped dark; `crown_rate` / `package_adj_gamma` / `fairness_threshold` tuned together when `trade_impressions` telemetry lands. A sweep against synthetic fixtures only would not be meaningful.
- Tests: `backend/tests/test_crown_asset.py` (8 cases: no-`n_other` identity, flag-off identity, equal/larger-count no-crown, smaller-count premium, below-floor ~zero, monotone-in-share, engine 1-for-1 neutrality, consolidation fairness shift). Full suite 203 green.

## Dependencies & sequencing

- **Depends on:** nothing in the top 20. Wants engine-metrics telemetry volume (#84 expansion helps) for final tuning, but fixtures + calibration script unblock shipping dark.
- **Feeds:** #4 (fairness threshold control — a user-adjustable gate should sit on top of *corrected* package math), #6 (verdict gap quantification uses package values), #3/#27 (rescore endpoint inherits crown automatically), #11 (offer analyzer credibility on real N-for-1 offers).
- Wave 1 (engine correctness), after #1/#8 — independent of them, so it can proceed in parallel.

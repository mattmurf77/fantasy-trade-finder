# Asset-centric Upgrade / Lateral / Downgrade ideas — status

**Status: built (backend engine + route + mobile grouped panel)** · 2026-07-26 · branch `teardown-remediation` worktree · flag `trade.asset_ideas` (default **ON**)

> **2026-07-27 — semantics amended by #198** (operator: upgrading means
> upgrading the PIN'S POSITION). Upgrade/Lateral are now constrained to the
> pin's position; Downgrade stays value-based with same-position headliners
> preferred; PICK pins keep the value bands described below. See
> `docs/feedback/items/198-upgrade-semantics/status.md` — the value-band
> description in this doc is otherwise historical.

## Context

Operator, on the Dynasty Trade Factory teardown
(`docs/business/product/2026-07-26-dynastydealer-dtf-teardowns.md`, "Smart
Trade Finder"): *"The upgrade, downgrade, horizontal options is exactly what
we should be doing when a user selects a player to trade away or trade for.
This is literally exactly what I expect and why I filed a feedback item that
I didn't like that we didn't have any or had limited options when selecting a
player to trade away (or even trade for for that matter)."*

Direct lineage: **#172** (consolidate / tier-up vs. spread-out / tier-down
intents — the PRD in `docs/feedback/items/168-looking-for-intents/prd.md`
proposed but didn't build them) and **#189** (targeted jobs should always
present offers — `docs/feedback/items/189-always-offer-fallback/status.md`
shipped the relaxed-fallback machinery this feature's labeling reuses).

## Behavior

When the user pins exactly **one** asset (player or owned pick, either
direction) in the finder targeting flow, a grouped idea list renders
**alongside** the normal deck (deck flow untouched; 0 or 2+ pins =
byte-identical to before).

**Backend** — `TradeService.generate_asset_ideas` (`backend/trade_service.py`)
+ synchronous `POST /api/trades/asset-ideas` (`backend/server.py`, 404 when
the flag is off). Consensus-basis sweep, classification around the pin's
consensus value with a ±`asset_ideas_lateral_band` (10%) band:

- **Upgrade** (trade-away pin): counterpart above the band comes back as a
  straight 1-for-1 when the gates pass, else pin + the own-roster sweetener
  that lands the closest deal (2-for-1 up).
- **Lateral**: 1-for-1 within the band.
- **Downgrade**: 2-3 lesser counterpart pieces packaged back (best 2 combos
  per opponent, distinct headliners).
- **Acquire pin mirrors**: counterparty is the pin's owner; ideas enumerate
  what the user GIVES — a package of lesser own assets tiers up into the pin,
  a band asset swaps across, a single better own asset returns the pin plus
  owner sweetener(s).

Each idea: counterparty, give/receive sides (hydrated player dicts + id
lists), adjusted package values (`give_value`/`receive_value`, same
`package_value_v2` value space as the calculator), signed `difference`
(receive − give; + = user ahead on consensus), `fairness`. Groups capped at
`asset_ideas_group_cap` (6), ordered by |difference| ascending; output is
deterministic for a fixed league snapshot.

**Why a dedicated endpoint, not a param on `/api/trades/generate`:** the
generate flow is an async job pipeline (job cache, polling, progress
streaming, deck ordering/bandit/fatigue layers) whose per-opponent budgets
and card caps fight the grouped, all-counterparties semantics — and
`_generate_for_pair_v2` / `generate_pair_trades_v3` are divergence engines
keyed on both boards, while this surface is a consensus-basis presentation.
The cheaper sound option reuses the consensus generator's exact helper set —
`elo_to_value`, `package_value_v2` (crown premium via `n_other`), the min/max
fairness ratio, `user_gain_epsilon`, `user_gain_ok_1for1`, `filler_ok`,
`consolidation_raw_loss_frac` — with **no new valuation math**, in a
deterministic synchronous read.

**Gates** apply as in normal consensus generation: the #108 user-gain gates
and the untouchable / not-interested exclusions are enforced and NEVER
relaxed (an untouchable pin or not-interested acquire pin returns empty
groups). Coverage relaxation follows the #189 convention: candidates are
evaluated against `min(fairness_threshold, relaxed_fairness_threshold)`, and
a group that would otherwise be **empty** refills from the widened band only,
labeled `relaxed: true` + `relaxed_reason: "fairness_band"`.

**Owned picks**: the route runs the same `_inject_owned_picks` guard as the
generate job (`trade.picks_in_pool`, non-ESPN, non-demo), so a pick can be
the pinned asset, a sweetener, or a downgrade piece.

**Client** (`mobile/src/screens/TradesScreen.tsx` +
`mobile/src/components/AssetIdeasPanel.tsx` + `mobile/src/api/trades.ts`):
single-pin detection over the existing `useFinderTargets` store; a
pin-driven `useQuery` (no extra button — the endpoint is cheap) renders
"Upgrade ideas / Lateral moves / Downgrade ideas" sections in a Chalkline
card under the deck controls. Rows: give ↔ receive (position dots +
names), counterparty, adjusted totals, green/red signed difference chip;
relaxed rows carry "Stretch — outside your fairness band". Direction-aware
header copy ("Ideas for trading away X" / "Ideas for landing X"). Tap →
`TradeCalculator` with the #190 `prefill` param (opponent + both sides
preloaded) — the least-invasive full-detail integration, reusing an existing
route param instead of new deck plumbing. Client checks
`useFlag('trade.asset_ideas')`.

## Flag / knobs

- `trade.asset_ideas` — default **true** in `config/features.json` (+
  `backend/feature_flags.py` FLAG_KEYS, mirrored in
  `backend/tests/fixtures/flags/release.json`). The kill switch.
- `model_config` (DB-seeded, live-tunable): `asset_ideas_lateral_band`
  (0.10), `asset_ideas_group_cap` (6).

## Files

- `backend/trade_service.py` — `generate_asset_ideas` + `_DEFAULT_CFG` knobs
- `backend/server.py` — `POST /api/trades/asset-ideas`
- `backend/database.py` — `_MODEL_CONFIG_DEFAULTS` seeds
- `backend/feature_flags.py`, `config/features.json`,
  `backend/tests/fixtures/flags/release.json` — flag
- `mobile/src/api/trades.ts` — `fetchAssetIdeas` + types
- `mobile/src/components/AssetIdeasPanel.tsx` — grouped panel
- `mobile/src/screens/TradesScreen.tsx` — single-pin detection, query, render,
  calculator handoff
- Docs: `docs/api-reference.md`, `docs/config-reference.md`,
  `docs/glossary.md` ("Asset ideas")

## Tests

`backend/tests/test_asset_ideas.py` (13): give-direction grouping vs value
bands (`test_give_direction_grouping_bands`), #108 exclusion of below-pin
laterals, exclusion lists (not-interested, untouchable sweetener, untouchable
pin), relaxed refill labels only otherwise-empty groups
(`test_relaxed_refill_labels_only_empty_groups`), group cap + |difference|
ordering + determinism (`test_group_cap_and_ordering`,
`test_give_ideas_deterministic`, `test_receive_ideas_deterministic`),
direction mirroring incl. owner-only counterparty
(`test_receive_direction_mirrors_grouping`,
`test_receive_direction_exclusions`), empty results for unknown
asset/direction/off-roster pin, route 404 when flagged off + response shape +
validation.

Full backend suite: **1213 passed, 1 skipped** (branch baseline before this
change: 1200 passed, 1 skipped). `cd mobile && npx tsc --noEmit` clean.

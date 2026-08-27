# Feature Scope — #403 "Shop a player"

<!-- Filled copy of docs/templates/feature-scope.md. Every section is answered
     or explicitly WAIVED with a reason — silence is not a waiver.
     Its §Maestro delta and §Simulator-gate tier are DEAD sections (D-056,
     docs/CLAUDE.md) and are deliberately absent. -->

**Date:** 2026-08-27
**Entry point:** feedback #403 (`Boston Brawlers`, screen `TradeCalculator`,
v1.16.8, filed 2026-08-26T21:54Z, severity `polish`)
**Builder:** Phase 1 dual-agent doc loop — Author agent (subagent 2)
**Operator sign-off on waivers:** **REQUIRED — 2 waivers below (§3 captures,
§Web tests) plus 4 open questions in [`prd.md`](prd.md) §1.** O-1 is on the
bright line and needs a confirming yes.

**Tree verified against:** `origin/main` @ `6e94ff71`.

---

## 1. Analytics scope

**(a) New events specced.** Four, all client-fired from mobile. Registered in
`backend/analytics_taxonomy.py` `ALLOWED_CLIENT_EVENTS` (`:38`) **and**
`CLIENT_EVENT_PROPS` (`:833`) **in the same commit as the emitter**
(`CLAUDE.md` §Common tasks) — unregistered props are silently dropped behind a
200.

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `shop_opened` | `asset_position` ∈ `{QB,RB,WR,TE}` · `source` ∈ `{matches,deck,calculator}` | `ShopAssetScreen` mounts | mobile |
| `shop_mode_selected` | `mode` ∈ `{tier_up,tier_down,same_value}` · `n_ideas` (int) | a mode chip is tapped | mobile |
| `shop_positions_selected` | `n` (int) | the W2 picker selection settles into a fetch | mobile (W2) |
| `shop_dismiss_undone` | `mode` | Undo tapped inside the 5 s window | mobile |

**Prop-cardinality decision, recorded:** `shop_positions_selected` carries a
**count**, not the selected set. The set is user preference data and would
raise cardinality for no analytic gain — "how many positions do people pick"
is the question; "which" is answerable from
`league_preferences.trade_away_positions` already.

**`NON_INTENT_EVENTS` (`backend/analytics_queries.py:63`) is UNCHANGED, and
that is an answer, not silence.** Intent is a **deny-list**
(`INTENT_EVENTS = (SERVER_FIRED | ALLOWED_CLIENT) − NON_INTENT`, `:335`), so
all four are INTENT by default, which is correct: each is a deliberate tap.
`shop_opened` is a menu-row press, not an impression. `shop_dismiss_undone`
matches its sibling `swipe_undone`, which is likewise **not** in the non-intent
set (verified: `grep -n swipe_undone backend/analytics_queries.py` → no match).

**(b) Existing events cover the rest** — no registration needed:

- **The like** → `calc_trade_queued {queued, reason?}` (`analytics_taxonomy.py:619`,
  props `:1503`) with `screen: 'ShopAsset'`. The D-158 precedent verbatim: *"the
  SAME shared helpers both hosts call, with the screen name as the only
  difference"*. #403 reuses `utils/queueCalcTrade.ts` rather than emitting its
  own event.
- **The dismiss** → the server-fired `match_swiped` from `/api/trades/swipe`
  (`server.py:12685`), already registered, already a `WAT_LIVE` feeder
  (`analytics_queries.py:53`).

**Follow-through:** `docs/data-dictionary.md` — **n/a**, nothing new is
stored; these ride the existing `user_events` P1 pipeline via
`POST /api/events`.

## 2. Schema & flag scope

**New/changed tables or columns: none.** No `backend/database.py` edit.
`docs/data-dictionary.md` needs no change.

**New env vars / `model_config` keys: none.** `asset_ideas_lateral_band` (0.10)
and `asset_ideas_group_cap` (6) are **reused as-is**
(`backend/database.py:2473-2474`, `backend/trade_service.py:202-203`). A build
agent adding a knob has left the spec.

**New feature flags: one.**

| Key | Default | Registration | Graduation |
|---|---|---|---|
| `trade.shop_asset` | **`false`** (ships dark) | `config/features.json` · `backend/feature_flags.py` `FLAG_KEYS` (near `ux.swipe_undo`, `:306`) · `docs/config-reference.md` · client `useFlag` · `backend/tests/fixtures/flags/*.json` — **all five, or the key reads as permanently false** (the D-035 lesson, `docs/feedback/items/318-awaiting-dismiss/scope.md`) | The `prd.md` §6.5 TestFlight checklist, run by the operator, outcome in `living-memory/TEST_LEDGER.md` |

Namespace: `trade.*` matches the sibling it extends (`trade.asset_ideas`), not
the presentation namespace `trades.*`.

**Ship-the-knob / deploy-free rollback lever:** `trade.shop_asset` alone, via
`POST /api/feature-flags/reload` — no deploy, no client build. TestFlight step
19 exercises it.

**Prerequisite flags, all `true` today** (named because any of them going dark
degrades or disables #403, and the degrade must be honest, not an empty
surface):

| Flag | Today | If it goes off |
|---|---|---|
| `trade.asset_ideas` | `true` | The route 404s (`server.py:12069`). **The entry point must not render** — the check is one exported `shopEnabled` helper, not duplicated per host. |
| `ux.player_context_menu` | `true` | No long-press menu, so no W1 entry point. |
| `calc.merged_layout` | `true` | `/api/trades/queue` 404s `feature_disabled` (`_calc_queue_denied`, `server.py:12894`) — **the shop card's Like stops working.** |
| `trade.likes_you` | `true` | The queue returns `{queued:false, reason:'likes_you_off'}` and `queueRefusalLine` already has honest copy for it. |
| `ux.swipe_undo` | `true` | **Not a prerequisite.** #403's undo is its own `pendingDismissRef`, shipped unconditionally — the #318 precedent. |

**OFF-state contract:** byte-identical **in the source**, not merely gated.
`swap_positions` and `record_elo` keys are **omitted** from request bodies (not
sent as `undefined`), no entry-point row is pushed, the screen is registered but
never navigated to, and no #402-owned file is edited. Full statement:
`lld-delta.md` §7.

## 3. Evidence scope

**[x] Structural guard:** `mobile/tests/check-shop-deck.js` (**NEW**,
dependency-free, runs under plain node; matching `npm run test:shop-deck`).
It runs in CI automatically — `.github/workflows/ci.yml:44` globs
`tests/check-*.js`. **13 assertions, each paired with a named sabotage**, in
`prd.md` §6.2. Pins, in one line each: both decision controls exist (A-1) and
are **uncrossed** (A-2, `tsc`-invisible); like → `queueCalcTrade`, dismiss →
`swipeTrade('pass')` (A-3); the dismiss **arms a timer before any network
call** and the undo makes none (A-4 — the honest-undo contract); the entry row
and `swap_positions` are inside truthy-flag branches (A-5, A-6); **no
`Gesture.Pan` / `PanResponder` / gesture-handler import** (A-7); the counter
and the pager read the same identifier (A-8); `FeedbackFAB` is mounted (A-9);
no Chalkline prohibition (A-10); `TradeCard` is mounted without `disposition`
(A-11); the mode→group map is **transpiled and executed** (A-12); the copy trio
appears once each and reuses `TRADE_INTENT_LABEL` (A-13).

**[x] Unit tests (pytest):** `backend/tests/test_asset_ideas.py` (extended) and
`backend/tests/test_shop_queue_elo.py` (**NEW**) — **9 tests, T-B1…T-B9**, each
with a named sabotage, in `prd.md` §6.1. Two-sidedness is explicit: T-B1/T-B2
are a pair (identical-when-absent ∧ different-when-present); T-B4 pairs its 400
legs with a must-succeed `[" rb "]` leg; T-B5 pairs an empty case with a partial
case; T-B7 requires the default leg to move the board while the `record_elo:false`
leg does not.

**[x] Code-walk proof:** `prd.md` §6.3 — three file:line-cited traces
(entry tap → card on screen; dismiss → undo → nothing happened; Chalkline
compliance). This is the substitute named in the capture waiver below.

**[x] Manual TestFlight checklist:** `prd.md` §6.5 — 19 numbered steps with
expected results, split flag-OFF (2 steps proving nothing changed) and flag-ON
(17 steps), including the deck's own swipe still working (step 18) and the
deploy-free kill switch (step 19).

**[x] WAIVED — `screens/` captures.** The PRD rule *"UI-touching items name
their captures"* **cannot be satisfied** and this is the written waiver, with a
named substitute:

> `screens/` is **frozen at 2026-08-11** (D-056 retired the simulator entirely;
> `screens/CLAUDE.md`), and `screens/mobile/trades/` holds only `empty`,
> `empty--cold`, `error`, `format-gate`, `generating`, `loading`, `populated`
> (`screens/manifest.json:1652-1725`). **There is no single-pin capture and no
> asset-ideas capture at all**, and the surface has changed since the freeze
> (#240, #287, #317, #384). `mobile/scripts/screen-freshness.sh` cannot flag a
> capture that does not exist, and no re-capture can be requested because the
> harness that made them is retired.
>
> **Substitute:** the code-walk proof at `prd.md` §6.3, cited against
> `AssetIdeasPanel.tsx`, `FeaturedTradeWindow.tsx`, `TradeCard.tsx`,
> `PlayerContextMenu.tsx` and `utils/ideaToCard.ts` — the live source, which is
> the only ground truth that still exists — plus TestFlight §A steps 1–2, whose
> whole job is "nothing looks different".
>
> **Not a substitute, deliberately:** `mockups/polish-lab-2026-08/asset-ideas-layout{,-v2,-v3}.html`.
> They are design prototypes and are **never** citable as current app behavior
> (`mockups/CLAUDE.md`). Named here so a later agent does not reach for them.
>
> **Capture delta at ship: none.** No capture can be taken. This is a permanent
> consequence of D-056, not a #403 shortcut.

**[x] WAIVED — web test section.** `prd.md` §6.6. No `web/` or `extension/`
file references asset ideas (`git grep -n "asset-ideas" -- web extension`
returns nothing) and #403 adds none. There is no URL, user action, or DOM
assertion to write.

**`testID`s added:** `player-menu.shop` (default from `PlayerContextMenu.tsx:38-40`) ·
`shop.back-btn` · `shop.mode.tier-up` · `shop.mode.tier-down` ·
`shop.mode.same-value` · `shop.pos.<POS>` · `shop.counter` · `shop.pager` ·
`shop.card.<assetIdeaKey>` · `shop.like-btn` · `shop.dismiss-btn` ·
`shop.empty`. None renamed, none removed.

**Honest note on `testid-lint`:** `mobile/scripts/testid-lint.sh` cross-checks
**flow → source** only, and `mobile/.maestro/` is frozen under D-056. It will
pass these trivially. It stays in CI as a ship gate, but it is **not** evidence
for #403 — `check-shop-deck.js` is.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | Three entries. `/api/trades/asset-ideas` (`:234`) — the optional `swap_positions: string[]`, its `{QB,RB,WR,TE}` domain, its **replaces-not-filters** semantic on `lateral` only, the `400 invalid_position` shape, and the avoid-beats-select rule. `/api/trades/queue` (`:239`) — the optional `record_elo` (default `true`; `false` skips `record_trade_signal` + `save_trade_swipes` and nothing else), **pending O-1**. `/api/trades/swipe` (`:238`) — a note that asset-idea cards reach it under an `asset-idea:<key>` id via FB-46. |
| `living-memory/LLD.md` | **updated** | A convention shift worth recording: *a caller-supplied position set REPLACES a #198-style semantic predicate for one band only, is validated closed against `VALID_POSITIONS`, 400s on an unknown token (unlike the persisted-preference `_normalize_avoid_positions`, which drops), and is applied at pool-scan time so the #189 relaxed refill structurally cannot widen it.* |
| `docs/architecture.md` | **n/a because** no module is added, removed, or re-wired and no data-flow edge changes direction. A new screen consuming an existing route sits inside the shape the document already describes. (`hld-delta.md` §6.) |
| `living-memory/HLD.md` | **n/a because** same — no new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **n/a because** no shared constant, enum, or color changes. Position colors are **reused** via `PositionChip`/`posColor`, never redefined. `CALC_QUEUE_REASONS` is consumed unchanged — #403 adds no reason. |
| `docs/glossary.md` | **updated** | Per Q-G: one entry recording **both** senses of "shop" — (a) **Shopping** = `trade_away_positions`, the league-level positional preference in Chasing / Shopping / Avoiding (`glossary.md:118`, `:172`); (b) **Shop a player** = the #403 asset-level surface over `POST /api/trades/asset-ideas`. Each points at its own mechanism so the collision is documented rather than latent. **R-16.** |
| ADR or `DECISIONS.md` entry | **updated** | `living-memory/DECISIONS.md` (orchestrator, next id = max + 1): one D- entry per operator ruling — Q-A like-semantics, Q-B dismiss + undo, Q-D positions-replace, Q-G naming — plus one for the **provisional** #402 vocabulary arbitration ("Tier up / Tier down / Same value"). **No ADR**: no architectural choice of ADR weight is made. |
| `docs/design/components.md` | **updated** | A `ShopCardPager` row in § Cards (or § Navigation for the mode chips) — the horizontally paged idea browser, its `1 / X` `TickLabel` header, and the ice-outlined mode chip row. |
| `mobile/src/components/CLAUDE.md` | **updated** | Two rows: `ShopCardPager`, `ShopPositionPicker`. |

## 5. Ship gate declaration

- **CI green** on the pushed sha: `backend-tests` (`pytest backend/tests`) ·
  `mobile-typecheck` (`npx tsc --noEmit` **and** the
  `for f in tests/check-*.js` loop — `.github/workflows/ci.yml:44`) ·
  `maestro-testid-lint` (`mobile/scripts/testid-lint.sh`).
  *Correction to the root `CLAUDE.md` §Stack claim that the `check-*.js`
  suites "gate nothing yet": they do gate CI. See `reconciliation-log.md` V-5.*
- **Ownership diff check** (a gate, not a test): `git diff --name-only
  origin/main` must contain none of
  `mobile/src/components/{AssetIdeasPanel,TradeCard,FeaturedTradeWindow}.tsx`,
  `mobile/src/utils/ideaToCard.ts`, `mobile/src/screens/TradesScreen.tsx`,
  `mobile/tests/check-single-pin-actions.js`.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming what ran
  and what it proved — including, per `prd.md` §6.4, the **red-under-sabotage
  then green-after-revert** pair for each of T-B1…T-B9 and A-1…A-13. A pass
  count is not the evidence; the sabotage pair is.
- **TestFlight verification:** `prd.md` §6.5, 19 steps, run by the operator,
  outcome logged in TEST_LEDGER.
- **Simulator gate:** there is no tier to declare and no
  `qa/sim-runs/last-sim-run.json` to write (D-056). `FTF_SKIP_SIM_GATE=1` is
  the standing posture for `githooks/pre-push`; note the evidence run in its
  place. (`docs/runbook.md` § Pre-ship simulator gate still describes the
  retired 4-tier matrix — history, not instruction.)
- **Express lane declared by the operator?** **No.** Full gates apply. This
  change touches an **API contract** (`swap_positions`, `record_elo`) and
  **analytics events**, so it is on the `CLAUDE.md` bright line: an express
  declaration here would need an explicit confirming yes, and agents never
  self-select express.

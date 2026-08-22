# Feature Scope — #384 Manual calculator becomes the merged trade surface

<!--
Copied from docs/templates/feature-scope.md. Written RETROSPECTIVELY on
2026-08-22, covering waves W0–W5 as they now stand on
`claude/manual-calculator-e2e-review-39a467`.

Writing it late is itself a finding: the e2e review's item #12 records that
gate 1 ("scope block first") was skipped for the whole build, which is how
three tour events reached a runner with no registry row and how the flag
prerequisites went unwritten until a reviewer read the flag file. This
document is the correction, not a formality — the flip is still pending and
this is what the flip is judged against.
-->

**Date:** 2026-08-22
**Entry point:** feedback #384 (canonical), folding #310 / #379 / #380, touching #333
**Builder:** waves W0–W4 (one session, `feat/calc-finder-merge`), W5 (three Opus build packages, lead-reviewed)
**Operator sign-off on waivers:** **PARTIAL** — §6 item 1 (the ✓ contract) was ruled and built as W6-A on 2026-08-22 ([D-152]). §6 items 2, 4 and 5 and the genuine §3 runtime-evidence waiver are still open. Surface them before the flag flips.

---

## 1. Analytics scope

**(a) New events specced.** 13 client event names were registered in `backend/analytics_taxonomy.py`
(commit `fcf3413`, W5-B) — 12 new #384 emitters plus `prompt_deferred`, which has had a live emitter
since the prompt arbiter shipped and was never registered. The registry is **default-deny behind a
200**: `analytics_ingest.py` counts and drops an unregistered name while still answering success, so
before W5-B every `calc_tour_*` envelope the W4 runner sent was silently discarded.

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `calc_tour_started` | `source` ∈ `auto` \| `show_me_around` | `startCalcTour` accepts a run (`utils/calcTour.ts`) | mobile |
| `calc_tour_ended` | `reason` ∈ `finished` \| `abandoned`; `beats_shown` int ≥ 0 | `endTour` — every exit, including a blur or a park timeout | mobile |
| `calc_tour_beat_missing` | `beat` (script id `n10`…`n24`) | the runner names a beat `analystScript.ts` cannot build | mobile |
| `calc_mode_switched` | `mode` ∈ `live` \| `league` (the mode switched TO) | `switchMode` on the calculator's tab row | mobile |
| `calc_include_players_toggled` | `on` bool (resulting state) | the merged action row's Include-players toggle | mobile |
| `calc_asset_added` | `side` ∈ `give` \| `receive` | a player/pick is added to the canvas | mobile |
| `calc_cleared` | `mode` ∈ `live` \| `league` | the canvas is cleared | mobile |
| `calc_find_a_trade_tapped` | `include_players` bool, `give_count` int, `receive_count` int, `has_partner` bool | the merged action row's Find a Trade — the conversion moment of the whole merge | mobile |
| `deck_back_to_calculator` | `pin_count` int ≥ 0 | end-of-deck "Back to calculator" | mobile |
| `deck_unpin_retry` | `pin_count` int ≥ 0 | end-of-deck "Search without …" | mobile |
| `trade_pass_overlay_opened` | *(none — deliberately)* | the ✕ overlay presents on a calculator-origin deck | mobile |
| `trade_pass_overlay_dismissed` | `banked` bool | the overlay is backdrop-dismissed | mobile |
| `prompt_deferred` | `surface` (InterruptSurface), `blocked_by` (`'tour'` or the holding surface) | the arbiter refuses a prompt — `blocked_by:'tour'` is the ruling-10 mute made measurable | mobile |
| `calc_trade_queued` **(W6-A, 2026-08-22)** | `queued` bool; `reason` only on `queued: false` — the six `POST /api/trades/queue` refusal codes plus the client-only `error` | the merged action row's ✓ cell answers, either way | mobile |

**INTENT classification is by SUBTRACTION**, so six of the thirteen were added to
`analytics_queries.NON_INTENT_EVENTS` **in the same commit**: `calc_tour_started` (the tour
auto-starts on landing — admitting it promotes every calculator visit to a user-day),
`calc_tour_ended`, `calc_tour_beat_missing`, `trade_pass_overlay_opened`,
`trade_pass_overlay_dismissed`, `prompt_deferred`. The other seven are real user decisions and stay
INTENT deliberately. **W6-A adds an eighth INTENT name, `calc_trade_queued`** — the ✓ tap is the
user's decision to offer the trade (the `sleeper_send_attempted` class), it fires on a refusal
too because a refusal is the answer to that decision, and it cannot open a DAU seam because a
filled canvas already fired `calc_asset_added`.

No `platform` prop is carried on any row — device platform is a `user_events` column derived
server-side. That is the NULL-`platform` incident's rule, and it is why it is written here.

Tracking-plan addendum: `docs/business/analytics/2026-08-22-384-calc-finder-addendum.md`.

**Adoption events — all registered, six of them weak.** Every `adoptionEvent` named by the fifteen
beats resolves to a registered event: `calc_asset_added`, `outlook_saved`, `find_trades_tapped`,
`trade_pass_layer1`, `trade_swap_suggest_opened`, `deck_regenerated`, `help_opened`,
`sleeper_send_attempted`, `deck_card_viewed`, `calc_tour_started`. The review's claim that
`trade_card_swap` / `send_attempted` / `trade_disposition` were named and missing is stale — no
shipped beat uses those names.

**Honest caveat:** n10, n13, n14, n15, n17 and n18's sibling beats declared
`adoptionEvent: 'calc_tour_started'` — the tour's own start. That is not a downstream behaviour
thesis; it was a placeholder that makes those beats' §5.0 "no event, no thesis" rule pass
without answering it. They narrate controls with no dedicated event (Find a Trade's own label,
Clear, the ✓, the mode tab). **W6-A fixed n15**: the ✓ now has a mechanism and its own event, so
`n15.adoptionEvent` is `calc_trade_queued`. The rest still carry the placeholder.

## 2. Schema & flag scope

- **New/changed tables or columns: none.** No `backend/database.py` change in any wave —
  including W6-A, which adds a read-only helper (`find_live_trade_like`) over the existing
  `trade_decisions` table and no column. `docs/data-dictionary.md` therefore n/a.
- **New/changed feature flags: one — `calc.merged_layout`, default `false`.**
  Declared in `config/features.json`, allow-listed in `backend/feature_flags.py` `FLAG_KEYS`,
  mirrored in `backend/tests/fixtures/flags/release.json`, documented in `docs/config-reference.md`.
  Graduation criterion: the TestFlight checklist in this folder passes on a real device **and** the
  four bright-line decisions in §6 are ruled.

  **Five PREREQUISITE flags.** `calc.merged_layout` on its own does not deliver the feature the
  operator specced. Each of these gates a piece the tour narrates:

  | Flag | Today | What it gates here | With it OFF |
  |---|---|---|---|
  | `onboarding.v2` | `true` | master kill-switch — every `onboarding.*` flag is ANDed with it | no guided anything; the tour never runs |
  | `onboarding.guided_avatar` | `true` | the Analyst overlay itself (`AnalystGuide`) | no bubbles at all; `startCalcTour` returns false and the "Show me around" link does not render |
  | `onboarding.guide_v2` | **`false`** | the whole v2 layer: spotlights (`targeted = v2 && !!step.target`), `degradeLine`, per-beat display caps, retirement, and the guide's claim on the arbiter slot | every deictic beat renders as a floating bubble pointing at nothing. `startCalcTour` refuses on this flag, so today the tour **does not run at all** and the link is hidden |
  | `ux.prompt_arbiter` | `true` | the interrupt slot AND the tour-long hold that rides it | ruling 10 is inert — quick-set prompts, banners and root modals can interrupt the tour freely |
  | `trade.outlook_direction` | **`false`** | `OutlookBiasReceipt`, the outlook row the tour's n11 beat is about | the receipt renders nothing; W5 added an honest **`calc.outlook-fallback`** row ("Not set" + Change) so the merged page still has an outlook section and n11's CTA still opens `TradeDnaSheet` |

  Two of the five are OFF today. **`onboarding.guide_v2` is the load-bearing one**: flipping
  `calc.merged_layout` alone ships the merged layout with no tour. That is a coherent state (W5
  gates the auto-start on it) but it is not the feature as specced, and it must be a decision
  rather than a surprise.

- **New env vars / `model_config` keys: none.**
- **Deploy-free rollback lever:** `calc.merged_layout` → `false` in `config/features.json`, push,
  Render redeploys; clients pick it up from `/api/feature-flags` with no rebuild. The demo-calculator
  removal (W0) is **outside** the flag and is not reversible this way — it was an unconditional
  deletion on the operator's call.

## 3. Evidence scope

**Maestro delta: n/a — retired per [D-056](../../../living-memory/DECISIONS.md) (2026-08-15).** No
flow was authored, extended or run, and `mobile/.maestro/` was not touched. The template's Maestro
row is a dead section.

**Structural guards** — five new, all sabotage-verified (`mobile/tests/`):

| Guard | Pins |
|---|---|
| `check-demo-calc-removed.js` | two-sided: the demo CALCULATOR is gone (fixture deleted, no importer, `'demo'` out of the `CalcMode` union, no tab) **and** the demo SESSION is untouched (`isDemo`, `/api/session/demo`, `startDemoSession`, `landing.try_before_sync`, the share-mint refusal, the 400 narrowing, all three demo-bridge anchors). Plus: no demo-calculator instruction copy survives in `TradeCalculatorScreen.tsx` |
| `check-calc-merged-layout.js` | the flag exists on both sides of the wire; the flag read is the bare statement (no `\|\| true`, no `!`); every merged-only testID is excised by brace-balancing when the flag is off; `compact` comes from the flag at both `TradeSide` mounts; the guide-target registration bails on `!merged` and re-runs on it; the price is moved not dropped; the 11pt type floor and the 44pt tap floor in the 15% cells; format chips + conversion note survive the merge; league-keyed remount; `popTo` not `navigate` |
| `check-calc-merged-behavior.js` | `reasonsAsOverlay` is a PROP, gated in the host on flag **AND** `deckOrigin === 'calculator'` (statement-anchored); the overlay stays up through layer 2 and commits the deferred advance on a dismiss-after-bank; `includePlayers &&` is IN the pin condition; `packageMode`; both end-of-deck exits in both exhausted branches, for any pin count, regenerating **W6-A** — the screen passes `onLikeTrade` (dropping it is the exact Q-029 regression and turns assertions 18–18e red); the handler calls `queueTradeForOpponent`, addresses the canvas's partner, emits one `calc_trade_queued` and distinguishes a refusal from a dead request; every one of the six reasons has a toast line AND a `CalcQueueReason` member; the disabled rule is exactly `!onLikeTrade || !bothSides || !opponent || queueing`; the in-flight lock is both set and released; and neither file reaches for `swipeTrade` to fake the like |
| `check-tour-suppression.js` | **transpiles and EXECUTES** `useInterruptCoordinator.ts` (minimal zustand shim) — claim/release/hold, no preemption, the gap between beats, idempotent begin, `isInterruptBusy` from the hold alone. Plus the four in-flow notices' mute and the `blocked_by:'tour'` emitter |
| `check-calc-tour.js` | 15 beats, argument-free, screen-declared, in order; every `advance:'action'` beat has an `advanceGuideIfActive` call site; one hold-release site; park + 30 s bound + hand-off-aware blur; the first-visit receipt; cap reset on re-entry; cursor reset on restart; the auto-start effect's deps; tour-owned ids registered without a store cycle |

`check-guide-script.js` was extended for the 15 new beats (copy budget, retirement, degrade
contract, the n23/n23b platform pair) — including a new rule that a `degradeLine` may exist only on
a beat that has a `target` to lose.

**Guard hardening, 2026-08-22 (review #13).** The review's QA pass ran 61 sabotage cycles and found
12 that stayed green. Fifteen named sabotages were re-run after this session's edits; all fifteen
are red, each against a specific assertion. All 76 guards pass; 19 previously unscripted guards were
wired into `mobile/package.json` as `test:<name>`.

**Unit tests.** Through W5 the only backend change was the taxonomy/classification registration,
covered by `backend/tests/test_analytics_taxonomy.py` and the NON_INTENT invariants — no new
backend behaviour. **W6-A adds one route and one test file**,
`backend/tests/test_calc_trade_queue.py` (26 tests): the flag gate; the happy path down to the
`trade_decisions` row and the Elo signal; **the recorded like actually surfacing through
`_inject_likes_you_cards` when the counterparty's deck generates** (the assertion that makes
`queued: true` mean something); every one of the six refusal reasons, each asserting that NOTHING
was recorded; idempotency (no second row, no second `swipe_decisions` row, no doubled in-memory
Elo); the deterministic id's set semantics; the 400s; and the analytics registration +
INTENT classification. Five named backend sabotages, all red and reverted: the idempotency probe
forced to miss, the mirror predicate forced to pass, the refusal branch bypassed, the flag gate
opened, and the preference lists read for the CALLER instead of the counterparty.

**Code-walk proof:** the e2e review (`review-2026-08-22-e2e.md`) is the trace, file:line-cited
throughout, plus the three W5 commit bodies which cite the fixes back to its item numbers.

**Manual TestFlight checklist:** `testflight-checklist.md` in this folder, rewritten 2026-08-22
against current behaviour (A/B/C/D + a Prerequisites table). **UNRUN.**

**WAIVED — runtime evidence:** nothing in this feature has ever executed on a device or a
simulator (D-056). Every claim above is structural or a code-walk. That is the standing posture,
but it is worth naming explicitly here because this feature is *entirely* presentation and timing:
two-column layout at SE width, 53pt tap targets, spotlight geometry, and the beat-to-beat rhythm of
a 15-step tour are exactly the class of thing a structural guard cannot see.

**No new testIDs in W6-A** — the ✓ cell already had `calc.action.confirm`; it only stopped being
inert. **testIDs added (W0–W5):** `calc.action-row`, `calc.action.find-a-trade`, `calc.action.include-players`,
`calc.action.clear`, `calc.action.confirm`, `calc.league-dropdown`, `calc.team-dropdown`,
`calc.trade-columns`, `calc.team-sheet`, `calc.outlook-fallback`, `calc.outlook-fallback.change`,
`calc.merged-format.<key>`, `calc.mode-tab.<key>`, `calc.league-give-add`,
`trades.pass-reason-overlay`, `trades.deck-summary.back-to-calc`, `trades.deck-summary.unpin-retry`,
`trades.deck-exhausted.back-to-calc`, `trades.deck-exhausted.unpin-retry`. `bash
mobile/scripts/testid-lint.sh` passes.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | **updated (W6-A)** | W0–W5 added no route. **W6-A adds ONE: `POST /api/trades/queue`** ([D-152]) — the ✓ cell's contract, flag-gated on `calc.merged_layout` (404 off). Full row in `api-reference.md`: body, both 200 shapes, the closed `reason` enum, the idempotency key, and what `queued: true` does and does not promise. Everything else on the merged page still rides `POST /api/trade/evaluate`, the #330 choke point and the shipped pin store verbatim. **§6 item 2 (receive-side all-mode) remains OPEN, not built** |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | **updated (W6-A) — route list only** | W6-A adds `POST /api/trades/queue` to the LLD's Trades route list, and `docs/architecture.md`'s trade-match lifecycle step 1 now names it as the second way a like is recorded (and says why it does NOT mint the match itself). No convention shifted (W0–W5): the one new module (`utils/calcTour.ts`) follows the existing `utils/` rule (no React, no store) and the existing guide-store contract; the tour-owned id set is registered INTO `useGuide` rather than imported FROM it, which is the existing no-cycle convention, not a new one |
| `docs/architecture.md` (module wiring / data flow changed) | **updated (W6-A) — one lifecycle line** | still no backend module added, removed or re-wired: W6-A is one route in `server.py` and one read-only helper in `database.py`. The trade-match lifecycle DID gain a second entry point, so step 1 names it |
| `living-memory/HLD.md` (architecture genuinely shifted) | **n/a** | no new client, no new service, no new major flow at the system level. The calculator→deck hand-off reuses `useFinderTargets`, which already existed |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | **updated (W6-A)** | W0–W5's enums (`calc_tour_started.source`, `calc_tour_ended.reason`, `deckOrigin`, `FinderHandoff.origin`) are mobile-only and stay unlisted. **W6-A's `reason` enum is not**: `POST /api/trades/queue` refuses with one of six codes and the client switches on every one, so a seventh added server-side would fall through to a generic line. New section **Trade-queue refusal reasons**, with the three locations that change together (server tuple, `CalcQueueReason`, `queueRefusalLine`). `calc_trade_queued` also joins the client-event contract section |
| `docs/glossary.md` (new domain term) | **updated** | "Demo league" (calculator) retired; **Real values**, **In league**, **Show me around**, **Tour hold** added. Canvas is defined under Real values / In league. **W6-A adds "Queue (a trade)"** — the ✓ cell's verb, and the one word that could be mistaken for `useTradeQueue`, the unrelated web-style list of Sleeper propose URLs |
| ADR or `DECISIONS.md` entry | **updated** | [D-150](../../../living-memory/DECISIONS.md) carries the feature's decisions; amended 2026-08-22 (W5) for the unwired ✓ cell and the calculator-origin overlay scope |

Also updated in the same pass, outside the template's rows:
`docs/feedback/items/INDEX.md` (row 384 → `built-dark`), this folder's `status.md`,
`config/features.json` `_comment_calc_merged_layout` and the `docs/config-reference.md` row (both
carried a false "no payload or analytics event changes in either state" claim),
`mobile/src/screens/CLAUDE.md`, `mobile/src/components/CLAUDE.md`, `mobile/src/state/CLAUDE.md`,
`mobile/src/utils/CLAUDE.md`, `mobile/tests/README.md`, and two new
`living-memory/OPEN_QUESTIONS.md` entries (Q-028, Q-029).

## 5. Ship gate declaration

**Simulator-gate tier: n/a — retired per [D-056](../../../living-memory/DECISIONS.md)
(2026-08-15).** There is no tier to declare and no `qa/sim-runs/last-sim-run.json` to write. The
template's tier matrix and `docs/runbook.md` § Pre-ship simulator gate are dead sections.

- **CI green:** W5 — `pytest backend/tests` 4128 passed / 1 skipped · `npx tsc --noEmit` clean ·
  `bash mobile/scripts/testid-lint.sh` OK · **76/76** `check-*.js` guards.
  W6-A — see the W6-A section of [`status.md`](status.md) for the re-run numbers.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` — the W0–W4 entry plus the W5 entry naming
  the fifteen sabotages and their assertions.
- **TestFlight verification:** checklist written (§3), **not run**. This is the gate that is still
  open, and it is the one that matters most for a presentation-and-timing feature.
- **Express lane declared by the operator?** No. Full gates apply — which is why this document
  exists, late.
- `githooks/pre-push`: `FTF_SKIP_SIM_GATE=1` is the standing posture per D-056.

## 6. Open bright-line decisions (operator)

These are carried here rather than in a build note because three of them are API/contract changes
and the fourth is an IA ruling — the exact class the feature-gate rule says an agent may not
self-select.

1. ~~**The ✓ like/queue cell has no mechanism.**~~ **RULED AND BUILT — W6-A, 2026-08-22
   ([D-152]).** The operator approved option (b), the new endpoint. `POST /api/trades/queue`
   records the package as the caller's LIKE through the swipe route's own path, and refuses —
   recording nothing — when the likes-you injector's own gates would not mirror it into the
   counterparty's deck. Neither of the two options this row proposed was taken as written: the
   share-package mint would have put a non-card in the likes surface, and "cut the cell" is moot.
   The third option the build found is what shipped — the predicate that decides the mirror is a
   pure function of state the request already holds, so it is evaluated UP FRONT and the refusal
   is named rather than silent. Contract, both 200 shapes and the reason enum:
   [`api-reference.md`](../../api-reference.md); enum:
   [`cross-client-invariants.md`](../../cross-client-invariants.md#trade-queue-refusal-reasons-post-apitradesqueue).
2. **Receive-side "must include" is any-one, not all.** `trade_optimizer.py:522` requires only that
   the served card's receive side intersect the pinned set; the give side with 2+ pins requires
   every one. A `pinned_receive_mode:'all'` would be an **API change** through `api/trades.ts` →
   `server.py` → the three enumerators. Also unresolved: a canvas pick outside `picks_pool_cap`
   (default 6) is never on `user_roster`, so `pinned_all` rejects every subset and the user gets
   zero cards with a misleading message.
3. **Overlay scope — RULED and built as calculator-origin.** W5-D made `reasonsAsOverlay` a prop
   driven by `FinderHandoff.origin === 'calculator'`, cleared on league switch / pins emptied / mode
   switch. Recorded here because the review listed it as open; the alternative (all decks) would
   need an explicit operator reversal.
4. **§6b — "Manual | In league" two tabs (built) vs "replaces the manual calc tab" (ruled).** → **RULED 2026-08-22: own tab for now ([D-151](../../../../living-memory/DECISIONS.md)); Q-028 closed.**
   Round-2 ruling 3 says the new surface *replaces* the manual calc tab; the build kept two tabs and
   defaults to **Real values**. #310 asked for the calculator to be reachable without a league,
   which the two-tab form satisfies and a collapse would break. Logged as **Q-028**.
5. **Rollout shape** — a global boolean, or the tester-allowlist experiment path `trades_home_inline`
   used.

Items 1 and 2 were logged as **Q-029**. **Item 1 is CLOSED 2026-08-22 (W6-A).** Item 2 (receive-side
`pinned_receive_mode:'all'` + the `picks_pool_cap` pin rejection) is still open and is what remains of Q-029.

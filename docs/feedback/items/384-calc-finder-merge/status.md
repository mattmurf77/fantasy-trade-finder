# Status — #384 Manual calculator becomes the merged trade surface

**Status:** **BUILT DARK — W5 landed, checklist ready to run (2026-08-22)** — waves W0–W5 on `claude/manual-calculator-e2e-review-39a467`, `calc.merged_layout` **false**, not merged, not pushed. TestFlight checklist rewritten against current behaviour and **still UNRUN**. The [E2E review](review-2026-08-22-e2e.md)'s 5 P0 and most P1s are fixed — see the W5 section at the bottom for what was fixed, what is still open, and the **five flag prerequisites**. **Do not flip without reading those prerequisites: `onboarding.guide_v2` is `false` today, and flipping `calc.merged_layout` alone ships the merged layout with no tour.** Scope block (retrospective, gate 1 was skipped): [`scope.md`](scope.md).
**Date:** 2026-08-22
**Covered feedback IDs:** #384 canonical. Folds in **#310** (don't lock the manual calc behind trades; simplify nav), **#379** (filters back in-page, minimized default), **#380** (clicking a partner minimizes that section and raises the calculator). Touches **#333** (league/team as side-by-side dropdowns under the fold).
**Reported:** `mattmurf77`, screen `TradesHome`, v1.15.0, filed 2026-08-22T03:04Z
**Filed severity:** `bug` — **it is a feature/IA spec**; treat as such.

> **This report is the one the 2000-char cap ate.** Written 03:04Z, delivered 04:26Z after the
> cap raise ([D-149](../../../living-memory/DECISIONS.md), [G-055](../../../living-memory/GOTCHAS.md)).
> 2,803 characters — it would have been lost permanently under the old limit.

---

## Scope, per the operator

**Only the manual calculator page changes.** The Find a Trade page is left alone this round.
*"Eventually will replace it. For now we're leaving that page alone and just editing the manual
calc page."* The eventual merge of the two surfaces is the direction; this is the test of it.

## Operator rulings — 2026-08-22, in answer to the report's own step 13

The report asked to be prompted on any Find a Trade controls its tour missed. Ten were found.
All ten were ruled on:

| # | Control found | Ruling |
|---|---|---|
| 1 | `feedback.decline_reasons` is **on** — the ✕ is *replaced* by three inline tiles (Value · Fit · Neither) | **✕ stays a single button.** Tapping it **pops the decline reasons as an overlay over the page**. This is a presentation change from the shipped inline-tile form |
| 2 | Three send buttons exist (`trades.send-sleeper-btn` / `-espn-btn` / `-mfl-btn`) | **Show the one that matches the user's league platform.** The tour names that platform, not Sleeper unconditionally |
| 3 | `trade-card.edit-in-calc` already bridges deck → calculator | Left alone; superseded eventually by the merge |
| 4 | `trade-card.remove-asset.<id>` is distinct from swap | **Both removal and add-a-player are explicit buttons** on the page |
| 5 | Untouchable/lock via long-press (`trade.preference_lists` on) | Covered by the end-of-deck ruling below |
| 6 | The utility row carries six entries (conditions · draft · free agents · manual calc · today's trade · track record) | **Hidden on this page for now** |
| 7 | Subnav is three tabs (Trades · Portfolio · Calculator) | **Does not exist.** The report's own step 2 "tabs" are a NEW two-way in-league/manual control, not this |
| 8 | End of deck is a summary state (See liked · Done · Pin), not an automatic next card | **Add a "back to calculator" button.** If the user had a player locked/pinned, **also offer "find a trade without that player pinned"** |
| 9 | `trades.package-toggle` and `trades.fairness-help` unexplained | **Add both to the tour** |
| 10 | Interstitials can interrupt (quick-set prompt, outlook receipt, banners) | **Mute all other interstitials and analyst prompts for the duration of the scripted tour** |

**Also settled:** the Sleeper password claim in tour step 14 is accurate as written — operator
confirmed, no verification needed. The report's step numbering starting at 2 was a typo, not a
missing beat.

## One reading I had to make — flag if wrong

Rulings 6 and 7 both arrived as short lines ("For now that tab view is hidden on this page" /
"The tab subnav doesn't exist"). I read them as: **the six-entry utility row is hidden on this
page**, and **the three-tab Trades/Portfolio/Calculator subnav is gone entirely**. Both point the
same way — neither appears on the new page — so the plan is written to that reading. If "that tab
view" meant something else, the layout section is the part to correct.

## Where the plan is

[`plan.md`](plan.md) — layout spec, the tour as authorable guide steps, and the four things that
need a decision before a build agent starts.

## Round-2 rulings — 2026-08-22, answering plan §5

| # | Ruling |
|---|---|
| 1 | ✕ → decline-reason overlay applies to **this calculator only**; the deck keeps its inline tiles |
| 2 | **Include Players ON ⇒ the search must include the players on the canvas**; OFF ⇒ unconstrained by the canvas |
| 3 | The new surface **replaces the manual calc tab and lives within the league calc**. **Remove the demo calculator** — "it's pointless" |
| 4 | Tour is **re-runnable** via a **"Show me around"** link, **top right** of the page |
| + | The tour **auto-starts on landing** on the manual calc page, since its first beat carries the user to the league version |

**Two things surfaced by ruling 3, both recorded in [`plan.md`](plan.md) §6:**

1. **"Demo" is two systems.** The demo *calculator mode* (mock dual-board league) is the one being
   deleted. The demo *session* (`/api/session/demo`, try-before-signin, `onboarding.demo_bridge`)
   must not be touched — they share only a word.
2. **Ruling 3 collides with #310 and with the tour's own first step.** `TradesScreen.tsx:4944`
   records the current intent — *"Calculator … is always reachable — it needs no league"* — and
   #310 is the report that asked for it. The plan proceeds on a stated assumption (two tabs,
   `Manual` | `In league`, demo deleted, rich spec on the league side) which needs a yes/no.


## Build record — 2026-08-22, waves W0–W4

| Wave | Commit | What |
|---|---|---|
| W0 | `224a830` | Demo CALCULATOR removed (net −239 lines). Demo SESSION untouched — verified by empty `git diff` over its five files |
| W1 | `dfcd532` | Merged layout behind `calc.merged_layout` (OFF): outlook beat, league/team dropdowns, two columns, the 40/30/15/15 action row |
| W2 | `56111a0` | ✕→overlay reasons, end-of-deck exits, include-players via the finder pin store. Send button: **already platform-aware, no code**. ⚠️ **This row's original wording presented the ✓ like/queue cell as built. It is not** — nothing passes `onLikeTrade`, so the cell has always been permanently disabled; see the W5 section and Q-029 |
| W3 | `4ff15f3` | Tour-long hold on the EXISTING prompt arbiter (it already existed — the plan overpriced this) |
| W4 | `ae605ad` | 15 tour beats compressed to the CI copy budget + `utils/calcTour.ts` runner + both entry points |

**Gates, every wave:** pytest 4117 passed / 1 skipped · `tsc --noEmit` clean · testid-lint OK ·
structural suites 71 → **76**. Four new guards, all red-proofed: `check-demo-calc-removed`,
`check-calc-merged-layout`, `check-calc-merged-behavior`, `check-tour-suppression`,
`check-calc-tour`.

**Five dead assertions found and fixed while red-proofing** — in my own guards, not in the
product: two substring anchors that survived their own sabotage (`/isDemo/` matched
`isDemoRenamed`, `/onDemo/` matched `onDemoStarted`), a backwards proximity search for the
flag gate that passed when the gate it should have been reading was replaced, a fixed-size
window that read the next JSX prop's body, and a drift detector that threw instead of failing
a named assertion.

**Two things the build corrected in the plan:**
- W3 was priced as "build a suppression gate across six surfaces". `useInterruptCoordinator`
  already was that gate, live behind `ux.prompt_arbiter`. The real gap was narrower and more
  interesting: the slot frees BETWEEN steps, so a tour needs a hold, not a per-step claim.
- The send-button ruling needed no code at all — `resolveSendPlatform` already routes
  Sleeper/MFL/ESPN.

**Pre-existing defect reported, not absorbed:** `InLeagueCalculator.lineupHeadText` is
`fontSize: 10`, under the Chalkline 11pt floor, on `origin/main` since #297. Not introduced
here and not fixed here.

---

## W5 — 2026-08-22: the journey works on paper, and the paper trail exists

Three build packages on `claude/manual-calculator-e2e-review-39a467`, each answering
[review](review-2026-08-22-e2e.md) items by number. Nothing above this line is rewritten — the
W0–W4 record is what it was, including where it was wrong.

| Commit | Wave | Review items closed |
|---|---|---|
| `fcf3413` | W5-B — analytics | **#12 (analytics half).** 13 client event names registered in `analytics_taxonomy.py` with exact prop allowlists; six classified NON_INTENT in the same commit (INTENT is derived by subtraction). Before this the registry was default-deny behind a 200 and every `calc_tour_*` envelope was counted-and-dropped. `beats_shown` now snapshots before `endTour` resets the counter. Addendum: `docs/business/analytics/2026-08-22-384-calc-finder-addendum.md` |
| `9dcd003` | W5-D — the deck side | **#1** the ✕-overlay stays up through layer 2 (only the two advancing callbacks close it) and a backdrop dismiss after a banked tile commits the deferred advance — the P0 dead-end. **#7** `reasonsAsOverlay` is a host-set PROP gated on the flag **AND** `deckOrigin === 'calculator'`, cleared three ways. **#3 (b)** `FinderHandoff` gains `origin`/`includePlayers`/a nullable opponent and the #330 choke point regenerates on a calculator arrival even with no partner. **#9** Back-to-calculator via the #190 prefill shape; unpin-retry for any pin count and it regenerates; both exhausted branches carry both exits. **#3 (c)** the three deck guide targets registered |
| `a52c91e` | W5-T — the tour | **#2** n10/n16/n17/n18 advance on the real action. **#3 (a/b)** `popTo`, not `navigate` — routers 7.5.3 pushed a *second* `TradesHome` ([G-056](../../../living-memory/GOTCHAS.md)); the runner PARKS after n18 and resumes when the deck says a card exists, 30 s bounded. **#8** first-visit `calc_tour_completed` receipt gates the auto-start; "Show me around" resets the per-beat caps and dismisses a stale bubble; a run-ahead Find a Trade jumps to the deck half; `endTour` takes down its own bubble. **#4 (partly)** n11 opens the DNA sheet through an opener ref, and an honest outlook **fallback row** stands in when `trade.outlook_direction` is dark. **#11 (partly)** format chips + conversion note restored in the merged header. **#10** league-keyed remount. **#14/#15/#17/#19/#24** hasLeague gate, the #213 link steps aside, n23/n23b by platform, n19's "Clear became the ✕", n14 after n16, the stale demo-league copy |

**This session (evidence + paper trail, no product code).** Review **#13**: fifteen named sabotages
re-run against the current files — all fifteen red, each against a specific assertion (flag read
anchored to its statement so `|| true` and `!` both fail; `compact` must come from the flag; the
target-registration effect must bail on `!merged`; `includePlayers &&` must be *in* the pin
condition; `reasonsAsOverlay` anchored to its terminator; `check-tour-suppression` now **transpiles
and executes** `useInterruptCoordinator.ts` instead of re-implementing it, so `endTourHold: () => {}`
and `beginTourHold: () => {}` are red; the `blocked_by:'tour'` assertion anchors the emitter, not the
doc comment; `cursor = 0` on re-entry; the auto-start effect's deps; the demo-bridge surface by three
named anchors; a `degradeLine` may exist only on a beat with a `target`). The 19 remaining unscripted
guards were wired into `mobile/package.json`. Review **#12**: [`scope.md`](scope.md) written
retrospectively — every section answered, the Maestro and simulator-tier rows marked dead per D-056.

**Gates:** `npx tsc --noEmit` clean · `bash mobile/scripts/testid-lint.sh` OK · **76/76** guards ·
pytest 4128 passed / 1 skipped.

### Flag prerequisites — read before flipping

`calc.merged_layout` alone does not deliver the specced feature. Two of the five prerequisites are
**off today**:

| Flag | Today | Gates | With it OFF |
|---|---|---|---|
| `onboarding.v2` | `true` | master — ANDed with every `onboarding.*` flag | no guided anything |
| `onboarding.guided_avatar` | `true` | the Analyst overlay | no bubbles; `startCalcTour` returns false and the link does not render |
| **`onboarding.guide_v2`** | **`false`** | spotlights (`targeted = v2 && !!step.target`), degrade lines, per-beat caps, retirement, the arbiter claim | **the tour does not run at all** and "Show me around" is hidden. Flipping `calc.merged_layout` alone ships the layout with no tour — coherent, but not the feature as specced |
| `ux.prompt_arbiter` | `true` | the interrupt slot **and** the tour-long hold | ruling 10 is inert; prompts and banners interrupt the tour freely |
| **`trade.outlook_direction`** | **`false`** | `OutlookBiasReceipt` — the row n11 is about | the receipt draws nothing; W5 added the honest `calc.outlook-fallback` row ("Not set" + Change) so n11's CTA still opens the sheet |

### Still open

1. **The ✓ like/queue cell is UNWIRED — the W2 row above is wrong about this.**
   `InLeagueCalculator.tsx` `disabled={!onLikeTrade || !bothSides}`; nothing passes `onLikeTrade`.
   There is no route that queues a hand-built package for a counterparty — the deck's like needs a
   server-minted `trade_id` and a canvas has no card. The cell renders disabled with an honest
   accessibility state; **beat n15 still describes it as working**, and
   [D-150](../../../living-memory/DECISIONS.md) Decision 3 has been amended to say so. Bright line —
   **Q-029**.
2. **Receive-side "must include" is any-one, not all.** The give side requires every pin
   (`pinned_give_mode:'all'`); the receive side only requires the served card to *intersect* the
   pinned set, in all three enumerators. Symmetry means `pinned_receive_mode:'all'` through
   `api/trades.ts` → `server.py` → the enumerators — an **API change**. Related: a canvas pick outside
   `picks_pool_cap` (default 6) is never on `user_roster`, so `pinned_all` rejects every subset.
   Bright line — **Q-029**.
3. **Overlay scope is now calculator-origin, not flag-scoped.** W5-D built round-2 ruling 1 as the
   operator wrote it: the shipped decks keep their inline tiles, and the overlay appears only on a
   deck the calculator handed off to. Recorded because the review listed it as open; reversing it to
   "all decks" would need an explicit call.
4. **§6b — two tabs (built) vs "replaces the manual calc tab" (ruled).** Unanswered since the plan.
   The `Real values` tab *is* #310's league-free calculator, and the tour's opening beat n10 exists
   to carry the user from it to `In league`; collapsing to one page re-answers #310 and needs a new
   opening beat. **Q-028**.
5. **Rollout shape** — a global boolean, or the `trades_home_inline` tester-allowlist experiment path.

### Known-unfixed, carried forward

The action row is still **inside** the page `ScrollView` rather than pinned as a footer (review #11)
— with 3+ assets per column it scrolls out of frame, against the report's one "important". The
outlook row is a receipt, not a disclosure. The mode row still renders a single lonely chip for a
league-less user (review P2 #14). `lineupHeadText` remains `fontSize: 10`, a pre-existing Chalkline
floor breach from #297, not introduced and not fixed here.

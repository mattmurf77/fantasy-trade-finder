# Status — #384 Manual calculator becomes the merged trade surface

**Status:** **BUILT DARK — W6-B landed, checklist ready to run (2026-08-22)** — waves W0–W5 on `claude/manual-calculator-e2e-review-39a467`, `calc.merged_layout` **false**, not merged, not pushed. TestFlight checklist rewritten against current behaviour and **still UNRUN**. The [E2E review](review-2026-08-22-e2e.md)'s 5 P0 and most P1s are fixed — see the W5 section at the bottom for what was fixed, what is still open, and the **five flag prerequisites**. **Do not flip without reading those prerequisites: `onboarding.guide_v2` is `false` today, and flipping `calc.merged_layout` alone ships the merged layout with no tour.** Scope block (retrospective, gate 1 was skipped): [`scope.md`](scope.md).
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

1. ~~**The ✓ like/queue cell is UNWIRED**~~ — **BUILT, W6-A (see the section below).** The
   operator ruled the contract; `POST /api/trades/queue` is live behind the same flag, beat n15's
   copy turned out to be accurate as written, and its placeholder `adoptionEvent` is now
   `calc_trade_queued`. The Q-029 half about the ✓ is **CLOSED**.
2. ~~**Receive-side "must include" is any-one, not all.**~~ **RETIRED 2026-08-22 by W6-B ([D-153])
   — see the W6-B section below. The concept no longer exists: a filled canvas does not run a
   pinned model job at all.** *(Kept as written, because the reasoning it records is what the
   ruling overturned.)* The give side requires every pin
   (`pinned_give_mode:'all'`); the receive side only requires the served card to *intersect* the
   pinned set, in all three enumerators. Symmetry means `pinned_receive_mode:'all'` through
   `api/trades.ts` → `server.py` → the enumerators — an **API change**. Related: a canvas pick outside
   `picks_pool_cap` (default 6) is never on `user_roster`, so `pinned_all` rejects every subset.
   Bright line — **Q-029**.
3. **Overlay scope is now calculator-origin, not flag-scoped.** W5-D built round-2 ruling 1 as the
   operator wrote it: the shipped decks keep their inline tiles, and the overlay appears only on a
   deck the calculator handed off to. Recorded because the review listed it as open; reversing it to
   "all decks" would need an explicit call.
4. ~~**§6b — two tabs (built) vs "replaces the manual calc tab" (ruled).** Unanswered since the plan.~~ **RULED 2026-08-22: own tab for now** — [D-151](../../../living-memory/DECISIONS.md), Q-028 closed. The built two-tab form stands.
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

---

## W6-A — 2026-08-22: the ✓ cell has a contract, and it refuses out loud

Nothing above this line is rewritten except the two "Still open" rows W6-A actually closes. The
W0–W5 record stands, including where it was wrong about this cell.

**What the operator asked for, verbatim:** *"queue this trade for the other manager — it shows up
in their suggested trades if it meets their preferences."*

**The reading that made it buildable.** That sentence names two systems that already exist and
adds no third one:

| The words | The system |
|---|---|
| "queue this trade" | the deck's **like** — a `trade_decisions` row, written by `_reconstruct_swipe_card` → `record_decision` → `save_trade_decision` / `save_trade_swipes`, the exact path `POST /api/trades/swipe` uses |
| "shows up in their suggested trades" | the **likes-you injector** (`server._inject_likes_you_cards_impl`, flag `trade.likes_you`), which reads precisely those rows and mirrors them into a league-mate's deck |
| "if it meets their preferences" | that injector's own skip conditions — untouchables (#95), not-interested (#163), roster actionability, and the **D-096 quality ladder** (gate level, user-gain floor, directional `overpay_ok`, `filler_ok`) |

So the route mints nothing. Its only original content is a deterministic card id and one
predicate function.

**The decision that shaped it: up front, not at mirror time.** Every gate the injector applies is
a pure function of state the request already holds — league membership, both rosters, the
counterparty's two preference lists, the consensus seed board, and the live `model_config` knobs.
None of it needs the counterparty's session. So the route **evaluates the predicate before
recording anything**, and a refusal writes **nothing at all**: no `trade_decisions` row, no Elo.
The alternative — record the like and let the mirror silently drop it — would have moved the
caller's board and parked the trade in their "Awaiting them" list for an offer the other manager
was never going to see. The operator's "if" is load-bearing, and this is what honouring it costs:
one extra predicate, and a named reason instead of a shrug.

**What `queued: true` promises, and what it does not.** It promises *eligible* — every stable
precondition is met. It cannot promise *served*: the mirror also has to win one of three
`_LIKES_YOU_CAP` slots on their next deck, clear the R4 live-pipeline dedup, not already have been
swiped, and land inside the 90-day window, and none of those exist until they generate. That
distinction is written into the route docstring, `api-reference.md` and the checklist rather than
left for someone to discover.

### The contract

`POST /api/trades/queue` · `@_gate_unverified_write` · flag `calc.merged_layout` (404
`feature_disabled` when off, checked before any session work)

Body `{league_id, opponent_user_id, give_player_ids[], receive_player_ids[]}` — all required, both
arrays non-empty.

- `200 {queued: true, already_queued: bool, trade_id}`
- `200 {queued: false, reason, detail?}` — a refusal is a 200 because the request was well formed
  and the answer is a product answer
- `reason` ∈ `likes_you_off` · `not_league_member` · `assets_not_on_roster` ·
  `opponent_untouchable` · `opponent_not_interested` · `fails_fairness_floor` — closed and
  cross-client ([invariants](../../cross-client-invariants.md#trade-queue-refusal-reasons-post-apitradesqueue))
- `400` `missing_field` · `league_mismatch` (another league's members, rosters and seed board are
  not on this session, so the predicate is unanswerable rather than refusable)
- **Idempotency key:** `calcq_<sha1(user|league|opponent|sorted give|sorted receive)[:16]>`. Asset
  order is irrelevant; side order is not. The probe (`database.find_live_trade_like`) runs **before**
  `record_trade_signal` — deliberately unlike `swipe_trade`, whose G-049 / D-073 note leaves the
  in-memory signal ungated because a deck swipe cannot be re-fired at will and a ✓ tap can.
  A #318 retraction re-opens the package.

**Mutual-match detection is deliberately not run here.** The queued like reaches the counterparty
as a likes-you card and *their* swipe fires `check_for_match` through the shipped path, so a match
is still minted in exactly one place. The cost is that a package the counterparty had *already*
liked matches one deck-generation later instead of instantly; the benefit is that the 110-line
match/notify/push block is not duplicated into a second route.

### Files

| File | Change |
|---|---|
| `backend/server.py` | `CALC_QUEUE_REASONS`, `_calc_queue_denied`, `_calc_queue_trade_id`, `_calc_queue_mirror_reason`, and the route — inserted after `swipe_trade`, whose like branch it reuses line for line |
| `backend/database.py` | `find_live_trade_like` — read-only, over the existing `trade_decisions` table. **No schema change** |
| `backend/analytics_taxonomy.py` | `calc_trade_queued` in `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS` (`{queued, reason}`) |
| `backend/analytics_queries.py` | classified **INTENT** by documented exclusion from `NON_INTENT_EVENTS` — the tap is the user's decision to offer the trade, and it cannot open a DAU seam because a filled canvas already fired `calc_asset_added` |
| `mobile/src/api/trades.ts` | `queueTradeForOpponent` + the `CalcQueueReason` union |
| `mobile/src/components/InLeagueCalculator.tsx` | `onLikeTrade` gains `opponent`; the cell owns a `queueing` in-flight lock; `disabled` becomes `!onLikeTrade \|\| !bothSides \|\| !opponent \|\| queueing` |
| `mobile/src/screens/TradeCalculatorScreen.tsx` | the handler (request → one `calc_trade_queued` → toast → haptic) and `queueRefusalLine`, one line per reason |
| `mobile/src/components/analystScript.ts` | n15's `adoptionEvent` placeholder → `calc_trade_queued`. **Copy unchanged** — it turned out to describe the built mechanism exactly |

### Evidence

- **`backend/tests/test_calc_trade_queue.py` — 26 tests.** The flag gate; the happy path down to
  the row and the Elo signal; **the recorded like surfacing through `_inject_likes_you_cards` when
  the counterparty's deck generates** (the test that makes `queued: true` mean something); all six
  refusal reasons, each asserting nothing was recorded and the board did not move; idempotency (no
  second row, no second `swipe_decisions` row, no doubled in-memory signal); the id's set
  semantics; the 400s; and the taxonomy + INTENT classification.
- **Five backend sabotages, all red, all reverted:** idempotency probe forced to miss · mirror
  predicate forced to pass · refusal branch bypassed · flag gate opened · preference lists read for
  the CALLER instead of the counterparty.
- **`mobile/tests/check-calc-merged-behavior.js` +12 assertions (18–19d).** Four mobile sabotages,
  all red, all reverted: drop `onLikeTrade` from the screen (the literal Q-029 regression) ·
  `disabled={true}` · a generic refusal toast · the in-flight lock never released.
- **No new testIDs** — the cell already had `calc.action.confirm`; it only stopped being inert.
- **Runtime: still none** (D-056). Checklist steps **13 / 13a / 13b** are new and 13a is the one
  worth the setup cost: it needs a second account to prove the route reads *their* preferences,
  which is exactly the half no structural test can reach.

**Gates:** `pytest backend/tests` **4154 passed / 1 skipped** (was 4128/1; +26) · `npx tsc --noEmit`
clean · `bash mobile/scripts/testid-lint.sh` OK · **76/76** `check-*.js` guards.

### Still open after W6-A

The other four items in the list above are untouched. Q-029's **receive-side `pinned_receive_mode:'all'`**
half is still open and is still a bright-line API change; Q-028 (§6b) is unanswered; the overlay
scope and the rollout shape are still operator calls.

*(Superseded the same day — see W6-B below: Q-029's second half is CLOSED by retirement, and Q-028
was closed by [D-151].)*


---

## W6-B — 2026-08-22: Find a Trade forks, the toggle goes, and the tour ends on the deck

Nothing above this line is rewritten except the "Still open" rows W6-B actually closes. The W0–W6-A
record stands.

**Three operator rulings, one wave.**

| Verbatim | What it settled |
|---|---|
| *"I'm thinking that this type of request shouldn't go through our models. It should be a much simpler set of cards solving for fairness only. Similar to how we determine the consolidate and downgrade suggestions already."* | Find a Trade with a FILLED canvas is not a model run |
| *"C works"* — on what Include-players OFF should mean | The toggle is **dropped**. The canvas is always the anchor |
| *"Rather than have the user add players to the calculator, I want the tour to have them go through the find a trade feature without any players selected… the tour mentions they can add players and we'll find trades with those players included, and then the user is pushed to find a trade with the calc empty."* | The tour ends in the **modeled** cards |

**The contract these three add up to.** Find a Trade with an **EMPTY canvas** → the modeled deck,
exactly as W5 built it (the #330 hand-off auto-run). Find a Trade with **assets on the canvas** →
a fairness-only package search: `POST /api/trades/fair-packages`, one synchronous sweep, no model,
no job, no polling.

### The route

`POST /api/trades/fair-packages` · `@_gate_unverified_write` · flag `calc.merged_layout` (404
`feature_disabled` when off, checked before any session work) · session league only (400
`league_mismatch`).

Body `{league_id, give_player_ids[] (required, non-empty), receive_player_ids?, opponent_user_id?,
fairness_threshold? (default 0.50)}` →
`{basis:'consensus', anchor:{…}, ideas:[…], relaxed: bool, reason?}`.

- **The give side is an ANCHOR.** Every idea gives away exactly the canvas give set, in that order.
  The search is over the RETURN — 1–3 assets from the named partner's roster, or from every
  league-mate's when no partner is named, with owned picks injected through the same
  `_inject_owned_picks` helper the generate job and asset-ideas use.
- **The receive side is a PREFERENCE, not a constraint.** Ideas carrying all of the canvas receive
  assets sort first, then by |difference| ascending — but an idea that cannot carry them is still
  returned. This is the decision that **retires Q-029's second half**: a hard receive constraint
  hands the user an empty deck the moment the canvas names an asset the partner does not own, and
  an empty deck is a worse answer than a ranked one. The same choice dissolves the
  `picks_pool_cap` trap the old row worried about — the anchor is priced from the seed board and
  never re-checked against `user_roster`, so a pick outside the cap costs nothing.
- **The gates are shared, not copied.** `_generate_asset_ideas_impl`'s `_eval` closure was
  extracted to `trade_service.eval_consensus_package` and both surfaces now call it, so a fair
  package and an Upgrade/Lateral/Downgrade idea can never price the same trade differently.
  `generate_asset_ideas` is byte-identical — `test_asset_ideas.py` and
  `test_bakeoff_arm_a_golden.py` are the golden and both pass untouched.
- **Each idea carries a deterministic `trade_id`** — `fairpk_<sha1(user|league|opponent|sorted
  give|sorted receive)[:16]>`, the same construction and the same reasoning as W6-A's `calcq_`.
  These cards are never registered by a generator, so a swipe / ✓ / flag on one arrives with an id
  the in-memory deck has never seen and is rebuilt from the echoed card context by
  `_reconstruct_swipe_card` (FB-46). A stable id is what makes a re-swipe one row.
- **Flat list, one cap** — new `model_config` knob `fair_packages_cap` (20). A deck is not three
  groups, so it does not get asset-ideas' per-group cap.
- `reason` accompanies an EMPTY list only, and is **diagnostic, not a cross-client enum** —
  `give_untouchable` (an anchor asset is on the caller's own untouchable list: their rule
  contradicting their own canvas, so the honest answer is zero and why) · `unknown_asset` ·
  `no_partner` · `unknown_league`. No client branches on it; a client that starts to must add it
  to `cross-client-invariants.md` first.

### The toggle, and the tour

**Include players is gone** — the control, its state, its ref, its guide target, its event
(`calc_include_players_toggled`, removed from `ALLOWED_CLIENT_EVENTS` / `CLIENT_EVENT_PROPS` /
`NON_INTENT_EVENTS` and from the tracking-plan addendum), and its tour beat. The action row is now
**Find a Trade 70 / Clear 15 / ✓ 15**, same 44 pt floor.

`calc_find_a_trade_tapped` swaps `include_players` for **`path` ∈ `fair` | `model`** — the toggle
was the user's declaration, `path` is what the system actually did, and the two are not renameable
into each other. `deck_search_all_tapped` (INTENT, no props) is new.

**The tour is 13 beats**, `['n10','n11','n12','n13','n15','n16','n18']` + the unchanged deck half
n19–n24. n17 left with the toggle. **n14 left with it too**: it spotlighted Clear, which is
disabled on an empty canvas, and it only ever sat after n16 because n16 used to be the beat that
filled the canvas. Both builders are **deleted** from `analystScript.ts` rather than orphaned.

- **n16** is now `advance:'tap'` on `calc.league-give-add` — *"Add players you'd move and we'll find
  trades that include them."* (11 words; tap budget 20). It **informs**; it no longer commands. An
  action beat there could only advance on a real pick, which is precisely the canvas state the
  reshape exists to avoid.
- **n18** stays `advance:'action'` — *"Now tap Find a Trade — start with the canvas empty."*
  (10 words; action budget 16). The second clause is the whole point: an empty canvas is what
  routes the tap to the MODELED deck, which is where n19–n24 live.

### The deck side

`FinderHandoff` loses `includePlayers` and gains `fairAnchor?: {giveIds, receiveIds}`, present iff
the canvas has a give side. Its presence is the fork, taken inside the ONE #330 choke point,
**before** the model gate and with a `return`, so a canvas arrival can never also dispatch a
generate (`autoRunPendingRef.current = !fair` makes the two arms mutually exclusive at the source).

`onFindATrade` **writes no pins at all** any more. W5 wrote them because the model's generate
payload is what reads pins; the sweep takes the canvas in its own request body, so a pin write
would only strand a constraint on whatever searched next — which is the only reason W5 also had to
clear the store on the other branch. A canvas with RECEIVE players but no GIVE players is treated
as empty: the fair sweep prices a give package, and there is nothing to price.

The deck's cards come from `ideas.map(ideaToCard)`. `ideaToCard` moved out of
`components/FeaturedTradeWindow.tsx` into `utils/ideaToCard.ts` — pure, zero runtime imports, so a
guard can transpile and RUN it — and the window imports it back. Disposition, the ✕ overlay, swipe,
the ✓ queue, flag and edit-in-calculator all work on these cards unchanged. `deckOrigin:'calculator'`
still applies to BOTH forks.

End of a FAIR deck: **Back to calculator** (unchanged) + a new **Search all trades**
(`trades.deck-summary.search-all` / `trades.deck-exhausted.search-all`), which drops the anchor and
runs the model for the same partner. The W5 **unpin-retry does not render on a fair deck** — there
are no pins to unpin; the anchor rode the request body.

### Spotlight tracking (operator ask)

The calculator's page `ScrollView` now announces `notifyGuideTargetsMoved` (throttled at 16 ms).
The spotlight caches an ABSOLUTE window frame, so without it every tour beat below the fold was
ringed at its stale position the moment the page moved — and n12–n18 are all below the fold on an
SE. `check-guide-spotlight-tracking.js` gained **rule 10**, which sweeps `src/` for the whole class:
any file that calls `registerGuideTarget(` AND contains `<ScrollView` must reference
`notifyGuideTargetsMoved`. Three files qualify (TradesScreen, LeagueSummaryScreen,
TradeCalculatorScreen) and all three pass; `InLeagueCalculator` is an **enumerated exception with a
reason** — its only `ScrollView` is inside the team-picker `Modal` and holds no guide target.

### Files

| File | Change |
|---|---|
| `backend/trade_service.py` | `eval_consensus_package` (the extracted gate set) · `generate_fair_packages` + `_generate_fair_packages_impl` · `fair_packages_cap` in `_DEFAULT_CFG` |
| `backend/server.py` | `_fair_package_trade_id` + the route, inserted after `asset_trade_ideas` whose session/prefs/pick-injection preamble it mirrors |
| `backend/database.py` | `fair_packages_cap` in `_MODEL_CONFIG_DEFAULTS`. **No schema change** |
| `backend/analytics_taxonomy.py` / `analytics_queries.py` | `calc_include_players_toggled` REMOVED · `calc_find_a_trade_tapped.include_players` → `path` · `deck_search_all_tapped` added (INTENT by exclusion) |
| `backend/tests/test_bakeoff_arm_a_golden.py` + `docs/plans/three-model-bakeoff/scope-phase2.md` | `fair_packages_cap` pinned in `_PINNED_KNOBS` with its arm-A disposition (EXCLUDED — it caps a surface, not a generator) |
| `mobile/src/utils/ideaToCard.ts` | **new** — the one `AssetIdea` → `TradeCard` mapping, pure |
| `mobile/src/api/trades.ts` | `getFairPackages` + `FairPackagesResult`; `AssetIdea` gains validated `trade_id` / `basis` |
| `mobile/src/state/useFinderTargets.ts` | `FinderHandoff`: −`includePlayers`, +`fairAnchor` |
| `mobile/src/screens/TradeCalculatorScreen.tsx` | the fork + `path` analytics; no pin writes; `onScroll` on the page ScrollView |
| `mobile/src/screens/TradesScreen.tsx` | `runFairPackages`, `fairDeck`, the choke-point fork, the two Search-all exits |
| `mobile/src/components/InLeagueCalculator.tsx` | toggle removed (state, ref, style, guide target, event); 70/15/15; n16 no longer advanced from the give picker |
| `mobile/src/components/analystScript.ts` | n14 + n17 builders deleted; n16 → tap beat with new copy; n18 copy |
| `mobile/src/utils/calcTour.ts` | `CALC_TOUR_CALCULATOR` → 7 ids |
| `mobile/src/components/FeaturedTradeWindow.tsx` | imports the moved helpers; re-exports `assetIdeaKey` |

### Evidence

- **`backend/tests/test_fair_packages.py` — 19 tests.** The flag gate; anchor exactness (single
  and package); partner scope and its subset property; the preferred-receive ordering AND that it
  does not constrain; a receive pin the partner does not own costing nothing; `give_untouchable`;
  not-interested excluded from every return; the #189 relaxed refill and its labels; the cap
  keeping the head of the same order; determinism; the id's set semantics; the 400s; and
  **a swipe on a returned card reaching `trade_decisions` under its `fairpk_` id** — the test that
  makes these cards real deck cards rather than a read-only list.
- **Golden:** `test_asset_ideas.py` (34 tests with the bake-off golden) passes unchanged, which is
  what "the extraction changed nothing" means.
- **Guards:** `check-calc-merged-behavior.js` rewritten around the new contract (no toggle
  anywhere; `fairAnchor` iff a give side; no pin writes; the choke point forks and returns; the
  fair deck is built through `utils/ideaToCard`; unpin-retry hidden and Search-all shown on a fair
  deck) · `check-calc-tour.js` 13 beats + the retired builders must be deleted + n16 must have NO
  call site · `check-calc-merged-layout.js` asserts the toggle's ABSENCE ·
  `check-guide-spotlight-tracking.js` rule 10 · `check-guide-script.js`,
  `check-analytics-297-302.js`, `check-offer-prefill-330.js` updated for the new shapes.
- **Sabotages, all red, all reverted:** put the toggle back · route a `fairAnchor` handoff to the
  model auto-run · drop the calculator's `onScroll` · make an idea's give side differ from the
  anchor · mint a random card id instead of the deterministic one.
- **Runtime: still none** (D-056). Checklist steps rewritten below.

**Gates:** `pytest backend/tests` **4173 passed / 1 skipped** (was 4154/1; +19) · `npx tsc --noEmit`
clean · `bash mobile/scripts/testid-lint.sh` OK · **76/76** `check-*.js` guards.

### Still open after W6-B

**Q-028 and Q-029 are both closed.** What remains from the original list: the **overlay scope**
(built as calculator-origin; reversing it to "all decks" would need an explicit call) and the
**rollout shape** (global boolean vs the `trades_home_inline` tester-allowlist path). The
known-unfixed carry-forwards above are unchanged — the action row is still inside the page
ScrollView, the outlook row is a receipt rather than a disclosure, the mode row still renders one
lonely chip for a league-less user, and `lineupHeadText` is still 10 pt.

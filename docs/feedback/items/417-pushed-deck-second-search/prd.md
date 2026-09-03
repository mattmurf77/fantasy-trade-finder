# FB-417 — mini-PRD: the pushed anchored deck cannot start a second, unanchored search

**Date:** 2026-09-03 · **Entry point:** feedback #417 (operator, v1.16.14, screen `TradeDeck`)
**Path:** fast-track bug · **Branch:** `feat/fb417-pushed-deck-research`
**Scope block:** [scope.md](scope.md) · **Evidence timeline:** [investigation.md](investigation.md)
**Surface:** mobile only — `mobile/src/screens/TradesScreen.tsx`. No backend, no schema, no API, no flag.

## 1. Problem

The report: *"Starting a trade offer with a player selected worked for the first offer and
didn't include him for subsequent offers."* Clarified 2026-09-03: a decision was made on the
first card; the second card presented did not include the selected player.

The user's mental contract on a give-side anchored search is that **every** card in that deck
sends the player he put on the canvas. The deck stopped honoring it mid-session, while the
"Built around <name>" receipt at the top of the page still claimed it did.

## 2. Repro — from the prod event stream, not a guess

The full timeline is in [investigation.md](investigation.md). The load-bearing three rows
(operator's account, 2026-09-02 UTC):

| Time | Event | What it means |
|---|---|---|
| 22:03:06 | `calc_find_a_trade_tapped {path: fair, give_count: 1}` → `screen_viewed TradeDeck` → `find_trades_tapped {source: calculator}` | The D-171 push; the anchored sweep starts |
| **22:03:07** | **`find_trades_tapped {mode: deck}` — no `source`** | A SECOND search ~1 s later, before the first card was even viewed. Only the pushed page's own `trades.find-btn` emitted that shape |
| 22:03:12 | `trade_card_viewed {card_index: 0, …}` twice, two different `trade_id`s, **no swipe between them** | The deck re-sorted under the user: model cards took index 0 from the fair card |

The 21:28:54 and 22:04:42 sessions are the control — one `find_trades_tapped`, fair card stays,
no bug. The trigger is the second tap, not the sweep.

## 3. Root cause (pre-fix line numbers, `mobile/src/screens/TradesScreen.tsx` @ `c529abc8`)

1. **The pushed page renders an unanchored search button.** The always-mounted primary
   `trades.find-btn` ("Find a Trade") renders on the pushed deck in both arms of its ternary
   (:7185-7200 legacy `!consolidateOn`, :7390-7402 consolidated) — `canvasHost !== 'flag'` is
   the only gate and the pushed instance nulls `canvasHost`. On a fair deck `job` is null, so
   the button is enabled and reads "Find a Trade": an invitation to search, on a page reached
   by searching.
2. **Its legacy arm dispatched privately** — `track → setPinIdeaResumed(false) →
   dispatchGenerate({})` (:7195-7197): no deck reset, and (unlike `handleFindTrades` since
   #384 W6-B) no `setFairDeck(false)`. The job reads pins from the store, which the anchor
   path never writes, so the job is **unanchored**.
3. **The results merge.** The streaming effect appends the job's cards to the existing deck
   (:2137-2143). Nothing there distinguishes bases.
4. **And then outrank the fair cards.** With the fairness toggle OFF (the 2026-08-17 default)
   `sortedDeck` (:3773) sorts by `match_score` desc; fair cards carry `match_score: 0`
   (`mobile/src/utils/ideaToCard.ts`), so every model card sorts **above** them — index 0
   changes identity while the user is looking at it.
5. **The receipt outlives its deck.** `fairDeck` stays true on that path, so `inlineAnchorShown`
   (:5775) keeps saying "Built around <name>" over a deck that is now mostly the model's.
6. **Nothing blocked the tap.** `disabled` read `generateMutation.isPending || job?.status ===
   'running'`; the fair sweep is one synchronous request with **no job**, so both are false for
   the second it runs.

`handleFindTrades` (:1097) is only half-safe: it clears `fairDeck` but does **not** reset the
deck, so the same merge happens through it (the fair deck's own "Search all trades" exit and
the receipt's Clear both route there).

## 4. Requirements

**R-1 — the anchored pushed deck renders no page-level primary, for its whole lifecycle.**
While `isResultsPushed && (fairDeck || fairSweepPending)`, neither arm of `trades.find-btn`
renders. Both mounts still exist (this is a render gate, not a deletion): every other host and
state renders the button byte-identically — flag-off, the landing, team/player modes, and
**model** decks on the pushed page.

*Widened 2026-09-03 (QA round 1, B-5).* The first cut gated on `fairDeck` alone, which is only
true once the sweep's cards land: for the ~1 s before that the page still rendered the button —
greyed by R-3 — under a card telling the user to tap it, then unmounted it. Two consequences
follow, both required by #316's rule that *the copy follows whichever control actually renders*:

- the deck tree's in-progress card (`Looking for trades…`) now also fires on
  `isResultsPushed && fairSweepPending`, so that second is narrated instead of falling through
  to the never-searched `Hit "Find a Trade" to start` card (which is now not even a reachable
  instruction on this page). The never-searched card is untouched for every other host;
- the deck-done card's body gains a third branch keyed on the same derivation: with the receipt
  up it names the receipt's **Clear** ("…or tap Clear on the receipt to search all trades."),
  and without one — a push whose `anchorLabel` is null — this card's own **Search all trades**
  ("…or tap Search all trades to widen the search."). Both live under `calc.merged_layout`, a
  documented prerequisite of `calc.results_push`. The two pre-existing sentences (landing and
  legacy host) are byte-identical.

Verified replacements on that page, post-change line numbers:

| Control | testID | Renders on the anchored pushed deck? |
|---|---|---|
| Receipt "Change" (:7760) | `trades.anchor-receipt.change` | Yes — `inlineAnchorShown` is `(canvasHost === 'flag' \|\| isResultsPushed) && fairDeck && !!inlineAnchor` (:5807); pops to the landing canvas that still holds the build (D-171 ruling 2) |
| Receipt "Clear" (:7786) | `trades.anchor-receipt.clear` | Yes — same gate; `onPress` is `handleSearchAllTrades` (:3670) verbatim, i.e. this IS the "search all trades" exit |
| "Back to calculator" (:8564, :8672) | `trades.deck-{summary,exhausted}.back-to-calc` | Yes — gated on `calcMergedOn` only |
| "Search all trades" (:8644, :8738) | `trades.deck-{summary,exhausted}.search-all` | Gated `fairDeck && !inlineAnchorShown` — it **stands aside while the receipt is up** (D-158: the receipt's Clear is the same action, and two copies on one screen is the same action twice). With a receipt: Clear is the exit. Without one (a push whose `anchorLabel` is null): this renders **at the end of the deck** (qa-A F-6 — mid-deck that instance's only exit is the header back control; it has no receipt to Clear) |
| Unpin-retry (:8580, :8680) | `trades.deck-{summary,exhausted}.unpin-retry` | No, by design — `!fairDeck` (#384 W5: a fair deck has no pins, the anchor rode the request body) |

So the anchored deck always has at least two live search controls and one exit; it is never
stranded. **Deliberate consequence:** `find_trades_tapped {mode: deck}` can no longer be emitted
from a pushed anchored deck — that emission was the bug.

**R-2 — a model dispatch never merges into a fair deck.**
Every path that can dispatch the model while `fairDeck` is true resets the deck first.
Implemented at the single shared entry point: `handleFindTrades` calls
`resetDeckForNewTargets()` when `fairDeck` (:1130), **before** `dispatchGenerate` (the reset
bumps `deckEpochRef` synchronously at :2893, and the dispatch's `onMutate` stamps the new
epoch — resetting after would kill the search it just started). Reset semantics: new epoch,
`deck` emptied, `deckIdx` 0, `job` null, `fairDeck` false, browse session killed — so the
receipt is gone and no fair card survives. Paths covered:

| Path | Covered by |
|---|---|
| `handleSearchAllTrades` (:3670) — the end-of-deck exit AND the receipt's Clear | Calls `handleFindTrades('deck_search_all')` |
| The legacy `!consolidateOn` CTA arm (:7251) | Re-routed: `onPress={() => handleFindTrades()}` — it can no longer drift from the consolidated arm, which already did this. Same event, same `{mode: deckMode}` shape (`handleFindTrades`'s no-`source` branch) |
| The prefs-changed strip, deck-error retry, unpin-retry | Already `handleFindTrades` |
| #186 keep-side (:3492-3493) | Already `resetDeckForNewTargets(); dispatchGenerate({});` |

**The reset does NOT clear the pin store.** `resetDeckForNewTargets` (:2890) touches deck state
only; pins are the user's targets and the next dispatch reads them out of the store. (A fair
deck has none anyway.) Pinned by assertion 8f.

**Non-fair decks are untouched:** the reset is behind `if (fairDeck)`, so a "Find more trades"
tap on a **model** deck still appends to the existing deck exactly as shipped.

**R-3 — the jobless sweep is not re-dispatchable while in flight.**
New state `fairSweepPending` (:781), armed at `runFairPackages`'s entry **below the
`if (!leagueId) return;` early return** and beside the epoch capture (:3562), and disarmed at
both of its exits **after** the `#330` epoch guard (:3594 success, :3604 failure). A
**superseded** sweep must not touch the flag and returns before both disarms, so the invariant
that keeps a control from being stranded disabled is: **every epoch bump disarms.** There are
exactly two bump sites and both do —

| Bump site | Disarms at |
|---|---|
| `resetDeckForNewTargets` (:2903) | :2916 |
| the QuickSet-regen focus effect's inline bump (:4596) | :4603 — *added 2026-09-03 (QA round 1, B-2)* |

That second site bypasses the reset on purpose (it must not clear pins or lane state) and had
bypassed the disarm with it: a sweep superseded by a Quick Set save mid-search left both CTA
arms disabled for the life of the page. Pinned by assertion 8t; the state's declaration comment
(:768-780) states the invariant and names both sites. Read by: both CTA arms' `disabled` (:7242, :7456) and the landing canvas cell, which
withholds its handler (:7667) because `disabled={!onFindATrade}` is that cell's own gate
(`mobile/src/components/InLeagueCalculator.tsx:1297`). No spinner added.

**R-4 — analytics: no new event.** `find_trades_tapped` keeps every shape it had. The legacy
arm's inline emitter is gone; the row it sent is now `handleFindTrades`'s no-`source` branch —
identical name, identical `{mode: deckMode}` payload, one emitter fewer (4 → 3). Hiding the CTA
on the anchored pushed deck removes the source-less `{mode}` emission **from that surface by
construction** — that emission was the defect, and no other surface changes.

**R-5 — no flag, no schema, no API.** `calc.results_push` remains the kill switch for this
whole surface; with it off, `isResultsPushed` is false and every predicate here is inert.

**R-6 — a failed anchored sweep retries the ANCHORED search.** *(added 2026-09-03, QA round 1,
B-3.)* On the pushed page the deck-failure card's "Try again" (`trades.deck-error.retry`, :8773)
forks: `isResultsPushed && inlineAnchor` re-runs `runFairPackages({giveIds, receiveIds})` from
the still-standing anchor; every other host keeps `handleFindTrades('deck_error_retry')`
verbatim. The in-canvas host already did this (`handleBrowseRetry`, :6068-6075); the pushed page
never took that fork, so a network failure on an anchored search quietly answered a different
question — the model deck, unanchored — while the user believed he was retrying his own search.
The failure exit clears `fairDeck`, so the receipt is already down and the page does not *lie*
about it; it simply was not doing what was asked. No new event: `runFairPackages` emits the same
`find_trades_tapped {source: 'calculator', mode: deckMode}` row the first attempt did, which is
the honest shape (the retry IS the calculator's search, re-run). Pinned by assertion 8u.

**Code-walk (R-6).** Failure path: `runFairPackages`'s catch (:3595) passes the `#330` epoch
guard (:3596), sets `deckFailure` (:3599), `setFairDeck(false)` (:3603),
`setFairSweepPending(false)` (:3604). Next render: `findCtaHiddenForAnchoredDeck` is false (both disjuncts false) → the CTA
returns, enabled; `inlineAnchorShown` false → no receipt; the deck tree reaches its `deckFailure`
branch (:8751) because `deck.length` is 0. `inlineAnchor` is **not** cleared by either exit — it
is seeded once from the push param at :3179 and cleared only by `endBrowseSession` (:5955,
in-canvas host only) — so the
retry's guard is true and `runFairPackages` re-runs with the exact `giveIds`/`receiveIds` of the
first attempt. Its entry sets `deckFailure` to null (:3563) and re-arms `fairSweepPending`
(:3562), so the in-progress card (R-1) takes over from the failure card immediately, and on
success `fairDeck` goes true → the receipt and the hidden CTA are back to the anchored posture.
Flag-off and every non-pushed host evaluate `isResultsPushed` false and take the model arm,
byte-identical.

### 4.1 The page's escapes, after R-1 (operator review, 2026-09-03)

Hiding the CTA does not strand anyone, and the QA-B B-4 cost was written before this was
checked. A pushed results deck is registered with `subScreenOptions('Trade ideas',
'TradesHome')` (`mobile/src/navigation/TabNav.tsx:459-465`), which always renders a custom
`HeaderBack` (`:148-152`) — a JS control, because native back is dead over a
`headerShown: false` parent on iOS 26 (RNS#3294). So an anchored deck always offers:

| Escape | Where | Lands on |
|---|---|---|
| Header back (always rendered) | `TabNav.tsx:459-465` → `:148-152` | the builder landing, canvas intact (D-171 ruling 4) |
| Receipt **Change** / **Clear** | `TradesScreen.tsx:7760` / `:7786-7802` | re-pick the anchor / `handleSearchAllTrades` (the model deck) |
| End of deck: **Back to calculator**, **Search all trades** (no receipt) | `:8564`/`:8672`, `:8597`/`:8691` | landing / model deck |

## 5. Out of scope

- Changing `sortedDeck`'s `match_score` ordering or giving fair cards a non-zero score — the
  ordering is correct once a deck holds one basis, which is what R-2 guarantees.
- Preventing a **double push** (two taps on the landing cell under the push posture pushing two
  `TradeDeck` instances). Not what the event stream shows (one `screen_viewed TradeDeck`), and
  the landing cell's guard here is inert under the push posture by D-171 ruling 1.
- ~~A visible in-flight affordance for the fair sweep (spinner/progress). R-3 is a disable, not a
  new signal.~~ **Reversed 2026-09-03 (QA round 1, B-5).** Hiding the CTA for the sweep window
  left the pushed page showing the *never-searched* card to a user who had just searched, so the
  deck tree's existing in-progress card ("Looking for trades…", its own spinner) now covers that
  window on the pushed instance. No new component, copy string, or token — the branch that
  already narrates a running job gained a third disjunct. Every other host is unchanged, and the
  progress **strip** is still job-only.
- Anything on the landing's own in-canvas browsing (`calc.canvas_results`, flag-dormant).

## 6. Guardrails honored

- **D-171 (2026-08-31, five verbatim rulings).** Ruling 2 keeps the anchor receipt on top of the
  pushed deck — this change makes the receipt's Change/Clear the page's search controls rather
  than one of three. Ruling 1 (landing = builder only) is untouched: the landing dispatches
  nothing under `resultsPushLive`. Ruling 5: ships LIT under `calc.results_push`, no new flag.
- **D-153 fork (#384 W6-B).** The fair/model fork still happens once, in
  `forkCanvasSearch`, before the push; `runFairPackages` still returns before the model gate.
  R-2 does not re-price anything — it only stops the two bases sharing one deck.
- **#330 R-10 epoch rule.** The reset's epoch bump is what makes the in-flight fair answer
  (or a superseded model job) drop on arrival; both new `fairSweepPending` disarms sit *after*
  the epoch guard for exactly that reason — which is precisely why the disarm has to live at
  **every** bump site (R-3's table): a superseded sweep returns before its own disarms by
  design, so whoever superseded it owns the flag.
- **#316 (the deck-done card quotes a control).** Honored, not sidestepped: the card's body
  gained a branch rather than keeping a sentence that named a button #417 removed.
- **G-056.** No navigation verb was added or changed; `popTo` paths untouched.
- **Chalkline (ADR-004/005).** No token, style, component or testID changed; `testid-lint` green.
  **Copy:** the build changed none; the QA round-1 resolution adds exactly two sentences to the
  deck-done card for the anchored pushed deck (both existing sentences byte-identical, both new
  ones plain-voice and quoting a control that renders) — required by #316, not decorative. No
  new heavy action: the receipt's Clear stays an ice text link and the anchored page still has
  zero page-level primaries (qa-B B-4's disclosed cost stands).

## 7. Test plan

### 7.1 Structural guard (D-056 evidence)

`mobile/tests/check-results-push.js` § 8 — **23 assertions** (`8`, `8a`–`8v`; 28 printed lines),
each proven red by a named sabotage and restored green. 18 shipped with the build (S1–S17,
[build-notes.md](build-notes.md) §3); the QA round-1 resolution changed two (`8`, `8j`) and
added five (`8r` in-flight card, `8s` deck-done copy, `8t` every-epoch-bump-disarms, `8u`
anchored retry, `8v` exactly-one-reset), proven by S18–S24 in [build-notes.md](build-notes.md)
§5.2. Run: `cd mobile && npm run test:results-push` (75 assertions, all passed).

### 7.2 Code-walk proof (post-change line numbers)

**(1) Pushed fair deck → no CTA, from the push to the last card.** `handleInlineFindATrade`
(:3206) forks, then under `resultsPushLive` pushes `TradeDeck` with `resultsPush.fairAnchor`. On
the pushed instance `isResultsPushed` is true (:862) and `canvasHost` is nulled by param
presence, so `canvasHost !== 'flag'` is true — the pre-#417 gate would render the CTA. The
consumption effect arms `fairAnchorRef` and the choke point calls `runFairPackages`, which arms
`fairSweepPending` (:3562) **before** its `await` and whose success path sets `fairDeck = true`
(:3593). `findCtaHiddenForAnchoredDeck = isResultsPushed && (fairDeck || fairSweepPending)`
(:5844) is therefore true from the first commit that runs the sweep through to the end of the
deck — no gap — and both arms' gates (:7253, :7467) evaluate
`canvasHost !== 'flag' && !findCtaHiddenForAnchoredDeck` → **false**: neither Button mounts.
While the sweep runs, the deck tree's in-progress branch (:8533-8535, third disjunct) renders
"Looking for trades…"; when it lands, the receipt renders (`inlineAnchorShown`, :5824 → :7777)
and the deck-done card's body (:8591) names the receipt's Clear rather than the hidden CTA.

**(2) Pushed fair deck → "Search all trades" → clean model deck.** The receipt's Clear (:7786)
presses `handleSearchAllTrades` (:3670) — `canvasResultsLive` is false on the pushed instance,
so it is the un-forked arm. It emits `deck_search_all_tapped`, then
`handleFindTrades('deck_search_all')` (:1108): `fairDeck` is true → `resetDeckForNewTargets()`
(:1130) bumps the epoch (:2893), empties `deck` (:2897), nulls `job`, sets `fairDeck` false
(:2902) and disarms `fairSweepPending` (:2906). `inlineAnchorShown` is now false → receipt
gone, and `findCtaHiddenForAnchoredDeck` false → the CTA returns for the model deck.
`dispatchGenerate({})` (:1134) runs under the new epoch, and the streaming effect (:2161-2164)
appends into an **empty** deck: model cards only. Same trace via the end-of-deck
`trades.deck-exhausted.search-all` (:8691) when no receipt is up.

**(3) Landing double-tap during the sweep → second tap ignored.** On the in-place posture
(`calc.canvas_results`, the kill-switch restore) tap 1 runs `handleInlineFindATrade` → choke
point → `runFairPackages`, which sets `fairSweepPending = true` at :3552 before its `await`.
The next render passes `onFindATrade={undefined}` (:7667), and `InLeagueCalculator:1297`
renders the cell `disabled={!onFindATrade}` with `styles.actionBtnDisabled` (:1318) and
early-returns in `onPress` (:1299). Tap 2 is inert. On arrival, :3584 (or :3594) disarms and
the cell returns. Under the **push** posture the same window is covered on the pushed page by
the **gate**, not the `disabled` prop: since the QA round-1 widening `fairSweepPending` makes
`findCtaHiddenForAnchoredDeck` true for exactly that window, so the button the operator tapped
at 22:03:07 is not merely inert — it is not on the page. The `fairSweepPending` conjunct in both
arms' `disabled` (:7266 / :7480) is now redundant on every host that can actually run a sweep (a
sweep needs either the flag-hosted canvas, where `canvasHost !== 'flag'` already withholds the
CTA, or the push, where the widened gate does). It is kept as defence in depth against a future
sweep caller and stays pinned by 8o; the in-place posture's own guard is the withheld
`onFindATrade` handler (:7690).

**(4) Pushed MODEL deck → "Find more trades" appends as before.** An empty canvas pushes with
`fairAnchor: null` (:3213), so the choke point takes the model arm and `fairDeck` is never set.
`findCtaHiddenForAnchoredDeck` is false → the CTA renders, labelled "Find more trades" once
`deck.length > 0 && job?.status === 'complete'` (:7235 / :7449, unchanged). Its press reaches
`handleFindTrades`, where `if (fairDeck)` is **false** → no reset → `dispatchGenerate({})`
streams the new job's cards onto the existing deck via :2160-2164. Byte-identical to shipped.

### 7.3 Manual TestFlight checklist (operator)

Adopted verbatim from [qa-B.md](qa-B.md) (2026-09-03) and extended with step 15 for R-6; it
replaces the 10-step list this PRD shipped with. Build with `calc.results_push` on (its shipped
default). In-league, Trades tab.

**Setup that makes the 1-second window reproducible.** The sweep is one
`POST /api/trades/fair-packages` and normally lands in ~1 s — too fast to hit by hand. Widen it
deterministically:

- **Preferred:** iPhone *Settings → Developer → Network Link Conditioner* → enable, profile
  **"Very Bad Network"** (or "Edge"). Developer settings appear once *Settings → Privacy &
  Security → Developer Mode* is on. This stretches the sweep to 5–15 s, which is what every
  "during the sweep" step below relies on. Turn it **off** again after step 9.
- **Fallback if NLC is unavailable:** use a give-side **three-player** package (more enumeration
  server-side, sweep ≈ 2–4 s) and tap twice as fast as you can the instant the "Trade ideas"
  header appears.
- **For the failure steps:** Airplane Mode toggled on *after* tapping Find a Trade (the push
  happens client-side first; the sweep then fails).

**Pre-check (proves you are on the fixed build):** open any anchored deck and confirm there is no
full-width "Find a Trade" under the cards once they load. If there is, you are on ≤ v1.16.14.

| # | Step | Expect | Catches |
|---|---|---|---|
| 1 | NLC on. Trades landing, **one** player on the give side, receive empty, Team dropdown untouched. Tap **Find a Trade** in the canvas row. | "Trade ideas" page pushes. For several seconds: a **"Looking for trades…"** card with a spinner and **no button under it** (the QA round-1 fix for B-5 — pre-resolution this was a greyed "Find a Trade" under a card telling you to tap it). | R-1 (widened gate + in-flight card) |
| 2 | While that card is up, tap **three times** where the button used to be. | Nothing — no progress strip, no "Searching…", no second search. | **The #417 bug** (pre-fix: a live button ⇒ model job) |
| 3 | Wait for the cards. | "Built around <name>" receipt at top, **no** "Find a Trade" button anywhere on the page (scroll to the bottom to be sure). Card 1 sends your player. | R-1 both arms |
| 4 | Pass on card 1. | Card 2 **also** sends your player. Then swipe the whole deck: every card does. | **The reported regression**; R-2 |
| 5 | At the end of the deck (summary or "That's all for now"): read the body copy. | It must say **"…or tap Clear on the receipt to search all trades."** — and Clear must be on screen. It must **not** name "Find more trades" (no such button here). Buttons present: Back to calculator, See liked, Done. **No** "Search all trades" (the receipt's Clear replaces it). | R-1 copy branch (B-1); D-158 stand-aside |
| 6 | Tap **Clear** on the receipt. | Receipt disappears; deck is **replaced** (not appended — card counter restarts, no `fairpk` cards remain); progress strip "Searching…" appears; "Find a Trade" button is back. Cards that land do **not** all send your player. | R-2 reset |
| 7 | When it completes, tap **Find more trades**. | Cards are **added** (counter grows, current card does not change identity). | R-2 non-fair untouched (8v) |
| 8 | Back arrow. | Landing, canvas still holds the player from step 1 (D-171 ruling 4 — no prefill, nothing cleared). Tap **Find a Trade** → fresh anchored deck, receipt present, no CTA. | D-171 rulings 3/4; #330 epoch |
| 9 | Repeat 1–4 with the **Team** dropdown set to a specific league-mate. | Same as 1–4; every card is with that partner. Then **Clear**: the model deck is also with that partner only. | The scope rides the push and survives Clear |
| 10 | **Empty** canvas → Find a Trade. | Pushed **model** deck **with** the "Find a Trade"/"Find more trades" button present and working. | R-1 must not touch model decks |
| 11 | NLC still on. Step 1 again; the instant the page pushes, toggle **Airplane Mode on**. | After a few seconds: "Search failed" card with **Try again**, and the "Find a Trade" button is back (the deck is no longer anchored). No receipt. | No stranded disabled button |
| 12 | Airplane Mode **off**. Tap **Try again**. | The **anchored** search re-runs: "Looking for trades…", then cards that **all send the player from step 1**, and the "Built around <name>" receipt is back. (Pre-resolution this silently ran the unanchored model deck — qa-B B-3.) | **R-6** (8u) |
| 13 | NLC "Very Bad Network". Step 1; while the "Looking for trades…" card is up, switch to the **Rank** tab, save any Quick Set, return to Trades. | The pushed page regenerates a model deck, and when that job completes **"Find more trades" is tappable, not permanently grey**. (Pre-resolution this stranded both CTA arms for the life of the page — qa-B B-2.) | R-3 every-epoch-bump-disarms (8t) |
| 14 | Turn NLC **off**. | — | — |
| 15 | **Analytics confirmation** (from a Mac, `CRON_SECRET` from `secrets.local.env`): pull your account's events for the session. | For every `calc_find_a_trade_tapped {path: fair}` followed by `screen_viewed TradeDeck`: exactly **one** `find_trades_tapped` and it carries `source: calculator`; **zero** `find_trades_tapped {mode}` rows without `source` on `TradeDeck`; **no** pair of `trade_card_viewed {card_index: 0}` with different `trade_id`s and no `match_swiped` between them. Step 6 shows one `deck_search_all_tapped` then one `find_trades_tapped {source: deck_search_all}`. Step 12 shows a second `find_trades_tapped {source: calculator}`. | The prod signature from investigation.md, negated; R-4/R-6 emit no new event |

Log the outcome in `living-memory/TEST_LEDGER.md`; if step 2 or 4 fails the fix did not ship —
stop and page the building session.

## 8. File ownership

| File | Change |
|---|---|
| `mobile/src/screens/TradesScreen.tsx` | R-1/R-2/R-3/R-6 — the only source file touched |
| `mobile/tests/check-results-push.js` | § 8 (23 assertions) + one re-spec in § 4 |
| `mobile/tests/check-inline-home.js`, `check-canvas-results.js`, `check-analytics-297-302.js` | Declared re-specs only (see build-notes.md §2) |
| `mobile/tests/check-offer-prefill-330.js` | Declared re-spec (§2) + a stale-prose fix at :190 (QA round 1, qa-A F-3) — comment only |

Not touched, by instruction: `mobile/src/components/ShopOffersBody.tsx`,
`mobile/tests/check-shop-deck.js` (owned by #418).

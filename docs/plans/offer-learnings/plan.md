# Offer learnings — build plan and specs

**Date:** 2026-11-10 · **Entry point:** direct operator ask, after reviewing
[the Sleeper offer review](../realtime-trade-engine/sleeper-review.html) and commenting on each
recommendation · **Evidence:** [offer-history.md](../realtime-trade-engine/offer-history.md)
(612 real offers, one proposer; effects to build and measure, not parameters to copy)

This file is the product spec for each workstream. Each workstream's builder writes its own
feature scope block (`scope-<workstream>.md`, from
[the template](../../templates/feature-scope.md)) in this folder before coding, and files its
evidence in TEST_LEDGER.

## 1. The operator's decisions

| Rec | The operator's comment (2026-11-10) | Decision |
|---|---|---|
| R1 Rank "you pay picks" above "you ask for their picks" | "When otherwise close, sure. This is where outlook of teams should be doing a lot of the work." | Build, as a tie-breaker whose strength comes from the other team's outlook. WS1 |
| R4 Value the other manager's own picks above market | "Same comment as above. Outlook drives how we treat the picks." | Build, with the premium set by the other team's outlook. WS1 |
| R5 Demote "several for their best asset" | "Yes. 'Several' for best asset should only work when it's a player for draft picks for a rebuilder/tanker." | Build with exactly that exception. WS1 |
| R6 Keep first-page suggestions small | "Yes. Aligned." | Confirm and pin; organic offers are already at most three assets. WS1 |
| Ranking changes, how to ship | "Dark, grade first, but add new calibration trades for all users and their linked leagues (additive to current calibration decks)." | New engine revision behind its own selector (off), plus an additive Calibration round. WS1 |
| R11 Lead card copy with fit | "I'm aligned. But the fit evaluation and description needs to be solid." | First build done (WS4). The operator then asked for a line for both sides with league position ranks; three versions are being mocked up before the copy is finalised |
| R9 Capture the decline reason | "Build it, but it breaks my goal of a quick and seamless UI. I think we present this once every few passes. Or upon a certain number of consecutive passes." | Build as a cadence on the existing pass-reason prompt. WS3 |
| R3 Record outcomes of sent trades | "Yes. Ideally pulling from the users' sleeper account as well (with explicit user permission and a line in the Ts & Cs)." | Part A built (WS2). Part B: the operator approved the private Sleeper read on 2026-11-10; **WS2b** |
| R2 Show the next move | "Mock it up, build it, control it via its own dedicated capability flag (I'm skeptical with this one, I think it has the risk to just invite haggling and ruin the value prop)." | Mockup and backend now (WS5). **Operator chose treatment A on 2026-11-10, with a twist: WS8** |
| R8 Score how willing each manager is to trade | "Yes, but controlled via a capability flag. And it should more so be a league specific threshold that's evaluated. If all managers are active in trading, it shouldn't get applied at all." | Build after manager profiles (PR #635) lands, relative to the league. WS7 |
| R10 Nudge after silence | "Need more definition… the nudge should just be to send the trade on the platform… wondering if the initial offers should just push directly to Sleeper… or at least give users an easy 'summary' page to quickly decide which offers they liked get sent into Sleeper… all offers go to DMs by default with an invitation/copy to the app 'This trade was built in Fleeced'." | Definition document only. WS6 |
| R10 Re-surface on events | "Not for now." | Not built |
| R7 Aim the opening offer at the other manager winning | "But doesn't this contradict the counter observation? If we build a better first offer, we're just suggesting less potential good starting offers." | Not built. Answered in §4 |

## 2. Rules for every workstream

- Branch from a freshly fetched `origin/main`. Commit on the named branch; do not push, open
  a PR or merge. The coordinating session reviews, integrates and ships.
- Everything user-visible or model-changing ships behind its own default-off flag or
  selector, registered in `feature_flags.py`, `config/features.json`, the flag fixtures that
  mirror it, and `docs/config-reference.md`. Flag off must be behaviour-identical, with a
  test that proves it.
- Existing engine revisions 1–3 and their evidence are immutable. Never edit
  `trade_gen_bilateral.py`, `trade_gen_bilateral_candidate.py` or
  `trade_gen_outlook_evidence.py` to change behaviour.
- No Maestro, no simulator (D-056). Evidence is unit and worker tests with named sabotages,
  structural `mobile/tests/check-*.js` suites for app changes, a code-walk proof, and a
  manual TestFlight checklist the operator can run.
- New analytics events are registered in `analytics_taxonomy.py` and classified in
  `analytics_queries.NON_INTENT_EVENTS` in the same commit as the emitter.
- A change to `_run_trade_job` or another function in `server.DECK_PIPELINE_FUNCTIONS` trips
  `test_deck_pipeline_digest`. Do not bump `DECK_PIPELINE_VERSION` yourself: leave that test
  red, say so in the report, and the coordinator pins one bump for the integrated tree.
- Do not number a DECISIONS entry. Write it with the heading `D-216` and the coordinator
  assigns numbers at integration.
- Private data (`data/sleeper-export/`, `data/prod-requests/` in the main checkout) is
  local only. Reports and docs carry aggregates, never names, ids or message text.
- Run targeted tests while building and the full backend suite once at the end; several
  builders share this machine.

## 3. Workstream specs

### WS1 — Engine revision 4 and its Calibration round (R1, R4, R5, R6)

**Branch:** `feat/bilateral-revision-4`

**What.** A new bilateral revision, `owner-v2-bilateral-4`, built on revision 2 (the one live
in production) and selected only by its own default-off selector, in the way revision 3 is
selected. It differs from revision 2 in how it treats picks and consolidation asks, using
the other team's outlook:

1. **Owned-pick premium (R4).** When scoring the other manager's side, their own picks that
   they would give up are worth more to them than market. The premium depends on their
   outlook: largest for a rebuilder or a team that is tanking, smaller for "not sure", none
   for a contender or championship team. Starting values to test: about 20% at the top of
   the range. The viewer's own picks are not marked up. The premium changes the support
   score, never the market floor or the fairness gate.
2. **Pay-picks tie-breaker (R1).** Between offers whose quality is otherwise within the
   ranker's existing tolerance, prefer the one where the viewer sends picks and receives a
   player over the one that asks the other manager for picks. With the premium in place this
   mostly falls out of the score; add the explicit tie-breaker only inside the existing
   tolerance so it can never promote a clearly worse offer.
3. **Best-asset rule (R5).** An uneven offer in which the other manager gives up the trade's
   most valuable asset in exchange for several lesser ones is demoted. The one exception: the
   several are draft picks and the other manager is a rebuilder or tanking (a player for
   picks to a team that wants picks). Demote, do not delete: the offer stays in the
   inventory.
4. **Size (R6).** Organic bilateral offers are already at most three assets (1×1, 2×1, 1×2).
   Pin that with a test for revision 4; no behaviour change.

**Calibration.** The operator grades before anything is turned on: "add new calibration
trades for all users and their linked leagues (additive to current calibration decks)". Add
revision-4 trades to Calibration for every user and each of their linked leagues, without
removing or reordering what their current Calibration decks hold. Blind, as Calibration
already is. Read `docs/plans/blind-grading/` and the calibration plan folders first and use
the existing round machinery; if adding an arm is a model_config or admin operation, deliver
the code path plus the exact operator command, and do not run it against production.

**Acceptance.**
- Selector off: revisions 1–3 produce byte-identical cards and proofs (existing goldens
  stay green; add one for the selector).
- Each rule has a test on a constructed league where it changes the order, and one where it
  must not (contender counterparty: no premium; picks-for-player to a rebuilder: not
  demoted; quality gap beyond tolerance: tie-breaker has no effect).
- Proofs record the premium applied, the outlook it came from and whether the best-asset
  rule fired, so a graded card can be explained.
- A report, on the recorded production requests in `data/prod-requests/` (aggregate only):
  how many of the first 30 cards change against revision 2, and the share of first-page
  offers that ask for the other manager's picks before and after.
- The page-first search (`trade_first_page.py`) has no parity suite for revision 4, so the
  fast deck must fall back to the full solve for it. Confirm with a test; do not extend the
  page search.

### WS2 — Outcomes of sent trades, and consented import from Sleeper (R3)

**Branch:** `feat/trade-outcomes`

**What.** Part A: for every trade a user sends through the app, record what happened to it
at the provider: accepted, declined, countered (with the counter's terms), withdrawn or
expired, and when. The send path already stores the provider's transaction id; use the
existing league sync and cron ticks rather than a new poller where possible. Part B: with
the user's explicit, revocable permission, import the trade offers and outcomes from their
own Sleeper account for their linked leagues (offers they sent or received outside the app),
as outcome evidence. Off until the user opts in; a line in the Terms says so in plain words.

**Constraints.**
- Part B reads only trade offers and their outcomes. Not direct messages, not chat.
- Consent is per user, recorded with a timestamp and the terms version, and revocable;
  revoking stops import and deletes what was imported. Account deletion deletes it too
  (extend the deletion coverage tests).
- Counterparties did not consent: store their side as league-scoped manager ids the app
  already holds, with no message text, and never show one user another's imported offers.
- Sleeper access uses what the app already has for the user. If Part B needs an endpoint or
  credential the app does not hold today, stop and report instead of adding one.
- The Terms line is a draft for the operator to approve: put it in the PR description and the
  terms file behind the same flag, not live.
- Flags: one for Part A (`trade.outcome_tracking`), one for Part B
  (`trade.sleeper_offer_import`), both off.

**Acceptance.** Schema and data dictionary updated; outcome transitions tested from fixtures
for each status; idempotent re-sync; analytics events registered if any are added; the
acceptance evaluation (`backend/eval/acceptance_eval.py`) can read the new outcomes, or a
note says exactly what it needs.

### WS3 — Ask why, once every few passes (R9)

**Branch:** `feat/pass-reason-cadence`

**What.** The app already has a pass-reason prompt and a `trade_pass_reasons` table. The
operator wants reasons captured without slowing the deck: "present this once every few
passes. Or upon a certain number of consecutive passes." Read how the prompt is triggered
today, then add a cadence: ask after N consecutive passes (starting value 3), and not again
for the next M passes (starting value 5) once asked or dismissed. A pass never waits on the
prompt. Dismissing is one tap and counts as no reason.

The reason chips should cover what managers actually said in the offer data: not moving that
player; keeping my picks; wrong direction for my team; don't rate what I'd get; waiting on
something; value too low. Map these onto the existing reason codes where they exist and add
only what is missing, keeping the existing Elo effects of each existing code unchanged.

**Constraints.** Behind `trade.pass_reason_cadence` (off): off means today's behaviour
exactly. N and M are server-provided config so they can change without an app release.

**Acceptance.** Structural checks for the cadence logic (ask at N, quiet for M, reset on a
like); backend tests for any new codes; a TestFlight checklist.

### WS4 — Lead the card with fit (R11)

**Branch:** `feat/fit-first-copy`

**What.** Card copy opens with why the trade suits the other team and the viewer's team, and
puts the value line second. The operator's condition: "the fit evaluation and description
needs to be solid." So a fit line appears only when the engine's own proof supports it
(a filled positional need, a plan match such as picks to a rebuilder or a starter to a
contender, a surplus position being moved), names the specific reason, and falls back to
today's copy when the proof has nothing specific. Never a generic "good fit". Copy stays
deterministic templates in `trade_narrative.py` (no LLM), using fields the proof already
freezes.

**Constraints.** Behind `trade.fit_first_copy` (off): off is byte-identical copy. No claim
the data does not support, and no claim about the other manager's private preferences beyond
what the app already shows.

**Acceptance.** A table in the scope block of every template with the proof fields that
trigger it; tests for each trigger and for the fallback; ten real-shaped examples in the
report (from synthetic or recorded inputs, with names replaced).

### WS5 — The next move (R2): mockup and backend

**Branch:** `feat/next-move`

**What.** The operator is skeptical ("it has the risk to just invite haggling and ruin the
value prop") and asked for it mocked up, built and controlled by its own flag. This round
delivers:

1. A mockup in `mockups/next-move/` (read `mockups/CLAUDE.md` first; Chalkline tokens; embed
   the real card capture as the "before"). Show two or three treatments, including the most
   restrained one: nothing on the card until an offer has been declined or has gone quiet,
   then a single "send a revised offer" with one pre-built revision. State for each
   treatment how it limits haggling.
2. Backend: for a sent offer, one pre-built revision that keeps the offer's core assets and
   improves the other side by a bounded amount (starting value 10–20% of the trade's market
   value), produced and proven by the same evaluator as any other card, so it is a valid
   trade or it is not offered. Behind `trade.next_move` (off).

The app UI is not built in this round: the operator picks a treatment from the mockup first.

**Acceptance.** Revision generation tested (valid, bounded, keeps the core assets, absent
when no valid revision exists); flag off adds no payload key.

### WS6 — Definition: sending and following up on the platform (R10)

**Branch:** `docs/send-on-platform`

**What.** A definition document, no code, in this folder (`send-on-platform.md`). The
operator's direction: the nudge should be to send the trade on the platform; consider
pushing offers straight to Sleeper; or give users a summary page to choose which liked
offers go to Sleeper; offers go to DMs by default with "This trade was built in Fleeced".
Lay out the options against what the app does today (Send in Sleeper, likes, matches), what
each needs from Sleeper and what that means for the platform's terms, the messaging-volume
and spam risk of a default DM, and a recommended first version small enough to test, with
the open questions for the operator at the top.

### WS7 — Trade willingness, relative to the league (R8)

**Starts after PR #635 (manager profiles) is on `main`.** Behind its own flag. Uses each
manager's completed trades from public league history, compared within their league: a
manager is down-weighted as a partner only when they trade clearly less than their
league-mates, and nothing is applied in a league where everyone trades. Spec to be written
against #635's schema when it lands.

### WS2b — Read the user's own Sleeper offers (R3 Part B, approved)

**Starts from the integrated tree that contains WS2.** Branch `feat/sleeper-offer-read`.
Flag `trade.sleeper_offer_import` (off).

The operator approved the private read on 2026-11-10 ("I'm aligned on the private read"),
after WS2 found that declines are invisible on Sleeper's public API. What the call returns
is in [sleeper-offers-read.md](sleeper-offers-read.md); build against that and nothing
broader.

**What.**
1. A read of `league_transactions_filtered` (trades only) for a linked user's leagues, using
   the Sleeper credential the app already holds for that user, through the same client and
   error handling as Send in Sleeper. No new credential, no other private call.
2. Outcomes for offers sent through the app move beyond WS2's two: `declined` (`rejected`,
   declined by the other manager), `withdrawn` (`cancelled` by the sender), `lapsed`
   (`cancelled` with no rejecter), `countered` (a later `is_counter` offer from the other
   manager between the same two rosters), still `sent` while `proposed`.
3. With the user's explicit, revocable consent, import the user's own offers made in Sleeper
   directly (sent and received), with their outcomes, into the same store, marked by source.
4. Consent as WS2's scope block designed it: append-only grants and withdrawals with the
   terms version; revoke deletes what was imported; account deletion covers it; one switch
   in Settings, off by default. The Terms line stays a draft for the operator.

**Constraints.** Trades only, never messages. The read returns only the signed-in user's own
non-complete offers; store the other side as a league roster id and never show one user
another's offers. Poll gently: at most once per league per user when Find a Trade is opened
or on the daily tick, never in a loop. Every Sleeper response in tests comes from fixtures
shaped like the capture; no live calls from tests or tools.

**Acceptance.** Each status transition from fixtures; counter linking by roster pair and
time; consent grant, revoke and deletion; flag off makes no call; a failed or unauthorised
read changes nothing and is logged once.

### WS8 — Revised-offer cards for declined offers (R2, treatment A plus the operator's twist)

**Starts after WS2, WS2b and WS5 are integrated.** Branch `feat/revised-offer-cards`. Behind
`trade.next_move` (off).

The operator, after seeing the WS5 mockup: "I like version A, with an added twist: We should
absolutely factor in platform (Sleeper, ESPN) specific data / trade proposals. If we see they
suggested a trade that was declined (where user is the sender), we should be generating a
counter card with slightly more value and give content that explains that we saw this and
have another idea. These cards should hold high in priority ranking for display too. It's
acceptable if these cards need to be generated via a batch or a different mechanism (but
that's not my ideal path, just a fallback depending on complexity)."

**What.**
1. **Trigger.** A trade the user sent that Sleeper shows as declined by the other manager
   (WS2b's `declined`): sent through the app or, where the user has opted in, sent in Sleeper
   directly. Nothing is shown for an offer that is pending, withdrawn by the user or lapsed.
   ESPN and MFL follow when their own offer reads exist; ship Sleeper first.
1b. **Middle ground.** The operator, 2026-11-10: "If we see a counter from a recipient on an
   original offer the user sent and that counter was declined, we should try finding a
   middle ground." When the other manager countered and the user declined that counter, the
   card is a revision that sits between the user's original offer and the counter: it keeps
   the assets both versions share and moves the other manager's side part of the way toward
   what the counter asked for (starting value: about half the gap in market value).
2. **The card.** One revised offer per declined offer, from WS5's generator. The operator,
   2026-11-10: "we only work to revise the pieces offered to improve the value of players
   offered slightly." So a revision keeps the trade the same size and the pieces asked for,
   and swaps one of the pieces the user offered for a slightly more valuable one from the
   user's roster. It does not add a piece and does not drop a piece that was asked for; WS5's
   generator gains this swap and the declined-offer path uses only it. Starting value for
   "slightly": 5–15% of the trade's market value. It is proven by the same evaluator as any
   other card, or it is not shown.
3. **The copy.** The card says plainly that the earlier offer was declined and what changed,
   for example "Your offer for <player> was declined. Another idea: add <asset>." It states
   only what the platform showed; it does not guess why the offer was declined.
4. **Priority.** These cards lead the deck, ahead of ordinary suggestions, in the way
   likes-you cards are placed today. Starting cap: three per deck, most recent decline first,
   so they never crowd out the deck.
5. **Mechanism.** Preferred: built with the deck when the user opens Find a Trade, so a card
   appears as soon as a decline is known. Fallback, only if the inline path proves too
   costly or fragile: a batch that prepares them after each outcome sync.

**Constraints.**
- A revised-offer card is shown once per declined offer. Passing it retires it; it is not
  regenerated with a still-higher price (this is what keeps treatment A from inviting
  haggling).
- Only the sender sees it. The other manager's decline is never shown to anyone else.
- An offer answered with a counter is not met with our own revision while that counter is
  pending or accepted: the counter is the next move. Only a counter the user has declined
  opens the middle-ground card (1b).
- Evidence and impressions follow the deck's existing contracts; the card is attributable as
  a revised offer in its frozen features.

**Acceptance.** Tests for each trigger source and for no card on pending, accepted, expired
or countered offers; once-only after a pass; cap and ordering; flag off adds nothing to the
deck or the payload; a TestFlight checklist.

## 4. R7, answered

The comment: a better first offer contradicts the counter finding, and narrows the good
starting offers.

The two findings point the same way. Counters asked for about 20 points more because the
typical first offer asked the other manager to lose about 10% at market. An opening offer
that already sits where counters end up needs fewer rounds; it does not replace negotiation.

The narrowing concern is right if R7 were a filter. It should not be one, and it is not
built. If it is ever tried it should be an ordering preference among offers that already
pass, graded in Calibration like revision 4, never a rule that removes offers where the
viewer wins. Revision 4's pick premium already moves in this direction for the case the data
supports best, which is picks.

## 5. Integration order

1. The engine branch (`feat/trade-engine-rearch`: fast deck, page-first search).
2. WS4, WS3, WS2, WS1, WS5 as each passes review, rebased in that order; one deck-pipeline
   bump for the integrated tree; decision numbers assigned then.
3. Full backend suite, mobile type-check and check suites, CI, then `main`.
4. WS2b, then WS8, after WS2 and WS5 are integrated; WS7 after PR #635.

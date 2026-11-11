# Feature Scope — WS8: revised-offer cards for declined offers (R2, treatment A + the twist)

**Date:** 2026-11-10
**Entry point:** direct operator ask — `plan.md` §3 WS8 (treatment A of `mockups/next-move/`, plus
"If we see they suggested a trade that was declined (where user is the sender), we should be
generating a counter card with slightly more value…" and the 1b middle ground).
**Builder:** WS2b/WS8 builder, branch `feat/sleeper-offer-read` (commit 2, on top of WS2b)
**Operator sign-off on waivers:** needed — §1 (no new analytics event) and the decisions in §0.7.

---

## 0. What is built

### 0.1 Trigger (from WS2b's rows; `backend/trade_revised_offers.sources`)

A `trade_offer_outcomes` row of the user, in this league, `direction = 'sent'` (through the app
or, with the import consent, in Sleeper directly), whose decline is within the last 30 days:

| Row | Card |
|---|---|
| `status = 'declined'` | a **revision** |
| `status = 'countered'` and `counter_status = 'declined'` | a **middle ground** |
| `sent`, `accepted`, `withdrawn`, `lapsed`, `completed_different_terms`; `countered` with the counter `pending` / `accepted` / `withdrawn` / `lapsed` / `countered` (back) | nothing |
| `direction = 'received'`, another user's row, FAAB or an unread pick in the offer or the counter | nothing |

Only the sender's rows are read (by account id), so no one else ever sees the card or the decline.
ESPN and MFL make no rows yet; Sleeper only.

### 0.2 The swap rule (declined offer)

`trade_next_move.propose_revision(offer, context, step_min=.05, step_max=.15, kinds=("swap_in_give",))`:
the user's offer `(G, R)` becomes `(G − {g} + {h}, R)` for one `g ∈ G` and one `h` from the user's
roster with `h ∉ G`, `h` not an untouchable, `h` known to the board, and consensus value
`value(h) > value(g)`. Same size, every asked-for asset kept, nothing added, nothing dropped. The
candidate must be eligible under `bakeoff_runner.owner_evaluator(config)` with organic gates (the
engine revision in force, the viewer's own checks included), and the other manager's net market
gain at that evaluator's package pricing must rise by 5–15% of the trade's market value (the larger
side of the original). Smallest step wins; ties by `h`, then `g`. WS5's two kinds and their tests are
unchanged (`kinds` defaults to them).

### 0.3 The middle-ground rule (declined counter)

`trade_next_move.propose_middle_ground(original, counter, context)`, original and counter both from
the user's side. Every asset both versions share stays; on each side any subset of the assets only
one version holds may be added, plus on the user's side at most one further asset from the user's
roster (never an untouchable the original did not already offer); no larger than the larger version;
neither version itself. With `n` = the other manager's net market gain at evaluator pricing
(`market.give − market.receive`), the counter must have asked for more (`n(counter) > n(original)`),
and the card's `n` must sit 35–65% of the way from the original's to the counter's; closest to 50%
wins (then fewer assets, then ids). At most 6 assets may differ between the versions. Proven by the
same evaluator with organic gates, or no card.

### 0.4 Inline, and why it is safe

Built with the deck when Find a Trade runs a job (`server._run_trade_job` →
`_inject_revised_offer_cards`), for organic decks served by the owner arm (`owner_serve`), never for
a prepared inventory, a replenish or Calibration build, a pinned / opponent / intent deck, or the demo
league. The cards are inserted at the front immediately before the owner revalidation, so they follow
every contract an owner card follows:

- **Proof:** each card is bound to its `OwnerDecisionContext`; `_owner_cards_valid` re-proves it
  against the same frozen context, then roster legality, significance and `_project_trade_dispositions`
  apply as to any card. A card that fails any gate is not served.
- **Order:** `card.injected = True` keeps the slot through the bilateral presentment and the quality
  filter (both already honour `injected`); `revised_offer` joins `_SERVED_PROTECTED_KEYS` so the
  serve-time repeat cap holds it too. Owner-served decks bypass every reordering layer, so the cards
  stay first.
- **Evidence:** the card carries the request's `owner_request_evidence`; its impression row gets the
  owner columns (`valuation_json`, `model_arm`, `trade_concept_id`) like any owner card, and the frozen
  features add `revised_offer: {kind, outcome_id, card_id, source, step_fraction, version}` (no copy).
  Bake-off attribution reads it as injected (`model_arm` from the proof).
- **Stored first pages:** the card is in the job's cards like any other; a stored page re-served
  later passes `_project_trade_dispositions`, so a passed card disappears there too.

The batch fallback the operator allowed was not needed.

Known limit: a deck reused from the 30-minute job cache, or an adopted prepared inventory (dark today),
does not rebuild, so a decline the WS2b read learned at this open shows on the next deck build.

### 0.5 Once only, retirement, cap

`revised_offer_cards`, one row per (user, source offer), written the first time a deck looks at the
offer: `active` with the card's terms, or `none` when no proven card exists. Never rebuilt, so the
price never climbs. An active card is re-proven on every build and served until:

- the user passes or likes it (it is then a past decision: the evaluator answers
  `previous_disposition`) → `retired / acted`;
- it stops passing (an asset moved) or its partner no longer holds the ask → `retired / unavailable`.

Never a revision of a revision: a source whose terms equal any built card's terms is skipped. At most
three cards per deck, most recent decline first (`status_at`, or the counter's `counter_status_at`);
at most six new builds per deck; two sources that yield the same package show it once.

### 0.6 Copy (`trade_narrative.revised_offer_line`, deterministic)

- Revision: **"Your offer for {asked} was declined. Another idea: {new} in place of {old}."**
- Middle ground: **"You turned down their counter to your offer for {asked}. A middle ground:
  {changes}."**, changes relative to the user's original from "add X", "keep X", "also ask for X",
  "no longer ask for X", joined with commas and "and".

`{asked}` is the original offer's asked-for assets ("A", "A and B", "A, B and C"); names are player
names or the deck's pick labels. It states what Sleeper showed and what changed, never a reason. On
the card it sits under the header, above the WS4 fit lines (which describe the new trade), so the two
read in order: what happened, then why this trade fits. Payload: `revised_offer: {kind, line}`.

### 0.7 Decisions for the operator

1. A card stays in the deck until the user acts on it or 30 days pass since the decline (shown on
   every deck until then, not literally once). "Once" is enforced as one card per declined offer,
   never rebuilt.
2. The middle ground may add one asset from the user's roster that neither version held, because a
   counter that asks for one more piece has no half-way point inside the two versions.
3. The 5–15% swap band, the 35–65% middle band, the 30-day window, the cap of 3 and 6 builds per
   deck are module constants, not `model_config` knobs.
4. Significance can still remove a revised card (it is not exempted like an inbound card).

## 1. Analytics scope

- [x] **(b) Existing events cover it:** a served card is a `deck_impressions` row whose frozen
  features name it (`revised_offer`), and passes, likes and sends ride the existing deck outcomes and
  `sleeper_send_*` events with its `impression_id`. No new event; `analytics_taxonomy.py` unchanged.

## 2. Schema & flag scope

- New table `revised_offer_cards` (create_all), in `accounts._ADDITIONAL_PRIVATE_TABLES`; a card built
  from an imported offer is deleted with the import on withdrawal. `docs/data-dictionary.md` updated.
- Flag: `trade.next_move` (existing, default off). Off ⇒ `build` returns `[]` before any read, no row,
  no payload key, no feature key (tests).
- No env var or `model_config` key.

## 3. Evidence scope

- [x] **Unit / worker tests:** `backend/tests/test_revised_offer_cards.py` — the swap (per engine
  revision; smallest step; band; untouchables; viewer checks; nothing when no piece qualifies; the
  declined path never adds or drops; WS5's default kinds unchanged), the middle ground (shared kept,
  about half, neither version, positive gap only, untouchables, flag off, pool limit), the builder
  (each trigger; every no-card status; received / another user / old / FAAB / another league; once
  only; acted and unavailable retirement; `none` never retried; no revision of a revision; cap and
  newest-first order; one card per package; flag off reads nothing; revoke deletes import cards), the
  copy, and the real worker with the owner arm serving (card first, public `revised_offer`, frozen
  features without copy, impression with owner valuation; flag off adds nothing). WS5's
  `test_no_production_module_reaches_the_generator` now names the one production importer
  (`trade_revised_offers`); none of WS5's other tests changed.
- [x] **Structural guard:** `mobile/tests/check-revised-offer-card.js`, `npm run test:revised-offer-card`.
- [x] **Code-walk proof:** §0.4 (`_run_trade_job` → `_inject_revised_offer_cards` →
  `trade_revised_offers.build` → `_owner_cards_valid` → roster / significance → dispositions →
  `trade_bilateral_presentment.present` (protected by `injected`) → `deck_quality.filter_deck`
  (protected) → `_log_deck_signal_impressions` (owner columns + `features.revised_offer`)).
- **Measured** (`measure_revised_offers.py`, eight synthetic 12-team leagues from the 340-player
  fixture, the first ten deck cards of each treated as sent offers): a declined offer gets a revision
  for 5/80 (owner-v1), 17/80 (bilateral-1), **29/80 (bilateral-2, live)**, 34/80 (bilateral-3), steps
  5–15% (median about 8% under the bilateral revisions). A declined counter that asks for one more
  piece worth at least 15% of the trade gets a middle ground for 53/80 (owner-v1, all 1-for-1 offers),
  0/80 (bilateral-1), **5/80 (bilateral-2)**, 6/80 (bilateral-3), median gap share 43–51%. Under the
  bilateral revisions most sent offers are already 2-for-1 or 1-for-2, so that counter is a
  four-asset trade the evaluator does not price (organic shape), and no middle ground is offered:
  the main limit of the rule as built. Median build time 6–39 ms a revision, 8–20 ms a middle ground.
- testIDs added: `trade-card.revised-offer`, `trade-card.revised-offer.line`.

### Manual TestFlight checklist (the operator's three Sleeper leagues)

Server: `FTF_FLAGS` with `trade.next_move`, `trade.sleeper_offer_import` and `trade.outcome_tracking`
on; the owner arm serving (as today). App build with this commit, the flag cached on.

1. In league 1, send a 1-for-1 through the app to a league-mate who will decline it. After they
   decline in Sleeper, open Find a Trade, wait for the read (about 10 s), pull to refresh or reopen
   after the deck cache expires: the first card reads "Your offer for {their player} was declined.
   Another idea: {your player} in place of {your original player}.", with a flare rule on the left,
   above any fit lines. The ask is unchanged and the trade is the same size.
2. Open the card's value bar: you send slightly more than before (the bar moved a little toward
   them), not a lot.
3. Pass the card. Reopen Find a Trade later: it does not come back, and no higher revision of the
   same offer appears.
4. Like (or send) a revised card; if that one is declined too, no revision of it appears.
5. Send an offer, have the league-mate counter asking for one more piece, decline the counter in
   Sleeper: the first card reads "You turned down their counter to your offer for {player}. A middle
   ground: add {piece}." and the added piece is cheaper than the one they asked for.
6. While a counter is pending, or after you withdraw an offer, or after one lapses, or after one is
   accepted: no revised card for it.
7. Decline-producing offers in two other leagues: each league shows only its own cards; at most three
   lead any deck, newest decline first.
8. Edit a revised card's players in the calculator: the line disappears from the edited card.
9. Flip `trade.next_move` off (reload flags): the cards and the line are gone on the next deck.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | the card payload's `revised_offer` key under `/api/trades/generate` |
| `docs/data-dictionary.md` | updated | `revised_offer_cards` |
| `docs/config-reference.md` | updated | `trade.next_move` row now describes the deck wiring |
| `docs/architecture.md` | updated | `trade_revised_offers.py` |
| `docs/glossary.md` | updated | Revised-offer card; Middle ground |
| `living-memory/LLD.md` / `HLD.md` | n/a | a leaf behind an existing flag at an existing injection point |
| `docs/cross-client-invariants.md` | n/a | only the mobile client reads `revised_offer` |

## 5. Ship gate declaration

- `test_deck_pipeline_digest` red on purpose (coordinator pins); everything else green.
- Express lane declared by the operator? No.

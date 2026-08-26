# Code-walk proof — Team Review defect batch

**Date:** 2026-08-20 · **Branch:** `claude/team-outlook-experience-27a7a1`
Under [D-056](../../../../living-memory/DECISIONS.md) this trace replaces the simulator capture.
Every claim is file:line on the post-fix tree.

---

## 1. #367 — the sell list selected the wrong players

**The report:** *"Think the easiest sells and buys page is backwards. I should sell guys I'm
lowest on on my roster and buy guys I'm highest on above the market not on my team."*

**What shipped.** `compute_consensus_gap` kept a roster player only when the USER rated him
above the community — `gap = u - c`, `if gap <= 0: continue`, under a comment that said
*"Only surface players where YOU value them ABOVE the market."* That is the set the league will
**not** pay up for. The Team Review card then printed over that list:
*"These are your easiest sells — someone pays you more than you think they're worth."*
The copy asserted the exact opposite of the filter that produced the rows.

**Two independent errors, both fixed.**

1. **Selection, upstream** — `backend/trends_service.py:399`: `gap = c - u`, keeping only
   `gap > 0`. The sell edge is the market sitting *above* your board. `gap` stays a **positive
   magnitude**, matching `easiest_buys` (`u - o`, `trends_service.py:437`), so every renderer
   that prints `+gap` (`TrendsScreen.tsx:443`, `web/js/app.js:6239`) is still correct with no
   client change. `rank_gap` flipped with it (`_rank_delta(u_rank, c_rank)`) so the rank view
   points the same way as the elo view.
   *`easiest_buys` was already right and is untouched* — it compares against the **owner's** elo,
   so `u - o > 0` means the owner will sell cheap. That is precisely the operator's "buy guys
   I'm highest on… not on my team."

2. **Which field each list lands in** — `backend/team_review.py:251` / `:256`. The community
   ladder assigned `easiest_sells` → `higher_than_market` and `easiest_buys` →
   `lower_than_market`. Both field names are literal, and both were wrong: `easiest_buys` **is**
   the set you are higher than the market on. The consequence on screen was that the user's best
   buys rendered under **"Skip these — you'd be buying at a price you don't believe"**
   (old `TeamReviewScreen.tsx:529`). Now `higher_than_market ← buys`, `lower_than_market ← sells`.

**The seed fallback had the same crossing** (`team_review.py:271-278`): it took `gap > 0 and pid
in user_roster` as a sell. Now `gap > 0 and pid not in user_roster` → buy, `gap < 0 and pid in
user_roster` → sell, with the sell gap negated so **both ladders ship the same positive-magnitude
convention**. Before this change the two source ladders disagreed about what the same field meant.

**Client** — `TeamReviewScreen.tsx:559` / `:578`: sells card first (matching the report's own
phrasing), each list labelled for the action it supports, and the stale "Skip these" line deleted.
`TrendsScreen.tsx:211` label corrected — that screen showed the same inverted set and its label
described the old filter accurately, so it had to move with the backend.

## 2. #368 — "pointed the other way" and the blank firsts

**The report:** *"The 'pointed the other way' page doesn't make sense and the 1st values are blank
for all teams listed."*

**One root cause, both symptoms.** `league_team_review_route` builds the per-owner pick capital it
needs — `pick_share[uid]` normalised to a league share, and `first_rounds[uid]` counted off the
pick labels (`backend/server.py:23269-23278`) — and then called `build_team_review` **without
passing either**. `_partners` declares both as `dict | None = None` and coalesces to `{}`
(`team_review.py:369-370`), so:

- `first_round_picks = int({}.get(uid, 0))` → **0 for every member**, rendered as the empty-looking
  `· 0 firsts` at `TeamReviewScreen.tsx:571` — the "blank" in the report;
- for a **contending** caller the sort key is `pick_capital_share`, also 0.0 for everyone
  (`team_review.py:317`), so `sorted()` was stable over an unordered dict — the list was in
  arbitrary order, which is the "doesn't make sense".

**Fix:** `backend/server.py:23405-23406` passes the two dicts it already computed. No logic
changed; an argument stopped being dropped.

**Why a unit test could not have caught it** and what does: the pure module was always correct,
so the defect lived entirely in the wiring. `test_team_review_route_passes_the_pick_capital_it_computes`
AST-parses `server.py`, finds the `build_team_review` call, and asserts both kwargs are present.

## 3. #364 — the disclaimer did not say IDP

**The report:** *"The playoff outlook disclaimer should be more specific: we can't rank IDPs, this
ranking is offensive positions only."*

The caption existed but was generic: *"Based on your offensive starters — we can price 7 of your 15
starting slots."* It never named the reason. `meta.priced_slot_coverage` has carried
`unpriced_slots` — the slot names, one per lineup seat — since 2026-08-10
(`backend/outlook/serialize.py:73`), and no client had ever read that field.

`TeamReviewScreen.tsx:346` now names the cause and the slots: *"Offensive positions only. We rank
QB, RB, WR and TE — we do not rank IDP or kickers, so 8 of your 15 starting slots (DL, LB, DB)
carry no value here."* `slotList()` collapses the repeats to distinct names in roster order.
Gate unchanged (`cov.affects_strength && cov.fraction < 1`), so a fully-priced league still shows
nothing — the honesty flag at `serialize.py:73` means a `trailing_scores` payload does not claim
the board biased odds it never read.

## 4. The two operator instructions

**"Build those values into the page itself so the user sees all of the inputs we use to determine
team outlook."**

`infer_team_outlook` reads seven knobs and previously returned only three shares plus a score, so
the screen restated thresholds in prose — **and got one wrong**: it rendered *"Value age 23 and
under"* while `youth_age` has been **26** (`trade_service.py:43`). The number the user read was
never the number the inference applied.

`trade_service.py:2597` now returns a `model` block carrying both age thresholds, all three
weights and both cuts; `team_review.py:148` passes it through. `TeamReviewScreen.tsx:415` renders
the full arithmetic — each share × its weight, the signed contribution, the total, and the two
cuts the total is bucketed against — with the ages read from the payload
(`TeamReviewScreen.tsx:399/403`). Same rule `equal_pick_share` already followed: a client reads an
encoding, it never restates one. Optional in the TS type, so an older payload hides the card
rather than rendering `undefined`.

This is also the honest partial answer to **#365**: the card states in plain words that the model
reads roster age and pick capital only — *not* record, lineup, or picks already traded away — so
a young all-in team reading as "rebuilder" is now explained on screen rather than mysterious.

**"Track user completion… once they've gone through it, it should be minimized by default."**

`TeamReviewEntryCard.tsx:31` adds `ftf_team_review_completed`, kept **separate** from the existing
`ftf_team_review_collapsed`: collapsing is "not now" (reversible deferral), completing is a fact
about the flow, and the row copy distinguishes them ("Team review · done" vs "Team review",
`:96`). Hydration ORs the two (`:72-80`), so either minimizes. `markTeamReviewCompleted`
(`:48`) is called from the `plan` beat's finish action (`TeamReviewScreen.tsx:271`), unawaited —
a storage failure costs the minimization, never the exit. Dismissal still **collapses, never
removes**, preserving D-025's ruling: the row remains the recovery path.

## 5. Sabotage results — every new assertion proven red

Each fix was reverted in isolation, the guard run, then restored (`pytest` re-run green at 3606).

| # | Sabotage | Guard | Result |
|---|---|---|---|
| 1 | Drop the two `#368` kwargs from the route call | `test_team_review_route_passes_the_pick_capital_it_computes` | **FAILED** ✓ |
| 2 | Re-cross the seed-ladder roster conditions | `test_seed_ladder_buys_are_off_roster_and_sells_are_on_roster` | **FAILED** ✓ |
| 3 | Re-cross the community ladder's two lists | `test_community_ladder_maps_buys_to_higher_and_sells_to_lower` | **FAILED** ✓ |
| 4 | Stop shipping `model` in `signals` | `test_window_ships_the_model_so_no_client_restates_a_threshold` | **FAILED** ✓ |
| 5 | Restore `gap = u - c` in `compute_consensus_gap` | `test_consensus_gap_sells_are_where_the_market_is_higher_than_you` | **FAILED** ✓ |

**One pre-existing test had to be re-encoded, not just re-run.**
`test_consensus_gap_sells_expose_rank_gap` asserted the defect directly — it took a player the user
rated 300 *above* the community and asserted he was an "easiest sell". It is now
`test_consensus_gap_sells_are_where_the_market_is_higher_than_you` and holds **both** roster
players, so it proves a *selection* (the 200-below player is in, the 300-above player is out)
rather than only a sign.

**A second test had gone vacuous under the fix and was repaired.**
`test_divergence_ignores_unjudged_players` seeded `user_roster=["p1", …]` with p1 high and p2 low —
under the corrected rule **both lists came back empty**, so its leak assertion proved nothing while
still passing green. The roster is now `["p2", …]` so each list carries a real row, plus an explicit
`assert d["higher_than_market"] and d["lower_than_market"]` so it can never silently hollow out again.

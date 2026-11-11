# Fast deck v2 — rules-first construction

**Date:** 2026-11-11 · **Status:** design, not built · **Baseline:** `origin/main` @ `adead776`
· **Entry point:** operator ask after the 2026-11-11 production regression (fast deck served 2
cards, then "No trades found"; flag turned off again by D-232 / PR #649)

Read with [ADR-028](../../adr/adr-028-page-first-trade-search.md), [recommendation](recommendation.md)
(R0, R2b, R3), [scale](scale.md) and [real leagues](real-leagues.md). Everything measured here
was measured offline on this laptop against the 247 recorded production requests in the main
checkout's git-ignored `data/prod-requests/` (aggregates only; no names, ids or rosters leave
that folder), plus synthetic leagues for sizes production has not recorded. The scratch scripts
are outside the repository. Nothing here touched production.

- [1. Problem and evidence](#1-problem-and-evidence)
- [2. Requirements, with numbers](#2-requirements-with-numbers)
- [3. What the measurements say](#3-what-the-measurements-say)
- [4. Candidates](#4-candidates)
- [5. Recommended design: rules-first construction](#5-recommended-design-rules-first-construction)
- [6. Tests that would have caught this](#6-tests-that-would-have-caught-this)
- [7. Rollout](#7-rollout)
- [8. Cost and scale](#8-cost-and-scale)
- [9. What stays open](#9-what-stays-open)
- [Appendix: method](#appendix-method)

## 1. Problem and evidence

The fast deck (ADR-028) proves the first 150 cards of the bilateral generator's ranked
inventory and hands only those to the worker. Everything after generation — significance, the
bilateral presentment, the deck quality filters (`deck_quality.py`), decline-window suppression,
dispositions — then runs on those 150. The parity suite compared the page with the full solve's
first 150 *generator* cards. It never compared what the user is finally served.

What production logged for one heavy tester's league:

| | Reached the quality filters | Survived | First durable batch |
|---|---|---|---|
| Full solve, 2026-11-09 | 2,444 | 67 (2.7%) | 30 cards at 26.2 s |
| Fast deck, 2026-11-11 (twice) | ~129 of 150 | 2 | 2 cards at 5.9 s |

The replay below shows this is not one league's quirk. The generator's ranking and the
downstream rules disagree about almost every card, so a prefix of the generator's order is a
prefix of mostly rejected cards.

## 2. Requirements, with numbers

| Requirement | Number designed to | How it is checked |
|---|---|---|
| **Fast** | First durable batch (30 cards) **≤ 3 s p95 on Render** for 12–14 team leagues at up to 1,000 searches an hour. Construction itself **≤ 1 s p95 on Render** (≈ 0.3 s on this laptop; Render's CPU is assumed 3–4× slower, which must be confirmed in shadow). | Shadow log of construction ms and first-batch ms per job |
| **Accurate** | The served deck (after every filter and rule) is **identical in cards and order** to the complete pipeline's, in the same process. Never thinner because of where a filter runs. | Served-deck parity test (§6) and the shadow comparison (§7) |
| **Scale** | One process, four threads, one CPU. Construction CPU at 1,000 searches an hour **under 50% of one core**; memory per search in tens of MB, not hundreds. | Load harness over recorded requests (§8) |

"Identical" means inside one process: the incumbent engine is not repeatable across processes
(R0, still open), so cross-process comparisons are not meaningful for any design here.

## 3. What the measurements say

Method in the appendix. The downstream pipeline was replayed in production's order for an
organic owner deck: significance (enforce), bilateral presentment, deck quality filters. The
database-backed stages (decline-window suppression, late dispositions, likes-you injection)
could not be replayed offline, so **production removes more than the numbers below** — the
heavy tester's league survives at 6.7% in the replay and 2.7% in production.

### 3.1 Survival is 2–33% everywhere, median 7%

247 requests, 13 leagues, full revision-2 solve, then the downstream pipeline:

| | Median | p10 | p90 | Min | Max |
|---|---|---|---|---|---|
| Cards the generator emits | 2,831 | 1,782 | 3,971 | 372 | 4,670 |
| Cards served after all replayed filters | 196 | 93 | 351 | 69 | 510 |
| Survival | 7.3% | 3.6% | 14.8% | 2.1% | 32.5% |

Per league the median survival runs from 4.3% to 29.2%; 12 of 13 leagues sit between 4% and 15%.
**~3% is the low end of normal, not an outlier**, and production's extra stages push it lower.

Which rule rejects a card first (pooled over 680k generated cards):

| Rule | Share of generated cards |
|---|---|
| filler (a piece below max(450, 25% of the headliner)) | 58.4% |
| significance (no meaningful centerpiece) | 17.7% |
| breakup (best piece received < 70% of best piece given) | 9.8% |
| redundant QB/TE | 6.4% |
| **survives** | **7.7%** |

What trips the filler rule — the sub-bar pieces on filler-rejected cards:

- **89.5% are below the absolute 450 floor**; 10.5% are above it but under a quarter of the headliner.
- **79.7% are bench players** (RB 27.7%, WR 21.3%, QB 16.7%, TE 14.0%), 12.5% are picks (almost
  all second-rounders, 9.9%; firsts 0.1%), 7.8% are starters.
- 56% of the rejected cards are 2-for-1, 41% are 1-for-2, 3% are 1-for-1; 81% have exactly one
  sub-bar piece. The viewer gives 58% of the offending pieces.

In plain terms: the bilateral search pads most packages with a low-value bench player or a
second-round pick, and the 2026-10-14 rule throws those packages away.

### 3.2 A deeper page does not rescue the current design

How deep into the generator's ranked inventory a page must go before the served deck's first N
cards are final (smallest prefix whose downstream result matches the full pipeline's first N):

| N served | Median depth | Median share of the inventory | p90 share |
|---|---|---|---|
| 30 | 1,832 cards | 70% | 91% |
| 60 | 1,844 | 72% | 91% |
| 150 | 2,278 | 86% | 100% |

Proving such a depth with the unchanged page search took 2–4 s of CPU (4,300–5,900 exact
evaluations) where it could be done at all; for 167 of 247 requests the depth exceeded 1,500
cards and was not attempted. That is about half the full solve's cost for none of its
simplicity.

The reason it is so deep is the **repeat cap** (no asset in more than 3 of the first 30 cards,
the rest deferred to just after the window). Survivors concentrate on a handful of assets, so
in **232 of 247 requests the cap's window never fills**: the first 30 served cards are every
cap-respecting survivor in the whole inventory, followed by deferred repeats. The first 30
therefore depend on the entire ranked inventory. In one replayed deck the 19th served card was
the generator's 1,613th.

What today's 150-card fast deck serves after the same pipeline: median **11 cards** (p10 3,
max 70); fewer than 30 for 216 of 247 requests, fewer than 10 for 108. Its first 30 equal the
full pipeline's first 30 for **2 of 247**. The 2026-11-11 incident is the typical case.

### 3.3 The full solve spends ~93% of its evaluation time on cards the rules reject

Instrumenting the unchanged full solve's evaluator: **96.2% of exact evaluations** (93.4% of
evaluation time) are on packages whose terms already fail a per-card rule, and 92.3% of the
eligible proofs it writes are later thrown away. The rules depend only on the package's terms
and on request inputs the worker already holds (consensus values, positions, rosters, lineup
slots, the board for significance). **They can be decided before pricing.**

### 3.4 Moving the per-card rules ahead of ranking: exact, cheap, and a small definition change

If the per-card rules (significance, breakup, filler, redundant) decide eligibility *before*
the ranker runs, the ranker's diversity window and revision 2's same-family price precedence
see only cards that can be shown. Two prototypes, both on all 247 requests:

- **Gated full solve** (expansions failing the rules are not evaluated; failing focal pairs
  are still evaluated because they are parents; failing survivors drop before ranking):
  identical to "rank the filtered survivors" on **247/247**, median **1.73 s** CPU against
  **8.45 s** for the incumbent (4.8×; 3.6–5.9×).
- **Filtered page search** (the ADR-028 search with the rules applied to the screened entries
  before pricing, to family completion, and to held proofs): its pages equal the gated full
  solve's prefix on **247/247**, and run to exhaustion it equals the whole gated inventory on
  23/23 latest requests. Median **0.20 s** to build the *entire* filtered inventory (max 0.30 s,
  985 exact evaluations median) against 3.55 s for the incumbent on a quiet machine.

The definition change, measured on the same 247 requests ("old" = filter after ranking, as
production does today; "new" = filter before ranking):

| | Old vs new |
|---|---|
| Served deck size | identical on 247/247 (same cards survive; only order moves) |
| First card the same | 167 of 247 (68%) |
| Cards shared in the first 30 | median 25 (p10 20) |
| Cards shared in the first 150 | median 141 (p10 93) |
| Mean weaker-side support, first 30 | 0.5046 → 0.5035 (median change −0.001) |
| Distinct assets in the first 30 | 33 → 35 (median +1) |
| Partners in the first 30 | 10 → 10 |

So the new definition serves the same cards, ranks them with equal support and slightly more
variety, and reorders roughly one card in six in the first 30. The reordering exists because
today a rejected card still consumes diversity budget and still delays its cheaper-family
siblings before it is thrown away.

## 4. Candidates

CPU figures are construction plus the downstream stand-in, single-threaded, this laptop,
medians over the 247 requests (main run, ten processes in parallel, so somewhat inflated)
unless marked "quiet" (latest request per pair, nothing else running).

### A. The operator's idea: fast page first, full solve in the background, append

How it would work: publish the fast deck's survivors, keep the job alive, run the full solve
behind it, append (or rebase the client onto) the full deck.

- **Speed:** the first view is today's fast deck after filters: median 11 cards, fewer than 10
  for 108 of 247 requests. The full deck still arrives after the full solve: 25–60 s for the
  heavy league in production.
- **Accuracy:** the first page is not the head of the final deck. Because the repeat cap reaches
  into the whole inventory (§3.2), the full pipeline's first 30 differ from the fast page's
  served cards on 245 of 247 requests, so the append either reorders cards the user has already
  seen or serves a deck that differs from the full pipeline's. Both break the publication
  contract (`_publish_owner_batch` asserts the published prefix is the head of the finished
  deck), impression ordinals, and the one-evidence-seal-per-job rule ADR-028 kept.
- **Scale:** total work is page + full solve + downstream twice, about **9.8 s of laptop CPU per
  search** against 9.1 s for the full solve alone — more than today's slow path. On one Render
  CPU the full solve already cannot sustain 100 searches an hour (§8). Under load it is worse
  than the arithmetic: on one process the background solves hold the interpreter lock while
  the next users' fast pages wait, and at 1,000 searches an hour the *first* page arrived in
  **47 s median** in the load test (§8.3).
- **Lifecycle:** a background solve per search needs cancellation when the user leaves,
  supersession when inputs move, and a rule for which deck the cursor follows. All exist in
  pieces (`preserve_running`, `rebased`), none for a job that publishes twice.

**Verdict: does not meet any of the three requirements on its own.** It makes the screen look
busy sooner and doubles the CPU. Its useful kernel — "show something while the rest is built" —
is not needed once the complete deck takes a fraction of a second (§5). Kept only as a
documented non-goal.

### B. Filter-aware page search

How it works: give the page search the per-card rules as an admission predicate. Screened
entries that fail are dropped before pricing (the rules need only terms and request inputs),
revision 2's family completion skips failing members, and only admitted proofs are held. The
proof structure of ADR-028 is unchanged: bounds order work, the unchanged evaluator decides,
the stop test is over admitted cards.

- Exact against "rank the filtered survivors" by construction; measured 247/247.
- It **cannot** be exact against today's definition (filter after ranking) cheaply: today's
  first 30 depend on ~70% of the inventory (§3.2). B therefore implies the definition change
  in §3.4.
- Order-dependent stages (presentment, repeat cap) need the served prefix to be final. With a
  150-card page the first 30 were final for 153 of 247 requests; the rest need deeper pages
  because the cap window rarely fills. Rather than certify a prefix, run the filtered search
  to exhaustion: the filtered inventory is small (median 196, max 510 cards) and exhausting it
  costs 0.20 s median.
- Cost: one-shot 150-card filtered page 0.32 s; whole filtered inventory 0.20 s quiet; today's
  unfiltered 150-card page 0.69 s.

**Verdict: the speed half of the answer.** Faster than today's fast deck, and its deck is the
whole filtered inventory instead of a 150-card stub.

### C. Generator-side constraints

How it works: the same predicate as a gate inside the full solve. Expansions whose terms fail
are not evaluated; focal pairs still are (parents of expansions); failing survivors are removed
before the ranker.

- Exact against the new definition, 247/247; 4.8× cheaper than the incumbent (1.73 s vs 8.45 s).
- Does not change which cards survive (same served set on 247/247); changes order only through
  the definition change of §3.4, which it shares with B.
- Further exact pruning is available: filler is monotone (adding an asset never removes a sub-bar
  piece and never lowers the bar), so any companion below max(450, 25% of the package's
  headliner) can be skipped without enumerating it.

**Verdict: the scale half of the answer.** Every path that still needs a full solve (prepared
inventories, weekly replenishment, Calibration's refresh, pinned and exact-give searches, very
large leagues, page-search fallbacks) gets ~5× cheaper and serves the same deck the page search
would.

### D. Precompute (prepared inventory, first-page store, replenishment)

These exist. The first-page store already holds the *served* (post-filter) pages per scope and
serves them while a backing job rebuilds; the prepared inventory (knob currently 0) and the
weekly replenishment build complete inventories ahead of time.

- Precompute helps only when the request was predictable and nothing changed. It misses exactly
  on the cold path that failed on 2026-11-11 (a changed roster, board or preference), and its
  cost scales with users × input changes, mostly for decks nobody opens (the bilateral arm wrote
  ~179k impression rows for 221 viewed cards).
- With B+C a cold build costs ~0.2 s, so precompute stops being needed for speed. It becomes
  ~15× cheaper wherever it remains (C), and the stored pages stay consistent with live builds
  because both use one definition.

**Verdict: keep what exists, do not extend.** No invalidation machinery is worth building for a
0.2 s rebuild.

### E. Combinations

| | Speed (first batch) | Accuracy (served deck = complete pipeline's) | Scale (construction CPU / search) | Verdict |
|---|---|---|---|---|
| Today's full solve | 25–60 s prod for the heavy league | Reference (old definition) | 9.1 s laptop | Too slow; saturates one CPU near 100/h |
| Today's fast deck | 5.9 s prod | **No**: median 11 served cards, first 30 match 2/247 | 0.7 s | Turned off (D-232), rightly |
| A. Page + background full | Thin first view; under 1,000/h load the first page itself took 47 s median | **No**: page ≠ head of final deck on 245/247 | 9.8 s | Reject |
| Old page, deepened to 30 survivors | ~3 s laptop where possible | Yes (old definition) | 2–4 s; often impossible (167/247 > 1,500 deep) | Reject |
| B alone, 150-card page | ~0.3 s construction | Yes for first 30 on 153/247 only; deck capped | 0.32 s | Needs exhaustion |
| C alone (gated full) | ~1.7 s laptop construction | Yes (new definition), 247/247 | 1.7 s | Good fallback, not the fast path |
| **B (to exhaustion) + C (fallback) — recommended** | **~0.2 s laptop construction** | **Yes (new definition), 247/247 page; 23/23 whole deck** | **0.20 s quiet** | **Recommend** |
| D (extend precompute) | Instant on a hit, nothing on a miss | Yes | Background CPU ∝ users × changes | Keep as is |

## 5. Recommended design: rules-first construction

**One sentence:** make the deck's per-card rules part of what an owner-bilateral card *is*, so
construction only ever builds cards that can be shown; build the whole admitted inventory with
the page search (it is small and cheap), fall back to the gated full solve, and leave the
order-dependent stages where they are.

### 5.1 The contract

- **Per-card rules move ahead of ranking** for owner-bilateral decks (revision 1 and 2, the two
  generators with parity suites): significance (discovery context), breakup, filler, redundant
  QB/TE. A card that fails is never ranked, never held, never published, never evidenced.
- **Ranking runs on admitted cards only.** The diversity window and revision 2's family
  precedence see only cards that can be served (the definition change of §3.4).
- **Order-dependent stages stay downstream, unchanged and in place:** likes-you / revised-offer
  injection (protected cards), decline-window suppression with its floor and one retest, owner
  revalidation, late dispositions (#419), the bilateral presentment permutation, the repeat cap,
  evidence and publication. They now run on the complete admitted inventory, exactly as they run
  on the complete inventory today.
- **The downstream copies of the per-card rules stay** as guards. On an owner deck they must
  remove zero cards; a non-zero count is logged as a parity tripwire (§7).
- **No deck-size cap.** The deck is the whole admitted inventory (median 196, max 510 in the
  replay). ADR-028's 150-card limit and its depth trade-off go away.

### 5.2 Modules

| Module | Change |
|---|---|
| `backend/deck_rules.py` (new leaf) | `DeckRules`: built once per job from what `_run_trade_job` already holds (viewer league id, `seed_map` → market via `elo_to_value`, `players_dict` positions, league rosters, `_league_lineup_slots`, the significance capture and the viewer's board and sources). `reason(target, give, receive)` returns the first failing rule or None; memoised by `(target, frozenset(give), frozenset(receive))`. `VERSION` string. Pure: no I/O, no flags. It calls the same predicate functions `deck_quality.filter_deck` uses (make `_breakup`, `_filler`, `_redundant_side` public there; `filter_deck` keeps calling them) and `trade_significance.evaluate_significance`, so the two cannot drift. |
| `backend/trade_first_page.py` | `PageSearch(..., admit=None)`. With `admit`: skip screened entries whose terms fail (in `_Member.screen`, before the heap push, so the heap holds only admitted packages), skip failing members in `_family`, and hold only admitted eligible proofs. Parents are still evaluated on demand for expansions, so the universe is unchanged. Report gains `rules_version` and `rules_rejected`. `admit=None` is byte-identical to today. |
| `backend/trade_fast_deck.py` | `serve(generate, context, rules, check)`: a `PageSearch` with `admit=rules.admits`, taken to exhaustion under the work limit (keep `MAX_VERIFICATIONS = 12,000`; the replay's maximum was 1,637). Unproven, over the limit, or unsupported → `None`. `DECK_SIZE` is removed. `shadow` compares the served decks, not generator prefixes (§7). |
| `backend/trade_gen_rules_gate.py` (new leaf) or a function in `trade_fast_deck.py` | The gated full solve: a private subclass of the generator's search (as `_private_search` does) whose `evaluate` returns a cheap rejection for expansions failing `rules`, plus a ranker wrapper that drops failing survivors before the generator's own `_rank`. Reuses `trade_gen_bilateral._generate_with_search`; the incumbent modules stay untouched. |
| `backend/server.py` `_run_trade_job` | Build `DeckRules` once, before `_gen_owner`, from the inputs the quality-filter block reads today. In `_gen_owner`: rules-first on → `trade_fast_deck.serve(...)`, else on `None` the gated full solve, else (flag off) today's path. Prepared inventories, replenishment and Calibration's refresh use the gated full solve under the same flag, so stored and live decks share one definition. The quality-filter block stays and logs its counts. `DECK_PIPELINE_VERSION` bumps; `deck_rules.py` joins `_ENGINE_CODE_MODULES`. |
| `backend/eval/served_deck_replay.py` (new operator tool) | Promote the scratch replay: per recorded request, full pipeline under both definitions, page vs gated vs full, survival by rule, timing. Aggregate-only output, as `acceptance_eval.py`. |

### 5.3 Invariants

1. **Served-deck parity:** for every supported request, the served deck from the page path
   equals the served deck from the gated full solve, same process, same inputs.
2. **Same survivors as today:** the set of cards served under rules-first equals the set served
   by today's full pipeline (only order may differ). Measured 247/247.
3. **Guards drop nothing:** downstream significance and quality filters remove zero owner-bilateral
   cards when rules-first is on.
4. **No thin decks by placement:** the served count from the page path equals the gated full
   solve's, always; there is no prefix length anywhere in the fast path.
5. **One evidence seal per job, published prefix = head of the finished deck:** unchanged, because
   the job still completes its inventory before publishing (it is just ~15× smaller and
   ~19× cheaper to build: 0.20 s against 3.8 s quiet).
6. **`admit=None` is byte-identical** to today's page search and fast deck; flag off is
   byte-identical to today's worker.

### 5.4 What it deliberately does not do

- It does not push decline-window suppression into the predicate yet. Suppression is a per-card
  near-duplicate test plus a floor and a single retest grant (order-dependent). For heavy users
  with long decision histories it may remove many cards, which is the likeliest reason
  production survival (2.7%) is below the replay's (6.7%) for the heavy tester. Under
  rules-first it removes from the complete admitted inventory, so it cannot thin the deck by
  placement. Moving its near-duplicate test into `DeckRules` (floor and retest staying
  downstream) is a later, measured step (§9).
- It does not touch legacy v2/v3, `trade_gen_v2`, `owner_v1`, bilateral revision 3 or
  `value_core`: they keep the full solve and today's definition.
- It does not change the repeat cap, the presentment, or any threshold.

## 6. Tests that would have caught this

The missing test is the obvious one: **compare what the user is served, not what the generator
emits.** All of these use synthetic leagues and committed fixtures; the replay tool covers
recorded requests offline.

1. **Served-deck parity through the worker** (`test_trade_fast_deck.py`, using its existing
   `revised` worker fixture): run `_run_trade_job` with rules-first on and with the page path
   forced off (gated full), capture `job["cards"]` after the final publication, assert identical
   trade identities and order, and identical served counts. Today's fast deck fails this test on
   any fixture where a filter rejects a page card.
2. **No thin deck by placement:** same harness with a fixture built so ≥90% of the top 150
   generator cards fail filler (bench padding, as production does). Assert the page path's
   served count equals the full path's and is ≥ 30. Today's design serves single digits.
3. **Predicate equivalence:** for random packages over the synthetic league, `DeckRules.reason`
   is None iff `deck_quality`'s per-card rules and `evaluate_significance` all pass. Pins the two
   copies together.
4. **Filtered page = gated full, exhaustively:** `PageSearch(admit=…)` taken to exhaustion equals
   the gated full solve card for card and proof for proof, for both revisions, several seeds and
   12/14/16 teams (the 16-team case with the budgets lifted, see §9).
5. **Gated full = rank(filtered survivors):** gated full solve equals the generator's `_rank` over
   the incumbent's survivors that pass `DeckRules`.
6. **Same survivors:** under rules-first the served *set* equals today's full pipeline's served
   set on the fixtures (order may differ).
7. **Guards drop nothing:** with rules-first on, the downstream quality filter and significance
   counts on owner-bilateral cards are zero.
8. **Repeat-cap regression fixture:** a deck where the cap window never fills (the normal case in
   production, 232/247), asserting the first 30 served cards match between paths.
9. **`admit=None` byte identity** for `trade_first_page` and flag-off byte identity for the
   worker (extend the existing flag-off tests).

## 7. Rollout

1. **Build behind two new flags, both off:** `deck.rules_first_shadow` and `deck.rules_first`.
   `trade.fast_deck` stays off (D-232) and is retired once rules-first serves.
2. **Offline gate before any flag:** `backend/eval/served_deck_replay.py` on `data/prod-requests`
   must show page = gated on every request, same served set as today on every request, and the
   timing distribution above.
3. **Shadow (one week):** the job serves exactly as today (full solve, filters after). With
   `deck.rules_first_shadow` it also, from the full solve's own inventory and in the same
   process, computes the rules-first served deck (filter, rank, downstream stand-in: cheap,
   milliseconds), runs the filtered page search to exhaustion and times it, and logs one line:
   `rules-first shadow: page_eq_gated=… same_served_set=… first_card_same=… overlap30=…
   served_old=… served_new=… page_ms=… verified=… rules_rejected={…}`. Plus a per-stage timing
   line for the whole job (prelude, construction, downstream, evidence, first batch), because the
   2026-11-11 fast deck took 5.9 s to its first batch with only ~0.5 s of construction and that
   remainder is not understood.
4. **Operator decision on the definition change** (§3.4), with the shadow's overlap numbers and,
   if wanted, a blind grade of old vs new first 30 on a few real decks.
5. **Serve:** flip `deck.rules_first`. Watch per job: construction ms, first-batch ms, served
   count, fallback reason (unsupported / over limit / error → gated full), downstream guard
   counts (must be zero), and the existing `presentment-tripwire`. Run the TestFlight checklist
   (cold build after a board edit, after a roster change, a heavy-history account, a 14-team
   league, a pinned search, deck paging to the end).
6. **Kill switch:** `deck.rules_first` off + `POST /api/feature-flags/reload` returns to today's
   full-solve pipeline (slow, known good). `DECK_PIPELINE_VERSION` moves once, so stored first
   pages rebuild once each way.

## 8. Cost and scale

### 8.1 CPU per search (this laptop)

| Path | Construction + downstream CPU per search | Notes |
|---|---|---|
| Today's full solve + filters | 8.45 s + 0.63 s (main run); 3.55 s + 0.27 s quiet | Peak ~250 MB per search (scale.md) |
| Today's fast deck (150) | 0.69 s | Serves median 11 cards |
| A. Page + background full | ~9.8 s | Both of the above |
| C. Gated full solve | 1.73 s (main run); 1.20 s quiet | Exact to the new definition |
| **B. Filtered page, whole admitted inventory** | **0.20 s quiet** (max 0.30 s); 150-card page 0.32 s main run | Downstream on ~200 cards is milliseconds |

The load results (production shape: one process, four threads, open-loop Poisson arrivals over
the latest request of each of the 23 manager-league pairs, latency from arrival) are in §8.3.

### 8.2 At 10, 100 and 1,000 searches an hour on one Render CPU

Render's CPU speed relative to this laptop is not measured; the production logs suggest roughly
3–4× (26 s to the first batch of a full solve whose construction takes ~8 s here). Using 4× on
quiet construction figures:

| Searches/hour | Today's full solve (~15 s each) | A (~16 s) | C gated full (~5 s) | **B rules-first (~0.8 s)** |
|---|---|---|---|---|
| 10 | 4% of a core | 4% | 1% | **0.2%** |
| 100 | 42% — queues form at bursts | 44% | 13% | **2%** |
| 1,000 | 420% — impossible on one CPU | 440% | 133% — impossible | **22%** |

The full solve's ~250 MB peak per search is the other limit: four overlapping solves took one
process past 1.1 GB (scale.md). The page search peaks near 16 MB.

### 8.3 Load test

One process, four threads, this laptop, run alone. Each search includes the downstream
stand-in. "Filtered" is a 150-card filtered page (whole-inventory exhaustion costs about the
same, §3.4). Latency is from scheduled arrival to the end of the search.

| Path | Searches/s offered (per hour) | CPU per search | Median | p95 | Within 3 s |
|---|---|---|---|---|---|
| Filtered page (B) | 0.28 (1,000/h) | 0.18 s | 0.18 s | 0.27 s | 100% |
| Filtered page (B) | 1 (3,600/h) | 0.18 s | 0.21 s | 0.44 s | 100% |
| Filtered page (B) | 2 (7,200/h) | 0.18 s | 0.24 s | 0.80 s | 100% |
| Filtered page (B) | 3 (10,800/h) | 0.19 s | 0.34 s | 1.2 s | 100% |
| Today's fast deck (150) | 0.28 | 0.30 s | 0.32 s | 0.46 s | 100% (but thin decks) |
| Today's fast deck (150) | 1 | 0.32 s | 0.44 s | 1.7 s | 100% (but thin decks) |
| Gated full solve (C) | 0.28 | 0.97 s | 1.45 s | 3.6 s | 83% |
| Gated full solve (C) | 0.5 | 0.94 s | 2.6 s | 5.8 s | 56% |
| Today's full solve | 0.1 (360/h) | 3.8 s | 7.3 s | 24 s | 4% |
| Today's full solve | 0.28 | 4.1 s | 49 s (backlog) | 72 s | 0% |
| **A. fast page, then full solve on the same process** | 0.28 | 4.7 s | **first page 47 s**, full deck 67 s | first page 86 s | 9% |

The last row is the operator's idea under load, and it is the decisive measurement against it:
the background full solves share the interpreter lock with the next users' fast pages, so at
1,000 searches an hour the *first* page waits behind other people's full solves and arrives in
47 s median. On one process, "fast page in front, full solve behind" is not fast for anyone
once more than a few people search. It would need the full solves moved to separate worker
processes and CPUs, which the deployment does not have.

The filtered page holds a sub-second p95 at ten times the 1,000/hour target on this laptop;
at Render's assumed 3–4× slower CPU that is roughly 3,000 searches an hour inside 3 s for
construction, before the unexplained non-construction time (§9).

### 8.4 League size

No production league has more than 14 teams, so this is the synthetic league
(`backend/eval/synthetic_league.py`, seed 7), one process, quiet. Its value distribution is
not production's: its survival rate (10–16%) is higher than the replay's, so the admitted
inventories below are larger than a real league of that size would have. Treat these as a
pessimistic cost probe, not a survival estimate.

| Teams | Candidate universe | Incumbent evaluated | Full solve CPU | Gated full CPU | Admitted inventory | Filtered page: 150 cards | Filtered page: whole inventory |
|---|---|---|---|---|---|---|---|
| 12 | 45,056 | 45,023 | 3.5 s | 1.3 s | 520 | 0.17 s | 0.38 s |
| 16 | 61,440 | 60,000 (budget) | 4.7 s | 1.7 s | 481 | 0.25 s | 0.37 s |
| 24 | 94,208 | 60,000 (budget) | 7.4 s | 2.6 s | 1,037 | 0.24 s | 0.74 s |
| 32 | 126,976 | 60,000 (budget) | 9.8 s | 3.0 s | 1,767 (1,783 un-budgeted) | 0.47 s | 1.5 s |

- From 16 teams the incumbent's 60,000-evaluation budget binds, so its "full solve" is a
  truncated search whose result depends on stream order. The filtered page search ignores the
  budget and covers the whole universe: at 32 teams it found 16 admitted cards the budgeted solve
  missed, and its first 150 still matched the gated solve's.
- The whole admitted inventory grows with league size (1.5 s at 32 teams here). If that is too
  slow on Render, cap the fast path at the first 150 admitted cards for leagues over 16 teams and
  accept that the repeat cap is then applied to those 150 — an explicit, logged definition for
  large leagues — or certify the served prefix (presentment moves cards fewer than 32 class
  positions; the repeat cap's head is final once 30 cards fill it). Decide after shadow timing.

## 9. What stays open

- **The definition change needs the operator's yes** (§3.4). It is the price of exactness at
  speed: today's definition (filter after ranking) makes the first 30 depend on ~70% of the
  ranked inventory, so no fast path can reproduce it.
- **The repeat cap almost never fills its window** (232/247). It therefore pulls the
  lowest-ranked distinct survivors into the first 30 ahead of better repeats. That is a product
  question about the 2026-10-14 rule, not part of this design; flag it to the operator.
- **Decline-window suppression** is not replayable offline. The shadow line in §7 measures how
  much it removes for heavy users; if it is large, push its near-duplicate test into `DeckRules`.
- **Production timing outside construction** (5.9 s to the first batch with ~0.5 s of
  construction on 2026-11-11) is unexplained. The per-stage timing line in shadow is the
  measurement; the 3 s first-batch target depends on it.
- **16–32 team leagues** have no recorded requests. The incumbent's stream budgets bind there,
  so its "full solve" is itself truncated and the page search falls back today. Rules-first
  should use the un-budgeted admitted universe as the reference (it is small); §8.4 has the
  synthetic cost. Decide whether the budgeted or un-budgeted universe is the definition for
  large leagues.
- **R0** (the incumbent's output depends on the hash seed) still stands. All parity here is
  in-process.
- **The generator still proposes padded packages.** Rules-first stops paying for them, but
  58% filler rejection says the bilateral pools favour bench padding. A pool-level change is a
  model change for the bake-off process, not this design.
- **Other per-card gates** that are dark today (`trade.roster_evaluation`,
  `trade.personal_market_policy_v1`) belong in `DeckRules` too when they turn on; the rule is
  "a per-card gate on owner cards is an admission rule; its downstream copy is a guard".

## Appendix: method

- **Inputs:** the 247 recorded owner requests (`bakeoff_runs.config_json.owner_request`) in the
  main checkout's git-ignored `data/prod-requests/`, production's `model_config` capture, this
  branch's `config/features.json`. Each request rebuilt as `bilateral_revision_benchmark.worker`
  rebuilds it, in a fresh interpreter with `PYTHONHASHSEED=0`, network blocked, a private
  scratch SQLite database.
- **Downstream stand-in:** `trade_significance.evaluate_significance` (discovery, tier "second",
  first-round picks allowed — production's capture), `trade_bilateral_presentment.present`,
  `deck_quality.filter_deck` with market = `elo_to_value(seed_elo)`, positions from the request,
  rosters from the request, lineup slots from the viewer's observed `starter_slots`, else
  another request in the same league, else the platform default template (+ SUPER_FLEX for
  `sf_tep`). Not replayed: decline-window suppression, dispositions, likes-you and revised-offer
  injection, owner revalidation (a no-op on unchanged inputs).
- **Depth for N served:** smallest prefix of the ranked inventory whose downstream result has the
  same first N cards as the downstream result of the whole inventory.
- **Prototypes:** a `PageSearch` subclass that removes failing screened entries before pricing,
  drops failing held proofs and filters family members; a gated full solve wrapping the
  generator's `evaluate` and ranker. Both scratch-only; the design in §5 places them properly.
- **Timing:** `time.process_time` per search. The 247-request run used ten processes on a
  12-core laptop with mixed core speeds, so its absolute times are inflated; "quiet" figures are
  one process over the 23 latest requests. Load tests ran alone.

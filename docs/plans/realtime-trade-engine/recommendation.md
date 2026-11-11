# Real-time trade engine — architecture review and recommendation

**Date:** 2026-11-10 · **Entry point:** direct operator ask · **Baseline:** `origin/main` @ `09a05875`

The ask: review the valuation and offer-construction architecture, bring in practice from
decision engines in lending, matchmaking and low-latency recommendation, and re-architect so
that (1) the trades shown are the ones both managers are likely to accept, and (2) a cold
search produces its first cards in near real time instead of depending on pre-generation.

This document is the review and the recommendation. What this branch actually builds is in
[scope.md](scope.md); everything else here is a proposal, not a shipped change.

## 1. What the engine does today

One organic Find a Trade request, on the owner-bilateral path (`bakeoff_owner_only` with
`owner_bilateral_enabled` and the revision selector):

1. **Prelude** (`server._run_trade_job`): load boards, preferences, untouchables, picks,
   outlooks; capture the request (`_owner_generation_context`).
2. **Construction** (`trade_gen_bilateral*._Search`, `_generate_with_search`): per opponent,
   stratify a pool of 16 assets a side, enumerate every 1×1 / 2×1 / 1×2 (4,096 per opponent,
   60,000 total), and run the exact evaluator on each. The evaluator prices the package on
   consensus market value, applies the fairness floor and overpay ceiling, scores each side's
   *support* (0.45 preference fulfilment + 0.35 market acceptability + 0.20 team plan), applies
   intent, untouchable and tanking rules, and freezes a JSON proof.
3. **Global rank**: maximise the weaker side's support, then total support, with bounded
   diversity and same-focal price-efficiency precedence.
4. **Final checks on the whole inventory**: owner revalidation, dispositions, significance,
   quality filters, presentment.
5. **Durable evidence, then publication**: impression rows for the first 30 cards commit
   before the first card is published; 100-row batches follow.

Latency is handled around this, not inside it: app-open warm-up, a device page store, and
persistent prepared inventories (`prepared_trade_*`) that are adopted when the exact request
and every dependency still match.

### Measured cost of a cold search

Production (2026-09-19, [trade-search-latency](../trade-search-latency/README.md)): 18–75 s
interactive, later 8.75 s to the first durable batch. The 2026-11-05 device baseline: one
123 ms cached success and two ~10 s timeouts in three taps.

Local profile for this review (`backend/eval/synthetic_league.py`, 12 teams, revision 2,
Python 3.12): **45,023 candidates evaluated, 3,923 survivors, 3.4 s for construction alone.**

| Finding | Number |
|---|---|
| Candidates rejected at the market floor (a three-number check) | 39,006 of 45,023 (87%) |
| JSON decode of the engine's own just-written proofs | 29,604 `json.loads`, ~19% of time |
| Proof serialisation (each eligible proof is written twice) | 7,862 `json.dumps`, ~9% |
| Market package pricing (same package priced 3–4×) | 81,125 calls, ~18% |
| Lineup assignment | 12,862 calls, ~12% |
| Fixed setup: search construction / pool building | ~11 ms / ~28 ms |

## 2. Diagnosis

**D1 — The pipeline is complete-then-paginate.** Every stage before the first card is
O(inventory): all 45,000 candidates are evaluated and all ~3,900 survivors are ranked,
revalidated and presented so that 30 can be shown. The first page is a *delivery* prefix of
finished work. A first page should cost O(page).

**D2 — Evaluation is evidence-first.** The evaluator builds the audit record while it
decides. Nine in ten candidates fail a check that needs three numbers, and the engine pays
for the card object, the selection record, tier lookups and a fresh price each time. Cheap
decisions and expensive evidence are not separated.

**D3 — The cache unit is the whole answer.** A prepared inventory is valid for one exact
request under one full dependency receipt. A preference edit, a pin, a league switch or any
of twelve rosters changing is a full miss, and the miss path is the 3–10 s solve. Adoption
itself recomputes receipts across many tables. Whole-deck caches have the worst hit rate
exactly where the 200 ms gate is failing (the immediate-change cohorts).

**D4 — The ordering score is not a probability.** Support is a hand-weighted blend that the
code itself labels "not an acceptance probability". Both managers are scored with the same
weights; a manager with no board gets a neutral 0.5 for preference; nothing models that
people overvalue what they already own; nothing is fitted to the accept/decline/pass
outcomes the app already logs.

**D5 — Six constructors, one job.** Legacy v2/v3, `trade_gen_v2`, `trade_gen_fit`,
`owner_v1`, bilateral 1/2/3 and `value_core` each own an enumerator, a gate stack and an
evidence shape. Every performance or quality change is paid for per engine, and the bake-off
machinery exists largely to arbitrate between them.

## 3. What other decision engines do

Full research notes with sources are in [research.md](research.md); the existing three-round
matchmaking corpus is in [docs/research/matchmaking/](../../research/matchmaking/README.md).
The practices that transfer:

| Practice | Where it comes from | What it means here |
|---|---|---|
| **Cascade: rules → cheap score → exact model on the top K** | Stripe Radar, Instagram Explore, Pinterest, Etsy | Screen on market floor first, bound the rest cheaply, run the full evaluator only on what can reach the page |
| **Cheap proposer, exact verifier** | Faiss refine indexes; Google Rules of ML #29/#32/#37 | The fast path may only *order* work; the unchanged evaluator still decides and writes the proof, so a served card is never less valid |
| **Anytime / top-K with a stopping proof** | Threshold algorithms in search engines; anytime algorithms (Zilberstein) | Stop when the K-th verified score beats every remaining bound; the page is provably the page, without the tail |
| **Cache components, not answers** | Feature stores (Uber Michelangelo, Chronon), incremental view maintenance | Cache per-league snapshots (values, boards, lineups, plan fits) keyed by input revision; one roster change invalidates one team, not every deck |
| **Pre-approval pools with criteria fixed in advance** | Firm-offer-of-credit practice | A prepared candidate pool per league, filtered at tap time with the same rules, not a prepared deck |
| **Rank by expected completion: P(A accepts) × P(B accepts) × value** | Loan take-rate curves; Su, Bayoumi & Joachims; kidney-exchange failure-aware matching | Order by the chance the trade actually happens, and prefer small packages because long chains fail as a whole |
| **Aggregate near the weaker side** | Reciprocal recommender literature (harmonic mean, cross-ratio) | The current max-min ordering is already the right family; keep it until a calibrated product can replace it |
| **Fit the passive side from outcomes, shrink toward a prior** | Airbnb host acceptance; empirical-Bayes thin-file handling | Per-manager acceptance learned from declines and counters, shrunk to league and global priors; a decline is an explicit negative |
| **Endowment effect** | List (QJE 2003), sports-card market | Managers overvalue assets they hold; price a premium on what the counterparty gives up, smaller for active traders |
| **Shadow, then champion/challenger** | FICO adaptive control, PayPal, Nubank | New paths score in shadow first and are diffed against the incumbent for both answers and latency |
| **Log the features you served with** | Chronon, Rules of ML | Already done here (frozen proofs, impression features); it is what makes offline replay and calibration possible |
| **Calibrate before multiplying** | General practice (no lending primary source found) | Two probabilities multiplied compound miscalibration; measure reliability before the product is allowed to rank |
| **Exposure control across the market** | Su et al. crowding result; LinkedIn response-rate floors | Do not send every manager in a league at the same two rosters |

## 4. Recommended decisions

### Built on this branch

**R2 — Page-first exact retrieval (speed, the architectural change).**
`backend/trade_first_page.py`: an admissible upper bound on the weaker side's support orders
the candidates; the unchanged evaluator verifies them best-first; the search stops when the
page is proven complete. On the 12-team synthetic league the first 30 cards take about
41–46 ms once the process has seen the league (73–82 ms the first time) against 3–4 s for
the full solve, after exactly verifying 100–140 of 45,056 candidates. Those figures were
taken before revision 2 was made exact. Revision 2 delays a card behind cheaper alternatives
found across the whole inventory, so an exact page also has to evaluate each page card's
family members; with that, the synthetic first page takes 70–130 ms. On 247 recorded
production requests the page is the full solve's on every one, and the cost is about 0.28 s
for 30 cards and 0.55 s for 150 against 5.9 s: about ten times faster, and not yet 200 ms
([real-leagues.md](real-leagues.md)). This is D1's answer for construction: the first page
costs O(page).

**The fast deck (the first serving step).** `backend/trade_fast_deck.py` puts R2 on the
worker's generator call behind `trade.fast_deck` (default off): an interactive cold build
gets the proven first 150 cards as its whole deck and runs the unchanged final checks on
them. `trade.fast_deck_shadow` serves the full deck and logs a per-job comparison. This is
narrower than R3 below: the deck ends at 150 cards and the tail is not built.

**Offline acceptance evaluation (evidence for R5).** `backend/eval/acceptance_eval.py`, run
read-only against production. Findings in [acceptance-eval.md](acceptance-eval.md).

**Offer history (evidence for R5 and R6).** 612 real offers from the operator's own Sleeper
inbox, matched to completed trades and priced at dated market values:
[offer-history.md](offer-history.md).

Measured results are in [scope.md](scope.md); load behaviour is in [scale.md](scale.md).

### Tried and not kept

**R1 — Exact fast kernel for the full solve.** The revision-2 constructor with pure calls
memoised, its own proofs decoded once and a short path to the market-floor rejection,
byte-identical to the incumbent. It was built and passed every parity check, and it measured
**1.15–1.18×** on a quiet machine, not the 3× the profile suggested, while raising peak
memory about 75% (252 → 438 MB) and duplicating the incumbent's loop and rankers. What is
left after removing redundant work is unique per candidate: 45,000 package prices, 12,000
owner utilities and their roster assignments, one proof per survivor. A byte-identical full
inventory cannot be made several times cheaper in Python; the gain has to come from not
building the tail before the page (R2). The kernel was removed from the branch.

### Recommended next, in order

**R3 — Publish the first page, then append the inventory.** The fast deck serves a bounded
deck in one pass. The full version publishes the page and then completes the inventory in the
background behind it. It was not attempted because the worker's final checks are not safe to
run twice in one job: they emit exposure events, consume suppression grants, and write one
candidate set and one evidence seal per job, and `_publish_owner_batch` asserts the published
prefix equals the head of the finished inventory. The existing deck paging (`deck_id` +
cursor, with `rebased` moving a client to the scope's current deck and dropping cards it
already holds) is the likely route: a fast deck first, a full deck built behind it, and the
client rebased when it runs out. That needs its own scope block and the trades-eng evidence
contract reviewed.

**R2b — Make revision 2 cheap enough for 200 ms.** On real leagues more than half of the
exact evaluations are family members, and each revision-2 evaluation audits every companion
by evaluating the trade without it. Bilateral-1 on the same requests takes 71 ms for 30
cards. Cheaper dismissal of family members, or sharing the companion audit's sub-evaluations
with the search's own, is the direct route; both must keep results identical.

**R0 — Make the full engine repeatable across processes.** The replay found that the same
request yields different decks and proof bytes in different processes (hash-seed dependent
iteration). That undermines replay, shadow comparison and the claim that a proof is frozen
evidence. Find the unordered iteration and sort it.

**R4 — A league snapshot instead of a prepared deck.** Hold one immutable in-process
snapshot per league and format: market values, each manager's board-derived values and tier
coordinates, lineup baselines, plan fits, pools. Key it by a compact input-revision vector
(roster revision, board revision per manager, values snapshot id, config hash) that every
writer bumps. A tap then pays only for request-specific work (floor, preferences, pins), and
a roster change invalidates one team's slice. The acceptance audit's cold-path finding
already names the revision vector as the prerequisite; R2 makes the per-tap remainder small
enough for it to matter. Prepared inventories stay as the durable fallback.

**R5 — A calibrated mutual-acceptance score: log first, model later.** The goal stands:
replace hand weights with two fitted heads over the components the proofs already record,
P(viewer likes) and P(counterparty accepts), and order by their product. The
[offline evaluation](acceptance-eval.md) says it cannot be built yet:

- Every labelled card on the bilateral arm comes from 3 people (2 without the tester
  account). Neither head is estimable, and a shadow score would be unevaluable for the same
  reason.
- There are fewer than 5 counterparty responses, all time, and `trade_proposals` has 0 rows
  in production. The counterparty head is a logging and product gap, not a modelling one.
- Within a user, `weaker_support` does not order likes (within-user AUC 0.28–0.39). The one
  consistent signal is the viewer's own market gain (0.58–0.61). This does not condemn the
  weaker-side ordering, which trades viewer appeal for counterparty acceptance that the data
  cannot score, but it does mean the current weights have no outcome evidence behind them.

So the order of work is: (1) record what happens to sent trades at the provider (accepted,
rejected, expired, countered) and counterparty exposure to mirrored cards; (2) log a small
randomised perturbation of first-page order with its probability, so position bias and
selection are correctable; (3) keep the per-side support components in the compact evidence
block; (4) re-run `acceptance_eval` at 10 or more responding users. A shadow head is
warranted when the fitted model beats `weaker_support` on within-user held-out AUC with an
interval above zero. Extend `value_model.py` rather than build a second learner.

**R6 — Model the counterparty as a person, not a mirror.** Two changes to the counterparty
side of the score, each a versioned revision: an endowment premium on assets the counterparty
gives up (scaled down for managers with trade history), and inference for managers with no
board from revealed behaviour (their completed trades, adds/drops, lineup choices) instead of
a neutral 0.5. The [offer history](offer-history.md) gives both effects numbers from one manager's leagues:
offers paying picks for players were accepted 18% of the time and offers asking for picks 7%;
asking for the trade's best asset in exchange for pieces was accepted about half as often as
offering it; and acceptance across league-mates ranged from 0% to 36%. That is evidence for
which effects to build, from one proposer; tuning them still needs R5's outcome data.

**R7 — One evaluator contract, many proposers.** Converge the constructor families on the
split R2 introduces: proposers enumerate and order; one exact evaluator owns gates, price
and evidence. `value_core`'s consensus band and the bilateral focal search then differ only
in how they propose, the bake-off compares proposers on one evidence shape, and a fix to
pricing or gates lands once. Retire the arms the bake-off has already answered.

**R8 — League-level exposure control.** When ranking across many viewers, cap how often one
roster or one asset is the target in first pages across a league-week. The single-deck
diversity rules exist; the cross-user version does not.

## 5. Rollout for what is built

With both flags off nothing changes in serving beyond a one-time rebuild of stored first
pages (the deck pipeline version moved 14 → 15).

1. Merge with both flags off. models-eng reviews the pipeline bump.
2. Turn on `trade.fast_deck_shadow` for a day. Each cold build logs whether the 150-card page
   equals the full solve's and how long each took on Render.
3. If the shadow lines agree, turn on `trade.fast_deck` and run the TestFlight checklist in
   [scope.md](scope.md) §3. Kill = flag off and reload.
4. Scope R3 (append the inventory) and R2b (cheaper revision 2).

## 6. What this review did not do

- It did not change which trades are served or their order. R5/R6 are model changes that need
  outcome data and the repo's blind-grade/shadow process; proposing a fourth unevaluated
  bilateral revision would add to the queue, not shorten it.
- It did not build append-behind-the-page (R3) or the league snapshot (R4). Both cross the
  evidence and currentness contracts that trades-eng owns. Until a flag is turned on, no user
  sees a faster card.
- It read production only to count, to capture recorded requests and for the acceptance
  evaluation, all read-only. No timing here was taken on Render.
- A universal 200 ms on a genuinely cold scope is not shown. On real leagues construction is
  about 0.3–0.55 s under revision 2; it still needs R2b, R4 and a physical-device
  measurement.
- Page-first supports organic and opponent-scoped searches. Pinned and exact-give searches
  return `None` and fall back to the full solve.

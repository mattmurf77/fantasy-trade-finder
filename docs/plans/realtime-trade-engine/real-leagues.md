# The fast deck on real leagues — replay of every recorded request

**Date:** 2026-11-10 · **Source:** production, read-only · **Scope:** aggregates only

The earlier measurements ([scope](scope.md), [scale](scale.md)) used a synthetic league. This
is the same search run on every Find a Trade request production has recorded, compared with
the full engine on the same inputs.

The recorded inputs (rosters, boards, values) and per-request results are kept locally
(`data/prod-requests/`, git-ignored) and are not in the repository.

## What was replayed

- Production has **18 connected leagues**. **13** have at least one recorded owner request
  with a full input snapshot (`bakeoff_runs.config_json.owner_request`). The other 5 were
  last refreshed in April or May 2026, have never been served a card and have nothing to
  replay.
- **247 distinct requests** from those 13 leagues (273 rows read, 24 repeated inputs, 2
  without a full snapshot), from **23 manager-league pairs**, 2026-09 to 2026-11.
- League sizes: 198 requests from 12-team leagues, 45 from 14-team, 4 from 13-team. Rosters
  hold a median of 29 assets and up to 40. 127 requests have no other manager's board, 90
  have six.
- All were organic (none pinned, none opponent-scoped) and were replayed under revision 2
  (`owner-v2-bilateral-2`), the revision live in production, with production's `model_config`.

Each request was rebuilt the way `backend/eval/bilateral_revision_benchmark.py` rebuilds one,
then run through `trade_fast_deck.serve` (150 cards) and the full generator **in the same
process**, with the network blocked.

## Results

**1. The fast deck matched the full engine on every request.** 247 of 247 were served, and
on all 247 the 150 cards were the full solve's first 150: same packages, same order, identical
proof bytes. The first 30 matched on all 247 as well.

**2. It is about ten times faster, not thirty to eighty.** One process, this laptop, with
other test suites running on the machine at the time:

| | 30-card page | 150-card deck | Full solve |
|---|---|---|---|
| Median | 0.28 s | 0.55 s | 5.9 s |
| 90th percentile | 0.38 s | 0.96 s | — |
| Slowest | 0.92 s | 1.6 s | 7.2 s |

(62 requests, every fourth; the full solve on 13 of them.) Across all 247, run six at a time,
the median ratio of full solve to fast deck was 9–10× and the worst tenth 6×.

**3. Construction alone does not reach 200 ms on real leagues under revision 2.** Between 5%
and 32% of the 30-card pages finished inside 200 ms, depending on how busy the machine was;
none of the 150-card decks did.

**4. The cost is revision 2, not real rosters.** The same requests under bilateral-1 took
71 ms for 30 cards and 174 ms for 150. Stage medians for revision 2 at 30 cards: setup 14 ms,
pools 8–48 ms, screen 13 ms, exact verification 160 ms, rank 3 ms. Two things make
verification expensive:

- Revision 2 delays a card behind cheaper alternatives in its families, so an exact page has
  to evaluate those family members too: 227 of 403 exact evaluations at 30 cards, 581 of 935
  at 150.
- Each revision-2 evaluation costs nearly twice a bilateral-1 evaluation, because it audits
  each companion by evaluating the trade without it.

**5. A work limit of 4,000 evaluations was too low for one league.** Four requests from a
sparse 13-team league (370–450 eligible trades in total) needed 4,400–5,000 exact
evaluations for 150 cards and fell back to the full solve. With the fast deck's limit set to
12,000 they finish in 1.0–1.3 s against 4.1–4.5 s and match. The heaviest request that was
served needed 3,288.

**6. The full engine is not repeatable across processes.** The same request gave 2,609 cards
in one process and 2,616 in another, with a different first 150 and different proof bytes,
for both bilateral-1 and revision 2. With Python's hash seed fixed, two processes agree. So
the incumbent's output depends on set iteration order somewhere in construction: a server
restart can reorder a deck for unchanged inputs, and a frozen proof's bytes are reproducible
only within the process that wrote it. This is existing behaviour; the fast deck neither
causes nor fixes it. It is why the comparison above is made in one process, and why
`trade.fast_deck_shadow` compares inside the job. The first replay compared across processes
and showed only 109 of 247 matching, which was this effect.

## Under load

Open-loop arrivals over the latest request of each of the 23 manager-league pairs, 150-card
deck, processes of four threads, 30-second windows. The machine was shared with other test
runs and has few performance cores, so these are pessimistic.

| Processes | Searches/s offered | Median | 95th percentile | Within 1 s |
|---|---|---|---|---|
| 1 | 0.5 | 0.57 s | 1.4 s | 76% |
| 1 | 1 | 0.90 s | 1.9 s | 55% |
| 1 | 1.5 | 1.6 s | 4.1 s | 40% |
| 1 | 2 | 4.8 s | 8.0 s | 5% |
| 4 | 4 | 0.81 s | 2.0 s | 64% |
| 4 | 6 | 1.9 s | 3.8 s | 18% |
| 8 | 8 | 1.2 s | 3.0 s | 34% |
| 8 | 12 | 5.1 s | 9.0 s | 1% |
| 8 | 16.7 | 12.7 s | 18.9 s | 0% |

- One process saturates at about 1.8 searches a second. The full solve's ceiling is about
  0.17 a second (one every 5.9 s), so the gain per process is about tenfold.
- A burst of 100 on one process drained in 51 s; a burst of 1,000 on eight in 96 s.
- 1,000 users each searching once a minute is 16.7 searches a second. Eight processes on
  this machine completed about 10 a second. At 0.55 s of CPU per deck the rate needs roughly
  ten dedicated cores for 150-card decks, or about five for 30-card pages.
- Peak memory per process was 200–390 MB with 23 requests loaded.

## What it means

- **The fast deck is safe to shadow.** It reproduced the full engine on every recorded
  request, and its fallbacks behaved as designed.
- **Expect a cold build to drop from about 6 s of construction to about half a second, not to
  200 ms.** Loading inputs, final checks and evidence are on top of both.
- **The next speed-up is in revision 2 itself.** More than half the exact evaluations are
  family members, and each evaluation carries the companion audit. Making either cheaper
  without changing results is the direct route to 200 ms; bilateral-1's numbers show the
  search is already there when the ranker is simpler.
- **Deck depth is a latency knob.** 30 cards cost about half of 150. The deepest card acted on
  in production since September is index 65.
- **Scale past a few searches a second needs worker processes and CPUs**, as
  [scale.md](scale.md) already concluded; the per-search cost on real leagues is about ten
  times the synthetic figure used there.
- **The process-to-process variation in the full engine deserves its own look.** It makes any
  cross-process comparison of decks or proofs unreliable.

## What this cannot support

- A production latency claim. This is one laptop, construction only, with other work on the
  machine. `trade.fast_deck_shadow` on Render is the measurement that matters.
- Leagues of 16 or more teams, pinned searches or revision 3: none appear in the recorded
  requests, and all three fall back to the full solve.
- The 5 dormant leagues. Nothing was recorded for them.

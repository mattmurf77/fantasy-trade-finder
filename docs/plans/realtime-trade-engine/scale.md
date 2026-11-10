# Scale test — trade construction toward 1,000 concurrent users

**Date:** 2026-11-10 · **Tool:** `backend/eval/first_page_load.py` · **Stretch goal:** 1,000
concurrent users with the first cards inside 200 ms, without pre-generating results.

## What was measured, and what was not

- **Construction only.** Each "search" is one call to `trade_first_page.first_page(k=30)`
  (or the full revision-2 solve, for contrast) on a synthetic 12-team league. A real request
  also loads boards and rosters, runs final checks and commits evidence before a card shows.
  Those are not in these numbers.
- **Open-loop arrivals.** Searches arrive on a schedule whether or not earlier ones finished,
  and latency is measured from the scheduled arrival, so a backlog shows as latency.
- **20 different leagues** (seeds 100–119), picked at random per arrival.
- **This laptop** (Apple M6, 12 cores in three speed classes: 2 fast, 4 medium, 6 slow;
  Python 3.12). Production is one Render `standard` instance: one CPU, one gunicorn process,
  four threads. That CPU is not the laptop's fast core; absolute numbers will be worse there
  and have to be measured there.
- **"1,000 concurrent users"** is modelled two ways: a steady rate (each user searches once a
  minute = 16.7 searches/s; once every 30 s = 33.3/s) and a burst (1,000 searches at once).

## Results: first version against the optimised search

"First" is page-first as first built (about 150 ms of CPU per search). "Optimised" is the
version on this branch (41–46 ms once the process has seen a league, 73–82 ms the first
time). Same machine, same 20 leagues, same arrival schedule.

Production shape: one process, four threads.

| Searches/s offered | Median, first | Median, optimised | p95, first | p95, optimised | Within 200 ms, first | Within 200 ms, optimised |
|---|---|---|---|---|---|---|
| 2 | 201 ms | 91 ms | 432 ms | 154 ms | 50% | 98% |
| 4 | 275 ms | 83 ms | 902 ms | 138 ms | 33% | 99% |
| 6 | 967 ms | 82 ms | 2.9 s | 159 ms | 5% | 98% |
| 8 | 4.8 s | 80 ms | 8.8 s | 193 ms | 1% | 96% |
| 12 | saturated | 93 ms | saturated | 272 ms | — | 86% |
| 16 | saturated | 137 ms | saturated | 468 ms | — | 66% |

One process saturates at **6.3 searches a second (first) and 20.1 (optimised)**: at 24 and 28
a second offered it completes 20.1 and falls behind.

More processes, one thread each:

| Shape | Searches/s offered | Median, first | Median, optimised | p95, first | p95, optimised | Within 200 ms, first | Within 200 ms, optimised |
|---|---|---|---|---|---|---|---|
| 4 processes | 16.7 | 494 ms | 61 ms | 1.0 s | 100 ms | 9% | 100% |
| 8 processes | 16.7 | 247 ms | 63 ms | 347 ms | 108 ms | 18% | 100% |
| 8 processes | 33.3 | 3.3 s | 64 ms | 5.3 s | 114 ms | 0% | 99.9% |

A burst of 1,000 searches at once:

| Shape | Time to clear, first | Time to clear, optimised | Median wait, optimised | p95 wait, optimised |
|---|---|---|---|---|
| 1 process, 4 threads | 157 s | 49 s | 25 s | 47 s |
| 8 processes | 38 s | 12.6 s | 6.8 s | 12.0 s |

The full solve, for contrast (one process, four threads):

| Searches/s offered | Completed/s | Median | p95 | Peak memory |
|---|---|---|---|---|
| 0.2 | 0.19 | 9.6 s | 13.9 s | 1.1 GB |
| 0.5 | 0.27 | 24.9 s | 38.0 s | 1.2 GB |

Per search, page-first peaks at about 16 MB and a process stays near 90–110 MB including
both memos; the full solve peaks at about 252 MB per search, and four overlapping solves took
one process past 1.1 GB.

## What the results say

1. **One process went from 6 to 20 searches a second**, and now holds 96–99% of searches
   inside 200 ms up to 8 a second. The first version missed half of them at 2 a second,
   because one search took about as long as the whole budget.
2. **Threads do not add capacity.** Four threads share one CPU under the interpreter lock:
   they complete the same number of searches as one thread, and each takes longer on the
   wall clock when they overlap. That is why the single-process shape degrades from 12 a
   second upward even though it is not yet saturated.
3. **Processes add capacity with real cores**, and handing a search to another process costs
   about 1 ms (a 49 KB request and a 346 KB result).
4. **1,000 users searching once a minute is met at 200 ms with four worker processes** (p95
   100 ms, every search inside 200 ms), and **once every 30 seconds with eight** (p95 114 ms).
   Neither is met by one process: at 16 a second it holds 66% inside 200 ms.
5. **The full solve cannot serve interactive load at all.** One process completes about one
   every four seconds, and a few overlapping solves exhaust a 2 GB instance.
6. **A burst cannot be absorbed by speed alone.** 1,000 simultaneous searches took 12.6 s to
   clear on eight processes: the first arrivals are fast and the last wait for everyone
   ahead of them. A burst needs a queue with a deadline and shared results for identical
   requests, not a faster search.
7. **"Seen" matters.** The gain is largest once the process memos hold a league's lineups and
   tier coordinates. A cold process, or a league not searched recently, pays 73–82 ms a
   search instead of 41–46 ms. The load test's 20 leagues repeat, so it is mostly the warm
   case; 1,000 users spread over several hundred leagues would sit between the two until
   the memos fill (the lineup memo is capped at about 50,000 entries, roughly 55 different
   managers' searches).

## Structural limits outside construction

Found by reading the serving path, not load-tested:

- **One web process by design.** `server.py` keeps sessions, the trade-job registry and the
  player pools in process memory, so gunicorn runs one worker (`render.yaml`). Every route
  and every search share one CPU.
- **No global cap on concurrent searches.** Each distinct request starts its own background
  thread running `_run_trade_job`; equivalent requests join one job, but nothing bounds how
  many different ones run at once. Under a burst they all compete for the same CPU and each
  holds its memory.
- **Evidence volume.** The bilateral arm has written about 179,000 impression rows for 221
  cards anyone viewed, because a job records its whole inventory
  ([acceptance-eval.md](acceptance-eval.md) §3). At 1,000 users that is a write and storage
  problem independent of CPU.
- **Polling.** Clients poll job status over the same process that is doing the work.

## What it would take

| Step | Effect | Status |
|---|---|---|
| Cut per-search CPU (content-keyed lineup and coordinate memos, serialising only returned cards, cheaper screen, resumable first cards) | 3.2× searches per process; headroom inside 200 ms | **Done on this branch** |
| Run construction in a small pool of worker processes fed by the web process | Capacity scales with cores without breaking the one-web-process rule; ~1 ms hand-off | Recommended; needs a larger instance than one CPU. Each worker keeps its own memos |
| Cap and queue concurrent searches, with a deadline | A burst degrades to waiting, not to memory exhaustion | Recommended |
| Share one result among identical requests (already done for equivalent jobs) and reuse league-level components across league-mates | Bursts inside one league cost far less than N searches | Partly exists; the lineup memo already shares across league-mates; the rest is R4 |
| Publish the page before the inventory, and write evidence for what is shown (R3) | Removes the O(inventory) work and most of the rows | Recommended; unscoped |

Sizing rule of thumb at about 0.05 s of CPU per search: to hold p95 well inside 200 ms plan
for about half utilisation, so cores ≈ 2 × rate × 0.05. That gives about 2 cores for 16.7
searches a second and 3–4 for 33.3, consistent with the four- and eight-process runs above
(on a machine where only six of twelve cores are fast). It excludes everything outside
construction, and Render's CPUs have to be measured, not assumed.

## Reproduce

```bash
python -m backend.eval.first_page_load --rate 4 --duration 30                  # production shape
python -m backend.eval.first_page_load --rate 16.7 --duration 30 --processes 8 --threads 1
python -m backend.eval.first_page_load --burst 1000 --processes 8 --threads 1
python -m backend.eval.first_page_load --mode full --rate 0.2 --duration 30
```

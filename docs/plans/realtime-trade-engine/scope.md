# Feature Scope — Real-time trade engine: page-first search and acceptance evaluation

**Date:** 2026-11-10
**Entry point:** direct operator ask (architecture review of valuation and offer creation;
follow-ups in the same session: offline acceptance evaluation on production data, a scale
test toward 1,000 concurrent users with a 3× per-process target, and an analysis of the
operator's own Sleeper offer history)
**Builder:** one coordinating session with Opus subagents for the page-first search, the
(dropped) fast kernel and the acceptance evaluation
**Operator sign-off on waivers:** pending — §1 and the TestFlight row of §3 are waived
because nothing here is reachable from the app; surfaced in the session summary

Review and recommendation: [recommendation.md](recommendation.md). Research:
[research.md](research.md). Findings: [acceptance-eval.md](acceptance-eval.md),
[offer-history.md](offer-history.md), [scale.md](scale.md).

## 0. What this branch is

| Piece | File | Wired into serving? |
|---|---|---|
| Page-first exact top-K search | `backend/trade_first_page.py` | **No.** Imported only by its tests and the two tools below |
| Benchmark | `backend/eval/first_page_bench.py` | Operator CLI |
| Load test | `backend/eval/first_page_load.py` | Operator CLI |
| Offer-history findings | `docs/plans/realtime-trade-engine/offer-history.md` | Document only; data and scripts are local and git-ignored |
| Synthetic league builder | `backend/eval/synthetic_league.py` | Test and tool input |
| Offline acceptance evaluation | `backend/eval/acceptance_eval.py` | Operator CLI, read-only |

No route, flag, config key, schema, generator or client file changes. The incumbent
constructor modules (`trade_gen_owner.py`, `trade_gen_bilateral.py`,
`trade_gen_bilateral_candidate.py`) are untouched and remain the reference the tests compare
against.

**Not kept:** an exact fast kernel for the full solve (`trade_gen_bilateral_fast.py` with an
`FTF_OWNER_FAST_KERNEL` selector in `bakeoff_runner.py`). It was byte-identical and measured
1.15–1.18× with about 75% more peak memory; see recommendation §4 R1.

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** nothing is user-visible and no code path
  a client can reach changes. The acceptance evaluation reads existing tables and adds no
  event. Its §9 lists logging that R5 would need; that is a recommendation with its own
  tracking-plan addendum when scoped, not part of this change.

## 2. Schema & flag scope

- New/changed tables or columns: none
- New/changed feature flags: none
- New env vars / `model_config` keys: none

## 3. Evidence scope

- [ ] **Structural guard:** n/a — backend only.
- [x] **Unit tests:**
  - `backend/tests/test_trade_first_page.py` — 129 tests: bilateral-1 first page identical to
    the full generator's first k (12 variants × crown flag × four k values, plus two
    production-sized seeds); revision-2 proofs byte-identical and the page equal to the
    re-ranked top-(k+31) prefix; exhaustive admissibility audit of all three bound levels for
    both generators; price-envelope property test (3,000 packages); unsupported requests,
    cancellation, verification cap, tiny and empty leagues; the verified stop prefix against
    the full generator; every returned proof against the full generator's bytes; both
    process memos (key completeness, eviction, detachment, 4-thread concurrency); and
    resumable takes.
  - `backend/tests/test_first_page_load.py` — 3 tests: the load tool completes and reports
    every scheduled arrival.
  - `backend/tests/test_acceptance_eval.py` — 16 tests: fitter against known coefficients and
    a closed form; grouped folds never share a group; small-cell suppression; inline and
    packed evidence; the identifier guard; insufficient-data verdicts.
  - Named sabotages that turn them red are listed in TEST_LEDGER.
- [x] **Code-walk proof:** the admissibility argument is the module docstring of
  `backend/trade_first_page.py`, checked against `trade_service._package_value_market`
  (`backend/trade_service.py:1798`) for the price envelope and against
  `bilateral._Search._owner` (`backend/trade_gen_bilateral.py:168`) for the support terms.
- [x] **Manual TestFlight checklist — WAIVED because:** no client-reachable behaviour changes.
- `testID`s added/renamed: none

### Measured (this laptop, Python 3.12, `synthetic_league.build`, 12 teams, k = 30)

| Seed | Full solve | First page, first time | First page, league seen | First 5, league seen | Exactly verified | Same 30 cards, same order |
|---|---|---|---|---|---|---|
| 7 | 3.57 s | 81 ms | 46 ms | 34 ms | 139 of 45,056 | yes |
| 11 | 3.9 s | 81 ms | 46 ms | 35 ms | 125 of 45,056 | yes |
| 23 | 3.8 s | 79 ms | 45 ms | 33 ms | 123 of 45,056 | yes |
| 100 | 3.07 s | 73 ms | 41 ms | 31 ms | 101 of 45,056 | yes |

Seeds 7 and 100 are the coordinating session's own runs; 11 and 23 are the building agent's.
All are revision 2. Stage breakdown once the league has been seen (seed 7): search setup
7 ms, pools 4 ms, bound screen 9 ms, exact verification 23 ms, rank 3 ms. Peak memory per
search is about 16 MB against about 252 MB for the full solve.

How it got there, per search on the same leagues: first version about 150 ms; round 1
(content-keyed lineup memo, decode-once, tighter price envelope, resumable takes) 54–59 ms;
round 2 (deferred serialisation, flat heap entries, cheaper memo keys, coordinate memo)
41–46 ms. Under load one process went from 6.3 to 15.0 to 20.1 searches a second
([scale.md](scale.md)).

Limits of this evidence:

- Synthetic leagues, not production requests. The bench accepts captured requests; that run
  is the first rollout step. The synthetic league has no FLEX slots, the easy case for
  lineup assignment.
- Construction only. Loading inputs, final checks and evidence commits are outside it.
- "League seen" means the two process memos already hold that league's lineups and tier
  coordinates. A cold process, or a league not seen recently, pays the first-time figure.
- Revision 2 has one documented difference from the full generator: its same-focal term
  precedence sees only the verified prefix. On small synthetic worlds two of fourteen
  k = 30 comparisons differed by one card (29 of 30), and a later, larger `take` can reorder
  an earlier one (reported as `prefix_stable: false`).
- The price envelope is proved from the current market pricing code. A change to
  `trade_service` package pricing must re-run `test_trade_first_page.py`; outside its proven
  config range the envelope switches itself off and every candidate is priced.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added or changed |
| `living-memory/LLD.md` | n/a | no schema, route or invariant convention changed |
| `docs/architecture.md` | updated | "Page-first trade search (library, not wired)" |
| `living-memory/HLD.md` | n/a | no serving flow changed; the module is not on a request path |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md` | updated | page-first search; admissible bound |
| ADR or `DECISIONS.md` entry | updated | ADR-028; DECISIONS entry |
| `backend/CLAUDE.md` | updated | eval tools list |
| `docs/plans/README.md` | updated | row for this folder |

## 5. Ship gate declaration

- **CI green:** `backend-tests` on the pushed sha; `mobile-typecheck` and
  `maestro-testid-lint` are unaffected (no mobile file changes).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-11-10.
- **TestFlight verification:** none owed.
- Express lane declared by the operator? No.

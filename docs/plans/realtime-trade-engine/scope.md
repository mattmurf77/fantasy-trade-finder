# Feature Scope — Real-time trade engine: page-first search, fast deck and acceptance evaluation

**Date:** 2026-11-10
**Entry point:** direct operator ask (architecture review of valuation and offer creation;
follow-ups in the same session: offline acceptance evaluation on production data, a scale
test toward 1,000 concurrent users with a 3× per-process target, an analysis of the
operator's own Sleeper offer history, "make the necessary pushes and code changes to enable
the fast trade suggestions", and "run a larger scale test on the fast path with all connected
leagues")
**Builder:** one coordinating session with Opus subagents for the page-first search, its
revision-2 exactness, the (dropped) fast kernel and the acceptance evaluation
**Operator sign-off on waivers:** pending — §1 is waived (no new event); surfaced in the
session summary. The deck-depth trade-off in §0 is an operator decision, not a waiver.

Review and recommendation: [recommendation.md](recommendation.md). Research:
[research.md](research.md). Findings: [acceptance-eval.md](acceptance-eval.md),
[offer-history.md](offer-history.md) (review page: [sleeper-review.html](sleeper-review.html)),
[scale.md](scale.md), [real-leagues.md](real-leagues.md).

## 0. What this branch is

| Piece | File | Wired into serving? |
|---|---|---|
| Page-first exact top-K search | `backend/trade_first_page.py` | Through the fast deck only |
| Fast deck (serve and shadow) | `backend/trade_fast_deck.py`, hook in `server._run_trade_job` | **Yes, behind two flags that ship off** |
| Benchmark | `backend/eval/first_page_bench.py` | Operator CLI |
| Load test | `backend/eval/first_page_load.py` | Operator CLI |
| Synthetic league builder | `backend/eval/synthetic_league.py` | Test and tool input |
| Offline acceptance evaluation | `backend/eval/acceptance_eval.py` | Operator CLI, read-only |
| Offer-history findings and review page | `offer-history.md`, `sleeper-review.html` | Documents only; data and scripts are local and git-ignored |
| Real-league replay findings | `real-leagues.md` | Document only; recorded requests are local and git-ignored |

**What a user sees with `trade.fast_deck` on.** A cold Find a Trade build asks the page-first
search for the proven first 150 cards and publishes those through the unchanged final checks,
instead of building the whole inventory first. The cards, their order and their proofs are the
full engine's first 150 (§3). **The deck then ends at 150 cards.** Today a deck holds a median
of 316 cards and up to 3,991. In production from 2026-09-01 to 2026-11-10 the deepest card
anyone acted on was index 65 (31 decks with a decision, 50 with an outcome), so 150 covers
every observed session about twice over. Building the tail behind the page is a separate
change (recommendation R3).

**Scope of the flag.** Interactive owner-serve jobs only (no job `source`, not a preparation
run). Prepared inventories, the weekly replenishment and Calibration's refresh keep the full
solve. The full solve also runs when the selected generator has no parity suite (`owner_v1`,
bilateral revision 3), for pinned and exact-give requests, when the page cannot be proven
within 12,000 exact evaluations, when the incumbent's stream budgets would bind (roughly, leagues of
16 or more teams), and on any error.

The incumbent constructor modules (`trade_gen_owner.py`, `trade_gen_bilateral.py`,
`trade_gen_bilateral_candidate.py`) are untouched and remain the reference the tests compare
against.

**Not kept:** an exact fast kernel for the full solve (`trade_gen_bilateral_fast.py` with an
`FTF_OWNER_FAST_KERNEL` selector in `bakeoff_runner.py`). It was byte-identical and measured
1.15–1.18× with about 75% more peak memory; see recommendation §4 R1.

## 1. Analytics scope

- [x] **(c) WAIVED — no new event because:** the fast deck changes how a deck is built, not
  what a client does. Attribution needs no event: every impression's frozen
  `owner_generation` diagnostics carry `page_first_version`, `k`, `verified` and the stage
  timings, and the `bakeoff_runs` row carries the same report, so a fast deck is separable
  from a full one in existing evidence. `trades_generated.props.gen_ms` already measures the
  whole worker and is the before/after latency read. The acceptance evaluation's §9 lists the
  logging R5 would need; that is its own tracking-plan addendum when scoped.

## 2. Schema & flag scope

- New/changed tables or columns: none
- New feature flags: `trade.fast_deck`, `trade.fast_deck_shadow`, both default false in code
  and in `config/features.json` ([config reference](../../config-reference.md))
- New env vars / `model_config` keys: none. The deck size (150) and the work limit (12,000)
  are constants in `backend/trade_fast_deck.py`.
- `DECK_PIPELINE_VERSION` 15 → 16: `_run_trade_job` gained the hook, so stored first pages
  rebuild once after deploy, as on every pipeline bump. `trade_first_page.py` and
  `trade_fast_deck.py` join `_ENGINE_CODE_MODULES`, the stored-page engine hash.
  **models-eng review of the bump is owed** (the guard's standing rule).

## 3. Evidence scope

- [ ] **Structural guard:** n/a — backend only.
- [x] **Unit and worker tests:**
  - `backend/tests/test_trade_first_page.py` — 172 tests: the first page equals the full
    solve's first k (identities, order, proof bytes) for BOTH generators on seeds 1–12 of a
    small league plus outlook, floor, size and ranked-opponent variations at k = 5, 30, 60,
    150, and for revision 2 on three production-sized builds; family members priced as their
    proofs; a cap inside family completion reports incomplete; exhaustive admissibility audit
    of all three bound levels; price-envelope property test; unsupported requests,
    cancellation, tiny and empty leagues; both process memos; resumable takes that extend.
  - `backend/tests/test_trade_fast_deck.py` — 27 tests. Helper: serve equals the full solve's
    first k; declines unsupported generators, pinned requests, unproven and budget-bound
    pages; shadow reports agreement and the first divergence; the currentness check is
    forwarded. Worker, on the owner route harness with production's shape (owner-only,
    revision 2): both flags off never import the module; serve on publishes the page with
    attributed evidence on every impression; an unavailable or failing fast deck serves the
    full solve; background sources keep the full solve; shadow serves the full solve and logs
    one comparison; a cancellation inside the fast deck cancels the job.
  - `backend/tests/test_first_page_load.py` — 3 tests; `backend/tests/test_acceptance_eval.py`
    — 16 tests.
  - Named sabotages that turn them red are listed in TEST_LEDGER.
- [x] **Replay on recorded production requests:** every recorded request with a full input
  snapshot, 247 distinct requests from the 13 leagues that have ever searched (23
  manager-league pairs). The fast deck was served on 247 of 247 and equalled the full solve's
  first 150 cards, in order, with identical proof bytes, on all 247.
  [real-leagues.md](real-leagues.md).
- [x] **Code-walk proof:** the bound and stop argument, and the revision-2 argument (horizon,
  family completion, merge induction), are the module docstring of
  `backend/trade_first_page.py`. The hook is `server._run_trade_job`'s `_gen_owner`: the
  flags and job source are read once per job; with both flags off the only change is that
  the generator is bound to a local before the same call.
- [ ] **Manual TestFlight checklist — owed when `trade.fast_deck` is turned on:**
  1. Force a cold build: change your team outlook in a league, then tap Find a Trade. Time
     tap to first card. Before: about 9 s. Expect a clear drop; record the number.
  2. Swipe past card 30: the next batch arrives with no repeated card.
  3. Keep swiping to the end: the deck ends at card 150 with the normal end-of-deck state,
     not an error or a spinner.
  4. Like one card and send one trade from the deck: both appear in Matches/pending as
     before.
  5. Run a pinned search (one specific player): results still appear. This path uses the
     full engine and should feel as it did.
  6. In Render logs, each cold organic build shows one `fast deck: served cards=…` line; a
     pinned search shows `fast deck: full_solve`.
  7. Kill switch: set the flag false, reload flags, repeat step 1; no `fast deck` line
     appears.
- `testID`s added/renamed: none

### Measured

Synthetic 12-team league, this laptop, k = 30, revision 2: about 110–130 ms the first time
and 70–90 ms once the league has been seen, against 3.3–3.8 s for the full solve.
Bilateral-1: 81–84 ms and 44–45 ms. Before revision 2 was made exact the same search took
46 ms; the difference is the family completion that exactness needs.

Recorded production requests, this laptop, revision 2, one process, other work running on the
machine ([real-leagues.md](real-leagues.md)):

| | 30 cards | 150 cards (the fast deck) | Full solve |
|---|---|---|---|
| Median | 0.28 s | 0.55 s | 5.9 s |
| 90th percentile | 0.38 s | 0.96 s | 7.2 s (max of 13) |

Limits of this evidence:

- Construction only. Loading inputs, final checks and evidence commits are outside it, and
  Render's CPU is slower than this laptop.
- The recorded requests are frozen inputs replayed offline; the persisted player projection
  omits some live pick metadata, so a replay is production-shaped, not a byte-exact
  re-run of the original job.
- The comparison is made inside one process. The full engine's own output varies between
  processes (Python's per-process hash seed): the same request gave 2,609 cards in one
  process and 2,616 in another. That is existing behaviour, recorded in real-leagues.md.
- Revision-2 exactness is proven given two properties that are tested, not proven: the
  page-first universe equals the full solve's when budgets do not bind, and a card's market
  loss recomputed from its pricing call equals the proof's within 1e-9.
- The price envelope is proved from the current market pricing code. A change to
  `trade_service` package pricing must re-run `test_trade_first_page.py`; outside its proven
  config range the envelope switches itself off and every candidate is priced.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added or changed; payload shape unchanged |
| `docs/config-reference.md` | updated | "Flags — Fast deck (ADR-028)" |
| `docs/data-dictionary.md` | updated | `trade_page_store.engine_version`: the two new hashed modules |
| `living-memory/LLD.md` | updated | deck pipeline 16 and the fast-deck hook |
| `docs/architecture.md` | updated | "Page-first trade search and the fast deck" |
| `living-memory/HLD.md` | updated | the cold path's flagged branch |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md` | updated | page-first search; admissible bound; fast deck |
| ADR or `DECISIONS.md` entry | updated | ADR-028; DECISIONS entries |
| `backend/CLAUDE.md` | updated | module map; eval tools list |
| `docs/plans/README.md` | updated | row for this folder |

## 5. Ship gate declaration

- **CI green:** `backend-tests` on the pushed sha; `mobile-typecheck` and
  `maestro-testid-lint` are unaffected (no mobile file changes).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`, 2026-11-10.
- **TestFlight verification:** owed by the operator when the flag is turned on (§3).
- **models-eng review of the pipeline bump:** owed.
- Express lane declared by the operator? No.

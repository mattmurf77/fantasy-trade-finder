# Feature Scope — arm C (`gen_v2`) per-stage kill counts

**Date:** 2026-08-19
**Entry point:** direct ask — "arm C has never served a single card; find out why it forfeits and fix it"
**Builder:** session 9a7e628e, branch `fix/armc-gen-v2-forfeits`
**Operator sign-off on waivers:** not needed (no waivers)

---

## 0. What this change is, and what it deliberately is NOT

Arm C recorded `cards=0, forfeits=9` against arm `current`'s `cards=40` in
production, and no impression has ever carried `model_arm = 'gen_v2'`. The
investigation (evidence in §3) found **no bug in `trade_gen_v2.py`**: arm C
is divergence-only by design and the leagues it produced nothing in have no
boarded opponent to diverge from. So this change is **instrumentation, not a
behaviour change** — it makes the difference between "starved" and "gated"
queryable, because `cards: 0` alone had already been misread once as a broken
generator.

**No generation behaviour changes.** No gate, threshold, pool size, ordering
rule or `gen2_*` knob is touched; `_pair_survivors` returns the same
candidates for the same inputs, and the two starvation exits it now counts
were already `return []`. `bakeoff_serve_interleaved` stays at its default
`0.0` (dark) — re-lighting serving is the operator's call, and it is the
*only* thing that would let an arm-C card reach a user.

One real accounting bug IS fixed: `BakeoffRun.run_row` looked forfeits up by
ARM name against a dict keyed by GROUP, so arm `current` — whose groups are
`current_divergence` + `current_consensus` — recorded a flat `0` in every run
ever logged, while arm C's single-group key happened to match. The published
"`current` forfeits=0 / `gen_v2` forfeits=9" contrast was therefore partly an
artefact of key spelling.

## 1. Analytics scope

- [x] **(b) Existing events cover it.** No new analytics event and no new
  client emission. The surface is the existing `bakeoff_runs.arms_json`
  column, which gains a per-arm `diagnostics` object. `deck_impressions` is
  untouched. The taxonomy (`backend/analytics_taxonomy.py`) is not involved —
  bake-off run rows are backend telemetry, never `user_events`.

## 2. Schema & flag scope

- New/changed tables or columns: **none.** `bakeoff_runs.arms_json` is
  free-form JSON text; its documented shape gains a `diagnostics` key →
  `docs/data-dictionary.md` updated (§`bakeoff_runs`). No migration.
- New/changed feature flags: **none.** The whole surface is already inside
  `trade.bakeoff` (default OFF); flag off ⇒ `bakeoff_runner` is never
  imported and nothing here executes.
- New env vars / `model_config` keys: **none.** No knob added deliberately —
  a diagnostic that can be switched off is a diagnostic that will be off when
  it is needed. Rollback lever is the existing `trade.bakeoff` flag.

## 3. Evidence scope

- [x] **Unit tests (backend pytest):**
  - `backend/tests/test_trade_gen_v2.py` — 5 new tests pinning each
    starvation mode to a distinct stage (`no_boarded_opponents`,
    `no_board_overlap`, `no_divergence`), pinning the GATED case to
    `starvation_reason is None` with the ε-gate owning the kills, and
    pinning the `kill_counts()` key set + order as a contract.
  - `backend/tests/test_bakeoff_serving.py` — 3 new tests: the forfeit
    sum-over-groups fix (asserting arm `current` no longer reports 0 when
    its groups forfeited), arm-C diagnostics reaching `arms_json` with the
    starving stage named, and the drain-on-read semantics that stop one
    run's counters leaking into the next.
- [x] **Code-walk proof (production, real data):** read-only against
  `DATABASE_URL_PROD`, `SET TRANSACTION READ ONLY`, SELECT only.

  | Claim | Evidence |
  |---|---|
  | Arm C's empty runs are LEAGUE-determined, not time-determined | All 18 `bakeoff_runs` rows: `cards=0` occurs **only** for `league_id` `62846` and `11896`; `league_id 1312140920132497408` returned 6–16 cards in all 11 of its runs, including the two runs cited as "improvement over the night" (06:39:59 and 06:41 — different league from the 05:33 run, not a different outcome in the same one) |
  | Those leagues have no boarded opponent | `member_rankings` grouped by league: `62846` has **zero** rows; `11896` has 1,286 rows for exactly one user — `313560442465169408`, the requester himself. `1312140920132497408` has 4,416 rows across 6 users |
  | The empty runs exit before enumerating anything | `arms_json.gen_v2.gen_ms = 3` in league 62846 vs `221` in league 1312… — the signature of `generate_league_suggestions` returning at the `boarded` loop, `backend/trade_gen_v2.py:848-853` |
  | The design intends this | `backend/trade_gen_v2.py:844-847` ("Divergence needs two REAL boards — unranked opponents are out of scope for this engine"); `config/features.json` `_comment_trade_gen_v2`. Arm C is **not** stricter than the engine arms' divergence path — same `member.has_rankings and member.elo_ratings` predicate as `backend/trade_service.py:4105` |
  | Zero `gen_v2` impressions is serving, not generation | `select distinct served_arm from bakeoff_runs` → `{'current'}` only, i.e. `bakeoff_serve_interleaved = 0.0` (dark). `backend/server.py:3950` stamps `model_arm` from `bakeoff_run.attribution_for(card)` over the SERVED deck; in dark mode the served deck is arm `current`'s, so `model_arm` can only ever be `'current'` or NULL. Arm C contributed 6 of 6 composed cards to the *interleaved* deck in the latest league-1312… run (`groups_json.gen_v2.served = 6`) — it is producing servable cards already, they are simply not served |
  | **Divergence supply is real but entirely concentrated in the boarded league** | `deck_impressions` basis joined to per-league board counts: `1312140920132497408` (6 boards) = 1,196 divergence / 2,911 consensus; `1312583962966650880` (2 boards) = 39 / 395; **`62846` (0 boards), `11896` (1 board = the requester), `1312076055586050048` (1), `1312146456701829120` (1) = ZERO divergence impressions, ever.** 96.8 % of all-time divergence (1,196/1,235) comes from the one league with ≥3 boards. So the all-time 15.2 % divergence rate is real *in aggregate* and is **not** evidence that arm C had supply: there is no league in production where divergence exists and arm C produced nothing |
  | **The control: arm `current` is equally divergence-silent in the same leagues** | Per-run `groups_json[...].pool` sizes. In `62846`/`11896` the `current_divergence` group pool is **0 in all six runs** — exactly like arm C. In `1312…497408` arm C's pool is 6–16 (median 7) against `current_divergence`'s 0–7 (median **1**), and arm `current` produced **zero** divergence cards in 8 of those 11 runs while arm C produced 6–8. Arm C out-produces arm `current` on the divergence axis in 11 of 11 runs. A defect in arm C's pipeline cannot explain a zero that arm `current` reproduces on the same input while arm C simultaneously beats it wherever input exists |
  | The forfeit key mismatch is real | `groups_json` keys are `current_divergence`, `current_consensus`, `gen_v2`; `run_row` read `self.draft.forfeits.get(arm, 0)`, so `current` missed in all 18 rows |

- [x] **Local reproduction against real-shaped inputs:** all four shapes
  (boarded + divergent / no boarded opponent / boarded but zero divergence /
  boarded but no board overlap) reproduced on the `_base_pair` fixture. Under
  the OLD counters, three of the four were byte-identical all-zero reports —
  that indistinguishability is the defect being fixed.
- [x] **WAIVED — structural guard, TestFlight checklist, testIDs:** no mobile
  or web surface. This is backend telemetry inside a default-OFF flag, with
  zero user-visible behaviour; there is nothing a device could show that the
  unit tests do not.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added, renamed, removed or contract-changed. `bakeoff_runner` is invoked inside the existing deck job; no endpoint sees a different request or response |
| `living-memory/LLD.md` | updated | Bake-off telemetry conventions — the per-stage `diagnostics` object and the forfeits-are-per-group rule |
| `docs/architecture.md` | n/a | No module wiring or data-flow change. `gen_v2_cards` already called `generate_league_suggestions` and already received the report; it now keeps it instead of discarding it |
| `living-memory/HLD.md` | n/a | No new module, client or flow; no architectural shift |
| `docs/cross-client-invariants.md` | n/a | Nothing shared with a client. `diagnostics` is server-side telemetry; no client reads `bakeoff_runs` |
| `docs/glossary.md` | updated | New entry **Starvation vs gating (arm C)**; **Forfeit (bake-off)** amended with the per-group sum |
| `docs/data-dictionary.md` | updated | `bakeoff_runs.arms_json` — the `diagnostics` key and its full counter list |
| ADR / `DECISIONS.md` | updated | **D-087** — record the stage, not the count: starvation and gating are different findings |

## 5. Ship gate declaration

- **CI green:** `pytest backend/tests` — **3449 passed, 1 skipped** (baseline
  on `a130dfc` was 3441 passed, 1 skipped; +8 = the 8 new tests). `tsc
  --noEmit` and `testid-lint` unaffected — no TS or mobile file touched.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md`.
- **TestFlight verification:** not applicable — no checklist written in §3,
  no user-visible surface.
- Express lane declared by the operator? **no** — full gates.

## 6. What this does NOT resolve (handed to the operator)

0. **Arm C is not the weak arm — it is the strongest divergence generator in
   the bake-off, and nothing has ever let it reach a user.** Where divergence
   supply exists it beats arm `current` on that axis in every run (median pool
   7 vs 1; arm `current` produced no divergence at all in 8 of 11 runs).
   Its `cards=0` runs are leagues with no boarded opponent, where arm
   `current` is equally divergence-silent and covers the deck from its
   consensus fallback — the path arm C deliberately does not have.

1. **Arm C still cannot reach a user.** `bakeoff_serve_interleaved` is `0.0`
   by design and re-lighting it is the operator's decision. Until it is `1.0`
   no `deck_impressions` row can carry `model_arm = 'gen_v2'`, no matter how
   many cards arm C generates.
2. **Arm C can only be evaluated where boards exist.** Today that is one
   league, `1312140920132497408` (6 boarded users). Every other league in
   production has ≤1 board, and in those arm C is correctly, by design, silent.
   Board supply is the binding constraint on this experiment, not model quality.
3. **The engine arms report no stages.** `diagnostics` is `{}` for `baseline`
   and `current`; `TradeService.presentment_kill_counts()` already exists and
   could fill it, but it accumulates across a job and would need a per-arm
   reset inside the fan-out. Left alone deliberately: that edit sits in the
   engine-arm path, which a concurrent session is editing.

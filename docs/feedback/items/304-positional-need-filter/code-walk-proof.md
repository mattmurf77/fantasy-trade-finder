# CW-1 — Code-walk proof: presentment-rule gate coverage per generator path

> Build-phase deliverable (D-056; prd.md §3.3). Every generation path is
> traced to exactly its stated gate set. Cites are against branch
> `feat/fb304-presentment` at the build commit (symbol + line; symbols are
> the contract, numbers a courtesy — lld §7 convention). Predicates:
> `overpay_ok` (R1 #340, `trade_service.py:1157`), `pos_net_ok` (R2 #341,
> `:1179`), `pick_gap_ok` (R3 #339, `:1204`), `need_gate_ok` (R5 #304,
> `:1238`). The bound per-job hook `_presentment_ok` is built once per
> `_generate_trades_v2` call at `trade_service.py:3509-3556` (flag check at
> `:3510` via the §"G6 presentment rules" block; `None` when
> `trade.presentment_rules` is off ⇒ every hook below is a no-op and R-8
> byte-identity holds — pinned by
> `test_r8_flag_off_predicates_never_run_and_cards_serve`).

| # | Path | Gate set | Evidence |
|---|---|---|---|
| 1 | **v3 organic** — `generate_pair_trades_v3` (`trade_optimizer.py:193`) | R1/R2/R3 (+R5 unless bypassed) at construction | kwarg `presentment_ok_fn` (`:222`); hook at `trade_optimizer.py:540-546` — immediately after the `filler_ok` gate and **before** `_both_feasible`/surplus/fairness, so a killed shape can never reach the near-miss collection (`:553-557`) and be sweetener-rescued (mirrors the #227 placement note). Threaded from the call site `trade_service.py:3623`. |
| 2 | **v3 sweetener** — `_try_sweeten` (`trade_optimizer.py:656`), called at `:629-638` | re-validation of the SWEETENED combo (R-6: a sweetener changes both `net_P` and the gap) | `presentment_ok_fn` passed through at `:637`; sweetened-combo check at `:699-703` (after the #141 `filler_ok_fn` check). Proven by `test_r2_sweetener_revalidation` + sabotage S-R2-5. |
| 3 | **v2 pair** — `_generate_for_pair_v2` (`trade_service.py:3822`), inner `_consider` | R1/R2/R3 (+R5 unless bypassed) at construction | kwarg at `:3846`; hook at `:4061-4067` — after its `filler_ok`, before the surplus/fairness math (same slot as v3). Threaded at `:3649`. |
| 4 | **consensus** — `_generate_consensus_for_pair` (`trade_service.py:4254`), inner `_emit` | R1/R2/R3 (+R5 unless bypassed) at construction | kwarg at `:4278`; hook at `:4394-4398`, inside the #108/#227/#141 gate block before the fairness check. Threaded via `_consensus_kw` at `:3588` — covers both the never-ranked path and the `trade.divergence_fallback` zero-card fall-through. |
| 5 | **relaxed pass** — `_relaxed_targeted_pass` (`trade_service.py:2903`) | identical to paths 1/3/4 — Part 1 + R5 NEVER relaxed | re-runs `_generate_trades_v2` with the same `_v2_kwargs` (incl. `bypass_need_gate`), so the hooks rebuild; its stage overrides (`:2934-2941`) touch only `fairness_floor_divergence` / `min_side_surplus*` — no presentment knob. NEVER-relaxed list updated in the docstring (`:2916-2924`). Proven by `test_r7_relaxed_pass_never_relaxes_r1` + sabotage S-R7. |
| 6 | **R4 dedup** — `_dedup_and_sort` (`trade_service.py:2866`) | R4 #336 windowless exclusion + existing 7-day past-decision filter | filters `self._past_decision_keys` then `self._exclusion_keys` (`:2874-2886`); called from the legacy loop, the v2 loop's streaming snapshots (`on_opponent_done`) and final sort — so R4 binds on streaming snapshots too (`test_r4_engine_exclusion_and_streaming_snapshot`). Exclusion set is overwrite-per-call (`:2682`, round-1 N3; `test_r4_engine_overwrite_per_call_two_league`). |
| 7 | **likes-you injection** — `_inject_likes_you_cards_impl` (`server.py:2881`) | R4 dedup ONLY (Q-G6-1); R1/R2/R3/R5 exempt (Q21); D-055 `likes_you_min_user_delta` floor unchanged | exclusion skip at `server.py:2970-2979`, alongside the existing `_past_decision_keys` skip; the D-055 floor check below it is untouched. Proven by `test_r4_injector_dedup_and_quality_carveout` (carve-out half: an R1-shaped above-floor like still injects). |
| 8 | **trade_gen.v2 (dark)** — `_generate_trades_impl` gen-v2 branch | R4 only, via the shared `past_decision_keys` kwarg (lld §1 generator-scope amendment); R1/R2/R3/R5 deliberately NOT inherited (gen-v2 carries its own gate stack; #341 port deferred to its lighting checklist) | `past_decision_keys=self._past_decision_keys \| self._exclusion_keys` at `trade_service.py:2722-2728`. |
| 9 | **Out of scope (unhooked, verified)** — asset-ideas (`_generate_asset_ideas_impl`), manual calculator, eveners | none | no `presentment_ok_fn` reference in those regions (`git grep presentment_ok_fn` returns only the sites above); eveners add to the *lighter* side by construction so the R3 shape is impossible (lld §3). |

## Server-side wiring (R-5b, R4 construction, R-9)

- **Bypass derivation** — `_presentment_need_gate_bypass` (`server.py:4921`),
  called in `_run_trade_job` at `:5084-5085` from the four job fields only
  (`pinned_give`, `pinned_receive`, `opponent_user_id`, resolved
  `acquire_positions` league pref); threaded at `:5226`. Never reads the
  request body (`test_r5b_run_trade_job_wiring` pins the wiring;
  `test_r5b_server_bypass_derivation` pins the field list, including that
  `trade_away_positions` is not even an input).
- **Exclusion set** — `_load_presentment_exclusions` (`server.py:4941`),
  built once per job at `:5087-5088` behind the flag, from
  `load_awaiting_trades` (windowless, league-filtered; retracted likes and
  matured matches already excluded upstream — `database.py` #318) +
  `load_matches_for_exclusion` (`database.py`, `status IN
  ('pending','accepted')`, both orientations, `declined` never blocks —
  Q-G6-2). Passed to `generate_trades` at `:5227` and the injector at
  `:5270`.
- **Counters + tripwire** — `_log_presentment_outcome` (`server.py:4971`),
  called at `:5537-5539` AFTER the ghost split, so `served` is the
  post-ghost count (lld §5 amendment: ghost-withheld cards pass the rules
  before withholding and feed neither tripwire term). Attributable form
  `served < 5 and served + Σkills(R1,R2,R3,R5) > 15` (round-1 N2);
  `presentment-tripwire` grep prefix documented in docs/runbook.md.

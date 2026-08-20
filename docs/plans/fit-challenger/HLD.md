# HLD — Fit challenger build (arm `fit` + serving re-light + measurement rail)

**Date:** 2026-08-20
**Status:** architecture layer between [PLAN-v2.md](PLAN-v2.md) (authoritative; §1 rulings
R-1..R-12 binding) and the file/function-level LLD that follows. Product spec:
[PRD.md](PRD.md) (§3 knockouts operator-CLOSED). Concerns C1–C7 and traps T1–T4:
[../../reviews/2026-08-20-fit-challenger-review.md](../../reviews/2026-08-20-fit-challenger-review.md).
**Rule of citation:** every integration claim below names a real symbol with file:line
against this checkout. Where code contradicts the plan, the contradiction is recorded in
§10 (Findings for the LLD), never silently adapted around.

---

## 1. System context

The bake-off fan-out already exists and already carries a sibling-generator precedent. One
job thread (`server._run_trade_job`, `backend/server.py:5402`) decides per deck whether the
bake-off applies (`bakeoff_active`, `backend/bakeoff_runner.py:360` — organic, unpinned,
non-demo decks only), then calls `run_bakeoff` (`bakeoff_runner.py:1322`), which runs every
ROSTERED arm sequentially on that thread, composes groups, drafts a deck, and returns a
`BakeoffRun` whose `run_row()` (`bakeoff_runner.py:1056`) becomes the `bakeoff_runs` row
(`backend/database.py:710`) and whose attribution stamps `deck_impressions`
(`server.py:4241–4272`).

Arm C (`gen_v2`) is the pattern the fit arm copies: a standalone generator module
(`backend/trade_gen_v2.py`) that the organic path never imports on the bake-off's account,
called DIRECTLY by an adapter in the runner (`gen_v2_cards`, `bakeoff_runner.py:1133`)
that mirrors the engine path's kwargs and re-applies the post-generation treatment
(intent filter, headliner cap, lane label) so every arm is compared on the same brief.

This build adds, in three lanes:

- **F-lane:** `backend/trade_gen_fit.py` (new module, PRD §3–§6), its runner adapter and
  roster entry (`bakeoff_include_fit`, F5), and the serve-bit (`bakeoff_serve_fit`, F5b)
  that lets fit generate + log while being excluded from the draft.
- **M-lane:** the measurement rail — `model_config_changes` table + `model_config.updated_at`
  (M1), `scripts/set_knob.py` (M1), `scripts/bakeoff_readout.sql` (M2), tripwire queries
  (M4), tester protocol doc (M5).
- **M3:** a generation-time diagnostic fit-score stamp (`features_json.fit_diag`) on every
  bake-off card, ALL arms, so the R-11 bucket-matched readout is possible.

### 1.1 Data-flow diagram

```
 _run_trade_job (server.py:5402)  [one daemon thread per job]
    │
    │ bakeoff_active? (runner:360)  ── no ──► organic generate_trades()  (fit NEVER imported)
    ▼ yes
 run_bakeoff (runner:1322)                       roster = arm_roster() (runner:247)
    │                                            + fit iff bakeoff_include_fit=1  [F5]
    │  for arm in GENERATION_ORDER ∩ roster (runner:1362; fit appended LAST):
    │    ┌──────────────────────────────────────────────────────────────┐
    │    │ current    → generate(**kw)          (arm B, streams progress)│
    │    │ challenger → model_challenger(): generate(**kw)               │
    │    │ gen_v2     → gen_v2_cards(ts, kw)    (runner:1133)            │
    │    │ fit        → gen_fit_cards(ts, kw)   [NEW, mirrors gen_v2]    │
    │    │              └─► trade_gen_fit.generate_league_suggestions    │
    │    │                    pool builder → enumerator → K-chain        │
    │    │                    → dual scorer → ranker → post-score filters│
    │    │                    → (cards, report)                          │
    │    │ try/except per arm (runner:1400): error recorded, never fatal │
    │    └──────────────────────────────────────────────────────────────┘
    │
    │  [M3] stamp card.fit_diag on EVERY arm's cards, post-ranking, try/except
    │
    │  serving_roster = roster − {fit} if bakeoff_serve_fit=0   [F5b]
    │  compose_deck(serving_roster) (runner:1293)  ── group_size=0 ──► team_draft (runner:850)
    ▼
 BakeoffRun ──► served_deck() ──► final_cards (server.py:5682)
    │                                │
    │ run_row() → save_bakeoff_run   │ _log_deck_signal_impressions (server.py:4020)
    │   arms_json[fit].diagnostics   │   features_json.fit / .fit_diag  + model_arm='fit'
    ▼                                ▼   (only if served; serve-bit off ⇒ no fit rows)
 bakeoff_runs (database.py:710)   deck_impressions (database.py:507)
    ▲                                ▲
    └── M2 readout SQL ──────────────┘        M1: PUT /api/admin/config/<key>
        M4 tripwires (daily)                       (server.py:16652) + scripts/set_knob.py
        never split fit by `basis` (C4)            → model_config_changes + updated_at
```

---

## 2. Component map

### 2.1 `backend/trade_gen_fit.py` (new; F1–F4)

One module, five internal stages, same external shape as `trade_gen_v2`:

```
generate_league_suggestions(...) -> (list[TradeCard], FitReport)
    per boarded-or-not opponent pair:
      1. POOL BUILDER      union: top fit_pool_consensus by consensus value
                            ∪ top fit_pool_div_seed by |board − seed| (if boarded)
                            ∪ top fit_pool_div_opp by |user − opp| (if both boarded)
                            ∪ owned in-horizon picks (K0); cap fit_pool_cap
      2. ENUMERATOR        1-for-1 full cartesian first, then 2/3-asset shapes
                            expanded around top fit_expand_from centerpieces;
                            hard stop at fit_max_packages_per_pair; §2.6 counters
      3. KNOCKOUT CHAIN    K1 shape → K2 pick-churn → K4 overpay → K5 pos-net
                            → K6 pick-gap → K7 need (fit_r5_mode) → K3 lineups LAST
      4. SCORER            per team: L1/L2/L3 via score(s)=even+50·tanh(s/scale),
                            weights renormalized over fired lenses; card.fit payload
      5. RANKER + FILTERS  sort by aggregate (unranked-pair tie-break = consensus
                            fairness, C7c); then F4: untouchables / not-interested /
                            pins / R4+swiped / C4+C4b / per-opponent caps
```

Stage boundaries are module-internal functions (LLD names them); the module's public
surface is exactly the entry point plus its report type, matching
`trade_gen_v2.generate_league_suggestions` (`trade_gen_v2.py:844`) and its
`GenerationReport` (`trade_gen_v2.py:367`).

**Imports it is allowed:** the live-predicate MODULE (`from . import trade_service as ts`
— T1, §5a), `trade_optimizer._feasible_after` (which lives at
`backend/trade_optimizer.py:161`, NOT in trade_service — PLAN.md note 1 names it
correctly), and value math `ts.elo_to_value` (`trade_service.py:1141`) /
`ts.package_value_v2` (`trade_service.py:1172`). It must NOT import `_shrink_user_elo`
(§5c) and must never be imported by `trade_service` (§4).

### 2.2 Runner integration (F5 + F5b)

- **Arm constant + roster.** New `ARM_FIT = "fit"` in `ALL_ARMS`
  (`bakeoff_runner.py:135`); `ARMS` (`:131`) stays the historical three (its docstring
  pins it as a Phase-3 test fixture — widening it silently rewrites those tests).
  `arm_roster()` (`:247`) gains `ARM_FIT: _cfg("bakeoff_include_fit", 0.0) >= 1.0`.
  Fit is appended LAST to `GENERATION_ORDER` (`:190`) — arm B stays first because dark
  fallback and the progress bar track it (`DARK_SERVED_ARM`, `:194`, unchanged).
- **Fit is NOT an ENGINE_ARM** (`:146`). `groups_for()` (`:521`) gives engine arms a
  divergence group and a consensus group; fit stamps `basis` as data-availability
  (PLAN.md note 6), so basis-narrowed groups would partition fit's list on the exact
  overloaded meaning C4 warns about. Fit gets one basis-`None` group, like `gen_v2`
  (`Group(fit, fit, None)`).
- **Fan-out entry.** `run_bakeoff(...)` (`:1322`) today takes exactly two callables
  (`generate`, `gen_v2`) and dispatches by if/elif (`:1371–1399`). It gains a third
  callable (`gen_fit`), bound at the call site (`server.py:5669`) the same way
  `gen_v2` is: `lambda **ov: _bakeoff.gen_fit_cards(trade_service,
  {**_generate_kwargs, **ov})`. A new adapter `gen_fit_cards` mirrors `gen_v2_cards`
  (`:1133`): resolve the league from `trade_service._leagues`, merge past-decision keys,
  apply the stud-tax pin, call the module, then re-apply the shared post-generation
  treatment (intent filter via `effective_trade_intent`, `cap_give_headliners`
  (`trade_service.py:1545`), lane labelling via `classify_lane`
  (`trade_service.py:2340`)) — the same three steps `gen_v2_cards` documents as
  presentation-side parity, for the same reason. Fit's diagnostics hand-off reuses the
  thread-local pattern (`_gen2_diag`, `:1120`) — its own slot, drained into
  `ArmResult.diagnostics` (`:926`) immediately after the call.
- **Serve-bit (F5b).** `run_bakeoff` computes a **serving roster** = roster minus `fit`
  when `_cfg("bakeoff_serve_fit", 0.0) < 1.0`, and passes it to BOTH draft paths:
  `compose_deck(roster=serving_roster)` (`:1293`) AND the `bakeoff_group_size = 0`
  fallback `team_draft` (`:1425–1427`) — the fallback matters because the W1 rollout
  config sets `group_size = 0`, so the team-draft path is the one actually live during
  the program. The full roster still drives the arms loop and `arms_json`. Whether
  fit's list stays in the `arm_lists` handed to the agreement scan (`_agreement`,
  `:828` — membership over FULL lists, so a dark fit would show up in
  `also_proposed_by`) is an LLD decision; the HLD's lean is **include it** (free
  agreement telemetry, no serving effect, since no fit card can be in the deck).
- **arms_json.** No schema change: `ArmResult.diagnostics` already flows into
  `run_row()`'s per-arm summary (`:1078`), and `bakeoff_runs.arms_json` is Text
  (`database.py:719`). Fit's §2.6 diagnostic dict rides that existing key.

### 2.3 Measurement rail (M1/M2/M4/M5)

- **M1 — knob log.** `model_config` gains `updated_at`; new table
  `model_config_changes` (`key, old_value, new_value, changed_at, source`). The single
  funnel is `database.set_config` (`database.py:4120`) — it is already the only write
  path `PUT /api/admin/config/<key>` (`server.py:16652`) uses, and that route already
  re-runs both `reload_config()`s. `scripts/set_knob.py` is a thin CLI over the same
  route (or `set_config` directly) stamping `source='operator'`. Raw-SQL bypass caveat
  stands (PLAN-v2 M1): bypassed writes are dated-not-attributed; the snapshot diff in
  M2 catches them because every run stores its effective config whole
  (`snapshot_config`, `bakeoff_runner.py:400`; `config_json`, `database.py:723–728`).
- **M2 — readout pack.** `scripts/bakeoff_readout.sql` encodes draft B §2.4 under the
  read-only posture (`backend/tools/prod_analytics.py` precedent). Binding: it never
  splits fit by `basis` — fit's analysis key is `features_json.fit.boards ∈
  {both, viewer, none}` (C4/R-11). `basis` and `lane` are already frozen on
  `features_json` (`database.py:589` comment), so no new column is needed.
- **M4 — tripwires.** Queries only, over `bakeoff_runs` + `deck_impressions`:
  deck-median, position balance, re-ranker bypass assertion, per-arm error/forfeit,
  ghost share, max single-tester share, per-arm `fit_diag` null-share, and the
  serve-bit leak check (`model_arm='fit'` rows while `bakeoff_serve_fit=0` → stop).
- **M5 — tester protocol.** Doc-only; no code surface.

### 2.4 M3 — the `fit_diag` stamp site

Stamped **in `_run_trade_job`, immediately after `run_bakeoff` returns** (after
`server.py:5682`), because that is the one place where both the ranked cards of every
arm AND the scorer's inputs (raw `elo_map_rt`, `seed_map`, league members' boards via
`trade_service._leagues`) are simultaneously in scope. Mechanics: set a plain card
attribute (`card.fit_diag = {you, them, bucket, ver}`) on every card of every arm's
list, whole loop wrapped in one try/except; `_log_deck_signal_impressions`
(`server.py:4020`) then copies it into the `features` dict unconditionally whenever
`bakeoff_run is not None` — key always present, value `None` when the stamp failed
(M4's null-share tripwire needs absence to be impossible). Post-ranking by
construction: every arm's list is already ranked and the draft already run before the
stamp executes, and `test_fit_diag_inert` (delete the stamp → served deck identical)
enforces that nothing downstream reads it. Note the T2 `executemany` trap
(`save_deck_impressions`, `database.py:5427`, compiled from the first row's keys —
HANDOVER §6.3) applies to ROW-level keys; `fit` / `fit_diag` ride INSIDE the single
`features_json` string (`server.py:4216`), so they are immune to the column-drop
failure mode — the uniform-presence rule is a measurement contract, not a persistence
workaround.

---

## 3. Boundary contracts

### 3.1 TradeCard fields the fit arm populates

`TradeCard` (`trade_service.py:2922`) — required positional fields first; the
gen_v2 constructor call (`trade_gen_v2.py:1001`) is the template.

| Field | Fit semantics |
|---|---|
| `trade_id`, `league_id`, `proposing_user_id`, `target_user_id`, `target_username` | As gen_v2: uuid4[:8], job identifiers, from `LeagueMember` |
| `give_player_ids` / `receive_player_ids` | Post-K2-strip is NOT applied to the stored lists — the card carries the full package; K2 only judges (matching live `pick_swap_ok` semantics, `trade_service.py:1686`) |
| `mismatch_score` | Required positional with no PRD ruling — LLD decides (§10 F-4); must be numeric because clients render it |
| `fairness_score` | **The live consensus ratio** (PLAN.md binding note 5) — computed from consensus package values so existing UI (TradeValueBar, filters) keeps meaning; NOT a fit-lens number |
| `composite_score` | `fit.aggregate`, 0–200 (PRD §4). Safe for the draft, which is rank-based (`_draft_core`, `bakeoff_runner.py:777`, consumes list ORDER only — C7b); never magnitude-compared across arms (`test_draft_rank_only`) |
| `basis` | `"divergence"` iff both members `has_rankings`, else `"consensus"` (PLAN.md note 6; PRD §7) — honest about data availability. Analysis NEVER keys on it for fit (C4); `features_json.fit.boards` is the analysis key |
| `give_value` / `receive_value` | Consensus package values, same as gen_v2 (`trade_gen_v2.py:1008–1009`) — drives the value bar |
| `fit` (new attribute) | The §4 payload: `{you, them, aggregate, bucket, boards, ver, lenses:{you:{board, vs_consensus, consensus}, them:{...}}}` — `boards ∈ {both, viewer, none}`, `ver` a pinned scorer version string. Serialized additively on the card dict (scope.md §4: api-reference row) |
| `need_fit` | May be STAMPED for telemetry, never multiplied (PRD §4) |
| NOT run | `_tier_mult_v2`, `need_fit` multiplier, `block_boost`, `outlook_dir`, aggression — live rank overlays the fit scorer replaces (PRD §4) |
| `lane` / `lane_shift` | NOT set by the module; applied by `gen_fit_cards` post-generation exactly as `gen_v2_cards` does (`bakeoff_runner.py:1262–1272`) so the lane comparison compares generators |

### 3.2 `arms_json['fit'].diagnostics` (draft B §2.6, adopted by PLAN-v2 §4)

Required keys, every run: `enumerated`, `scored`, `killed{K0..K7}` (K7 first-class —
C2), `one_sided_pct`, `both_high_pct`, `mixed_pct`, `you_tilt_pct`,
`median_aggregate`, `ms`, `top_q_pick_share`, `top_q_junk_share` (junk = asset below
`asset_floor_abs` consensus). Transport: the thread-local diagnostics slot →
`ArmResult.diagnostics` → `run_row()` (`bakeoff_runner.py:1078`). W3 soak bars read
these fields directly (`top_q_junk_share ≤ 0.10`, `top_q_pick_share ≤ arm B + 10pp`,
p95 `total_ms ≤ 30 s`, `killed[K7]` reported).

### 3.3 `features_json` payloads

- `features_json.fit` — on served fit cards only (attribute exists only on fit cards);
  same object as card payload §3.1, minus lens nulls nothing downstream needs.
- `features_json.fit_diag` — `{you, them, bucket, ver}` on EVERY bake-off card of
  EVERY arm; `ver` must equal the `fit.ver` of the scorer build that stamped it, so a
  readout can refuse to bucket-match across scorer versions.
- Both keys present (possibly null-valued) on every row whenever `bakeoff_run is not
  None` — the M4 null-share tripwire's contract.

### 3.4 Config keys (T4 discharge, blocking)

All 16 keys — PRD §9's 13 + `fit_r5_mode`, `fit_junk_floor`, `bakeoff_serve_fit` —
registered in `trade_service._DEFAULT_CFG` (ends `trade_service.py:841`), which is
what puts them in `snapshot_config()` → `config_json` (the contamination diff's
mechanism), plus `_PINNED_KNOBS` (`backend/tests/test_bakeoff_arm_a_golden.py:454` —
fails BY NAME on any unlisted key, HANDOVER §6.6) with the D-095 disposition sentence,
plus `docs/plans/three-model-bakeoff/scope-phase2.md`, same commit. **And** — see
finding F-1 — each key needs a `database._MODEL_CONFIG_DEFAULTS` row
(`database.py:2157`), because `set_config` (`database.py:4120`) raises `KeyError` for
keys without a table row and rows are seeded only from that list
(`database.py:2874`, INSERT OR IGNORE). Without the row, `set_knob.py` and
`PUT /api/admin/config` 404 on every fit knob and the whole knob-rollback ladder is
theater.

---

## 4. Integration points and isolation proofs

**Organic path never imports the module.** The organic deck is
`trade_service.generate_trades` → `_generate_trades_impl`
(`trade_service.py:3186/3196`); `trade_gen_fit` is imported in exactly one place, the
runner adapter (`gen_fit_cards`), and the adapter runs only inside `run_bakeoff`'s arm
loop, which runs only when `bakeoff_on` (`server.py:5662`), which requires the
`trade.bakeoff` flag AND an organic unpinned deck (`bakeoff_active`,
`bakeoff_runner.py:360`), AND fit requires `bakeoff_include_fit=1` on top. Three
independent proofs ship: the grep code-walk (scope.md §3), `test_organic_never_imports_fit`
(F6), and the organic byte-identical fixture run (PR-F3 gate). Pinned/opponent-scoped
decks get isolation for free — `bakeoff_active` is False there, so fit never even
generates.

**How fit enters the fan-out.** Roster membership only (`arm_roster()`), evaluated per
job; the arm loop's per-arm try/except (`:1400`) makes fit's failure a recorded
`ArmResult.error`, never a job failure (§7).

**How fit stays out of the draft under `bakeoff_serve_fit=0`.** The serving-roster
split (§2.2) removes fit from the participants of BOTH draft paths. Everything else
still happens: fit generates, its `ArmResult` lands in `arms_json`, its cards get
`fit_diag`-stamped, its diagnostics get written. What does NOT happen: no fit card in
`draft.deck`, therefore no `deck_impressions` row with `model_arm='fit'`
(`attribution_for` only resolves served cards, `server.py:4247`) — which is exactly
what the M4 serve-bit-leak tripwire asserts.

**What covers fit for free.** `elo_freeze_mult` (`bakeoff_runner.py:350`) keys on
`bakeoff_enabled()` alone — arm-agnostic, so swipe-K freezing needs nothing new.
`bypass_rerankers` (`:374`) keys on `serve_interleaved() and bakeoff_active(...)` —
also arm-agnostic: any interleaved deck fit cards are served into (W4) is already
protected from the five re-rankers (HANDOVER §6.5), and every bypass site in
`_run_trade_job` (`server.py:5728–5858`) checks `bakeoff_fixed_order`, not the arm.
**Where they don't cover fit:** in dark mode (`serve_interleaved`=0)
`bypass_rerankers` is False by design (`:379–381`) — harmless for fit, which isn't
served then; and nothing bypasses the re-rankers on the arm's INTERNAL ranking —
irrelevant, since fit's ranker is its own scorer and no post-generation layer touches
per-arm lists before the draft.

**Admin/config surface.** No new routes. M1 touches the existing
GET/PUT `/api/admin/config` pair (`server.py:16634/16652`, `X-Cron-Secret` via
`_require_cron_auth`); the PUT's write path is the M1 hook point and its existing
`reload_config()` calls are what make every knob flip deploy-free.

---

## 5. Design decisions (alternatives named and rejected)

### (a) Live predicates: module-level import, by-name import, or copy? — **module import**

- **Chosen:** `from . import trade_service as ts`, call `ts.overpay_ok(...)`,
  `ts.pos_net_ok(...)`, `ts.pick_gap_ok(...)`, `ts.need_gate_ok(...)`,
  `ts.pick_swap_ok(...)` (`trade_service.py:1743/1765/1790/1824/1686`), plus
  `trade_optimizer._feasible_after` imported at call time or as a module reference.
- **Rejected: by-name import** (`from .trade_service import overpay_ok`). This is T1,
  observed in this repo: `trade_optimizer.py` and `trade_gen_v2.py` (`:112–131`) bind
  predicates by value at import, and an agent measuring a wrapped-not-edited gate saw a
  perfect no-op on a gate firing 1.17M times. A rebind (D-096-style monkeypatch, test
  fixture, hot-fix) would silently not propagate to fit.
- **Rejected: copying bodies.** Forks the K-math the PRD explicitly closes ("Reuse the
  live predicates. Do not fork R1–R3/C3 math", PRD §3), and scope.md §5 fails review on
  any diff under the live gates.
- Note the predicates read knobs through `_c` (`trade_service.py:878`), which resolves
  thread-local overrides first — so fit's K4–K7 automatically see the same live values
  arm B sees, and a shared-knob change moves both arms at once (PRD §9's stated
  intent). `test_fit_gate_binding_sabotage` (F6) proves the binding by mutating the
  module attribute and watching fit's kill counts move.

### (b) K-evaluation order with K3 last (C6) — **cost-ordered chain**

Order: K1 (integer shape test, O(1)) → K2 (pick strip: sort ≤3 picks/side,
`trade_service.py:1649`) → K4/K5/K6 (sums over ≤6 assets with a cached
consensus-value accessor) → K7 (primary-asset scan + roster position lookup,
`trade_service.py:1824`) → **K3 last** (`_feasible_after`,
`trade_optimizer.py:161`). Cost model: with `_pos_counts` precomputed once per roster
per pair (the v3 pattern), K3's per-candidate cost is the O(|package|) delta build
(`_subset_pos_delta`) ×2 sides plus a 4-position compare — cheap amortized, but the
only predicate whose input is a per-side aggregation that cannot ride the same cached
scalar accessor the K4–K6 sums share, and the review's measured claim (C6) is that
feasibility dominates. Ordering it last means it runs only on the survivors of six
cheaper kills.
- **Rejected: PRD table order (K3 third).** Spec order is construction logic, not
  execution order; PLAN-v2 F1's binding note makes K3-last explicit.
- **Rejected: adaptive ordering (re-sort predicates by observed kill rate).**
  Speculative machinery; the waterfall report already tells us the static order, and
  the `killed[K1..K7]` counters must stay attributable to a FIXED order to be
  comparable across runs.

### (c) Scorer reads raw boards only (T3) — **raw member boards + raw seed, never `shrunk_elo`**

Where the boards come from in the call chain: `gen_fit_cards` receives the job kwargs;
`kwargs["user_elo"]` is the user's raw board (`elo_map_rt`, bound at
`server.py:5637`), `kwargs["seed_elo"]` the raw consensus seed, and the partner boards
are `member.elo_ratings` on `trade_service._leagues[league_id].members` — raw by
construction (nothing ever shrinks a partner board; `LeagueMember` carries no
confidence map). Shrinkage exists only where a generator CALLS `_shrink_user_elo`
(`trade_service.py:1305`) — gen_v2 does (`trade_gen_v2.py:903`); **fit simply never
calls it**, so `shrunk_elo` cannot appear in any lens. Enforced by module docstring +
`test_fit_lens_provenance_raw` (F3 binding note).
- **Rejected: shrink the viewer board like arm B/C.** Re-imports the audit's bug-3
  asymmetry (raw partner vs shrunk user — the mechanism behind 86.9% one-directional
  boarded-pair cards, `trade_service.py:~800` comment) into the one arm whose thesis is
  symmetric team scores, and creates a THIRD provenance variant (the exact thing T3
  forbids).
- **Rejected: shrink both.** Impossible without partner confidence data, and a math
  change the PRD doesn't authorize.

### (d) `fit_diag` at generation time on all arms vs offline re-scoring — **generation-time stamp (R-11)**

- **Chosen:** stamp in `_run_trade_job` post-ranking (§2.4), version-pinned, inert.
  The scorer's inputs (raw boards as they were AT SERVE) exist only in that moment;
  boards mutate with every ranking session.
- **Rejected: offline re-scoring at readout time.** Re-derives boards from
  `swipe_decisions`/rankings history — a reconstruction of serve-time state that the
  D-091 contamination discipline exists to distrust; and it silently diverges the
  moment any board changes between serve and readout. The frozen-at-serve rule is
  already the `features_json` design principle (`database.py:492`).
- **Rejected: stamp only fit's own cards.** That is the biased readout R-11 names: fit's
  best buckets vs arm B un-bucketed — biased FOR fit.
- Cost: one extra scorer pass over ~40–120 cards/arm × ≤4 arms, all sums — noise
  against a 7.4 s job.

### (e) Serve-bit as fit-only knob vs general serving-roster mechanism — **fit-only bit**

- **Chosen:** `bakeoff_serve_fit` (float 0/1), read in exactly one place
  (`run_bakeoff`'s serving-roster derivation). One knob, one consumer, one tripwire.
- **Rejected: a general `bakeoff_serve_<arm>` family or a serving-roster list knob.**
  `model_config` is float-only (`backend/CLAUDE.md` §Database), so a roster string
  can't live there; a per-arm bit family generalizes a mechanism with exactly one
  current consumer — the repo's convention (D-078/D-086 pattern) is to build the
  general mechanism on the second consumer, and PLAN-v2 F5b's binding note says
  precisely that.
- **Rejected: reuse `bakeoff_include_fit=1` + a dark-mode trick.** Couples rostering to
  serving — the exact coupling whose dissolution made R-4's dark soak possible (A
  withdrew its no-soak position because the serve-bit exists).

### (f) Enumeration budget shape — **1-for-1 cartesian, then expand-from-top-N**

- **Chosen:** full 1-for-1 cartesian over the ≤15×15 pool (≤225 candidates — every
  single-asset idea is examined), then 2- and 3-asset shapes built only around the top
  `fit_expand_from` (25) 1-for-1 centerpieces, hard-capped at
  `fit_max_packages_per_pair` (5,000 at first rostering, 20,000 default). Leave-short
  is recorded (`enumerated` vs cap) — data, not failure.
- **Rejected: full combinatorial enumeration.** `C(15,3)² ≈ 2.1e5` shapes per pair
  before K1 widening; the un-pooled figure is the PRD's own 7e6 headline. Kills the C6
  job budget for ideas that centre on assets no 1-for-1 signal supports.
- **Rejected: divergence-direction pruning (live's `_vo ≥ 0.97×user`).** That is the
  filter this arm exists to delete (PRD §3 "Explicitly not knockouts"); re-adding it as
  a budget device would smuggle the direction prune back in through the enumerator.
- **Rejected: random/sampled enumeration.** Non-deterministic diagnostics; `enumerated`
  and `killed_by` become unstable across re-runs of the same job, breaking the frozen
  fixture (HANDOVER §6.7) and the W0 dry-run comparison.

---

## 6. Failure containment

- **Fit throws mid-fan-out.** Contained by the existing per-arm try/except in
  `run_bakeoff` (`bakeoff_runner.py:1400–1402`): the arm records
  `ArmResult(error=repr(e), cards=[])`, forfeits its draft slots (an empty participant
  is DATA, `:1346–1349`), and the job proceeds — arm B still serves. `arms_json[fit].error`
  is non-null; M4's per-arm error tripwire reads it. `gen_fit_cards` clears its
  diagnostics thread-local on entry (the `_gen2_diag` pattern, `:1179`) so a raise
  can't leak a previous job's counters.
- **Timeout.** `_JOB_HARD_TIMEOUT = 60` (`server.py:2218`) is enforced by the cleanup
  loop (`server.py:2704–2715`): a running job older than 60 s is MARKED error — the
  thread is not preempted, but the user gets nothing. A slow fit arm therefore fails
  the whole job for the user even though the code "works" — this is why the W3 soak bar
  is p95 `total_ms ≤ 30 s` (headroom, not the cliff) and why
  `fit_max_packages_per_pair` starts at 5,000. There is no per-arm deadline (rejected:
  adding one is new machinery; the cap knob is the relief valve and is per-pair, which
  bounds per-job work linearly in opponents).
- **Knob-rollback ladder** (every rung one logged `set_knob.py` write, no deploy):
  1. `bakeoff_serve_fit = 0` — fit out of the draft; generation + diagnostics continue.
  2. `bakeoff_include_fit = 0` — fit out of the fan-out entirely; zero added cost.
  3. `fit_max_packages_per_pair` ↓ — job-time relief without leaving the roster.
  4. `fit_junk_floor = 1` / `fit_r5_mode` — the pre-wired dark levers (C2/C5), flipped
     only as a pre-registered iterate action, never mid-window.
  5. `trade.bakeoff` off — the program-level kill (flag, not model_config), which also
     stops attribution and unfreezes swipe-K (`elo_freeze_mult`).
  Deck-shrink tripwire (R-9): median < 22 investigate same day; < 18 two consecutive
  days → revert = rung 1 (or rung 5 if the shrink isn't fit's).

---

## 7. Performance budget

Baselines from code and PLAN-v2: the three-arm fixture run measured 7.36 s total with
arm A the slowest at 4.19 s (`bakeoff_runner.py:258–260`); PLAN-v2 quotes ~7.5 s at 3
arms on the boarded league. Hard ceiling `_JOB_HARD_TIMEOUT = 60 s`; W3 soak bar p95
≤ 30 s.

Per-pair model (11-opponent league, worst case):

| Stage | Cost | Notes |
|---|---|---|
| Pool build | O(roster · log) per side | 3 sorts of ≤ ~30 assets + union/cap — sub-ms |
| 1-for-1 cartesian | ≤ 225 candidates | full pool × pool |
| Expand | up to cap (5,000 first roster; 20,000 default) | around top-25 centerpieces |
| K1/K2/K4–K6 | O(package) sums with cached value accessor | the `_cv_cache` pattern (`trade_gen_v2.py:911`) |
| K7 | primary-asset scan + one sorted position list per pair | precompute `user_pos_values` once per job |
| K3 (last) | O(package) delta vs precomputed `_pos_counts` | runs only on six-kill survivors |
| Scoring | 3 lenses × 2 teams × O(package) sums | sums, no search — the cheap part by design |

Per job: ≤ 11 × 5,000 = 55k enumerated worst case at first rostering — the same order
as gen_v2's own league-wide `_ITER_BUDGET = 60_000` (`trade_gen_v2.py:137`), which the
existing job budget already absorbs. The 20,000 default (≤ 220k/job) is why the W0
dry-run fixture ms is recorded and the operator sets the fail bar BEFORE
`bakeoff_include_fit=1` (scope.md §6); the arm-roster knob is the relief valve (C6).
Expected ms distribution: enumeration+K-chain dominates; K3 is the largest single
predicate; scoring is noise. The M3 stamp adds one scorer pass over the ≤ ~160 already-
ranked cards across all arms — negligible.

---

## 8. Rollout hooks (context only — schedule owned by PLAN-v2 §5)

W0 dry run exercises the module offline (replay boards for league
`1312140920132497408`, fixture league, one 16-team SF roster) with no serving change.
W1–W2 serve B+D+C under `bakeoff_serve_interleaved=1`, `group_size=0`,
`deck_limit=30` — note `serve_interleaved`'s code default is 1.0
(`bakeoff_runner.py:236`) with the DB row currently 0.0 (operator, 2026-08-19), so the
re-light is a `model_config` write, logged via M1. W3 rosters fit dark
(`bakeoff_include_fit=1`, `bakeoff_serve_fit=0`). W4 serves fit at k=2
(`bakeoff_serve_fit=1`, `bakeoff_include_challenger=0`, `bakeoff_include_gen_v2=0` —
both roster knobs already exist, `trade_service.py:~835–840`).

---

## 9. What the HLD does NOT decide (LLD handoff)

- Exact function signatures inside `trade_gen_fit.py` (stage boundaries, report
  dataclass name/fields) and `gen_fit_cards`' full kwarg mirror.
- `mismatch_score` semantics for fit cards (§10 F-4) and whether `fit.lenses` nulls
  serialize.
- The tanh value table for the frozen scorer fixture (compute, don't copy — §10 F-5)
  and the `fit_score_even` knob-vs-constant call (§10 F-2).
- SQL text of M2/M4 (tables and keys are fixed above; the queries are not).
- `model_config_changes` DDL details (index, retention) and `set_knob.py` CLI shape.
- Test fixtures (pinned inputs per HANDOVER §6.7) and the exact F6 test list beyond the
  named-in-plan tests.
- Whether fit's list stays in the agreement scan's `arm_lists` while serve-bit-off
  (§2.2 lean: yes).
- `docs/` row wording (config-reference, api-reference, data-dictionary) — owed per
  scope.md §4, authored at build time.

## 10. Findings for the LLD (code facts the plan does not state, or contradicts)

- **F-1 (blocking).** T4 as written is insufficient for the M-rail:
  `database.set_config` (`database.py:4120`) raises `KeyError` for any key without an
  existing `model_config` row, and rows are seeded only from
  `database._MODEL_CONFIG_DEFAULTS` (`database.py:2157`, seeding loop `:2874`).
  Registering the 16 keys in `trade_service._DEFAULT_CFG` + `_PINNED_KNOBS` alone
  leaves `PUT /api/admin/config` and `set_knob.py` returning 404 for every fit knob —
  the entire knob-rollback ladder would be inoperable. Every fit key needs a
  `_MODEL_CONFIG_DEFAULTS` row in the same commit.
- **F-2.** PRD §4's code block names `fit_score_even` (default 50) as a
  `model_config` knob, but PRD §9's knob table and both T4 key lists omit it. Decide:
  knob (then the T4 set is 17 and F-1 applies to it too) or module constant (then fix
  the §4 comment). Either way the count "16" in PLAN-v2 needs the disposition recorded.
- **F-3.** `run_bakeoff`'s signature takes exactly two generator callables
  (`generate`, `gen_v2` — `bakeoff_runner.py:1324–1325`) with an if/elif dispatch;
  adding fit is an API change to the runner touching its call site
  (`server.py:5669`) and every test that calls `run_bakeoff` directly.
- **F-4.** `TradeCard.mismatch_score` is a required positional field
  (`trade_service.py:2930`) that the PRD never mentions for fit. gen_v2 fills it with
  the harmonic mean of the two sides' gains (`trade_gen_v2.py:1010`); fit has no
  equivalent gains. LLD must pick a value (candidate: harmonic mean of `you`/`them`,
  or 0.0 with a comment) and check nothing client-side renders it misleadingly.
- **F-5.** PLAN-v2 F3's pinned curve table says ±400 → 88.4/11.6, but
  50 + 50·tanh(1) = 88.08. The ±200 values (73.1/26.9) are correct. The frozen fixture
  must pin COMPUTED values, not the plan's rounded ones (this is C7a's own trap
  recurring inside its fix).
- **F-6.** The W1 rollout config sets `bakeoff_group_size = 0`, so the live draft path
  for the whole program is `team_draft` (`bakeoff_runner.py:1425–1427`), not
  `compose_deck` — the F5b serve-bit exclusion MUST be applied to the team-draft
  fallback's participants, not only to `groups_for()`. A groups-only implementation
  would pass its unit tests and leak fit into every real deck.
- **F-7.** Fit must not be added to `ENGINE_ARMS` (`bakeoff_runner.py:146`):
  `groups_for()` would give it basis-narrowed divergence/consensus groups keyed on
  exactly the overloaded `basis` meaning C4 flags, and `effective_fairness_threshold`
  (`:413`) would apply the divergence floor logic to fit cards whose `basis` means
  something else. Fit's `ArmResult.fairness_threshold` should be `None` like gen_v2's
  (`:1414` — "takes no such argument" is equally true of fit, whose fairness is a
  score, not a gate).
- **F-8.** `ARMS` (`:131`) is pinned by Phase-3 tests as the historical three-arm
  fixture — fit goes in `ALL_ARMS` (`:135`) and `GENERATION_ORDER` (`:190`) only.
- **F-9.** `_feasible_after` lives in `backend/trade_optimizer.py:161` (with
  `_pos_counts` `:150` and `_subset_pos_delta` `:181`), not in `trade_service` — the
  task-brief's suspicion is confirmed; PLAN.md note 1's import list is correct as
  written but the LLD should import it from the optimizer module (module-style, per
  T1 discipline, since it too reads `_starters_at`/knobs transitively).

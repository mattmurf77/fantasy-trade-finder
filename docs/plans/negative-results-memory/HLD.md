# HLD: Negative-results memory

**Version:** candidate v3 (round-3 M2×strength decision applied; round-4 verification pending)
**Date:** 2026-08-21 · Serves: [PRD.md](PRD.md) (FINAL — R/NG/C/GR/§8.3 are requirements) ·
Facts: [research-verification.md](research-verification.md) ("memo") ·
Drafts: [HLD-draft-A.md](HLD-draft-A.md) (coherence), [HLD-draft-B.md](HLD-draft-B.md) (failure-modes)

---

## 1. Context & Goals

One new leaf module gives every generation arm a per-league, per-partner soft prior
built from reasoned rejections (M1) and feeds gen_v2's existing acceptance prior (M2),
under one flag (`trade.negmem`), with byte-identical-off as a structural property.
Non-functional envelope: map build inside the job budget (S6), zero new tables (NG6),
zero new events, every influence stamped (R7), full as-of reproducibility (R6).

**Three inherited fragilities this design must not amplify** (draft B §1.1): the
one-worker in-process job model (daemon threads, shared `TradeService` state); the
executemany first-row-keys trap on `deck_impressions` writes; and the bake-off's
measurement discipline (re-ranker bypass, config snapshots, round boundaries — GR3).

## 2. Architecture Overview

### 2.1 Components

```
backend/negmem.py  (LEAF — imports feature_flags + database ONLY; suggestion_telemetry
                    precedent. negmem imports NO engine module; engines import negmem
                    via `import negmem` + attribute call (the T1 rule) — no cycle. The
                    MAP arrives as data; the helper is called, never passed around.)
  ├─ ADMISSION           one shared implementation of PRD R1's closed list:
  │                      a SQL WHERE fragment + a Python predicate PAIR, consumed by
  │                      the builder, the readout, and the RFPS metric SQL — one
  │                      definition so map and metric cannot drift (H-1 fix;
  │                      deck_centerpiece discipline, server.py:4405-4412)
  ├─ build_map(user_id, league_id, as_of=None) -> NegmemMap | None
  │     Returns None for a non-allowlisted (user, league) — the PRD §8.2 league
  │     scoping seam (mechanism = the tester_allowlist pattern; LLD finalizes).
  │     None is indistinguishable from flag-off downstream: no kwarg, NO stamps.
  │     Build-time knobs (halflife, min_evidence) are read ONCE here, globally —
  │     acceptable because arm-A's opt-out is strength-only (D-6), stated here so
  │     nobody "fixes" it into the overlay.
  │     NegmemMap: cells{(partner_league_id, family): {n_raw, n_decayed, mult}},
  │               acceptance_stats{partner: (responses, accepts)},   # M2, same read
  │               degraded: bool, as_of, ver
  ├─ effective_mult(nm_map, partner, *, strength, floor) -> float   # PURE (D-10):
  │     no config access, no defaults inside negmem. Each SEAM reads strength/floor
  │     via its own `ts._c(...)` AT THE CALL SITE, inside the arm's overlay context,
  │     and passes numbers — this is what makes arm A's MODEL_A_PROFILE pin of
  │     negmem_strength=0 actually apply. (A build-time or job-start frozen read is
  │     overlay-blind and would contaminate arm A while every golden passes.)
  ├─ negmem_readout(user_id, league_id, as_of=None)    # R8; same builder
  └─ (module-global map: FORBIDDEN — see T1 rule, §5.2)

server._run_trade_job          builds the map once per job (after flag check),
                               threads it as an explicit kwarg (D-3)
trade_service / trade_gen_v2 / trade_gen_fit
                               consult via negmem.effective_mult at each arm's
                               candidate-creation point (D-4); knobs via _c so the
                               bake-off arm overlays apply (D-6)
server features-assembly       stamps features_json.negmem on EVERY row while ON (§3.4)
```

### 2.2 Consultation seams (one rule, instantiated per arm)

**The rule: after all gates, multiply the ranking score by the partner's effective
multiplier, exactly once, at candidate creation.** Per path (memo §2h + draft A §2.3,
line-verified):

| Path | Seam | Notes |
|---|---|---|
| serving engine (v2-pair, v3, consensus fallback) | the per-member bounded-multiplier stack, `trade_service.py:4943-5196` | joins block-boost/outlook-dir's `_m != 1.0` skip pattern (`:5125`) |
| gen_v2 | pair-constant multiplier in the per-pair loop, `trade_gen_v2.py:939-975` | distinct from M2's `acceptance_stats` (different math, same map) |
| fit | rank-key multiplier in the ranker (post-score, pre-C7c tie-break; `trade_gen_fit.py:384-392` sort key, `composite_score` set separately at `:442`) | ordering only — fit's aggregate payload stays pure. LLD: apply the multiplier BEFORE the 1e-9 quantization so plateau noise (~1e-13) scaled by m stays below the quantum and the C7c same-partner tie survives. Fragility: this path depends on per-arm order surviving to serve — `restore_order` (`bakeoff_runner.py:1415`, called `server.py:5766`) undoing the likes-you composite re-sort; end-to-end test required (§7) |

**Rejected shared seams** (draft A D-4, cited): a post-generation multiplier step
(violates GR3 — interleaved decks bypass post-gen layers, `server.py:5890-5910`, so the
prior would vanish exactly when measured); `_dedup_and_sort` (re-runs per streaming
snapshot over the accumulating list, `trade_service.py:4152-4157` — an in-place multiply
compounds); extending `past_decision_keys` with family keys (that seam is membership =
exclusion = NG1 territory).

### 2.3 Threading: explicit kwarg, job-scoped (D-3 = draft B KD-1; both lenses converged)

`server._run_trade_job` → `negmem=` on `_generate_kwargs` (`server.py:5644-5671`) → both
bake-off fan-out lambdas and `generate_trades` → stored overwrite-per-call like
`exclusion_keys` (`trade_service.py:3983`; None ⇒ identity). **Read once into a local**
at the top of `_generate_trades_impl` and threaded from the local — a concurrent
same-session job overwriting the slot mid-generation cannot produce a mixed-map deck
(H-4; the one free delta over the `_exclusion_keys` precedent). One map per job, never
rebuilt mid-job — bake-off arms must see identical memory or the comparison is
contaminated (H-3).

## 3. Data Model & Flow

```
trade_pass_reasons ─┐  (admission: viewed ∧ reason-carrying{value,fit} ∧ ¬ghost ∧
deck_outcomes ──────┤   ¬retracted/undone ∧ clean-epoch — ONE shared implementation)
deck_impressions ───┴─► evidence events ─► cells (decay τ=negmem_halflife_days;
   (features_json:            │             shrinkage: n_decayed < min_evidence ⇒ identity;
    context tags)             │             clamp mult ∈ [negmem_floor, 1.0])
deck_outcomes(likes) ─► netting events ─► folded in timestamp order vs (P,✱) cells
trade_matches ────────► acceptance_stats (M2; count-based, 180d lookback in-query)
                              │
                              ▼
        NegmemMap ──(kwarg)──► arms: eff = effective_mult(map, partner,
                              │          strength=_c("negmem_strength"),
                              │          floor=_c("negmem_floor"))   # seam-side reads
                              │        · the SEAM owns the eff == 1.0 skip
                              ▼
        features_json.negmem stamp (every row while ON — §3.4 trichotomy)
```

### 3.1 The bulk read
One query set per job over the spine (league-scoped, indexed by the existing
`ix_deck_outcomes_impression` join path), bounded by the READ HORIZON
`max(clean_epoch_floor, as_of − 4·negmem_halflife_days)` — evidence older than four
half-lives contributes < 6.25% of an event, below the shrinkage floor's resolution, so
the bound changes nothing the clamp can see while keeping the read O(window), not
O(lifetime): worst case ~10k–40k rows at 10x under the default 45d half-life (≈180d
cap). Cost measured by S6 — budget seeded at p95 ≤ 2× the fatigue read's measured p95,
absolute ceiling 250ms (LLD may tighten, not loosen silently). One read per job, after
the flag+allowlist check, before the arm fan-out.

### 3.2 Failure behavior: fail-open to identity, loudly (draft B §3.2)
The job NEVER dies for negmem — identity is always a legal output (C1/NG1; the F3
precedent "any read failure degrades to all-1.0," `server.py:4497-4503`). Three
trip-wires: (1) `NegmemMap.degraded = True` on build exception OR build_ms > 2× the S6
ceiling, recorded on the job dict (the `suppression_note` pattern); (2) stamp-absence
as signal — flag ON + no `negmem` keys = builds failing, one SQL away from visible
(readout computes `stamp_rate BY day, arm`, expected 100%); (3) runbook line: degraded
rate > 1% of jobs over 24h ⇒ set `negmem_strength = 0` and investigate. Rejected:
fail-closed, in-job retry, stale-map reuse (violates C5).

### 3.3 Consistency hazards, named and handled (draft B §3.3)
- **H-1 reason lateness:** pass and reason arrive in separate requests; a job in the
  gap sees a bare pass (not admitted), the next job sees it admitted. Accepted: `as_of`
  = build time; the defense that matters is the ONE shared admission implementation so
  builder, readout, and metric can never disagree.
- **H-2 the upsert hop:** a reason can change family after admission
  (`trade_pass_reasons` upserts; `switched_from` keeps one hop). Cell counts may move
  without new events — R6 concedes this. The REAL exposure is the RFPS baseline (risk
  R-X, §6): fixed by freezing the baseline cohort at pre-registration.
- **H-3 netting:** derive-on-read ⇒ no write-path ordering hazard; a like is visible to
  every build starting after its commit. Within-job consistency = one map per job.
- **H-4 concurrent same-session jobs:** same pre-existing race class as
  `_exclusion_keys`; blast radius bounded (ordering shifts within clamp; membership
  untouched); the read-once-into-local rule prevents mixed-map decks.

### 3.4 Stamps: the trichotomy, enforced not hoped (draft B §3.4)
`features_json.negmem = {m, keys, ev, ver}` INSIDE features_json (fit/fit_diag
precedent — the Text column always present, so first-row-keys compilation cannot drop
it). **Provenance rule (B2): the multiplier and its keys/ev are computed at CONSULT
time and ride the card; features assembly COPIES card state and computes nothing** —
it only applies the `{m: 1.0, exempt}` / `{m: 1.0}` / degraded defaults for cards with
no consult site. By logging time every arm's `_cfg_override` context has exited, so an
assembly-side recompute would stamp arm-A rows with the live arm's m and silently
poison per-arm attribution — hence the rule, plus a test asserting arm-A rows in a
bake-off deck stamp exactly `{m: 1.0}`. The trichotomy's ON-condition is
**flag ON ∧ league allowlisted** (a non-allowlisted league's build_map returns None ⇒
no stamps, so the stamp-rate tripwire never false-alarms on it). Rules:
flag OFF ∨ not allowlisted ⇒ no row anywhere carries the key (byte-identical
features_json);
flag ON + non-degraded ⇒ **every row the job writes** carries it (influenced: real
m; uninfluenced: `{m: 1.0}`; likes-you-exempt: `{m: 1.0, exempt}`) — stated as
"every row" rather than "served and ghost" since the ghost holdout is disabled and
operator-ruled off (2026-08-21), though the rule would cover any such row regardless; flag ON + degraded
⇒ every row `{m: 1.0, degraded: true}` — failure is in the data, never inferred from
absence. C3 reduces to a trivial SQL invariant. Structural test: a deck led by a
likes-you injection (the exact model_arm scar scenario) retains the key batch-wide.

### 3.5 M2 flow and edges (draft B §3.5)
`acceptance_stats` rides the map (D-9); both gen_v2 call sites receive it only when the
map exists. At n=0 (today's reality — the decline route has essentially never fired)
the E-B math must return the global prior, not 0/0 — **guard placement rule: the
aggregation never emits zero-response keys and the feed returns `{}` when
`gen2_accept_prior_strength ≤ 0` (the E-B pseudo-count `m` in the memo §2f formula IS
that knob); the guard lives in the FEED, never inside the ratified `acceptance_prior`
math (NG9)**. **M2 strength governance (the round-3 decision): `negmem_strength` is an
M1-ONLY lever. M2's strength is governed by the EXISTING seeded knobs
`gen2_accept_prior_strength` / `gen2_accept_global_prior` (PRD R5), and its independent
deploy-free kill is `gen2_accept_prior_strength = 0` — which the feed-guard above makes
structural (feed returns `{}`).** Arm A never invokes M2 in any case — it is the v1/v3
engine and gen_v2's acceptance prior runs only inside arm C — so arm A remains a clean
M1 comparator under any knob state.
The parity test (C4) includes the empty-table case explicitly; S4 is annotated
expected-null. Relaxed/targeted passes need no special case: same map, same strength
via `_c`; and a soft multiplier cannot trigger the `not cards` relaxed rerun (NG1,
structural — `trade_service.py:4271-4318`).

## 4. Key Design Decisions (mini-ADR; full rationale in draft A §4)

- **D-1 Derive-on-read, no tables** (NG6; DC-2 house style; deletion structural;
  materialization only on a MEASURED S6 failure, §5.4).
- **D-2 Leaf placement `backend/negmem.py`** (suggestion_telemetry precedent; readout
  callable without the app; no engine imports of negmem — no cycles).
- **D-3 Kwarg threading, job-scoped, overwrite-per-call, read-once-into-local**
  (both lenses independently; thread-locals rejected — hidden state makes C1 a runtime
  property and adds a leak surface; constructor state rejected — session-stale).
- **D-4 Consultation inside each arm at candidate creation** (post-gen fails GR3;
  `_dedup_and_sort` compounds under streaming snapshots; key-set seam is NG1).
- **D-5 Families key EVIDENCE, candidates see a per-partner collapsed multiplier**
  (no card feature honestly maps a fresh candidate to a rejection family at the v1
  key; families still earn admission-gating, bookkeeping, readout, RFPS, and the P2
  path; combine rule — product vs min — is LLD with fixtures).
- **D-6 `negmem_strength` applies at consultation via `_c`, not baked into the map**
  (structural short-circuit at 0; the thread-local overlay makes arm A's disposition a
  plain profile pin `MODEL_A_PROFILE["negmem_strength"] = 0.0` — no bespoke bypass).
- **D-10 (new at synthesis; resolves A's own D-6 worry + B's triplication attack):**
  the effective-multiplier computation — strength scaling and clamp — lives in ONE
  PURE function, `negmem.effective_mult(map, partner, *, strength, floor)`: no config
  access and no defaults inside negmem. Each seam reads strength/floor via its own
  `ts._c(...)` at the call site (inside the arm's overlay context — the arm-A opt-out
  mechanism) and owns the `eff != 1.0` skip; seams contribute two lines each. C2's
  invariants are tested against the single implementation; a seam cannot drift the
  math. Seams import the MODULE (`import negmem` + attribute call — T1); the helper
  is never passed around as a value.
- **D-7 Like-netting lives in the builder** as events in the as-of domain (R6 purity;
  netting anywhere else splits the domain and makes the readout lie).
- **D-8 Bake-off citizenship = knob registration; mechanism verified:**
  `snapshot_config()` iterates `_DEFAULT_CFG` via `_c` per arm inside each arm's
  override context (`bakeoff_runner.py:423-433`) → registration alone yields
  `config_json` coverage incl. arm A's strength-0 delta. The invisible-knob failure
  (a knob missing from `_DEFAULT_CFG` never snapshots → mid-window moves undetectable)
  is defended by the EXISTING knob-inventory test (`test_bakeoff_arm_a_golden.py:546`)
  which fails by name on any `_DEFAULT_CFG`/`_PINNED_KNOBS` drift; R10's triple
  registration is CI-enforced, not convention.
- **D-9 M2 rides the NegmemMap; one flag** (one build, one as-of, one S6; P0
  severability is build-order, not an architectural fork).

## 5. Cross-Cutting

### 5.1 C1 byte-identical-off proof, per path
Flag OFF (or league not allowlisted) ⇒ map never built, kwarg never passed, stamp key
never written, M2 kwarg absent — byte-identical in full, including features_json.
`negmem_strength = 0` is scoped differently, deliberately: **the M1 seams produce
byte-identical deck content, scores and order on every path** (seam skip ⇒ no multiply,
no round()) — with ONE stated exception: arm C's decks may still differ via the M2
acceptance-prior feed, which `negmem_strength` does not govern (§3.5 decision; M2's own
kill is `gen2_accept_prior_strength = 0`). Stamps FOLLOW THE TRICHOTOMY — every row
carries `{m: 1.0}` while flag ON ∧ allowlisted, because the stamp-absence tripwire
(§3.2) depends on it. This is an HLD strengthening over PRD R7 (which requires stamps
only on influenced rows) — stated as such. The golden set is scoped to match: (a)
serving-engine + fit fixtures assert FULL byte-equality at `negmem_strength = 0`; (b)
arm-C parity is asserted separately at `gen2_accept_prior_strength = 0`; (c) the arm-A
golden expects `{m: 1.0}` on every row — never absence, never a live m.

### 5.2 The T1 rule (from the fit-challenger scar, now doctrine)
No module-global map, ever — `from .negmem import current_map` would freeze the
import-time empty binding and every golden would pass while the feature silently no-ops
(identity IS flag-off behavior — the worst possible silent failure). Consumers import
the module and call functions; the map moves only as an argument. Sabotage test: rebind
`negmem.effective_mult` → fit/serving output must change (proves live binding).

### 5.3 Observability & operability
R7 stamps (§3.4) · R8 readout (same builder; powers the operator TestFlight checklist)
· GR4 joint-multiplier audit — COMPUTABILITY (draft B §3.6, restored): taste and
fatigue multipliers are NOT individually stamped today, so the joint is computed as
`negmem_stamp.m × (final_score / base_score)` on non-bake-off rows (works uniformly,
incl. fit, since the stamp's m is explicitly multiplied in); the LLD chooses between
accepting the diversity-penalty pollution of that ratio (the 0.15 bar has margin) or
adding `fatigue_m`/`taste_m` keys to features_json under the same uniformity rule ·
runbook triage order: stamp rate → degraded notes → knob triple · degraded-rate and
stamp-rate runbook lines with numeric thresholds (~60 bytes/row stamp residue is the
accepted storage cost) ·
rollback ladder, all deploy-free, nothing left behind at any rung (derive-on-read):
`trade.negmem` off (everything, incl. M2) → `negmem_strength = 0` (M1 inert; M2 still
feeds, with its OWN deploy-free kill `gen2_accept_prior_strength = 0` — §3.5; map still
builds for readout) → `negmem_floor = 1.0` (clamp to identity; diagnostic posture —
stamps keep flowing). Flag/knob flips at round boundaries only
(GR3; operator procedure in the rollout runbook).

### 5.4 10x and the materialization fallback
Derive-on-read holds while the bulk read stays inside the S6 budget (comfortably, at
current volumes ×10 — the read is league-scoped and index-served). If measured
otherwise: the fallback is a `negmem_cells` MATERIALIZED CACHE of the same builder —
same math, same admission fragment, refreshed from the same events, readable as-of via
event replay — never a second source of truth; the `negmem_` prefix is spent only then,
with its own scope block (NG6's spirit: the gate is a measurement, the artifact is a
cache).

### 5.5 Identity & privacy
League identities end-to-end (R9; `_league_user_id` contract; the RFPS metric SQL
documents its global-id→league-id mapping). D3(c) posture: everything derive-on-read,
nothing persisted per-person, deletion structural.

## 6. Risks & Open Questions

- **R-X (the one nobody designed for — draft B):** the pre-registered RFPS baseline is
  computed over MUTABLE reason rows (H-2) — the promotion decision could drift with no
  bug anywhere. **Fix (binding on the LLD/metric spec):** at pre-registration, snapshot
  the baseline cohort by `impression_id` + cell assignment into a committed artifact;
  evaluate window-close on state frozen at close; report the family switch-rate inside
  the window alongside the point estimate; switch-rate > 5% ⇒ the window extends
  (§8.3's ladder).
- **Underpowered signal (honest):** with the flag global, the only negmem-OFF
  comparator is arm A (confounded by its whole profile), so RFPS rests on within-arm
  before/after across a round boundary at ~120 clean reason rows/week. The machinery
  is sound; the honest early outcome may be "extend," repeatedly. The PRD's §8.3
  ladder (with the 2×-window review trigger) is the containment; nothing here
  fabricates power that doesn't exist.
- **M2 empty-table edge:** 0/0 must yield the global prior (C4 includes it); S4
  expected-null annotated.
- **Residual:** the per-partner collapse (D-5) means a partner with heavy `value`
  evidence is also damped on candidates a `fit`-only reading might spare — accepted at
  v1 grain; P2's shape keys refine it when the data earns it.

## 7. Handed to the LLD (explicitly)
Additions from cross-review: the league-allowlist mechanism (build_map's None seam;
tester_allowlist precedent) · the GR4 computability decision (score-ratio pollution
accepted vs stamping fatigue_m/taste_m) · the read-horizon constant (4·halflife) and
the S6 seed numbers (2× fatigue p95, 250ms ceiling) · the fit end-to-end ordering
assertion (a downstream composite-score sort must not erase negmem ordering;
`restore_order` dependency) · the fit quantization order (multiply before
the 1e-9 round) · the M2 id-space fixture check (trade_matches.user_a/b_id vs league
member space) · co-owner canonicalization call sites (ADR-012) · the streaming-callback
golden fixture · the operator TestFlight checklist text (D-056) · the arm-A `{m: 1.0}`
stamp test and the B2 provenance test.
Round-3 additions: the GR4 SQL must define base/final so the score ratio EXCLUDES
negmem's own multiply on the serving/gen_v2 paths (else the joint reads m² —
conservative, but false-tripping) and must state where Thompson propensity enters the
joint (it is captured in telemetry) · the stamp-rate tripwire's denominator is
allowlist-scoped (partial rollout must not read as build failures) · fixture-power
rule: the arm-A golden, B2 provenance test, and T1 sabotage test all run against a
fixture producing m < 1.0 on at least one non-A arm in the same job (no vacuous
passes) · degraded-map BEHAVIOR rule: seams treat a degraded map as identity even when
the build was slow-but-valid (discarded by design, not just stamped) · the build-time
knob read path: negmem reads `model_config` via `database.get_config()` directly
(leaf-legal) OR the server reads via `_c` and passes values into `build_map` — LLD
picks ONE and notes the two-read-paths drift surface (the knobs also live in
`_DEFAULT_CFG` for D-8 snapshots).
Signatures + NegmemMap dataclass; the admission SQL fragment + predicate pair; decay/
shrinkage formulas and the D-5 combine rule (product vs min) with fixtures; netting
magnitude + decrement-vs-reset; the R1(d) join path (impression↔decision; asymmetric
retraction note); the bulk-read SQL + S6 budget number; knob table with disposition
sentences + seed rows; stamp payload schema + ver; readout output format + RFPS/GR4
SQL (with the R-X frozen-cohort artifact format); test plan incl. the T1 sabotage,
the likes-you-led-deck batch test, per-path goldens, and the C4 empty-table parity.

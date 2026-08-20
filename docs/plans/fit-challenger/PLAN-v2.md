# PLAN v2 — fit arm + serving re-light + measurement rail (MERGED, authoritative)

**Date:** 2026-08-20
**Status:** authoritative build plan. Supersedes [PLAN.md](PLAN.md) (build order absorbed);
the PRD ([PRD.md](PRD.md)) remains the product spec and its §3 knockouts remain
operator-CLOSED.
**How this was produced:** two adversarial drafts
([PLAN-v2-draft-A.md](PLAN-v2-draft-A.md) build-first,
[PLAN-v2-draft-B.md](PLAN-v2-draft-B.md) risk/measurement-first), full cross-critique
([CRITIQUE-of-B.md](CRITIQUE-of-B.md), [CRITIQUE-of-A.md](CRITIQUE-of-A.md)), then this
synthesis. Where the drafts agreed, this plan states the result without re-arguing. The
drafts and critiques stay in-tree as the reasoning record.

**Scope (operator-approved 2026-08-20):** build bake-off arm `fit` per the PRD; re-light
interleaved serving so arms produce per-arm user decisions; land the measurement rail
(knob log, bucketed readout, tester cadence per
[../trade-engine-accuracy/PLAN.md](../trade-engine-accuracy/PLAN.md)).

---

## 1. Resolutions of the disputed points

Both agents conceded the majority of each other's machinery (recorded in the critiques'
Concessions sections — all of those adoptions are binding here). The synthesis rulings on
what remained:

| # | Dispute | Ruling | Reason |
|---|---|---|---|
| R-1 | Arms served during the **screen** weeks (W1–W2) | **B + D + C rostered** (3 arms; C self-caps by supply) | C zero-cards in boardless leagues so it costs ~218 ms and no decisions there; its boarded-league dilution is acceptable while the B-vs-D read needs only ~1.5 wk of the 3-wk window. Honors the operator's variety goal where it is nearly free. B's league-captivity point is conceded — **C's served like-rate is never used as a verdict**, only its diagnostics |
| R-2 | Arms served during the **fit round** | **k = 2: B + fit only** (`include_challenger = 0`, `include_gen_v2 = 0`) | B's arithmetic survived cross-examination: ~60–65 bucketed co-primary decisions/wk at k=4 puts a 10pp read at 4–5 wk. Where power binds, variety yields. D re-enters after the fit verdict if its own round was ambiguous |
| R-3 | Sensitivity laddering | **Screen at 15pp / non-inferiority, confirm at 10pp only if needed** (A's ladder) inside B's pre-registered promote/iterate/kill frame | The PRD's own success criterion is non-inferiority on `both_high`+`mixed`; generator-level effects are large (prod basis split is ~17pp); precision belongs to the confirmatory read |
| R-4 | Prod dark soak for fit | **Yes — F5b `bakeoff_serve_fit` bit, 3-day soak** with B's numeric exit bars | A withdrew its no-soak position once the serve-bit dissolved the roster=serving coupling; 3 days (not a week) because every soak target (p95 ms, cards/run, junk/pick shares) lands per-run |
| R-5 | Mid-window knob change | **Censor at the logged timestamp** — split the window, keep both segments; **discard** only for re-ranker contamination or an *unlogged* change (snapshot-diff-detected) | M1's log makes knob changes recoverable; discarding ~400 decided cards for a timestamped Wednesday flip wastes the program's scarcest resource. Trap-5 discard keeps its original scope |
| R-6 | 3-week contamination ceiling | **Review trigger, not design constraint** — a round crossing it gets its snapshot-diff audit read before its verdict is trusted; the schedule is built to fit inside it anyway | The ceiling's evidence base predates the machinery this plan builds |
| R-7 | Control-arm freeze | **Arm B frozen for the duration of any round**; the accuracy-plan Phase-3 queue consumes *between-round* Monday slots only, severity escape clause: a tripped guardrail is fixed same-day and the window is censored at the fix | B's rule with A's escape clause |
| R-8 | S0 volume auto-kill | **Softened**: fit ≤ 1.2× arm B distinct ideas at S0 → operator decision, not automatic no-roster | The PRD says success is not "more cards"; the scorer/presentment change can move like-rate at equal volume |
| R-9 | Deck-shrink tripwire | median < 22 investigate same day; **median < 18 on 2 consecutive days → revert**; SC2 target median ≥ 24; daily cadence during any transition week | A's tightening of B's bar (a 35% shrink never tripped B's < 15) |
| R-10 | `trade.outlook_direction` flip (operator already inclined, pending their confirm) | **W0, before any serving window opens**, logged via M1 | One arm-B baseline change, landed pre-measurement, is strictly cleaner than a mid-program W3 slot. If the operator declines, nothing else moves |
| R-11 | Readout parity | **M3 generation-time `fit_diag` stamp on every bake-off card** (all arms), version-pinned, testably inert | Without it the bucketed co-primary compares fit's best buckets against arm B un-bucketed — biased *for* fit (B's catch) |
| R-12 | SC6/SC9 fixes | SC6 restated **per-arm** (n bars are per arm, per B §2.2); SC9 replaced by B's **within-regime** pooled-like-rate tripwire (fit pooled < 5% for a week at n ≥ 100 → pause) | Both were miscalibrated as drafted (B's catches) |

## 2. Tickets (merged)

Estimates from the drafts; owners are repo role skills. Detail specs live in the PRD (F)
and draft B §3 (M); deltas from the critiques are folded in.

| ID | Ticket | Est | Depends | Binding notes |
|---|---|---:|---|---|
| M1 | Knob log: `model_config.updated_at` + `model_config_changes` table; every write path funnels through one helper; `scripts/set_knob.py` blessed CLI (`source='operator'`) | 0.5d | — | Schema change → full gates, own scope block (`scope-measurement.md`). Raw-SQL bypass caveat stands (A's R5): bypassed writes are *dated but unattributed*; snapshot-diff (§4) catches them and triggers discard |
| M2 | Readout pack: `scripts/bakeoff_readout.sql` + runbook §; encodes §4 metrics, the config-snapshot diff, and never splits fit by `basis` (C4 — analysis keys on `features_json.fit.boards ∈ {both, viewer, none}`) | 1d | M1 | Friday = 30-min execution, not authoring |
| M3 | Diagnostic fit-score stamp: score every bake-off card post-ranking with the fit scorer → `features_json.fit_diag = {you, them, bucket, ver}`, try/except, never read by any ranking path | 0.5d | F3 | Inertness enforced by `test_fit_diag_inert` (delete stamp from every card → served deck identical) |
| M4 | Tripwire queries: daily deck-median, position balance, re-ranker bypass assertion, per-arm error/forfeit, ghost share, max single-tester share, `fit_diag` null-share per arm, serve-bit leak (`model_arm='fit'` while `bakeoff_serve_fit=0` → stop) | 0.25d | M2 | The four rows A added to B's failure table are in |
| M5 | Tester protocol committed: `docs/plans/trade-engine-accuracy/tester-protocol.md` + runbook § (≥40 decided/wk, always a decline reason, ≥1 real send attempt, onboarding = board ≥100 votes + declared outlook) | 0.25d | — | |
| F1 | Knockout module wrapping live K1–K7 + `fit_r5_mode` (default 1 = kill; 0 = score into viewer lens) | 1d | — | T1: import the **module** (`ts.overpay_ok(...)`), never bind names. K3 evaluated **last** (expensive predicate). No K-math changes |
| F2 | Enumerator: union pool, 1-for-1 then expand, `fit_max_packages_per_pair` enforced, §2.6-contract counters built in | 2d | F1 | |
| F3 | Dual 0–100 scorer + `fit` payload incl. `bucket` + `boards` + `ver`; aggregate sort; unranked-pair tie-break by consensus fairness (C7c); tanh comment fixed, curve pinned by value table (C7a: 0→50, ±200→73.1/26.9, ±400→88.4/11.6) | 1.5d | F2 | T3: all lenses read **raw** member boards + raw seed, never `shrunk_elo` — docstring + `test_fit_lens_provenance_raw` |
| F4 | Post-score preference filters + R4 + C4 caps + `fit_junk_floor` pre-built default-off | 0.5d | F3 | |
| F5 | Bake-off arm `fit` behind `bakeoff_include_fit` (default 0); diagnostics onto `arms_json`; fit appended last in generation order (arm B stays first — dark fallback) | 1d | F3 | T2: `fit_diag`/`fit` ride `features_json` (no new columns); every row writes every key, nulls never absent |
| F5b | Serve-bit `bakeoff_serve_fit` (default 0): fit generates + logs, excluded from draft participants | 0.5d | F5 | Fit-only bit, not a general mechanism (generalize on the second consumer) |
| F6 | Test suite (union of both drafts' §6/§7 lists — the drafts' test names are the spec) | 1d | F1–F5b | Includes `test_fit_gate_binding_sabotage` (T1), `test_impressions_uniform_columns` (T2), `test_draft_rank_only` (C7b), `test_serve_fit_bit_excludes_from_draft`, `test_fit_r5_mode_knob`, `test_zero_card_arm_deck_still_fills` (S1b), `test_organic_never_imports_fit` |

**T4 discharge (blocking):** all 16 new `model_config` keys (the PRD §9 set +
`fit_r5_mode`, `fit_junk_floor`, `bakeoff_include_fit`, `bakeoff_serve_fit`) registered in
`trade_service._DEFAULT_CFG` — which also puts them in `snapshot_config()` → `config_json`,
the mechanism the contamination diff depends on — plus `_PINNED_KNOBS` and a disposition
sentence in `docs/plans/three-model-bakeoff/scope-phase2.md`, same commit, D-095 wording:
*"generation knob for `trade_gen_fit`, a module arm A never imports; no effect on
MODEL_A_PROFILE output."* F5 does not merge until the guard passes with all sentences.

Total ≈ 10 eng-days. Critical path F1→F2→F3→F5→F5b; M1/M2/M4/M5 parallel and merge first.

## 3. PR sequence

| PR | Contains | Merge gate (all: CI green — pytest, `tsc --noEmit`, testid-lint) |
|---|---|---|
| PR-M | M1 + M2 + M4 + M5 | `test_model_config_log.py` green; migration additive; data-dictionary + config-reference rows in-PR; `scope-measurement.md` filled |
| PR-S | S1b regression test + re-ranker-bypass code-walk + TestFlight checklist doc + `scope-serving.md` | tests green; **no knob values change in-PR** — flips are config, post-merge, logged |
| PR-F1 | F1 + F6 knockout tests + T4 for F1 keys | knockout tests + T1 sabotage green; no bake-off hook |
| PR-F2 | F2 + F3 + M3 + F6 scorer tests + T4 for pool/scorer keys | fixture scores frozen (inputs pinned, HANDOVER trap 7); curve table green; provenance green; `test_fit_diag_inert` green |
| PR-F3 | F4 + F5 + F5b + dry-run TEST_LEDGER + T4 for roster/serve keys | dry run recorded; organic byte-identical proof; knob-inventory guard green (16 sentences); operator yes on rostering |

Ordering: PR-M → PR-S (flips after both) ∥ PR-F1 → PR-F2 → PR-F3. Every PR branches from
freshly fetched `origin/main`.

## 4. Measurement design (adopted from draft B §2 with the §1 rulings applied)

Draft B §2.2 (metric definitions), §2.3 (contamination rules, amended per R-5/R-6/R-7),
§2.4 (SQL), §2.5 (pre-registered promote/iterate/kill), and §2.6 (diagnostic contract with
C2/C5 fields and numeric bars) are adopted as written except:

- Co-primary 1 is **bucket-matched via M3's `fit_diag`** on all arms (R-11).
- Per-arm n bars: 10pp ≈ 300 decided (paired-adjusted ≈ 255); 15pp ≈ 130 (≈ 110). Screen
  reads at 15pp/non-inferiority; confirm at 10pp (R-3).
- Window handling per R-5 (censor at logged timestamp; discard only re-ranker/unlogged).
- Small-n honesty rules verbatim: Wilson intervals; deltas < 3pp read "did not move";
  nothing called before its pre-registered n.

Failure-mode table = draft B §6 **plus** A's four rows (serve-bit leak; cross-round arm-B
drift check; `fit_diag` null-share per arm; max single-tester share) **with** the R-9
tripwire tightening. M4 implements every detection query.

## 5. Rollout schedule

All transitions are `model_config` writes via `scripts/set_knob.py` (logged). Rollback at
every stage is one knob. Monday boundaries; Friday readouts filed to
`docs/plans/fit-challenger/readouts/2026-Wnn.md`.

**W0 — build + dry run (no serving change).**
Merge PR-M, PR-S; build F1–F6. Offline dry run: replay boards (league
`1312140920132497408`) + fixture league + one 16-team SF roster, full §2.6 diagnostic set,
fixture ms recorded → operator sets the ms fail bar (closes scope.md §6). Volume check per
R-8. *If the operator confirms the `trade.outlook_direction` flip, it lands this week
(R-10).* Baseline M2 readout snapshotted.

**W1 — screen round opens (the week's one engine-affecting change).**
`bakeoff_serve_interleaved = 1` · `bakeoff_group_size = 0` · `bakeoff_deck_limit = 30` ·
roster B + D + C (R-1). TestFlight-only app ⇒ the user base is the tester base; no
allowlist. Operator runs the S3 TestFlight checklist within the hour; SC1 (first
non-`current` decision) within 3 days; SC2 median ≥ 24; daily tripwires armed (R-9).
Tester brief goes out (M5 protocol).

**W2 — screen continues (no change).** Friday: first full B-vs-D readout (10pp read
expected ~1.5–2 wk at realized supply).

**W3 — fit rosters dark.** `bakeoff_include_fit = 1`, `bakeoff_serve_fit = 0`,
`fit_max_packages_per_pair = 5,000` first, other knobs PRD §9 defaults. **3-day soak
bars:** p95 total_ms ≤ 30 s, fit ≥ 15 cards/run boarded, `top_q_junk_share ≤ 0.10`,
`top_q_pick_share ≤ arm B + 10pp`, `killed[K7]` reported. Operator same-hour canary on
their own deck. R0 (B-vs-D) verdict filed Friday; D's lever evidence goes to the accuracy
plan's Phase-3 queue as evidence, not as a mid-round change.

**W4 — fit round opens (k = 2, R-2).** `bakeoff_serve_fit = 1`,
`bakeoff_include_challenger = 0`, `bakeoff_include_gen_v2 = 0`. Arm B frozen for the round
(R-7). Screen read at 15pp/non-inferiority resolves as early as ~1 wk; if ambiguous, the
round continues to the 10pp n (~2.5–3 wk at k = 2).

**W5–W7 — round continues → pre-registered verdict** (draft B §2.5: promote / iterate one
knob / kill — each names its next action). Promote path: F7 dual-R5 knob flip with
`killed[K7]` evidence, `fit_min_them` tuning, then any organic-path conversation. Kill
path: `bakeoff_serve_fit = 0`, `bakeoff_include_fit = 0`, findings memo; D re-enters if
its round was ambiguous.

**gen_v2 re-entry condition (unchanged from B):** serves again when ≥ 2 leagues have 3+
boards. Its diagnostics keep accruing in dark generation throughout.

## 6. Evidence plan (D-056)

Union of the drafts' evidence sections: the F6 test list (§2), code-walk proofs (organic
isolation; serve-bit path trace: fan-out includes fit / draft excludes it / `arms_json`
records it; M3 stamp site post-ranking inside try/except; draft rank-based), the W0
dry-run + W3 soak TEST_LEDGER entries, the operator TestFlight checklist at W1 and W4
(draft B §7's 8-step list), and weekly readout files as standing runtime evidence.
Full gates, no express — schema (M1) + config surface + analytics is triple bright-line.
`FTF_SKIP_SIM_GATE=1` standing posture with evidence noted.

## 7. Docs + living-memory owed

Draft A §7's table is adopted with B's additions: `scope-measurement.md` +
`scope-serving.md` (owed before PR-M/PR-S merge), `readouts/` directory, the
cross-client-invariants n/a note, and the accuracy-plan reconciliation line (this plan's
W1 = its Phase 1.1; W1–W7 = its Phase 2 loop; its Phase-3 queue consumes between-round
slots only). ADRs: "fit-challenger is a generator, not a profile"; "screen-then-confirm
serving rounds, arm B always seated" (the §1 rulings are architecture for every future
arm). DECISIONS.md entries grep max-ID immediately before writing.

## 8. Risks accepted (carried from the drafts, post-critique)

| # | Risk | Why accepted |
|---|---|---|
| 1 | Serving re-lights before fit exists; testers see B/D/C for ~2 weeks | Attribution is per card; a week of B-vs-D decisions is the program's first per-arm signal ever, and it reads arm D's levers before anyone commits them to arm B |
| 2 | `group_size = 0` discards lane-quota telemetry | 79 runs of lane data banked; the binding question is per-arm like-rate; quotas are what killed serving last time. One knob restores composition |
| 3 | Knob log covers funneled writes only | Bypassed writes are dated-not-attributed; snapshot diff catches them; consequence defined (discard) |
| 4 | C's boarded-league dilution during the screen | Bounded (~23% of that league's deck); C's served like-rate is never a verdict input; W1–W2 has power margin |
| 5 | `fit_r5_mode` / `fit_junk_floor` shipped dark and speculative | One-line reads, ruled defaults, pre-wired precisely so activation is a knob not a deploy mid-window |

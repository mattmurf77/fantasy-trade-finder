# Calibration readout spec — counterparty breaker (v1)

**Status: PREREGISTERED. Committed before `trade.breaker` first lights**, per [HLD](HLD.md) **D-6**
(per-class maturity ladder — a class graduates only from its own row) and **R-3** (calibration
theater: an aggregate match-rate is not a finding, and a metric quoted before its cell fills is
worse than no metric). This document IS the artifact those two commit to. It materializes
[LLD](LLD.md) §8; where the two ever disagree, the LLD is the spec and this file is the defect.

**Date:** 2026-08-21 · **Evaluator version in scope:** `brk-1` · **Template version in scope:** `brt-1`
**Flags:** `trade.breaker` (compute + stamp), `trade.breaker_narrative` (the on-card line) — both
default OFF at the time of writing.

**Freeze rule.** The **TBD-operator** cells below are filled by the operator before flag-on and then
**frozen**. Changing a frozen cell afterwards requires a **new `ver` window** — the accrued cohort is
kept, but the gate is read only at the new value and the two windows are never pooled. Everything
*not* marked TBD is already binding and is not an operator question.

**Reading order for anyone running this:** §1 (what may be joined at all) → §2 (boundaries — most
readouts die here) → §3 (coverage, which gates `trade.breaker` on its own) → §4 (the per-class
calibration table, which gates narration) → §5 (reported-never-gated) → §6 (the SQL artifact).

---

## 0. Populations — and which one is the verdict

Three populations exist. Only one of them decides anything in v1.

| # | Population | Role in v1 |
|---|---|---|
| (a) **Counterparty-seat** | the mirrored card was served to the counterparty within the A-5 window AND they filed a coded pass reason | **Long-horizon accumulator. Never a launch gate.** Implied n ≈ 0–2/month at the ~3.7 % mirrored-serve rate (A-5, itself unverified). Not to be cited in any graduation or v2 argument until its cell prints **n ≥ 30**, which v1 will not see. Quoting it earlier is the R-3 failure mode by name |
| (b) **Viewer-seat shadow** | `features_json.breaker_shadow.top` vs the **viewer's own** filed layer-2 code | **PRIMARY.** Labeled **proxy validation**, with its selection caveat stated in every report: the viewer files reasons today, the counterparty does not; the shadow answers "does this predicate machinery predict the seat it is aimed at" and not "does it predict the counterparty" |
| (c) **Cross-seat consistency** | the [HLD](HLD.md) §2.7 mirrored-predicate check | Population-independent third signal. Reported; never a gate |

**Selection caveat, verbatim obligation:** every (b) number is printed with the sentence *"viewer-seat
proxy — the viewer chose to pass, the counterparty was never asked"* or an equivalent that survives
being read alone. A precision figure that escapes its caveat becomes a claim about the counterparty
within one retelling.

**Banned outright:** an **aggregate** match-rate across classes, in any form, as a success claim.
"Always predict `value_giving`" scores ≈40 % aggregate on the current filed-reason mix (n=208) —
so the aggregate number measures the mix, not the model. Per-class rows only (HLD D-6, R-3).

---

## 1. Join

```
deck_impressions.features_json  ⨝  trade_pass_reasons   ON impression_id
```

Binding join rules:

1. **`ver` filter is mandatory.** Rows whose `breaker.ver` is null are the synthetic
   `flag_flip_or_unstamped` marker written at log time — degraded, never "covered", **never joined**.
   Calibration keys on `ver`; the narration A/B keys on the pair (`ver`, `tmpl_ver`). Cross-version
   pooling refuses rather than degrades.
2. **`is_ghost = 0`, unconditionally** — see §2.1.
3. **`other_text` rows are excluded from every per-class precision denominator.** They are unmatched
   by construction (the breaker never emits `other_text`), so counting them as misses would
   understate precision by a quantity that is really "the taxonomy did not offer them a word".
   Hand-coding `other_text` free text into breaker classes is **forbidden** — see §4, `roster_crunch`.
4. Only rows with `key_source = 'impression'` join the F1 spine. A `local:` surrogate key cannot be
   joined to an impression and is therefore out of every calibration denominator (it still counts in
   the raw filed-reason baseline of §4.1, which is computed on `trade_pass_reasons` alone).

---

## 2. Boundaries — restated verbatim, because most of a wrong readout happens here

### 2.1 No ghost rows, ever

Operator ruling 2026-08-21 (batch-wide): **no ghost cards, full stop.** `ghost_holdout_one_in`
10 → 0 @ **00:43:32Z**, made durable in Receipts' next ship. Every design in this spec is
served-cards-only by construction and none uses ghost impressions in either direction; the
historical `is_ghost = 1` rows (which end at that boundary) are excluded from every breaker readout.
**The `is_ghost = 0` filter is applied regardless** of whether the window is believed to contain any
— a filter that is only correct because of a fact about the data is a filter that rots.

### 2.2 The D-091 phantom-pick window

**2026-08-16 → 2026-08-19 excluded** from any baseline. Not narrowed, not "probably fine for value
classes" — excluded.

### 2.3 The two 1QB QB repricing seams

`qb_1qb_cap_elo` moved **1785 → 1644 @ 04:46Z** and again **1644 → 1717 @ 11:48Z** (2026-08-21; the
knee stays 1200). QB **value optics are not comparable across either seam.** Any cut touching
`value_giving` severities, or any per-class row where QBs are a material share of the assets, censors
at both timestamps. Both are logged in `model_config_changes`, so the M1 rail catches them
automatically — which is exactly what makes §2.4 dangerous.

### 2.4 The code-ship boundary — **invisible to `model_config_changes`** — LANDED 2026-08-22

**BOUNDARY PINNED (2026-08-22, supersedes the "Monday" forecast):** the
`fix/package-benchmark-sweetener` ship merged EARLY by operator election —
**[PR #162](https://github.com/mattmurf77/fantasy-trade-finder/pull/162), `main` = `d42872f`**,
Render deploy following immediately. The merge SHA is the boundary marker; the bracketing
`model_config_changes` rows date it. It re-benchmarks the package depth discount to **the
trade's best asset** (the "4 mids for a stud scored fair" defect, analysed in
`docs/reviews/2026-08-21-market-curve-comparison.md`, now on `main`). The breaker's
`value_giving` math reads package-adjusted values, so **its severities inherit the semantics
change**. Rollback note: **D-143** records the pair-rollback rule — the benchmark fix and the
sweetener revert TOGETHER, never separately.

**This is a code deploy. The M1 `model_config_changes` rail will NOT censor it.** The readout
censors at the `d42872f` deploy explicitly, and per the LLD §3.4 sequencing sentence the
**calibration cohort starts at or after that deploy — a condition now SATISFIED**: any
`trade.breaker` flag-on from here starts a clean post-fix cohort. Every severity formula in the
LLD reads as *post-fix* semantics. ~~TBD-operator deploy timestamp~~ — resolved by the pinned
SHA; `value_giving` rows are readable for stamps at/after it.

**Two cohort facts from the same ship:** (1) sweetened cards (`features_json.gap_sweetener`
non-null) exist in served decks from this deploy forward — the §2.5 cut is live-relevant from
day one; (2) **arm C is benched** (`bakeoff_include_gen_v2` = 0 @ 2026-08-22T16:37Z, logged)
until its sweetener extension lands — per-arm cuts should expect **no fresh `gen_v2`
impressions** during the opening cohort window and must not read the empty cell as signal.

### 2.5 `gap_sweetener` — an optional cut, never a silent state

The same ship adds a generation-time **auto-sweetener** (equalizer asset at consensus gap > 1539)
which stamps `features_json.gap_sweetener` — **present on every row, null when absent** (name
confirmed 2026-08-21, sibling tip `0e04d30`). Sweetened cards are ordinary cards to the breaker and
are evaluated as-is. The readout therefore carries an **optional cut** on that key — sweetened vs
unsweetened reported separately **when the operator asks** — rather than pooling two populations
without saying so. Not a gate, not a stratum; a cut that exists so the state is never invisible.

### 2.6 Arm-A invariance

`package_bench_trade_wide` and `package_floor_cross` are pinned **0.0** in `MODEL_A_PROFILE`, so
**arm A is byte-invariant across the §2.4 code-ship boundary** (superseding the earlier "re-capture
the golden" plan — there is no re-capture). Per-arm cuts may therefore treat **arm A as the fixed
reference** while arms B / C / fit move across it. Nothing in this spec cites the old golden SHA.

### 2.7 The standing rule

Every measurement window censors at logged `model_config_changes` timestamps (M1 rail, live since
PR-M) — **plus** the explicitly named code-ship boundary in §2.4, which that rail cannot see.

---

## 3. Coverage & degraded share — the `trade.breaker` gate

`trade.breaker` graduates on this section alone; no calibration number is required for it.

**Definitions (arithmetic, not vibes).** Over served impressions in the window, after §2:

- **Denominator** = all served impressions on flag-on decks (`is_ghost = 0`).
- **Scored** = `breaker.ver` non-null **AND** `breaker.objections` non-null **AND**
  `breaker.degraded` null. Nothing else counts as covered.
- **Not covered**, enumerated so the residual is never a mystery bucket:
  - `ver: null` → the synthetic `flag_flip_or_unstamped` marker (log-time, module possibly never
    imported — hence the honest null version);
  - `degraded` non-null → the rung ladder: `partner_snapshot` (1) · pass-2 `budget` skip (2) ·
    `budget_exhausted` (3) · `exception_card` / `self_partner` (4) · `exception_outer` (5).
- **Coverage** = scored ÷ denominator. **Bar: ≥ 99 %** (NFR-6 / M-G1).
- **Degraded share** = (rung 1 + rung 2 + rung 3) ÷ denominator. **Bar: < `breaker_degraded_share_max`**
  (default 0.05). Rungs 4–5 are reported separately and investigated rather than budgeted — an
  exception is a defect, not a degradation allowance.
- **`predicate_error` is counted separately and is NOT part of degraded share.** A per-class predicate
  exception is contained to its class: the card stays **rung 0 and covered**, with that class carrying
  `skipped: "predicate_error"`. It is durable in `features_json`, therefore countable, and it is
  reported as **per-class `predicate_error` share** (numerator: cards where class *c* carries the
  marker; denominator: scored cards). A non-trivial share on any class means that class's precision
  row is being computed on a biased subset and the row is flagged, not read.
- **Cost:** `breaker.ms` p50 / p95 against `breaker_ms_budget` (250 ms, 60-card basis), plus p95
  **job** time unregressed vs the flag-off baseline. A pre-flag-on dry-run ms number goes to the
  operator first (M-G2).

**Sum check, always printed:** scored + `ver:null` + rung1..5 = denominator, exactly. A readout whose
buckets do not sum is not reported with a note; it is not reported.

---

## 4. Per-class calibration gate table — the narration gate

**A class graduates only from its own row.** No class inherits another's evidence, and no aggregate
row exists (§0).

**Two baselines, both required.** A class must beat **BOTH**:

- **B1 — majority-class:** always predict `value_giving`. ≈ **40 %** aggregate on the filed-reason mix
  at n = 208 — **re-derived at readout**, never pasted from here.
- **B2 — stratified-random:** draw from the filed-reason distribution within the same stratum.

### 4.1 The table

| Class | min n (cell) | required margin over B1 (majority-class) | required margin over B2 (stratified-random) | Notes |
|---|---|---|---|---|
| `fit_outlook` | **TBD-operator** *(proposed 50)* | **TBD-operator** *(proposed ≥ +10 pts)* | **TBD-operator** *(proposed ≥ +10 pts)* | reported per `outlook_src` stratum **separately** — never pooled across `declared` / `legacy` |
| `fit_new_weakness` | **TBD-operator** *(proposed 50)* | **TBD-operator** *(proposed ≥ +10 pts)* | **TBD-operator** *(proposed ≥ +10 pts)* | **envelope rows only** (§4.3) |
| `fit_duplicate` | **TBD-operator** *(proposed 50)* | **TBD-operator** *(proposed ≥ +10 pts)* | **TBD-operator** *(proposed ≥ +10 pts)* | **envelope rows only**; realistically does not reach gate n inside v1 |
| `value_giving` | **TBD-operator** *(proposed 50)* | **TBD-operator** *(proposed ≥ +10 pts)* | **TBD-operator** *(proposed ≥ +10 pts)* | reported per **basis** stratum; the `consensus` stratum is flagged **near-tautological** (R-4) and read with that flag attached |
| `other_player_keep` | — | — | — | **dark class.** Calibration-reported only; **no graduation target in v1** — it may never render a sentence (it would advertise that we read the counterparty's private keep-list) |
| `roster_crunch` | — | — | — | **extension code: no filed-reason anchor exists.** No manager has ever been offered it as a pass reason. Measuring its precision against hand-coded `other_text` is **FORBIDDEN** (`other_text` is excluded by construction, §1.3). **Its row may remain unpassable in v1 — stated, not hidden** |

### 4.2 The min-n consequence note (register item 16 — binding, not a footnote)

At **n = 50** a **+10-point** margin is ≈ **1–1.4 SE**. Therefore:

- Graduation at the proposed numbers is **PROVISIONAL**, and is paired with a **re-read at n ≈ 100**.
  It is reversible at rollback **rung 2** (per-class narrate switch / `breaker_min_severity`) — no
  deploy, no revert.
- **Horizons scale ~linearly with min-n.** At n = 100: `fit_outlook` / `value_giving` reach gate n in
  **2–4 weeks**; `fit_new_weakness` in **10–16 weeks** — i.e. out of v1 entirely.
- Any min-n change lands **before `trade.breaker` lights** (a P1 precondition). A later change **keeps
  the accrued cohort**, with the gate simply read at the new n.
- Min-n does **not** move the **n = 130/side** claim bar — different population, different question.
  M4 lift and M-G5 degradation claims stay bound to 130/side regardless of what min-n becomes.
- **The PRD §4.1 realism column and register item 17's throughput argument are FUNCTIONS of this
  item.** If min-n moves, recompute both; do not carry the old prose forward.

### 4.3 Stratification (minimum, pinned)

**`outlook_src` × board basis** — `outlook_src` ∈ {`declared`, `legacy`}, board basis ∈
{`board`, `board_suspect`, `consensus`}. Primary stratum for the proposed defaults:
`consensus` basis × `legacy` outlook_src.

- **Every reported precision carries its cell n.**
- **Cells below min-n print `insufficient`.** They are never pooled silently, never rounded up into a
  neighbour, and never quoted with a "directionally" qualifier.
- **Envelope-gated classes** (`fit_new_weakness`, `fit_duplicate`, `roster_crunch`) are read on
  **envelope rows only** — rows where the depth classes actually ran. A card outside the v1 format
  envelope (14-team, IDP, non-Sleeper) carries `skipped: "format_gap"` for those classes; counting it
  as a miss would measure the envelope, not the predicate.

---

## 5. Reported, never a gate

Printed in the same readout, each with its cell n, none of them able to graduate anything:

- **Class entropy of `top.code`** (weekly). This is the **D-7 anti-wallpaper red line** and it is
  checked **before any narration graduation** — it can *block*, but it cannot *pass* a class.
- **Per-class fire rate** (share of scored cards where class *c* is `top`).
- **Degraded share by rung**, including the `flag_flip_or_unstamped` bucket, and the per-class
  `skipped: "predicate_error"` share (§3).
- **`ms` p50 / p95.**
- **Mirrored-serve narration-divergence count** — the R-6 monitor, re-read at the A-5 cadence.
- **The three-cell narration readout** (D-7 / M7): every scored card on a narration-flag-on deck lands
  in exactly one of

  | Cell | Meaning |
  |---|---|
  | **narrated** | `breaker.narrated` non-null — a sentence rendered |
  | **suppressed** | a candidate existed and was withheld; broken out by reason: `below_floor` · `repetition` · `class_ineligible` · `format_gap` · `template_error` |
  | **no objection** | `top` null — nothing cleared its class floor |

  The three cells **sum to the scored population** on a narration-on deck; the sum is printed. The
  point of the middle cell is that "we had something to say and chose not to" must be visible and
  attributable, not inferred from a shortfall between the other two.
- **The optional `gap_sweetener` cut** (§2.5), on request.
- **M3 counterparty-seat**, **M4 lift**, **M5 propose counts**, **M6 filter counterfactual** — per the
  PRD §4.1 verdicts. M6 is the v2 earn-in and is read pooled-across-arms first, per-arm as
  confirmation, both with cell n.

---

## 6. The graduation SQL is a reviewed artifact, not composed at readout time

Per [LLD](LLD.md) §7.6 item 2, the queries behind §3 and §4 ship as a **`scripts/`-style artifact**
following the fit arm's [`scripts/bakeoff_readout.sql`](../../../scripts/bakeoff_readout.sql)
precedent, so the graduation query is **code-reviewed before it is trusted**, dual-dialect, and
diffable across readouts. This is required by §8 of the LLD and is **owed before `trade.breaker`
lights**, alongside the TBD-operator cells above.

**Status of that artifact: NOT YET WRITTEN.** It is a P1 precondition, not a v1 stretch item.

## 7. Preconditions checklist before `trade.breaker` lights

| # | Item | Status |
|---|---|---|
| 1 | Every **TBD-operator** cell in §4.1 filled and frozen | **open** |
| 2 | The §2.4 deploy timestamp recorded | **open** |
| 3 | The §6 readout SQL artifact written and reviewed | **open** |
| 4 | Dry-run `ms` number delivered to the operator (M-G2) | **open** |
| 5 | This document re-read against the LLD §8 skeleton for drift | done 2026-08-21 |

Before `trade.breaker_narrative` lights, add: the PRD §8.3 **19-step manual TestFlight checklist**,
run by the operator on a build containing the element, logged verbatim in
[`living-memory/TEST_LEDGER.md`](../../../living-memory/TEST_LEDGER.md). It is the **only** runtime
evidence this feature gets (D-056), and it is **unrun**.

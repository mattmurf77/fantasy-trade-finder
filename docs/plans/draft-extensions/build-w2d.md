# Build status — W2d: re-balanced calibration split + create-contract gaps

**Date:** 2026-08-06 · **Wave:** draft-extensions W2d · **Status:** _in progress — §1 is the PRE-REGISTERED decision, written and committed before the fit was run_
**Predecessor:** [build-w2c.md](build-w2c.md) → [build-w2b.md](build-w2b.md) → [build-w2.md](build-w2.md)
**Gate artifact (I-10):** [mock-calibration-2026-08d.md](mock-calibration-2026-08d.md) (08 / 08b / 08c kept as history)
**Spec:** [plan.md](plan.md) §5 + amendments · [lld.md](lld.md) §2.3 / §3.3 / §4.2.3

---

## 1. PRE-REGISTERED DECISION — the gate change, recorded before it was run

> **This section was authored and committed in its own commit BEFORE the harness
> was modified or the fit re-run.** A gate change decided after seeing its own
> results is worthless; the separate commit is the evidence of ordering. Nothing
> below was revised after the numbers came in — corrections, if any, appear in
> §4 as explicit deviations.

W2c's verdict (FAILED, both paired-mean bars) localised its own cause: the
observable drifts **2.017 slots** between the fit block (Lakeview r1–2, observed
mean 1.870) and the hold-out (r3–4, observed mean 3.886) — twice the ±1.0 bar,
inside one corpus, before any model. `d` is a *rank* distance and the consensus
value curve is steep at the top and flat in the tail, so the fit block is
systematically the shallowest part of the draft. The operator's decision is
**option A (re-balance the split) plus option B (add corpora)**. Practice/replay
(rejected) is not on the table, and no bar, α, tie rule, model family or `d_i`
definition moves.

### 1.1 The new split — alternating interleave over the retained pick sequence

Take `lakeview-complete`'s 48 picks **in draft order**, drop the picks the
consensus cannot price (the unchanged `reach_report` `skipped` rule) to get the
**45 retained picks**, indexed `0..44` in draft order. Then:

| Block | Rule | n |
|---|---|---|
| **Fit** | retained picks at **even** index (0, 2, 4, …) | 23 |
| **Hold-out** | retained picks at **odd** index (1, 3, 5, …) | 22 |

Block sizes are **identical to W2c's** (23 / 22), so every n, SE and bar
comparison against 08c is like-for-like and the change is visible as a change of
*composition*, not of *power*.

**Why alternation, and not stratified sampling from both ends** (both were
offered; one had to be chosen and justified):

1. **Determinism.** Alternation is a pure function of the corpus — no RNG, no
   seed, nothing an operator could re-roll until the gate passed. A stratified
   sample needs either an RNG or an arbitrary within-stratum rule, and both are
   degrees of freedom the gate should not have.
2. **The finest possible depth balance.** Adjacent retained picks sit one draft
   slot apart, so alternation pairs every fit pick with its immediate
   neighbour. The two blocks' depth distributions therefore match at the
   granularity of a single pick. Stratified-by-round sampling balances only to
   *round* granularity — it would still let the two blocks differ by up to half
   a round of depth, which on this corpus is ~6 slots.
3. **Every round is in both blocks.** Each 12-pick round contributes 6 picks to
   each block (±1 where a pick was skipped), so no round is fit-only or
   hold-out-only and no round-level idiosyncrasy can be mistaken for a model
   failure.

**Not changed, deliberately:** the hold-out is still never fitted; the fit
objective is still W₁ on `|d|` over the same 110-point grid; the observable is
still the remaining-pool `d_i`; ties are still average-rank over the tied block;
unvalued picks are still excluded and counted.

### 1.2 The precondition that makes the split un-skewable

A new test, **T-W2-19**, asserts the balance **before** the fit consumes the
split, so it can never silently re-skew (e.g. if a corpus is re-recorded or the
`skipped` set changes):

* **Depth balance.** `|mean(draft position of fit block) − mean(draft position
  of hold-out block)| ≤ 1.0 pick.` The tolerance is one pick position — the
  finest granularity the observable has, and the number the ±1.0 mean bar is
  denominated in.
* **Round balance.** In every round, `|count(fit) − count(hold-out)| ≤ 1`.

Stated as a bar, in the test, in the same units as the gate. If either fails the
suite goes red and the split has to be re-derived deliberately.

### 1.3 The corpora — one added

| Corpus | Role | Why it qualifies |
|---|---|---|
| `lakeview-complete` | fit (interleaved) + hold-out (interleaved) | unchanged from W2a/b/c |
| `mfl-complete` | independent, **no refit** | unchanged |
| **`mfl-partial`** | **independent, no refit — NEW** | single `draftUnit`, 6 rounds ⇒ rookie-shaped (≤ `ROOKIE_MAX_ROUNDS`), 36 of 72 picks made and all in rounds 1–3. Already shape-checked by T-W2-17 and unused since M1. `mfl-multi-unit` stays excluded — it is a two-unit conference split, so "the pool as it stood at that pick" is not well defined across units; that exclusion is about units, not round count |
| `mfl-made0`, `startup-shaped`, `ffv3-predraft`, `empty-drafts` | excluded | **no made picks at all** — nothing to measure |

**How the new corpus enters the gate:** as its **own** independent validation
block with **both** bars applied to it, exactly like `mfl-complete`, with **no
refit**. The gate therefore becomes **six bars** (KS + paired mean on each of
three validation blocks) where W2c had four. Adding a corpus this way can only
make the gate **harder** to pass, which is the point: it removes any suspicion
that the corpus was added because it helps.

**Pricing:** `mfl-partial` is priced `1qb_ppr`, the same default `mfl-complete`
uses. Neither MFL corpus records league scoring settings — the fixture is a
`draftResults` export only — so this is an assumption, and it is the *same*
assumption already recorded for `mfl-complete` (whose `sf_tep` alternative was
tested and rejected in 08c §3). It is recorded here rather than discovered
later.

### 1.4 What is FROZEN

Restated so the diff can be checked against it: **the model family** (the W2b
two-parameter `bpa_prob` + Gumbel-reach mixture), **both bars** (KS not rejected
at α = 0.05; `|Δ mean|d|| ≤ 1.0`), **α = 0.05**, **the ±1.0 constant**, **the
tie rule** (average rank over the tied block, applied identically to observed
and simulated series), **the unvalued-pick rule** (excluded and counted), and
**`d_i`** (the remaining-pool reading). The two parameters `mock_bpa_prob` and
`mock_reach_decay` **may** be re-fitted — that is what a re-run means.

### 1.5 What a pass and a fail each commit to

* **All six bars pass** ⇒ flip `CPU_MODEL_VALIDATED = True`, remove the create
  route's `cpu_model_unvalidated` short-circuit, keep the both-directions gate
  test intact. `draft.mock` still ships **OFF**.
* **Any bar fails** ⇒ `CPU_MODEL_VALIDATED` stays `False` and the short-circuit
  stays. If the failure is again the paired-mean bar *and* the blocks' SEs still
  exceed ±1.0, the artifact says so with the numbers and states plainly whether
  the bar is measurable at the available sample size. **The bar is not widened
  unilaterally under any outcome.**

---

## 2. RESULT — the gate still FAILS, and the residual moved again

Full numbers in the gate artifact [mock-calibration-2026-08d.md](mock-calibration-2026-08d.md).

| Stage | Block | n | Bar | Result | |
|---|---|---|---|---|---|
| Fit | Lakeview, interleaved fit | 23 | min W₁ over 110 points | **0.10 / 0.70**, interior, W₁ **0.329** | ✓ |
| Hold-out | Lakeview, interleaved | 22 | KS α=0.05 | D 0.198, p **0.317** | **PASS** |
| Hold-out | " | 22 | \|Δ mean\| ≤ 1.0 | obs 3.591 / sim 1.943 ⇒ **1.648** | **FAIL** |
| Independent | `mfl-complete` | 28 | KS | D 0.147, p **0.546** | **PASS** |
| Independent | " | 28 | \|Δ mean\| ≤ 1.0 | obs 5.536 / sim 1.930 ⇒ **3.605** | **FAIL** |
| Independent | **`mfl-partial`** | 29 | KS | D 0.219, p **0.108** | **PASS** |
| Independent | " | 29 | \|Δ mean\| ≤ 1.0 | obs 3.966 / sim 1.939 ⇒ **2.026** | **FAIL** |

**Verdict: FAILED.** `CPU_MODEL_VALIDATED` stays `False`, the create route's
`cpu_model_unvalidated` short-circuit **stays**, `draft.mock` stays OFF, and the
both-directions gate test is intact (now over all six bars).

Every corpus's own observed mean and n:

| Corpus / block | n | own observed mean | sd | SE |
|---|---|---|---|---|
| `lakeview-complete` fit (even idx) | 23 | 2.152 | 2.786 | 0.581 |
| `lakeview-complete` hold-out (odd idx) | 22 | 3.591 | 6.237 | 1.330 |
| `lakeview-complete` whole draft | 45 | 2.856 | 4.793 | 0.715 |
| `mfl-complete` | 28 | 5.536 | 11.380 | 2.151 |
| `mfl-partial` | 29 | 3.966 | 5.130 | **0.953** |

### 2.1 The split change worked — and that is what makes the rest readable

The depth gap between the blocks went from **23.42 picks to 0.028**, and the
observable's block difference from **2.017 to 1.439 slots** — the residual 1.44
being ~1.1 SE of the hold-out block's own mean, i.e. sampling noise on a heavy
tail rather than structure. W2c's diagnosis is therefore **closed**: the split is
no longer the cause.

### 2.2 The bar's measurability — the operator's question, answered

Adding a corpus did exactly what W2c predicted. **`mfl-partial`'s SE is 0.953,
inside the ±1.0 bar** — the first block where the paired-mean bar is a real test
— and the model **fails it by 2.13 standard errors**. The other two blocks
(SE 1.330 and 2.151) remain wider than the bar and cannot reject on their own.

So: the ±1.0 mean bar is **not** measurable at n = 22 / 28 on the heavy-tailed
Lakeview and `mfl-complete` blocks, **is** measurable on `mfl-partial`, and the
failure there is genuine rather than a power artifact. **No bar was widened.**

### 2.3 Where the residual actually lives now — the candidate window

`cpu_pick` only ever scans `available[:MOCK_CANDIDATE_WINDOW]`, so every
simulated `d` is bounded at **11.5**. Seven of the 102 validation picks reach
**13 to 51.5** slots — probability *exactly zero* under the shipped model — and
they carry **1.34 / 4.04 / 1.24** slots of the three blocks' observed means,
which is essentially the whole paired-mean gap.

This is W2a's failure shape (a model whose support excludes observed data) now
living in the **product cap `K`** rather than in the noise family. `K` is
explicitly **not** a fitted parameter, so **W2d did not touch it** — choosing it
by what makes the gate pass is the fit-on-the-validation-set move amendment 2
exists to prevent. It is published as evidence and left to the operator as a
product decision ("how deep a reach still reads as conviction"), to be taken on
its own terms and only then re-gated.

---

## 3. THE DELIVERED CONTRACT (G1–G3) — read this alongside `docs/api-reference.md`

### G1 — the create route now resolves all four engine inputs

`POST /api/mock-draft` previously passed **none** of `order`, `order_source`,
`ownership`, `personas`, so every mock was randomized-order, every traded pick
was silently discarded, and every CPU team was `{outlook: "not_sure"}` — which
pins `need_weight` at one alpha for the whole field and makes the entire
`outlook_alpha` persona mechanism inert.

| Input | Source | Degradation |
|---|---|---|
| `order` (slot → user id) | round-1 `original_user_id` from `draft_board_service.build_board` — **the Draft Room's own cached board**, single-flight, budgeted, breaker-guarded | `order_confidence != "assigned"`, or a partial slot map ⇒ **no order**; the engine's seeded shuffle takes over |
| `order_source` | `"assigned"` iff a complete real order resolved, else `"randomized"` | always present, echoed in `settings_echo.order_source` — **never an invented "real" order** |
| `ownership` (traded picks) | board entries with `is_traded` → `(round, slot) → current owner`, translated to `{pick_no: user_id}` by `build_settings(traded_slots=…)` | dropped with the order — a traded pick is meaningless without the slots it trades between |
| `personas` | `league_preferences.team_outlook` (`declared`) → `trade_service.infer_team_outlook` (`inferred`) → `not_sure` (`default`) | a member with no roster is omitted; `build_settings` fills the default |

**Sleeper only.** MFL's grid states the *current* pick owner and never the
original, so it cannot distinguish a slot order from an ownership overlay;
reading it would produce an "order" that is really a trade log. An MFL league
stays `randomized` and says so.

**Why `traded_slots` and not `ownership` from the route:** the platform states a
trade as `(round, slot) → new owner`; the persisted shape is `{pick_no: owner}`,
and the pick number depends on *this* mock's `rounds`/`teams`/`type`. Only
`build_settings` knows those, so it owns the translation. An explicit
`ownership` entry still wins, so a replayed row is unaffected.

**Client obligation:** render `settings_echo.order_source == "randomized"` as a
visible disclosure ("we shuffled the order — your league hasn't set one yet").

### G2 — the capability probe

`GET /api/mock-draft` with no active mock now returns, alongside
`{"empty": true, "reason": "no_active_mock"}`:

```json
"capability": {
  "can_start": false,
  "reason": "cpu_model_unvalidated",
  "teams": 12,
  "min_teams": 4,
  "rounds_default": 4,
  "rounds_max": 8,
  "type": null,
  "order_source": null
}
```

* `reason` is `null` when `can_start` is `true`; otherwise it is **the same
  string the create route's typed-empty would carry**, because both read one
  ladder — `mock_draft_service.start_refusal`, ordered `class_not_loaded` →
  `cpu_model_unvalidated` → `league_too_small`. The probe can never promise
  something the create route then refuses.
* **Today it always answers `can_start: false, reason: "cpu_model_unvalidated"`**,
  because the gate is closed. That is the disabled entry state to build against.
* The probe is a DB + process-pool read — **no platform call**, preserving the
  GET path's zero-egress property. It deliberately does not use
  `_mock_league_context` (which resolves the lineup template and every rookie
  row: the cost of *starting* a mock, not of *asking*).
* `type` / `order_source` are populated only when a caller supplies them; the
  route leaves them `null`. **For the setup toggle, read `type` from
  `GET /api/draft/board`** (below) — the client already holds that payload.

**Also delivered:** `league_too_small`. `teams` was `len(owners)` with no floor,
so a 2-team league got a 2-team "mock". `MOCK_MIN_TEAMS = 4`; below it the
create route returns the typed-empty `league_too_small` and the probe reports it.
The floor ships in `capability.min_teams` so the client hardcodes nothing.

**Also delivered:** `GET /api/draft/board` now carries **`type`** ∈
`"linear" | "snake" | null` — Sleeper's `detail.type`, MFL's
`draftType` (`SAME`→linear, `REVERSE`→snake). `null` whenever the platform
states no shape we recognise; **never a guess**, because an invented shape
renumbers every pick.

### G3 — recap deltas

`picks[]` entries gain three fields:

| Field | Meaning |
|---|---|
| `consensus_rank` | the player's 1-based position in the **frozen pre-draft** consensus pool. Frozen, so a pick's delta does not move as later picks come off the board |
| `consensus_delta` | `consensus_rank − pick_no`, signed in the **ADP convention**: **positive = went LATER than the consensus said** (value); negative = a reach. `+3` reads "the consensus had him 3 slots earlier than where he went" |
| `valued` | `false` for a D7 unvalued rookie (present on the board, sorted last) |

`consensus_rank` and `consensus_delta` are **`null`, never `0`**, when the
consensus cannot place the player — render "no consensus value", not an even
delta. `settings_echo.consensus_pool_size` is the denominator for "12th of 79".
The client never needs the full class ordering.

---

## 4. What changed

| File | Change |
|---|---|
| `backend/tests/test_mock_draft.py` | the interleaved split (`_interleaved_split`, `_lakeview_blocks`), `INDEPENDENT_CORPORA` + `_independent_block`, full-draft simulation with index selection, six-bar `all_pass`; **new** T-W2-19 precondition + `test_w2_19_the_rebalanced_split_removes_the_depth_drift`; the three W2c diagnostics re-stated for W2d; **new** `test_w2_16_the_candidate_window_cannot_produce_the_deepest_observed_reaches`; **new** T-W2-20 block (12 tests) for G1/G2/G3 |
| `backend/mock_draft_service.py` | `REASON_NO_ACTIVE_MOCK` / `REASON_LEAGUE_TOO_SMALL` / `MOCK_MIN_TEAMS`; **new** `start_refusal` + `capability`; `build_settings(traded_slots=…)`; `state_payload` picks carry `consensus_rank` / `consensus_delta` / `valued` and `settings_echo.consensus_pool_size`; `empty_payload(reason, capability_info)`; fitted default `mock_bpa_prob` 0.20 → 0.10; the gate comment, `CALIBRATION_ARTIFACT` and the `MOCK_CANDIDATE_WINDOW` comment re-pointed at 08d; `reach_report`'s stale test reference and split-dependent claim corrected |
| `backend/server.py` (mock route region) | **new** `_mock_capability`, `_mock_real_draft`, `_mock_personas`; create path passes all four G1 inputs and reads the shared refusal ladder; GET returns `capability` |
| `backend/draft_board_service.py` | board payload gains `type` (+ `TYPE_LINEAR`/`TYPE_SNAKE`/`_MFL_DRAFT_TYPE`) |
| `backend/tests/test_draft_board.py` | schema pin updated for `type` |
| `docs/plans/draft-extensions/mock-calibration-2026-08d.md` | **the new I-10 gate artifact** |
| `docs/api-reference.md` · `config-reference.md` · `glossary.md` · `architecture.md` | per the CLAUDE.md trigger table |

**Not touched:** any `mobile/` file · `backend/database.py` · `_MODEL_CONFIG_DEFAULTS` ·
`MOCK_CANDIDATE_WINDOW`'s value · every W1/W3 file · the corpora themselves ·
the model family, both bars, α, ±1.0, the tie rule and `d_i`.

## 5. Deviations worth stating

1. **The pre-registration is its own commit.** The brief named one commit; §1
   was committed separately *first* so the ordering of decision-then-result is
   verifiable in the history rather than merely asserted. Nothing in §1 was
   revised afterwards.
2. **`reach_report`'s stationarity argument was split-dependent and is
   corrected, not deleted.** The static-rank reading drifts far harder than the
   remaining-pool one under the round-based split (3.56 vs 2.02) but slightly
   *less* under the balanced one (1.16 vs 1.44) — most of its excess drift *was*
   the depth term. The choice of reading is unchanged; it now rests only on the
   argument that survives (a frozen-pool reading scores a pure-BPA draft as a
   large fall by construction, so it cannot falsify a noise model).
3. **The refusal order is the shipped route's, not the one that reads "most
   permanent first".** `class_not_loaded` still outranks `cpu_model_unvalidated`,
   preserving an existing tested contract.
4. **The POST typed-empty body stays byte-identical to M2's** — `capability`
   rides the GET only. The `reason` is the information on a refused create, and
   a client that got that far already read the probe.
5. **`mfl-partial` is priced `1qb_ppr` by assumption.** Neither MFL cassette
   records league scoring settings; this is the same assumption already recorded
   for `mfl-complete`. Stated in 08d §3 rather than discovered later.
6. **`mfl-partial` retains 29 of 36 made picks.** Six MFL player ids are absent
   from the committed DynastyProcess crosswalk and one is unpriced by the
   consensus. Pre-existing `_mfl_corpus` behaviour; counted and published rather
   than left as a discrepancy against the fixture README's "36/72 made".
7. **`mobile/` typecheck could not be run in this worktree** — `mobile/node_modules`
   is not installed here. The claim it exists to support is proved directly
   instead: `git status --porcelain -- mobile/` is empty, so no mobile file was
   touched.

## 6. Gates

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **1881 passed / 1 skipped, exit 0** (baseline 1867/1; +14 = 13 new W2d tests + 1 split test) |
| `cd mobile && npx tsc --noEmit` | **not runnable here** (no `node_modules` in this worktree); `git status --porcelain -- mobile/` is **empty** — `mobile/` untouched, as required |
| `test_w2_16_calibration_gate` | green **because it asserts the FAILURE is still real** — `all_pass is CPU_MODEL_VALIDATED` (`False`), now over six bars |
| T-W2-19 (split precondition) | green — depth gap 0.028 picks, tolerance 1.0 |
| Amendment 1 (no second consensus) | `test_w2_14_the_service_declares_no_second_consensus` (AST, no `sorted`/`.sort`) + `test_w2_15_..._element_for_element` still green |
| Zero platform egress | T-W2-13's three checks still green; the G2 probe adds no platform read |

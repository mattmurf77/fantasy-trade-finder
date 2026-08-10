# Status — G2 backend build (#290 / #292 / D-16 / D-5)

> **Phase 2 — backend only.** The mobile half of #291 and #292 is a separate
> agent running after this merges. Branch `worktree-agent-a7185764ba235f8b7`,
> based on `feedback-289-294` @ `e73e3ae`.
>
> Spec: [`prd.md`](./prd.md) · [`lld-delta.md`](./lld-delta.md) ·
> [`hld-delta.md`](./hld-delta.md) · [`scope.md`](./scope.md) ·
> [`reconciliation-log.md`](./reconciliation-log.md)

---

## Table of Contents

- [1. Base and merge note](#1-base-and-merge-note)
- [2. A Phase 1 defect the orchestrator must resolve](#2-a-phase-1-defect-the-orchestrator-must-resolve)
- [3. What shipped](#3-what-shipped)
- [4. Measured results](#4-measured-results)
- [5. Discrimination proofs](#5-discrimination-proofs)
- [6. Test results](#6-test-results)
- [7. Requirement to implementation to test](#7-requirement-to-implementation-to-test)
- [8. Knowing deviations](#8-knowing-deviations)
- [9. For the orchestrator to apply](#9-for-the-orchestrator-to-apply)
- [10. QA checklist](#10-qa-checklist)

---

## 1. Base and merge note

**The worktree came up on the wrong base and was corrected before any work.**

- Worktree started at `16b1dcb` ("changelog: odds surface audit") — a lineage
  from a concurrent Outlook/odds session, **not** the batch branch. The
  `docs/feedback/items/290-mock-draft-engine/` spec directory did not exist.
- `16b1dcb` is a clean **ancestor** of `feedback-289-294` @ `e73e3ae`:
  `git rev-list --count e73e3ae..16b1dcb` = **0**. No divergent commits, so the
  fix was a fast-forward, not a merge.
- After `git merge --ff-only e73e3ae` the base contains, newest first:
  `e73e3ae` (#289 docs) · `ad641a6` (merge of G1's worktree) ·
  `bc8a85c` (Phase 1 planning artifacts) · `03d4c87` (**G1 backend**, MFL
  identity) · then `16b1dcb` and the earlier `origin/main` history.

**This branch therefore contains G1's merged work and carries no unrelated
commits.** It should merge cleanly into `feedback-289-294`.

---

## 2. A Phase 1 defect the orchestrator must resolve

**Rounds 2 and 3 of the adversarial review are not in the repository.**

`reconciliation-log.md` contains **Round 1 only** — its own table of contents
lists a single section, "Round 1 — Author". `git log --all -- docs/feedback/items/290-mock-draft-engine/`
returns exactly one commit (`bc8a85c`). Searching every ref for
`MOCK_RUN_MIN_OFFSET`, `abandon_completed_mock_drafts` and `T-290-14` returns
nothing.

My build instructions carry four Round-2/3 corrections that **contradict the
committed PRD and LLD**. I verified each against the code before acting, and
**all four are correct** — a build to the committed documents would have
shipped three of these defects:

| # | Committed doc says | Instruction says | Verified in code |
|---|---|---|---|
| **D-5 aggregate** | `lld-delta.md` §4.1: `max()` over severities | denominator-weighted | **Instruction right.** `_BENCH_TARGET` gives TE `(S,B)=(1,0)` (`mock_draft_service.py:201`), so `severity("TE") == 1.0` for any roster without a 1280+ TE. Under `max()` the tilt is `1.0` for nearly every August roster and `effective_bpa_prob` returns `bpa_prob` unchanged — **D-5 would have shipped inert.** |
| **#292 backend** | `prd.md` §2.3 / `lld-delta.md` §7.5: "no backend change at all" | needs `abandon_completed_mock_drafts()` | **Instruction right.** `load_current_mock_draft` (`database.py:10762`) falls back to `status="complete" ORDER BY id DESC LIMIT 1`, and nothing prunes complete rows. Abandoning mock N uncovers mock N-1: the dismissal **paginates**. |
| **`MOCK_RUN_MIN_OFFSET`** | absent from PRD and LLD | ship `= 1` | **Instruction right, and I reproduced the blocker.** At `0`, `sf_tep` forces pick 1.01 in **100%** of mocks with **24** distinct top-4 orderings — passing both of the PRD's one-sided bars (`>= 0.43`, `>= 12`). `1qb_ppr` is unaffected. See §5. |
| **stale docs** | `scope.md` §2.2: five locations | six | **Both right.** Five are orchestrator-owned docs; the sixth is `backend/feature_flags.py:462`, a code comment, which I fixed. |

Two further instruction items I could **not** reconcile to any document and had
to derive — flagged in §8 as knowing deviations:

- the exact **two-sided bar table** ("exactly as tabulated") — no table exists;
  I set every bound from measurement and proved each discriminates (§5).
- `T-290-11`'s shipped upper-bound reference of **171** — I measure **149** at
  the pinned `N = 500`. The requirement ("must fail on shipped code") is met
  either way; the bound is 80.

**Nothing here blocked the build, but the reconciliation log should be brought
up to date before this batch closes** — the next reader of these documents will
reproduce the `max()` and #292 defects.

---

## 3. What shipped

### `backend/mock_draft_service.py`

| Added | Purpose |
|---|---|
| `import statistics` | stdlib, no I/O; the import allow-list test stays green |
| `MOCK_RUN_GAP_MULTIPLE = 2.5`, `MOCK_RUN_MEDIAN_WINDOW = 9` | the adaptive gap rule (D-9) |
| `MOCK_RUN_CROSS_ALLOWANCE_LATE = 1` | D-6's rounds-3+ softening |
| **`MOCK_RUN_MIN_OFFSET = 1`** | the floor that prevents the `sf_tep` collapse |
| `MOCK_IDIOSYNCRASY_FLOOR = 0.25` | D-5's "idiosyncrasy survives" |
| `run_boundaries()` | the raw gap rule — single forward walk, no `sorted`/`.sort` |
| `run_offset()` | distance to the last considerable row, floored and clamped |
| `aggregate_severity()` | **denominator-weighted**, not `max()` |
| `effective_bpa_prob()` | the need-conditional mixture weight |
| `_severity_targets()` | split out of `_severities` so the denominators are reachable |

Changed: `cpu_pick` gains a `targets` keyword and reads `effective_bpa_prob`
for its single Bernoulli — **the scoring loop is byte-identical**;
`advance_cpu` and `simulate_reaches` compose `min(cap, run_offset(...))` at the
existing `reach_cap` seam, **identically** (R-6/G-6), and only when `cap > 0` so
the spent-budget case stays strict best-available verbatim.

### `backend/server.py` — G2's `/api/mock-draft` region

- `_MOCK_MFL_MEMBER_RE`, `_mock_owner_name()`, `_mock_usernames()` — one shared
  identity helper on G1's four-tier ladder, one `load_league_members` call.
- Wired at **both** D-16 sites: `_mock_league_context` (create) and
  `_mock_context_from_row` (**resume — every GET and every `/pick`**).
- `mock_draft_abandon_route` clears the completed-mock backlog (#292).

### `backend/database.py`

- `abandon_completed_mock_drafts(user_id, league_id) -> int` — owner-scoped,
  idempotent, leaves `active` and already-`abandoned` rows alone.

### `backend/feature_flags.py:462`

- The stale `draft.mock` NOTE corrected: the flag is **ON** and
  `CPU_MODEL_VALIDATED` is **True**. This is the only doc-class change applied.

### `backend/tests/test_mock_draft.py`

17 new tests; one shipped helper corrected (`_reach_draws`, §7.2 of the PRD —
`needs = 0.0` → `1.0`, with the cancellation argument in the docstring). **No
shipped assertion was edited.**

---

## 4. Measured results

Pinned board (`ktc_blend_pipeline_2026-07-17`), 12-team linear, explicit order,
user last, **N = 500** (pinned — the distinct-orderings statistic scales with N).

### Per format, as implemented at `MOCK_RUN_MIN_OFFSET = 1`

| Statistic | shipped | **1qb_ppr** | **sf_tep** | bar |
|---|---|---|---|---|
| P(consensus #1 at 1.01) | 0.456 | **0.456** | **0.650** | `0.35 – 0.85` |
| P(consensus #1 falls past pick 3) | 0.180 | **0.100** | **0.040** | `<= 0.12` |
| P(consensus #7 at pick <= 4) | 0.102 | **0.000** | **0.000** | `<= 0.02` |
| P(Carnell Tate falls past pick 4) | 0.194 | **0.076** | **0.076** | `<= 0.10` |
| distinct top-4 orderings | 149 | **39** | **33** | `28 – 80` |
| median run size (raw gap rule) | — | **5.0** | **5.0** | `4 – 5` |
| `run_offset(head, allow_cross=0)` | — | 3 | **1** (floored) | `>= 1` |

**The shipped engine's numbers are identical on both formats.** That is not a
copy-paste error — it is root cause (a) demonstrated directly: the shipped model
scores list position and never reads `row["value"]`, so two boards with the same
89 ranks and completely different value curves produce the same distribution.

**Median run size is 5.0 on both formats**, matching the PRD's prediction, and
it is an emergent property of the value curve — no size clamp (D-9).

**`P(Tate past pick 4)` is not zero and is not asserted to be.** Tate is the
consensus #2 and shares a run with Tyson and Lemon (46.1 and 71.1 Elo). Under
the value-gap rule the operator asked for, Tate at pick 4 is legitimate; PRD §4
is explicit that driving it to zero would encode the wrong model. It falls from
19.4% to 7.6%, and *who* can now go ahead of him is the real change.

### The D-10 tripwire — did NOT fire

`test_w2_16_calibration_gate` passes unmodified: `report["all_pass"] is False`
still. No escalation needed.

### G-2 regression bar

`pytest -k "w2_16 or w2_17 or w2_19"` — **8 passed** after the change; the same
8 passed in the pre-change baseline run. The gate's KS bars are not asserted by
the test (the module records at `:1857-1867` that they have failed since W2e,
because the fitted parameters and the caps disagree — pre-existing, not a
regression from this change). No artifact re-published, per D-10.

---

## 5. Discrimination proofs

Every proof was run by temporarily installing the defective version, observing
the failure, and reverting. All three reverts verified green afterwards.

### Proof 1 — D-16 keying

Reverted both sites to the shipped `{str(m.user_id): m.username for m in members}`
and `_mock_owner_name` to a passthrough. **Both tests failed:**

```
FAILED test_290_12_mfl_owner_names_never_render_a_machine_id
FAILED test_290_12b_the_username_map_itself_never_carries_a_machine_id
E  AssertionError: mfl:no-such-league-290-12b.f0001 ->
   'mfl:no-such-league-290-12b.f0001' still renders a machine id
```

`T-290-12b` exists because a test that only exercises the ladder helper passes
on the shipped code — the discriminating assertion has to run the **map
builder**.

### Proof 2 — `T-290-11`'s upper bound fails on shipped code

Neutralised the run rule (`run_offset` returns `n - 1`) and the need tilt,
leaving both call sites intact so `T-290-07` still passes:

```
E  AssertionError: 1qb_ppr: 149 distinct top-4 orderings over N=500.
   … above 80 it is not biting at all (149 = shipped).
E  AssertionError: 1qb_ppr: P(consensus #1 falls past pick 3) = 0.180
```

### Proof 3 — the collapse the one-sided bars missed

`MOCK_RUN_MIN_OFFSET = 0`, everything else shipped:

```
FAILED test_290_14_the_candidate_set_is_never_a_singleton
FAILED test_290_10 — sf_tep: P(consensus #1 at 1.01) = 1.000
FAILED test_290_11 — 1qb_ppr: 18 distinct top-4 orderings
```

At `0`, `sf_tep` yields **1.000** and **24** orderings — both of which **pass**
the PRD's one-sided `>= 0.43` and `>= 12`. The upper bound on the first and the
raised lower bound (28, not 12) on the second are what catch it, and
`T-290-14` catches it seedlessly and structurally in under a second.

---

## 6. Test results

| Run | Result |
|---|---|
| `pytest backend/tests/ -q` — **baseline** on this base, pre-change | **2308 passed, 1 skipped** (246.83s) |
| `pytest backend/tests/ -q` — **after** | **2325 passed, 1 skipped** |
| `pytest backend/tests/test_mock_draft.py -q` | **97 passed** (80 shipped + 17 new) |

Delta is **+17, all new tests**. No pre-existing test changed verdict; no
pre-existing failure was found or "fixed".

New tests: `290_01`, `290_03`, `290_04`, `290_05`, `290_06`, `290_07`, `290_08`,
`290_08b`, `290_09`, `290_10`, `290_11`, `290_12`, `290_12b`, `290_13`,
`290_14`, `292_01`, `292_04`.

---

## 7. Requirement to implementation to test

| Req | Implementation | Test |
|---|---|---|
| R-1 | `run_boundaries` / `run_offset` | `T-290-01`, `test_w2_14` (AST, unmodified) |
| R-2 | no size clamp | `T-290-03` (median 5.0 / 5.0) |
| R-3 | `allow_cross=0` in rounds 1-2 | `T-290-04` (exact) |
| R-4 | `MOCK_RUN_CROSS_ALLOWANCE_LATE` | `T-290-05` (bounded **and** proven to soften) |
| R-5 | `min()` at the `reach_cap` seam, skipped when `cap == 0` | `T-290-06` + `:332`, `:362` unmodified |
| R-6 | identical composition in both call sites | `T-290-07` (AST over both functions) |
| R-7 | `effective_bpa_prob` | `T-290-08` |
| **D-5** | **`aggregate_severity` denominator-weighted** | **`T-290-08b`** |
| R-8 | `MOCK_IDIOSYNCRASY_FLOOR` | `T-290-09` (two-sided) |
| R-9 / R-10 | no change to the noise family or the RNG stream | `:248`, `:472`, `:584`, `:607`, `:724` unmodified |
| R-11 | the engine change | `T-290-10` (two-sided, **per format**) |
| R-12 | — | `T-290-11` (two-sided, upper bound fails on shipped) |
| **new** | **`MOCK_RUN_MIN_OFFSET`** | **`T-290-14`** (seedless, structural) |
| R-14 / R-17 | `abandon_completed_mock_drafts` + route wiring | `T-292-01` (three rows), `T-292-04` |
| R-18 / R-20 | `_mock_usernames` at **both** sites | `T-290-12`, `T-290-12b` |
| R-19 | no id added to any player lookup | `T-290-13` (raising stub) |
| R-21 / R-22 | no route or import change | `:956-1056`, `:764`, `:787` unmodified |
| D-10 | — | `test_w2_16_calibration_gate` unmodified, **did not fire** |

---

## 8. Knowing deviations

1. **Two-sided bar values are mine, not the (missing) Round-3 table.** Every
   bound in §4 was set from measurement and each is proven to discriminate in
   both directions (§5). If Round 3 tabulated different numbers, reconcile
   against §4 — the measurements, not the bounds, are the durable artifact.
2. **`T-290-11`'s shipped reference is 149, not 171.** Measured at the pinned
   `N = 500`. The requirement is met: 149 exceeds the bound of 80.
3. **`P(Tate past 4) <= 0.10`, not `== 0`; `P(#1 past 3) <= 0.12`, not `0.05`.**
   The PRD's R-11 values were measured on the Round-1 prototype, which had no
   `MOCK_RUN_MIN_OFFSET`. The floor is what admits a one-slot reach past a wall
   — that is the *point* of the floor, and it is why `sf_tep` is not
   deterministic. Both bars still reject the shipped engine.
4. **`run_boundaries` was factored out of `run_offset`.** Not in the LLD. R-2's
   run-size statistic is a property of the gap rule; measuring it through
   `run_offset` reports every singleton run as a pair (it read median 4 / 3.0
   before the split, 5.0 / 5.0 after). Same forward walk, no second ordering.
5. **`cpu_pick` gains a `targets` keyword.** Unavoidable: `_severities` returns
   `{pos: severity}` and the denominators are not recoverable from it. Optional
   and defaulted to `None`, which reproduces every PRD endpoint for `T-290-08`
   exactly.
6. **`mock_draft_abandon_route` (`:11893`) is edited, which is ~360 lines past
   the stated `~11380-11530` region.** It is an `/api/mock-draft` route in G2's
   named family and no other lane claims it; a `database.py` function with no
   caller is not a fix. Flagging it because the line range was explicit.
7. **`_mock_owner_name`'s annotation avoids `Mapping`/`Any`.** `server.py`
   imports neither and has no `from __future__ import annotations`; it only
   parsed here because this runtime is Python 3.14 (PEP 649). Plain `dict | None`
   keeps it portable to the deploy runtime.

---

## 9. For the orchestrator to apply

Nothing in this section was applied by me — all orchestrator-owned.

### 9.1 Five stale doc locations (all verified still stale on this base)

Exact replacement text is already written in [`scope.md` §2.2](./scope.md) for
(a)–(c) and [`hld-delta.md` §12](./hld-delta.md) for (d)–(e). All five remain
correct as drafted; I confirmed each string is present and wrong:

| # | Location | Defect |
|---|---|---|
| (a) | `config/features.json:155` | "It stays OFF beyond the usual lands-dark convention"; cites the superseded `mock-calibration-2026-08.md` |
| (b) | `docs/config-reference.md:309` | default column reads `false`; "This flag stays OFF"; "`CPU_MODEL_VALIDATED` is `False`" |
| (c) | `docs/config-reference.md:565` | "`CPU_MODEL_VALIDATED` is `False`, the CPU-bot mock stays cut" |
| (d) | `docs/architecture.md:135` | "gated OFF by its own calibration verdict", "`CPU_MODEL_VALIDATED = False`", and "the routes never do" — now false |
| (e) | `docs/glossary.md:42` | "`CPU_MODEL_VALIDATED` is `False` and the create route answers a typed-empty" |

The **sixth**, `backend/feature_flags.py:462`, **is applied** in this branch.

**A seventh, found during the build and deliberately NOT fixed:**
`backend/mock_draft_service.py:31-32` — the module docstring still says *"The
last recorded verdict is **STILL A FAILURE**, so `advance_cpu` remains
unreachable from the routes"*. The first clause is true (the statistical
verdict is still FAILED); the second is **false** — `CPU_MODEL_VALIDATED` is
`True`, so the routes reach `advance_cpu` normally. This is the same defect
class as (d)'s "the routes never do". It sits in a file I own, but it was not
among the named six and fixing it is scope expansion, so it is reported rather
than applied. Proposed replacement for the second clause:

> `…re-gating**. The last recorded verdict is STILL A FAILURE, but the ship
> decision no longer follows from it: CPU_MODEL_VALIDATED was flipped True by
> operator override once W2e made the reach policy a product rule, so
> advance_cpu IS reachable from the routes. test_w2_16_calibration_gate pins
> the statistical verdict independently, so the two facts stay visible
> together.`

### 9.2 `docs/api-reference.md` — one sentence for #292

`lld-delta.md` §8 says no api-reference edit is needed. That was true of the
mobile-only #292; it is **not** true now that abandon clears the backlog.
Proposed, for the `POST /api/mock-draft/abandon` entry:

> Retires the named mock **and** every other `complete` mock the caller owns in
> that league, so a dismissal frees the room rather than surfacing the previous
> recap. Owner-scoped and idempotent; the request body is unchanged.

`GET /api/mock-draft`'s `order[].owner_username` also now resolves MFL franchise
names rather than synthetic member ids — same type and nullability, so this is
optional:

> On MFL leagues `owner_username` resolves through `league_members`
> (`username` → `display_name` → session username → `"Team <fid>"`) and is
> omitted rather than emitted empty.

### 9.3 `living-memory/DECISIONS.md`

Next id is **D-023** (`e73e3ae` added D-022). Proposed:

> **D-023 — a mock-draft "run" is engine-internal and denominator-weighted
> need is what makes D-5 real.** (2026-08-10) The #290 run rule partitions the
> consensus pool by a locally-significant value gap (`MOCK_RUN_GAP_MULTIPLE`
> × a 9-gap local median) and composes at the existing `reach_cap` seam via
> `min()`, so it can only tighten the operator's W2e policy. It deliberately
> does **not** reuse the 8-tier ladder or the cross-client tier enum — the
> second time that call has been made (#279 was the first). Two parameters are
> load-bearing and were both fixed by measurement, not taste:
> `MOCK_RUN_GAP_MULTIPLE = 2.5` (median run 5.0 on both scoring formats) and
> `MOCK_RUN_MIN_OFFSET = 1` (at 0, `sf_tep` forces pick 1.01 in 100% of mocks
> while `1qb_ppr` looks fine). Separately, aggregating positional need with
> `max()` is inert — TE's `(S,B) = (1,0)` makes `severity("TE") == 1.0` for
> almost every August roster — so the aggregate is denominator-weighted.

### 9.4 `living-memory/TEST_LEDGER.md`

> 2026-08-10 — G2 backend (#290/#292/D-16/D-5): `pytest backend/tests/ -q`
> **2325 passed, 1 skipped** (baseline on `feedback-289-294` @ `e73e3ae`:
> 2308 passed, 1 skipped; delta +17, all new). `test_mock_draft.py` 97 passed.
> D-10 calibration tripwire did **not** fire. No Maestro run — backend lane.

### 9.5 Reconciliation log

See §2. Rounds 2 and 3 are missing from the repo and should be written back.

---

## 10. QA checklist

### For the mobile agent (runs against this merged code)

- [ ] **The abandon route now clears the whole completed backlog.** After
      `POST /api/mock-draft/abandon`, `GET` returns
      `{empty: true, reason: "no_active_mock"}` — **not** the previous mock's
      recap. The client's "Start a new mock" primary can rely on this; before
      this change it would have surfaced mock N-1.
- [ ] `POST /api/mock-draft/abandon` still accepts a `complete` row and is
      idempotent — a double-tap on the recap's dismiss control is safe.
- [ ] `order[].owner_username` may now be a **franchise name** on MFL leagues,
      or **`null`** when nothing resolves. It is never `""` and never contains
      `"mfl:"`. `MockDraftScreen.tsx:284`'s
      `slot?.owner_username ?? String(onClock.roster_id)` fallback is correct
      and should stay — it will simply stop firing.
- [ ] No route contract changed: no new route, no new response key, `SCHEMA`
      unchanged. Nothing in the mobile API layer needs a type change.
- [ ] **Pre-existing persisted mocks replay differently** (G-5). Truncating the
      candidate list changes how many `_gumbel` draws the scoring loop consumes.
      A mock created before this merge and resumed after it will not match its
      old board. Expected; INV-10 promises one build replays a seed
      identically, not that two builds agree. Worth one release-note line.
- [ ] The backend half of #291 is **nil** — the pick path was already wired.

### For the batch QA round

- [ ] `draft.mock` is **ON in production**. There is no dark landing; this
      ships lit on merge. Treat the Maestro gate as load-bearing.
- [ ] Live-league check on an MFL league (Dependables, 62846): open a mock and
      confirm the on-the-clock card and the order rail show **franchise names**,
      not `mfl:…` ids — on a **resumed** mock, not only a freshly created one.
      The resume path (`_mock_context_from_row`) is the common case and was the
      site an earlier draft missed.
- [ ] Second-mock loop end to end: complete a mock → dismiss the recap → start
      another → reach the clock. Then do it a **third** time — the paginated
      bug only shows from the second dismissal onward.
- [ ] Sanity-check a superflex mock's round 1 by eye. It should be varied, not
      chalk: `P(#1 at 1.01)` is 0.650 there versus 0.456 on 1QB, which is
      correct (the superflex board's top gap is 82.6 Elo) but is a visible
      behaviour change from today's 0.456.
- [ ] Not covered by any automated test, by design: whether the operator agrees
      with the **consensus pricing** of Tate against Tyson and Lemon. If a
      post-fix mock still reads wrong at pick 4, that is a DP/KTC blend
      question in a different lane, not the mock engine — PRD §4.4.

# Status — G2 backend build (#290 / #292 / D-16 / D-5)

> **Phase 2 — backend only.** The mobile half of #291 and #292 is a separate
> agent running after this merges. Branch `worktree-agent-a7185764ba235f8b7`,
> merged up to `feedback-289-294` @ `a01efad` (full Phase 1 spec, G1 + G3).
>
> Spec: [`prd.md`](./prd.md) · [`lld-delta.md`](./lld-delta.md) ·
> [`hld-delta.md`](./hld-delta.md) · [`scope.md`](./scope.md) ·
> [`reconciliation-log.md`](./reconciliation-log.md) (Rounds 1-3)

---

## Table of Contents

- [1. Base and merge note](#1-base-and-merge-note)
- [2. Built against Round 1, realigned to Rounds 2-3](#2-built-against-round-1-realigned-to-rounds-2-3)
- [3. What shipped](#3-what-shipped)
- [4. Measured results at the pinned N = 1500](#4-measured-results-at-the-pinned-n--1500)
- [5. Failing-first evidence](#5-failing-first-evidence)
- [6. Test results](#6-test-results)
- [7. Requirement to implementation to test](#7-requirement-to-implementation-to-test)
- [8. Knowing deviations and findings](#8-knowing-deviations-and-findings)
- [9. For the orchestrator to apply](#9-for-the-orchestrator-to-apply)
- [10. QA checklist](#10-qa-checklist)

---

## 1. Base and merge note

The worktree came up at `16b1dcb` (a concurrent Outlook/odds lineage), which is
a clean **ancestor** of the batch branch — `git rev-list --count e73e3ae..16b1dcb`
= **0**, so the correction was a fast-forward, not a merge. Built on `e73e3ae`,
then merged `a01efad` once the full Phase 1 spec landed. **No unrelated commits.**

---

## 2. Built against Round 1, realigned to Rounds 2-3

The first pass was built when only Round 1 was committed. Four Round-2/3
corrections were reconstructed from code evidence at that point, and the
committed spec now confirms **all four**. Two things that had to be derived are
pinned differently in the real spec, and **the spec's values are what shipped**:

| | Derived in pass 1 | **Spec (authoritative)** | Now |
|---|---|---|---|
| N | 500 | **1500** | 1500 |
| shipped distinct orderings | 149 (at N=500) | **171** (at N=1500) | 171 reproduced exactly |
| T-290-11 bounds | 28–80 | **25–120** | spec's |
| T-290-10 bounds | 0.35–0.85 / ≤0.12 / ≤0.02 / ≤0.10 | **0.43–0.75 / 0.02–0.11 / ≤0.02 / ≤0.10** | spec's |
| D-5 function | `aggregate_severity(needs, targets=None)` | **`need_pressure(severities, targets)`** | renamed |
| D-5 plumbing | `cpu_pick(targets=…)` | **`cpu_pick(need_pressure_value=…)`**, `targets` hoisted per-mock | spec's |
| new tests | — | **T-290-15, T-290-16** | added |
| T-292-01 | 3 rows, owner-scoped | + **different-league** clause | added |

The 149-vs-171 disagreement was not a conflict — they were different
experiments. At the pinned N = 1500 the spec's figure reproduces **to the
digit** (§5). No bound in the shipped tests is one I set from my own
measurement; every one is the PRD's.

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
| **`need_pressure(severities, targets)`** | denominator-weighted, **not** `max()` |
| `effective_bpa_prob(bpa_prob, needs, pressure=None)` | the need-conditional mixture weight |
| `_severity_targets()` | split out of `_severities` so the denominators are reachable |

`cpu_pick` gains `need_pressure_value`; the scoring loop is **byte-identical**
and the per-position severity term that decides *what* a bot reaches for is
untouched. `advance_cpu` hoists `targets` once per mock (the lineup template
cannot change mid-draft) and both it and `simulate_reaches` compose
`min(cap, run_offset(...))` **identically**, only when `cap > 0`, and both pass
`need_pressure(...)`.

Also corrected the stale module docstring at `:31-32` (the seventh stale
location — "`advance_cpu` remains unreachable from the routes" is now false).

### `backend/server.py` — G2's `/api/mock-draft` region

`_MOCK_MFL_MEMBER_RE`, `_mock_owner_name()`, `_mock_usernames()` on G1's
four-tier ladder, one `load_league_members` call, wired at **both** D-16 sites
including the resume path. `mock_draft_abandon_route` clears the completed
backlog.

### `backend/database.py`

`abandon_completed_mock_drafts(user_id, league_id) -> int` — owner-scoped,
league-scoped, idempotent.

### `backend/feature_flags.py:462`

The stale `draft.mock` NOTE corrected.

### `backend/tests/test_mock_draft.py`

**18 new tests.** One shipped helper corrected (`_reach_draws`, PRD §7.2 —
`needs = 0.0` → `1.0`, cancellation argument in the docstring). **No shipped
assertion was edited.**

---

## 4. Measured results at the pinned N = 1500

Pinned board (`ktc_blend_pipeline_2026-07-17`), 12-team linear, explicit order,
user last, `for seed in range(1500)`.

| Statistic | shipped | **1qb_ppr** | PRD says | **sf_tep** | PRD says | bound |
|---|---|---|---|---|---|---|
| P(consensus #1 at 1.01) | 0.4553 | **0.4553** | 0.455 ✓ | **0.6380** | 0.638 ✓ | `0.43 – 0.75` |
| P(consensus #1 past pick 3) | 0.1553 | **0.0893** | 0.089 ✓ | **0.0420** | 0.042 ✓ | `0.02 – 0.11` |
| P(Carnell Tate past pick 4) | 0.1713 | **0.0733** | 0.073 ✓ | **0.0733** | 0.073 ✓ | `<= 0.10` |
| P(consensus #7 at pick <= 4) | 0.1147 | **0.0000** | 0.0000 ✓ | **0.0000** | 0.0000 ✓ | `<= 0.02` |
| distinct top-4 orderings | **171** | **39** | — | **33** | — | `25 – 120` |
| median run size (one-pass walk) | — | **5.0** | 5.0 ✓ | **5.0** | 5.0 ✓ | `4 – 5` |
| `run_offset(head, allow_cross=0)` | — | 3 | — | **1** (floored) | — | `>= 1` |

**Every PRD-tabulated figure reproduced to the digit.** The shipped column is
identical on both formats — root cause (a) demonstrated directly: the model
scores list position and never reads `row["value"]`, so two boards with the
same 89 ranks and different value curves give the same distribution.

`need_pressure` endpoints, also exact: all-filled **0.0**, TE-only hole
**0.1111** (`1/9`, *not* 1.0 — the assertion that catches the `max()` defect),
all-unfilled **1.0**, WR-corps hole **0.4444** > TE-only, and the three
`effective_bpa_prob` values `0.775 / 0.10 / 0.4375`.

### D-10 tripwire — did NOT fire

`test_w2_16_calibration_gate` passes unmodified at N = 1500:
`report["all_pass"] is False` still. No escalation.

### G-2 regression bar

`pytest -k "w2_16 or w2_17 or w2_19"` — **8 passed**, same as baseline. KS bars
are not asserted by the gate (the module records at `:1857-1867` that they have
failed since W2e because the fitted parameters and the caps disagree —
pre-existing, not a regression from this change). No artifact re-published.

---

## 5. Failing-first evidence

All five failing-first-mandatory tests, run at N = 1500 against the **tabulated**
bounds. Each defect was installed, the failure captured, then reverted and
re-verified green.

### (a) Unfixed engine — `run_offset` intact, composition removed

The faithful `7cea1fa` state: the function exists but is not wired into
`advance_cpu` / `simulate_reaches`, and no need tilt. (Neutralising `run_offset`
itself is *not* a valid reproduction — it is also the yardstick T-290-04 and
T-290-14 measure against, so it silences the very bound under test.)

```
FAILED test_290_04 — 1qb_ppr r1: pick at pool position 2 passed the head's
                     run boundary at 1 — the rounds-1/2 wall is not holding
                     assert 2 <= 1
FAILED test_290_10 — 1qb_ppr: P(consensus #1 falls past pick 3) = 0.1553
                     (shipped 0.155)   assert 0.1553 <= 0.11
FAILED test_290_11 — 1qb_ppr: 171 distinct top-4 orderings over N=1500
                     assert 171 <= 120
```

**171 exactly**, matching the PRD's shipped figure.

### (b) `MOCK_RUN_MIN_OFFSET = 0` — the collapse

```
FAILED test_290_14 — assert 0 >= 1  (where 0 = mds.MOCK_RUN_MIN_OFFSET)
FAILED test_290_10 — sf_tep: P(consensus #1 at 1.01) = 1.0000
                     assert 1.0 <= 0.75
FAILED test_290_11 — 1qb_ppr: 18 distinct top-4 orderings over N=1500
                     assert 25 <= 18
```

**18**, matching the PRD's tabulated "MIN = 0 collapse gives 18 / 24".
T-290-14 fails at the *cause*, seedlessly, in under a second; the two
distributional bars catch the same collapse from opposite sides. Round 1's
one-sided bars (`>= 0.43`, `>= 12`) **both pass** on this board — that is the
whole reason the bounds are two-sided.

### (c) T-292-01 — shipped single-row dismissal

Abandon only the newest `complete` row, as the shipped route did:

```
FAILED test_292_01 — cleared 1 rows, expected all 3 — the dismissal paginated
                     assert 1 == 3
```

Re-verified after the isolation fix in §8.3, so the failing-first property is a
real property of the test and not an artifact of leftover DB rows.

### (d) D-16 naive keying

Both sites reverted to `{str(m.user_id): m.username for m in members}` and the
ladder to a passthrough:

```
FAILED test_290_12  — mfl owner names never render a machine id
FAILED test_290_12b — mfl:no-such-league-290-12b.f0001 ->
                      'mfl:no-such-league-290-12b.f0001' still renders a
                      machine id
```

`T-290-12b` exists because a test that exercises only the ladder helper passes
on the shipped code — the discriminating assertion has to run the **map
builder**.

---

## 6. Test results

| Run | Result |
|---|---|
| `pytest backend/tests/ -q` — baseline, `feedback-289-294` @ `a01efad` | **2308 passed, 1 skipped** |
| `pytest backend/tests/ -q` — after | **2326 passed, 1 skipped** (531s) |
| `pytest backend/tests/test_mock_draft.py -q` | **98 passed** (80 shipped + 18 new) |

Delta **+18, all new tests**. No pre-existing test changed verdict; no
pre-existing failure found or "fixed".

New: `290_01`, `290_03`, `290_04`, `290_05`, `290_06`, `290_07`, `290_08`,
`290_09`, `290_10`, `290_11`, `290_12`, `290_12b`, `290_13`, `290_14`,
`290_15`, `290_16`, `292_01`, `292_04`.

---

## 7. Requirement to implementation to test

| Req | Implementation | Test |
|---|---|---|
| R-1 | `run_boundaries` / `run_offset` | `T-290-01`, `test_w2_14` (AST, unmodified) |
| R-2 | no size clamp; one-pass partition | `T-290-03` (median 5.0 / 5.0) |
| **R-2b** | **`MOCK_RUN_MIN_OFFSET = 1`** | **`T-290-14`** (seedless, primary collapse guard) + **`T-290-15`** (floor < round-1 cap) |
| R-3 | `allow_cross=0` in rounds 1-2 | `T-290-04` (exact) |
| R-4 | `MOCK_RUN_CROSS_ALLOWANCE_LATE` | `T-290-05` (bounded **and** proven to soften) |
| R-5 | `min()` at the `reach_cap` seam, skipped when `cap == 0` | `T-290-06` + `:332`, `:362` unmodified |
| R-6 | identical composition in both call sites | `T-290-07` (AST over both) |
| R-7 | `need_pressure` + `effective_bpa_prob` | `T-290-08` (incl. the `≈0.111` assertion) |
| **R-7b** | **pressure passed at both call sites** | **`T-290-16`** (AST over both) |
| R-8 | `MOCK_IDIOSYNCRASY_FLOOR` | `T-290-09` (two-sided) |
| R-9 / R-10 | noise family and RNG stream unchanged | `:248`, `:472`, `:584`, `:607`, `:724` unmodified |
| R-11 | the engine change | `T-290-10` (two-sided, per format) |
| R-12 | — | `T-290-11` (two-sided, N pinned at 1500) |
| R-14 / R-17 | `abandon_completed_mock_drafts` + route wiring | `T-292-01` (3 rows, owner- and league-scoped), `T-292-04` |
| R-18 / R-20 | `_mock_usernames` at **both** sites | `T-290-12`, `T-290-12b` |
| R-19 | no id added to any player lookup | `T-290-13` (raising stub) |
| R-21 / R-22 | no route or import change | `:956-1056`, `:764`, `:787` unmodified |
| D-10 | — | `test_w2_16_calibration_gate` unmodified, **did not fire** |

---

## 8. Knowing deviations and findings

### 8.1 `run_boundaries` factored out of `run_offset` — not in the LLD

R-2's run-size statistic is a property of the gap rule, and the PRD pins the
partition as the **one-pass walk** (T-290-03), warning that the sequential
`run_offset(pool[start:])` reading gives 4.0 / **3.0** and fails on sf_tep.
I hit exactly that before splitting the function — measured 4 / 3.0, then
5.0 / 5.0 after. `run_boundaries` is that one-pass walk, made callable; same
forward walk, no second ordering, no `sorted`.

### 8.2 `mock_draft_abandon_route` (`:11893`) is outside the quoted region

Approved by the orchestrator. Same `/api/mock-draft` family, unclaimed by any
other lane; G1's `10411-10513` verified untouched by hunk offsets.

### 8.3 **Finding — T-292-01 was not hermetic, and the batch would have hit it**

`data/trade_finder.db` persists across runs and the test used fixed ids
(`u-292-01` / `L-292-01`), so rows accumulate. My own failing-first run left 2
complete rows behind, and the next full run reported `cleared 5 rows, expected
all 3`. This is a test defect, not a code defect, but it would have surfaced as
a mystery failure in batch QA on any machine that had run the suite before.
Fixed by clearing the three id pairs at test entry; verified by running the
test twice in a row, and the failing-first property re-verified afterwards.
`T-292-04` got the same treatment.

### 8.4 Observation — distinct orderings saturate post-fix

39 / 33 at N = 1500 and **also** 39 / 33 at N = 500: the post-fix ordering set
is essentially exhausted well below the pinned N. The shipped engine does not
saturate (149 at N=500, 171 at N=1500). So the upper bound is the N-sensitive
half of T-290-11 and the lower bound is not — worth knowing before anyone is
tempted to lower N for speed. Not a spec disagreement; the bounds hold either
way.

### 8.5 `_mock_owner_name`'s annotation avoids `Mapping` / `Any`

`server.py` imports neither and has no `from __future__ import annotations`; it
only parsed because this runtime is Python 3.14 (PEP 649). Plain `dict | None`
keeps it portable to the deploy runtime.

---

## 9. For the orchestrator to apply

### 9.1 Five stale doc locations (all verified still stale on `a01efad`)

Replacement text already drafted in [`scope.md` §2.2](./scope.md) for (a)–(c)
and [`hld-delta.md` §12](./hld-delta.md) for (d)–(e); all five confirmed
present and wrong:

| # | Location | Defect |
|---|---|---|
| (a) | `config/features.json:155` | "It stays OFF beyond the usual lands-dark convention"; cites the superseded `mock-calibration-2026-08.md` |
| (b) | `docs/config-reference.md:309` | default column reads `false`; "This flag stays OFF"; "`CPU_MODEL_VALIDATED` is `False`" |
| (c) | `docs/config-reference.md:565` | "`CPU_MODEL_VALIDATED` is `False`, the CPU-bot mock stays cut" |
| (d) | `docs/architecture.md:135` | "gated OFF by its own calibration verdict"; "`CPU_MODEL_VALIDATED = False`"; "the routes never do" |
| (e) | `docs/glossary.md:42` | "`CPU_MODEL_VALIDATED` is `False` and the create route answers a typed-empty" |

**Applied in this branch:** `backend/feature_flags.py:462` (the sixth) and
`backend/mock_draft_service.py:31-32` (the seventh, per the orchestrator's
instruction — a comment contradicting the code beside it is worse than a stale
doc).

### 9.2 `docs/api-reference.md` — one sentence for #292

`lld-delta.md` §8 records api-reference as n/a. That held for the mobile-only
#292; it does **not** hold now that abandon clears the backlog. For
`POST /api/mock-draft/abandon`:

> Retires the named mock **and** every other `complete` mock the caller owns in
> that league, so a dismissal frees the room rather than surfacing the previous
> recap. Owner-scoped, league-scoped and idempotent; the request body is
> unchanged.

Optional, for `GET /api/mock-draft`:

> On MFL leagues `owner_username` resolves through `league_members`
> (`username` → `display_name` → session username → `"Team <fid>"`) and is
> omitted rather than emitted empty.

### 9.3 `living-memory/DECISIONS.md`

`a01efad` already added a **D-023**. Next free id is **D-024**:

> **D-024 — the mock-draft run is engine-internal, and two of its constants are
> load-bearing in opposite directions.** (2026-08-10) #290 partitions the
> consensus pool by a locally-significant value gap and composes at the
> existing `reach_cap` seam via `min()`, so it can only tighten the operator's
> W2e policy. It deliberately does not reuse the 8-tier ladder or the
> cross-client tier enum — the second time that call has been made (#279 was
> the first). `MOCK_RUN_GAP_MULTIPLE = 2.5` sets how tight a run is (median 5.0
> on both scoring formats); `MOCK_RUN_MIN_OFFSET = 1` stops a singleton run
> from making the pick deterministic — at 0, `sf_tep` forces pick 1.01 in 100%
> of mocks while `1qb_ppr` looks fine, and it must stay strictly below
> `round_reach_cap(1)` or the rule is inert in round 1. Both bounds are pinned
> by tests that fail on unfixed code. Separately, aggregating positional need
> with `max()` is inert — TE's `(S,B) = (1,0)` makes `severity("TE") == 1.0`
> for almost every August roster — so `need_pressure` is denominator-weighted.

### 9.4 `living-memory/TEST_LEDGER.md`

> 2026-08-10 — G2 backend (#290/#292/D-16/D-5): `pytest backend/tests/ -q`
> **2326 passed, 1 skipped** (baseline on `feedback-289-294` @ `a01efad`:
> 2308 passed, 1 skipped; delta +18, all new). `test_mock_draft.py` 98 passed.
> D-10 calibration tripwire did **not** fire. Failing-first captured for
> T-290-04 / T-290-10 / T-290-11 / T-290-14 / T-292-01 at the pinned N=1500.
> No Maestro run — backend lane.

---

## 10. QA checklist

### For the mobile agent (runs against this merged code)

- [ ] **Abandon now clears the whole completed backlog.** After
      `POST /api/mock-draft/abandon`, **one** `GET` returns
      `{empty: true, reason: "no_active_mock"}` — not the previous recap. The
      "Start a new mock" primary can rely on this.
- [ ] Abandon still accepts a `complete` row and is idempotent — double-tap safe.
- [ ] Other leagues are unaffected: dismissing a recap in league A leaves the
      user's completed mock in league B intact.
- [ ] `order[].owner_username` may now be a **franchise name** on MFL leagues,
      or **`null`** when nothing resolves. Never `""`, never contains `"mfl:"`.
      Keep `MockDraftScreen.tsx:284`'s `?? String(onClock.roster_id)` fallback —
      it will simply stop firing.
- [ ] No route contract changed: no new route, no new response key, `SCHEMA`
      unchanged. No mobile type change needed.
- [ ] **Pre-existing persisted mocks replay differently** (G-5) — truncating the
      candidate list changes `_gumbel` consumption. INV-10 promises one build
      replays a seed identically, not that two builds agree. One release-note line.
- [ ] The backend half of #291 is **nil** — the pick path was already wired.

### For the batch QA round

- [ ] `draft.mock` is **ON in production**; this ships lit. The Maestro gate is
      load-bearing, not ceremonial.
- [ ] Live MFL league (Dependables, 62846): open a mock and confirm the
      on-the-clock card and order rail show **franchise names** on a **resumed**
      mock, not only a freshly created one — the resume path is the common case
      and is the site an earlier draft missed.
- [ ] Second-mock loop: complete → dismiss → start another → reach the clock.
      Then do it a **third** time — the paginated bug only shows from the second
      dismissal onward.
- [ ] Superflex round 1 by eye: `P(#1 at 1.01)` is 0.638 there vs 0.455 on 1QB.
      Correct (the sf board's top gap is 82.6 Elo) but a visible change from
      today's 0.455 on both.
- [ ] If the suite has been run before on the machine, note §8.3 — mock-draft
      DB rows persist; the two `292` tests now self-clear, but other lanes'
      fixed-id DB tests may not.
- [ ] Not covered by any automated test, by design: whether the operator agrees
      with the **consensus pricing** of Tate against Tyson and Lemon. A post-fix
      mock that still reads wrong at pick 4 is a DP/KTC blend question in a
      different lane — PRD §4.4.

---

# Status — G2 mobile build (#291 / #292 / D-16 client half)

> **Phase 2 — mobile only.** Appended below the backend agent's report; none of
> its content is rewritten. Branch `worktree-agent-a01a07b48449f2476`,
> fast-forwarded to `feedback-289-294` @ `701f6a3`.
>
> Spec: [`prd.md`](./prd.md) §R-13…R-17 · [`lld-delta.md`](./lld-delta.md) §6, §7
> · [`batch-plan.md`](../289-mfl-draft-room-ids/batch-plan.md) D-7, D-8, D-16, D-17

---

## Table of Contents

- [M1. Base](#m1-base)
- [M2. What shipped](#m2-what-shipped)
- [M3. Test results](#m3-test-results)
- [M4. Discrimination evidence](#m4-discrimination-evidence)
- [M5. Requirement to implementation to test](#m5-requirement-to-implementation-to-test)
- [M6. Knowing deviations and findings](#m6-knowing-deviations-and-findings)
- [M7. For the orchestrator to apply](#m7-for-the-orchestrator-to-apply)
- [M8. QA checklist for the batch round](#m8-qa-checklist-for-the-batch-round)

---

## M1. Base

The worktree came up at `16b1dcb` — the **wrong base**, the concurrent
Outlook/odds lineage, with no `docs/feedback/items/290-mock-draft-engine/`
in the tree at all. `git rev-list --count feedback-289-294..HEAD` = **0**, so
`16b1dcb` is a clean ancestor and the correction was a fast-forward, not a
merge: `Updating 16b1dcb..701f6a3`. **No unrelated commits carried in.** The
base now contains `701f6a3` ("#290 (G2 backend): realign to Rounds 2-3"), G1's
`draft_board_service` MFL hydration and G3's `LeagueSummaryScreen`.

`mobile/node_modules` was absent; installed with `npm ci` in this worktree, not
symlinked — `@react-native-cookies/cookies` resolves, no phantom `tsc` error.

---

## M2. What shipped

Five files, all inside the D-17 ownership grant. **No `backend/` file was
opened for edit.**

### `mobile/src/screens/DraftRoomScreen.tsx`

| Change | Item |
|---|---|
| `UndraftedRowView` trailing slot: `actionLabel && selected` → **`actionLabel`** | #291 |
| meta line gains whatever the label evicts — `TIER_LABEL[tierForElo(…)]` for a valued row, **`· No value`** for an unvalued one | #291 |
| `mockEntryContent` complete state: **primary = "Start a new mock"**, secondary = "View recap"; testIDs stay bound to the ACTION | #292 (1) |
| `retry={{…}}` passed to `MockEntryPanel` — `createMock.reset()` + `mockQuery.refetch()` | #292 (2) |
| `onMode` clears `postRefusal` on re-entering Mock mode | #292 (3) |
| `onStart` clears `postRefusal` **and** `createMock.reset()` before opening the sheet | #292 (2, 3) |
| `TIER_LABEL` added to the existing `tierBands` import | — |

### `mobile/src/components/draft/MockEntryPanel.tsx`

Optional `retry?: { label; onPress; testID }`, rendered inside the `errorText`
branch. The `block` branch is deliberately **not** armed — a block is an honest
refusal and an enabled button there would fail on tap; that dead end is cleared
by clearing `postRefusal`, not by lying about the state.

### `mobile/src/screens/MockDraftScreen.tsx`

| Change | Item |
|---|---|
| `actionLabel={isUserTurn ? 'Pick' : undefined}` | #291 |
| section header `{isUserTurn ? 'Tap to draft' : 'Still on the board'}` | #291 |
| `OnTheClockCard` gains **"Tap a rookie below, then confirm."** (`styles.clockHow`, 13px) when `isUser` | #291 |
| `headerRight` renders on `active` **or `complete`**; label and a11y switch to "Clear" | #292 (1) |
| `endMock` branches its `Alert` copy on status | #292 (1) |
| new `ownerNameOf()` + `MFL_MEMBER_RE`, used at **both** owner-render sites | D-16 |

### `mobile/tests/check-mock-lifecycle.js` — new, 52 assertions

Structural, with one behavioural half. Registered as
`npm run test:mock-lifecycle`. See §M4.

### `mobile/.maestro/flows/rookie/d3-mock-draft-loop.yaml` — new

Two full laps. **Not executed here** — authored and statically verified only,
per instruction; execution belongs to the batch QA round. Non-colliding with
the league lane's `flows/league/01…04`.

### `mobile/scripts/testid-lint-allow.txt`

Four ids the flow references that the grep cross-check cannot resolve — §M6.2.
Added as three exact ids plus one glob, **not** a blanket `mock-entry.*`.

---

## M3. Test results

| Gate | Result |
|---|---|
| `cd mobile && npx tsc --noEmit` | **exit 0** (baseline on `701f6a3`: exit 0) |
| `bash mobile/scripts/testid-lint.sh` | **`testid-lint OK`, exit 0** |
| `node mobile/tests/check-mock-mode-marker.js` | **exit 0** — 28/28 PASS |
| `node mobile/tests/check-mock-lifecycle.js` | **exit 0** — 52/52 PASS (new) |
| the other six `mobile/tests/check-*.js` | all **exit 0**, unchanged |
| `python3 -m pytest backend/tests/ -q` | **2326 passed, 1 skipped** |

The pytest figure is a **baseline confirmation, not a delta**: this lane
changed no Python. It was run before and after the mobile edits and reported
the same number both times — identical to the backend agent's post-merge count.

⚠ `test:mock-lifecycle` is **not in CI** — only `maestro-testid-lint` is, the
same gap `check-mock-mode-marker.js` has. Both must be run by hand on any commit
touching these three files. Raised in §M7.2.

---

## M4. Discrimination evidence

Every structural assertion was proven capable of failing: the defect was
installed, the failure text captured, then reverted and re-verified green.
**Two assertions passed on the very bug they named on the first cut** and had to
be rewritten — recorded here rather than quietly fixed.

### (a) #291 — the shipped `selected` gate restored

```
FAIL  The action label does NOT wait for `selected`: condition is
      `actionLabel && selected` — a mock row gated on `selected` is
      pixel-identical to the read-only room row until it has already been
      tapped (#291)
```

### (b) #291 — the "Tap to draft" header reverted

```
FAIL  MockDraftScreen renders the "Tap to draft" header: this exact string is
      the Maestro acceptance for #291
```

### (c) #292 (2) — the retry block deleted from the error branch

```
FAIL  The errorText branch renders a control: shipped it rendered a bare
      <Text> — one failed create replaced the card with a BUTTONLESS view
FAIL  The ONLY control-free branch is the transient loading spinner:
      control-free branches: 2
```

The second assertion is the one that catches a *future* buttonless branch, not
only this one.

### (d) #292 (1, 3) — the complete-state swap and both `postRefusal` clears reverted

```
FAIL  The complete state's PRIMARY is the way onward: primary is
      `primary: { label: 'View recap', onPress: onResume, testID: 'mock-entry.recap' }`
FAIL  The recap is demoted to secondary, not removed
FAIL  testID `mock-entry.run-it-back` still means start-another
FAIL  testID `mock-entry.recap` still means the recap
FAIL  Re-entering Mock mode clears `postRefusal`
FAIL  Opening the setup sheet clears `postRefusal`
FAIL  Opening the setup sheet clears a stale create error
```

### (e) D-16 — the MFL rung neutralised inside `ownerNameOf`

```
FAIL  ownerNameOf resolves the D-16 ladder:
      ownerNameOf(null, "mfl:62846.f0003") = "mfl:62846.f0003", want "Team 0003"
      … 5 rows, incl. ownerNameOf("mfl:62846.f0003", "mfl:62846.f0003")
FAIL  No owner render can emit a string containing "mfl:"
FAIL  The fid keeps the zero-padding it has in the id
```

This half is **behavioural, not structural**: the ladder is real logic, so the
function is transpiled out of the TSX and called against a seven-row table. A
pattern match would have passed on a ladder that returned the id unchanged.

### (f) ⚠ Two assertions passed on their own defect and were rewritten

1. **The completed-mock header guard.** The first cut asserted only that
   `'complete'` appeared *somewhere inside the `useLayoutEffect`*. With the
   guard reverted to `state?.status === 'active'` it **passed**, because the
   local `done` feeding the button label was still declared. Rewritten to
   resolve the guard's condition through its local `const`s and assert on the
   condition alone:
   ```
   FAIL  The header dismissal is reachable on a COMPLETE mock: guard resolves
         to `state?.status === 'active'` — shipped, the only abandon control
         rendered while `status === "active"`, so a finished mock had no way
         out at all (#292 dead-end 1)
   ```
2. **The "No value" relocation.** The first cut read `meta.getText()` and looked
   for the substring `No value`. With the relocation deleted it **passed** —
   because the JSX comment *explaining* the relocation contains the words "No
   value". A check satisfied by its own documentation is worse than no check.
   Rewritten to read only literal / JsxText nodes, and the tier half to look for
   an `ElementAccessExpression` on `TIER_LABEL` rather than a substring:
   ```
   FAIL  The "No value" text is relocated onto the meta line (D7 preserved):
         meta literals are `— | · | · | 1qb_ppr`
   FAIL  The tier label is relocated onto the meta line (#277 preserved)
   ```

Both traps are named in the test file's own comments so the next reader does not
reintroduce them.

---

## M5. Requirement to implementation to test

| Req | Implementation | Test |
|---|---|---|
| **R-13** (#291 affordance) | trailing slot ungated from `selected`; `actionLabel` gated on `isUserTurn` at the caller | `check-mock-lifecycle` §1 (4 assertions) + `d3` `assertVisible: "Tap to draft"` **before any tap** |
| R-13 (#277 relocated, not deleted) | tier label + `No value` moved to the meta line under `actionLabel` | `check-mock-lifecycle` meta-line block (4 assertions, incl. the literals-only rewrite) |
| R-13 (header + instruction copy) | `Tap to draft`; `Tap a rookie below, then confirm.` | rendered-text assertions + `d3` step 4 |
| R-13 (no room copy imported) | nothing added to `MockDraftScreen` from the real room | `check-mock-mode-marker` (`never drafts`) + `check-mock-lifecycle` (`Picks are made on the platform`) |
| **R-14** (one dismissal clears the surface) | `headerRight` on `complete`; branched `Alert`; same `abandonMockDraft` call, backend clears the backlog | guard-resolution block + **`d3` step 8** (two completed mocks, ONE dismissal, assert `mock-entry.start`) + backend `T-292-01` |
| R-14 (way onward is primary) | `mockEntryContent` complete branch swapped | primary/secondary + testID-binding assertions |
| **R-15** (no zero-control state) | `retry` prop + error-branch render | T-292-02 block — incl. "the ONLY control-free branch is the loading spinner" |
| **R-16** (transient refusal cannot stick) | `onMode` + `onStart` clear `postRefusal`; `onStart`/`retry` clear `createMock` | T-292-03 block |
| **R-17** (second mock creates) | client half: the primary now leads there | `d3` lap 2 + backend `T-292-04` |
| **D-16** (client half) | `ownerNameOf` at both owner-render sites | §5 — behavioural table + both-sites + no-raw-fallback |
| **R-23** (typecheck) | — | `npx tsc --noEmit` exit 0 |
| G-4 (`check-mock-mode-marker`) | one return, one rail, six markers, all intact | 28/28 PASS |

---

## M6. Knowing deviations and findings

### M6.1 Deviation — D-16's client fallback is `Team <fid>`, not `No selection` / `Player <mfl_id>`

The build brief asked for G1's fallback strings **exactly, including
`No selection` for MFL's all-zeros sentinel and `Player <mfl_id>` as the last
resort**. The LLD says the opposite — [§5.4](./lld-delta.md#54-not-changed):
*"`MockDraftScreen.tsx:284` … stays as the honest last resort. ⚠ The plan lists
this line as needing a fix; it does not"* — and §10's checklist repeats it.
**I did neither. Reasoning, for the orchestrator to overrule if it wants:**

Those two strings are G1's **player-name** ladder
(`draft_board_service._hydrate_mfl_picks`, tiers S and 3). They cannot apply in
the mock: the pool is `_rookie_player_ids(season)`, our own id space, so no MFL
player id and no MFL slot sentinel can reach this screen. Emitting
`No selection` here would invent a state that does not exist.

But leaving `:284` alone was also wrong. Its fallback was
`String(onClock.roster_id)`, which on an MFL league renders **`mfl:62846.f0003`**
— a raw machine id at the top of the board, `#289`/D-16 verbatim. The backend
now almost always resolves the name, so "it will simply stop firing" is true *in
the common case* and the hazard is still in the code.

**What shipped is the OWNER half of the same convention, re-used not
reinvented:** the same `Team <fid>` string, the same zero-padding, the same
`"mfl:"` filtering as `server.py:_mock_owner_name`'s last rung. Non-MFL ids keep
the shipped behaviour untouched. Applied at **both** owner-render sites —
`clockName` and the recap's `nameOf`. The recap was a second site nobody had
named: the same one-of-two miss the backend lane found at `server.py:11474`.

If you want `:284` restored verbatim, it is three lines and §5 of the test comes
out with it.

### M6.2 Finding — the flow hit four `testid-lint` failures, exactly as warned

```
testid-lint: flow references missing testID: draft-room.mode.mock
testid-lint: flow references missing testID: mock-entry.recap
testid-lint: flow references missing testID: mock-entry.run-it-back
testid-lint: flow references missing testID: mock-entry.start
```

The PRD's testID audit (§7.3) lists all four as *"already exists, verified by
`grep testID` in source"* — true of the **strings**, not of the lint's
`testID=`-anchored grep. Two causes:

- `draft-room.mode.mock` is `` testID={`${testIDPrefix}.mock`} `` in
  `MockChrome.tsx` — a genuine template literal.
- The `mock-entry.*` CTAs render as `testID={primary.testID}`; the literals live
  in `DraftRoomScreen.tsx`'s `mockEntryContent` as object **values**
  (`testID: 'mock-entry.start'`), which gives the grep no `testID=` to anchor on.

Added as `draft-room.mode.*` plus three **exact** ids. Deliberately not
`mock-entry.*`: the panel's own `mock-entry.card` / `.loading` / `.error` are
real `testID="…"` attributes and must stay lint-checked, and a typo'd id must
stay a lint failure.

`mock-entry.retry` is **not** referenced by any flow and needs no entry — as the
LLD predicted. If a later flow taps it, the constructing site is
`DraftRoomScreen.tsx` and it will need one.

### M6.3 The `d3` flow's seeding precondition is real and NOT fixed here

`backend/tests/fixtures/profiles/standard.json` declares exactly one league
(`990000000000000001`). `d1`, `d2` and now `d3` all target
`1312140920132497408`, which appears in no profile; the *"ffv3-predraft corpus
merged into the fixture dir"* step their headers assume is unimplemented.
**The flow cannot pass until that is closed** — step 2 will not find the row.

The fixture profile is outside this lane's ownership, so it was not touched. The
fix is **one entry in a profile's `leagues[]`**, and it repairs `d1` and `d2` as
a side effect. Written into the flow's own header so it cannot be lost.

### M6.4 The native Alert is the one place an id selector does not exist

`d3` step 8 must tap "Clear" on `Alert.alert`. iOS draws those buttons; they
carry no testID. The flow uses the multi-line form, which `testid-lint` permits:

```yaml
- tapOn:
    text: "Clear"
```

A one-line `tapOn: "Clear"` would be rejected, correctly. This is the only text
tap in the flow; every other selector is an id.

### M6.5 `MockEntryPanel`'s loading branch renders no control — by design

R-15 says no reachable state renders zero interactive controls. The loading
branch renders an `ActivityIndicator` and nothing else, and it was left that
way: it is transient and self-clearing, and a button there would have nothing to
do. The structural test pins this rather than waiving it — it asserts the
control-free branch **count is exactly one and that one is the spinner**, so a
fifth buttonless branch fails.

### M6.6 Observation — every row shows "Pick" on the user's turn

D-7 asks for the affordance to be visible before tap, and the honest reading is
that *every* undrafted row is tappable, so every row carries the label. On the
user's turn the tier badge is uniformly replaced by a meta-line tier string for
the whole list. Two consequences worth an eye in QA: the list's right edge is
denser during your turn than between turns, and `selected` is now distinguished
only by `undraftedRowSelected` (background + ice bottom border) rather than by
the label appearing at all. Both are what the design intends; neither is
asserted by a test, because both are purely visual.

Chalkline compliance checked by hand: `draftRow.rowAction` is `type.label`
(**11 px — at the floor, not below it**), ice text on an ice border, `radii.xs`;
the new `clockHow` is `type.bodySm` (13 px), `chalk.dim`. No new token, no
glyph, no emoji, no gradient, no radius above 8. Nothing captures touches from
`react-native-draggable-flatlist` — this lane adds no gesture handler at all.

---

## M7. For the orchestrator to apply

### M7.1 `mobile/src/screens/CLAUDE.md` and `mobile/src/components/CLAUDE.md`

Orchestrator-owned. Proposed text:

- `screens/CLAUDE.md` § Sharp edges, add:
  > `DraftRoomScreen` / `MockDraftScreen` / `MockEntryPanel` are also pinned by
  > `mobile/tests/check-mock-lifecycle.js` (the #291 affordance, #292's three
  > dead ends, D-16's owner ladder). Like `check-mock-mode-marker.js` it is
  > **not in CI** — run both on every commit touching those three files.
- `components/CLAUDE.md`, the `draft/MockEntryPanel` row:
  > Mock-mode entry card: start/resume/recap + a muted card per refusal reason
  > + a retry control in the error branch (#292); exports `MOCK_MIN_TEAMS`.

### M7.2 CI — add the mobile structural checks

Only `maestro-testid-lint` runs in CI. `check-mock-mode-marker` was already
outside it — the PRD calls it "the highest-probability breakage" for this change
(G-4) — and `check-mock-lifecycle` now joins it. **Recommend one CI job running
every `mobile/tests/check-*.js`**: eight scripts, all sub-second, all currently
green. Not applied here; CI config is outside this lane.

### M7.3 The `d3` seeding precondition (§M6.3)

One entry in `backend/tests/fixtures/profiles/standard.json`'s `leagues[]` for
`1312140920132497408`, or a new `mock.json` profile. Blocks `d3`, `d1` and `d2`
— i.e. it blocks the Tier-1 sim gate, not a nice-to-have. **Needs an owner.**

### M7.4 `living-memory/TEST_LEDGER.md`

> 2026-08-10 — G2 mobile (#291/#292/D-16 client): `tsc --noEmit` exit 0;
> `testid-lint OK`; `check-mock-mode-marker` 28/28; **new**
> `check-mock-lifecycle` 52/52; other six `check-*.js` green.
> `pytest backend/tests/ -q` **2326 passed, 1 skipped** — unchanged, this lane
> touched no Python. Discrimination captured for all five requirement groups;
> two first-cut assertions passed on their own defect and were rewritten
> (`status.md` §M4f). Maestro `d3-mock-draft-loop.yaml` **authored, not run** —
> blocked on the `standard.json` profile gap that also blocks d1/d2.

### M7.5 `living-memory/DECISIONS.md`

The backend agent proposes **D-024**; this would be **D-025**:

> **D-025 — a mock row states its tappability before the tap, and the trailing
> slot holds exactly one thing.** (2026-08-10) #291 was reported as "the mock
> should be interactive" and was in fact an affordance defect: the pick path
> worked, but the "Pick" label rendered only once `selected`, so a tappable row
> was pixel-identical to the read-only Draft Room row until after it had been
> tapped — announced to VoiceOver via `accessibilityHint` and to nobody else.
> The label now renders on the user's turn, gated at the caller so the CPU-turn
> and read-only renders stay byte-identical. Because the trailing slot holds one
> thing, whatever the label evicts is **relocated to the meta line, never
> deleted**: #277's tier badge becomes a tier string, D7's "No value" becomes a
> meta suffix. Drafting for other teams stays out (D-7), and the real room's
> "never drafts for you" copy stays out of the mock — over a board that takes
> taps it would read as a promise about that board.

---

## M8. QA checklist for the batch round

Backend items are in §10 above; these are the mobile ones.

### Blocker to clear first

- [ ] **`d3-mock-draft-loop.yaml` cannot run** until `1312140920132497408` is in
      a fixture profile (§M6.3). Same blocker for `d1` and `d2`, which the PRD
      names as the shared-component no-regression check for this change.

### #291 — the affordance

- [ ] On the mock board, **before tapping anything**, every undrafted row shows
      a "Pick" chip and the section header reads **"Tap to draft"**. The
      on-the-clock card reads "Tap a rookie below, then confirm."
- [ ] Between turns (CPU on the clock) the rows revert **exactly** to the
      read-only look: tier badge back in the trailing slot, header back to
      "Still on the board", no instruction line.
- [ ] Open the **real** Draft Room (`Real draft` side) and confirm its rows are
      unchanged — `UndraftedRowView` is shared and this is where a regression
      would show first.
- [ ] A row with **no consensus value**, on the user's turn: the meta line must
      end `· No value`. That text used to live in the trailing slot.
- [ ] VoiceOver: the row's hint is unchanged; the visible label is now redundant
      with it rather than the only signal.

### #292 — the three dead ends

- [ ] Complete a mock → back to the room → the **primary** reads **"Start a new
      mock"**; "View recap" is the ghost.
- [ ] **Three laps matter.** complete → dismiss → start → complete → dismiss →
      start → complete → dismiss. From the *second* dismissal onward the room
      must land on "No mock running", never on an older recap. One lap does not
      reproduce the paginated bug.
- [ ] On a completed mock's recap the header action reads **"Clear"** (not
      "End") and its confirm says "Clear this recap?".
- [ ] Double-tap the dismissal — idempotent, no error toast.
- [ ] **Cross-league:** dismiss a recap in league A, switch to league B; B's
      completed mock must still be there.
- [ ] Force a create failure (airplane mode at the `mock-setup.start` tap) → the
      card shows the error **with a "Try again" button** → tap it → the card
      recovers. Shipped, this state was permanent for the session.
- [ ] Trigger a refusal (a league the card blocks), switch to `Real draft`,
      switch back to `Mock` → the card must re-evaluate, not stay muted.

### D-16 — identity

- [ ] Live MFL league (**Dependables, 62846**): open a mock. The on-the-clock
      card **and the recap rail** must show franchise names — never anything
      containing `mfl:`. Check a **resumed** mock, not only a fresh one.
- [ ] If a franchise has no stored name the correct render is **`Team 0003`**
      (zero-padded), matching the Draft Room on the adjacent screen. `Team 3` is
      a failure.

### Regression surface

- [ ] `npm run test:mock-mode-marker` and `npm run test:mock-lifecycle` are
      **not in CI** — run both by hand before merge (§M7.2).
- [ ] `draft.mock` is **ON in production**: every item above ships lit.

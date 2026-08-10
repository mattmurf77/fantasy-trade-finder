# PRD — G2: mock draft engine, lifecycle, interactivity (#290 / #291 / #292 / D-16)

- **Items:** #290 (MockDraft) · #291 (MockDraft) · #292 (DraftRoom) · scope addition **D-16**
- **Group:** G2 — feature path (heaviest ceremony). App 1.11.0, `mattmurf77`, filed 2026-08-10.
- **Branch:** `feedback-289-294` (base `origin/main` @ `7cea1fa`), worktree `.claude/worktrees/fb-289-294`
- **Inputs:** [`plan.md`](./plan.md) · [`batch-plan.md`](../289-mfl-draft-room-ids/batch-plan.md) (D-5…D-16) · G1's [`prd.md`](../289-mfl-draft-room-ids/prd.md) (R-7, T-289-06)
- **Design:** [`hld-delta.md`](./hld-delta.md) · [`lld-delta.md`](./lld-delta.md) · [`scope.md`](./scope.md) · [`reconciliation-log.md`](./reconciliation-log.md)
- **Phase:** 1 — PRD only. No production code is delivered. (A prototype was applied and reverted purely to measure the blast radius; see §7.1.)

## Reported (verbatim)

> **#290** — "I think something's broken. The draft logic needs its own set of tiers that should take precedence when drafting these tiers should be tight groups of 4-5 players. The mock I just did for ffv3 league has Tate going 4th overall which feels too unrealistic based on value gaps between him and the other WRs. Also reaching should more so be to fill a position of need than just random."
>
> **#291** — "The mock draft should be interactive. The user should get to draft their own players at the very least."
>
> **#292** — "Can't do a second mock draft"

---

## Table of Contents

- [1. Summary](#1-summary)
- [2. Reproduction and root cause](#2-reproduction-and-root-cause)
- [3. Requirements](#3-requirements)
- [4. The Tate case](#4-the-tate-case)
- [5. Success criteria](#5-success-criteria)
- [6. Out of scope](#6-out-of-scope)
- [7. Test plan](#7-test-plan)
- [8. Guardrails](#8-guardrails)
- [9. Sequencing](#9-sequencing)
- [10. Requirement → test matrix](#10-requirement--test-matrix)

---

## 1. Summary

| Item | Verdict | Where the fix lands |
|---|---|---|
| **#290** | Reproduces, **and the diagnosis moves**. The CPU model scores `rank − need_bonus − noise` and never reads `row["value"]` (`mock_draft_service.py:646-651`), so it is blind to value gaps; and reaching is an unconditional Bernoulli independent of need (`:643`). Measured on the real board: the consensus **#1** lands 4th overall 15.8 % of the time. | `backend/mock_draft_service.py` — two pure functions, one composition at the existing `reach_cap` seam, one changed mixture weight. |
| **#291** | Reproduces as an **affordance** defect, not a capability gap. The pick path works end-to-end. The trailing "Pick" label renders only when `selected` (`DraftRoomScreen.tsx:1325`), so before the first tap the mock row is pixel-identical to the read-only Draft Room row. VoiceOver users are told (`:1374-1377`); sighted users are not. | `DraftRoomScreen.tsx` (`UndraftedRowView`) + `MockDraftScreen.tsx` copy. |
| **#292** | Reproduces. Three proven dead-ends (D-8). **All three are client-side** — the abandon route already accepts a completed mock, so the plan's backend half does not exist. | `DraftRoomScreen.tsx`, `MockEntryPanel.tsx`, `MockDraftScreen.tsx`. |
| **D-16** | Reproduces, at **two** sites not one. `usernames` is built off the session league object at `server.py:11437` (create) **and `:11474`** (every GET and /pick). | `backend/server.py`, G2's owned region. |

**This PRD authorises a targeted change to how candidates are truncated and how
need weighs against noise. It does not authorise a rewrite of the mock engine.**
The scoring function `argmin(rank − need_bonus − Gumbel)` is byte-identical
after this change; the noise family, the persona mechanism, the W2e policy
tables, the budget accounting, the payload shape and every route contract are
untouched.

---

## 2. Reproduction and root cause

**Code has not moved since 1.11.0 shipped.** `git log -- backend/mock_draft_service.py`
shows nothing after `6caca35` (2026-08-08); HEAD is `7cea1fa`. Every relevant
flag is `true` (`config/features.json:149,151,156,157,169`) and
`CPU_MODEL_VALIDATED = True` (`:294`), so **this surface is lit in production**
and every change here ships visible on merge.

### 2.1 #290 — measured, not inferred

Method (reproducible, hermetic, ~20 s): build the pinned consensus board the
calibration harness builds — `backend.tests.test_mock_draft._rookie_ctx(fmt)`,
which composes `rookie_universe_2026.json` × `ktc_blend_pipeline_2026-07-17.json`
through the **shipped** `data_loader._apply_consensus_blend` and
`seed_elo_for_value` — then drive the **shipped** `mds.build_settings` /
`new_state` / `advance_cpu` over 12 owners, linear, explicit order, user last,
N seeded replays. Needs no DB and no network.

**Board (1qb_ppr, top 5):** Love RB 1886.9 · **Tate WR 1817.5** · Tyson WR 1771.3 ·
Lemon WR 1746.4 · Price RB 1667.2. Gaps: 69.5 / 46.1 / 25.0 / **79.2**.

**Shipped engine, N = 2000 round-1 replays:**

| Statistic | Value |
|---|---|
| P(consensus #1 Love goes 1.01) | 45.1 % |
| P(Love falls past pick 3) | 15.8 % |
| P(Tate falls past pick 4) | 16.5 % |
| Who goes 4th | Lemon 17.7 · Tyson 16.0 · **Love 15.8** · Price 15.3 · Concepcion ~13 · Sadiq ~11 · Tate 10.1 (%) |
| Distinct top-4 orderings | 173 |

The distribution at pick 4 is near-flat across the top seven. **That is the
defect** — and note that the consensus #1 lands there more often than the player
the report named.

**Root cause (a) — the metric is rank, not value.** `mock_draft_service.py:646-651`:
```python
for rank, row in enumerate(candidates_ranked, start=1):
    bonus = weight * float(needs_for_team.get(pos, 0.0)) * float(max_reach)
    noise = _gumbel(rng, scale) if reaching else 0.0
    score = rank - bonus - noise
```
`row["value"]` is present on every candidate (`draft_board_service.py:938-968`)
and is never read. A 3-slot round-1 reach costs the same across a 5-Elo gap and
a 300-Elo cliff. There is **no** gap-based clustering anywhere in the codebase:
every shipped tier boundary is a fixed absolute-Elo floor
(`backend/tier_config.json`), a fixed rank cut (`tier_size = 24.0`,
`database.py:1699`) or a fixed raw-value threshold (`trade_service.py:1010-1012`).

**Root cause (b) — need and noise are independent, and need is near-inert.**
`reaching = scale > 0.0 and rng.random() >= float(bpa_prob)` (`:643`) is drawn
*before* and independently of any need, so ~90 % of picks enter the reach branch
regardless of roster state. A maximal need for a `not_sure` bot buys
`0.5 × 1.0 × 3.0 = 1.5` slots of pull (`need_weight` → `outlook_alpha`,
`database.py:1732-1736`) against a noise branch that reaches the full round-1
cap 12.3 % of the time with no need at all. And severity is
`clamp01((S+B−viable)/(S+B))` with `VIABLE_ELO_FLOOR = 1280` (`:194`), which is
`0` for most (team, position) pairs in August. **Reaching today is ~entirely
random.**

### 2.2 #291 — the affordance, verified

`UndraftedRowView` is shared verbatim between the read-only room and the mock
(`MockDraftScreen.tsx:73` imports it from `DraftRoomScreen`). At
`DraftRoomScreen.tsx:1325` the trailing "Pick" renders only `if (actionLabel && selected)`;
otherwise the slot holds #277's `TierBadge`. So before the first tap the mock row
has the same style (`draftRow.undraftedRow`), the same trailing content and no
chevron — the only difference is the transient `pressed` background (`:1385`).
The section header says "Still on the board" (`MockDraftScreen.tsx:386`) and
`OnTheClockCard` says "You're on the clock" (`:531`) without saying *how* to act.
Meanwhile the Pressable carries `accessibilityHint="Select this rookie, then confirm the pick"`
(`:1374-1377`) — the capability is announced to assistive tech and hidden from
everyone else.

The pick path itself is fully wired and pinned by existing tests
(`test_mock_draft.py:619`, `:443`): `onPress={isUserTurn ? setSelected : undefined}`
(`:426`) → `mock-draft.confirm` (`:441`) → `pickMutation.mutate` (`:471`) →
`POST /api/mock-draft/pick` → `apply_user_pick` (`mock_draft_service.py:947`).

### 2.3 #292 — three dead-ends, all client-side (D-8)

1. **A completed mock is permanently "current."** `load_current_mock_draft`
   falls back to the most recent `status="complete"` row with no time bound
   (`database.py:10774-10783`), and `MockDraftScreen`'s only abandon control is
   the header "End", rendered *only while* `status === 'active'` (`:198-212`).
   The room therefore shows "Mock complete" forever with **primary = "View recap"**
   and the only way onward as the recessive ghost "Run it back"
   (`DraftRoomScreen.tsx:823-830`).
2. **One failed create permanently replaces the card with a buttonless error
   view.** `MockEntryPanel` checks `errorText` before rendering any button
   (`:90-96`); `errorText` folds in `createMock.isError`
   (`DraftRoomScreen.tsx:625-633`); there is no `onError` on `createMock`
   (`:278-294`) and no retry control. React-query mutation error state persists
   until the next `mutate`/`reset`.
3. **`block` short-circuits both buttons from six triggers.**
   `MockEntryPanel.tsx:72-80` returns a muted card with a disabled dead CTA
   whenever `block` is non-null, and `mockBlock` (`DraftRoomScreen.tsx:298-355`)
   is computed from the *real* board. Of its six triggers the sticky one is
   `postRefusal` (`:300`), which is never cleared.

**Correction to the plan.** The abandon route already accepts a completed mock:
`mock_draft_abandon_route` (`server.py:11781-11794`) calls `update_mock_draft`,
whose `WHERE` is **id + user_id only** (`database.py:10786-10805`). There is no
backend work in #292, no route contract change, and no `database.py` edit.

### 2.4 D-16 — two sites

`state_payload` resolves both `owner_username` and `original_username` through
`ctx.usernames` (`mock_draft_service.py:1013-1015`). The routes build that map as
`{str(m.user_id): m.username for m in members}` off `sess["league"].members` — at
`server.py:11437` **and again at `:11474`**. For an MFL league those are whatever
the session carries, not the franchise names G1's Draft Room fix will resolve.
Rendered at `MockDraftScreen.tsx:284` (`slot?.owner_username ?? String(onClock.roster_id)`)
and `:622`.

---

## 3. Requirements

Every requirement has a mechanically verifiable pass criterion. "Assertion" =
pytest; "structural" = a node/AST check; "flow" = Maestro; "observation" = a
recorded manual step.

### #290 — the run model

**R-1 — the consensus pool is partitioned into runs by a locally-significant
value gap, computed by a single forward walk.**
`run_offset()` cuts a boundary between rows `i` and `i+1` when the value drop is
at least `MOCK_RUN_GAP_MULTIPLE` × the median gap in a `MOCK_RUN_MEDIAN_WINDOW`-wide
local window. Adaptive, not a fixed Elo threshold (**D-9**). Algorithm, boundary
conditions and tie handling: [`lld-delta.md` §2](./lld-delta.md#2-run-detection).
*Pass:* T-290-01 (unit table over a hand-built board, including start/end/tie/
unvalued cases) **and** T-290-02 (the AST test `test_w2_14` at
`test_mock_draft.py:708` still finds zero `sorted`/`.sort` in the module).

**R-2 — runs are NOT size-clamped, and the gap rule is checked against the
operator's 4-5 target rather than forced to it (D-9).**
*Pass:* T-290-03 — on the pinned 2026 board, for **both** `1qb_ppr` and `sf_tep`,
the **median run size is 4 or 5** under the one-pass partition (§7.3). Asserted as
a range, recomputed from the fixture.

**R-2b — the run rule may never truncate the candidate set to a single player.**
`MOCK_RUN_MIN_OFFSET` floors the run's contribution to the cap, so a genuine value
cliff narrows the field but can never make a pick deterministic. The floor sits
**inside** the `min()`, so it can never loosen the operator's W2e cap; and it must
be **strictly less than `round_reach_cap(1) = 3`**, or round 1 silently reverts to
the shipped engine.
*Pass:* T-290-14 (structural, seedless, both formats), T-290-15 (the `< 3`
boundary), T-290-06 (the two-sided cap invariant).

*Why a floor and not a different `m`:* 27 `(m, W)` configurations were swept on
both boards and **none** clears `run_offset >= 1` on both while holding a 4-5
median run on both — `m = 2.5` gives `run_offset = 0` on `sf_tep`, forcing pick
1.01 in every superflex/TE-premium league. The floor separates the two jobs `m`
was doing at once: `m` defines *where the runs are* (R-2, a data property), the
floor decides *how tight a wall may be* (R-11/R-12, a behavioural property). Full
sweep: [`reconciliation-log.md` §M–N](./reconciliation-log.md#round-3--author-incorporation).

**R-3 — a run boundary is a HARD wall in rounds 1-2 (D-6).**
Over N ≥ 200 seeds on the pinned board, **no** round-1 or round-2 CPU pick is a
player who sits past the head's run boundary. Exact, not statistical.
*Pass:* T-290-04.

**R-4 — rounds 3+ soften to a one-boundary allowance (D-6).**
A round-3+ CPU pick may cross at most **one** run boundary, and is still bounded
by `round_reach_cap` = 15.
*Pass:* T-290-05 — over N ≥ 200 seeds, every round-3+ pick's 0-based pool
position is `<= run_offset(head, allow_cross=1)`, and at least one pick in the
sample **does** cross a boundary (so the softening is proven live, not merely
permitted).

**R-5 — the run can only TIGHTEN the operator's W2e cap, never loosen it.**
For every round `1..8` and every candidate head, `effective_cap <= round_reach_cap(round)`;
and when the round's budget is spent, `effective_cap == 0`.
*Pass:* T-290-06, plus `test_w2_21_the_policy_table_is_the_operators_rule_verbatim`
(`:332`) and `test_w2_21_a_round_never_spends_more_than_its_frequency_budget`
(`:362`) unmodified.

**R-6 — the run rule is applied at BOTH call sites.**
`advance_cpu` (`:936`) and the calibration harness's mirror `simulate_reaches`
(`:1247`) compose the cap identically, so the simulator and the product cannot
diverge on the policy.
*Pass:* T-290-07 — a structural test asserting the `min(..., run_offset(` call
appears in both functions, plus a behavioural test that a `simulate_reaches`
replay of a fixed sequence produces reach depths bounded by the same rule.

### #290 — need-conditional reaching (D-5)

**R-7 — the mixture weight is need-conditional, and the need aggregate is
DENOMINATOR-WEIGHTED, not a max.** `effective_bpa_prob` returns exactly
`bpa_prob` at pressure 1.0. Pressure is
`Σ severity_p·(S_p+B_p) / Σ (S_p+B_p)` via `need_pressure`.
*Why not `max`:* `slot_targets` gives TE `(S,B) = (1,0)`, so **any** roster
without a 1280+ TE scores `max = 1.0` → `bpa_effective == bpa_prob` → today's
behaviour exactly. Measured on a roster full at QB/RB/WR with no viable TE:
`max` = 1.000 (P(reach) 0.900, unchanged), `mean` = 0.250, **weighted = 0.111**
(P(reach) 0.300). Under `max` the whole change is a no-op on ordinary rosters.
*Pass:* T-290-08 — `need_pressure` endpoints (all-filled → 0.0; TE-only hole →
0.111 on a standard lineup; all-empty → 1.0; monotone), plus
`effective_bpa_prob` against the closed form at 0.0 / 0.5 / 1.0.

**R-7b — both engine call sites pass the pressure.**
*Pass:* T-290-16 — AST: `need_pressure(` appears inside **both** `advance_cpu`
and `simulate_reaches`. The optional parameter exists only so the shipped
single-position unit tests keep working.

**R-8 — a bot with NO positional need still reaches sometimes (D-5:
"idiosyncrasy survives").** At pressure 0 and the shipped `bpa_prob = 0.10`, the
reach rate is `(1 − bpa_prob) × MOCK_IDIOSYNCRASY_FLOOR = 22.5 %`, materially
above zero and materially below today's 90 %.
*Pass:* T-290-09 — over M ≥ 4000 draws on a need-free board, the observed reach
rate is in `[0.18, 0.27]`; and `> 0.02` is asserted separately with a message
naming D-5, so a future "simplification" to pure BPA fails loudly.

**R-9 — the noise FAMILY is unchanged.** The reach depth is still geometric in
`reach_decay` conditional on reaching, and still persona-independent.
*Pass:* `test_w2_04b_the_reach_branch_is_geometric_in_reach_decay` (`:248`) and
`test_w2_04b_the_reach_branch_is_persona_independent` (`:472`) pass with their
assertions **unmodified** (the helper correction in §7.2 is a fixture change, not
an assertion change).

**R-10 — one Bernoulli, same stream position, determinism intact.**
`effective_bpa_prob` consumes no RNG; `_pick_rng` stays a pure function of
`(rng_seed, pick_no)`.
*Pass:* `test_w2_05_same_seed_is_byte_identical` (`:584`),
`test_w2_05_per_pick_rng_is_a_function_of_seed_and_pick_only` (`:607`) and
`test_w2_11_resume_from_the_row_is_identical` (`:724`) pass unmodified.

### #290 — the acceptance case (see §4)

**R-11 — top-of-board integrity. Every clause is TWO-SIDED and named per
format.** Pinned `N = 1500`, seeds `range(N)`, 12-team linear, on **both**
`1qb_ppr` and `sf_tep`:

| Clause | Bound | shipped (both fmt) | measured after (1qb / sf) |
|---|---|---|---|
| 1a `P(#1 at pick 1)` | `0.43 <= p <= 0.75` | 0.455 | 0.455 / 0.638 |
| 1b `P(#1 falls past 3)` | `0.02 <= p <= 0.11` | 0.155 | 0.089 / 0.042 |
| 2 `P(Tate falls past 4)` | `p <= 0.10` | 0.171 | 0.073 / 0.073 |
| 3 `P(#7 taken at pick <= 4)` | `p <= 0.02` | 0.1147 | 0.0000 / 0.0000 |

*The upper bounds are the point.* Round 1's floor-only clause 1
(`>= 0.43`) **passed on the collapsed sf_tep board** (1.000 ≥ 0.43) — a test that
passed on the very bug it existed to catch. Clause 1b's *lower* bound catches the
same collapse from the other side (0.000 < 0.02). Clause 2's `== 0` was measured
false at any floor ≥ 1 and is now a bound. Clause 3 is unchanged and is the only
clause identical on both formats.
*Pass:* T-290-10, per format, with the shipped values in the docstring.
**T-290-14 is the primary collapse guard** — these distributional bounds are a
generously-set smoke alarm, not a fitted threshold.

**R-12 — the board is still varied, and the run rule actually applied.**
At the pinned `N = 1500`, distinct round-1 top-4 orderings must be
`25 <= n <= 120`, per format (shipped **171** — fails the upper bound, so this
test is failing-first-capable; MIN = 0 collapse gives 18 / 24 — fails the lower).
⚠ This statistic **scales with N**, so N is pinned exactly rather than bounded
below.
*Pass:* T-290-11.

### #291 — the affordance (D-7)

**R-13 — the pick affordance is visible BEFORE tap, and #277's tier information
is relocated rather than deleted.**
While the user is on the clock, every undrafted row renders the action label in
its trailing slot; the tier label moves to the row's meta line for those rows.
When the user is not on the clock, the row is byte-identical to today. The
section header reads "Tap to draft" and `OnTheClockCard` carries a one-line
instruction. No emoji, no new glyph, no new radius, ice only.
*Pass:* T-291-01 (Maestro: `assertVisible: "Tap to draft"` on the mock board
before any row tap) + T-291-02 (`npm run test:mock-mode-marker` green) +
observation against `docs/design/components.md` recorded in `status.md`.

### #292 — the lifecycle (D-8, all three)

**R-14 — ONE dismissal clears the mock surface, however many completed mocks
have accumulated.**
The recap screen exposes a header action that abandons the completed row; the
Mock card's complete state has **primary = "Start a new mock"**, secondary =
"View recap". Because `create_mock_draft` abandons only *active* rows
(`database.py:10739`) and the complete-fallback is `ORDER BY id DESC LIMIT 1`,
completed rows accumulate forever — so dismissing a completed mock must abandon
**every** completed row for that (user, league), not just the named one. Older
completed rows are unreachable from any UI, so nothing observable is destroyed.
*Pass:* **T-292-01 seeds THREE completed mocks** and asserts that after **one**
`POST /api/mock-draft/abandon`, `GET` returns `no_active_mock` — owner-scoped
(another user's rows untouched) and idempotent. Round 1's single-row version
passed while the defect stood. Plus T-291-03 (Maestro).

**R-15 — no reachable state of the Mock card renders zero interactive controls.**
The `errorText` branch gains a retry that calls `createMock.reset()` and refetches.
*Pass:* T-292-02 — a structural test over `MockEntryPanel.tsx` asserting that
every early-return branch contains either a `Button` or the `retry` slot.

**R-16 — a transient refusal cannot mute the card for the session.**
`postRefusal` is cleared on re-entering Mock mode and on opening the setup sheet.
*Pass:* T-292-03 — structural: `setPostRefusal(null)` appears in the
`DraftModeToggle` `onMode` handler and in the `onStart` handler.

**R-17 — the second mock genuinely creates.** Creating after a completed mock
returns a fresh **active** mock with the user reachable on the clock, and the
prior row goes `abandoned`.
*Pass:* T-292-04 (extends `test_w2_11_only_one_active_mock_survives_per_user_and_league`,
`:1330`) + T-291-03.

### D-16 — identity

**R-18 — a mock's `order[].owner_username` never renders a machine id.**
Both `_mock_league_context` (`:11437`) and `_mock_context_from_row` (`:11474`)
build the map through one shared helper reading `league_members`, with the ladder
`username → display_name → session username → "Team <fid>"`. A name is **omitted**
rather than emitted empty.
*Pass:* T-290-12 — route test: for an MFL-shaped league, no `order[]` or
`my_picks[]` entry's `owner_username` contains `"mfl:"`, and a franchise absent
from the member map renders exactly `"Team 0003"`.

**R-19 — no player lookup is ever attempted with an uncrosswalked id.**
Inherited from G1's R-7: MFL and Sleeper player ids share a numeric range, so a
raw MFL id can resolve to **the wrong player**. The mock's player half is safe by
construction (`ctx.player_rows` is keyed on `_rookie_player_ids`, our own id
space) and this change must not add an id to any lookup list.
*Pass:* T-290-13 — assertion: the set of ids `_mock_context_from_row` passes to
`dbs.database_players` is exactly `_rookie_player_ids(season)`; a fetcher that
raises on any other id completes a full render.

**R-20 — the resume path is fixed, not just the create path.**
*Pass:* T-290-12 is asserted against `GET /api/mock-draft` on an **existing** row,
not only against the create response.

### Invariants

**R-21 — no route contract changes.** `SCHEMA` unchanged; the key set of every
`/api/mock-draft` response unchanged; no new route.
*Pass:* the existing route tests (`test_mock_draft.py:956-1056`) pass unmodified.

**R-22 — no new platform egress, no new import that can reach one.**
*Pass:* `test_w2_13_the_engine_imports_nothing_that_can_reach_a_platform` (`:764`)
and `test_w2_13_a_full_mock_runs_with_the_test_mode_counters_untouched` (`:787`)
pass unmodified.

**R-23 — mobile typecheck stays clean.** `cd mobile && npx tsc --noEmit` exits 0
(baseline in this worktree: exit 0; `node_modules` here is a **real** install —
do not symlink the main checkout's, it lacks `@react-native-cookies/cookies`).

---

## 4. The Tate case

The operator's falsification handle. It must not evaporate into "feels better
now" — and it must not be turned into an assertion that measurement shows to be
wrong.

### 4.1 The plan's two blockers are closed

The plan could not establish Tate's consensus rank: `data/trade_finder.db` is
empty in this worktree and the value fixtures carry no names. **Both are
circumvented by the harness the plan itself cited.**
`backend.tests.test_mock_draft._rookie_ctx(fmt)` joins
`rookie_universe_2026.json` (names + positions) to
`ktc_blend_pipeline_2026-07-17.json` (values) through the shipped blend, needs no
DB, and reproduces the product's board exactly. **Spike A is closed, not
blocking.**

### 4.2 What it says

**Carnell Tate is the consensus #2 rookie**, on both `1qb_ppr` (1817.5, behind
Love's 1886.9) and `sf_tep` (1776.5). **Tate going 4th overall is a two-slot
fall, not a reach.** Under the shipped engine it happens 10.1 % of the time —
*less often* than Lemon (17.7 %), Tyson (16.0 %) or **Love, the consensus #1**
(15.8 %) landing there.

### 4.3 Model form or consensus pricing? — Both, and the tests separate them

The plan asked the right question and expected "model form". The honest answer is
**a model-form defect the operator noticed through the wrong symptom.**

- **Model form — real, and this PRD fixes it.** The engine is blind to value
  gaps, so the top of the board is near-uniform across seven players. That is why
  a #2 can be 4th, why a #1 can be 4th, and why a #7 can be 4th. R-11 kills it.
- **Pricing — possible, and this PRD cannot fix it.** The operator's stated
  reason ("value gaps between him and the other WRs") does not match the board:
  Tate → Tyson is 46.1 Elo and Tyson → Lemon is 24.9. (Round 1 called these "the
  two tightest gaps at the top" — 24.9 is indeed the tightest, but 46.1 ranks 5th
  of the first eight; the superlative is withdrawn and the conclusion does not
  need it.) **They are one run**, confirmed structurally: the first run at
  `m = 2.5` on 1qb_ppr is {Love, Tate, Tyson, Lemon}. Under a value-gap-driven tier rule — precisely
  what the operator asked for in the same sentence — Tate at pick 4 is
  *legitimate*: it means only that the two WRs he is genuinely tied with went
  first.

**Consequence the operator must see before build.** After this fix, Tate will
still go 4th about one time in six. What changes is *who can go ahead of him*:
Love (a real 69.5-Elo gap above) plus Tyson and Lemon (within 46 and 71) — and
**never** Sadiq, Concepcion or Price, who sit 79–219 Elo below him. If the
operator looks at a post-fix mock and still says "Tate 4th is unrealistic", the
complaint is about **the consensus pricing of Tate against Tyson and Lemon**, not
about the mock engine, and the fix lives in the DP/KTC blend — a different lane
entirely.

### 4.4 How the tests distinguish the two

| | Model-form defect | Pricing defect |
|---|---|---|
| Signature | a player from a *lower run* is taken ahead of the head's run | players *within one run* are taken in an order the operator dislikes |
| Test that catches it | **R-3 / R-11** — exact, deterministic, N seeds | **none, by design** — R-12 requires the within-run order to stay varied |
| Test that would mask it | an assertion that `P(Tate ≤ 4) → 0` | — |

This is why R-11 is written as three *board-integrity* assertions (consensus #1
holds 1.01, Tate never falls past 4, consensus #7 essentially never reaches pick
4) and **not** as the plan's "P(Tate ≤ 4) drops below a bar". Driving Tate off
pick 4 would require either a size clamp (D-9 forbids it) or a hard wall between
players 46 Elo apart (which would mean walling off almost every adjacent pair on
this board). The plan's secondary assertion is therefore **rejected and replaced**
— recorded in [`reconciliation-log.md`](./reconciliation-log.md).

### 4.6 What D-5 does and does not change — measured

The Planner objected that the spec changes *how often* a bot reaches, never *what*
it reaches for, and that D-5 asks the second question. **Measured, that premise is
wrong — and the objection's conclusion is still right, for a different reason.**

A `championship` bot with `severity[RB] = 1.0` and zero elsewhere, real board head,
N = 6000 seeded `cpu_pick` calls:

| Round / config | cap | P(picks an RB) | RB share of the reachable window | lift |
|---|---|---|---|---|
| r1, **shipped** | 3 | **0.693** | 0.250 | **2.77×** |
| r1, run rule + floor | 3 | 0.693 | 0.250 | 2.77× |
| r3, shipped | 15 | 0.685 | 0.250 | 2.74× |
| r3, run rule + floor | 10 | 0.683 | 0.182 | 3.75× |

**When severity is non-zero the shipped engine already steers hard toward need.**
So the plan's *"reaching today is ~entirely random"* is overstated, and this PRD
withdraws its Round-1 adoption of it. What is inert is **severity itself** — zero
for most (team, position) pairs in August — and when severity is zero there is no
direction to have.

That is what D-5 is really asking for. *"Reaching should more so be to fill a
position of need than just random"* is a statement about the **composition of the
reach population**: of all the deviations from BPA on a board, most should be
need-fills. `effective_bpa_prob` delivers exactly that — needy teams keep reaching
at 90 %, satisfied teams drop to ~30 % — **but only with R-7's denominator-weighted
aggregate.** Under a `max()` every ordinary roster scores 1.0 and the composition
never shifts.

**Stated for the operator (O-7): per-pick direction is unchanged at 2.77×; D-5 is
answered by re-weighting *who* reaches, not by changing what a reaching bot
prefers.** If the operator wants the per-pick lift itself raised, that is a change
to `mock_max_reach_slots` — a `model_config` product cap W2e deliberately narrowed
— and a separate item.

### 4.5 The board moves; the test must not silently rot

The pinned fixture is the 2026-07-17 blend. Production reprices continuously, so
"Tate is #2" is true of the fixture and was very probably true on 2026-08-10, but
is not permanent. R-11 is therefore written against **ordinal positions on the
fixture** (`pool[0]`, `pool[1]`, `pool[6]`) with the *names* asserted separately
in one place, so a consensus refresh produces one loud, obvious failure with a
message that says "the pinned board moved; re-read §4" rather than a silent
change of meaning.

---

## 5. Success criteria

1. `python3 -m pytest backend/tests/ -q` green. Baseline in this worktree:
   **2297 passed, 1 skipped**; the count rises by the number of new tests.
2. `cd mobile && npx tsc --noEmit` exit 0.
3. `bash mobile/scripts/testid-lint.sh` exit 0 (baseline verified in this
   worktree: **`testid-lint OK`, exit 0**). This is a required CI job.
4. `cd mobile && npm run test:mock-mode-marker` green.
5. The new Maestro flow `d3-mock-draft-loop.yaml` passes on the simulator, plus
   the Tier-1 suite (§7.4).
6. R-11's four numbers recorded in `status.md`, before and after.
7. The calibration regression bar (§8, D-10) recorded in `status.md`, before and
   after.

---

## 6. Out of scope

Named so the adversarial review can hold the line.

1. **Drafting for other teams** (D-7, explicit). The engine has no such call;
   `MockSetupSheet.tsx:110-120` renders "You're drafting for" as a read-only
   `fixed` value and `DraftRoomScreen.tsx:368-370` records why.
2. **Re-fitting `mock_bpa_prob` / `mock_reach_decay`** (D-10). A re-fit under the
   W2e caps is already owed from `build-w2e.md`; this change inherits that debt
   and does not create it. If the tripwire fires, §8 says what happens.
3. **Re-publishing a calibration artifact** (D-10). Run-and-record only.
4. **Any change to the W2e policy tables.** Changing either is a product decision
   requiring a re-gate (`mock_draft_service.py:104-113`).
5. **The 8-tier ladder, `tier_config.json`, or the cross-client tier enum.** A run
   is engine-internal; see [`hld-delta.md` §3](./hld-delta.md#3-new-engine-notion-the-run).
6. **`MOCK_MIN_TEAMS` client/server disagreement** — client `6`
   (`MockEntryPanel.tsx:41`) vs server `4` (`mock_draft_service.py:85`). A real
   fourth dead-end for 4- and 5-team leagues, but not a *second*-mock dead-end
   and not in D-8. Backlog item.
7. **`MockSetupSheet` busy-stranding** (`:182`). Not one of D-8's three.
8. **The plan's #292 backend work.** It does not exist (§2.3).
9. **`draft_picks` / `mock_drafts` seeding in `seed_ui_test_db.py`.** Not needed
   — §7.3 shows the flow is authorable against the existing `ffv3-predraft`
   corpus. Building an MFL seam for the harness stays G1's backlog item.
10. **Analytics instrumentation.** Waived with reason in [`scope.md` §1](./scope.md#1-analytics-scope).

---

## 7. Test plan

### 7.1 Prototype measurement already performed

To size the blast radius rather than guess it, the full engine change (§R-1…R-10)
was applied to this worktree as a **prototype**, `backend/tests/test_mock_draft.py`
was run, and the change was then **reverted**. No production code is delivered by
Phase 1. Results:

| Prototype | Result |
|---|---|
| Need-conditional weight alone (R-7…R-10) | **1 failed, 79 passed** (311 s) — the single failure `test_w2_04b_the_reach_branch_is_geometric_in_reach_decay`, `P(1)/P(0) = 0.069` vs an expected `0.5`. `test_w2_16_calibration_gate` **passed** — the D-10 tripwire did **not** fire. |
| Full change: `run_offset` at `m = 2.5, W = 9` composed at **both** call sites, `allow_cross = 0` in rounds 1-2 / `1` in rounds 3+, need-conditional weight at `floor = 0.25`, plus the §7.2 helper correction | **80 passed, 0 failed** (424 s). The D-10 tripwire did **not** fire. |

So the entire blast radius of #290 is: **one test-helper line**, explained and
mitigated in §7.2. Nothing else in the eighty-test mock suite moves. This is a
measured result, not an estimate — the working tree was restored to `7cea1fa`
immediately afterwards (`git status` clean apart from these docs).

Two cautions on reading it. First, it covers `test_mock_draft.py` only; the build
agent still owes the full `backend/tests/` suite (baseline **2297 passed, 1
skipped**). Second, a green run is not the D-10 regression bar — see §8 G-2.

### 7.2 The one shipped test that must change, and why it is not a weakening

`_reach_draws` (`test_mock_draft.py:230-238`) measures the reach law with
`needs = {pos: 0.0}` — which, under R-7, is no longer the branch the tests it
feeds are named after. Change the helper to `needs = {pos: 1.0}`.

The two assertions it feeds stay **verbatim**. The board is single-position, so
the need bonus `weight × severity × max_reach` is a **constant across every
candidate** and cancels out of the argmin: `argmin(rank − c − noise) ==
argmin(rank − noise)` exactly. The measured law is therefore identical under both
the shipped and the changed engine; the helper simply stops measuring the *tilt*
while claiming to measure the *branch*. A comment in the helper must say so, or
the next reader will read it as a weakened test.

**Nothing else in the shipped suite may be edited.** If any other assertion goes
red, that is a finding, not a fixture problem — stop and report it in `status.md`.

### 7.3 Backend pytest — `backend/tests/test_mock_draft.py` (additions only)

Determinism/seeding: every case below fixes `rng_seed` explicitly and drives the
shipped `build_settings` / `new_state` / `advance_cpu` with an **explicit
`order=`** (never the seeded shuffle) so the user's slot is fixed and the CPU run
length is constant. That is the reproducibility contract — the plan's own
measurements were skewed by a randomised order until it was pinned.

| ID | Level | Req | Assertion |
|---|---|---|---|
| T-290-01 | unit | R-1 | `run_offset` over a hand-built board: an ordinary gap sequence; a boundary at index 0; a boundary at the last gap; an all-tied block (no boundary); an all-`None` head (returns `n-1`); a valued→unvalued frontier (boundary); `n == 0` and `n == 1` (return 0); `allow_cross=1` skips exactly one boundary |
| T-290-02 | AST | R-1 | `test_w2_14` (`:708`) still finds zero `sorted`/`.sort` — unmodified, re-run |
| T-290-03 | data | R-2 | On the pinned board, for `1qb_ppr` **and** `sf_tep`, `4 <= median(run sizes) <= 5`, where the partition is the **ONE-PASS** walk: scan the full pool once, cut at every boundary, measure the resulting block sizes. ⚠ The alternative reading — sequential `run_offset(pool[start:])` re-scans — gives 4.0 / **3.0** and fails this bar on sf_tep, so the definition is pinned here or the test is unimplementable. Docstring records the measured `5.0 / 5.0` at `m = 2.5, W = 9` |
| T-290-04 | behavioural | R-3 | N ≥ 200 seeds, 12-team linear, rounds 1-2: for every CPU pick, its 0-based position in the remaining pool `<= run_offset(head, allow_cross=0)`. **Exact** |
| T-290-05 | behavioural | R-4 | Same, rounds 3+: position `<= run_offset(head, allow_cross=1)`; **and** at least one sampled pick has position `> run_offset(head, allow_cross=0)` |
| T-290-06 | property | R-5 | For every round 1..8 and a synthetic head, `effective_cap <= round_reach_cap(round)`; budget spent ⇒ `effective_cap == 0` |
| T-290-07 | structural + behavioural | R-6 | AST over `mock_draft_service.py`: a `run_offset(` call appears inside **both** `advance_cpu` and `simulate_reaches`. Plus: a `simulate_reaches` replay's depths obey the same bound |
| T-290-08 | unit | R-7 | **`need_pressure` first:** all positions filled → `0.0`; a standard lineup with only TE unfilled → `≈0.111` (**not** 1.0 — this is the assertion that would have caught the `max()` defect); all unfilled → `1.0`; a WR-corps hole scores strictly higher than a TE-only hole. **Then `effective_bpa_prob`:** `(0.10, {}, 0.0)` == `1 − 0.9×0.25`; `(0.10, {}, 1.0)` == `0.10`; `(0.10, {}, 0.5)` == `1 − 0.9×0.625`; monotone non-increasing in pressure |
| T-290-09 | statistical | R-8 | M ≥ 4000 draws, need-free board: reach rate in `[0.18, 0.27]`, and `> 0.02` asserted separately with a message naming D-5 |
| T-290-10 | behavioural | R-11 | **Both formats, named explicitly.** Pinned `N = 1500`, seeds `range(N)`: `0.43 <= P(pool[0] at 1) <= 0.75`; `0.02 <= P(pool[0] past 3) <= 0.11`; `P(Tate past 4) <= 0.10`; `P(pool[6] at <= 4) <= 0.02`. Per-format expected values in the docstring (1qb / sf: `0.455/0.638`, `0.089/0.042`, `0.073/0.073`, `0.0000/0.0000`) alongside shipped (`0.455 / 0.155 / 0.171 / 0.1147`, identical on both formats). Separate one-line assertion that `pool[1]` is "Carnell Tate", message pointing at §4.5 |
| T-290-11 | behavioural | R-12 | **Both formats.** At the pinned `N = 1500`: `25 <= distinct round-1 top-4 orderings <= 120`. Shipped is **171** ⇒ fails the upper bound on unfixed code (so this test has teeth); the MIN = 0 collapse gives 18 / 24 ⇒ fails the lower. Docstring must state that the statistic scales with N and that N is pinned for that reason |
| **T-290-14** | **structural** | **R-2b** | **The primary collapse guard.** Deterministic, seedless, both formats: `min(round_reach_cap(1), max(run_offset(pool[:24], allow_cross=0), MOCK_RUN_MIN_OFFSET)) >= 1`. Fails at the *cause* rather than a distributional symptom. Un-floored on sf_tep this is 0 |
| **T-290-15** | **unit** | **R-2b** | `MOCK_RUN_MIN_OFFSET < round_reach_cap(1)`, with a message naming the failure: at MIN = 3 the round-1 composition is `min(3, max(off, 3)) == 3` for every board and the feature is silently disabled in round 1 |
| **T-290-16** | **AST** | **R-7b** | `need_pressure(` appears inside **both** `advance_cpu` and `simulate_reaches` — the same both-call-sites rule as T-290-07 |
| T-290-12 | route | R-18 / R-20 | `GET /api/mock-draft` on an **existing** row for an MFL-shaped league: no `order[]` / `my_picks[]` `owner_username` contains `"mfl:"`; a franchise absent from the member map renders exactly `"Team 0003"`; a member with no stored name is **omitted** (⇒ `null`), never `""` |
| T-290-13 | route | R-19 | A `database_players` stub that raises on any id outside `_rookie_player_ids(season)` completes both create and GET without raising |
| T-292-01 | route | R-14 | **Seed THREE completed mocks** for one (user, league). `POST /api/mock-draft/abandon` on the newest → `{ok: true}`, and **one** subsequent `GET` returns `{empty: true, reason: "no_active_mock"}` — not the second-newest recap. Idempotent on a repeat call; another user's completed rows in the same league are untouched; the same user's completed rows in a *different* league are untouched. ⚠ Round 1's single-row version passed while the defect stood |
| T-292-04 | db+route | R-17 | Extends `:1330` — create after a **complete** row leaves the complete row untouched and the new row active with the user reachable on the clock |
| — | regression | R-9/R-10/R-21/R-22 | `:248 :265 :332 :347 :362 :375 :392 :402 :443 :472 :584 :595 :607 :619 :724 :742 :764 :787 :956-1056 :1330` all pass **unmodified** |
| — | tripwire | D-10 | `test_w2_16_calibration_gate` (`:1809`) passes unmodified. See §8 |

**Failing-first is mandatory** for **T-290-04, T-290-10, T-290-11, T-290-14 and
T-292-01**. Run each against `7cea1fa` and paste the failure text into
`status.md` before the fix lands. T-290-11 and T-290-14 are on this list
*because* Round 1's versions of them passed on the defect they existed to catch —
a test that cannot fail on unfixed code is not evidence.

**Seeding, for reproducibility (I-13):** every distributional test iterates
`for seed in range(N)` with `N` a module constant, builds settings with an
**explicit `order=`** (never the seeded shuffle) so the user's slot is fixed, and
relies on `_pick_rng(state, pick_no) = Random(rng_seed*10007 + pick_no)`. All
figures in this PRD reproduce to three decimals across runs and across machines.

### 7.3 Maestro

**Correction to the plan (R9).** The plan concluded there is "no hermetic way to
seed a mock" and that `ffv3-predraft` is "blocked by `draft_order: null`". That
is wrong: `draft_order: null` only makes `_mock_real_draft` return
`order_source: randomized` (`server.py:11555-11557`) — it does not block a mock.
Verified against the fixture: `ffv3-predraft` is **12 teams, `pre_draft`, 4
rounds, linear** (`league/1312140920132497408.json`,
`draft/1312140920136699904.json`), so every one of `mockBlock`'s six predicates
passes: not `startup`, `teams >= 6`, not `live`, not `complete`, and
`class_not_loaded` cannot fire because `d2-draft-room-order-not-set.yaml` already
asserts `draft-room.undrafted-row..*` renders on this very league with the
`standard` profile.

**No engine, route or `mock_drafts`-seeding work is needed** — the flow creates
the mock live through the shipped UI against the ffv3 cassette, and G3's finding
that `seed_ui_test_db.py` writes no `draft_picks` (it writes no `mock_drafts`
either) does not bite.

⚠ **But there IS a seeding precondition, and Round 1 wrongly called it "zero
seeder work".** `d2` declares its profile as *"standard + ffv3-predraft corpus
merged into the fixture dir"* — and **no tooling implements that merge.**
Verified: `backend/tests/fixtures/profiles/standard.json` declares exactly one
league (`990000000000000001`); d1 and d2 target `1312076055586050048` and
`1312140920132497408`, which appear in **no** profile; and `git grep` finds d1/d2
referenced only by docs and their own YAML — **no suite file, no runner** — so
their current green status is unverified.

**This is a named precondition of the Tier-1 sim gate, not an assumption.** Two
options, to be sized by the build agent before authoring the flow:
1. Add the ffv3 league to a profile's `leagues[]` (or add a `mock.json` profile)
   so `leagues.row.1312140920132497408` renders — the smaller change, and it
   fixes d1/d2 as a side effect.
2. Implement the corpus-merge step the d1/d2 headers already assume.

Also for the flow author: ffv3's **top-level `rounds` is `null`** — the 4 lives in
`settings.rounds`.

**New flow:** `mobile/.maestro/flows/rookie/d3-mock-draft-loop.yaml`,
`tags: [rookie, draft-room, mock]`, profile `standard` + the `ffv3-predraft`
corpus merged into the fixture dir (identical to `d2`), flags `draft.room` /
`draft.mock` / `draft.tab` ON.

1. sign in `qa_standard` → `leagues.row.1312140920132497408` → League tab →
   `league-summary.league-home` → `league.draft-room-row`
2. `draft-room.mode.mock` → `mock-entry.card` + `mock-entry.start` visible
3. `mock-entry.start` → `mock-setup-sheet` → `mock-setup.rounds.minus` × 3
   (4 → 1, so the user makes exactly one pick) → assert
   `mock-setup.rounds.value` → `mock-setup.type.linear` → `mock-setup.start`
4. `mock-draft.rail` + `mock-draft.on-the-clock` visible;
   **`assertVisible: "Tap to draft"`** — *#291's acceptance, before any row tap*
5. `mock-draft.undrafted-row..*` → `mock-draft.confirm` → `mock-draft.confirm.draft`
6. `mock-draft.recap` visible → back → `mock-entry.run-it-back` is the
   **primary** and visible
7. `mock-entry.run-it-back` → `mock-setup.start` → `mock-draft.on-the-clock`
   again — ***#292's acceptance***
8. Drive the second mock to its recap, then **dismiss it via `mock-draft.end`**
   and assert the room's card reaches `mock-entry.start` ("No mock running") —
   ***R-14's acceptance***: with two completed mocks on file, ONE dismissal must
   clear the surface, not reveal the previous recap

**testID audit — every id above already exists**, verified by
`grep testID` in source: `signin.username-input`, `signin.continue-btn`,
`leagues.row.*`, `tab.league`, `league-summary.league-home`,
`league.draft-room-row`, `draft-room.mode.mock` (`MockChrome.tsx:85`),
`mock-entry.card` / `.start` / `.run-it-back` / `.recap`
(`MockEntryPanel.tsx`, `DraftRoomScreen.tsx:799-836`), `mock-setup-sheet`,
`mock-setup.rounds.minus` / `.value`, `mock-setup.type.linear`,
`mock-setup.start` (`MockSetupSheet.tsx:103-190`), `mock-draft.rail`,
`mock-draft.on-the-clock`, `mock-draft.undrafted-row.*`, `mock-draft.confirm`,
`mock-draft.confirm.draft`, `mock-draft.recap` (`MockDraftScreen.tsx`).
**No new testID is referenced by the flow.** `mock-entry.retry` (R-15) is added
to source but deliberately **not** referenced, so it needs no allow-list entry.

**Lint baseline was RUN, not assumed:** `bash mobile/scripts/testid-lint.sh` in
this worktree ⇒ `testid-lint OK`, exit 0. Re-run after authoring the flow;
`id:` selectors only, **no `- sleep`**, no `point:`, no `tapOn: "text"` /
`tapOn: text:` (an `assertVisible: "Tap to draft"` is a *text assertion*, which
the linter permits — `d2` already uses `assertVisible: "Round ownership"`).

**Partial waiver, explicit.** The flow does **not** cover:
- **#292 dead-ends 2 and 3** (sticky create error, sticky `postRefusal`).
  *Reason:* both require injecting a server failure or a typed-empty refusal
  mid-session, and the harness has no fault-injection seam. Covered instead by
  the structural tests T-292-02 and T-292-03, which assert the *code shape* that
  makes those states recoverable. Named as a backlog item: a fault-injection knob
  for the mobile harness.
- **#290's engine behaviour.** *Reason:* not observable through a UI assertion —
  it is a distribution over seeds. Covered by T-290-01…T-290-11.
- **D-16.** *Reason:* the harness is Sleeper-fixture-driven with **zero** MFL
  references in `backend/test_users.py`, `backend/test_support.py`, `qa/` or
  `mobile/.maestro/*.yaml`; an MFL flow is not authorable without first building
  harness support. Covered by T-290-12/13 and folded into G1's live-league QA
  pass on Dependables (62846) — record the Mock Draft screen's owner names in the
  same pass.

### 7.4 Mobile static gates

- `cd mobile && npm run test:mock-mode-marker` — **every commit** touching either
  screen. Not in CI; only `maestro-testid-lint` is.
- `bash mobile/scripts/testid-lint.sh` — CI job.
- `cd mobile && npx tsc --noEmit`.

### 7.5 Pre-ship simulator gate

**Tier 1** (mobile screen + state change) per `docs/runbook.md`
§ Pre-ship simulator gate: **full 11-flow smoke suite + the feature's own flow**
(`d3-mock-draft-loop.yaml`), plus `d1-draft-room-complete.yaml` and
`d2-draft-room-order-not-set.yaml` as the shared-component no-regression check
(`UndraftedRowView` is shared). Log in `living-memory/TEST_LEDGER.md`; write
`qa/sim-runs/last-sim-run.json`. Enforced locally by `githooks/pre-push`.

---

## 8. Guardrails

**G-1 — the calibration tripwire (D-10). Standing instruction to the build
agent.** `test_w2_16_calibration_gate` (`test_mock_draft.py:1809-1853`) asserts
`report["all_pass"] is False`. If this change makes the model **pass**, the suite
goes RED with the message *"the calibration verdict MOVED to passing"*.

> **If the tripwire fires: STOP and escalate to the orchestrator.**
> Do **not** edit, skip, xfail or relax the assertion. Do **not** re-point
> `mds.CALIBRATION_ARTIFACT`. A passing verdict means the full W2e re-fit +
> artifact re-publish (`mock-calibration-2026-08e.md`) becomes mandatory, and
> that is an operator decision with a real cost, not a side effect of a feedback
> fix. Record the full `report` JSON in `status.md` and hand it up.

Under the need-conditional prototype the tripwire **did not fire** (§7.1).

**G-2 — the regression bar (D-10).** The gate test is one-sided and cannot detect
a distribution regression. Run
`python3 -m pytest backend/tests/test_mock_draft.py -k "w2_16 or w2_17 or w2_19"`
before and after and record both. **Abort and escalate** if either:
(a) any of the three paired-mean deltas grows beyond its 08d value
(**1.648 / 3.605 / 2.026**); or (b) any of the three KS bars moves from pass to
fail. Record the numbers in `status.md` **regardless of outcome** — the artifact
is not re-published either way.
⚠ Note the caveat the module itself records at `:1846-1853`: since W2e the KS
bars fail too, because the fitted parameters and the caps disagree. So (b) is
measured against the *current* run's values, captured before the change, not
against 08d's published KS numbers.

**G-2b — the calibration harness cannot see the need half (I-9).**
`_lakeview_corpus` prices rosters with **rookie-only** Elo, so every viable count
is 0 and every owner enters `simulate_reaches` at pressure 1.0 — under `max` and
under the denominator-weighted aggregate alike. **The D-10 regression bar
therefore reports the run rule's effect and nothing at all about R-7/R-8.** Record
that sentence beside the numbers in `status.md`, so a green-looking bar is not
read as broader validation than it is. The harness artifact is pre-existing and
out of scope to fix here.

**G-3 — flags are ON; this ships lit.** `draft.mock`, `draft.room`, `draft.tab`,
`draft.rank_inline` are all `true`. There is no dark landing. Treat the Maestro
gate as load-bearing, not ceremonial.

**G-4 — `check-mock-mode-marker.js` is the highest-probability breakage** for
#291/#292 and is **not** in CI. Constraints it enforces are enumerated in
[`lld-delta.md` §6.5](./lld-delta.md#65-structural-constraints-this-must-not-break).

**G-5 — pre-existing persisted mocks replay differently** after this change,
because truncating the candidate list changes how many `_gumbel` draws the
scoring loop consumes. No test and no invariant breaks: INV-10 promises that one
build replays a seed identically, not that two builds agree. One line in the
release note.

**G-6 — both `run_offset` call sites, or neither.** Applying the rule in
`advance_cpu` but not `simulate_reaches` would silently invalidate the
calibration harness. R-6 / T-290-07 exist for this.

**G-7 — file ownership.** G2 owns `backend/mock_draft_service.py`,
`mobile/src/screens/MockDraftScreen.tsx`, the `/api/mock-draft` shims in
`backend/server.py` (~`:11380-11530`), `backend/tests/test_mock_draft.py`, the
new Maestro flow, and this folder. **G2 additionally needs
`mobile/src/screens/DraftRoomScreen.tsx` and
`mobile/src/components/draft/MockEntryPanel.tsx`** — the batch plan's ownership
table does not list either; G1's PRD R-14 states G1 touches **no** file under
`mobile/`, and G3 owns only `LeagueSummaryScreen.tsx`, so the claim is
uncontested. **Raise it to the orchestrator for confirmation before build.**
G2 **releases** `backend/database.py` (no edit needed) and does not touch
`config/features.json`, `docs/api-reference.md` or
`docs/cross-client-invariants.md` (orchestrator-owned; text proposed in
[`scope.md`](./scope.md)).

---

## 9. Sequencing

The plan proposed: reproduce #292 → #292 → #291 → #290 (parallel to #291).
**Confirmed, with one amendment and one simplification.**

| # | Step | Note |
|---|---|---|
| 0 | ~~Reproduce #292~~ | **Dropped.** D-8 cancels the diagnostic spike and rules all three dead-ends in scope. |
| 1 | **#292** — client lifecycle | Lands first: it is what makes the mock loop iterable for the operator and for #290's build agent. Now **mobile-only** (§2.3), so it is smaller than the plan assumed. |
| 2 | **#291** — affordance | Serialised behind #292: both touch `DraftRoomScreen.tsx` and `MockDraftScreen.tsx`. |
| 3 | **#290 + D-16** — backend | **Parallel with #291** once #292 has landed: file sets are disjoint (backend vs mobile) and #290/D-16 both live in G2's backend region. Confirmed — and the amendment is that D-16 rides with #290 rather than being sequenced separately, since both are `mock_draft_service`/`server.py` edits by the same owner. |
| 4 | Maestro flow + Tier-1 sim run | Last: the flow asserts copy introduced in steps 1-2. |

Within the backend lane, do **#290 before D-16**: #290 is where the calibration
tripwire can fire, and discovering that after an identity refactor is more
expensive to unwind.

---

## 10. Requirement → test matrix

Every item maps to ≥ 1 requirement; every requirement maps to ≥ 1 test.

| Item | Requirements |
|---|---|
| **#290** (tiers) | R-1, R-2, R-2b, R-3, R-4, R-5, R-6, R-11, R-12 |
| **#290** (need-driven reaching) | R-7, R-7b, R-8, R-9, R-10 |
| **#291** | R-13 |
| **#292** | R-14, R-15, R-16, R-17 |
| **D-16** | R-18, R-19, R-20 |
| invariants | R-21, R-22, R-23 |

| Req | Tests |
|---|---|
| R-1 | T-290-01, T-290-02 |
| R-2 | T-290-03 |
| R-2b | T-290-14, T-290-15, T-290-06 |
| R-3 | T-290-04 |
| R-4 | T-290-05 |
| R-5 | T-290-06 + `:332`, `:362` |
| R-6 | T-290-07 |
| R-7 | T-290-08 |
| R-7b | T-290-16 |
| R-8 | T-290-09 |
| R-9 | `:248`, `:472` (unmodified) |
| R-10 | `:584`, `:607`, `:724` (unmodified) |
| R-11 | T-290-10 |
| R-12 | T-290-11 |
| R-13 | T-291-01 (Maestro), T-291-02 (marker), design-review observation |
| R-14 | T-292-01, T-291-03 (Maestro) |
| R-15 | T-292-02 |
| R-16 | T-292-03 |
| R-17 | T-292-04, T-291-03 |
| R-18 | T-290-12 |
| R-19 | T-290-13 |
| R-20 | T-290-12 (asserted on GET of an existing row) |
| R-21 | `:956-1056` (unmodified) |
| R-22 | `:764`, `:787` (unmodified) |
| R-23 | `npx tsc --noEmit` |

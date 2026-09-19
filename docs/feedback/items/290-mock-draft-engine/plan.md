# Plan — G2: Mock draft engine, lifecycle, interactivity (#290 / #291 / #292)

> Planner output, Phase 1 of the `/feedback` pipeline. **Plan only — no production code.**
> Worktree `.claude/worktrees/fb-289-294`, branch `feedback-289-294`, based on `origin/main` @ `7cea1fa`.
> Author: planner agent, 2026-08-10.

Three feedback items, all app 1.11.0, user `mattmurf77`, filed 2026-08-10.

| ID | Screen | Verbatim |
|---|---|---|
| #290 | MockDraft | "I think something's broken. The draft logic needs its own set of tiers that should take precedence when drafting these tiers should be tight groups of 4-5 players. The mock I just did for ffv3 league has Tate going 4th overall which feels too unrealistic based on value gaps between him and the other WRs. Also reaching should more so be to fill a position of need than just random." |
| #291 | MockDraft | "The mock draft should be interactive. The user should get to draft their own players at the very least." |
| #292 | DraftRoom | "Can't do a second mock draft" |

---

## Table of contents

1. [Reproduction verdict per item](#1-reproduction-verdict-per-item)
2. [Problem statement per item](#2-problem-statement-per-item)
3. [Root cause per item](#3-root-cause-per-item)
4. [Approach](#4-approach)
5. [Platforms touched and sequencing](#5-platforms-touched-and-sequencing)
6. [Risks](#6-risks)
7. [File-ownership proposal](#7-file-ownership-proposal)
8. [Spike needs](#8-spike-needs)
9. [Test plan seed](#9-test-plan-seed)
10. [Open questions for the operator](#10-open-questions-for-the-operator)

---

## 1. Reproduction verdict per item

**Precondition check — has the code moved since 1.11.0 shipped?** No. Every commit touching
the mock-draft surface predates the 2026-08-10 report:

| Commit | Date | What |
|---|---|---|
| `8e146a3` … `023f747` | ≤ 2026-08-07 | W2–W2d engine + calibration |
| `fefe72f` | 2026-08-08 | W2e round-tiered reach caps + frequency budget |
| `6caca35` | 2026-08-08 | `CPU_MODEL_VALIDATED = True` — **operator override**, not a statistical pass |
| `4deaf31` | 2026-08-09 | #277 tier labels (touched `DraftRows.tsx`; no mock-logic change) |

`git log --format="%h %ad" --date=short -- backend/mock_draft_service.py` shows nothing after
`6caca35`. HEAD is `7cea1fa` (2026-08-10). **No mock-draft behaviour changed between the tested
binary and current `origin/main`.**

Flags are all ON — this surface is **lit in production**, not dark:
`config/features.json:149` `draft.room=true`, `:157` `draft.mock=true`, `:169` `draft.tab=true`,
`:156` `draft.rank_inline=true`. `backend/mock_draft_service.py:294` `CPU_MODEL_VALIDATED = True`.

### #290 — REPRODUCES. Confirmed by measurement, not inspection.

The engine has **no tier or value-gap concept anywhere**. `cpu_pick` scores
`rank - need_bonus - noise` where `rank` is the 1-based *list position* in the remaining
consensus pool (`backend/mock_draft_service.py:646-652`). Value is never read — the only place
`value` is touched in the whole module is `_block_rank`
(`backend/mock_draft_service.py:1144-1147`), which is calibration-harness-only and tests for
*exact equality*, not gaps.

I ran the shipped `cpu_pick` under the shipped defaults
(`bpa_prob=0.10` `:113`, `reach_decay=0.70` `:114`, `max_reach=3.0` `:96`,
round-1 cap 3 / budget 3 `:154`,`:159`), 200k draws per round, severity pinned to 0:

| Round | cap | P(d=0) | P(d=1) | P(d=2) | P(d=3) | … | P(reach>0) |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 0.455 | 0.249 | 0.174 | 0.123 | — | **0.545** |
| 2 | 5 | 0.405 | 0.214 | 0.150 | 0.105 | 0.075 / 0.051 | 0.595 |
| 3+ | 15 | 0.371 | 0.189 | 0.133 | 0.093 | … 0.001 @ d=15 | 0.630 |

Then a full seeded round-1 replay (12 teams, 20k sims, budget consumed in pick order exactly as
`advance_cpu:929-943` does it):

```
pick #4: consensus rank taken there —
   c4=0.186  c1=0.164  c3=0.155  c5=0.149  c6=0.131  c7=0.109  c2=0.108
P(consensus rank r goes at or before pick 4):
   #2 → 0.836   #3 → 0.749   #4 → 0.631   #5 → 0.423   #6 → 0.253   #7 → 0.109
```

So: **the consensus #7 rookie goes 4th overall or earlier 10.9 % of the time, and #6 does 25 % of
the time — and the model is indifferent to whether the Elo gap between #4 and #7 is 5 points or
300.** At pick 4 the modal consensus rank is only 18.6 % likely; the distribution is near-flat
across ranks 1–7. The operator's "Tate going 4th overall … feels too unrealistic based on value
gaps" is the model behaving exactly as specified. **Not a defect in the implementation — a defect
in the model's form.** That is the same class of finding as W2a and W2b
(`backend/mock_draft_service.py:21-34`).

The second half ("reaching should more so be to fill a position of need than just random")
reproduces as well, and is quantifiable: the need term and the noise term are **independent
additive terms** (`:648-650`). `bonus = need_weight × severity × max_reach`, and
`need_weight = trade_service.outlook_alpha(outlook)` (`:555-562`), whose defaults are
`championship 1.0 / contender 0.75 / not_sure 0.5 / rebuilder 0.25 / jets 0.1`
(`backend/database.py:1732-1736`). A `not_sure` bot with a *maximal* need therefore gets
`0.5 × 1.0 × 3.0 = 1.5` slots of pull — while the noise branch alone moves 3 slots 12.3 % of the
time with **no need at all**. And severity is `clamp01((S+B−viable)/(S+B))` (`:545-552`) with
`VIABLE_ELO_FLOOR = 1280` (`:194`): in August, most dynasty rosters already hold `S+B` viable
bodies at most positions, so severity is 0 for most (team, position) pairs and the need term is
**effectively inert**. Reaching today is ~entirely random.

### #291 — REPRODUCES, but **not as written**. The capability exists; the affordance does not.

The orchestrator was right to suspect this one. The pick path is fully wired and fully working:

- `mobile/src/screens/MockDraftScreen.tsx:471` — `onPress={() => pickMutation.mutate(selected)}`
- `:157-169` — the mutation, `:426` — `onPress={isUserTurn ? setSelected : undefined}`
- `backend/server.py:11744-11779` — `POST /api/mock-draft/pick`
- `backend/mock_draft_service.py:947-960` — `apply_user_pick`

I drove the engine end-to-end with a synthetic 12-team / 4-round league and a 60-rookie priced
pool. Result: `advance_cpu` stopped after 8 CPU picks with
`on_the_clock = {pick_no: 9, round: 1, slot: 9, roster_id: 'u5', is_user: True}`; the user then
took **4 turns**, all 4 recorded with `by: "user"`, and the mock completed at 48 picks. This is
also pinned by two existing tests — `test_mock_draft.py:619`
(`next_pick(state)["is_user"] is True` after `advance_cpu`) and `:443`.

**So "the user should get to draft their own players" is already true — and invisible.**
The root cause is a missing visual affordance; see §3. **Do not build an interactivity feature.**

One residual ambiguity worth surfacing: "at the very least" may mean he *also* wants to draft for
other teams. That is explicitly out of v1 — `MockSetupSheet.tsx:110-120` renders "You're drafting
for" as a read-only `fixed` value and `DraftRoomScreen.tsx:368-370` says "Read-only on purpose:
`user_owner_id` IS the session user and drafting for another team is out of v1 (the engine has no
such call)." Q6 in §10.

### #292 — REPRODUCES as a dead-end, but the **precise trigger is not determinable from reading**.

There is no hard block on creating a second mock at the data layer. `create_mock_draft`
(`backend/database.py:10723-10748`) abandons any prior *active* row and inserts a new one in the
same transaction; `test_mock_draft.py:1330` pins that a second create works and the first goes
`abandoned`. My e2e run confirmed a second `build_settings` → `new_state` → `advance_cpu` cycle
runs clean.

What I *can* prove from code are **three distinct dead-ends in the room's Mock card**, any of
which produces exactly "can't do a second mock draft":

1. **A completed mock is permanently "current", and the only escape is a ghost button.**
   `load_current_mock_draft` (`backend/database.py:10762-10785`) falls back to the most recent
   `status="complete"` row with **no time bound and no dismissal path**. `MockDraftScreen`'s only
   abandon control is the header "End", rendered *only while* `state?.status === 'active'`
   (`MockDraftScreen.tsx:200-212`) — so a finished mock can never be cleared. The room therefore
   shows "Mock complete" forever, with **primary = "View recap"** and the only way forward as the
   **secondary ghost "Run it back"** (`DraftRoomScreen.tsx:823-830`). The eye goes to the primary;
   the primary returns you to the same recap you just left. This is my leading hypothesis.
2. **A single failed create permanently replaces the card with a buttonless error view.**
   `MockEntryPanel` checks `errorText` *before* rendering any button
   (`MockEntryPanel.tsx:90-96`), and `errorText` folds in `createMock.isError`
   (`DraftRoomScreen.tsx:625-631`). React-query mutation error state persists until the next
   `mutate`/`reset`, and there is **no `onError` handler** on `createMock`
   (`DraftRoomScreen.tsx:278-294`) and no retry control in the error view. Once a create fails,
   the panel has no button at all until the screen unmounts.
3. **`block` short-circuits the whole panel, including both buttons.**
   `MockEntryPanel.tsx:72-80` returns a muted card with a disabled dead CTA and no `primary`
   prop whenever `block` is non-null — and `mockBlock` is computed from the *real* board, not the
   mock (`DraftRoomScreen.tsx:298-353`). Six triggers: sticky `postRefusal` (never cleared,
   `:300`), `class_not_loaded` (`:311`), `board.kind === 'startup'` (`:322`),
   `board.teams < 6` (`:330` — note the client constant is `MOCK_MIN_TEAMS = 6` at
   `MockEntryPanel.tsx:41` against the server's `4` at `mock_draft_service.py:85`),
   `board.state === 'live'` (`:338`), `board.state === 'complete'` (`:347`).

**Verdict: reproduces.** Which of the three the tester hit is investigation work for the build
task — see §3 and the diagnostic in §9.

---

## 2. Problem statement per item

**#290.** The mock's CPU drafters choose by *rank distance* over the consensus board and are blind
to *value distance*. A 3-slot round-1 reach costs the same whether it crosses a 5-Elo gap or a
300-Elo cliff, so the bots routinely jump a genuine talent tier and the board reads as noise
rather than as drafting. Separately, reaching is driven by an unconditional noise draw rather
than by roster need, so a team with a full WR room reaches for a WR as readily as a team with
none.

**#291.** The mock board accepts taps and the user genuinely drafts for their own team, but the
surface gives a sighted user no signal that this is true. The rows are the same component with
the same styling as the read-only Draft Room, the section header uses the same words, and the
"Pick" label appears only *after* selection. A tester arriving from a screen whose stated
promise is "Fantasy Trade Finder never drafts for you" reasonably concludes the mock is a
spectator view.

**#292.** After a mock ends, the Draft Room's Mock card offers a prominent path back to the recap
and a recessive path to a new mock, and there are at least two states (sticky create error,
sticky `postRefusal`) in which the card offers no path at all. The user cannot reliably get a
second mock.

---

## 3. Root cause per item

### #290 — two distinct causes, both model-FORM, both in `cpu_pick`

**(a) The scoring metric is rank, not value.**
`backend/mock_draft_service.py:646-652`:
```python
for rank, row in enumerate(candidates_ranked, start=1):
    bonus = weight * float(needs_for_team.get(pos, 0.0)) * float(max_reach)
    noise = _gumbel(rng, scale) if reaching else 0.0
    score = rank - bonus - noise
```
`row["value"]` is present on every candidate (`draft_board_service.py:938-968` puts `value` and
`valued` on each undrafted row) and is **never read**. The reach cap
(`round_reach_cap`, `:164-166`) and the truncation that enforces it (`:637-638`) are likewise
pure rank arithmetic. There is no tier, cluster, run, or gap concept in the module — confirmed by
an exhaustive search: the codebase has **zero gap-based tier detection anywhere**; every shipped
tier boundary is a fixed absolute-Elo floor (`backend/tier_config.json`,
`ranking_service.py:1243-1268`), a fixed rank cut (`tier_size = 24.0`,
`database.py:1699`), or a fixed raw-value threshold (`trade_service.py:1010-1012`).

**(b) Need and noise are independent additive terms, and need is near-inert.**
Same lines. `reaching` is a single Bernoulli on `bpa_prob` drawn *before* and *independently of*
any need (`:643`), so ~90 % of picks enter the reach branch regardless of roster state. Measured
magnitudes above: max need pull for a `not_sure` bot is 1.5 slots against a noise branch that
reaches the full 3-slot round-1 cap 12.3 % of the time. And severity (`:545-552`) is 0 whenever a
team already holds `S+B` bodies at or above `VIABLE_ELO_FLOOR = 1280` (`:194`), which is the
common case in August.

### #291 — the row has no visual affordance

`UndraftedRowView` is shared verbatim between the read-only room and the mock
(`MockDraftScreen.tsx:73` imports it from `DraftRoomScreen`). The trailing "Pick" label is gated
on `selected`:

`mobile/src/screens/DraftRoomScreen.tsx:1325-1327`
```tsx
{actionLabel && selected ? (
  <Text style={draftRow.rowAction}>{actionLabel}</Text>
) : row.valued ? ( … <TierBadge … /> … )
```

So before the first tap the mock row is **pixel-identical to the read-only room row** — same
`draftRow.undraftedRow` style, same TierBadge in the trailing slot, no chevron, no glyph. The
only visual difference is the transient `pressed` background
(`DraftRoomScreen.tsx:1386-1390`). Accessibility is handled — the Pressable carries
`accessibilityHint="Select this rookie, then confirm the pick"` (`:1375-1377`) — so **VoiceOver
users are told and sighted users are not.** Compounding it, the section header is the same
"Still on the board" the room uses (`MockDraftScreen.tsx:386`), and `OnTheClockCard` says
"You're on the clock" (`:537`) without ever saying *how* to act.

### #292 — investigation is part of the build task

The three dead-ends in §1 are each provable, but which one the tester hit is not. The report was
filed from screen `DraftRoom`, which places him at the Mock card rather than in the session — so
dead-end 1 (complete-mock stickiness) or 3 (`block` short-circuit) are the likeliest, and 2 is a
real latent bug regardless. Structural root cause common to all three:

**`MockEntryPanel` has four mutually exclusive early returns (`block` → `loading` → `errorText` →
card), and three of them render zero interactive controls** (`MockEntryPanel.tsx:72-96`). The
panel's contract makes "no way forward" a reachable state from several independent inputs, and
none of them is recoverable in place.

Secondary structural cause: **a completed mock never stops being the current mock**
(`backend/database.py:10774-10783`) and there is no user-reachable way to clear it
(`MockDraftScreen.tsx:200-212` hides the only abandon control once `status !== 'active'`).

---

## 4. Approach

### 4.1 #292 — lifecycle + entry recoverability

**Backend (small, surgical).**
Give a completed mock a way to stop being "current". Two options:

- **Option A (recommended): add a dismissal, don't change the query.** Extend the abandon route
  to accept a `complete` row, and surface it in the client. `update_mock_draft`
  (`backend/database.py:10786-10805`) already sets any status, owner-scoped, so this is a client
  change plus (optionally) relaxing `mock_draft_pick_route`'s sibling guard. Preserves the
  resume-or-recap contract exactly as `lld.md` specifies it.
- **Option B (rejected): bound the complete-fallback by age in `load_current_mock_draft`.** An
  invisible time bound makes "where did my recap go" a new bug class, and it changes a documented
  contract (`lld.md` §2.3 "resume-or-recap") to fix a UI problem.

**Mobile (the real fix).**
1. In the complete state, **swap the button priority**: primary "Start a new mock", secondary
   "View recap" (`DraftRoomScreen.tsx:823-830`). The user's next intent after a finished mock is
   another mock, not the recap they just closed.
2. Give `MockEntryPanel`'s `errorText` branch a **retry control**, and add an `onError` to
   `createMock` that clears the sticky state — no reachable state may render zero controls
   (`MockEntryPanel.tsx:90-96`, `DraftRoomScreen.tsx:278-294`).
3. Clear `postRefusal` when the user changes any setup input or re-enters Mock mode
   (`DraftRoomScreen.tsx:300`), so one transient refusal cannot mute the card for the session.
4. Add a "Start another" action to the **recap** on `MockDraftScreen` so the loop closes without
   a round trip to the room. **Constraint:** must not introduce a second top-level `return`
   (see §6).

Alternatives rejected: adding a new `/api/mock-draft/reset` route (the create route already
abandons-and-inserts atomically — a second route is a second way to get it wrong);
auto-abandoning the complete row on room focus (silently destroys a recap the user may want).

### 4.2 #291 — make the affordance visible

Minimum change that answers the report:

1. **Show the action label unconditionally on the user's turn**, not only when selected —
   `DraftRoomScreen.tsx:1325` becomes `actionLabel ? … : row.valued ? …`, with the selected state
   distinguished by the existing `undraftedRowSelected` style
   (`DraftRows.tsx:147`). The row then reads "Pick" on every row while the user is on the clock,
   and stays a TierBadge row otherwise. **Tension to resolve in the PRD:** #277 deliberately put a
   TierBadge in that slot (`DraftRows.tsx:153`); we must not silently delete the tier label. Prefer
   a distinct leading/trailing affordance over evicting the badge — decide in design review against
   `docs/design/components.md`.
2. **Retitle the section on the user's turn** — "Still on the board" → e.g. "Tap a player to
   draft him" (`MockDraftScreen.tsx:386`), or add a one-line hint under `OnTheClockCard` when
   `isUserTurn`.
3. Chalkline compliance: no emoji glyphs, no new radii, ice for the action affordance
   (`docs/design/design-system.md`; ADR-004/005).

Alternatives rejected: a per-row "Draft" `Button` (heavier than the specced row, and the confirm
bar already owns the commitment step — `MockDraftScreen.tsx:437-476`); a one-time coach-mark
(persistent state for a problem a permanent label solves).

### 4.3 #290 — the engine change

This is the heavy one and the only one that touches a model whose form has failed a published
gate three times. Structure it as: **define the run → place it relative to the reach policy →
make reaching need-conditional → re-measure.**

#### 4.3.1 The tier model — call it a **run**, not a tier

**Do not reuse or extend the 8-tier ladder.** Reasons, all citable:
- The ladder's bands are far too wide for "tight groups of 4-5": `first_1` spans Elo 1580–1785 and
  `second` spans 1400–1575 (`backend/tier_config.json`; `docs/cross-client-invariants.md:36`).
  They will hold dozens of rookies, not 4-5.
- The tier keys are a **cross-client enum** sent verbatim on `/api/tiers/save`,
  `/api/tier-config`, `/api/extension/rankings` and `/api/anchor/save`
  (`docs/cross-client-invariants.md:9`, `:40`). Repurposing them as a draft-run definition either
  drifts the enum or mislabels it.
- There is established precedent for exactly this refusal: #279 declined to extend `TIER_LABEL`
  for aggregates and reused an existing formula instead, calling a parallel scale "the 'invent a
  second scale' mistake this item explicitly warns against"
  (`docs/feedback/items/279-aggregate-tier-labels/status.md:49-56`).
- `docs/cross-client-invariants.md:28` already quarantines three engine-internal lookalikes
  (`web/css`'s 4-level set, `tier_depth`, `tier_mult_*`) as explicitly **NOT** the tier enum.
  A gap-derived run is a fourth, and gets a line there.

**Definition (proposed, subject to the spike in §8).** The consensus pool is already sorted
descending by `value` with `rank` renumbered 1..n
(`draft_board_service.py:956-968`, consumed by `mock_draft_service.consensus_pool:396-412`).
Walk it once and cut a run boundary between `i` and `i+1` when the value drop is *locally
significant* — i.e. materially larger than the surrounding gaps — with a size clamp keeping runs
near the operator's 4-5. Two candidate thresholds:

- **Absolute:** cut when `value[i] − value[i+1] ≥ G`. Simple; but G behaves very differently at
  the top of the board (large gaps) and in the tail, which is exactly the flattening W2c recorded
  (`mock_draft_service.py:1170` — "a value curve that flattens in the tail").
- **Adaptive (recommended):** cut when the gap exceeds `m ×` the median gap over a local window.
  Scale-free, survives the tail, and needs one dimensionless parameter instead of one Elo-scaled
  one.

**Implementation constraint that shapes this:** `test_mock_draft.py:708`
(`test_w2_14_the_service_declares_no_second_consensus`) is an **AST test asserting zero `sorted`
/ `.sort` calls anywhere in `backend/mock_draft_service.py`** — amendment 1, "there is deliberately
no second ordering in this file" (`mock_draft_service.py:15-19`). The run scan must therefore be a
single forward walk over the already-ordered pool, preserving `_undrafted`'s order. The precedent
is right there: `_block_rank` (`:1127-1148`) already walks neighbours in that sorted run for exact
ties. A run is the same walk with a tolerance instead of equality. **This constraint is satisfiable
and should not need waiving.**

#### 4.3.2 Where the run sits relative to the reach policy

Three placements considered:

| Option | Verdict |
|---|---|
| **Replace `round_reach_cap`** | **Rejected.** The caps are the operator's verbatim product rule, pinned literally by `test_mock_draft.py:332`, and `build-w2e.md:99-104` states changing either table is a product decision requiring a fresh operator ruling. |
| **Sit above them** (run boundary is a hard wall, free reaching within a run) | Viable. |
| **Constrain the candidate set before them** | Viable, and mechanically identical to the above. |

**Recommended: express both as one tighter truncation at the existing seam.**
`cpu_pick` already truncates at `:637-638`:
```python
if reach_cap is not None:
    candidates_ranked = candidates_ranked[:max(0, int(reach_cap)) + 1]
```
The caller (`advance_cpu:936`, and the harness's mirror at `:1247`) computes
`cap = round_reach_cap(round_no) if spent < round_reach_budget(round_no) else 0`. The change is to
pass `min(round_reach_cap(round_no), run_boundary_offset)` instead — where
`run_boundary_offset` is the 0-based distance from the head of the remaining pool to the last
member of the head's run.

Why this placement:
- **It never loosens the operator's rule** — `min()` can only tighten. The W2e policy stays exactly
  as ruled, and `test_w2_21_the_policy_table_is_the_operators_rule_verbatim` is untouched.
- **It preserves the Gumbel-max identity.** The reach branch remains a geometric law truncated
  earlier, so `test_w2_04b_the_reach_branch_is_geometric_in_reach_decay`
  (`test_mock_draft.py:248`) still holds conditional on reaching.
- **It preserves budget accounting.** `reaches_spent` (`:861-887`) re-derives spend from persisted
  picks by pool position > 0 and is untouched, so the resume-identity test (`:402`) holds.
- **One seam, one place to get it wrong** — the existing `reach_cap` parameter, already
  per-pick, already documented as the caller's product cap (`:626-633`).

**Note on determinism, which looks like a risk and is not.** Truncating the candidate list changes
how many `_gumbel` draws the loop consumes (`:649`), so a given `rng_seed` will produce a
*different* draft than it does today. That does not break INV-10 or any determinism test: `:584`,
`:724`, `:402` all compare two runs of the *same* code, and `_pick_rng` stays a pure function of
`(rng_seed, pick_no)` (`:820-823`). Persisted mocks created before the change will replay
differently — acceptable, and worth one line in the PRD.

#### 4.3.3 Making reaching need-driven

**Recommended (primary): make the mixture weight need-conditional.** Today
`reaching = scale > 0 and rng.random() >= bpa_prob` (`:643`) — one unconditional Bernoulli. Make
the effective BPA probability rise as need falls, e.g.

```
bpa_effective = 1 − (1 − bpa_prob) × f(max_severity_for_this_team)
```

so a team with nothing it needs drafts ~pure best-available, and a team with a desperate hole
reaches at today's rate. This:
- directly implements the operator's sentence ("reaching should more so be to fill a position of
  need than just random");
- is a change to one scalar, not to the noise family — the geometric law and the Gumbel-max
  identity survive intact;
- consumes the same one `rng.random()` call, so it is the smallest possible perturbation of the
  stream.

**Alternative (rejected as primary): scale the reach *magnitude* by severity** (multiply `scale`
by severity). Rejected because it changes the noise family's parameterisation per pick, which
breaks `test_mock_draft.py:248`'s geometric-ratio assertion and re-opens the model-form question
W2b closed.

**Alternative (rejected): raise `mock_max_reach_slots`.** That is a parameter tweak on a term the
docstring at `:88-95` explicitly says only scales the need bonus; it cannot make reaching
*conditional*, only stronger, and it would still fire on teams with zero need.

#### 4.3.4 Re-validation plan, and the abort criterion

**Say it plainly: this does not need an operator-funded calibration campaign, but it does need one
harness run, and it has a live tripwire.**

Facts:
- The gate is **already open by operator override**, not by a pass
  (`mock_draft_service.py:276-294`, commit `6caca35`). The recorded verdict in
  `mock-calibration-2026-08d.md` is still **FAILED** — all three KS bars passed
  (p = 0.317 / 0.546 / 0.108), all three paired-mean bars failed (Δ = 1.648 / 3.605 / 2.026).
- W2e moved the support bound underneath those numbers **without re-fitting**, so
  `build-w2e.md:126-130` already records that "a re-fit and a re-gate are owed before any figure
  from 08d is quoted again." **Our change does not create that debt; it inherits it.**
- The harness is **not** opt-in. It runs inside every `pytest backend/tests` invocation, needs no
  env var, marker, network, DB, or credential, and costs ~1.5–3 minutes:
  `python3 -m pytest backend/tests/test_mock_draft.py -k "w2_16 or w2_17 or w2_19"`.
  **The compute is free. What is not free is re-publishing an artifact.**
- **The tripwire:** `test_w2_16_calibration_gate` (`test_mock_draft.py:1809-1853`) asserts
  `report["all_pass"] is False` — and *only* that. It is a one-sided tripwire. If our change makes
  the model **pass**, the suite goes **RED** and we owe a deliberate artifact re-publish. If it
  keeps failing, the test stays green and tells us nothing about regression.

**Therefore the plan's validation is a regression bar, not a pass bar:**

> **Abort criterion for this change.** Run the harness before and after. Abort (and return to the
> operator) if either: (a) any of the three paired-mean deltas grows beyond its 08d value
> (1.648 / 3.605 / 2.026), or (b) any of the three KS bars moves from pass to fail. Both
> directions are recorded in the item's `status.md` with the raw numbers regardless of outcome.

**My recommendation to the operator: run it, record it, do not re-publish an artifact unless the
verdict flips.** Re-publishing means writing `mock-calibration-2026-08e.md`, re-pointing
`mds.CALIBRATION_ARTIFACT` (`:295`), and reconciling a statistical verdict against a live
`CPU_MODEL_VALIDATED = True` — that is the operator cost, and it should be spent deliberately, not
as a side effect of a feedback fix. Q4 in §10.

#### 4.3.5 The Tate case as the acceptance test — and a fixture gap

This is the operator's falsification handle and should be the headline acceptance test. **One
blocker the build agent must know up front:**

`backend/tests/fixtures/draft/ffv3-predraft/` is a **Sleeper league + draft cassette only**. Its
`manifest.json` records `draft_order: null, start_time: null, last_picked: null, picks: []`,
league `1312140920132497408`, draft `1312140920136699904`, and its purpose is the identity
`slot_to_roster_id` trap (drives `T-M3-03` / `D5`). It contains **no player values** — so it cannot
by itself reproduce "Tate going 4th overall". The acceptance test must compose it with the pinned
consensus board the calibration harness already builds
(`rookie_universe_2026.json` + `ktc_blend_pipeline_2026-07-17.json` +
`dp_playerids_snapshot_2026-07-11.csv` + `player_pool_2026.json`, assembled at
`test_mock_draft.py:1466-1491` with the blend weight pinned rather than read from `model_config`).

Second caveat: I could **not** determine Carnell Tate's actual consensus rank or the WR value gaps
around him. `data/trade_finder.db`'s `players` table is empty (0 rows) in this worktree, and the
value fixtures carry values without names. **Establishing the real numbers is the first task of
the spike (§8)** — and it is what decides whether "Tate 4th" is the model behaving as designed
(my strong expectation, given the measurements in §1) or a genuine pricing defect.

Assertion shape, once the numbers exist — and it must be **value-based, not rank-based**, because
that is the operator's actual complaint:

1. **Primary:** over N seeds on the ffv3 order + pinned consensus board, no round-1 CPU pick
   crosses a run boundary. (Deterministic given the truncation in §4.3.2 — assert it exactly, not
   statistically.)
2. **Secondary:** `P(Carnell Tate taken at pick ≤ 4)` falls from its measured pre-change value to
   ≈ 0 (or below an agreed bar), with the pre-change value recorded in the same test's docstring
   so the fix is falsifiable in both directions.
3. **Guard:** the same seeds still produce a *varied* board — assert the round-1 outcome set has
   more than one distinct ordering, so "fixed" does not silently mean "now deterministic BPA".

---

## 5. Platforms touched and sequencing

| Item | Backend | Mobile | Web / extension | Docs |
|---|---|---|---|---|
| #290 | **yes** — engine only | no | no | config-reference, cross-client-invariants, LLD delta |
| #291 | no | **yes** | no | components/design review note |
| #292 | small (lifecycle/route) | **yes** | no | api-reference if the abandon contract widens |

**Proposed order — I accept the orchestrator's sequencing with one amendment.**

The brief proposed #291 → #292 → #290, justified by "the engine work needs a working second-mock
loop to iterate against." That justification argues for **#292 before #290**, which both orderings
satisfy — but it does not require #291 to be first. What *does* argue for touching #291 first is
scoping: its verdict ("already exists, invisible") had to be settled before anyone budgeted for an
interactivity feature. **That scoping is now done, in §1.** So:

0. **Reproduce #292 first** (cheap, ~30 min, see the diagnostic in §9). Its precise trigger is the
   one thing in this group that reading could not settle, and it gates the shape of the fix.
1. **#292** — backend lifecycle + `MockEntryPanel` / `DraftRoomScreen` recoverability. Lands first
   because it is what makes the mock loop iterable, for the operator and for the #290 build agent.
2. **#291** — mobile affordance. Touches `DraftRoomScreen.tsx` (`UndraftedRowView`) and
   `DraftRows.tsx`, which #292 also touches, so **serialize behind #292**.
3. **#290** — engine. Backend-only, so it **can run in parallel with #291** once #292 has landed:
   after that point their file sets are disjoint (backend engine vs mobile). Recommend parallel to
   recover the time #292's serialization costs.

The brief's constraint that #290 and #292 serialize on `backend/mock_draft_service.py` holds, but
note their regions are disjoint: #292 is lifecycle (`load_current_mock_draft`, abandon path,
routes) and #290 is `cpu_pick` / `advance_cpu`. If the orchestrator wants them parallel, the seam
is clean — but I would not recommend it, because #290's author needs a working second-mock loop to
iterate against, which is #292's whole point.

---

## 6. Risks

| # | Risk | Detail | Mitigation |
|---|---|---|---|
| R1 | **Calibration tripwire fires** | `test_mock_draft.py:1809-1853` asserts `all_pass is False`. A change that makes the model *pass* turns the suite RED. | Run the harness early, not at the end. If it passes, stop and escalate (Q4) — that is an artifact re-publish decision, not a bug. |
| R2 | **Green calibration proves nothing** | The gate test is one-sided; it cannot detect a distribution regression. | Use the explicit regression bar in §4.3.4 (compare the three paired-mean Δ and three KS p-values against 08d), not the test's pass/fail. |
| R3 | **AST test: no `sorted` / `.sort`** | `test_mock_draft.py:708` forbids both anywhere in `mock_draft_service.py` (amendment 1). | The run scan is a single forward walk over the already-ordered pool, modelled on `_block_rank:1127-1148`. Satisfiable — do not request a waiver. |
| R4 | **AST test: import allow-list** | `test_mock_draft.py:764` forbids `urllib/http/socket/requests/ssl` and the four platform services in the engine. | The run scan needs no new imports. If one is proposed, it gets audited. |
| R5 | **`check-mock-mode-marker.js`** | Structural AST test over both screens. `MockDraftScreen` must keep **exactly one top-level `return`**, exactly one **unconditional** `<MockRail>` before and outside the ScrollView, and six literal testID substrings (`mock-draft.empty-text`, `.error-text`, `.empty.`, `.on-the-clock`, `.confirm`, `.recap`); no rendered string may contain "never drafts". `DraftRoomScreen` must keep `const mockMode = mockOn &&`, `useFlag('draft.mock')`, exactly one `DraftModeToggle`, and a ternary whose condition text is **exactly** `mockMode`. | Highest-probability breakage for #291/#292. Adding a "Start another" action to the recap must not add an early return. **Not in CI** — only `testid-lint` runs there (`.github/workflows/ci.yml:38-42`). Run `npm run test:mock-mode-marker` in `mobile/` manually, every commit. |
| R6 | **Determinism** | Truncating candidates changes RNG consumption, so old `rng_seed`s replay differently. | Not a test break (§4.3.2) and not an INV-10 break. `_pick_rng` must stay a pure function of `(rng_seed, pick_no)` (`:820-823`). One PRD line noting pre-existing rows replay differently. |
| R7 | **Flags are ON — this ships lit** | `draft.mock`/`draft.room`/`draft.tab` are all `true` (`config/features.json:149,157,169`). There is no dark landing here. | Every change is immediately user-visible on merge. Treat the Maestro gate as load-bearing, not ceremonial. |
| R8 | **No Maestro mock flow exists** | Grep of `mobile/.maestro` finds three draft flows (`d1-draft-room-complete`, `d2-draft-room-order-not-set`, `r5-flag-off-no-entry`) and **zero** mock flows. Touching either screen is a Tier-1 change → 11 smoke flows **plus the feature's own flow** (`docs/runbook.md:93-98`). | We author the first mock flow. See §9 — and note the hermetic-seeding blocker. |
| R9 | **Hermetic mock seeding does not exist** | `seed_ui_test_db.py` never writes `mock_drafts`; `test_support.py` has no mock surface; `lakeview-complete` is blocked by `board.state === 'complete'` and `ffv3-predraft` has `draft_order: null`. | Either drive the mock through the UI in the flow, or add a seed-profile knob writing a `mock_drafts` row via `mds.dumps` — `GET /api/mock-draft` then answers from DB + process pool alone (`server.py:11683-11698`). Scope this in the PRD; it is real work. |
| R10 | **Stale docs contradict the code** | `config/features.json:145` still says `draft.mock` "stays OFF" and that create returns `cpu_model_unvalidated`; `docs/config-reference.md:565` still asserts `CPU_MODEL_VALIDATED is False`. Both are wrong since `6caca35`. | Correct both as part of this work — a future agent reading them will make a wrong call. |
| R11 | **#277's TierBadge vs #291's affordance** | Both want the row's trailing slot (`DraftRoomScreen.tsx:1325-1340`). | Do not silently evict the tier label; resolve in design review against `docs/design/components.md`. |
| R12 | **Client/server `MOCK_MIN_TEAMS` disagree** | Client 6 (`MockEntryPanel.tsx:41`), server 4 (`mock_draft_service.py:85`). | Out of scope for these three items, but note it — a 4- or 5-team league is refused by the client for a reason the server would allow. |

---

## 7. File-ownership proposal

**Claimed by G2 — exclusive:**

| File | Item | Region |
|---|---|---|
| `backend/mock_draft_service.py` | #290, #292 | #290: `cpu_pick`, `advance_cpu`, new run scan. #292: lifecycle constants only if needed. |
| `backend/tests/test_mock_draft.py` | all | Additions only; existing assertions preserved unless deliberately renamed. |
| `mobile/src/screens/MockDraftScreen.tsx` | #291, #292 | Affordance copy, recap "start another". |
| `mobile/src/components/draft/MockEntryPanel.tsx` | #292 | Error-branch retry, block precedence. |
| `mobile/src/components/draft/MockSetupSheet.tsx` | #292 | Only if the busy-stranding path (`:182`) is in scope. |
| `docs/feedback/items/290-mock-draft-engine/**` | all | This plan, PRD, HLD/LLD deltas, status, QA. |
| `mobile/.maestro/flows/rookie/<new mock flow>.yaml` | all | New file. |

**Claimed by G2 — SHARED, needs orchestrator arbitration:**

| File | Why | Collision |
|---|---|---|
| `mobile/src/screens/DraftRoomScreen.tsx` | Hosts `UndraftedRowView` (#291) **and** the Mock entry panel wiring (#292). | ⚠️ **G1 is #289 "MFL draft room ids".** The brief says G1 owns `backend/draft_board_service.py` + `backend/mfl_service.py`, but an MFL *draft room* fix plausibly reaches this screen. **Flagging now — please confirm G1 does not touch `DraftRoomScreen.tsx`.** If it does, we need a split: G1 takes the MFL branch, G2 takes `UndraftedRowView` + the mock panel, or we serialize. |
| `mobile/src/components/draft/DraftRows.tsx` | Row styles + the #277 TierBadge slot (#291). | Same G1 question. |
| `backend/server.py` | The four `/api/mock-draft` shims, `:11381-11800` only. | 20k-line shared file; region-scoped claim. |
| `backend/database.py` | `load_current_mock_draft` / `update_mock_draft`, `:10714-10805` only. | 10k-line shared file; region-scoped claim. |
| `docs/api-reference.md`, `docs/config-reference.md`, `docs/cross-client-invariants.md`, `living-memory/LLD.md` | Mandatory doc updates. | Append-only sections; low collision risk but coordinate. |

**Confirmed NOT touched by G2:** `backend/draft_board_service.py` (G1), `backend/mfl_service.py`
(G1), `mobile/src/screens/LeagueSummaryScreen.tsx` (G3).

> Note on the #290 seam: the run scan naturally *wants* to live next to `_undrafted` in
> `draft_board_service.py`. **It must not.** That file is G1's, and putting the run there would
> also make it board payload surface (a new field on a shipped contract). Keep it entirely inside
> `mock_draft_service.py`, consuming the rows `_undrafted` already returns.

---

## 8. Spike needs

**Yes — #290's tier model cannot be specced without a spike.** State this plainly to the operator.

**Spike A — the real ffv3 / 2026 consensus board (blocking; ~2-3 h).** Deliverables:
1. Assemble the pinned consensus rookie board the way `test_mock_draft.py:1466-1491` does, and
   dump the top ~30 as `(rank, name, position, value)`.
2. **Locate Carnell Tate** — establish his consensus rank and the Elo gaps to the WRs around him.
   Until this exists, "Tate 4th is unrealistic" cannot be turned into a test. (`data/trade_finder.db`
   is empty in this worktree; the value fixtures carry no names.)
3. Measure `P(Tate ≤ pick 4)` under the **current** engine on the ffv3 order. This is the
   before-number the acceptance test asserts against.
4. **Decide whether "Tate 4th" is model-form or a pricing defect.** My measurements in §1 strongly
   indicate model-form (consensus #7 reaches pick ≤4 10.9 % of the time by construction), but if
   Tate's consensus rank turns out to be ~#4 already, the operator's premise is about the
   *consensus board*, not the mock — a completely different fix, and one that would land in G1's
   files. **This is the single highest-value output of the spike.**

**Spike B — run-size distribution (blocking the tier spec; ~2 h).** On the real board from Spike A,
plot run sizes for both threshold families (absolute Elo gap, adaptive local-median multiple)
across a parameter sweep, and report which family and which parameter actually yields runs near
4-5 across the whole board rather than only at the top. **"Tight groups of 4-5" is an empirical
property of the value curve, not a design choice** — we cannot pick the threshold from a
whiteboard. Output: one recommended family + parameter, with the run-size histogram, for operator
sign-off before build.

**No spike needed** for #291 or #292 — #291's root cause is settled, and #292 needs a reproduction
(30 min, §9), not a spike.

---

## 9. Test plan seed

### 9.0 Reproduction diagnostic for #292 (do this first)

Against a real session, in the Draft Room in Mock mode, capture: `GET /api/mock-draft`'s
`status` and `reason`; the board's `state`, `kind`, `teams`, `notice.code`; and which
`mock-entry.*` testID is on screen (`mock-entry.card` / `.loading` / `.error` /
`.blocked.<reason>`). That single observation distinguishes all three dead-ends in §1 and decides
whether the fix is copy/priority (dead-end 1) or state handling (2 and 3).

### 9.1 Backend pytest — `backend/tests/test_mock_draft.py` (additions only)

**#290 — the run model**
- run boundaries are a pure forward walk (AST: still zero `sorted`/`.sort` — extend `:708`'s spirit)
- a run boundary is never crossed by a CPU pick in round 1, over N seeds — **exact, not statistical**
- `min(round_cap, run_offset)` never *loosens* the operator's cap: for every round 1..8 the
  effective cap ≤ `round_reach_cap(round)` (companion to `:265`)
- the geometric law still holds conditional on reaching, within a run (companion to `:248`)
- the round frequency budget is unchanged in semantics and still survives a resume (`:402` must
  stay green)
- `bpa_effective` is exactly `bpa_prob` at maximal need and → 1.0 at zero need
- a zero-need team drafts best-available within tolerance over M draws
- a maximal-need team's reach rate is unchanged from today

**#290 — the Tate acceptance test** (the headline)
- fixture: `ffv3-predraft` order + the pinned consensus board (see §4.3.5 for the composition and
  the fixture gap)
- assert (1) no round-1 run-boundary crossing; (2) `P(Tate ≤ pick 4)` below the agreed bar, with
  the pre-change value in the docstring; (3) the board is still varied across seeds

**#290 — calibration**
- no new assertions. Run `-k "w2_16 or w2_17 or w2_19"` before and after; record the three
  paired-mean Δ and three KS p-values in `status.md` and check them against the §4.3.4 bar.

**#292 — lifecycle**
- a completed mock can be dismissed and `GET` then returns `no_active_mock`
- create-after-complete returns a fresh **active** mock with the user on the clock
- abandon of a `complete` row is owner-scoped and idempotent
- (extends `:1330`, which already pins the DB-layer second-mock behaviour)

### 9.2 Mobile static gates (manual — not in CI)

- `cd mobile && npm run test:mock-mode-marker` — **every commit** touching either screen (R5)
- `bash mobile/scripts/testid-lint.sh` — CI runs this (`.github/workflows/ci.yml:42`); any new
  testID must be a literal `testID=` in `mobile/src` or an allowlist entry
- `npx tsc --noEmit`

### 9.3 Maestro

**New flow** (first mock flow in the repo), under `mobile/.maestro/flows/rookie/`, tagged
`[rookie, draft-room, mock]`:

1. Draft Room → `DraftModeToggle` → Mock → `mock-entry.card` visible with `mock-entry.start`
2. `mock-setup-sheet` → `mock-setup.rounds.*`, `mock-setup.type.linear` → `mock-setup.start`
3. `MockDraftScreen`: `mock-draft.rail` visible, `mock-draft.on-the-clock` visible, **the new
   affordance visible on an unselected row** (#291's acceptance)
4. tap `mock-draft.undrafted-row.<id>` → `mock-draft.confirm` → `mock-draft.confirm.draft`
5. drive to completion → `mock-draft.recap`
6. back to the room → **start a second mock and reach `mock-draft.on-the-clock` again** (#292's
   acceptance)

Constraints (`mobile/scripts/testid-lint.sh`): `id:` selectors only, **no `- sleep`**, no
coordinate taps or `point:`. Run with `--flags` pinning `draft.mock`/`draft.room` on
(`mobile/scripts/sim-run.sh:5`).

**Blocker to scope in the PRD (R9):** no seed profile puts a user in a mock. Either the flow
creates one live (slow, but the create is hermetic under `FTF_TEST_MODE` against the ffv3
cassette), or we add a `mock_drafts` seed knob to `seed_ui_test_db.py`.

### 9.4 Pre-ship simulator gate

Tier **1** (mobile screen + state change) per `docs/runbook.md:93-98`: **full 11-flow smoke suite +
the new mock flow**, logged in `living-memory/TEST_LEDGER.md` with `qa/sim-runs/last-sim-run.json`
written. `githooks/pre-push` enforces it locally.

---

## 10. Open questions for the operator

Each of these has two readings that lead to materially different builds.

**Q1 — Tier definition: absolute or adaptive?**
Cut a run at a fixed Elo gap (`value[i] − value[i+1] ≥ G`), or at a *locally* significant gap
(`≥ m ×` the local median)? The absolute form is simpler and easier to explain; the adaptive form
survives the value curve flattening in the tail, which is a documented property of this board
(`mock_draft_service.py:1170`). I recommend adaptive. **Related:** is "tight groups of 4-5" a hard
size clamp (always 4-5, gaps only decide *where* inside that window) or a target the gap rule
should naturally produce? These build differently.

**Q2 — Is a run boundary a hard wall in every round, or only rounds 1-2?**
Rounds 3+ currently allow 15-slot reaches (`MOCK_REACH_CAP_LATE = 15`). If a run averages 4-5
players, a hard wall in round 3+ collapses the late rounds to near-BPA and will make mocks feel
chalky and lifeless. Options: hard wall everywhere; hard wall in rounds 1-2 and a *soft* penalty
later; or allow crossing exactly one boundary in rounds 3+.

**Q3 — Should a bot with no positional need reach at all?**
"Reaching should more so be to fill a position of need" reads two ways: (a) *only* need drives
reaching — a satisfied roster goes pure BPA; or (b) need *dominates* but idiosyncrasy survives.
(a) is a big behavioural change: severity is 0 for most (team, position) pairs in August
(`VIABLE_ELO_FLOOR = 1280`, `:194`), so under (a) most bots would draft strict best-available and
the board would get much more predictable. (b) preserves texture. I recommend (b) with a strong
tilt. **Which do you want?**

**Q4 — Re-gate: run-and-record, or re-publish?**
The harness is free to run (~1.5–3 min, already inside every `pytest backend/tests`). Publishing a
`mock-calibration-2026-08e.md` and re-pointing `mds.CALIBRATION_ARTIFACT` (`:295`) is not free —
and per `build-w2e.md:126-130` a re-fit + re-publish is **already owed** from W2e, independent of
this work. Do you want (a) run-and-record the numbers in this item's `status.md` against the §4.3.4
regression bar [my recommendation], or (b) pay down the W2e debt now with a full re-fit + new
artifact? Note the tripwire: if our change makes the model *pass*, the suite goes red and (b)
becomes mandatory.

**Q5 — #292: what did you actually hit?**
I can prove three independent dead-ends (§1) but not which one you saw. Most likely: after a mock
completes, the room's Mock card's **primary** button is "View recap" and the only way to a new mock
is the recessive ghost "Run it back" (`DraftRoomScreen.tsx:823-830`) — so every obvious tap returns
you to the same recap. **Does that match?** If instead you saw a muted card with a greyed-out
button, or a card with no buttons at all, say which — it changes the fix. **Related:** should a
completed mock ever stop being "the current mock", or is the recap meant to persist until you
start another?

**Q6 — #291: is a visible affordance enough?**
The pick path works today (verified end-to-end). What is missing is that the row looks identical
to the read-only Draft Room row until after you tap it (`DraftRoomScreen.tsx:1325`). Making it
visibly tappable is a small mobile change. But "at the very least" suggests you may want more —
**do you also want to draft for other teams?** That is explicitly out of v1 and the engine has no
such call (`MockSetupSheet.tsx:110-120`, `DraftRoomScreen.tsx:368-370`); it would be a separate,
much larger item.

**Q7 — Rigor level.**
No express declaration was made, so this plan assumes **full gates**. Note that #290 touches
engine behaviour behind a live feature flag and #292 may touch a route contract, which is on the
bright-line list ("schema, API contracts, feature-flag surfaces, or analytics events is not a
quick fix"). If you intend express here, please say so explicitly and confirm.

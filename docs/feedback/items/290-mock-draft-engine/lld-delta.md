# LLD delta — G2: mock draft engine, lifecycle, interactivity (#290 / #291 / #292 / D-16)

> **Delta against [`living-memory/LLD.md`](../../../../living-memory/LLD.md) and the
> shipped code — exact interfaces only.** A build agent must be able to implement
> every item here without a judgment call. Where a judgment was needed, it has
> been made and the reasoning lives in [`hld-delta.md` §10](./hld-delta.md#10-decisions-taken-alternatives-rejected).
>
> All line references verified against `origin/main` @ `7cea1fa` in
> `.claude/worktrees/fb-289-294`. Corrections to the plan's citations are marked ⚠.

---

## Table of Contents

- [1. New module constants](#1-new-module-constants)
- [2. Run detection](#2-run-detection)
- [3. Reach-cap composition](#3-reach-cap-composition)
- [4. Need-conditional mixture weight](#4-need-conditional-mixture-weight)
- [5. D-16 — owner identity sourcing](#5-d-16--owner-identity-sourcing)
- [6. Client — #291 affordance](#6-client--291-affordance)
- [7. Client — #292 lifecycle](#7-client--292-lifecycle)
- [8. Route and response contracts](#8-route-and-response-contracts)
- [9. Test-helper corrections](#9-test-helper-corrections)
- [10. Citation corrections to `plan.md`](#10-citation-corrections-to-planmd)

---

## 1. New module constants

**File:** `backend/mock_draft_service.py`. Place immediately **above**
`def cpu_pick` (`:588`), after `_decay_to_scale`, inside the
"The scoring function" section.

```python
#: How many times the LOCAL median gap a value drop must be before it counts as
#: a run boundary. Dimensionless on purpose (D-9): an absolute Elo threshold
#: behaves differently at the head of the board than in the tail, which is the
#: flattening this module already records at :231.
#:
#: 2.5 yields a MEDIAN RUN OF 5 players on BOTH scoring formats — the operator's
#: "tight groups of 4-5" as an emergent property of the value curve rather than
#: an imposed clamp (D-9). It governs the PARTITION only.
#:
#: **It does NOT on its own keep pick 1.01 free, and must never be described as
#: if it did.** Un-floored, `run_offset(pool[:24])` is 3 on 1qb_ppr but **0 on
#: sf_tep**, which forces 1.01 in every superflex / TE-premium league. The
#: threshold that keeps 1.01 free is :data:`MOCK_RUN_MIN_OFFSET`, below.
#:
#: **Safe band: 2.2 <= m <= 2.6.** Inside it, P(consensus #7 reaching pick <= 4)
#: is 0.0000 on both formats and the median run stays 4.0-5.0. It leaks at 2.8
#: (0.0173 on sf_tep) and breaks R-11's 0.02 bar at 3.0 (0.0507 on 1qb_ppr).
#: 2.5 sits mid-plateau, not on an edge: with the floor in place, every m in
#: [2.2, 2.6] behaves within 0.638 <-> 0.455 of P(#1 at 1.01).
#: Per-format measurements: docs/feedback/items/290-mock-draft-engine/prd.md §4.
MOCK_RUN_GAP_MULTIPLE = 2.5

#: Width, in GAPS, of the window the median is taken over. Odd so the window is
#: symmetric about the gap under test where it can be.
MOCK_RUN_MEDIAN_WINDOW = 9

#: The run rule may never truncate the candidate set below this many slots.
#:
#: **Why a floor exists.** A run of size 1 makes `run_offset` 0, which makes
#: `reach_cap` 0, which makes the pick DETERMINISTIC. That is what happens on
#: sf_tep at every m the partition otherwise wants, and it is the collapse D-6
#: and R-12 exist to prevent. The floor is the only thing standing between a
#: genuine value cliff and a forced 1.01.
#:
#: **This is NOT the size clamp D-9 forbids.** D-9 rejects clamping runs DOWN to
#: 4-5, because that manufactures boundaries where the values state none. A floor
#: only ever SUPPRESSES a boundary's effect on the cap; it can never create one,
#: and it leaves the partition (and therefore R-2's median-run figure) untouched.
#: It states a product rule — "a bot may always consider at least MIN+1 available
#: players, however large the gap above them" — not a claim about the values.
#:
#: **It can never loosen the operator's W2e cap:** the outer
#: `min(round_reach_cap(r), ...)` still binds, so effective_cap <= round cap
#: always (R-5, T-290-06).
#:
#: **Boundary condition, pinned by T-290-15: MIN must be < round_reach_cap(1) = 3.**
#: At MIN = 3 the round-1 composition is `min(3, max(off, 3)) == 3` for every
#: board, every figure reverts to the shipped engine exactly, and the feature is
#: silently disabled in the round it matters most.
#:
#: 1 is the MINIMUM intervention that makes a forced pick structurally impossible.
#: Measured at m=2.5 (1qb_ppr / sf_tep): P(#1 at 1.01) 0.455 / 0.638,
#: P(#1 falls past 3) 0.089 / 0.042, P(Tate falls past 4) 0.073 / 0.073,
#: P(#7 reaches pick <= 4) 0.0000 / 0.0000. Operator ruling O-6 may set this to
#: 2 instead (more variety, less tier discipline) — see prd.md §4.
MOCK_RUN_MIN_OFFSET = 1

#: Rounds 3+ may cross this many run boundaries (D-6's "softer penalty in
#: rounds 3+"). Rounds 1-2 cross none — a hard wall. Expressed in the same
#: units as the thing it softens (candidate-set width), so `cpu_pick`'s scoring
#: function stays byte-identical and the Gumbel-max identity survives.
MOCK_RUN_CROSS_ALLOWANCE_LATE = 1

#: The share of today's reach rate a bot with ZERO positional need keeps (D-5:
#: "need DOMINATES reaching, but idiosyncrasy survives"). At 0.25 and the fitted
#: `mock_bpa_prob = 0.10`, a satisfied roster reaches 22.5% of the time against
#: a desperate roster's unchanged 90%. Zero here would make most August bots
#: pure BPA and the board chalky, which D-5 explicitly rejects.
#:
#: The floor is only meaningful because the pressure it scales is DENOMINATOR-
#: WEIGHTED (see :func:`need_pressure`). Under a naive `max()` over positions,
#: TE's (S,B) = (1,0) means any roster without a 1280+ TE scores 1.0 and this
#: constant is never reached at all.
MOCK_IDIOSYNCRASY_FLOOR = 0.25
```

**New import:** `import statistics` beside the existing `import math` at the top
of the module. `statistics` is stdlib and performs no I/O, so
`test_w2_13_the_engine_imports_nothing_that_can_reach_a_platform`
(`test_mock_draft.py:764`, allow-list AST test) stays green — verified.

**None of these four become `model_config` keys.** Same reasoning the module
already records for the W2e tables (`:104-113`): they are support bounds on the
model, and a bound an operator can retune from the DB silently invalidates the
calibration verdict. Documented in `docs/config-reference.md` beside the W2e
policy, not in the `_DEFAULT_CFG` table.

---

## 2. Run detection

### 2.1 Signature

```python
def run_offset(candidates_ranked: Sequence[Mapping[str, Any]],
               *,
               allow_cross: int = 0,
               multiple: float = MOCK_RUN_GAP_MULTIPLE,
               window: int = MOCK_RUN_MEDIAN_WINDOW) -> int:
    """The 0-based distance from the head of ``candidates_ranked`` to the last
    row a CPU may consider without passing more than ``allow_cross`` run
    boundaries.

    Pure. No RNG, no I/O, no ordering — a single forward walk over the list
    ``_undrafted`` already produced, modelled on :func:`_block_rank` (:1127),
    which is why amendment 1's no-``sorted`` rule needs no waiver here.

    Returns a value in ``[0, len(candidates_ranked) - 1]``, suitable to pass
    straight into ``min()`` against :func:`round_reach_cap`.
    """
```

### 2.2 Algorithm — exact

**Input.** `candidates_ranked` is the **windowed head of the remaining pool** —
the same `available[:candidate_window(max_reach)]` slice `cpu_pick` scores over
(length ≤ `MOCK_CANDIDATE_WINDOW` = 24). It is already value-descending; rows
carry `value: float | None` and `valued: bool` from
`draft_board_service._undrafted`. The build agent **must** hoist that slice into
a local and pass the *same object* to both `run_offset` and `cpu_pick` — see §3.

1. `n = len(candidates_ranked)`. **If `n <= 1`: return `0`.**
2. Build two parallel lists of length `n - 1`. For each `i` in `0 .. n-2`, with
   `a = candidates_ranked[i]["value"]` and `b = candidates_ranked[i+1]["value"]`:

   | Case | `gaps[i]` | `frontier[i]` | Meaning |
   |---|---|---|---|
   | `a is None` | `None` | `False` | inside the unvalued block — the consensus holds no opinion, so **never** a boundary |
   | `a is not None and b is None` | `None` | `True` | the valued → unvalued frontier — **always** a boundary |
   | both numeric | `max(0.0, float(a) - float(b))` | `False` | an ordinary gap |

   The `max(0.0, …)` clamp is defensive: the pool is value-descending, so a
   negative gap is impossible; clamping keeps a future reordering from producing
   a negative median.
3. `crossed = 0`
4. For each `i, g` in `enumerate(gaps)`:
   - **If `g is None`:** `boundary = frontier[i]`.
   - **Else** compute the local median:
     ```python
     lo = max(0, i - window // 2)
     hi = min(len(gaps), lo + window)
     lo = max(0, hi - window)              # re-clip so the window keeps its
                                           # full width near the list's end
     win = [x for x in gaps[lo:hi] if x is not None]
     med = statistics.median(win) if win else 0.0
     boundary = med > 0.0 and g >= float(multiple) * med
     ```
   - **If `boundary`:** if `crossed >= int(allow_cross)`, **return `i`**;
     otherwise `crossed += 1`.
5. Return `n - 1` (no boundary reached inside the window).

### 2.3 Boundary conditions and tie handling — stated, not implied

| Condition | Behaviour | Why |
|---|---|---|
| Empty list | `return 0` | `cpu_pick` already raises `PlayerUnavailable` on an empty candidate list; `0` is the safe value if it is ever called first. |
| Single candidate | `return 0` | `reach_cap=0` truncates to `[:1]` — the only possible pick. |
| `i = 0` (list start) | `lo = 0`, `hi = min(len(gaps), 9)` | The window is one-sided at the head. Deliberate: no synthetic padding, so the function is a pure read of the data present. |
| `i = len(gaps) - 1` (list end) | `lo = max(0, len(gaps) - 9)` | The re-clip keeps the full width where the list allows. |
| Exact ties (`gap == 0`) | never a boundary | `g >= multiple * med` with `g == 0` needs `med <= 0`, which the `med > 0.0` guard already excludes. A consensus-tied block — the thing `_block_rank` averages — therefore always sits **inside** a run, which is the right reading: a tie carries no opinion to wall off. |
| All gaps zero in the window (`med == 0`) | no boundary anywhere in that window | Same reason. Prevents a flat block from being cut into singletons by float noise. |
| Whole head unvalued (`a is None` throughout) | returns `n - 1` | No opinion ⇒ no wall. The round cap alone governs, exactly as today. **Do not** collapse this to BPA: `reach_report`'s own docstring (`:1181-1191`) argues that an unvalued rookie "carries no opinion to reach past". |
| Head valued, tail unvalued | boundary at the frontier | A valued player is never passed over for an unvalued one under the wall. |

### 2.4 Cost

`O(n · window)` with `n ≤ 24` and `window = 9` — at most ~207 comparisons plus 23
9-element medians per CPU pick. Against the existing per-pick `O(24)` Gumbel
draws this is noise. **No caching, no memoisation.** The pool changes every pick,
and a cache keyed on the head would be a correctness hazard for a saving that
does not exist (`docs/coding-guidelines.md` §2).

---

## 3. Reach-cap composition

### 3.1 `advance_cpu` — `backend/mock_draft_service.py:890-945`

Replace the two statements at `:936-941`:

```python
        # BEFORE
        cap = round_reach_cap(round_no) if spent < round_reach_budget(round_no) else 0
        player_id = cpu_pick(available[:window], persona.get("outlook"),
                             _severities(ctx, state, str(owner)),
                             _pick_rng(state, slot["pick_no"]),
                             max_reach=max_reach, bpa_prob=bpa_prob,
                             reach_decay=reach_decay, reach_cap=cap)
```

```python
        # AFTER
        cap = round_reach_cap(round_no) if spent < round_reach_budget(round_no) else 0
        head = available[:window]
        if cap > 0:
            # The run can only TIGHTEN the operator's W2e cap, never loosen it.
            # `cap == 0` is the spent-budget case and already means strict
            # best-available, so the run rule is skipped rather than min()'d —
            # that keeps "strict best available" the operator's words verbatim.
            cap = min(cap, max(run_offset(
                head,
                allow_cross=0 if round_no <= 2 else MOCK_RUN_CROSS_ALLOWANCE_LATE),
                MOCK_RUN_MIN_OFFSET))
        player_id = cpu_pick(head, persona.get("outlook"),
                             _severities(ctx, state, str(owner)),
                             _pick_rng(state, slot["pick_no"]),
                             max_reach=max_reach, bpa_prob=bpa_prob,
                             reach_decay=reach_decay, reach_cap=cap)
```

`round_no` is already an `int` at this point (`:930`). The reach-accounting line
that follows (`if str(available[0]["player_id"]) != str(player_id): spent += 1`,
`:942-943`) is **unchanged** — the definition of a reach does not move.

### 3.2 `simulate_reaches` — `backend/mock_draft_service.py:1247-1252`

**Mandatory, and it is the easiest thing in this delta to forget.** The
calibration harness drives the shipped `cpu_pick` so that "the simulator and the
product cannot diverge on the policy" (`:1226-1229`). Apply the identical
composition:

```python
        cap = round_reach_cap(round_no) if spent < round_reach_budget(round_no) else 0
        if cap > 0:
            cap = min(cap, max(run_offset(
                head,
                allow_cross=0 if round_no <= 2 else MOCK_RUN_CROSS_ALLOWANCE_LATE),
                MOCK_RUN_MIN_OFFSET))
        chosen = cpu_pick(head, personas.get(owner, DEFAULT_OUTLOOK), …)
```

`head` is already a local here (`:1245`). Nothing else in the function changes;
`_block_rank(available, position)` at `:1256` still reads the **full** remaining
pool, not `head`, exactly as today.

### 3.3 Composition invariant

For every round `r` and every candidate head `h`:

```
effective_cap(r, h) <= round_reach_cap(r)                       # min() only tightens
effective_cap(r, h) >= min(round_reach_cap(r), MOCK_RUN_MIN_OFFSET)
spent >= round_reach_budget(r)  =>  effective_cap == 0          # floor is skipped
MOCK_RUN_MIN_OFFSET < round_reach_cap(1)                        # else round 1 is a no-op
```

**The floor sits INSIDE the `min()`, never outside it.** `max(run_offset, MIN)`
raises the run's contribution; the outer `min(round_reach_cap(r), …)` still binds,
so the operator's W2e cap is never loosened. Writing it the other way round —
`max(min(cap, run_offset), MIN)` — would let the floor override a spent budget and
break "strict best available". The `if cap > 0` guard already excludes the
spent-budget case, so the floor cannot resurrect a reach the budget forbade.

Pinned by T-290-04, T-290-05, T-290-06, T-290-14 and T-290-15
([`prd.md` §7](./prd.md#7-test-plan)).

---

## 4. Need-conditional mixture weight

### 4.1 New function

Place immediately above `cpu_pick`.

```python
def need_pressure(severities: Mapping[str, float],
                  targets: Mapping[str, tuple[int, int]]) -> float:
    """How much of this team's STARTING+BENCH need is unfilled, in [0, 1].

    The denominator-weighted share of unmet slots:

        sum_p severity[p] * (S_p + B_p)  /  sum_p (S_p + B_p)

    **Why not ``max(severities.values())``.** ``slot_targets`` gives TE
    ``(S, B) = (1, 0)`` on a standard lineup, so a team with no 1280+ TE scores
    ``severity["TE"] == 1.0`` and ``max`` returns 1.0 — which makes
    :func:`effective_bpa_prob` return ``bpa_prob``, i.e. TODAY'S BEHAVIOUR, for
    the large majority of real rosters. Measured on a roster full at QB/RB/WR
    with no viable TE: ``max`` = 1.000 (P(reach) 0.900, unchanged), ``mean`` =
    0.250, denominator-weighted = **0.111** (P(reach) 0.300).

    **Why not ``mean``.** A team missing its whole WR corps and a team missing
    one TE both score 0.25 under ``mean``. Denominator weighting scores them
    0.44 and 0.11, which is the honest ordering.
    """
    den = sum(sum(targets.get(p, (0, 0))) for p in _POSITIONS)
    if den <= 0:
        return 0.0
    num = sum(float(severities.get(p, 0.0)) * sum(targets.get(p, (0, 0)))
              for p in _POSITIONS)
    return max(0.0, min(1.0, num / den))


def effective_bpa_prob(bpa_prob: float,
                       needs_for_team: Mapping[str, float],
                       pressure: float | None = None) -> float:
    """P(this pick is the strict board pick), tilted by the team's worst hole.

    ``bpa_prob`` is the FITTED mixture weight and stays the value at MAXIMAL
    need: a team with a desperate hole reaches exactly as often as the fit says.
    As need falls the reach branch is damped toward — but never to —
    best-available, which is D-5's ruling ("need DOMINATES reaching, but
    idiosyncrasy survives"):

        tilt          = floor + (1 - floor) * max_severity
        bpa_effective = 1 - (1 - bpa_prob) * tilt

    max_severity == 1 -> bpa_effective == bpa_prob      (today's behaviour)
    max_severity == 0 -> bpa_effective == 1 - (1 - bpa_prob) * floor

    Pure; consumes no RNG. It changes the mixture WEIGHT and nothing about the
    noise FAMILY, so the Gumbel-max identity and the geometric reach law hold
    unchanged conditional on reaching (T-W2-04b).
    """
    if pressure is None:
        # Callers that hold no lineup template (the existing unit tests) fall
        # back to the worst single hole. Production callers ALWAYS pass
        # `pressure` from `need_pressure`; see the note below.
        values = [float(v) for v in (needs_for_team or {}).values()]
        pressure = max(values) if values else 0.0
    sev = max(0.0, min(1.0, float(pressure)))
    tilt = MOCK_IDIOSYNCRASY_FLOOR + (1.0 - MOCK_IDIOSYNCRASY_FLOOR) * sev
    return 1.0 - (1.0 - float(bpa_prob)) * tilt
```

**`pressure` is optional in the signature and mandatory in production.** The
default exists so the shipped single-position unit tests keep working unchanged
(on a uniform board `max` and the weighted share coincide). Both engine call
sites — `advance_cpu` and `simulate_reaches` — **must** pass it, and T-290-16
asserts they do by AST.

**Per-position severity is unchanged and still drives DIRECTION.** `need_pressure`
aggregates only for the mixture weight (how *often* a bot reaches). The
`bonus = weight × severity[pos] × max_reach` term at `:648`, which decides *what*
it reaches for, keeps reading the raw per-position severity and is not touched —
measured at a **2.77× lift** over the window base rate on the shipped engine
([`prd.md` §4.6](./prd.md#46-what-d-5-does-and-does-not-change)).

### 4.2 `cpu_pick` — the only change inside it

`cpu_pick` gains one keyword-only parameter,
`need_pressure_value: float | None = None`, threaded straight through.

`backend/mock_draft_service.py:641-643`:

```python
     weight = need_weight(persona_outlook)
     scale = _decay_to_scale(reach_decay)
+    bpa_eff = effective_bpa_prob(bpa_prob, needs_for_team, need_pressure_value)
     # ONE Bernoulli per pick, drawn first so the branch (and therefore the
     # whole stream) is a pure function of the seed.
-    reaching = scale > 0.0 and rng.random() >= float(bpa_prob)
+    reaching = scale > 0.0 and rng.random() >= float(bpa_eff)
```

The scoring loop (`:646-651`) is **byte-identical**. `bpa_prob` keeps its name,
its default and its meaning in the signature; the docstring gains one paragraph
naming `effective_bpa_prob` and stating that `bpa_prob` is now the value at
maximal need.

### 4.3 Caller wiring

Both engine call sites hoist `slot_targets` once and pass the pressure per pick:

```python
# advance_cpu, before the loop (it is per-mock, not per-pick):
targets = slot_targets(state["settings"].get("lineup_slots") or ctx.lineup_slots)
# ...inside the loop, beside the existing _severities call:
sev = _severities(ctx, state, str(owner))
player_id = cpu_pick(head, persona.get("outlook"), sev, _pick_rng(...),
                     ..., need_pressure_value=need_pressure(sev, targets))
```

`simulate_reaches` already has `targets` as a parameter (`:1234`), so it passes
`need_pressure(needs, targets)` with no new plumbing. **Both, or neither** — the
same rule as the run rule (R-6).

### 4.4 RNG-stream invariant

`effective_bpa_prob` consumes no RNG and is evaluated **before** the single
`rng.random()` call, so the Bernoulli stays the first draw of the pick and
`_pick_rng` (`:820-823`) stays a pure function of `(rng_seed, pick_no)`. INV-10
holds. What does change is the *outcome* for a given seed — pre-existing
persisted mocks replay differently. Accepted; see
[`hld-delta.md` §11](./hld-delta.md#11-properties-preserved-no-regression-contract).

---

## 5. D-16 — owner identity sourcing

### 5.1 The two sites

⚠ The plan and G1's PRD both name a single site, at `:11437` and `:11438`
respectively. **There are two, and the line is `:11437`:**

| File:line | Function | Path |
|---|---|---|
| `backend/server.py:11437` | `_mock_league_context` | **create** |
| `backend/server.py:11474` | `_mock_context_from_row` | **every GET and every /pick** |

Both read `usernames = {str(m.user_id): m.username for m in members}` off
`sess["league"].members`. Fixing only `:11437` would leave every *resumed* mock
still rendering ids — which is the common case, since a mock is read far more
often than it is created.

### 5.2 Required behaviour

Introduce one private helper in `backend/server.py`, inside G2's owned region
(`~:11380-11530`), and call it from both sites:

```python
def _mock_usernames(league_id: str, members) -> dict[str, str]:
    """user_id -> display name for a mock's order rows.

    Ladder, first non-empty wins, applied per member:
        league_members.username -> league_members.display_name
        -> the session member's own `username`
        -> "Team <fid>" for a synthetic MFL id (`mfl:<league>.f<fid>`)

    Mirrors `_sync_mfl_owned_picks` (server.py:9201-9207) and the ladder G1 is
    establishing in `_mfl_board_binding`, so the Draft Room and the Mock Draft
    cannot disagree about a franchise's name on adjacent screens (D-16).
    ONE `load_league_members` call; never per member.
    """
```

**Exact contract:**

| Input | Output |
|---|---|
| `league_members` row with non-empty `username` | that string |
| row with empty `username`, non-empty `display_name` | `display_name` |
| no `league_members` row, session member has a non-empty `username` | the session value (today's behaviour — the Sleeper path is unaffected) |
| neither, and the id matches `^mfl:.*\.f(?P<fid>\w+)$` | `f"Team {fid}"` (the fid **as it appears in the id**, zero-padded) |
| neither, and the id is not a synthetic MFL id | the key is **omitted** from the map |

An omitted key makes `state_payload` emit `owner_username: None`
(`mock_draft_service.py:1013`: `ctx.usernames.get(str(owner)) if owner else None`),
which the client renders through its existing fallback. That is deliberate: an
absent name is honest, an empty string is not.

**Never** emit a string containing `"mfl:"`. Pinned by T-290-13.

### 5.3 The id-space hazard, restated for this lane

G1's R-7 / T-289-06 finding applies here and the delta must not create an
exposure. `picks[].player_id` in the **board** payload can hold a raw MFL id when
the crosswalk missed, and MFL and Sleeper ids share a numeric range — so a
`players` lookup keyed on a raw MFL id can return **a different, wrong player**.

The mock is currently safe by construction: `ctx.player_rows` is
`dbs.database_players(sorted(rookie_ids))` where `rookie_ids` comes from
`_rookie_player_ids(season)` — **our** id space, never MFL's
(`backend/server.py:11431-11433`, `:11477-11479`). **The rule for this change:
nothing in D-16 may add an id to any player lookup list.** D-16 is the *owner*
half only. `state_payload`'s player half (`:1004-1005`, `mock_draft_service.py`)
is untouched.

### 5.4 Not changed

- `mock_draft_service.py:1013-1015` — the resolution expression stays exactly as
  written. Only the map handed to it improves.
- `MockDraftScreen.tsx:284` — `slot?.owner_username ?? String(onClock.roster_id)`
  stays as the honest last resort. ⚠ The plan lists this line as needing a fix;
  it does not. It is a fallback that will simply stop firing, and keeping it is
  the same call G1 made for `DraftRoomScreen.tsx:1140`.
- `order[].original_username` (`:1015`) — for a mock, `original_user_id` **is**
  `owner`, so it improves for free with no separate change.

---

## 6. Client — #291 affordance

### 6.1 `MockDraftScreen.tsx:428` — gate the label on the turn

```diff
-                    actionLabel="Pick"
+                    actionLabel={isUserTurn ? 'Pick' : undefined}
```

`isUserTurn` is already in scope (`:141`). Today the prop is passed
unconditionally and only the `selected` gate hides it; after this change the
label's presence *is* the turn, which is what makes §6.2 safe for the CPU-turn
render.

### 6.2 `DraftRoomScreen.tsx:1325-1341` — `UndraftedRowView` trailing slot

```diff
-      {actionLabel && selected ? (
+      {actionLabel ? (
         <Text style={draftRow.rowAction}>{actionLabel}</Text>
       ) : row.valued ? (
```

and, in the meta line at `:1318-1323`, append the tier label when the action
label has taken the trailing slot, so **#277's tier information is relocated,
never deleted** (D-8′):

```diff
         <Text style={draftRow.playerMeta} numberOfLines={1}>
           <Text style={{ color: positionOf(row.position) }}>
             {row.position || '—'}
           </Text>
           {row.team ? ` · ${row.team}` : ''}
+          {actionLabel && row.valued
+            ? ` · ${TIER_LABEL[tierForElo(row.value as number,
+                                          row.position as Position,
+                                          rowFormat ?? '1qb_ppr')]}`
+            : ''}
         </Text>
```

`tierForElo`, `Position` and `rowFormat` are already in scope in this component
(`:1310`, `:1332-1336`). `TIER_LABEL` comes from `mobile/src/utils/tierBands.ts`
— **verify the export name before writing the import**; if it is not exported
under that name, use the same map `TierBadge` reads rather than introducing a
second one.

**Selected-state distinction is unaffected:** the row already carries
`draftRow.undraftedRowSelected` when `selected` (`:1383`), which is what now
distinguishes "selected" from "selectable". No new style token, no new radius,
no glyph, ice only — Chalkline-compliant by construction.

### 6.3 `MockDraftScreen.tsx:386` — section header

```diff
-              <TickLabel>Still on the board</TickLabel>
+              <TickLabel>{isUserTurn ? 'Tap to draft' : 'Still on the board'}</TickLabel>
```

This string is the Maestro assertion for #291 (§ [`prd.md` §7.3](./prd.md#73-maestro)),
because Maestro cannot assert on a style and *can* assert on text.

### 6.4 `OnTheClockCard` — `MockDraftScreen.tsx:530-540`

When `isUser`, render one additional line under the existing "You're on the
clock" heading: **"Tap a rookie below, then confirm."** Inside the existing
`View testID="mock-draft.on-the-clock"`; no new testID.

### 6.5 Structural constraints this must not break

`mobile/tests/check-mock-mode-marker.js` (run: `cd mobile && npm run test:mock-mode-marker`;
**not in CI** — only `maestro-testid-lint` is) asserts, among others:

- `MockDraftScreen` has **exactly one** top-level `return` and **exactly one**
  `MockRail`, unconditional and before/outside the `ScrollView`;
- six literal testID substrings survive: `mock-draft.empty-text`,
  `mock-draft.error-text`, `mock-draft.empty.`, `mock-draft.on-the-clock`,
  `mock-draft.confirm`, `mock-draft.recap`;
- no rendered string in `MockDraftScreen` contains `"never drafts"`;
- `DraftRoomScreen` keeps `const mockMode = mockOn &&`, `useFlag('draft.mock')`,
  exactly one `DraftModeToggle`, and a ternary whose condition text is **exactly**
  `mockMode`.

Nothing in §6 or §7 adds a return, moves the rail, or changes the toggle count.
Run it on **every** commit that touches either screen.

---

## 7. Client — #292 lifecycle

### 7.1 `MockEntryPanel.tsx` — a retry control in the error branch

Add one optional prop beside `primary` / `secondary` (`:66-68`):

```ts
  /** Rendered inside the errorText branch. No reachable state of this panel
   *  may render zero controls (#292 dead-end 2). */
  retry?: { label: string; onPress: () => void; testID: string };
```

and in the `errorText` branch (`:90-96`):

```diff
   if (errorText) {
     return (
       <View testID="mock-entry.error" style={[styles.card, styles.cardMuted]}>
         <Text style={styles.error}>{errorText}</Text>
+        {retry ? (
+          <View style={styles.btnRow}>
+            <View style={styles.btnCell}>
+              <Button testID={retry.testID} label={retry.label}
+                      variant="primary" onPress={retry.onPress} />
+            </View>
+          </View>
+        ) : null}
       </View>
     );
   }
```

**New testID: `mock-entry.retry`.** It is a literal `testID={retry.testID}` fed a
literal string from `DraftRoomScreen`, so `mobile/scripts/testid-lint.sh` resolves
it via its `testID=[\"'{]*.${base}` branch **only if** a flow references it. No
flow does (§ [`prd.md` §7.3](./prd.md#73-maestro)), so there is no lint exposure —
but if a later flow adds it, the constructing site is `DraftRoomScreen.tsx`, not
`MockEntryPanel.tsx`, and it will need an allow-list entry. Stated so nobody
rediscovers it.

The `block` branch (`:72-80`) keeps its disabled CTA and is **not** given a
control: a block is a true refusal with an honest reason, and an enabled button
there would fail on tap. The dead-end it causes is fixed by clearing
`postRefusal` (§7.3), not by arming the blocked card.

### 7.2 `DraftRoomScreen.tsx:823-830` — swap the complete-state priority

```diff
   if (activeMock?.status === 'complete') {
     return {
       headline: 'Mock complete',
       body: `${activeMock.picks.length} picks. Your league was never touched.`,
-      primary: { label: 'View recap', onPress: onResume, testID: 'mock-entry.recap' },
-      secondary: { label: 'Run it back', onPress: onStart, testID: 'mock-entry.run-it-back' },
+      primary: { label: 'Start a new mock', onPress: onStart, testID: 'mock-entry.run-it-back' },
+      secondary: { label: 'View recap', onPress: onResume, testID: 'mock-entry.recap' },
     };
   }
```

**testIDs deliberately stay bound to the *action*, not the position** —
`mock-entry.run-it-back` is still the start-another action and
`mock-entry.recap` is still the recap action. No testID is added, renamed or
orphaned, so `testid-lint` is unaffected and any future flow keeps working.

### 7.3 `DraftRoomScreen.tsx` — clear `postRefusal`, wire `retry`

Three edits:

1. **Mode re-entry** (`:611`):
   ```diff
   -            <DraftModeToggle mode={mode} onMode={setMode} />
   +            <DraftModeToggle
   +              mode={mode}
   +              onMode={(m) => { if (m === 'mock') setPostRefusal(null); setMode(m); }}
   +            />
   ```
   ⚠ `check-mock-mode-marker.js` asserts `DraftModeToggle` appears **exactly
   once** and that its guards mention `mockOn`. An inline arrow satisfies both.

2. **Setup-sheet open** — inside the existing `onStart: () => setSetupOpen(true)`
   at `:636`, also `setPostRefusal(null)` and `createMock.reset()`. One transient
   refusal or failed create must not mute the card for the session.

3. **Retry** — pass to `MockEntryPanel` at `:625-639`:
   ```ts
   retry={{
     label: 'Try again',
     testID: 'mock-entry.retry',
     onPress: () => { createMock.reset(); mockQuery.refetch(); },
   }}
   ```
   `createMock.reset()` clears the sticky `isError`; `refetch()` re-answers the
   `mockQuery.isError` half. Both error sources feed one `errorText`
   (`:626-633`), so one control clears both.

### 7.4 `MockDraftScreen.tsx:198-212` — a dismissal for a completed mock

```diff
       headerRight: () =>
-        state?.status === 'active' ? (
+        state?.status === 'active' || state?.status === 'complete' ? (
           <Pressable
             testID="mock-draft.end"
             onPress={endMock}
             …
-            accessibilityLabel="End this mock draft"
+            accessibilityLabel={state?.status === 'complete'
+              ? 'Clear this mock draft recap'
+              : 'End this mock draft'}
           >
-            <Text style={styles.headerAction}>End</Text>
+            <Text style={styles.headerAction}>
+              {state?.status === 'complete' ? 'Clear' : 'End'}
+            </Text>
           </Pressable>
         ) : null,
```

and in `endMock` (`:170-195`), branch the `Alert` copy on status:

| Status | Title | Body | Destructive label |
|---|---|---|---|
| `active` | "End this mock?" | unchanged | "End mock" |
| `complete` | "Clear this recap?" | "The recap is discarded. You can start a new mock any time — your league was never touched." | "Clear" |

Both paths call the **same** `abandonMockDraft(mockId)` → invalidate → `goBack()`.
No new testID; `mock-draft.end` is reused, which keeps the marker test and any
future flow stable.

**No new top-level return is introduced** — `headerRight` is a `useLayoutEffect`
callback, outside the component's single return.

### 7.5 Backend: sweep the accumulated completed mocks (I-5)

**Round 1 claimed #292 was mobile-only. That was right for the first completed
mock and wrong for the steady state**, and the correction costs one small
`database.py` function.

`create_mock_draft` abandons only rows with `status == "active"`
(`database.py:10739`), and `load_current_mock_draft`'s complete-fallback is
`ORDER BY id DESC LIMIT 1` (`:10774-10781`). So **completed rows accumulate, one
per finished mock, forever** — dismiss mock #N and #N-1 appears. For anyone past
their second mock (exactly the #292 population) the dead-end is paginated, not
fixed.

**New in `backend/database.py`, beside the other four mock functions:**

```python
def abandon_completed_mock_drafts(user_id: str, league_id: str) -> int:
    """Abandon EVERY completed mock for this (user, league). Returns rowcount.

    Older completed rows are unreachable from any UI — every read path goes
    through `load_current_mock_draft`, which returns only the newest — so
    clearing them destroys nothing a user can see, and leaving them turns one
    dismissal into N (#292).
    """
```

One `UPDATE … WHERE user_id = ? AND league_id = ? AND status = 'complete'`
setting `status='abandoned', updated_at=now`. Owner-scoped, idempotent.

**Route change — `mock_draft_abandon_route` (`server.py:11781-11794`), G2's region:**

```python
row = load_mock_draft(body.get("mock_id") or 0, user_id)     # +1 query
if row is None:
    return jsonify({"error": "mock_not_found"}), 404
if str(row.get("status")) == mds.STATUS_COMPLETE:
    abandon_completed_mock_drafts(user_id, str(row["league_id"]))
elif not update_mock_draft(row["id"], user_id, status=mds.STATUS_ABANDONED):
    return jsonify({"error": "mock_not_found"}), 404
return jsonify({"ok": True})
```

Request shape, response shape and status codes are **unchanged**; only the
semantics of dismissing a *completed* mock widen. `docs/api-reference.md`
therefore moves from "n/a" to **one clarifying sentence** — see
[`scope.md` §4](./scope.md#4-docs-scope-mandatory--hld--lld--api).

**Consequence for ownership:** G2 **retains** its `backend/database.py:10714-10805`
region claim. Round 1's release of it is withdrawn.

### 7.6 What is *not* changed

- **`load_current_mock_draft` (`database.py:10762-10785`) is untouched.** Its
  complete-fallback is the documented resume-or-recap contract; the fix is to
  give the user a way to *dismiss*, not to make the row expire invisibly, and not
  to change what "current" means.
- **`MockSetupSheet.tsx` is not touched.** The busy-stranding path the plan
  flagged is not one of D-8's three proven dead-ends and is out of scope.
- **`MOCK_MIN_TEAMS` disagreement stays** — client `6`
  (`MockEntryPanel.tsx:41`), server `4` (`mock_draft_service.py:85`). A real
  fourth dead-end for 4- and 5-team leagues, but not a *second*-mock dead-end and
  not in D-8. Flagged in [`scope.md` §6](./scope.md#6-out-of-scope-and-flagged).

---

## 8. Route and response contracts

**No change.** Stated explicitly because the scope block's docs table depends on
it:

| Route | Change |
|---|---|
| `GET /api/mock-draft` | none — `order[].owner_username` may now hold a *better string* on MFL leagues (D-16); type, nullability and key set unchanged |
| `POST /api/mock-draft` | none |
| `POST /api/mock-draft/pick` | none |
| `POST /api/mock-draft/abandon` | none — already accepts a `complete` row |

`SCHEMA` is unchanged. `docs/api-reference.md` therefore needs **no** edit for
this group — recorded as "n/a because" in [`scope.md` §4](./scope.md#4-docs-scope-mandatory--hld--lld--api),
not left silent.

---

## 9. Test-helper corrections

One shipped test measures the reach law with `needs = 0.0`, which under §4 is no
longer the branch it names.

**`backend/tests/test_mock_draft.py:230-238` — `_reach_draws`:**

```diff
     board = _candidates(["WR"] * width)
-    needs = {pos: 0.0 for pos in ("QB", "RB", "WR", "TE")}
+    # Maximal need, so `effective_bpa_prob` returns `bpa_prob` exactly and this
+    # helper keeps measuring the mixture's REACH BRANCH rather than the tilt.
+    # The board is single-position, so the need bonus is a constant across every
+    # candidate and cancels out of the argmin — the measured law is unchanged.
+    needs = {pos: 1.0 for pos in ("QB", "RB", "WR", "TE")}
```

This is **not** an assertion weakening. On a uniform-position board the bonus
`weight × severity × max_reach` is identical for every candidate, so
`argmin(rank − c − noise) == argmin(rank − noise)` exactly. The two tests it
feeds keep their assertions verbatim:

- `test_w2_04b_bpa_prob_is_exactly_the_mass_on_the_board_pick` (`:241`)
- `test_w2_04b_the_reach_branch_is_geometric_in_reach_decay` (`:248`)

**Measured blast radius.** Running the full `test_mock_draft.py` against a
prototype of §4 alone in this worktree: **1 failed, 79 passed** — the single
failure being `test_w2_04b_the_reach_branch_is_geometric_in_reach_decay`
(`P(1)/P(0) = 0.069` against an expected `0.5`), which is precisely the helper
above. `test_w2_16_calibration_gate` **passed** — the tripwire did not fire.
Full-change result and the standing instruction if the tripwire *does* fire:
[`prd.md` §7](./prd.md#7-test-plan).

---

## 10. Citation corrections to `plan.md`

Every load-bearing citation in the plan was re-read against `7cea1fa`. The
substantive claims hold; these drift or are wrong.

| Plan says | Actual | Impact |
|---|---|---|
| `mock_draft_service.py:646-652` (the scoring loop) | `:646-651`; `reaching` at `:643`; truncation at `:637-638` | cosmetic |
| `:1144-1147` / `:1127-1148` for `_block_rank` | `def` at `:1127`, body ends `:1148` | none |
| `:1170` for *"a value curve that flattens in the tail"* | that phrase is at **`:231`**; `:1170` is inside `reach_report`'s docstring | none — the claim is right, the line is not |
| `:294` `CPU_MODEL_VALIDATED` / `:295` `CALIBRATION_ARTIFACT` | correct | — |
| `:154`,`:159` for the round-1 cap/budget tables | `MOCK_REACH_CAP_BY_ROUND` at `:154`, `MOCK_REACH_BUDGET_BY_ROUND` at `:159` | correct |
| `database.py:10723-10748` `create_mock_draft`; `:10762-10785` `load_current_mock_draft`; complete-fallback at `:10774` | correct | — |
| `server.py:11437` mock `usernames` (plan) / `:11438` (G1 PRD §11) | **`:11437`, and a SECOND site at `:11474`** | material — see §5.1 |
| `server.py:11744-11779` `/pick`, `:11781-11794` `/abandon` | correct | — |
| "Extend the abandon route to accept a `complete` row" (§4.1 Option A) | **already true** — `update_mock_draft` filters on id + user only. **But** `create_mock_draft` abandons only `active` rows (`:10739`) and the complete-fallback is `ORDER BY id DESC LIMIT 1`, so completed rows accumulate and one dismissal is not enough | material — the route needs no *contract* change, but #292 does need a backend sweep (§7.5). Round 1's "mobile-only" is withdrawn |
| `DraftRoomScreen.tsx:1325` / `:1375` / `:823-830`; `MockDraftScreen.tsx:200-212` (actually `:198-212`) / `:284`; `MockEntryPanel.tsx:90-96` / `:72-80` / `:41`; `test_mock_draft.py:332` / `:708` / `:248` / `:265` / `:402` | all correct | — |
| §1: "the consensus #7 rookie goes 4th overall 10.9 % of the time" | measured on a **synthetic uniform** board. On the **real** pinned board the same statistic is ~11 % for Kenyon Sadiq (#7) — so the number survives, but the *player* it was attributed to does not: **Carnell Tate is consensus #2** | material — see [`prd.md` §4](./prd.md#4-the-tate-case) |
| §8 Spike A: "Tate's consensus rank cannot be established" | **established** — `_rookie_ctx` + `consensus_pool` reproduce the shipped board with no DB; Tate is #2 in both `1qb_ppr` and `sf_tep` | material — Spike A is closed, not blocking |
| R9: "`ffv3-predraft` is blocked by `draft_order: null`" | `draft_order: null` only downgrades `order_source` to `randomized` (`_mock_real_draft`, `server.py:11555-11557`); it does **not** block a mock. The fixture is 12 teams, `pre_draft`, 4 rounds, linear — every `mockBlock` predicate passes. ⚠ **But the league is not seedable today:** `profiles/standard.json` declares exactly one league (`990000000000000001`), d1/d2 target leagues in no profile, and `git grep` finds d1/d2 referenced by no suite file or runner — the "corpus merged into the fixture dir" step is unimplemented. Also: ffv3's **top-level `rounds` is `null`** (the 4 is in `settings.rounds`) | material both ways — no engine or route work is needed, but the flow is blocked on a pre-existing seeding gap. Round 1's "zero seeder work" is withdrawn; see [`scope.md` §3](./scope.md#3-test-scope-mobile-test-platform) |

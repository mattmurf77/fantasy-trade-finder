# FB-328 — Critic review, round 1

> Reviewer: G3 Planner (critic role). Docs reviewed: `hld-delta.md`,
> `lld-delta.md`, `prd.md`, `scope.md` (working tree, 2026-08-16). All code
> verification against `origin/main` @ `d3fe3ac`. Verdict: **sound overall —
> 1 BLOCKING, 4 NON-BLOCKING.**

## Verdict on the Author's four corrections

All four accepted after independent code verification:

1. **`_assignment_grid` second-caller (checked hardest): correct, no shape
   mismatch.** `_assignment_grid(league_id, season)` exists at
   `server.py:11208-11245`, is already the board route's helper, filters to
   the requested season, and excludes contested/orphaned rows at the source
   (`load_draft_picks(source=PICK_SOURCE_USER)` default row filter;
   grid comment `server.py:11219-11221`). `assigned_board`
   (`draft_board_service.py:1372-1462`) emits `order[]` rows carrying exactly
   the fields the reused reader consumes (`slot`, `round`,
   `original_user_id`, `is_traded`, `owner_user_id`) with unconditional
   `order_confidence: ORDER_ASSIGNED` (`:1453`), and the unseeded case
   returns `_render_unavailable` whose non-assigned confidence hits the
   existing early return — label stays `"none"` with zero new code, as the
   LLD claims. `BoardRequest` defaults (`draft_board_service.py:201-224`)
   make the LLD's minimal construction valid; `consensus_elo`/`basis` are
   only read under `fetchers`, which the mock doesn't pass. A slot whose
   original owner is missing from the stored order gets `slot: None`
   (`server.py:11229`), which the reader's `if slot` guards skip — degrades
   honestly, no crash.
2. **Mount placement:** verified — `:697-700` is the active clock card's
   `clockMeta`, `:824-827` the recap card's; `styles.clockHow` already
   mounted at `:704`/`:710`. Mounting in both cards is the right call.
3. **Probe cites:** `_mock_capability` at `:12062`, comment block at
   `:12262-12269` — correct.
4. **Coercion mirror:** `mode`'s returned-dict coercion idiom confirmed at
   `mock_draft_service.py:1093`; mirroring it is the right convention.

Also independently verified: the MFL pre-shuffle recipe (lld §2.4) is
deterministic and permutation-identical to `build_settings`' internal shuffle
(`owners` is str-coerced at entry, `resolved_order = list(owners)` +
`shuffle` is the only rng consumer, `mock_draft_service.py:1043/1061-1062`);
the analytics cites (`analytics_taxonomy.py:855-856`,
`DraftRoomScreen.tsx:315-326`, `check-mock-draft-modes.js:617-627`) are all
accurate, and extending the `>= 5` pin to six is correctly specced;
Fleaflicker is explicitly fallback (prd R-7/T-6, out-of-scope bullet) — the
platform sweep is complete.

**Cross-group (hunt 6):** `state_payload()` appears in both G2's and G3's
touch lists, but G2's prd §3 (round-2 corrected) declares region-level
ownership that exactly mirrors G3's prd §4 reserved regions, plus a binding
serialization order (G3 merges first, G2 rebases). Function-level overlap
with disjoint regions + serialization is acceptable; no objection beyond
OBJ-5's cite drift.

---

## OBJ-1 — BLOCKING — prd §6.1: T-7's sabotage mapping is unsatisfiable

T-7's label half asserts a resolved Sleeper board yields
`ownership_source == "platform"`, and names **SAB-C** ("hardcode
`ownership_source=OWNERSHIP_SOURCE_PLATFORM` in `build_settings`") as its
proven-to-fail sabotage. SAB-C produces **exactly the value T-7 expects** —
T-7 passes under SAB-C by construction, so the proof obligation can never be
met. This is the 2026-08-10 lesson class ("a test that passes on the very
defect it names") baked into the spec itself. The build agent would either
discover the contradiction and stall, or worse, tick the box without running
it.

**Fix (small):** map T-7's label half to **SAB-E** (removing the
`settings_echo` echo line makes T-7's label read fail), or add **SAB-F**
("hardcode `OWNERSHIP_SOURCE_NONE`"), which also gives T-1/T-9's
positive-label assertions a second, sharper sabotage. Re-check the whole
matrix row-by-row after the remap.

## OBJ-2 — NON-BLOCKING (requires disposition) — partial-coverage data under a full-coverage label

Two cases produce a mock that is only *partially* real while labeled
`"user"`/`"platform"`; neither is dispositioned in prd §4 (out of scope) nor
tested:

- **(a) Contested/orphaned ESPN slots at round ≥ 2.** `_assignment_grid`
  excludes them (`server.py:11219-11221`), so a contested traded pick
  silently reverts to slot-order ownership while the caption reads "Real
  pick ownership applied". (Round-**1** contested is fine: the missing slot
  breaks `by_slot` completeness and the whole resolution honestly drops to
  `"none"` — the asymmetry is worth stating.) This also answers the hunt's
  "new owner left the league" case for ESPN: orphan-excluded, silent at
  round ≥ 2.
- **(b) Mock `rounds` exceeding grid/store coverage.** Defaults align
  (`DEFAULT_ROUNDS = 4`, `mock_draft_service.py:222`;
  `_ASSIGNMENT_DEFAULT_ROUNDS = 4`, `server.py:10947`), but grid rounds are
  user-settable and MFL store depth follows MFL's export — a 4-round mock
  over a 3-round grid drafts round 4 at slot order under a `"user"` label.
  The plan's risk table named this and promised "documented in the PRD"; the
  PRD dropped it.

**Fix:** either (i) an explicit accepted-limitation bullet in prd §4 + one
test pinning the round-≥2-contested behavior (so the choice is recorded and
guarded), or (ii) degrade the label when coverage is partial. Given the
operator's honesty requirement, (i) is the minimum; the choice is the
Author's, but silence is not available.

## OBJ-3 — NON-BLOCKING — hld §4 HD-2: the parity sentence is factually wrong

"the board … is what `PickAssignmentScreen` renders. Reading the board means
the mock and the assignment screen can never disagree." —
`PickAssignmentScreen` renders the pick-assignments **GET**, which
deliberately *includes* contested/orphaned slots ("this is the screen where
someone fixes them", `docs/api-reference.md:484`); the board **excludes**
them. Parity is with the **Draft Room**, and the screen/mock *can* disagree
in exactly OBJ-2(a)'s case. Rewrite the two sentences; the design itself
(read the board, not raw JSON) stays right and HD-2's rejection of the
raw-JSON alternative stands.

## OBJ-4 — NON-BLOCKING — prd §6.1: SAB-D is underspecified and T-3 can vacuously pass

SAB-D says "anchor the MFL overlay to the row's stored round-1 ordinal" —
MFL store rows carry no slot/ordinal field, so two builders would implement
the sabotage differently (the plausible reading is keying off
`int(original_roster_id)`, the franchise fid). Worse, if the chosen
`rng_seed`'s shuffle happens to place the original owner at that same
number, T-3 *passes under the sabotage* and the proof run records a false
green. **Fix:** define SAB-D concretely (e.g. `slot =
int(row["original_roster_id"].lstrip("0") or 0)`), and require T-3's fixture
to assert, as a precondition, that the sabotage keying differs from the
correct shuffled slot for the pinned seed.

## OBJ-5 — NON-BLOCKING (trivial) — settings_echo region cite drift

G2 prd §3's ownership table reserves "`state_payload()`'s `settings_echo`
dict (**:1414** block)" for G3; G3's lld §1.3 and prd §4 cite "**:1418**
block". Same region, two anchors — harmonize (the dict literal opens at
:1411; `order_source` sits at :1418) so the two build agents can't dispute
the boundary edge during the serialized rebase.

---

Not objected to, per instructions: the revert-only rollback posture (queued
for the operator checkpoint; scope.md §2/waiver 2 surfaces it correctly).

---

# ROUND 2: SIGNED OFF

All five dispositions verified present in the four docs' text, and the
reconciliation log's claims re-verified against `d3fe3ac`. OBJ-1: SAB-F
exists, T-7/T-9/T-1-label remapped to it, the self-satisfaction audit
paragraph sits above the matrix, and I independently spot-checked the three
re-audit fixes for the pattern a re-audit can reintroduce — T-12(d)/SAB-H
fails hard (a gapped round-1 map under `bool(by_slot)` either KeyErrors on
the order build or labels a positive value, never the expected `"none"`,
and SAB-A/SAB-G are explicitly rejected for (d) because both self-satisfy);
T-3's SAB-A removal is correct against code (the MFL block is route-level;
SAB-A leaves `real["order"]` None so the block still runs); T-8's
key-presence assertion closes the `.get()` hole. OBJ-2: the `"partial"`
vocabulary is threaded end-to-end (lld §1.1/§1.2/§2.2 `expected <= covered`
/§2.3 census + step-8 label rule/§3.1/§4.1/§4.2 caption; prd
R-6/8/9/11/14, T-4/T-12, SAB-G/H, TF step 7; hld §3 + HD-8; scope §1/§4),
the round-1 asymmetry is stated and pinned, and both enabler claims check
out in code — the Sleeper assigned path emits every `(round, slot)`
(`draft_board_service.py:826-829`) and `_ORDER_CAP=500`
(`draft_board_service.py:172`) cannot truncate a ≤8-round mock. OBJ-3:
HD-2 now states Draft-Room parity and discloses the PickAssignmentScreen
GET divergence as `"partial"`. OBJ-4: SAB-D is concrete (franchise-fid
ordinal) and T-3 carries the non-collision precondition plus a
distinct-seeds assertion. OBJ-5: `:1414` harmonized everywhere and verified
as the true `settings_echo` opener (my round-1 `:1411` was indeed wrong);
the G3-first serialization is stamped in prd §4 and scope waiver 4. One
zero-impact nit, no action needed: the reconciliation log's aside calls
`:1416` the `teams` line — it is `type` (`teams` is `:1417`); the binding
anchor `:1414` is unaffected and no contract doc carries the wrong number.
No round-2 objections. Ready for Phase 2, G3 first per the stamped order.

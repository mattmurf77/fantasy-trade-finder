# Status — FB-289: MFL Draft Room renders raw IDs instead of names (G1, backend)

- **Phase:** 2 (build) — **complete**, awaiting batch QA + orchestrator merge
- **Spec:** [`prd.md`](./prd.md) (15 requirements R-1…R-15, 14 tests T-289-01…14)
- **Worktree branch:** `worktree-agent-a361e2513acc56c5f`
  (descendant of `feedback-289-294` @ `7cea1fa`; two unrelated commits in
  between touch only `backend/data_loader.py` and
  `backend/tests/test_dp_values_history.py`)
- **Date:** 2026-08-10
- **Lane:** backend only. Zero files under `mobile/` changed (R-14).

## Table of Contents
- [1. What changed](#1-what-changed)
- [2. Verification evidence](#2-verification-evidence)
- [3. Requirement → implementation → test map](#3-requirement--implementation--test-map)
- [4. Deviations from the PRD](#4-deviations-from-the-prd)
- [5. For the orchestrator to apply](#5-for-the-orchestrator-to-apply)
- [6. Live QA checklist — Dependables (62846)](#6-live-qa-checklist--dependables-62846)

---

## 1. What changed

Three files, 408 insertions / 9 deletions.

### `backend/draft_board_service.py` (+105)

1. **`BoardRequest`** gains two MFL-only injected fields beside the existing
   `mfl_franchise_to_user` / `mfl_player_ids`, following the module's existing
   injection discipline (docstring I-7 — no `database` import added):
   `mfl_usernames: Mapping[str, str] | None` and
   `mfl_player_names: Mapping[str, tuple[str, str]] | None`.
2. **`_mfl_is_slot_sentinel(mfl_pid)`** — new 1-line predicate,
   `bool(mfl_pid) and set(mfl_pid) == {"0"}` (R-15).
3. **`_hydrate_mfl_picks(pending, pid_map, dp_names, fetchers)`** — new. One
   batched `fetchers.players(...)` call over `{pid_map[mfl_pid]}` for
   non-sentinel picks that crosswalked, then the four-tier resolution of §4's
   normative pseudocode, applied in place. **Tier 1's row is read by
   `pid_map[mfl_pid]`, never by `entry["player_id"]`** (R-7).
4. **`_render_mfl`** — three surgical edits: `username = req.mfl_usernames or {}`
   (was `{}` with the now-wrong comment "MFL has no display-name export here");
   `owner_username` gains the `Team <fid>` fallback with the empty-`fid` guard;
   the pick dict is bound to a name and paired with its **raw** MFL id in a
   `pending` list, hydrated in one pass after the grid walk. The loop keeps its
   shape — no refactor (coding-guidelines §3).

### `backend/server.py` (+26, all inside `_mfl_board_binding`)

Diff hunks land at 10446, 10476, 10481, 10495, 10504, 10511, 10513 — every one
inside `_mfl_board_binding` (original region 10411–10493). **No other line of
`server.py` is touched**; G2's mock-draft shims at ~11380–11530 are untouched.

- The existing `for m in members:` loop also collects
  `usernames[uid] = (username or display_name).strip()`, keeping only non-empty
  values. **Zero extra queries** — `members` was already loaded.
- The crosswalk `try` binds the object once and reads both maps off it
  (`xw.by_mfl_sleeper`, `xw.by_mfl_id`); the `except` sets both to `{}` and
  keeps today's `log.warning`, never a 5xx.
- `request_fields` gains `mfl_usernames` and `mfl_player_names`.
- Two docstring bullets added for the two new sources.

### `backend/tests/test_draft_board.py` (+286)

Fourteen cases (map in §3), plus the two fixture changes the PRD mandates:
- the `mfl_league` route fixture's stubbed `load_league_members` rows gain
  `username` values (without them T-289-09 would have passed on the
  `Team <fid>` fallback and proved nothing); franchises 0001–0006/0008/0009
  keep **no** member row so the fallback stays covered by the same fixture;
- the `_xwalk` helper gains `by_mfl_id` (the binding now reads it off the same
  object; without it the stub would raise into the `except` and silently
  zero the crosswalk, breaking `test_m5_08`).

**No corpus file was edited.** All four MFL corpora carry
`provenance: recorded-live`; T-289-08 uses an inline synthetic `draftResults`
dict, exactly as the PRD spells out.

---

## 2. Verification evidence

### 2.1 Suite

| Run | Command | Result |
|---|---|---|
| **Baseline** (pre-change, this worktree) | `python3 -m pytest backend/tests/ -q` | **2298 passed, 1 skipped** in 505.88s |
| **After** | `python3 -m pytest backend/tests/ -q` | **2308 passed, 1 skipped** in 223.13s |

Delta **+10 passed, 0 failed** — exactly the 10 new test functions
(`t289_04`, `t289_05`, `t289_05b` ×4 params, `t289_06`, `t289_07`, `t289_08`,
`t289_14`); the other four PRD cases extend existing tests. **No pre-existing
failure was observed and none was fixed.**

> The PRD quotes the `fb-289-294` worktree baseline as **2297 passed, 1 skipped**.
> This worktree reads **2298** because it sits two commits ahead of `7cea1fa`
> with an unrelated `backend/tests/test_dp_values_history.py` addition. Neither
> commit touches any file in this lane.

### 2.2 Targeted

```
python3 -m pytest backend/tests/test_draft_board.py -q
  -> 67 passed in 10.08s      (was 55 passed / 12 failed pre-fix)

python3 -m pytest backend/tests/test_draft_board.py \
                  backend/tests/test_mock_draft.py \
                  backend/tests/test_slot_values.py -q
  -> 180 passed in 146.39s
```

### 2.3 Failing-first (PRD §6.6, mandatory)

Run against the pre-fix tree. Two stages, because the first failure is a
signature error that proves nothing about behaviour:

**Stage 1 — before `BoardRequest` gained the fields:**

```
E  TypeError: BoardRequest.__init__() got an unexpected keyword argument 'mfl_usernames'
   backend/tests/test_draft_board.py:666
```

**Stage 2 — fields added, render unchanged. T-289-03 (R-5):**

```
>  assert (first["name"], first["position"], first["team"]) == \
E  AssertionError: assert ('', '', None) == ('Cam Skattebo', 'RB', 'ARI')
E    At index 0 diff: '' != 'Cam Skattebo'
```

**Stage 2 — T-289-06 (R-7), on the same tree:**

```
>  assert by_pick[1]["player_id"] == "17473" and by_pick[1]["name"] == "WRONG"
E  AssertionError: assert ('17473' == '17473'
E      17473 and '' == 'WRONG')
```

**Stage 2 — T-289-01 (R-1) and R-2, captured by direct render** (they sit
behind T-289-03 in the same test, so pytest never reaches them):

```
owned rows: 4
owner_username values (T-289-01 expects 'Eire Rebels'): [None]
unmapped-franchise owner_username (R-2 expects 'Team 00xx'): [None]
first pick name (R-5/R-9): ''
```

That is the reported bug, reproduced: `owner_username` structurally `None` on
every MFL row, `picks[].name` structurally `""`.

### 2.4 T-289-06 discrimination proof (PRD §4, the load-bearing guard)

The naive keying was temporarily introduced in `_hydrate_mfl_picks` —
`row = rows.get(entry["player_id"])` in place of the crosswalked-id read,
**leaving the query list correctly constrained** (which is the whole point:
the query is legal and the consumption is still wrong):

```
python3 -m pytest backend/tests/test_draft_board.py -q -k t289
  1 failed, 9 passed, 57 deselected

>  assert by_pick[2]["name"] != "WRONG", \
       "pick B adopted pick A's player — tier 1 was keyed by pick['player_id']"
E  AssertionError: pick B adopted pick A's player — tier 1 was keyed by pick['player_id']
E  assert 'WRONG' != 'WRONG'
```

T-289-06 is the **only** test that fails on the naive implementation, and it
does fail. Reverted immediately; the full suite above was run after the revert.

### 2.5 Route smoke — `GET /api/draft/board`, MFL path, over HTTP

**Ran.** Real Flask app on `127.0.0.1:5289` against a scratch copy of
`data/trade_finder.db` (the live DB was never written). Exactly two things
stubbed, both for hermeticity rather than to dodge code under test:
`server._mfl_draft_opener` → the committed `mfl-complete` corpus (MFL has no
env fixture seam), and the session dict (a real one needs a Sleeper login).
The route, `_mfl_board_binding`, the `league_members` read, `_shared_crosswalk()`
over the committed DP file, and `_render_mfl` are all production code.

Scratch league seeded with franchise names for 0001/0003/0006/0007/0010 and
**no** member row for 0002/0004/0005/0008/0009, so both R-1 and R-2 are live.

```
"GET /api/draft/board?league_id=10005 HTTP/1.1" 200 -
```

PRD §9 counting script over the captured payload
(`feedback-workspace/289/board-smoke.json`, gitignored):

```
platform: mfl  state: complete  schema: 1
order rows: 30  my_picks: 4
made picks: 30  (sentinel 'No selection': 0)
tier-3 fallback: 0 / 30 (0.0%)  -> REPORT to operator, not a gate
HARD FAILS -> letter-less name: 0  mfl: in owner: 0
no position chip: 0 / 30

sample order rows: [(1, 1, 'smoke_user_289', 'Eire Rebels'),
                    (1, 2, 'mfl:10005.f0010', 'Kings of the Empire'),
                    (1, 3, 'mfl:10005.f0006', 'Sunday Scaries'),
                    (1, 4, None, 'Team 0004'), ...]
sample picks: [(1, '13287', 'Jeremiyah Love', 'RB', None),
               (2, '13286', 'Jadarian Price', 'RB', None),
               (3, '13279', 'Carnell Tate', 'WR', None), ...]
distinct owner_username: ['Dependables', 'Eire Rebels', 'Gridiron Ghosts',
  'Kings of the Empire', 'Sunday Scaries', 'Team 0002', 'Team 0004',
  'Team 0005', 'Team 0008', 'Team 0009']
```

Zero live egress: `grep -icE "myfantasyleague.com|api.sleeper.app"` over the
server log returns `0`.

**Finding worth escalating — tier 2 carried the entire board.** The scratch DB
has `SELECT count(*) FROM players` = **0** (this dev DB has no player cache), so
tier 1 resolved *nothing* and all 30 names came from the DP crosswalk's
`by_mfl_id` map. That is the tier the Planner recommended omitting; without it
this smoke would have rendered 30 rows of `Player 17472`-style placeholders.
It also explains `team = None` on every row (tier 2 carries no team) and is a
concrete instance of the §9 note that a high tier-3 / no-team rate points at a
stale player cache, not at a code defect.

### 2.6 Not run, deliberately

- **iOS simulator / Maestro** — batch QA's job per the task brief; parallel
  agents contending over one simulator has broken prior runs.
- **`cd mobile && npx tsc --noEmit`** — this worktree has **no**
  `mobile/node_modules`, so it cannot run here. It is a guard, not a target:
  `git diff --name-only` lists zero paths under `mobile/` (R-14), so there is
  nothing for it to catch. Whoever runs the batch typecheck should confirm.
- **Live Dependables (62846) run** — the local DB holds no such league (only
  synthetic `990062846` / `test_owned_picks_mfl` rows). Checklist in §6.

---

## 3. Requirement → implementation → test map

| Req | Implemented at | Covered by |
|---|---|---|
| **R-1** `order[].owner_username` = franchise name | `draft_board_service._render_mfl` (`username = req.mfl_usernames or {}`, owner cell) + `server._mfl_board_binding` (`usernames` collection) | T-289-01 (in `test_m5_mfl_franchise_and_player_maps_are_honoured`), T-289-09 (in `test_m5_07…`) |
| **R-2** fallback `Team <fid>`, never a synthetic id | `_render_mfl` owner cell: `(username.get(owner) if owner else None) or (f"Team {fid}" if fid else None)` | T-289-02 (same test — `re.fullmatch(r"Team \d{4}")` on unmapped rows + the global no-`mfl:` scan) |
| **R-3** no franchise at all ⇒ both `None` | same expression, `if fid` guard | `test_t289_08_a_franchise_less_slot_stays_unassigned` |
| **R-4** `my_picks` inherits the names | consequence of the `order` slice at `_payload` | asserted in `test_m5_mfl_…_honoured` (`user_id="user-7"`) and in `test_m5_07…` |
| **R-5** picks hydrated from our `players` | `_hydrate_mfl_picks` tier 1 | T-289-03 (same test) |
| **R-6** exactly one batched `players` call | `_hydrate_mfl_picks` — `wanted` set built before the resolution loop | `test_t289_07_pick_hydration_is_one_batched_call_over_crosswalked_ids_only` |
| **R-7** per-pick tier-1 gate, keyed by the crosswalked id | `_hydrate_mfl_picks`: `crosswalked = pid_map.get(mfl_pid)`, `rows.get(crosswalked)` | **`test_t289_06_an_uncrosswalked_pick_never_adopts_another_picks_player`** — proven discriminating (§2.4) |
| **R-8** DP-name fallback (tier 2) | `_hydrate_mfl_picks` tier 2 + `server` binding `player_names = xw.by_mfl_id` | `test_t289_04_a_crosswalk_miss_falls_back_to_the_dp_name` |
| **R-9** terminal `Player <mfl_id>`; a name always has a letter | `_hydrate_mfl_picks` tier 3 | `test_t289_05_…never_a_bare_number` + `test_t289_05b_every_rendered_pick_name_contains_a_letter` (4 corpora × 3 map configs) |
| **R-10** `owner_user_id` untouched | no change to that key | `test_m5_07…` (`my_picks` still resolves via the synthetic-id scheme), `test_m5_08` |
| **R-11** `original_*` stay `null` | no change | `test_t289_08…` |
| **R-12** `schema` 1, key set unchanged, other platforms unmoved | no change to `_payload` | `test_m5_06` (flag-off byte-identical), `test_m5_10` (no Sleeper response moves), `EXPECTED_KEYS` |
| **R-13** no new egress, no new DB read | `usernames` off the already-loaded `members`; one bounded `players` read, none when nothing crosswalked | `test_m5_07…` (`len(mfl_league) == 1 and "TYPE=draftResults" in …`) + T-289-07's "no crosswalk ⇒ no call" half |
| **R-14** mobile untouched | — | `git diff --name-only` lists no `mobile/` path |
| **R-15** all-zeros sentinel ⇒ `No selection` | `_mfl_is_slot_sentinel` + tier S | `test_t289_14_the_all_zeros_slot_sentinel_reads_no_selection` |

Regression cases T-289-10 / -11 / -12 / -13 are the existing `test_m5_06`,
`test_m5_10`, `test_m5_07`'s egress assertion and
`test_the_whole_matrix_is_replayed_never_live` — all pass unmodified except
`test_m5_07`, which gained the T-289-09 assertions (additive only).

---

## 4. Deviations from the PRD

**None material.** Three notes, all inside the spec's own latitude:

1. **T-289-01/02/03 are asserted inside the existing
   `test_m5_mfl_franchise_and_player_maps_are_honoured`**, which is exactly
   what the PRD's anchor column says ("extend …", "same test"). That test also
   gained `user_id="user-7"` so `my_picks` is non-empty and R-4's assertion is
   not vacuous.
2. **Tier 2's condition is the PRD's literal `elif dp:`** — truthiness of the
   `(name, position)` tuple, not of `dp[0]`. A DP row with an empty name cannot
   exist (`_parse_crosswalk_rows` inserts `by_mfl_id` only under
   `if raw_name and pos`), so tightening it would be a speculative guard.
   Flagged rather than taken.
3. **The `_xwalk` test helper gained `by_mfl_id`.** Not named in the PRD, but
   forced by its own §4 binding delta: reading both maps off one object means a
   stub without `by_mfl_id` raises into the `except` and silently zeroes
   `mfl_player_ids`, which would have broken `test_m5_08` for a reason
   unrelated to the fix.

---

## 5. For the orchestrator to apply

G1 did **not** touch any of these (orchestrator-owned per `batch-plan.md`).

1. **`docs/api-reference.md`** — the `GET /api/draft/board` row (`:414`),
   inserted after "…never stale-as-live.". Exact text is in
   [`scope.md` §4](./scope.md#4-docs-scope-mandatory--hld--lld--api) under
   *Proposed `docs/api-reference.md` delta*. **Required** — the documented MFL
   contract is now wrong by omission.
2. **`living-memory/DECISIONS.md`** — one entry at next id (max + 1); exact
   text in `scope.md` §4 under *Proposed `living-memory/DECISIONS.md` entry*.
   Covers the four-tier resolution and the crosswalked-id keying guard.
3. **`living-memory/CHANGELOG.md`** — dated H2 at ship.
4. **`living-memory/TEST_LEDGER.md`** — suite result (2298 → 2308 passed,
   1 skipped), the Tier 3 sim run, and the live-league coverage counts from §6.
5. **Optional, `docs/glossary.md`** — the one-clause tightening of the
   *Synthetic member id* entry proposed in `scope.md` §4.
6. **Backlog item** — "MFL seam for the mobile QA harness" (`scope.md` §3's
   three pieces) → `living-memory/NEXT.md` or the feedback backlog.
7. **Cross-group** — the identical defect in the mock draft
   (`mock_draft_service.py:1013` fed from `server.py:11438`) is **G2's**, per
   `prd.md` §10. After this ships, an MFL league's Draft Room shows franchise
   names while its Mock Draft may still show ids.

`config/features.json` needs **no** change: `draft.mfl` and `draft.room` stay
`true`; the fix ships unflagged, with `draft.mfl → false` as the deploy-free
rollback lever.

---

## 6. Live QA checklist — Dependables (62846)

PRD §9 is the acceptance surface. It could **not** be run from this worktree:
the local `data/trade_finder.db` holds no league 62846 (only the synthetic
`990062846` / `test_owned_picks_mfl` rows), so there is no real MFL grid, no
real franchise names and no real player ids to count. Run it against a build
pointed at a backend carrying this fix.

**Preconditions**

- [ ] Backend under test carries this change (local `python run.py`, a Render
      preview, or `main` post-deploy) — **record which** in the ledger entry.
- [ ] The operator's account is linked to MFL league 62846 and the league row
      carries a `platform_host` (if it did not, the screen would render
      `platform_unsupported` and #289 could not have been filed).
- [ ] `draft.mfl` and `draft.room` are `true`.
- [ ] Any credential comes from `secrets.local.env`, never from chat.

**Steps**

- [ ] Launch a dev/TestFlight build pointed at that backend; sign in as the
      operator.
- [ ] Make **Dependables (62846)** the active league (League tab → switcher).
- [ ] Open the Draft tab (or deep link `app/league/draft-room`).
- [ ] Screenshot the order list **and** the made-picks list into
      `docs/feedback/items/289-mfl-draft-room-ids/`.

**On-screen pass criteria**

| Req | Must be true | Automatic FAIL |
|---|---|---|
| R-1 | every order row's owner cell reads a franchise name | any row reading `mfl:62846.f0001` — the exact string from the report |
| R-2 | a franchise with no stored name reads `Team 0007`-style | any `mfl:` prefix anywhere on the screen |
| R-3 | slots the grid leaves unassigned read `Unassigned` | a bare `Team ` with no number |
| R-4 | the operator's own rows read their franchise name | `mfl:62846.f<their fid>` |
| R-5 | every made pick reads a player name with a **coloured** position chip, and ` · TEAM` where known | a bare number, or a dim `—` chip on a row that also has a real name |
| R-8 | DP-tier rows read a real name + coloured chip but **no** ` · TEAM` | a name with a `—` chip (position was lost, not just team) |
| R-9 | any unresolvable row reads `Player 17472`-style | **a bare numeric id — the original bug, automatic FAIL** |
| R-15 | a passed/forfeited slot reads `No selection` with a dim `—` chip | `0000`, or `Player 0000` |
| R-11 | traded rows read `from —` | known + accepted (`prd.md` §7 item 1) |

**Coverage count (folded-in spike S-2)**

- [ ] Capture `GET /api/draft/board?league_id=62846` to
      `feedback-workspace/289/board-62846.json` — QA-harness scratch-DB boot
      (`qa/lib/harness.py` `make_scratch_db` + `boot_server`) if the league is
      in the local DB, otherwise from the authenticated dev build's network
      inspector. **Never point a local server at prod.**
- [ ] Run the PRD §9 counting script over it.
- [ ] **Absolute FAILs, no judgement:** `letter-less name > 0` or
      `mfl: in owner > 0` ⇒ do not ship.
- [ ] **`tier-3 fallback` has no pass bar** — record the count and rate and
      hand them to the operator (ship / refresh-and-recount). First remedy for
      a high rate is the player-cache refresh at `docs/runbook.md:482`, then a
      re-count. §2.5 above is a live demonstration of why: an empty player
      cache pushes the whole board off tier 1.
- [ ] `no position chip` — reported, not gated.
- [ ] Record every count verbatim here and in `TEST_LEDGER.md`. **Do not claim
      "names are fixed" without the numbers.**

**Sim gate** — Tier **3**: run
`mobile/.maestro/flows/rookie/d1-draft-room-complete.yaml` and
`d2-draft-room-order-not-set.yaml` (Sleeper corpus, no-regression), log in
`TEST_LEDGER.md`, write `qa/sim-runs/last-sim-run.json`.

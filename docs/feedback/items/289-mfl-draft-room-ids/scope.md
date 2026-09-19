# Feature Scope — FB-289: MFL identity in the Draft Room (G1)

<!--
Copied from docs/templates/feature-scope.md. Every section answered or
explicitly WAIVED with a reason. Silence is not a waiver.
Full requirements + payload contract: ./prd.md
-->

**Date:** 2026-08-10
**Entry point:** feedback #289 (screen `DraftRoom`, app 1.11.0, mattmurf77)
**Builder:** `/feedback` pipeline — G1 build agent, branch `feedback-289-294`,
base `origin/main` @ `7cea1fa`
**Operator sign-off on waivers:** REQUIRED — two waivers below (§1 analytics,
§3 Maestro). The Maestro waiver already carries an operator ruling (live-league
QA on Dependables 62846); the analytics waiver is surfaced for confirmation.

**Rigor lane:** FULL GATES. No operator express declaration was made, and
agents never self-select express (CLAUDE.md §Conventions).

---

## 1. Analytics scope

- [ ] **(a) New events specced** — none.
- [x] **(b) Existing events cover it** — `screen_viewed` with
  `screen = "DraftRoom"` already measures reach of the surface, and the
  Draft Room's W1 action events (`draft_room_row_menu_opened`,
  `draft_room_action_taken`, `draft_room_coverage_nudge_shown`,
  `draft_room_rank_rookies_tapped`, registered in
  `backend/analytics_taxonomy.py:87-88` with property sets at `:241-246`)
  already measure engagement with player rows. If the fix works, MFL users
  should begin producing `draft_room_row_menu_opened` at rates closer to
  Sleeper users' — that is the observational read, off events that already
  exist.
- [x] **(c) WAIVED — no NEW analytics because:** this is a bug fix that changes
  only string *values* inside an already-shipped payload. It adds no user
  action, no new surface, no new decision point, and collects no new data. The
  taxonomy is **DEFAULT-DENY** (`analytics_taxonomy.py` module docstring:
  unregistered client events are counted and silently dropped, never 4xx'd), so
  a new event would require a tracking-plan addendum first — disproportionate
  for a defect fix with no new behaviour to instrument. **No client fires
  anything new; no `record_event` call is added.**

→ follow-through: none. `docs/data-dictionary.md` unaffected (nothing stored).

## 2. Schema & flag scope

- **New/changed tables or columns:** **none.** No DDL, no migration, no
  backfill. The fix is entirely inside a per-request computed payload
  (`draft_board_service._render_mfl`) — only the raw upstream `_Entry` is
  cached, never a rendered payload, so the first request after deploy is
  correct. Stored MFL data is already right (`league_members.username` holds
  cleaned franchise names; `draft_picks.owner_username` is already resolved by
  `_sync_mfl_owned_picks`). `docs/data-dictionary.md` unaffected.
- **New/changed feature flags:** **none.** No new flag is added.
  **`draft.mfl` stays `true`** (`config/features.json:151`, and it is in
  `feature_flags.FLAG_KEYS` at `:415`); `draft.room` stays `true`
  (`config/features.json:149`). The fix ships **unflagged**, deliberately:
  gating a defect fix behind a new switch would mean shipping a second code
  path whose "off" state is the bug, and the existing `draft.mfl` flag already
  provides the deploy-free rollback lever (turning it off restores the
  byte-identical `platform_unsupported` payload — asserted by `test_m5_06`).
  `docs/config-reference.md` unaffected.
- **New env vars / `model_config` keys:** **none.**
  **Ship-the-knob / rollback lever:** `draft.mfl → false` reverts the entire MFL
  board to the pre-M5 honest-unsupported state without a deploy. Blast radius of
  a bad fix is one platform on one screen.

## 3. Test scope (mobile test platform)

- [ ] **New flow:** none.
- [ ] **Extended flow:** none.
- [x] **WAIVED — no `mobile/.maestro/` flow is authored, because MFL is not
  seedable in the mobile QA harness AND because a stronger substitute exists.**

  *Mechanical reason (why one cannot be written):* the harness is
  Sleeper-fixture-driven via `FTF_SLEEPER_FIXTURES_DIR`. `backend/test_users.py`,
  `backend/test_support.py`, `qa/` and every `mobile/.maestro/*.yaml` contain
  **zero** MFL references (the only `mfl` hits under `.maestro/` are unrelated
  screenshot filenames). MFL's only test seam is the
  `server._mfl_draft_opener()` monkeypatch, reachable from pytest and not from
  a device-driven flow. Authoring an MFL flow requires building the seam first.

  *Coverage reason (why the waiver is not a coverage gap):* **operator ruling —
  QA runs against the real MFL league where #289 was observed, Dependables
  (id 62846).** A live-league verification on the reporter's own board is
  stronger evidence than a fixture flow: it exercises real franchise names, real
  MFL player ids, and the real DP crosswalk, and it produces the crosswalk
  coverage number a fixture cannot. Full procedure, per-requirement observable
  pass criteria, and the counting script are in [`prd.md` §9](./prd.md#9-live-league-qa-acceptance-procedure-dependables-62846).
  Screenshots land in this folder.

  *What a future automated flow would need* — **named backlog item: "MFL seam
  for the mobile QA harness."** Three pieces, none of which belong to this fix:
  1. An `FTF_MFL_FIXTURES_DIR`-style env seam so `_mfl_draft_opener()` replays a
     committed `TYPE=draftResults` corpus for a harness league (the pytest
     monkeypatch has no env equivalent).
  2. An MFL-linked `qa_*` stage user in `backend/test_users.py`, with seeded
     `leagues.platform_host` / `platform_season` / `platform_my_team` and
     `league_members` rows carrying franchise names.
  3. A `testID` on the Draft Room order-row owner cell (today only the row
     itself is tagged — `draft-room.order-row.<round>-<slot>`,
     `DraftRoomScreen.tsx:1134`), so a flow can assert the owner **text**
     rather than the row's existence.

  Recommend the orchestrator file this to `living-memory/NEXT.md` or the
  feedback backlog rather than absorbing it here.

- **`testID`s added/renamed:** **none.** No mobile file changes, so
  `mobile/scripts/testid-lint.sh` has nothing new to check (it must still pass).
- **Smoke-suite impact:** the route this change touches (`GET /api/draft/board`)
  is crossed by `mobile/.maestro/flows/rookie/d1-draft-room-complete.yaml` and
  `d2-draft-room-order-not-set.yaml`. Both drive the **Sleeper** Lakeview corpus
  as `qa_standard`; the Sleeper render path is provably unchanged
  (`test_m5_10`), so both must stay green — they are the Tier 3 subset in §5.
- **Backend: pytest files added/updated:** `backend/tests/test_draft_board.py`
  only — fourteen cases T-289-01…14 (table in [`prd.md` §8](./prd.md#8-test-plan)),
  two of them **failing-first** against `7cea1fa`. Three carry full inline specs
  in the PRD because they cannot be improvised: **T-289-06** (the discriminating
  wrong-player guard — an earlier draft's version could not fail on the buggy
  implementation), **T-289-08** (an inline synthetic `draftResults` dict; no
  committed corpus has a franchise-less pick), and **T-289-14** (MFL's
  `"player": "0000"` sentinel, live in `mfl-multi-unit`).
  Also required: a change to the `mfl_league` fixture (`:931-934`), which
  currently stubs `load_league_members` with rows that have no `username` key —
  without it the new route assertion passes on the fallback and proves nothing.
  Suite baseline on this worktree: **2297 passed, 1 skipped**.
  `cd mobile && npx tsc --noEmit` clean (guard only; no mobile change).

## 4. Docs scope (MANDATORY — HLD / LLD / API)

Shared docs are **orchestrator-owned** (`batch-plan.md` § File ownership). G1
proposes exact text below and does **not** edit these files.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **YES — orchestrator applies** | The route is unchanged and the payload shape is unchanged, but the **documented MFL contract is now wrong by omission**: `order[].owner_username` and `picks[].name/position/team` are described generically at `:414` with no statement that MFL populated none of them, and after the fix their MFL population follows a specified fallback ladder a client author must know about. Contract-level behaviour change ⇒ the row is updated. Proposed text below. |
| `living-memory/LLD.md` | **no — n/a because** no schema, route, or invariant *convention* shifts. `BoardRequest` gains two MFL-only injected fields, which is the module's existing, documented injection convention (docstring I-7), not a new one. |
| `docs/architecture.md` | **no — n/a because** no module is added, removed or re-wired. `draft_board_service.py`'s entry at `:134` describes it as read-only and injection-driven with no `database` import beyond the two lazy player/rookie-id reads — all still true; the fix adds no fetcher, no import, and no new data flow. |
| `living-memory/HLD.md` | **no — n/a because** no architecture shift: no new module, no new client, no new major flow. |
| `docs/cross-client-invariants.md` | **no — n/a because** `Team <franchise_id>`, `Player <mfl_player_id>` and `No selection` are **single-producer, server-side** display strings emitted by one function and never re-derived by any client — the same class as the shipped `Team <fid>`, which has no entry today. Invariants govern values that exist in *multiple* clients (tier colours, K-factors, enum strings). The enums this change touches — position codes, `order_confidence`, `notice.code` — are all unchanged. |
| `docs/glossary.md` | **no — n/a because** no new domain term. *Optional one-clause tightening the orchestrator may take:* the existing **Synthetic member id** entry (`:224`) ends "must never reach push/notification paths" — this bug is proof it must also never reach user-visible UI. Suggested: "…must never reach push/notification paths **or user-visible UI** (feedback #289 — the MFL Draft Room rendered `mfl:62846.f0001` as a team name)." |
| ADR / `DECISIONS.md` | **no ADR — n/a because** no architectural choice; the fix copies a shipped in-repo pattern (`_sync_mfl_owned_picks`, `server.py:9201-9207`). **One `DECISIONS.md` entry is warranted** (orchestrator-owned, next id = max+1): the four-tier player-name resolution (sentinel → our `players` row → DP crosswalk → `Player <mfl_id>`) and the crosswalked-id keying guard behind it — a deliberate, non-obvious choice to never emit a bare id, taken against the Planner's recommendation. Proposed text below. |

### Proposed `docs/api-reference.md` delta (orchestrator applies)

In the `GET /api/draft/board` row (`:414`), inside the **Platforms** sentence
for MFL — after "…an expired MFL cookie serves the stored snapshot with
`notice.mfl_reconnect` + `stale:true`, **never stale-as-live**." — insert:

> **MFL identity is resolved server-side, never left as an id (#289).**
> `order[].owner_username` comes from the stored `league_members` row for the
> franchise's user id (`username` → `display_name`), falling back to
> `Team <franchise_id>`; it is **never** the synthetic `mfl:<league>.f<fid>`
> member id, and is `null` only when the grid states no franchise for the slot.
> `picks[].name`/`position`/`team` resolve in a fixed order: MFL's all-zeros
> slot sentinel (`player: "0000"`) renders `No selection`; otherwise our own
> `players` row **looked up by the pick's crosswalked id** (the only tier that
> carries `team`), then the DynastyProcess crosswalk's own name/position for the
> raw MFL id, then the placeholder `Player <mfl_player_id>`. `picks[].name`
> therefore **always contains at least one letter** on an MFL board — never
> empty, never a bare id. `player_id` is unchanged and still carries the raw MFL
> id when the crosswalk misses; note that an uncrosswalked MFL id may coincide
> with an unrelated Sleeper id, so it is never used as a `players` lookup key.
> `original_user_id`/`original_username` remain `null` for MFL — the grid states
> current ownership only.

### Proposed `living-memory/DECISIONS.md` entry (orchestrator applies, next id)

> **MFL Draft Room player names resolve in four ordered tiers, and never render
> a bare id.** (2026-08-10, feedback #289.) `_render_mfl` renders MFL's
> all-zeros slot sentinel (`player: "0000"`) as `No selection`; otherwise it
> hydrates `picks[]` from our `players` table for crosswalked ids, falls back to
> the DP crosswalk's own `by_mfl_id` name/position map for ids that never
> crosswalked, and finally to the placeholder `Player <mfl_id>`. The planner
> recommended stopping at tier 1 and leaving `name: ""` on a miss, accepting
> that the client's `pick.name || pick.player_id` fallback would show a raw
> number. Rejected: rookies are the crosswalk's weakest segment and a rookie
> draft is exactly where they appear, so that variant would have left the
> reported defect live on the most likely rows. Tier 2 costs nothing —
> `by_mfl_id` rides on the same `_shared_crosswalk()` object the binding already
> fetches, and it is a superset of `by_mfl_sleeper` in practice (measured on the
> committed snapshot: 3563 vs 2828 ids, 735 reachable only via tier 2, zero
> counterexamples), because `_parse_crosswalk_rows` inserts it *before* the
> `sleeper_id` guard. Precedence is total, so the two name sources can never
> disagree on a rendered row.
>
> **The load-bearing guard is the keying, not the query list.** MFL and Sleeper
> player ids are numeric strings from different epochs that overlap densely in
> the rookie band — 255 MFL ids in the committed snapshot alone are also a
> *different* player's Sleeper id (`13674` = Dallas Goedert as MFL, Chris Hilton
> Jr. as Sleeper). A pick may take tier 1 only if its own MFL id crosswalked,
> and its row must be read by **that pick's crosswalked id**, never by
> `pick["player_id"]` — which still holds the raw MFL id on a miss. Consuming
> `load_players_by_ids`' `{player_id: row}` result with `pick["player_id"]`
> renders one pick's player on another pick, inside a query that is itself
> entirely legal. Guarded by test `T-289-06`.

### Also at ship (orchestrator-owned, motion docs)

`living-memory/CHANGELOG.md` (dated H2) and `living-memory/TEST_LEDGER.md`
(suite result, the Tier 3 sim run, and the live-league crosswalk coverage
count from `prd.md` §9).

## 5. Ship gate declaration

- **Simulator-gate tier: 3.** Matrix read (`docs/runbook.md` § Pre-ship
  simulator gate, tier table at `:93-98`): row 3 is "Backend route/schema
  consumed by mobile → smoke subset that exercises the route", which is exactly
  this change — `GET /api/draft/board`'s payload values change and the mobile
  Draft Room renders them directly. Tier 4 ("Backend-only, web-only, docs-only →
  no sim run") is the tempting reading because no `mobile/src` file changes and
  `githooks/pre-push` therefore would not block, but Tier 4 is for backend work
  mobile does not consume; taking it here would mean shipping a
  mobile-user-visible change with zero device verification. **Tier 3 confirmed —
  the Planner's reading is correct.**
  Flows to run: `mobile/.maestro/flows/rookie/d1-draft-room-complete.yaml` and
  `mobile/.maestro/flows/rookie/d2-draft-room-order-not-set.yaml`.
- **Evidence:** `living-memory/TEST_LEDGER.md` entry (flows, pass/fail, sim
  device, SHA) **plus** `qa/sim-runs/last-sim-run.json`
  (`{"tier": 3, "flows": ["rookie/d1", "rookie/d2"], …}`), **plus** — specific to
  this item — the live-league run on Dependables 62846: screenshots in this
  folder and the crosswalk coverage counts recorded in `status.md` and the
  ledger entry.
- **Operator deviation from the matrix:** none proposed. Two operator decisions
  are already recorded above and need confirming sign-off:
  1. §3 Maestro waiver — no authored flow; live-league QA on 62846 substitutes.
     *(Operator already ruled; recorded here for the audit trail.)*
  2. §1 analytics waiver — no new events.

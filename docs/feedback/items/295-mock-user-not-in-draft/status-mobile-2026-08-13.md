# Status — mobile build agent, 2026-08-13 (#295/#296/#305)

> Phase 5, mobile lane. Base `origin/main` @ `3b64a44`, branch
> `mock-draft-fix`. Contract: [`prd-2026-08-13.md`](prd-2026-08-13.md) +
> [`lld-2026-08-13.md`](lld-2026-08-13.md). Backend commits visible at
> start: `6f0d44e` (analytics registration); `5cbff26` (engine + routes)
> landed mid-build — my commits stage only my own paths.

## Commits (this lane)

| SHA | What |
|---|---|
| `e31309a` | mobile: modes + user_not_in_draft surfaces — the four `src` files |
| `fffcf08` | mobile tests: the two structural suites + `package.json` registration |
| `712ad2e` | maestro: d3 retarget + new d4 + `draft-pre.json` pin + lint allow-list |

## Changes at file:line

### `mobile/src/api/mockDraft.ts`
- `:37` `MockDraftMode = 'cpu' | 'manual'` (closed enum, per invariants doc)
- `:45` `MockEmptyReason` gains `'user_not_in_draft'`; `(string & {})` kept
- `:98`/`:104` `MockSettingsEcho.mode` + `.user_owner_id` (nullable in type only)
- `:110-119` `MockCapability` — the frozen §5.6 shape; `:144`
  `MockDraftEmpty.capability?` (GET-only ride-along)
- `:182`/`:193` `createMockDraft` `mode?` param, conditional body spread
  `...(params.mode ? { mode: params.mode } : {})` — 1.12.x wire-identical

### `mobile/src/components/draft/MockSetupSheet.tsx`
- `:53` `MockSetupResult.mode`; `:84-88` state, `'cpu'` default (Q2);
  `:93` re-seed to `'cpu'` in the visibility effect
- `:171-198` "You pick for" field: `TypeSeg` verbatim,
  `mock-setup.mode.cpu` ("Your team") / `mock-setup.mode.manual`
  ("Every team"), both `disabled={busy}`; mode-branched `fieldHint`
  (PRD §4.1 strings, curly apostrophes)
- `:224` `onStart({ rounds, type: draftType, mode })`; `:227-238`
  mode-branched footNote (cpu sentence byte-unchanged)

### `mobile/src/screens/DraftRoomScreen.tsx`
- `:282-285` `probeReason` from a `no_active_mock` empty's
  `capability.reason` (R9 — entry card disables pre-POST)
- `:293` create passes `mode: setup.mode`
- `:296-331` emitters in `createMock.onSuccess`: `mock_create_refused`
  (`:305`, empty branch) and `mock_started` (`:315`, before `navigate`,
  all five props off `res.settings_echo`); league platform via the
  `InLeagueCalculator` convention verbatim
- `:355-370` seventh `mockBlock` arm `mock-entry.blocked.user_not_in_draft`,
  after `class_not_loaded` (server-answer group), keyed
  `postRefusal === … || probeReason === …`; PRD §4.5 strings byte-exact
  (straight apostrophes); `:405` `probeReason` joins the memo deps
- `:656-661` the stale "No track() here on purpose" comment updated
  (`draft_room_mode_switched` itself stays unfired — still unregistered)

### `mobile/src/screens/MockDraftScreen.tsx`
- `:36-44` header analytics block updated (family now registered)
- `:151` `forOwnTeam` — `!onClock?.roster_id || !userOwnerId ||
  String(onClock.roster_id) === userOwnerId`; never reads `by`
- `:170-186` `pickedSlotRef` captured in `pickMutation.onMutate`
  (round/pick_no/roster_id/prevStatus of the PRE-mutation clock)
- `:205` `mock_pick_made` (captured slot, `for_own_team` vs
  `settings_echo.user_owner_id`); `:226` `mock_completed` gated on
  `prevStatus === 'active' && status === 'complete'`,
  `user_picks: ns.my_picks.length`; `:282` `mock_abandoned` inside the
  Alert's destructive `onPress`, BEFORE the abandon promise
- `:395-405` `ownerNames` map (one `ownerNameOf` D-16-ladder call) —
  `clockName` now reads it; shared with the ticker
- `:588-596` confirm-bar meta: `your pick` / `` {clockName}’s pick `` /
  bare `pick` (PRD §4.3, curly `’s`)
- `:669-717` `OnTheClockCard` gains `forOwnTeam`: headline
  `You’re picking for {name}` (fallback `…for this team`), chalk when not
  the own turn (approved frame); sub-line `mock-draft.clock.picking-for`
  = "You chose to pick for every team in this mock."; `Tap a rookie
  below, then confirm.` renders in both user-turn variants, unchanged
- `:751-773` `PickTicker` gains `nameOf` (the ticker fix — below)
- `:894-909` `resolveUserOwnerId` echo-first; shipped inference kept as
  the old-server fallback; empty-string echo falls through
- `:951` `emptyCopy` arm — PRD §4.4 string, before `default:`, ≠ default

### Tests, flows, fixture
- `mobile/tests/check-mock-user-not-in-draft.js` (new, T-295-10, 18 asserts)
- `mobile/tests/check-mock-draft-modes.js` (new, 78 asserts); both in
  `package.json` as `test:mock-user-not-in-draft` / `test:mock-draft-modes`
- `mobile/.maestro/flows/rookie/d3-mock-draft-loop.yaml` — retargeted to
  `qa_draft`/`990000000000000001` (dead ffv3 PRECONDITION deleted —
  repaired, not worked around), law-10 typed-username retry preamble,
  RUN-9 three-variant entry normalisation, and the #295 acceptance:
  `.*You’re on the clock.*` (curly source byte) before any row tap, both laps
- `mobile/.maestro/flows/rookie/d4-mock-manual-mode.yaml` (new, tc
  T-305-M2) — manual toggle → `mock-draft.clock.picking-for` at pick 1 →
  one confirmed pick → `.*pick 2 of 12.*` + `picking-for` again →
  End-mock teardown (multi-line Alert text exemption) → `mock-entry.start`
- `backend/tests/fixtures/profiles/draft-pre.json` — **pin**:
  `traded_picks` 6 → 0 (+ description). See "Seeded-world requirements".
- `mobile/scripts/testid-lint-allow.txt` — `mock-draft.empty.*`
  (template-generated id, law 4)

## The ticker fix — exact shape (mockup finding 1)

Shipped who-column: `mine ? 'You' : p.by === 'cpu' ? 'CPU' : '—'` — in
manual mode every pick is `by: "user"`, so every non-own row rendered "—".
Fix (`MockDraftScreen.tsx:764-770`): `PickTicker` takes an optional
`nameOf: Map<string, string>` and the third arm becomes
`(p.picked_by_user_id != null ? nameOf?.get(String(p.picked_by_user_id)) :
undefined) ?? '—'`. "You" still keys on `picked_by_user_id ===
userOwnerId` (never `by`); "CPU" unchanged; "—" survives only for an
unnameable owner. The map is the new screen-level `ownerNames` memo —
built through the same `ownerNameOf` D-16 ladder the recap uses.
**Shape driver:** `check-mock-lifecycle.js` pins *exactly two*
`ownerNameOf` call sites; `clockName` now reads the shared map (call 1 =
the memo, call 2 = the recap's own), so the pin holds without weakening it.

## Suite baselines vs finals (actual runs, this worktree)

Baseline measured before my first edit; final after all commits.

| Suite | Baseline | Final |
|---|---|---|
| `npx tsc --noEmit` | exit 0 | exit 0 |
| `bash mobile/scripts/testid-lint.sh` | OK (exit 0) | OK (exit 0) |
| `check-league-drill-in.js` | 29 PASS / 0 FAIL | 29 / 0 |
| `check-analytics-297-302.js` | 35 / 0 | 35 / 0 |
| `check-single-pin-actions.js` | 17 / 0 | 17 / 0 |
| `check-league-candidates-300.js` | 67 / 0 | 67 / 0 |
| `check-picks-subset-invariance.js` | 72 / 0 | 72 / 0 |
| `check-analytics-300.js` | 51 / 0 | 51 / 0 |
| `check-mock-lifecycle.js` | 52 / 0 | 52 / 0 |
| `check-mock-mode-marker.js` | 28 / 0 | 28 / 0 |
| `check-mock-draft-modes.js` (new) | n/a (red pre-build: 27 FAIL, exit 1) | 78 / 0 |
| `check-mock-user-not-in-draft.js` (new) | n/a (red pre-build: 8 FAIL, exit 1) | 18 / 0 |

`npm run test:mock-lifecycle` run by hand → "All mock affordance +
lifecycle checks passed." No pre-existing count moved.

## Sabotage matrix (15 named, each RED then restored green)

Both new suites were first proven red on the pre-build tree (files
reverted to `5cbff26`'s mobile state): 8 and 27 FAILs respectively. Then,
per-assertion — each sabotage byte-verified as applied before the run:

| # | Sabotage (one targeted revert) | Suite | Red assertion hit |
|---|---|---|---|
| S1 | remove the `emptyCopy` arm (T-295-10's named sabotage) | user-not-in-draft | "not the default string" (called, answered the default) |
| S2 | blocked arm keyed on `postRefusal` only | user-not-in-draft | "keyed on probeReason too" |
| S3 | `MockEmptyReason` loses the member | user-not-in-draft | union literals enumerated without it |
| S4 | `resolveUserOwnerId` echo-read removed | modes | behavioural: answered '3' (the on-clock team) not '8' |
| S5 | ticker who-column reverted to shipped ternary | modes | behavioural: manual non-own pick rendered "—" |
| S6 | setup-sheet re-seed removed | modes | "re-seeds mode to 'cpu'" |
| S7 | `mock_completed.user_picks` → `ns.picks.length` | modes | "counts my_picks" |
| S8 | emitter renamed to unregistered `mock_pick` | modes | "track('mock_pick_made') is fired" |
| S9 | `mock_started.teams` read from `board` | modes | "settings_echo (all five)" + "never reads … the board" |
| S10 | `mock_pick_made.round` from response `on_the_clock` | modes | "never reads the response's on_the_clock" |
| S11 | picking-for gate flipped to `isUser && forOwnTeam` | modes | "only when isUser && !forOwnTeam" |
| S12 | `mock_abandoned` gains extra prop `basis` | modes | frozenset equality (client `[basis,…]` vs taxonomy) |
| S13 | `mock_completed` transition guard dropped | modes | "gated on the active → complete transition" |
| S14 | `mode` body spread made unconditional | modes | "spreads `mode` conditionally" |
| S15 | sheet default flipped to `'manual'` | modes | "defaults to 'cpu' (Q2)" |

Standing-trap defences in the suites themselves: all TSX facts are AST
(comments cannot satisfy a literal); `emptyCopy`, `resolveUserOwnerId`
and the who-column are transpiled and CALLED; Python facts are read with
`#` comments stripped (the taxonomy's own comments name these events);
the sabotage runner diffs bytes against a backup so a silently-unapplied
sabotage is reported, not counted.

## Seeded-world requirements (LLD §8.3) — verified / pinned

1. **Untraded round-1 slot for `qa_draft`: PINNED, and it was genuinely
   violated.** The seeder's traded formula (`orig_rid = i % teams + 1`,
   `round = i % rounds + 1`, `seed_ui_test_db.py:934-946`) trades roster
   1's round-1 pick away at `i = 0` — and roster 1 IS `qa_draft`
   (`member_order` index 0). With the old `traded_picks: 6` the user
   owned **zero** round-1 slots and a 1-round mock completed at create —
   d3's clock assertion could never pass. Only `traded_picks: 0` avoids
   it (any nonzero count hits `i = 0`); the profile schema has no
   per-pick exclusion knob and the seeder is outside this lane's
   ownership. Traded-pick coverage stays in the pytest corpora (lakeview).
2. **Slot off 1–2: VERIFIED generator-guaranteed, no pin needed.**
   `uid_by_slot = member_order[(s - 1 + 5) % teams]` with the app user
   first ⇒ `qa_draft` at slot 8 for 12 teams (mid-order, mirrors the live
   ffv3 operator position). Documented in the profile description.

## Out of scope, report-only

- **`MOCK_MIN_TEAMS = 6` (client) vs server floor 4** — pre-existing
  mismatch in `MockEntryPanel.tsx:41`; its own comment says to delete the
  constant once a server-side `league_too_small` refusal exists — which
  the shipped ladder now has. A 4–5-team league is client-blocked before
  the server would allow it. Not fixed here per the brief; candidate
  follow-up: delete the constant + the client-derived arm and lean on
  `probeReason`/`postRefusal`.
- **Recap "4 picks" surprise** (user drafts 48, "Your draft" shows 4):
  PRD deliberately added no disclosure. I concur — the recap's round rail
  names every team (user's rows tinted), and `mock_completed.user_picks`
  records the team-count for measurement; no copy added.
- **No simulator, no Maestro runs** — flows are authored and lint-clean;
  on-sim M-1/M-2 + the Q3 sim-gate tier are the batch QA round's.

## PRD notes / divergences (report, not improvisation)

1. **Brief vs PRD suite filename.** The build brief named the new suite
   `check-mock-draft-modes.js`; PRD T-295-10 names
   `check-mock-user-not-in-draft.js`. Shipped BOTH: T-295-10 lives in its
   PRD-named file; the modes/analytics/ticker coverage in the brief-named
   file. Both registered and sabotage-proven.
2. **LLD §1.6 placeholder label "Drafting mode"** superseded by PRD §4.1
   "You pick for" — PRD is final copy; PRD used.
3. **LLD §8.3 called the profile pin "additive"** — the only available
   knob made it a modification (`traded_picks` 6 → 0, rationale above).
4. **On-behalf headline color**: PRD is silent; the approved
   `manual-picking-for` frame draws it chalk (flare reserved for the own
   turn) — implemented as drawn.
5. No other PRD gaps found; §4 strings landed byte-exact per file
   apostrophe convention (curly in MockSetupSheet/MockDraftScreen,
   straight in DraftRoomScreen).

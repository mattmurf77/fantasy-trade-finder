# QA results — rookie-draft V1 (M0–M4)

**Date:** 2026-08-06 · **Base:** `origin/main` @ `34ac136`, QA'd from a clean detached worktree
**Rig:** hermetic UI-test harness (`seed_ui_test_db.py --profile standard`), flags injected via
`FTF_FLAGS`, Sleeper cassettes via `FTF_SLEEPER_FIXTURES_DIR`. Zero live egress
(`sleeper_live_egress_attempts: 0`, `vcr_misses: 0`).

## Baseline gates

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **1692 passed / 1 skipped** |
| `cd mobile && npx tsc --noEmit` | **clean (exit 0)** |

(The handoff's 1685 figure predates the analytics commit `9a22432`, which added tests.)

## Findings

### F-1 — the hermetic fixture world contained ZERO rookies (blocker, fixed)

`backend/tests/fixtures/player_pool_2026.json` was generated 2026-07-11 from the
**pre-NFL-draft** Apr-11 players cache. Its 56 `years_exp == 0` rows were therefore all
**teamless**, and THE rookie predicate (`draft_status.is_rookie_row` /
`database.load_rookie_player_ids`) deliberately requires a team — it is what drops the
teamless January prospect tail. Net effect: the seeded world had **no** rookies, so every
rookie surface in the Maestro matrix would have rendered the typed-empty state and the
M2 QA list could not have been run at all.

**Fix:** backfilled the real `team` + `metadata.rookie_year` for all 56 rows from the
post-draft Sleeper dump. The seeded world now carries **QB 8 / RB 16 / WR 20 / TE 12 = 56**
rookies — every format/position can field a 3-candidate rookie trio, including TE, the
thinnest. Full suite re-run green after the change.

This was a fixture defect, not a product defect, but it is the reason the rookie matrix had
never actually exercised a rookie.

### F-2 — `platform_unsupported` notice copy contradicted itself (fixed)

The server's `notice.message` for an MFL league read *"Draft rooms are available for Sleeper
and MyFantasyLeague."* — attached to an `unavailable` board, on a build where MFL is
deliberately **unbound until M5**. It promised the exact thing that had just failed.

Scope is limited: `DraftRoomScreen` overrides copy per notice code and renders the correct
"Draft rooms aren't available for this platform yet.", so **no mobile user would have seen
it**. The wrong string is the API payload fallback every other consumer reads.

**Fix:** server fallback now states what is *not* available, matching the client and staying
true after M5 lands. `backend/draft_board_service.py:104`.

### F-3 — `sim-build.sh` fails from a clean `npm ci` (environment; local workaround applied)

The UI-test build path dies in the "Bundle React Native code and images" phase:

```
Error: Cannot find module 'metro-runtime/package.json'
  at withMetroMultiPlatformAsync (…/expo/node_modules/@expo/cli/…/withMetroMultiPlatform.ts:935)
```

`metro-runtime` appears in `package-lock.json` only as **nested** installs
(`metro/node_modules/`, `react-native/node_modules/`, `@expo/metro/node_modules/`) and is
never hoisted to top level. Expo's CLI resolves it from
`mobile/node_modules/expo/node_modules/@expo/cli/…`, whose upward walk never enters
`metro/node_modules` — so it cannot be found. Confirmed **not** a worktree artifact: it is
absent from the main working copy's `node_modules` too, and a clean `npm ci` in a fresh
worktree reproduces it exactly.

**Local workaround (QA rig only):** `npm install metro-runtime@0.83.3 --no-save` —
deliberately unsaved so `package.json` and `package-lock.json` are untouched.

**Not fixed here, and it needs an owner.** The durable fix is a dependency decision (pin
`metro-runtime` as a direct devDependency, or align the Expo/RN metro versions so one copy
hoists) that changes the shipping dependency tree — out of scope for a QA pass and not
something to slip into a flag-flip commit. Until it lands, *any* clean checkout cannot
produce a simulator test build. EAS cloud builds resolve dependencies themselves and are
unaffected — build 71 and the build below both come from EAS.

## D-criteria verified

### D2 — scope is a post-Elo view filter (live, all four positions)

| Position | Full board | Rookie scope | Not in full board | **Elo mismatch** | Vet leak | Ranks 1..n |
|---|---|---|---|---|---|---|
| QB | 58 | 8 | 0 | **0** | 0 | ✅ |
| RB | 103 | 16 | 0 | **0** | 0 | ✅ |
| WR | 123 | 20 | 0 | **0** | 0 | ✅ |
| TE | 68 | 12 | 0 | **0** | 0 | ✅ |

Consolidated cross-position view (`GET /api/rankings?scope=rookie`, no position): 56 rows,
strictly Elo-descending, ranks 1..n, and **every** pid's Elo byte-equal to its value on the
position board — values synced by construction, not by a sync step.

### D3 — pre-scope snapshot + operator restore (the flag precondition)

Exercised end-to-end against a real board, not just unit tests:

1. Unscoped WR tier save → board B0 (24 overrides, 2 of them rookies). Snapshot correctly
   **not** taken (`load_tier_override_snapshot` → `None`).
2. Scoped WR save (`scope:rookie`, `via:rookie_tiers`) → snapshot written once,
   `v:1 / reason:pre_scope_v1`, and its `1qb_ppr` map **equals B0 exactly**.
3. **Merged-band rule holds:** 22 non-rookie overrides **byte-unchanged**; the 12 pids that
   had no override before and one after were **all** rookies.
4. Runbook restore (`restore_tier_overrides_from_snapshot`) → board **=== B0 exactly**;
   snapshot **survives** the restore; a second restore is idempotent.
5. Forensic trail lands: `user_events.tier_save` with `via` = `rookie_tiers` /
   `rookie_quickset` for scoped saves, `tiers` for the unscoped one.

**D3 passes — `ranks.rookie_subset` is cleared to flip on this criterion.**

### I-4 — a scoped save never marks a position complete

A scoped **TE** save (a position never saved before) returned `saved: ["WR"]`, `all_done:
false` — TE was **not** added. `#244` launch routing and LeagueScreen's ranked count are safe.

### O4 / #161 — demotion scoped to the visible subset

A scoped save submitting two **veterans** in `demoted_pids` alongside two visible rookies:
both veterans' overrides were **byte-unchanged** (the server ignored them); both rookies
demoted to `DEMOTED_ELO` 1100.0. The one path that could silently damage a board is closed.

### D4 / D10 — flag-off byte identity and no entry point

Two servers, same seed data, flag on vs off:

| Check | Result |
|---|---|
| `/api/rankings?position={QB,RB,WR,TE}` on vs off | **byte-identical** (4/4) |
| `/api/tier-config`, `/api/tiers/status` | **byte-identical** |
| `?scope=rookie` with the flag **off** | **byte-identical** to the unscoped response — the param is never read |
| `GET /api/draft/board` with `draft.room` off | **404 `feature_disabled`** |

### D5 — Draft Room states, driven by the operator's two real leagues

**Lakeview `1312076055586050048`** (complete): `state: complete`, `order_confidence:
assigned`, 48 order rows + 48 picks, traded-pick overlay correct (rows carry
`is_traded: true` with `original_username` ≠ `owner_username`), deep link present.

**FFv3 `1312140920132497408`** (pre-draft, `draft_order: null`, identity
`slot_to_roster_id` map): `order_confidence: **unset**`, notice `order_not_set`, and
**every** `slot` and `pick_no` is `null` across all 48 rows — round-level ownership only.
**The identity map is not read as an order.** The D5 trap is closed.

**Startup-shaped** (28 rounds, `pre_draft`): `kind: startup`, `undrafted_suppressed: true`,
0 undrafted rows, honest `startup_draft` notice, real order retained (336 rows).

**MFL** (unbound until M5): `state: unavailable`, notice `platform_unsupported` — **not**
`mfl_reconnect` (see F-2 for the copy fix).

Error paths: `bad_basis` → 400 · unknown league → 404 `league_not_found`.

*Fixture note:* `startup-shaped/` reuses `lakeview-complete/`'s league and draft IDs, so the
two corpora **cannot** share one `FTF_SLEEPER_FIXTURES_DIR`. Merging them silently
overwrites Lakeview. They were run from separate dirs.

## On-device QA (iOS 18.4 simulator, Maestro)

New flows in `mobile/.maestro/flows/rookie/`. All five **PASS**.

| Flow | Covers | Result |
|---|---|---|
| `r1-scope-tiers-and-consolidated` | QA notes 1/2/6 — scope control on Tiers, scoped board, consolidated view + position filters | **PASS** |
| `r2-quickset-and-trios-scoped` | QA notes 3/5 — Quick Set under scope, Trios under scope | **PASS** |
| `d1-draft-room-complete` | D5/D9 — Lakeview complete board, tile swap, basis toggle, deep-link CTA | **PASS** |
| `d2-draft-room-order-not-set` | D5 — FFv3 `order_not_set` notice + "Round ownership" | **PASS** |
| `r5-flag-off-no-entry` | D10 — no scope control, no rookie section, rookie-board tile restored, no Draft Room tile | **PASS** |

**Tile swap (O1) confirmed on device:** with `draft.room` on, `league.rookie-board-row` is
**absent** and `league.draft-room-row` present; with the flag off, exactly the reverse.

**No polling with `draft.live_poll` off:** `/api/draft/board` request counts track discrete
user actions (one per mount, one per basis switch) with no growth over dwell time.

*Two navigation facts the pre-existing smoke flows do not model* (worth adding to the
mobile-testing drift ledger): the Rank tab lands directly on **Quick Set**
(`ux.rank_tab_destination`), with the mode chooser behind `rank.more-ways` — `rankmenu.*`
is not reachable straight from `tab.rank`; and the League tab lands on **League rankings**,
with the Explore tiles behind `league-summary.league-home`. Draft Room scrolls need
`centerElement: true` + `speed: 30` to clear 48 pick rows reliably.

### F-4 — harness rails are not clean (pre-existing, NOT fixed)

Every run reports `vcr_misses: 2` (`sleeper_live_egress_attempts: 0`,
`completed_proposes: 0`). The misses are:

```
league/990000000000000001/drafts        → cassette not emitted
league/990000000000000001/traded_picks  → cassette not emitted
```

`seed_ui_test_db.py` emits no `drafts` or `traded_picks` path for its synthetic leagues,
while #207's draft-status detector fetches `/drafts` during league sync — so the standard
profile can never produce a clean rails audit. **Pre-existing and unrelated to this
feature** (it reproduces with all rookie flags OFF).

Critically, **every miss is on the seeded synthetic league** — never on the
`lakeview-complete` / `ffv3-predraft` corpora, which do carry both files. No rookie or
Draft Room assertion depended on a missed cassette.

**Deliberately not fixed here.** Emitting `drafts: []` would change what #207's detector
concludes for the QA league, which could shift seeded draft-status behaviour under the ten
existing smoke flows — not something to change inside a flag-flip ship. It needs its own
batch.

## Flags flipped

| Flag | New state | Evidence |
|---|---|---|
| `ranks.rookie_subset` | **ON** | D2 (Elo identity, 4/4 positions) · D3 (snapshot + exact restore, the stated precondition) · D4 (byte identity) · I-4 · O4 · flows R1/R2/R5 |
| `draft.room` | **ON** | D5 on both operator leagues + startup + unsupported · D7 unit-covered · D9 (no write path; deep-link CTA) · D10 (404 + tile restore, verified on device) · flows D1/D2/R5 |
| `draft.live_poll` | **stays OFF** | Release gate T-M4-06 (throwaway Sleeper league with a started draft) not run — operator-supplied precondition |

Both flipped in `config/features.json` **and** `backend/tests/fixtures/flags/release.json`
(the mirror is test-enforced). Full suite + `tsc` re-run green with the flags on.

### Still open for the operator

1. **T-M4-06** — the throwaway-league live test. `draft.live_poll` stays off until it passes;
   the hard threshold is **zero** requests when blurred/backgrounded, verified by
   instrumentation, never by reading the code.
2. **Fan-in restatement (plan O8).** The ≤3 req/min/draft ceiling is **per process**. The
   Render upgrade that makes live polling viable also allows multiple workers, at which
   point the real ceiling is `3 × worker_count` per draft and the runbook number needs
   restating. Do this before `draft.live_poll` goes on, not after.
3. **F-3** — `metro-runtime` resolution; no clean checkout can build the simulator test app.
4. **F-4** — the seeder's missing draft cassettes.

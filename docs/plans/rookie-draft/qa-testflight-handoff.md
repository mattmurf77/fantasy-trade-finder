# Handoff prompt — Rookie-draft V1 QA + TestFlight pass

Copy everything below into a fresh session.

---

You are running the QA + TestFlight pass for the rookie-draft V1 feature set in the Fantasy Trade Finder repo (`/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder`). All code is already built, merged, and green on `origin/main` (through commit `cee4324`, 2026-08-06; backend suite 1685 passed / 1 skipped; tsc clean). Nothing is user-visible yet — every feature flag landed OFF. Your job: QA it, flip flags where preconditions are met, cut a TestFlight build, and report.

**Read first, in order:**
1. `docs/plans/rookie-draft/plan.md` — the converged plan; §1's D-criteria table is the acceptance contract; the "Operator decisions" section at the bottom binds everything.
2. `docs/plans/rookie-draft/build-m2-mobile.md` — has the 7-item Maestro QA list for the rookie-scope surfaces.
3. `docs/plans/rookie-draft/build-m4.md` — Draft Room states + the explicitly-deferred tests T-M4-01..06 (T-M4-06 = the live-poll release gate).
4. `docs/plans/rookie-draft/measurement.md`, `hld.md`/`lld.md` as reference.
5. Repo conventions: root `CLAUDE.md` (esp. secrets in `secrets.local.env`, feedback pipeline, Chalkline rules) and `.claude/skills/maestro-test` if present.

**What shipped (all dark):**
- `ranks.rookie_subset` — rookie scope control on all six ranking modes + a consolidated cross-position rookie view (`RookieRanksScreen`, route `app/rank/rookies`). Same Elo space; scope is a view filter.
- `draft.room` — `GET /api/draft/board` + `DraftRoomScreen` (root stack, League-page tile swaps to "Rookie draft" only when on). Sleeper only; MFL intentionally unbound until M5.
- `draft.live_poll` — focus-gated 15s polling; OFF pending the live-draft release gate.
- Foundation (unflagged, already live): daily player-cache refresh, pool generation counter, pinned rookie predicate, draft fixture/replay harness in `backend/tests/fixtures/draft/`.

**QA tasks:**
1. Full backend suite + tsc as a baseline sanity check.
2. Flag-on QA locally (flip flags in `config/features.json` + `backend/tests/fixtures/flags/release.json` — the mirror is test-enforced) or via the tester-allowlist experiment overlay for device QA. Run the build-m2-mobile 7-item list on simulator; exercise every DraftRoomScreen state (the replay fixtures + the operator's two real leagues: Lakeview `1312076055586050048` = drafted/recap, FFv3 `1312140920132497408` = pre-draft with `draft_order:null` — must show "order not set", never an invented order).
3. Verify flag-off byte-identity and no-entry-point (D4/D10) on device.
4. **Precondition check before flipping `ranks.rookie_subset` for real users:** the pre-scope board snapshot (`__pre_rookie_scope__` sibling key) must be verified working — D3 in the plan. Test the operator restore path once.
5. **Do NOT flip `draft.live_poll`** unless the operator has created the throwaway Sleeper league with a started draft and the live test passes (T-M4-06; zero requests when backgrounded is a hard threshold).
6. Fix what QA finds (small fixes inline; bigger ones via worktree agents per repo convention), re-gate.

**Ship pipeline (established):** merge/commit → `python3 -m pytest backend/tests -q` green → `cd mobile && npx tsc --noEmit` → push `origin HEAD:main` (Render auto-deploys backend) → `npx eas-cli build --platform ios --profile production --non-interactive --no-wait` → poll `eas-cli build:view <id> 2>&1 | grep -iE "^Status"` in a background loop → `eas-cli submit --platform ios --id <id> --non-interactive`. Current version 1.11.0, last build 71. Flags are server-delivered, so flag flips post-build reach the app instantly — the build only needs to carry the new screens.

**Warnings:**
- The local `teardown-remediation` branch LAGS `origin/main` and the working tree may hold another session's uncommitted analytics WIP (`backend/server.py`, `database.py`, others). NEVER commit/stash/discard foreign WIP. If blocked, work from a clean worktree of `origin/main` and push from there (established pattern this feature has used throughout).
- Multiple sessions share this repo — re-check `git status` before any merge.
- `mobile/src/screens/CLAUDE.md` etc. registry files conflict on multi-agent merges; resolve by union-dedupe of table lines.
- Flag flips that reprice or expose surfaces ship only after their D-criteria pass; when in doubt, leave a flag off and report.

**Report at the end:** QA findings + fixes, which flags flipped (with precondition evidence), build number submitted, and what remains gated (expected: `draft.live_poll` on the throwaway-league test; M5 MFL + M6 slot values are separate upcoming build waves — do not attempt them).

# Handoff — Fantasy Trade Finder

> **Purpose:** forward-looking session handoff. Where am I right now, what's half-done, what's next, what's blocking. Like a doctor's shift handoff sheet — different from CHANGELOG (which is backward-looking).
>
> **Read at:** session start. **Write at:** session end (or before stopping for the day).
>
> Companion files: [`CHANGELOG.md`](CHANGELOG.md), [`NEXT.md`](NEXT.md).

---

## Table of Contents
- [2026-06-16 — Current State (Tiers reorder shipped)](#2026-06-16--current-state-tiers-reorder-shipped)
- [Handoff Template (for future sessions)](#handoff-template-for-future-sessions)

---

## 2026-06-16 — Current State (Tiers reorder shipped)

### Where I am right now
- **Tiers reordering rebuilt + shipped to TestFlight as build (16)** (v1.0.0;
  `autoIncrement` bumped past 12 → 16). Carries both Tiers PRs below. Apple was
  processing at handoff time.
- **PR #84** (`fix/tiers-rework` → main `999d6c4`): Tiers drag rebuilt on the
  STANDARD `react-native-draggable-flatlist` engine (same as ManualRanksScreen)
  — single `DraggableFlatList` with tier-header rows as non-draggable items;
  real-time slide-to-make-room, within- AND cross-tier drag. Replaced the old
  custom-Reanimated gap-shift engine (which the user rejected as "too custom").
- **PR #85** (`fix/tiers-multiselect` → main `ba647de`): `bulkMove` fix so the
  multi-select ↑/↓ arrows no longer shove NON-selected players across tiers
  (was re-bucketing by fixed tier sizes; now non-selected keep their tier, only
  the selected block changes tier when it crosses a boundary). Verified with a
  6-case deterministic logic test.
- Both PRs touched only `mobile/src/screens/TiersScreen.tsx`. Verified: drag
  on-device (iPhone 17 Pro sim), multi-select via logic test. tsc clean.

### What's half-done / NEXT person should do FIRST
- **Branch/uncommitted-work audit** (user asked; interrupted by an API outage).
  Run: `git fetch origin --prune` · `gh pr list --state open` (was EMPTY) ·
  `git worktree list` · `git status` (current branch `trade-engine-v2` has many
  modified/untracked files from prior sessions) · `git branch -vv` ·
  `git branch -r --no-merged origin/main`. For squash-merged branches compare
  CONTENT (`git diff origin/main <branch> -- <files>`) not hashes — squash
  orphans the source commits. Confirm `fix/tiers-rework` + `fix/tiers-multiselect`
  are fully represented on main (they are, via #84/#85) and safe to delete.

### Open follow-ups (not started; user's call)
1. **Background-refetch UX bug** in `TiersScreen.tsx`: `loading = isLoading ||
   isFetching` swaps the whole list for a full-screen spinner on ANY background
   refetch; and the auto-bucket `useEffect` rebuilds `buckets` from server data
   on refetch → WIPES unsaved drags if the app refocuses mid-edit
   (refetchOnWindowFocus). Fix: drop `isFetching` from the full-screen `loading`
   gate + guard the auto-bucket effect against clobbering unsaved local changes.
2. **Rotate `CRON_SECRET`** (guards `/api/feedback/admin` + `/api/cron/*`; in
   gitignored `secrets.local.env` at root, also set in Render). Launch-blocking.
3. Minor: an Overall Ranks drag TEST left ~1pt ELO drift on real ranks (order
   restored, self-corrects) — no action unless asked.

### Key learning worth keeping
- **`PlayerCard` (`mobile/src/components/PlayerCard.tsx`) renders its OWN inner
  `<Pressable>`.** Any screen wrapping PlayerCard in an outer Pressable/gesture
  MUST wrap it in `<View pointerEvents="none">`, or the inner Pressable becomes
  the touch responder and SWALLOWS the gesture. This silently killed both the
  multi-select tap and the drag long-press on Tiers. ManualRanks works because
  it builds its row inline (no nested Pressable).
- Synthetic-mouse drag DOES work in the iOS sim with draggable-flatlist — proved
  Tiers was buggy (not the library) by A/B-testing the same drag on Overall
  Ranks. Use that A/B technique to localize "is it my code or the library/sim?"

### Active environment state
- `origin/main` HEAD includes #84 + #85 (Tiers). Current local branch is
  `trade-engine-v2` (NOT a `fix/*` branch). Local `main` diverged / worktree-
  owned — base new work on `origin/main`, merge PRs server-side via `gh pr merge`.
- Mobile typecheck: `cd mobile && npx tsc --noEmit` → clean. Backend:
  `python3 -m pytest backend/tests/ -q` → 55 passing.
- **Spaces in repo path break local `expo run:ios`.** For a local iOS sim build
  use the no-space clone at `/Users/teresadickens/Documents/Claude/Projects/ftf-test-clone`.
  Sim build installed on UDID `1574B9D9-DAD8-44DC-A988-41D50C19DC16` (iOS 26.4).
- **Metro from clone:** start with stdin held open or it exits on EOF —
  `cd ftf-test-clone/mobile && (sleep 100000 | npx expo start --port 8081 &)`.
  `simctl launch` cold-starts the dev client WITHOUT Metro's URL ("No script
  URL"); attach with `xcrun simctl openurl <UDID>
  "com.fantasytradefinder.app://expo-development-client/?url=http://localhost:8081"`.
  Sync clone: `git -C ftf-test-clone fetch origin <branch> && git -C
  ftf-test-clone reset --hard FETCH_HEAD`. Fast Refresh unreliable — full reload
  via dev menu (Cmd+D → Reload) is the dependable way to load new code.
- **TestFlight/EAS:** profile `production` in `mobile/eas.json` (`autoIncrement`
  true). Build+submit in one shot: `cd mobile && npx eas-cli build --platform
  ios --profile production --auto-submit --non-interactive`. ascAppId 6771488431,
  appleTeamId N5Y4N2Q49A. Logged in as `mattmurf77`.
- **In-app feedback:** prod `https://fantasy-trade-finder.onrender.com`; table
  `app_feedback`; read via `GET /api/feedback/admin?since_id=N&limit=M` with
  header `X-Cron-Secret: <CRON_SECRET>` (from `secrets.local.env`). Local DB does
  NOT have it (app posts to prod); returns 401 without the secret.

---

## Handoff Template (for future sessions)

```markdown
## YYYY-MM-DD — Current State

### Where I am right now
- <one or two-bullet snapshot of project state>

### What's half-done
- <each in-flight item, with where the next person picks up>

### What I was about to do next
1. <ordered list, top is highest priority>

### What's blocking me
- <open questions / external waits / decisions pending>

### Active environment state
- <git status, data freshness, env vars, anything that affects "can I just run things">
```

Overwrite each day; do not let this file accumulate. (The history lives in [`CHANGELOG.md`](CHANGELOG.md).)

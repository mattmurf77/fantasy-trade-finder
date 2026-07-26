# #188 — Feedback button on all new pages + standing CLAUDE.md rule

**Status:** Built (this worktree, branch `teardown-remediation`). Backend untouched.

**Operator ask:** "Newly created pages are missing the feedback button. Change
that and write a rule into claude.md to ensure that all new pages have the
button added by default when creating the page."

## Root cause

`FeedbackFAB` is mounted exactly once, inside RootNav's **Main** screen — it
floats over every TAB screen (Rank stack incl. Trends, Trades, Matches,
League stack incl. the LeagueRankings tab root). But root-stack screens pushed
**over** Main (FreeAgents, LeagueSummary's push variant, Profile, TestStages…)
render as cards above that mount, covering the FAB. Every "new page" added as
a root-stack push therefore shipped without the button.

## What changed

1. **Mount pattern** (`mobile/src/components/FeedbackFAB.tsx` — mount-pattern
   only): new optional prop `aboveTabBar` (default `true`, byte-identical for
   existing mounts). `aboveTabBar={false}` drops the bottom offset from
   tab-bar height (+64) to +16 for screens with no tab bar underneath.
   Header comment now documents the multi-mount pattern (RootNav mount for
   tabs; root-stack pushes carry their own; multiple mounts safe — `hydrate()`
   idempotent, only the topmost card's FAB is visible).

2. **Screens fixed (owned this round):**
   - `mobile/src/screens/FreeAgentsScreen.tsx` — mounts
     `<FeedbackFAB activeScreen="FreeAgents" aboveTabBar={false} />`.
   - `mobile/src/screens/LeagueSummaryScreen.tsx` — mounts it **only when
     `!isTabRoot`** (the root-stack `LeagueSummary` push variant). The tab-root
     `LeagueRankings` instance is already covered by the RootNav mount — an
     unconditional mount would double the FAB on the League tab.
   - `TrendsScreen` — no change needed: it lives in the Rank tab stack, already
     covered by the RootNav mount (verified).
   - `SettingsScreen` — deliberately skipped: it is a modal presentation, which
     the new rule lists as an exception (modal chrome + the FAB's absolute
     positioning fight; Settings already links to the feedback inbox).

3. **Standing rule** (root `CLAUDE.md`, Conventions):
   > **Feedback button on every screen (#188):** every new user-facing mobile
   > screen mounts `FeedbackFAB` by default — tab-stack screens are covered by
   > the RootNav mount; root-stack pushes render their own
   > `<FeedbackFAB activeScreen="<RouteName>" aboveTabBar={false} />`.
   > Exceptions: modals/sheets and onboarding flows.

## Still missing (not touchable this round — follow-ups)

- `ProfileScreen` (root-stack push, user-facing) — needs the same one-line
  mount.
- `TradeFinderHubScreen` — being handled by another agent this round.
- Exempt by the rule (no action): `SleeperConnect`, `Settings`,
  `FeedbackInbox` (modals; the last IS the feedback surface), `TestStages`
  (operator-only QA tool), `SignIn`/`LeaguePicker` (onboarding flow, pre-auth).

## Files

- `mobile/src/components/FeedbackFAB.tsx`
- `mobile/src/screens/FreeAgentsScreen.tsx`
- `mobile/src/screens/LeagueSummaryScreen.tsx`
- `CLAUDE.md` (root, Conventions)
- `mobile/src/components/CLAUDE.md` (registry note)

## Verification

- `cd mobile && npx tsc --noEmit` — clean.
- Backend suite untouched and green (1089 passed, 1 skipped).
- Manual QA suggested: League tab → rankings root shows ONE FAB; push
  Free agents / deep-link `app/league/summary` → FAB present bottom-right;
  capture sheet pre-fills the screen name.

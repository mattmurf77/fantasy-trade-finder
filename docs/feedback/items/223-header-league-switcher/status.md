# FB-223 — League switcher in the global header (covers FB-224)

- **Type:** UX restructure · **Status:** built 2026-08-01 (branch
  `teardown-remediation` worktree; ships live, no flag)
- **Spec:** approved mock
  `mockups/polish-lab-2026-08/header-league-switcher.html` (PROPOSED side).
  Operator ruling (verbatim): "League Switcher in the header is my
  preference. The Feature/page name should move to a header on the page
  itself."

## What shipped

### #223 — the global TopBar carries the ACTIVE league

`mobile/src/components/TopBar.tsx` (the one mount above the tab navigator
in TabNav) replaces the app wordmark with the league affordance, per the
mock:

- Brand tick (3×22 ice) + 11px chalk-faint `LEAGUE` micro-label over the
  truncating league name (15px `uiSemi` chalk, ~200pt tail-truncate) +
  14px **ice** chevron-down (ice = tappable). The whole left cluster is one
  full-bar-height press target (pressed = ink-3, the icon-button treatment);
  testID **`topbar.league`**.
- Tapping opens the shipped `LeagueSwitcherSheet` from ANY tab. The sheet
  is now mounted ONCE, inside TopBar — the per-screen mounts it obsoleted
  were removed (see below). `onAddLeague` (#199 "Add a league" row,
  testID `league.switcher.add-league` unchanged) closes the sheet and
  routes to the root-stack `LeaguePicker` via `navigationRef` — so #199 is
  now reachable from every tab, not just League home.
- The affordance dims + disables while `useSession.switching` is true
  (same guard the old LeaguePill had; no concurrent switches).
- **No-league (account-only) sessions fall back to the wordmark** — tick +
  `TRADE FINDER`, exactly the old markup.
- Bar height `TOP_BAR_HEIGHT` 44 → **52pt** (fits the two-line stack at
  the 11px type floor; constant is only consumed inside TopBar).
- Right side: bell + gear unchanged in behavior/ids (`topbar.settings`,
  bell badge logic untouched), but per the mock the **order swapped** —
  bell inboard of the gear so the unread badge sits away from the edge.

### #224 — page identity moved into page content (tab-root audit)

| Tab root | Before | After |
|---|---|---|
| Trades — hub (`TradesHome`, flag on) | in-page "Find a Trade" heading | unchanged (verified present) — no double title |
| Trades — classic (`TradesScreen`, flag off) | no page title (wordmark-adjacent) | new compact in-page **"Find a Trade"** heading (`type.heading`, matching the hub), rendered only when NOT a hub-launched finder mode (the `TradeFinderModeBar` titles those) and NOT first-run (collapsed chrome is deliberate there) |
| Rank (`QuickSetTiers` root) | native stack header "Quick Set Tiers" | unchanged — keeps it |
| Matches | in-page "Matches" title | unchanged — keeps it |
| League (`LeagueRankings` root) | native stack header "League rankings" + chart-card caption | unchanged — keeps it |

No screen gained a duplicate title; no tab root is now title-less.

### De-duplicated league indicators (removed vs kept)

**Removed** (the header already says it):

- `TradeFinderHubScreen` — the "Trading in" `LeaguePill` row + its local
  `LeagueSwitcherSheet` mount/state (~63pt back to hub content; feeds the
  #218 fit-to-screen pass).
- `TradesScreen` (classic + deck) — the "Trading in" `LeaguePill` row +
  its local sheet mount/state. The `[leagueId]` effect that resets
  deck/job state on a switch is untouched — it keys off the zustand league
  slice, not the switch's origin. The in-flight "Switching league…" /
  slow-switch overlay also still works (keys off `useSession.switching`).
- `LeagueScreen` (League home) — the hero's **switcher role**: the hero
  card stays as league identity (name, ESPN/scoring/teams badges, rank
  chip, joined chip → members overlay) but is no longer pressable and the
  chevron-down cue is gone; the bottom "Switch league" button and the
  local sheet mount (which carried the #199 wiring, now global) are
  removed. testID `league.hero` kept on the identity card (smoke flow
  09-league asserts it).
- `mobile/src/components/LeaguePill.tsx` — **deleted** (both mounts gone;
  component orphaned by this change).

**Kept:**

- League home hero card (identity), its joined-chip members overlay, and
  the RankChipBadge.
- `LeagueSwitcherSheet` itself — byte-identical, just re-homed to TopBar.
- Matches' per-league filter row (a filter, not a switcher).

## Switch behavior from any tab

Identical to the old per-screen switchers: the sheet calls
`useSession.switchLeague` (sessionInit re-run), screens react via the
league slice + league-keyed query keys (hub prefs/asset-prefs refetch,
Trades deck resets, League summary/coverage refetch). No navigation is
performed on switch, so there's no nav weirdness from Rank/Trades/Matches
— the current screen simply re-renders with the new league. Verified by
code-path audit: no removed mount had an `onSwitched` callback, so the
global sheet passes none either.

## testIDs

- New: `topbar.league` (registered in `mobile/src/components/CLAUDE.md`,
  Header league switcher tranche).
- Kept: `topbar.settings`, bell badge, `league.switcher.add-league`,
  `league.hero`.
- Maestro smoke flows: unaffected (`topbar.settings` in 11-apple,
  `league.hero` in 09-league both still resolve). Test-case doc TC-TRD-15
  ("Tap LeaguePill") now maps to tapping `topbar.league` — noted here
  rather than editing the historical test-case table.

## Files

- `mobile/src/components/TopBar.tsx` (league affordance, 52pt bar, bell
  order, global sheet mount)
- `mobile/src/components/LeaguePill.tsx` (deleted)
- `mobile/src/screens/TradeFinderHubScreen.tsx` (pill + sheet removed)
- `mobile/src/screens/TradesScreen.tsx` (pill + sheet removed; #224
  classic-home heading)
- `mobile/src/screens/LeagueScreen.tsx` (hero identity-only; bottom
  switch button + sheet removed)
- Docs: `mobile/src/components/CLAUDE.md`, `mobile/src/screens/CLAUDE.md`,
  `docs/design/components.md` (TopNav/LeagueRow rows)

## Verification

- `cd mobile && npx tsc --noEmit` — clean.
- `node tests/check-feedback-badge.js` / `node tests/check-dna-chips.js`
  — all pass (pure; unaffected surface, run per definition of done).

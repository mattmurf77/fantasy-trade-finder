# PRD FB-06 — League header team-count fix

**Feedback:** #41 · **Surface:** mobile/backend · **Priority:** P0 (data correctness)

## Requirement
The League screen's top header tile shows the wrong team count — it **excludes
the logged-in user's own team** (e.g. shows "11 teams" for a 12-team league).
Show the **total** number of teams in the league, including the user.

## User story
As a manager, the league header shows the true size of my league (e.g. "12
teams"), counting my own team — not one fewer.

## Acceptance criteria
- [ ] The top league header tile shows the league's **total roster/team count**
      (Sleeper's `total_rosters` for the league), including the logged-in user.
- [ ] A 12-team league reads "12", not "11".
- [ ] No other count that intentionally excludes self (e.g. "leaguemates joined"
      counts) is changed — fix ONLY the total-teams figure in the header tile.
- [ ] `cd mobile && npx tsc --noEmit` clean (and backend tests green if the fix
      is backend-side).

## Implementation notes
- First locate the source of the header count. Candidates: the mobile
  `LeagueScreen.tsx` header rendering, or the backend league-summary payload
  (`leaguemates_*` vs a total-teams field). If the backend returns
  `total_rosters` correctly and the mobile subtracts 1 (or uses a "leaguemates"
  field that excludes self), fix it on the mobile side. If the backend computes a
  count-minus-self for this tile, fix it at the source.
- **Owns** whichever single source produces the header number — keep the change
  surgical and do not touch the (correct) "joined the app" leaguemate counts.
- Cross-check against the related earlier branch
  `fix/league-summary-include-self-in-joined-count` if present — but #41 is about
  TOTAL teams, a distinct figure.

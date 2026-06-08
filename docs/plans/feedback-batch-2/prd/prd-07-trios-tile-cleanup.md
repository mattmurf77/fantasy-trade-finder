# PRD FB-07 — Trios tile cleanup (remove rookies link + injury tags)

**Feedback:** #26 (reverses #20), #33 · **Surface:** mobile · **Priority:** P1/P2 · **Owner:** primary (self, small)

## Part A — Remove the rookies link from Trios (#26)

### Requirement
Remove the "rookies" link/entry from the Trios (RankScreen) surface. (This
reverses the earlier #20 decision to keep it — the user now wants it gone.)

### User story
As a manager on the Trios screen, I don't see a rookies link cluttering the page.

### Acceptance criteria
- [ ] The rookies link/button is removed from the Trios/RankScreen UI.
- [ ] The backend `/api/rookies` route is left intact (UI removal only); no dead
      imports remain; tsc clean.

## Part B — Remove injury tags from Trios player tiles (#33)

### Requirement
Remove the injury-status tags shown on player tiles on the Trios screen.

### User story
As a manager ranking trios, the player tiles don't show injury tags.

### Acceptance criteria
- [ ] Injury tags no longer render on the Trios player tiles.
- [ ] Scope: if `PlayerCard` is shared, gate the injury display behind a prop
      (e.g. `showInjury`, default current behavior) and set it off for the Trios
      cards — so Tiers/Trades tiles are NOT unintentionally changed. (If injury
      tags are only ever shown in the Trios context, a direct removal is fine.)
- [ ] tsc clean; no visual regression on other screens that use PlayerCard.

## Implementation notes
- **Owns** `mobile/src/screens/RankScreen.tsx` and `mobile/src/components/PlayerCard.tsx`.
- Coordinate: FB-02 (Tiers) and FB-05 (Trades) render PlayerCard but must not
  edit it — adding an optional `showInjury` prop with a default that preserves
  current behavior is safe and won't conflict.
- Small change — primary executes directly (no subagent).

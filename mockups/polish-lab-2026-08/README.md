# Polish lab — 2026-08

Design mockups (no app code changes) for the August polish feedback batch.
Each page is self-contained (inline CSS, no external requests), shows the
CURRENT screen recreated faithfully from the real screen code on the left and
a PROPOSED redesign on the right in ~390px iPhone frames, with rationale
bullets at the bottom. Chalkline tokens per `docs/design/design-system.md`
(`--line-strong` at the 2026-07-19 a11y value `#59647A`); tier hexes per
`docs/cross-client-invariants.md`.

| Page | Feedback | What it shows |
|---|---|---|
| [`empty-states-progress.html`](empty-states-progress.html) | #229 · #230 · #234 | League home day-one zero state (0/11 joined, empty contrarian/leaderboards, 0% coverage) and the Matches empty inbox vs one system: a solo-value "Works right now" card (single action, clearly-labeled EXAMPLE trade), a single League-progress module (ring = positions ranked, 12-slot bar = leaguemates ranked, honest unlock line "2 more ranked leaguemates unlocks mutual matches"), and zero-rows collapsed into that module until they have data. |
| [`rank-method-consolidation.html`](rank-method-consolidation.html) | #232 · #233 | Both current chooser surfaces (RankHome 5-card chooser + Rank-tab 7-row sheet) and the Quick set empty-tier CTA vs: ONE chooser with three outcome-labeled primary cards (Fastest = Quick set / Most precise = Head-to-heads / Most control = Your full board), Quick rank folded into Quick set as a follow-on pass, advanced paths behind a "More ways to rank" disclosure, and the empty-tier primary reworded action-first ("Continue — no QBs this high") with the redundant Skip hidden at 0 selected. |

Sources recreated: `mobile/src/screens/LeagueScreen.tsx`,
`MatchesScreen.tsx` (S4 PRD-05 CTA variant), `RankHomeScreen.tsx`,
`RankMenu` in `mobile/src/navigation/TabNav.tsx`,
`QuickSetTiersScreen.tsx` (#159/#217 footer state),
`ContrarianLeaderboard.tsx`, `LeaderboardsSection.tsx`.

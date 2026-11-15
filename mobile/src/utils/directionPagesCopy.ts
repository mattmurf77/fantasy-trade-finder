// Improve pages — every string the two pages add (spec
// docs/plans/league-projections/direction-pages/spec.md §3). The rows, lines
// and buttons inside each list are NOT here: they are the existing bodies'
// own copy (utils/maxPfMovesCopy.ts, utils/playoffTargetsCopy.ts), unchanged.
// `{…}` are fills. tests/check-direction-pages.js pins the spec's strings.
// Zero imports.

export const DIRECTION_COPY = {
  // P-2: titles (also the RootNav header titles).
  'TITLE.playoffs': 'Improve Playoff Chances',
  'TITLE.draft_pick': 'Improve Draft Pick',
  // P-6: the two-figure summary.
  'SUM.playoff': 'Playoff chance',
  'SUM.pick': 'Projected pick',
  // P-10: the links under the list.
  'LINK.standings': 'View projected standings',
  'LINK.other.playoffs': 'Improve Playoff Chances instead',
  'LINK.other.draft_pick': 'Improve Draft Pick instead',
  // P-13: the Standings link rows' spoken hint.
  'HINT.opens': 'Opens {title}',
  // P-12: no league, and the unavailable card.
  'NO-LEAGUE.title': 'No league selected',
  'NO-LEAGUE.body': 'Pick a league from the league switcher to see this page.',
  'UNAVAILABLE.title': 'Not available for this league',
  'UNAVAILABLE.body': 'This page works for Sleeper leagues with a saved weekly forecast. Standings and the trade market work as usual.',
  // The forecast read failed (Standings' "Couldn't load" pattern).
  'ERROR.body': 'Couldn’t load the forecast.',
  'ERROR.retry': 'Try again',
} as const;

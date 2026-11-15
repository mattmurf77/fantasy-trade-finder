// Playoff targets — every user-facing string, verbatim from the build
// contract (docs/plans/league-projections/playoff-targets/contract.md §10).
// Keys are the contract's ids; a `.suffix` key is a second string from the
// same row. `{…}` are fills, formatted by utils/playoffTargets.ts per
// contract §11. tests/check-playoff-targets.js compares this table with the
// contract's §10 table in both directions, so an edit here without the
// contract fails. Zero imports.

export const TARGETS_COPY = {
  'C-TITLE': 'Playoff targets',
  'C-BASE': 'Your playoff chance today: {playoff}.',
  'C-HEAD': 'Lineup points added over the remaining {n} weeks',
  'C-HEAD.final': 'over the final week',
  'C-ROW-1': '{short_name}  {position}  {lineup_gain}',
  'C-ROW-2': 'Playoff chance {now} → {after}',
  'C-ROW-3': '{team} · {playoff} playoff chance',
  'C-OPEN-WEEKS': 'Starts for you in {k} of the remaining {n} weeks.',
  'C-OPEN-WEEKS.final': 'Starts for you in the final week.',
  'C-REPL-1': 'Starts over {name}.',
  'C-REPL-N': 'Starts over {name1} ({w1} weeks), {name2} ({w2} weeks).',
  'C-REPL-N.more': ' and {k} more.',
  'C-REPL-N.one': '1 week',
  'C-REPL-FA': '{name} (free agent)',
  'C-OPEN-SPOT': 'Fills an open lineup spot ({w} weeks).',
  'C-SHOWALL': 'Show all',
  'C-BUTTON': 'Find trades for {short_name}',
  'C-FOOT': 'Each number assumes you give up only picks or players who would not start for you, and that the other team gets no starter back. A real trade costs something, so the true gain is usually smaller.',
  'C-ELIGIBLE': 'Only players on teams with a playoff chance under 50% in this forecast, or whose manager set a Rebuilding or Tanking outlook, are listed.',
  'C-CHANGED': "A team's outlook changed after this forecast. The list updates with the next weekly forecast.",
  'C-ROSTER': 'Rosters changed after this forecast. The list updates with the next weekly forecast.',
  'C-NO-TARGETS': 'No single player on those teams raises your playoff chance.',
  'C-NONE-ALONE': 'None of these raises your playoff chance by a visible amount on its own.',
  'C-NO-SELLERS': 'No other team has a playoff chance under 50% or a Rebuilding or Tanking outlook right now.',
  'C-CLINCHED': 'You have clinched a playoff spot.',
  'C-ELIMINATED': 'Your team can no longer make the playoffs.',
  'C-NEAR-CERTAIN': 'Your team makes the playoffs in {playoff} of simulations, so no trade raises that by a visible amount.',
  'C-DEADLINE': "Your league's trade deadline has passed.",
  'C-SEASON-OVER': 'The regular season is over, so no trade can change your playoff chance.',
  'C-U-no_forecast': 'There is no saved forecast for this league yet.',
  'C-U-update_pending': 'A new forecast is being prepared. Playoff targets return when it is saved.',
  'C-U-refresh_failed': 'The latest forecast update failed. Playoff targets return after the next successful update.',
  'C-U-stale': 'The saved forecast is from an earlier week. Playoff targets return after the next weekly update.',
  'C-U-old_model': 'The saved forecast was made by an earlier version of the model. Playoff targets return after the next update.',
  'C-U-incomplete': 'This forecast is incomplete, so playoff targets are not shown.',
  'C-U-team_not_found': 'Your team could not be matched to the saved forecast.',
  'C-U-unsupported': 'Forecasts are not available for this league.',
  'C-U-missing_projections': 'The projection source had no projections for an upcoming week, so there is no new forecast.',
  'C-U-read_failed': 'The saved forecast could not be read just now.',
  'C-U-not_computed': 'Playoff targets are worked out with the weekly forecast. They appear after the next update.',
  'C-U-other': 'Playoff targets are not available right now.',
} as const;

export type PlayoffTargetsCopyId = keyof typeof TARGETS_COPY;

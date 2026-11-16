// The Home playoff card and its half sheet — every string they add (spec
// docs/plans/league-projections/direction-pages/spec.md §4, §5.6, §7.3;
// D-270). The figure labels and the sheet's three row titles are the pages'
// own strings (utils/directionPagesCopy.ts), so the card, the sheet and the
// pages cannot drift apart. `{…}` are fills. Zero imports.

export const DIRECTION_CARD_COPY = {
  // H-4: under the projected pick when another team owns it.
  'PICK.owned': 'owned by {team}',
  'PICK.owner_unknown': 'another team',
  // H-7: the one sentence the explanation gains.
  'EXPLAIN.pick': 'Projected pick is where your own first-round pick lands if the season follows the forecast.',
  // S-8: the scrim's spoken label, and the sheet's for VoiceOver.
  'SHEET.close': 'Close',
  'SHEET.label': 'Playoff options',
  // §7.3: the disabled-row line per reason. `feature_off` is never shown
  // (the row is not listed).
  'REASON.unavailable': 'Not available until the next forecast.',
  'REASON.season_over': 'The regular season is over.',
  'REASON.after_trade_deadline': 'The trade deadline has passed.',
  'REASON.none_found': 'No single move changes this right now.',
  'REASON.pick_owned_elsewhere': '{team} owns your first-round pick.',
  'REASON.no_miss': 'Your team almost never misses the playoffs.',
  'REASON.draft_order_not_maxpf': 'Your league does not draft by max PF.',
  'REASON.clinched': 'You have clinched a playoff spot.',
  'REASON.eliminated': 'You are eliminated from the playoffs.',
  'REASON.near_certain': 'Your playoff chance is already 99% or higher.',
  'REASON.no_sellers': 'No team in your league is selling right now.',
  'REASON.unknown': 'Not available right now.',
  'REASON.owner_unknown': 'Another team',
} as const;

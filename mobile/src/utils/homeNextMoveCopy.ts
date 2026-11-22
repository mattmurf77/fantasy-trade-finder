// Home's next move — every user-facing string it adds (scope
// docs/plans/home-next-move/scope.md §7, D-278). `{…}` are fills, formatted
// by utils/homeNextMove.ts with the lists' own formatters. "Find trades for
// {short_name}" is the lists' own C-BUTTON wording. Zero imports;
// tests/check-home-next-move.js compares this table with the scope's §7
// table in both directions.

export const NEXT_MOVE_COPY = {
  'NM-LABEL': 'Next move',
  'NM-SELL.pick': 'Sell {short_name} ({position}): projected pick {now} → {after}',
  'NM-SELL.top3': 'Sell {short_name} ({position}): top-3 pick chance {now} → {after}',
  'NM-SELL.playoff': 'Sell {short_name} ({position}): playoff chance {now} → {after}',
  'NM-BUY': 'Buy {short_name} ({position}) from {team}: playoff chance {now} → {after}',
  'NM-ACTION': 'Find trades',
  'NM-A11Y': 'Next move. {line}. Find trades for {short_name}.',
} as const;

export type NextMoveCopyId = keyof typeof NEXT_MOVE_COPY;

// Home's next move when there is none (flag `league.next_move_empty`; scope
// docs/plans/next-move-empty/scope.md "Every new string", D-279): the one
// line the row shows for a `none` block (or a move the live rosters no
// longer allow). Kept apart from NEXT_MOVE_COPY so build 199's table, and
// its check against the D-278 scope, are unchanged;
// tests/check-home-next-move.js compares this table with the D-279 scope's
// table in both directions.
export const NEXT_MOVE_NONE_COPY = {
  'NM-NONE.keep': 'Hold: your top sale is a player you marked Keep',
  'NM-NONE.sell-threshold': 'Hold: your top sale does not move your projected pick enough',
  'NM-NONE.buy-threshold': 'Hold: no single buy moves your playoff chance enough',
  'NM-NONE.clinched': 'Playoffs clinched: no move to suggest',
  'NM-NONE.eliminated': 'Eliminated from the playoffs: no buy to suggest',
  'NM-NONE.pick-elsewhere': 'No sale to suggest: another team owns your first-round pick',
  'NM-NONE.none': 'No move to suggest right now',
  'NM-A11Y.none': 'Next move. {line}.',
} as const;

export type NextMoveNoneCopyId = keyof typeof NEXT_MOVE_NONE_COPY;

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

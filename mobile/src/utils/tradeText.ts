// Platform resolution + copy-trade text for the send affordance (audit P0-6).
//
// PURE BY DESIGN: zero React imports, zero react-native imports, zero project
// imports. tests/check-trade-text.js transpiles this exact file and runs it
// under plain node with a `require` shim that THROWS on any runtime import —
// that shim is what mechanically enforces the rule, and it is why the
// clipboard write lives in utils/clipboard.ts instead of here.

/** Platforms a league can be linked from. Mirrors LeagueSummary.platform's
 *  four values (shared/types.ts) — deliberately NOT `string`, so a new
 *  platform is a compile error here and in NO_SEND_REASON, not a silent
 *  fall-through to "sendable". */
export type SendPlatform = 'sleeper' | 'espn' | 'mfl' | 'fleaflicker';

const NON_SLEEPER: readonly string[] = ['espn', 'mfl', 'fleaflicker'];

/** Which platform a send would target, from the SESSION's cached league list.
 *
 *  #146 fail-open, preserved verbatim: a league id that is not in the cache
 *  (demo league, stale cache, a launch that skipped the picker), or a cached
 *  row with no `platform` stamp, resolves to 'sleeper' and therefore keeps
 *  the Send button. Failing CLOSED would hide Send on real Sleeper leagues
 *  whenever the cache is cold, which is strictly worse.
 *
 *  `leagues` is typed structurally rather than as LeagueSummary[] to keep the
 *  "no project imports" rule mechanical; it is a strict supertype of
 *  LeagueSummary, so `useSession((s) => s.leagues)` passes unchanged. */
export function resolveSendPlatform(
  leagueId: string | undefined,
  leagues: ReadonlyArray<{ league_id: string; platform?: string }>,
): SendPlatform {
  if (!leagueId) return 'sleeper';
  const row = leagues.find((lg) => lg.league_id === leagueId);
  const p = row?.platform;
  return p && NON_SLEEPER.includes(p) ? (p as SendPlatform) : 'sleeper';
}

/** One honest, platform-NAMED reason per non-Sleeper platform. Structurally
 *  mirrors FreeAgentsScreen's NO_ADD_REASON (#179), minus its {title, body}
 *  shape — that reason is an Alert payload and needs a title; this one renders
 *  inline, where a title would be a second line of chrome. Keyed exhaustively
 *  so a fifth SendPlatform is a compile error here. */
export const NO_SEND_REASON: Record<Exclude<SendPlatform, 'sleeper'>, string> = {
  espn:        'Sending is Sleeper-only for now — copy this trade to propose it in ESPN.',
  mfl:         'Sending is Sleeper-only for now — copy this trade to propose it in MyFantasyLeague.',
  fleaflicker: 'Sending is Sleeper-only for now — copy this trade to propose it in Fleaflicker.',
};

/** Which mount the affordance is rendering in. Declared here, in the pure
 *  module, on P0-7's behalf: every value P0-7 will register as an analytics
 *  dimension is greppable in one place, importable without dragging React into
 *  the transpile, and pinned by check-trade-text.js. P0-6 fires no events. */
export type SendSurface = 'deck' | 'match' | 'awaiting' | 'calculator';

/** Exported only so the unit test can assert the union's exact membership —
 *  a TS type erases at transpile and cannot be checked at runtime. */
export const SEND_SURFACES: readonly SendSurface[] = ['deck', 'match', 'awaiting', 'calculator'];

// Per-INDEX fallback, not per-array: a partially-resolved names array (the
// MatchesScreen adapters do exactly this — `m.my_side_player_names?.[i] || id`)
// must not discard the names it does have. A raw player id in the pasted text
// is ugly but correct and actionable; an empty side is neither.
function sideNames(names: string[] | undefined, ids: string[] | undefined): string[] {
  if (ids && ids.length > 0) {
    return ids.map((id, i) => (names?.[i] || '').trim() || id);
  }
  return (names ?? []).map((n) => (n || '').trim()).filter(Boolean);
}

/** The clipboard payload for the non-Sleeper "Copy trade" action. Five
 *  candidate lines, assembled then filter(Boolean)-joined (the same idiom as
 *  TradeCalculatorScreen.shareTrade), so an absent field drops its line rather
 *  than blanking it — no trailing newline, no double blank lines, never ''.
 *
 *  Deliberately carries NO URL: growth.share_landing owns share attribution
 *  (it is the flag that appends `Build your own: {baseUrl}/?ref={username}` and
 *  fires calc_trade_shared). This is a paste-into-league-chat message, not a
 *  share; adding a ?ref= link here would widen the attribution surface with no
 *  flag and no event. Pinned by check-trade-text.js case 27. */
export function formatTradeForClipboard(input: {
  giveNames?: string[];
  giveIds?: string[];
  receiveNames?: string[];
  receiveIds?: string[];
  opponentUsername?: string;
  leagueName?: string;
}): string {
  const give = sideNames(input.giveNames, input.giveIds);
  const receive = sideNames(input.receiveNames, input.receiveIds);
  const league = (input.leagueName || '').trim();
  const opponent = (input.opponentUsername || '').trim();

  const lines = [
    league ? `Trade proposal — ${league}` : 'Trade proposal',
    opponent ? `To: @${opponent}` : '',
    give.length > 0 ? `I send: ${give.join(', ')}` : '',
    receive.length > 0 ? `I get: ${receive.join(', ')}` : '',
    '(Built with Fantasy Trade Finder)',
  ];
  return lines.filter(Boolean).join('\n');
}

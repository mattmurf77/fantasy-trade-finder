import { openPlatform, type ExternalSurface } from './openExternal';

// Sleeper hand-off: the #351 PRD §3.2 API, built on openPlatform.
//
// Always the `sleeper://` scheme, never https. sleeper.com's AASA claims no
// league path, so an https link goes Safari → Branch → Sleeper's home screen
// (#351 F1/F3), which is the symptom the operator reported. If the scheme
// rejects, Sleeper isn't installed and the user gets the D2 alert with a
// Get Sleeper button (openExternal.ts).
//
// Every Sleeper hand-off calls openInSleeperApp; there is no second
// implementation (PRD AC-2). Pinned by tests/check-sleeper-handoff.js.

export type SleeperTarget = 'add' | 'trade' | 'league';

export type SleeperRung =
  | 'add'
  | 'player'
  | 'players_tab'
  | 'trade'
  | 'trades_tab'
  | 'league'
  | 'bare';

// The closed ladder per target, deepest first (PRD §4.1). A rung outside its
// target's ladder is never used, so 'trade' can't land on an add screen.
export const SLEEPER_RUNG_LADDER: Readonly<Record<SleeperTarget, readonly SleeperRung[]>> = {
  add: ['add', 'player', 'players_tab', 'league', 'bare'],
  trade: ['trade', 'trades_tab', 'league', 'bare'],
  league: ['league', 'bare'],
};

// Rungs proven on a device, per target, deepest first, `bare` last.
// This is THE config choice. The device tests (#351 1–12, T1–T4) aren't
// recorded yet, so every target ships `bare` only. Add a rung only with a
// PASS row for it in docs/plans/sleeper-fa-deeplink/device-results.md;
// check-sleeper-handoff.js S10 fails otherwise.
export const SLEEPER_PROVEN_RUNGS: Readonly<Record<SleeperTarget, readonly SleeperRung[]>> = {
  add: ['bare'],
  trade: ['bare'],
  league: ['bare'],
};

export interface SleeperLink {
  target: SleeperTarget;
  leagueId?: string;
  /** add target only */
  playerId?: string;
}

const NUMERIC = /^\d+$/;
// Sleeper player ids are numeric, except a team defense ("KC").
const PLAYER_ID = /^[A-Za-z0-9]+$/;

// URL patterns from PRD §4.1. All but `bare` are unproven. For `league`,
// test 4 is the plural form and test 5 the singular; use whichever passes.
function rungUrl(rung: SleeperRung, L?: string, P?: string): string | null {
  switch (rung) {
    case 'add':
      return P ? `sleeper://players/${P}` : null;
    case 'player':
      return L && P ? `sleeper://leagues/${L}/players/${P}` : null;
    case 'players_tab':
      return L ? `sleeper://leagues/${L}/players` : null;
    case 'trade':
      return L ? `sleeper://leagues/${L}/trade` : null;
    case 'trades_tab':
      return L ? `sleeper://leagues/${L}/trades` : null;
    case 'league':
      return L ? `sleeper://leagues/${L}` : null;
    case 'bare':
      return 'sleeper://';
  }
}

// Pure. The deepest proven rung for the target that the inputs support;
// `bare` is the floor. A missing or non-numeric leagueId never yields a
// league rung. Never https. `proven` is a test seam.
export function sleeperAppUrl(
  t: SleeperLink,
  proven: Readonly<Record<SleeperTarget, readonly SleeperRung[]>> = SLEEPER_PROVEN_RUNGS,
): string {
  const L = t.leagueId && NUMERIC.test(t.leagueId) ? t.leagueId : undefined;
  const P = t.target === 'add' && t.playerId && PLAYER_ID.test(t.playerId) ? t.playerId : undefined;
  for (const rung of proven[t.target]) {
    if (!SLEEPER_RUNG_LADDER[t.target].includes(rung)) continue;
    const url = rungUrl(rung, L, P);
    if (url) return url;
  }
  return 'sleeper://';
}

// Copy (optional) → open the scheme → on rejection, the D2 alert.
// 'not_installed' means the alert is showing; nothing failed silently.
export async function openInSleeperApp(
  t: SleeperLink & { clipboardText?: string; surface?: ExternalSurface },
): Promise<'app' | 'not_installed'> {
  const outcome = await openPlatform({
    platform: 'sleeper',
    schemeUrl: sleeperAppUrl(t),
    clipboardText: t.clipboardText,
    surface: t.surface ?? 'unspecified',
    appMissing: 'alert',
  });
  return outcome === 'app' ? 'app' : 'not_installed';
}

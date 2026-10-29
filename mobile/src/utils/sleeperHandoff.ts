import { track } from '../api/events';
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
// implementation (PRD AC-2). It also emits the granted
// `sleeper_handoff_resolved` (trackHandoff, below), so call sites don't.
// Pinned by tests/check-sleeper-handoff.js.

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
  // ux-lead: if `player`/`add` is ever proven, the claim sheet's copy and disclosure become rung-conditional together.
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
  return resolveRung(t, proven).url;
}

function resolveRung(
  t: SleeperLink,
  proven: Readonly<Record<SleeperTarget, readonly SleeperRung[]>> = SLEEPER_PROVEN_RUNGS,
): { rung: SleeperRung; url: string } {
  const L = t.leagueId && NUMERIC.test(t.leagueId) ? t.leagueId : undefined;
  const P = t.target === 'add' && t.playerId && PLAYER_ID.test(t.playerId) ? t.playerId : undefined;
  for (const rung of proven[t.target]) {
    if (!SLEEPER_RUNG_LADDER[t.target].includes(rung)) continue;
    const url = rungUrl(rung, L, P);
    if (url) return { rung, url };
  }
  return { rung: 'bare', url: 'sleeper://' };
}

// Copy (optional) → open the scheme → sleeper_handoff_resolved → on
// rejection, the D2 alert. 'not_installed' means the alert is showing;
// nothing failed silently. `hasDrop` is the claim sheet's "picked a drop";
// it reaches the event only on an add hand-off off send_button.
export async function openInSleeperApp(
  t: SleeperLink & { clipboardText?: string; surface?: ExternalSurface; hasDrop?: boolean },
): Promise<'app' | 'not_installed'> {
  const { rung, url } = resolveRung(t);
  const surface = t.surface ?? 'unspecified';
  const outcome = await openPlatform({
    platform: 'sleeper',
    schemeUrl: url,
    clipboardText: t.clipboardText,
    surface,
    appMissing: 'alert',
    onSchemeSettled: (opened) => trackHandoff(t, surface, rung, opened),
  });
  return outcome === 'app' ? 'app' : 'not_installed';
}

// `sleeper_handoff_resolved`, INTENT (analytics-lead grant G1–G7, 2026-10-20,
// widened @ 8b63ef10; addendum docs/business/analytics/2026-10-28-sleeper-
// handoff-events.md). One per hand-off, fired synchronously from openPlatform's
// settle seam before the D2 alert (G3). `not_installed` = openURL rejected; the
// code never asks canOpenURL (G4). `has_drop` rides only on a target=add row
// off send_button, and only when the caller passed it: an absent key, never
// null (G2). No player id, name or league id (G5). A surface of 'unspecified'
// emits nothing, and so does target 'league' (not in the granted `target` set).
function trackHandoff(
  t: SleeperLink & { hasDrop?: boolean },
  surface: ExternalSurface,
  rung: SleeperRung,
  opened: boolean,
): void {
  if (surface === 'unspecified' || t.target === 'league') return;
  const props: Record<string, unknown> = {
    surface,
    target: t.target,
    rung,
    outcome: opened ? 'app' : 'not_installed',
  };
  if (t.target === 'add' && surface !== 'send_button' && typeof t.hasDrop === 'boolean') {
    props.has_drop = t.hasDrop;
  }
  track('sleeper_handoff_resolved', props);
}

// passReasonCadence.ts — when the deck asks why (flag `trade.pass_reason_cadence`,
// offer-learnings WS3; scope docs/plans/offer-learnings/scope-pass-reason-cadence.md).
//
// The operator's rule: a reason after every pass breaks a quick deck, so ask
// "once every few passes … upon a certain number of consecutive passes".
//   • ask once the user has passed `askAfter` (N) cards in a row;
//   • once asked — answered with a chip, "Just pass", or any other pass of the
//     asked card — stay quiet for the next `quietFor` (M) passes;
//   • a like resets the run of passes (it does not shorten the quiet period).
// N and M come from the server (`pass_reason_cadence` on GET /api/feature-flags).
//
// Pure and type-only-import, so tests/check-pass-reason-cadence.js runs it under
// plain node. The hook (hooks/usePassReasonCadence.ts) owns the React state;
// TradesScreen only calls `record` and passes the card props through.

import type { Layer1Code, Layer2Code } from '../api/declineReasons';

export interface CadenceConfig {
  /** N — consecutive passes before the prompt appears (>= 1). */
  askAfter: number;
  /** M — passes left unasked after the prompt was answered or dismissed (>= 0). */
  quietFor: number;
}

/** Starting values (operator, 2026-11-10). Mirrors the seeded knobs
 *  `pass_reason_ask_after` / `pass_reason_quiet_for`; used only when the
 *  server sent nothing usable. */
export const DEFAULT_CADENCE: CadenceConfig = { askAfter: 3, quietFor: 5 };

function intAtLeast(v: unknown, floor: number, fallback: number): number {
  return typeof v === 'number' && Number.isInteger(v) && v >= floor ? v : fallback;
}

/** The served `{ask_after, quiet_for}` → a config; anything malformed falls
 *  back per field to DEFAULT_CADENCE (the server already clamps the same way). */
export function normalizeCadence(raw: unknown): CadenceConfig {
  const o = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {};
  return {
    askAfter: intAtLeast(o.ask_after, 1, DEFAULT_CADENCE.askAfter),
    quietFor: intAtLeast(o.quiet_for, 0, DEFAULT_CADENCE.quietFor),
  };
}

export interface CadenceState {
  /** Passes since the last like or the last ask. */
  consecutivePasses: number;
  /** Passes still to go before the prompt may appear again. */
  quietRemaining: number;
}

export const INITIAL_CADENCE: CadenceState = { consecutivePasses: 0, quietRemaining: 0 };

/** Should the card now fronted carry the prompt? Flag off ⇒ never. */
export function shouldAsk(on: boolean, s: CadenceState, cfg: CadenceConfig): boolean {
  return on && s.quietRemaining === 0 && s.consecutivePasses >= cfg.askAfter;
}

/** Fold one deck disposition into the state. Flag off ⇒ the state never moves.
 *  A pass while the prompt was showing IS the answer or the dismissal, however
 *  it was made (chip, "Just pass", swipe), so it starts the quiet period. */
export function recordDisposition(
  on: boolean,
  s: CadenceState,
  decision: 'like' | 'pass',
  cfg: CadenceConfig,
): CadenceState {
  if (!on) return s;
  if (decision === 'like') return { ...s, consecutivePasses: 0 };
  if (shouldAsk(on, s, cfg)) return { consecutivePasses: 0, quietRemaining: cfg.quietFor };
  return {
    consecutivePasses: s.consecutivePasses + 1,
    quietRemaining: Math.max(0, s.quietRemaining - 1),
  };
}

/** The chips: what managers said when declining real offers (offer-learnings
 *  evidence), each mapped onto the existing taxonomy. Two codes are new and
 *  cadence-only (`other_picks_keep`, `other_waiting`); neither writes Elo. Only
 *  `value_giving` writes Elo, exactly as it does from the tiles. */
export interface PassReasonChip {
  label: string;
  reason: Layer1Code;
  detail: Layer2Code;
}

export const PASS_REASON_CHIPS: readonly PassReasonChip[] = [
  { label: 'Not moving that player', reason: 'other', detail: 'other_player_keep' },
  { label: 'Keeping my picks', reason: 'other', detail: 'other_picks_keep' },
  { label: 'Wrong direction for my team', reason: 'fit', detail: 'fit_outlook' },
  { label: "Don't rate what I'd get", reason: 'other', detail: 'other_player_avoid' },
  { label: 'Waiting on something', reason: 'other', detail: 'other_waiting' },
  { label: 'Value too low', reason: 'value', detail: 'value_giving' },
];

/** What the deck card receives on its `reasons` props while the flag is on. */
export interface PassReasonCadenceCard {
  mode: 'quiet' | 'ask';
  consecutivePasses: number;
  onShown: (tradeId: string) => void;
  onDismissed: (tradeId: string) => void;
}

/** The deck card's reasons: a 'quiet' card gets none, so it renders the plain
 *  ✓/✕ row. No `cadence` field (flag off) ⇒ returned untouched. */
export function cadenceCardReasons<T extends { cadence?: PassReasonCadenceCard }>(
  reasons: T | undefined,
): T | undefined {
  return reasons?.cadence?.mode === 'quiet' ? undefined : reasons;
}

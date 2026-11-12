// passReasonCadence.ts — when the deck asks why (flag `trade.pass_reason_cadence`,
// offer-learnings WS3; scope docs/plans/offer-learnings/scope-pass-reason-cadence.md).
//
// The operator's rule: a reason after every pass breaks a quick deck, so ask
// "once every few passes … upon a certain number of consecutive passes".
//   • ask once the user has passed `askAfter` (N) cards in a row — "ask" arms
//     the card: its ✕ opens the why-pass frame (TradeCard / PassReasonChips);
//   • once the frame has been shown, the card's pass (chip, "Just pass", or
//     any other exit — the frame always ends in a pass) starts the quiet
//     period: the next `quietFor` (M) passes go unasked;
//   • an armed card the user never opened the frame on (liked it, or passed
//     it by swipe / VoiceOver action) does not spend the ask: it carries to
//     the next card;
//   • otherwise a like resets the run of passes (it does not shorten the
//     quiet period).
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
 *  `prompted` — the why-pass frame was shown on this card. A pass of an armed
 *  card after the frame was shown IS the answer or the dismissal, so it starts
 *  the quiet period; an armed card whose frame never opened keeps the ask
 *  armed (a like leaves the state as is, a pass extends the run). */
export function recordDisposition(
  on: boolean,
  s: CadenceState,
  decision: 'like' | 'pass',
  cfg: CadenceConfig,
  prompted: boolean,
): CadenceState {
  if (!on) return s;
  const armed = shouldAsk(on, s, cfg);
  if (decision === 'like') return armed ? s : { ...s, consecutivePasses: 0 };
  if (armed && prompted) return { consecutivePasses: 0, quietRemaining: cfg.quietFor };
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

/** Where the why-pass frame's panel goes (PassReasonChips), in the frame's own
 *  coordinates (the frame covers the card). The invariant: whenever the frame
 *  opens, the WHOLE panel ends up inside the deck's visible scroll viewport —
 *  so the label, the copy line and the first chips are always readable.
 *   1. Preferred: vertically centred on the action row the ✕ sits in
 *      (`anchorY`), clamped into the part of the card that is both inside
 *      the card's padding and inside the visible viewport. No scroll.
 *   2. If that visible part is shorter than the panel (the card is mostly
 *      scrolled away), clamp into the card only and return `scrollBy` — the
 *      content offset delta that brings the panel in, top-aligned when the
 *      panel is taller than the viewport (the top is what must be read).
 *  Pure, so tests/check-pass-reason-cadence.js executes it. */
export interface WhyPassPlacementInput {
  /** Centre of the ✓/✕ row, frame coordinates. */
  anchorY: number;
  panelH: number;
  frameH: number;
  /** Frame padding — the panel never touches the card edge. */
  pad: number;
  /** The frame's top in window coordinates. */
  frameWinY: number;
  /** The visible viewport, window coordinates. */
  visTop: number;
  visBottom: number;
  /** Clearance kept from the viewport edges. */
  edge: number;
}

export function placeWhyPassPanel(i: WhyPassPlacementInput): { top: number; scrollBy: number } {
  const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);
  const want = i.anchorY - i.panelH / 2;
  const lo = i.pad;
  const hi = Math.max(lo, i.frameH - i.pad - i.panelH);
  const visLo = i.visTop + i.edge - i.frameWinY;
  const visHi = i.visBottom - i.edge - i.frameWinY - i.panelH;
  const a = Math.max(lo, visLo);
  const b = Math.min(hi, visHi);
  if (a <= b) return { top: clamp(want, a, b), scrollBy: 0 };
  const top = clamp(want, lo, hi);
  const pTop = i.frameWinY + top;
  const pBottom = pTop + i.panelH;
  const wantTop = i.visTop + i.edge;
  const wantBottom = i.visBottom - i.edge;
  let scrollBy = 0;
  if (pTop < wantTop) scrollBy = pTop - wantTop;
  else if (pBottom > wantBottom) scrollBy = Math.min(pBottom - wantBottom, pTop - wantTop);
  return { top, scrollBy };
}

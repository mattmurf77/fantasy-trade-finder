// rosterSetup — the pure half of roster-first setup for Find a Trade
// (flag `trades.roster_setup`; docs/plans/roster-first-trade-setup/prd.md).
//
// Zero runtime imports on purpose: `mobile/tests/check-roster-setup.js`
// transpiles and EXECUTES this file, so every decision the screen, the
// TradesHome card and the auto-push share lives here as a plain function.
// The store (`state/rosterSetup.ts`) only remembers; the screen only renders.

import type { Position } from '../shared/types';

/** The three per-asset states (prd §4.2). `open` is the "—" segment. */
export type AssetSetupState = 'move' | 'keep' | 'open';

/** The ONLY `list` values the setup step ever writes to
 *  `POST /api/league/asset-prefs` (prd §4.2; pinned by check-roster-setup). */
export type RosterSetupList = 'trade_block' | 'untouchable' | 'none';

export const SETUP_POSITIONS: readonly Position[] = ['QB', 'RB', 'WR', 'TE'];

/** Mirror of the server's model_config `picks_pool_cap` DEFAULT (6,
 *  `backend/database.py` model_config seed; read by `_picks_pool_cap()` in
 *  `backend/server.py`). The cap is not exposed to the client — neither
 *  `/api/league/picks` nor `/api/feature-flags` carries it — so the greyed
 *  "not in trade search" marker follows the default. If the knob is retuned
 *  server-side this marker drifts until the value is served; the toggle
 *  itself still saves either way (prd AC-4). */
export const PICKS_POOL_CAP_DEFAULT = 6;

/** Above this share of non-pick assets marked Keep, the guard note shows
 *  (prd §4.2 "Keep guard", D-213). Information only — never blocks. */
export const KEEP_GUARD_SHARE = 0.4;

export function listForState(state: AssetSetupState): RosterSetupList {
  if (state === 'move') return 'trade_block';
  if (state === 'keep') return 'untouchable';
  return 'none';
}

/** Saved tags → prefill (prd AC-2): untouchable → Keep, trade_block → Move,
 *  anything else (target, not_interested, untagged) → open. */
export function prefillStates(
  assetIds: readonly string[],
  prefs: { untouchables?: string[] | null; trade_block?: string[] | null } | null | undefined,
): Record<string, AssetSetupState> {
  const keep = new Set(prefs?.untouchables ?? []);
  const move = new Set(prefs?.trade_block ?? []);
  const out: Record<string, AssetSetupState> = {};
  for (const id of assetIds) {
    out[id] = keep.has(id) ? 'keep' : move.has(id) ? 'move' : 'open';
  }
  return out;
}

export interface SetupCounts {
  move: number;
  keep: number;
  open: number;
  pickMove: number;
  pickKeep: number;
  /** Non-pick assets — the Keep guard's denominator. */
  playerTotal: number;
  playerKeep: number;
}

export function countStates(
  assets: readonly { id: string; isPick: boolean }[],
  states: Record<string, AssetSetupState>,
): SetupCounts {
  const c: SetupCounts = {
    move: 0, keep: 0, open: 0, pickMove: 0, pickKeep: 0, playerTotal: 0, playerKeep: 0,
  };
  for (const a of assets) {
    const s = states[a.id] ?? 'open';
    c[s] += 1;
    if (a.isPick) {
      if (s === 'move') c.pickMove += 1;
      if (s === 'keep') c.pickKeep += 1;
    } else {
      c.playerTotal += 1;
      if (s === 'keep') c.playerKeep += 1;
    }
  }
  return c;
}

/** "Keeping 14 of 27. Fewer trades will fit." — null while under the guard. */
export function keepGuardNote(c: Pick<SetupCounts, 'playerKeep' | 'playerTotal'>): string | null {
  if (c.playerTotal <= 0) return null;
  if (c.playerKeep <= c.playerTotal * KEEP_GUARD_SHARE) return null;
  return `Keeping ${c.playerKeep} of ${c.playerTotal}. Fewer trades will fit.`;
}

/** Assets whose current state differs from the prefill. */
export function changedCount(
  states: Record<string, AssetSetupState>,
  prefill: Record<string, AssetSetupState>,
): number {
  let n = 0;
  for (const id of Object.keys(states)) {
    if ((states[id] ?? 'open') !== (prefill[id] ?? 'open')) n += 1;
  }
  return n;
}

/** Owned picks the engine never sees: the server keeps only the top
 *  `cap` picks per owner by PRICED value, and drops anything priced ≤ 0
 *  (`_owned_pick_assets`, server.py). `/api/league/picks` serves that same
 *  priced value as `pool_value`, so the client can mirror the cut. */
export function picksBeyondCap(
  picks: readonly { pick_id: string; pool_value?: number | null }[],
  cap: number = PICKS_POOL_CAP_DEFAULT,
): Set<string> {
  const sorted = picks
    .slice()
    .sort((a, b) => (b.pool_value ?? 0) - (a.pool_value ?? 0));
  const out = new Set<string>();
  sorted.forEach((p, i) => {
    if (i >= cap || (p.pool_value ?? 0) <= 0) out.add(p.pick_id);
  });
  return out;
}

/** Picks display order (prd §4.1): season, then round, then priced value. */
export function sortPicks<T extends { season: number; round: number; pool_value?: number | null }>(
  picks: readonly T[],
): T[] {
  return picks.slice().sort(
    (a, b) =>
      a.season - b.season
      || a.round - b.round
      || (b.pool_value ?? 0) - (a.pool_value ?? 0),
  );
}

/** Rank-step walk (prd §5.2): QB, RB, WR, TE, skipping any position with
 *  fewer than 2 rankable roster players. With `onlyPositions` (the
 *  roster-changed entry, prd §3.3) only positions that gained a player. */
export function rankSteps(
  rankableByPosition: Partial<Record<Position, number>>,
  onlyPositions?: ReadonlySet<string> | null,
): Position[] {
  return SETUP_POSITIONS.filter(
    (p) => (rankableByPosition[p] ?? 0) >= 2 && (!onlyPositions || onlyPositions.has(p)),
  );
}

/** Quick Rank's save order: clicked order first, unclicked appended in
 *  their current order. Ids only — no `via` is ever attached (prd §5.2). */
export function orderedIdsForSave(
  clicked: readonly string[],
  currentOrder: readonly string[],
): string[] {
  const clickedSet = new Set(clicked);
  return [...clicked, ...currentOrder.filter((id) => !clickedSet.has(id))];
}

/** Assets on the roster now that the stored snapshot never saw (prd §3.3).
 *  Removals never prompt. */
export function newAssetIds(
  current: readonly string[],
  seen: readonly string[] | null | undefined,
): string[] {
  const s = new Set(seen ?? []);
  return current.filter((id) => !s.has(id));
}

// ── Entry decisions ─────────────────────────────────────────────────────

export interface AutoPushInput {
  flagOn: boolean;
  leagueId: string | null;
  isDemo: boolean;
  hydrated: boolean;
  hasRecord: boolean;
  /** Players + owned picks on the caller's roster; null while unknown. */
  assetCount: number | null;
  alreadyPushedThisSession: boolean;
}

/** prd §3.1 — the only automatic entry. All must hold. */
export function shouldAutoPush(i: AutoPushInput): boolean {
  return (
    i.flagOn
    && !!i.leagueId
    && i.leagueId !== 'league_demo'
    && !i.isDemo
    && i.hydrated
    && !i.hasRecord
    && (i.assetCount ?? 0) > 0
    && !i.alreadyPushedThisSession
  );
}

// ── Return-card snooze ladder (prd §3.3, QuickSetPromptCard grammar) ────
// Not now → one re-offer in a later session → retired. "Retired" collapses
// the card to a one-line row (the TeamReviewEntryCard / D-025 rule: an
// entry is never removed outright), except the roster-changed card, whose
// retirement absorbs the new assets into the snapshot instead.

export type PromptKind = 'entry' | 'roster_changed';

export interface PromptLadder {
  kind: PromptKind;
  /** onboarding `sessionCount` at the first "Not now". */
  snoozedSession: number;
  /** sessionCount the one re-offer was shown in; null until shown. */
  reofferSession: number | null;
  retired: boolean;
}

export type CardView = 'full' | 'collapsed';

/** What the TradesHome card shows for a ladder in this session. A ladder
 *  for a different kind does not apply (a fresh card starts fresh). */
export function cardView(
  ladder: PromptLadder | null | undefined,
  kind: PromptKind,
  sessionCount: number,
): CardView {
  if (!ladder || ladder.kind !== kind) return 'full';
  if (ladder.retired) return 'collapsed';
  if (sessionCount <= ladder.snoozedSession) return 'collapsed';
  if (ladder.reofferSession == null || ladder.reofferSession === sessionCount) return 'full';
  return 'collapsed';
}

/** Bookkeeping when the full card renders: stamps the re-offer session the
 *  first time a snoozed card is shown again. Returns null when unchanged. */
export function ladderOnShow(
  ladder: PromptLadder | null | undefined,
  kind: PromptKind,
  sessionCount: number,
): PromptLadder | null {
  if (!ladder || ladder.kind !== kind || ladder.retired) return null;
  if (sessionCount > ladder.snoozedSession && ladder.reofferSession == null) {
    return { ...ladder, reofferSession: sessionCount };
  }
  return null;
}

/** "Not now": first tap snoozes; a tap on the re-offer retires. */
export function ladderOnSnooze(
  ladder: PromptLadder | null | undefined,
  kind: PromptKind,
  sessionCount: number,
): PromptLadder {
  if (!ladder || ladder.kind !== kind) {
    return { kind, snoozedSession: sessionCount, reofferSession: null, retired: false };
  }
  if (ladder.reofferSession != null || sessionCount > ladder.snoozedSession) {
    return { ...ladder, retired: true };
  }
  return ladder;
}

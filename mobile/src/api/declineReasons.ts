// declineReasons.ts — decline-reason capture (flag `feedback.decline_reasons`).
// Spec: docs/plans/decline-reason-capture/SPEC.md §2 (taxonomy), §3 (persistence).
//
// PROGRESSIVE WRITES ARE THE POINT (SPEC §3). Every tap commits on its own;
// nothing is batched behind a submit:
//   1. layer-1 tile tap  → postDeclineReason({ layer: 1, reason })
//   2. layer-2 option    → postDeclineReason({ layer: 2, reason, detail })
//   3. "Other" tap       → postDeclineReason({ layer: 2, detail: '*_other' })
//                          BEFORE the text box opens, then the send upgrades
//                          the same row with `free_text`.
// The server upsert is keyed on `impression_id`, so 1→2→3 land on one row and
// a tester who stops at any step still leaves a complete, honest record.
//
// Fire-and-forget by contract, exactly like api/events.ts: a reason write must
// never block the deck or surface an error to a tester who is mid-triage. The
// companion `/api/trades/swipe` remains independent. Since #419 the existing
// `passed` response also reports a verified durable pass (including repair
// after a reason was banked without its card). A caller must read that field,
// not infer commitment from HTTP success or from `ok`.

import { api } from './client';

// ── Taxonomy (SPEC §2 — exact codes, do not improvise) ────────────────────

export type Layer1Code = 'value' | 'fit' | 'other';

export type Layer2Code =
  | 'value_giving'
  | 'value_getting'
  | 'value_other'
  | 'fit_outlook'
  | 'fit_new_weakness'
  | 'fit_duplicate'
  | 'fit_other'
  // The "Neither" tile's structured options (SPEC §2 amendment 2026-08-19,
  // D-080). Two codes, not one: `keep` is a give-side keep-list signal
  // ("won't trade MY guy"), `avoid` is a receive-side avoid-list signal
  // ("don't want THEIR guy"), and they point at different engine fixes.
  // The shared `other_player_` stem makes the axis selectable as a prefix.
  | 'other_player_keep'
  | 'other_player_avoid'
  | 'other_text';

/** Layer-2 codes that open the free-text box instead of committing outright. */
export const FREE_TEXT_CODES = ['value_other', 'fit_other', 'other_text'] as const;

/** Free text is stored on the row and NEVER sent as an analytics property
 *  (SPEC §3.4). Capped client-side so a runaway paste can't wedge the POST. */
export const FREE_TEXT_MAX = 500;

export interface DeclineReasonWrite {
  /** Joins the deck impression that was passed. Omitted when the served card
   *  carried none (deck.signal_v2 off / legacy card) — see the assumption note
   *  in the scope block: the server then keys on (user, trade_id). */
  impressionId?: string;
  tradeId: string;
  leagueId?: string;
  givePlayerIds?: string[];
  receivePlayerIds?: string[];
  targetUserId?: string;
  targetUsername?: string;
  layer: 1 | 2;
  reason: Layer1Code;
  /** Layer 1 only — the prior layer-1 reason when the tester switched tiles,
   *  else 'none'. A switch is a refinement, not a reset (SPEC §3). */
  switchedFrom?: Layer1Code | 'none';
  /** Layer 2 only. */
  detail?: Layer2Code;
  /** Layer 2 only, on the free-text send. */
  freeText?: string;
  /** Layer 1 only, on the FIRST tile tap — the tap that carries the pass
   *  disposition. The backend keeps only the first `pass` outcome row per
   *  impression, and this write lands BEFORE the swipe POST, so the reason
   *  row must carry the same dwell/engagement signal the swipe sends
   *  (SwipeSignal in api/trades.ts) or the surviving row has NULL dwell.
   *  Omitted on tile switches (the disposition-time signal already landed)
   *  and whenever the swipe itself would send none (deck.signal_v2 off or
   *  no impression_id). */
  dwellMs?: number;
  detailExpanded?: boolean;
  calcOpened?: boolean;
}

/**
 * POST /api/trades/pass-reason — upsert the decline-reason row for this
 * impression. `ok` acknowledges the reason; only `passed === true` confirms
 * the exact durable pass. Null means transport failure. Never throws or shows UI.
 */
export interface DeclineReasonResult {
  ok?: boolean;
  passed?: boolean;
  reason?: Layer1Code | null;
  detail?: Layer2Code | null;
  switched_from?: Layer1Code | null;
  elo_written?: boolean;
}

export async function postDeclineReason(w: DeclineReasonWrite): Promise<DeclineReasonResult | null> {
  try {
    return await api.post<DeclineReasonResult>('/api/trades/pass-reason', {
      impression_id: w.impressionId || undefined,
      trade_id: w.tradeId,
      league_id: w.leagueId || undefined,
      give_player_ids: w.givePlayerIds,
      receive_player_ids: w.receivePlayerIds,
      target_user_id: w.targetUserId || undefined,
      target_username: w.targetUsername || undefined,
      layer: w.layer,
      reason: w.reason,
      switched_from: w.switchedFrom || undefined,
      detail: w.detail || undefined,
      free_text: w.freeText ? w.freeText.slice(0, FREE_TEXT_MAX) : undefined,
      // Booleans are sent faithfully (a `|| undefined` would drop `false`,
      // and the swipe POST sends `detail_expanded: false` explicitly).
      dwell_ms: typeof w.dwellMs === 'number' ? w.dwellMs : undefined,
      detail_expanded: typeof w.detailExpanded === 'boolean' ? w.detailExpanded : undefined,
      calc_opened: typeof w.calcOpened === 'boolean' ? w.calcOpened : undefined,
    });
  } catch {
    // A companion swipe may still succeed; absence of this response is not
    // evidence either for or against that independent request.
    return null;
  }
}

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
// disposition itself rides the unchanged `/api/trades/swipe` POST, so a failed
// reason write costs the reason, never the pass.
//
// ── BACKEND CONTRACT ASSUMPTION (reconcile at integration) ────────────────
// The backend half is being built on `feat/decline-reasons-backend`. This
// module is written against SPEC §3/§6 and is deliberately the ONLY place
// mobile knows the route shape — if the sibling agent's route differs (name,
// verb, field names, or folding layer-1 into `/api/trades/swipe`), the fix is
// this file and nothing else. Callers only ever see the typed helpers below.

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
  layer: 1 | 2;
  reason: Layer1Code;
  /** Layer 1 only — the prior layer-1 reason when the tester switched tiles,
   *  else 'none'. A switch is a refinement, not a reset (SPEC §3). */
  switchedFrom?: Layer1Code | 'none';
  /** Layer 2 only. */
  detail?: Layer2Code;
  /** Layer 2 only, on the free-text send. */
  freeText?: string;
}

/**
 * POST /api/trades/pass-reason — upsert the decline-reason row for this
 * impression. Resolves to `true` on a committed write, `false` on any
 * failure; never throws, never surfaces UI.
 */
export async function postDeclineReason(w: DeclineReasonWrite): Promise<boolean> {
  try {
    await api.post('/api/trades/pass-reason', {
      impression_id: w.impressionId || undefined,
      trade_id: w.tradeId,
      league_id: w.leagueId || undefined,
      layer: w.layer,
      reason: w.reason,
      switched_from: w.switchedFrom || undefined,
      detail: w.detail || undefined,
      free_text: w.freeText ? w.freeText.slice(0, FREE_TEXT_MAX) : undefined,
    });
    return true;
  } catch {
    // Swallowed by contract (see the header). The pass is already recorded by
    // the swipe POST; losing the reason degrades the diagnostic, not the deck.
    return false;
  }
}

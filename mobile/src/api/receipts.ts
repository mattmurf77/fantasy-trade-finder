// Receipts — the viewer's graded suggestion track record.
// Backend: GET /api/league/<league_id>/receipts (docs/plans/receipts/LLD.md §2.2).
//
// ONE call, ALL THREE windows. There is deliberately no per-window endpoint:
// if the client could request a single window, some surface eventually would
// request the flattering one. The window chips switch between fields of a
// payload that is already in memory — they never refetch.
//
// 404 `feature_disabled` while `receipts.screen` is dark. Callers treat that
// as "hide the entry point", never as an error to show.

import { api } from './client';

export type ReceiptsWindowDays = 14 | 28 | 56;

/** `ready` = n cleared the min-n gate and the stats are populated.
 *  `insufficient` = graded rows exist but not enough to publish a number.
 *  `pending` = nothing graded at this window yet. */
export type ReceiptsWindowStatus = 'ready' | 'insufficient' | 'pending';

export interface ReceiptsWindowSummary {
  window_days: ReceiptsWindowDays;
  n: number;
  status: ReceiptsWindowStatus;
  /** Present only when status is `ready` — below min-n there is no number. */
  win_share?: number;
  median_edge_pct?: number | null;
}

export interface ReceiptsAsset {
  id: string;
  name: string | null;
  is_pick: boolean;
}

export interface ReceiptsRowWindow {
  give_delta: number | null;
  receive_delta: number | null;
  /** Swap edge: receive-side delta minus give-side delta, consensus units. */
  edge: number | null;
  /** Edge over the serve-time package midpoint. NULL on junk-for-junk rows. */
  edge_pct: number | null;
  imputed: boolean;
}

export interface ReceiptsRow {
  impression_id: string;
  served_at: string | null;
  shape_bucket: string | null;
  give: { assets: ReceiptsAsset[]; serve_value: number | null };
  receive: { assets: ReceiptsAsset[]; serve_value: number | null };
  windows: Record<string, ReceiptsRowWindow | null>;
  has_picks: boolean;
  coverage: { give: number | null; receive: number | null };
}

export interface ReceiptsMaturity {
  tracked_n: number;
  first_tracked_at: string | null;
  graded_n: Record<string, number>;
  min_n: number;
  mature: Record<string, boolean>;
}

export interface ReceiptsDisclosure {
  gradeable_share: number | null;
  ties: number;
  null_edge_pct: number;
  deduped_reserves: number;
  pre_telemetry: number;
  excluded: Record<string, number>;
  methodology: string;
}

export interface ReceiptsResponse {
  league_id: string;
  scoring_format: string | null;
  grader_version: string | null;
  maturity: ReceiptsMaturity;
  windows: ReceiptsWindowSummary[];
  headline_window_days: number;
  best_call_impression_id: string | null;
  worst_call_impression_id: string | null;
  rows: ReceiptsRow[];
  disclosure: ReceiptsDisclosure;
}

export const RECEIPTS_WINDOWS: ReceiptsWindowDays[] = [14, 28, 56];

export async function getLeagueReceipts(leagueId: string) {
  return api.get<ReceiptsResponse>(
    `/api/league/${encodeURIComponent(leagueId)}/receipts`,
  );
}

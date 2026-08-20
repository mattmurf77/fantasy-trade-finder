import { useEffect, useRef, useState } from 'react';

import { evaluateTradeInLeague, type CalcEvaluationInLeague } from '../api/calc';
import type { ScoringFormat } from '../shared/types';

// #357 — LAZY per-card impact fetch (operator decision 2026-08-19:
// *"Compute on the fronted card only"*).
//
// WHY LAZY, IN NUMBERS. The with-trade playoff re-simulation costs ~112 ms
// server-side (backend/outlook/trade_delta.py, DELTA_SIM_COUNT = 2000). A deck
// is ~30 cards. Computing eagerly would add ~3.4 s to deck generation and throw
// most of it away — the median card is passed in well under a second. Fetching
// only for the card the user is actually looking at makes the deck open at its
// current speed and spends the 112 ms only where someone reads it.
//
// This hook is therefore mounted ONLY by the top card. A peek card, a match
// variant or a read-only mount passes `enabled: false` and costs nothing.
//
// FAILURES ARE QUIET ON SCREEN BUT NOT INVISIBLE TO CODE. The card's job is
// the trade; the impact block is enrichment, so a 404 (flag off), a 501
// (non-Sleeper league), a timeout or a 500 must never put an error state on a
// swipe card. They resolve to `evaluation: null` — but they also set `failed`.
//
// The distinction was learned the hard way (2026-08-19/20). The first cut of
// this hook rendered `null` on every failure, which is byte-identical on
// screen to a healthy trade that moves no starting slots. A binding bug —
// passing the session's raw `activeFormat`, which is legitimately null in
// several states, instead of the `calcFormat` fallback every other consumer in
// TradesScreen uses — disabled the fetch entirely and shipped in build 122
// looking exactly like "this trade changes nothing". `failed` is what makes
// those three states tellable apart.

export interface CardImpactState {
  loading: boolean;
  evaluation: CalcEvaluationInLeague | null;
  /** True when a fetch was attempted and FAILED, as opposed to never having
   *  run or having returned a trade that moves no starting slots. Without this
   *  the three states are indistinguishable on screen, which is exactly how
   *  the disabled-hook bug survived a build: it rendered `null`, and so does a
   *  perfectly healthy trade that changes nothing. */
  failed: boolean;
}

const EMPTY: CardImpactState = { loading: false, evaluation: null, failed: false };

export function useCardImpact(params: {
  enabled: boolean;
  tradeId: string | null;
  leagueId: string | null;
  opponentUserId: string | null;
  givePlayerIds: string[];
  receivePlayerIds: string[];
  format: ScoringFormat | null;
}): CardImpactState {
  const {
    enabled, tradeId, leagueId, opponentUserId,
    givePlayerIds, receivePlayerIds, format,
  } = params;

  const [state, setState] = useState<CardImpactState>(EMPTY);

  // The fetch is keyed on the TRADE, not on the array identities: the card's
  // id arrays are rebuilt on every render, so depending on them directly would
  // refire the request on each parent re-render (and each swipe animation
  // frame). `trade_id` changes exactly when the fronted card changes, which is
  // the moment we actually want a new fetch.
  const key = enabled && tradeId && leagueId && opponentUserId && format
    ? `${tradeId}|${leagueId}|${opponentUserId}`
    : null;

  // Latest-wins: a fast swiper can front three cards before the first response
  // lands, and a late reply must never paint over the card now on screen.
  const activeKey = useRef<string | null>(null);

  useEffect(() => {
    activeKey.current = key;
    if (!key) {
      setState(EMPTY);
      return;
    }
    const controller = new AbortController();
    setState({ loading: true, evaluation: null, failed: false });

    evaluateTradeInLeague(
      givePlayerIds,
      receivePlayerIds,
      format as ScoringFormat,
      leagueId as string,
      opponentUserId as string,
      controller.signal,
    )
      .then((res) => {
        if (activeKey.current !== key) return;   // a newer card is fronted
        setState({ loading: false, evaluation: res ?? null, failed: !res });
      })
      .catch(() => {
        if (activeKey.current !== key) return;
        // Quiet on screen, but RECORDED — see `failed`. The card must not
        // shout, and it must not lie by looking identical to success.
        setState({ loading: false, evaluation: null, failed: true });
      });

    return () => {
      controller.abort();
      // Do NOT clear activeKey here — the next effect run sets it, and
      // clearing on unmount would let an in-flight reply from the OLD key
      // pass the `activeKey.current !== key` guard on a remount.
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return state;
}

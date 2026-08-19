import { useCallback, useEffect, useRef, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { generateTrades, getTradeStatus } from '../api/trades';
import {
  FAIRNESS_PREF_KEY,
  fairnessOnFromPref,
  fairnessThresholdFor,
} from '../api/tradePregen';
import { getProgress } from '../api/rankings';
import type { RankingProgress, TradeCard, TradeJobSnapshot } from '../shared/types';

// usePresentationDeck — read-only deck fetch for the presentation-v2 surface
// (flag `trades.presentation_v2`).
//
// ══ IT MUST LAND IN THE SAME SERVER CACHE SLOT AS THE DECK ════════════════
// The server's `_trade_job_is_fresh` keys its job cache on `fairness_threshold`
// (among other things). If this surface derived its own threshold, it would
// kick a SECOND full generation for a user who had already warmed the deck's
// slot — doubling engine load and, worse, serving a different set of cards
// (and therefore a different set of impression rows) than the deck for the
// same user in the same session.
//
// So the threshold comes from the SAME `fairnessOnFromPref` /
// `fairnessThresholdFor` helpers that TradesScreen and the session-init
// pregen both call. That agreement is pinned by
// mobile/tests/check-fairness-default.js for the two existing readers and by
// mobile/tests/check-presentation-v2.js §3 for this one. Do not re-derive it.
//
// This hook deliberately sends NONE of the deck's targeting fields (pins,
// opponent scope, trade_intent, package mode): the endorsed hero is the
// league-wide organic sweep by definition, and an unpinned body is exactly
// what the pregen already warmed. `force` is never sent — this surface must
// never invalidate a deck the user is mid-triage on.
//
// Polling mirrors the deck's self-scheduling backoff (800ms -> 4000ms) and
// gives up after MAX_POLL_FAILURES rather than hammering a wedged job.

const POLL_START_MS = 800;
const POLL_MAX_MS = 4000;
const MAX_POLL_FAILURES = 4;

export interface PresentationDeckState {
  cards: TradeCard[];
  loading: boolean;
  /** True while the job is still fanning out — some cards may already be in. */
  streaming: boolean;
  error: string | null;
  /** Rosters swept, for the honest empty state's "we checked all N rosters". */
  rostersChecked: number;
  /** Decline-suppression count the snapshot reports (flag `deck.fatigue`). */
  suppressedCount: number;
  /** The threshold this deck actually ran at — the empty state's price lever. */
  fairnessThreshold: number;
  progress: RankingProgress | undefined;
  refresh: () => void;
}

export default function usePresentationDeck(leagueId: string | null | undefined): PresentationDeckState {
  const [job, setJob] = useState<TradeJobSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [threshold, setThreshold] = useState<number>(fairnessThresholdFor(fairnessOnFromPref(null)));
  const [progress, setProgress] = useState<RankingProgress | undefined>(undefined);
  const epochRef = useRef(0);

  const run = useCallback(async () => {
    if (!leagueId) return;
    const epoch = ++epochRef.current;
    setLoading(true);
    setError(null);
    try {
      const raw = await AsyncStorage.getItem(FAIRNESS_PREF_KEY);
      const t = fairnessThresholdFor(fairnessOnFromPref(raw));
      if (epoch !== epochRef.current) return;
      setThreshold(t);
      const snap = await generateTrades({ league_id: leagueId, fairness_threshold: t });
      if (epoch !== epochRef.current) return;
      setJob(snap);
      if (snap.status === 'error') setError(snap.error || 'Could not build trade ideas.');
    } catch (e: any) {
      if (epoch !== epochRef.current) return;
      setError(e?.message || 'Could not build trade ideas.');
    } finally {
      if (epoch === epochRef.current) setLoading(false);
    }
  }, [leagueId]);

  useEffect(() => {
    setJob(null);
    void run();
  }, [run]);

  // Board progress — the honest denominator behind the confidence cap. An
  // existing GET; no new route. Failure is silent: a missing progress payload
  // degrades the cap's copy, it never blocks the surface.
  useEffect(() => {
    let cancelled = false;
    getProgress()
      .then((p) => {
        if (!cancelled) setProgress(p);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [leagueId]);

  // Poll while running.
  useEffect(() => {
    if (!job || job.status !== 'running' || !job.job_id) return;
    let cancelled = false;
    let failures = 0;
    let intervalMs = POLL_START_MS;
    let prevDone = job.opponents_done ?? 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const epoch = epochRef.current;

    const tick = async () => {
      if (cancelled) return;
      try {
        const next = await getTradeStatus(job.job_id);
        if (cancelled || epoch !== epochRef.current) return;
        failures = 0;
        // Reset the backoff on real progress; otherwise widen it so a stalled
        // job is not hammered.
        const done = next.opponents_done ?? 0;
        intervalMs = done > prevDone ? POLL_START_MS : Math.min(POLL_MAX_MS, intervalMs * 2);
        prevDone = done;
        setJob(next);
        if (next.status === 'running') timer = setTimeout(tick, intervalMs);
        else if (next.status === 'error') setError(next.error || 'Could not build trade ideas.');
      } catch {
        if (cancelled) return;
        failures += 1;
        if (failures >= MAX_POLL_FAILURES) {
          // Give up locally; the server worker keeps running, so a refresh
          // lands on the warm cache rather than restarting the sweep.
          setError('Lost contact while building ideas. Pull to try again.');
          return;
        }
        timer = setTimeout(tick, Math.min(POLL_MAX_MS, intervalMs * 2));
      }
    };
    timer = setTimeout(tick, intervalMs);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [job]);

  return {
    cards: job?.cards ?? [],
    loading: loading && !job,
    streaming: job?.status === 'running',
    error,
    rostersChecked: job?.opponents_total ?? 0,
    suppressedCount: job?.suppression_note?.count ?? 0,
    fairnessThreshold: threshold,
    progress,
    refresh: run,
  };
}

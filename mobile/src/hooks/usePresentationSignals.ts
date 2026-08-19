import { useCallback, useEffect, useRef } from 'react';
import { AppState, Platform } from 'react-native';
import { track } from '../api/events';
import { swipeTrade, type SwipeSignal } from '../api/trades';
import {
  postDeclineReason,
  type Layer1Code,
  type Layer2Code,
} from '../api/declineReasons';
import { useFlag } from '../state/useFeatureFlags';
import type { TradeCard } from '../shared/types';

// usePresentationSignals — the impression/outcome spine for the
// presentation-v2 surface (flag `trades.presentation_v2`).
//
// ══ INSTRUMENTATION PARITY IS THE WHOLE JOB OF THIS FILE ══════════════════
// A card dismissed on the new surface MUST produce the same rows the old deck
// produces, because that data is what the entire engine programme (deck
// impressions -> outcomes -> Thompson/taste/fatigue re-rankers -> the
// three-model bake-off) is built on. A second presentation that quietly
// writes a different shape would silently poison every downstream estimator.
//
// Parity is enforced by REUSE, not by re-implementation:
//   • the disposition rides `swipeTrade(card, decision, signal)` — the same
//     exported function TradesScreen's swipeMutation calls, so the POST body
//     (trade_id, decision, league_id, give/receive ids, target ids) plus the
//     additive SwipeSignal fields are byte-identical;
//   • `SwipeSignal` is imported, not redeclared, so a field added there
//     cannot silently go unsent here;
//   • decline reasons ride `postDeclineReason` — the same module, the same
//     progressive-write contract, the same taxonomy codes;
//   • the analytics events are the same NAMES with the same property sets:
//     `deck_card_viewed` after VIEWED_MIN_MS, `trade_pass_layer1` /
//     `trade_pass_layer2` on the reason taps.
//
// Two constants are duplicated from TradesScreen (VIEWED_MIN_MS,
// DWELL_CAP_MS) because they are module-private there. They are pinned
// against the screen's literals by mobile/tests/check-presentation-v2.js §4,
// so a change on one side fails CI rather than drifting.
//
// The one deliberate DIFFERENCE from the deck, recorded so nobody "fixes" it:
// the deck's front-of-deck notion of "viewed" is a single top card. Here the
// hero is the front-of-view card and browse rows are not — a browse row is
// only marked viewed when the user OPENS it. Impressions are still minted
// server-side for every served card either way; what differs is which of them
// earn a `deck_card_viewed` outcome, and "the user actually looked at it" is
// the same claim in both cases.

/** Front-of-view dwell before a card counts as seen. Mirrors
 *  TradesScreen's VIEWED_MIN_MS. */
export const VIEWED_MIN_MS = 500;
/** Dwell ceiling. Mirrors TradesScreen's DWELL_CAP_MS. */
export const DWELL_CAP_MS = 120_000;

/** `user_events.screen` — the surface an event fired from.
 *
 * This is the EXISTING attribution mechanism (the `track()` third argument,
 * a real column, already populated on 100% of client-fired trade events and
 * carrying 12+ distinct values in prod). It is NOT a new analytics property
 * and needs no taxonomy change.
 *
 * It is passed in rather than hardcoded because these two screens must be
 * separable from each other AND from the deck. Hardcoding `'Trades'` here —
 * the value `TradesScreen` already reports — silently merged all three into
 * one bucket, which is the whole reason per-surface comparison looked
 * impossible. */
export type PresentationScreen = 'TodaysTrade' | 'TradeBrowseAll';

function platformProp(): string {
  // Set EXPLICITLY at the emitter, never inferred downstream — the
  // NULL-`platform` incident is why this is written out longhand.
  return Platform.OS === 'android' ? 'android' : Platform.OS === 'web' ? 'web' : 'ios';
}

export interface PresentationSignals {
  /** Call when a card becomes the front-of-view card (hero, or an opened
   *  browse row). Resets dwell + engagement and arms the viewed timer. */
  onCardFronted: (card: TradeCard | null | undefined) => void;
  /** Mark that the user expanded detail on the fronted card. */
  markDetailExpanded: () => void;
  /** Mark that the user opened the calculator from the fronted card. */
  markCalcOpened: () => void;
  /** Record a like/pass. Returns the signal that was sent (or undefined). */
  dispatch: (card: TradeCard, decision: 'like' | 'pass') => SwipeSignal | undefined;
  /** Progressive decline-reason writes — same three commit moments as the deck. */
  reasonLayer1: (card: TradeCard, reason: Layer1Code, switchedFrom: Layer1Code | 'none') => void;
  reasonLayer2Select: (card: TradeCard, reason: Layer1Code, detail: Layer2Code) => void;
  reasonLayer2Bank: (card: TradeCard, reason: Layer1Code, detail: Layer2Code) => void;
  reasonLayer2Send: (
    card: TradeCard,
    reason: Layer1Code,
    detail: Layer2Code,
    freeText: string,
  ) => void;
}

export default function usePresentationSignals(screen: PresentationScreen): PresentationSignals {
  const signalV2On = useFlag('deck.signal_v2');

  const dwellRef = useRef<{ startedAt: number; pausedAt: number | null; pausedTotal: number }>({
    startedAt: Date.now(),
    pausedAt: null,
    pausedTotal: 0,
  });
  const engagementRef = useRef({ detailExpanded: false, calcOpened: false });
  const viewedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const renderedAtRef = useRef<number>(Date.now());

  // Backgrounding must not inflate dwell — same pause/resume contract as the
  // deck's AppState listener.
  useEffect(() => {
    const sub = AppState.addEventListener('change', (st) => {
      const d = dwellRef.current;
      if (st === 'active') {
        if (d.pausedAt != null) {
          d.pausedTotal += Date.now() - d.pausedAt;
          d.pausedAt = null;
        }
      } else if (d.pausedAt == null) {
        d.pausedAt = Date.now();
      }
    });
    return () => sub.remove();
  }, []);

  useEffect(
    () => () => {
      if (viewedTimerRef.current) clearTimeout(viewedTimerRef.current);
    },
    [],
  );

  const currentDwellMs = useCallback((): number => {
    const d = dwellRef.current;
    const end = d.pausedAt ?? Date.now();
    return Math.max(0, Math.min(DWELL_CAP_MS, end - d.startedAt - d.pausedTotal));
  }, []);

  const signalForCard = useCallback(
    (card: TradeCard | undefined): SwipeSignal | undefined => {
      // Identical gate to TradesScreen.signalForCard: the flag AND a served
      // impression_id. No id ⇒ no signal fields ⇒ a POST body byte-identical
      // to the pre-F1 shape, exactly as on the deck.
      if (!signalV2On || !card?.impression_id) return undefined;
      return {
        impression_id: card.impression_id,
        dwell_ms: currentDwellMs(),
        detail_expanded: engagementRef.current.detailExpanded,
        calc_opened: engagementRef.current.calcOpened,
      };
    },
    [signalV2On, currentDwellMs],
  );

  const onCardFronted = useCallback(
    (card: TradeCard | null | undefined) => {
      dwellRef.current = { startedAt: Date.now(), pausedAt: null, pausedTotal: 0 };
      engagementRef.current = { detailExpanded: false, calcOpened: false };
      renderedAtRef.current = Date.now();
      if (viewedTimerRef.current) {
        clearTimeout(viewedTimerRef.current);
        viewedTimerRef.current = null;
      }
      if (!signalV2On || !card?.impression_id) return;
      const impressionId = card.impression_id;
      const tradeId = card.trade_id;
      viewedTimerRef.current = setTimeout(() => {
        viewedTimerRef.current = null;
        track(
          'deck_card_viewed',
          // Same three props the deck sends. `card_index` is 0 here: this
          // surface fronts one card at a time by construction, and the served
          // position already lives on the impression row server-side.
          { impression_id: impressionId, trade_id: tradeId, card_index: 0 },
          screen,
        );
      }, VIEWED_MIN_MS);
    },
    [signalV2On],
  );

  const markDetailExpanded = useCallback(() => {
    engagementRef.current.detailExpanded = true;
  }, []);
  const markCalcOpened = useCallback(() => {
    engagementRef.current.calcOpened = true;
  }, []);

  const dispatch = useCallback(
    (card: TradeCard, decision: 'like' | 'pass') => {
      const signal = signalForCard(card);
      // Fire-and-forget like the deck's mutation: a failed swipe must not
      // wedge the surface. The server is idempotent per (user, trade).
      void swipeTrade(card, decision, signal).catch(() => undefined);
      return signal;
    },
    [signalForCard],
  );

  // ── Decline reasons — the deck's exact three commit moments ─────────────
  const reasonEventProps = useCallback(
    (card: TradeCard) => ({
      impression_id: card.impression_id ?? 'none',
      trade_id: card.trade_id,
      ms_since_render: Math.max(0, Date.now() - renderedAtRef.current),
      platform: platformProp(),
    }),
    [],
  );

  const writeTarget = useCallback(
    (card: TradeCard) => ({
      impressionId: card.impression_id,
      tradeId: card.trade_id,
      leagueId: card.league_id || undefined,
    }),
    [],
  );

  const reasonLayer1 = useCallback(
    (card: TradeCard, reason: Layer1Code, switchedFrom: Layer1Code | 'none') => {
      track('trade_pass_layer1', { reason, switched_from: switchedFrom, ...reasonEventProps(card) }, screen);
      void postDeclineReason({ ...writeTarget(card), layer: 1, reason, switchedFrom });
    },
    [reasonEventProps, writeTarget],
  );

  const reasonLayer2Select = useCallback(
    (card: TradeCard, reason: Layer1Code, detail: Layer2Code) => {
      track('trade_pass_layer2', { reason, detail, has_free_text: false, ...reasonEventProps(card) }, screen);
      void postDeclineReason({ ...writeTarget(card), layer: 2, reason, detail });
    },
    [reasonEventProps, writeTarget],
  );

  // "Other" tapped: bank the code BEFORE the composer opens so a user who
  // bails still leaves "none of the listed reasons". No event here — the
  // funnel counts only the two moments that advance.
  const reasonLayer2Bank = useCallback(
    (card: TradeCard, reason: Layer1Code, detail: Layer2Code) => {
      void postDeclineReason({ ...writeTarget(card), layer: 2, reason, detail });
    },
    [writeTarget],
  );

  const reasonLayer2Send = useCallback(
    (card: TradeCard, reason: Layer1Code, detail: Layer2Code, freeText: string) => {
      track(
        'trade_pass_layer2',
        {
          reason,
          detail,
          // The text is stored on the row only; the event carries the BOOLEAN
          // and nothing else.
          has_free_text: freeText.length > 0,
          ...reasonEventProps(card),
        },
        screen,
      );
      void postDeclineReason({
        ...writeTarget(card),
        layer: 2,
        reason,
        detail,
        freeText: freeText || undefined,
      });
    },
    [reasonEventProps, writeTarget],
  );

  return {
    onCardFronted,
    markDetailExpanded,
    markCalcOpened,
    dispatch,
    reasonLayer1,
    reasonLayer2Select,
    reasonLayer2Bank,
    reasonLayer2Send,
  };
}

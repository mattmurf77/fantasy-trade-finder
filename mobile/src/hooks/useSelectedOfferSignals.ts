import { useCallback, useEffect, useRef, type RefObject } from 'react';
import { AppState, Dimensions, type View } from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { useAppActive } from './useAppActive';
import { useFlag } from '../state/useFeatureFlags';
import { track } from '../api/events';
import type { TradeCard } from '../shared/types';
import { createOfferExposureClock, offerIsVisible } from '../utils/offerExposure';

/** One fronted offer, never a prefetched pager row. Focus/background and
 * measured viewport visibility all gate the existing F1 viewed event. */
export function useSelectedOfferSignals(card: TradeCard | null, screen: string,
  cardIndex: number, measurable: RefObject<View | null>, enabled = true) {
  const focused = useIsFocused();
  const active = useAppActive();
  const signalOn = useFlag('deck.signal_v2');
  const clock = useRef(createOfferExposureClock()).current;
  const live = useRef(false);
  live.current = signalOn && focused && active && enabled;

  useEffect(() => {
    clock.setCard(card, Date.now());
    clock.sample(false, Date.now());
    if (!live.current || !card?.impression_id) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = () => {
      if (cancelled || !live.current) return;
      const node = measurable.current;
      if (!node) {
        clock.sample(false, Date.now());
        timer = setTimeout(poll, 250);
        return;
      }
      node.measureInWindow((x, y, width, height) => {
        if (cancelled || !live.current) return;
        const window = Dimensions.get('window');
        const viewed = clock.sample(AppState.currentState === 'active' &&
          offerIsVisible(x, y, width, height, window.width, window.height), Date.now());
        if (viewed) track('deck_card_viewed', {
          impression_id: viewed.impression_id, trade_id: viewed.trade_id, card_index: cardIndex,
        }, screen);
        timer = setTimeout(poll, 250);
      });
    };
    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      clock.sample(false, Date.now());
    };
  }, [card, cardIndex, focused, active, signalOn,
    enabled, measurable, clock, screen]);

  return useCallback((target: TradeCard) => {
    if (!signalOn) return undefined;
    return clock.signalFor(target, Date.now());
  }, [clock, signalOn]);
}

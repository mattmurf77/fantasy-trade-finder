import type { TradeCard } from '../shared/types';
import type { SwipeSignal } from '../api/trades';

export const OFFER_VIEW_MIN_MS = 500;
const DWELL_CAP_MS = 120_000;

type Offer = Pick<TradeCard, 'trade_id' | 'impression_id' | 'league_id' |
  'opponent_user_id' | 'give_player_ids' | 'receive_player_ids'>;

type OfferPackage = {
  leagueId: string;
  opponentUserId: string;
  giveIds: readonly string[];
  receiveIds: readonly string[];
};

/** Package identity, not canvas history: a changed side or partner cannot
 * borrow the recommendation's impression. Side ordering is immaterial. */
export function isExactOfferPackage(card: Offer | null | undefined, target: OfferPackage): boolean {
  const same = (a: readonly string[], b: readonly string[]) =>
    JSON.stringify([...a].sort()) === JSON.stringify([...b].sort());
  return !!card && card.league_id === target.leagueId &&
    card.opponent_user_id === target.opponentUserId &&
    same(card.give_player_ids, target.giveIds) && same(card.receive_player_ids, target.receiveIds);
}

export function signalForExactTrialPackage(card: TradeCard | null | undefined,
  target: OfferPackage, signalFor: (card: TradeCard) => SwipeSignal | undefined): SwipeSignal | undefined {
  if (!card?.impression_id || card.preserve_server_order !== true ||
      !isExactOfferPackage(card, target)) return undefined;
  return signalFor(card);
}

function offerKey(card: Offer | null | undefined): string | null {
  if (!card?.impression_id) return null;
  return JSON.stringify([card.impression_id, card.trade_id, card.league_id,
    card.opponent_user_id, [...card.give_player_ids].sort(), [...card.receive_player_ids].sort()]);
}

/** Native viewport intersection; mounted or prefetched is not viewed. */
export function offerIsVisible(x: number, y: number, width: number, height: number,
  windowWidth: number, windowHeight: number): boolean {
  if (![x, y, width, height, windowWidth, windowHeight].every(Number.isFinite) ||
      Math.min(width, height, windowWidth, windowHeight) <= 0) return false;
  const w = Math.max(0, Math.min(x + width, windowWidth) - Math.max(x, 0));
  const h = Math.max(0, Math.min(y + height, windowHeight) - Math.max(y, 0));
  return w >= Math.min(width, windowWidth) / 2 && h >= Math.min(height, windowHeight) / 2;
}

/** Clock only: caller supplies measured visibility and time, making pauses,
 * card changes and deduplication executable without React/native timers. */
export function createOfferExposureClock() {
  let key: string | null = null;
  let card: Offer | null = null;
  let lastAt = 0;
  let wasVisible = false;
  let continuousMs = 0;
  let dwellMs = 0;
  const viewed = new Set<string>();
  return {
    setCard(next: Offer | null | undefined, now: number) {
      const nextKey = offerKey(next);
      if (nextKey === key) return;
      key = nextKey;
      card = next ?? null;
      lastAt = now;
      wasVisible = false;
      continuousMs = 0;
      dwellMs = 0;
    },
    sample(visible: boolean, now: number): Offer | null {
      if (key && visible && wasVisible) {
        const elapsed = Math.max(0, now - lastAt);
        continuousMs += elapsed;
        dwellMs = Math.min(DWELL_CAP_MS, dwellMs + elapsed);
      } else if (!visible) {
        continuousMs = 0;
      }
      wasVisible = visible;
      lastAt = now;
      if (!key || !card?.impression_id || !visible || continuousMs < OFFER_VIEW_MIN_MS ||
          viewed.has(card.impression_id)) return null;
      viewed.add(card.impression_id);
      return card;
    },
    signalFor(target: Offer | null | undefined, now: number): SwipeSignal | undefined {
      if (!key || offerKey(target) !== key || !target?.impression_id) return undefined;
      return { impression_id: target.impression_id,
        dwell_ms: Math.min(DWELL_CAP_MS, dwellMs + (wasVisible ? Math.max(0, now - lastAt) : 0)),
        detail_expanded: false, calc_opened: false };
    },
  };
}

import { track } from '../api/events';
import { queueTradeForOpponent, type CalcQueueReason } from '../api/trades';
import { haptics } from './haptics';

// ── The ✓ cell's queue call (D-152), owned in ONE place (D-158, Wave B0) ──
//
// `POST /api/trades/queue` records a hand-built package as the caller's LIKE
// only when the likes-you injector would actually mirror it into @partner's
// deck, so the toast can name WHO refused and WHY instead of the generic
// failure the disabled cell used to stand in for.
//
// This was `TradeCalculatorScreen`'s inline `onLikeTrade` body until D-158
// gave the canvas a second host (`TradesScreen`'s inline mount). The layering
// follows `mobile/src/CLAUDE.md`: the NETWORK call stays in `api/trades.ts`,
// this helper owns the outcome→copy mapping plus the one analytics row and
// the haptic (both derived from the outcome and identical in both hosts), and
// the SCREEN still owns its own Toast state — it renders the descriptor
// returned here. No new event: `calc_trade_queued` keeps its two shapes, and
// only the `screen` label differs between hosts.

export type QueueToast = {
  msg: string;
  tone: 'success' | 'warn' | 'error';
};

// One line per server reason (the enum is a cross-client invariant). Every
// line names whose preference refused it and why, because the alternative —
// a generic "couldn't queue that" — is the dishonest state the cell was
// disabled to avoid. `name` is the counterparty's username, already @-less.
export function queueRefusalLine(
  reason: CalcQueueReason | undefined,
  name: string,
): string {
  switch (reason) {
    case 'opponent_untouchable':
      return `@${name} has someone in this trade marked untouchable.`;
    case 'opponent_not_interested':
      return `@${name} isn't interested in one of the players you're offering.`;
    case 'fails_fairness_floor':
      return `@${name}'s board reads this as a loss for them, so it won't surface.`;
    case 'assets_not_on_roster':
      return 'Those assets are no longer on the rosters this trade needs.';
    case 'not_league_member':
      return `@${name} isn't in this league.`;
    case 'likes_you_off':
      return 'Queueing trades for other managers is turned off right now.';
    default:
      return "Couldn't queue that. Try again.";
  }
}

export async function queueCalcTrade(args: {
  leagueId: string;
  opponent: { userId: string; name: string };
  giveIds: string[];
  receiveIds: string[];
  /** Analytics screen label — the only thing that differs between the two
   *  hosts of the canvas. */
  screen: string;
}): Promise<{ queued: boolean; alreadyQueued?: boolean; toast: QueueToast }> {
  let res: Awaited<ReturnType<typeof queueTradeForOpponent>> | null = null;
  try {
    res = await queueTradeForOpponent({
      leagueId: args.leagueId,
      opponentUserId: args.opponent.userId,
      giveIds: args.giveIds,
      receiveIds: args.receiveIds,
    });
  } catch {
    res = null;
  }
  const queued = !!res?.queued;
  // ONE event, both outcomes. `reason` is absent on a success — the taxonomy
  // allows the prop, the emitter omits it.
  track(
    'calc_trade_queued',
    queued ? { queued: true } : { queued: false, reason: res?.reason ?? 'error' },
    args.screen,
  );
  if (queued) {
    haptics.success();
    return {
      queued: true,
      // The server's own idempotence signal, surfaced so a host can tell a
      // real first queue from a re-✓ of the same package (G22 — the
      // activation-moment hook must not count a repeat as a second like).
      alreadyQueued: !!res?.already_queued,
      toast: {
        msg: res?.already_queued
          ? `Already queued for @${args.opponent.name}.`
          : `Queued for @${args.opponent.name} — it'll show in their suggestions.`,
        tone: 'success',
      },
    };
  }
  haptics.warning();
  return {
    queued: false,
    toast: {
      msg: queueRefusalLine(res?.reason, args.opponent.name),
      tone: res ? 'warn' : 'error',
    },
  };
}

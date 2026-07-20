import type { GuideStep } from '../state/useGuide';

// The Analyst — dialogue script table (source of truth:
// docs/plans/onboarding-conversion/guided-avatar-script.md §3). This file is
// DATA: copy edits land here without touching engine or screen logic. Slots
// are resolved by the small builder functions; every number quoted must come
// from a live value (script §1.3 honesty rule) — each numbered line has a
// no-number variant.

export const S = {
  s0_1: (): GuideStep => ({
    id: 's0.1', screen: 'SignIn', pose: 'neutral', advance: 'tap', once: true,
    line: "Evening. I'm The Analyst — I model dynasty trades. You bring the roster, I bring the math.",
  }),
  s0_2: (): GuideStep => ({
    id: 's0.2', screen: 'SignIn', pose: 'point', flip: true, side: 'right',
    advance: 'action', target: 'signin.username-input', once: true,
    line: 'Type your Sleeper username. No password needed.',
  }),
  s0_err_notfound: (): GuideStep => ({
    id: 's0.err-notfound', screen: 'SignIn', pose: 'oops', advance: 'tap',
    line: "No such username. Common error: that's a team name. Sleeper profile → the @handle. I'll wait.",
  }),
  s0_err_down: (): GuideStep => ({
    id: 's0.err-down', screen: 'SignIn', pose: 'oops', advance: 'tap',
    line: "Sleeper isn't answering. Statistically it comes back. Retry in a moment.",
  }),
  s1_1: (): GuideStep => ({
    id: 's1.1', screen: 'LeaguePicker', pose: 'point', flip: true, side: 'right',
    advance: 'action', once: true,
    line: "Pick the league that matters most. Per my model, that's the one you check at work.",
  }),
  s2_wait: (nOpps: number | null): GuideStep => ({
    id: 's2.wait', screen: 'Trades', pose: 'computing', advance: 'action', once: true,
    line: nOpps
      ? `Running ${nOpps}-roster simulations… first cards land in seconds.`
      : 'Running the league simulations… first cards land in seconds.',
  }),
  s2_1: (): GuideStep => ({
    id: 's2.1', screen: 'Trades', pose: 'celebrate', advance: 'tap', once: true,
    line: "Done. Every card is a trade my model thinks both sides say yes to. This isn't a wishlist — it's a market.",
  }),
  s2_2: (): GuideStep => ({
    id: 's2.2', screen: 'Trades', pose: 'point', advance: 'action',
    target: 'trades.card-body', once: true,
    line: 'Swipe right to take it, left to pass. Every swipe teaches me your taste.',
  }),
  s2_3: (): GuideStep => ({
    id: 's2.3', screen: 'Trades', pose: 'neutral', advance: 'tap',
    target: 'trades.provenance-chip', once: true,
    line: "Logged. Also — see that label? CONSENSUS VALUES. These prices are the market's, not yours. We'll fix that shortly.",
  }),
  s3_1: (): GuideStep => ({
    id: 's3.1', screen: 'Trades', pose: 'thinking', advance: 'tap', once: true,
    line: "Per my model, you and consensus disagree — most GMs do. Right now I'm pricing your players with everyone's numbers.",
  }),
  s3_2: (pos: string, thin: boolean): GuideStep => ({
    id: 's3.2', screen: 'Trades', pose: 'point', advance: 'cta',
    target: 'trades.provenance-chip', side: 'right',
    line:
      `Two minutes on one position and I'll re-price the whole deck with your board.` +
      (thin ? ` Your ${pos} room is the thin one.` : ''),
    ctas: [
      { label: `Fix ${pos} →`, kind: 'primary', action: 'accept' },
      { label: 'Not now', kind: 'ghost', action: 'dismiss' },
    ],
  }),
  s4_1: (): GuideStep => ({
    id: 's4.1', screen: 'QuickSetTiers', pose: 'point', advance: 'tap', once: true,
    line: 'Tap everyone worth the tier label, then Save. Gut calls beat overthinking — for most rosters, tier one is 0–3 names.',
  }),
  s5_1: (nNew: number, pos: string): GuideStep => ({
    id: 's5.1', screen: 'Trades', pose: 'celebrate', advance: 'tap',
    line: `There it is. ${nNew} new trade${nNew === 1 ? '' : 's'} that only exist because of your numbers. Your board, your market.`,
  }),
  s5_0: (pos: string): GuideStep => ({
    id: 's5.0', screen: 'Trades', pose: 'oops', advance: 'tap',
    line: `Honest result: same trades. Your ${pos} board agrees with consensus more than you'd think. More positions = more edge — or your league is just efficient.`,
  }),
  s5_5: (donePos: string, nextPos: string): GuideStep => ({
    id: 's5.5', screen: 'Trades', pose: 'point', flip: true, side: 'right',
    advance: 'cta',
    line: `${donePos} is done. Per my model, ${nextPos} is your next-highest leverage — same drill, two minutes.`,
    ctas: [
      { label: `Rank ${nextPos} next →`, kind: 'primary', action: 'accept' },
      { label: 'Later', kind: 'ghost', action: 'dismiss' },
    ],
  }),
  s6_1: (): GuideStep => ({
    id: 's6.1', screen: 'Trades', pose: 'celebrate', advance: 'auto', autoMs: 2200, once: true,
    line: "First target logged. If they accept, you'll hear it from me first.",
  }),
  s6_2: (): GuideStep => ({
    id: 's6.2', screen: 'Trades', pose: 'neutral', advance: 'auto', autoMs: 2600, once: true,
    line: 'One admin item: sign in with Apple to save your rankings to your account. Takes five seconds.',
  }),
  s7_1: (): GuideStep => ({
    id: 's7.1', screen: 'Trades', pose: 'point', advance: 'tap',
    target: 'trades.trio-entry',
    line: "You've cleared the market. Head-to-heads sharpen your board while we wait for new inventory — 30 seconds at a time.",
  }),
  s8_1: (): GuideStep => ({
    id: 's8.1', screen: 'Trades', pose: 'celebrate', advance: 'tap', once: true,
    line: "That's the tour. I'll keep modeling in the background — you'll see me when the numbers say something worth hearing.",
  }),
  err_burst: (): GuideStep => ({
    id: 'err.burst', screen: 'Trades', pose: 'oops', advance: 'tap',
    line: "Something's broken on my end. Not your fault. Investigating.",
  }),
} as const;

/** Fixed leverage order for the S5.5 next-position ask (client-side proxy
 *  for need_fit leverage — thinnest-first ordering ships with the powered
 *  arm once per-position need is exposed to the client). */
export function nextUnrankedPosition(done: string[]): string | null {
  const order = ['QB', 'RB', 'WR', 'TE'];
  return order.find((p) => !done.includes(p)) ?? null;
}

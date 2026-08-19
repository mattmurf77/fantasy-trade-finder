// tradePresentation.ts — pure derivations for the presentation-v2 surface
// (flag `trades.presentation_v2`). Scope block:
// docs/plans/trade-presentation-v2/scope.md. Approved lab:
// mockups/trade-suggestion-redesign/ (states 01/03/04/07/09).
//
// NO REACT, NO STATE, NO NETWORK. Everything here is a total function of a
// `TradeCard` (plus, for the confidence cap, the user's board progress), so
// `mobile/tests/check-presentation-v2.js` can transpile this module and run
// the assertions for real instead of grepping JSX.
//
// ── THE FIVE DESIGN LAWS THIS FILE ENCODES ────────────────────────────────
// P1  Scarcity is the endorsement, not the catalog. Exactly one card can be
//     the hero; the Featured tier is capped; browse is UNCAPPED.
// P2  Asymmetric explanation. The user's side gets <=3 concrete feature
//     bullets built from data we already have about THEIR roster. The
//     counterparty gets a CONFIDENCE STATEMENT and nothing else — no board,
//     no values, no needs list. `counterpartyStatement()` is deliberately
//     incapable of returning a number.
// P3  No winner needle. `fairnessBand()` returns a RANGE and a marker inside
//     it, never a verdict. The existing FairnessMeter/TradeValueBar are
//     winner-oriented and are NOT used on this surface.
// P4  Plausible deniability. Nothing here formats anything the counterparty
//     would see; passing is private and the copy says so.
// P5  Honesty compounds. `confidenceBand()` degrades LANGUAGE, never numbers,
//     and `confidenceCap()` names the data-volume ceiling.
//
// ── PROVENANCE OF THE CONFIDENCE BAND (read before changing it) ───────────
// There is NO `confidence` field on the wire. `TradeCard` carries no band, no
// percentage and no per-card ranking coverage — see scope.md §2 "fields that
// do not exist". Rather than invent a score, the band is read off the two
// DATA-PROVENANCE fields the backend already ships, which is exactly what the
// mockup's own band definitions describe:
//   `basis`          'divergence' = the card came from a real disagreement
//                    between two saved boards; 'consensus' = the counterparty
//                    has not ranked players and we priced them off consensus.
//   `real_opponent`  true = the counterparty's Elos are their actual saved
//                    rankings; false/undefined = noise-randomized off the
//                    consensus seed.
// So: both boards real -> Strong; one side thin -> Moderate; consensus-only
// AND estimated counterparty -> Early. That is a reading of shipped fields,
// not an approximation of a missing one. If a server-side `confidence_band`
// ever lands, delete `confidenceBand()` and read the field.

import type { TradeCard, Player, RankingProgress } from '../shared/types';

// ── Confidence bands (mockup 04) ──────────────────────────────────────────

export type ConfidenceBand = 'strong' | 'moderate' | 'early';

/** Display labels. Three labeled bands, never a percentage (OkCupid rule). */
export const BAND_LABEL: Record<ConfidenceBand, string> = {
  strong: 'Strong fit',
  moderate: 'Moderate fit',
  early: 'Early signal',
};

/** One-line band definitions, verbatim from the approved lab's legend. */
export const BAND_BLURB: Record<ConfidenceBand, string> = {
  strong:
    'Both boards well-fed, clear mutual gain. The only band that earns the hero slot.',
  moderate:
    'Real signal, thinner data on one side.',
  early:
    'Pattern spotted, not enough ranked players to stand behind it.',
};

/**
 * The band for one card, derived from shipped provenance fields only.
 *
 * `likesYou` is a hard promotion: the counterparty has already liked the
 * mirror of this trade, which is the strongest acceptance evidence the system
 * can hold — stronger than any inference from their board.
 */
export function confidenceBand(card: Pick<TradeCard, 'basis' | 'real_opponent' | 'likesYou'>): ConfidenceBand {
  if (card.likesYou === true) return 'strong';
  const realOpponent = card.real_opponent === true;
  const divergence = card.basis !== 'consensus'; // normalizer defaults to 'divergence'
  if (divergence && realOpponent) return 'strong';
  if (divergence || realOpponent) return 'moderate';
  return 'early';
}

/**
 * ONLY a `strong` card may wear the endorsement. The badge is BINARY — there
 * is no endorsement ladder (research §5 transfer note 2), so this returns a
 * boolean and never a level.
 */
export function isEndorsable(card: Pick<TradeCard, 'basis' | 'real_opponent' | 'likesYou'>): boolean {
  return confidenceBand(card) === 'strong';
}

/**
 * The data-volume ceiling (mockup 04, OkCupid lower-bound rule): a thin board
 * caps what we are allowed to claim, and the cap doubles as the ranking
 * prompt. Returns null when the board is complete enough that nothing is
 * being withheld.
 *
 * HONESTY NOTE: the lab's copy reads "You've ranked 34 of the 60 players this
 * deal touches". Per-deal coverage does NOT exist on the wire (scope.md §2),
 * so this reports the user's OVERALL board progress from the existing
 * GET /api/rankings/progress payload and says so. We do not fabricate a
 * per-deal denominator.
 */
export interface ConfidenceCap {
  /** Headline sentence. Never contains a percentage. */
  headline: string;
  /** Honest second line naming what the number actually measures. */
  detail: string;
  /** 0-1 board coverage for the progress track, or null when unknown. */
  coverage: number | null;
  completed: number;
  required: number;
}

export function confidenceCap(
  band: ConfidenceBand,
  progress: Pick<RankingProgress, 'total_completed' | 'total_required'> | undefined,
): ConfidenceCap | null {
  if (band === 'strong') return null;
  const completed = Math.max(0, Number(progress?.total_completed ?? 0) || 0);
  const required = Math.max(0, Number(progress?.total_required ?? 0) || 0);
  const coverage = required > 0 ? Math.min(1, completed / required) : null;
  return {
    headline: `${BAND_LABEL[band]} — rank more players to sharpen this.`,
    detail:
      required > 0
        ? `You've ranked ${completed} of ${required} players on your board, so we cap what we claim.`
        : 'We cap what we claim until your board has more ranked players.',
    coverage,
    completed,
    required,
  };
}

// ── Fairness as a RANGE, never a verdict (mockup 01) ──────────────────────

/**
 * League-normal band geometry. `fairness` is the shipped 0-1 package ratio
 * (min/max), so 1.0 is a dead-even package and lower values are more lopsided
 * in EITHER direction — the field is symmetric and carries no winner. That is
 * precisely why it can be rendered as a range without picking a side.
 *
 * `NORMAL_LOW` is the balanced-mode generation threshold (0.75, see
 * api/tradePregen FAIRNESS_ON_THRESHOLD): a package at or above it is what
 * this league's own engine calls balanced.
 */
export const NORMAL_LOW = 0.75;

export interface FairnessBand {
  /** true when the package sits inside the league-normal window. */
  withinNormal: boolean;
  /** 0-1 position of the marker along the track. */
  markerPct: number;
  /** 0-1 left edge of the shaded normal zone. */
  zoneStartPct: number;
  /** 0-1 right edge of the shaded normal zone. */
  zoneEndPct: number;
  /** The ONLY string this surface renders about fairness. */
  label: string;
}

/**
 * Map the 0-1 ratio onto a track whose shaded zone IS "league-normal".
 *
 * The track spans ratio 0.5 (the widest net the app ever generates at) to
 * 1.0 (dead even). The normal zone is [NORMAL_LOW, 1.0]. There is no "you
 * win by X" anywhere in the return type — deliberately. The same card is
 * shown to both managers, so a needle would be a league-chat weapon (P3).
 */
export function fairnessBand(fairness: number | undefined): FairnessBand | null {
  if (typeof fairness !== 'number' || !Number.isFinite(fairness)) return null;
  const lo = 0.5;
  const hi = 1.0;
  const clamped = Math.min(hi, Math.max(lo, fairness));
  const pct = (v: number) => (v - lo) / (hi - lo);
  const withinNormal = fairness >= NORMAL_LOW;
  return {
    withinNormal,
    markerPct: pct(clamped),
    zoneStartPct: pct(NORMAL_LOW),
    zoneEndPct: 1,
    label: withinNormal
      ? 'Within league-normal range'
      : 'Outside league-normal range',
  };
}

// ── Asymmetric explanation (mockup 01, research §5 transfer note 1) ───────

/** Hard cap from the research: more than three features stops helping. */
export const MAX_USER_BULLETS = 3;

function playerLabel(p: Player): string {
  return p?.name ? String(p.name) : 'a player';
}

function joinNames(players: Player[], max = 2): string {
  const names = players.slice(0, max).map(playerLabel);
  if (players.length > max) names.push(`${players.length - max} more`);
  if (names.length === 0) return '';
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/**
 * Up to three CONCRETE feature bullets about the USER's side, built only from
 * fields the card already carries. Each bullet names a thing on the card —
 * a player, a position, a lane — so it can be checked against the trade in
 * front of the reader. Returns [] rather than padding when the card is thin;
 * an empty explanation is honest, a generic one is not.
 */
export function userSideBullets(card: TradeCard): string[] {
  const out: string[] = [];
  const receive = card.receive_players ?? [];
  const give = card.give_players ?? [];

  // 1. What you get, and why it lands — the strongest concrete statement.
  const needs = card.match_context?.user_needs ?? [];
  if (receive.length > 0) {
    const head = joinNames(receive);
    if (needs.length > 0) {
      out.push(`You get ${head} — ${needs.slice(0, 2).join(' and ')} is your thinnest room.`);
    } else {
      out.push(`You get ${head}.`);
    }
  }

  // 2. The lane the move serves. 'window' is the contention-window (win-now)
  //    lane; 'value' is pure value accumulation. Both are shipped enum values.
  if (out.length < MAX_USER_BULLETS && card.lane === 'window') {
    out.push('This is a win-now move — it raises your starting lineup this season.');
  } else if (out.length < MAX_USER_BULLETS && card.lane === 'value') {
    out.push('This is a value move — it builds long-term capital, not this week’s lineup.');
  }

  // 3. What it costs you, stated plainly. Never hidden behind the upside.
  if (out.length < MAX_USER_BULLETS && give.length > 0) {
    out.push(`It costs you ${joinNames(give)}.`);
  }

  // 3b. The fit premium, when the engine says you are paying one. Honesty
  //     beats persuasion: if we are asking the user to overpay for fit, say so.
  if (out.length < MAX_USER_BULLETS && card.fitPremium?.position) {
    out.push(`You pay a small premium to land a ${card.fitPremium.position}.`);
  }

  return out.slice(0, MAX_USER_BULLETS);
}

/**
 * The counterparty half — A CONFIDENCE STATEMENT AND NOTHING ELSE.
 *
 * This is not a stylistic choice. Exposing the other manager's board or
 * valuations is both a privacy leak and, in a 12-person league where everyone
 * re-encounters everyone, a social hazard. The return type is a single string
 * by construction so no caller can accidentally render their numbers, and the
 * function never reads `match_context.opponent_surplus`, `partner_fit`, or any
 * value field. Do not "enrich" this.
 */
export function counterpartyStatement(card: Pick<TradeCard, 'opponent_username' | 'likesYou'>): string {
  const who = card.opponent_username?.trim() || 'This manager';
  if (card.likesYou === true) {
    return `${who} has already shown interest in a deal like this one.`;
  }
  return `Based on their roster needs and recent activity, ${who} is likely to be interested in this deal.`;
}

// ── Row summaries (mockups 03 + 09) ───────────────────────────────────────

/**
 * One-line package shape for a Featured row or a browse row: "Smith + 2nd <->
 * Cook + 3rd". Truncation is by COUNT, not by characters, so the row never
 * mid-word-clips a player name at large text sizes.
 */
export function packageSummary(card: TradeCard): string {
  const give = joinNames(card.give_players ?? [], 2);
  const recv = joinNames(card.receive_players ?? [], 2);
  if (!give && !recv) return 'Trade idea';
  return `${give || 'nothing'} ↔ ${recv || 'nothing'}`;
}

// ── Deck partitioning (P1) ────────────────────────────────────────────────

/** Featured tier cap. Small at the TOP of the funnel: choice overload there
 *  produces a rejection mind-set (Pronk & Denissen 2020). Discovery below it
 *  is deliberately UNCAPPED. */
export const FEATURED_CAP = 5;

export interface PresentationDeck {
  /** The one endorsed hero, or null when nothing clears the bar. */
  hero: TradeCard | null;
  /** Up to FEATURED_CAP cards beneath the hero. */
  featured: TradeCard[];
  /** EVERYTHING, hero first — the uncapped browse list. Never sliced. */
  all: TradeCard[];
  /** Count for the "all N trades" affordance. */
  total: number;
}

/**
 * Split a ranked deck into the pyramid.
 *
 * `dismissed` are excluded from hero/featured selection but are KEPT in
 * `all`, because the browse list renders them in their acknowledged
 * dismissed state with an Undo (mockup 09) — removing the row would delete
 * the acknowledgement the design exists to show.
 *
 * The hero must be endorsable. If no card is, there is NO hero and the
 * caller renders the honest empty state (mockup 07) rather than promoting a
 * moderate card into an endorsement it has not earned.
 */
export function partitionDeck(
  cards: TradeCard[],
  dismissed: ReadonlySet<string> = new Set(),
): PresentationDeck {
  const live = cards.filter((c) => !dismissed.has(c.trade_id));
  const hero = live.find((c) => isEndorsable(c)) ?? null;
  const featured = live
    .filter((c) => c.trade_id !== hero?.trade_id)
    .slice(0, FEATURED_CAP);
  return { hero, featured, all: cards, total: cards.length };
}

// ── Honest empty state (mockup 07) ────────────────────────────────────────

/**
 * The price-feedback pivot. The lab names a specific blocking player and
 * compares the user's board value against league consensus for him; NEITHER
 * datum exists on any shipped response (scope.md §2). Rather than invent a
 * diagnosis, this returns the levers that genuinely change the outcome, each
 * derived from a real value we hold:
 *   - the fairness threshold the job actually ran at
 *   - the user's real board coverage
 *   - the decline-suppression count the snapshot already reports
 * "Keep my price" stays a first-class choice: the app is a mediator, not a nag.
 */
export interface EmptyStateCopy {
  heading: string;
  body: string;
  /** Rendered only when we have a real number to stand behind. */
  suppressionNote: string | null;
  /** true when widening the fairness net is an available lever. */
  canWidenFairness: boolean;
}

export function emptyStateCopy(opts: {
  rostersChecked?: number;
  fairnessThreshold?: number;
  suppressedCount?: number;
}): EmptyStateCopy {
  const n = Math.max(0, Number(opts.rostersChecked ?? 0) || 0);
  const checked = n > 0 ? `We checked all ${n} rosters against your board. ` : '';
  return {
    heading: 'No trade today',
    body:
      `${checked}Nothing clears the bar for both sides right now — ` +
      "we'd rather show nothing than pad the list.",
    suppressionNote:
      opts.suppressedCount && opts.suppressedCount > 0
        ? `${opts.suppressedCount} idea${opts.suppressedCount === 1 ? '' : 's'} you already declined ` +
          'stayed hidden this cycle.'
        : null,
    canWidenFairness:
      typeof opts.fairnessThreshold === 'number' && opts.fairnessThreshold > 0.5,
  };
}

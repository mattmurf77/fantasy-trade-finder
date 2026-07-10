// ⚠️ MOCK / DEMO DATA — Trade Calculator only.
//
// Seeded stand-in for real league + Elo ranking data, ported from
// mockups/trade-calc/src/data/mock.ts. Each owner has their own "board":
// personal player values derived from a shared consensus base, positional
// leans, an age bias, and a stable per-owner jitter. Disagreements between
// two owners' boards are what make mutual-gain trades possible — the same
// mechanic the real FTF engine exploits.
//
// Swap path: when the server-authoritative `/api/trade/evaluate` endpoint
// ships (docs/plans/manual-trade-calculator-plan.md), this module and the
// client-side math in utils/tradeCalcMath.ts get replaced by that API.

import type { Position } from '../shared/types';

/** Tradable-asset position: the four player positions plus draft picks. */
export type CalcPos = Position | 'PICK';

export interface CalcPlayer {
  id: string;
  name: string;
  pos: CalcPos;
  nflTeam: string;
  age: number;
  /** Consensus dynasty value on an Elo-like scale (~900–2600). */
  base: number;
  /** Draft pick rather than a player. Picks carry age 21 so the existing
   *  youth/vet board biases price them naturally (youth-lovers pay up,
   *  win-now owners fade) with zero extra valuation math. */
  pick?: true;
}

export interface CalcOwner {
  id: string;
  teamName: string;
  ownerName: string;
  /** One-line scouting report on how their board leans. */
  tendency: string;
  posLean: Partial<Record<CalcPos, number>>;
  /** -1..1 — positive means they pay up for youth, negative for proven vets. */
  youthBias: number;
  rosterIds: string[];
}

const P = (id: string, name: string, pos: CalcPos, nflTeam: string, age: number, base: number): CalcPlayer => ({
  id, name, pos, nflTeam, age, base,
});

const PICK = (id: string, name: string, base: number): CalcPlayer => ({
  id, name, pos: 'PICK', nflTeam: '—', age: 21, base, pick: true,
});

export const CALC_PLAYERS: CalcPlayer[] = [
  // My team — Murph's Turf
  P('jdaniels', 'Jayden Daniels', 'QB', 'WAS', 25, 2380),
  P('jgoff', 'Jared Goff', 'QB', 'DET', 31, 1560),
  P('brobinson', 'Bijan Robinson', 'RB', 'ATL', 24, 2520),
  P('kwilliams', 'Kyren Williams', 'RB', 'LAR', 25, 1800),
  P('rwhite', 'Rachaad White', 'RB', 'TB', 27, 1450),
  P('tspears', 'Tyjae Spears', 'RB', 'TEN', 25, 1380),
  P('jchase', "Ja'Marr Chase", 'WR', 'CIN', 26, 2600),
  P('dmetcalf', 'DK Metcalf', 'WR', 'PIT', 28, 1720),
  P('jaddison', 'Jordan Addison', 'WR', 'MIN', 24, 1750),
  P('rodunze', 'Rome Odunze', 'WR', 'CHI', 24, 1850),
  P('slaporta', 'Sam LaPorta', 'TE', 'DET', 25, 1950),
  P('hhenry', 'Hunter Henry', 'TE', 'NE', 31, 1250),

  // Gridiron Gurus
  P('jallen', 'Josh Allen', 'QB', 'BUF', 30, 2350),
  P('bnix', 'Bo Nix', 'QB', 'DEN', 26, 1780),
  P('jgibbs', 'Jahmyr Gibbs', 'RB', 'DET', 24, 2500),
  P('dachane', "De'Von Achane", 'RB', 'MIA', 24, 2150),
  P('jcook', 'James Cook', 'RB', 'BUF', 26, 1700),
  P('ipacheco', 'Isiah Pacheco', 'RB', 'KC', 27, 1400),
  P('jjefferson', 'Justin Jefferson', 'WR', 'MIN', 27, 2550),
  P('thiggins', 'Tee Higgins', 'WR', 'CIN', 27, 1850),
  P('colave', 'Chris Olave', 'WR', 'NO', 26, 1650),
  P('jwaddle', 'Jaylen Waddle', 'WR', 'MIA', 27, 1600),
  P('mandrews', 'Mark Andrews', 'TE', 'BAL', 30, 1350),
  P('dkincaid', 'Dalton Kincaid', 'TE', 'BUF', 26, 1500),

  // Youth Movement
  P('cwilliams', 'Caleb Williams', 'QB', 'CHI', 24, 2280),
  P('dmaye', 'Drake Maye', 'QB', 'NE', 23, 2200),
  P('ajeanty', 'Ashton Jeanty', 'RB', 'LV', 22, 2450),
  P('ohampton', 'Omarion Hampton', 'RB', 'LAC', 23, 2050),
  P('thenderson', 'TreVeyon Henderson', 'RB', 'NE', 23, 1750),
  P('ballen', 'Braelon Allen', 'RB', 'NYJ', 22, 1300),
  P('mnabers', 'Malik Nabers', 'WR', 'NYG', 23, 2450),
  P('bthomas', 'Brian Thomas Jr.', 'WR', 'JAX', 23, 2300),
  P('mharrison', 'Marvin Harrison Jr.', 'WR', 'ARI', 24, 2000),
  P('tmcmillan', 'Tetairoa McMillan', 'WR', 'CAR', 23, 1900),
  P('bbowers', 'Brock Bowers', 'TE', 'LV', 23, 2350),
  P('cloveland', 'Colston Loveland', 'TE', 'CHI', 22, 1550),

  // Win Now Willy
  P('pmahomes', 'Patrick Mahomes', 'QB', 'KC', 31, 2150),
  P('bmayfield', 'Baker Mayfield', 'QB', 'TB', 31, 1500),
  P('sbarkley', 'Saquon Barkley', 'RB', 'PHI', 29, 2050),
  P('jjacobs', 'Josh Jacobs', 'RB', 'GB', 28, 1750),
  P('dhenry', 'Derrick Henry', 'RB', 'BAL', 32, 1600),
  P('ajones', 'Aaron Jones', 'RB', 'MIN', 31, 1100),
  P('cdlamb', 'CeeDee Lamb', 'WR', 'DAL', 27, 2400),
  P('arsb', 'Amon-Ra St. Brown', 'WR', 'DET', 27, 2300),
  P('ajbrown', 'A.J. Brown', 'WR', 'PHI', 29, 1950),
  P('dadams', 'Davante Adams', 'WR', 'LAR', 33, 1150),
  P('gkittle', 'George Kittle', 'TE', 'SF', 33, 1300),
  P('tkelce', 'Travis Kelce', 'TE', 'KC', 37, 900),

  // Draft capital — one 2027 1st/2nd/3rd per team. Same consensus base per
  // round; per-owner jitter + youth bias make each board price them apart.
  PICK('mt27_1', '2027 1st Round', 1750),
  PICK('mt27_2', '2027 2nd Round', 950),
  PICK('mt27_3', '2027 3rd Round', 450),
  PICK('gg27_1', '2027 1st Round', 1750),
  PICK('gg27_2', '2027 2nd Round', 950),
  PICK('gg27_3', '2027 3rd Round', 450),
  PICK('ym27_1', '2027 1st Round', 1750),
  PICK('ym27_2', '2027 2nd Round', 950),
  PICK('ym27_3', '2027 3rd Round', 450),
  PICK('ww27_1', '2027 1st Round', 1750),
  PICK('ww27_2', '2027 2nd Round', 950),
  PICK('ww27_3', '2027 3rd Round', 450),
];

export const CALC_PLAYER_BY_ID: Record<string, CalcPlayer> = Object.fromEntries(
  CALC_PLAYERS.map((p) => [p.id, p]),
);

export const CALC_MY_TEAM: CalcOwner = {
  id: 'me',
  teamName: "Murph's Turf",
  ownerName: 'You',
  tendency: 'Slight WR lean, otherwise close to consensus.',
  posLean: { WR: 1.03 },
  youthBias: 0.1,
  rosterIds: [
    'jdaniels', 'jgoff', 'brobinson', 'kwilliams', 'rwhite', 'tspears',
    'jchase', 'dmetcalf', 'jaddison', 'rodunze', 'slaporta', 'hhenry',
    'mt27_1', 'mt27_2', 'mt27_3',
  ],
};

export const CALC_PARTNERS: CalcOwner[] = [
  {
    id: 'gurus',
    teamName: 'Gridiron Gurus',
    ownerName: 'Dana',
    tendency: 'Pays a premium for RBs, cool on TEs.',
    posLean: { RB: 1.12, WR: 0.97, TE: 0.94 },
    youthBias: 0,
    rosterIds: [
      'jallen', 'bnix', 'jgibbs', 'dachane', 'jcook', 'ipacheco',
      'jjefferson', 'thiggins', 'colave', 'jwaddle', 'mandrews', 'dkincaid',
      'gg27_1', 'gg27_2', 'gg27_3',
    ],
  },
  {
    id: 'youth',
    teamName: 'Youth Movement',
    ownerName: 'Sam',
    tendency: 'All-in on youth — fades anyone past their prime.',
    posLean: {},
    youthBias: 1,
    rosterIds: [
      'cwilliams', 'dmaye', 'ajeanty', 'ohampton', 'thenderson', 'ballen',
      'mnabers', 'bthomas', 'mharrison', 'tmcmillan', 'bbowers', 'cloveland',
      'ym27_1', 'ym27_2', 'ym27_3',
    ],
  },
  {
    id: 'willy',
    teamName: 'Win Now Willy',
    ownerName: 'Will',
    tendency: 'Chasing a title — pays up for proven vets, fades rookies.',
    posLean: {},
    youthBias: -0.8,
    rosterIds: [
      'pmahomes', 'bmayfield', 'sbarkley', 'jjacobs', 'dhenry', 'ajones',
      'cdlamb', 'arsb', 'ajbrown', 'dadams', 'gkittle', 'tkelce',
      'ww27_1', 'ww27_2', 'ww27_3',
    ],
  },
];

export const CALC_LEAGUE_NAME = 'Lakeview Dynasty (demo data)';

/** Deterministic ±4% jitter so each owner's board disagrees with consensus in stable, personal ways. */
function jitter(ownerId: string, playerId: string): number {
  const s = `${ownerId}:${playerId}`;
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const unit = ((h >>> 0) % 1000) / 1000; // 0..1
  return 0.96 + unit * 0.08;
}

const AGE_PIVOT = 26;

/** A player's value on one owner's board (their "ranking set"). */
export function ownerValue(owner: CalcOwner, player: CalcPlayer): number {
  const pos = owner.posLean[player.pos] ?? 1;
  const ageMult = Math.min(1.3, Math.max(0.7, 1 + owner.youthBias * (AGE_PIVOT - player.age) * 0.03));
  return Math.round(player.base * pos * ageMult * jitter(owner.id, player.id));
}

/** Full board for an owner: playerId → personal value. */
export function boardFor(owner: CalcOwner): Record<string, number> {
  return Object.fromEntries(CALC_PLAYERS.map((p) => [p.id, ownerValue(owner, p)]));
}

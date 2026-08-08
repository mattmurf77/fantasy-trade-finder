import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';

import { getLeagueRosters } from '../api/sleeper';
import { getLeagueCoverage, getLeaguePicks, getPowerRankings } from '../api/league';
import {
  evaluateTradeInLeague,
  evaluateTradesInLeague,
  getTradeValues,
  type CalcEvaluationInLeague,
  type CalcEvener,
  type TradeProbe,
} from '../api/calc';
import {
  evalFromBoards,
  evalFromConsensus,
  rankAddOnCandidates,
  rankGapCandidates,
  type CalcSuggestion,
} from '../utils/tradeCalcMath';
import TradeSide from './TradeSide';
import TradeValueBar from './TradeValueBar';
import PlayerPickerModal, { type SuggestedPlayer } from './PlayerPickerModal';
import SuggestionCard from './SuggestionCard';
import EvenerRows from './EvenerRows';
import AdjustmentsDisclosure from './AdjustmentsDisclosure';
import SendInSleeperButton from './SendInSleeperButton';
import ShareTradeImage, { type ShareAsset } from './ShareTradeImage';
import { Badge, Button, Card, Icon, Text as ChalkText, TickLabel } from './chalkline';
import { haptics } from '../utils/haptics';
import { useSession } from '../state/useSession';
import { chalk, fonts, ice, ink, radii, semantic, space, type } from '../theme/chalkline';
import { posColor, type Position } from '../theme/colors';
import type { CalcPlayer, CalcPos } from '../data/tradeCalcMock';
import type { ScoringFormat, StarterImpactSlot } from '../shared/types';

// In-league calculator (Mode B, docs/plans/manual-trade-calculator-plan.md).
// The FTF differentiator applied to a hand-built trade: pick a real opponent,
// assemble a trade from BOTH rosters, and evaluate it by BOTH owners' real
// rankings (POST /api/trade/evaluate with league_id + opponent_user_id). It's
// the one calculator surface with a real league + opponent, so it carries the
// "Send in Sleeper" button.

interface Props {
  leagueId: string;
  userId: string;
  // #190 — optional prefill from the trade deck's "Edit in calculator"
  // (TradeCalculatorScreen threads route params through). Initial values
  // only — this component owns all state after mount.
  initialOpponentId?: string;
  initialGiveIds?: string[];
  initialReceiveIds?: string[];
}

const FORMATS: { key: ScoringFormat; label: string }[] = [
  { key: '1qb_ppr', label: '1QB PPR' },
  { key: 'sf_tep', label: 'SF TEP' },
];
const FORMAT_LABEL: Record<string, string> = {
  '1qb_ppr': '1QB PPR',
  sf_tep: 'SF TEP',
};
// Partner-summary display order (DTF teardown 2026-07-27).
const POSITIONS: Position[] = ['QB', 'RB', 'WR', 'TE'];

// #192 — partner ranked-status, rendered as a small text badge instead of
// the old (misleading) flare dot: R = ranked in the active calculator
// format, R* = ranked only in the other format (board derived via #191
// cross-format value mapping), NR = never ranked. Old servers without
// ranked_formats degrade to the format-blind R/NR pair.
type RankState = 'R' | 'R*' | 'NR';
function rankStateFor(
  m: { has_rankings: boolean; ranked_formats?: string[] },
  format: ScoringFormat,
): RankState {
  if (Array.isArray(m.ranked_formats)) {
    if (m.ranked_formats.includes(format)) return 'R';
    if (m.ranked_formats.length > 0) return 'R*';
    return 'NR';
  }
  return m.has_rankings ? 'R' : 'NR';
}
const RANK_STATE_A11Y: Record<RankState, string> = {
  R: 'ranked',
  'R*': 'ranked in another format, values converted',
  NR: 'not ranked',
};

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function InLeagueCalculator({
  leagueId,
  userId,
  initialOpponentId,
  initialGiveIds,
  initialReceiveIds,
}: Props) {
  // #166/#167 — the format defaults to the LEAGUE's detected scoring
  // format (useSession.activeFormat, kept league-accurate by
  // useLeagueFormatDefault in RootNav), not a hard-coded 1QB PPR. A chip
  // tap still overrides for this calculator session; the override is
  // local so it never stomps the app-wide format.
  const sessionFormat = useSession((s) => s.activeFormat);
  const [formatChoice, setFormatChoice] = useState<ScoringFormat | null>(null);
  const format: ScoringFormat = formatChoice ?? sessionFormat ?? '1qb_ppr';
  // #190 — "Edit in calculator" prefill from a suggested trade card.
  const [opponentId, setOpponentId] = useState<string | null>(initialOpponentId ?? null);
  const [giveIds, setGiveIds] = useState<string[]>(initialGiveIds ?? []);
  const [receiveIds, setReceiveIds] = useState<string[]>(initialReceiveIds ?? []);
  const [picker, setPicker] = useState<'give' | 'receive' | null>(null);
  // #202 — a prefilled mount (deck "Edit in calculator") already made the
  // partner decision, so the picker section collapses to one compact row
  // ("Trading with @x · Change") and the trade itself leads. "Change"
  // expands today's chips; no-prefill mounts keep today's layout.
  const [partnerCollapsed, setPartnerCollapsed] = useState(!!initialOpponentId);

  const valuesQ = useQuery({
    queryKey: ['calc-values', format],
    queryFn: ({ signal }) => getTradeValues(format, signal),
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });
  const rostersQ = useQuery({
    queryKey: ['league-rosters', leagueId],
    queryFn: () => getLeagueRosters(leagueId),
    staleTime: 5 * 60_000,
  });
  const coverageQ = useQuery({
    queryKey: ['league-coverage', leagueId],
    queryFn: () => getLeagueCoverage(leagueId),
    staleTime: 5 * 60_000,
  });
  // #158 — owned draft picks for this league (per-owner, engine-scale values).
  // Empty when the picks.owned_sync flag is off (no rows synced); ESPN leagues
  // return picks_supported=false so we can render an honest note.
  const picksQ = useQuery({
    queryKey: ['league-picks', leagueId],
    queryFn: () => getLeaguePicks(leagueId),
    staleTime: 5 * 60_000,
  });
  // Partner positional summary (DTF teardown 2026-07-27): one consensus
  // power-rankings read already carries every team's per-position values +
  // draft capital — same queryKey as LeagueSummaryScreen, so a league the
  // user has viewed costs nothing here. Silent-fail enrichment: no data →
  // the chips render exactly as before.
  const powerQ = useQuery({
    queryKey: ['league-power-rankings', leagueId, 'consensus'],
    queryFn: () => getPowerRankings(leagueId, 'consensus'),
    staleTime: 5 * 60_000,
  });
  const partnerSummaries = useMemo(() => {
    const m: Record<
      string,
      { pos: Record<Position, number>; picks: number | null }
    > = {};
    for (const t of powerQ.data?.teams ?? []) {
      m[t.user_id] = {
        pos: {
          QB: t.positions?.QB?.value ?? 0,
          RB: t.positions?.RB?.value ?? 0,
          WR: t.positions?.WR?.value ?? 0,
          TE: t.positions?.TE?.value ?? 0,
        },
        picks: t.picks && t.picks.count > 0 ? t.picks.value : null,
      };
    }
    return m;
  }, [powerQ.data]);
  // #203 — cheapest honest need signal: league-relative positional weakness
  // from the SAME power-rankings read as the partner summaries (no caller-only
  // /api/league/preferences call can serve the OPPONENT's needs). A position
  // is a "need" for a team when its positional value ranks in the league's
  // bottom third. Works symmetrically for the opponent (adding to what you
  // send) and for you (adding to what you receive).
  const needsByTeam = useMemo(() => {
    const teams = powerQ.data?.teams ?? [];
    const m: Record<string, Position[]> = {};
    for (const pos of POSITIONS) {
      const sorted = [...teams].sort(
        (a, b) => (b.positions?.[pos]?.value ?? 0) - (a.positions?.[pos]?.value ?? 0),
      );
      const cut = Math.ceil((sorted.length * 2) / 3);
      for (const t of sorted.slice(cut)) (m[t.user_id] ??= []).push(pos);
    }
    return m;
  }, [powerQ.data]);

  // A CalcPlayer per owned pick, keyed by pick_id, priced at pool_value.
  const pickById = useMemo(() => {
    const m: Record<string, CalcPlayer> = {};
    for (const p of picksQ.data?.all_picks ?? []) {
      m[p.pick_id] = {
        id: p.pick_id,
        name: p.label,
        pos: 'PICK',
        nflTeam: 'PICK',
        age: 0,
        base: p.pool_value ?? 0,
      };
    }
    return m;
  }, [picksQ.data]);
  const picksByOwner = useMemo(() => {
    const m: Record<string, CalcPlayer[]> = {};
    for (const p of picksQ.data?.all_picks ?? []) {
      const cp = pickById[p.pick_id];
      if (cp) (m[p.owner_user_id] ??= []).push(cp);
    }
    return m;
  }, [picksQ.data, pickById]);
  const picksSupported = picksQ.data?.picks_supported ?? true;

  const board = useMemo<Record<string, number>>(
    () => ({
      ...Object.fromEntries((valuesQ.data?.players ?? []).map((r) => [r.id, r.value])),
      ...Object.fromEntries(Object.values(pickById).map((p) => [p.id, p.base])),
    }),
    [valuesQ.data, pickById],
  );
  const playerById = useMemo(() => {
    const m: Record<string, CalcPlayer> = {};
    for (const r of valuesQ.data?.players ?? []) {
      m[r.id] = {
        id: r.id,
        name: r.name,
        pos: r.position as CalcPos,
        nflTeam: r.team ?? '—',
        age: r.age ?? 0,
        base: r.value,
      };
    }
    // Owned picks are selectable assets too — merge so TradeSide + evaluate
    // resolve their labels/values alongside players.
    for (const p of Object.values(pickById)) m[p.id] = p;
    return m;
  }, [valuesQ.data, pickById]);

  const rosterByOwner = useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const row of rostersQ.data ?? []) if (row.owner_id) m[row.owner_id] = row.players ?? [];
    return m;
  }, [rostersQ.data]);

  const opponents = useMemo(
    () => (coverageQ.data?.members ?? []).filter((mm) => mm.user_id !== userId),
    [coverageQ.data, userId],
  );

  // Default to the first opponent once the list loads.
  useEffect(() => {
    if (!opponentId && opponents.length) setOpponentId(opponents[0].user_id);
  }, [opponents, opponentId]);

  // Their roster changed → what you'd receive no longer applies. Skips
  // the mount run (guard ref) so a #190 prefill isn't wiped before it
  // renders — the mount run was always a no-op before prefill existed.
  const prevOpponentRef = useRef(opponentId);
  useEffect(() => {
    if (prevOpponentRef.current === opponentId) return;
    prevOpponentRef.current = opponentId;
    setReceiveIds([]);
    setPicker(null);
  }, [opponentId]);

  const opponent = opponents.find((o) => o.user_id === opponentId) ?? null;
  // #202 — collapse only while the prefilled partner actually resolves;
  // an unknown initialOpponentId falls back to the full picker.
  const collapsedPartner = partnerCollapsed && !!opponent;
  const myPoolPlayers = [
    ...((rosterByOwner[userId] ?? []).map((id) => playerById[id]).filter(Boolean) as CalcPlayer[]),
    ...(picksByOwner[userId] ?? []),
  ];
  const oppPoolPlayers = [
    ...((opponentId ? rosterByOwner[opponentId] ?? [] : [])
      .map((id) => playerById[id])
      .filter(Boolean) as CalcPlayer[]),
    ...(opponentId ? picksByOwner[opponentId] ?? [] : []),
  ];

  const debGive = useDebounced(giveIds, 250);
  const debReceive = useDebounced(receiveIds, 250);
  const evalQ = useQuery({
    queryKey: ['calc-eval-league', leagueId, opponentId, format, debGive.join('+'), debReceive.join('+')],
    queryFn: ({ signal }) =>
      // #264 — one_sided_eveners: with only one side filled there is no gap
      // to hang eveners on, so the server builds candidates for the EMPTY
      // side instead (its owner's roster + owned picks, sized against the
      // filled side). That's what makes the calculator offer trade options
      // while a trade is still half-built. Two-sided reads are unchanged.
      evaluateTradeInLeague(debGive, debReceive, format, leagueId, opponentId!, signal, true),
    enabled: !!opponentId && (debGive.length > 0 || debReceive.length > 0),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // ── Balance suggestions (#78/#88) ────────────────────────────────────
  // When the evaluator above says the trade isn't agreeable, propose 1–2
  // piece add-ons from the lighter side's ACTUAL roster. Candidates are
  // shortlisted on the consensus board (heuristic), then CONFIRMED through
  // the same Mode B evaluate call that renders the verdict — a card only
  // survives if the evaluator itself scores the sweetened trade as fairer.
  const ev = evalQ.data;

  // #203 v1 — "Suggested" rows at the top of the add-player picker: only when
  // the current trade is uneven AND this picker adds to the side gap.add_to
  // points at. Ranked by value-closeness to the gap; a NEED badge marks
  // assets whose position is a league-relative weakness of the RECEIVING
  // team (needsByTeam above). Need-fillers inside the evener value window
  // (0.4–1.5 × gap, mirroring the backend's _EVENER_WINDOW) sort first;
  // outside it, value-closeness wins the order and the badge stays visible.
  let pickerSuggestions: SuggestedPlayer[] = [];
  if (picker && ev?.gap && ev.gap.add_to === picker && ev.gap.value > 0) {
    const gapV = ev.gap.value;
    const inTrade = new Set([...giveIds, ...receiveIds]);
    const receiverId = picker === 'give' ? opponentId : userId;
    const needs = new Set(receiverId ? needsByTeam[receiverId] ?? [] : []);
    pickerSuggestions = (picker === 'give' ? myPoolPlayers : oppPoolPlayers)
      .filter((p) => !inTrade.has(p.id))
      .map((p) => {
        const v = board[p.id] ?? 0;
        return {
          player: p,
          need: needs.has(p.pos as Position),
          dist: Math.abs(v - gapV),
          inWindow: v >= gapV * 0.4 && v <= gapV * 1.5,
        };
      })
      .sort(
        (a, b) =>
          Number(b.need && b.inWindow) - Number(a.need && a.inWindow) || a.dist - b.dist,
      )
      .slice(0, 4)
      .map(({ player, need }) => ({ player, need }));
  }

  const balancePlan = useMemo(() => {
    if (!ev || debGive.length === 0 || debReceive.length === 0) return null;
    const agreeable =
      ev.basis === 'divergence'
        ? ev.mutual_gain
        : ev.verdict === 'fair' || ev.verdict === 'even';
    if (agreeable) return null;
    // Which side needs sweetening: the owner whose board reads the trade as
    // the bigger loss (divergence) or the lighter package (consensus read).
    const addTo: 'give' | 'receive' | null =
      ev.basis === 'divergence'
        ? ev.your_value_delta <= ev.their_value_delta
          ? 'receive' // you're down → more comes your way, from THEIR roster
          : 'give' //    they're down → sweeten what you send, from YOURS
        : ev.gap?.add_to ?? null;
    if (!addTo) return null;
    const inTrade = new Set([...debGive, ...debReceive]);
    const roster =
      addTo === 'receive' ? (opponentId ? rosterByOwner[opponentId] ?? [] : []) : rosterByOwner[userId] ?? [];
    const pool = roster.filter((id) => !inTrade.has(id) && board[id] !== undefined);
    const cands: string[][] =
      ev.basis === 'divergence'
        ? rankGapCandidates(
            pool,
            board,
            Math.abs(Math.min(ev.your_value_delta, ev.their_value_delta)),
          )
        : rankAddOnCandidates(
            debGive,
            debReceive,
            addTo === 'give' ? 'send' : 'receive',
            pool,
            board,
          ).map((c) => c.ids);
    return cands.length > 0 ? { addTo, cands, basis: ev.basis } : null;
  }, [ev, debGive, debReceive, opponentId, userId, rosterByOwner, board]);

  const balanceQ = useQuery({
    queryKey: [
      'calc-balance-league',
      leagueId,
      opponentId,
      format,
      debGive.join('+'),
      debReceive.join('+'),
      balancePlan?.cands.map((c) => c.join('.')).join('+') ?? '',
    ],
    // evalQ must be settled: improvement is judged against the CURRENT
    // trade's evaluation, never a stale placeholder.
    enabled: !!opponentId && !!balancePlan && !evalQ.isFetching,
    staleTime: 60_000,
    queryFn: async ({ signal }): Promise<CalcSuggestion[]> => {
      const plan = balancePlan!;
      const probes: TradeProbe[] = plan.cands.map((ids) =>
        plan.addTo === 'give'
          ? { give: [...debGive, ...ids], receive: debReceive }
          : { give: debGive, receive: [...debReceive, ...ids] },
      );
      const evals = await evaluateTradesInLeague(probes, format, leagueId, opponentId!, signal);
      const curMin = ev ? Math.min(ev.your_value_delta ?? 0, ev.their_value_delta ?? 0) : 0;
      const curRatio = ev?.point_ratio ?? null;
      return plan.cands
        .map((ids, i) => ({ ids, e: evals[i] }))
        .filter(({ e }) => {
          if (!e) return false;
          if (plan.basis === 'divergence') {
            // Strictly better for the worse-off board AND fair on consensus.
            const newMin = Math.min(e.your_value_delta, e.their_value_delta);
            return newMin > curMin && (e.verdict === 'fair' || e.verdict === 'even');
          }
          return (
            (e.verdict === 'fair' || e.verdict === 'even') &&
            e.point_ratio !== null &&
            (curRatio === null || e.point_ratio > curRatio)
          );
        })
        .sort((a, b) => {
          if (plan.basis === 'divergence') {
            // Win-wins first, then by how well the worse board does.
            const mg = Number(b.e!.mutual_gain) - Number(a.e!.mutual_gain);
            if (mg !== 0) return mg;
            return (
              Math.min(b.e!.your_value_delta, b.e!.their_value_delta) -
              Math.min(a.e!.your_value_delta, a.e!.their_value_delta)
            );
          }
          return (b.e!.point_ratio ?? 0) - (a.e!.point_ratio ?? 0);
        })
        .slice(0, 3)
        .map(({ ids, e }) => ({
          players: ids.map((id) => playerById[id]).filter(Boolean) as CalcPlayer[],
          evaluation:
            e!.basis === 'divergence' ? evalFromBoards(e!) : evalFromConsensus(e!),
          score: e!.point_ratio ?? 0,
        }));
    },
  });

  const applyBalance = (s: CalcSuggestion) => {
    haptics.selection();
    const ids = s.players.map((p) => p.id);
    if (balancePlan?.addTo === 'give') setGiveIds((cur) => [...cur, ...ids]);
    else setReceiveIds((cur) => [...cur, ...ids]);
  };

  // Eveners (DynastyGM teardown 2026-07-26): server-picked one-tap assets
  // from the WINNING side's real roster + owned picks (POST /api/trade/
  // evaluate `eveners`). gap.add_to names the side that adds — 'give' =
  // your roster, 'receive' = theirs. Adding re-runs the debounced evaluate,
  // which refreshes or clears the rows as the trade evens.
  //
  // #264 — one-sided reads carry no gap, so the target side is derived from
  // the RESPONSE (per_player side counts) rather than local state: the rows
  // and the side they land on then always describe the same payload, even
  // while a newer evaluate is in flight behind placeholderData.
  const oneSidedAddTo: 'give' | 'receive' | null = (() => {
    if (!ev || ev.gap?.add_to) return null;
    const evGive = ev.per_player.filter((p) => p.side === 'give').length;
    const evReceive = ev.per_player.length - evGive;
    if (evGive > 0 && evReceive === 0) return 'receive'; // ask them for a return
    if (evReceive > 0 && evGive === 0) return 'give'; //    what you'd have to send
    return null;
  })();
  const evenerAddTo = ev?.gap?.add_to ?? oneSidedAddTo;

  const addEvener = (e: CalcEvener) => {
    const addTo = evenerAddTo;
    if (!addTo) return;
    haptics.selection();
    const ids = e.ids ?? [e.id];
    const setter = addTo === 'give' ? setGiveIds : setReceiveIds;
    setter((cur) => [...cur, ...ids.filter((id) => !cur.includes(id))]);
  };

  // Share-as-image inputs: names/positions/values from the merged
  // player+pick map (picks share the same map, so they render too).
  const shareAssets = (ids: string[]): ShareAsset[] =>
    (ids.map((id) => playerById[id]).filter(Boolean) as CalcPlayer[]).map((p) => ({
      id: p.id,
      name: p.name,
      position: p.pos,
      value: board[p.id] ?? 0,
    }));

  const bothSides = giveIds.length > 0 && receiveIds.length > 0;
  const anySide = giveIds.length > 0 || receiveIds.length > 0;
  const clear = () => {
    haptics.warning();
    setGiveIds([]);
    setReceiveIds([]);
  };

  if (rostersQ.isLoading || coverageQ.isLoading) {
    return (
      <Card>
        <View style={styles.row}>
          <ActivityIndicator color={ice.base} />
          <Text style={type.bodySm}>Loading your league…</Text>
        </View>
      </Card>
    );
  }
  if (opponents.length === 0) {
    return (
      <Card>
        <Text style={type.bodySm}>No leaguemates found for this league yet.</Text>
      </Card>
    );
  }

  return (
    <View style={styles.wrap}>
      {collapsedPartner ? (
        <View style={styles.partnerCollapsed} testID="calc.partner-collapsed" accessible={false}>
          <Text style={styles.partnerCollapsedText} numberOfLines={1}>
            Trading with <Text style={styles.partnerCollapsedName}>@{opponent!.username}</Text>
          </Text>
          <Pressable
            testID="calc.partner-change"
            onPress={() => {
              haptics.selection();
              setPartnerCollapsed(false);
            }}
            accessibilityRole="button"
            accessibilityLabel={`Change trade partner, currently @${opponent!.username}`}
            hitSlop={6}
            style={({ pressed }) => [styles.changeBtn, pressed && styles.changeBtnPressed]}
          >
            <Text style={styles.changeText}>Change</Text>
          </Pressable>
        </View>
      ) : null}

      <TickLabel>Scoring format</TickLabel>
      <View style={styles.chipRow}>
        {FORMATS.map((f) => {
          const active = format === f.key;
          return (
            <Pressable
              key={f.key}
              style={[styles.chip, active && styles.chipActive]}
              onPress={() => {
                if (f.key !== format) {
                  haptics.selection();
                  setFormatChoice(f.key);
                }
              }}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>{f.label}</Text>
            </Pressable>
          );
        })}
      </View>

      {!collapsedPartner ? (
        <>
      <TickLabel>Trade partner</TickLabel>
      <View style={styles.chipRow}>
        {opponents.map((o) => {
          const active = o.user_id === opponentId;
          // #192 — R / R* / NR text badge replaces the old flare dot.
          const state = rankStateFor(o, format);
          // DTF teardown 2026-07-27 — team-shape line under the handle:
          // color-coded positional values + picks from power-rankings.
          const summary = partnerSummaries[o.user_id];
          const a11ySummary = summary
            ? ', ' +
              POSITIONS.map(
                (pos) => `${pos} ${Math.round(summary.pos[pos])}`,
              ).join(', ') +
              (summary.picks != null ? `, picks ${Math.round(summary.picks)}` : '')
            : '';
          return (
            <Pressable
              key={o.user_id}
              style={[styles.chip, active && styles.chipActive]}
              onPress={() => {
                haptics.selection();
                setOpponentId(o.user_id);
              }}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              accessibilityLabel={`@${o.username}, ${RANK_STATE_A11Y[state]}${a11ySummary}`}
            >
              <View style={styles.chipTop}>
                <Text style={[styles.chipText, active && styles.chipTextActive]}>@{o.username}</Text>
                <Badge
                  label={state}
                  color={state === 'NR' ? chalk.dim : semantic.pos}
                  colorText
                />
              </View>
              {summary ? (
                <Text
                  testID={`calc.partner-summary.${o.user_id}`}
                  style={styles.summaryLine}
                  numberOfLines={1}
                  ellipsizeMode="tail"
                >
                  {POSITIONS.map((pos, i) => (
                    <Text key={pos}>
                      {i > 0 ? ' · ' : ''}
                      <Text style={{ color: posColor(pos) }}>{pos} </Text>
                      {Math.round(summary.pos[pos]).toLocaleString()}
                    </Text>
                  ))}
                  {summary.picks != null ? (
                    <Text>
                      {' · Picks '}
                      {Math.round(summary.picks).toLocaleString()}
                    </Text>
                  ) : null}
                </Text>
              ) : null}
            </Pressable>
          );
        })}
      </View>
      {opponent ? (() => {
        const state = rankStateFor(opponent, format);
        if (state === 'NR') {
          return (
            <Text style={styles.note}>
              @{opponent.username} hasn't ranked yet — you'll get a consensus read. Invite them to
              rank for a two-sided verdict.
            </Text>
          );
        }
        if (state === 'R*') {
          // #191 — derived board: honest about the conversion.
          const src = (opponent.ranked_formats ?? []).find((f) => f !== format);
          return (
            <Text style={styles.note}>
              @{opponent.username} ranked in {FORMAT_LABEL[src ?? ''] ?? 'another format'} — values
              converted to {FORMAT_LABEL[format]} for this read.
            </Text>
          );
        }
        return <Text style={styles.note}>Priced by your rankings and @{opponent.username}'s.</Text>;
      })() : null}
        </>
      ) : null}
      {!picksSupported ? (
        <Text style={styles.note}>Draft picks aren't available for ESPN leagues.</Text>
      ) : null}

      <TradeSide
        title="You send"
        teamName="your roster"
        players={giveIds.map((id) => playerById[id]).filter(Boolean) as CalcPlayer[]}
        valueOf={(p) => board[p.id] ?? 0}
        accent={semantic.neg}
        addTestID="calc.league-give-add"
        onAdd={() => setPicker('give')}
        onRemove={(id) => {
          haptics.warning();
          setGiveIds((ids) => ids.filter((x) => x !== id));
        }}
      />

      <View style={styles.swap}>
        <View style={styles.rule} />
        <Icon name="swap" size={16} />
        <View style={styles.rule} />
      </View>

      <TradeSide
        title="You receive"
        teamName={opponent ? `@${opponent.username}` : 'their roster'}
        players={receiveIds.map((id) => playerById[id]).filter(Boolean) as CalcPlayer[]}
        valueOf={(p) => board[p.id] ?? 0}
        accent={semantic.pos}
        addTestID="calc.league-receive-add"
        onAdd={() => setPicker('receive')}
        onRemove={(id) => {
          haptics.warning();
          setReceiveIds((ids) => ids.filter((x) => x !== id));
        }}
      />

      {/* #251 (operator, via the featured-trade window's edit-in-calculator
          hand-off): the "Recommended to even it" rows sit DIRECTLY under
          the trade window (the give/receive sides above), ABOVE the
          fairness summary — the fix is one tap away before the verdict
          re-explains the gap. Pure reorder; same render condition.
          #264: ONE block covers both states — uneven two-sided (eveners) and
          half-built one-sided (trade options for the empty side). A second
          card would have re-stacked the screen (#205); the label carries the
          difference instead. */}
      {anySide && ev?.eveners && ev.eveners.length > 0 && evenerAddTo ? (
        <EvenerRows
          eveners={ev.eveners}
          title={
            ev.gap?.add_to
              ? evenerAddTo === 'give'
                ? 'Recommended to even it — add from your roster'
                : `Recommended to even it — ask @${opponent?.username ?? 'them'} to add`
              : // #264 — half-built trade: these aren't evening anything, they
                // are candidate assets worth about what the filled side is
                // worth. Same rows, same slot, honest label.
                evenerAddTo === 'give'
                ? 'Trade options — from your roster'
                : `Trade options — from @${opponent?.username ?? 'them'}'s roster`
          }
          onAdd={addEvener}
        />
      ) : null}

      {anySide && evalQ.data ? (
        <LeagueVerdict ev={evalQ.data} oppName={opponent?.username ?? 'them'} stale={evalQ.isFetching} />
      ) : anySide && evalQ.isLoading ? (
        <Card>
          <View style={styles.row}>
            <ActivityIndicator color={ice.base} />
            <Text style={type.bodySm}>Evaluating…</Text>
          </View>
        </Card>
      ) : null}

      {balancePlan && balanceQ.data && balanceQ.data.length > 0 ? (
        <View style={styles.suggestions}>
          <TickLabel color={semantic.warn}>
            {balancePlan.addTo === 'give'
              ? 'To balance — add from your roster'
              : `To balance — ask @${opponent?.username ?? 'them'} to add`}
          </TickLabel>
          {balanceQ.data.map((s) => (
            <SuggestionCard
              key={'bal:' + s.players.map((p) => p.id).join('+')}
              suggestion={s}
              onApply={() => applyBalance(s)}
            />
          ))}
        </View>
      ) : null}

      {anySide ? (
        <View style={styles.actions}>
          {bothSides && opponentId ? (
            <SendInSleeperButton
              leagueId={leagueId}
              theirUserId={opponentId}
              givePlayerIds={giveIds}
              receivePlayerIds={receiveIds}
            />
          ) : null}
          {/* Share-as-image (DynastyDealer teardown 2026-07-26): render the
              verdict to a PNG for the native share sheet; text fallback. */}
          {bothSides && ev ? (
            <ShareTradeImage
              caption={`vs @${opponent?.username ?? 'them'} · ${FORMAT_LABEL[format]}`}
              sendTitle="You send"
              receiveTitle="You receive"
              sendAssets={shareAssets(giveIds)}
              receiveAssets={shareAssets(receiveIds)}
              sendTotal={ev.give_value}
              receiveTotal={ev.receive_value}
              verdictLine={shareVerdictLine(ev, opponent?.username ?? 'them')}
              fallbackText={[
                `Trade idea vs @${opponent?.username ?? 'them'} (Dynasty Trade Finder · ${FORMAT_LABEL[format]})`,
                `I send: ${giveIds.map((id) => playerById[id]?.name ?? id).join(', ')}`,
                `I get: ${receiveIds.map((id) => playerById[id]?.name ?? id).join(', ')}`,
                `Consensus: ${Math.round(ev.give_value).toLocaleString()} vs ${Math.round(ev.receive_value).toLocaleString()}`,
                shareVerdictLine(ev, opponent?.username ?? 'them'),
              ].join('\n')}
            />
          ) : null}
          <Button label="Clear trade" variant="ghost" onPress={clear} />
        </View>
      ) : null}

      <PlayerPickerModal
        visible={picker === 'give'}
        title="Send from your roster"
        players={myPoolPlayers}
        suggested={pickerSuggestions}
        selectedIds={[...giveIds, ...receiveIds]}
        ownerBoardValue={(p: CalcPlayer) => board[p.id] ?? 0}
        onPick={(p) => {
          haptics.selection();
          setGiveIds((ids) => [...ids, p.id]);
        }}
        onClose={() => setPicker(null)}
      />
      <PlayerPickerModal
        visible={picker === 'receive'}
        title={opponent ? `Receive from @${opponent.username}` : 'Receive'}
        players={oppPoolPlayers}
        suggested={pickerSuggestions}
        selectedIds={[...giveIds, ...receiveIds]}
        ownerBoardValue={(p: CalcPlayer) => board[p.id] ?? 0}
        onPick={(p) => {
          haptics.selection();
          setReceiveIds((ids) => [...ids, p.id]);
        }}
        onClose={() => setPicker(null)}
      />
    </View>
  );
}

// One-line verdict for the share card / text fallback — mirrors the
// LeagueVerdict headline's logic, compressed.
function shareVerdictLine(ev: CalcEvaluationInLeague, oppName: string): string {
  if (ev.basis === 'divergence') {
    if (ev.mutual_gain) return 'Win–win by both boards';
    if (ev.your_value_delta > 0 && ev.their_value_delta <= 0)
      return `Wins by my board — @${oppName} likely disagrees`;
    if (ev.your_value_delta <= 0 && ev.their_value_delta > 0)
      return `@${oppName} wins this one by their board`;
    return 'Roughly even by both boards';
  }
  return ev.verdict ? `Consensus verdict: ${ev.verdict}` : 'Consensus read';
}

// In-league verdict. #204: the shared pick-denominated TradeValueBar is the
// headline visual (consistent with live mode's ConsensusVerdictCard), fed by
// the same evaluate response's consensus fields. The two-board divergence
// read stays below it — that's DIFFERENT information (each owner's board),
// not a duplicate of the bar's market read. What the bar replaced: the old
// consensus-basis headline sentence (now a one-line provenance note).
function LeagueVerdict({
  ev,
  oppName,
  stale,
}: {
  ev: CalcEvaluationInLeague;
  oppName: string;
  stale: boolean;
}) {
  const both = ev.give_value > 0 && ev.receive_value > 0;
  const youGain = ev.your_value_delta > 0;
  const theyGain = ev.their_value_delta > 0;
  // Two-board headline — only meaningful on a two-sided divergence read.
  const headline = ev.mutual_gain
    ? 'Win–win — you both come out ahead by your own rankings.'
    : youGain && !theyGain
    ? `You win by your board — @${oppName} likely sees it as a loss.`
    : !youGain && theyGain
    ? `@${oppName} wins by their board — this one costs you.`
    : 'Roughly even by both boards.';

  const sign = (n: number) => (n > 0 ? `+${Math.round(n).toLocaleString()}` : Math.round(n).toLocaleString());
  const deltaColor = (n: number) => (n > 0 ? semantic.pos : n < 0 ? semantic.neg : chalk.dim);

  return (
    <Card>
      <View style={styles.verdictHead}>
        <Text style={[type.label, { color: ev.basis === 'divergence' ? ice.base : chalk.dim }]}>
          {ev.basis === 'divergence' ? 'BOTH BOARDS' : 'CONSENSUS'}
        </Text>
        {stale ? <ActivityIndicator size="small" color={ice.base} /> : null}
      </View>
      {!both ? (
        <Text style={[type.body, styles.headline]}>Add a player to each side for a verdict.</Text>
      ) : (
        <View style={styles.bar}>
          <TradeValueBar
            giveValue={ev.give_value}
            receiveValue={ev.receive_value}
            favors={ev.favors}
            gap={ev.gap}
          />
        </View>
      )}
      {both && ev.basis === 'consensus' ? (
        <Text style={[type.bodySm, styles.derivedNote]}>
          Market values only — @{oppName} hasn't ranked.
        </Text>
      ) : null}
      {/* #191 — derived-board honesty line: their side of the verdict was
          value-mapped from the other format's board, not ranked here. */}
      {ev.basis === 'divergence' && ev.opponent_board_derived ? (
        <Text style={[type.bodySm, styles.derivedNote]}>
          @{oppName}'s board converted from{' '}
          {FORMAT_LABEL[ev.opponent_board_derived_from ?? ''] ?? 'their other format'}.
        </Text>
      ) : null}
      {both && ev.basis === 'divergence' ? (
        <Text style={[type.body, styles.headline]}>{headline}</Text>
      ) : null}
      {ev.basis === 'divergence' ? (
        <View style={styles.boards}>
          <View style={styles.boardRow}>
            <Text style={type.bodySm}>Your board</Text>
            <Text style={[type.data, { color: deltaColor(ev.your_value_delta) }]}>
              {sign(ev.your_value_delta)}
            </Text>
          </View>
          <View style={styles.boardRow}>
            <Text style={type.bodySm}>@{oppName}'s board</Text>
            <Text style={[type.data, { color: deltaColor(ev.their_value_delta) }]}>
              {sign(ev.their_value_delta)}
            </Text>
          </View>
        </View>
      ) : null}
      <View style={styles.boardRow}>
        <Text style={type.bodySm}>Consensus</Text>
        <Text style={type.data}>
          {Math.round(ev.give_value).toLocaleString()} vs {Math.round(ev.receive_value).toLocaleString()}
        </Text>
      </View>
      {/* Starter impact (DTF teardown 2026-07-27; #238 V2 table) — how the
          trade moves the IMMEDIATE optimal lineup, not just raw value.
          Server-derived; the field is absent without a lineup-slot template
          (old servers, non-Sleeper leagues) and nothing renders. When the
          #238 per-slot breakdown is present the full before/after lineup
          table replaces the one-line sentence (approved mock: polish-lab
          lineup-before-after.html frame C1); pre-#238 servers still get
          the sentence. */}
      {ev.starter_impact?.slots && ev.starter_impact.slots.length > 0 ? (
        <LineupImpactTable note={ev.starter_impact.note} slots={ev.starter_impact.slots} />
      ) : ev.starter_impact ? (
        <Text testID="calc.starter-impact" style={styles.starterImpact}>
          {ev.starter_impact.note}
        </Text>
      ) : null}
      {/* Why the consensus totals differ from the naive sum of parts —
          collapsed by default, only when the server itemized adjustments
          (#215: mode 'off' shows the one-line "Value adjustments off"). */}
      {ev.adjustments || ev.stud_tax_mode === 'off' ? (
        <View style={styles.adjustments}>
          <AdjustmentsDisclosure
            adjustments={ev.adjustments}
            naiveTotals={ev.naive_totals}
            giveTotal={ev.give_value}
            receiveTotal={ev.receive_value}
            studTaxMode={ev.stud_tax_mode}
          />
        </View>
      ) : null}
    </Card>
  );
}

// #238 — full before/after starting-lineup table (approved mock frame C1 of
// mockups/polish-lab-2026-08/lineup-before-after.html). One row per lineup
// slot in the league's template order: slot label · before player · arrow ·
// after player · signed delta chip. Unchanged rows are dimmed with a flat
// "—" chip; the net line totals the whole lineup. The container is a single
// accessibility element voicing the server's one-sentence `note`, so screen
// readers hear one clean read instead of a cell-by-cell table.
const SLOT_SHORT: [string, string][] = [
  ['SUPER_FLEX', 'SF'],
  ['WRRB_FLEX', 'W/R'],
  ['REC_FLEX', 'W/T'],
];
function slotShortLabel(slot: string): string {
  // Numbered variants shorten too: SUPER_FLEX2 → SF2.
  for (const [long, short] of SLOT_SHORT) {
    if (slot.startsWith(long)) return short + slot.slice(long.length);
  }
  return slot;
}

function LineupImpactTable({ note, slots }: { note: string; slots: StarterImpactSlot[] }) {
  const beforeTotal = slots.reduce((t, s) => t + (s.before?.value ?? 0), 0);
  const afterTotal = slots.reduce((t, s) => t + (s.after?.value ?? 0), 0);
  const net = afterTotal - beforeTotal;
  const fmt = (n: number) => Math.round(n).toLocaleString();
  const signed = (n: number) => (n > 0 ? `+${fmt(n)}` : fmt(n));
  const netColor = net > 0 ? semantic.pos : net < 0 ? semantic.neg : chalk.dim;
  return (
    <View
      testID="calc.lineup-impact"
      style={styles.lineupMod}
      accessible
      accessibilityLabel={note}
    >
      <TickLabel>Your lineup — before → after</TickLabel>
      <View style={styles.lineupHead}>
        <Text style={[styles.lineupHeadText, styles.lineupSlotCol]}>SLOT</Text>
        <Text style={[styles.lineupHeadText, styles.lineupNameCol]}>BEFORE</Text>
        <View style={styles.lineupArrowCol} />
        <Text style={[styles.lineupHeadText, styles.lineupNameCol]}>AFTER</Text>
        <View style={styles.lineupDeltaCol} />
      </View>
      {slots.map((s) => {
        const changed = (s.before?.player_id ?? null) !== (s.after?.player_id ?? null);
        return (
          <View key={s.slot} style={[styles.lineupRow, !changed && styles.lineupRowDim]}>
            <ChalkText scale="dense" style={[styles.lineupSlotCol, styles.lineupSlotText]}>
              {slotShortLabel(s.slot)}
            </ChalkText>
            <ChalkText scale="dense" style={[styles.lineupNameCol, styles.lineupName]} numberOfLines={1}>
              {s.before?.name ?? '—'}
            </ChalkText>
            <View style={styles.lineupArrowCol}>
              {changed ? <Icon name="chevron-right" size={12} color={chalk.faint} /> : null}
            </View>
            <ChalkText scale="dense" style={[styles.lineupNameCol, styles.lineupName]} numberOfLines={1}>
              {s.after?.name ?? '—'}
            </ChalkText>
            <View style={styles.lineupDeltaCol}>
              {changed ? (
                <ChalkText
                  scale="dense"
                  style={[
                    styles.lineupDeltaChip,
                    s.delta >= 0 ? styles.lineupDeltaPos : styles.lineupDeltaNeg,
                  ]}
                >
                  {signed(s.delta)}
                </ChalkText>
              ) : (
                <ChalkText scale="dense" style={styles.lineupDeltaFlat}>—</ChalkText>
              )}
            </View>
          </View>
        );
      })}
      <View style={styles.lineupNet}>
        <Text style={[type.bodySm, { color: chalk.dim }]}>Starting lineup total</Text>
        <ChalkText scale="dense" style={[styles.lineupNetVal, { color: netColor }]}>
          {fmt(beforeTotal)} → {fmt(afterTotal)} ({signed(net)})
        </ChalkText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.md },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    minHeight: 44,
    maxWidth: '100%',
    justifyContent: 'center',
    gap: 2,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
  },
  chipActive: { borderColor: ice.base },
  chipTop: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  chipText: { fontFamily: fonts.uiSemi, fontSize: 13, lineHeight: 18, color: chalk.dim },
  chipTextActive: { color: chalk.base },
  // DTF teardown 2026-07-27 — compact positional line under the handle.
  // Plex Mono at the 11px type floor; position labels carry the position
  // hexes (data encoding, always paired with the text label).
  summaryLine: {
    fontFamily: fonts.data,
    fontSize: 11,
    lineHeight: 14,
    color: chalk.dim,
  },
  note: { ...type.bodySm },
  // #202 — collapsed partner row ("Trading with @x · Change").
  partnerCollapsed: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 44,
    backgroundColor: ink.ink1,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.line,
    paddingHorizontal: space.md,
  },
  partnerCollapsedText: { ...type.bodySm, flex: 1, color: chalk.dim },
  partnerCollapsedName: { color: chalk.base, fontFamily: fonts.uiSemi },
  changeBtn: {
    minHeight: 32,
    justifyContent: 'center',
    paddingHorizontal: space.sm,
    borderRadius: radii.sm,
  },
  changeBtnPressed: { backgroundColor: ink.ink3 },
  changeText: { ...type.bodySm, color: ice.base, fontFamily: fonts.uiSemi },
  suggestions: { gap: space.sm },
  swap: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  rule: { flex: 1, height: 1, backgroundColor: ink.line },
  actions: { gap: space.sm, alignItems: 'stretch' },
  verdictHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  bar: { marginTop: space.sm },
  headline: { marginTop: space.xs },
  derivedNote: { marginTop: space.xs, color: chalk.dim },
  boards: { gap: space.xs, marginTop: space.sm },
  boardRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  starterImpact: { ...type.bodySm, color: chalk.dim, marginTop: space.xs },
  adjustments: { marginTop: space.sm },
  // #238 lineup before/after table.
  lineupMod: {
    marginTop: space.sm,
    paddingTop: space.sm,
    borderTopWidth: 1,
    borderTopColor: ink.line,
    gap: space.xs,
  },
  lineupHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  lineupHeadText: {
    fontFamily: fonts.uiSemi,
    fontSize: 10,
    lineHeight: 13,
    letterSpacing: 0.6,
    color: chalk.faint,
  },
  lineupRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, minHeight: 24 },
  lineupRowDim: { opacity: 0.5 },
  lineupSlotCol: { width: 40, flexShrink: 0 },
  lineupSlotText: {
    fontFamily: fonts.data,
    fontSize: 11,
    lineHeight: 14,
    color: chalk.dim,
  },
  lineupNameCol: { flex: 1, minWidth: 0 },
  lineupName: { fontFamily: fonts.ui, fontSize: 12, lineHeight: 16, color: chalk.base },
  lineupArrowCol: { width: 14, flexShrink: 0, alignItems: 'center' },
  lineupDeltaCol: { width: 56, flexShrink: 0, alignItems: 'flex-end' },
  lineupDeltaChip: {
    fontFamily: fonts.data,
    fontSize: 11,
    lineHeight: 14,
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderWidth: 1,
    borderRadius: radii.xs,
    overflow: 'hidden',
  },
  lineupDeltaPos: { color: semantic.pos, borderColor: `${semantic.pos}66` },
  lineupDeltaNeg: { color: semantic.neg, borderColor: `${semantic.neg}66` },
  lineupDeltaFlat: {
    fontFamily: fonts.data,
    fontSize: 11,
    lineHeight: 14,
    color: chalk.faint,
    paddingHorizontal: 6,
  },
  lineupNet: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    marginTop: space.xs,
    paddingTop: space.sm,
    borderTopWidth: 1,
    borderTopColor: ink.line,
    borderStyle: 'dashed',
  },
  lineupNetVal: { fontFamily: fonts.dataSemi, fontSize: 14, lineHeight: 18 },
});

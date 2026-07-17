import React, { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';

import { getLeagueRosters } from '../api/sleeper';
import { getLeagueCoverage } from '../api/league';
import {
  evaluateTradeInLeague,
  evaluateTradesInLeague,
  getTradeValues,
  type CalcEvaluationInLeague,
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
import PlayerPickerModal from './PlayerPickerModal';
import SuggestionCard from './SuggestionCard';
import SendInSleeperButton from './SendInSleeperButton';
import { Button, Card, Icon, TickLabel } from './chalkline';
import { haptics } from '../utils/haptics';
import { chalk, flare, fonts, ice, ink, radii, semantic, space, type } from '../theme/chalkline';
import type { CalcPlayer, CalcPos } from '../data/tradeCalcMock';
import type { ScoringFormat } from '../shared/types';

// In-league calculator (Mode B, docs/plans/manual-trade-calculator-plan.md).
// The FTF differentiator applied to a hand-built trade: pick a real opponent,
// assemble a trade from BOTH rosters, and evaluate it by BOTH owners' real
// rankings (POST /api/trade/evaluate with league_id + opponent_user_id). It's
// the one calculator surface with a real league + opponent, so it carries the
// "Send in Sleeper" button.

interface Props {
  leagueId: string;
  userId: string;
}

const FORMATS: { key: ScoringFormat; label: string }[] = [
  { key: '1qb_ppr', label: '1QB PPR' },
  { key: 'sf_tep', label: 'SF TEP' },
];

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function InLeagueCalculator({ leagueId, userId }: Props) {
  const [format, setFormat] = useState<ScoringFormat>('1qb_ppr');
  const [opponentId, setOpponentId] = useState<string | null>(null);
  const [giveIds, setGiveIds] = useState<string[]>([]);
  const [receiveIds, setReceiveIds] = useState<string[]>([]);
  const [picker, setPicker] = useState<'give' | 'receive' | null>(null);

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

  const board = useMemo<Record<string, number>>(
    () => Object.fromEntries((valuesQ.data?.players ?? []).map((r) => [r.id, r.value])),
    [valuesQ.data],
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
    return m;
  }, [valuesQ.data]);

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

  // Their roster changed → what you'd receive no longer applies.
  useEffect(() => {
    setReceiveIds([]);
    setPicker(null);
  }, [opponentId]);

  const opponent = opponents.find((o) => o.user_id === opponentId) ?? null;
  const myPoolPlayers = (rosterByOwner[userId] ?? [])
    .map((id) => playerById[id])
    .filter(Boolean) as CalcPlayer[];
  const oppPoolPlayers = (opponentId ? rosterByOwner[opponentId] ?? [] : [])
    .map((id) => playerById[id])
    .filter(Boolean) as CalcPlayer[];

  const debGive = useDebounced(giveIds, 250);
  const debReceive = useDebounced(receiveIds, 250);
  const evalQ = useQuery({
    queryKey: ['calc-eval-league', leagueId, opponentId, format, debGive.join('+'), debReceive.join('+')],
    queryFn: ({ signal }) =>
      evaluateTradeInLeague(debGive, debReceive, format, leagueId, opponentId!, signal),
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
                  setFormat(f.key);
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

      <TickLabel>Trade partner</TickLabel>
      <View style={styles.chipRow}>
        {opponents.map((o) => {
          const active = o.user_id === opponentId;
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
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>@{o.username}</Text>
              {!o.has_rankings ? <View style={styles.unranked} /> : null}
            </Pressable>
          );
        })}
      </View>
      {opponent && !opponent.has_rankings ? (
        <Text style={styles.note}>
          @{opponent.username} hasn't ranked yet — you'll get a consensus read. Invite them to rank
          for a two-sided verdict.
        </Text>
      ) : (
        <Text style={styles.note}>Priced by your rankings and @{opponent?.username}'s.</Text>
      )}

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
          <Button label="Clear trade" variant="ghost" onPress={clear} />
        </View>
      ) : null}

      <PlayerPickerModal
        visible={picker === 'give'}
        title="Send from your roster"
        players={myPoolPlayers}
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

// Two-board verdict: how the trade reads by YOUR rankings and by THEIRS.
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
  const headline = !both
    ? 'Add a player to each side for a verdict.'
    : ev.basis === 'consensus'
    ? `Consensus read — @${oppName} hasn't ranked, so this is market value only.`
    : ev.mutual_gain
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
      <Text style={[type.body, styles.headline]}>{headline}</Text>
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
    </Card>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.md },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    paddingHorizontal: space.md,
  },
  chipActive: { borderColor: ice.base },
  chipText: { fontFamily: fonts.uiSemi, fontSize: 13, lineHeight: 18, color: chalk.dim },
  chipTextActive: { color: chalk.base },
  unranked: { width: 6, height: 6, borderRadius: 3, backgroundColor: flare.base },
  note: { ...type.bodySm },
  suggestions: { gap: space.sm },
  swap: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  rule: { flex: 1, height: 1, backgroundColor: ink.line },
  actions: { gap: space.sm, alignItems: 'stretch' },
  verdictHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headline: { marginTop: space.xs },
  boards: { gap: space.xs, marginTop: space.sm },
  boardRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
});

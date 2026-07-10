import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQuery } from '@tanstack/react-query';

import {
  CALC_LEAGUE_NAME,
  CALC_MY_TEAM,
  CALC_PARTNERS,
  CALC_PLAYER_BY_ID,
  CalcPlayer,
  CalcPos,
  boardFor,
} from '../data/tradeCalcMock';
import {
  CALC_VERDICT_LABEL,
  evaluateTrade as evaluateTradeLocal,
  formatDelta,
  suggestAddOns,
  suggestPackages,
} from '../utils/tradeCalcMath';
import { evaluateTrade as evaluateTradeApi, getTradeValues } from '../api/calc';
import TradeSide from '../components/TradeSide';
import VerdictPanel from '../components/VerdictPanel';
import ConsensusVerdictCard from '../components/ConsensusVerdictCard';
import SuggestionCard from '../components/SuggestionCard';
import PlayerPickerModal from '../components/PlayerPickerModal';
import { Button, Card, Icon, TickLabel } from '../components/chalkline';
import { haptics } from '../utils/haptics';
import { chalk, flare, fonts, ice, ink, radii, semantic, space, type } from '../theme/chalkline';
import type { ScoringFormat } from '../shared/types';

// Manual Trade Calculator. Two modes:
//   'live' — REAL consensus values from the backend's universal pool.
//            Verdicts are server-authoritative (POST /api/trade/evaluate
//            reuses the finder's _fairness_v3), per the plan doc
//            docs/plans/manual-trade-calculator-plan.md. No login needed.
//   'demo' — the seeded mock league (data/tradeCalcMock.ts): dual-board
//            fairness, partner tendencies, arbitrage badges. Demonstrates
//            the future league-aware version.

const MY_BOARD = boardFor(CALC_MY_TEAM);
const PARTNER_BOARDS = Object.fromEntries(CALC_PARTNERS.map((o) => [o.id, boardFor(o)]));

// Persisted draft trade — survives leaving the Trades stack / app restart.
const DRAFT_KEY = 'ftf:tradecalc:v1';

// A board disagreement big enough to flag as arbitrage in the demo picker.
const ARBITRAGE_EDGE = 1.05;

// Live-mode suggestion search runs over the top-N pool players (combos over
// the full ~500-player universe would be wasteful for no ranking benefit;
// 40 keeps the 1–3-piece combo scan around ~10k evaluations per edit).
const LIVE_SUGGEST_POOL = 40;

type CalcMode = 'live' | 'demo';

const FORMATS: { key: ScoringFormat; label: string }[] = [
  { key: '1qb_ppr', label: '1QB PPR' },
  { key: 'sf_tep', label: 'SF TEP' },
];

/** Debounce list changes so the evaluate call fires ~250ms after the last tap. */
function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export default function TradeCalculatorScreen() {
  const [mode, setMode] = useState<CalcMode>('live');
  const [format, setFormat] = useState<ScoringFormat>('1qb_ppr');
  // Demo-mode trade state.
  const [partnerId, setPartnerId] = useState(CALC_PARTNERS[0].id);
  const [sendIds, setSendIds] = useState<string[]>([]);
  const [receiveIds, setReceiveIds] = useState<string[]>([]);
  // Live-mode trade state (separate so switching modes keeps both drafts).
  const [liveSendIds, setLiveSendIds] = useState<string[]>([]);
  const [liveReceiveIds, setLiveReceiveIds] = useState<string[]>([]);
  const [picker, setPicker] = useState<'send' | 'receive' | null>(null);
  const [hydrated, setHydrated] = useState(false);

  // Restore the persisted draft once; demo ids validate against the mock
  // rosters here, live ids validate lazily once the pool loads (below).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(DRAFT_KEY);
        if (!cancelled && raw) {
          const draft = JSON.parse(raw);
          if (draft?.mode === 'demo' || draft?.mode === 'live') setMode(draft.mode);
          if (draft?.format === '1qb_ppr' || draft?.format === 'sf_tep') setFormat(draft.format);
          const savedPartner = CALC_PARTNERS.find((o) => o.id === draft?.partnerId);
          if (savedPartner) {
            setPartnerId(savedPartner.id);
            setSendIds(
              (Array.isArray(draft.sendIds) ? draft.sendIds : []).filter((id: string) =>
                CALC_MY_TEAM.rosterIds.includes(id),
              ),
            );
            setReceiveIds(
              (Array.isArray(draft.receiveIds) ? draft.receiveIds : []).filter((id: string) =>
                savedPartner.rosterIds.includes(id),
              ),
            );
          }
          if (Array.isArray(draft.liveSendIds)) setLiveSendIds(draft.liveSendIds.map(String));
          if (Array.isArray(draft.liveReceiveIds))
            setLiveReceiveIds(draft.liveReceiveIds.map(String));
        }
      } catch {
        /* corrupt/unavailable storage — start fresh */
      }
      if (!cancelled) setHydrated(true);
    })();
    return () => { cancelled = true; };
  }, []);

  // Fire-and-forget save; gated on hydration so the initial empty state
  // never clobbers a stored draft.
  useEffect(() => {
    if (!hydrated) return;
    AsyncStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({ mode, format, partnerId, sendIds, receiveIds, liveSendIds, liveReceiveIds }),
    ).catch(() => {});
  }, [hydrated, mode, format, partnerId, sendIds, receiveIds, liveSendIds, liveReceiveIds]);

  // ── Live mode: real consensus values ─────────────────────────────────
  const valuesQuery = useQuery({
    queryKey: ['calc-values', format],
    queryFn: ({ signal }) => getTradeValues(format, signal),
    enabled: mode === 'live',
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });

  const liveBoard = useMemo(
    () =>
      Object.fromEntries((valuesQuery.data?.players ?? []).map((r) => [r.id, r.value])) as Record<
        string,
        number
      >,
    [valuesQuery.data],
  );
  const livePlayers = useMemo<CalcPlayer[]>(
    () =>
      (valuesQuery.data?.players ?? []).map((r) => ({
        id: r.id,
        name: r.name,
        pos: r.position as CalcPos,
        nflTeam: r.team ?? '—',
        age: r.age ?? 0,
        base: r.value,
      })),
    [valuesQuery.data],
  );
  const livePlayerById = useMemo(
    () => Object.fromEntries(livePlayers.map((p) => [p.id, p])),
    [livePlayers],
  );

  // Prune stale draft ids that aren't in the loaded pool (players fall out
  // of the universal pool when they lose their consensus value).
  useEffect(() => {
    if (mode !== 'live' || !valuesQuery.data) return;
    setLiveSendIds((ids) => {
      const kept = ids.filter((id) => liveBoard[id] !== undefined);
      return kept.length === ids.length ? ids : kept;
    });
    setLiveReceiveIds((ids) => {
      const kept = ids.filter((id) => liveBoard[id] !== undefined);
      return kept.length === ids.length ? ids : kept;
    });
  }, [mode, valuesQuery.data, liveBoard]);

  // Server-authoritative evaluation, debounced ~250ms behind list edits.
  const debSendIds = useDebounced(liveSendIds, 250);
  const debReceiveIds = useDebounced(liveReceiveIds, 250);
  const evalQuery = useQuery({
    queryKey: ['calc-eval', format, debSendIds.join('+'), debReceiveIds.join('+')],
    queryFn: ({ signal }) => evaluateTradeApi(debSendIds, debReceiveIds, format, signal),
    enabled: mode === 'live' && (debSendIds.length > 0 || debReceiveIds.length > 0),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });

  // Suggestion search pool: top-N valued players not already in the trade.
  const livePoolIds = useMemo(() => {
    const chosen = new Set([...liveSendIds, ...liveReceiveIds]);
    return livePlayers
      .filter((p) => !chosen.has(p.id))
      .slice(0, LIVE_SUGGEST_POOL)
      .map((p) => p.id);
  }, [livePlayers, liveSendIds, liveReceiveIds]);

  // ── Demo mode: seeded dual boards ────────────────────────────────────
  const partner = CALC_PARTNERS.find((o) => o.id === partnerId)!;
  const theirBoard = PARTNER_BOARDS[partnerId];

  const isLive = mode === 'live';
  const activeSendIds = isLive ? liveSendIds : sendIds;
  const activeReceiveIds = isLive ? liveReceiveIds : receiveIds;
  const setActiveSendIds = isLive ? setLiveSendIds : setSendIds;
  const setActiveReceiveIds = isLive ? setLiveReceiveIds : setReceiveIds;
  const activeBoard = isLive ? liveBoard : MY_BOARD;
  const activeOtherBoard = isLive ? liveBoard : theirBoard;
  const activePlayerById = isLive ? livePlayerById : CALC_PLAYER_BY_ID;
  const activeMyPool = isLive ? livePoolIds : CALC_MY_TEAM.rosterIds;
  const activeTheirPool = isLive ? livePoolIds : partner.rosterIds;

  const demoEvaluation = useMemo(
    () => evaluateTradeLocal(sendIds, receiveIds, MY_BOARD, theirBoard),
    [sendIds, receiveIds, theirBoard],
  );

  // Fair-package + balance-add-on suggestions. In live mode both "boards"
  // are the one consensus board, so the same dual-board math degrades to
  // pure consensus fairness — suggestions still rank by closeness.
  const suggested = useMemo(
    () =>
      suggestPackages(
        activeSendIds,
        activeReceiveIds,
        activeMyPool,
        activeTheirPool,
        activeBoard,
        activeOtherBoard,
        activePlayerById,
      ),
    [activeSendIds, activeReceiveIds, activeMyPool, activeTheirPool, activeBoard, activeOtherBoard, activePlayerById],
  );
  const addOns = useMemo(
    () =>
      suggestAddOns(
        activeSendIds,
        activeReceiveIds,
        activeMyPool,
        activeTheirPool,
        activeBoard,
        activeOtherBoard,
        activePlayerById,
      ),
    [activeSendIds, activeReceiveIds, activeMyPool, activeTheirPool, activeBoard, activeOtherBoard, activePlayerById],
  );

  const bothSides = activeSendIds.length > 0 && activeReceiveIds.length > 0;
  const anySide = activeSendIds.length > 0 || activeReceiveIds.length > 0;

  const switchMode = (m: CalcMode) => {
    if (m === mode) return;
    haptics.selection();
    setMode(m);
  };

  const switchPartner = (id: string) => {
    haptics.selection();
    setPartnerId(id);
    setReceiveIds([]); // their roster changed; what you send can stay
  };

  const switchFormat = (f: ScoringFormat) => {
    if (f === format) return;
    haptics.selection();
    setFormat(f); // selections survive — values re-fetch for the new format
  };

  const applySuggestion = (playerIds: string[], side: 'send' | 'receive') => {
    haptics.selection();
    if (side === 'receive') setActiveReceiveIds(playerIds);
    else setActiveSendIds(playerIds);
  };

  const applyAddOn = (playerIds: string[], side: 'send' | 'receive') => {
    haptics.selection();
    if (side === 'receive') setActiveReceiveIds((ids) => [...ids, ...playerIds]);
    else setActiveSendIds((ids) => [...ids, ...playerIds]);
  };

  const shareTrade = async () => {
    haptics.selection();
    const names = (ids: string[]) =>
      ids.map((id) => activePlayerById[id]?.name ?? id).join(', ');
    const lines = isLive
      ? [
          `Trade idea (DTF Trade Calculator · ${FORMATS.find((f) => f.key === format)?.label})`,
          `Side A: ${names(liveSendIds)}`,
          `Side B: ${names(liveReceiveIds)}`,
          evalQuery.data
            ? `Consensus: ${Math.round(evalQuery.data.give_value).toLocaleString()} vs ${Math.round(evalQuery.data.receive_value).toLocaleString()}${
                evalQuery.data.point_ratio !== null
                  ? ` (ratio ${Math.round(evalQuery.data.point_ratio * 100)}%)`
                  : ''
              }`
            : '',
          evalQuery.data?.verdict ? `Verdict: ${evalQuery.data.verdict}` : '',
        ]
      : [
          `Trade idea vs ${partner.teamName} (DTF Trade Calculator)`,
          `I send: ${names(sendIds)}`,
          `I get: ${names(receiveIds)}`,
          `My board: ${demoEvaluation.myGive.toLocaleString()} out, ${demoEvaluation.myGet.toLocaleString()} back (${formatDelta(demoEvaluation.myDeltaPct)})`,
          `Their board: ${demoEvaluation.theirGive.toLocaleString()} out, ${demoEvaluation.theirGet.toLocaleString()} back (${formatDelta(demoEvaluation.theirDeltaPct)})`,
          `Verdict: ${CALC_VERDICT_LABEL[demoEvaluation.verdict]}`,
        ];
    try {
      await Share.share({ message: lines.filter(Boolean).join('\n') });
    } catch {
      /* user dismissed or share unavailable — nothing to do */
    }
  };

  const liveReady = !!valuesQuery.data;

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Mode switch: real consensus values vs the seeded demo league. */}
        <View style={styles.modeRow}>
          {(
            [
              { key: 'live', label: 'Real values' },
              { key: 'demo', label: 'Demo league' },
            ] as { key: CalcMode; label: string }[]
          ).map((m) => {
            const active = mode === m.key;
            return (
              <Pressable
                key={m.key}
                style={[styles.modeChip, active && styles.modeChipActive]}
                onPress={() => switchMode(m.key)}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
              >
                <Text style={[styles.modeText, active && styles.modeTextActive]}>{m.label}</Text>
              </Pressable>
            );
          })}
        </View>

        {isLive ? (
          <>
            <TickLabel>Scoring format</TickLabel>
            <View style={styles.partnerRow}>
              {FORMATS.map((f) => {
                const active = format === f.key;
                return (
                  <Pressable
                    key={f.key}
                    style={[styles.partnerChip, active && styles.partnerChipActive]}
                    onPress={() => switchFormat(f.key)}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                  >
                    <Text style={[styles.partnerText, active && styles.partnerTextActive]}>
                      {f.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={styles.tendency}>
              Live consensus values from the FTF engine — no league or login needed.
            </Text>
            {valuesQuery.isLoading ? (
              <Card>
                <View style={styles.loadingRow}>
                  <ActivityIndicator color={ice.base} />
                  <Text style={type.bodySm}>Loading player values…</Text>
                </View>
              </Card>
            ) : valuesQuery.isError && !valuesQuery.data ? (
              <Card>
                <View style={styles.loadingRow}>
                  <Text style={[type.bodySm, { flex: 1 }]}>
                    Couldn't reach the value server. Retry, or switch to the demo league.
                  </Text>
                  <Button
                    label="Retry"
                    variant="secondary"
                    compact
                    onPress={() => valuesQuery.refetch()}
                  />
                </View>
              </Card>
            ) : null}
          </>
        ) : (
          <>
            <Text style={styles.league}>{CALC_LEAGUE_NAME}</Text>
            <TickLabel>Trade partner</TickLabel>
            <View style={styles.partnerRow}>
              {CALC_PARTNERS.map((o) => {
                const active = o.id === partnerId;
                return (
                  <Pressable
                    key={o.id}
                    style={[styles.partnerChip, active && styles.partnerChipActive]}
                    onPress={() => switchPartner(o.id)}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                  >
                    <Text style={[styles.partnerText, active && styles.partnerTextActive]}>
                      {o.teamName}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={styles.tendency}>
              {partner.ownerName}'s board: {partner.tendency}
            </Text>
          </>
        )}

        <TradeSide
          title={isLive ? 'Side A sends' : 'You send'}
          teamName={isLive ? 'any player' : CALC_MY_TEAM.teamName}
          players={activeSendIds.map((id) => activePlayerById[id]).filter(Boolean)}
          valueOf={(p) => activeBoard[p.id] ?? 0}
          accent={semantic.neg}
          onAdd={() => setPicker('send')}
          onRemove={(id) => {
            haptics.warning();
            setActiveSendIds((ids) => ids.filter((x) => x !== id));
          }}
        />

        <View style={styles.swapRule}>
          <View style={styles.rule} />
          <Icon name="swap" size={16} />
          <View style={styles.rule} />
        </View>

        <TradeSide
          title={isLive ? 'Side B sends' : 'You receive'}
          teamName={isLive ? 'any player' : partner.teamName}
          players={activeReceiveIds.map((id) => activePlayerById[id]).filter(Boolean)}
          valueOf={(p) => activeBoard[p.id] ?? 0}
          accent={semantic.pos}
          onAdd={() => setPicker('receive')}
          onRemove={(id) => {
            haptics.warning();
            setActiveReceiveIds((ids) => ids.filter((x) => x !== id));
          }}
        />

        {isLive ? (
          anySide && evalQuery.data ? (
            <ConsensusVerdictCard evaluation={evalQuery.data} stale={evalQuery.isFetching} />
          ) : anySide && evalQuery.isLoading ? (
            <Card>
              <View style={styles.loadingRow}>
                <ActivityIndicator color={ice.base} />
                <Text style={type.bodySm}>Evaluating…</Text>
              </View>
            </Card>
          ) : null
        ) : bothSides ? (
          <VerdictPanel evaluation={demoEvaluation} />
        ) : anySide ? (
          <Card>
            <Text style={styles.oneSidedText}>
              {sendIds.length > 0 ? (
                <>
                  That package is worth{' '}
                  <Text style={styles.oneSidedValue}>
                    {demoEvaluation.myGive.toLocaleString()}
                  </Text>{' '}
                  on your board and{' '}
                  <Text style={styles.oneSidedValue}>
                    {demoEvaluation.theirGet.toLocaleString()}
                  </Text>{' '}
                  on {partner.ownerName}'s.
                </>
              ) : (
                <>
                  That package is worth{' '}
                  <Text style={styles.oneSidedValue}>
                    {demoEvaluation.myGet.toLocaleString()}
                  </Text>{' '}
                  on your board and{' '}
                  <Text style={styles.oneSidedValue}>
                    {demoEvaluation.theirGive.toLocaleString()}
                  </Text>{' '}
                  on {partner.ownerName}'s.
                </>
              )}
            </Text>
          </Card>
        ) : null}

        {addOns && addOns.suggestions.length > 0 ? (
          <View style={styles.suggestions}>
            <TickLabel color={semantic.warn}>
              {isLive
                ? addOns.forSide === 'send'
                  ? 'To balance — add to Side A'
                  : 'To balance — add to Side B'
                : addOns.forSide === 'send'
                ? 'To balance — add from your side'
                : `To balance — ask ${partner.teamName} to add`}
            </TickLabel>
            {addOns.suggestions.map((s) => (
              <SuggestionCard
                key={'addon:' + s.players.map((p) => p.id).join('+')}
                suggestion={s}
                onApply={() => applyAddOn(s.players.map((p) => p.id), addOns.forSide)}
              />
            ))}
          </View>
        ) : null}

        {suggested && suggested.suggestions.length > 0 ? (
          <View style={styles.suggestions}>
            <TickLabel>
              {isLive
                ? suggested.forSide === 'receive'
                  ? 'Fair returns (consensus)'
                  : 'Fair offers (consensus)'
                : suggested.forSide === 'receive'
                ? `Fair asks from ${partner.teamName}`
                : `Fair offers from your roster`}
            </TickLabel>
            {suggested.suggestions.map((s) => (
              <SuggestionCard
                key={s.players.map((p) => p.id).join('+')}
                suggestion={s}
                onApply={() => applySuggestion(s.players.map((p) => p.id), suggested.forSide)}
              />
            ))}
          </View>
        ) : anySide && suggested && (!isLive || liveReady) ? (
          <Text style={styles.noSuggestions}>
            No fair {suggested.forSide === 'receive' ? 'return' : 'offer'} found for that package —
            try adding or removing a piece.
          </Text>
        ) : null}

        {anySide ? (
          <View style={styles.actions}>
            {bothSides && (!isLive || evalQuery.data) ? (
              <Button label="Share trade" variant="secondary" onPress={shareTrade} />
            ) : null}
            <Button
              label="Clear trade"
              variant="ghost"
              onPress={() => {
                haptics.warning();
                setActiveSendIds([]);
                setActiveReceiveIds([]);
              }}
            />
          </View>
        ) : null}
      </ScrollView>

      <PlayerPickerModal
        visible={picker === 'send'}
        title={isLive ? 'Add to Side A' : `Send from ${CALC_MY_TEAM.teamName}`}
        players={
          isLive ? livePlayers : CALC_MY_TEAM.rosterIds.map((id) => CALC_PLAYER_BY_ID[id])
        }
        selectedIds={[...activeSendIds, ...activeReceiveIds]}
        ownerBoardValue={(p: CalcPlayer) => activeBoard[p.id] ?? 0}
        secondaryValue={isLive ? undefined : (p: CalcPlayer) => theirBoard[p.id]}
        secondaryPrefix="them"
        badgeFor={
          isLive
            ? undefined
            : (p: CalcPlayer) =>
                theirBoard[p.id] >= MY_BOARD[p.id] * ARBITRAGE_EDGE
                  ? { label: 'Sell high', color: flare.base }
                  : null
        }
        onPick={(p) => {
          haptics.selection();
          setActiveSendIds((ids) => [...ids, p.id]);
        }}
        onClose={() => setPicker(null)}
      />

      <PlayerPickerModal
        visible={picker === 'receive'}
        title={isLive ? 'Add to Side B' : `Receive from ${partner.teamName}`}
        players={isLive ? livePlayers : partner.rosterIds.map((id) => CALC_PLAYER_BY_ID[id])}
        selectedIds={[...activeSendIds, ...activeReceiveIds]}
        ownerBoardValue={(p: CalcPlayer) => activeOtherBoard[p.id] ?? 0}
        secondaryValue={isLive ? undefined : (p: CalcPlayer) => MY_BOARD[p.id]}
        secondaryPrefix="you"
        badgeFor={
          isLive
            ? undefined
            : (p: CalcPlayer) =>
                MY_BOARD[p.id] >= theirBoard[p.id] * ARBITRAGE_EDGE
                  ? { label: 'Target', color: semantic.pos }
                  : null
        }
        onPick={(p) => {
          haptics.selection();
          setActiveReceiveIds((ids) => [...ids, p.id]);
        }}
        onClose={() => setPicker(null)}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, gap: space.md, paddingBottom: space.xxl + space.lg },
  league: { ...type.bodySm },
  modeRow: {
    flexDirection: 'row',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    overflow: 'hidden',
  },
  modeChip: {
    flex: 1,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
  },
  modeChipActive: { backgroundColor: ink.ink3 },
  modeText: { fontFamily: fonts.uiSemi, fontSize: 13, lineHeight: 18, color: chalk.dim },
  modeTextActive: { color: ice.base },
  partnerRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  partnerChip: {
    minHeight: 44,
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: 'transparent',
    paddingHorizontal: space.md,
  },
  partnerChipActive: { borderColor: ice.base },
  partnerChipPressed: { backgroundColor: ink.ink3 },
  partnerText: { fontFamily: fonts.uiSemi, fontSize: 13, lineHeight: 18, color: chalk.dim },
  partnerTextActive: { color: chalk.base },
  tendency: { ...type.bodySm },
  loadingRow: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  swapRule: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
  },
  rule: { flex: 1, height: 1, backgroundColor: ink.line },
  oneSidedText: { ...type.body },
  oneSidedValue: { ...type.data },
  suggestions: { gap: space.sm },
  noSuggestions: { ...type.bodySm },
  actions: { gap: space.sm, alignItems: 'center' },
});

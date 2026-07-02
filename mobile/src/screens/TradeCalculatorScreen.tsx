import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  CALC_LEAGUE_NAME,
  CALC_MY_TEAM,
  CALC_PARTNERS,
  CALC_PLAYER_BY_ID,
  CalcPlayer,
  boardFor,
} from '../data/tradeCalcMock';
import { evaluateTrade, suggestPackages } from '../utils/tradeCalcMath';
import TradeSide from '../components/TradeSide';
import VerdictPanel from '../components/VerdictPanel';
import SuggestionCard from '../components/SuggestionCard';
import PlayerPickerModal from '../components/PlayerPickerModal';
import { Button, Card, Icon, TickLabel } from '../components/chalkline';
import { haptics } from '../utils/haptics';
import { chalk, fonts, ink, semantic, space, radii, type, volt } from '../theme/chalkline';

// Manual Trade Calculator (demo) — hand-build a trade against a mock
// leaguemate and see a live dual-board fairness verdict + fair-offer
// suggestions. Ported from mockups/trade-calc/; runs entirely on the
// seeded mock boards in data/tradeCalcMock.ts (no league, no network).
// The server-authoritative version replaces the mock plumbing per
// docs/plans/manual-trade-calculator-plan.md.

const MY_BOARD = boardFor(CALC_MY_TEAM);
const PARTNER_BOARDS = Object.fromEntries(CALC_PARTNERS.map((o) => [o.id, boardFor(o)]));

export default function TradeCalculatorScreen() {
  const [partnerId, setPartnerId] = useState(CALC_PARTNERS[0].id);
  const [sendIds, setSendIds] = useState<string[]>([]);
  const [receiveIds, setReceiveIds] = useState<string[]>([]);
  const [picker, setPicker] = useState<'send' | 'receive' | null>(null);

  const partner = CALC_PARTNERS.find((o) => o.id === partnerId)!;
  const theirBoard = PARTNER_BOARDS[partnerId];

  const evaluation = useMemo(
    () => evaluateTrade(sendIds, receiveIds, MY_BOARD, theirBoard),
    [sendIds, receiveIds, theirBoard],
  );

  const suggested = useMemo(
    () =>
      suggestPackages(
        sendIds,
        receiveIds,
        CALC_MY_TEAM.rosterIds,
        partner.rosterIds,
        MY_BOARD,
        theirBoard,
      ),
    [sendIds, receiveIds, partner, theirBoard],
  );

  const bothSides = sendIds.length > 0 && receiveIds.length > 0;
  const anySide = sendIds.length > 0 || receiveIds.length > 0;

  const switchPartner = (id: string) => {
    haptics.selection();
    setPartnerId(id);
    setReceiveIds([]); // their roster changed; what you send can stay
  };

  const applySuggestion = (playerIds: string[], side: 'send' | 'receive') => {
    haptics.selection();
    if (side === 'receive') setReceiveIds(playerIds);
    else setSendIds(playerIds);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.league}>{CALC_LEAGUE_NAME}</Text>

        <TickLabel>Trade partner</TickLabel>
        <View style={styles.partnerRow}>
          {CALC_PARTNERS.map((o) => {
            const active = o.id === partnerId;
            return (
              <Pressable
                key={o.id}
                style={({ pressed }) => [
                  styles.partnerChip,
                  active && styles.partnerChipActive,
                  pressed && styles.partnerChipPressed,
                ]}
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

        <TradeSide
          title="You send"
          teamName={CALC_MY_TEAM.teamName}
          players={sendIds.map((id) => CALC_PLAYER_BY_ID[id])}
          valueOf={(p) => MY_BOARD[p.id]}
          accent={semantic.neg}
          onAdd={() => setPicker('send')}
          onRemove={(id) => {
            haptics.warning();
            setSendIds((ids) => ids.filter((x) => x !== id));
          }}
        />

        <View style={styles.swapRule}>
          <View style={styles.rule} />
          <Icon name="swap" size={16} />
          <View style={styles.rule} />
        </View>

        <TradeSide
          title="You receive"
          teamName={partner.teamName}
          players={receiveIds.map((id) => CALC_PLAYER_BY_ID[id])}
          valueOf={(p) => MY_BOARD[p.id]}
          accent={semantic.pos}
          onAdd={() => setPicker('receive')}
          onRemove={(id) => {
            haptics.warning();
            setReceiveIds((ids) => ids.filter((x) => x !== id));
          }}
        />

        {bothSides ? (
          <VerdictPanel evaluation={evaluation} />
        ) : anySide ? (
          <Card>
            <Text style={styles.oneSidedText}>
              {sendIds.length > 0 ? (
                <>
                  That package is worth{' '}
                  <Text style={styles.oneSidedValue}>{evaluation.myGive.toLocaleString()}</Text> on
                  your board and{' '}
                  <Text style={styles.oneSidedValue}>{evaluation.theirGet.toLocaleString()}</Text>{' '}
                  on {partner.ownerName}'s.
                </>
              ) : (
                <>
                  That package is worth{' '}
                  <Text style={styles.oneSidedValue}>{evaluation.myGet.toLocaleString()}</Text> on
                  your board and{' '}
                  <Text style={styles.oneSidedValue}>{evaluation.theirGive.toLocaleString()}</Text>{' '}
                  on {partner.ownerName}'s.
                </>
              )}
            </Text>
          </Card>
        ) : null}

        {suggested && suggested.suggestions.length > 0 ? (
          <View style={styles.suggestions}>
            <TickLabel>
              {suggested.forSide === 'receive'
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
        ) : anySide && suggested ? (
          <Text style={styles.noSuggestions}>
            No fair {suggested.forSide === 'receive' ? 'return' : 'offer'} found for that package —
            try adding or removing a piece.
          </Text>
        ) : null}

        {anySide ? (
          <Button
            label="Clear trade"
            variant="ghost"
            onPress={() => {
              haptics.warning();
              setSendIds([]);
              setReceiveIds([]);
            }}
            style={styles.clear}
          />
        ) : null}
      </ScrollView>

      <PlayerPickerModal
        visible={picker === 'send'}
        title={`Send from ${CALC_MY_TEAM.teamName}`}
        players={CALC_MY_TEAM.rosterIds.map((id) => CALC_PLAYER_BY_ID[id])}
        selectedIds={sendIds}
        ownerBoardValue={(p: CalcPlayer) => MY_BOARD[p.id]}
        onPick={(p) => {
          haptics.selection();
          setSendIds((ids) => [...ids, p.id]);
        }}
        onClose={() => setPicker(null)}
      />

      <PlayerPickerModal
        visible={picker === 'receive'}
        title={`Receive from ${partner.teamName}`}
        players={partner.rosterIds.map((id) => CALC_PLAYER_BY_ID[id])}
        selectedIds={receiveIds}
        ownerBoardValue={(p: CalcPlayer) => theirBoard[p.id]}
        yourBoardValue={(p: CalcPlayer) => MY_BOARD[p.id]}
        onPick={(p) => {
          haptics.selection();
          setReceiveIds((ids) => [...ids, p.id]);
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
  partnerChipActive: { borderColor: volt.base },
  partnerChipPressed: { backgroundColor: ink.ink3 },
  partnerText: { fontFamily: fonts.uiSemi, fontSize: 13, lineHeight: 18, color: chalk.dim },
  partnerTextActive: { color: chalk.base },
  tendency: { ...type.bodySm },
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
  clear: { alignSelf: 'center' },
});

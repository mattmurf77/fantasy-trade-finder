import React, { useMemo, useState } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as Haptics from 'expo-haptics';

import {
  LEAGUE_NAME,
  MY_TEAM,
  PARTNERS,
  PLAYER_BY_ID,
  Player,
  boardFor,
} from './src/data/mock';
import { evaluateTrade, suggestPackages } from './src/logic/tradeMath';
import { TradeSide } from './src/components/TradeSide';
import { VerdictPanel } from './src/components/VerdictPanel';
import { SuggestionCard } from './src/components/SuggestionCard';
import { PlayerPickerModal } from './src/components/PlayerPickerModal';
import { colors, fontSize, radius, spacing } from './src/theme';

function tap() {
  if (Platform.OS !== 'web') {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  }
}

const MY_BOARD = boardFor(MY_TEAM);
const PARTNER_BOARDS = Object.fromEntries(PARTNERS.map((o) => [o.id, boardFor(o)]));

function Calculator() {
  const [partnerId, setPartnerId] = useState(PARTNERS[0].id);
  const [sendIds, setSendIds] = useState<string[]>([]);
  const [receiveIds, setReceiveIds] = useState<string[]>([]);
  const [picker, setPicker] = useState<'send' | 'receive' | null>(null);

  const partner = PARTNERS.find((o) => o.id === partnerId)!;
  const theirBoard = PARTNER_BOARDS[partnerId];

  const evaluation = useMemo(
    () => evaluateTrade(sendIds, receiveIds, MY_BOARD, theirBoard),
    [sendIds, receiveIds, theirBoard],
  );

  const suggested = useMemo(
    () =>
      suggestPackages(sendIds, receiveIds, MY_TEAM.rosterIds, partner.rosterIds, MY_BOARD, theirBoard),
    [sendIds, receiveIds, partner, theirBoard],
  );

  const bothSides = sendIds.length > 0 && receiveIds.length > 0;
  const anySide = sendIds.length > 0 || receiveIds.length > 0;

  const switchPartner = (id: string) => {
    tap();
    setPartnerId(id);
    setReceiveIds([]); // their roster changed; what you send can stay
  };

  const applySuggestion = (playerIds: string[], side: 'send' | 'receive') => {
    tap();
    if (side === 'receive') setReceiveIds(playerIds);
    else setSendIds(playerIds);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <StatusBar style="light" />
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.topBar}>
          <Text style={styles.appTitle}>Trade Calculator</Text>
          <Text style={styles.league}>{LEAGUE_NAME}</Text>
        </View>

        <Text style={styles.sectionLabel}>Trade partner</Text>
        <View style={styles.partnerRow}>
          {PARTNERS.map((o) => {
            const active = o.id === partnerId;
            return (
              <Pressable
                key={o.id}
                style={[styles.partnerChip, active && styles.partnerChipActive]}
                onPress={() => switchPartner(o.id)}
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
          teamName={MY_TEAM.teamName}
          players={sendIds.map((id) => PLAYER_BY_ID[id])}
          valueOf={(p) => MY_BOARD[p.id]}
          accent={colors.red}
          onAdd={() => setPicker('send')}
          onRemove={(id) => {
            tap();
            setSendIds((ids) => ids.filter((x) => x !== id));
          }}
        />

        <TradeSide
          title="You receive"
          teamName={partner.teamName}
          players={receiveIds.map((id) => PLAYER_BY_ID[id])}
          valueOf={(p) => MY_BOARD[p.id]}
          accent={colors.green}
          onAdd={() => setPicker('receive')}
          onRemove={(id) => {
            tap();
            setReceiveIds((ids) => ids.filter((x) => x !== id));
          }}
        />

        {bothSides ? (
          <VerdictPanel evaluation={evaluation} />
        ) : anySide ? (
          <View style={styles.oneSided}>
            <Text style={styles.oneSidedText}>
              {sendIds.length > 0
                ? `That package is worth ${evaluation.myGive.toLocaleString()} on your board and ${evaluation.theirGet.toLocaleString()} on ${partner.ownerName}'s.`
                : `That package is worth ${evaluation.myGet.toLocaleString()} on your board and ${evaluation.theirGive.toLocaleString()} on ${partner.ownerName}'s.`}
            </Text>
          </View>
        ) : null}

        {suggested && suggested.suggestions.length > 0 ? (
          <View style={styles.suggestions}>
            <Text style={styles.sectionLabel}>
              {suggested.forSide === 'receive'
                ? `Fair asks from ${partner.teamName}`
                : `Fair offers from your roster`}
            </Text>
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
          <Pressable
            style={styles.clear}
            onPress={() => {
              tap();
              setSendIds([]);
              setReceiveIds([]);
            }}
          >
            <Text style={styles.clearText}>Clear trade</Text>
          </Pressable>
        ) : null}
      </ScrollView>

      <PlayerPickerModal
        visible={picker === 'send'}
        title={`Send from ${MY_TEAM.teamName}`}
        players={MY_TEAM.rosterIds.map((id) => PLAYER_BY_ID[id])}
        selectedIds={sendIds}
        ownerBoardValue={(p: Player) => MY_BOARD[p.id]}
        onPick={(p) => {
          tap();
          setSendIds((ids) => [...ids, p.id]);
        }}
        onClose={() => setPicker(null)}
      />

      <PlayerPickerModal
        visible={picker === 'receive'}
        title={`Receive from ${partner.teamName}`}
        players={partner.rosterIds.map((id) => PLAYER_BY_ID[id])}
        selectedIds={receiveIds}
        ownerBoardValue={(p: Player) => theirBoard[p.id]}
        yourBoardValue={(p: Player) => MY_BOARD[p.id]}
        onPick={(p) => {
          tap();
          setReceiveIds((ids) => [...ids, p.id]);
        }}
        onClose={() => setPicker(null)}
      />
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <Calculator />
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  topBar: { gap: 2 },
  appTitle: { color: colors.text, fontSize: fontSize.xl, fontWeight: '800' },
  league: { color: colors.muted, fontSize: fontSize.sm },
  sectionLabel: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginTop: spacing.xs,
  },
  partnerRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  partnerChip: {
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
  },
  partnerChipActive: { borderColor: colors.accent, backgroundColor: colors.accent + '22' },
  partnerText: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '600' },
  partnerTextActive: { color: colors.accent },
  tendency: { color: colors.muted, fontSize: fontSize.xs, fontStyle: 'italic' },
  oneSided: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
  },
  oneSidedText: { color: colors.text, fontSize: fontSize.sm, lineHeight: 20 },
  suggestions: { gap: spacing.sm },
  noSuggestions: { color: colors.muted, fontSize: fontSize.sm },
  clear: { alignItems: 'center', paddingVertical: spacing.sm },
  clearText: { color: colors.red, fontSize: fontSize.sm, fontWeight: '600' },
});

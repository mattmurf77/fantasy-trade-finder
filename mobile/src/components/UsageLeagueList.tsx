import React from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Icon, PositionBadge, Text, TickLabel } from './chalkline';
import { chalk, fonts, ink, radii, scrim, semantic, shadowSheet, space, type } from '../theme/chalkline';
import type { UsagePlayer } from '../api/usageTrends';
import type { LeagueStatus } from '../utils/usageTrends';

// Usage Trends (docs/plans/usage-trends/scope.md) — a player's status in each
// of the caller's leagues. One list, two homes: the Version A availability
// sheet (below) and the Version B table's expanded row (`compact`). Each row
// carries the league's own action: Add when he is a free agent there, Trade
// when another manager has him. The screen owns what those do (acting in a
// league other than the focused one switches leagues first).

export interface UsageLeagueRow {
  league_id: string;
  name: string;
  formatLine: string | null;
  isFocus: boolean;
  status: LeagueStatus;
  owner: string | null;
}

export function StatusPip({ status, size = 8 }: { status: LeagueStatus; size?: number }) {
  const base = { width: size, height: size, borderRadius: radii.xs };
  if (status === 'free_agent') return <View style={[base, { backgroundColor: semantic.pos }]} />;
  if (status === 'mine') return <View style={[base, { backgroundColor: chalk.base }]} />;
  return <View style={[base, { borderWidth: 1.5, borderColor: ink.lineStrongA11y }]} />;
}

function statusText(row: UsageLeagueRow) {
  switch (row.status) {
    case 'free_agent':
      return <Text style={[styles.status, styles.statusFa]}>Free agent</Text>;
    case 'mine':
      return <Text style={[styles.status, { color: chalk.base }]}>On your roster</Text>;
    case 'rostered':
      return (
        <Text style={styles.status} numberOfLines={1}>
          Rostered by{' '}
          <Text style={styles.statusOwner}>{row.owner ?? 'another team'}</Text>
        </Text>
      );
    default:
      return <Text style={styles.status}>Couldn't check this league</Text>;
  }
}

export function UsageLeagueList({
  player,
  rows,
  onAdd,
  onTrade,
  compact = false,
}: {
  player: UsagePlayer;
  rows: UsageLeagueRow[];
  onAdd: (leagueId: string) => void;
  onTrade: (leagueId: string) => void;
  compact?: boolean;
}) {
  return (
    <View>
      {rows.map((row, i) => (
        <View
          key={row.league_id}
          style={[styles.row, compact && styles.rowCompact, i === rows.length - 1 && styles.rowLast]}
          testID={`usage-trends.league.${player.player_id}.${row.league_id}`}
        >
          <View style={styles.rowText}>
            <Text style={compact ? styles.nameCompact : styles.name} numberOfLines={1}>
              {row.name}
            </Text>
            {row.formatLine || row.isFocus ? (
              <View style={styles.metaRow}>
                {row.formatLine ? <Text style={type.bodySm}>{row.formatLine}</Text> : null}
                {row.isFocus ? (
                  <View style={styles.tag}><Text scale="dense" style={styles.tagText}>This league</Text></View>
                ) : null}
              </View>
            ) : null}
            <View style={styles.statusRow}>
              <StatusPip status={row.status} />
              {statusText(row)}
            </View>
          </View>
          {row.status === 'free_agent' || row.status === 'rostered' ? (
            <Pressable
              testID={`usage-trends.league-action.${player.player_id}.${row.league_id}`}
              accessibilityRole="button"
              accessibilityLabel={
                row.status === 'free_agent'
                  ? `Add ${player.name} in ${row.name}`
                  : `Find a trade for ${player.name} in ${row.name}`
              }
              onPress={() =>
                row.status === 'free_agent' ? onAdd(row.league_id) : onTrade(row.league_id)
              }
              style={({ pressed }) => [styles.action, pressed && styles.actionPressed]}
            >
              <Icon name={row.status === 'free_agent' ? 'plus' : 'trade'} size={16} color={chalk.base} />
              <Text style={styles.actionText}>{row.status === 'free_agent' ? 'Add' : 'Trade'}</Text>
            </Pressable>
          ) : null}
        </View>
      ))}
    </View>
  );
}

export function UsageAvailabilitySheet({
  player,
  rows,
  onAdd,
  onTrade,
  onClose,
}: {
  player: UsagePlayer;
  rows: UsageLeagueRow[];
  onAdd: (leagueId: string) => void;
  onTrade: (leagueId: string) => void;
  onClose: () => void;
}) {
  const known = rows.filter((r) => r.status !== 'unknown').length;
  const fa = rows.filter((r) => r.status === 'free_agent').length;
  const summary =
    known === 0
      ? "Couldn't check your leagues right now."
      : fa === 0
        ? `Not a free agent in any of your ${known} ${known === 1 ? 'league' : 'leagues'}.`
        : fa === known
          ? `Free agent in all ${known} of your leagues.`
          : `Free agent in ${fa} of your ${known} leagues.`;
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} accessibilityRole="button" accessibilityLabel="Close" />
      <View style={styles.sheet} testID="usage-trends.availability-sheet">
        <SafeAreaView edges={['bottom']}>
          <View style={styles.grabber} />
          <ScrollView contentContainerStyle={styles.sheetContent}>
            <View style={styles.header}>
              <View style={styles.headerText}>
                <TickLabel>AVAILABILITY IN YOUR LEAGUES</TickLabel>
                <View style={styles.headerName}>
                  <Text style={type.heading} numberOfLines={1} accessibilityRole="header">{player.name}</Text>
                  <PositionBadge pos={player.position} />
                  <Text style={type.bodySm}>{player.team}</Text>
                </View>
                <Text style={type.bodySm}>{summary}</Text>
              </View>
              <Pressable
                testID="usage-trends.availability-close"
                accessibilityRole="button"
                accessibilityLabel="Close"
                onPress={onClose}
                style={styles.close}
              >
                <Icon name="x" size={20} color={chalk.dim} />
              </Pressable>
            </View>
            <UsageLeagueList player={player} rows={rows} onAdd={onAdd} onTrade={onTrade} />
            <Text style={styles.footer}>
              Add opens a quick claim check, then finishes in the Sleeper app. Trade opens the trade
              finder in that league.
            </Text>
          </ScrollView>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    borderTopWidth: 1,
    borderTopColor: ink.line,
  },
  rowCompact: { paddingVertical: space.sm },
  rowLast: { borderBottomWidth: 1, borderBottomColor: ink.line },
  rowText: { flex: 1, minWidth: 0, gap: 2 },
  name: { ...type.title },
  nameCompact: { ...type.title, fontSize: 14, lineHeight: 20 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, flexWrap: 'wrap' },
  tag: {
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.xs,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  tagText: { ...type.label },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 },
  status: { ...type.bodySm, flexShrink: 1 },
  statusFa: { color: semantic.pos, fontFamily: fonts.uiSemi },
  statusOwner: { color: chalk.base, fontFamily: fonts.uiSemi },
  action: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.sm,
    flexShrink: 0,
  },
  actionPressed: { backgroundColor: ink.ink3 },
  actionText: { ...type.body, fontFamily: fonts.uiSemi },

  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '85%',
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrongA11y,
    marginTop: space.sm,
  },
  sheetContent: { paddingHorizontal: space.lg, paddingBottom: space.xl, gap: space.md },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: space.sm, paddingTop: space.sm },
  headerText: { flex: 1, minWidth: 0, gap: 6 },
  headerName: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  close: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center', marginTop: -6, marginRight: -10 },
  footer: { ...type.bodySm, paddingTop: space.xs },
});

import React from 'react';
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { ink, chalk, space, radii, type, semantic } from '../theme/chalkline';
import { posColor } from '../theme/colors';
import { Icon, TickLabel, Card } from './chalkline';
import type { AssetIdea, AssetIdeasResponse } from '../api/trades';
import type { Player } from '../shared/types';

// #172/#189 follow-up (flag trade.asset_ideas) — grouped Upgrade / Lateral /
// Downgrade ideas for the single pinned asset, the Dynasty-Trade-Factory
// "Smart Trade Finder" presentation. Renders alongside the deck on
// TradesScreen when exactly ONE finder target is pinned; each compact row is
// "your side ↔ their side · counterparty" with a signed difference chip, and
// tapping it hands the package to the calculator (#190 prefill).
//
// #198 — semantics are position-centric: Upgrade/Lateral are constrained to
// the pin's position server-side, so the group headers name it ("Upgrade at
// WR"). Downgrade stays value-based (same-position headliners ordered first
// by the backend) and keeps a neutral header. PICK pins have no position —
// headers fall back to the generic labels.

interface Props {
  data: AssetIdeasResponse | undefined;
  loading: boolean;
  pinnedName: string;
  direction: 'give' | 'receive';
  onOpenIdea: (idea: AssetIdea) => void;
}

const GROUP_KEYS = ['upgrade', 'lateral', 'downgrade'] as const;

function groupTitle(
  key: (typeof GROUP_KEYS)[number],
  pinPos: string | null,
): string {
  if (key === 'upgrade') return pinPos ? `Upgrade at ${pinPos}` : 'Upgrade ideas';
  if (key === 'lateral') return pinPos ? `Lateral moves at ${pinPos}` : 'Lateral moves';
  return 'Downgrade ideas';
}

function sideLabel(players: Player[]): string {
  return players.map((p) => p.name).join(' + ') || '?';
}

function IdeaRow({ idea, onPress }: { idea: AssetIdea; onPress: () => void }) {
  const diff = idea.difference;
  const gain = diff >= 0;
  // Position dot keyed off each side's first (headline) asset.
  const givePos = idea.give[0]?.position;
  const recvPos = idea.receive[0]?.position;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`Trade ${sideLabel(idea.give)} for ${sideLabel(
        idea.receive,
      )} with ${idea.counterparty_username}`}
      style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
    >
      <View style={styles.rowMain}>
        <View style={styles.sides}>
          {givePos ? (
            <View
              style={[styles.posDot, { backgroundColor: posColor(givePos as any) }]}
            />
          ) : null}
          <Text style={[type.body, styles.sideText]} numberOfLines={1}>
            {sideLabel(idea.give)}
          </Text>
          <Icon name="swap" size={14} color={chalk.faint} />
          {recvPos ? (
            <View
              style={[styles.posDot, { backgroundColor: posColor(recvPos as any) }]}
            />
          ) : null}
          <Text style={[type.body, styles.sideText]} numberOfLines={1}>
            {sideLabel(idea.receive)}
          </Text>
        </View>
        <Text style={[type.bodySm, styles.metaLine]} numberOfLines={1}>
          {idea.counterparty_username}
          {'  ·  '}
          <Text style={type.data}>{Math.round(idea.give_value)}</Text>
          {' ↔ '}
          <Text style={type.data}>{Math.round(idea.receive_value)}</Text>
          {idea.relaxed ? '  ·  Stretch — outside your fairness band' : ''}
        </Text>
      </View>
      <View
        style={[
          styles.diffChip,
          gain ? styles.diffChipPos : styles.diffChipNeg,
        ]}
      >
        <Text
          style={[
            type.data,
            styles.diffText,
            { color: gain ? semantic.pos : semantic.neg },
          ]}
        >
          {gain ? '+' : ''}
          {Math.round(diff)}
        </Text>
      </View>
    </Pressable>
  );
}

export default function AssetIdeasPanel({
  data,
  loading,
  pinnedName,
  direction,
  onOpenIdea,
}: Props) {
  const groups = data?.groups;
  const total = groups
    ? groups.upgrade.length + groups.lateral.length + groups.downgrade.length
    : 0;
  // #198 — the pin's position drives the group headers/copy; PICK pins (and
  // a not-yet-loaded asset) fall back to the generic value-band labels.
  const rawPos = data?.asset?.position;
  const pinPos = rawPos && rawPos !== 'PICK' ? rawPos : null;
  const subtitle =
    direction === 'give'
      ? pinPos
        ? `A better ${pinPos} back (add pieces to close the gap), a sideways ${pinPos} swap, or a spread-out package.`
        : 'What league-mates could send back — tier up, sideways, or down.'
      : pinPos
        ? `What it could cost you — your lesser ${pinPos} plus pieces, an even ${pinPos} swap, or a stud for them plus change.`
        : 'What it could cost you — tier up into them, swap even, or cash down.';
  return (
    <Card>
      <View testID="trades.asset-ideas" style={styles.inner}>
        <TickLabel>
          {direction === 'give' ? 'Ideas for trading away' : 'Ideas for landing'}
        </TickLabel>
        <Text style={[type.title, styles.assetName]} numberOfLines={1}>
          {pinnedName}
        </Text>
        <Text style={[type.bodySm, styles.subtitle]}>{subtitle}</Text>
        {loading ? (
          <View style={styles.loadingRow}>
            <ActivityIndicator color={chalk.dim} size="small" />
            <Text style={type.bodySm}>Sweeping rosters…</Text>
          </View>
        ) : !groups || total === 0 ? (
          <Text style={[type.bodySm, styles.empty]}>
            No defensible packages found around this asset right now.
          </Text>
        ) : (
          GROUP_KEYS.map((key) => {
            const ideas = groups[key];
            if (ideas.length === 0) return null;
            return (
              <View key={key} style={styles.group}>
                <Text style={[type.label, styles.groupTitle]}>
                  {groupTitle(key, pinPos)}
                </Text>
                {ideas.map((idea, i) => (
                  <IdeaRow
                    key={`${key}-${i}-${idea.counterparty_user_id}`}
                    idea={idea}
                    onPress={() => onOpenIdea(idea)}
                  />
                ))}
              </View>
            );
          })
        )}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  inner: { gap: space.xs },
  assetName: { marginTop: 2 },
  subtitle: { marginBottom: space.xs },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
  },
  empty: { paddingVertical: space.sm },
  group: { marginTop: space.sm, gap: space.xs },
  groupTitle: { marginBottom: 2 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.sm,
    paddingVertical: space.sm,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  rowPressed: { backgroundColor: ink.ink3 },
  rowMain: { flex: 1, minWidth: 0, gap: 2 },
  sides: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    minWidth: 0,
  },
  sideText: { flexShrink: 1 },
  posDot: { width: 6, height: 6, borderRadius: 3 },
  metaLine: { color: chalk.dim },
  diffChip: {
    paddingHorizontal: space.sm,
    paddingVertical: 2,
    borderRadius: radii.xs,
    borderWidth: 1,
  },
  diffChipPos: { borderColor: 'rgba(34,197,94,0.4)' },
  diffChipNeg: { borderColor: 'rgba(239,68,68,0.4)' },
  diffText: { fontSize: 12, lineHeight: 16 },
});

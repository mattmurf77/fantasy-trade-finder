import React from 'react';
import { View, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import { ink, chalk, ice, space, radii, type, semantic } from '../theme/chalkline';
import { posColor } from '../theme/colors';
import { Icon, TickLabel, Card, Text } from './chalkline';
import { assetIdeaKey } from './FeaturedTradeWindow';
import type { AssetIdea, AssetIdeasResponse } from '../api/trades';
import type { Player } from '../shared/types';

// #172/#189 follow-up (flag trade.asset_ideas) — grouped Upgrade / Lateral /
// Downgrade ideas for the single pinned asset. #216 reworked the panel into
// the "More trades for <pin>" list under the FeaturedTradeWindow (approved
// mock: mockups/polish-lab-2026-08/asset-ideas-layout-v2 + -v3): rows are
// tappable and load their trade INTO the window above (the host owns the
// window + history state); the row currently in the window carries an
// "In window" tag (ice border, no chevron) and ignores taps. Rows keep the
// signed diff chip and DROP the raw value pair (v2 tenet note) — the full
// verdict lives in the window.
//
// #198 — semantics stay position-centric: Upgrade/Lateral are constrained
// to the pin's position server-side, so the group headers name it
// ("Upgrade at WR"). PICK pins fall back to the generic labels.

interface Props {
  data: AssetIdeasResponse | undefined;
  loading: boolean;
  pinnedName: string;
  direction: 'give' | 'receive';
  /** assetIdeaKey of the idea currently in the featured window. */
  featuredKey: string | null;
  /** Tap a row → feature that idea (host swaps the window + records history). */
  onSelectIdea: (idea: AssetIdea) => void;
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

function IdeaRow({
  idea,
  featured,
  onPress,
}: {
  idea: AssetIdea;
  featured: boolean;
  onPress: () => void;
}) {
  const diff = idea.difference;
  const gain = diff >= 0;
  // Position dot keyed off each side's first (headline) asset.
  const givePos = idea.give[0]?.position;
  const recvPos = idea.receive[0]?.position;
  return (
    <Pressable
      testID={`featured-trade.idea.${assetIdeaKey(idea)}`}
      onPress={featured ? undefined : onPress}
      disabled={featured}
      accessibilityRole="button"
      accessibilityState={featured ? { selected: true, disabled: true } : undefined}
      accessibilityLabel={
        `Trade ${sideLabel(idea.give)} for ${sideLabel(idea.receive)} with ` +
        `${idea.counterparty_username}` +
        (featured ? ', currently in the featured window' : '')
      }
      style={({ pressed }) => [
        styles.row,
        featured && styles.rowFeatured,
        pressed && !featured && styles.rowPressed,
      ]}
    >
      {/* #240 — the give↔receive line owns (nearly) the full row width so
          names render fully or ellipsize; the diff chip and IN WINDOW tag
          live on the meta line below instead of squeezing the name column
          from a fixed-width right rail (which crushed names to a few
          characters and, at large Dynamic Type sizes, overflowed the
          fixed-size dots/swap glyph underneath the chip). Only the 14pt
          chevron stays beside the names. */}
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
        <View style={styles.metaRow}>
          <Text style={[type.bodySm, styles.metaLine]} numberOfLines={1}>
            {idea.counterparty_username}
            {idea.relaxed ? '  ·  Stretch — outside your fairness band' : ''}
          </Text>
          <View
            style={[
              styles.diffChip,
              gain ? styles.diffChipPos : styles.diffChipNeg,
            ]}
          >
            <Text
              scale="dense"
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
          {featured ? (
            <View style={styles.inTag}>
              <Text scale="dense" style={styles.inTagText}>
                IN WINDOW
              </Text>
            </View>
          ) : null}
        </View>
      </View>
      {featured ? null : (
        <Icon name="chevron-right" size={14} color={chalk.faint} />
      )}
    </Pressable>
  );
}

export default function AssetIdeasPanel({
  data,
  loading,
  pinnedName,
  direction,
  featuredKey,
  onSelectIdea,
}: Props) {
  const groups = data?.groups;
  const total = groups
    ? groups.upgrade.length + groups.lateral.length + groups.downgrade.length
    : 0;
  // #198 — the pin's position drives the group headers; PICK pins (and a
  // not-yet-loaded asset) fall back to the generic value-band labels.
  const rawPos = data?.asset?.position;
  const pinPos = rawPos && rawPos !== 'PICK' ? rawPos : null;
  return (
    <Card>
      <View testID="trades.asset-ideas" style={styles.inner}>
        <TickLabel>
          {direction === 'give'
            ? `More trades for ${pinnedName}`
            : `More ways to land ${pinnedName}`}
        </TickLabel>
        {loading ? (
          <View style={styles.loadingRow}>
            <ActivityIndicator color={chalk.dim} size="small" />
            <Text style={type.bodySm}>Sweeping rosters…</Text>
          </View>
        ) : !groups || total === 0 ? (
          <Text style={[type.bodySm, styles.empty]}>
            {/* D-178 QA-B B-6 — the line below is a claim about PACKAGE
                QUALITY, and since D-178 the server can empty this panel
                purely because the user already sent every package it would
                have listed. Those packages were defensible enough to offer,
                so say what actually happened. Only reachable when the route
                says so (`excluded_count`); a panel emptied by anything else
                keeps the sentence that is still true for it. */}
            {(data?.excluded_count ?? 0) > 0
              ? 'You have already offered every package we would build around this asset. Retract one under Awaiting them and it comes back here.'
              : 'No defensible packages found around this asset right now.'}
          </Text>
        ) : (
          GROUP_KEYS.map((key) => {
            const ideas = groups[key];
            if (ideas.length === 0) return null;
            return (
              <View key={key} style={styles.group}>
                <Text scale="dense" style={[type.label, styles.groupTitle]}>
                  {groupTitle(key, pinPos)}
                </Text>
                {ideas.map((idea) => {
                  const k = assetIdeaKey(idea);
                  return (
                    <IdeaRow
                      key={`${key}-${k}`}
                      idea={idea}
                      featured={k === featuredKey}
                      onPress={() => onSelectIdea(idea)}
                    />
                  );
                })}
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
    minHeight: 48,
    paddingHorizontal: space.sm,
    paddingVertical: space.sm,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  rowPressed: { backgroundColor: ink.ink3 },
  // In-window row: ice border + raised surface, tap-inert, no chevron.
  rowFeatured: { borderColor: ice.base, backgroundColor: ink.ink2 },
  rowMain: { flex: 1, minWidth: 0, gap: 2 },
  sides: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    minWidth: 0,
  },
  sideText: { flexShrink: 1 },
  posDot: { width: 6, height: 6, borderRadius: 3 },
  // #240 — meta line carries the counterparty (flexes + ellipsizes) with the
  // diff chip / IN WINDOW tag right-aligned after it.
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  metaLine: { color: chalk.dim, flex: 1 },
  diffChip: {
    paddingHorizontal: space.sm,
    paddingVertical: 2,
    borderRadius: radii.xs,
    borderWidth: 1,
  },
  diffChipPos: { borderColor: 'rgba(34,197,94,0.4)' },
  diffChipNeg: { borderColor: 'rgba(239,68,68,0.4)' },
  diffText: { fontSize: 12, lineHeight: 16 },
  inTag: {
    paddingHorizontal: space.xs,
    paddingVertical: 2,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink3,
  },
  inTagText: {
    ...type.label,
    fontSize: 10,
    color: ice.base,
  },
});

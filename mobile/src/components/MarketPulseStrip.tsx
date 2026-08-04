import React, { useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  flare,
  semantic,
  position as positionColors,
  space,
  radii,
  type,
  fonts,
  shadowSheet,
  scrim,
} from '../theme/chalkline';
import { Icon, Text } from './chalkline';
import { getMarketMovers, MarketMover } from '../api/market';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';

// Market pulse strip (#243 — approved mock
// mockups/polish-lab-2026-08/risers-fallers-cards.html, frame D1, with the
// operator's placement override: mounts BELOW the Explore section on League
// home, not at the top). One compact line — top riser + top faller (last
// name + signed %) + "See all movers ›" — opening a bottom sheet with the
// full risers/fallers columns (#242 sheet pattern: maxHeight 85%,
// size-to-content). Data is the honest "FTF community value" framing per
// the mock: GET /api/market/movers over player_value_history consensus
// snapshots, NOT observed market trades.
//
// Self-contained (own flag/format/query reads) so hosts mount it with one
// line. Renders null while flag `market.movers` is off, the query is in
// flight/errored, or history is too thin to name a single mover.

// "A. Jeanty" → "Jeanty"; suffix tokens never win the last-name slot.
const NAME_SUFFIXES = new Set(['jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v']);
function lastName(full: string): string {
  const parts = full.trim().split(/\s+/);
  while (parts.length > 1 && NAME_SUFFIXES.has(parts[parts.length - 1].toLowerCase())) {
    parts.pop();
  }
  return parts[parts.length - 1] || full;
}

// Signed whole-percent label with a true minus sign (mock: "+21%" / "−14%").
function signedPct(pct: number): string {
  return `${pct > 0 ? '+' : '−'}${Math.abs(Math.round(pct))}%`;
}

function posColor(position: string): string {
  return (
    (positionColors as Record<string, string>)[position?.toLowerCase?.() ?? ''] ||
    ink.lineStrong
  );
}

function MoverInline({ mover, up }: { mover: MarketMover; up?: boolean }) {
  const color = up ? semantic.pos : semantic.neg;
  return (
    <View style={styles.inlineItem}>
      <Icon name={up ? 'chevron-up' : 'chevron-down'} size={10} color={color} />
      <Text scale="dense" style={[styles.inlineText, { color }]} numberOfLines={1}>
        {lastName(mover.name)} {signedPct(mover.pct_30d)}
      </Text>
    </View>
  );
}

function MoverRow({ mover, up }: { mover: MarketMover; up?: boolean }) {
  return (
    <View style={styles.mvRow}>
      <View style={[styles.posDot, { backgroundColor: posColor(mover.position) }]} />
      <View style={styles.mvInfo}>
        <Text scale="dense" style={styles.mvName} numberOfLines={1}>
          {mover.name}
        </Text>
        <Text scale="dense" style={styles.mvMeta} numberOfLines={1}>
          {mover.position}
          {mover.team ? ` · ${mover.team}` : ''}
        </Text>
      </View>
      <Text
        scale="dense"
        style={[styles.mvDelta, { color: up ? semantic.pos : semantic.neg }]}
      >
        {signedPct(mover.pct_30d)}
      </Text>
    </View>
  );
}

export default function MarketPulseStrip() {
  const enabled = useFlag('market.movers');
  const activeFormat = useSession((s) => s.activeFormat);
  const [open, setOpen] = useState(false);

  const moversQuery = useQuery({
    queryKey: ['market-movers', activeFormat ?? '1qb_ppr'],
    queryFn: () => getMarketMovers(activeFormat ?? '1qb_ppr'),
    enabled,
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });

  const data = moversQuery.data;
  const topRiser = data?.risers?.[0];
  const topFaller = data?.fallers?.[0];
  // Null without the flag or without data — loading, error (incl. the
  // flag-off server 404), and thin-history empty payloads all end here.
  if (!enabled || (!topRiser && !topFaller)) return null;

  return (
    <>
      <Pressable
        testID="league.market-pulse"
        onPress={() => setOpen(true)}
        accessibilityRole="button"
        accessibilityLabel="Market pulse — top movers by FTF community value. See all movers"
        // ~36pt visual (fold budget: the strip shares League home's
        // low-activity viewport with the progress module — #243 keeps the
        // module's end above the 658pt fold); hitSlop restores the 44pt
        // effective touch target (same pattern as ux.touch_polish compacts).
        hitSlop={{ top: 4, bottom: 4 }}
        style={({ pressed }) => [styles.strip, pressed && { backgroundColor: ink.ink3 }]}
      >
        {topRiser ? <MoverInline mover={topRiser} up /> : null}
        {topRiser && topFaller ? (
          <Text scale="dense" style={styles.sep}>
            ·
          </Text>
        ) : null}
        {topFaller ? <MoverInline mover={topFaller} /> : null}
        <Text testID="league.market-pulse.see-all" scale="dense" style={styles.seeAll}>
          See all movers ›
        </Text>
      </Pressable>

      {/* Full movers sheet — #242 pattern: bottom sheet sizes to content up
          to maxHeight 85%; backdrop tap + onRequestClose dismiss. */}
      <Modal
        visible={open}
        transparent
        animationType="slide"
        onRequestClose={() => setOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setOpen(false)}
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        <View style={styles.sheet} testID="market-movers.sheet">
          <View style={styles.grabber} />
          <Text style={type.heading} accessibilityRole="header">
            Market movers
          </Text>
          {/* Honest data framing per the mock — this is FTF's own consensus
              value trend, not an observed trade market. */}
          <Text scale="dense" style={styles.srcLine}>
            FTF community value · {data?.window_days ?? 30}-day change
          </Text>
          <ScrollView style={styles.sheetScroll}>
            <View style={styles.cols}>
              <View style={styles.col}>
                <View style={styles.colHead}>
                  <Icon name="chevron-up" size={12} color={semantic.pos} />
                  <Text scale="dense" style={[styles.colHeadText, { color: semantic.pos }]}>
                    Risers
                  </Text>
                </View>
                {(data?.risers ?? []).map((m) => (
                  <MoverRow key={m.player_id} mover={m} up />
                ))}
                {(data?.risers ?? []).length === 0 ? (
                  <Text scale="dense" style={styles.emptyCol}>
                    No risers yet.
                  </Text>
                ) : null}
              </View>
              <View style={[styles.col, styles.colDown]}>
                <View style={styles.colHead}>
                  <Icon name="chevron-down" size={12} color={semantic.neg} />
                  <Text scale="dense" style={[styles.colHeadText, { color: semantic.neg }]}>
                    Fallers
                  </Text>
                </View>
                {(data?.fallers ?? []).map((m) => (
                  <MoverRow key={m.player_id} mover={m} />
                ))}
                {(data?.fallers ?? []).length === 0 ? (
                  <Text scale="dense" style={styles.emptyCol}>
                    No fallers yet.
                  </Text>
                ) : null}
              </View>
            </View>
          </ScrollView>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  // One-line strip (mock .pulsestrip): card tokens, row layout, ~36pt tall
  // (44pt effective target via the Pressable's hitSlop).
  strip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs + 2,
    paddingVertical: 9,
    paddingHorizontal: space.md,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    backgroundColor: ink.ink1,
  },
  inlineItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    flexShrink: 1,
  },
  inlineText: { ...type.bodySm, fontFamily: fonts.uiSemi },
  sep: { ...type.bodySm, color: chalk.faint },
  // Ice text link — the strip's single action cue.
  seeAll: {
    ...type.bodySm,
    color: ice.base,
    marginLeft: 'auto',
    fontFamily: fonts.uiSemi,
  },

  // Movers sheet (#242 pattern — mirrors the hub's team-picker sheet).
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '85%',
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    padding: space.lg,
    gap: space.sm,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.xs,
  },
  // Flare = informational highlight (ADR-005): the data-source label.
  srcLine: { ...type.label, color: flare.base },
  sheetScroll: { flexGrow: 0, flexShrink: 1, marginTop: space.xs },
  cols: { flexDirection: 'row', gap: space.md },
  col: { flex: 1, minWidth: 0 },
  colDown: {
    borderLeftWidth: 1,
    borderLeftColor: ink.line,
    paddingLeft: space.md,
  },
  colHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingBottom: space.xs + 2,
    marginBottom: 2,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  colHeadText: { ...type.label },
  mvRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm - 1,
    paddingVertical: space.sm - 1,
  },
  posDot: { width: 8, height: 8, borderRadius: radii.xs },
  mvInfo: { flex: 1, minWidth: 0 },
  mvName: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  mvMeta: { ...type.bodySm, fontSize: 11, lineHeight: 14, color: chalk.faint, fontFamily: fonts.data },
  mvDelta: { ...type.data, fontFamily: fonts.dataSemi },
  emptyCol: { ...type.bodySm, color: chalk.dim, paddingVertical: space.sm },
});

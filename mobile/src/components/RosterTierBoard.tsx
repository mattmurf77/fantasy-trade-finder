import React from 'react';
import { View, StyleSheet, Pressable, ScrollView, AccessibilityActionEvent } from 'react-native';

import {
  ink,
  chalk,
  ice,
  tier as tierColors,
  position as positionColors,
  space,
  radii,
  fonts,
  type,
} from '../theme/chalkline';
import { Text, TickLabel, Icon } from './chalkline';
import { TIERS, TIER_LABEL } from '../utils/tierBands';
import { marketTierShown, type TierBoard } from '../utils/rosterSetup';
import type { Position, Tier } from '../shared/types';

// Roster setup Step 2 as one-page tier placement (flag
// `trades.roster_tier_rank`; docs/plans/roster-first-trade-setup/
// scope-tier-rank.md §2.1). Prop-driven, no fetching: the screen owns the
// board, the pre-fill, the selection and the save.
//
// Eight tier sections in ladder order ("4+ 1sts" → FA). Empty tiers still
// render: they are targets for the footer's "Move to" chips. Each section is
// a 3-per-row grid in the Quick Set chip construction (ink-1, hairline,
// radius sm, ≥48pt, name Archivo semi 12 one line) with the POS token SHOWN
// — this page mixes positions (RankChipGrid's SHOW_POSITION rule) — plus
// the 3px position rail. Selected = ice border + check (two signals).
// Two optional micro-labels: "was <tier>" in the old tier's encode color
// once a chip has moved, and "mkt: <tier>" in the market tier's encode
// color when the consensus tier differs from where the chip sits now
// (operator decision 5). Picks are NOT on this page (operator decision 3).
// Off-board roster players are greyed, unselectable, "not on your board".

export interface RosterTierChip {
  id: string;
  name: string;
  position: Position;
  team?: string | null;
}

export interface RosterTierBoardProps {
  /** Tier → selectable (on-board) ids, in page order. */
  board: TierBoard;
  /** Every chip's display data, on-board and off-board. */
  players: Readonly<Record<string, RosterTierChip>>;
  /** Saved tier per on-board id (the save baseline: the pre-fill until a
   *  save lands) — the "was" marker's reference, so it marks unsaved moves. */
  prefillTier: Readonly<Record<string, Tier>>;
  /** Consensus tier per id (values query `tier`), for the market label. */
  marketTier: Readonly<Record<string, Tier | null | undefined>>;
  /** Tier → read-only off-board ids (rendered after the board's chips). */
  offBoard: Readonly<Partial<Record<Tier, string[]>>>;
  selected: readonly string[];
  onToggle: (id: string) => void;
  /** VoiceOver "Move to <tier>" on one chip. */
  onMove: (ids: string[], tier: Tier) => void;
  /** Room under the last tier for the host's pinned footer. */
  bottomInset: number;
  header?: React.ReactNode;
}

const COLUMNS = 3;

function rows<T>(items: T[]): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += COLUMNS) out.push(items.slice(i, i + COLUMNS));
  return out;
}

function posColor(p: string): string {
  return positionColors[p.toLowerCase() as keyof typeof positionColors] ?? ink.lineStrong;
}

export default function RosterTierBoard({
  board,
  players,
  prefillTier,
  marketTier,
  offBoard,
  selected,
  onToggle,
  onMove,
  bottomInset,
  header,
}: RosterTierBoardProps) {
  const sel = new Set(selected);

  const renderChip = (id: string, current: Tier, readOnly: boolean) => {
    const p = players[id];
    if (!p) return <View key={id} style={styles.cell} />;
    const was = !readOnly && prefillTier[id] && prefillTier[id] !== current ? prefillTier[id] : null;
    const mkt = marketTierShown(current, marketTier[id]);
    const isSel = !readOnly && sel.has(id);
    const a11yParts = [
      p.name,
      p.position,
      TIER_LABEL[current],
      was ? `moved from ${TIER_LABEL[was]}` : null,
      mkt ? `market ${TIER_LABEL[mkt]}` : null,
      readOnly ? 'not on your board' : null,
    ].filter(Boolean);
    const body = (
      <>
        <View style={[styles.rail, { backgroundColor: posColor(p.position) }]} />
        <View style={styles.chipTop}>
          <Text scale="dense" style={styles.chipName} numberOfLines={1}>{p.name}</Text>
          {isSel ? <View style={styles.check}><Icon name="check" size={12} color={ice.base} /></View> : null}
        </View>
        <View style={styles.chipMeta}>
          <Text scale="dense" style={[styles.meta, { color: posColor(p.position) }]}>{p.position}</Text>
          <Text scale="dense" style={[styles.meta, styles.team]} numberOfLines={1}>
            {readOnly ? 'not on your board' : p.team ?? 'FA'}
          </Text>
        </View>
        {was || mkt ? (
          <View style={styles.chipMeta}>
            {was ? (
              <Text scale="dense" style={[styles.meta, { color: tierColors[was] }]}>
                {`was ${TIER_LABEL[was]}`}
              </Text>
            ) : null}
            {mkt ? (
              <Text scale="dense" style={[styles.meta, { color: tierColors[mkt] }]}>
                {`mkt: ${TIER_LABEL[mkt]}`}
              </Text>
            ) : null}
          </View>
        ) : null}
      </>
    );
    if (readOnly) {
      return (
        <View
          key={id}
          testID={`roster-setup.tiers.chip.${id}`}
          accessible
          accessibilityLabel={a11yParts.join(', ')}
          accessibilityState={{ disabled: true }}
          style={[styles.cell, styles.chip, styles.chipOff]}
        >
          {body}
        </View>
      );
    }
    return (
      <Pressable
        key={id}
        testID={`roster-setup.tiers.chip.${id}`}
        accessibilityRole="button"
        accessibilityState={{ selected: isSel }}
        accessibilityLabel={a11yParts.join(', ')}
        accessibilityActions={TIERS.filter((t) => t !== current).map((t) => ({
          name: `tier:${t}`,
          label: `Move to ${TIER_LABEL[t]}`,
        }))}
        onAccessibilityAction={({ nativeEvent }: AccessibilityActionEvent) => {
          const t = nativeEvent.actionName.replace(/^tier:/, '') as Tier;
          if ((TIERS as readonly string[]).includes(t)) onMove([id], t);
        }}
        onPress={() => onToggle(id)}
        style={({ pressed }) => [
          styles.cell,
          styles.chip,
          isSel && styles.chipSelected,
          pressed && !isSel && { backgroundColor: ink.ink2 },
        ]}
      >
        {body}
      </Pressable>
    );
  };

  return (
    <ScrollView
      testID="roster-setup.tiers.board"
      contentContainerStyle={[styles.list, { paddingBottom: bottomInset + space.lg }]}
    >
      {header}
      {TIERS.map((t) => {
        const ids = board[t] ?? [];
        const off = offBoard[t] ?? [];
        const cells = [
          ...ids.map((id) => ({ id, readOnly: false })),
          ...off.map((id) => ({ id, readOnly: true })),
        ];
        return (
          <View key={t} style={styles.section}>
            <View testID={`roster-setup.tiers.header.${t}`} style={styles.sectionHdr}>
              <TickLabel color={tierColors[t]}>{TIER_LABEL[t]}</TickLabel>
              <Text scale="dense" style={styles.count}>{String(cells.length)}</Text>
            </View>
            {cells.length === 0 ? (
              <View style={styles.emptyWell}>
                <Text scale="dense" style={styles.emptyText}>No players</Text>
              </View>
            ) : (
              rows(cells).map((r, i) => (
                <View key={i} style={styles.gridRow}>
                  {r.map((c) => renderChip(c.id, t, c.readOnly))}
                  {Array.from({ length: COLUMNS - r.length }, (_, k) => (
                    <View key={`pad${k}`} style={styles.cell} />
                  ))}
                </View>
              ))
            )}
          </View>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  list: {
    paddingHorizontal: space.lg,
    paddingTop: space.sm,
    gap: space.md,
  },
  section: { gap: space.xs },
  sectionHdr: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginBottom: 2 },
  count: { ...type.label, fontFamily: fonts.data },
  gridRow: { flexDirection: 'row', gap: space.xs },
  cell: { flex: 1, minWidth: 0 },
  chip: {
    minHeight: 48,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingLeft: space.sm + 3,
    paddingRight: space.sm,
    paddingVertical: 6,
    justifyContent: 'center',
    overflow: 'hidden',
  },
  chipSelected: { borderColor: ice.base },
  chipOff: { opacity: 0.5 },
  // 3px position rail (dense-tile construction) — a data encoding.
  rail: { position: 'absolute', left: 0, top: 0, bottom: 0, width: 3 },
  chipTop: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  chipName: { fontFamily: fonts.uiSemi, fontSize: 12, color: chalk.base, flexShrink: 1 },
  check: { marginLeft: 'auto' },
  chipMeta: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', columnGap: 6, marginTop: 2 },
  meta: { fontFamily: fonts.uiSemi, fontSize: 11, letterSpacing: 0.5 },
  team: { color: chalk.dim, textTransform: 'uppercase', flexShrink: 1 },
  emptyWell: {
    minHeight: 36,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyText: { ...type.label, color: chalk.faint },
});

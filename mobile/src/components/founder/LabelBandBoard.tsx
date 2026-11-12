import React from 'react';
import { AccessibilityActionEvent, Pressable, StyleSheet, View } from 'react-native';

import { chalk, fonts, ice, ink, position as positionColors, radii, space, type } from '../../theme/chalkline';
import { Icon, Text, TickLabel } from '../chalkline';
import {
  BANDS,
  BAND_LABEL,
  bandCounts,
  bandOf,
  engineNote,
  unlabelledWhy,
  type Draft,
  type FounderLabel,
  type FounderRow,
} from '../../utils/founderReview';

// Founders' review — one position's players laid out as label bands
// (docs/plans/founder-review/design.md §7). Prop-driven, no fetching: the
// host (FounderLabelReview) owns the rows, the draft, the selection and Save.
//
// The interaction and the chip construction are RosterTierBoard's (D-233,
// "tap him, then tap the tier"): a 3-per-row grid of chips (ink-1, hairline,
// radius sm, ≥48pt, 3px position rail), selected = ice border + check (two
// signals), each band a TickLabel header with its count, empty bands still
// rendered. RosterTierBoard itself is typed on the eight-tier ladder and its
// tier colour encodings, so it is not widened for this: label bands carry no
// colour encoding (neutral ticks). A "No label" chip is read-only.

const COLUMNS = 3;

export interface LabelBandBoardProps {
  rows: readonly FounderRow[];
  draft: Draft;
  selected: readonly string[];
  onToggle: (id: string) => void;
  /** VoiceOver "Move to <band>" on one chip. */
  onMove: (ids: string[], label: FounderLabel) => void;
}

function chunk<T>(items: T[]): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += COLUMNS) out.push(items.slice(i, i + COLUMNS));
  return out;
}

function posColor(p: string): string {
  return positionColors[p.toLowerCase() as keyof typeof positionColors] ?? ink.lineStrong;
}

const num = (v: number | null, digits = 1) => (v == null ? '—' : v.toFixed(digits));

export default function LabelBandBoard({ rows, draft, selected, onToggle, onMove }: LabelBandBoardProps) {
  const sel = new Set(selected);
  const counts = bandCounts(rows, draft);

  const renderChip = (row: FounderRow) => {
    const band = bandOf(row, draft);
    const note = engineNote(row, draft);
    const readOnly = row.movable_to.length === 0;
    const isSel = !readOnly && sel.has(row.id);
    const facts = `${row.team ?? 'FA'} · ${row.age ?? '—'} · ${num(row.ppg)} pts · ${num(row.value, 0)}`;
    const a11y = [row.name, row.position, BAND_LABEL[band], facts, note,
      readOnly ? unlabelledWhy(row) : null].filter(Boolean).join(', ');
    const body = (
      <>
        <View style={[styles.rail, { backgroundColor: posColor(row.position) }]} />
        <View style={styles.chipTop}>
          <Text scale="dense" style={styles.chipName} numberOfLines={1}>{row.name}</Text>
          {isSel ? <View style={styles.check}><Icon name="check" size={12} color={ice.base} /></View> : null}
        </View>
        <Text scale="dense" style={styles.meta} numberOfLines={1}>{facts}</Text>
        {readOnly ? (
          <Text scale="dense" style={styles.meta} numberOfLines={1}>{unlabelledWhy(row)}</Text>
        ) : note ? (
          <Text scale="dense" style={styles.note} numberOfLines={1} testID={`founder-review.engine-note.${row.id}`}>
            {note}
          </Text>
        ) : null}
      </>
    );
    if (readOnly) {
      return (
        <View
          key={row.id}
          testID={`founder-review.chip.${row.id}`}
          accessible
          accessibilityLabel={a11y}
          accessibilityState={{ disabled: true }}
          style={[styles.cell, styles.chip, styles.chipOff]}
        >
          {body}
        </View>
      );
    }
    return (
      <Pressable
        key={row.id}
        testID={`founder-review.chip.${row.id}`}
        accessibilityRole="button"
        accessibilityState={{ selected: isSel }}
        accessibilityLabel={a11y}
        accessibilityActions={row.movable_to.filter((l) => l !== band).map((l) => ({
          name: `band:${l}`,
          label: `Move to ${BAND_LABEL[l]}`,
        }))}
        onAccessibilityAction={({ nativeEvent }: AccessibilityActionEvent) => {
          const l = nativeEvent.actionName.replace(/^band:/, '') as FounderLabel;
          if (row.movable_to.includes(l)) onMove([row.id], l);
        }}
        onPress={() => onToggle(row.id)}
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
    <View style={styles.list}>
      {BANDS.map((b) => {
        const members = rows.filter((r) => bandOf(r, draft) === b);
        return (
          <View key={b} style={styles.section}>
            <View testID={`founder-review.band.${b}`} style={styles.sectionHdr}>
              <TickLabel color={chalk.faint}>{BAND_LABEL[b]}</TickLabel>
              <Text scale="dense" style={styles.count} testID={`founder-review.count.${b}`}>{String(counts[b])}</Text>
            </View>
            {members.length === 0 ? (
              <View style={styles.emptyWell}>
                <Text scale="dense" style={styles.emptyText}>No players</Text>
              </View>
            ) : (
              chunk(members).map((r, i) => (
                <View key={i} style={styles.gridRow}>
                  {r.map(renderChip)}
                  {Array.from({ length: COLUMNS - r.length }, (_, k) => (
                    <View key={`pad${k}`} style={styles.cell} />
                  ))}
                </View>
              ))
            )}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: space.md },
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
  meta: { fontFamily: fonts.uiSemi, fontSize: 11, color: chalk.dim, marginTop: 2 },
  note: { fontFamily: fonts.uiSemi, fontSize: 11, color: chalk.base, marginTop: 2 },
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

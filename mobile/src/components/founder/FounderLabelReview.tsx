import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { chalk, ice, ink, radii, space, type } from '../../theme/chalkline';
import { Button, Text } from '../chalkline';
import Toast from '../Toast';
import { setPinnedBottomBarHeight } from '../FeedbackFAB';
import { getFounderLabels, saveFounderLabels } from '../../api/founder';
import {
  BAND_LABEL,
  applyMove,
  changedIds,
  emptyReason,
  otherScopeLine,
  resetToEngine,
  savePayload,
  scopeHeading,
  targetsFor,
  type Draft,
  type FounderLabel,
  type ReviewPosition,
} from '../../utils/founderReview';
import LabelBandBoard from './LabelBandBoard';

// Founders' review — the player label review for the selected league
// (docs/plans/founder-review/design.md §7). Self-contained: it owns its query,
// the local draft, the selection and Save. Mounted by CalibrationScreen ONLY
// after GET /api/founder/capability answered 200; every route behind it is
// server-gated (404 for anyone else), so this file reads no flag.
//
// Interaction = the tier board's (D-233): tap players, then a "Move to" chip
// in the pinned footer. A chip is enabled only when it is legal for every
// selected player (utils/founderReview.targetsFor). Save sends changed players
// only; Reset to engine resets the visible position locally (Save commits).
// The pinned footer reports its height through setPinnedBottomBarHeight
// (no second FeedbackFAB: a tab-stack screen, RootNav's mount covers it).

const COPY = {
  title: 'Founders’ review',
  intro: 'Review the engine’s player labels for this league. Tap players, then a label.',
  moveTo: 'Move to',
  save: 'Save',
  reset: (pos: string) => `Reset ${pos} to engine`,
  changed: (n: number) => `${n} changed`,
  saved: 'Saved',
  saveFailed: 'Couldn’t save. Try again.',
  readFailed: 'Couldn’t load the labels.',
  tryAgain: 'Try again',
  line: (pos: string, v: number | null | undefined) =>
    v == null ? `${pos} starter line: none` : `${pos} starter line: ${v.toFixed(1)} pts/game`,
  globalNote: 'RB, WR and TE labels apply in every league. Moving a player back to the engine’s label clears your call.',
  summaryTitle: 'Your corrections here',
  noCorrections: 'None yet',
} as const;

const POS_TABS = [
  { pos: 'QB', testID: 'founder-review.pos.QB' },
  { pos: 'RB', testID: 'founder-review.pos.RB' },
  { pos: 'WR', testID: 'founder-review.pos.WR' },
  { pos: 'TE', testID: 'founder-review.pos.TE' },
] as const;

// One chip per label of the server's vocabulary, in band order
// (tests/check-founder-review.js pins this list equal to utils LABELS).
const MOVE_CHIPS = [
  { label: 'cornerstone', testID: 'founder-review.move.cornerstone' },
  { label: 'win_now', testID: 'founder-review.move.win_now' },
  { label: 'rebuild', testID: 'founder-review.move.rebuild' },
  { label: 'depth', testID: 'founder-review.move.depth' },
] as const;

export default function FounderLabelReview({ leagueId }: { leagueId: string }) {
  const qc = useQueryClient();
  const isFocused = useIsFocused();
  const key = ['founder', 'labels', leagueId] as const;
  const pageQ = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => getFounderLabels(leagueId, { signal }),
    retry: false,
    staleTime: 0,
  });
  const [position, setPosition] = useState<ReviewPosition>('QB');
  const [draft, setDraft] = useState<Draft>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [toast, setToast] = useState<{ text: string; tone: 'success' | 'error' } | null>(null);
  const [footerH, setFooterH] = useState(0);

  // A new league is a new review: drop the draft and the selection.
  useEffect(() => { setDraft({}); setSelected([]); }, [leagueId]);
  useEffect(() => { setSelected([]); }, [position]);

  const rows = pageQ.data?.players ?? [];
  const posRows = rows.filter((r) => r.position === position);
  const changed = changedIds(rows, draft);
  const targets = targetsFor(posRows, selected);
  const hasRows = rows.length > 0;

  useEffect(() => {
    setPinnedBottomBarHeight('founder_review', isFocused && hasRows ? footerH : 0);
  }, [isFocused, hasRows, footerH]);
  useEffect(() => () => setPinnedBottomBarHeight('founder_review', 0), []);

  const saveM = useMutation({
    mutationFn: () => saveFounderLabels(savePayload(leagueId, rows, draft)),
    onSuccess: async () => {
      setDraft({});
      setSelected([]);
      setToast({ text: COPY.saved, tone: 'success' });
      await qc.invalidateQueries({ queryKey: key });
    },
    onError: () => setToast({ text: COPY.saveFailed, tone: 'error' }),
  });

  const toggle = (id: string) =>
    setSelected((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));
  const moveTo = (ids: string[], label: FounderLabel) => {
    setDraft((d) => applyMove(d, rows, ids, label));
    setSelected([]);
  };
  const reset = () => { setDraft((d) => resetToEngine(d, rows, position)); setSelected([]); };

  if (pageQ.isPending) {
    return (
      <View style={styles.center} testID="founder-review.loading">
        <ActivityIndicator color={ice.base} />
      </View>
    );
  }
  if (pageQ.isError) {
    return (
      <View style={styles.block} testID="founder-review.error">
        <Text variant="body">{COPY.readFailed}</Text>
        <Button testID="founder-review.retry" label={COPY.tryAgain} variant="secondary"
          onPress={() => { void pageQ.refetch(); }} />
      </View>
    );
  }
  if (!hasRows) {
    return (
      <View style={styles.block} testID="founder-review.empty">
        <Text variant="heading">{COPY.title}</Text>
        <Text variant="body">{emptyReason(pageQ.data?.evidence?.reason)}</Text>
      </View>
    );
  }

  const summary = pageQ.data!.summary.positions[position];
  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: footerH + space.lg }]}>
        <Text variant="heading">{COPY.title}</Text>
        <Text variant="bodySm">{COPY.intro}</Text>
        <View style={styles.segmentRow}>
          {POS_TABS.map((t) => (
            <Pressable
              key={t.testID}
              testID={t.testID}
              accessibilityRole="button"
              accessibilityState={{ selected: position === t.pos }}
              onPress={() => setPosition(t.pos)}
              style={[styles.segmentBtn, position === t.pos && styles.segmentBtnActive]}
            >
              <Text variant="label" style={position === t.pos ? styles.segmentTextActive : null}>{t.pos}</Text>
            </Pressable>
          ))}
        </View>
        {position === 'QB' ? (
          <View style={styles.scope} testID="founder-review.qb-scope">
            <Text variant="title">{scopeHeading(pageQ.data!.qb_scope)}</Text>
            <Text variant="bodySm">{otherScopeLine(pageQ.data!.qb_scope)}</Text>
          </View>
        ) : (
          <Text variant="bodySm" testID="founder-review.global-note">{COPY.globalNote}</Text>
        )}
        <Text variant="data" testID="founder-review.line">{COPY.line(position, pageQ.data!.line[position])}</Text>
        <LabelBandBoard rows={posRows} draft={draft} selected={selected} onToggle={toggle} onMove={moveTo} />
        <View style={styles.summary} testID="founder-review.summary">
          <Text variant="label">{COPY.summaryTitle}</Text>
          <Text variant="bodySm">{`${position}: ${summary.moved} moved`}</Text>
          {summary.corrections.length === 0 ? (
            <Text variant="bodySm" style={styles.dim}>{COPY.noCorrections}</Text>
          ) : summary.corrections.map((c) => (
            <Text key={`${c.from}-${c.to}`} variant="bodySm">
              {`${BAND_LABEL[c.from]} → ${BAND_LABEL[c.to]}: ${c.count}`}
            </Text>
          ))}
        </View>
      </ScrollView>
      <View style={styles.footer} onLayout={(e) => setFooterH(e.nativeEvent.layout.height)}>
        <View style={styles.moveRow}>
          <Text scale="dense" style={styles.moveLabel}>{COPY.moveTo}</Text>
          {MOVE_CHIPS.map((c) => {
            const enabled = targets.includes(c.label);
            return (
              <Pressable
                key={c.testID}
                testID={c.testID}
                disabled={!enabled}
                accessibilityRole="button"
                accessibilityState={{ disabled: !enabled }}
                accessibilityLabel={`Move selected players to ${BAND_LABEL[c.label]}`}
                onPress={() => moveTo(selected, c.label)}
                hitSlop={4}
                style={({ pressed }) => [styles.chip, !enabled && styles.chipOff, pressed && { backgroundColor: ink.ink3 }]}
              >
                <Text scale="dense" style={[styles.chipText, enabled && styles.chipTextOn]}>{BAND_LABEL[c.label]}</Text>
              </Pressable>
            );
          })}
        </View>
        <View style={styles.actionRow}>
          <Text variant="data" testID="founder-review.changed">{COPY.changed(changed.length)}</Text>
          <View style={styles.actions}>
            <Button testID="founder-review.reset" label={COPY.reset(position)} variant="ghost" onPress={reset} />
            <Button
              testID="founder-review.save"
              label={COPY.save}
              variant="primary"
              disabled={changed.length === 0 || saveM.isPending}
              loading={saveM.isPending}
              onPress={() => saveM.mutate()}
            />
          </View>
        </View>
      </View>
      <Toast visible={!!toast} message={toast?.text ?? ''} tone={toast?.tone ?? 'success'} onDismiss={() => setToast(null)} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  content: { padding: space.lg, gap: space.md },
  block: { gap: space.lg, padding: space.lg },
  center: { alignItems: 'center', justifyContent: 'center', paddingVertical: space.xxxl },
  segmentRow: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  segmentBtn: {
    flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center',
    borderBottomWidth: 2, borderBottomColor: 'transparent',
  },
  segmentBtnActive: { backgroundColor: ink.ink3, borderBottomColor: ice.base },
  segmentTextActive: { color: chalk.base },
  scope: { gap: space.xs },
  summary: {
    gap: space.xs, padding: space.md, borderWidth: 1, borderColor: ink.line,
    borderRadius: radii.sm, backgroundColor: ink.ink1,
  },
  dim: { color: chalk.dim },
  footer: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: ink.ink1, borderTopWidth: 1, borderTopColor: ink.line,
    paddingHorizontal: space.lg, paddingVertical: space.sm, gap: space.sm,
  },
  moveRow: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space.sm },
  moveLabel: { ...type.label },
  chip: {
    minHeight: 36, paddingHorizontal: space.md, justifyContent: 'center',
    borderRadius: radii.xs, borderWidth: 1, borderColor: ice.base,
  },
  chipOff: { borderColor: ink.lineStrong },
  chipText: { ...type.label, color: chalk.faint },
  chipTextOn: { color: ice.base },
  actionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: space.sm },
  actions: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
});

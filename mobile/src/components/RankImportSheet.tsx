import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { Button, Icon } from './chalkline';
import {
  importApplyRankings,
  importMatchRankings,
  type ImportMatchRow,
  type ImportRowHint,
} from '../api/rankings';
import {
  chalk,
  fonts,
  ice,
  ink,
  radii,
  scrim,
  semantic,
  shadowSheet,
  space,
  type,
} from '../theme/chalkline';
import { haptics } from '../utils/haptics';

// #232 follow-on — "Bring your rankings" import flow (flag `ranks.import`;
// approved mocks rank-method-consolidation-v2 B1–B3 + v3). PASTE-FIRST v1
// scope: one method (paste a table); CSV/XLSX upload are deferred follow-ons
// (v2 rationale — paste covers the CSV case via open-file → copy → paste).
//
// Two steps inside one bottom sheet (no nav route — the flow is strictly
// chooser-scoped and modal, per the mock's sheet framing):
//   paste  — textarea + tolerant row count + honesty line + "Match N players"
//   review — per-row match results from POST /api/rankings/import-match:
//            auto-matched rows show a check (audit-visible), ambiguous rows
//            show "Which one?" candidate chips + Skip, unmatched rows are
//            skipped. Footer "Apply N ranks — M to resolve" stays disabled
//            until every ambiguous row is resolved or skipped, then posts
//            the resolved order to /api/rankings/import-apply.
//
// Modal/sheet ⇒ no FeedbackFAB mount (root CLAUDE.md exception).

interface Props {
  visible: boolean;
  onClose: () => void;
  /** Called after a successful apply; parent owns toast + navigation. */
  onApplied: (importedCount: number) => void;
  // ── Preset intake (Premium Rankings Import v1, [D-058]) ───────────────
  // Both props are OPTIONAL and both default to today's exact behavior, so
  // the "Paste rankings" row still opens this sheet unchanged.
  /** Ordered rows from a confirmed premium preset. When present the sheet
   *  skips the paste step entirely and runs the SAME match → review → apply
   *  path, so there is exactly one apply implementation. Order-only by
   *  contract: `ImportRowHint` has no value/trend/points field. */
  presetRows?: ImportRowHint[] | null;
  /** Raw text for the generic fallback path — an unrecognized file's rows
   *  land in the paste box for the user to check, rather than being guessed
   *  at (addendum §3.2: unknown signature → generic mapping, never a guess). */
  initialText?: string | null;
}

// Display-only row estimate for the paste step ("N rows detected"). The
// BACKEND parser is authoritative — this mirrors just enough of its rules
// (skip blanks, numbers-only lines, and obvious header rows) for an honest
// live count; the review step then shows exactly the server-parsed rows.
const HEADER_WORDS = new Set([
  'rank', 'rk', 'no', 'num', 'overall', 'ovr', 'row',
  'player', 'players', 'name', 'names',
  'pos', 'position', 'team', 'tm', 'club',
  'age', 'value', 'values', 'tier', 'adp', 'bye', 'pts', 'points',
]);

export function countRankRows(text: string): number {
  return rankRowLines(text).length;
}

function rankRowLines(text: string): string[] {
  return text.split('\n').filter((line) => {
    if (!/[A-Za-z]/.test(line)) return false; // blank / numbers-only
    const words = line
      .toLowerCase()
      .split(/[^a-z]+/)
      .filter(Boolean);
    if (words.length === 0) return false;
    return !words.every((w) => HEADER_WORDS.has(w)); // header row
  });
}

type Resolution = string | 'skip'; // player_id or explicit skip

export default function RankImportSheet({
  visible,
  onClose,
  onApplied,
  presetRows,
  initialText,
}: Props) {
  const [step, setStep] = useState<'paste' | 'review'>('paste');
  const [text, setText] = useState('');
  const [matching, setMatching] = useState(false);
  const [applying, setApplying] = useState(false);
  const [rows, setRows] = useState<ImportMatchRow[]>([]);
  const [resolutions, setResolutions] = useState<Record<number, Resolution>>({});
  const [error, setError] = useState<string | null>(null);

  const rowCount = useMemo(() => countRankRows(text), [text]);

  const reset = useCallback(() => {
    setStep('paste');
    setText('');
    setRows([]);
    setResolutions({});
    setError(null);
    setMatching(false);
    setApplying(false);
  }, []);

  const close = useCallback(() => {
    reset();
    onClose();
  }, [reset, onClose]);

  // ONE match implementation for every intake. `hints` is the preset path's
  // ordered [{name, team, pos}] — api/rankings.ts sends it as the optional
  // `rows` field and falls back to the plain text path on a 400 from a
  // backend that predates it.
  const runMatch = useCallback(
    async (lines: string[], hints?: ImportRowHint[] | null) => {
      setMatching(true);
      setError(null);
      try {
        const res = await importMatchRankings(lines, hints ?? null);
        setRows(res.rows);
        setResolutions({});
        setStep('review');
      } catch (e: any) {
        setError(e?.message || 'Could not match your rankings. Try again.');
      } finally {
        setMatching(false);
      }
    },
    [],
  );

  const onMatch = useCallback(
    () => runMatch(rankRowLines(text)),
    [runMatch, text],
  );

  // Preset intake: a confirmed premium CSV opens this sheet straight into
  // the review step. Guarded by a ref so a re-render can't re-POST the same
  // batch; cleared when the sheet closes.
  const adopted = useRef(false);
  useEffect(() => {
    if (!visible) {
      adopted.current = false;
      return;
    }
    if (adopted.current) return;
    if (presetRows && presetRows.length) {
      adopted.current = true;
      void runMatch(presetRows.map((r) => r.name), presetRows);
    } else if (initialText) {
      adopted.current = true;
      setText(initialText);
    }
  }, [visible, presetRows, initialText, runMatch]);

  // Ordered resolved player ids, and how many ambiguous rows still need a
  // tap. Unmatched rows are skipped (there is nothing to resolve them to);
  // the hint line says so honestly.
  const { orderedIds, unresolved } = useMemo(() => {
    const ids: string[] = [];
    let pending = 0;
    rows.forEach((row, i) => {
      if (row.status === 'matched' && row.player) {
        ids.push(row.player.id);
      } else if (row.status === 'ambiguous') {
        const r = resolutions[i];
        if (r == null) pending += 1;
        else if (r !== 'skip') ids.push(r);
      }
      // unmatched → skipped
    });
    return { orderedIds: ids, unresolved: pending };
  }, [rows, resolutions]);

  const onApply = useCallback(async () => {
    if (unresolved > 0 || orderedIds.length === 0) return;
    setApplying(true);
    setError(null);
    try {
      const res = await importApplyRankings(orderedIds);
      haptics.success();
      const n = res.imported_count;
      reset();
      onApplied(n);
    } catch (e: any) {
      setError(e?.message || 'Could not apply your rankings. Try again.');
      setApplying(false);
    }
  }, [unresolved, orderedIds, reset, onApplied]);

  const matchedCount = useMemo(
    () =>
      rows.filter(
        (r, i) =>
          (r.status === 'matched') ||
          (r.status === 'ambiguous' &&
            resolutions[i] != null &&
            resolutions[i] !== 'skip'),
      ).length,
    [rows, resolutions],
  );

  const renderRow = useCallback(
    ({ item, index }: { item: ImportMatchRow; index: number }) => {
      const n = index + 1;
      const resolution = resolutions[index];
      let right: React.ReactNode = null;
      let candidates: React.ReactNode = null;

      if (item.status === 'matched' && item.player) {
        right = (
          <View style={styles.hit}>
            <Text style={styles.hitName} numberOfLines={1}>
              {item.player.name}
            </Text>
            {item.player.team ? (
              <Text style={styles.hitTeam}>{item.player.team}</Text>
            ) : null}
            <Icon name="check" size={14} color={semantic.pos} />
          </View>
        );
      } else if (item.status === 'ambiguous') {
        if (resolution == null) {
          right = <Text style={styles.whichOne}>Which one?</Text>;
          candidates = (
            <View style={styles.candWrap}>
              {item.candidates.map((c) => (
                <Pressable
                  key={c.id}
                  accessibilityRole="button"
                  accessibilityLabel={`${c.name}${c.team ? `, ${c.team}` : ''}${c.position ? `, ${c.position}` : ''}`}
                  onPress={() => {
                    haptics.selection();
                    setResolutions((prev) => ({ ...prev, [index]: c.id }));
                  }}
                  style={({ pressed }) => [
                    styles.cand,
                    pressed && { backgroundColor: ink.ink3 },
                  ]}
                >
                  <Text style={styles.candName} numberOfLines={1}>
                    {c.name}
                  </Text>
                  {c.team || c.position ? (
                    <Text style={styles.candMeta}>
                      {[c.team, c.position].filter(Boolean).join(' · ')}
                    </Text>
                  ) : null}
                </Pressable>
              ))}
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Skip this row"
                onPress={() => {
                  haptics.selection();
                  setResolutions((prev) => ({ ...prev, [index]: 'skip' }));
                }}
                style={({ pressed }) => [
                  styles.cand,
                  pressed && { backgroundColor: ink.ink3 },
                ]}
              >
                <Text style={styles.candSkip}>Skip this row</Text>
              </Pressable>
            </View>
          );
        } else if (resolution === 'skip') {
          right = <Text style={styles.skipped}>Skipped</Text>;
        } else {
          const chosen = item.candidates.find((c) => c.id === resolution);
          right = (
            <View style={styles.hit}>
              <Text style={styles.hitName} numberOfLines={1}>
                {chosen?.name ?? 'Selected'}
              </Text>
              <Icon name="check" size={14} color={semantic.pos} />
            </View>
          );
        }
      } else {
        right = <Text style={styles.skipped}>No match — skipped</Text>;
      }

      return (
        <View testID={`rank-import.row.${n}`} style={styles.row}>
          <View style={styles.rowMain}>
            <Text style={styles.rowRank}>{n}</Text>
            <Text style={styles.rowInput} numberOfLines={1}>
              {item.name}
            </Text>
            {right}
          </View>
          {candidates}
        </View>
      );
    },
    [resolutions],
  );

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={close}>
      <Pressable
        style={styles.backdrop}
        onPress={close}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.kav}
        pointerEvents="box-none"
      >
        <View style={styles.sheet}>
          <View style={styles.handle} />

          {step === 'paste' ? (
            <>
              <Text style={type.heading} accessibilityRole="header">
                Bring your rankings
              </Text>
              <Text style={styles.sub}>
                Pull in a board you keep somewhere else. Ranks only — a
                numbered list of players is all we need. Paste rows straight
                from a spreadsheet or site; row order works too.
              </Text>
              <TextInput
                testID="rank-import.paste"
                style={styles.pasteBox}
                multiline
                value={text}
                onChangeText={setText}
                placeholder={'1  Ja’Marr Chase  WR\n2  Justin Jefferson  WR\n3  Bijan Robinson  RB\n…'}
                placeholderTextColor={chalk.faint}
                autoCorrect={false}
                autoCapitalize="none"
                accessibilityLabel="Paste your rankings table"
              />
              {rowCount > 0 ? (
                <View style={styles.countRow}>
                  <Icon name="check" size={14} color={semantic.pos} />
                  <Text style={styles.countText}>
                    {rowCount} row{rowCount === 1 ? '' : 's'} detected
                  </Text>
                </View>
              ) : null}
              <View style={styles.honesty}>
                <Text style={styles.honestyText}>
                  We&apos;ll match player names to your league&apos;s player
                  pool — you review anything we can&apos;t match.
                </Text>
              </View>
              {error ? <Text style={styles.error}>{error}</Text> : null}
              <Button
                testID="rank-import.match"
                label={
                  rowCount > 0
                    ? `Match ${rowCount} player${rowCount === 1 ? '' : 's'}`
                    : 'Match players'
                }
                onPress={onMatch}
                disabled={rowCount === 0 || matching}
                loading={matching}
              />
              <Button label="Cancel" variant="ghost" onPress={close} />
            </>
          ) : (
            <>
              <Text style={type.heading} accessibilityRole="header">
                Review your import
              </Text>
              <View style={styles.countRow}>
                <Icon name="check" size={14} color={semantic.pos} />
                <Text style={styles.countText}>
                  {matchedCount} of {rows.length} matched
                </Text>
                {unresolved > 0 ? (
                  <Text style={styles.needsYou}>· {unresolved} need you</Text>
                ) : null}
              </View>
              <FlatList
                data={rows}
                keyExtractor={(_r, i) => String(i)}
                renderItem={renderRow}
                style={styles.list}
                keyboardShouldPersistTaps="handled"
              />
              <Text style={styles.hint}>
                Close matches (suffixes, punctuation) are accepted
                automatically and shown here so you can catch a wrong one.
                Skipped and unlisted players fall in below your imported
                ranks, in their current order.
              </Text>
              {error ? <Text style={styles.error}>{error}</Text> : null}
              <View style={styles.footerRow}>
                <Button label="Cancel" variant="ghost" compact onPress={close} />
                <Pressable
                  testID="rank-import.apply"
                  accessibilityRole="button"
                  accessibilityLabel={
                    unresolved > 0
                      ? `Apply ${orderedIds.length} ranks, ${unresolved} to resolve first`
                      : `Apply ${orderedIds.length} ranks`
                  }
                  accessibilityState={{
                    disabled: unresolved > 0 || orderedIds.length === 0 || applying,
                  }}
                  disabled={unresolved > 0 || orderedIds.length === 0 || applying}
                  onPress={onApply}
                  style={[
                    styles.applyBtn,
                    (unresolved > 0 || orderedIds.length === 0 || applying) &&
                      styles.applyBtnDisabled,
                  ]}
                >
                  {applying ? (
                    <ActivityIndicator color={ice.on} />
                  ) : (
                    <Text style={styles.applyText}>
                      {unresolved > 0
                        ? `Apply ${orderedIds.length} ranks — ${unresolved} to resolve`
                        : `Apply ${orderedIds.length} rank${orderedIds.length === 1 ? '' : 's'}`}
                    </Text>
                  )}
                </Pressable>
              </View>
            </>
          )}
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  kav: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    maxHeight: '88%',
    ...shadowSheet,
  },
  handle: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  sub: { ...type.bodySm },

  // Paste box — Input construction (ink-2 fill would vanish on the ink-2
  // sheet, so the box steps down to ink-1 like the mock's pastebox) with
  // line-strong border; mono content because pasted tables are data.
  pasteBox: {
    minHeight: 170,
    maxHeight: 260,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    padding: space.md,
    color: chalk.base,
    fontFamily: fonts.data,
    fontSize: 12,
    lineHeight: 19,
    textAlignVertical: 'top',
  },
  countRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  countText: {
    fontFamily: fonts.data,
    fontSize: 13,
    color: chalk.dim,
  },
  needsYou: {
    fontFamily: fonts.data,
    fontSize: 13,
    color: semantic.warn,
  },
  honesty: {
    backgroundColor: ink.ink3,
    borderRadius: radii.sm,
    padding: space.md,
  },
  honestyText: { ...type.bodySm },
  error: { ...type.bodySm, color: semantic.neg },

  // Review list
  list: { flexGrow: 0 },
  row: {
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    paddingVertical: space.sm,
    gap: space.sm,
  },
  rowMain: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  rowRank: {
    fontFamily: fonts.data,
    fontSize: 12,
    color: chalk.dim,
    width: 24,
    textAlign: 'right',
  },
  rowInput: { ...type.bodySm, flex: 1 },
  hit: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    maxWidth: '55%',
  },
  hitName: {
    fontFamily: fonts.uiSemi,
    fontSize: 13,
    color: chalk.base,
    flexShrink: 1,
  },
  hitTeam: { ...type.label, color: chalk.dim },
  whichOne: { ...type.label, color: semantic.warn },
  skipped: { ...type.bodySm, color: chalk.dim },
  candWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.sm - 2,
    paddingLeft: 24 + space.sm,
  },
  cand: {
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    backgroundColor: ink.ink1,
    minHeight: 32,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: space.sm + 2,
  },
  candName: { fontFamily: fonts.uiSemi, fontSize: 12, color: chalk.base },
  candMeta: { ...type.label, color: chalk.dim },
  candSkip: { fontFamily: fonts.uiSemi, fontSize: 12, color: chalk.dim },
  hint: { ...type.bodySm, color: chalk.dim },

  footerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    marginTop: space.xs,
  },
  applyBtn: {
    flex: 1,
    backgroundColor: ice.base,
    borderRadius: radii.sm,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.lg,
  },
  applyBtnDisabled: { opacity: 0.45 },
  applyText: { fontFamily: fonts.uiSemi, fontSize: 14, color: ice.on },
});

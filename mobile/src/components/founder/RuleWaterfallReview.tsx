import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, TextInput, View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { chalk, flare, ice, ink, radii, space, type } from '../../theme/chalkline';
import { Button, Meter, Text } from '../chalkline';
import Toast from '../Toast';
import { ApiError } from '../../api/client';
import {
  getRuleNoteHistory,
  getRuleWaterfall,
  saveRuleNote,
  startRuleWaterfall,
  type RuleNote,
  type RuleWaterfallPage,
} from '../../api/founder';
import { relativeTime } from '../../utils/relativeTime';
import {
  NOTE_MAX,
  addedLine,
  buildTable,
  dirtyKeys,
  earlierVersions,
  formatCount,
  formatShare,
  headerLine,
  isZero,
  noteByline,
  noteCounter,
  notesByKey,
  pollInterval,
  rowA11yLabel,
  startErrorText,
  statusMessage,
  statusWords,
  type TableRow,
} from '../../utils/ruleWaterfall';

// Founders' review, use case 2 — "Trade rules": every yes/no rule as a
// decline waterfall, with a note per rule
// (docs/plans/founder-review/rule-waterfall-design.md §6). Self-contained: it
// owns the page query (polled every 2 s only while a run is in progress), the
// Run button, the note drafts, Save per row and the history view. Mounted by
// FounderReview only after GET /api/founder/rule-waterfall answered (an older
// server's 404 hides the choice), so this file reads no flag.
//
// Note drafts live HERE (one map keyed by rule), never in a row, so text
// survives scrolling and expanding other rows. Leaving the page with unsaved
// notes asks first: in-screen section switches call confirmLeaveNotes, and a
// navigator removal is caught by beforeRemove. A tab switch keeps this screen
// mounted, so its drafts stay.
// No FeedbackFAB: a tab-stack screen, RootNav's mount covers it.

const COPY = {
  title: 'Trade rules',
  intro: 'Every yes/no rule a suggested trade must pass, in the order the engine applies them.',
  run: 'Run for this league',
  running: 'Running…',
  runningNote: 'Measuring every candidate trade. This takes up to a minute.',
  noRun: 'No run yet for this league. Every rule is listed below, and you can write notes now.',
  hideZero: (n: number) => `Hide rules that removed nothing (${n})`,
  removed: 'Removed',
  remaining: 'Remaining',
  more: 'Show full description',
  less: 'Show less',
  flagged: 'Worth questioning: ',
  notePlaceholder: 'Your comment or question about this rule',
  save: 'Save',
  saved: 'Saved',
  saveFailed: 'Couldn’t save the note.',
  tooLong: 'That note is over 2,000 characters.',
  earlier: (n: number) => (n === 1 ? '1 earlier version' : `${n} earlier versions`),
  hideEarlier: 'Hide earlier versions',
  noteMarker: 'Note',
  unsavedMarker: 'Unsaved',
  readFailed: 'Couldn’t load the trade rules.',
  tryAgain: 'Try again',
  others: 'Other rules (not in the waterfall)',
  othersNote: 'What the search starts from, cards added after the deck is built, and rules that only reorder.',
  addedTitle: 'Added after the deck was built',
  leaveTitle: 'Unsaved notes',
  leaveBody: (n: number) => `You have ${n} unsaved ${n === 1 ? 'note' : 'notes'}. Leave without saving?`,
  leaveStay: 'Keep editing',
  leaveGo: 'Leave',
  off: 'off today',
  searchLimit: 'search limit',
} as const;

// ── unsaved-notes guard (module state: one page, one founder) ───────────────
let unsavedCount = 0;

/** Run `proceed` now, or after the founder confirms leaving unsaved notes. */
export function confirmLeaveNotes(proceed: () => void): void {
  if (unsavedCount === 0) {
    proceed();
    return;
  }
  Alert.alert(COPY.leaveTitle, COPY.leaveBody(unsavedCount), [
    { text: COPY.leaveStay, style: 'cancel' },
    { text: COPY.leaveGo, style: 'destructive', onPress: () => { unsavedCount = 0; proceed(); } },
  ]);
}

export const ruleWaterfallKey = (leagueId: string) => ['founder', 'rule-waterfall', leagueId] as const;

/** One query definition for the page and for FounderReview's availability check. */
export function ruleWaterfallQuery(leagueId: string) {
  return {
    queryKey: ruleWaterfallKey(leagueId),
    queryFn: ({ signal }: { signal: AbortSignal }) => getRuleWaterfall(leagueId, { signal }),
    retry: false,
    staleTime: 0,
    refetchInterval: (q: { state: { data: RuleWaterfallPage | null | undefined } }) =>
      pollInterval(q.state.data?.status),
  };
}

export default function RuleWaterfallReview({ leagueId, leagueName }: { leagueId: string; leagueName: string | null }) {
  const qc = useQueryClient();
  const navigation = useNavigation<any>();
  const pageQ = useQuery(ruleWaterfallQuery(leagueId));
  const page = pageQ.data ?? null;
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [hideZero, setHideZero] = useState(false);
  const [savedKey, setSavedKey] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [toast, setToast] = useState<string | null>(null);

  // A new league is a new page: drop the drafts.
  useEffect(() => { setDrafts({}); setExpanded({}); setRowErrors({}); }, [leagueId]);

  const saved = useMemo(() => notesByKey(page?.notes), [page?.notes]);
  const dirty = dirtyKeys(drafts, saved);
  useEffect(() => { unsavedCount = dirty.length; }, [dirty.length]);
  useEffect(() => () => { unsavedCount = 0; }, []);
  useEffect(() => navigation.addListener('beforeRemove', (e: any) => {
    if (unsavedCount === 0) return;
    e.preventDefault();
    confirmLeaveNotes(() => navigation.dispatch(e.data.action));
  }), [navigation]);

  useEffect(() => {
    if (!savedKey) return undefined;
    const t = setTimeout(() => setSavedKey(null), 2000);
    return () => clearTimeout(t);
  }, [savedKey]);

  const startM = useMutation({
    mutationFn: () => startRuleWaterfall(leagueId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ruleWaterfallKey(leagueId) }),
    onError: (e: unknown) => {
      const status = e instanceof ApiError ? e.status : undefined;
      const code = e instanceof ApiError ? (e.body as { error?: string } | null)?.error : undefined;
      setToast(startErrorText(status, code));
      void qc.invalidateQueries({ queryKey: ruleWaterfallKey(leagueId) });
    },
  });

  const saveM = useMutation({
    mutationFn: ({ key, body }: { key: string; body: string }) => saveRuleNote(key, body),
    onSuccess: (note: RuleNote, { key }) => {
      qc.setQueryData<RuleWaterfallPage | null>(ruleWaterfallKey(leagueId), (cur) => (cur ? {
        ...cur, notes: [...cur.notes.filter((n) => n.rule_key !== key), ...(note.versions ? [note] : [])],
      } : cur));
      setDrafts((d) => { const next = { ...d }; delete next[key]; return next; });
      setRowErrors((errs) => { const next = { ...errs }; delete next[key]; return next; });
      setSavedKey(key);
      void qc.invalidateQueries({ queryKey: ['founder', 'rule-note-history', key] });
    },
    onError: (e: unknown, { key }) => {
      const code = e instanceof ApiError ? (e.body as { error?: string } | null)?.error : undefined;
      setRowErrors((errs) => ({ ...errs, [key]: code === 'too_long' ? COPY.tooLong : COPY.saveFailed }));
    },
  });

  if (pageQ.isPending) {
    return (
      <View style={styles.center} testID="founder-rules.loading">
        <ActivityIndicator color={ice.base} />
      </View>
    );
  }
  if (pageQ.isError || !page) {
    return (
      <View style={styles.block} testID="founder-rules.error">
        <Text variant="body">{COPY.readFailed}</Text>
        <Button testID="founder-rules.retry" label={COPY.tryAgain} variant="secondary"
          onPress={() => { void pageQ.refetch(); }} />
      </View>
    );
  }

  const w = page.waterfall;
  const running = page.status === 'running' || startM.isPending;
  const { sections, others } = buildTable(page);
  const zeroCount = sections.reduce((n, s) => n + s.rows.filter(isZero).length, 0);
  const problem = statusMessage(page);
  const added = w ? addedLine(w) : null;

  const rowProps = (row: TableRow) => {
    const draft = drafts[row.key];
    const body = draft ?? saved[row.key]?.body ?? '';
    return {
      row,
      note: saved[row.key],
      text: body,
      dirty: dirty.includes(row.key),
      open: !!expanded[row.key],
      quiet: isZero(row),
      saving: saveM.isPending && saveM.variables?.key === row.key,
      justSaved: savedKey === row.key,
      error: rowErrors[row.key] ?? null,
      onToggle: () => setExpanded((x) => ({ ...x, [row.key]: !x[row.key] })),
      onChangeText: (t: string) => setDrafts((d) => ({ ...d, [row.key]: t })),
      onSave: () => saveM.mutate({ key: row.key, body }),
    };
  };

  return (
    <View style={styles.root}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        automaticallyAdjustKeyboardInsets
      >
        <Text variant="heading">{COPY.title}</Text>
        {leagueName ? <Text variant="label" testID="founder-rules.league">{leagueName}</Text> : null}
        <Text variant="bodySm">{COPY.intro}</Text>

        <View style={styles.header} testID="founder-rules.header">
          {w ? (
            <>
              <Text variant="title" testID="founder-rules.headline">{headerLine(w)}</Text>
              <Text variant="bodySm" testID="founder-rules.started-definition">
                {`“Started with” = ${w.started_definition}`}
              </Text>
              <Text variant="data" testID="founder-rules.run-at">
                {`Run ${relativeTime(page.run_at)} · ${formatCount(w.teams)} teams · ${w.generator_version}`}
              </Text>
              {added ? <Text variant="bodySm" testID="founder-rules.added-note">{`(${added})`}</Text> : null}
            </>
          ) : (
            <Text variant="bodySm" testID="founder-rules.no-run">{COPY.noRun}</Text>
          )}
          {running ? (
            <View style={styles.runningRow} testID="founder-rules.running">
              <ActivityIndicator color={ice.base} />
              <Text variant="bodySm" style={styles.flexText}>{COPY.runningNote}</Text>
            </View>
          ) : null}
          {problem && !running ? (
            <Text variant="bodySm" style={styles.problem} testID="founder-rules.problem">{problem}</Text>
          ) : null}
          <Button
            testID="founder-rules.run"
            label={running ? COPY.running : COPY.run}
            variant="primary"
            disabled={running}
            loading={startM.isPending}
            onPress={() => startM.mutate()}
          />
        </View>

        {w && zeroCount > 0 ? (
          <Pressable
            testID="founder-rules.hide-zero"
            accessibilityRole="switch"
            accessibilityState={{ checked: hideZero }}
            onPress={() => setHideZero((v) => !v)}
            style={styles.toggleRow}
          >
            <View style={[styles.box, hideZero && styles.boxOn]} />
            <Text variant="bodySm" style={styles.flexText}>{COPY.hideZero(zeroCount)}</Text>
          </Pressable>
        ) : null}

        {sections.map((section) => (
          <View key={section.stage} style={styles.section} testID={`founder-rules.stage.${section.stage}`}>
            <View style={styles.sectionHeader} accessibilityRole="header">
              <Text variant="label" style={styles.flexText}>{section.title}</Text>
              {section.removed != null ? (
                <Text variant="data">{`${COPY.removed} ${formatCount(section.removed)}`}</Text>
              ) : null}
            </View>
            {section.rows.filter((r) => !(hideZero && isZero(r))).map((row) => (
              <RuleRow key={row.key} {...rowProps(row)} />
            ))}
            {section.stage === 'after the deck is built' && added ? (
              <View style={styles.addedRow} testID="founder-rules.added">
                <Text variant="label">{COPY.addedTitle}</Text>
                <Text variant="data">{`+${formatCount(w!.added)}`}</Text>
                <Text variant="bodySm">{added}</Text>
              </View>
            ) : null}
          </View>
        ))}

        <View style={styles.section} testID="founder-rules.others">
          <View style={styles.sectionHeader} accessibilityRole="header">
            <Text variant="label" style={styles.flexText}>{COPY.others}</Text>
          </View>
          <Text variant="bodySm" style={styles.dim}>{COPY.othersNote}</Text>
          {others.map((row) => <RuleRow key={row.key} {...rowProps(row)} />)}
        </View>
      </ScrollView>
      <Toast visible={!!toast} message={toast ?? ''} tone="error" onDismiss={() => setToast(null)} />
    </View>
  );
}

interface RowProps {
  row: TableRow;
  note: RuleNote | undefined;
  text: string;
  dirty: boolean;
  open: boolean;
  quiet: boolean;
  saving: boolean;
  justSaved: boolean;
  error: string | null;
  onToggle: () => void;
  onChangeText: (t: string) => void;
  onSave: () => void;
}

function RuleRow({ row, note, text, dirty, open, quiet, saving, justSaved, error, onToggle, onChangeText, onSave }: RowProps) {
  const words = statusWords(row);
  const hasNote = !!note && note.versions > 0 && note.body !== '';
  const counter = noteCounter(text.length);
  const byline = noteByline(note, relativeTime);
  const earlier = earlierVersions(note);
  const [showHistory, setShowHistory] = useState(false);
  const historyQ = useQuery({
    queryKey: ['founder', 'rule-note-history', row.key] as const,
    queryFn: ({ signal }) => getRuleNoteHistory(row.key, { signal }),
    enabled: open && showHistory && earlier > 0,
    retry: false,
  });
  return (
    <View style={[styles.row, quiet && styles.rowQuiet]} testID={`founder-rules.row.${row.key}`}>
      <Pressable
        testID={`founder-rules.row.${row.key}.toggle`}
        accessibilityRole="button"
        accessibilityLabel={rowA11yLabel(row, hasNote)}
        accessibilityHint={open ? COPY.less : COPY.more}
        accessibilityState={{ expanded: open }}
        onPress={onToggle}
        style={styles.rowHead}
      >
        <View style={styles.nameLine}>
          <Text variant="title" style={[styles.flexText, quiet && styles.dim]}>{row.name}</Text>
          {!row.live ? <Text variant="label" style={styles.tag}>{COPY.off}</Text> : null}
          {row.kind === 'search_limit' ? <Text variant="label" style={styles.tag}>{COPY.searchLimit}</Text> : null}
          {hasNote ? (
            <Text variant="label" style={styles.noteMarker} testID={`founder-rules.row.${row.key}.has-note`}>
              {COPY.noteMarker}
            </Text>
          ) : null}
          {dirty ? <Text variant="label" style={styles.unsaved}>{COPY.unsavedMarker}</Text> : null}
        </View>
        <Text variant="bodySm" numberOfLines={open ? undefined : 2} style={quiet ? styles.dim : undefined}>
          {row.description}
        </Text>
        {!open ? <Text variant="label" style={styles.more}>{COPY.more}</Text> : null}
        {words ? (
          <Text variant="bodySm" style={styles.dim} testID={`founder-rules.row.${row.key}.status`}>{words}</Text>
        ) : row.removed != null && row.remaining != null ? (
          <View style={styles.counts}>
            <View style={styles.countsLine}>
              <Text variant="data" style={quiet ? styles.dim : undefined}>
                {`${COPY.removed} ${formatCount(row.removed)}`}
              </Text>
              <Text variant="data" style={styles.dim}>{`${COPY.remaining} ${formatCount(row.remaining)}`}</Text>
              <Text variant="data" style={styles.dim}>{formatShare(row.share)}</Text>
            </View>
            <Meter value={row.share} color={quiet ? ink.lineStrong : flare.base} />
            {row.removed > 0 ? (
              <Text variant="bodySm" style={styles.dim}>
                {`Removed ${formatShare(row.shareReaching)} of the trades that reached it`}
              </Text>
            ) : null}
          </View>
        ) : null}
      </Pressable>
      {open ? (
        <View style={styles.noteBlock}>
          {row.question ? (
            <Text variant="bodySm" testID={`founder-rules.row.${row.key}.question`}>
              <Text variant="bodySm" style={styles.questionLead}>{COPY.flagged}</Text>
              {row.question}
            </Text>
          ) : null}
          <TextInput
            testID={`founder-rules.row.${row.key}.note`}
            style={styles.input}
            value={text}
            onChangeText={onChangeText}
            placeholder={COPY.notePlaceholder}
            placeholderTextColor={chalk.faint}
            multiline
            maxLength={NOTE_MAX}
            accessibilityLabel={`Note on ${row.name}`}
          />
          <View style={styles.noteActions}>
            <View style={styles.flexText}>
              {counter ? (
                <Text variant="data" testID={`founder-rules.row.${row.key}.counter`}>{counter}</Text>
              ) : null}
              {justSaved ? <Text variant="bodySm" testID={`founder-rules.row.${row.key}.saved`}>{COPY.saved}</Text> : null}
              {error ? <Text variant="bodySm" style={styles.problem}>{error}</Text> : null}
              {byline && !justSaved ? <Text variant="bodySm" style={styles.dim}>{byline}</Text> : null}
            </View>
            <Button
              testID={`founder-rules.row.${row.key}.save`}
              label={COPY.save}
              variant="secondary"
              disabled={!dirty || saving}
              loading={saving}
              onPress={onSave}
              accessibilityLabel={`Save note on ${row.name}`}
            />
          </View>
          {earlier > 0 ? (
            <Pressable
              testID={`founder-rules.row.${row.key}.history`}
              accessibilityRole="button"
              onPress={() => setShowHistory((v) => !v)}
              style={styles.historyToggle}
            >
              <Text variant="label" style={styles.more}>{showHistory ? COPY.hideEarlier : COPY.earlier(earlier)}</Text>
            </Pressable>
          ) : null}
          {showHistory && historyQ.data ? (
            <View style={styles.history}>
              {historyQ.data.history.slice(0, -1).reverse().map((v, i) => (
                <View key={`${v.created_at}-${i}`} style={styles.historyItem}>
                  <Text variant="label">{`${v.author} · ${relativeTime(v.created_at)}`}</Text>
                  <Text variant="bodySm">{v.body === '' ? '(cleared)' : v.body}</Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  content: { padding: space.lg, gap: space.md, paddingBottom: space.xxxl },
  block: { gap: space.lg, padding: space.lg },
  center: { alignItems: 'center', justifyContent: 'center', paddingVertical: space.xxxl },
  header: {
    gap: space.sm, padding: space.md, borderWidth: 1, borderColor: ink.line,
    borderRadius: radii.sm, backgroundColor: ink.ink1,
  },
  runningRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  flexText: { flexShrink: 1, flexGrow: 1 },
  problem: { color: chalk.base },
  dim: { color: chalk.dim },
  toggleRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, minHeight: 44 },
  box: { width: 18, height: 18, borderRadius: radii.xs, borderWidth: 1, borderColor: ink.lineStrongA11y },
  boxOn: { backgroundColor: ice.base, borderColor: ice.base },
  section: { gap: space.sm },
  sectionHeader: {
    flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space.sm,
    paddingVertical: space.xs, borderBottomWidth: 1, borderBottomColor: ink.line,
  },
  row: {
    gap: space.sm, padding: space.md, borderWidth: 1, borderColor: ink.line,
    borderRadius: radii.sm, backgroundColor: ink.ink1,
  },
  rowQuiet: { backgroundColor: ink.ink0 },
  rowHead: { gap: space.xs },
  nameLine: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space.sm },
  tag: {
    paddingHorizontal: space.xs, borderWidth: 1, borderColor: ink.lineStrong, borderRadius: radii.xs,
  },
  noteMarker: {
    color: flare.base, paddingHorizontal: space.xs, borderWidth: 1, borderColor: flare.base,
    borderRadius: radii.xs,
  },
  unsaved: { color: chalk.base },
  more: { color: ice.base },
  counts: { gap: space.xs },
  countsLine: { flexDirection: 'row', flexWrap: 'wrap', gap: space.md },
  noteBlock: { gap: space.sm },
  questionLead: { ...type.bodySm, color: chalk.base },
  input: {
    ...type.body,
    minHeight: 84,
    padding: space.md,
    textAlignVertical: 'top',
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.sm,
  },
  noteActions: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: space.sm },
  historyToggle: { minHeight: 44, justifyContent: 'center' },
  history: { gap: space.sm, paddingLeft: space.md, borderLeftWidth: 1, borderLeftColor: ink.line },
  historyItem: { gap: space.xs },
  addedRow: {
    gap: space.xs, padding: space.md, borderWidth: 1, borderColor: ink.line, borderStyle: 'dashed',
    borderRadius: radii.sm,
  },
});

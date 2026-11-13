import React, { useEffect, useState } from 'react';
import { View, Pressable, StyleSheet } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { Badge, Button, Icon, Text } from './chalkline';
import { ink, chalk, ice, space, type } from '../theme/chalkline';
import type { MaxPfMoves, MaxPfMoveRow } from '../api/leagueProjections';
import { setDraftOrderRule } from '../api/draftOrderRule';
import { track } from '../api/events';
import { useFinderTargets } from '../state/useFinderTargets';
import { readMaxPfPrompts, markRulesNoteShown, markDraftOrderAsked } from '../state/maxPfMovesPrompts';
import { MAXPF_COPY as C } from '../utils/maxPfMovesCopy';
import {
  rowLine1, rowLine1Parts, rowLine2, rowDetail, visibleRows, viewedProps, expandedProps, answeredProps,
  answerLabel, handOffToFinder, questionAutoShown, MAXPF_EVENTS, DRAFT_ORDER_ANSWERS, SCREEN,
  type SectionModel, type DraftOrderAnswer,
} from '../utils/maxPfMoves';

// Max PF moves — the body of the fourth disclosure inside the user's OWN
// open team card on Standings (contract §2; LeagueProjectionDetail mounts it
// under "Draft pick odds"). Everything shown is decided in utils/maxPfMoves
// (`model`); this file only renders and wires the taps. It mounts when the
// disclosure opens, which is when the section body becomes visible
// (maxpf_moves_viewed, once per opening of the card via `viewedRef`).
//
// NO extra request on open: the block rides the one forecast read
// (['league-projection-batch', userId, leagueId]). The only request this file
// makes is the draft-order POST, after a tap, followed by a refetch of that
// same key.

interface Props {
  block: MaxPfMoves;
  model: SectionModel;
  leagueId: string;
  userId: string | null;
  /** Owned by the open team card, so the impression fires once per opening. */
  viewedRef: React.MutableRefObject<boolean>;
}

export function MaxPfMovesBody({ block, model, leagueId, userId, viewedRef }: Props) {
  const navigation = useNavigation<any>();
  const queryClient = useQueryClient();
  const [revealed, setRevealed] = useState(false);       // Show anyway / Show moves
  const [showAll, setShowAll] = useState(false);
  const [openRank, setOpenRank] = useState<number | null>(null);
  const [prompts, setPrompts] = useState<{ rulesNote: boolean; asked: boolean } | null>(null);
  const [question, setQuestion] = useState<'first_ask' | 'change' | null>(null);
  const [posting, setPosting] = useState<DraftOrderAnswer | null>(null);
  const [postError, setPostError] = useState(false);

  useEffect(() => {
    if (viewedRef.current) return;
    viewedRef.current = true;
    track(MAXPF_EVENTS.viewed, viewedProps(block, model), SCREEN);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Device-only prompts (§6.4): read once per mount; nothing shows until read.
  useEffect(() => {
    let cancelled = false;
    readMaxPfPrompts(leagueId).then((p) => {
      if (cancelled) return;
      setPrompts({ rulesNote: !p.rulesNoteShown, asked: p.draftOrderAsked });
    });
    return () => { cancelled = true; };
  }, [leagueId]);

  // Gates (§6.2 overrides §6.1): owner first, then collapsed.
  const gated = model.isList && !revealed && (model.ownerGate || !model.defaultOpen);
  const listOpen = model.isList && !gated;
  const showRulesNote = listOpen && !!model.baseline && !!prompts?.rulesNote;
  useEffect(() => {
    if (showRulesNote) markRulesNoteShown();
  }, [showRulesNote]);

  const autoAsk = !!prompts && question === null && questionAutoShown(block, prompts.asked);
  const questionShown = question !== null || autoAsk;
  const questionSource: 'first_ask' | 'change' = question ?? 'first_ask';

  const answer = async (rule: DraftOrderAnswer) => {
    if (posting) return;
    setPosting(rule);
    setPostError(false);
    try {
      await setDraftOrderRule(leagueId, rule);
      markDraftOrderAsked(leagueId);
      track(MAXPF_EVENTS.answered, answeredProps(rule, questionSource), SCREEN);
      setPrompts((p) => (p ? { ...p, asked: true } : p));
      setQuestion(null);
      queryClient.invalidateQueries({ queryKey: ['league-projection-batch', userId, leagueId] });
    } catch {
      setPostError(true);
    } finally {
      setPosting(null);
    }
  };

  const onFindTrades = (row: MaxPfMoveRow) =>
    handOffToFinder(row, {
      setSide: (side, players) => useFinderTargets.getState().setSide(side, players),
      track,
      // Standings is a ROOT-stack push over 'Main', so a bare
      // navigate('Trades') is unhandled in React Navigation 7: pop back to
      // Main's Trades tab (the League rankings legacy-push pattern), with the
      // canvas prefill from utils/maxPfMoves.finderNavParams.
      navigate: (params) => navigation.popTo('Main', params),
      now: Date.now,
    });

  const toggleRow = (row: MaxPfMoveRow) => {
    const opening = openRank !== row.rank;
    setOpenRank(opening ? row.rank : null);
    if (opening) track(MAXPF_EVENTS.expanded, expandedProps(row), SCREEN);
  };

  const { rows, showAllButton } = visibleRows(model.listed, showAll);

  return <View style={styles.body} testID="standings.maxpf.body">
    {questionShown ? <View style={styles.question} testID="standings.maxpf.question">
      <Text variant="bodySm" style={styles.strong}>{C['C-Q']}</Text>
      <View style={styles.answers}>
        {DRAFT_ORDER_ANSWERS.map((a) => <Button key={a} label={answerLabel(a)} variant="secondary"
          loading={posting === a} onPress={() => answer(a)} testID={`standings.maxpf.answer.${a}`} />)}
      </View>
      {postError ? <Text variant="bodySm" style={styles.strong} testID="standings.maxpf.answer-error">{C['C-Q-ERR']}</Text> : null}
    </View> : null}

    {model.line ? <Text variant="bodySm" testID="standings.maxpf.line">{model.line}</Text> : null}

    {model.isList && gated ? <View style={styles.gate}>
      <Text variant="bodySm">{model.ownerGate ? model.ownerLine : model.collapsedLine}</Text>
      <Button label={model.ownerGate ? C['C-OWNER.button'] : C['C-COLLAPSED.button']} variant="secondary"
        onPress={() => setRevealed(true)}
        testID={model.ownerGate ? 'standings.maxpf.show-anyway' : 'standings.maxpf.show-moves'} />
    </View> : null}

    {listOpen ? <>
      {model.baseline ? <Text variant="bodySm" testID="standings.maxpf.baseline">{model.baseline}</Text> : null}
      {showRulesNote ? <Text variant="bodySm" testID="standings.maxpf.rules">{C['C-RULES']}</Text> : null}
      {model.rosterLine ? <Text variant="bodySm" style={styles.strong} testID="standings.maxpf.roster-changed">{model.rosterLine}</Text> : null}
      {model.noMovesLine ? <Text variant="bodySm" testID="standings.maxpf.no-moves">{model.noMovesLine}</Text> : null}
      {model.head ? <Text variant="label" style={styles.head}>{model.head}</Text> : null}
      {rows.map((row) => <MoveRow key={row.player_id} row={row} priced={model.priced}
        open={openRank === row.rank} onToggle={() => toggleRow(row)} onFindTrades={() => onFindTrades(row)} />)}
      {showAllButton ? <Pressable accessibilityRole="button" testID="standings.maxpf.show-all"
        onPress={() => setShowAll(true)} style={styles.link}>
        <Text variant="bodySm" style={styles.linkText}>{C['C-SHOWALL']}</Text>
      </Pressable> : null}
      {model.foot ? <Text variant="bodySm">{model.foot}</Text> : null}
    </> : null}

    {model.order && (listOpen || !model.isList) ? <View style={styles.order}>
      {model.order.text ? <Text variant="bodySm" style={styles.orderText}>{model.order.text}</Text> : null}
      <Pressable accessibilityRole="button" testID="standings.maxpf.order-change" hitSlop={{ top: 6, bottom: 6 }}
        onPress={() => { setPostError(false); setQuestion('change'); }} style={styles.link}>
        <Text variant="bodySm" style={styles.linkText}>{model.order.link}</Text>
      </Pressable>
    </View> : null}
  </View>;
}

function MoveRow({ row, priced, open, onToggle, onFindTrades }: {
  row: MaxPfMoveRow; priced: boolean; open: boolean; onToggle: () => void; onFindTrades: () => void;
}) {
  const p = rowLine1Parts(row);
  const line2 = rowLine2(row, priced);
  const d = open ? rowDetail(row) : null;
  return <View style={styles.row}>
    <Pressable accessibilityRole="button" aria-expanded={open} testID={`standings.maxpf.row.${row.rank}`}
      accessibilityLabel={`${rowLine1(row)}${row.keep ? `, ${C['C-KEEP']}` : ''}. ${line2}`}
      onPress={onToggle} style={styles.rowHead}>
      <View style={styles.rowText}>
        <View style={styles.line1}>
          <Text variant="bodySm" style={[styles.strong, styles.name]} numberOfLines={1}>{p.name}</Text>
          <Text variant="bodySm">{p.position}</Text>
          {row.keep ? <Badge label={C['C-KEEP']} /> : null}
          <Text scale="dense" style={styles.num}>{p.change}</Text>
        </View>
        <Text variant="bodySm">{line2}</Text>
      </View>
      <Icon name={open ? 'chevron-up' : 'chevron-down'} size={16} color={chalk.base} />
    </Pressable>
    {d ? <View style={styles.rowDetail} testID={`standings.maxpf.detail.${row.rank}`}>
      <Text variant="bodySm">{d.top3}</Text>
      <Text variant="bodySm">{d.playoff}</Text>
      {d.label ? <Text variant="bodySm">{d.label}</Text> : null}
      {d.replacement ? <Text variant="bodySm">{d.replacement}</Text> : null}
      {d.weeks.map((w) => <Text key={w} variant="bodySm">{w}</Text>)}
      {d.button ? <Button label={d.button} variant="secondary" onPress={onFindTrades}
        testID={`standings.maxpf.find.${row.rank}`} /> : null}
      {d.keepNote ? <Text variant="bodySm" testID={`standings.maxpf.keep-note.${row.rank}`}>{d.keepNote}</Text> : null}
    </View> : null}
  </View>;
}

// Same construction as LeagueProjectionDetail's disclosures: ink-3 hairlines,
// 44pt rows, chalk text. Ice only on the tappable links (actions).
const styles = StyleSheet.create({
  body: { gap: space.sm },
  strong: { color: chalk.base },
  question: { gap: space.sm },
  answers: { gap: space.sm },
  gate: { gap: space.sm, alignItems: 'flex-start' },
  head: { marginTop: space.xs },
  row: { borderTopWidth: 1, borderTopColor: ink.ink3 },
  rowHead: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingVertical: space.xs },
  rowText: { flex: 1, minWidth: 0, gap: 2 },
  line1: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  name: { flexShrink: 1, minWidth: 0 },
  num: { ...type.data, marginLeft: 'auto', flexShrink: 0 },
  rowDetail: { gap: space.xs, paddingBottom: space.sm, alignItems: 'flex-start' },
  order: { gap: 2, alignItems: 'flex-start' },
  orderText: { flexShrink: 1 },
  link: { minHeight: 44, justifyContent: 'center' },
  linkText: { color: ice.base },
});

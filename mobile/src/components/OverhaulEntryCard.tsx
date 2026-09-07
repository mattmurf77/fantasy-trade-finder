import React from 'react';
import { View, Pressable, StyleSheet } from 'react-native';

import ChalkText from './chalkline/Text';
import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { LIVE_ATTEMPT_STATES, type OverhaulView, type OverhaulOutlook } from '../api/overhaul';

// Team overhaul (flag `overhaul.enabled`, BUILD-CONTRACT §9 / D9) — the Acquire
// landing entry, mounted by TradesScreen directly below TeamReviewEntryCard.
//
// Two states, one location: no saved plan → "Start overhaul"; a saved plan →
// "Resume overhaul" with the plan's outlook and a compact summary derived from
// the OverhaulView the host already fetched. Prop-driven: the host owns the
// `['overhaul', leagueId]` query, the analytics event and the navigation.
//
// Unlike TeamReviewEntryCard there is no collapse/dismiss — an overhaul with
// offers in flight is the one thing on this screen the user must not lose.

const OUTLOOK_LABEL: Record<OverhaulOutlook, string> = {
  push_all_in: 'Push all in',
  blow_it_up: 'Blow it up',
};

/** One line describing where a saved overhaul stands. Counts only. */
export function overhaulSummaryLine(active: OverhaulView): string {
  const attempts = active.attempts ?? [];
  if (attempts.length > 0) {
    const sent = attempts.filter((a) => LIVE_ATTEMPT_STATES.has(a.state)).length;
    const accepted = attempts.filter((a) => a.state === 'accepted').length;
    const roadmap = active.roadmaps.find((r) => r.roadmap_id === active.selected_roadmap_id);
    const left = roadmap
      ? roadmap.packages.filter((p) => p.status !== 'complete').length
      : null;
    const parts = [`${sent} sent`, `${accepted} accepted`];
    if (left != null) parts.push(`${left} ${left === 1 ? 'package' : 'packages'} left`);
    return parts.join(' · ');
  }
  switch (active.status) {
    case 'setup':
      return 'Setup in progress';
    case 'reviewing':
      return `${active.progress.decided} of ${active.progress.total} offers reviewed`;
    case 'assembled':
      return 'Roadmap chosen · set your priorities';
    case 'complete':
      return 'Overhaul complete';
    default:
      return 'Saved plan';
  }
}

export default function OverhaulEntryCard({
  leagueId,
  active,
  onStart,
  onResume,
}: {
  leagueId: string;
  active: OverhaulView | null;
  onStart: () => void;
  onResume: (overhaulId: string) => void;
}) {
  if (!leagueId) return null;

  if (!active) {
    return (
      <View style={styles.card} testID="overhaul.entry-card">
        <ChalkText style={styles.kicker}>Team overhaul</ChalkText>
        <ChalkText style={styles.body}>
          Plan 4–5 independent trades that push all in or blow it up, then send them together.
        </ChalkText>
        <Pressable
          testID="overhaul.entry-start"
          style={styles.cta}
          onPress={onStart}
          accessibilityRole="button"
          accessibilityLabel="Start overhaul"
        >
          <ChalkText style={styles.ctaText}>Start overhaul</ChalkText>
        </Pressable>
      </View>
    );
  }

  const outlook = active.settings.outlook ? OUTLOOK_LABEL[active.settings.outlook] : 'Outlook not set';
  const inMotion = active.attempts.some((a) => LIVE_ATTEMPT_STATES.has(a.state));
  return (
    <View style={styles.card} testID="overhaul.entry-card">
      <View style={styles.head}>
        <ChalkText style={styles.kicker}>Your saved roadmap</ChalkText>
        <View style={styles.outlookPill}>
          <ChalkText style={styles.outlookText}>{outlook}</ChalkText>
        </View>
      </View>
      <ChalkText style={styles.title}>Resume overhaul</ChalkText>
      <ChalkText style={styles.body}>
        {inMotion
          ? 'Your plan is in motion. Review responses and choose the next offer for each package.'
          : 'Pick up where you left off.'}
      </ChalkText>
      <ChalkText style={styles.summary}>{overhaulSummaryLine(active)}</ChalkText>
      <Pressable
        testID="overhaul.entry-resume"
        style={styles.cta}
        onPress={() => onResume(active.overhaul_id)}
        accessibilityRole="button"
        accessibilityLabel="Resume overhaul"
      >
        <ChalkText style={styles.ctaText}>Resume overhaul</ChalkText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: ink.ink1, borderWidth: 1, borderColor: ink.lineStrongA11y,
    borderRadius: radii.md, padding: space.md, marginBottom: space.md, gap: space.sm,
  },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  kicker: { ...type.label, color: chalk.dim, letterSpacing: 1, textTransform: 'uppercase' },
  title: { ...type.title, color: chalk.base },
  body: { ...type.bodySm, color: chalk.base },
  summary: { ...type.bodySm, color: semantic.pos, fontFamily: fonts.data },
  outlookPill: {
    borderWidth: 1, borderColor: ink.lineStrongA11y, borderRadius: radii.xs,
    paddingHorizontal: space.sm, paddingVertical: 2,
  },
  outlookText: { ...type.label, color: chalk.base },
  cta: {
    backgroundColor: ice.base, borderRadius: radii.sm,
    paddingVertical: 10, alignItems: 'center',
  },
  ctaText: { ...type.bodySm, color: ice.on, fontFamily: fonts.uiBold },
});

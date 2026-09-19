import React from 'react';
import { View, Pressable, StyleSheet } from 'react-native';

import ChalkText from './chalkline/Text';
import { ice, space, radii, type, fonts } from '../theme/chalkline';
import { LIVE_ATTEMPT_STATES, type OverhaulView, type OverhaulOutlook } from '../api/overhaul';

// Team overhaul (flag `overhaul.enabled`, BUILD-CONTRACT §9 / D9) — the Acquire
// landing entry. Since G-425 (#425/#426) it is a full-width HERO TILE mounted by
// TradesScreen directly above the utility row / mode bar — the slot the strip
// cohort's Draft cell used to occupy — instead of a card under Team review.
//
// Two states, one location: no saved plan → "Start overhaul"; a saved plan →
// "Resume overhaul" with the plan's outlook and a compact summary derived from
// the OverhaulView the host already fetched. Prop-driven: the host owns the
// `['overhaul', leagueId]` query, the analytics event and the navigation.
//
// Colour: HERO_TONE below is the ONE place this file names a colour. The
// operator asked for red (#426); the design system has no red action fill
// (flare is informational-only, `neg` is Pass/error), so the tile is ice —
// the only sanctioned bold action colour. If a hero/alarm token is ever added,
// switching is a one-object edit here. Pinned by check-team-overhaul.js §3e.
//
// Unlike TeamReviewEntryCard there is no collapse/dismiss — an overhaul with
// offers in flight is the one thing on this screen the user must not lose.

const HERO_TONE = { fill: ice.base, press: ice.press, on: ice.on } as const;

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
      <View testID="overhaul.entry-card">
        <Pressable
          testID="overhaul.entry-start"
          style={({ pressed }) => [styles.tile, pressed && styles.tilePressed]}
          onPress={onStart}
          accessibilityRole="button"
          accessibilityLabel="Start overhaul"
        >
          <View style={styles.main}>
            <ChalkText scale="display" style={styles.title}>Team overhaul</ChalkText>
            <ChalkText style={styles.line}>
              Plan 4–5 trades that push all in or blow it up.
            </ChalkText>
          </View>
          <ChalkText style={styles.trail}>Start overhaul ›</ChalkText>
        </Pressable>
      </View>
    );
  }

  const outlook = active.settings.outlook ? OUTLOOK_LABEL[active.settings.outlook] : 'Outlook not set';
  return (
    <View testID="overhaul.entry-card">
      <Pressable
        testID="overhaul.entry-resume"
        style={({ pressed }) => [styles.tile, pressed && styles.tilePressed]}
        onPress={() => onResume(active.overhaul_id)}
        accessibilityRole="button"
        accessibilityLabel="Resume overhaul"
      >
        <View style={styles.main}>
          <ChalkText scale="display" style={styles.title}>Resume overhaul</ChalkText>
          <ChalkText style={styles.line} numberOfLines={1}>
            {outlook} · {overhaulSummaryLine(active)}
          </ChalkText>
        </View>
        <ChalkText style={styles.trail}>Resume ›</ChalkText>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  // Full width of the scroll content; the ScrollView's own `gap` spaces it, so
  // no margin here. minHeight 64 matches the utility cells it replaces.
  tile: {
    backgroundColor: HERO_TONE.fill,
    borderRadius: radii.md,
    minHeight: 64,
    paddingVertical: space.md,
    paddingHorizontal: space.lg,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
  },
  tilePressed: { backgroundColor: HERO_TONE.press },
  main: { flex: 1, gap: space.xs },
  title: { ...type.heading, color: HERO_TONE.on },
  line: { ...type.bodySm, color: HERO_TONE.on },
  trail: { ...type.bodySm, color: HERO_TONE.on, fontFamily: fonts.uiBold },
});

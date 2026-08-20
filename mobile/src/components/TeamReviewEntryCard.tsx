import React, { useEffect, useState } from 'react';
import { View, Pressable, StyleSheet } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

import ChalkText from './chalkline/Text';
import { AnalystAvatar } from './analyst';
import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';

// #357/#358/#359 — the Team Review entry on TradesHome.
//
// DISMISSING COLLAPSES; IT NEVER REMOVES. This follows D-025's ruling for the
// League-Summary outlook section verbatim — "a collapsed one-line strip
// (per-league, per-user persisted) with the full section one tap away". The
// reason is the same here: a permanently dismissible entry means the user who
// most needs this feature can lose it forever with one accidental tap, and
// TradesHome has no other always-present surface to recover it from.
//
// Storage is a SPARSE record of collapsed league ids, so the blob only ever
// names leagues the user actually collapsed.

const KEY = 'ftf_team_review_collapsed';

// Operator, 2026-08-20: "track user completion of the experience. Once they've
// gone through it, it should be minimized by default."
//
// KEPT SEPARATE FROM `KEY` ON PURPOSE. Collapsing is "not now" — a deferral the
// user may reverse. Completing is "I have read this" — a fact about the flow.
// Folding them into one flag would make a completed review indistinguishable
// from a dismissed one, and the row copy below needs to tell them apart. Both
// render the same minimized row; only the label differs.
const DONE_KEY = 'ftf_team_review_completed';

type LeagueFlags = Record<string, true>;

const readMap = async (key: string): Promise<LeagueFlags> => {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as LeagueFlags) : {};
  } catch {
    return {};
  }
};

/** Record that this league's review was run to the end. Called from the
 *  `plan` beat's finish action, so the entry is minimized next time
 *  TradesHome renders. Fire-and-forget: a storage failure costs the
 *  minimization, never the navigation. */
export async function markTeamReviewCompleted(leagueId: string): Promise<void> {
  if (!leagueId) return;
  try {
    const map = await readMap(DONE_KEY);
    if (map[leagueId]) return;
    map[leagueId] = true;
    await AsyncStorage.setItem(DONE_KEY, JSON.stringify(map));
  } catch {
    /* quota or serialization failure is not fatal */
  }
}

export default function TeamReviewEntryCard({
  leagueId,
  onOpen,
}: {
  leagueId: string;
  onOpen: (source: 'trades_home_card' | 'collapsed_row') => void;
}) {
  const [collapsed, setCollapsed] = useState<boolean | null>(null);
  const [completed, setCompleted] = useState(false);

  useEffect(() => {
    let dead = false;
    Promise.all([readMap(KEY), readMap(DONE_KEY)])
      .then(([collapsedMap, doneMap]) => {
        if (dead) return;
        const isDone = !!doneMap[leagueId];
        setCompleted(isDone);
        // A completed review minimizes by default; an explicit "Not now" still
        // minimizes on its own. Either one is enough.
        setCollapsed(!!collapsedMap[leagueId] || isDone);
      })
      .catch(() => { if (!dead) setCollapsed(false); });
    return () => { dead = true; };
  }, [leagueId]);

  const persist = (next: boolean) => {
    setCollapsed(next);
    readMap(KEY)
      .then((map) => {
        if (next) map[leagueId] = true;
        else delete map[leagueId];
        return AsyncStorage.setItem(KEY, JSON.stringify(map));
      })
      .catch(() => { /* fire-and-forget; a quota failure is not fatal */ });
  };

  if (collapsed === null) return null;   // pre-hydration: render nothing, never a flash

  if (collapsed) {
    return (
      <Pressable
        testID="team-review.entry-row"
        style={styles.row}
        onPress={() => onOpen('collapsed_row')}
        accessibilityRole="button"
        accessibilityLabel={completed ? 'Run team review again' : 'Open team review'}
      >
        <ChalkText style={styles.rowText}>
          {completed ? 'Team review · done' : 'Team review'}
        </ChalkText>
        <ChalkText style={styles.rowChevron}>›</ChalkText>
      </Pressable>
    );
  }

  return (
    <View style={styles.card} testID="team-review.entry-card">
      <View style={styles.head}>
        <AnalystAvatar pose="neutral" size={38} />
        <View style={styles.headText}>
          <ChalkText style={styles.kicker}>Not sure what to do with this team?</ChalkText>
          <ChalkText style={styles.body}>
            I&apos;ll walk your roster in about a minute and set your trade
            preferences as we go.
          </ChalkText>
        </View>
      </View>
      <View style={styles.actions}>
        <Pressable
          testID="team-review.entry-start"
          style={styles.cta}
          onPress={() => onOpen('trades_home_card')}
        >
          <ChalkText style={styles.ctaText}>Start team review</ChalkText>
        </Pressable>
        <Pressable
          testID="team-review.entry-dismiss"
          style={styles.dismiss}
          onPress={() => persist(true)}
          accessibilityLabel="Collapse team review"
        >
          <ChalkText style={styles.dismissText}>Not now</ChalkText>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: ink.ink1, borderWidth: 1, borderColor: ink.lineStrongA11y,
    borderRadius: radii.md, padding: space.md, marginBottom: space.md, gap: space.sm,
  },
  head: { flexDirection: 'row', gap: space.sm, alignItems: 'flex-start' },
  headText: { flex: 1, gap: 2 },
  kicker: { ...type.label, color: chalk.dim, letterSpacing: 1, textTransform: 'uppercase' },
  body: { ...type.bodySm, color: chalk.base },
  actions: { flexDirection: 'row', gap: space.sm, alignItems: 'center' },
  cta: {
    flex: 1, backgroundColor: ice.base, borderRadius: radii.sm,
    paddingVertical: 10, alignItems: 'center',
  },
  ctaText: { ...type.bodySm, color: ice.on, fontFamily: fonts.uiBold },
  dismiss: { paddingHorizontal: space.md, paddingVertical: 10 },
  dismissText: { ...type.bodySm, color: chalk.dim },
  row: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: ink.ink1, borderWidth: 1, borderColor: ink.line,
    borderRadius: radii.sm, paddingHorizontal: space.md, paddingVertical: 10,
    marginBottom: space.md,
  },
  rowText: { ...type.bodySm, color: chalk.dim },
  rowChevron: { ...type.bodySm, color: ice.base },
});

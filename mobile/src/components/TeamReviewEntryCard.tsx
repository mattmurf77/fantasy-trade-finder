import React, { useEffect, useState } from 'react';
import { View, Pressable, StyleSheet } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

import ChalkText from './chalkline/Text';
import { AnalystAvatar } from './analyst';
import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';
import { useTeamReviewCompletion } from '../state/teamReviewCompletion';

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
//
// #423 — completion lives in `state/teamReviewCompletion.ts` (same device key,
// same sparse map), NOT in a mount-time read here: TradesHome stays mounted
// beneath the pushed review, so a once-per-mount read could never show "done"
// until relaunch. The card subscribes to the store instead.

type LeagueFlags = Record<string, true>;

const readMap = async (key: string): Promise<LeagueFlags> => {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as LeagueFlags) : {};
  } catch {
    return {};
  }
};

/** Record that this league's review was gone through. Called when the
 *  review reaches the `plan` beat and again from its finish action (the
 *  store's `mark` is idempotent), so the entry is minimized the moment
 *  TradesHome is visible again — the store updates synchronously and
 *  mirrors to disk fire-and-forget: a storage failure costs the next-launch
 *  minimization, never the navigation. */
export function markTeamReviewCompleted(leagueId: string): void {
  useTeamReviewCompletion.getState().mark(leagueId);
}

export default function TeamReviewEntryCard({
  leagueId,
  onOpen,
}: {
  leagueId: string;
  onOpen: (source: 'trades_home_card' | 'collapsed_row') => void;
}) {
  // "Not now" — this card's own deferral, still read once per mount.
  const [collapsed, setCollapsed] = useState<boolean | null>(null);
  // Completion — live from the store, so a review finished while this card sat
  // mounted beneath it minimizes the entry on the way back (#423).
  const hydrated = useTeamReviewCompletion((s) => s.hydrated);
  const completed = useTeamReviewCompletion((s) => !!s.byLeague[leagueId]);

  useEffect(() => {
    void useTeamReviewCompletion.getState().hydrate();
  }, []);

  useEffect(() => {
    let dead = false;
    readMap(KEY)
      .then((collapsedMap) => { if (!dead) setCollapsed(!!collapsedMap[leagueId]); })
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

  // Pre-hydration (either source): render nothing, never a flash.
  if (collapsed === null || !hydrated) return null;

  // A completed review minimizes by default; an explicit "Not now" still
  // minimizes on its own. Either one is enough.
  if (collapsed || completed) {
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

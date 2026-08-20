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

export default function TeamReviewEntryCard({
  leagueId,
  onOpen,
}: {
  leagueId: string;
  onOpen: (source: 'trades_home_card' | 'collapsed_row') => void;
}) {
  const [collapsed, setCollapsed] = useState<boolean | null>(null);

  useEffect(() => {
    let dead = false;
    AsyncStorage.getItem(KEY)
      .then((raw) => {
        if (dead) return;
        const map = raw ? (JSON.parse(raw) as Record<string, true>) : {};
        setCollapsed(!!map[leagueId]);
      })
      .catch(() => { if (!dead) setCollapsed(false); });
    return () => { dead = true; };
  }, [leagueId]);

  const persist = (next: boolean) => {
    setCollapsed(next);
    AsyncStorage.getItem(KEY)
      .then((raw) => {
        const map = raw ? (JSON.parse(raw) as Record<string, true>) : {};
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
        accessibilityLabel="Open team review"
      >
        <ChalkText style={styles.rowText}>Team review</ChalkText>
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

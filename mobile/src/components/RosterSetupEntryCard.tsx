import React, { useEffect, useRef } from 'react';
import { View, Pressable, StyleSheet } from 'react-native';
import { useNavigation } from '@react-navigation/native';

import ChalkText from './chalkline/Text';
import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';
import { track } from '../api/events';
import { useRosterSetup } from '../state/rosterSetup';
import { useOnboardingState } from '../state/useOnboardingState';
import { useMyRosterAssets } from '../hooks/useMyRosterAssets';
import {
  cardView,
  ladderOnShow,
  ladderOnSnooze,
  newAssetIds,
  type PromptKind,
} from '../utils/rosterSetup';

// Roster-first setup's TradesHome RETURN CARD (flag `trades.roster_setup`;
// prd §3.2/§3.3, TeamReviewEntryCard pattern). TradesScreen mounts this ONLY
// with the flag on, on the `TradesHome` route, outside demo — so with the
// flag off nothing here exists: no query, no card (AC-0).
//
// This card never pushes the setup on its own. The automatic entry is the
// user's first declined suggestion in a league (operator amendment
// 2026-11-10), owned by `hooks/useRosterSetupPassTrigger` and called from
// TradesScreen's committed-pass points.
//
//    - `skipped` record → "Set up your roster" (opens the full step);
//    - `done` record whose roster gained assets → "N new on your roster"
//      (opens Step 1 filtered to them). Losing assets never prompts.
//    Snooze grammar = QuickSetPromptCard's: Not now → one re-offer in a later
//    session → retired. A retired entry card COLLAPSES to a one-line row
//    rather than vanishing (D-025: one accidental tap must not lose the
//    feature); a retired roster-changed card absorbs the new assets into the
//    snapshot instead. Impressions ride the existing `prompt_shown` event
//    (surface `roster_setup_card`).

const impressionsThisSession = new Set<string>();

export default function RosterSetupEntryCard({
  leagueId,
  userId,
  isDemo,
}: {
  leagueId: string;
  userId: string;
  isDemo: boolean;
}) {
  const navigation = useNavigation<any>();
  const hydrated = useRosterSetup((s) => s.hydrated);
  const record = useRosterSetup((s) => s.byLeague[leagueId]);
  const write = useRosterSetup((s) => s.write);
  const sessionCount = useOnboardingState((s) => s.ob.sessionCount);
  const roster = useMyRosterAssets(leagueId, userId, !isDemo);

  useEffect(() => {
    void useRosterSetup.getState().hydrate();
  }, []);

  // ── Card ──────────────────────────────────────────────────────────────
  const ready = hydrated && !!record && roster.rostersReady && roster.picksSettled;
  const newIds = ready ? newAssetIds(roster.assetIds, record!.seenAssetIds) : [];
  const kind: PromptKind | null = !ready
    ? null
    : record!.status === 'skipped'
      ? 'entry'
      : newIds.length > 0 ? 'roster_changed' : null;
  const view = kind ? cardView(record!.prompt, kind, sessionCount) : null;

  // Impression + the re-offer stamp, once per league/kind per app session.
  const impressionKey = kind && view === 'full' ? `${leagueId}:${kind}:${sessionCount}` : null;
  const lastImpression = useRef<string | null>(null);
  useEffect(() => {
    if (!impressionKey || !kind || lastImpression.current === impressionKey) return;
    lastImpression.current = impressionKey;
    if (!impressionsThisSession.has(impressionKey)) {
      impressionsThisSession.add(impressionKey);
      track('prompt_shown', { surface: 'roster_setup_card' }, 'Trades');
    }
    const stamped = ladderOnShow(record?.prompt, kind, sessionCount);
    if (stamped) write(leagueId, { prompt: stamped });
  }, [impressionKey, kind, record, sessionCount, leagueId, write]);

  if (!kind || !view) return null;

  const open = () => {
    try {
      track('roster_setup_prompt_tapped', {
        league_id: leagueId,
        surface: kind === 'entry' ? 'entry_card' : 'roster_changed_card',
        new_asset_count: kind === 'roster_changed' ? newIds.length : 0,
      }, 'Trades');
    } catch { /* analytics must never block navigation */ }
    navigation.navigate(
      'RosterSetup',
      kind === 'entry'
        ? { entry: 'entry_card' }
        : { entry: 'roster_changed', filterAssetIds: newIds },
    );
  };

  const snooze = () => {
    const next = ladderOnSnooze(record?.prompt, kind, sessionCount);
    if (kind === 'roster_changed' && next.retired) {
      // Retiring "N new" acknowledges them: absorb into the snapshot so the
      // NEXT roster change prompts fresh.
      write(leagueId, {
        seenAssetIds: Array.from(new Set([...(record?.seenAssetIds ?? []), ...roster.assetIds])),
        prompt: null,
      });
    } else {
      write(leagueId, { prompt: next });
    }
  };

  const title = kind === 'entry'
    ? 'Set up your roster'
    : `${newIds.length} new on your roster`;

  if (view === 'collapsed') {
    return (
      <Pressable
        testID="trades.roster-setup-card.row"
        style={styles.row}
        onPress={open}
        accessibilityRole="button"
        accessibilityLabel={title}
      >
        <ChalkText style={styles.rowText}>{title}</ChalkText>
        <ChalkText style={styles.rowChevron}>›</ChalkText>
      </Pressable>
    );
  }

  return (
    <View style={styles.card} testID="trades.roster-setup-card">
      <ChalkText style={styles.kicker}>{kind === 'entry' ? 'Your roster' : 'Roster changed'}</ChalkText>
      <ChalkText style={styles.body}>
        {kind === 'entry'
          ? "These trades guess who you'd move. Mark who's available and who's staying. About a minute."
          : `${title}. Set them so your trades use them.`}
      </ChalkText>
      <View style={styles.actions}>
        <Pressable
          testID="trades.roster-setup-card.open"
          accessibilityRole="button"
          style={({ pressed }) => [styles.cta, pressed && { backgroundColor: ice.press }]}
          onPress={open}
        >
          <ChalkText style={styles.ctaText}>
            {kind === 'entry' ? 'Set up your roster' : 'Set them'}
          </ChalkText>
        </Pressable>
        <Pressable
          testID="trades.roster-setup-card.dismiss"
          accessibilityRole="button"
          accessibilityLabel="Not now"
          style={styles.dismiss}
          onPress={snooze}
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

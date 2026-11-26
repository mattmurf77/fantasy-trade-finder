import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';

import ChalkText from './chalkline/Text';
import { Icon } from './chalkline';
import { chalk, ink, space } from '../theme/chalkline';
import { useEntitlements } from '../state/useEntitlements';
import { useFlag } from '../state/useFeatureFlags';
import { useSession } from '../state/useSession';
import { MON } from '../copy/monetization';
import {
  buyerPass,
  coveredElsewhere,
  fill,
  leagueNameFor,
  looksUnbound,
  memberPasses,
  passDate,
  proBuyEntry,
} from '../utils/leaguePass';

// League pass rows on the existing monetization surfaces (flag
// `monetize.league_pass`, dark; lld §8, D-281). Every export renders NOTHING
// unless `monetize.league_pass` AND `monetize.paywall` are on, so with the
// flag off the paywall and Settings › Subscription are exactly today's.
//
//   LeaguePassPaywallEntry  — R30: the paywall's separate entry to the
//                             league pass screen, below the plans; never a
//                             plan row.
//   LeaguePassOtherLeagueLine — R26: a covered member, in a league their pass
//                             does not cover, is told the pass covers only
//                             the other league.
//   LeaguePassSettingsRows  — R25 / R27 / R28 in Settings › Subscription:
//                             the member's covered league and date (the buyer
//                             shown as "a leaguemate" unless named), the
//                             buyer's league and date with a Manage row, the
//                             unbound pass's choose-a-league row, and, for a
//                             Pro user who is not a buyer, the buy row
//                             (operator 2026-11-25).
//
// ZERO REQUESTS: everything here reads the entitlement answer already in
// memory (Settings' hub fires no queries). The buyer's renewal state, covered
// count, move control and name toggle need `GET /api/league-pass`, so they
// live on LeaguePassScreen's manage view, one tap away.
//
// All copy is `mon.lp.*` (copy/monetization.ts). Chalkline: no accent here
// but the chevron's chalk; the paywall keeps its one ice action.

function useLeaguePassSurfaces(): boolean {
  const lp = useFlag('monetize.league_pass');
  const paywall = useFlag('monetize.paywall');
  return lp && paywall;
}

/** R30: "Paying for your whole league? See the league pass" → LeaguePass. */
export function LeaguePassPaywallEntry({ source }: { source: string }) {
  const on = useLeaguePassSurfaces();
  const navigation = useNavigation<any>();
  if (!on) return null;
  return (
    <Pressable
      testID="paywall-league-pass-entry"
      accessibilityRole="button"
      accessibilityLabel={MON['mon.lp.entry_a11y']}
      onPress={() => navigation.navigate('LeaguePass', { source })}
      style={({ pressed }) => [styles.entry, pressed && styles.pressed]}
    >
      <ChalkText variant="bodySm" style={styles.entryText}>
        {MON['mon.lp.entry']}
      </ChalkText>
      <Icon name="chevron-right" color={chalk.dim} size={16} />
    </Pressable>
  );
}

/** R26: the line for a member covered in ANOTHER league. Nothing when they
 *  are covered here or nowhere. "Here" is the session's active league. */
export function LeaguePassOtherLeagueLine() {
  const on = useLeaguePassSurfaces();
  const passes = useEntitlements((s) => s.leaguePasses);
  const leagueId = useSession((s) => s.league?.league_id ?? null);
  const leagues = useSession((s) => s.leagues);
  if (!on) return null;
  const other = coveredElsewhere(passes, leagueId, Date.now());
  if (!other) return null;
  const name = leagueNameFor(leagues, other.league_id);
  return (
    <ChalkText variant="bodySm" style={styles.dim} testID="paywall-league-pass-other-league">
      {name ? fill(MON['mon.lp.other_league'], { league_name: name }) : MON['mon.lp.other_league.unnamed']}
    </ChalkText>
  );
}

/** Settings › Subscription (verified sessions only; SubscriptionSection's
 *  VerifiedRows mounts it once the entitlement answer has loaded). */
export function LeaguePassSettingsRows() {
  const on = useLeaguePassSurfaces();
  const navigation = useNavigation<any>();
  const pro = useEntitlements((s) => s.pro);
  const sources = useEntitlements((s) => s.sources);
  const passes = useEntitlements((s) => s.leaguePasses);
  const leagues = useSession((s) => s.leagues);
  if (!on) return null;
  const now = Date.now();
  const nameOf = (id: string) => leagueNameFor(leagues, id) ?? MON['mon.lp.unknown_league'];
  const mine = buyerPass(passes, now);
  const covered = memberPasses(passes, now);
  const unbound = looksUnbound(pro, sources, passes, now);
  // Existing Pro users (operator 2026-11-25): the paywall's entry is never
  // seen by a Pro user, so Settings offers the purchase. Shown also to a
  // Pro user a leaguemate's pass covers (they may buy for another league).
  const buy = proBuyEntry(pro, sources, passes, now);
  if (!mine && covered.length === 0 && !unbound && !buy) return null;
  const open = () => navigation.navigate('LeaguePass', { source: 'settings', mode: 'manage' });
  return (
    <View testID="settings-league-pass">
      {covered.map((p) => (
        <View key={p.league_id} style={styles.kvRow} testID={`settings-league-pass-member-${p.league_id}`}>
          <ChalkText variant="body">
            {fill(MON['mon.lp.member.line'], { league_name: nameOf(p.league_id), date: passDate(p.covered_until) ?? '' })}
          </ChalkText>
          <ChalkText variant="bodySm" style={styles.dim}>
            {fill(MON['mon.lp.member.by'], { buyer: p.buyer_display?.trim() || MON['mon.lp.member.leaguemate'] })}
          </ChalkText>
        </View>
      ))}
      {mine ? (
        <View style={styles.kvRow} testID="settings-league-pass-buyer">
          <ChalkText variant="body">{fill(MON['mon.lp.buyer.line'], { league_name: nameOf(mine.league_id) })}</ChalkText>
        </View>
      ) : null}
      {mine || unbound ? (
        <Pressable
          testID={mine ? 'settings-league-pass-manage' : 'settings-league-pass-unbound'}
          accessibilityRole="button"
          accessibilityLabel={mine ? MON['mon.lp.manage'] : MON['mon.lp.unbound.row']}
          onPress={open}
          style={({ pressed }) => [styles.linkRow, pressed && styles.pressed]}
        >
          <ChalkText variant="title" style={styles.flex}>
            {mine ? MON['mon.lp.manage'] : MON['mon.lp.unbound.row']}
          </ChalkText>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>
      ) : null}
      {buy ? (
        <Pressable
          testID="settings-league-pass-buy"
          accessibilityRole="button"
          accessibilityLabel={MON['mon.lp.pro.row_a11y']}
          onPress={() => navigation.navigate('LeaguePass', { source: 'settings' })}
          style={({ pressed }) => [styles.linkRow, pressed && styles.pressed]}
        >
          <ChalkText variant="title" style={styles.flex}>{MON['mon.lp.pro.row']}</ChalkText>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  dim: { color: chalk.dim },
  pressed: { backgroundColor: ink.ink3 },
  entry: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    paddingHorizontal: space.xs,
  },
  entryText: { color: chalk.base, textDecorationLine: 'underline' },
  kvRow: {
    gap: space.xs,
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
});

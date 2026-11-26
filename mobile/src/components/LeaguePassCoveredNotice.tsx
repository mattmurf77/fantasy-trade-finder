import React, { useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

import ChalkText from './chalkline/Text';
import { Icon } from './chalkline';
import { chalk, ice, ink, radii, space } from '../theme/chalkline';
import { useEntitlements } from '../state/useEntitlements';
import { useFlag } from '../state/useFeatureFlags';
import { useSession } from '../state/useSession';
import { MON } from '../copy/monetization';
import { coveredNoticeDue, coveredNoticeKey, fill, leagueNameFor } from '../utils/leaguePass';

// League pass R29 (flag `monetize.league_pass`, dark; D-281): an existing
// INDIVIDUAL subscriber is told ONCE, per league, that a leaguemate's pass now
// covers that league. Nothing about their plan changes, and the line says so.
//
// Mounted by TradesScreen under the new-partners banner, for the session's
// active league. Construction and storage follow NewPartnersBanner: a
// dismissible ink-2 strip with an ice tick, dismissed for good under a device
// key that carries the user id AND the league id
// (`ftf_lp_covered_notice_<user>_<league>`), so account reset keeps it
// (accountReset keeps every key that already names its user, D-280) and a
// second account on the device is told on its own. Shown once: the first
// render that shows it writes the key, so leaving the screen counts as told.
// Renders nothing with the flag off, before the key is read, or when not due
// (utils/leaguePass.coveredNoticeDue).

export default function LeaguePassCoveredNotice({ userId, leagueId }: { userId: string; leagueId: string }) {
  const flagOn = useFlag('monetize.league_pass');
  const pro = useEntitlements((s) => s.pro);
  const sources = useEntitlements((s) => s.sources);
  const passes = useEntitlements((s) => s.leaguePasses);
  const leagues = useSession((s) => s.leagues);
  const due = coveredNoticeDue(pro, sources, passes, leagueId, flagOn, Date.now());
  // undefined = still reading the key: never a one-frame flash.
  const [seen, setSeen] = useState<boolean | undefined>(undefined);
  const [dismissed, setDismissed] = useState(false);
  const key = coveredNoticeKey(userId, leagueId);

  useEffect(() => {
    setSeen(undefined);
    setDismissed(false);
    if (!due) return;
    let cancelled = false;
    AsyncStorage.getItem(key)
      .then((v) => {
        if (cancelled) return;
        const already = v === '1';
        setSeen(already);
        // Told once: showing it is the telling.
        if (!already) AsyncStorage.setItem(key, '1').catch(() => {});
      })
      .catch(() => { if (!cancelled) setSeen(true); });
    return () => { cancelled = true; };
  }, [key, due]);

  if (!due || seen !== false || dismissed) return null;
  const name = leagueNameFor(leagues, leagueId) ?? MON['mon.lp.unknown_league'];
  return (
    <View style={styles.banner} testID="league-pass.covered-notice">
      <View style={styles.tick} />
      <ChalkText variant="bodySm" style={styles.text}>
        {fill(MON['mon.lp.notice'], { league_name: name })}
      </ChalkText>
      <Pressable
        testID="league-pass.covered-notice.dismiss"
        onPress={() => setDismissed(true)}
        style={({ pressed }) => [styles.close, pressed && styles.closePressed]}
        hitSlop={10}
        accessibilityRole="button"
        accessibilityLabel={MON['mon.lp.notice.dismiss_a11y']}
      >
        <Icon name="x" size={16} color={chalk.dim} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radii.md,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
  },
  tick: { width: 3, height: 14, backgroundColor: ice.base },
  text: { flex: 1, color: chalk.base },
  close: { width: 28, height: 28, borderRadius: radii.sm, alignItems: 'center', justifyContent: 'center' },
  closePressed: { backgroundColor: ink.ink3 },
});

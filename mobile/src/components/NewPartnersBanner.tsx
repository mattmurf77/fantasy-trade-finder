import React, { useEffect, useState } from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { ink, chalk, ice, space, radii, type } from '../theme/chalkline';
import { Icon } from './chalkline';
import type { NewPartnerEntry } from '../shared/types';

// Dismissible banner shown at the top of TradesScreen when a leaguemate
// has newly unlocked. Each unique "latest partner" id only shows the
// banner once per (user, league) — dismissal key encodes the latest
// partner's user_id so a *new* unlock re-surfaces the banner.
//
// Chalkline banner construction: ink-2 surface, hairline border, ice tick,
// body-sm copy, ghost dismiss.

interface Props {
  partners: NewPartnerEntry[];
  userId: string;       // current FTF user id — keys the dismissal record
  leagueId: string;
}

function dismissKey(userId: string, leagueId: string, latestPartnerId: string) {
  return `ftf_new_partners_dismissed_${userId}_${leagueId}_${latestPartnerId}`;
}

export default function NewPartnersBanner({ partners, userId, leagueId }: Props) {
  // Tri-state: undefined = still checking AsyncStorage, true/false = resolved.
  // The undefined gate prevents a one-frame flash of the banner before we
  // confirm the user hasn't already dismissed it.
  const [dismissed, setDismissed] = useState<boolean | undefined>(undefined);

  // Sort newest-first matches the API layer's output, but be defensive in
  // case a caller passes pre-sorted-the-other-way data.
  const latest = partners[0];
  const latestPartnerId = latest?.user_id || '';

  useEffect(() => {
    if (!latestPartnerId) {
      setDismissed(true);
      return;
    }
    let cancelled = false;
    AsyncStorage.getItem(dismissKey(userId, leagueId, latestPartnerId))
      .then((v) => { if (!cancelled) setDismissed(v === '1'); })
      .catch(() => { if (!cancelled) setDismissed(false); });
    return () => { cancelled = true; };
  }, [userId, leagueId, latestPartnerId]);

  if (!latest || dismissed === undefined || dismissed === true) return null;

  const n = partners.length;
  async function handleDismiss() {
    setDismissed(true);
    try {
      await AsyncStorage.setItem(dismissKey(userId, leagueId, latestPartnerId), '1');
    } catch { /* non-fatal */ }
  }

  return (
    <View style={styles.banner}>
      <View style={styles.tick} />
      <Text style={styles.text}>
        {n} new trade partner{n === 1 ? '' : 's'} unlocked — refresh to find trades
      </Text>
      <Pressable
        onPress={handleDismiss}
        style={({ pressed }) => [styles.close, pressed && styles.closePressed]}
        hitSlop={10}
        accessibilityRole="button"
        accessibilityLabel="Dismiss new partners banner"
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
  tick: {
    width: 3,
    height: 14,
    backgroundColor: ice.base,
  },
  text: {
    flex: 1,
    ...type.bodySm,
    color: chalk.base,
  },
  close: {
    width: 28,
    height: 28,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  closePressed: { backgroundColor: ink.ink3 },
});

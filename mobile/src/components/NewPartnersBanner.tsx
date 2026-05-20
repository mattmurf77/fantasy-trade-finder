import React, { useEffect, useState } from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import type { NewPartnerEntry } from '../shared/types';

// Dismissible banner shown at the top of TradesScreen when a leaguemate
// has newly unlocked. Each unique "latest partner" id only shows the
// banner once per (user, league) — dismissal key encodes the latest
// partner's user_id so a *new* unlock re-surfaces the banner.

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
      <Text style={styles.text}>
        🎯 {n} new trade partner{n === 1 ? '' : 's'} unlocked — refresh to find trades
      </Text>
      <Pressable
        onPress={handleDismiss}
        style={({ pressed }) => [styles.close, pressed && { opacity: 0.6 }]}
        hitSlop={10}
        accessibilityRole="button"
        accessibilityLabel="Dismiss new partners banner"
      >
        <Text style={styles.closeText}>✕</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: 'rgba(34,197,94,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(34,197,94,0.45)',
  },
  text: {
    flex: 1,
    color: colors.green,
    fontSize: fontSize.sm,
    fontWeight: '700',
  },
  close: {
    paddingHorizontal: spacing.xs,
    paddingVertical: 2,
  },
  closeText: {
    color: colors.green,
    fontSize: fontSize.base,
    fontWeight: '800',
  },
});

import React from 'react';
import { View, Text, Pressable, Share, StyleSheet } from 'react-native';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { getBaseUrl } from '../api/client';

// Cold-start banner shown at the top of TradesScreen when NO league-mate
// has submitted rankings yet. In that state every card is a consensus-basis
// "fair-value idea" — the divergence engine (and mutual matching) needs at
// least one ranked counterparty. The Invite button opens the OS share sheet
// with the same referral URL format the web client builds
// (`/?league=<id>&ref=<username>` — captured by captureReferralFromUrl and
// utils/deepLinks on the receiving end).

interface Props {
  leagueId: string;
  leagueName?: string | null;
  username?: string | null;   // referrer attribution; omitted if unknown
  total: number;              // league-mates excluding the current user
}

export function buildInviteUrl(leagueId: string, username?: string | null): string {
  const params = [`league=${encodeURIComponent(leagueId)}`];
  if (username) params.push(`ref=${encodeURIComponent(username)}`);
  return `${getBaseUrl()}/?${params.join('&')}`;
}

export default function InviteLeaguematesBanner({ leagueId, leagueName, username, total }: Props) {
  async function handleInvite() {
    const url = buildInviteUrl(leagueId, username);
    const where = leagueName || 'our league';
    try {
      await Share.share({
        message: `Join me on Dynasty Trade Finder to find trades in ${where} → ${url}`,
      });
    } catch {
      /* user dismissed the sheet — nothing to do */
    }
  }

  return (
    <View style={styles.banner}>
      <View style={styles.textCol}>
        <Text style={styles.title}>
          0 of {total} league-mates have ranked
        </Text>
        <Text style={styles.body}>
          Ideas below are fair-value estimates. Real trade matches unlock when
          league-mates rank their players.
        </Text>
      </View>
      <Pressable
        onPress={handleInvite}
        style={({ pressed }) => [styles.inviteBtn, pressed && { opacity: 0.7 }]}
        accessibilityRole="button"
        accessibilityLabel="Invite league-mates"
      >
        <Text style={styles.inviteText}>Invite</Text>
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
    backgroundColor: 'rgba(79,124,255,0.10)',   // colors.accent @ 10%
    borderWidth: 1,
    borderColor: 'rgba(79,124,255,0.45)',       // colors.accent @ 45%
  },
  textCol: {
    flex: 1,
    gap: 2,
  },
  title: {
    color: colors.accent,
    fontSize: fontSize.sm,
    fontWeight: '700',
  },
  body: {
    color: colors.muted,
    fontSize: fontSize.xs,
  },
  inviteBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.accent,
  },
  inviteText: {
    color: colors.text,
    fontSize: fontSize.sm,
    fontWeight: '800',
  },
});

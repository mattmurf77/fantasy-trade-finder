import React from 'react';
import { View, Text, Pressable, Share, StyleSheet } from 'react-native';

import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';
import { getBaseUrl } from '../api/client';
import { track } from '../api/events';
import { useFlag } from '../state/useFeatureFlags';

// Cold-start banner shown at the top of TradesScreen when NO league-mate
// has submitted rankings yet. In that state every card is a consensus-basis
// "fair-value idea" — the divergence engine (and mutual matching) needs at
// least one ranked counterparty. The Invite button opens the OS share sheet
// with the same referral URL format the web client builds
// (`/?league=<id>&ref=<username>` — captured by captureReferralFromUrl and
// utils/deepLinks on the receiving end).
//
// Chalkline banner construction: ink-2 surface, hairline border, ice tick,
// body-sm copy.

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
  // S7 PRD-01 (growth.share_landing): the invite URL already IS the landing
  // page with ?ref= attribution preserved (verified against
  // utils/deepLinks + web captureReferralFromUrl) — no URL change needed;
  // the flag adds the share→open funnel event only.
  const shareLandingOn = useFlag('growth.share_landing');
  async function handleInvite() {
    const url = buildInviteUrl(leagueId, username);
    const where = leagueName || 'our league';
    try {
      const res = await Share.share({
        message: `Join me on Dynasty Trade Finder to find trades in ${where} → ${url}`,
      });
      if (shareLandingOn && res.action !== Share.dismissedAction) {
        track('invite_shared', { league_id: leagueId }, 'Trades');
      }
    } catch {
      /* user dismissed the sheet — nothing to do */
    }
  }

  return (
    <View style={styles.banner}>
      <View style={styles.tick} />
      <View style={styles.textCol}>
        <Text style={styles.title}>
          0 of {total} league-mates have ranked
        </Text>
        <Text style={type.bodySm}>
          Ideas below are fair-value estimates. Real trade matches unlock when
          league-mates rank their players.
        </Text>
      </View>
      {/* Composed secondary button: the chalkline Button has no
          accessibilityLabel passthrough. */}
      <Pressable
        onPress={handleInvite}
        style={({ pressed }) => [styles.inviteBtn, pressed && styles.inviteBtnPressed]}
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
    alignSelf: 'flex-start',
    marginTop: 2,
  },
  textCol: {
    flex: 1,
    gap: 2,
  },
  title: {
    ...type.bodySm,
    fontFamily: fonts.uiSemi,
    color: chalk.base,
  },
  inviteBtn: {
    minHeight: 36,
    minWidth: 44,
    paddingHorizontal: space.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
  },
  inviteBtnPressed: { backgroundColor: ink.ink3 },
  inviteText: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
    color: chalk.base,
  },
});

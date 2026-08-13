import React from 'react';
import { View, Text, Pressable, Share, StyleSheet } from 'react-native';

import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';
import { getBaseUrl } from '../api/client';
import { track } from '../api/events';
import { useFeatureFlags } from '../state/useFeatureFlags';

// Cold-start banner shown at the top of TradesScreen when NO league-mate
// has submitted rankings yet. In that state every card is a consensus-basis
// "fair-value idea" — the divergence engine (and mutual matching) needs at
// least one ranked counterparty. The Invite button delegates to shareInvite
// below — the one share path behind every invite surface in the app.
//
// TWO accepted URL formats, and BOTH are parsed forever:
//   • `/?league=<id>&ref=<username>` — every link ever shared. The web side
//     captures it in captureReferralFromUrl; the mobile side captures it in
//     utils/deepLinks' `?league=` reader, which P0-3 ADDED — before that fix
//     mobile dropped the league on the floor on every invite ever sent.
//   • `/app/league/join/<id>?ref=<username>` — the P0-3 path form, emitted
//     only while `growth.invite_join_link` is on.
// The legacy form is never retired: links already sitting in Sleeper chats
// have to keep working.
//
// Chalkline banner construction: ink-2 surface, hairline border, ice tick,
// body-sm copy.

interface Props {
  leagueId: string;
  leagueName?: string | null;
  username?: string | null;   // referrer attribution; omitted if unknown
  total: number;              // league-mates excluding the current user
}

/** The invite URL. Two accepted formats, and BOTH are parsed forever:
 *
 *   flag OFF (default) — <base>/?league=<id>&ref=<u>      (every link ever shared)
 *   flag ON            — <base>/app/league/join/<id>?ref=<u>
 *
 * The flag is read IMPERATIVELY, inside this function, so both call sites
 * (this banner's handleInvite, and LeagueScreen's inviteLeaguemates) stay
 * byte-identical one-liners and cannot drift into emitting different formats.
 * This is a callback-time read, never a render-time one — the same
 * useFeatureFlags.getState() idiom as ratingPrompt.ts and TabNav.tsx. Do NOT
 * convert it to a useFlag() hook: this is a module-level pure function called
 * from handlers, not a component.
 *
 * `=== true` explicitly, because the fail-safe direction matters: an
 * unhydrated flag map must emit the LEGACY URL. A wrong `false` costs
 * nothing; a wrong `true` before the AASA claim has propagated through
 * Apple's CDN sends every invite to Safari.
 *
 * `ref` stays optional — an unknown username omits it, which is why AASA
 * must match `league` on its own (FB #239).
 */
export function buildInviteUrl(leagueId: string, username?: string | null): string {
  const base = getBaseUrl();
  const ref = username ? `?ref=${encodeURIComponent(username)}` : '';
  if (useFeatureFlags.getState().flags['growth.invite_join_link'] === true) {
    return `${base}/app/league/join/${encodeURIComponent(leagueId)}${ref}`;
  }
  const params = [`league=${encodeURIComponent(leagueId)}`];
  if (username) params.push(`ref=${encodeURIComponent(username)}`);
  return `${base}/?${params.join('&')}`;
}

/** Where an invite was raised from. CLOSED SET — these four values are the
 *  `surface` property's registered domain in the analytics taxonomy, so a
 *  new surface needs a taxonomy change, not just a new string here. */
export type InviteSurface =
  | 'league_home'      // the promoted InviteLeaguematesCard, and League Home's inline link
  | 'matches_empty'    // the mutual-empty state's invite block
  | 'trades_banner'    // this banner
  | 'members_overlay'  // the members overlay's footer action
  | 'notif_empty';     // the bell sheet's empty state (GD-1)

export interface ShareInviteArgs {
  leagueId:   string;
  leagueName?: string | null;
  username?:  string | null;   // referrer attribution; omitted if unknown
  surface:    InviteSurface;
  /** int | null. `null` means HONESTLY UNKNOWN — never substitute 0. The
   *  banner has no join counts at all, and a summary that hasn't landed is
   *  not the same fact as "everyone joined". */
  notJoined:  number | null;
  totalMates: number | null;
  /** The LEAGUE platform (sleeper|espn|mfl|fleaflicker|unknown), NEVER the
   *  device platform — that is a server-derived column on user_events, and
   *  conflating the two is the NULL-`platform` incident. */
  platform:   string;
  /** track()'s third argument: the route name. */
  screen:     string;
}

/**
 * THE invite share path. Every invite emission in the app goes through this
 * one function, so four surfaces cannot drift into shipping four different
 * URLs, four different messages, or four different event shapes.
 *
 * It lives beside buildInviteUrl rather than in utils/ on purpose: the
 * banner already owns the URL builder, and putting the share path anywhere
 * else would create a require cycle (util → banner → util) the moment this
 * banner delegated to it.
 *
 * Order of operations is load-bearing. `invite_cta_tapped` fires BEFORE the
 * OS sheet opens, so `invite_cta_tapped − invite_shared` is the share-sheet
 * abandon rate. Firing it afterwards would make the two events
 * tautologically equal and hide that funnel step entirely.
 *
 * `buildInviteUrl` is called AFTER the tap event so a throw inside it (it
 * reads a feature flag) can never swallow the tap.
 *
 * The `growth.share_landing` conjunct that used to gate `invite_shared` is
 * deliberately gone (PRD OG-9(a)). The flag key, its default in
 * config/features.json, and every other read of it are untouched — this
 * removes one READ, so that one flag-off configuration can no longer
 * silently blind the invite funnel.
 */
export async function shareInvite(args: ShareInviteArgs): Promise<void> {
  if (!args.leagueId) return;
  const props = {
    surface:     args.surface,
    not_joined:  args.notJoined,
    total_mates: args.totalMates,
    platform:    args.platform,
  };
  track('invite_cta_tapped', props, args.screen);
  const url = buildInviteUrl(args.leagueId, args.username);
  const where = args.leagueName || 'our league';
  try {
    const res = await Share.share({
      message: `Join me on Dynasty Trade Finder to find trades in ${where} → ${url}`,
    });
    if (res.action !== Share.dismissedAction) {
      track('invite_shared', { league_id: args.leagueId, ...props }, args.screen);
    }
  } catch {
    /* user dismissed the sheet — nothing to do */
  }
}

export default function InviteLeaguematesBanner({ leagueId, leagueName, username, total }: Props) {
  async function handleInvite() {
    // notJoined/totalMates are null, not 0: this banner's props carry the
    // league-mate TOTAL but no join counts, and 0 would be a lie.
    await shareInvite({
      leagueId,
      leagueName,
      username,
      surface:    'trades_banner',
      notJoined:  null,
      totalMates: null,
      platform:   'unknown',   // no league platform is in scope at this mount
      screen:     'Trades',
    });
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

import React, { useEffect, useRef, useState } from 'react';
import { View, Text, ActivityIndicator, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ink, chalk, ice, space, type } from '../theme/chalkline';
import { Button } from '../components/chalkline';
import { useSession } from '../state/useSession';
import { track } from '../api/events';

// ── P0-3 — the invite JOIN interstitial ──────────────────────────────────
// Destination of `<base>/app/league/join/<leagueId>?ref=<u>` (the format
// `buildInviteUrl` emits while `growth.invite_join_link` is on). The LEGACY
// `<base>/?league=<id>&ref=<u>` form never reaches here — it has no path, so
// utils/deepLinks captures it directly into the same persisted intent. One
// owner per URL form; both end in the same place.
//
// This screen decides and leaves. It NEVER pins a league itself: every pin
// in the app runs through LeaguePickerScreen's auto-pin effect, which calls
// pickLeague({auto:true}) → setLeague(), and setLeague() is what overwrites
// the `no_league` sentinel P0-5's relaunch predicate keys on. A second pin
// path here would be the likeliest place to forget that.
//
// It also NEVER looks up invite meta — see lld-p0-3 §2.0. Its non-member leg
// runs with league ids that have no hermetic cassette, and one lookup here
// would increment `vcr_misses` and fail the whole sim run. SignInScreen is
// the app's single invite-meta call site; keep it that way.

interface Props {
  // react-navigation props; only params + replace are used.
  route: { params?: { leagueId?: string; ref?: string } };
  navigation: {
    replace: (name: string, params?: object) => void;
  };
}

export default function LeagueJoinScreen({ route, navigation }: Props) {
  const leagueId = (route?.params?.leagueId || '').trim();
  const inviteRef = (route?.params?.ref || '').trim();

  // Read for RENDER only. The decision below reads getState() instead — it
  // is a one-shot decision, not a subscription.
  const cachedName = useSession(
    (s) => s.invitedLeagueName ?? s.leagues.find((l) => l.league_id === leagueId)?.name ?? null,
  );

  // Honest failure state. Reached only when the link carries no league id or
  // the decision throws — never a bare spinner that spins forever.
  const [failed, setFailed] = useState(!leagueId);

  const decided = useRef(false);
  useEffect(() => {
    if (decided.current) return;
    decided.current = true;
    if (!leagueId) return;

    const st = useSession.getState();

    // 1. Own the path form's intent (utils/deepLinks deliberately skips it).
    void st.setInvitedLeague(leagueId);
    // 2. Belt-and-braces: handleDeepLink normally captured `?ref=` already,
    //    and setInvitedBy is last-write-wins.
    if (inviteRef) st.setInvitedBy(inviteRef);

    // 3. Classify. The four cases below are exactly the four `auth_state`
    //    values the taxonomy registers.
    const isMember = st.leagues.some((l) => l.league_id === leagueId);
    // A demo session is treated as a non-member and — crucially — the intent
    // is left INTACT: a demo user must never be pinned into a real league,
    // and the invite has to survive for their real sign-in.
    const authState = !st.user
      ? 'signed_out'
      : st.user.account_only
      ? 'account_only'
      : !st.isDemo && isMember
      ? 'authed_member'
      : 'authed_non_member';

    track('invite_link_opened', {
      league_id:  leagueId,
      has_ref:    !!inviteRef,
      format:     'path',
      auth_state: authState,
    }, 'LeagueJoin');

    // 4. Decide and leave. `replace`, never `navigate`: a spent invite link
    //    must not leave a back edge.
    try {
      if (authState === 'signed_out') {
        // The intent is already persisted, so SignIn's banner names the
        // inviter and the post-auth journey picks the league up.
        navigation.replace('SignIn');
      } else if (authState === 'account_only') {
        // P0-5's companion state, carrying inviter + league context. NEVER a
        // pin: an acct_ user has no Sleeper roster in that league.
        navigation.replace('LeaguePicker', {
          ...(st.invitedBy ? { invitedBy: st.invitedBy } : {}),
          ...(st.invitedLeagueName ? { invitedLeagueName: st.invitedLeagueName } : {}),
        });
      } else if (authState === 'authed_member') {
        // The picker's auto-pin effect owns every pin, so there is exactly
        // one pin implementation. It paints for a frame at most.
        navigation.replace('LeaguePicker', { autoPinLeagueId: leagueId });
      } else {
        // Not (apparently) a member. `leagues` may be a stale cache, so the
        // picker — which refreshes and re-derives membership — gets the
        // decision. `inviteNotice` is a hint, not a command.
        navigation.replace('LeaguePicker', { inviteNotice: true });
      }
    } catch {
      setFailed(true);
    }
  }, [leagueId, inviteRef, navigation]);

  if (failed) {
    return (
      <SafeAreaView testID="leaguejoin.root" style={styles.root}>
        <View style={styles.centered}>
          <Text testID="leaguejoin.not-member" style={styles.body}>
            We couldn't open that invite. Pick a league to keep going.
          </Text>
          <Button
            testID="leaguejoin.cta"
            label="Choose a league"
            onPress={() => navigation.replace('LeaguePicker')}
          />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView testID="leaguejoin.root" style={styles.root}>
      <View style={styles.centered}>
        <Text testID="leaguejoin.title" style={styles.title}>
          Joining {cachedName || 'your league'}…
        </Text>
        <ActivityIndicator color={ice.base} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.md,
    paddingHorizontal: space.lg,
  },
  title: { ...type.heading, textAlign: 'center' },
  body: { ...type.bodySm, color: chalk.dim, textAlign: 'center' },
});

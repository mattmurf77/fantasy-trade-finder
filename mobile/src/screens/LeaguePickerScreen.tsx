import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  Pressable,
  ActivityIndicator,
  StyleSheet,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import { ink, chalk, ice, semantic, space, type } from '../theme/chalkline';
import { Badge, Button, Icon } from '../components/chalkline';
import { useSession, inviteIntentAgeMs } from '../state/useSession';
import { useFlag, onboardingEnabled } from '../state/useFeatureFlags';
import { requestGuideStep, advanceGuideIfActive, guidedAvatarActive } from '../state/useGuide';
import { S as GUIDE } from '../components/analystScript';
import { getLeagues } from '../api/sleeper';
import { getEspnLeagues } from '../api/espn';
import { getPlatformLeagues, LinkPlatform } from '../api/platformLink';
import {
  buildSessionInitBody,
  submitSessionInit,
  type LinkSleeperResponse,
  type SessionInitSeed,
} from '../api/auth';
import { seedLeagueSessionCaches } from '../state/queryClient';
import { maybePregenTrades } from '../api/tradePregen';
import { track } from '../api/events';
import { ApiError } from '../api/client';
import EspnLinkSheet from '../components/EspnLinkSheet';
import RankChipBadge from '../components/RankChipBadge';
import PlatformLinkSheet from '../components/PlatformLinkSheet';
import LinkSleeperSheet from '../components/LinkSleeperSheet';
import type { LeagueSummary } from '../shared/types';

// Platform → league-list badge text (ESPN keeps 'ESPN'; MFL/Fleaflicker are
// the new short badges — cross-client-invariants platform-badge rule).
const PLATFORM_BADGE: Record<string, string> = {
  espn: 'ESPN',
  mfl: 'MFL',
  fleaflicker: 'FLEA',
};

interface Props {
  onLeaguePicked: () => void;
  onSignOut: () => void;
  /** #130 — open the ESPN link sheet on mount (Settings CTA). Honored only
   *  while the `espn.link` flag is on. */
  autoOpenEspnLink?: boolean;
  /** Landing platform options — the MFL twin of `autoOpenEspnLink`: the
   *  entry page's MFL chip rode Apple sign-in here, open the MFL link sheet
   *  on arrival. Honored only while the `mfl.link` flag is on. */
  autoOpenMflLink?: boolean;
  /** P0-3 (commit 12) — invite context for an account-only arrival via
   *  LeagueJoin. Optional and unset in wave 1; when present the companion
   *  state names the inviter and league instead of its generic copy. Never
   *  used to PIN a league: an acct_ user has no Sleeper roster in an invited
   *  Sleeper league (see hld.md §1.3). */
  invitedBy?: string | null;
  invitedLeagueName?: string | null;
  /** P0-3 — case-B hint from LeagueJoinScreen. The auto-pin effect below
   *  re-derives membership from `cached`, so this is an optimization, not a
   *  command. */
  autoPinLeagueId?: string;
  /** P0-3 — case-C hint: render the invite notice row even once the store's
   *  intent has been consumed. */
  inviteNotice?: boolean;
}

// Show user's leagues → tap one → run sessionInit against it → done.
// Matches the web app's selectLeague flow but without the overlay modals.
export default function LeaguePickerScreen({
  onLeaguePicked,
  onSignOut,
  autoOpenEspnLink,
  autoOpenMflLink,
  invitedBy,
  invitedLeagueName,
  autoPinLeagueId,
  inviteNotice,
}: Props) {
  // #266 — needed for the transition-settled auto-open below. Typed loose
  // like the rest of the screens; only addListener('transitionEnd') is used.
  const navigation = useNavigation<any>();
  const user = useSession((s) => s.user);
  const verification = useSession((s) => s.verification);
  const canVerifySleeper = !!user && !user.account_only && !user.user_id.startsWith('demo_user_') && !verification?.session_verified;
  const cached = useSession((s) => s.leagues);
  // P0-3 — the persisted invite intent. SUBSCRIBED (not getState) because the
  // notice row and the companion copy render from it; the auto-pin effect
  // below still reads getState() at decision time.
  const invitedLeagueId = useSession((s) => s.invitedLeagueId);
  const storedInviteName = useSession((s) => s.invitedLeagueName);
  const storedInvitedBy = useSession((s) => s.invitedBy);
  const setLeagues = useSession((s) => s.setLeagues);
  const setLeague = useSession((s) => s.setLeague);
  // P0-5 — the Sleeper-identity link (companion state) re-keys the session.
  const setUser = useSession((s) => s.setUser);
  const queryClient = useQueryClient();

  const [loading, setLoading] = useState(cached.length === 0);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slowLoad, setSlowLoad] = useState(false);
  // League linking (read-only import). Each platform gates on its own flag.
  const espnEnabled = useFlag('espn.link');
  const mflEnabled = useFlag('mfl.link');
  const fleaflickerEnabled = useFlag('fleaflicker.link');
  // P0-5 — the Sleeper *identity* link. Gated on the same flag that must be
  // on for an account-only session to exist at all, so the Sleeper button is
  // gated symmetrically with the three platform buttons.
  const sleeperLinkEnabled = useFlag('auth.accounts');
  const [espnOpen, setEspnOpen] = useState(false);
  // Which zero-auth platform sheet is open (MFL / Fleaflicker), if any.
  const [platformOpen, setPlatformOpen] = useState<LinkPlatform | null>(null);
  const [sleeperOpen, setSleeperOpen] = useState(false);

  // P0-5 — the companion state: a session-holder with no league to pick and
  // no Sleeper identity to look one up with. Detected from DATA (account_only
  // + an empty list), not from a navigation param, so it is equally correct
  // on a first sign-in, a cold relaunch, and an arrival from Settings.
  //
  // `canLink` is a deliberate floor: with every link flag off the companion
  // state would be a heading, a sentence and nothing to press, so the screen
  // falls back to today's empty sentence instead — which is also what keeps
  // "the existing flags are the per-platform rollback lever" honest.
  const canLink = sleeperLinkEnabled || espnEnabled || mflEnabled || fleaflickerEnabled;
  const accountOnlyEmpty = !!user?.account_only && cached.length === 0 && canLink;

  // #130 — Settings' ESPN CTA lands here with `espnLink: true`; open the
  // sheet once the flag confirms. Effect (not initial state) because the
  // flag store may hydrate after mount.
  //
  // #266 — the open is DEFERRED until the arrival transition has settled.
  // The Settings path dismisses the Settings native modal and pushes this
  // screen in the same tick (`account.settings_v2`'s coalesced
  // goBack+navigate), so a synchronous mount-time setEspnOpen(true) asked
  // iOS to present an RN <Modal> while that dismissal/push was still
  // animating. The presentation wedges (the modal attaches to the
  // dismissing controller and never appears), and because `espnOpen` is
  // already true the footer "Link an ESPN league" button's setEspnOpen(true)
  // is a state no-op — while the half-presented Modal host also blocks the
  // sibling PlatformLinkSheet Modal from presenting (iOS won't stack
  // sibling RN Modals), killing "Link an MFL league" too. Waiting for the
  // screen's own transitionEnd presents against a settled hierarchy; the
  // timeout is the fallback for arrivals that animate nothing (late flag
  // hydration re-run, cold-start deep link), where opening is already safe.
  useEffect(() => {
    if (!autoOpenEspnLink || !espnEnabled) return;
    let opened = false;
    const open = () => {
      if (opened) return;
      opened = true;
      setEspnOpen(true);
    };
    const unsub = navigation.addListener(
      'transitionEnd',
      (e: { data?: { closing?: boolean } }) => {
        if (e?.data?.closing) return; // leaving, not arriving
        open();
      },
    );
    const fallback = setTimeout(open, 800);
    return () => {
      unsub();
      clearTimeout(fallback);
    };
  }, [autoOpenEspnLink, espnEnabled, navigation]);

  // Landing platform options — the MFL twin of the #130 auto-open above,
  // with the same #266 transition-settled deferral (PlatformLinkSheet is a
  // sibling RN <Modal> and wedges the same way if presented mid-transition).
  useEffect(() => {
    if (!autoOpenMflLink || !mflEnabled) return;
    let opened = false;
    const open = () => {
      if (opened) return;
      opened = true;
      setPlatformOpen('mfl');
    };
    const unsub = navigation.addListener(
      'transitionEnd',
      (e: { data?: { closing?: boolean } }) => {
        if (e?.data?.closing) return; // leaving, not arriving
        open();
      },
    );
    const fallback = setTimeout(open, 800);
    return () => {
      unsub();
      clearTimeout(fallback);
    };
  }, [autoOpenMflLink, mflEnabled, navigation]);

  // Onboarding item 6 (F9): exactly one league → skip the picker (free step
  // removal). Once-only per mount; never when the user came here to link
  // ESPN. Failure falls back to this screen's existing inline error +
  // retry — the single league row on screen names the league.
  // Guided tour S1 — only for pickers with a real choice (multi-league);
  // auto-skip users never mount long enough to need it.
  useEffect(() => {
    if (!guidedAvatarActive() || loading || cached.length < 2) return;
    requestGuideStep(GUIDE.s1_1());
  }, [loading, cached.length]);

  const autoSkipTried = useRef(false);
  useEffect(() => {
    if (autoSkipTried.current) return;
    if (loading || error || selectingId || autoOpenEspnLink || autoOpenMflLink) return;
    if (cached.length !== 1) return;
    if (!onboardingEnabled('onboarding.league_autoskip')) return;
    autoSkipTried.current = true;
    void pickLeague(cached[0], { auto: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cached, loading, error, selectingId, autoOpenEspnLink, autoOpenMflLink]);

  // P0-3 — pin the invited league as soon as it appears in the list.
  //
  // Mirrors web one-for-one (web/js/app.js: read localStorage
  // ftf_invited_league, findIndex over the loaded leagues, remove the key =
  // consume, selectLeague). Keyed on `cached`, NOT on mount, and that is the
  // whole trick: an account-only invitee (P0-5) arrives with zero leagues,
  // links Sleeper/ESPN/MFL from the companion state, and the list
  // repopulates — this effect re-fires and pins, with neither fix knowing
  // about the other.
  //
  // pickLeague({auto:true}) is the ONLY pin path: it calls setLeague(), which
  // OVERWRITES the `no_league` sentinel, so P0-5's relaunch predicate sends
  // the user to Main on every subsequent cold start instead of bouncing them
  // back here forever. CONSUME BEFORE PIN — pickLeague navigates away, and
  // code after a navigation is a coin flip.
  //
  // An account_only session never reaches the pin: it has no Sleeper roster
  // in the invited league, so its list stays empty and `find` returns
  // undefined. That is the companion state's job, not this effect's.
  const invitePinTried = useRef(false);
  useEffect(() => {
    if (invitePinTried.current) return;
    if (loading || error || selectingId) return;
    const wanted = useSession.getState().invitedLeagueId ?? autoPinLeagueId ?? null;
    if (!wanted) return;
    const lg = cached.find((x) => x.league_id === wanted);
    if (!lg) return;                       // not (yet) a member — notice row below
    invitePinTried.current = true;
    void (async () => {
      const ageMs = inviteIntentAgeMs();
      track('invite_league_pinned', {
        league_id: wanted,
        source:    'picker_autopin',
        ...(ageMs === null ? {} : { ms_since_open: ageMs }),
      }, 'LeaguePicker');
      await useSession.getState().consumeInvitedLeague();   // consume ON PIN
      await pickLeague(lg, { auto: true });
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cached, loading, error, selectingId, autoPinLeagueId]);

  // P0-3 — the honest notice: an invite exists, the list has loaded, and the
  // invited league is not in it. NOT a dead end and NOT a spinner — the real
  // list stays usable underneath. The intent is deliberately NOT consumed
  // here: the user may join on Sleeper and come back inside the 14-day TTL,
  // and the effect above will fire on the refreshed list.
  const wantedInviteId = invitedLeagueId ?? autoPinLeagueId ?? null;
  const listReady = !loading && !error && cached.length > 0;
  const showInviteNotice =
    listReady &&
    ((!!wantedInviteId && !cached.some((l) => l.league_id === wantedInviteId)) ||
      inviteNotice === true);

  // Once per MOUNT, not once per render.
  const inviteFailReported = useRef(false);
  useEffect(() => {
    if (!showInviteNotice || inviteFailReported.current) return;
    inviteFailReported.current = true;
    track('invite_pin_failed', {
      ...(wantedInviteId ? { league_id: wantedInviteId } : {}),
      reason: 'not_member',
    }, 'LeaguePicker');
  }, [showInviteNotice, wantedInviteId]);

  // P0-3 case D — invite context for P0-5's companion state, from TWO
  // sources: route params win (a link tapped THIS launch), the persisted
  // intent is the fallback (signed in with Apple three launches ago, only
  // now linking a platform).
  const inviteName = invitedLeagueName ?? storedInviteName ?? null;
  const inviteBy = invitedBy ?? storedInvitedBy ?? null;

  // Render free-tier cold starts run 30–60s. Hold the friendly default for
  // the first 4s so warm requests never show the alarming "waking up" copy.
  useEffect(() => {
    if (!loading) {
      setSlowLoad(false);
      return;
    }
    const t = setTimeout(() => setSlowLoad(true), 4000);
    return () => clearTimeout(t);
  }, [loading]);

  useEffect(() => {
    if (!user) return;
    if (cached.length > 0) {
      setLoading(false);
      return;
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id]);

  async function refresh() {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      // P0-5 — NEVER ask Sleeper about a synthetic id. An account-only user's
      // user_id is `acct_<account_id>`; GET /api/sleeper/leagues/acct_… proxies
      // that key to Sleeper, which returns null live (→ the "No 2026 NFL
      // leagues found" sentence) and raises a fixture-miss 599 under the VCR
      // harness (→ 503 sleeper_unavailable → "Couldn't reach Sleeper"). Both
      // blame Sleeper or the user for a situation that is neither. The platform
      // merges below are session-scoped and MUST still run: an account-only
      // user who already linked ESPN from Settings has leagues to list.
      const lgs = user.account_only ? [] : await getLeagues(user.user_id);
      // Merge in imported non-Sleeper leagues (each flag-gated; backend 404s
      // dark). Best-effort — a hiccup on one platform must not hide the rest.
      const merged: LeagueSummary[] = [...lgs];
      const seen = new Set(lgs.map((lg) => lg.league_id));
      const addAll = (rows: LeagueSummary[]) => {
        for (const row of rows) {
          if (!seen.has(row.league_id)) {
            merged.push(row);
            seen.add(row.league_id);
          }
        }
      };
      if (espnEnabled) {
        try {
          const espn = await getEspnLeagues();
          addAll(espn.map((lg) => ({
            league_id: lg.league_id,
            name: lg.name || `ESPN league ${lg.league_id}`,
            total_rosters: lg.total_rosters ?? undefined,
            platform: 'espn',
          })));
        } catch {
          /* non-fatal */
        }
      }
      for (const p of ['mfl', 'fleaflicker'] as LinkPlatform[]) {
        if (p === 'mfl' ? !mflEnabled : !fleaflickerEnabled) continue;
        try {
          const rows = await getPlatformLeagues(p);
          addAll(rows.map((lg) => ({
            league_id: lg.league_id,
            name: lg.name || `${PLATFORM_BADGE[p]} league ${lg.league_id}`,
            total_rosters: lg.total_rosters ?? undefined,
            platform: p,
          })));
        } catch {
          /* non-fatal */
        }
      }
      setLeagues(merged);
    } catch (e: any) {
      setError(e?.message || 'Could not load leagues');
    } finally {
      setLoading(false);
    }
  }

  // Post-import handler (any platform): put the league in the cached list
  // first (buildSessionInitBody detects imported leagues via that cache's
  // `platform` field), then run the normal pick flow.
  async function onLeagueLinked(lg: {
    league_id: string; name: string; total_rosters: number; platform?: string;
  }) {
    setEspnOpen(false);
    setPlatformOpen(null);
    const summary: LeagueSummary = {
      league_id: lg.league_id,
      name: lg.name,
      total_rosters: lg.total_rosters,
      platform: lg.platform || 'espn',   // EspnLinkSheet omits platform
    };
    const merged = [
      ...cached.filter((x) => x.league_id !== lg.league_id),
      summary,
    ];
    await setLeagues(merged);
    await pickLeague(summary);
  }

  // The Sleeper *identity* link (not league linking): the session stops being
  // account-only and becomes keyed to a real Sleeper user. Drop the sentinel
  // league and let the existing [user?.user_id] effect re-run refresh() — with
  // account_only now falsy, the Sleeper fetch happens and the real list paints
  // IN PLACE. No navigation: the user asked for their leagues and this screen
  // is where leagues live. (Settings' copy of this handler navigates because
  // it is not the picker; see LinkSleeperSheet's header.)
  async function onSleeperLinked(res: LinkSleeperResponse) {
    setSleeperOpen(false);
    await setUser({
      user_id:      res.sleeper_user_id,
      username:     res.username,
      display_name: res.display_name || res.username,
      avatar_id:    res.avatar ?? null,
    });
    await setLeague(null);
    queryClient.invalidateQueries({ queryKey: ['account'] });
  }

  async function pickLeague(lg: LeagueSummary, opts?: { auto?: boolean }) {
    if (!user || selectingId) return;
    if (!opts?.auto) advanceGuideIfActive('s1.1');
    setSelectingId(lg.league_id);
    setError(null);
    track(
      'league_selected',
      {
        league_index: cached.findIndex((x) => x.league_id === lg.league_id),
        league_count: cached.length,
        auto: !!opts?.auto,
        // F12 segment tag: redraft users are excluded from activation
        // denominators (dynasty values are wrong for them by construction).
        league_type:
          lg.settings_type === 0
            ? 'redraft'
            : lg.settings_type === 1
              ? 'keeper'
              : lg.settings_type === 2
                ? 'dynasty'
                : 'unknown',
      },
      'LeaguePicker',
    );
    try {
      // Gather the roster preview, then initialize before entering the tabs.
      //
      // Fetch rosters + users from Sleeper and build the
      // session_init payload. This is the "data-gather" leg — fast enough
      // that we block on it so we can surface Sleeper errors inline.
      // `seed` collects the rosters + users phase 1 fetches, so the tabs we
      // are about to navigate into read them from cache instead of asking
      // Sleeper for the same two payloads again (state/queryClient).
      const seed: SessionInitSeed = {};
      const body = await buildSessionInitBody(user, { league_id: lg.league_id, name: lg.name }, seed);
      seedLeagueSessionCaches(lg.league_id, seed);

      // Keep the picker reachable until the server accepts identity and
      // membership. A rejected init must not strand the caller in Main.
      await submitSessionInit(body);
      await setLeague({ league_id: lg.league_id, league_name: lg.name });
      onLeaguePicked();
      maybePregenTrades(lg.league_id);
    } catch (e: any) {
      const code = e instanceof ApiError ? (e.body as any)?.error : null;
      if (code === 'verification_required') {
        const previous = useSession.getState().verification;
        useSession.getState().setVerification({
          session_verified: false,
          user_verified: previous?.user_verified ?? false,
          verified_via: previous?.verified_via ?? null,
          enforced: true,
        });
      }
      setError(code === 'verification_required'
        ? 'Verify your Sleeper account, then choose your league again.'
        : e?.message || 'Failed to import this league');
      setSelectingId(null);
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title} accessibilityRole="header">
            {accountOnlyEmpty ? 'Connect a League' : 'Choose a League'}
          </Text>
          <Text style={styles.sub}>Leagues for {user?.display_name || '…'}</Text>
        </View>
        <Button label="Sign out" variant="ghost" compact onPress={onSignOut} />
      </View>

      {canVerifySleeper && (
        <Button testID="leagues.verify-sleeper" label="Verify Sleeper account"
          variant="secondary" disabled={!!selectingId}
          onPress={() => {
            setError(null);
            navigation.navigate('SleeperConnect');
          }} />
      )}

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator color={ice.base} />
          <Text style={styles.loadingText}>
            {slowLoad
              ? 'Waking up server — first request after a quiet period can take 30s.'
              : 'Loading your leagues…'}
          </Text>
        </View>
      ) : accountOnlyEmpty ? (
        // P0-5 — the companion state. Sits ABOVE `error` deliberately: after
        // the Sleeper skip in refresh() the only error reachable here is a
        // local persistence failure whose "Try again" would retry nothing the
        // user needs, and these three buttons are the screen's only
        // actionable content. It sits BELOW `loading` so it never flashes
        // before the platform merges resolve.
        <View style={styles.centered}>
          <Text testID="leagues.empty.body" style={styles.emptyBody}>
            {inviteBy
              ? `@${inviteBy} invited you to ${inviteName || 'their league'}. ` +
                'Connect Sleeper, ESPN or MFL to join.'
              : 'Connect Sleeper, ESPN or MFL to see your leagues.'}
          </Text>
          {sleeperLinkEnabled ? (
            <Button
              testID="leagues.empty.link-sleeper"
              label="Connect Sleeper"
              onPress={() => setSleeperOpen(true)}
            />
          ) : null}
          {espnEnabled ? (
            <Button
              testID="leagues.empty.link-espn"
              label="Connect ESPN"
              variant="secondary"
              onPress={() => setEspnOpen(true)}
            />
          ) : null}
          {mflEnabled ? (
            <Button
              testID="leagues.empty.link-mfl"
              label="Connect MFL"
              variant="secondary"
              onPress={() => setPlatformOpen('mfl')}
            />
          ) : null}
          {fleaflickerEnabled ? (
            <Button
              testID="leagues.empty.link-fleaflicker"
              label="Connect Fleaflicker"
              variant="secondary"
              onPress={() => setPlatformOpen('fleaflicker')}
            />
          ) : null}
        </View>
      ) : error ? (
        <View style={styles.centered}>
          <Text style={styles.error}>{error}</Text>
          <Button label="Try again" variant="secondary" compact onPress={refresh} />
        </View>
      ) : cached.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.error}>
            No 2026 NFL leagues found for this account.
          </Text>
        </View>
      ) : (
        <>
        {/* P0-3 — the invite notice. ABOVE the list, INSIDE this branch: it
            must never leak into the `cached.length === 0` branch, whose
            literal "No 2026 NFL leagues found for this account." sentence is
            asserted verbatim by capture/leagues@fresh.yaml.

            The copy is platform-NEUTRAL by necessity: an invite link carries
            only a league id, so at this point we do not know which platform
            the league lives on. Naming Sleeper here (as this did until
            2026-08-12) sent ESPN, MFL and Fleaflicker invitees to the wrong
            app entirely — the one platform they were guaranteed not to be
            joining. Surfaced while tracing PR-7 in the P1 round. */}
        {showInviteNotice ? (
          <Text testID="leaguepicker.invite-notice" style={styles.inviteNotice}>
            You're not in that league yet — pick one below, or join it on your
            fantasy platform and open the invite again.
          </Text>
        ) : null}
        <FlatList
          data={cached}
          keyExtractor={(lg) => lg.league_id}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={false} onRefresh={refresh} tintColor={ice.base} />
          }
          renderItem={({ item }) => {
            const isBusy = selectingId === item.league_id;
            return (
              <Pressable
                testID={`leagues.row.${item.league_id}`}
                // S8 PRD-02 — the row Pressable swallows child text on iOS
                // (documented in components/CLAUDE.md); the explicit
                // grouped label makes it one complete button utterance.
                accessibilityRole="button"
                accessibilityLabel={[
                  item.name,
                  item.platform && PLATFORM_BADGE[item.platform]
                    ? PLATFORM_BADGE[item.platform]
                    : null,
                  `${item.total_rosters || 12} teams`,
                ]
                  .filter(Boolean)
                  .join(', ')}
                accessibilityHint="Opens this league"
                accessibilityState={{ disabled: !!selectingId, busy: isBusy }}
                style={({ pressed }) => [
                  styles.row,
                  pressed && styles.rowPressed,
                  isBusy && styles.rowBusy,
                ]}
                onPress={() => pickLeague(item)}
                disabled={!!selectingId}
              >
                <View style={styles.rowBody}>
                  <View style={styles.rowNameRow}>
                    <Text style={[styles.rowName, styles.rowNameText]} numberOfLines={1}>
                      {item.name}
                    </Text>
                    {item.platform && PLATFORM_BADGE[item.platform] ? (
                      <Badge label={PLATFORM_BADGE[item.platform]} />
                    ) : null}
                  </View>
                  <View style={styles.rowMetaRow}>
                    <Text style={styles.rowMeta}>
                      {item.total_rosters || 12} teams
                    </Text>
                    {/* #14 — consensus power rank in this league (silent-fail). */}
                    <RankChipBadge leagueId={item.league_id} />
                  </View>
                </View>
                {isBusy ? (
                  <ActivityIndicator color={chalk.dim} />
                ) : (
                  <Icon name="chevron-right" size={16} color={chalk.dim} />
                )}
              </Pressable>
            );
          }}
        />
        </>
      )}

      {/* Flag-gated link affordances. Each platform gates on its own flag and
          appears in every non-loading state — including "no leagues found",
          where a non-Sleeper-only manager would otherwise dead-end.
          Suppressed in the P0-5 companion state, which offers the same
          platforms as full-width primary actions — rendering both would show
          every button twice. */}
      {!loading && !accountOnlyEmpty && (espnEnabled || mflEnabled || fleaflickerEnabled) ? (
        <View style={styles.espnFooter}>
          {espnEnabled ? (
            <Button
              testID="leagues.link-espn"
              label="Link an ESPN league"
              variant="secondary"
              compact
              onPress={() => setEspnOpen(true)}
              disabled={!!selectingId}
            />
          ) : null}
          {mflEnabled ? (
            <Button
              testID="leagues.link-mfl"
              label="Link an MFL league"
              variant="secondary"
              compact
              onPress={() => setPlatformOpen('mfl')}
              disabled={!!selectingId}
              style={styles.linkBtnGap}
            />
          ) : null}
          {fleaflickerEnabled ? (
            <Button
              testID="leagues.link-fleaflicker"
              label="Link a Fleaflicker league"
              variant="secondary"
              compact
              onPress={() => setPlatformOpen('fleaflicker')}
              disabled={!!selectingId}
              style={styles.linkBtnGap}
            />
          ) : null}
        </View>
      ) : null}

      <EspnLinkSheet
        visible={espnOpen}
        onClose={() => setEspnOpen(false)}
        onLinked={onLeagueLinked}
      />
      {platformOpen ? (
        <PlatformLinkSheet
          visible={platformOpen !== null}
          platform={platformOpen}
          onClose={() => setPlatformOpen(null)}
          onLinked={onLeagueLinked}
        />
      ) : null}
      {/* Mounted CONDITIONALLY, like PlatformLinkSheet above and for the same
          reason: the sibling-modal wedge documented at the top of this file.
          A third always-mounted <Modal> on this screen re-opens that hazard
          for no benefit. */}
      {sleeperOpen ? (
        <LinkSleeperSheet
          visible
          onClose={() => setSleeperOpen(false)}
          onLinked={onSleeperLinked}
        />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  header: {
    paddingLeft: space.xl,
    paddingRight: space.lg,
    paddingTop: space.lg,
    paddingBottom: space.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: { ...type.heading },
  sub: { ...type.bodySm, marginTop: 2 },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
    gap: space.md,
  },
  loadingText: { ...type.bodySm, textAlign: 'center' },
  error: { ...type.bodySm, color: semantic.neg, textAlign: 'center' },
  // P0-5 companion-state copy. Not `error` — that one is semantic.neg (red)
  // and this is not a failure.
  emptyBody: { ...type.body, textAlign: 'center' },
  // P0-3 — informational, NOT an error: dim chalk, same rhythm as the
  // companion copy. Never semantic.neg — nothing has gone wrong.
  inviteNotice: {
    ...type.bodySm,
    color: chalk.dim,
    paddingHorizontal: space.xl,
    paddingTop: space.sm,
  },
  list: { paddingVertical: space.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 56,
    paddingHorizontal: space.xl,
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    gap: space.md,
  },
  rowPressed: { backgroundColor: ink.ink3 },
  rowBusy: { opacity: 0.6 },
  rowBody: { flex: 1, minWidth: 0 },
  rowName: { ...type.title },
  rowNameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  rowNameText: { flexShrink: 1 },
  rowMeta: { ...type.bodySm, marginTop: 2 },
  rowMetaRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  espnFooter: {
    paddingHorizontal: space.xl,
    paddingVertical: space.md,
    borderTopWidth: 1,
    borderTopColor: ink.line,
  },
  linkBtnGap: { marginTop: space.sm },
});

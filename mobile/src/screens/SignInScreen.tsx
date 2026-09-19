import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  Pressable,
  ActivityIndicator,
  StyleSheet,
  Keyboard,
  Platform,
  KeyboardAvoidingView,
  Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as AppleAuthentication from 'expo-apple-authentication';
import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { TickLabel, Text as ChalkText } from '../components/chalkline';
import { appleSignIn, resolveSmartStart, signIn } from '../api/auth';
import { track } from '../api/events';
import { consumeAppleReauthHint, NO_LEAGUE_ID, useSession } from '../state/useSession';
import { useFlag, useOnboardingFeature } from '../state/useFeatureFlags';
import {
  useGuide,
  requestGuideStep,
  advanceGuideIfActive,
  guideActiveStepId,
  guidedAvatarActive,
} from '../state/useGuide';
import { getOnboardingState, patchOnboardingState } from '../state/useOnboardingState';
import { registerGuideTarget, unregisterGuideTarget } from '../state/guideTargets';
import { S as GUIDE } from '../components/analystScript';
import { getLeagues, getLeagueRosters, getLeagueUsers } from '../api/sleeper';
import { fetchInviteMeta } from '../api/league';
import { getLastUsername, setLastUsername } from '../api/client';
import { testLaunchArg } from '../utils/testRouteEntry';
import EspnLinkSheet from '../components/EspnLinkSheet';
import PlatformLinkSheet from '../components/PlatformLinkSheet';

// Maestro seam (hld.md §5). `null` in every production bundle: testLaunchArg
// returns null unless the build-time `extra.testMode` constant is true, which
// only mobile/scripts/sim-build.sh produces. Read once at module load — the
// argument domain is volatile and cannot be set at runtime.
const TEST_APPLE_SUB = testLaunchArg('FTFTestAppleSub');

/** Landing platform options (`landing.platform_options`): the entry chip a
 *  non-Sleeper manager selected. Since D-164 the chip's own panel carries the
 *  sessionless entry flow, so this type survives for the ONE remaining Apple
 *  path — the quiet "Already have an account?" re-entry link, whose callbacks
 *  carry it so RootNav can land LeaguePicker with the matching link sheet
 *  auto-opened (#130 `espnLink` / its `mflLink` twin). */
export type EntryPlatformIntent = 'espn' | 'mfl';

interface Props {
  onSignedIn: (platformIntent?: EntryPlatformIntent) => void;
  /** Called when the user opts into the seeded demo session. Bundle 8 sends
   *  them straight into the Main tabs (no league picker). */
  onDemoStarted?: () => void;
  /** P2.6 account-first: called after an Apple sign-in that has no linked
   *  Sleeper source — the account-keyed session + sentinel league are
   *  already pinned, so the caller routes straight into Main (no league
   *  picker). Falls back to onSignedIn when unset. */
  onAccountSignedIn?: (platformIntent?: EntryPlatformIntent) => void;
}

// Sign-in (P2.6 account-first): Sign in with Apple is the PRIMARY portal
// (behind auth.accounts); the Sleeper-username flow is demoted to a
// "Continue with Sleeper" secondary — the flow itself is unchanged
// (POST /api/extension/auth, the same one-shot auth the extension uses).
// A brand-new Apple identity lands in an account-only session (rank/tiers/
// anchors work; league features show link-a-league states) and can link a
// Sleeper username later from Settings → Account.
//
// Bundle 8 layers two growth-loop CTAs on top, each behind a flag:
//   • landing.smart_start_cta   — accept a Sleeper league URL as well as a
//     bare username; URL inputs go through /api/league/parse-url to find
//     a roster owner, then drop into the normal username sign-in.
//   • landing.try_before_sync   — "Try the app on a sample league →" link
//     under the primary button that calls /api/session/demo and skips the
//     league picker entirely.
export default function SignInScreen({ onSignedIn, onDemoStarted, onAccountSignedIn }: Props) {
  const [username, setUsername] = useState('');
  const [error, setError] = useState<string | null>(null);
  // Onboarding landing (ADR-006): which failure class the current error is —
  // 'unavailable' upgrades the error line with the sample-league escape.
  const [errorKind, setErrorKind] = useState<'notfound' | 'unavailable' | 'other' | null>(null);
  const [busy, setBusy] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const setUser = useSession((s) => s.setUser);
  const setLeague = useSession((s) => s.setLeague);
  const setLeagues = useSession((s) => s.setLeagues);
  const startDemoSession = useSession((s) => s.startDemoSession);
  const smartStartEnabled = useFlag('landing.smart_start_cta');
  const tryDemoEnabled    = useFlag('landing.try_before_sync');
  const accountsEnabled   = useFlag('auth.accounts');
  // Username-first landing (onboarding plan item 5, ADR-006 account-later):
  // when on, the Sleeper username field is the primary surface and Apple
  // demotes to a quiet re-entry link. Flags-off renders the P2.6 layout
  // unchanged. NOTE: the demo affordances below still require
  // landing.try_before_sync (the backend demo endpoint 404s without it) —
  // the operator flips that flag together with onboarding.landing.
  const landingOn = useOnboardingFeature('onboarding.landing');

  // ── Landing platform options (flag `landing.platform_options`) ─────────
  // The entry page offers Sleeper · ESPN · MFL as supported platforms.
  // Sleeper (default) renders today's username form untouched. ESPN/MFL swap
  // the form for an explainer + a button that opens that platform's link
  // sheet in ENTRY mode (D-164): the user signs in to ESPN/MFL or pastes a
  // league ID, claims a team, and the sessionless POST /api/entry/platform
  // mints the session at the claim — no Apple account anywhere in the path.
  // landingOn-layout only: the flags-off P2.6 layout is already Apple-first
  // and platform-agnostic.
  const platformOptionsFlag = useFlag('landing.platform_options');
  const espnLinkOn = useFlag('espn.link');
  const mflLinkOn = useFlag('mfl.link');
  const [entryPlatform, setEntryPlatform] =
    useState<'sleeper' | EntryPlatformIntent>('sleeper');
  const platformChips: Array<'sleeper' | EntryPlatformIntent> = [
    'sleeper',
    ...(espnLinkOn ? (['espn'] as const) : []),
    ...(mflLinkOn ? (['mfl'] as const) : []),
  ];
  // A single chip is no choice — hide the row unless ≥2 platforms are live.
  const platformPickerShown =
    landingOn && platformOptionsFlag && platformChips.length >= 2;
  const nonSleeperEntry = platformPickerShown && entryPlatform !== 'sleeper';
  // Flag revalidation can withdraw the selected platform mid-session — fall
  // back to Sleeper instead of stranding the user on a chip that no longer
  // renders.
  useEffect(() => {
    if (
      (entryPlatform === 'espn' && !espnLinkOn) ||
      (entryPlatform === 'mfl' && !mflLinkOn)
    ) {
      setEntryPlatform('sleeper');
    }
  }, [entryPlatform, espnLinkOn, mflLinkOn]);

  // V2 (D-164): which entry-mode link sheet is open. One at a time — iOS
  // won't stack sibling RN Modals (#266 class).
  const [entrySheet, setEntrySheet] = useState<null | 'espn' | 'mfl'>(null);

  // Entry mint landed (the sheet stored the session token already) — pin the
  // entry user. account_only is accurate AND load-bearing: it tells
  // LeaguePicker's refresh to skip the Sleeper league fetch (an entry:… id
  // is not a Sleeper user id) and merge the platform leagues instead.
  async function handleEntrySession(u: { user_id: string; display_name: string }) {
    await setUser({
      user_id: u.user_id,
      username: '',
      display_name: u.display_name,
      avatar_id: null,
      account_only: true,
    });
  }

  // Entry import finished — the league is persisted server-side and bound to
  // the entry user. Route to LeaguePicker: its refresh merges the platform
  // league (one league → onboarding.league_autoskip carries them into Main).
  function handleEntryLinked() {
    setEntrySheet(null);
    (onAccountSignedIn ?? onSignedIn)();
  }

  function selectEntryPlatform(p: 'sleeper' | EntryPlatformIntent) {
    if (p === entryPlatform) return;
    setEntryPlatform(p);
    setError(null);
    setErrorKind(null);
    if (p !== 'sleeper') {
      Keyboard.dismiss();
    }
    // The Analyst's s0.2 spotlight rings whichever entry control the chip row
    // is currently showing — the Sleeper username field, or the ESPN/MFL
    // panel's link button (`GUIDE.s0_2(entryPlatform)` below picks both the
    // target and the line). A switch unmounts that control, in EITHER
    // direction, so the beat has to do two things:
    //
    //   advance — end it now, so no ring outlives its target. This is why the
    //             switch BACK to Sleeper is handled too: once the beat can
    //             point at the platform button, returning to Sleeper strands
    //             it exactly the way leaving Sleeper used to.
    //   re-arm  — clear its once-ever mark, so the chain effect re-offers it
    //             against the control that replaced it. Without this, `once:
    //             true` spends the beat on the door the user just closed and a
    //             platform-entry user is never told where to start.
    if (guideActiveStepId() === 's0.2') {
      advanceGuideIfActive('s0.2');
      patchOnboardingState({ guideSeen: { 's0.2': false } });
    }
  }

  // ── Sign in with Apple (auth.accounts flag; account-auth plan P2/P2.6) ─
  const [appleAvailable, setAppleAvailable] = useState(false);
  const [appleBusy, setAppleBusy] = useState(false);
  // Teardown 06-03 (flag auth.persistent_sessions): an account-only
  // session's 401 routed here for an Apple re-auth — say so, once. The
  // hint is one-shot (consumed at mount) so an ordinary later visit to
  // SignIn doesn't re-show it. Only ever set while the flag is on.
  const [reauthNotice] = useState(() => consumeAppleReauthHint());

  // ── P0-3 — the invited banner ─────────────────────────────────────────
  // Subscribed selectors, so the copy upgrades in place when the name lands.
  const invitedBy = useSession((s) => s.invitedBy);
  const invitedLeagueId = useSession((s) => s.invitedLeagueId);
  const invitedLeagueName = useSession((s) => s.invitedLeagueName);

  // Resolve the invited league's name ONCE, for the banner. The result is
  // cached into the persisted invite intent so the LeaguePicker companion
  // state (P0-5) can name the league without a second call site — see the
  // vcr_misses rail in lld-p0-3 §2.0. THIS IS THE APP'S ONLY INVITE-META
  // CALL SITE; adding another one turns a passing tier-1 sim run red.
  // Never throws, never blocks the form, and has no loading or error state:
  // a missing name is a copy fallback, not a failure the user should see.
  useEffect(() => {
    const id = invitedLeagueId;
    if (!id || invitedLeagueName) return;
    let alive = true;
    void fetchInviteMeta(id).then((meta) => {
      if (!alive || !meta?.league_name) return;
      void useSession.getState().setInvitedLeagueName(meta.league_name);
    });
    return () => {
      alive = false;
    };
  }, [invitedLeagueId, invitedLeagueName]);

  const inviteHeadline = invitedBy
    ? `@${invitedBy} invited you to ${invitedLeagueName || 'their league'} — ` +
      "sign in and we'll take you straight there."
    : invitedLeagueName
    ? `You were invited to ${invitedLeagueName} — ` +
      "sign in and we'll take you straight there."
    : null;

  useEffect(() => {
    getLastUsername().then((u) => {
      if (u) {
        setUsername(u);
        setHint(u);
      }
    });
  }, []);

  // ── Guided tour S0 (The Analyst; guided-avatar-script.md) ──────────────
  // Intro (s0.1) on mount, then the point-at-field step (s0.2) chains when
  // the intro is advanced. Both once-ever; the chain effect re-fires off
  // persisted guideSeen, so a backgrounded app re-offers at the same gate.
  const guideActive = useGuide((s) => s.active);
  const usernameFieldRef = useRef<View | null>(null);
  // The ESPN/MFL panel's link button — s0.2's target whenever a non-Sleeper
  // chip is selected. Registered unconditionally, like the username field:
  // only one of the two is ever mounted, and the other measures null, which
  // is the registry's ordinary degrade-to-bubble path.
  const platformLinkRef = useRef<View | null>(null);
  useEffect(() => {
    registerGuideTarget('signin.username-input', usernameFieldRef);
    registerGuideTarget('signin.platform-link-btn', platformLinkRef);
    return () => {
      unregisterGuideTarget('signin.username-input');
      unregisterGuideTarget('signin.platform-link-btn');
    };
  }, []);
  useEffect(() => {
    if (!landingOn || !guidedAvatarActive()) return;
    const seen = getOnboardingState().guideSeen;
    if (!seen['s0.1']) {
      const t = setTimeout(() => requestGuideStep(GUIDE.s0_1()), 600);
      return () => clearTimeout(t);
    }
    if (!guideActive && !seen['s0.2']) {
      // Platform-aware: the beat rings the control this chip choice put on
      // screen. `entryPlatform` is a dep so a chip switch re-offers it (see
      // selectEntryPlatform, which ends + re-arms an in-flight s0.2); with
      // `landing.platform_options` off the chips never render, the value is
      // pinned to 'sleeper', and this is the shipped call.
      requestGuideStep(GUIDE.s0_2(entryPlatform));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [landingOn, guideActive, entryPlatform]);

  useEffect(() => {
    if (!accountsEnabled || Platform.OS !== 'ios') return;
    AppleAuthentication.isAvailableAsync()
      .then(setAppleAvailable)
      .catch(() => setAppleAvailable(false));
  }, [accountsEnabled]);

  // Test builds show the Apple entry even when the simulator reports Apple
  // sign-in unavailable (no iCloud account) — the credential is substituted,
  // so availability is irrelevant. Identical to `appleAvailable` in
  // production, where TEST_APPLE_SUB is null.
  const appleShown = appleAvailable || TEST_APPLE_SUB !== null;

  async function handleAppleSignIn() {
    if (busy || demoBusy || appleBusy) return;
    // Landing platform options: an ESPN/MFL chip selection rides the Apple
    // flow so LeaguePicker can auto-open the matching link sheet on arrival.
    const platformIntent: EntryPlatformIntent | undefined =
      nonSleeperEntry ? entryPlatform : undefined;
    setAppleBusy(true);
    setError(null);
    setErrorKind(null);
    track('signin_attempted', { method: 'apple' }, 'SignIn');
    try {
      // Everything AFTER this line — the account_only branch, setUser,
      // setLeague, onAccountSignedIn — is production code under test.
      // Stubbing further up (seeding useSession directly) would test the
      // harness instead of the branch. The explicit structural annotation is
      // what lets an object literal stand in for an
      // AppleAuthenticationCredential: only `identityToken` and `fullName`
      // are read below.
      const cred: {
        identityToken: string | null;
        fullName?: { givenName?: string | null; familyName?: string | null } | null;
      } = TEST_APPLE_SUB
        ? { identityToken: `ftf-test-apple:${TEST_APPLE_SUB}`, fullName: null }
        : await AppleAuthentication.signInAsync({
            requestedScopes: [
              AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
              AppleAuthentication.AppleAuthenticationScope.EMAIL,
            ],
          });
      if (!cred.identityToken) throw new Error('Apple did not return an identity token.');
      // Apple sends the name only on FIRST authorization — forward it so
      // a brand-new account's users row has a display name.
      const appleName = [cred.fullName?.givenName, cred.fullName?.familyName]
        .filter(Boolean)
        .join(' ');
      const res = await appleSignIn(cred.identityToken, appleName || undefined);
      if (res.linked && res.sleeper_user_id && res.session_token) {
        // Returning account — the backend restored a session for the bound
        // Sleeper user. Same post-auth steps as the username path.
        await setUser({
          user_id:      res.sleeper_user_id,
          username:     res.username || '',
          display_name: res.display_name || res.username || 'Manager',
          avatar_id:    res.avatar ?? null,
        });
        if (res.username) void setLastUsername(res.username);
        try {
          const lgs = await getLeagues(res.sleeper_user_id);
          setLeagues(lgs);
        } catch {
          // Non-fatal; picker will fetch its own copy
        }
        track('signin_succeeded', { method: 'apple' }, 'SignIn');
        onSignedIn(platformIntent);
      } else if (res.account_only && res.user_id && res.session_token) {
        // ACCOUNT-FIRST (P2.6): no Sleeper source linked — the backend
        // minted an account-keyed session with an empty sentinel league.
        // Pin both locally and go straight to Main; a Sleeper username can
        // be linked later from Settings → Account.
        await setUser({
          user_id:      res.user_id,
          username:     '',
          display_name: res.display_name || 'Manager',
          avatar_id:    null,
          account_only: true,
        });
        await setLeague({
          league_id:   res.league_id || NO_LEAGUE_ID,
          league_name: res.league_name || 'No league linked',
        });
        track('signin_succeeded', { method: 'apple' }, 'SignIn');
        (onAccountSignedIn ?? onSignedIn)(platformIntent);
      } else {
        throw new Error('Apple sign-in did not return a usable session.');
      }
    } catch (err: any) {
      track(
        'signin_failed',
        { method: 'apple', error_code: signInErrorCode(err) },
        'SignIn',
      );
      if (err?.code !== 'ERR_REQUEST_CANCELED') {
        setError(err?.message || 'Apple sign-in failed. Try again.');
      }
    } finally {
      setAppleBusy(false);
    }
  }

  async function handleSubmit(
    override?: string,
    method: 'sleeper' | 'last_user' = 'sleeper',
  ) {
    if (busy) return;
    const rawInput = (override ?? username).trim();
    if (!rawInput) {
      setError('Enter your Sleeper username');
      return;
    }
    setBusy(true);
    setError(null);
    setErrorKind(null);
    advanceGuideIfActive('s0.2');
    track('signin_attempted', { method }, 'SignIn');
    Keyboard.dismiss();

    let usernameToAuth = rawInput.toLowerCase();

    // Smart-start: when the flag is on, the field accepts either a bare
    // username or a Sleeper / ESPN / MFL league URL. URLs get parsed into
    // a (platform, league_id) tuple; we then look up an owner and drop
    // into the existing username flow. Mirrors the web's smart-start panel.
    if (smartStartEnabled) {
      const resolved = await resolveSmartStart(rawInput);
      if (resolved.kind === 'invalid') {
        track(
          'signin_failed',
          { method, error_code: 'smart_start_invalid' },
          'SignIn',
        );
        setError(resolved.message || "Couldn't parse that URL.");
        setBusy(false);
        return;
      }
      if (resolved.kind === 'league_url') {
        if (resolved.platform !== 'sleeper' || !resolved.supported || !resolved.league_id) {
          track(
            'signin_failed',
            { method, error_code: 'platform_unsupported' },
            'SignIn',
          );
          // ESPN/MFL are live platforms now — a league URL just can't START
          // sign-in (the link routes need a session first). Point at the
          // entry chips when they render; otherwise at the Settings path.
          const pname =
            resolved.platform === 'espn'
              ? 'ESPN'
              : resolved.platform === 'mfl'
              ? 'MFL'
              : null;
          setError(
            pname && platformPickerShown
              ? `That's an ${pname} league URL — choose ${pname} above to link it.`
              : pname
              ? `${pname} leagues link after sign-in — enter a Sleeper username here, or sign in with Apple and link your league from Settings.`
              : "That league URL isn't from a supported platform — paste a Sleeper league URL or your username.",
          );
          setBusy(false);
          return;
        }
        // Sleeper URL: resolve a roster owner and use their username.
        try {
          const [rosters, leagueUsers] = await Promise.all([
            getLeagueRosters(resolved.league_id),
            getLeagueUsers(resolved.league_id),
          ]);
          const firstOwner = (rosters || [])
            .map((r) => r?.owner_id)
            .find((id) => !!id);
          if (!firstOwner) throw new Error('No roster owners found.');
          const ownerRow = (leagueUsers || []).find((u) => u.user_id === firstOwner);
          const ownerName = ownerRow?.username || ownerRow?.display_name;
          if (!ownerName) throw new Error('Could not resolve a league owner.');
          usernameToAuth = ownerName.toLowerCase();
        } catch (e: any) {
          track(
            'signin_failed',
            { method, error_code: 'owner_resolve_failed' },
            'SignIn',
          );
          setError(
            e?.message ||
              "We found that league but couldn't resolve a username. Try typing your Sleeper username.",
          );
          setBusy(false);
          return;
        }
      } else {
        usernameToAuth = resolved.username || rawInput.toLowerCase();
      }
    }

    try {
      const auth = await signIn(usernameToAuth);
      await setUser({
        user_id: auth.user_id,
        username: auth.username,
        display_name: auth.display_name,
        avatar_id: auth.avatar ?? null,
      });
      // Remember username in Keychain so it survives reinstall + sign-out.
      void setLastUsername(auth.username);
      // Prefetch leagues so the league picker is instant
      try {
        const lgs = await getLeagues(auth.user_id);
        setLeagues(lgs);
      } catch {
        // Non-fatal; picker will fetch its own copy
      }
      track('signin_succeeded', { method }, 'SignIn');
      onSignedIn();
    } catch (err: any) {
      track(
        'signin_failed',
        { method, error_code: signInErrorCode(err) },
        'SignIn',
      );
      const kind = classifySignInError(err);
      setErrorKind(kind);
      // Guided tour: The Analyst delivers the error commentary (oops pose);
      // the inline error text below still renders for accessibility parity.
      if (landingOn && guidedAvatarActive()) {
        requestGuideStep(kind === 'notfound' ? GUIDE.s0_err_notfound() : GUIDE.s0_err_down());
      }
      if (landingOn && kind === 'notfound') {
        // Voice doc: username-vs-team-name confusion is the most likely
        // first-field failure — the copy must say what to fix.
        setError(
          `No "@${usernameToAuth}" on Sleeper. Usernames aren't team names — check your Sleeper profile and retype it.`,
        );
      } else if (landingOn && kind === 'unavailable') {
        setError("Sleeper isn't responding.");
      } else {
        setError(err?.message || 'Sign-in failed. Try again.');
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleTryDemo() {
    if (demoBusy || busy) return;
    setDemoBusy(true);
    setError(null);
    setErrorKind(null);
    track('signin_attempted', { method: 'demo' }, 'SignIn');
    try {
      await startDemoSession();
      track('signin_succeeded', { method: 'demo' }, 'SignIn');
      // The demo flow drops the user straight into Main — RootNav's gating
      // (user + league + token) is already satisfied by startDemoSession.
      onDemoStarted?.();
    } catch (err: any) {
      track(
        'signin_failed',
        { method: 'demo', error_code: signInErrorCode(err) },
        'SignIn',
      );
      setError(err?.message || 'Demo unavailable — try again.');
    } finally {
      setDemoBusy(false);
    }
  }

  const submitDisabled = busy || demoBusy || !username.trim();

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <View style={styles.body}>
          <View style={styles.hero}>
            <TickLabel>Dynasty Fantasy Football</TickLabel>
            <Text style={styles.headline}>
              Rank your league.{'\n'}Find the trades both sides want.
            </Text>
            <Text style={styles.sub}>
              Compare your rankings to your leaguemates' and find trades where
              both sides come out ahead.
            </Text>
          </View>

          <View style={styles.form}>
            {reauthNotice ? (
              <Text testID="signin.reauth-notice" style={styles.reauthNotice}>
                Your session expired — sign in with Apple to pick up where you
                left off.
              </Text>
            ) : null}
            {/* P0-3 — the invited banner. INSIDE styles.form, beside the
                reauth notice, so it renders in BOTH `landingOn` variants:
                with onboarding.landing on, the Apple entry demotes to a text
                link and everything above this changes, so a banner attached
                to the Apple block would vanish for exactly the cohort P0-9
                is testing. */}
            {inviteHeadline ? (
              <Text testID="signin.invited-banner" style={styles.invitedBanner}>
                {inviteHeadline}
              </Text>
            ) : null}
            {/* Landing platform options — Sleeper · ESPN · MFL entry chips.
                Sleeper (default) leaves the form below untouched; ESPN/MFL
                swap it for the explainer + Apple panel further down. */}
            {platformPickerShown ? (
              <View style={styles.platformRow}>
                {platformChips.map((p) => {
                  const on = entryPlatform === p;
                  return (
                    <Pressable
                      key={p}
                      testID={`signin.platform-${p}`}
                      accessibilityRole="button"
                      accessibilityLabel={`Use ${
                        p === 'sleeper' ? 'Sleeper' : p === 'espn' ? 'ESPN' : 'MyFantasyLeague'
                      }`}
                      accessibilityState={{ selected: on }}
                      onPress={() => selectEntryPlatform(p)}
                      disabled={busy || demoBusy || appleBusy}
                      style={({ pressed }) => [
                        styles.platformChip,
                        on && styles.platformChipOn,
                        pressed && !on && styles.platformChipPressed,
                      ]}
                    >
                      <ChalkText
                        style={[styles.platformChipText, on && styles.platformChipTextOn]}
                      >
                        {p === 'sleeper' ? 'Sleeper' : p === 'espn' ? 'ESPN' : 'MFL'}
                      </ChalkText>
                    </Pressable>
                  );
                })}
              </View>
            ) : null}
            {!landingOn && appleShown ? (
              <>
                {/* P2.6 — Apple is the PRIMARY portal. Official Apple button
                    (HIG-required component). White variant — the HIG
                    mandates it on dark backgrounds. */}
                <AppleAuthentication.AppleAuthenticationButton
                  testID="signin.apple-btn"
                  buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
                  buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.WHITE}
                  cornerRadius={radii.sm}
                  style={styles.appleButton}
                  onPress={handleAppleSignIn}
                />
                {appleBusy ? (
                  <ActivityIndicator color={chalk.dim} style={styles.appleBusy} />
                ) : null}
                <Text style={styles.orDivider}>or continue with Sleeper</Text>
              </>
            ) : null}
            {nonSleeperEntry ? (
              // ESPN/MFL entry panel (v2, D-164): no Apple dependency. The
              // button opens the platform's own link sheet in entry mode —
              // claim your team, and the session is minted at the claim (the
              // sessionless /api/entry/platform), same trust model as the
              // Sleeper username field beside it.
              <View testID="signin.platform-panel">
                <ChalkText style={styles.platformExplainer}>
                  {entryPlatform === 'espn'
                    ? 'ESPN dynasty leagues are supported. Sign in to ESPN and we’ll find your leagues, or enter a league ID — no extra account needed.'
                    : 'MyFantasyLeague dynasty leagues are supported. Sign in with MFL and we’ll find your leagues, or enter a league ID — no extra account needed.'}
                </ChalkText>
                {/* Guide spotlight target — collapsable={false} so the
                    wrapper survives view-flattening and stays measurable,
                    exactly as the username field's wrapper does. This is what
                    s0.2 rings for an ESPN/MFL chip. */}
                <View ref={platformLinkRef} collapsable={false}>
                <Pressable
                  testID="signin.platform-link-btn"
                  accessibilityRole="button"
                  style={({ pressed }) => [
                    styles.button,
                    pressed && styles.buttonPressed,
                  ]}
                  onPress={() => {
                    // The real action s0.2 asks for on this path — the same
                    // contract handleSubmit carries for the username field.
                    advanceGuideIfActive('s0.2');
                    setEntrySheet(entryPlatform === 'espn' ? 'espn' : 'mfl');
                  }}
                  disabled={busy || demoBusy || appleBusy}
                >
                  <Text style={styles.buttonText}>
                    {entryPlatform === 'espn'
                      ? 'Link your ESPN league →'
                      : 'Link your MFL league →'}
                  </Text>
                </Pressable>
                </View>
              </View>
            ) : null}
            {!nonSleeperEntry && hint ? (
              <Pressable
                testID="signin.hint-btn"
                accessibilityRole="button"
                accessibilityLabel={`Continue as @${hint}`}
                style={({ pressed }) => [
                  styles.hintRow,
                  pressed && styles.hintRowPressed,
                ]}
                onPress={() => {
                  setUsername(hint);
                  void handleSubmit(hint, 'last_user');
                }}
                disabled={busy}
              >
                <Text style={styles.hintLabel}>Continue as</Text>
                <Text style={styles.hintName}>@{hint}</Text>
              </Pressable>
            ) : null}
            {/* Guide spotlight target — collapsable={false} so the wrapper
                survives view-flattening and stays measurable. Hidden while an
                ESPN/MFL chip is selected; selectEntryPlatform ends s0.2 before
                that happens (and re-arms it against the platform panel's
                button), so no spotlight outlives its target. */}
            {nonSleeperEntry ? null : (
            <View ref={usernameFieldRef} collapsable={false}>
            <TextInput
              testID="signin.username-input"
              style={[styles.input, focused && styles.inputFocused]}
              placeholder={smartStartEnabled && !landingOn ? 'Sleeper username or league URL' : 'Sleeper username'}
              placeholderTextColor={chalk.faint}
              value={username}
              onChangeText={setUsername}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="off"
              returnKeyType="go"
              onSubmitEditing={() => handleSubmit()}
              editable={!busy && !demoBusy}
              inputMode="text"
            />
            </View>
            )}
            {nonSleeperEntry ? null : landingOn ? (
              <Text style={styles.fieldHint}>
                No password. Your league's rosters do the talking.
              </Text>
            ) : smartStartEnabled ? (
              <Text style={styles.fieldHint}>
                Paste your Sleeper username or league URL.
              </Text>
            ) : null}
            {error ? <Text testID="signin.error-text" style={styles.error}>{error}</Text> : null}
            {landingOn && errorKind === 'unavailable' && tryDemoEnabled ? (
              // F6: the highest-intent moment we'll ever have must not die on
              // a dead error line — the demo escape converts a total loss
              // into a partial activation.
              <Pressable
                testID="signin.error-demo-escape"
                accessibilityRole="button"
                onPress={handleTryDemo}
                disabled={busy || demoBusy}
                hitSlop={8}
                style={styles.errorEscape}
              >
                {({ pressed }) => (
                  <Text style={[styles.errorEscapeText, pressed && styles.tryDemoTextPressed]}>
                    Browse the sample league while we retry →
                  </Text>
                )}
              </Pressable>
            ) : null}
            {nonSleeperEntry ? null : (
            <Pressable
              testID="signin.continue-btn"
              accessibilityRole="button"
              style={({ pressed }) => [
                styles.button,
                !landingOn && appleAvailable && styles.buttonSecondary,
                pressed && !submitDisabled && (!landingOn && appleAvailable ? styles.buttonSecondaryPressed : styles.buttonPressed),
                submitDisabled && styles.buttonDisabled,
              ]}
              onPress={() => handleSubmit()}
              disabled={submitDisabled}
            >
              {busy ? (
                <ActivityIndicator color={!landingOn && appleAvailable ? chalk.base : ice.on} />
              ) : (
                <Text style={[styles.buttonText, !landingOn && appleAvailable && styles.buttonSecondaryText]}>
                  {landingOn
                    ? 'See trades for your team →'
                    : appleAvailable
                      ? 'Continue with Sleeper →'
                      : 'Connect →'}
                </Text>
              )}
            </Pressable>
            )}

            {tryDemoEnabled ? (
              <Pressable
                testID="signin.demo-link"
                accessibilityRole="button"
                onPress={handleTryDemo}
                disabled={busy || demoBusy}
                style={styles.tryDemoBtn}
                hitSlop={8}
              >
                {({ pressed }) =>
                  demoBusy ? (
                    <ActivityIndicator color={chalk.dim} />
                  ) : (
                    <Text
                      style={[styles.tryDemoText, pressed && styles.tryDemoTextPressed]}
                    >
                      {landingOn
                        ? 'Just looking? Browse a sample league →'
                        : 'Try the app on a sample league →'}
                    </Text>
                  )
                }
              </Pressable>
            ) : null}

            {landingOn && appleShown ? (
              // ADR-006: quiet re-entry door for existing Apple-bound
              // (P2.6 account-only) users — they may have no Sleeper
              // username to type. Text link by design: it must never
              // compete with the username field. (Conscious HIG tradeoff:
              // the official Apple button is reserved for the flags-off
              // layout; revisit if App Review objects.)
              <Pressable
                testID="signin.apple-link"
                accessibilityRole="button"
                onPress={handleAppleSignIn}
                disabled={busy || demoBusy || appleBusy}
                style={styles.tryDemoBtn}
                hitSlop={8}
              >
                {({ pressed }) =>
                  appleBusy ? (
                    <ActivityIndicator color={chalk.dim} />
                  ) : (
                    <Text style={[styles.tryDemoText, pressed && styles.tryDemoTextPressed]}>
                      Already have an account? Sign in with Apple
                    </Text>
                  )
                }
              </Pressable>
            ) : null}

            <Text style={styles.legalLine}>
              By signing in you agree to the{' '}
              <Text
                style={styles.legalLink}
                onPress={() => Linking.openURL('https://fantasy-trade-finder.onrender.com/terms')}
              >
                Terms
              </Text>
              {' '}&amp;{' '}
              <Text
                style={styles.legalLink}
                onPress={() => Linking.openURL('https://fantasy-trade-finder.onrender.com/privacy')}
              >
                Privacy Policy
              </Text>
            </Text>
          </View>
        </View>
      </KeyboardAvoidingView>
      {/* V2 (D-164) — entry-mode link sheets. Mount pattern mirrors
          LeaguePicker: ESPN sheet unconditional (it manages its own Modal
          visibility, incl. hiding for the EspnConnect WebView push),
          PlatformLinkSheet conditional. Only one is ever visible. */}
      <EspnLinkSheet
        entry
        visible={entrySheet === 'espn'}
        onClose={() => setEntrySheet(null)}
        onEntrySession={handleEntrySession}
        onLinked={handleEntryLinked}
      />
      {entrySheet === 'mfl' ? (
        <PlatformLinkSheet
          entry
          visible
          platform="mfl"
          onClose={() => setEntrySheet(null)}
          onEntrySession={handleEntrySession}
          onLinked={handleEntryLinked}
        />
      ) : null}
    </SafeAreaView>
  );
}

// Onboarding landing failure classes. The backend contract
// (/api/extension/auth): 404 user_not_found for an unknown username,
// 502 sleeper_error when Sleeper itself fails; timeouts/network errors
// also mean "Sleeper (or our server) unreachable" from the user's seat.
function classifySignInError(err: any): 'notfound' | 'unavailable' | 'other' {
  if (err?.status === 404) return 'notfound';
  if (err?.isTimeout || err?.status === 0 || (typeof err?.status === 'number' && err.status >= 500)) {
    return 'unavailable';
  }
  return 'other';
}

// Analytics: normalize this screen's real error shapes into a compact
// error_code for signin_failed. ApiError carries status/isTimeout; the
// Apple flow throws coded errors (e.g. ERR_REQUEST_CANCELED → 'canceled').
function signInErrorCode(err: any): string {
  if (err?.code === 'ERR_REQUEST_CANCELED') return 'canceled';
  if (typeof err?.code === 'string' && err.code) return err.code;
  if (err?.isTimeout) return 'timeout';
  if (typeof err?.status === 'number' && err.status > 0) return `http_${err.status}`;
  return 'unknown';
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  flex: { flex: 1 },
  body: {
    flex: 1,
    paddingHorizontal: space.xl,
    justifyContent: 'center',
    alignItems: 'flex-start',
  },
  hero: {
    marginBottom: space.xxl,
    alignItems: 'flex-start',
  },
  headline: {
    ...type.display,
    marginTop: space.md,
    marginBottom: space.md,
  },
  sub: {
    ...type.body,
    color: chalk.dim,
  },
  form: { alignSelf: 'stretch' },
  hintRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 44,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.lg,
    marginBottom: space.md,
  },
  hintRowPressed: { backgroundColor: ink.ink3 },
  hintLabel: { ...type.bodySm },
  hintName: { ...type.title },
  input: {
    height: 44,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    color: chalk.base,
    fontFamily: fonts.ui,
    fontSize: 14,
    paddingHorizontal: space.lg,
    marginBottom: space.sm,
  },
  inputFocused: { borderColor: ice.base },
  error: {
    ...type.bodySm,
    color: semantic.neg,
    marginBottom: space.sm,
  },
  // Teardown 06-03 — account-only session-expired re-auth notice.
  // Informational (not an error): dim chalk, sits above the Apple portal.
  reauthNotice: {
    ...type.bodySm,
    color: chalk.dim,
    marginBottom: space.md,
  },
  // P0-3 — invited banner. Same slot, same rhythm as reauthNotice: no new
  // visual pattern, no accent beyond the existing ones.
  invitedBanner: {
    ...type.bodySm,
    color: chalk.dim,
    marginBottom: space.md,
  },
  button: {
    height: 44,
    backgroundColor: ice.base,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: space.sm,
  },
  buttonPressed: { backgroundColor: ice.press },
  buttonDisabled: { opacity: 0.45 },
  buttonText: {
    color: ice.on,
    fontFamily: fonts.uiSemi,
    fontSize: 14,
  },
  fieldHint: {
    ...type.bodySm,
    marginTop: -space.xs,
    marginBottom: space.sm,
  },
  // ── Landing platform options (Sleeper · ESPN · MFL entry chips) ────────
  // Outline chips matching hintRow's border treatment; selected = ice, the
  // one action accent Chalkline allows.
  platformRow: {
    flexDirection: 'row',
    gap: space.sm,
    marginBottom: space.md,
  },
  platformChip: {
    flex: 1,
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
  },
  platformChipOn: { borderColor: ice.base },
  platformChipPressed: { backgroundColor: ink.ink3 },
  platformChipText: {
    ...type.bodySm,
    fontFamily: fonts.uiSemi,
    color: chalk.dim,
  },
  platformChipTextOn: { color: chalk.base },
  platformExplainer: {
    ...type.bodySm,
    color: chalk.dim,
    marginBottom: space.md,
  },
  // ── Sign in with Apple (auth.accounts; P2.6 primary portal) ────────────
  appleButton: {
    alignSelf: 'stretch',
    height: 44,
    marginBottom: space.md,
  },
  appleBusy: {
    marginBottom: space.md,
  },
  orDivider: {
    ...type.bodySm,
    color: chalk.faint,
    textAlign: 'center',
    marginBottom: space.md,
  },
  // Sleeper demoted to a secondary (outline) action when Apple is shown.
  buttonSecondary: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: ink.lineStrong,
  },
  buttonSecondaryPressed: { backgroundColor: ink.ink3 },
  buttonSecondaryText: { color: chalk.base },
  tryDemoBtn: {
    alignSelf: 'stretch',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 44,
    marginTop: space.sm,
  },
  tryDemoText: {
    ...type.bodySm,
    fontFamily: fonts.uiSemi,
  },
  tryDemoTextPressed: { color: chalk.base },
  // Onboarding landing: Sleeper-down escape rendered directly under the
  // error line (ice = action per Chalkline).
  errorEscape: {
    minHeight: 32,
    justifyContent: 'center',
    marginBottom: space.sm,
  },
  errorEscapeText: {
    ...type.bodySm,
    color: ice.base,
    fontFamily: fonts.uiSemi,
  },
  legalLine: {
    ...type.bodySm,
    color: chalk.faint,
    textAlign: 'center',
    alignSelf: 'stretch',
    marginTop: space.lg,
  },
  legalLink: {
    color: chalk.dim,
    textDecorationLine: 'underline',
  },
});

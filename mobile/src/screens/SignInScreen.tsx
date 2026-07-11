import React, { useEffect, useState } from 'react';
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
import { TickLabel } from '../components/chalkline';
import { appleSignIn, resolveSmartStart, signIn } from '../api/auth';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { getLeagues, getLeagueRosters, getLeagueUsers } from '../api/sleeper';
import { getLastUsername, setLastUsername } from '../api/client';

interface Props {
  onSignedIn: () => void;
  /** Called when the user opts into the seeded demo session. Bundle 8 sends
   *  them straight into the Main tabs (no league picker). */
  onDemoStarted?: () => void;
}

// Sign-in: Sleeper username → POST /api/extension/auth.
// Same one-shot auth flow the Chrome extension uses. After success we
// prefetch the user's leagues so the next screen has data ready.
//
// Bundle 8 layers two growth-loop CTAs on top, each behind a flag:
//   • landing.smart_start_cta   — accept a Sleeper league URL as well as a
//     bare username; URL inputs go through /api/league/parse-url to find
//     a roster owner, then drop into the normal username sign-in.
//   • landing.try_before_sync   — "Try the app on a sample league →" link
//     under the primary button that calls /api/session/demo and skips the
//     league picker entirely.
export default function SignInScreen({ onSignedIn, onDemoStarted }: Props) {
  const [username, setUsername] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demoBusy, setDemoBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const setUser = useSession((s) => s.setUser);
  const setLeagues = useSession((s) => s.setLeagues);
  const startDemoSession = useSession((s) => s.startDemoSession);
  const smartStartEnabled = useFlag('landing.smart_start_cta');
  const tryDemoEnabled    = useFlag('landing.try_before_sync');
  const accountsEnabled   = useFlag('auth.accounts');

  // ── Sign in with Apple (auth.accounts flag; account-auth plan P2) ──────
  // appleToken holds the verified identity token while the account still
  // needs a Sleeper username bound to it — the username submit re-posts it.
  const [appleAvailable, setAppleAvailable] = useState(false);
  const [appleBusy, setAppleBusy] = useState(false);
  const [appleToken, setAppleToken] = useState<string | null>(null);

  useEffect(() => {
    getLastUsername().then((u) => {
      if (u) {
        setUsername(u);
        setHint(u);
      }
    });
  }, []);

  useEffect(() => {
    if (!accountsEnabled || Platform.OS !== 'ios') return;
    AppleAuthentication.isAvailableAsync()
      .then(setAppleAvailable)
      .catch(() => setAppleAvailable(false));
  }, [accountsEnabled]);

  async function handleAppleSignIn() {
    if (busy || demoBusy || appleBusy) return;
    setAppleBusy(true);
    setError(null);
    try {
      const cred = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
      });
      if (!cred.identityToken) throw new Error('Apple did not return an identity token.');
      const res = await appleSignIn(cred.identityToken);
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
        onSignedIn();
      } else {
        // New Apple account with no Sleeper user bound yet — keep the token
        // and ask for the Sleeper username; handleSubmit re-posts it to bind.
        setAppleToken(cred.identityToken);
      }
    } catch (err: any) {
      if (err?.code !== 'ERR_REQUEST_CANCELED') {
        setError(err?.message || 'Apple sign-in failed. Try again.');
      }
    } finally {
      setAppleBusy(false);
    }
  }

  async function handleSubmit(override?: string) {
    if (busy) return;
    const rawInput = (override ?? username).trim();
    if (!rawInput) {
      setError('Enter your Sleeper username');
      return;
    }
    setBusy(true);
    setError(null);
    Keyboard.dismiss();

    let usernameToAuth = rawInput.toLowerCase();

    // Smart-start: when the flag is on, the field accepts either a bare
    // username or a Sleeper / ESPN / MFL league URL. URLs get parsed into
    // a (platform, league_id) tuple; we then look up an owner and drop
    // into the existing username flow. Mirrors the web's smart-start panel.
    if (smartStartEnabled) {
      const resolved = await resolveSmartStart(rawInput);
      if (resolved.kind === 'invalid') {
        setError(resolved.message || "Couldn't parse that URL.");
        setBusy(false);
        return;
      }
      if (resolved.kind === 'league_url') {
        if (resolved.platform !== 'sleeper' || !resolved.supported || !resolved.league_id) {
          setError(
            `${resolved.platform === 'espn' ? 'ESPN' : resolved.platform === 'mfl' ? 'MyFantasyLeague' : 'That platform'} sync is coming soon — paste a Sleeper league URL or your username for now.`,
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
      // Apple-first flow: a verified Apple identity is waiting for a Sleeper
      // user to bind to. Now that the session exists, re-post the identity
      // token so the backend links + verifies. Best-effort — a failure here
      // never blocks Sleeper sign-in (the link can be redone next launch).
      if (appleToken) {
        try {
          await appleSignIn(appleToken);
        } catch {
          /* non-fatal */
        }
        setAppleToken(null);
      }
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
      onSignedIn();
    } catch (err: any) {
      setError(err?.message || 'Sign-in failed. Try again.');
    } finally {
      setBusy(false);
    }
  }

  async function handleTryDemo() {
    if (demoBusy || busy) return;
    setDemoBusy(true);
    setError(null);
    try {
      await startDemoSession();
      // The demo flow drops the user straight into Main — RootNav's gating
      // (user + league + token) is already satisfied by startDemoSession.
      onDemoStarted?.();
    } catch (err: any) {
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
            {appleAvailable && !appleToken ? (
              <>
                {/* Official Apple button (HIG-required component). White
                    variant — the HIG mandates it on dark backgrounds. */}
                <AppleAuthentication.AppleAuthenticationButton
                  testID="signin.apple-btn"
                  buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
                  buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.WHITE}
                  cornerRadius={radii.sm}
                  style={styles.appleButton}
                  onPress={handleAppleSignIn}
                />
                <Text style={styles.orDivider}>or continue with your Sleeper username</Text>
              </>
            ) : null}
            {appleToken ? (
              <View style={styles.appleLinkBlock}>
                <Text style={styles.appleLinkTitle}>Link your Sleeper username</Text>
                <Text style={styles.fieldHint}>
                  You're signed in with Apple — connect your Sleeper username
                  to load your leagues.
                </Text>
              </View>
            ) : null}
            {hint ? (
              <Pressable
                testID="signin.hint-btn"
                style={({ pressed }) => [
                  styles.hintRow,
                  pressed && styles.hintRowPressed,
                ]}
                onPress={() => {
                  setUsername(hint);
                  void handleSubmit(hint);
                }}
                disabled={busy}
              >
                <Text style={styles.hintLabel}>Continue as</Text>
                <Text style={styles.hintName}>@{hint}</Text>
              </Pressable>
            ) : null}
            <TextInput
              testID="signin.username-input"
              style={[styles.input, focused && styles.inputFocused]}
              placeholder={smartStartEnabled ? 'Sleeper username or league URL' : 'Sleeper username'}
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
            {smartStartEnabled ? (
              <Text style={styles.fieldHint}>
                Paste your Sleeper username or league URL.
              </Text>
            ) : null}
            {error ? <Text testID="signin.error-text" style={styles.error}>{error}</Text> : null}
            <Pressable
              testID="signin.continue-btn"
              accessibilityRole="button"
              style={({ pressed }) => [
                styles.button,
                pressed && !submitDisabled && styles.buttonPressed,
                submitDisabled && styles.buttonDisabled,
              ]}
              onPress={() => handleSubmit()}
              disabled={submitDisabled}
            >
              {busy ? (
                <ActivityIndicator color={ice.on} />
              ) : (
                <Text style={styles.buttonText}>Connect →</Text>
              )}
            </Pressable>

            {tryDemoEnabled ? (
              <Pressable
                testID="signin.demo-link"
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
                      Try the app on a sample league →
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
    </SafeAreaView>
  );
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
  // ── Sign in with Apple (auth.accounts) ─────────────────────────────────
  appleButton: {
    alignSelf: 'stretch',
    height: 44,
    marginBottom: space.md,
  },
  orDivider: {
    ...type.bodySm,
    color: chalk.faint,
    textAlign: 'center',
    marginBottom: space.md,
  },
  appleLinkBlock: {
    marginBottom: space.md,
  },
  appleLinkTitle: {
    ...type.title,
    marginBottom: space.xs,
  },
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

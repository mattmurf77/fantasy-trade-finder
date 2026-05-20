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
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { resolveSmartStart, signIn } from '../api/auth';
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
  const setUser = useSession((s) => s.setUser);
  const setLeagues = useSession((s) => s.setLeagues);
  const startDemoSession = useSession((s) => s.startDemoSession);
  const smartStartEnabled = useFlag('landing.smart_start_cta');
  const tryDemoEnabled    = useFlag('landing.try_before_sync');

  useEffect(() => {
    getLastUsername().then((u) => {
      if (u) {
        setUsername(u);
        setHint(u);
      }
    });
  }, []);

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

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <View style={styles.body}>
          <View style={styles.hero}>
            <Text style={styles.eyebrow}>
              <Text style={styles.eyebrowDot}>●  </Text>
              Dynasty Fantasy Football
            </Text>
            <Text style={styles.headline}>
              Your Rankings{' '}
              <Text style={styles.operator}>+</Text>
              {'\n'}Their Rankings{' '}
              <Text style={styles.operator}>=</Text>
              {'\n'}
              <Text style={styles.highlight}>Trades That Actually Work</Text>
            </Text>
            <Text style={styles.sub}>
              Compare your rankings to your leaguemates' and find trades where
              both sides come out ahead.
            </Text>
          </View>

          <View style={styles.form}>
            {hint ? (
              <Pressable
                style={({ pressed }) => [
                  styles.hintPill,
                  pressed && { opacity: 0.7 },
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
              style={styles.input}
              placeholder={smartStartEnabled ? 'Sleeper username or league URL' : 'Sleeper username'}
              placeholderTextColor="#3e4258"
              value={username}
              onChangeText={setUsername}
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
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <Pressable
              style={({ pressed }) => [
                styles.button,
                (busy || demoBusy || !username.trim()) && styles.buttonDisabled,
                pressed && styles.buttonPressed,
              ]}
              onPress={() => handleSubmit()}
              disabled={busy || demoBusy || !username.trim()}
            >
              {busy ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.buttonText}>Connect →</Text>
              )}
            </Pressable>

            {tryDemoEnabled ? (
              <Pressable
                onPress={handleTryDemo}
                disabled={busy || demoBusy}
                style={({ pressed }) => [
                  styles.tryDemoBtn,
                  pressed && { opacity: 0.6 },
                ]}
                hitSlop={8}
              >
                {demoBusy ? (
                  <ActivityIndicator color={colors.muted} />
                ) : (
                  <Text style={styles.tryDemoText}>
                    Try the app on a sample league →
                  </Text>
                )}
              </Pressable>
            ) : null}

            <View style={styles.taglines}>
              <Text style={styles.tagline}>📈 Rank</Text>
              <Text style={styles.taglineSep}>·</Text>
              <Text style={styles.tagline}>🔗 Match</Text>
              <Text style={styles.taglineSep}>·</Text>
              <Text style={styles.tagline}>🤝 Trade</Text>
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  body: {
    flex: 1,
    paddingHorizontal: spacing.xl,
    justifyContent: 'center',
  },
  hero: { marginBottom: spacing.xxl },
  eyebrow: {
    color: colors.green,
    fontSize: fontSize.sm,
    fontWeight: '700',
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
  },
  eyebrowDot: { color: colors.green, fontSize: 10 },
  headline: {
    color: colors.text,
    fontSize: fontSize.xxl,
    fontWeight: '800',
    lineHeight: 36,
    marginBottom: spacing.md,
  },
  operator: { color: colors.accent, fontWeight: '900' },
  highlight: { color: colors.accent },
  sub: {
    color: colors.muted,
    fontSize: fontSize.base,
    lineHeight: 22,
  },
  form: {},
  input: {
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    color: colors.text,
    fontSize: fontSize.base,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    marginBottom: spacing.sm,
  },
  error: {
    color: colors.red,
    fontSize: fontSize.sm,
    marginBottom: spacing.sm,
  },
  button: {
    backgroundColor: colors.accent,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  buttonPressed: { opacity: 0.85 },
  buttonDisabled: { opacity: 0.5 },
  buttonText: {
    color: '#fff',
    fontSize: fontSize.base,
    fontWeight: '700',
  },
  taglines: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: spacing.xl,
    gap: spacing.md,
  },
  tagline: {
    color: colors.text,
    fontSize: fontSize.sm,
    fontWeight: '600',
  },
  taglineSep: { color: colors.border },
  hintPill: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    backgroundColor: 'rgba(255,255,255,0.04)',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    marginBottom: spacing.md,
  },
  hintLabel: { color: colors.muted, fontSize: fontSize.sm },
  hintName: { color: colors.accent, fontSize: fontSize.base, fontWeight: '700' },
  fieldHint: {
    color: colors.muted,
    fontSize: fontSize.sm,
    marginTop: -spacing.xs,
    marginBottom: spacing.sm,
  },
  tryDemoBtn: {
    alignItems: 'center',
    paddingVertical: spacing.md,
    marginTop: spacing.sm,
  },
  tryDemoText: {
    color: colors.muted,
    fontSize: fontSize.sm,
    fontWeight: '600',
  },
});

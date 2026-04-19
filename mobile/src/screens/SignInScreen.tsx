import React, { useState } from 'react';
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
import { signIn } from '../api/auth';
import { useSession } from '../state/useSession';
import { getLeagues } from '../api/sleeper';

interface Props {
  onSignedIn: () => void;
}

// Sign-in: Sleeper username → POST /api/extension/auth.
// Same one-shot auth flow the Chrome extension uses. After success we
// prefetch the user's leagues so the next screen has data ready.
export default function SignInScreen({ onSignedIn }: Props) {
  const [username, setUsername] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const setUser = useSession((s) => s.setUser);
  const setLeagues = useSession((s) => s.setLeagues);

  async function handleSubmit() {
    if (busy) return;
    const trimmed = username.trim().toLowerCase();
    if (!trimmed) {
      setError('Enter your Sleeper username');
      return;
    }
    setBusy(true);
    setError(null);
    Keyboard.dismiss();
    try {
      const auth = await signIn(trimmed);
      await setUser({
        user_id: auth.user_id,
        username: auth.username,
        display_name: auth.display_name,
        avatar_id: auth.avatar ?? null,
      });
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
            <TextInput
              style={styles.input}
              placeholder="Sleeper username"
              placeholderTextColor="#3e4258"
              value={username}
              onChangeText={setUsername}
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="off"
              returnKeyType="go"
              onSubmitEditing={handleSubmit}
              editable={!busy}
              inputMode="text"
            />
            {error ? <Text style={styles.error}>{error}</Text> : null}
            <Pressable
              style={({ pressed }) => [
                styles.button,
                (busy || !username.trim()) && styles.buttonDisabled,
                pressed && styles.buttonPressed,
              ]}
              onPress={handleSubmit}
              disabled={busy || !username.trim()}
            >
              {busy ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.buttonText}>Connect →</Text>
              )}
            </Pressable>

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
});

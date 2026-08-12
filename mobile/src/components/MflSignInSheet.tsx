import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Modal,
  TextInput,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { ink, chalk, semantic, space, radii, type, shadowSheet, scrim } from '../theme/chalkline';
import { Button } from './chalkline';
import { ApiError } from '../api/client';
import { mflAuthLink } from '../api/platformLink';

// Focused MFL sign-in sheet (send-auth lazy flow, 2026-08-11). The full MFL
// sign-in previously lived ONLY inside PlatformLinkSheet on the league
// picker ("Add league" → MFL → Sign in) — a dead end for a user mid-send.
// This sheet is the in-flow equivalent for surfaces that just need the
// CREDENTIAL (POST /api/mfl/auth-link stores the MFL session cookie and
// verifies the FTF session): no league list, no import step — the league is
// already linked. Mounted by SendInMflButton; PlatformLinkSheet keeps its
// own richer flow for actual league linking.
//
// Password handling matches PlatformLinkSheet exactly: component state just
// long enough for the ONE auth-link call (the backend uses it for MFL's
// login and never stores or logs it), cleared the moment the call returns.

interface Props {
  visible: boolean;
  onClose: () => void;
  /** Fired after MFL accepts the sign-in (credential stored server-side,
   *  session verified). The caller resumes whatever needed the sign-in. */
  onSignedIn: () => void;
}

export default function MflSignInSheet({ visible, onClose, onSignedIn }: Props) {
  const [user, setUser] = useState('');
  const [pass, setPass] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function close() {
    if (busy) return;
    setPass('');
    setError(null);
    onClose();
  }

  async function signIn() {
    if (!user.trim() || !pass) {
      setError('Enter your MFL username and password.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await mflAuthLink(user.trim(), pass);
      setPass(''); // transient — done with it the moment the call returns
      onSignedIn();
    } catch (e: any) {
      setPass('');
      if (e instanceof ApiError && (e.body as any)?.error === 'mfl_bad_credentials') {
        setError("MFL didn't accept that username and password.");
      } else if (e instanceof ApiError && e.isVerificationRequired) {
        setError('Verify your account first — sign in from Settings.');
      } else {
        setError(e?.message || "Couldn't reach MFL — try again shortly.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={close}>
      <Pressable
        style={styles.backdrop}
        onPress={close}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.kav}
      >
        <View style={styles.sheet}>
          <View style={styles.grabber} />
          <Text style={type.heading} accessibilityRole="header">
            Sign in with MFL
          </Text>
          <Text style={[type.bodySm, styles.sub]}>
            Sending trades needs your MyFantasyLeague sign-in. Your password
            goes to MFL&rsquo;s login only — we keep just the session it
            returns, never the password.
          </Text>
          <TextInput
            testID="mfl-signin.username"
            style={styles.field}
            value={user}
            onChangeText={setUser}
            placeholder="MFL username"
            placeholderTextColor={chalk.dim}
            autoCapitalize="none"
            autoCorrect={false}
            editable={!busy}
          />
          <TextInput
            testID="mfl-signin.password"
            style={styles.field}
            value={pass}
            onChangeText={setPass}
            placeholder="MFL password"
            placeholderTextColor={chalk.dim}
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry
            textContentType="password"
            editable={!busy}
          />
          {error ? (
            <Text testID="mfl-signin.error" style={styles.error}>
              {error}
            </Text>
          ) : null}
          <Button
            testID="mfl-signin.submit"
            label={busy ? 'Signing in…' : 'Sign in'}
            onPress={() => {
              void signIn();
            }}
            disabled={busy}
            style={styles.cta}
          />
          <Button
            testID="mfl-signin.cancel"
            label="Cancel"
            variant="ghost"
            onPress={close}
            disabled={busy}
            style={styles.cancel}
          />
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  kav: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    maxHeight: '88%',
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  sub: { marginBottom: space.xs, color: chalk.dim },
  field: {
    ...type.body,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minHeight: 44,
    color: chalk.base,
  },
  error: { ...type.bodySm, color: semantic.neg },
  cta: { marginTop: space.sm },
  cancel: { marginTop: space.xs },
});

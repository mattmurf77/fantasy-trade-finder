import React, { useState } from 'react';
import { Modal, View, Text, Pressable, ActivityIndicator, StyleSheet } from 'react-native';
import * as AppleAuthentication from 'expo-apple-authentication';
import { ink, chalk, space, radii, type, fonts, scrim } from '../theme/chalkline';
import { TickLabel } from './chalkline';
import { appleSignIn } from '../api/auth';
import { useSession } from '../state/useSession';
import { useInterruptCoordinator } from '../state/useInterruptCoordinator';
import { useFlag } from '../state/useFeatureFlags';

interface Props {
  visible: boolean;
  /** Which save-moment class fired this ask (analytics + one-per-class policy). */
  trigger: 'like' | 'quickset_save' | 'session2_banner';
  /** Called on any resolution. `bound` true only after a successful link. */
  onClose: (bound: boolean) => void;
}

// Save-moment Apple ask (onboarding plan item 8, flag
// onboarding.apple_save_moment; ADR-006 + operator direction 2026-07-19).
// Rankings-first value prop: "save your rankings to your account" — TRUE
// (the bind writes the board to a durable account and mints the verified-
// controller lock that blocks squatters). Still prohibited: implying the
// board is LOST without Apple (it persists keyed to the Sleeper user).
// Decline is one tap, recorded by the caller, never immediately re-asked.
//
// Bind flow mirrors SettingsScreen.handleLinkApple: with a live session the
// backend binds this Apple identity to the session's Sleeper user and marks
// it verified (P2 outcome a). Sticky-bind conflicts surface honestly.
export default function AppleSaveMomentSheet({ visible, trigger, onClose }: Props) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const setVerification = useSession((s) => s.setVerification);
  const verification = useSession((s) => s.verification);
  // S4 PRD-04 (`ux.prompt_arbiter`): root modals self-defer while any
  // instructional surface holds the arbiter slot — the caller's `visible`
  // stays true, so the sheet presents the moment the slot frees instead of
  // stacking over an open banner/prompt. Flag off: passthrough.
  const arbiterOn = useFlag('ux.prompt_arbiter');
  const surfaceBusy = useInterruptCoordinator((s) => s.activeSurface !== null);
  const effectiveVisible = visible && !(arbiterOn && surfaceBusy);

  async function handleApple() {
    if (busy) return;
    setBusy(true);
    setNote(null);
    try {
      const cred = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
      });
      if (!cred.identityToken) throw new Error('Apple did not return an identity token.');
      const res = await appleSignIn(cred.identityToken);
      if (res.conflict) {
        setNote('That Apple ID is already linked to a different account.');
        setBusy(false);
        return;
      }
      if (res.linked) {
        setVerification({
          session_verified: true,
          user_verified: true,
          verified_via: res.verified_via || 'apple',
          enforced: verification?.enforced ?? false,
        });
        setBusy(false);
        onClose(true);
        return;
      }
      // No live session server-side — rare here (we were just swiping).
      // Treat as a soft failure; the Settings row remains the fallback.
      setNote('Linking hiccuped — you can finish anytime in Settings → Account.');
      setBusy(false);
    } catch (err: any) {
      setBusy(false);
      if (err?.code === 'ERR_REQUEST_CANCELED') {
        // Canceling Apple's own dialog is a decline, not an error.
        onClose(false);
        return;
      }
      setNote(err?.message || 'Apple sign-in failed. Try again.');
    }
  }

  return (
    <Modal visible={effectiveVisible} transparent animationType="fade" onRequestClose={() => onClose(false)}>
      <View style={styles.scrim}>
        <View testID={`trades.apple-sheet.${trigger}`} style={styles.sheet}>
          <TickLabel>Your front office</TickLabel>
          <Text style={styles.title}>Save your rankings.</Text>
          <Text style={styles.body}>
            Sign in with Apple to save your board to your account — and lock
            it so only you can change it.
          </Text>
          {note ? <Text style={styles.note}>{note}</Text> : null}
          <AppleAuthentication.AppleAuthenticationButton
            testID="trades.apple-sheet.signin"
            buttonType={AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN}
            buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.WHITE}
            cornerRadius={radii.sm}
            style={styles.appleButton}
            onPress={() => void handleApple()}
          />
          {busy ? <ActivityIndicator color={chalk.dim} /> : null}
          <Pressable
            testID="trades.apple-sheet.decline"
            onPress={() => onClose(false)}
            disabled={busy}
            hitSlop={8}
            style={styles.decline}
          >
            {({ pressed }) => (
              <Text style={[styles.declineText, pressed && styles.declineTextPressed]}>
                Not now
              </Text>
            )}
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: {
    flex: 1,
    backgroundColor: scrim,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
  },
  sheet: {
    alignSelf: 'stretch',
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.md,
    padding: space.xl,
    gap: space.md,
  },
  title: { ...type.heading },
  body: { ...type.body, color: chalk.dim },
  note: { ...type.bodySm, color: chalk.dim, fontFamily: fonts.uiSemi },
  appleButton: { alignSelf: 'stretch', height: 44, marginTop: space.sm },
  decline: { minHeight: 36, alignItems: 'center', justifyContent: 'center' },
  declineText: { ...type.bodySm, fontFamily: fonts.uiSemi },
  declineTextPressed: { color: chalk.base },
});

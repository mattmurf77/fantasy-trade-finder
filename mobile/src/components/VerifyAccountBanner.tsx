import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';
import { useSession } from '../state/useSession';

// "Verify your account" — account-auth P1 (docs/plans/account-auth-plan-
// 2026-07-11.md §3-P1 client). A quiet, dismissible strip mounted once at
// the authed root (RootNav → Main), shown ONLY when the server says this
// session is unverified AND it matters:
//   * someone has already verified this user_id (this session has lost
//     write access — the squatter/second-device case), or
//   * the grace period is over (enforcement on) so writes will 403.
// During plain grace with no verified controller it stays hidden — no nag.
// Tapping "Verify" routes into the existing SleeperConnectScreen capture,
// which doubles as the verification proof. Dismissal is per-launch
// (in-memory) so it returns quietly next launch.
//
// Chalkline: ink-1 surface, hairline border, dim body copy — informational,
// not a modal, no motion.

interface Props {
  onVerify: () => void;
}

export default function VerifyAccountBanner({ onVerify }: Props) {
  const insets = useSafeAreaInsets();
  const verification = useSession((s) => s.verification);
  const dismissed = useSession((s) => s.verifyBannerDismissed);
  const dismiss = useSession((s) => s.dismissVerifyBanner);
  const isDemo = useSession((s) => s.isDemo);

  if (
    isDemo ||
    dismissed ||
    !verification ||
    verification.session_verified ||
    !(verification.user_verified || verification.enforced)
  ) {
    return null;
  }

  // #126: post-replay this banner appears only when the silent replay
  // couldn't succeed (no stored token on this device, dead/expired token,
  // or Sleeper unreachable) — the copy covers all three truthfully.
  const copy = verification.user_verified
    ? "We couldn't confirm your Sleeper login on this device. Reconnect to keep editing your ranks."
    : 'Verify with your Sleeper login to keep editing your ranks.';

  return (
    <View
      // Floats just above the bottom tab bar (same anchoring approach as
      // FeedbackFAB) so it never displaces screen content.
      style={[styles.banner, { bottom: insets.bottom + 56 }]}
      testID="main.verify-banner"
    >
      <View style={styles.textCol}>
        <Text style={styles.title}>Verify your account</Text>
        <Text style={[type.bodySm, styles.body]}>{copy}</Text>
      </View>
      <Pressable
        onPress={onVerify}
        style={({ pressed }) => [styles.btn, pressed && styles.btnPressed]}
        accessibilityRole="button"
        accessibilityLabel="Verify your account"
        testID="main.verify-banner.verify"
      >
        <Text style={styles.btnText}>Verify</Text>
      </Pressable>
      <Pressable
        onPress={dismiss}
        style={({ pressed }) => [styles.dismiss, pressed && styles.btnPressed]}
        accessibilityRole="button"
        accessibilityLabel="Dismiss verify reminder"
        hitSlop={8}
        testID="main.verify-banner.dismiss"
      >
        <Text style={styles.dismissText}>×</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    position: 'absolute',
    left: space.md,
    right: space.md,
    // bottom set dynamically with the safe-area inset
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radii.md,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
  },
  textCol: { flex: 1, gap: 2 },
  title: {
    ...type.bodySm,
    fontFamily: fonts.uiSemi,
    color: chalk.base,
  },
  body: { color: chalk.dim },
  btn: {
    minHeight: 36,
    minWidth: 44,
    paddingHorizontal: space.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
  },
  btnPressed: { backgroundColor: ink.ink3 },
  btnText: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
    color: ice.base,
  },
  dismiss: {
    minHeight: 36,
    minWidth: 32,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
  },
  dismissText: {
    fontFamily: fonts.uiSemi,
    fontSize: 18,
    lineHeight: 22,
    color: chalk.dim,
  },
});

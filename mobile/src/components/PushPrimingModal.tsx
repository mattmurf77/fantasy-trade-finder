import React from 'react';
import { Modal, View, Text, Pressable, StyleSheet } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import { usePushPriming } from '../state/usePushPriming';

// Pre-permission priming sheet. Shown once when usePushNotifications detects
// the iOS permission is `undetermined` AND the user has progressed far
// enough to benefit from pushes (rankings unlocked → first match imminent).
//
// Two outcomes:
//   Enable now  → calls the registered handler which triggers the iOS prompt
//   Maybe later → dismisses the sheet without prompting. Re-asked next session.
export default function PushPrimingModal() {
  const pending = usePushPriming((s) => s.pending);
  const acceptHandler = usePushPriming((s) => s.acceptHandler);
  const dismiss = usePushPriming((s) => s.dismiss);

  const accept = async () => {
    if (acceptHandler) await acceptHandler();
  };

  return (
    <Modal
      visible={pending}
      transparent
      animationType="fade"
      onRequestClose={dismiss}
    >
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <Text style={styles.emoji}>🔔</Text>
          <Text style={styles.title}>Get pinged when a trade match drops</Text>
          <Text style={styles.body}>
            We'll let you know when:{"\n"}
            • A new trade match is generated for you{"\n"}
            • A leaguemate counters your offer{"\n"}
            • A match is about to expire
          </Text>
          <Text style={styles.fine}>
            Quiet hours (10pm–8am local) bundle overnight pings into one
            morning summary. Customize anytime in Settings.
          </Text>
          <Pressable
            onPress={accept}
            style={({ pressed }) => [styles.primary, pressed && { opacity: 0.85 }]}
          >
            <Text style={styles.primaryText}>Enable notifications</Text>
          </Pressable>
          <Pressable onPress={dismiss} style={styles.secondary}>
            <Text style={styles.secondaryText}>Maybe later</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.66)',
    justifyContent: 'center',
    padding: spacing.lg,
  },
  card: {
    backgroundColor: colors.bg,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.xl,
    gap: spacing.sm,
  },
  emoji: { fontSize: 36, alignSelf: 'center', marginBottom: spacing.xs },
  title: {
    color: colors.text,
    fontSize: fontSize.xl,
    fontWeight: '800',
    textAlign: 'center',
  },
  body: {
    color: colors.text,
    fontSize: fontSize.base,
    lineHeight: 22,
    marginTop: spacing.xs,
  },
  fine: {
    color: colors.muted,
    fontSize: fontSize.xs,
    lineHeight: 18,
    marginTop: spacing.xs,
    marginBottom: spacing.md,
  },
  primary: {
    backgroundColor: colors.accent,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    alignItems: 'center',
  },
  primaryText: { color: '#0b1020', fontWeight: '800', fontSize: fontSize.base },
  secondary: {
    paddingVertical: spacing.md,
    alignItems: 'center',
  },
  secondaryText: { color: colors.muted, fontWeight: '700', fontSize: fontSize.sm },
});

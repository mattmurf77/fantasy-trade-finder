import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';
import { TickLabel } from './chalkline';

interface Props {
  onAccept: () => void;
  onDismiss: () => void;
}

// Contextual Quick Set prompt (onboarding plan item 7, flag
// onboarding.quickset_prompt). Rendered INLINE in the Trades deck area —
// card grammar, never a modal. Copy is voice-doc verbatim (Assistant GM,
// docs/business/marketing/2026-07-17-assistant-gm-voice.md #8). Dismiss is
// a snooze by contract — "dismissed forever" must not exist (review F10);
// the caller owns the snooze/re-offer bookkeeping.
//
// Spec deviation, on purpose: the review asked for "same gesture grammar"
// (swipeable). Wiring a non-trade card into the swipe mutation path would
// special-case every disposition handler, so v1 uses explicit actions —
// primary CTA + a quiet "Not now". Revisit only if prompt-dismiss data
// says the buttons underperform.
export default function QuickSetPromptCard({ onAccept, onDismiss }: Props) {
  return (
    <View testID="trades.quickset-prompt" style={styles.card}>
      <TickLabel>Your board</TickLabel>
      <Text style={styles.title}>These trades use consensus values.</Text>
      <Text style={styles.body}>
        Your board would find better ones. Fix one position in 2 minutes →
      </Text>
      <Pressable
        testID="trades.quickset-prompt.accept"
        accessibilityRole="button"
        style={({ pressed }) => [styles.cta, pressed && styles.ctaPressed]}
        onPress={onAccept}
      >
        <Text style={styles.ctaText}>Fix one position →</Text>
      </Pressable>
      <Pressable
        testID="trades.quickset-prompt.dismiss"
        onPress={onDismiss}
        hitSlop={8}
        style={styles.dismiss}
      >
        {({ pressed }) => (
          <Text style={[styles.dismissText, pressed && styles.dismissTextPressed]}>
            Not now
          </Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.md,
    padding: space.xl,
    gap: space.md,
  },
  title: { ...type.heading },
  body: { ...type.body, color: chalk.dim },
  cta: {
    height: 44,
    backgroundColor: ice.base,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: space.sm,
  },
  ctaPressed: { backgroundColor: ice.press },
  ctaText: { color: ice.on, fontFamily: fonts.uiSemi, fontSize: 14 },
  dismiss: {
    minHeight: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dismissText: { ...type.bodySm, fontFamily: fonts.uiSemi },
  dismissTextPressed: { color: chalk.base },
});

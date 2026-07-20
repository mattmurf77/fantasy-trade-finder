import React from 'react';
import { Text, Pressable, StyleSheet } from 'react-native';
import { ink, chalk, space, radii, type } from '../theme/chalkline';
import { Icon } from './chalkline';

// Coach mark (onboarding guided layer, v2.1 — docs/plans/onboarding-
// conversion/plan.md): a one-time, inline, always-dismissible callout.
// Never modal, never stacked with another mark — callers own the ≤4-marks /
// shown-once bookkeeping (ftf_onboarding_state.coachMarksShown) and the
// coach_mark_shown / coach_mark_dismissed events.

interface Props {
  text: string;
  onDismiss: () => void;
  testID?: string;
}

export default function CoachMark({ text, onDismiss, testID }: Props) {
  return (
    <Pressable
      testID={testID}
      onPress={onDismiss}
      // S8 PRD-02 — instructional "Tap to dismiss" moves from the label
      // (name) into the hint, per the label/hint split.
      accessibilityRole="button"
      accessibilityLabel={text}
      accessibilityHint="Tap to dismiss"
      style={({ pressed }) => [styles.mark, pressed && styles.markPressed]}
    >
      <Text style={styles.text}>{text}</Text>
      <Icon name="x" size={14} color={chalk.dim} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  // Sheet-tier surface without the modal: ink-2 + interactive border.
  mark: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: ink.ink2,
  },
  markPressed: {
    backgroundColor: ink.ink3,
  },
  text: {
    ...type.bodySm,
    color: chalk.base,
    flex: 1,
  },
});

import React from 'react';
import { Modal, View, Text, StyleSheet } from 'react-native';
import {
  ink,
  chalk,
  space,
  radii,
  type,
  scrim,
  shadowSheet,
} from '../theme/chalkline';
import { Button, Icon } from './chalkline';
import { usePushPriming } from '../state/usePushPriming';
import { useInterruptCoordinator } from '../state/useInterruptCoordinator';
import { useFlag } from '../state/useFeatureFlags';
import { track } from '../api/events';

// Pre-permission priming sheet. Shown once when usePushNotifications detects
// the iOS permission is `undetermined` AND the user has progressed far
// enough to benefit from pushes (rankings unlocked → first match imminent).
//
// Two outcomes:
//   Enable now  → calls the registered handler which triggers the iOS prompt
//   Maybe later → dismisses the sheet without prompting. With
//     `ux.prompt_arbiter` on, declines persist and the primer re-arms only
//     after 3+ sessions or a want-it moment (see usePushPriming); flag off,
//     it re-asks next session as before.
//
// S4 PRD-04 (`ux.prompt_arbiter`): as a root modal this SELF-DEFERS while
// any instructional surface holds the arbiter slot — `pending` stays true,
// so the sheet appears the moment the slot frees instead of stacking.
export default function PushPrimingModal() {
  const pending = usePushPriming((s) => s.pending);
  const acceptHandler = usePushPriming((s) => s.acceptHandler);
  const dismiss = usePushPriming((s) => s.dismiss);
  const arbiterOn = useFlag('ux.prompt_arbiter');
  const surfaceBusy = useInterruptCoordinator((s) => s.activeSurface !== null);

  const accept = async () => {
    if (arbiterOn) track('push_primer_accepted');
    if (acceptHandler) await acceptHandler();
  };

  return (
    <Modal
      visible={pending && !(arbiterOn && surfaceBusy)}
      transparent
      animationType="fade"
      onRequestClose={dismiss}
    >
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <View style={styles.iconWrap}>
            <Icon name="bell" size={28} color={chalk.base} />
          </View>
          <Text style={styles.title}>Get pinged when a trade match drops</Text>
          {/* Copy correction (W1B handoff, unflagged): "counters your offer"
              promised a push kind that never fires — the real trigger is a
              leaguemate accepting your match. */}
          <Text style={styles.body}>
            We'll let you know when:{"\n"}
            • A new trade match is generated for you{"\n"}
            • A leaguemate accepts your match{"\n"}
            • A match is about to expire
          </Text>
          <Text style={styles.fine}>
            Quiet hours (10pm–8am local) bundle overnight pings into one
            morning summary. Customize anytime in Settings.
          </Text>
          <Button label="Enable notifications" onPress={accept} />
          <Button variant="ghost" label="Maybe later" onPress={dismiss} />
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: scrim,
    justifyContent: 'center',
    padding: space.lg,
  },
  card: {
    backgroundColor: ink.ink2,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    padding: space.xl,
    gap: space.sm,
    ...shadowSheet,
  },
  iconWrap: { alignSelf: 'center', marginBottom: space.xs },
  title: {
    ...type.heading,
    textAlign: 'center',
  },
  body: {
    ...type.body,
    marginTop: space.xs,
  },
  fine: {
    ...type.bodySm,
    marginTop: space.xs,
    marginBottom: space.md,
  },
});

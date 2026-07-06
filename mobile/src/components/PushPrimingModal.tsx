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
          <View style={styles.iconWrap}>
            <Icon name="bell" size={28} color={chalk.base} />
          </View>
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

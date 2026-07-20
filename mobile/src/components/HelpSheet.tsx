import React from 'react';
import { Linking, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button } from './chalkline';
import { useReducedMotionSafe } from '../hooks/useReducedMotionSafe';
import {
  chalk,
  ink,
  radii,
  scrim,
  shadowSheet,
  space,
  type,
} from '../theme/chalkline';
import { track } from '../api/events';

// In-app help surface (teardown S4 PRD-01, flag `ux.help_surface`).
// A lightweight Chalkline bottom sheet: 2–3 sentences answering the doubt
// IN PLACE, plus a "Read more" link to the full web article. Opened from
// `InfoButton` ⓘ affordances at high-doubt moments (trade fairness meter,
// Matches empty state; the Settings Help row is W2C's).
//
// Slide falls back to fade under Reduce Motion (`useReducedMotionSafe`).

interface Props {
  visible: boolean;
  title: string;
  body: string;
  /** Full web article; opens in the system browser. */
  readMoreUrl?: string;
  /** Analytics id, e.g. 'trade_pricing' / 'matching'. */
  topic?: string;
  onClose: () => void;
}

export default function HelpSheet({
  visible,
  title,
  body,
  readMoreUrl,
  topic,
  onClose,
}: Props) {
  const reduceMotion = useReducedMotionSafe();
  return (
    <Modal
      visible={visible}
      transparent
      animationType={reduceMotion ? 'fade' : 'slide'}
      onRequestClose={onClose}
    >
      <Pressable style={styles.backdrop} onPress={onClose} accessibilityLabel="Close" />
      <View style={styles.sheet} testID="help-sheet">
        <SafeAreaView edges={['bottom']}>
          <View style={styles.grabber} />
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.body}>{body}</Text>
          <View style={styles.actions}>
            {readMoreUrl ? (
              <Button
                variant="secondary"
                label="Read more"
                onPress={() => {
                  track('help_read_more_tapped', { topic });
                  Linking.openURL(readMoreUrl).catch(() => {});
                }}
                style={styles.actionBtn}
              />
            ) : null}
            <Button variant="ghost" label="Close" onPress={onClose} style={styles.actionBtn} />
          </View>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

// ⓘ affordance — 44pt effective hit target around a 18px glyph (Chalkline
// stroke construction; local Svg to stay conflict-free with parallel
// chalkline owners — fold into chalkline/Icon at flag cleanup).
export function InfoButton({
  onPress,
  label,
  size = 18,
  color = chalk.dim,
  testID,
}: {
  onPress: () => void;
  /** VoiceOver label, e.g. "How trades are priced". */
  label: string;
  size?: number;
  color?: string;
  testID?: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      hitSlop={{
        top: (44 - size) / 2,
        bottom: (44 - size) / 2,
        left: (44 - size) / 2,
        right: (44 - size) / 2,
      }}
      style={({ pressed }) => [styles.infoBtn, pressed && { opacity: 0.6 }]}
    >
      <Svg
        width={size}
        height={size}
        viewBox="0 0 20 20"
        fill="none"
        stroke={color}
        strokeWidth={1.75}
        strokeLinecap="square"
      >
        <Circle cx={10} cy={10} r={7.5} />
        <Path d="M10 9v5M10 6v.5" />
      </Svg>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    paddingHorizontal: space.xl,
    paddingBottom: space.md,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
    marginBottom: space.md,
  },
  title: { ...type.heading },
  body: { ...type.body, color: chalk.dim, marginTop: space.sm, lineHeight: 22 },
  actions: { flexDirection: 'row', gap: space.sm, marginTop: space.lg },
  actionBtn: { flex: 1 },
  infoBtn: { alignItems: 'center', justifyContent: 'center' },
});

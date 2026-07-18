import React from 'react';
import { View, Text, Image, Pressable, StyleSheet } from 'react-native';
import { ink, chalk, ice, space, radii, type, fonts } from '../theme/chalkline';
import { Icon } from './chalkline';

// Identity-confirm strip (onboarding item 4, accepted F5): first-run-only
// one-liner in the Trades header area. A valid-but-wrong Sleeper username
// silently loads a stranger's team — this is the escape hatch, and it also
// gates the later Apple bind (plan step 3). "not you?" is the action (ice);
// the X hides it for the session. The evergreen Settings affordance is
// item 8's scope.

interface Props {
  username: string;
  avatarId: string | null;
  /** Opens the caller's confirm dialog → sign-out path. */
  onNotYou: () => void;
  /** Hide for the rest of the session. */
  onDismiss: () => void;
}

export default function IdentityConfirmStrip({
  username,
  avatarId,
  onNotYou,
  onDismiss,
}: Props) {
  return (
    <View testID="trades.identity-strip" style={styles.strip}>
      {avatarId ? (
        <Image
          source={{ uri: `https://sleepercdn.com/avatars/thumbs/${avatarId}` }}
          style={styles.avatar}
        />
      ) : null}
      <Text style={styles.text} numberOfLines={1}>
        {'Trading as '}
        <Text style={styles.name}>@{username}</Text>
        {' — '}
        <Text
          testID="trades.identity-strip.switch"
          accessibilityRole="button"
          style={styles.action}
          onPress={onNotYou}
        >
          not you?
        </Text>
      </Text>
      <Pressable
        testID="trades.identity-strip.dismiss"
        accessibilityRole="button"
        accessibilityLabel="Dismiss"
        onPress={onDismiss}
        hitSlop={8}
        style={({ pressed }) => [styles.dismiss, pressed && styles.dismissPressed]}
      >
        <Icon name="x" size={14} color={chalk.dim} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  strip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 40,
    paddingHorizontal: space.md,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  avatar: {
    width: 20,
    height: 20,
    borderRadius: radii.xs,
    backgroundColor: ink.ink3,
  },
  text: {
    ...type.bodySm,
    flex: 1,
  },
  name: {
    color: chalk.base,
    fontFamily: fonts.uiSemi,
  },
  action: {
    color: ice.base,
    fontFamily: fonts.uiSemi,
  },
  dismiss: {
    width: 28,
    height: 28,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dismissPressed: {
    backgroundColor: ink.ink3,
  },
});

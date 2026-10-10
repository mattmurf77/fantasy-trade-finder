import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { Badge, Icon, Text, type IconName } from '../chalkline';
import { chalk, flare, ink, radii, space, type } from '../../theme/chalkline';

// One "Get things done" task tile (scope.md D4): full width, ~58pt, one
// format for all five — icon well, title, one detail line, optional flare
// count badge, chevron. The whole tile is the button. Prop-driven: the hub
// owns the analytics and the navigation.

interface Props {
  testID: string;
  icon: IconName;
  title: string;
  detail: string;
  /** Informational count ("2 mutual") — flare, never an action colour. */
  badge?: string | null;
  onPress: () => void;
}

export default function TaskTile({ testID, icon, title, detail, badge, onPress }: Props) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${title}. ${detail}${badge ? `. ${badge}` : ''}`}
      style={({ pressed }) => [styles.tile, pressed && styles.pressed]}
    >
      <View style={styles.well}>
        <Icon name={icon} />
      </View>
      <View style={styles.text}>
        <Text style={type.title}>{title}</Text>
        <Text style={type.bodySm}>{detail}</Text>
      </View>
      {/* Wrapped: Badge pins itself with alignSelf flex-start, which in this
          row would lift it to the top edge instead of centring it. */}
      {badge ? (
        <View>
          <Badge label={badge} color={flare.base} colorText />
        </View>
      ) : null}
      <Icon name="chevron-right" size={16} color={chalk.dim} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  tile: {
    minHeight: 58,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
  },
  pressed: { backgroundColor: ink.ink3 },
  well: {
    width: 40,
    height: 40,
    borderRadius: radii.sm,
    backgroundColor: ink.ink2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  text: { flex: 1, minWidth: 0 },
});

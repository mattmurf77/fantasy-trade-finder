// Toggle row — Chalkline hairline row with a title, optional sub copy, and a
// trailing Switch.
//
// Lifted verbatim from SettingsScreen.tsx's private `Row` helper (origin/main
// @ ecdbcb3, :1561). It was never exported, so the Phase-0 section extraction
// produced three byte-identical copies (AccountData / Guide / Notifications);
// this is the single owner they all import.
//
// The accessibility pairing is load-bearing: a bare Switch announces with no
// name, which is what S8 PRD-02 was raised against. Title becomes the label,
// sub copy becomes the hint.

import React from 'react';
import { View, Text, Switch } from 'react-native';

import { ink, chalk, ice, space } from '../../theme/chalkline';
import { styles } from './styles';

export default function Row({
  title, sub, value, onChange, testID,
}: {
  title: string;
  sub?: string;
  value: boolean;
  onChange: () => void;
  testID?: string;
}) {
  return (
    <View style={styles.row}>
      <View style={{ flex: 1, paddingRight: space.md }}>
        <Text style={styles.rowKey}>{title}</Text>
        {sub ? <Text style={styles.rowSub}>{sub}</Text> : null}
      </View>
      <Switch
        testID={testID}
        value={value}
        onValueChange={onChange}
        // S8 PRD-02 — the bare Switch announced with no name; pair it
        // with the visible row title (+ sub copy as the hint).
        accessibilityLabel={title}
        accessibilityHint={sub}
        trackColor={{ false: ink.ink3, true: ice.base }}
        thumbColor={chalk.base}
      />
    </View>
  );
}

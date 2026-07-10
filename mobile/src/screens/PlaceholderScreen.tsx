import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ink, type, space } from '../theme/chalkline';

interface Props {
  title: string;
  note?: string;
}

// Temporary placeholder used by the tab navigator until the real screens
// (RankScreen, TiersScreen, TradesScreen, MatchesScreen) land in later phases.
export default function PlaceholderScreen({ title, note }: Props) {
  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.body}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.note}>
          {note || 'This screen is coming in a later phase of the mobile rollout.'}
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  body: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl },
  title: { ...type.heading, marginBottom: space.md },
  note: { ...type.bodySm, textAlign: 'center' },
});

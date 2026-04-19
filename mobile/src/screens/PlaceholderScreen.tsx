import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '../theme/colors';
import { spacing, fontSize } from '../theme/spacing';

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
  safe: { flex: 1, backgroundColor: colors.bg },
  body: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  title: { color: colors.text, fontSize: fontSize.xxl, fontWeight: '800', marginBottom: spacing.md },
  note: { color: colors.muted, fontSize: fontSize.base, textAlign: 'center', lineHeight: 22 },
});

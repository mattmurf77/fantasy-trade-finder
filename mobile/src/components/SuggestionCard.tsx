import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import PositionChip from './PositionChip';
import { Icon } from './chalkline';
import { CalcSuggestion, CALC_VERDICT_LABEL, formatDelta } from '../utils/tradeCalcMath';
import { ink, chalk, semantic, type, space, radii } from '../theme/chalkline';

interface Props {
  suggestion: CalcSuggestion;
  onApply: () => void;
}

// One suggested fair package in the Trade Calculator — tap to apply it to
// the open side of the trade. Follows the Chalkline Card pattern (ink-1
// surface + hairline, radius md) composed on a Pressable since the Card
// primitive isn't tappable.
export default function SuggestionCard({ suggestion, onApply }: Props) {
  const { players, evaluation } = suggestion;
  const winWin = evaluation.verdict === 'WIN_WIN';
  const verdictColor = winWin ? semantic.pos : chalk.base;
  return (
    <Pressable
      style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
      onPress={onApply}
      accessibilityRole="button"
    >
      <View style={styles.players}>
        {players.map((p) => (
          <View key={p.id} style={styles.playerRow}>
            <PositionChip position={p.pos} size="sm" />
            <Text style={styles.name}>{p.name}</Text>
          </View>
        ))}
      </View>
      <View style={styles.right}>
        <Text style={[type.label, { color: verdictColor }]}>
          {CALC_VERDICT_LABEL[evaluation.verdict]}
        </Text>
        <Text style={styles.deltas}>
          you {formatDelta(evaluation.myDeltaPct)} · them {formatDelta(evaluation.theirDeltaPct)}
        </Text>
        <View style={styles.applyRow}>
          <Text style={styles.apply}>Use this</Text>
          <Icon name="chevron-right" size={16} />
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    backgroundColor: ink.ink1,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    padding: space.md,
    gap: space.md,
    alignItems: 'center',
  },
  cardPressed: { backgroundColor: ink.ink3 },
  players: { flex: 1, gap: space.xs },
  playerRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  name: { ...type.body, flexShrink: 1 },
  right: { alignItems: 'flex-end', gap: 2 },
  deltas: { ...type.data, color: chalk.dim },
  applyRow: { flexDirection: 'row', alignItems: 'center', gap: space.xs, marginTop: 2 },
  apply: { ...type.bodySm },
});

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ink, chalk, semantic, space, radii, type } from '../../theme/chalkline';
import { Text, Badge, Icon, Button } from '../chalkline';
import {
  BAND_LABEL,
  type ConfidenceBand,
  type ConfidenceCap,
} from '../../utils/tradePresentation';

// ConfidenceChip + ConfidenceCapNote — three labeled bands, NEVER a
// percentage. Flag `trades.presentation_v2`; approved lab
// mockups/trade-suggestion-redesign/04-confidence.html.
//
// The OkCupid lower-bound rule: displayed confidence is capped by data
// volume, and the cap is expressed in LANGUAGE, not by shrinking a number.
// Two shared answers can never render "94%". At FTF's N a two-digit
// percentage is a lie with a decimal point in it, so this component has no
// numeric prop at all — the band enum is the whole input, which makes
// "just show the score" impossible without a type change.
//
// Colour encoding matches the lab: pos border for Strong, default border +
// dim text for Moderate, hairline border + faint text for Early. Border
// carries the encoding and the text stays chalk, per the Badge construction.

export function ConfidenceChip({ band }: { band: ConfidenceBand }) {
  const color =
    band === 'strong' ? semantic.pos : band === 'moderate' ? ink.lineStrongA11y : ink.line;
  return (
    <View testID={`presentation.confidence.${band}`}>
      <Badge label={BAND_LABEL[band]} color={color} colorText={band === 'strong'} />
    </View>
  );
}

/**
 * The data-volume ceiling, rendered under a capped card. Shows the honest
 * board-coverage track (real numbers from GET /api/rankings/progress) and the
 * ranking pivot that raises the ceiling. The lab's "34 of the 60 players this
 * deal touches" is deliberately NOT shipped: per-deal coverage does not exist
 * on any response, and inventing a denominator to make the sentence prettier
 * is exactly the confidently-wrong failure this surface exists to avoid.
 */
export function ConfidenceCapNote({
  cap,
  onRank,
}: {
  cap: ConfidenceCap;
  onRank?: () => void;
}) {
  return (
    <View style={styles.cap} testID="presentation.confidence-cap">
      <View style={styles.capRow}>
        {/* `rank` (the bar glyph) — the shared Icon set has no info glyph, and
            the cap IS a statement about ranking volume, so this is the honest
            semantic fit rather than a decorative stand-in. */}
        <Icon name="rank" size={16} color={chalk.dim} />
        <View style={styles.capText}>
          <Text scale="body" style={styles.capHead}>
            {cap.headline}
          </Text>
          <Text variant="bodySm">{cap.detail}</Text>
        </View>
      </View>

      {cap.coverage != null ? (
        <View style={styles.cov}>
          <Text scale="dense" style={type.label}>
            Your board coverage
          </Text>
          <View style={styles.covTrack}>
            <View style={[styles.covFill, { width: `${Math.round(cap.coverage * 100)}%` }]} />
          </View>
          <Text variant="bodySm">
            {cap.completed} of {cap.required} ranked
          </Text>
        </View>
      ) : null}

      {onRank ? (
        <Button
          label="Rank more players"
          variant="secondary"
          onPress={onRank}
          testID="presentation.rank-more"
          style={styles.capBtn}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  cap: {
    marginTop: space.md,
    padding: space.md,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    gap: space.sm,
  },
  capRow: { flexDirection: 'row', gap: space.sm },
  capText: { flex: 1, gap: 2 },
  capHead: { ...type.body, color: chalk.base },
  cov: { gap: space.xs },
  covTrack: { height: 4, backgroundColor: ink.ink3 },
  covFill: { height: 4, backgroundColor: chalk.dim },
  capBtn: { width: '100%' },
});

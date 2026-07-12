import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { ink, chalk, flare, semantic, radii, type, position, tier } from '../../theme/chalkline';

interface Props {
  label: string;
  /** Border color carries the encoding; text stays chalk (kills the old rgba-tint fills). */
  color?: string;
  /** Color the text too (rookie, injury). */
  colorText?: boolean;
}

// Chalkline badge construction: 1px border in the encode color + chalk text on ink.
export default function Badge({ label, color = ink.lineStrong, colorText = false }: Props) {
  return (
    <View style={[styles.badge, { borderColor: color }]}>
      <Text style={[type.label, styles.text, colorText && { color }]}>{label}</Text>
    </View>
  );
}

// Convenience wrappers matching docs/design/components.md → Badges & chips.
export function PositionBadge({ pos }: { pos: 'QB' | 'RB' | 'WR' | 'TE' }) {
  return <Badge label={pos} color={position[pos.toLowerCase() as keyof typeof position]} />;
}

// Pick-value tier ladder labels (docs/cross-client-invariants.md) — keys
// are enums, so render the display label, not the raw key.
const TIER_BADGE_LABEL: Record<keyof typeof tier, string> = {
  firsts_4plus: '4+ 1sts',
  firsts_3: '3 1sts',
  firsts_2: '2 1sts',
  first_1: '1st',
  second: '2nd',
  third: '3rd',
  fourth: '4th',
  waivers: 'Waivers',
};

export function TierChalkBadge({ t }: { t: keyof typeof tier }) {
  return <Badge label={TIER_BADGE_LABEL[t]} color={tier[t]} />;
}

export function RookieBadge() {
  return <Badge label="RK" color={flare.base} colorText />;
}

export function InjuryBadge({ status }: { status: 'Q' | 'D' | 'Out' | 'IR' }) {
  const color = status === 'Q' || status === 'D' ? semantic.warn : semantic.neg;
  return <Badge label={status} color={color} colorText />;
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radii.xs,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  text: { color: chalk.base },
});

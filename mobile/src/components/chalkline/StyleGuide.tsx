import React from 'react';
import { ScrollView, View, Text, StyleSheet } from 'react-native';
import { ink, chalk, ice, semantic, type, space, position } from '../../theme/chalkline';
import TickLabel from './TickLabel';
import Button from './Button';
import { PositionBadge, TierChalkBadge, RookieBadge, InjuryBadge } from './Badge';
import Card from './Card';
import Meter, { fairnessColor } from './Meter';

// RN mirror of web/style-guide.html. Not registered in navigation — to view,
// temporarily add to a stack in mobile/src/navigation/ or render from App.tsx.
export default function StyleGuide() {
  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Text style={type.display}>Trade Finder</Text>
      <Text style={type.bodySm}>
        Chalkline RN reference — tokens: src/theme/chalkline.ts · specs: docs/design/
      </Text>

      <Section label="Typography">
        <Text style={type.display}>Find the trade</Text>
        <Text style={type.heading}>Positional tiers</Text>
        <Text style={type.title}>Jahmyr Gibbs</Text>
        <Text style={type.body}>
          This leaguemate hasn't ranked players yet — balanced by consensus value.
        </Text>
        <Text style={type.dataLg}>
          1580 <Text style={{ color: semantic.pos }}>+14</Text>
        </Text>
        <Text style={type.data}>FAIR 92% · ELO 1462</Text>
      </Section>

      <Section label="Buttons">
        <View style={styles.row}>
          <Button label="Generate trades" />
          <Button label="Skip trio" variant="secondary" />
        </View>
        <View style={styles.row}>
          <Button label="Like" variant="like" />
          <Button label="Pass" variant="pass" />
          <Button label="Mark all read" variant="ghost" />
        </View>
        <Button label="Disabled" disabled />
      </Section>

      <Section label="Badges">
        <View style={styles.row}>
          <PositionBadge pos="QB" />
          <PositionBadge pos="RB" />
          <PositionBadge pos="WR" />
          <PositionBadge pos="TE" />
          <RookieBadge />
          <InjuryBadge status="Q" />
          <InjuryBadge status="IR" />
        </View>
        <View style={styles.row}>
          <TierChalkBadge t="firsts_4plus" />
          <TierChalkBadge t="firsts_3" />
          <TierChalkBadge t="firsts_2" />
          <TierChalkBadge t="first_1" />
          <TierChalkBadge t="second" />
          <TierChalkBadge t="third" />
          <TierChalkBadge t="fourth" />
          <TierChalkBadge t="waivers" />
        </View>
      </Section>

      <Section label="Player card">
        <Card rail={position.wr} selected>
          <Text style={type.title}>Puka Nacua</Text>
          <View style={[styles.row, { marginTop: space.sm }]}>
            <PositionBadge pos="WR" />
            <TierChalkBadge t="firsts_2" />
            <Text style={[type.data, { marginLeft: 'auto' }]}>1608</Text>
          </View>
        </Card>
      </Section>

      <Section label="Meters">
        <Meter value={0.92} color={fairnessColor(0.92)} label="Fairness" showPercent />
        <Meter value={0.63} label="Coverage" showPercent />
      </Section>
    </ScrollView>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <TickLabel>{label}</TickLabel>
      <View style={styles.sectionBody}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: ink.ink0 },
  content: { padding: space.xl, gap: space.sm, paddingBottom: space.xxxl },
  section: { marginTop: space.xxl, gap: space.lg },
  sectionBody: { gap: space.md },
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, flexWrap: 'wrap' },
});

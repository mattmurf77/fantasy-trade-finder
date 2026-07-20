import React from 'react';
import { ScrollView, View, StyleSheet } from 'react-native';
import { ink, semantic, space, position } from '../../theme/chalkline';
import TickLabel from './TickLabel';
import Text from './Text';
import Button from './Button';
import { PositionBadge, TierChalkBadge, RookieBadge, InjuryBadge } from './Badge';
import Card from './Card';
import Meter, { fairnessColor } from './Meter';

// RN mirror of web/style-guide.html. Not registered in navigation — to view,
// temporarily add to a stack in mobile/src/navigation/ or render from App.tsx.
export default function StyleGuide() {
  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Text variant="display">Trade Finder</Text>
      <Text variant="bodySm">
        Chalkline RN reference — tokens: src/theme/chalkline.ts · specs: docs/design/
      </Text>

      <Section label="Typography">
        <Text variant="display">Find the trade</Text>
        <Text variant="heading">Positional tiers</Text>
        <Text variant="title">Jahmyr Gibbs</Text>
        <Text variant="body">
          This leaguemate hasn't ranked players yet — balanced by consensus value.
        </Text>
        <Text variant="dataLg">
          1580 <Text scale="display" style={{ color: semantic.pos }}>+14</Text>
        </Text>
        <Text variant="data">FAIR 92% · ELO 1462</Text>
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
          <Text variant="title">Puka Nacua</Text>
          <View style={[styles.row, { marginTop: space.sm }]}>
            <PositionBadge pos="WR" />
            <TierChalkBadge t="firsts_2" />
            <Text variant="data" style={{ marginLeft: 'auto' }}>1608</Text>
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

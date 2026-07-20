import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Icon, type IconName } from '../components/chalkline';
import { setRankingMethod } from '../api/rankings';
import { useSession, type RankMethodPref } from '../state/useSession';
import { chalk, flare, ice, ink, radii, space, type } from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import type { RankRoute } from '../navigation/TabNav';

// Build-your-board chooser — reached from Quick Set's "More ways to rank"
// header link (since #122 the Rank tab defaults no-pref users straight into
// Quick Set, not here). Describes the
// five ranking flows by PROCESS (how guided vs. hands-on), not feature name,
// ordered most-guided → most-manual. Picking one saves the preference
// (useSession.rankingMethodPref) so subsequent launches route straight to
// that flow; the Settings steer slider changes it later. The intro carries
// the value prop: trade suggestions are priced off this board, so accuracy
// here is what buys good trades.

interface Method {
  pref: RankMethodPref;
  route: RankRoute;
  icon: IconName;
  title: string;
  body: string;
  time: string;
  /** Hands-on level, 1 (we steer) → 4 (you steer). Drives the meter. */
  level: 1 | 2 | 3 | 4;
  /** #119 — the lowest-effort flow, tagged "recommended" (flare). */
  recommended?: boolean;
}

const METHODS: Method[] = [
  // #119 — Quick set promoted to a first-class method: the lowest-effort
  // way to a usable board, so it leads the list and carries the tag.
  {
    pref: 'quickset',
    route: 'QuickSetTiers',
    icon: 'check',
    title: 'Tap players into tiers',
    body:
      'We deal you one value tier at a time — tap the players who belong, ' +
      'save, next. The fastest route to a board good enough to trade off.',
    time: '~2 MIN PER POSITION',
    level: 1,
    recommended: true,
  },
  {
    pref: 'trio',
    route: 'Trios',
    icon: 'rank',
    title: 'Answer quick head-to-heads',
    body:
      'We show you three players — you put them in order. A few seconds ' +
      'each, and your board builds itself from the pattern of your answers.',
    time: '30 SEC AT A TIME',
    level: 1,
  },
  {
    pref: 'anchor',
    route: 'Anchors',
    icon: 'swap',
    title: 'Price players in picks',
    body:
      'One player at a time: worth two 1sts? One? A mid 2nd? Each answer ' +
      'locks in a value everyone in your league understands the same way.',
    time: '~5 MIN FOR YOUR TOP 50',
    level: 2,
  },
  {
    pref: 'tiers',
    route: 'Tiers',
    icon: 'crown',
    title: 'Sort players into groups',
    body:
      'Drag players into value groups, from untouchable to bench. You ' +
      'decide the shape of your board — we handle the exact numbers inside ' +
      'each group.',
    time: '~10 MIN PER POSITION',
    level: 3,
  },
  {
    pref: 'manual',
    route: 'ManualRanks',
    icon: 'trends',
    title: 'Order every player yourself',
    body:
      'The full list, in your exact order, top to bottom. Nothing inferred, ' +
      'nothing suggested — total control over every slot.',
    time: 'THE LONG WAY — YOUR WAY',
    level: 4,
  },
];

function HandsOnMeter({ level }: { level: 1 | 2 | 3 | 4 }) {
  return (
    <View style={styles.meter} accessibilityLabel={`hands-on level ${level} of 4`}>
      {[1, 2, 3, 4].map((i) => (
        <View
          key={i}
          style={[styles.meterSeg, i <= level && styles.meterSegOn]}
        />
      ))}
    </View>
  );
}

export default function RankHomeScreen({ navigation }: any) {
  const setPref = useSession((s) => s.setRankingMethodPref);

  const choose = (m: Method) => {
    haptics.selection();
    // Persist locally first (this is what routes future launches), then
    // record on the backend fire-and-forget — a failed POST must never
    // block the user from starting to rank.
    void setPref(m.pref);
    setRankingMethod(m.pref).catch(() => {});
    navigation.replace(m.route);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body}>
        <Text style={styles.title} accessibilityRole="header">Build your board</Text>

        <View style={styles.callout}>
          <Icon name="trade" size={18} color={flare.base} />
          <Text style={styles.calloutText}>
            <Text style={styles.calloutLead}>
              Every trade we suggest is priced off this board.{' '}
            </Text>
            The closer it matches what you really believe, the better the
            deals we find — sharper targets, fairer offers, fewer duds. Five
            ways to build it; pick how hands-on you want to be.
          </Text>
        </View>

        {METHODS.map((m) => (
          <Pressable
            key={m.pref}
            testID={`rank-home.card.${m.pref}`}
            accessibilityRole="button"
            accessibilityLabel={m.recommended ? `${m.title}, recommended` : m.title}
            accessibilityHint={`${m.body} ${m.time}`}
            onPress={() => choose(m)}
            style={({ pressed }) => [
              styles.card,
              m.recommended && styles.cardFeatured,
              pressed && { backgroundColor: ink.ink3 },
            ]}
          >
            <View style={styles.cardHead}>
              <Icon
                name={m.icon}
                size={20}
                color={m.recommended ? ice.base : chalk.dim}
              />
              <Text style={styles.cardTitle}>{m.title}</Text>
              {m.recommended ? (
                <Text style={styles.recommendedTag}>recommended</Text>
              ) : null}
            </View>
            <Text style={styles.cardBody}>{m.body}</Text>
            <View style={styles.cardFoot}>
              <Text style={styles.timeHint}>{m.time}</Text>
              <HandsOnMeter level={m.level} />
            </View>
          </Pressable>
        ))}

        <View style={styles.axis}>
          <Text style={styles.axisLabel}>WE STEER</Text>
          <View style={styles.axisLine} />
          <Text style={styles.axisLabel}>YOU STEER</Text>
        </View>
        <Text style={styles.mixNote}>
          Mix them anytime — every method writes to the same board, and you
          can fine-tune any player later. Change your pick in Settings.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  body: { padding: space.lg, gap: space.md },
  title: { ...type.heading },

  callout: {
    flexDirection: 'row',
    gap: space.sm,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    padding: space.md,
  },
  calloutText: { ...type.bodySm, flex: 1, lineHeight: 19 },
  calloutLead: { color: chalk.base, fontWeight: '500' },

  card: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    padding: space.md,
    gap: space.sm,
  },
  cardFeatured: { borderColor: ice.base },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  cardTitle: { ...type.title, flex: 1 },
  // #119 — flare tag = informational highlight (ADR-005), never on the
  // action itself; the card's featured state stays the ice border.
  recommendedTag: { ...type.label, color: flare.base },
  cardBody: { ...type.bodySm, lineHeight: 19 },
  cardFoot: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  timeHint: { ...type.label, color: chalk.faint },
  meter: { flexDirection: 'row', gap: 3 },
  meterSeg: {
    width: 14,
    height: 4,
    borderRadius: 2,
    backgroundColor: ink.ink3,
  },
  meterSegOn: { backgroundColor: ice.base },

  axis: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    marginTop: space.xs,
  },
  axisLabel: { ...type.label, color: chalk.faint },
  axisLine: { flex: 1, height: 1, backgroundColor: ink.line },
  mixNote: { ...type.bodySm, color: chalk.faint, textAlign: 'center' },
});

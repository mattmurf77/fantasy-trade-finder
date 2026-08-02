import React, { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Icon } from '../components/chalkline';
import RankImportSheet from '../components/RankImportSheet';
import Toast from '../components/Toast';
import { setRankingMethod } from '../api/rankings';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { chalk, flare, ice, ink, radii, space, type, fonts } from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import {
  MORE_METHODS,
  PRIMARY_METHODS,
  type ChooserMethod,
} from '../navigation/rankChooserModel';

// Build-your-board chooser — reached from the rank surfaces' "More ways to
// rank" header path (since #122 the Rank tab defaults no-pref users straight
// into Quick Set, not here).
//
// #232 consolidation (approved mocks rank-method-consolidation-v2 + -v3):
// THREE primary cards labeled by outcome — FASTEST = Quick set (recommended,
// with the Quick-rank follow-on subrow) · MOST PRECISE = Head-to-heads
// (Trios) · MOST CONTROL = Tiers board — with Pick Anchors / Overall ranks /
// Trends behind a collapsed "More ways to rank" disclosure. Content comes
// from the shared model (navigation/rankChooserModel.ts) also consumed by
// the Rank-tab RankMenu sheet, so the two surfaces can't diverge.
//
// Import entry (flag `ranks.import`, v3 Variant A): a quiet text link right
// of the heading — chalk-dim question, ice underline + upload glyph — that
// opens the "Bring your rankings" paste-first sheet. It shares the heading's
// line; when they can't fit, the intact link wraps under, right-aligned
// (never truncate the link, never shrink the heading).
//
// Picking a method saves the preference (useSession.rankingMethodPref) so
// subsequent launches route straight to that flow; the Settings steer
// slider changes it later. The callout carries the value prop: trades are
// priced off this board.

export default function RankHomeScreen({ navigation }: any) {
  const setPref = useSession((s) => s.setRankingMethodPref);
  const importOn = useFlag('ranks.import');
  const [moreOpen, setMoreOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const choose = (m: ChooserMethod) => {
    haptics.selection();
    if (m.pref) {
      // Persist locally first (this is what routes future launches), then
      // record on the backend fire-and-forget — a failed POST must never
      // block the user from starting to rank.
      void setPref(m.pref);
      setRankingMethod(m.pref).catch(() => {});
    }
    // #162/#165 — navigate, don't replace: replace() removed this chooser
    // from the stack, so back (header, iOS edge-swipe, Android hardware)
    // from the chosen surface could never return here — testers read that
    // as being stuck in a loop. Pushing keeps the chooser underneath;
    // launch routing is unaffected (it reads the saved pref, not the stack).
    navigation.navigate(m.route);
  };

  const onImportApplied = (count: number) => {
    setImportOpen(false);
    setToast(`Imported ${count} rank${count === 1 ? '' : 's'} onto your board`);
    // Land on the Overall board so the imported order is immediately
    // visible (every method writes to the same board).
    navigation.navigate('ManualRanks');
  };

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <Toast
        visible={!!toast}
        message={toast || ''}
        tone="success"
        onDismiss={() => setToast(null)}
      />
      <ScrollView contentContainerStyle={styles.body}>
        <View style={styles.headingRow}>
          <Text style={styles.title} accessibilityRole="header">Build your board</Text>
          {importOn ? (
            <Pressable
              testID="rank-home.import"
              accessibilityRole="button"
              accessibilityLabel="Have rankings already? Import them"
              onPress={() => {
                haptics.selection();
                setImportOpen(true);
              }}
              hitSlop={space.sm}
              style={({ pressed }) => [styles.importLink, pressed && { opacity: 0.6 }]}
            >
              <Icon name="upload" size={14} color={ice.base} />
              <Text style={styles.importLinkText}>Have rankings already?</Text>
            </Pressable>
          ) : null}
        </View>

        <View style={styles.callout}>
          <Icon name="trade" size={18} color={flare.base} />
          <Text style={styles.calloutText}>
            <Text style={styles.calloutLead}>
              Trades are priced off this board.{' '}
            </Text>
            The better it matches you, the better the deals we find.
          </Text>
        </View>

        {PRIMARY_METHODS.map((m) => (
          <Pressable
            key={m.key}
            testID={`rank-home.card.${m.key}`}
            accessibilityRole="button"
            accessibilityLabel={
              m.recommended
                ? `${m.title}, ${m.role}, recommended`
                : `${m.title}, ${m.role}`
            }
            accessibilityHint={m.body}
            onPress={() => choose(m)}
            style={({ pressed }) => [
              styles.card,
              m.recommended && styles.cardFeatured,
              pressed && { backgroundColor: ink.ink3 },
            ]}
          >
            <View style={styles.cardHead}>
              <Text style={styles.roleTag}>{m.role}</Text>
              <View style={{ flex: 1 }} />
              {m.recommended ? (
                <Text style={styles.recommendedTag}>recommended</Text>
              ) : null}
            </View>
            <View style={styles.cardHead}>
              <Icon
                name={m.icon}
                size={20}
                color={m.recommended ? ice.base : chalk.dim}
              />
              <Text style={styles.cardTitle}>{m.title}</Text>
            </View>
            <Text style={styles.cardBody}>{m.body}</Text>
            {m.sub ? (
              <View style={styles.subRow}>
                <Text style={styles.cardBody}>
                  <Text style={styles.subLead}>Then, if you want: </Text>
                  {m.sub}
                </Text>
              </View>
            ) : null}
          </Pressable>
        ))}

        <Pressable
          testID="rank-home.more-toggle"
          accessibilityRole="button"
          accessibilityLabel="More ways to rank"
          accessibilityState={{ expanded: moreOpen }}
          onPress={() => {
            haptics.selection();
            setMoreOpen((v) => !v);
          }}
          style={styles.moreHeader}
        >
          <Text style={styles.moreHeaderText}>More ways to rank</Text>
          <Icon
            name={moreOpen ? 'chevron-up' : 'chevron-down'}
            size={16}
            color={chalk.dim}
          />
        </Pressable>

        {moreOpen ? (
          <View style={styles.moreBox}>
            {MORE_METHODS.map((m, i) => (
              <Pressable
                key={m.key}
                testID={`rank-home.card.${m.key}`}
                accessibilityRole="button"
                accessibilityLabel={m.title}
                accessibilityHint={m.body}
                onPress={() => choose(m)}
                style={({ pressed }) => [
                  styles.moreRow,
                  i === MORE_METHODS.length - 1 && { borderBottomWidth: 0 },
                  pressed && { backgroundColor: ink.ink3 },
                ]}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.moreRowTitle}>{m.title}</Text>
                  <Text style={styles.moreRowSub}>{m.body}</Text>
                </View>
                <Icon name="chevron-right" size={16} color={chalk.dim} />
              </Pressable>
            ))}
          </View>
        ) : null}

        <Text style={styles.mixNote}>
          Every method writes to the same board — mix anytime. Change your
          pick in Settings.
        </Text>
      </ScrollView>

      <RankImportSheet
        visible={importOpen}
        onClose={() => setImportOpen(false)}
        onApplied={onImportApplied}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  body: { padding: space.lg, gap: space.md },

  // v3 heading row — heading left, import entry right, baseline-aligned.
  // The heading never wraps internally; if the pair can't share the row,
  // the whole link wraps under, right-aligned (marginLeft: 'auto').
  headingRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    flexWrap: 'wrap',
    columnGap: space.md,
    rowGap: space.xs,
  },
  title: { ...type.heading },
  importLink: {
    marginLeft: 'auto',
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs + 2,
  },
  importLinkText: {
    fontFamily: fonts.uiSemi,
    fontSize: 13,
    color: chalk.dim,
    textDecorationLine: 'underline',
    textDecorationColor: ice.base,
  },

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
  // Outcome label (FASTEST / MOST PRECISE / MOST CONTROL).
  roleTag: { ...type.label, color: chalk.dim },
  cardTitle: { ...type.title, flex: 1 },
  // #119 — flare tag = informational highlight (ADR-005), never on the
  // action itself; the card's featured state stays the ice border.
  recommendedTag: { ...type.label, color: flare.base },
  cardBody: { ...type.bodySm, lineHeight: 19 },
  subRow: {
    borderTopWidth: 1,
    borderTopColor: ink.line,
    paddingTop: space.sm,
    marginTop: 2,
  },
  subLead: { color: chalk.base, fontFamily: fonts.uiSemi },

  moreHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.xs,
    paddingTop: space.sm,
    minHeight: 44,
  },
  moreHeaderText: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
    color: chalk.base,
  },
  moreBox: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
  },
  moreRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm + 2,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    minHeight: 44,
  },
  moreRowTitle: { fontFamily: fonts.uiSemi, fontSize: 14, color: chalk.base },
  moreRowSub: { ...type.bodySm, marginTop: 2 },

  mixNote: { ...type.bodySm, color: chalk.faint, textAlign: 'center' },
});

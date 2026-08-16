import React, { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useFocusEffect } from '@react-navigation/native';

import { Icon, TickLabel } from '../components/chalkline';
import RankImportSheet from '../components/RankImportSheet';
import ImportRankingsSheet, {
  type PresetMeta,
} from '../components/ImportRankingsSheet';
import Toast from '../components/Toast';
import { setRankingMethod, type ImportRowHint } from '../api/rankings';
import { onRankCsvCaptured, type CapturedCsv } from '../state/rankImportBus';
import { usePremiumImport } from '../state/premiumImport';
import type { PremiumSource } from '../utils/rankPresets';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import {
  guideV2Active,
  recordGuideReceipt,
  requestGuideStep,
} from '../state/useGuide';
import { setPendingGuidedRegen } from '../state/onboardingBus';
import { S as GUIDE } from '../components/analystScript';
import { chalk, flare, ice, ink, radii, space, type, fonts } from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import {
  MORE_METHODS,
  PRIMARY_METHODS,
  type ChooserMethod,
} from '../navigation/rankChooserModel';
import { CONSOLIDATED_VIEW, useRookieScope } from '../state/rookieScope';

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
// opens the "Bring your rankings" sheet. It shares the heading's line; when
// they can't fit, the intact link wraps under, right-aligned (never truncate
// the link, never shrink the heading).
//
// Premium Rankings Import v1 ([D-058]) turned that one sheet into two: the
// link now opens the INTAKE CHOOSER (`ImportRankingsSheet` — Dynasty Nerds /
// DLF behind `ranks.source.*`, CSV upload, paste), and every one of its
// routes ends in the SAME `RankImportSheet` match → review → apply step.
// This screen owns both sheets because only one RN Modal can be up at a time
// on iOS, and because the in-app-browser handoff (`rankImportBus`) lands
// here after the pushed WebView pops.
//
// Picking a method saves the preference (useSession.rankingMethodPref) so
// subsequent launches route straight to that flow; the Settings steer
// slider changes it later. The callout carries the value prop: trades are
// priced off this board.

export default function RankHomeScreen({ navigation, route }: any) {
  const setPref = useSession((s) => s.setRankingMethodPref);
  const importOn = useFlag('ranks.import');
  // rookie-draft M2 / O1-expanded — the chooser is where a user goes to
  // find a way to rank, so the consolidated rookie view gets a discoverable
  // home here as well as the in-context link on every rank surface's scope
  // control. Entering from here also flips the shared scope to rookies, so
  // the modes the user picks next are already scoped — the section and the
  // control are two doors into ONE state.
  const rookieScope = useRookieScope();
  const [moreOpen, setMoreOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // ── Import intake ([D-058], Premium Rankings Import v1) ───────────────
  // `importOpen` is the CHOOSER (ImportRankingsSheet). `pasteOpen` is the
  // existing paste/review sheet, which every route ends in — preset rows,
  // an unrecognized file's raw text, or a plain paste. Exactly one is up at
  // a time: iOS will not stack sibling RN Modals.
  const [importOpen, setImportOpen] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [presetRows, setPresetRows] = useState<ImportRowHint[] | null>(null);
  const [fallbackText, setFallbackText] = useState<string | null>(null);
  const [presetSource, setPresetSource] = useState<PremiumSource | null>(null);
  const [incoming, setIncoming] = useState<CapturedCsv | null>(null);
  const markImported = usePremiumImport((s) => s.markImported);

  // A CSV captured by the in-app browser arrives here after the push pops.
  useEffect(
    () =>
      onRankCsvCaptured((csv) => {
        setIncoming(csv);
        setPasteOpen(false);
        setImportOpen(true);
      }),
    [],
  );

  const openBrowser = (source: PremiumSource) => {
    setImportOpen(false);
    navigation.navigate('PremiumRankingsBrowser', { source });
  };

  const openPaste = (rows: ImportRowHint[] | null, text: string | null) => {
    setImportOpen(false);
    setPresetRows(rows);
    setFallbackText(text);
    setPasteOpen(true);
  };

  const onPresetConfirmed = (rows: ImportRowHint[], meta: PresetMeta) => {
    setPresetSource(meta.source);
    openPaste(rows, null);
  };

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
    setPasteOpen(false);
    // The staleness stamp is written on APPLY, not on preview — "imported N
    // weeks ago" must describe a board that actually changed.
    if (presetSource) {
      void markImported(presetSource);
      setPresetSource(null);
    }
    setPresetRows(null);
    setFallbackText(null);
    setToast(`Imported ${count} rank${count === 1 ? '' : 's'} onto your board`);
    if (guideV2Active()) {
      // The board receipt (retires N8 + every other "help me build a board"
      // nudge) and the payoff handoff: the next Trades focus force-regens and
      // the s5.x reveal fires on the imported numbers — the strongest payoff
      // path in the tour (PRD §5.3-A). Client-observed at the real moment,
      // never off a server-fired event (FR-E3).
      recordGuideReceipt('import_completed');
      setPendingGuidedRegen('import');
    }
    // Land on the Overall board so the imported order is immediately
    // visible (every method writes to the same board).
    navigation.navigate('ManualRanks');
  };

  // N8 — request on guided entry (s3.2's CTA routes here with
  // `guidedEntry: 'n8'`) OR on any RankHome focus (the O-7 first-visit
  // floor). Both arms request the same step; `once` + `invalidateOn` in the
  // eligibility contract make it once-per-device and retire it the moment the
  // user has a board by any method, so re-requesting on focus is self-
  // limiting (a suppressed request re-arms for the next visit).
  //
  // Fail closed on `ranks.import`: that flag is the kill switch for the
  // import entry, and a beat must never outlive the feature it points at —
  // with it off there is nothing for `Upload →` to open, so N8 is not asked.
  const guidedEntry = route?.params?.guidedEntry;
  useFocusEffect(
    useCallback(() => {
      if (!guideV2Active() || !importOn) return;
      requestGuideStep(GUIDE.n8(), {
        onAccept: () => setImportOpen(true),
        // "No — start simple" → Trios, the lightest rung (O-6). RankHome and
        // Trios are siblings in the Rank stack, so this is a plain sibling
        // navigate — the nested `navigate('Rank', { screen: … })` form is for
        // call sites in another tab.
        onDismiss: () => navigation.navigate('Trios', { guidedEntry: 'n8' }),
      });
      // `guidedEntry` is a dependency, not decoration: a fresh guided arrival
      // re-runs the request even when the screen was already focused.
    }, [guidedEntry, importOn, navigation]),
  );

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

        {rookieScope.enabled ? (
          <View style={styles.rookieSection}>
            <TickLabel>Rookies</TickLabel>
            <Pressable
              testID="rank-home.rookie-ranks"
              accessibilityRole="button"
              accessibilityLabel={CONSOLIDATED_VIEW.title}
              accessibilityHint={CONSOLIDATED_VIEW.body}
              onPress={() => {
                haptics.selection();
                rookieScope.setScope('rookie');
                navigation.navigate(CONSOLIDATED_VIEW.route);
              }}
              style={({ pressed }) => [
                styles.moreRow,
                { borderBottomWidth: 0 },
                pressed && { backgroundColor: ink.ink3 },
              ]}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.moreRowTitle}>{CONSOLIDATED_VIEW.title}</Text>
                <Text style={styles.moreRowSub}>{CONSOLIDATED_VIEW.body}</Text>
              </View>
              <Icon name="chevron-right" size={16} color={chalk.dim} />
            </Pressable>
          </View>
        ) : null}

        <Text style={styles.mixNote}>
          Every method writes to the same board — mix anytime. Change your
          pick in Settings.
        </Text>
      </ScrollView>

      <ImportRankingsSheet
        visible={importOpen}
        onClose={() => setImportOpen(false)}
        onPaste={() => openPaste(null, null)}
        onOpenSource={openBrowser}
        onConfirmed={onPresetConfirmed}
        onFallback={(text) => openPaste(null, text)}
        incoming={incoming}
        onIncomingConsumed={() => setIncoming(null)}
      />

      <RankImportSheet
        visible={pasteOpen}
        onClose={() => {
          setPasteOpen(false);
          setPresetRows(null);
          setFallbackText(null);
          setPresetSource(null);
        }}
        onApplied={onImportApplied}
        presetRows={presetRows}
        initialText={fallbackText}
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

  // rookie-draft M2 — the Rookies section reuses the "More ways" row
  // construction so it reads as a peer entry, not a promo.
  rookieSection: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingTop: space.sm,
  },
  mixNote: { ...type.bodySm, color: chalk.faint, textAlign: 'center' },
});

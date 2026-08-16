import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';

import { Button, Icon } from './chalkline';
import { track } from '../api/events';
import { useFlag } from '../state/useFeatureFlags';
import { stalenessLabel, usePremiumImport } from '../state/premiumImport';
import type { CapturedCsv } from '../state/rankImportBus';
import {
  FORMAT_LABEL,
  SCORING_LABEL,
  SOURCE_LABEL,
  isContender,
  parsePreset,
  type BoardFormat,
  type ParsedPreset,
  type PremiumSource,
  type PresetRow,
  type PresetVia,
} from '../utils/rankPresets';
import {
  chalk,
  flare,
  ice,
  ink,
  radii,
  scrim,
  semantic,
  shadowSheet,
  space,
  type,
  fonts,
} from '../theme/chalkline';
import { haptics } from '../utils/haptics';

// Premium Rankings Import v1 — the intake chooser
// (docs/plans/connected-rankings/build-v1-premium-import/scope.md, addendum
// §2 lanes 1 + 2a, [D-058]).
//
// This sheet REPLACES the direct "Have rankings already?" → paste jump: it is
// the one place a board can enter FTF, and it routes four ways —
//
//   Dynasty Nerds  (flag `ranks.source.dynasty_nerds`) → in-app browser
//   DLF            (flag `ranks.source.dlf`)           → in-app browser
//   Upload CSV file (NEVER flag-gated — plain file intake for the existing
//                    import; the flags gate the premium surfaces only)
//   Paste rankings  → the existing RankImportSheet, unchanged
//
// Both premium flags default FALSE in every layer (compiled default,
// config/features.json). There is no fail-open: with a flag off its row is
// not rendered at all, so the surface can go dark same-day if the parallel
// counsel read comes back adverse (addendum §3.4).
//
// Second step: CONFIRMATION. A premium CSV's header is identical across DN's
// four formats AND across its Dynasty/Contender value systems — the
// distinction lives only in the filename (risk R16). So nothing is ever
// applied on an inference: the user confirms value system + format, the
// nearest-format remaps are named out loud, and a `contender_` file cannot
// apply at all until the user explicitly overrides.
//
// Modal/sheet ⇒ no FeedbackFAB mount (root CLAUDE.md exception).

export interface PresetMeta {
  source: PremiumSource;
  via: PresetVia;
  format: BoardFormat;
}

interface Props {
  visible: boolean;
  onClose: () => void;
  /** Paste row → the existing RankImportSheet, behavior unchanged. */
  onPaste: () => void;
  /** Premium row → PremiumRankingsBrowser for that source. */
  onOpenSource: (source: PremiumSource) => void;
  /** Confirmed preset → the existing import preview (match → apply). */
  onConfirmed: (rows: PresetRow[], meta: PresetMeta) => void;
  /** Unknown header signature → the generic paste flow, prefilled with the
   *  raw file text. The preset NEVER guesses (addendum §3.2). */
  onFallback: (text: string, via: PresetVia) => void;
  /** A CSV captured by the in-app browser (via rankImportBus). */
  incoming?: CapturedCsv | null;
  /** Called once `incoming` has been adopted, so the host can clear it. */
  onIncomingConsumed?: () => void;
}

const PREMIUM_ROWS: {
  source: PremiumSource;
  flag: string;
  title: string;
  site: string;
}[] = [
  {
    source: 'dynasty_nerds',
    flag: 'ranks.source.dynasty_nerds',
    title: 'Dynasty Nerds',
    site: 'Dynasty Nerds',
  },
  { source: 'dlf', flag: 'ranks.source.dlf', title: 'DLF', site: 'DLF' },
];

export default function ImportRankingsSheet({
  visible,
  onClose,
  onPaste,
  onOpenSource,
  onConfirmed,
  onFallback,
  incoming,
  onIncomingConsumed,
}: Props) {
  // Flags are read unconditionally at the top level (hook rules) and used to
  // decide whether the row renders at all.
  const dnOn = useFlag('ranks.source.dynasty_nerds');
  const dlfOn = useFlag('ranks.source.dlf');
  const flagOn: Record<PremiumSource, boolean> = {
    dynasty_nerds: dnOn,
    dlf: dlfOn,
  };

  const stamps = usePremiumImport((s) => s.stamps);
  const loadStamps = usePremiumImport((s) => s.load);

  const [parsed, setParsed] = useState<ParsedPreset | null>(null);
  const [format, setFormat] = useState<BoardFormat | null>(null);
  /** True once the user picks a format other than the inferred one — the
   *  `set_confirmed` property on `rankings_preset_detected`. */
  const [changed, setChanged] = useState(false);
  const [contenderOverride, setContenderOverride] = useState(false);
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (visible) void loadStamps();
  }, [visible, loadStamps]);

  const resetConfirm = useCallback(() => {
    setParsed(null);
    setFormat(null);
    setChanged(false);
    setContenderOverride(false);
    setError(null);
  }, []);

  // ── Intake ───────────────────────────────────────────────────────────
  // One funnel for both intake routes (browser capture and file picker):
  // parse → recognized? confirm : fall back to the generic paste flow.
  const ingest = useCallback(
    (text: string, filename: string | null, via: PresetVia) => {
      const p = parsePreset(text, filename, via);
      if (!p) {
        track('rankings_preset_fallback', { via });
        resetConfirm();
        onFallback(text, via);
        return;
      }
      setParsed(p);
      setFormat(p.format);
      setChanged(false);
      setContenderOverride(false);
      setError(null);
    },
    [onFallback, resetConfirm],
  );

  // Adopt a capture handed over by the in-app browser.
  useEffect(() => {
    if (!visible || !incoming) return;
    ingest(incoming.text, incoming.filename, incoming.via);
    onIncomingConsumed?.();
  }, [visible, incoming, ingest, onIncomingConsumed]);

  const close = useCallback(() => {
    resetConfirm();
    onClose();
  }, [resetConfirm, onClose]);

  const onPickFile = useCallback(async () => {
    setPicking(true);
    setError(null);
    try {
      const res = await DocumentPicker.getDocumentAsync({
        // iOS matches on UTI, Android on MIME — list both, plus the generic
        // text type some file providers report for a .csv.
        type: [
          'text/csv',
          'text/comma-separated-values',
          'public.comma-separated-values-text',
          'text/plain',
        ],
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (res.canceled || !res.assets?.length) return;
      const asset = res.assets[0];
      const text = await FileSystem.readAsStringAsync(asset.uri);
      ingest(text, asset.name ?? null, 'file');
    } catch {
      setError('Could not read that file. Try again, or paste the rows.');
    } finally {
      setPicking(false);
    }
  }, [ingest]);

  const onPickSource = useCallback(
    (source: PremiumSource) => {
      haptics.selection();
      // The sheet must be DOWN before the push: a RN Modal renders above the
      // navigator, so a WebView pushed under a live Modal is invisible (the
      // EspnLinkSheet lesson). The host closes us, then navigates.
      resetConfirm();
      onOpenSource(source);
    },
    [onOpenSource, resetConfirm],
  );

  // ── Confirmation ─────────────────────────────────────────────────────
  const blockedByContender = !!parsed && isContender(parsed) && !contenderOverride;
  const canContinue = !!parsed && !!format && !blockedByContender;

  const chooseFormat = useCallback(
    (f: BoardFormat) => {
      haptics.selection();
      setFormat(f);
      // "Did the user override what we inferred?" — an unknown inference
      // that the user resolves counts as a change, which is the honest read
      // (we had nothing; they supplied it).
      setChanged(f !== parsed?.format);
    },
    [parsed],
  );

  const confirm = useCallback(() => {
    if (!parsed || !format || blockedByContender) return;
    haptics.success();
    track('rankings_preset_detected', {
      source: parsed.source,
      via: parsed.via,
      set_confirmed: changed,
    });
    const rows = parsed.rows;
    resetConfirm();
    onConfirmed(rows, { source: parsed.source, via: parsed.via, format });
  }, [parsed, format, blockedByContender, changed, onConfirmed, resetConfirm]);

  const nearestNote = useMemo(() => {
    if (!parsed || parsed.formatMatch !== 'nearest' || !parsed.scoring) return null;
    const { format: inferred } = parsed;
    if (!inferred) return null;
    return `${SCORING_LABEL[parsed.scoring]} isn't one of our two boards — the closest is ${FORMAT_LABEL[inferred]}. Confirm or change it.`;
  }, [parsed]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={close}>
      <Pressable
        style={styles.backdrop}
        onPress={close}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={styles.sheetWrap} pointerEvents="box-none">
        <View style={styles.sheet}>
          <View style={styles.handle} />

          {parsed ? (
            // ── Step 2: confirm value system + format ──────────────────
            <ScrollView contentContainerStyle={styles.confirmBody}>
              <Text style={type.heading} accessibilityRole="header">
                Confirm this import
              </Text>
              <Text style={styles.sub}>
                {SOURCE_LABEL[parsed.source]} export ·{' '}
                {parsed.rows.length} player
                {parsed.rows.length === 1 ? '' : 's'}
                {parsed.rookiesOnly ? ' · rookies only' : ''}
                {parsed.positionFilter ? ` · ${parsed.positionFilter} only` : ''}
              </Text>

              {isContender(parsed) ? (
                <View testID="import-rankings.contender-warning" style={styles.warnBox}>
                  <Icon name="flag" size={16} color={semantic.warn} />
                  <View style={{ flex: 1, gap: space.sm }}>
                    <Text style={styles.warnText}>
                      This is Dynasty Nerds&apos; win-now (Contender) set — not
                      their dynasty board. Importing it will re-order your
                      dynasty ranks by win-now value.
                    </Text>
                    <Pressable
                      testID="import-rankings.contender-override"
                      accessibilityRole="checkbox"
                      accessibilityLabel="Import the Contender set anyway"
                      accessibilityState={{ checked: contenderOverride }}
                      onPress={() => {
                        haptics.selection();
                        setContenderOverride((v) => !v);
                      }}
                      style={styles.checkRow}
                    >
                      <View
                        style={[
                          styles.checkBox,
                          contenderOverride && styles.checkBoxOn,
                        ]}
                      >
                        {contenderOverride ? (
                          <Icon name="check" size={12} color={ice.on} />
                        ) : null}
                      </View>
                      <Text style={styles.checkLabel}>Import it anyway</Text>
                    </Pressable>
                  </View>
                </View>
              ) : null}

              <Text style={styles.fieldLabel}>Value system</Text>
              <Text style={styles.fieldValue}>
                {parsed.set === 'contender'
                  ? 'Contender (win-now)'
                  : parsed.set === 'dynasty'
                    ? 'Dynasty'
                    : 'Dynasty (assumed — the file did not say)'}
              </Text>

              <Text style={styles.fieldLabel}>Board format</Text>
              {nearestNote ? (
                <Text testID="import-rankings.nearest-note" style={styles.nearest}>
                  {nearestNote}
                </Text>
              ) : null}
              {parsed.formatMatch === 'unknown' ? (
                <Text style={styles.nearest}>
                  We couldn&apos;t tell which format this export is for. Pick
                  the board it should land on.
                </Text>
              ) : null}
              <View style={styles.segment}>
                {(['1qb_ppr', 'sf_tep'] as BoardFormat[]).map((f) => (
                  <Pressable
                    key={f}
                    testID={`import-rankings.format.${f}`}
                    accessibilityRole="radio"
                    accessibilityLabel={FORMAT_LABEL[f]}
                    accessibilityState={{ selected: format === f }}
                    onPress={() => chooseFormat(f)}
                    style={[styles.segItem, format === f && styles.segItemOn]}
                  >
                    <Text
                      style={[
                        styles.segText,
                        format === f && styles.segTextOn,
                      ]}
                    >
                      {FORMAT_LABEL[f]}
                    </Text>
                  </Pressable>
                ))}
              </View>

              <View style={styles.honesty}>
                <Text style={styles.honestyText}>
                  We read the ORDER only — the file&apos;s values, trends and
                  points columns are never imported or stored. These are the
                  analysts&apos; ranks, applied to your board.
                </Text>
              </View>

              {error ? <Text style={styles.error}>{error}</Text> : null}

              <Button
                testID="import-rankings.confirm"
                label={
                  blockedByContender
                    ? 'Confirm the Contender warning first'
                    : `Match ${parsed.rows.length} player${parsed.rows.length === 1 ? '' : 's'}`
                }
                onPress={confirm}
                disabled={!canContinue}
              />
              <Button
                label="Back"
                variant="ghost"
                onPress={resetConfirm}
              />
            </ScrollView>
          ) : (
            // ── Step 1: where are the rankings coming from? ────────────
            <>
              <Text style={type.heading} accessibilityRole="header">
                Bring your rankings
              </Text>
              <Text style={styles.sub}>
                Pull in a board you keep somewhere else. Ranks only — we never
                import anyone&apos;s values.
              </Text>

              <View style={styles.rows}>
                {PREMIUM_ROWS.filter((r) => flagOn[r.source]).map((r) => {
                  const staleness = stalenessLabel(stamps[r.source]);
                  return (
                    <Pressable
                      key={r.source}
                      testID={`import-rankings.source.${r.source}`}
                      accessibilityRole="button"
                      accessibilityLabel={`${r.title} — requires your own ${r.site} subscription`}
                      onPress={() => onPickSource(r.source)}
                      style={({ pressed }) => [
                        styles.row,
                        pressed && { backgroundColor: ink.ink3 },
                      ]}
                    >
                      <Icon name="trends" size={18} color={chalk.dim} />
                      <View style={{ flex: 1 }}>
                        <Text style={styles.rowTitle}>{r.title}</Text>
                        <Text style={styles.rowSub}>
                          requires your own {r.site} subscription
                        </Text>
                        {staleness ? (
                          <Text
                            testID={`import-rankings.staleness.${r.source}`}
                            style={styles.rowStale}
                          >
                            {staleness}
                          </Text>
                        ) : null}
                      </View>
                      <Icon name="chevron-right" size={16} color={chalk.dim} />
                    </Pressable>
                  );
                })}

                <Pressable
                  testID="import-rankings.upload"
                  accessibilityRole="button"
                  accessibilityLabel="Upload a CSV file"
                  onPress={() => {
                    haptics.selection();
                    void onPickFile();
                  }}
                  disabled={picking}
                  style={({ pressed }) => [
                    styles.row,
                    pressed && { backgroundColor: ink.ink3 },
                  ]}
                >
                  <Icon name="upload" size={18} color={chalk.dim} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>Upload CSV file</Text>
                    <Text style={styles.rowSub}>
                      A rankings export saved on this device
                    </Text>
                  </View>
                  {picking ? (
                    <ActivityIndicator color={chalk.dim} />
                  ) : (
                    <Icon name="chevron-right" size={16} color={chalk.dim} />
                  )}
                </Pressable>

                <Pressable
                  testID="import-rankings.paste"
                  accessibilityRole="button"
                  accessibilityLabel="Paste rankings"
                  onPress={() => {
                    haptics.selection();
                    onPaste();
                  }}
                  style={({ pressed }) => [
                    styles.row,
                    styles.rowLast,
                    pressed && { backgroundColor: ink.ink3 },
                  ]}
                >
                  <Icon name="rank" size={18} color={chalk.dim} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>Paste rankings</Text>
                    <Text style={styles.rowSub}>
                      Rows from a spreadsheet or any site
                    </Text>
                  </View>
                  <Icon name="chevron-right" size={16} color={chalk.dim} />
                </Pressable>
              </View>

              {error ? <Text style={styles.error}>{error}</Text> : null}
              <Button label="Cancel" variant="ghost" onPress={close} />
            </>
          )}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheetWrap: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    maxHeight: '88%',
    ...shadowSheet,
  },
  handle: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  sub: { ...type.bodySm },

  rows: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    marginTop: space.xs,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm + 4,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    minHeight: 56,
  },
  rowLast: { borderBottomWidth: 0 },
  rowTitle: { fontFamily: fonts.uiSemi, fontSize: 14, color: chalk.base },
  rowSub: { ...type.bodySm, marginTop: 2 },
  rowStale: { ...type.label, color: chalk.faint, marginTop: 3 },

  confirmBody: { gap: space.sm, paddingBottom: space.sm },
  fieldLabel: { ...type.label, color: chalk.dim, marginTop: space.sm },
  fieldValue: { fontFamily: fonts.uiSemi, fontSize: 14, color: chalk.base },
  nearest: { ...type.bodySm, color: flare.base, lineHeight: 19 },

  segment: {
    flexDirection: 'row',
    gap: space.sm,
  },
  segItem: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    backgroundColor: ink.ink1,
  },
  segItemOn: { borderColor: ice.base },
  segText: { fontFamily: fonts.uiSemi, fontSize: 13, color: chalk.dim },
  segTextOn: { color: chalk.base },

  warnBox: {
    flexDirection: 'row',
    gap: space.sm,
    backgroundColor: ink.ink3,
    borderWidth: 1,
    borderColor: semantic.warn,
    borderRadius: radii.sm,
    padding: space.md,
  },
  warnText: { ...type.bodySm, lineHeight: 19 },
  checkRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, minHeight: 44 },
  checkBox: {
    width: 20,
    height: 20,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkBoxOn: { backgroundColor: ice.base, borderColor: ice.base },
  checkLabel: { fontFamily: fonts.uiSemi, fontSize: 13, color: chalk.base },

  honesty: {
    backgroundColor: ink.ink3,
    borderRadius: radii.sm,
    padding: space.md,
    marginTop: space.sm,
  },
  honestyText: { ...type.bodySm, lineHeight: 19 },
  error: { ...type.bodySm, color: semantic.neg },
});

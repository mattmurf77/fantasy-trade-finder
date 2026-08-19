// Shared Chalkline row primitives for the Settings tree.
//
// Lifted verbatim from SettingsScreen.tsx's StyleSheet (origin/main @ ecdbcb3)
// so the extracted sections render pixel-identically to the shipped flat list.
// Every section module and every settings page imports from here — there is no
// second copy of these rules.
//
// Additions for the hub/page split are at the bottom, clearly marked.

import { StyleSheet } from 'react-native';
import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../../theme/chalkline';

export const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  body: { padding: space.lg },
  section: {
    marginTop: space.xl,
    marginBottom: space.sm,
  },
  // Hairline key-value / toggle rows — surface stays ink-0, depth via lines.
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  rowKey: type.label,
  rowSub: {
    ...type.bodySm,
    marginTop: space.xs,
  },
  // #214/#215 — stud-tax segmented row (TestStages Segmented pattern:
  // Chalkline pills, ice = selected).
  studTaxBlock: {
    paddingVertical: space.md,
    gap: space.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  segRow: { flexDirection: 'row', gap: space.sm },
  seg: {
    flex: 1,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingVertical: space.sm,
    alignItems: 'center',
  },
  segOn: { borderColor: ice.base, backgroundColor: ink.ink3 },
  segBusy: { opacity: 0.6 },
  segText: { ...type.bodySm, color: chalk.dim },
  segTextOn: { color: ice.base, fontFamily: fonts.uiSemi },
  kvRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  kvValue: type.body,
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  rowPressed: { backgroundColor: ink.ink3 },
  rowDim: { opacity: 0.45 },
  signOut: {
    minHeight: 44,
    paddingVertical: space.md,
    justifyContent: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ink.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  signOutText: {
    ...type.body,
    color: semantic.neg,
  },
  destructiveKey: {
    ...type.label,
    color: semantic.neg,
  },
  // B3 — Switch league rows + Connect another league card
  leagueRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  leagueName: type.title,
  leagueMeta: {
    ...type.bodySm,
    marginTop: space.xs,
  },
  leagueMetaCount: {
    ...type.data,
    color: chalk.dim,
  },
  connectBody: { gap: space.md },
  connectHelp: type.bodySm,
  // Official Sign in with Apple button (Settings → Account link card).
  appleButton: {
    alignSelf: 'stretch',
    height: 44,
  },
  rankingHint: { ...type.bodySm, color: chalk.faint, marginTop: space.sm },
  // Value-row footnote (v2): provenance/explainer line under a kv row.
  rowFootnote: {
    ...type.bodySm,
    color: chalk.faint,
    marginTop: space.xs,
    marginBottom: space.sm,
  },
  // Teardown 05-03 — denied-permission banner body + subordinate toggles.
  deniedBody: { gap: space.md },
  subordinate: { opacity: 0.65 },
  connectInput: {
    ...type.body,
    height: 44,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
  },
});


// ── Additions for the hub + second-level pages (flag `account.settings_hub`) ──
export const hubStyles = StyleSheet.create({
  // Hub nav row: 16px sentence-case title over a 13px chalk-dim state preview,
  // chevron right. NOT the shipped `rowKey` label construction — with a 13px
  // preview beneath it, an 11px uppercase title reads smaller than its own
  // subtitle. Spec row owed to docs/design/components.md § Navigation.
  navRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 56,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  navTitle: type.title,
  navPreview: {
    ...type.bodySm,
    color: chalk.dim,
    marginTop: 2,
  },
  // Honest-empty preview: a value we don't know for free is never guessed.
  navPreviewNone: {
    ...type.bodySm,
    color: chalk.faint,
    fontStyle: 'italic',
    marginTop: 2,
  },
  // Identity block at the top of the hub — taps through to Account & data.
  identityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingTop: space.md,
    paddingBottom: space.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  identityName: type.title,
  identityMeta: {
    ...type.bodySm,
    marginTop: 2,
  },
  verifyChip: {
    borderWidth: 1,
    borderColor: semantic.warn,
    borderRadius: radii.xs,
    paddingHorizontal: space.sm,
    paddingVertical: 3,
  },
  verifyChipOk: { borderColor: semantic.pos },
  verifyChipText: { ...type.label, color: semantic.warn },
  verifyChipTextOk: { color: semantic.pos },
});

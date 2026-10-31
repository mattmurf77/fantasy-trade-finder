import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Alert,
  Modal,
  ScrollView,
  TextInput,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  ink,
  chalk,
  ice,
  semantic,
  space,
  radii,
  fonts,
  scrim,
  shadowSheet,
  type,
} from '../theme/chalkline';
import { Button, TickLabel, Text as ChalkText } from './chalkline';
import PositionChip from './PositionChip';
import TierBadge from './TierBadge';
import type {
  FreeAgentDropCandidates,
  FreeAgentRosterCapacity,
  FreeAgentRow,
  FreeAgentWaivers,
} from '../api/league';
import { isEspnLeague } from '../api/espn';
import { isMflLeague, isFleaflickerLeague } from '../api/platformLink';
import { openInSleeperApp } from '../utils/sleeperHandoff';
import type { ExternalSurface } from '../utils/openExternal';

// #179 claim sheet + the "where can an Add happen" resolver, shared by the
// Free Agents finder and Usage Trends (moved out of FreeAgentsScreen
// unchanged, 2026-10-10). The sheet only needs a player's identity; the
// board extras (pos_rank / tier / value) are optional because a Usage
// Trends row is not priced on the caller's board — absent, the header
// simply omits them.
export type ClaimTarget = Pick<FreeAgentRow, 'player_id' | 'name' | 'position' | 'team'> &
  Partial<Pick<FreeAgentRow, 'pos_rank' | 'tier' | 'value'>>;

// #179 — where an "Add" can actually be executed. Sleeper publishes no
// write API for roster moves, so the honest Sleeper flow is the claim-
// preparation sheet (ClaimSheet below): FAAB bid + budget, drop selection,
// then a hand-off to the Sleeper app (utils/sleeperHandoff, #351).
// Platform-linked leagues (ESPN / MFL / Fleaflicker) are read-only imports
// today — no write path, so the Add affordance renders dimmed and explains
// why on tap. 'local' covers demo/local leagues that exist nowhere outside
// FTF.
export type AddPlatform = 'sleeper' | 'espn' | 'mfl' | 'fleaflicker' | 'local';

export function resolveAddPlatform(leagueId: string | undefined, isDemo: boolean): AddPlatform {
  if (!leagueId || isDemo) return 'local';
  if (isEspnLeague(leagueId)) return 'espn';
  if (isMflLeague(leagueId)) return 'mfl';
  if (isFleaflickerLeague(leagueId)) return 'fleaflicker';
  // Real Sleeper league ids are numeric; anything else is a local league.
  return /^\d+$/.test(leagueId) ? 'sleeper' : 'local';
}

const NO_ADD_REASON: Record<Exclude<AddPlatform, 'sleeper'>, { title: string; body: string }> = {
  espn: {
    title: "Can't add in ESPN leagues yet",
    body:
      'This league is imported from ESPN with read-only access, so ' +
      'Fantasy Trade Finder can’t make roster moves there. Open the ' +
      'ESPN Fantasy app to add this player.',
  },
  mfl: {
    title: "Can't add in MFL leagues yet",
    body:
      'This league is linked to MyFantasyLeague with read-only access, so ' +
      'Fantasy Trade Finder can’t make roster moves there. Open MFL ' +
      'to add this player.',
  },
  fleaflicker: {
    title: "Can't add in Fleaflicker leagues yet",
    body:
      'This league is linked to Fleaflicker with read-only access, so ' +
      'Fantasy Trade Finder can’t make roster moves there. Open ' +
      'Fleaflicker to add this player.',
  },
  local: {
    title: "Can't add in this league",
    body:
      'This league isn’t connected to a fantasy platform, so there’s ' +
      'no roster to add this player to.',
  },
};

// #179 — non-Sleeper Add handling: honest "why not" alert (read-only
// platform imports / local leagues). Sleeper leagues open the claim sheet
// instead (ClaimSheet below).
export function explainNoAdd(addPlatform: Exclude<AddPlatform, 'sleeper'>) {
  const reason = NO_ADD_REASON[addPlatform];
  Alert.alert(reason.title, reason.body);
}

// After the Modal's slide-in (about 300ms on iOS), so the flash is seen.
const FLASH_DELAY_MS = 400;

// #179 claim-preparation sheet (DynastyDealer-style, honest about write
// limits). Sleeper publishes NO write API, so FTF PREPARES the claim —
// FAAB bid sizing against the caller's live budget, drop selection from
// the value-ascending candidate list when the roster is full — and the CTA
// hands off to the Sleeper app (utils/sleeperHandoff) where the user
// executes it.
export default function ClaimSheet({
  row,
  leagueId,
  leagueName,
  surface = 'unspecified',
  capacity,
  waivers,
  dropCandidates,
  onClose,
}: {
  row: ClaimTarget;
  leagueId: string;
  /** The claim league's name; step 1 of the steps block names it (#351 PRD §4.2). Null/absent: step 1 reads a generic fallback. */
  leagueName?: string | null;
  /** Which host opened the sheet, for the hand-off's ExternalTarget.surface. */
  surface?: ExternalSurface;
  capacity: FreeAgentRosterCapacity | null | undefined;
  waivers: FreeAgentWaivers | null | undefined;
  dropCandidates: FreeAgentDropCandidates | null | undefined;
  onClose: () => void;
}) {
  const [bid, setBid] = useState('');
  const [dropId, setDropId] = useState<string | null>(null);

  // Flash the scroll bar once when the sheet opens, so a list that runs
  // under the fixed footer reads as scrollable (ux-lead, 2026-11-01). The
  // host mounts this sheet only while it is open, so mount = open. The delay
  // lets the slide-in and first layout finish.
  const scrollRef = useRef<ScrollView>(null);
  useEffect(() => {
    const t = setTimeout(() => scrollRef.current?.flashScrollIndicators(), FLASH_DELAY_MS);
    return () => clearTimeout(t);
  }, []);

  const faab = waivers?.type === 'faab' ? waivers.faab : null;
  const remaining = faab?.remaining ?? null;
  const bidNum = bid === '' ? null : Number(bid);
  const bidTooHigh = bidNum != null && remaining != null && bidNum > remaining;

  const openSlots = capacity?.open_slots ?? null;
  const candidates = dropCandidates?.players ?? [];
  const untouchablesExcluded = dropCandidates?.untouchables_excluded ?? 0;
  // Open slots known and > 0 ⇒ no drop needed; 0 (or unknown, when we have
  // candidates) ⇒ show the least-valuable-first drop list.
  const showDropList = openSlots !== null ? openSlots === 0 : candidates.length > 0;
  const dropName = candidates.find((c) => c.id === dropId)?.name ?? null;
  // Steps block: a drop step when a drop is picked, or when the roster is
  // full and one still has to be; none when the roster has room.
  const dropStep = dropName != null || openSlots === 0;

  const openSleeper = () => {
    // Copies the player's name (the steps block says so), then opens the
    // Sleeper app (`sleeper://`, the deepest proven rung; today `bare`, so
    // Sleeper's last-viewed screen). Not installed → the Get Sleeper alert,
    // never silent. Sleeper has no public write API, so the claim itself
    // happens in Sleeper.
    void openInSleeperApp({
      target: 'add',
      leagueId,
      playerId: row.player_id,
      clipboardText: row.name,
      surface,
    });
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable
        style={sheetStyles.backdrop}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={sheetStyles.kav}
        pointerEvents="box-none"
      >
        <View style={sheetStyles.sheet} testID="fa-claim.sheet">
          <SafeAreaView edges={['bottom']} style={sheetStyles.sheetBody}>
            <View style={sheetStyles.grabber} />
            <ScrollView
              ref={scrollRef}
              contentContainerStyle={sheetStyles.content}
              keyboardShouldPersistTaps="handled"
            >
              {/* Player header */}
              <View style={sheetStyles.header}>
                <View style={sheetStyles.headerText}>
                  <Text style={type.heading} numberOfLines={1} accessibilityRole="header">
                    Claim {row.name}
                  </Text>
                  <View style={sheetStyles.headerMeta}>
                    <PositionChip position={row.position} size="sm" />
                    <Text style={type.bodySm}>
                      {row.team ?? 'FA'} · FA {row.position}
                      {row.pos_rank}
                    </Text>
                    {/* #277 — tier label instead of the numeric board value;
                        numeric fallback only for old-server payloads. */}
                    {row.tier ? (
                      // TierBadge hardcodes alignSelf:'flex-start'; re-center
                      // it in this vertically-centered row.
                      <View style={sheetStyles.tierSlot}>
                        <TierBadge tier={row.tier} size="sm" />
                      </View>
                    ) : row.value != null ? (
                      <Text style={sheetStyles.headerValue}>
                        {Math.round(row.value).toLocaleString('en-US')}
                      </Text>
                    ) : null}
                  </View>
                </View>
                <Button label="Cancel" variant="ghost" compact onPress={onClose} />
              </View>

              {/* FAAB bid — only for FAAB leagues; priority-waiver leagues get
                  the honest one-liner instead. */}
              {faab ? (
                <View style={sheetStyles.section}>
                  <TickLabel>FAAB BID</TickLabel>
                  <View style={sheetStyles.bidRow}>
                    <Text style={sheetStyles.bidCurrency}>$</Text>
                    <TextInput
                      testID="fa-claim.bid"
                      value={bid}
                      onChangeText={(t) => setBid(t.replace(/[^0-9]/g, ''))}
                      keyboardType="number-pad"
                      accessibilityLabel="FAAB bid amount"
                      style={[
                        sheetStyles.bidInput,
                        bidTooHigh && sheetStyles.bidInputInvalid,
                      ]}
                      placeholder="0"
                      placeholderTextColor={chalk.faint}
                      maxLength={4}
                    />
                    {remaining != null ? (
                      <Text style={type.bodySm}>
                        Budget: ${remaining.toLocaleString('en-US')} remaining
                      </Text>
                    ) : null}
                  </View>
                  {bidTooHigh ? (
                    <Text style={sheetStyles.bidError}>
                      That's more than your ${remaining!.toLocaleString('en-US')}{' '}
                      remaining — lower the bid.
                    </Text>
                  ) : null}
                </View>
              ) : waivers?.type === 'rolling' || waivers?.type === 'reverse_standings' ? (
                <View style={sheetStyles.section}>
                  <Text style={type.bodySm}>
                    This is a waiver priority league — no FAAB bid needed.
                  </Text>
                </View>
              ) : null}

              {/* Drop selection — least valuable first (or the open-slots
                  all-clear when no drop is needed). */}
              <View style={sheetStyles.section}>
                {!showDropList ? (
                  openSlots !== null ? (
                    <Text style={type.bodySm}>
                      You have {openSlots} open roster{' '}
                      {openSlots === 1 ? 'slot' : 'slots'} — no drop needed.
                    </Text>
                  ) : null
                ) : (
                  <>
                    <TickLabel>SELECT A PLAYER TO DROP</TickLabel>
                    <Text style={sheetStyles.sectionHint}>
                      {openSlots === 0
                        ? 'Your roster is full — least valuable first.'
                        : 'If your roster is full, pick a drop — least valuable first.'}
                    </Text>
                    {candidates.map((c) => {
                      const selected = c.id === dropId;
                      return (
                        <Pressable
                          key={c.id}
                          testID={`fa-claim.drop.${c.id}`}
                          accessibilityRole="radio"
                          accessibilityState={{ selected }}
                          accessibilityLabel={`Drop ${c.name}`}
                          onPress={() => setDropId(selected ? null : c.id)}
                          style={({ pressed }) => [
                            sheetStyles.dropRow,
                            selected && sheetStyles.dropRowSelected,
                            pressed && { backgroundColor: ink.ink3 },
                          ]}
                        >
                          <View style={[sheetStyles.radio, selected && sheetStyles.radioSelected]}>
                            {selected ? <View style={sheetStyles.radioDot} /> : null}
                          </View>
                          <PositionChip position={c.position} size="sm" />
                          <Text style={sheetStyles.dropName} numberOfLines={1}>
                            {c.name}
                          </Text>
                          {/* #277 — tier label per drop candidate; numeric
                              fallback for old-server payloads. The list stays
                              value-ASCENDING (server order — unchanged). */}
                          {c.tier ? (
                            <View style={sheetStyles.tierSlot}>
                              <TierBadge tier={c.tier} size="sm" />
                            </View>
                          ) : (
                            <Text style={type.data}>
                              {Math.round(c.value).toLocaleString('en-US')}
                            </Text>
                          )}
                        </Pressable>
                      );
                    })}
                    {candidates.length === 0 ? (
                      <Text style={type.bodySm}>
                        No droppable players found on your roster.
                      </Text>
                    ) : null}
                    {untouchablesExcluded > 0 ? (
                      <Text style={sheetStyles.untouchableNote}>
                        {untouchablesExcluded === 1
                          ? '1 untouchable player was'
                          : `${untouchablesExcluded} untouchable players were`}{' '}
                        left out of the drop suggestions.
                      </Text>
                    ) : null}
                  </>
                )}
              </View>

              {/* #351 PRD §4.2 steps: what to do once Sleeper opens, as a
                  numbered list (design-lead review 2026-10-28). Re-renders with
                  the drop selection and the bid. Only the `bare` rung is proven,
                  and bare reopens Sleeper's last-viewed league, so step 1 always
                  names the league, generically when the host doesn't know it. */}
              <View style={sheetStyles.section} testID="fa-claim.steps">
                {/* COPY: final per marketing addendum 12; verbs pending #351 §7.3 */}
                <TickLabel>IN SLEEPER</TickLabel>
                <View style={sheetStyles.stepList}>
                  <ClaimStep n={1} testID="fa-claim.step.league">
                    {leagueName ? (
                      <>
                        {'Open '}
                        <ChalkText style={sheetStyles.stepsEm}>{leagueName}</ChalkText>
                      </>
                    ) : (
                      // COPY: null-league fallback, final per marketing addendum 12.
                      "Open the league you're claiming in"
                    )}
                  </ClaimStep>
                  <ClaimStep n={2} testID="fa-claim.step.search">
                    {'Go to Players, then search '}
                    <ChalkText style={sheetStyles.stepsEm}>{row.name}</ChalkText>
                  </ClaimStep>
                  <ClaimStep n={3} testID="fa-claim.step.add">
                    Add
                  </ClaimStep>
                  {dropStep ? (
                    <ClaimStep n={4} testID="fa-claim.step.drop">
                      {dropName ? (
                        <>
                          {'Drop '}
                          <ChalkText style={sheetStyles.stepsEm}>{dropName}</ChalkText>
                        </>
                      ) : candidates.length === 0 ? (
                        // Full roster, nothing listed above (design-lead, 2026-10-28).
                        // COPY: empty-drop-list fallback, final per marketing addendum 12.
                        'Drop a player to make room'
                      ) : (
                        'Drop: pick a player above'
                      )}
                    </ClaimStep>
                  ) : null}
                  {/* The bid doesn't carry over to Sleeper, so FAAB leagues
                      restate it once one is entered. */}
                  {faab && bidNum != null ? (
                    <ClaimStep n={dropStep ? 5 : 4} testID="fa-claim.step.bid">
                      {'Bid '}
                      <ChalkText style={sheetStyles.stepsEm}>
                        ${bidNum.toLocaleString('en-US')}
                      </ChalkText>
                    </ClaimStep>
                  ) : null}
                </View>
                <ChalkText style={sheetStyles.sectionHint}>
                  {`Opening Sleeper copies ${row.name}, so you can paste it into search.`}
                </ChalkText>
              </View>
            </ScrollView>

            {/* Fixed footer (design-lead, 2026-11-01): the CTA stays on screen
                however long the steps make the sheet. A full-roster FAAB claim
                on an iPhone SE measured 648pt against the 567pt sheet. */}
            <View style={sheetStyles.footerBar} testID="fa-claim.footer">
              <Button
                testID="fa-claim.open-sleeper"
                label="Open in Sleeper to claim"
                variant="primary"
                disabled={bidTooHigh}
                onPress={openSleeper}
              />
              <Text style={sheetStyles.footer}>
                Sleeper doesn't allow apps to submit claims — finish in Sleeper.
              </Text>
            </View>
          </SafeAreaView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

// One numbered row of the steps block: the step number in `data` (Plex Mono)
// chalk-dim, then `body-sm` chalk-dim text. `accessible` makes VoiceOver read
// the number and the text as one step.
function ClaimStep({
  n,
  testID,
  children,
}: {
  n: number;
  testID: string;
  children: React.ReactNode;
}) {
  return (
    <View style={sheetStyles.stepRow} testID={testID} accessible>
      <ChalkText style={sheetStyles.stepNum}>{n}</ChalkText>
      <ChalkText style={sheetStyles.stepText}>{children}</ChalkText>
    </View>
  );
}

// #179 claim sheet — construction mirrors SwapPlayerSheet (components.md →
// Sheets, modals, menus): ink-2 surface, top radius, grabber, sheet shadow.
const sheetStyles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  // Fills the Modal and bottom-aligns the sheet, as FeedbackSheet and
  // RankImportSheet do. KeyboardAvoidingView pads by its own onLayout frame,
  // which is parent-relative, so it must start at the screen's top for the
  // padding to equal the keyboard's height. With the pad up, the sheet and
  // its fixed footer sit above the keyboard.
  kav: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    maxHeight: '85%',
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    ...shadowSheet,
  },
  // Lets the body shrink to the sheet's maxHeight. Unstyled, it keeps its
  // content height, so a long ScrollView pushes the fixed footer below the
  // screen. The ScrollView (flexShrink 1 by default) absorbs the cut.
  sheetBody: { flexShrink: 1 },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
  },
  content: {
    paddingHorizontal: space.lg,
    paddingBottom: space.xl,
    gap: space.lg,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: space.md,
    paddingTop: space.sm,
  },
  headerText: { flex: 1, gap: space.xs },
  headerMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  headerValue: { ...type.data, color: chalk.base },
  // TierBadge hardcodes alignSelf:'flex-start'; these rows center children.
  tierSlot: { alignSelf: 'center' },

  section: { gap: space.sm },
  sectionHint: { ...type.bodySm, color: chalk.dim },
  // Steps block emphasis (league / player / drop / bid): the `title` weight
  // at the surrounding body-sm size.
  stepsEm: { fontFamily: fonts.uiSemi, color: chalk.base },
  // Steps block rows: space.xs apart, no hairlines, no card.
  stepList: { gap: space.xs },
  stepRow: { flexDirection: 'row', gap: space.sm },
  stepNum: { ...type.data, color: chalk.dim },
  stepText: { ...type.bodySm, color: chalk.dim, flex: 1 },

  bidRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  bidCurrency: { ...type.data, color: chalk.dim },
  bidInput: {
    ...type.data,
    fontSize: 16,
    color: chalk.base,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minWidth: 72,
    textAlign: 'right',
  },
  bidInputInvalid: { borderColor: semantic.neg },
  bidError: { ...type.bodySm, color: semantic.neg },

  dropRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
    paddingHorizontal: space.sm,
    borderWidth: 1,
    borderColor: 'transparent',
    borderRadius: radii.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  dropRowSelected: {
    borderColor: ice.base,
    borderBottomWidth: 1,
    borderBottomColor: ice.base,
    backgroundColor: ink.ink3,
  },
  dropName: { ...type.title, flex: 1 },
  // Selection tick — square per the radius rule (no radius >8px outside
  // specced pills); radio semantics live in accessibilityRole/state.
  radio: {
    width: 18,
    height: 18,
    borderRadius: radii.xs,
    borderWidth: 1.5,
    borderColor: ink.lineStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioSelected: { borderColor: ice.base },
  radioDot: {
    width: 8,
    height: 8,
    borderRadius: 1,
    backgroundColor: ice.base,
  },
  untouchableNote: { ...type.bodySm, color: chalk.dim },
  // Fixed footer under the ScrollView: the CTA and its footnote.
  footerBar: {
    backgroundColor: ink.ink2,
    borderTopWidth: 1,
    borderTopColor: ink.line,
    paddingTop: space.md,
    paddingHorizontal: space.lg,
    paddingBottom: space.lg,
    gap: space.sm,
  },
  footer: {
    ...type.bodySm,
    color: chalk.dim,
    textAlign: 'center',
  },
});

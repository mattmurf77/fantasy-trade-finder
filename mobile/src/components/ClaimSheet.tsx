import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Alert,
  Linking,
  Modal,
  ScrollView,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  ink,
  chalk,
  ice,
  semantic,
  space,
  radii,
  scrim,
  shadowSheet,
  type,
} from '../theme/chalkline';
import { Button, TickLabel } from './chalkline';
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
// then a deep-link into the league's players page in the Sleeper app/site
// (same pragmatic pattern as the trade-propose deep-link in TradesScreen).
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

// #179 claim-preparation sheet (DynastyDealer-style, honest about write
// limits). Sleeper publishes NO write API, so FTF PREPARES the claim —
// FAAB bid sizing against the caller's live budget, drop selection from
// the value-ascending candidate list when the roster is full — and the CTA
// hands off to Sleeper's players page (same deep-link target as the old
// alert flow) where the user executes it.
export default function ClaimSheet({
  row,
  leagueId,
  capacity,
  waivers,
  dropCandidates,
  onClose,
}: {
  row: ClaimTarget;
  leagueId: string;
  capacity: FreeAgentRosterCapacity | null | undefined;
  waivers: FreeAgentWaivers | null | undefined;
  dropCandidates: FreeAgentDropCandidates | null | undefined;
  onClose: () => void;
}) {
  const [bid, setBid] = useState('');
  const [dropId, setDropId] = useState<string | null>(null);

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

  const openSleeper = () => {
    // Lands on the league's Players (available players) surface — Sleeper
    // has no public write API, so the claim itself happens in Sleeper.
    Linking.openURL(`https://sleeper.com/leagues/${leagueId}/players`).catch(() => {});
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable
        style={sheetStyles.backdrop}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={sheetStyles.sheet} testID="fa-claim.sheet">
        <SafeAreaView edges={['bottom']}>
          <View style={sheetStyles.grabber} />
          <ScrollView
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
          </ScrollView>
        </SafeAreaView>
      </View>
    </Modal>
  );
}

// #179 claim sheet — construction mirrors SwapPlayerSheet (components.md →
// Sheets, modals, menus): ink-2 surface, top radius, grabber, sheet shadow.
const sheetStyles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '85%',
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    ...shadowSheet,
  },
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
  footer: {
    ...type.bodySm,
    color: chalk.dim,
    textAlign: 'center',
  },
});

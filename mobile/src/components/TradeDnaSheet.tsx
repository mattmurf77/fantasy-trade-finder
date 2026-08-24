import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  Modal,
  ActivityIndicator,
  TextInput,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  semantic,
  tier,
  space,
  radii,
  type,
  fonts,
  shadowSheet,
  scrim,
} from '../theme/chalkline';
import { posColor } from '../theme/colors';
import { Icon, Button } from './chalkline';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { guideV2Active, recordGuideReceipt } from '../state/useGuide';
import { GUIDE_RECEIPTS } from './analystScript';
import { track } from '../api/events';
import { haptics } from '../utils/haptics';
import {
  getLeaguePreferences,
  saveLeaguePreferences,
  getAssetPrefs,
  setAssetPref,
  type Outlook,
  type LeaguePreferences,
} from '../api/league';
import { getTradeValues } from '../api/calc';
import { findMyRoster, getLeagueRosters } from '../api/sleeper';
import type { Player } from '../shared/types';

// #246 — Trade DNA as a bottom sheet over the guided deck (approved mock
// mockups/polish-lab-2026-08/acquire-landing-guided-first.html, frame B3).
// With the launcher hub unrouted (guided-first landing), the hub's #212 v3
// DNA editor body is LIFTED here verbatim — same queries, same #236
// autosave machinery (every tap POSTs, in-flight coalesced, last-write-
// wins), same testIDs (`dna.outlook.*` / `dna.chase.*` / `dna.shop.*` /
// `dna.done` / `finder-hub.dna.untouchables` and the #173 untouchables
// management rows all change HOST and keep their ids). The sheet opens
// straight into the expanded editor (no collapsed summary — the deck's
// OutlookBiasReceipt is the collapsed summary now); Done is a pure
// dismiss, exactly as #236 made the hub's Done a pure collapse. The #173
// untouchables management sheet remains reachable via the Manage link —
// it renders as a second layer INSIDE this Modal (never a sibling Modal,
// which iOS won't stack).
//
// #257 (flag trades.edit_full_sheet, variant C "Big three + one quiet
// strip") — the optional `full` prop expands this same sheet into the
// consolidated TradesHome edit sheet: the "tap all that apply ·
// multi-select" header suffixes and the 3-sentence hint drop, Chasing/
// Shopping become one "Positions" block, untouchables gain up to 2 name
// chips (still the same Manage entry point), and two new sections appear
// — "Specific players" (targeting chips, omitted in player mode, which
// keeps its own on-screen board per operator decision Q4) and a demoted
// "Fine tuning" strip (trade fairness + the #256 lane pills) below a
// hairline. Omitting `full` entirely (flag off, or any other DNA-only
// entry point) renders the exact legacy half-sheet body — that omission
// is what keeps flag-off byte-identical.

const DNA_POSITIONS = [
  { key: 'QB', label: 'QB', tid: 'qb' },
  { key: 'RB', label: 'RB', tid: 'rb' },
  { key: 'WR', label: 'WR', tid: 'wr' },
  { key: 'TE', label: 'TE', tid: 'te' },
  { key: 'PICK', label: 'Picks', tid: 'picks' },
] as const;

const OUTLOOK_CARDS: {
  key: NonNullable<Outlook>;
  title: string;
  bias: string;
}[] = [
  // #253 — CANONICAL DISPLAY ORDER: All-in → Contending → Rebuilding →
  // Tanking (the win-now→future ladder a dynasty player reads down).
  // Presentation only: the stored enum values are unchanged, and
  // OutlookSheet + the web outlook overlay already list them this way.
  // Do not reshuffle.
  { key: 'championship', title: 'All-in', bias: 'Win now, spend picks' },
  { key: 'contender', title: 'Contending', bias: 'Balanced moves' },
  { key: 'rebuilder', title: 'Rebuilding', bias: 'Leans young + picks' },
  { key: 'jets', title: 'Tanking', bias: 'Max youth, high picks' },
];

// Position-color for the DNA dots/fills; Picks uses the 1st-round tier
// teal (the pick data color the deck's pick rows already use).
function dnaPosColor(pos: string): string {
  if (pos === 'PICK' || pos === 'PICKS') return tier.first_1;
  return posColor(pos as any) ?? ink.lineStrong;
}

// One Chasing/Shopping toggle button (lifted from the hub — selected =
// solid position-color fill + check glyph + bolded dark label; the check
// is the primary state cue, never color alone).
function DnaToggle({
  label,
  color,
  selected,
  testID,
  accessibilityLabel,
  onPress,
}: {
  label: string;
  color: string;
  selected: boolean;
  testID: string;
  accessibilityLabel: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      testID={testID}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: selected }}
      accessibilityLabel={accessibilityLabel}
      onPress={onPress}
      style={({ pressed }) => [
        styles.ptb,
        selected
          ? { backgroundColor: color, borderColor: color }
          : pressed
            ? { backgroundColor: ink.ink3 }
            : null,
      ]}
    >
      {selected ? (
        <Icon name="check" size={12} color={ice.on} />
      ) : (
        <View style={[styles.ptbDot, { backgroundColor: color }]} />
      )}
      <Text style={[styles.ptbText, selected && styles.ptbTextSel]}>
        {label}
      </Text>
    </Pressable>
  );
}

// #257 — the extra sections the full sheet needs beyond the DNA editor.
// TradesScreen owns fairness/lane/targeting state; this component only
// renders them and calls back. `onAnyChange` fires on any DNA edit
// (outlook/chasing/shopping/untouchables) — the signal TradesScreen uses
// to show its "Preferences changed" refresh strip on dismiss (fairness,
// lane and targeting changes already reset or re-filter the deck
// themselves, so they don't need that nudge).
export interface TradeDnaSheetFullProps {
  fairnessOn: boolean;
  onToggleFairness: (next: boolean) => void;
  deckHasLanes: boolean;
  laneFilter: 'window' | 'value' | null;
  onLaneFilter: (lane: 'window' | 'value') => void;
  /** null in player mode — that mode keeps its board on-screen (Q4). */
  targeting: {
    pinnedGive: Player[];
    pinnedReceive: Player[];
    onAdd: (direction: 'trade_away' | 'acquire') => void;
    onRemove: (id: string, direction: 'trade_away' | 'acquire') => void;
  } | null;
  onAnyChange?: () => void;
  /** #172 (flag trades.intent_modes) — single-select trade SHAPE: null =
   * no preference (today's behavior). Absent entirely when the flag is
   * off, which is what keeps the chip row from rendering at all. */
  tradeIntent?: TradeIntent;
  onTradeIntent?: (intent: TradeIntent) => void;
  /** #269 (flag trades.sheet_targeting) — league picker + single-select
   * "Trade with" team targeting, rendered above the primary questions.
   * Absent entirely when the flag is off (mode-bar Team/Player chips stay
   * the entry point instead). */
  teamTargeting?: {
    leagueName: string | null;
    onOpenLeaguePicker: () => void;
    opponentName: string | null;
    onOpenPicker: () => void;
    onClear: () => void;
  };
}

// #172 — trade intent modes ("I want to consolidate / tier up / tier
// down"). Kept local to this file (only the full sheet renders the chips)
// but exported so TradesScreen can type its own state the same way.
export type TradeIntent = 'consolidate' | 'tier_up' | 'tier_down' | null;

const TRADE_INTENTS: { key: NonNullable<TradeIntent>; label: string; tid: string }[] = [
  { key: 'consolidate', label: 'Consolidate', tid: 'consolidate' },
  { key: 'tier_up', label: 'Tier up', tid: 'tier-up' },
  { key: 'tier_down', label: 'Tier down', tid: 'tier-down' },
];

// #315 — the outlook receipt's details row re-states the selected lane;
// derived from TRADE_INTENTS so the row's word can never drift from the
// chip the user actually tapped.
export const TRADE_INTENT_LABEL = Object.fromEntries(
  TRADE_INTENTS.map((i) => [i.key, i.label]),
) as Record<NonNullable<TradeIntent>, string>;

interface Props {
  visible: boolean;
  /** Pure dismiss — every edit already autosaved on tap (#236). */
  onClose: () => void;
  /** #257 — present only under `trades.edit_full_sheet`; see file header. */
  full?: TradeDnaSheetFullProps;
  /** Guided Onboarding v2 — who opened this sheet, for the `source` prop on
   *  `outlook_saved`. `'guide'` when `N2`'s CTA opened it (the opener
   *  passes it; TradesScreen owns that path), `'strip'` for the
   *  prefs-changed strip, default `'sheet'` for every ordinary entry point.
   *  Inert unless `onboarding.guide_v2` is on. */
  openSource?: 'guide' | 'sheet' | 'strip';
}

export default function TradeDnaSheet({ visible, onClose, full, openSource }: Props) {
  // Wave A (v2 note 13) — "the outlook sheet sits too tight to the bottom".
  // The sheet is `bottom: 0` with a uniform `space.lg` pad, so on a
  // home-indicator device the last control sat under the indicator and the
  // whole panel read as cut off. The pad now clears the inset as well:
  // `space.lg` of breathing room ABOVE whatever the system reserves. Applied
  // to all three `styles.sheet` mounts — the outlook editor and the two
  // layers nested inside the same Modal (untouchables, roster picker) are one
  // surface to the user, and padding only the outer one would look like a bug.
  const insets = useSafeAreaInsets();
  const queryClient = useQueryClient();
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id || null;
  const userId = useSession((s) => s.user)?.user_id || '';

  const [untouchablesOpen, setUntouchablesOpen] = useState(false);
  // #259 — the roster picker inside the untouchables layer.
  const [rosterPickOpen, setRosterPickOpen] = useState(false);
  const [rosterQuery, setRosterQuery] = useState('');

  // Drafts mirror the saved prefs until the user touches a control.
  const [draftOutlook, setDraftOutlook] = useState<NonNullable<Outlook> | null>(
    null,
  );
  const [draftChasing, setDraftChasing] = useState<string[]>([]);
  const [draftShopping, setDraftShopping] = useState<string[]>([]);
  const [dnaError, setDnaError] = useState<string | null>(null);
  const dnaTouched = useRef(false);

  // #173 — untouchables management (flag trade.preference_lists, same
  // gate the deck uses for its lock toggles).
  const untouchablesEnabled = useFlag('trade.preference_lists');

  const prefsQuery = useQuery({
    queryKey: ['league-prefs', leagueId],
    queryFn: () => getLeaguePreferences(leagueId!),
    enabled: !!leagueId,
    staleTime: 5 * 60_000,
    placeholderData: (prev) => prev,
  });
  const prefs = prefsQuery.data;

  const assetPrefsQuery = useQuery({
    queryKey: ['asset-prefs', leagueId],
    queryFn: () => getAssetPrefs(leagueId!),
    enabled: !!leagueId && visible,
    staleTime: 60_000,
  });
  const untouchableIds = assetPrefsQuery.data?.untouchables ?? [];
  const untouchableCount = untouchableIds.length;

  // Resolve untouchable ids to names for the management layer — the same
  // shared ['calc-values', …] cache the hub and the deck's swap sheet use.
  // #257 — also enabled whenever `full` is present (not just while the
  // Manage layer is open): the full sheet's "Off the table" summary shows
  // up to 2 name chips, so the names need to be ready before Manage is
  // ever tapped.
  const untouchableNamesQuery = useQuery({
    queryKey: ['calc-values', '1qb_ppr'],
    queryFn: ({ signal }) => getTradeValues('1qb_ppr', signal),
    enabled: untouchablesOpen || (!!full && untouchablesEnabled),
    staleTime: 5 * 60_000,
  });
  const untouchableRows = useMemo(() => {
    const byId = new Map(
      (untouchableNamesQuery.data?.players ?? []).map((p) => [p.id, p]),
    );
    return untouchableIds.map((id) => {
      const p = byId.get(id);
      return {
        id,
        name: p?.name ?? `Player ${id}`,
        position: p?.position ?? null,
      };
    });
  }, [untouchableIds, untouchableNamesQuery.data]);

  const removeUntouchable = useMutation({
    mutationFn: (playerId: string) => setAssetPref(leagueId!, playerId, 'none'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['asset-prefs', leagueId] });
      full?.onAnyChange?.();
    },
  });

  // ── #259 — add untouchables FROM YOUR ROSTER ─────────────────────────
  // #173 shipped list + remove and left adding contextual ("hold a player
  // on any trade card"), which cannot reach a player no trade idea ever
  // offers. The picker below closes that hole. It draws on the SAME two
  // sources already open here — the shared ['calc-values'] pool for
  // names/values and the league rosters — and writes through the SAME
  // `setAssetPref` lane the deck's lock toggle uses. No new endpoint.
  //
  // It renders as a THIRD layer inside this Modal rather than mounting
  // PlayerPickerModal: that component renders its own <Modal>, and iOS
  // will not present a sibling Modal over an open one (the constraint
  // that put the untouchables layer in here in the first place).
  const rostersQuery = useQuery({
    queryKey: ['league-rosters', leagueId],
    queryFn: () => getLeagueRosters(leagueId!),
    enabled: !!leagueId && untouchablesOpen,
    staleTime: 5 * 60_000,
  });

  const myRosterRows = useMemo(() => {
    // Owner OR co-owner: matching on owner_id alone left a co-manager with an
    // empty untouchables picker in that league (scope.md §0.1 A).
    const ids = findMyRoster(rostersQuery.data, userId)?.players ?? [];
    const byId = new Map(
      (untouchableNamesQuery.data?.players ?? []).map((p) => [p.id, p]),
    );
    const protectedIds = new Set(untouchableIds);
    const q = rosterQuery.trim().toLowerCase();
    return ids
      .filter((id) => !protectedIds.has(id))
      .map((id) => byId.get(id))
      .filter((p): p is NonNullable<typeof p> => !!p)
      .filter((p) => (q ? p.name.toLowerCase().includes(q) : true))
      .sort((a, b) => b.value - a.value);
  }, [
    rostersQuery.data,
    userId,
    untouchableNamesQuery.data,
    untouchableIds,
    rosterQuery,
  ]);

  const addUntouchable = useMutation({
    mutationFn: (playerId: string) =>
      setAssetPref(leagueId!, playerId, 'untouchable'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['asset-prefs', leagueId] });
      full?.onAnyChange?.();
    },
  });

  // Seed the drafts from saved prefs while untouched (covers the sheet
  // opening before the prefs fetch lands). Once the user touches a
  // control the drafts are theirs until dismiss.
  useEffect(() => {
    if (visible && dnaTouched.current) return;
    setDraftOutlook(
      (prefs?.team_outlook as NonNullable<Outlook>) ??
        (prefs?.inferred_outlook as NonNullable<Outlook>) ??
        null,
    );
    setDraftChasing(prefs?.acquire_positions ?? []);
    setDraftShopping(prefs?.trade_away_positions ?? []);
  }, [prefs, visible]);

  // Guided Onboarding v2 — `outlook_saved` fires on the FIRST preference
  // write of a sheet SESSION, not per tap: #236 autosave POSTs on every
  // tap, so a per-tap emit would count keystrokes rather than the decision
  // `N2` retires on. Reset with the rest of the per-open state below.
  const outlookSavedFiredRef = useRef(false);

  // Reset per-open state when the sheet opens.
  useEffect(() => {
    if (visible) {
      dnaTouched.current = false;
      outlookSavedFiredRef.current = false;
      setDnaError(null);
      setUntouchablesOpen(false);
      setRosterPickOpen(false);
      setRosterQuery('');
    }
  }, [visible]);

  const saveOutlook = useMutation({
    mutationFn: (vars: {
      outlook: NonNullable<Outlook>;
      acquire: string[];
      shed: string[];
    }) =>
      saveLeaguePreferences(leagueId!, {
        team_outlook: vars.outlook,
        acquire_positions: vars.acquire,
        trade_away_positions: vars.shed,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['league-prefs', leagueId] });
    },
  });

  // #236 — autosave: every editor tap persists immediately. One POST in
  // flight at a time; taps landing mid-flight coalesce into a single
  // trailing save of the latest FULL payload (last-write-wins).
  const dnaDesired = useRef<{
    outlook: NonNullable<Outlook>;
    acquire: string[];
    shed: string[];
  } | null>(null);
  const dnaInFlight = useRef(false);

  const flushDnaSave = async () => {
    if (dnaInFlight.current) return;
    const payload = dnaDesired.current;
    if (!payload) return;
    dnaDesired.current = null;
    dnaInFlight.current = true;
    try {
      await saveOutlook.mutateAsync(payload);
    } catch (e: any) {
      // Quiet-but-honest failure: drop queued edits, revert the drafts to
      // the last-saved prefs, and surface the inline error line.
      dnaDesired.current = null;
      const saved = queryClient.getQueryData<LeaguePreferences>([
        'league-prefs',
        leagueId,
      ]);
      setDraftOutlook(
        (saved?.team_outlook as NonNullable<Outlook>) ??
          (saved?.inferred_outlook as NonNullable<Outlook>) ??
          null,
      );
      setDraftChasing(saved?.acquire_positions ?? []);
      setDraftShopping(saved?.trade_away_positions ?? []);
      dnaTouched.current = false;
      setDnaError(e?.message || 'Could not save preferences');
    } finally {
      dnaInFlight.current = false;
      if (dnaDesired.current) void flushDnaSave();
    }
  };

  const queueDnaSave = (payload: {
    outlook: NonNullable<Outlook>;
    acquire: string[];
    shed: string[];
  }) => {
    // The single choke point for every outlook / Chasing / Shopping write,
    // so "first preference write of this sheet session" is one guard and
    // cannot drift between the editor controls. Emitted at QUEUE time, not
    // on the POST's success: the user made the choice, and the autosave
    // path already reverts the drafts and surfaces an error line if the
    // write fails. The retirement receipt is deliberately tolerant of that
    // failure — re-teaching a user who has already stated their outlook is
    // the help-abuse case whether or not the server took it.
    if (guideV2Active() && !outlookSavedFiredRef.current) {
      outlookSavedFiredRef.current = true;
      track('outlook_saved', { source: openSource ?? 'sheet' }, 'Trades');
      recordGuideReceipt(GUIDE_RECEIPTS.outlookSaved);
    }
    dnaDesired.current = payload;
    void flushDnaSave();
  };

  const pickOutlook = (key: NonNullable<Outlook>) => {
    haptics.selection();
    if (draftOutlook === key) return; // re-tapping the pick isn't an edit
    dnaTouched.current = true;
    setDnaError(null);
    setDraftOutlook(key);
    queueDnaSave({ outlook: key, acquire: draftChasing, shed: draftShopping });
    full?.onAnyChange?.();
  };

  // Multi-select within a row; cross-row mutual exclusion MOVES the
  // position. Next values are computed up front so the tap can autosave
  // the exact state it shows.
  const toggleDnaPos = (side: 'chase' | 'shop', pos: string) => {
    haptics.selection();
    dnaTouched.current = true;
    setDnaError(null);
    let nextChasing: string[];
    let nextShopping: string[];
    if (side === 'chase') {
      nextChasing = draftChasing.includes(pos)
        ? draftChasing.filter((p) => p !== pos)
        : [...draftChasing, pos];
      nextShopping = draftShopping.filter((p) => p !== pos);
    } else {
      nextShopping = draftShopping.includes(pos)
        ? draftShopping.filter((p) => p !== pos)
        : [...draftShopping, pos];
      nextChasing = draftChasing.filter((p) => p !== pos);
    }
    setDraftChasing(nextChasing);
    setDraftShopping(nextShopping);
    queueDnaSave({
      // The backend requires a valid outlook to persist positions;
      // 'not_sure' is the honest no-choice value.
      outlook: draftOutlook ?? 'not_sure',
      acquire: nextChasing,
      shed: nextShopping,
    });
    full?.onAnyChange?.();
  };

  const handleDone = () => {
    haptics.selection();
    dnaTouched.current = false;
    setDnaError(null);
    onClose();
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={
        rosterPickOpen
          ? () => setRosterPickOpen(false)
          : untouchablesOpen
            ? () => setUntouchablesOpen(false)
            : handleDone
      }
    >
      <Pressable
        style={styles.backdrop}
        onPress={handleDone}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={[styles.sheet, { paddingBottom: insets.bottom + space.lg }]}>
        <View style={styles.grabber} />
        <View style={styles.sheetTop}>
          <Text style={type.heading} accessibilityRole="header">
            {full ? 'What are you after?' : 'Your Trade DNA'}
          </Text>
          <Pressable
            testID="dna.done"
            accessibilityRole="button"
            accessibilityLabel="Done editing trade preferences"
            onPress={handleDone}
            hitSlop={8}
            style={({ pressed }) => [
              styles.doneBtn,
              pressed && { backgroundColor: ice.press },
            ]}
          >
            <Icon name="check" size={13} color={ice.on} />
            <Text style={styles.doneText}>Done</Text>
          </Pressable>
        </View>

        <ScrollView style={styles.bodyScroll} contentContainerStyle={styles.body}>
          {/* #269 (flag trades.sheet_targeting) — league picker + specific-
              team targeting, ahead of the primary questions (this is the
              only place either lives now that the mode-bar's Team/Player
              chips are gone). League picker opens the SAME global
              LeagueSwitcherSheet instance TopBar uses (close this sheet
              first, reopen when it closes — iOS won't stack sibling
              Modals, same pattern the "Specific players" add flow below
              uses for PlayerPickerModal). Team targeting reuses the
              existing "Pick a manager" list Modal and its
              opponent_user_id wiring verbatim; tapping the active manager
              again clears the selection. */}
          {full?.teamTargeting ? (
            <>
              <Text style={styles.dnaGroupHdr}>League</Text>
              <Pressable
                testID="dna.league-picker"
                accessibilityRole="button"
                accessibilityLabel={`League: ${full.teamTargeting.leagueName ?? 'none selected'}`}
                accessibilityHint="Opens the league switcher"
                onPress={full.teamTargeting.onOpenLeaguePicker}
                style={({ pressed }) => [
                  styles.leaguePickerRow,
                  pressed && { backgroundColor: ink.ink3 },
                ]}
              >
                <Text style={styles.leaguePickerName} numberOfLines={1}>
                  {full.teamTargeting.leagueName ?? 'Choose a league'}
                </Text>
                <Icon name="chevron-down" size={14} color={ice.base} />
              </Pressable>

              <Text style={styles.dnaGroupHdr}>
                Trade with <Text style={styles.dnaSub}>optional</Text>
              </Text>
              {full.teamTargeting.opponentName ? (
                <View style={styles.chipsWrap}>
                  <Pressable
                    testID="dna.team-target.chip"
                    accessibilityRole="button"
                    accessibilityLabel={`Stop limiting trades to ${full.teamTargeting.opponentName}`}
                    onPress={full.teamTargeting.onClear}
                    style={({ pressed }) => [
                      styles.targetChip,
                      pressed && { backgroundColor: ink.ink3 },
                    ]}
                  >
                    <Text style={styles.targetChipDir}>ONLY</Text>
                    <Text style={styles.targetChipName}>
                      {full.teamTargeting.opponentName}
                    </Text>
                    <Icon name="x" size={12} color={chalk.dim} />
                  </Pressable>
                </View>
              ) : null}
              <Pressable
                testID="dna.team-target.pick"
                accessibilityRole="button"
                accessibilityLabel={
                  full.teamTargeting.opponentName
                    ? 'Change trade partner'
                    : 'Pick a team to trade with'
                }
                onPress={full.teamTargeting.onOpenPicker}
                style={({ pressed }) => [
                  styles.addBtn,
                  pressed && { backgroundColor: ink.ink3 },
                ]}
              >
                <Text style={styles.addBtnText}>
                  {full.teamTargeting.opponentName
                    ? '+ Change team'
                    : '+ Pick a specific team'}
                </Text>
              </Pressable>
            </>
          ) : null}

          <Text style={styles.dnaGroupHdr}>My team is…</Text>
          <View style={styles.outGrid}>
            {OUTLOOK_CARDS.map((o) => {
              const sel = draftOutlook === o.key;
              return (
                <Pressable
                  key={o.key}
                  testID={`dna.outlook.${o.key}`}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: sel, checked: sel }}
                  accessibilityLabel={o.title}
                  accessibilityHint={o.bias}
                  onPress={() => pickOutlook(o.key)}
                  style={({ pressed }) => [
                    styles.outCard,
                    sel && styles.outCardSel,
                    pressed && { backgroundColor: ink.ink3 },
                  ]}
                >
                  <View style={styles.outCardTop}>
                    <Text style={styles.outCardTitle}>{o.title}</Text>
                    {sel ? <View style={styles.outCardTick} /> : null}
                  </View>
                  <Text
                    style={[styles.outCardBias, sel && { color: chalk.base }]}
                  >
                    {o.bias}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          {full ? (
            <>
              <Text style={styles.dnaGroupHdr}>Positions</Text>
              <View style={styles.posLine}>
                <View style={styles.posLbl}>
                  <Text style={styles.posLblText}>Chasing</Text>
                  <Text style={styles.posLblSub}>want more</Text>
                </View>
                <View style={styles.toggleRow}>
                  {DNA_POSITIONS.map((p) => (
                    <DnaToggle
                      key={`chase-${p.key}`}
                      label={p.label}
                      color={dnaPosColor(p.key)}
                      selected={draftChasing.includes(p.key)}
                      testID={`dna.chase.${p.tid}`}
                      accessibilityLabel={`Chase ${p.label}`}
                      onPress={() => toggleDnaPos('chase', p.key)}
                    />
                  ))}
                </View>
              </View>
              <View style={styles.posLine}>
                <View style={styles.posLbl}>
                  <Text style={styles.posLblText}>Shopping</Text>
                  <Text style={styles.posLblSub}>happy to move</Text>
                </View>
                <View style={styles.toggleRow}>
                  {DNA_POSITIONS.map((p) => (
                    <DnaToggle
                      key={`shop-${p.key}`}
                      label={p.label}
                      color={dnaPosColor(p.key)}
                      selected={draftShopping.includes(p.key)}
                      testID={`dna.shop.${p.tid}`}
                      accessibilityLabel={`Shop ${p.label}`}
                      onPress={() => toggleDnaPos('shop', p.key)}
                    />
                  ))}
                </View>
              </View>

              {/* #172 — trade intent modes, its own primary question
                  (it IS a primary question, per the operator ask) placed
                  with outlook/positions, above the demoted "Fine tuning"
                  strip. Single-select; tapping the active chip clears it. */}
              {full.onTradeIntent ? (
                <>
                  <Text style={styles.dnaGroupHdr}>Trade idea</Text>
                  <View style={styles.toggleRow}>
                    {TRADE_INTENTS.map((it) => {
                      const selected = full.tradeIntent === it.key;
                      return (
                        <Pressable
                          key={it.key}
                          testID={`dna.intent.${it.tid}`}
                          accessibilityRole="button"
                          accessibilityState={{ selected }}
                          accessibilityLabel={it.label}
                          onPress={() => full.onTradeIntent!(it.key)}
                          style={({ pressed }) => [
                            styles.ptb,
                            selected
                              ? styles.intentChipSel
                              : pressed
                                ? { backgroundColor: ink.ink3 }
                                : null,
                          ]}
                        >
                          <Text
                            style={[styles.ptbText, selected && styles.ptbTextSel]}
                          >
                            {it.label}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </View>
                </>
              ) : null}
            </>
          ) : (
            <>
              <Text style={styles.dnaGroupHdr}>
                Chasing — tap all that apply{' '}
                <Text style={styles.dnaMs}>· multi-select</Text>
              </Text>
              <View style={styles.toggleRow}>
                {DNA_POSITIONS.map((p) => (
                  <DnaToggle
                    key={`chase-${p.key}`}
                    label={p.label}
                    color={dnaPosColor(p.key)}
                    selected={draftChasing.includes(p.key)}
                    testID={`dna.chase.${p.tid}`}
                    accessibilityLabel={`Chase ${p.label}`}
                    onPress={() => toggleDnaPos('chase', p.key)}
                  />
                ))}
              </View>

              <Text style={styles.dnaGroupHdr}>
                Shopping — tap all that apply{' '}
                <Text style={styles.dnaMs}>· multi-select</Text>
              </Text>
              <View style={styles.toggleRow}>
                {DNA_POSITIONS.map((p) => (
                  <DnaToggle
                    key={`shop-${p.key}`}
                    label={p.label}
                    color={dnaPosColor(p.key)}
                    selected={draftShopping.includes(p.key)}
                    testID={`dna.shop.${p.tid}`}
                    accessibilityLabel={`Shop ${p.label}`}
                    onPress={() => toggleDnaPos('shop', p.key)}
                  />
                ))}
              </View>

              <Text style={styles.dnaHint}>
                Pick as many per row as apply. A position can't be both chased
                and shopped — tapping it on one row moves it there. Changes save
                as you tap.
              </Text>
            </>
          )}

          {dnaError ? <Text style={styles.dnaErrorText}>{dnaError}</Text> : null}

          {/* #257 — Specific players. Omitted in player mode (`targeting`
              is null there) — that mode keeps its own on-screen TRADE
              AWAY/TRADE FOR board (operator decision Q4). Opening the
              picker closes this sheet first (setDnaSheetOpen(false) in
              TradesScreen's onAdd) — iOS won't stack a second Modal over
              this one — and TradesScreen reopens the sheet when the
              picker closes. */}
          {full?.targeting ? (
            <>
              <Text style={styles.dnaGroupHdr}>
                Specific players <Text style={styles.dnaSub}>optional</Text>
              </Text>
              {full.targeting.pinnedGive.length > 0 ||
              full.targeting.pinnedReceive.length > 0 ? (
                <View style={styles.chipsWrap}>
                  {full.targeting.pinnedGive.map((p) => (
                    <Pressable
                      key={`send-${p.id}`}
                      testID={`dna.targets.chip.${p.id}`}
                      accessibilityRole="button"
                      accessibilityLabel={`Remove ${p.name} from trade-away targets`}
                      onPress={() => full.targeting!.onRemove(p.id, 'trade_away')}
                      style={({ pressed }) => [
                        styles.targetChip,
                        pressed && { backgroundColor: ink.ink3 },
                      ]}
                    >
                      <Text style={styles.targetChipDir}>SEND</Text>
                      <Text style={styles.targetChipName}>{p.name}</Text>
                      <Icon name="x" size={12} color={chalk.dim} />
                    </Pressable>
                  ))}
                  {full.targeting.pinnedReceive.map((p) => (
                    <Pressable
                      key={`get-${p.id}`}
                      testID={`dna.targets.chip.${p.id}`}
                      accessibilityRole="button"
                      accessibilityLabel={`Remove ${p.name} from acquire targets`}
                      onPress={() => full.targeting!.onRemove(p.id, 'acquire')}
                      style={({ pressed }) => [
                        styles.targetChip,
                        pressed && { backgroundColor: ink.ink3 },
                      ]}
                    >
                      <Text style={styles.targetChipDir}>GET</Text>
                      <Text style={styles.targetChipName}>{p.name}</Text>
                      <Icon name="x" size={12} color={chalk.dim} />
                    </Pressable>
                  ))}
                </View>
              ) : null}
              {/* #312 — GIVE-LEFT / GET-RIGHT (the #209/#216 ruling): what
                  you send renders left/first on every side-by-side trade
                  surface (player board AWAY/FOR, idea rows, featured
                  window, clipboard "I send:"/"I get:"). This row was the
                  app's one violation — authored get-first because acquire
                  is the sheet's headline motive. Pure child-order swap;
                  testIDs/labels/handlers untouched. Pinned by
                  mobile/tests/check-dna-side-order.js. */}
              <View style={styles.addRow}>
                <Pressable
                  testID="dna.targets.add-send"
                  accessibilityRole="button"
                  accessibilityLabel="Add someone to send"
                  onPress={() => full.targeting!.onAdd('trade_away')}
                  style={({ pressed }) => [
                    styles.addBtn,
                    pressed && { backgroundColor: ink.ink3 },
                  ]}
                >
                  <Text style={styles.addBtnText}>+ Add someone to send</Text>
                </Pressable>
                <Pressable
                  testID="dna.targets.add-get"
                  accessibilityRole="button"
                  accessibilityLabel="Add someone to get"
                  onPress={() => full.targeting!.onAdd('acquire')}
                  style={({ pressed }) => [
                    styles.addBtn,
                    pressed && { backgroundColor: ink.ink3 },
                  ]}
                >
                  <Text style={styles.addBtnText}>+ Add someone to get</Text>
                </Pressable>
              </View>
            </>
          ) : null}

          {/* #173 — count + Manage line; Manage opens the untouchables
              management layer (inside this same Modal). #257: the full
              sheet upgrades this to up to 2 name chips + overflow count,
              still the same Manage entry point. */}
          {untouchablesEnabled ? (
            full ? (
              <>
                <Text style={styles.dnaGroupHdr}>Off the table</Text>
                <View style={styles.untLine}>
                  {untouchableRows.slice(0, 2).map((row) => (
                    <View key={row.id} style={styles.miniChip}>
                      <View
                        style={[
                          styles.miniChipDot,
                          { backgroundColor: dnaPosColor(row.position || '') },
                        ]}
                      />
                      <Text style={styles.miniChipText} numberOfLines={1}>
                        {row.name}
                      </Text>
                    </View>
                  ))}
                  {untouchableRows.length > 2 ? (
                    <Text style={styles.untOverflow}>
                      +{untouchableRows.length - 2}
                    </Text>
                  ) : null}
                  {untouchableRows.length === 0 ? (
                    <Text style={styles.untProtected}>None yet</Text>
                  ) : null}
                  <Pressable
                    testID="finder-hub.dna.untouchables"
                    accessibilityRole="button"
                    accessibilityLabel={`Manage untouchables, ${untouchableCount}`}
                    onPress={() => {
                      haptics.selection();
                      setUntouchablesOpen(true);
                    }}
                    hitSlop={8}
                    style={{ marginLeft: 'auto' }}
                  >
                    {({ pressed }) => (
                      <Text
                        style={[styles.manageLink, pressed && { color: chalk.base }]}
                      >
                        Manage
                      </Text>
                    )}
                  </Pressable>
                </View>
              </>
            ) : (
              <View style={styles.untLine}>
                <Text style={styles.sumKey}>Untouchables</Text>
                <Text style={styles.untCount}>{untouchableCount}</Text>
                <Text style={styles.untProtected}>protected</Text>
                <Pressable
                  testID="finder-hub.dna.untouchables"
                  accessibilityRole="button"
                  accessibilityLabel={`Manage untouchables, ${untouchableCount}`}
                  onPress={() => {
                    haptics.selection();
                    setUntouchablesOpen(true);
                  }}
                  hitSlop={8}
                  style={{ marginLeft: 'auto' }}
                >
                  {({ pressed }) => (
                    <Text
                      style={[styles.manageLink, pressed && { color: chalk.base }]}
                    >
                      Manage
                    </Text>
                  )}
                </Pressable>
              </View>
            )
          ) : null}

          {/* #257 — "Fine tuning": both engine levers, demoted below a
              hairline (variant C). Same slider/pill constructions and the
              landed #256 lane wording — nothing new invented, just visual
              weight moved down. */}
          {full ? (
            <>
              <View style={styles.hairline} />
              <Text style={[styles.dnaGroupHdr, styles.fineHdr]}>
                Fine tuning
              </Text>
              <View style={styles.fineRow}>
                <Text style={styles.fineLbl}>Trade fairness</Text>
                <Pressable
                  testID="dna.fine.fairness"
                  onPress={() => full.onToggleFairness(!full.fairnessOn)}
                  accessibilityRole="switch"
                  accessibilityLabel="Trade fairness"
                  accessibilityState={{ checked: full.fairnessOn }}
                  style={styles.fairnessSliderTap}
                  hitSlop={8}
                >
                  <View style={styles.fairnessTrack}>
                    <View
                      style={[
                        styles.fairnessThumb,
                        full.fairnessOn
                          ? styles.fairnessThumbOn
                          : styles.fairnessThumbOff,
                      ]}
                    />
                  </View>
                </Pressable>
                <Text style={styles.fineCaption}>
                  {full.fairnessOn ? 'Balanced trades' : 'Ranked by mismatch'}
                </Text>
              </View>
              {full.deckHasLanes ? (
                <View style={styles.fineRow}>
                  <Text style={styles.fineLbl}>Focus</Text>
                  <View style={styles.fineLaneRow}>
                    {(
                      [
                        ['window', 'Team-fit moves'],
                        ['value', 'Value moves'],
                      ] as const
                    ).map(([lane, label]) => {
                      const active = full.laneFilter === lane;
                      return (
                        <Pressable
                          key={lane}
                          testID={`dna.fine.lane.${lane}`}
                          onPress={() => full.onLaneFilter(lane)}
                          accessibilityRole="button"
                          accessibilityState={{ selected: active }}
                          style={({ pressed }) => [
                            styles.fineLanePill,
                            active && styles.fineLanePillActive,
                            pressed && { backgroundColor: ink.ink3 },
                          ]}
                        >
                          <Text
                            style={[
                              styles.fineLanePillText,
                              active && styles.fineLanePillTextActive,
                            ]}
                          >
                            {label}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </View>
                </View>
              ) : null}
            </>
          ) : null}
        </ScrollView>
      </View>

      {/* #173 — untouchables management, layered INSIDE this Modal (a
          sibling Modal wouldn't present over an open one on iOS). Scrim
          tap or hardware back closes just this layer. */}
      {untouchablesOpen ? (
        <>
          <Pressable
            style={styles.backdrop}
            onPress={() => setUntouchablesOpen(false)}
            accessibilityRole="button"
            accessibilityLabel="Close untouchables"
          />
          <View style={[styles.sheet, { paddingBottom: insets.bottom + space.lg }]}>
            <View style={styles.grabber} />
            <Text style={type.heading} accessibilityRole="header">
              Untouchables
            </Text>
            <Text style={type.bodySm}>
              Never offered from your roster in trade ideas. Add one below,
              or hold a player you'd send on any trade card and pick "Mark
              untouchable".
            </Text>
            {/* #259 — pick straight from your own roster. #173 deliberately
                shipped without this; the gap it left is that a player no
                trade idea ever offers could not be protected at all. */}
            <Button
              variant="secondary"
              compact
              label="Add from your roster"
              testID="untouchables.add-from-roster"
              onPress={() => {
                haptics.selection();
                setRosterQuery('');
                setRosterPickOpen(true);
              }}
            />
            {untouchableNamesQuery.isLoading ? (
              <ActivityIndicator
                color={ice.base}
                style={{ marginTop: space.lg }}
              />
            ) : (
              <ScrollView style={styles.pickerScroll}>
                {untouchableRows.map((row) => (
                  <View
                    key={row.id}
                    testID={`finder-hub.untouchables.row.${row.id}`}
                    style={styles.pickerRow}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={styles.pickerName}>{row.name}</Text>
                      {row.position ? (
                        <Text style={styles.dnaEmpty}>{row.position}</Text>
                      ) : null}
                    </View>
                    <Button
                      variant="ghost"
                      compact
                      label="Remove"
                      testID={`finder-hub.untouchables.remove.${row.id}`}
                      disabled={removeUntouchable.isPending}
                      onPress={() => removeUntouchable.mutate(row.id)}
                    />
                  </View>
                ))}
                {untouchableRows.length === 0 ? (
                  <Text style={styles.dnaEmpty}>
                    None yet — hold a player you'd send on any trade card.
                  </Text>
                ) : null}
              </ScrollView>
            )}
          </View>
        </>
      ) : null}

      {/* #259 — roster picker, layered over the untouchables layer inside
          this same Modal (see the note by the queries above for why this
          is not PlayerPickerModal). Rows are the user's OWN roster only —
          untouchable is a promise about your players, so a leaguemate's
          roster has no meaning here. Already-protected players are absent:
          they are in the list one layer down. */}
      {untouchablesOpen && rosterPickOpen ? (
        <>
          <Pressable
            style={styles.backdrop}
            onPress={() => setRosterPickOpen(false)}
            accessibilityRole="button"
            accessibilityLabel="Close roster picker"
          />
          <View style={[styles.sheet, { paddingBottom: insets.bottom + space.lg }]}>
            <View style={styles.grabber} />
            <View style={styles.sheetTop}>
              <Text style={type.heading} accessibilityRole="header">
                Protect a player
              </Text>
              <Pressable
                testID="untouchables.roster-back"
                accessibilityRole="button"
                accessibilityLabel="Back to untouchables"
                onPress={() => setRosterPickOpen(false)}
                hitSlop={8}
                style={{ marginLeft: 'auto' }}
              >
                {({ pressed }) => (
                  <Text
                    style={[styles.manageLink, pressed && { color: chalk.base }]}
                  >
                    Done
                  </Text>
                )}
              </Pressable>
            </View>
            <Text style={type.bodySm}>
              Tap a player from your roster. Protected players are never
              offered from your side of a trade idea.
            </Text>
            <TextInput
              testID="untouchables.roster-search"
              value={rosterQuery}
              onChangeText={setRosterQuery}
              placeholder="Search your roster"
              placeholderTextColor={chalk.faint}
              autoCorrect={false}
              accessibilityLabel="Search your roster"
              style={styles.rosterSearch}
            />
            {rostersQuery.isLoading || untouchableNamesQuery.isLoading ? (
              <ActivityIndicator
                color={ice.base}
                style={{ marginTop: space.lg }}
              />
            ) : (
              <ScrollView style={styles.pickerScroll}>
                {myRosterRows.map((p) => (
                  <Pressable
                    key={p.id}
                    testID={`untouchables.roster-row.${p.id}`}
                    accessibilityRole="button"
                    accessibilityLabel={`Protect ${p.name}`}
                    disabled={addUntouchable.isPending}
                    onPress={() => {
                      haptics.selection();
                      addUntouchable.mutate(p.id);
                    }}
                    style={({ pressed }) => [
                      styles.pickerRow,
                      pressed && { backgroundColor: ink.ink3 },
                    ]}
                  >
                    <View
                      style={[
                        styles.rosterDot,
                        { backgroundColor: dnaPosColor(p.position) },
                      ]}
                    />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.pickerName}>{p.name}</Text>
                      <Text style={styles.dnaEmpty}>
                        {p.position}
                        {p.team ? ` · ${p.team}` : ''}
                      </Text>
                    </View>
                    <Button
                      variant="ghost"
                      compact
                      label="Protect"
                      testID={`untouchables.roster-add.${p.id}`}
                      disabled={addUntouchable.isPending}
                      onPress={() => {
                        haptics.selection();
                        addUntouchable.mutate(p.id);
                      }}
                    />
                  </Pressable>
                ))}
                {myRosterRows.length === 0 ? (
                  <Text testID="untouchables.roster-empty" style={styles.dnaEmpty}>
                    {rosterQuery.trim()
                      ? 'No one on your roster matches that name.'
                      : 'Nothing left to protect — every valued player on your roster is already an untouchable.'}
                  </Text>
                ) : null}
              </ScrollView>
            )}
          </View>
        </>
      ) : null}
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '85%',
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    padding: space.lg,
    gap: space.sm,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.xs,
  },
  sheetTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  doneBtn: {
    minHeight: 32,
    paddingHorizontal: space.md,
    borderRadius: radii.sm,
    backgroundColor: ice.base,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  doneText: { ...type.bodySm, color: ice.on, fontFamily: fonts.uiBold },
  bodyScroll: { flexGrow: 0, flexShrink: 1 },
  body: { gap: space.sm },

  // Editor bits — lifted from the hub's #212 panel styles.
  dnaGroupHdr: { ...type.label, marginTop: 2 },
  dnaMs: { color: ice.base },
  dnaSub: { color: chalk.faint, textTransform: 'none', fontWeight: '400' },
  outGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  outCard: {
    flexBasis: '48%',
    flexGrow: 1,
    minHeight: 44,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    backgroundColor: ink.ink1,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  outCardSel: { borderColor: ice.base },
  outCardTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  outCardTitle: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  outCardTick: { width: 3, height: 12, backgroundColor: ice.base },
  outCardBias: {
    ...type.bodySm,
    fontSize: 11,
    lineHeight: 15,
    color: chalk.dim,
    marginTop: 1,
  },
  toggleRow: { flexDirection: 'row', gap: 6 },
  ptb: {
    flex: 1,
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    paddingHorizontal: 2,
  },
  ptbDot: { width: 7, height: 7, borderRadius: radii.xs },
  ptbText: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  ptbTextSel: { color: ice.on, fontFamily: fonts.uiBold },
  // #172 — trade intent chips reuse the ptb (position-toggle) shape but
  // fill with the ice action accent (no per-item color like positions).
  intentChipSel: { backgroundColor: ice.base, borderColor: ice.base },
  dnaHint: {
    ...type.bodySm,
    fontSize: 11,
    lineHeight: 15,
    color: chalk.dim,
  },
  dnaErrorText: { ...type.bodySm, color: semantic.neg },
  untLine: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  sumKey: { ...type.bodySm, color: chalk.dim },
  untCount: { ...type.data, color: chalk.base, fontFamily: fonts.dataSemi },
  untProtected: { ...type.bodySm, color: chalk.dim },
  manageLink: { ...type.bodySm, color: ice.base, fontFamily: fonts.uiSemi },
  dnaEmpty: { ...type.bodySm, color: chalk.faint },
  untOverflow: { ...type.bodySm, color: chalk.dim },

  // #269 — league picker row, same row construction as a picker-modal
  // trigger (name + ice chevron, ink-1 fill, hairline border).
  leaguePickerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 44,
    paddingHorizontal: space.md,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.xs,
    backgroundColor: ink.ink1,
  },
  leaguePickerName: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi, flex: 1 },

  // #257 — full-sheet-only additions (variant C). Positions: a label +
  // sublabel to the left of the same toggleRow, instead of a header line
  // above it (mockups/polish-lab-2026-08/trades-edit-full-sheet.html).
  posLine: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  posLbl: { width: 64, flex: 0 },
  posLblText: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  posLblSub: { ...type.bodySm, fontSize: 11, color: chalk.faint },

  // Specific players — same chip/add-button construction as the Controls
  // Card's targeting block, lifted here since that block is cut on this
  // screen when the full sheet is on.
  chipsWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  targetChip: {
    minHeight: 32,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: space.sm,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: ink.ink1,
  },
  targetChipDir: {
    fontFamily: fonts.dataSemi,
    fontSize: 10,
    letterSpacing: 0.5,
    color: chalk.dim,
  },
  targetChipName: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  addRow: { flexDirection: 'row', gap: space.sm },
  addBtn: {
    flex: 1,
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: ink.lineStrong,
    borderRadius: radii.xs,
  },
  addBtnText: { ...type.bodySm, color: chalk.dim },

  // Off the table — up to 2 name chips (mini position dot + name) ahead
  // of the overflow count and Manage link, all sharing `untLine`.
  miniChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.xs,
    backgroundColor: ink.ink1,
    paddingHorizontal: 7,
    paddingVertical: 4,
    maxWidth: 120,
  },
  miniChipDot: { width: 6, height: 6, borderRadius: radii.xs },
  miniChipText: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },

  // Fine tuning — trade fairness + lane, demoted below a hairline. Same
  // slider construction TradesScreen's Controls Card used (4px ink-3
  // track, 16px square ice thumb).
  hairline: { height: 1, backgroundColor: ink.line, marginVertical: 2 },
  fineHdr: { color: chalk.faint },
  fineRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  fineLbl: { ...type.bodySm, width: 84, flex: 0, color: chalk.dim },
  fineCaption: { ...type.bodySm, fontSize: 11, color: chalk.faint, flex: 1 },
  fairnessSliderTap: { width: 56, height: 36, justifyContent: 'center' },
  fairnessTrack: { height: 4, backgroundColor: ink.ink3 },
  fairnessThumb: {
    position: 'absolute',
    top: -6,
    width: 16,
    height: 16,
    borderRadius: radii.xs,
  },
  fairnessThumbOn: { right: 0, backgroundColor: ice.base },
  fairnessThumbOff: { left: 0, backgroundColor: ink.lineStrong },
  fineLaneRow: { flexDirection: 'row', gap: space.xs, flex: 1 },
  fineLanePill: {
    flex: 1,
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.xs,
    backgroundColor: ink.ink1,
    paddingHorizontal: 4,
  },
  fineLanePillActive: { borderColor: ink.lineStrong, backgroundColor: ink.ink3 },
  fineLanePillText: { ...type.bodySm, fontSize: 11, color: chalk.dim },
  fineLanePillTextActive: { color: chalk.base, fontFamily: fonts.uiSemi },

  // Untouchables management layer list (shared row construction).
  pickerScroll: { flexGrow: 0, flexShrink: 1, marginTop: space.sm },
  pickerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.md,
    paddingHorizontal: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  pickerName: { ...type.title },
  // #259 — roster picker layer.
  rosterSearch: {
    ...type.body,
    color: chalk.base,
    minHeight: 44,
    paddingHorizontal: space.md,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.xs,
    backgroundColor: ink.ink1,
  },
  rosterDot: { width: 6, height: 6, marginRight: space.sm },
});

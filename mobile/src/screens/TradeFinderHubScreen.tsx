import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  Modal,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import {
  ink,
  chalk,
  ice,
  flare,
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
import { Icon, Button, TickLabel } from '../components/chalkline';
import { useSession } from '../state/useSession';
import { useFinderTargets } from '../state/useFinderTargets';
import { useFlag } from '../state/useFeatureFlags';
import { haptics } from '../utils/haptics';
import {
  getLeaguePreferences,
  saveLeaguePreferences,
  getAssetPrefs,
  setAssetPref,
  type Outlook,
  type LeaguePreferences,
} from '../api/league';
import { getLeagueUsers } from '../api/sleeper';
import { getTradeValues } from '../api/calc';

// FB #156 — Trade-Finding Hub (Variant B, "Launcher Hub"). The Trades tab
// home (behind flag `trades.finder_hub`): a Trade DNA summary panel + four
// mode launcher cards. Each card opens its surface full-screen; the deck
// modes carry a lateral quick-switch chip row (TradeFinderModeBar) so users
// jump between modes without returning here. Card-launcher pattern mirrors
// RankHomeScreen's method chooser. Everything is a re-composition of shipped
// features — no mode reimplements trade generation.

// #212/#206 — Trade DNA panel v3 (approved mock mockups/polish-lab-2026-08/
// trade-dna-outlook-v3.html, plus two operator tweaks on top of it:
// the NEED/DEPTH roster-scan hint tags are DROPPED entirely ("overkill"),
// and the untouchable mini-cards read "A Jeanty" — first-name initial +
// last name). Collapsed by default: outlook chip + one summary line
// listing ALL selections + untouchable mini-cards. Edit expands IN PLACE:
// four outlook cards + Chasing/Shopping multi-select toggle rows (Picks
// is a fifth toggle) + count/Manage untouchables line. #236: every tap
// in the editor AUTOSAVES via the same preferences API OutlookSheet used
// (in-flight coalesced, last-write-wins); Done is a pure collapse. The hub no
// longer mounts OutlookSheet (the sheet survives for TradesScreen's own
// entry points — see docs/feedback/items/212-trade-dna-redesign/status.md).

// The Picks toggle stores 'PICK' — the backend's pick pseudo-player
// position — so the FB-47 counterparty-fit targeting already understands
// it; the /api/league/preferences POST validates array-ness only.
const DNA_POSITIONS = [
  { key: 'QB', label: 'QB', tid: 'qb' },
  { key: 'RB', label: 'RB', tid: 'rb' },
  { key: 'WR', label: 'WR', tid: 'wr' },
  { key: 'TE', label: 'TE', tid: 'te' },
  { key: 'PICK', label: 'Picks', tid: 'picks' },
] as const;

// Expanded editor cards — plain-words bias line per outlook (v3 mock).
const OUTLOOK_CARDS: {
  key: NonNullable<Outlook>;
  title: string;
  bias: string;
}[] = [
  { key: 'rebuilder', title: 'Rebuilding', bias: 'Leans young + picks' },
  { key: 'contender', title: 'Contending', bias: 'Balanced moves' },
  { key: 'championship', title: 'All-in', bias: 'Win now, spend picks' },
  { key: 'jets', title: 'Tanking', bias: 'Max youth, high picks' },
];

// Collapsed chip copy — every outlook value maps to a plain-words bias.
const OUTLOOK_CHIP: Record<string, { title: string; bias: string }> = {
  rebuilder: { title: 'Rebuilding', bias: 'leans young + picks' },
  contender: { title: 'Contending', bias: 'balanced moves' },
  championship: { title: 'All-in', bias: 'win now, spend picks' },
  jets: { title: 'Tanking', bias: 'max youth, high picks' },
  not_sure: { title: 'Not sure', bias: 'no bias applied' },
};

// Position-color for the DNA dots/fills; Picks uses the 1st-round tier
// teal (the pick data color the deck's pick rows already use).
function dnaPosColor(pos: string): string {
  if (pos === 'PICK' || pos === 'PICKS') return tier.first_1;
  return posColor(pos as any) ?? ink.lineStrong;
}

// "Ashton Jeanty" → "A Jeanty" (operator tweak on the v3 mock, which
// showed last name only). Single-token names pass through untouched.
function shortName(full: string): string {
  const parts = full.trim().split(/\s+/);
  if (parts.length < 2) return full;
  return `${parts[0].charAt(0)} ${parts.slice(1).join(' ')}`;
}

// One Chasing/Shopping toggle button. Selected = solid position-color
// fill + check glyph + bolded dark label — the check is the primary state
// cue (never color alone; the mock flagged WR blue at ≈4.1:1, hence the
// weight bump). Unselected = line-strong outline + position dot.
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

interface ModeCard {
  key: 'guided' | 'team' | 'player' | 'calc';
  icon: React.ComponentProps<typeof Icon>['name'];
  title: string;
  body: string;
  recommended?: boolean;
}

const MODE_CARDS: ModeCard[] = [
  {
    key: 'guided',
    icon: 'crown',
    title: 'Fully Guided',
    body: 'We read your roster & league and walk you to the best deals.',
    recommended: true,
  },
  {
    key: 'team',
    icon: 'match',
    title: 'Specific Team',
    body: 'Target one league-mate and see only mutual-gain deals.',
  },
  {
    key: 'player',
    icon: 'swap',
    title: 'Specific Player',
    body: 'Trade for someone, away someone, or both — engine fills the rest.',
  },
  {
    key: 'calc',
    icon: 'trade',
    title: 'Manual Calculator',
    body: 'Hand-build any trade, get the dual-board fairness verdict.',
  },
];

export default function TradeFinderHubScreen({ navigation, route }: any) {
  const queryClient = useQueryClient();
  const league = useSession((s) => s.league);
  const user = useSession((s) => s.user);
  const leagueId = league?.league_id || null;
  const userId = user?.user_id || '';

  const [teamPickerOpen, setTeamPickerOpen] = useState(false);
  const [untouchablesOpen, setUntouchablesOpen] = useState(false);

  // #212 — in-place DNA editor state. Drafts mirror the saved prefs until
  // the user touches a control (dnaTouched). #236: every tap autosaves
  // (Done is a pure collapse); an idle expand/collapse still fires no
  // POST, so a mere look never invalidates the backend's cached deck.
  const [dnaEditing, setDnaEditing] = useState(false);
  const [draftOutlook, setDraftOutlook] = useState<NonNullable<Outlook> | null>(
    null,
  );
  const [draftChasing, setDraftChasing] = useState<string[]>([]);
  const [draftShopping, setDraftShopping] = useState<string[]>([]);
  const [dnaError, setDnaError] = useState<string | null>(null);
  const dnaTouched = useRef(false);

  // #156 finish item 3 — live pin counts for the Specific Player card.
  // Pins live in the shared useFinderTargets store (session-only, cleared
  // on league switch), so counts survive hub ⇄ deck navigation.
  const pinnedForCount = useFinderTargets((s) => s.pinnedReceive.length);
  const pinnedAwayCount = useFinderTargets((s) => s.pinnedGive.length);

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
    enabled: !!leagueId,
    staleTime: 60_000,
  });
  const untouchableIds = assetPrefsQuery.data?.untouchables ?? [];
  const untouchableCount = untouchableIds.length;

  // #173 — resolve untouchable ids to names for the management sheet.
  // The universal value pool is the same id→name source the deck's swap
  // sheet uses; format doesn't change names, so 1QB is fine here. Shares
  // the ['calc-values', …] cache. #212: also fetched whenever the list is
  // non-empty — the collapsed panel's mini-cards need names at a glance,
  // not only behind Manage.
  const untouchableNamesQuery = useQuery({
    queryKey: ['calc-values', '1qb_ppr'],
    queryFn: ({ signal }) => getTradeValues('1qb_ppr', signal),
    enabled: untouchablesOpen || untouchableCount > 0,
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
    mutationFn: (playerId: string) =>
      setAssetPref(leagueId!, playerId, 'none'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['asset-prefs', leagueId] });
    },
  });

  // League managers for the Specific Team picker — lazily loaded when the
  // picker opens. Shares the ['league-users', leagueId] cache with TradesScreen.
  const leagueUsersQuery = useQuery({
    queryKey: ['league-users', leagueId],
    queryFn: () => getLeagueUsers(leagueId!),
    enabled: !!leagueId && teamPickerOpen,
    staleTime: 5 * 60_000,
  });
  const opponents = useMemo(
    () => (leagueUsersQuery.data ?? []).filter((u) => u.user_id !== userId),
    [leagueUsersQuery.data, userId],
  );

  // #212/#206 — collapsed summary reads the EXPLICIT selections only.
  // The #193 splitDnaChips NEED/DEPTH recommendation chips are gone per
  // operator decision (#206: "overkill... drop it"); position_needs /
  // position_surplus stay on the payload for other surfaces.
  const chasingSel = DNA_POSITIONS.filter((p) =>
    (prefs?.acquire_positions ?? []).includes(p.key),
  );
  const shoppingSel = DNA_POSITIONS.filter((p) =>
    (prefs?.trade_away_positions ?? []).includes(p.key),
  );

  // Collapsed outlook chip: declared outlook, else the backend inference
  // (marked), else an honest not-set nudge.
  const declaredOutlook = prefs?.team_outlook ?? null;
  const resolvedOutlook = declaredOutlook ?? prefs?.inferred_outlook ?? null;
  const outlookChip = resolvedOutlook ? OUTLOOK_CHIP[resolvedOutlook] : undefined;

  // Seed the drafts from saved prefs whenever the panel is idle (or the
  // editor is open but untouched — covers the editDna auto-expand racing
  // the prefs fetch). Once the user touches a control the drafts are
  // theirs until Done/collapse.
  useEffect(() => {
    if (dnaEditing && dnaTouched.current) return;
    setDraftOutlook(
      (prefs?.team_outlook as NonNullable<Outlook>) ??
        (prefs?.inferred_outlook as NonNullable<Outlook>) ??
        null,
    );
    setDraftChasing(prefs?.acquire_positions ?? []);
    setDraftShopping(prefs?.trade_away_positions ?? []);
  }, [prefs, dnaEditing]);

  // #231 — the deck receipt's "Change" link lands here with editDna:true;
  // auto-expand the editor and consume the param.
  useEffect(() => {
    if (route?.params?.editDna) {
      setDnaEditing(true);
      navigation?.setParams?.({ editDna: undefined });
    }
  }, [route?.params?.editDna]);

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
        // #360 — COMPILE FIX ONLY. This screen is UNROUTED dead code kept
        // in tree per #246 (navigation/TabNav.tsx says so explicitly); the
        // Avoiding UI is deliberately NOT built here. `avoid_positions`
        // became required on LeaguePreferences, so this literal needs the
        // key to typecheck and nothing more.
        avoid_positions: [],
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['league-prefs', leagueId] });
    },
  });

  // #236 — autosave: every editor tap persists immediately (no Done
  // gate). One POST in flight at a time; taps landing mid-flight coalesce
  // into a single trailing save of the latest FULL payload, so the last
  // write wins and requests can't complete out of order.
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
      // the last-saved prefs, and surface the existing inline error line.
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
    dnaDesired.current = payload;
    void flushDnaSave();
  };

  const openDnaEdit = () => {
    haptics.selection();
    dnaTouched.current = false;
    setDnaError(null);
    setDnaEditing(true);
  };

  const pickOutlook = (key: NonNullable<Outlook>) => {
    haptics.selection();
    if (draftOutlook === key) return; // re-tapping the pick isn't an edit
    dnaTouched.current = true;
    setDnaError(null);
    setDraftOutlook(key);
    queueDnaSave({ outlook: key, acquire: draftChasing, shed: draftShopping });
  };

  // Multi-select within a row; cross-row mutual exclusion MOVES the
  // position (tapping a position selected on the other row selects it
  // here and clears it there — never an error). #236: next values are
  // computed up front so the tap can autosave the exact state it shows.
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
      // 'not_sure' is the honest no-choice value (chip: "no bias applied").
      outlook: draftOutlook ?? 'not_sure',
      acquire: nextChasing,
      shed: nextShopping,
    });
  };

  // #236 — Done is a pure collapse affordance: every edit already saved
  // on tap, so collapsing never POSTs.
  const handleDnaDone = () => {
    haptics.selection();
    dnaTouched.current = false;
    setDnaError(null);
    setDnaEditing(false);
  };

  const openMode = (key: ModeCard['key']) => {
    haptics.selection();
    if (key === 'calc') {
      navigation.navigate('TradeCalculator');
    } else if (key === 'team') {
      setTeamPickerOpen(true);
    } else {
      navigation.navigate('TradeDeck', { mode: key });
    }
  };

  const pickTeam = (opponentUserId: string, opponentName: string) => {
    haptics.selection();
    setTeamPickerOpen(false);
    navigation.navigate('TradeDeck', {
      mode: 'team',
      opponentUserId,
      opponentName,
    });
  };

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.header}>
          {/* #245 — page retitled to match the renamed tab; the TRADE
              section label below carries the trade context. */}
          <Text style={styles.pageTitle} accessibilityRole="header">
            Acquire
          </Text>
        </View>
        {/* #223 — the "Trading in" LeaguePill row is gone: the global
            TopBar now carries the active league + switcher on every tab,
            and its ~63pt goes back to hub content (feeds the #218
            fit-to-screen pass). */}

        {/* #245 — TRADE section header: heads the existing hub content
            (Trade DNA panel + mode cards) now that the page title says
            "Acquire" rather than "Find a Trade". */}
        <TickLabel>Trade</TickLabel>

        {/* #212 Trade DNA panel — collapsed summary by default; Edit
            expands the editor IN PLACE (no sheet). */}
        <View style={styles.dna}>
          <View style={styles.dnaTop}>
            <Text style={styles.dnaLabel}>Your Trade DNA</Text>
            {dnaEditing ? (
              // #236 — pure collapse control (edits autosave per tap), so
              // it never disables or spins on an in-flight save.
              <Pressable
                testID="dna.done"
                accessibilityRole="button"
                accessibilityLabel="Done editing trade preferences"
                onPress={handleDnaDone}
                hitSlop={8}
                style={({ pressed }) => [
                  styles.doneBtn,
                  pressed && { backgroundColor: ice.press },
                ]}
              >
                <Icon name="check" size={13} color={ice.on} />
                <Text style={styles.doneText}>Done</Text>
              </Pressable>
            ) : (
              <Pressable
                testID="dna.edit"
                accessibilityRole="button"
                accessibilityLabel="Edit trade preferences"
                onPress={openDnaEdit}
                hitSlop={8}
                style={({ pressed }) => [
                  styles.editBtn,
                  pressed && { borderColor: ice.base },
                ]}
              >
                <Text style={styles.editText}>Edit</Text>
              </Pressable>
            )}
          </View>

          {!dnaEditing ? (
            <>
              {/* Collapsed: outlook chip + one summary line + untouchable
                  mini-cards. Nothing here is tappable — Edit is the panel's
                  single affordance (v3 mock). */}
              <View style={styles.outChip}>
                <View style={styles.outChipTick} />
                <Text style={styles.outChipTitle}>
                  {outlookChip?.title ?? 'Not set'}
                </Text>
                <Text style={styles.outChipBias}>
                  {' · '}
                  {outlookChip
                    ? `${outlookChip.bias}${
                        !declaredOutlook && resolvedOutlook !== null
                          ? ' · inferred'
                          : ''
                      }`
                    : 'tap Edit to choose'}
                </Text>
              </View>

              {chasingSel.length > 0 || shoppingSel.length > 0 ? (
                <View style={styles.sumLine}>
                  {chasingSel.length > 0 ? (
                    <Text style={styles.sumKey}>Chasing</Text>
                  ) : null}
                  {chasingSel.map((p) => (
                    <View key={`c-${p.key}`} style={styles.sumMini}>
                      <View
                        style={[
                          styles.sumDot,
                          { backgroundColor: dnaPosColor(p.key) },
                        ]}
                      />
                      <Text style={styles.sumMiniText}>{p.label}</Text>
                    </View>
                  ))}
                  {chasingSel.length > 0 && shoppingSel.length > 0 ? (
                    <Text style={styles.sumSep}>—</Text>
                  ) : null}
                  {shoppingSel.length > 0 ? (
                    <Text style={styles.sumKey}>Shopping</Text>
                  ) : null}
                  {shoppingSel.map((p) => (
                    <View key={`s-${p.key}`} style={styles.sumMini}>
                      <View
                        style={[
                          styles.sumDot,
                          { backgroundColor: dnaPosColor(p.key) },
                        ]}
                      />
                      <Text style={styles.sumMiniText}>{p.label}</Text>
                    </View>
                  ))}
                </View>
              ) : null}

              {/* Untouchable mini-cards (collapsed only, cap 3 + "+N"):
                  6px position dot + "A Jeanty". Read-only. */}
              {untouchablesEnabled && untouchableCount > 0 ? (
                <View style={styles.untRow}>
                  <Text style={styles.sumKey}>Untouchables</Text>
                  {untouchableRows.slice(0, 3).map((row) => (
                    <View
                      key={row.id}
                      testID={`dna.untouchable.${row.id}`}
                      style={styles.untChip}
                    >
                      <View
                        style={[
                          styles.untDot,
                          {
                            backgroundColor: row.position
                              ? dnaPosColor(row.position.toUpperCase())
                              : ink.lineStrong,
                          },
                        ]}
                      />
                      <Text style={styles.untChipText}>
                        {shortName(row.name)}
                      </Text>
                    </View>
                  ))}
                  {untouchableCount > 3 ? (
                    <Text style={styles.untMore}>+{untouchableCount - 3}</Text>
                  ) : null}
                </View>
              ) : null}
            </>
          ) : (
            <>
              {/* Expanded editor — outlook cards + multi-select rows. */}
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
                        style={[
                          styles.outCardBias,
                          sel && { color: chalk.base },
                        ]}
                      >
                        {o.bias}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>

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
                Pick as many per row as apply. A position can't be both
                chased and shopped — tapping it on one row moves it there.
              </Text>

              {dnaError ? (
                <Text style={styles.dnaErrorText}>{dnaError}</Text>
              ) : null}

              {/* #173 — expanded keeps the count + Manage line (mini-cards
                  are collapsed-only per the operator). Manage opens the
                  existing management sheet. */}
              {untouchablesEnabled ? (
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
                        style={[
                          styles.dnaEdit,
                          pressed && { color: chalk.base },
                        ]}
                      >
                        Manage
                      </Text>
                    )}
                  </Pressable>
                </View>
              ) : null}
            </>
          )}
        </View>

        <Text style={styles.sectionLabel}>How do you want to find trades?</Text>

        {MODE_CARDS.map((m) => {
          // #156 finish item 3 — the Specific Player card carries the LIVE
          // pin counts (mockup's "1 for · 1 away" status line) instead of
          // static copy once anything is pinned.
          const playerPins = pinnedForCount + pinnedAwayCount;
          const body =
            m.key === 'player' && playerPins > 0
              ? `${pinnedForCount} to trade for · ${pinnedAwayCount} to trade away`
              : m.body;
          return (
            <Pressable
              key={m.key}
              testID={`finder-hub.card.${m.key}`}
              accessibilityRole="button"
              accessibilityLabel={
                m.recommended ? `${m.title}, recommended` : m.title
              }
              accessibilityHint={body}
              onPress={() => openMode(m.key)}
              style={({ pressed }) => [
                styles.card,
                pressed && { backgroundColor: ink.ink2 },
              ]}
            >
              <View style={styles.cardIcon}>
                <Icon name={m.icon} size={20} color={ice.base} />
              </View>
              <View style={{ flex: 1 }}>
                <View style={styles.cardTitleRow}>
                  <Text style={styles.cardTitle}>{m.title}</Text>
                  {m.recommended ? (
                    <Text style={styles.recTag}>recommended</Text>
                  ) : null}
                </View>
                <Text
                  style={[
                    styles.cardBody,
                    m.key === 'player' && playerPins > 0 && styles.cardBodyLive,
                  ]}
                >
                  {body}
                </Text>
              </View>
              <Icon name="chevron-right" size={18} color={chalk.faint} />
            </Pressable>
          );
        })}

        {/* #245 — FREE AGENCY section: one row linking to the existing
            Free Agent finder (root-stack route 'FreeAgents', #143 — the
            navigate call bubbles up from this tab screen to RootNav; the
            League tab's entry row stays in place). */}
        <TickLabel>Free agency</TickLabel>
        <Pressable
          testID="finder-hub.card.free-agents"
          accessibilityRole="button"
          accessibilityLabel="Free agent finder"
          accessibilityHint="Best available players, ranked by your board values."
          onPress={() => {
            haptics.selection();
            navigation.navigate('FreeAgents');
          }}
          style={({ pressed }) => [
            styles.card,
            pressed && { backgroundColor: ink.ink2 },
          ]}
        >
          <View style={styles.cardIcon}>
            <Icon name="plus" size={20} color={ice.base} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.cardTitle}>Free Agent Finder</Text>
            <Text style={styles.cardBody}>
              Best available players, ranked by your board values.
            </Text>
          </View>
          <Icon name="chevron-right" size={18} color={chalk.faint} />
        </Pressable>
      </ScrollView>

      {/* Specific Team — manager picker sheet. */}
      <Modal
        visible={teamPickerOpen}
        transparent
        animationType="slide"
        onRequestClose={() => setTeamPickerOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setTeamPickerOpen(false)}
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        <View style={styles.sheet}>
          <View style={styles.grabber} />
          <Text style={type.heading} accessibilityRole="header">
            Pick a manager
          </Text>
          <Text style={type.bodySm}>
            We'll surface only mutual-gain deals with their roster.
          </Text>
          {leagueUsersQuery.isLoading ? (
            <ActivityIndicator color={ice.base} style={{ marginTop: space.lg }} />
          ) : (
            <ScrollView style={styles.pickerScroll}>
              {opponents.map((o) => {
                const name = o.display_name || o.username || o.user_id;
                return (
                  <Pressable
                    key={o.user_id}
                    testID={`finder-hub.team-picker.${o.user_id}`}
                    accessibilityRole="button"
                    accessibilityLabel={name}
                    onPress={() => pickTeam(o.user_id, name)}
                    style={({ pressed }) => [
                      styles.pickerRow,
                      pressed && { backgroundColor: ink.ink3 },
                    ]}
                  >
                    <Text style={styles.pickerName}>{name}</Text>
                    <Icon name="chevron-right" size={16} color={chalk.dim} />
                  </Pressable>
                );
              })}
              {opponents.length === 0 ? (
                <Text style={styles.dnaEmpty}>No league-mates found.</Text>
              ) : null}
            </ScrollView>
          )}
        </View>
      </Modal>

      {/* #173 — untouchables management sheet. The list + remove live
          here; ADDING stays where it always was (hold a give-side player
          on any trade card, or its visible lock toggle) — the how-to line
          points there instead of duplicating a player picker. */}
      <Modal
        visible={untouchablesOpen}
        transparent
        animationType="slide"
        onRequestClose={() => setUntouchablesOpen(false)}
      >
        <Pressable
          style={styles.backdrop}
          onPress={() => setUntouchablesOpen(false)}
          accessibilityRole="button"
          accessibilityLabel="Close"
        />
        <View style={styles.sheet}>
          <View style={styles.grabber} />
          <Text style={type.heading} accessibilityRole="header">
            Untouchables
          </Text>
          <Text style={type.bodySm}>
            Never offered from your roster in trade ideas. To add one, hold
            a player you'd send on any trade card and pick "Mark
            untouchable".
          </Text>
          {untouchablesOpen && untouchableNamesQuery.isLoading ? (
            <ActivityIndicator color={ice.base} style={{ marginTop: space.lg }} />
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
      </Modal>

      {/* #196/#197 — NO local FeedbackFAB here. TradesHome is a Trades-stack
          TAB screen, so RootNav's global mount already floats a FAB above the
          tab bar (activeScreen tracks the focused route → "TradesHome"). The
          hub's own mount (added in the hub-finish batch) rendered a SECOND
          flag at a different height — the two don't overlap because this one
          offsets from the screen's bottom edge, above the tab bar. Per the
          #188 convention only root-stack pushes mount their own. */}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  // #218/#219 fit-to-screen density pass (approved mock
  // mockups/polish-lab-2026-08/hub-fit-to-screen.html): screen padding
  // lg 16 → md 12, stack gap md 12 → sm 8 — the hub is a launcher, not a
  // reading surface, so the inter-block air is the cheapest height on the page.
  scroll: { padding: space.md, gap: space.sm },
  header: { flexDirection: 'row', alignItems: 'center' },
  pageTitle: { ...type.heading },

  // Trade DNA panel
  dna: {
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    backgroundColor: ink.ink1,
    // #218 — 12 → 10 pad, 8 → 6 inner gap per the mock; 10 and 6 have no
    // 4-pt-scale token (between sm 8 / md 12 and xs 4 / sm 8), so literals.
    padding: 10,
    gap: 6,
  },
  dnaTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  dnaLabel: { ...type.label },
  dnaEdit: { ...type.bodySm, color: ice.base, fontFamily: fonts.uiSemi },
  dnaEmpty: { ...type.bodySm, color: chalk.faint },

  // #212 — Edit (outline) / Done (ice fill) header buttons. 32pt visual
  // height per the mock; hitSlop 8 lifts the effective target past 44.
  editBtn: {
    minHeight: 32,
    paddingHorizontal: space.md,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  editText: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
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

  // Collapsed: outlook chip (specced pill), summary minis, untouchable chips.
  outChip: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.pill,
    backgroundColor: ink.ink2,
    paddingHorizontal: 11,
    paddingVertical: space.xs,
  },
  outChipTick: { width: 3, height: 11, backgroundColor: ice.base },
  outChipTitle: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  outChipBias: { ...type.bodySm, color: chalk.dim },
  sumLine: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    columnGap: 7,
    rowGap: space.xs,
  },
  sumKey: { ...type.bodySm, color: chalk.dim },
  sumMini: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  sumDot: { width: 7, height: 7, borderRadius: radii.xs },
  sumMiniText: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  sumSep: { ...type.bodySm, color: chalk.dim },
  untRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 5,
  },
  untChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.pill,
    backgroundColor: ink.ink2,
    paddingHorizontal: 9,
    paddingVertical: 3,
  },
  untDot: { width: 6, height: 6, borderRadius: radii.pill },
  untChipText: {
    ...type.bodySm,
    fontSize: 12,
    lineHeight: 16,
    color: chalk.base,
    fontFamily: fonts.uiSemi,
  },
  untMore: { ...type.data, color: chalk.dim, fontFamily: fonts.dataSemi },

  // Expanded editor.
  dnaGroupHdr: { ...type.label, marginTop: 2 },
  dnaMs: { color: ice.base },
  outGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  outCard: {
    flexBasis: '48%',
    flexGrow: 1,
    minHeight: 44,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    backgroundColor: ink.ink2,
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
  dnaHint: {
    ...type.bodySm,
    fontSize: 11,
    lineHeight: 15,
    color: chalk.dim,
  },
  dnaErrorText: { ...type.bodySm, color: semantic.neg },
  untLine: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  untCount: { ...type.data, color: chalk.base, fontFamily: fonts.dataSemi },
  untProtected: { ...type.bodySm, color: chalk.dim },

  // #218 — extra marginTop dropped (mock: 8 → 0); the stack gap separates it.
  sectionLabel: { ...type.label },

  // Mode launcher cards
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    backgroundColor: ink.ink1,
    // #218 — vertical pad 12 → 9 (no token; horizontal keeps md 12). Cards
    // stay ~61pt tall — comfortably over the 44pt tap-target floor.
    paddingVertical: 9,
    paddingHorizontal: space.md,
  },
  cardIcon: {
    // #218 — icon well 40 → 34 (icon glyph 22 → 20) per the mock.
    width: 34,
    height: 34,
    borderRadius: radii.md,
    backgroundColor: ink.ink2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardTitleRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  cardTitle: { ...type.title },
  recTag: { ...type.label, color: flare.base },
  cardBody: { ...type.bodySm, marginTop: 1 },
  // #156 finish item 3 — live pin-count line (mono, chalk) on the player card.
  cardBodyLive: { color: chalk.base, fontFamily: fonts.data },

  // Team picker sheet
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    // #242 — tall enough that a 12-team league's 11 manager rows fit
    // without scrolling on modern iPhones (shared with the untouchables
    // sheet, which also just sizes to content up to this bound).
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
  // #242 — size to content (the fixed 360pt cap forced a 12-team league to
  // scroll); the sheet's maxHeight is the only bound, and flexShrink lets
  // the list compress into it (and scroll) when content exceeds it.
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
});

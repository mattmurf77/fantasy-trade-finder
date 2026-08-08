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
import { getLeagueRosters } from '../api/sleeper';

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

interface Props {
  visible: boolean;
  /** Pure dismiss — every edit already autosaved on tap (#236). */
  onClose: () => void;
}

export default function TradeDnaSheet({ visible, onClose }: Props) {
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
  const untouchableNamesQuery = useQuery({
    queryKey: ['calc-values', '1qb_ppr'],
    queryFn: ({ signal }) => getTradeValues('1qb_ppr', signal),
    enabled: untouchablesOpen,
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
    const ids =
      (rostersQuery.data ?? []).find((r) => r.owner_id === userId)?.players ??
      [];
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

  // Reset per-open state when the sheet opens.
  useEffect(() => {
    if (visible) {
      dnaTouched.current = false;
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
      <View style={styles.sheet}>
        <View style={styles.grabber} />
        <View style={styles.sheetTop}>
          <Text style={type.heading} accessibilityRole="header">
            Your Trade DNA
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

          {dnaError ? <Text style={styles.dnaErrorText}>{dnaError}</Text> : null}

          {/* #173 — count + Manage line; Manage opens the untouchables
              management layer (inside this same Modal). */}
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
                    style={[styles.manageLink, pressed && { color: chalk.base }]}
                  >
                    Manage
                  </Text>
                )}
              </Pressable>
            </View>
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
          <View style={styles.sheet}>
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
          <View style={styles.sheet}>
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

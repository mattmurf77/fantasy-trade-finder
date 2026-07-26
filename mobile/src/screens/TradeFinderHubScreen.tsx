import React, { useMemo, useState } from 'react';
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
  space,
  radii,
  type,
  fonts,
  shadowSheet,
  scrim,
} from '../theme/chalkline';
import { posColor } from '../theme/colors';
import { Icon, Button } from '../components/chalkline';
import LeaguePill from '../components/LeaguePill';
import LeagueSwitcherSheet from '../components/LeagueSwitcherSheet';
import OutlookSheet from '../components/OutlookSheet';
import FeedbackFAB from '../components/FeedbackFAB';
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

const POS_ORDER = ['QB', 'RB', 'WR', 'TE'];

function cap(s?: string | null): string {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// One position chip: colored square encoding + label. `rec` renders the
// recommendation (dashed) treatment with a flare tag ("need" / "deep").
function PosChip({
  pos,
  rec,
  tag,
}: {
  pos: string;
  rec?: boolean;
  tag?: string;
}) {
  return (
    <View style={[styles.posChip, rec && styles.posChipRec]}>
      <View style={[styles.posDot, { backgroundColor: posColor(pos as any) }]} />
      <Text style={styles.posChipText}>{pos}</Text>
      {rec && tag ? <Text style={styles.posChipTag}>{tag}</Text> : null}
    </View>
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

export default function TradeFinderHubScreen({ navigation }: any) {
  const queryClient = useQueryClient();
  const league = useSession((s) => s.league);
  const user = useSession((s) => s.user);
  const leagueId = league?.league_id || null;
  const userId = user?.user_id || '';

  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [outlookOpen, setOutlookOpen] = useState(false);
  const [teamPickerOpen, setTeamPickerOpen] = useState(false);
  const [untouchablesOpen, setUntouchablesOpen] = useState(false);

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
  // sheet uses; format doesn't change names, so 1QB is fine here. Only
  // fetched while the sheet is open (shares the ['calc-values', …] cache).
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

  // Trade DNA: acquire/shed position chips, plus recommendation chips from
  // the roster-strength needs/surplus the backend now surfaces (FB #156).
  const acquire = prefs?.acquire_positions ?? [];
  const shed = prefs?.trade_away_positions ?? [];
  const recNeeds = useMemo(
    () => (prefs?.position_needs ?? []).filter((p) => !acquire.includes(p)),
    [prefs?.position_needs, acquire],
  );
  const recSurplus = useMemo(
    () => (prefs?.position_surplus ?? []).filter((p) => !shed.includes(p)),
    [prefs?.position_surplus, shed],
  );

  const outlookLabel = prefs?.team_outlook
    ? cap(prefs.team_outlook)
    : prefs?.inferred_outlook
      ? `${cap(prefs.inferred_outlook)} (inferred)`
      : 'Not set';

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
      <OutlookSheet
        visible={outlookOpen}
        initial={prefs?.team_outlook ?? prefs?.inferred_outlook ?? null}
        onClose={() => setOutlookOpen(false)}
        onSubmit={async (o, a, s) => {
          await saveOutlook.mutateAsync({ outlook: o, acquire: a, shed: s });
        }}
      />
      <LeagueSwitcherSheet
        visible={switcherOpen}
        onClose={() => setSwitcherOpen(false)}
      />

      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.header}>
          <Text style={styles.pageTitle} accessibilityRole="header">
            Find a Trade
          </Text>
        </View>
        <LeaguePill label="Trading in" onPress={() => setSwitcherOpen(true)} />

        {/* Trade DNA panel — your live targeting preferences at a glance. */}
        <View style={styles.dna}>
          <View style={styles.dnaTop}>
            <Text style={styles.dnaLabel}>Your Trade DNA</Text>
            <Pressable
              testID="finder-hub.dna.edit"
              accessibilityRole="button"
              accessibilityLabel="Edit trade preferences"
              onPress={() => setOutlookOpen(true)}
              hitSlop={8}
            >
              {({ pressed }) => (
                <Text style={[styles.dnaEdit, pressed && { color: chalk.base }]}>
                  Edit prefs
                </Text>
              )}
            </Pressable>
          </View>

          <View style={styles.dnaRow}>
            <Text style={styles.dnaKV}>
              <Text style={styles.dnaK}>Outlook </Text>
              {outlookLabel}
            </Text>
            {/* #173 — the untouchables count opens the management sheet
                (list + remove + how-to-add), so the feature is findable
                from the hub, not only via deck-card long-press. */}
            {untouchablesEnabled ? (
              <Pressable
                testID="finder-hub.dna.untouchables"
                accessibilityRole="button"
                accessibilityLabel={`Untouchables, ${untouchableCount}. Manage`}
                onPress={() => {
                  haptics.selection();
                  setUntouchablesOpen(true);
                }}
                hitSlop={8}
              >
                {({ pressed }) => (
                  <Text style={styles.dnaKV}>
                    <Text style={styles.dnaK}>Untouchables </Text>
                    {untouchableCount}
                    <Text
                      style={[
                        styles.dnaEdit,
                        pressed && { color: chalk.base },
                      ]}
                    >
                      {'  Manage'}
                    </Text>
                  </Text>
                )}
              </Pressable>
            ) : (
              <Text style={styles.dnaKV}>
                <Text style={styles.dnaK}>Untouchables </Text>
                {untouchableCount}
              </Text>
            )}
          </View>

          <Text style={styles.dnaGroupLabel}>Chasing</Text>
          <View style={styles.chipWrap}>
            {acquire.length === 0 && recNeeds.length === 0 ? (
              <Text style={styles.dnaEmpty}>Nothing set</Text>
            ) : null}
            {POS_ORDER.filter((p) => acquire.includes(p)).map((p) => (
              <PosChip key={`acq-${p}`} pos={p} />
            ))}
            {POS_ORDER.filter((p) => recNeeds.includes(p)).map((p) => (
              <PosChip key={`need-${p}`} pos={p} rec tag="need" />
            ))}
          </View>

          <Text style={styles.dnaGroupLabel}>Shopping</Text>
          <View style={styles.chipWrap}>
            {shed.length === 0 && recSurplus.length === 0 ? (
              <Text style={styles.dnaEmpty}>Nothing set</Text>
            ) : null}
            {POS_ORDER.filter((p) => shed.includes(p)).map((p) => (
              <PosChip key={`shed-${p}`} pos={p} />
            ))}
            {POS_ORDER.filter((p) => recSurplus.includes(p)).map((p) => (
              <PosChip key={`deep-${p}`} pos={p} rec tag="deep" />
            ))}
          </View>
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
                <Icon name={m.icon} size={22} color={ice.base} />
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

      {/* #188-adjacent — in-app feedback capture on the hub (every authed
          screen carries the FAB during TestFlight; this screen is new
          surface, so it mounts its own). */}
      <FeedbackFAB activeScreen="TradesHome" />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, gap: space.md },
  header: { flexDirection: 'row', alignItems: 'center' },
  pageTitle: { ...type.heading },

  // Trade DNA panel
  dna: {
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    backgroundColor: ink.ink1,
    padding: space.md,
    gap: space.sm,
  },
  dnaTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  dnaLabel: { ...type.label },
  dnaEdit: { ...type.bodySm, color: ice.base, fontFamily: fonts.uiSemi },
  dnaRow: { flexDirection: 'row', gap: space.xl, flexWrap: 'wrap' },
  dnaKV: { ...type.body },
  dnaK: { color: chalk.faint },
  dnaGroupLabel: { ...type.label, marginTop: space.xs },
  dnaEmpty: { ...type.bodySm, color: chalk.faint },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },

  posChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink2,
  },
  posChipRec: { borderStyle: 'dashed', borderColor: ink.lineStrong },
  posDot: { width: 8, height: 8, borderRadius: radii.xs },
  posChipText: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  posChipTag: { ...type.label, color: flare.base, fontSize: 9, marginLeft: 2 },

  sectionLabel: { ...type.label, marginTop: space.sm },

  // Mode launcher cards
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    backgroundColor: ink.ink1,
    padding: space.md,
  },
  cardIcon: {
    width: 40,
    height: 40,
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
    maxHeight: '80%',
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
  pickerScroll: { maxHeight: 360, marginTop: space.sm },
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

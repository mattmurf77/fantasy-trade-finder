import React, { useEffect, useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Modal,
  ScrollView,
  ActivityIndicator,
} from 'react-native';

import {
  ink,
  chalk,
  ice,
  semantic,
  space,
  radii,
  type,
  fonts,
  shadowSheet,
  scrim,
} from '../theme/chalkline';
import { Icon } from './chalkline';
import { haptics } from '../utils/haptics';
import { track } from '../api/events';
import { createStandingOffer, type StandingOffer } from '../api/trades';

// #362 — the post-like standing-offer sheet.
// Approved design: mockups/standing-offer-362/index.html §2 (honor its §6
// dated CORRECTION, not the struck-through value-gate row above it).
// Build contract: docs/feedback/items/362-standing-offer/prd.md §4.2.
//
// WHAT THIS IS. After a right-swipe on a 1-for-1 where the user RECEIVES a
// first, this asks which OTHER seasons and which OTHER teams they would take
// a first from. Confirming writes a standing offer — "I will send player P
// for any round-1 pick, in seasons Y, from teams T, in this league, for 30
// days" — which widens the match rule feeding the EXISTING likes-you
// injector.
//
// TWO FLAT MULTI-SELECTS, NEVER A MATRIX (R-7). Seasons and teams are
// independent: toggling a season may change a team row's ANNOTATION but
// never its checked state, and toggling a team never touches a season pill.
// A per-(team × season) picker would be the wrong shape and four times the
// taps.
//
// THE SHEET CAN NEVER COST THE USER THEIR LIKE (R-7). The like is banked and
// the deck advanced before this can mount; "Just this one trade" dismisses
// with today's exact behavior.
//
// CHALKLINE: ice for the CTA and the selected-state affordances (actions);
// NO flare anywhere in this sheet — the flare pill in this feature is the
// shipped "They're interested" treatment on the RECIPIENT's card, reused
// unchanged. No emoji as icons; radius ≤ 8px except the specced season
// pills.

/** R-6 — the two default-selection variants. Variant (b) is specced and NOT
 *  shipped; flipping the constant below is the entire change. */
export type StandingOfferDefaultSelection = 'source-only' | 'all';

/** R-6 — SHIPPED DEFAULT, operator-confirmed 2026-08-19.
 *
 *  Source-only: exactly one season pill (the season of the pick in the card
 *  just liked) and exactly one team row (that card's counterparty) arrive
 *  checked. An unedited tap-through therefore reproduces TODAY's behavior
 *  exactly — one team, the same reach a plain like already has — so an
 *  accidental confirm is a no-op rather than a league-wide broadcast. And
 *  the ask is half EXCLUSION ("a first from any of these rosters but not
 *  xyz"); pre-checking everything would make the requested thing into the
 *  work. The live count in the CTA is the nudge.
 *
 *  Flipping this to the other variant is the ONE edit needed for variant
 *  (b); nothing else in this file branches on it. */
export const STANDING_OFFER_DEFAULT_SELECTION: StandingOfferDefaultSelection =
  'source-only';

const ROUND_WORD: Record<number, string> = { 1: '1st', 2: '2nd', 3: '3rd', 4: '4th' };
function roundWord(round: number): string {
  return ROUND_WORD[round] ?? `round ${round}`;
}
/** "2027" → "'27". Derived from the value, never a literal (R-4). */
function shortSeason(season: number): string {
  return `'${String(season).slice(-2)}`;
}

export interface StandingOfferSheetProps {
  visible: boolean;
  leagueId: string;
  /** The card just liked — give[0] is the player, receive[0] the source pick. */
  playerId: string;
  playerName: string;
  sourcePickId: string;
  sourceSeason: number;
  sourceTeamUserId: string;
  /** v1 is always 1 (D-d); the column exists so widening is config, not schema. */
  round: number;
  /** Every season in which this league really holds round-`round` picks,
   *  derived by the caller from `all_picks`. NEVER a fixed N-year window:
   *  that is the #355 defect D-091 fixed at the writer, which offered 2029
   *  picks in leagues that had none and reached 12.8% of served cards. */
  availableSeasons: number[];
  /** Every OTHER league member (the caller is filtered out upstream). Sourced
   *  from the members endpoint, NOT from `all_picks` — a team that owns no
   *  first must still appear and be seen to own none. */
  members: Array<{ user_id: string; username: string }>;
  /** owner_user_id → the seasons in which they hold a round-`round` pick.
   *  Sourced from `all_picks`. Drives the trailing annotation only. */
  memberFirstsBySeason: Record<string, number[]>;
  sourceTradeId?: string;
  defaultSelection?: StandingOfferDefaultSelection;
  onPosted: (offer: StandingOffer) => void;
  onSkip: () => void;
}

export default function StandingOfferSheet({
  visible,
  leagueId,
  playerId,
  playerName,
  sourceSeason,
  sourceTeamUserId,
  round,
  availableSeasons,
  members,
  memberFirstsBySeason,
  sourceTradeId,
  defaultSelection = STANDING_OFFER_DEFAULT_SELECTION,
  onPosted,
  onSkip,
}: StandingOfferSheetProps) {
  const [seasons, setSeasons] = useState<number[]>([]);
  const [teams, setTeams] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const seasonPills = useMemo(
    () => [...new Set(availableSeasons)].sort((a, b) => a - b),
    [availableSeasons],
  );
  const teamRows = useMemo(
    () => members.filter((m) => m.user_id !== sourceTeamUserId),
    [members, sourceTeamUserId],
  );
  /** The source team leads the grid, captioned FROM THIS OFFER. */
  const sourceRow = useMemo(
    () => members.find((m) => m.user_id === sourceTeamUserId) ?? null,
    [members, sourceTeamUserId],
  );
  const orderedRows = useMemo(
    () => (sourceRow ? [sourceRow, ...teamRows] : teamRows),
    [sourceRow, teamRows],
  );

  // R-6 — the ONE branch on the variant constant. Everything else reads the
  // seeded state, so variant (b) is a one-word edit above.
  const startAll = defaultSelection === 'all';

  // Re-seed on every open: the props arrive from the card that was just
  // liked, and a stale seed would broadcast the previous card's team.
  useEffect(() => {
    if (!visible) return;
    setError(null);
    setSubmitting(false);
    setSeasons(startAll ? [...seasonPills] : seasonPills.filter((s) => s === sourceSeason));
    setTeams(
      startAll
        ? orderedRows.map((m) => m.user_id)
        : orderedRows.filter((m) => m.user_id === sourceTeamUserId).map((m) => m.user_id),
    );
    // Analytics — counts only, never id lists (R-19). `*_offered` are the
    // sizes of the sets SHOWN; the posted event carries the sizes SELECTED.
    track(
      'standing_offer_prompted',
      {
        round,
        seasons_offered: seasonPills.length,
        teams_offered: orderedRows.length,
      },
      'Trades',
    );
    // Seeding is keyed on the OPEN, not on every prop identity change —
    // re-running it mid-edit would silently discard the user's selection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  // R-7 — the two setters are independent. Neither reads the other's state;
  // a season toggle changes only `seasons`, a team toggle only `teams`.
  function toggleSeason(season: number) {
    haptics.selection();
    setSeasons((prev) =>
      prev.includes(season) ? prev.filter((s) => s !== season) : [...prev, season],
    );
  }
  function toggleTeam(userId: string) {
    haptics.selection();
    setTeams((prev) =>
      prev.includes(userId) ? prev.filter((t) => t !== userId) : [...prev, userId],
    );
  }
  const allSeasons = seasonPills.length > 0 && seasons.length === seasonPills.length;
  const allTeams = orderedRows.length > 0 && teams.length === orderedRows.length;

  /** Which of the CURRENTLY SELECTED seasons this member owns a pick in.
   *  Annotation only — it never changes a row's checked state (R-7). */
  function ownedInSelected(userId: string): number[] {
    const owned = memberFirstsBySeason[userId] ?? [];
    return seasons.filter((s) => owned.includes(s)).sort((a, b) => a - b);
  }

  const canConfirm = seasons.length > 0 && teams.length > 0 && !submitting;

  async function handleConfirm() {
    if (!canConfirm) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await createStandingOffer({
        league_id: leagueId,
        player_id: playerId,
        round,
        seasons: [...seasons].sort((a, b) => a - b),
        team_user_ids: teams,
        ...(sourceTradeId ? { source_trade_id: sourceTradeId } : {}),
      });
      track(
        'standing_offer_posted',
        {
          round,
          seasons: seasons.length,
          teams: teams.length,
          used_all_teams: allTeams,
        },
        'Trades',
      );
      haptics.success();
      onPosted(res.offer);
    } catch (e: any) {
      // The create route validates round → season horizon → membership and
      // reports only the FIRST failure, so the server's message is the only
      // honest thing to show; do not synthesize a cause.
      setError(e?.message || 'Could not post that standing offer');
      setSubmitting(false);
    }
  }

  const ctaLabel =
    teams.length === 1 ? 'Broadcast to 1 team' : `Broadcast to ${teams.length} teams`;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onSkip}>
      <Pressable
        style={styles.backdrop}
        onPress={onSkip}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={styles.sheet} testID="standing-offer-sheet">
        <View style={styles.grabber} />
        <Text style={type.heading} accessibilityRole="header">
          Open to more {roundWord(round)}s?
        </Text>
        <Text style={type.bodySm}>
          {`You'd send ${playerName} for a ${sourceSeason} ${roundWord(round)}. `}
          {`Tell us the rest of what you'd take and we'll put this in front of those teams.`}
        </Text>

        <ScrollView style={styles.scroll} showsVerticalScrollIndicator={false}>
          <View style={styles.groupHdr}>
            <Text style={type.label}>{`Years you'd accept`}</Text>
            <Pressable
              testID="standing-offer-all-seasons"
              accessibilityRole="button"
              accessibilityLabel={allSeasons ? 'Clear all years' : 'Select all years'}
              hitSlop={8}
              onPress={() => {
                haptics.selection();
                setSeasons(allSeasons ? [] : [...seasonPills]);
              }}
            >
              {({ pressed }) => (
                <Text style={[styles.allLink, pressed && styles.allLinkPressed]}>
                  {allSeasons ? 'None' : 'All'}
                </Text>
              )}
            </Pressable>
          </View>
          <View style={styles.pillRow}>
            {seasonPills.map((s) => {
              const selected = seasons.includes(s);
              return (
                <Pressable
                  key={s}
                  testID={`standing-offer-season-${s}`}
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: selected }}
                  accessibilityLabel={`Accept a ${s} ${roundWord(round)}`}
                  onPress={() => toggleSeason(s)}
                  style={({ pressed }) => [
                    styles.pill,
                    selected && styles.pillSel,
                    pressed && !selected && styles.pillPressed,
                  ]}
                >
                  <Text style={[styles.pillText, selected && styles.pillTextSel]}>
                    {String(s)}
                  </Text>
                  {s === sourceSeason ? (
                    <Text style={[styles.fromOffer, selected && styles.fromOfferSel]}>
                      FROM THIS OFFER
                    </Text>
                  ) : null}
                </Pressable>
              );
            })}
          </View>

          <Text style={[type.bodySm, styles.independence]}>
            Years and teams are independent — picking a year doesn't change who
            sees this, and picking a team doesn't change which years you'd take.
          </Text>

          <View style={styles.groupHdr}>
            <Text style={type.label}>{`Teams you'd take one from`}</Text>
            <Pressable
              testID="standing-offer-all-teams"
              accessibilityRole="button"
              accessibilityLabel={allTeams ? 'Clear all teams' : 'Select all teams'}
              hitSlop={8}
              onPress={() => {
                haptics.selection();
                setTeams(allTeams ? [] : orderedRows.map((m) => m.user_id));
              }}
            >
              {({ pressed }) => (
                <Text style={[styles.allLink, pressed && styles.allLinkPressed]}>
                  {allTeams ? 'None' : 'All'}
                </Text>
              )}
            </Pressable>
          </View>
          {orderedRows.map((m) => {
            const selected = teams.includes(m.user_id);
            const owned = ownedInSelected(m.user_id);
            return (
              <Pressable
                key={m.user_id}
                testID={`standing-offer-team-${m.user_id}`}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: selected }}
                accessibilityLabel={`Take a ${roundWord(round)} from @${m.username}`}
                onPress={() => toggleTeam(m.user_id)}
                style={({ pressed }) => [
                  styles.teamRow,
                  selected && styles.teamRowSel,
                  pressed && !selected && styles.teamRowPressed,
                ]}
              >
                <View style={[styles.checkbox, selected && styles.checkboxSel]}>
                  {selected ? <Icon name="check" size={12} color={ice.on} /> : null}
                </View>
                <View style={styles.teamNameCol}>
                  <Text style={styles.teamName} numberOfLines={1}>
                    @{m.username}
                  </Text>
                  {m.user_id === sourceTeamUserId ? (
                    <Text style={styles.fromOffer}>FROM THIS OFFER</Text>
                  ) : null}
                </View>
                <Text style={styles.teamOwned}>
                  {owned.length ? owned.map(shortSeason).join(' ') : '—'}
                </Text>
              </Pressable>
            );
          })}
          <Text style={[type.bodySm, styles.ownedNote]}>
            The trailing numbers are the {roundWord(round)}-round picks each team
            still owns in your selected years. A dash means they have none to
            give.
          </Text>
        </ScrollView>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Pressable
          testID="standing-offer-confirm"
          accessibilityRole="button"
          accessibilityLabel={ctaLabel}
          accessibilityState={{ disabled: !canConfirm, busy: submitting }}
          disabled={!canConfirm}
          onPress={handleConfirm}
          style={({ pressed }) => [
            styles.submit,
            pressed && styles.submitPressed,
            !canConfirm && styles.submitDisabled,
          ]}
        >
          {submitting ? (
            <ActivityIndicator color={ice.on} />
          ) : (
            <Text style={styles.submitText}>{ctaLabel}</Text>
          )}
        </Pressable>
        <Pressable
          testID="standing-offer-skip"
          accessibilityRole="button"
          accessibilityLabel="Just this one trade"
          disabled={submitting}
          onPress={onSkip}
          style={styles.skip}
        >
          {({ pressed }) => (
            <Text style={[styles.skipText, pressed && { color: chalk.base }]}>
              Just this one trade
            </Text>
          )}
        </Pressable>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: scrim,
  },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '90%',
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    padding: space.lg,
    gap: space.md,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.xs,
  },
  scroll: { maxHeight: 400 },
  groupHdr: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: space.md,
    marginBottom: space.sm,
  },
  allLink: {
    fontFamily: fonts.uiSemi,
    fontSize: 13,
    color: ice.base,
  },
  allLinkPressed: { color: ice.press },
  pillRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  // The one specced pill in this sheet (radii.pill is otherwise reserved).
  pill: {
    minHeight: 44,
    minWidth: 72,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  pillSel: { borderColor: ice.base, backgroundColor: ice.base },
  pillPressed: { backgroundColor: ink.ink3 },
  pillText: {
    fontFamily: fonts.dataSemi,
    fontSize: 14,
    color: chalk.dim,
  },
  pillTextSel: { color: ice.on },
  fromOffer: {
    fontFamily: fonts.dataSemi,
    fontSize: 9,
    letterSpacing: 0.5,
    color: chalk.faint,
  },
  fromOfferSel: { color: ice.on },
  independence: { marginTop: space.md },
  teamRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    paddingHorizontal: space.md,
    marginBottom: space.sm,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  teamRowSel: { borderColor: ice.base },
  teamRowPressed: { backgroundColor: ink.ink3 },
  checkbox: {
    width: 20,
    height: 20,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.lineStrong,
  },
  checkboxSel: { borderColor: ice.base, backgroundColor: ice.base },
  teamNameCol: { flex: 1 },
  teamName: {
    fontFamily: fonts.uiMedium,
    fontSize: 14,
    color: chalk.base,
  },
  teamOwned: {
    fontFamily: fonts.data,
    fontSize: 12,
    color: chalk.dim,
  },
  ownedNote: { marginTop: space.sm },
  error: { ...type.bodySm, color: semantic.neg },
  submit: {
    backgroundColor: ice.base,
    borderRadius: radii.sm,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: space.md,
  },
  submitPressed: { backgroundColor: ice.press },
  submitDisabled: { opacity: 0.45 },
  submitText: {
    fontFamily: fonts.uiSemi,
    fontSize: 14,
    color: ice.on,
  },
  skip: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  skipText: {
    fontFamily: fonts.uiMedium,
    fontSize: 14,
    color: chalk.dim,
  },
});

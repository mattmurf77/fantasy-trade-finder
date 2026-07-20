import React, { forwardRef } from 'react';
import {
  View,
  StyleSheet,
  Pressable,
  type AccessibilityActionEvent,
  type AccessibilityActionInfo,
  type AccessibilityState,
} from 'react-native';
import {
  ink,
  chalk,
  ice,
  flare,
  semantic,
  position as positionColors,
  space,
  radii,
  type,
  fonts,
} from '../theme/chalkline';
import { Badge, PositionBadge, TierChalkBadge, RookieBadge, InjuryBadge, Text } from './chalkline';
import { TIER_LABEL } from '../utils/tierBands'; // tier name in the composed a11y label
import { colors } from '../theme/colors'; // medal tokens (gold/silver) for rank accents
import { useFlag } from '../state/useFeatureFlags';
import type { Player, Tier } from '../shared/types';

export interface PlayerCardProps {
  player: Player;
  testID?: string;                 // UI-test harness id (registry: mobile/src/components/CLAUDE.md)
  // Ranking-state props — used by RankScreen's Trios loop
  rank?: 1 | 2 | 3 | null;         // which position the user has assigned
  selected?: boolean;              // any rank assigned at all
  onPress?: () => void;
  onLongPress?: () => void;        // used for "gesture audit" info sheet
  disabled?: boolean;
  // Decorative props — used by Tiers / Trades / Matches
  tier?: Tier | null;
  posRank?: string;                // e.g. "QB4"
  compact?: boolean;               // shorter card for tier bins / trade cards
  rightSlot?: React.ReactNode;     // optional right-side widget (drag handle, trend arrow, etc.)
  showInjury?: boolean;            // render the injury-status tag (default true). Off for Trios tiles (feedback #33).
  // #58 (cozy) — dense 60px two-line row, used ONLY by the Tiers board.
  // Renders a separate layout branch: line 1 = name + team + RK/injury
  // micro-tags, line 2 = TierChalkBadge + `statsSlot`, right cluster =
  // posRank (position-colored mono, #53) over `value` (#54). Drops the
  // PositionBadge and age/experience meta (redundant with the rail +
  // posRank at this density). All other callers render the classic card.
  dense?: boolean;
  statsSlot?: React.ReactNode;     // dense line 2 — the TileStats strip
  value?: number | null;           // dense right cluster — 0–10k seed-scale value
  // Teardown S8 PRD-01/-02 (inert a11y): the card is a composite tile —
  // VoiceOver reads it as ONE utterance (Pressable groups children by
  // default). When no override is passed, a label is composed from the
  // player facts so the utterance is ordered/complete instead of a raw
  // child-text concatenation. Custom actions let callers attach board
  // commands ("Move to tier…", "Set rank…") to the row's single focusable.
  accessibilityLabel?: string;
  accessibilityHint?: string;
  accessibilityState?: AccessibilityState;
  accessibilityActions?: readonly AccessibilityActionInfo[];
  onAccessibilityAction?: (event: AccessibilityActionEvent) => void;
}

// Normalize Sleeper injury strings to the Chalkline InjuryBadge codes.
// Unknown statuses fall back to a generic neg-bordered badge below.
function injuryCode(status: string): 'Q' | 'D' | 'Out' | 'IR' | null {
  const s = status.trim().toLowerCase();
  if (s === 'q' || s.startsWith('questionable')) return 'Q';
  if (s === 'd' || s.startsWith('doubtful')) return 'D';
  if (s === 'out') return 'Out';
  if (s === 'ir') return 'IR';
  return null;
}

// Shared player-card primitive. Consumed by RankScreen (Trios) today and
// by TiersScreen + TradesScreen + MatchesScreen in Phases 3-4. Keeping
// visual variants here so every screen renders players identically.
// Chalkline: replicates the Card primitive pattern (ink-1 surface, hairline,
// 3px position rail) because the trio loop needs Pressable + ref + rank
// accents that Card doesn't model.
const PlayerCard = forwardRef<View, PlayerCardProps>(function PlayerCard(
  {
    player,
    testID,
    rank = null,
    selected = false,
    onPress,
    onLongPress,
    disabled,
    tier,
    posRank,
    compact = false,
    rightSlot,
    showInjury = true,
    dense = false,
    statsSlot,
    value,
    accessibilityLabel,
    accessibilityHint,
    accessibilityState,
    accessibilityActions,
    onAccessibilityAction,
  },
  ref,
) {
  const ranked = rank != null;
  // Teardown S2 PRD-04: dense micro-tags rise from 9px to the 11px floor.
  const cleanup = useFlag('visual.chalkline_cleanup');
  // Teardown S3 PRD-02 (`ux.player_context_menu`): command long-press
  // standardizes on the system 500ms (drops the 400ms override). This card
  // never hosts drag-lift — reorder surfaces (Tiers/ManualRanks) own their
  // own delayLongPress on DraggableFlatList rows.
  const commandLongPressMs = useFlag('ux.player_context_menu') ? 500 : 400;
  const ageStr = player.age != null ? `${player.age} yo` : null;
  const teamStr = player.team || 'FA';
  const expStr =
    player.years_experience != null
      ? `${player.years_experience} yr${player.years_experience === 1 ? '' : 's'}`
      : null;
  const isRookie = player.years_experience === 0;

  // Position rail + badge — position hexes are cross-client invariants,
  // rendered only via the chalkline re-export.
  const posKey = String(player.position).toLowerCase() as keyof typeof positionColors;
  const railColor: string | undefined = positionColors[posKey];
  const isStdPos =
    player.position === 'QB' ||
    player.position === 'RB' ||
    player.position === 'WR' ||
    player.position === 'TE';

  const injury = showInjury && player.injury_status ? player.injury_status : null;
  const injCode = injury ? injuryCode(injury) : null;

  // Per-rank border accents echoing the web's .ranked-1 / .ranked-2 / .ranked-3.
  const rankBorderStyle =
    rank === 1 ? styles.rankBorder1 :
    rank === 2 ? styles.rankBorder2 :
    rank === 3 ? styles.rankBorder3 : null;
  const rankFgStyle =
    rank === 1 ? styles.rankFg1 :
    rank === 2 ? styles.rankFg2 :
    rank === 3 ? styles.rankFg3 : null;

  // ── Composed a11y label (S8 PRD-01/-02, inert) ──────────────────────
  // One ordered utterance per tile: name, position, team, then the data
  // facts a sighted user reads off the badges/right cluster. Callers can
  // override wholesale via `accessibilityLabel`.
  const composedLabel =
    accessibilityLabel ??
    [
      player.name,
      String(player.position),
      teamStr,
      rank != null ? `ranked ${rank} of 3` : null,
      tier ? `tier ${TIER_LABEL[tier]}` : null,
      posRank ?? null,
      value != null ? `value ${value.toLocaleString('en-US')}` : null,
      isRookie ? 'rookie' : null,
      injury ? `injury ${injCode ?? injury}` : null,
    ]
      .filter(Boolean)
      .join(', ');
  // Pressable is the tile's single focusable; give it the button trait
  // only when it actually does something on activation.
  const a11yProps = {
    accessible: true,
    accessibilityRole:
      onPress || onLongPress ? ('button' as const) : undefined,
    accessibilityLabel: composedLabel,
    accessibilityHint,
    accessibilityState: {
      selected: selected || rank != null,
      disabled: !!disabled,
      ...accessibilityState,
    },
    accessibilityActions: accessibilityActions as AccessibilityActionInfo[] | undefined,
    onAccessibilityAction,
  };

  // ── Dense (cozy) branch — Tiers board only (#58) ────────────────────
  if (dense) {
    return (
      <Pressable
        ref={ref as any}
        testID={testID}
        onPress={onPress}
        onLongPress={onLongPress}
        disabled={disabled}
        delayLongPress={commandLongPressMs}
        {...a11yProps}
        style={({ pressed }) => [
          styles.card,
          styles.cardDense,
          selected && styles.cardSelected,
          pressed && !disabled && styles.cardPressed,
          disabled && styles.cardDisabled,
        ]}
      >
        {railColor ? <View style={[styles.rail, { backgroundColor: railColor }]} /> : null}
        <View style={styles.denseMain}>
          <View style={styles.denseLine1}>
            <Text scale="dense" style={styles.denseName} numberOfLines={1}>
              {player.name}
            </Text>
            <Text scale="dense" style={styles.denseTeam}>{teamStr}</Text>
            {isRookie && (
              <Text
                scale="dense"
                style={[
                  styles.denseTag,
                  cleanup && styles.denseTagFloor,
                  { color: flare.base, borderColor: flare.base },
                ]}
              >
                RK
              </Text>
            )}
            {injury ? (
              <Text
                scale="dense"
                style={[
                  styles.denseTag,
                  cleanup && styles.denseTagFloor,
                  injCode === 'Q' || injCode === 'D'
                    ? { color: semantic.warn, borderColor: semantic.warn }
                    : { color: semantic.neg, borderColor: semantic.neg },
                ]}
              >
                {injCode ?? injury}
              </Text>
            ) : null}
          </View>
          <View style={styles.denseLine2}>
            {tier && <TierChalkBadge t={tier} />}
            {statsSlot}
          </View>
        </View>
        {/* #53/#54 — positional rank prominent, 0–10k value secondary */}
        {posRank || value != null ? (
          <View style={styles.denseNums}>
            {posRank ? (
              <Text scale="dense" style={[styles.densePosRank, railColor ? { color: railColor } : null]}>
                {posRank}
              </Text>
            ) : null}
            {value != null ? (
              <Text scale="dense" style={styles.denseValue}>{value.toLocaleString('en-US')}</Text>
            ) : null}
          </View>
        ) : null}
        {rightSlot ? <View style={styles.denseRightSlot}>{rightSlot}</View> : null}
      </Pressable>
    );
  }

  return (
    <Pressable
      ref={ref as any}
      testID={testID}
      onPress={onPress}
      onLongPress={onLongPress}
      disabled={disabled}
      delayLongPress={commandLongPressMs}
      {...a11yProps}
      style={({ pressed }) => [
        styles.card,
        compact && styles.cardCompact,
        selected && styles.cardSelected,
        rankBorderStyle,
        pressed && !disabled && styles.cardPressed,
        disabled && styles.cardDisabled,
      ]}
    >
      {/* 3px position-color left rail (Card primitive pattern) */}
      {railColor ? <View style={[styles.rail, { backgroundColor: railColor }]} /> : null}

      {/* Rank badge floating in top-right */}
      {ranked && (
        <View style={[styles.rankBadge, rankFgStyle]}>
          <Text scale="dense" style={styles.rankBadgeText}>{rank}</Text>
        </View>
      )}

      <View style={styles.header}>
        {isStdPos ? (
          <PositionBadge pos={player.position as 'QB' | 'RB' | 'WR' | 'TE'} />
        ) : (
          <Badge label={String(player.position)} />
        )}
        {tier && <TierChalkBadge t={tier} />}
        {posRank ? <Badge label={posRank} /> : null}
        {isRookie && <RookieBadge />}
        {injury ? (
          injCode ? (
            <InjuryBadge status={injCode} />
          ) : (
            <Badge label={injury} color={semantic.neg} colorText />
          )
        ) : null}
      </View>

      <Text scale="body" style={[type.title, styles.name]} numberOfLines={1}>
        {player.name}
      </Text>

      <View style={styles.meta}>
        <Text scale="body" style={type.bodySm}>{teamStr}</Text>
        {ageStr && (
          <>
            <Text scale="body" style={styles.metaDot}>·</Text>
            <Text scale="body" style={type.bodySm}>{ageStr}</Text>
          </>
        )}
        {expStr && !compact && (
          <>
            <Text scale="body" style={styles.metaDot}>·</Text>
            <Text scale="body" style={type.bodySm}>{expStr}</Text>
          </>
        )}
      </View>

      {rightSlot ? <View style={styles.rightSlot}>{rightSlot}</View> : null}
    </Pressable>
  );
});

export default React.memo(PlayerCard);

const styles = StyleSheet.create({
  card: {
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: space.lg,
    position: 'relative',
    overflow: 'hidden',
  },
  cardCompact: {
    padding: space.md,
  },
  cardPressed: {
    backgroundColor: ink.ink3,
  },
  cardDisabled: { opacity: 0.45 },
  cardSelected: {
    borderColor: ice.base,
  },
  rail: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    width: 3,
  },
  // Rank accent border by assigned rank — MEDAL tokens (gold/silver/neutral),
  // matching web .ranked-1/2/3. Not tier tokens: rank is not a tier, and tier
  // hexes are data encodings (cross-client invariants) reserved for tiers.
  rankBorder1: { borderColor: colors.gold },
  rankBorder2: { borderColor: colors.silver },
  rankBorder3: { borderColor: ink.lineStrong },

  rankBadge: {
    position: 'absolute',
    top: space.sm,
    right: space.sm,
    width: 24,
    height: 24,
    borderRadius: radii.xs,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // Medal fills to match the borders above; rank 3 is a neutral bright-gray
  // (chalk.faint) so the dark badge text stays readable on all three.
  rankFg1: { backgroundColor: colors.gold },
  rankFg2: { backgroundColor: colors.silver },
  rankFg3: { backgroundColor: chalk.faint },
  rankBadgeText: {
    ...type.data,
    color: ink.ink0,
  },

  header: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: space.xs,
    marginBottom: space.sm,
  },
  name: {
    marginBottom: space.xs,
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  metaDot: { color: chalk.faint, marginHorizontal: space.xs },
  rightSlot: { position: 'absolute', right: space.md, top: space.md },

  // ── Dense (cozy) variant — #58, Tiers board only ─────────────────────
  // 60px fixed-height two-line row (mockups/tier-density/cozy.html). The
  // classic card's ink-1 surface / hairline / 3px rail carry over; padding
  // is replaced by vertical centering inside the fixed height.
  cardDense: {
    height: 60,
    padding: 0,
    flexDirection: 'row',
    alignItems: 'center',
  },
  denseMain: {
    flex: 1,
    justifyContent: 'center',
    paddingLeft: 13, // 3px rail + 10px inset (mockup .main)
    paddingRight: space.sm,
  },
  denseLine1: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 6,
  },
  denseName: {
    fontFamily: fonts.uiSemi,
    fontSize: 15,
    color: chalk.base,
    flexShrink: 1, // long names ellipsize before the team/tags/nums do
  },
  denseTeam: {
    fontFamily: fonts.ui,
    fontSize: 11,
    color: chalk.dim,
  },
  // Micro-tag (mockup .tag): Badge construction (border in encode color +
  // colored text) shrunk to fit line 1 of a 60px row.
  denseTag: {
    fontFamily: fonts.uiSemi,
    fontSize: 9, // legacy — flag off only; see denseTagFloor
    letterSpacing: 0.5,
    paddingHorizontal: 3,
    paddingVertical: 1,
    borderWidth: 1,
    borderRadius: radii.xs,
    overflow: 'hidden',
  },
  // S2 PRD-04 (`visual.chalkline_cleanup`): micro-tags — including injury
  // status, a decision input — meet the 11px type floor. Padding stays; the
  // ~2px taller tag still fits the 60px pitch (line 1 is baseline-aligned).
  denseTagFloor: {
    fontSize: 11,
  },
  denseLine2: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    marginTop: 3,
  },
  // Right cluster (#53/#54): positional rank prominent (mono, position
  // color) stacked over the 0–10k value (mono, chalk-dim).
  denseNums: {
    alignItems: 'flex-end',
    marginRight: space.sm,
  },
  densePosRank: {
    fontFamily: fonts.dataSemi,
    fontSize: 14,
    fontVariant: ['tabular-nums'],
    color: chalk.base,
  },
  denseValue: {
    fontFamily: fonts.data,
    fontSize: 11,
    fontVariant: ['tabular-nums'],
    color: chalk.dim,
    marginTop: 1,
  },
  denseRightSlot: {
    marginRight: space.sm,
  },
});

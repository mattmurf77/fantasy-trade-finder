import React from 'react';
import { StyleSheet, View, ViewStyle } from 'react-native';
import Svg, { Circle } from 'react-native-svg';

import { ink, chalk, ice, space, type, fonts } from '../theme/chalkline';
import { Button, Card, Text } from './chalkline';

// League progress module (#229/#230/#234 — approved mock
// mockups/polish-lab-2026-08/empty-states-progress-v3.html). ONE card owns
// every unlock on the low-activity League home: an SVG ring for "positions
// you've ranked" (the foundation, #230), a per-team segmented bar counting
// ranked members (you included, honestly labeled "(you)"), one plain
// unlock sentence (#234), and the fold line the collapsed zero-sections
// point at. The Matches empty state mounts the `compact` variant (bar +
// unlock line only) so the two surfaces can never tell different stories.
//
// Thresholds (documented in docs/feedback/items/229-empty-states-progress/):
// - Mutual matches "unlock" at MATCH_UNLOCK_MATES ranked leaguemates
//   (mock-anchored: "2 more ranked leaguemates unlocks mutual matches").
// - Leaderboards + contrarian ranks return at 3 ranked members total —
//   the backend /api/league/contrarian threshold; the fold-line copy is
//   static because the host folds those sections on the server's own
//   `insufficient_data` flag, not on a client-side recount.
const MATCH_UNLOCK_MATES = 2;

interface Props {
  /** Positions the caller has fully ranked (0–4); null while unknown. */
  positionsRanked: number | null;
  /** Leaguemates (excluding the caller) with stored rankings — coverage.ranked. */
  rankedMates: number;
  /** Total teams in the league, caller included. */
  totalTeams: number;
  /** Matches empty-state variant: segmented bar + unlock line only. */
  compact?: boolean;
  /** Show the "Leaderboards and contrarian ranks appear…" fold line. */
  showFoldLine?: boolean;
  /** Full variant's in-section CTA (solid ice per operator tweak). */
  onRankPlayers?: () => void;
  /** "Invite leaguemates" ghost action (OS share sheet). */
  onInvite?: () => void;
  testID?: string;
  style?: ViewStyle;
}

// 0–4 positions-ranked ring. 72×72, 5px stroke, square caps; at 0 a small
// start nub keeps the ring readable as progress (per mock). The mock's
// in-ring 8px "positions" caption violates the 11px type floor, so the
// caption lives OUTSIDE the ring as a standard label (documented deviation).
function PositionsRing({ value }: { value: number | null }) {
  const R = 31;
  const C = 2 * Math.PI * R;
  const frac = value == null ? 0 : Math.max(0, Math.min(1, value / 4));
  const dash = value == null ? 0 : Math.max(frac * C, 2.5);
  return (
    <View
      style={styles.ringWrap}
      accessible
      accessibilityLabel={
        value == null
          ? 'Positions ranked unavailable'
          : `${value} of 4 positions ranked`
      }
    >
      <Svg width={72} height={72} viewBox="0 0 72 72">
        <Circle cx={36} cy={36} r={R} stroke={ink.ink3} strokeWidth={5} fill="none" />
        {dash > 0 ? (
          <Circle
            cx={36}
            cy={36}
            r={R}
            stroke={ice.base}
            strokeWidth={5}
            fill="none"
            strokeDasharray={`${dash} ${C}`}
            strokeLinecap="square"
            transform="rotate(-90 36 36)"
          />
        ) : null}
      </Svg>
      <View style={styles.ringCenter}>
        <Text scale="dense" style={styles.ringValue}>
          {value == null ? '—' : value}/4
        </Text>
      </View>
    </View>
  );
}

// One 8px-tall slot per team; ranked slots (you + ranked leaguemates) fill ice.
function SegBar({ filled, total }: { filled: number; total: number }) {
  return (
    <View style={styles.segBar}>
      {Array.from({ length: total }, (_, i) => (
        <View key={i} style={[styles.seg, i < filled && styles.segFilled]} />
      ))}
    </View>
  );
}

export default function LeagueProgressModule({
  positionsRanked,
  rankedMates,
  totalTeams,
  compact = false,
  showFoldLine = false,
  onRankPlayers,
  onInvite,
  testID,
  style,
}: Props) {
  if (totalTeams <= 1) return null; // solo/unknown league — nothing to count

  // You occupy one slot (labeled "(you)"); ranked leaguemates fill the rest.
  const rankedShown = Math.min(rankedMates + 1, totalTeams);
  const remaining = Math.max(0, MATCH_UNLOCK_MATES - rankedMates);

  // #243 (league-home fold V1, approved mock league-home-fold.html): the
  // full variant's invite affordance is an inline text link appended to the
  // unlock sentence (same OS-share handler as the old ghost button — saves
  // the button row's ~36pt everywhere the full variant mounts). The compact
  // variant never rendered the invite and keeps its short sentence.
  const inviteLink =
    !compact && onInvite ? (
      <Text
        testID="league.progress-invite"
        scale="dense"
        style={styles.inviteLink}
        onPress={onInvite}
        accessibilityRole="link"
        accessibilityLabel="Invite leaguemates"
        suppressHighlighting
      >
        Invite them
      </Text>
    ) : null;

  const barBlock = (
    <>
      <View style={styles.statBetween}>
        <Text scale="dense" style={type.label}>
          Leaguemates ranked
        </Text>
        <Text scale="dense" style={type.data}>
          {rankedShown}/{totalTeams} <Text scale="dense" style={styles.youNote}>(you)</Text>
        </Text>
      </View>
      <SegBar filled={rankedShown} total={totalTeams} />
      {remaining > 0 ? (
        <Text style={styles.unlockLine}>
          <Text style={styles.unlockEm}>
            {remaining} more ranked leaguemate{remaining === 1 ? '' : 's'}
          </Text>{' '}
          unlocks mutual matches.{inviteLink ? <> {inviteLink}</> : null}
        </Text>
      ) : null}
    </>
  );

  if (compact) {
    return (
      <View testID={testID} style={style}>
        <Card>
          <View style={styles.inner}>{barBlock}</View>
        </Card>
      </View>
    );
  }

  return (
    <View testID={testID} style={style}>
      <Card>
        <View style={styles.inner}>
          <View style={styles.ringRow}>
            <PositionsRing value={positionsRanked} />
            <View style={styles.ringSide}>
              <Text scale="dense" style={type.label}>
                Positions ranked
              </Text>
              {onRankPlayers ? (
                // Operator tweak on the approved v3 mock: the in-section
                // buttons are BOTH solid ice — this one included.
                <Button
                  label="Rank players"
                  variant="primary"
                  compact
                  onPress={onRankPlayers}
                />
              ) : null}
            </View>
          </View>

          <View style={styles.divider} />
          {barBlock}

          {/* Matches already unlocked (no sentence to host the link) but
              other unlocks outstanding — keep the invite affordance as a
              standalone text link rather than losing it. */}
          {remaining === 0 && onInvite ? (
            <Text
              testID="league.progress-invite"
              scale="dense"
              style={styles.inviteLink}
              onPress={onInvite}
              accessibilityRole="link"
              accessibilityLabel="Invite leaguemates"
              suppressHighlighting
            >
              Invite leaguemates
            </Text>
          ) : null}

          {showFoldLine ? (
            <Text style={styles.foldLine}>
              Leaderboards and contrarian ranks appear here once 3 leaguemates
              have ranked.
            </Text>
          ) : null}
        </View>
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  inner: { gap: space.sm },

  ringRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.lg,
  },
  ringWrap: { width: 72, height: 72 },
  ringCenter: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ringValue: {
    ...type.data,
    fontSize: 16,
    fontFamily: fonts.dataSemi,
  },
  ringSide: { flex: 1, gap: space.sm, alignItems: 'flex-start' },

  divider: { height: 1, backgroundColor: ink.line },

  statBetween: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  youNote: { ...type.data, color: chalk.dim },

  segBar: { flexDirection: 'row', gap: 2 },
  seg: { flex: 1, height: 8, backgroundColor: ink.ink3 },
  segFilled: { backgroundColor: ice.base },

  unlockLine: { ...type.bodySm, color: chalk.base },
  unlockEm: { ...type.bodySm, color: ice.base, fontFamily: fonts.uiSemi },

  // #243 — inline invite text link (replaces the old ghost Button row).
  // Ice + semibold + underline: the same text-link construction as the
  // #213 calculator hand-off row. Nested-Text link ⇒ no 44pt target;
  // documented deviation, matches the approved V1 mock.
  inviteLink: {
    ...type.bodySm,
    color: ice.base,
    fontFamily: fonts.uiSemi,
    textDecorationLine: 'underline',
  },

  foldLine: {
    ...type.bodySm,
    color: chalk.dim,
    borderTopWidth: 1,
    borderTopColor: ink.line,
    paddingTop: space.sm + 2,
    marginTop: space.xs,
  },
});

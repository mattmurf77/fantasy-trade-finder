import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import PlayerCard from './PlayerCard';
import StrengthBar from './StrengthBar';
import { useFlag } from '../state/useFeatureFlags';
import type { TradeCard as TradeCardData } from '../shared/types';

interface Props {
  data: TradeCardData;
  variant?: 'swipe' | 'match';
  // Match-variant actions
  onAccept?: () => void;
  onDecline?: () => void;
  acting?: boolean;
}

// Shared rendering for generated trades (TradesScreen swipe deck) and
// mutual matches (MatchesScreen list). The only difference between the
// two variants is the action buttons at the bottom — swipe decks don't
// show buttons (gestures drive the decision), match cards do.
function TradeCardComp({
  data,
  variant = 'swipe',
  onAccept,
  onDecline,
  acting,
}: Props) {
  const matchPct = Math.round(data.match_score || 0);
  // `fairness` is always serialized by the v2 backend (fairness_score),
  // so the meter renders on every fresh card. Keep the guard so legacy /
  // adapter-shaped cards without it hide the row instead of showing a
  // bogus 0%.
  const hasFairness = typeof data.fairness === 'number';
  const fairPct = hasFairness ? Math.round((data.fairness as number) * 100) : 0;
  // v2: consensus cards are fair-value ideas vs an opponent who hasn't
  // ranked yet (no real disagreement signal behind them).
  const isConsensus = data.basis === 'consensus';
  // v2: the counterparty already liked the mirror of this trade.
  const likesYou = data.likesYou === true;
  // v2 sweetener — resolve the flagged player from whichever side it's
  // on. Resolution failure (id not in the arrays) just hides the line.
  const sweetenerSide = data.sweetener?.side;
  const sweetenerPlayer = data.sweetener
    ? (sweetenerSide === 'give' ? data.give_players : data.receive_players)
        ?.find((p) => p.id === data.sweetener!.playerId)
    : undefined;
  // Defensive: backend or normalizer should always populate these, but
  // never let a missing array crash the card. Empty arrays just render
  // an empty side, which is recoverable visually.
  const receivePlayers = Array.isArray(data.receive_players) ? data.receive_players : [];
  const givePlayers    = Array.isArray(data.give_players)    ? data.give_players    : [];
  // Reasons render only when the flag is on AND backend supplied them.
  // Mirrors the web gate at app.js:3205. Even though the backend already
  // omits `reasons` when the flag is off, double-gating client-side keeps
  // the rendering predictable if flags drift (e.g. cached job snapshot).
  const reasonsEnabled = useFlag('trade_math.human_explanations');
  const showReasons = reasonsEnabled
    && Array.isArray(data.reasons)
    && data.reasons.length > 0;
  // Real vs estimated opponent badge — only rendered when the backend
  // explicitly returned the field. Undefined = legacy/static path, hide
  // the chip entirely rather than guessing.
  const hasOpponentConfidence = typeof data.real_opponent === 'boolean';

  return (
    <View style={styles.card}>
      {/* Likes-you pill — counterparty already liked the mirror of this
          trade, so lead with it. Server pins these cards to the top of
          the snapshot; this badge explains why. */}
      {likesYou && (
        <View style={styles.likesYouPill}>
          <Text style={styles.likesYouText}>👀 They're interested</Text>
        </View>
      )}

      <View style={styles.header}>
        <View>
          <Text style={styles.headerLabel}>Trade with</Text>
          <View style={styles.nameRow}>
            <Text style={styles.headerName}>@{data.opponent_username}</Text>
            {hasOpponentConfidence && (
              data.real_opponent ? (
                <View style={styles.opBadge}>
                  <Text style={styles.opBadgeDotReal}>●</Text>
                  <Text style={styles.opBadgeTextReal}>real</Text>
                </View>
              ) : (
                <View style={styles.opBadge}>
                  <Text style={styles.opBadgeDotEst}>○</Text>
                  <Text style={styles.opBadgeTextEst}>est.</Text>
                </View>
              )
            )}
          </View>
        </View>
      </View>

      {/* Consensus basis — subtle label so users know this card isn't
          built on real ranking disagreement. No tooltip pattern in the
          app, so the hint renders inline as a muted sub-line. */}
      {isConsensus && (
        <View style={styles.consensusNote}>
          <Text style={styles.consensusLabel}>Fair-value idea</Text>
          <Text style={styles.consensusHint}>
            This league-mate hasn't ranked players yet — this is a balanced trade by consensus value.
          </Text>
        </View>
      )}

      {/* Match strength — gradient bar replacing the prior accent pill. */}
      <StrengthBar value={matchPct} label="Match strength" />

      <View style={styles.split}>
        <View style={styles.side}>
          <Text style={styles.sideLabel}>YOU GET</Text>
          <View style={styles.sideStack}>
            {receivePlayers.map((p) => (
              <PlayerCard key={p.id} player={p} compact />
            ))}
          </View>
          {sweetenerSide === 'receive' && sweetenerPlayer && (
            <Text style={styles.sweetenerLine}>
              + {sweetenerPlayer.name} added to balance the deal
            </Text>
          )}
        </View>
        <Text style={styles.swap}>↔</Text>
        <View style={styles.side}>
          <Text style={styles.sideLabel}>YOU GIVE</Text>
          <View style={styles.sideStack}>
            {givePlayers.map((p) => (
              <PlayerCard key={p.id} player={p} compact />
            ))}
          </View>
          {sweetenerSide === 'give' && sweetenerPlayer && (
            <Text style={styles.sweetenerLine}>
              + {sweetenerPlayer.name} added to balance the deal
            </Text>
          )}
        </View>
      </View>

      {hasFairness && (
        <View style={styles.fairnessRow}>
          <Text style={styles.fairnessLabel}>Fairness</Text>
          <View style={styles.fairnessTrack}>
            <View style={[styles.fairnessFill, { width: `${fairPct}%` }]} />
          </View>
          <Text style={styles.fairnessValue}>{fairPct}%</Text>
        </View>
      )}

      {/* Human-readable reasons (flag trade_math.human_explanations is ON).
          Rendered only when the flag is on AND the backend returns a
          non-empty list. */}
      {showReasons && (
        <View style={styles.reasons}>
          {data.reasons!.map((r, i) => (
            <Text key={`${i}:${r}`} style={styles.reasonLine}>• {r}</Text>
          ))}
        </View>
      )}

      {variant === 'match' && (
        <View style={styles.actions}>
          <Pressable
            disabled={acting}
            onPress={onDecline}
            style={({ pressed }) => [
              styles.btn,
              styles.decline,
              pressed && { opacity: 0.7 },
              acting && { opacity: 0.5 },
            ]}
          >
            <Text style={styles.declineText}>Decline</Text>
          </Pressable>
          <Pressable
            disabled={acting}
            onPress={onAccept}
            style={({ pressed }) => [
              styles.btn,
              styles.accept,
              pressed && { opacity: 0.85 },
              acting && { opacity: 0.5 },
            ]}
          >
            <Text style={styles.acceptText}>Accept →</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

export default React.memo(TradeCardComp);

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.xl,
    padding: spacing.lg,
    gap: spacing.md,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  headerName: { color: colors.text, fontSize: fontSize.base, fontWeight: '800' },
  // Likes-you pill: prominent accent-tinted banner pinned to the top of
  // the card. Same translucent-accent treatment as the web's .score-pill.
  likesYouPill: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(79,124,255,0.15)',
    borderWidth: 1,
    borderColor: colors.accent,
    borderRadius: radius.pill,
    paddingVertical: 4,
    paddingHorizontal: spacing.md,
  },
  likesYouText: {
    color: colors.accent,
    fontSize: fontSize.xs,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  // Consensus-basis note: deliberately muted — it's a caveat, not a sell.
  consensusNote: { gap: 2 },
  consensusLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  consensusHint: {
    color: colors.muted,
    fontSize: fontSize.xs,
    lineHeight: 16,
  },
  // Sweetener callout under the side that contains the balancing player.
  sweetenerLine: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontStyle: 'italic',
    lineHeight: 16,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  // Opponent-confidence chip: small dot + 4-letter label next to @handle.
  // Green/filled = real (their actual saved rankings); muted/outlined =
  // estimated (noise-randomized off consensus seed). Mirrors web's
  // app.js:3198-3200 styling.
  opBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  opBadgeDotReal: {
    color: colors.green,
    fontSize: 10,
    lineHeight: 12,
  },
  opBadgeTextReal: {
    color: colors.green,
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.3,
  },
  opBadgeDotEst: {
    color: colors.muted,
    fontSize: 10,
    lineHeight: 12,
  },
  opBadgeTextEst: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.3,
  },
  split: {
    flexDirection: 'row',
    gap: spacing.md,
    alignItems: 'stretch',
  },
  side: { flex: 1, gap: spacing.xs },
  sideLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  sideStack: { gap: spacing.xs },
  swap: {
    color: colors.accent,
    fontSize: 24,
    alignSelf: 'center',
    paddingHorizontal: 4,
  },
  fairnessRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  fairnessLabel: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
    width: 62,
  },
  fairnessTrack: {
    flex: 1,
    height: 6,
    backgroundColor: colors.border,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  fairnessFill: {
    height: '100%',
    backgroundColor: colors.green,
  },
  fairnessValue: {
    color: colors.text,
    fontSize: fontSize.xs,
    fontWeight: '700',
    width: 40,
    textAlign: 'right',
  },
  reasons: {
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderLeftWidth: 3,
    borderLeftColor: colors.accent,
    padding: spacing.sm,
    paddingLeft: spacing.md,
    borderRadius: radius.sm,
    gap: 2,
  },
  reasonLine: { color: colors.muted, fontSize: fontSize.xs, lineHeight: 18 },
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  btn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: radius.md,
    alignItems: 'center',
  },
  decline: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  accept: { backgroundColor: colors.green },
  declineText: { color: colors.muted, fontSize: fontSize.sm, fontWeight: '700' },
  acceptText: { color: '#0a1510', fontSize: fontSize.sm, fontWeight: '800' },
});

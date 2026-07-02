import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { ink, chalk, volt, semantic, space, radii, type } from '../theme/chalkline';
import { TickLabel, Button, Meter, fairnessColor, Icon } from './chalkline';
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
          the snapshot; this badge explains why. Cross-client copy: the
          old emoji pill migrated to eye icon + verbatim text. */}
      {likesYou && (
        <View style={styles.likesYouPill}>
          <Icon name="eye" size={16} color={volt.base} />
          <Text style={[type.label, styles.likesYouText]}>They're interested</Text>
        </View>
      )}

      <View style={styles.header}>
        <View>
          <Text style={type.label}>Trade with</Text>
          <View style={styles.nameRow}>
            <Text style={type.title}>@{data.opponent_username}</Text>
            {hasOpponentConfidence && (
              data.real_opponent ? (
                <View style={styles.opBadge}>
                  <View style={styles.opDotReal} />
                  <Text style={[type.label, styles.opTextReal]}>real</Text>
                </View>
              ) : (
                <View style={styles.opBadge}>
                  <View style={styles.opDotEst} />
                  <Text style={type.label}>est.</Text>
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
          <Text style={type.label}>Fair-value idea</Text>
          <Text style={type.bodySm}>
            This league-mate hasn't ranked players yet — this is a balanced trade by consensus value.
          </Text>
        </View>
      )}

      <StrengthBar value={matchPct} label="Match strength" />

      <View style={styles.split}>
        <View style={styles.side}>
          <TickLabel>YOU SEND</TickLabel>
          <View style={styles.sideStack}>
            {givePlayers.map((p) => (
              <PlayerCard key={p.id} player={p} compact />
            ))}
          </View>
          {sweetenerSide === 'give' && sweetenerPlayer && (
            <Text style={type.bodySm}>
              + {sweetenerPlayer.name} added to balance the deal
            </Text>
          )}
        </View>
        <View style={styles.divider} />
        <View style={styles.side}>
          <TickLabel>YOU GET</TickLabel>
          <View style={styles.sideStack}>
            {receivePlayers.map((p) => (
              <PlayerCard key={p.id} player={p} compact />
            ))}
          </View>
          {sweetenerSide === 'receive' && sweetenerPlayer && (
            <Text style={type.bodySm}>
              + {sweetenerPlayer.name} added to balance the deal
            </Text>
          )}
        </View>
      </View>

      {hasFairness && (
        <Meter
          value={data.fairness as number}
          color={fairnessColor(data.fairness as number)}
          label="Fairness"
          showPercent
        />
      )}

      {/* Human-readable reasons (flag trade_math.human_explanations is ON).
          Rendered only when the flag is on AND the backend returns a
          non-empty list. */}
      {showReasons && (
        <View style={styles.reasons}>
          {data.reasons!.map((r, i) => (
            <Text key={`${i}:${r}`} style={type.bodySm}>• {r}</Text>
          ))}
        </View>
      )}

      {variant === 'match' && (
        <View style={styles.actions}>
          <Button
            variant="pass"
            label="Decline"
            onPress={onDecline}
            disabled={acting}
            style={styles.actionBtn}
          />
          <Button
            variant="like"
            label="Accept"
            onPress={onAccept}
            disabled={acting}
            style={styles.actionBtn}
          />
        </View>
      )}
    </View>
  );
}

export default React.memo(TradeCardComp);

const styles = StyleSheet.create({
  card: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    padding: space.lg,
    gap: space.md,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  // Likes-you pill: volt-bordered pill (the one sanctioned pill shape)
  // with the Chalkline eye icon replacing the old emoji.
  likesYouPill: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    borderWidth: 1,
    borderColor: volt.base,
    borderRadius: radii.pill,
    paddingVertical: space.xs,
    paddingHorizontal: space.md,
  },
  likesYouText: { color: chalk.base },
  // Consensus-basis note: deliberately muted — it's a caveat, not a sell.
  consensusNote: { gap: space.xs },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  // Opponent-confidence chip: 6px square dot + micro label next to @handle.
  // Filled pos-green square = real (their actual saved rankings); hollow
  // dim square = estimated (noise-randomized off consensus seed).
  opBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
  },
  opDotReal: {
    width: 6,
    height: 6,
    backgroundColor: semantic.pos,
  },
  opDotEst: {
    width: 6,
    height: 6,
    borderWidth: 1,
    borderColor: chalk.dim,
  },
  opTextReal: { color: semantic.pos },
  split: {
    flexDirection: 'row',
    gap: space.md,
    alignItems: 'stretch',
  },
  side: { flex: 1, gap: space.sm },
  sideStack: { gap: space.xs },
  divider: {
    width: 1,
    backgroundColor: ink.line,
    alignSelf: 'stretch',
  },
  reasons: {
    backgroundColor: ink.ink0,
    borderWidth: 1,
    borderColor: ink.line,
    borderLeftWidth: 3,
    borderLeftColor: ink.lineStrong,
    padding: space.sm,
    paddingLeft: space.md,
    borderRadius: radii.sm,
    gap: space.xs,
  },
  actions: {
    flexDirection: 'row',
    gap: space.sm,
  },
  actionBtn: { flex: 1 },
});

import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ActivityIndicator,
  type AccessibilityActionEvent,
} from 'react-native';
import { ink, chalk, flare, ice, semantic, space, radii, type } from '../theme/chalkline';
import { TickLabel, Button, Icon, Badge } from './chalkline';
import PlayerCard from './PlayerCard';
import StrengthBar from './StrengthBar';
import TradeValueBar from './TradeValueBar';
import SendInSleeperButton from './SendInSleeperButton';
import { LockGlyph } from './PlayerContextMenu';
import { useFlag } from '../state/useFeatureFlags';
import type { Player, TradeCard as TradeCardData } from '../shared/types';

interface Props {
  data: TradeCardData;
  variant?: 'swipe' | 'match';
  // Match-variant action: archive the match from the inbox (ELO-neutral).
  // The "do the trade" action is the Send-in-Sleeper button below.
  onDismiss?: () => void;
  acting?: boolean;
  // "Send in Sleeper" — flagged beta. When true, render the direct-propose
  // button (itself flag-gated, so it's a no-op when the flag is off).
  showSend?: boolean;
  // Untouchables (feedback #95, flag trade.preference_lists): ids of the
  // caller's players marked "never offer in trades". Marked give-side
  // players render an UNTOUCHABLE badge; long-pressing a give-side player
  // invokes the toggle. Both optional — screens that don't wire the
  // feature render exactly as before.
  untouchableIds?: ReadonlySet<string>;
  onToggleUntouchable?: (player: Player) => void;
  // Player-swap (feedback #86): when set, every player row gets a swap
  // affordance that opens the replacement picker (swipe deck only —
  // MatchesScreen doesn't pass it, so match cards render exactly as
  // before). `repricing` shows a small in-flight indicator while an
  // edited card's /api/trade/evaluate round-trip re-prices the package.
  onSwapPlayer?: (player: Player, side: 'give' | 'receive') => void;
  repricing?: boolean;
  // Player context menu (teardown S3 PRD-02, flag ux.player_context_menu).
  // When set (screens pass it only while the flag is on), long-pressing ANY
  // player row opens the shared context menu instead of the legacy
  // single-purpose gestures, and give-side rows gain a visible lock toggle
  // (the untouchable "visible twin") beside the swap affordance.
  onPlayerMenu?: (player: Player, side: 'give' | 'receive') => void;
  // FB-47 finder targeting: positions the user is trying to ACQUIRE
  // (pinned targets + saved acquire prefs). Used only to sharpen the
  // partner-fit line's copy ("They're deep at WR"); the line itself
  // renders whenever the card carries `partner_fit`.
  fitTargetPositions?: string[];
}

// FB-47 — partner-fit line copy. `partner_fit` is a 0–1 scalar; the exact
// depth count behind it isn't serialized, so the copy is a calibrated tier
// label — sharpened to name the position when the card's match_context
// confirms the opponent is surplus-deep at a position the user targets.
export function partnerFitLine(
  fit: number,
  opponentSurplus?: string[],
  targetPositions?: string[],
): string {
  const hit = (targetPositions ?? []).find((pos) =>
    (opponentSurplus ?? []).includes(pos),
  );
  if (fit >= 0.65) {
    return hit
      ? `They're deep at ${hit} — a natural seller`
      : 'Strong fit for your targets';
  }
  if (fit >= 0.35) return 'Decent fit for your targets';
  return 'Weak fit for your targets';
}

// Shared rendering for generated trades (TradesScreen swipe deck) and
// mutual matches (MatchesScreen list). The only difference between the
// two variants is the action buttons at the bottom — swipe decks don't
// show buttons (gestures drive the decision), match cards do.
function TradeCardComp({
  data,
  variant = 'swipe',
  onDismiss,
  acting,
  showSend = false,
  untouchableIds,
  onToggleUntouchable,
  onSwapPlayer,
  repricing = false,
  onPlayerMenu,
  fitTargetPositions,
}: Props) {
  const matchPct = Math.round(data.match_score || 0);
  // The pick-denominated TradeValueBar (feedback #157) is the universal
  // trade verdict — it replaces the old 0–1 fairness meter on the deck.
  // Backend stamps give_value/receive_value/favors/gap on every generated
  // card; render only when both package values are present so legacy /
  // echo-rebuilt cards (and swapped cards mid-reprice) hide the bar instead
  // of crashing. `gap` may be null (one-sided/exactly even) — the bar
  // renders correctly with gap={null}.
  const hasValueVerdict =
    typeof data.give_value === 'number' && typeof data.receive_value === 'number';
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
  // FB-47 — partner-fit line, only when the engine stamped a fit score
  // (flag on + user expressed targets). One short line; the deck order
  // already reflects fit server-side, this just explains it.
  const fitLine =
    typeof data.partner_fit === 'number'
      ? partnerFitLine(
          data.partner_fit,
          data.match_context?.opponent_surplus,
          fitTargetPositions,
        )
      : null;

  // Player-swap affordance (feedback #86) — 28px icon button per player
  // row (Chalkline icon-button construction: square radius, 1px border;
  // hitSlop lifts the touch target to ~44px). Rendered via PlayerCard's
  // rightSlot; on the give side it shares the slot with the UNTOUCHABLE
  // badge so both features co-exist.
  // FB-147 — "ON THE BLOCK" micro-tag: the backend stamps `on_block` on a
  // card player when the league's synced Sleeper trade block (flag
  // sleeper.trade_block) names them. Chalkline Badge construction, flare =
  // informational (ADR-005). Absent field = no tag, so legacy payloads and
  // flag-off builds render exactly as before.
  const blockBadge = (p: Player) =>
    p.on_block ? <Badge label="ON THE BLOCK" color={flare.base} colorText /> : null;

  const swapSlot = (p: Player, side: 'give' | 'receive') =>
    onSwapPlayer ? (
      <Pressable
        hitSlop={8}
        onPress={() => onSwapPlayer(p, side)}
        accessibilityRole="button"
        accessibilityLabel={`Swap ${p.name} for another player`}
        style={({ pressed }) => [styles.swapBtn, pressed && styles.swapBtnPressed]}
      >
        <Icon name="swap" size={14} color={chalk.dim} />
      </Pressable>
    ) : null;

  // Untouchable visible twin (S3 PRD-02, menu flag on): a lock toggle in
  // the give-side rightSlot so the long-press accelerator is never the
  // sole path. Marked = ice-bordered closed lock; unmarked = dim open lock.
  const lockSlot = (p: Player) =>
    onPlayerMenu && onToggleUntouchable ? (
      (() => {
        const marked = untouchableIds?.has(p.id) ?? false;
        return (
          <Pressable
            hitSlop={8}
            onPress={() => onToggleUntouchable(p)}
            accessibilityRole="button"
            accessibilityState={{ selected: marked }}
            accessibilityLabel={
              marked
                ? `Remove untouchable from ${p.name}`
                : `Mark ${p.name} untouchable`
            }
            style={({ pressed }) => [
              styles.swapBtn,
              marked && styles.lockBtnMarked,
              pressed && styles.swapBtnPressed,
            ]}
          >
            <LockGlyph size={14} color={marked ? ice.base : chalk.dim} locked={marked} />
          </Pressable>
        );
      })()
    ) : null;

  // Command long-press: the shared context menu (flag on via onPlayerMenu)
  // supersedes the legacy give-side-only untouchable toggle.
  const longPressFor = (p: Player, side: 'give' | 'receive') => {
    if (onPlayerMenu) return () => onPlayerMenu(p, side);
    if (side === 'give' && onToggleUntouchable) return () => onToggleUntouchable(p);
    return undefined;
  };

  // S8 PRD-02 (inert a11y) — each player row is one grouped utterance
  // (PlayerCard composes the base label; badges appended here) with the
  // row's commands as custom actions. The rightSlot icon buttons are
  // swallowed by the row container on iOS (the documented RN caveat), so
  // the actions are the screen-reader path to swap/untouchable/menu.
  const rowA11y = (p: Player, side: 'give' | 'receive') => {
    const marked = untouchableIds?.has(p.id) ?? false;
    const actions: { name: string; label: string }[] = [];
    if (onPlayerMenu) actions.push({ name: 'menu', label: 'Player options' });
    if (side === 'give' && onToggleUntouchable) {
      actions.push({
        name: 'untouchable',
        label: marked ? 'Remove untouchable' : 'Mark untouchable',
      });
    }
    if (onSwapPlayer) actions.push({ name: 'swap', label: 'Swap for another player' });
    return {
      accessibilityLabel: [
        p.name,
        String(p.position),
        p.team || 'FA',
        marked ? 'untouchable' : null,
        p.on_block ? 'on the block' : null,
        p.injury_status ? `injury ${p.injury_status}` : null,
      ]
        .filter(Boolean)
        .join(', '),
      accessibilityActions: actions.length ? actions : undefined,
      onAccessibilityAction: actions.length
        ? ({ nativeEvent }: AccessibilityActionEvent) => {
            if (nativeEvent.actionName === 'menu') onPlayerMenu?.(p, side);
            else if (nativeEvent.actionName === 'untouchable') onToggleUntouchable?.(p);
            else if (nativeEvent.actionName === 'swap') onSwapPlayer?.(p, side);
          }
        : undefined,
    };
  };

  return (
    <View style={styles.card}>
      {/* Likes-you pill — counterparty already liked the mirror of this
          trade, so lead with it. Server pins these cards to the top of
          the snapshot; this badge explains why. Cross-client copy: the
          old emoji pill migrated to eye icon + verbatim text. */}
      {likesYou && (
        <View style={styles.likesYouPill}>
          <Icon name="eye" size={16} color={flare.base} />
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
        {/* Header badges — flare = informational accent (ADR-005).
            PAYS FOR FIT (phase-2): the package overpays consensus value to
            land a positional fit; the narrative already explains the
            tradeoff, so the badge is the whole callout. EDITED (feedback
            #86): the user modified this package, so the engine's original
            numbers no longer describe it. */}
        {(data.fitPremium || data.edited) && (
          <View style={styles.headerBadges}>
            {data.fitPremium && (
              <Badge label="PAYS FOR FIT" color={flare.base} colorText />
            )}
            {data.edited && <Badge label="EDITED" color={flare.base} colorText />}
          </View>
        )}
      </View>

      {/* FB-47 — partner-fit line. Muted, hint-tier: it narrates why this
          counterparty ranks where they do in the deck, nothing more. */}
      {fitLine && (
        <View style={styles.fitRow}>
          <View style={styles.fitDot} />
          <Text style={type.bodySm}>{fitLine}</Text>
        </View>
      )}

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

      {/* Match strength was computed for the ORIGINAL package; after a
          player swap it's stale, so edited cards hide it and lean on the
          re-priced value bar below. */}
      {!data.edited && <StrengthBar value={matchPct} label="Match strength" />}

      <View style={styles.split}>
        <View style={styles.side}>
          <TickLabel>YOU SEND</TickLabel>
          <View style={styles.sideStack}>
            {givePlayers.map((p) => (
              <PlayerCard
                key={p.id}
                player={p}
                compact
                {...rowA11y(p, 'give')}
                onLongPress={longPressFor(p, 'give')}
                rightSlot={
                  p.on_block ||
                  untouchableIds?.has(p.id) ||
                  onSwapPlayer ||
                  (onPlayerMenu && onToggleUntouchable) ? (
                    <View style={styles.rightSlotRow}>
                      {blockBadge(p)}
                      {untouchableIds?.has(p.id) ? (
                        <Badge label="UNTOUCHABLE" color={flare.base} />
                      ) : null}
                      {lockSlot(p)}
                      {swapSlot(p, 'give')}
                    </View>
                  ) : undefined
                }
              />
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
              <PlayerCard
                key={p.id}
                player={p}
                compact
                {...rowA11y(p, 'receive')}
                onLongPress={longPressFor(p, 'receive')}
                rightSlot={
                  p.on_block || onSwapPlayer ? (
                    <View style={styles.rightSlotRow}>
                      {blockBadge(p)}
                      {swapSlot(p, 'receive')}
                    </View>
                  ) : undefined
                }
              />
            ))}
          </View>
          {sweetenerSide === 'receive' && sweetenerPlayer && (
            <Text style={type.bodySm}>
              + {sweetenerPlayer.name} added to balance the deal
            </Text>
          )}
        </View>
      </View>

      {hasValueVerdict && !repricing && (
        <TradeValueBar
          giveValue={data.give_value as number}
          receiveValue={data.receive_value as number}
          favors={data.favors ?? null}
          gap={data.gap ?? null}
          youLabel="You"
          themLabel={`@${data.opponent_username}`}
        />
      )}

      {/* Edited-card re-price in flight — the value bar above is hidden
          (give/receive cleared on swap) until fresh numbers land. */}
      {repricing && (
        <View style={styles.repricingRow}>
          <ActivityIndicator size="small" color={ice.base} />
          <Text style={type.bodySm}>Re-pricing…</Text>
        </View>
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

      {/* Mutual-match CTAs: Dismiss (archive, ELO-neutral) + Send in Sleeper
          (the real "execute the trade" action — flag-gated, renders null when
          the beta flag is off, so a flag-off build shows Dismiss alone). */}
      {variant === 'match' ? (
        <View style={styles.actions}>
          <Button
            variant="pass"
            label="Dismiss"
            onPress={onDismiss}
            disabled={acting}
            style={styles.actionBtn}
          />
          {showSend && (
            <SendInSleeperButton
              leagueId={data.league_id}
              theirUserId={data.opponent_user_id}
              givePlayerIds={data.give_player_ids}
              receivePlayerIds={data.receive_player_ids}
              style={styles.actionBtn}
            />
          )}
        </View>
      ) : (
        showSend && (
          <View style={styles.sendRow}>
            <SendInSleeperButton
              leagueId={data.league_id}
              theirUserId={data.opponent_user_id}
              givePlayerIds={data.give_player_ids}
              receivePlayerIds={data.receive_player_ids}
            />
          </View>
        )
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
  // Likes-you pill: flare-bordered pill (the one sanctioned pill shape)
  // with the Chalkline eye icon replacing the old emoji. Flare = informational
  // accent (ADR-005); ice stays reserved for actions.
  likesYouPill: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.pill,
    paddingVertical: space.xs,
    paddingHorizontal: space.md,
  },
  likesYouText: { color: chalk.base },
  // Consensus-basis note: deliberately muted — it's a caveat, not a sell.
  consensusNote: { gap: space.xs },
  // FB-47 partner-fit line: hint-tier row — 6px hollow square marker (same
  // construction as the est. opponent dot) + muted body text.
  fitRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  fitDot: {
    width: 6,
    height: 6,
    borderWidth: 1,
    borderColor: chalk.dim,
  },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  // Header badge cluster (PAYS FOR FIT / EDITED) — right side of the
  // header row; wraps if both render on a narrow card.
  headerBadges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: space.xs,
    flexShrink: 1,
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
  sendRow: { marginTop: space.sm },

  // Player-swap (feedback #86) — per-row icon button + shared rightSlot
  // row (swap button beside the UNTOUCHABLE badge on give-side rows).
  rightSlotRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
  },
  swapBtn: {
    width: 28,
    height: 28,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: ink.ink1,
  },
  swapBtnPressed: {
    backgroundColor: ink.ink3,
  },
  // Untouchable lock twin — marked state borrows the active treatment
  // (ice border) from the queue button's queued state.
  lockBtnMarked: {
    borderColor: ice.base,
  },
  repricingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
});

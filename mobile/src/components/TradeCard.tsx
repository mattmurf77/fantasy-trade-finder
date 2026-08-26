import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  Platform,
  KeyboardAvoidingView,
  Pressable,
  ActivityIndicator,
  type AccessibilityActionEvent,
} from 'react-native';
import { ink, chalk, flare, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { TickLabel, Button, Icon, Badge } from './chalkline';
import PlayerCard from './PlayerCard';
import StrengthBar from './StrengthBar';
import TradeValueBar from './TradeValueBar';
import CardImpactBlock from './CardImpactBlock';
import type { CardImpactState } from '../state/useCardImpact';
import SendInSleeperButton from './SendInSleeperButton';
import DeclineReasonPanel, {
  type DeclineReasonPanelProps,
} from './DeclineReasonPanel';
import { LockGlyph } from './PlayerContextMenu';
import { registerGuideTarget, unregisterGuideTarget } from '../state/guideTargets';
import { useFlag } from '../state/useFeatureFlags';
import { consensusNote } from '../utils/consensusNote';
import type { Player, TradeCard as TradeCardData } from '../shared/types';

// #362 — chip copy helpers. Both derive entirely from the server-stamped
// `standing_offer_mine` payload; neither invents a season the offer does
// not carry.
const ROUND_WORDS: Record<number, string> = { 1: '1st', 2: '2nd', 3: '3rd', 4: '4th' };
function roundWordFor(round: number): string {
  return ROUND_WORDS[round] ?? `R${round}`;
}
/** [2027, 2028] → "'27–'28" · [2027] → "'27" · [2027, 2029] → "'27 '29". */
function seasonSpan(seasons: number[]): string {
  const sorted = [...seasons].sort((a, b) => a - b);
  const short = (s: number) => `'${String(s).slice(-2)}`;
  if (sorted.length === 0) return '';
  if (sorted.length === 1) return short(sorted[0]);
  const contiguous = sorted.every((s, i) => i === 0 || s === sorted[i - 1] + 1);
  return contiguous
    ? `${short(sorted[0])}–${short(sorted[sorted.length - 1])}`
    : sorted.map(short).join(' ');
// #384 — the overlay presentation needs two host hooks the inline form has no
// use for. Kept OUT of `DeclineReasonPanelProps` on purpose: the panel itself
// knows nothing about being hosted in a sheet, and every existing caller of it
// (inline deck, EndorsedTradeCard) must stay untouched.
export interface DispositionReasons extends DeclineReasonPanelProps {
  /** The ✕ opened the reason sheet. */
  onOverlayOpened?: () => void;
  /** The sheet was dismissed by the backdrop / system close. `banked` is true
   *  when a layer-1 tile had already committed the pass — the host must then
   *  commit the deferred deck advance, or the card is stranded (review #1). */
  onOverlayDismissed?: (banked: boolean) => void;
}

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
  // audit P0-6 — league display name for the copy-trade fallback's first
  // line. Matches passes TradeMatch/AwaitingTrade.league_name; every other
  // caller omits it and the copy text drops the line.
  leagueName?: string;
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
  // #357 — per-card lineup + playoff-odds impact, fetched by the HOST for the
  // fronted card only (operator: "compute on the fronted card only"). Absent
  // on peek cards, match/awaiting mounts and read-only cards, which is what
  // keeps a 30-card deck at one simulation rather than thirty. Prop-driven
  // rather than self-fetching, per the components/ convention.
  cardImpact?: CardImpactState | null;
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
  // #186 — per-side "keep this side" affordance (swipe deck only). When
  // set, each side gets a compact action that pins that side's players
  // (the existing pinned_give/pinned_receive machinery) and regenerates
  // the deck, so a user who likes ONE side sees other offers around it.
  onKeepSide?: (side: 'give' | 'receive') => void;
  // #190 — "Edit in calculator": opens the manual calculator prefilled
  // with this card's opponent + both sides (swipe deck only).
  onEditInCalculator?: () => void;
  // #194 — per-asset remove (swipe deck only): drop this asset from the
  // suggested trade and re-price the rest. The card renders the ✕ dimmed
  // when the asset is the last one on its side (a trade needs ≥1 per
  // side); the handler owns the honest hint + pinned-package confirm.
  onRemoveAsset?: (player: Player, side: 'give' | 'receive') => void;
  // #216 — featured-trade window reuse: asset-idea cards have no match
  // score (consensus sweep, not the divergence engine), so the window
  // hides the bar instead of rendering an honest-looking 0%.
  hideMatchStrength?: boolean;
  // #249 — MatchesScreen: the untouchable lock "visible twin" isn't wanted
  // on the matches inbox (operator call). Hides ONLY the button UI — the
  // long-press context menu, the a11y custom action and the UNTOUCHABLE
  // badge all still work, so the mechanism stays reachable on-screen.
  hideLockButton?: boolean;
  // #169 (card frame C, operator-modified) — deck disposition actions.
  // When present, Pass/Like render inside the card directly beneath the
  // player tile section. Only the deck's TOP card passes this — match
  // variant, peek card, and read-only mounts never do.
  disposition?: {
    onPass: () => void;
    onLike: () => void;
    disabled?: boolean;
    // Decline-reason capture (flag `feedback.decline_reasons`, SPEC §1/§5).
    // Present ⇒ the ✕ is replaced by the three layer-1 tiles (Value · Fit ·
    // Neither) rendered beneath this row, with layer 2 opening under them;
    // the ✓ is untouched. Absent (flag off, or any non-deck mount) ⇒ the
    // shipped ✓/✕ row renders byte-identically. Only TradesScreen's top
    // card ever supplies it.
    reasons?: DispositionReasons;
  };
  // #384 ruling 1 (review #7) — render the decline reasons as an OVERLAY over
  // the page instead of the shipped inline tiles. A PROP, never a flag read:
  // the operator scoped the overlay to "this version of the calculator", and
  // only the host knows whether this deck was reached from it. Absent/false ⇒
  // the shipped inline-tile form, byte-identical.
  reasonsAsOverlay?: boolean;
  // #319 — rendered as the card's FINAL block, after the actions/send rows.
  // The Matches inbox mounts MatchValueSection (and the awaiting Dismiss row)
  // here; every other caller omits it and the card renders byte-identically.
  footer?: React.ReactNode;
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
// two variants is the actions — match cards show Dismiss/Send buttons at
// the bottom; on the deck, gestures drive the decision and the top card
// (alone) mirrors them with the in-card Pass/Like row (#169).
function TradeCardComp({
  data,
  variant = 'swipe',
  onDismiss,
  acting,
  showSend = false,
  leagueName,
  untouchableIds,
  onToggleUntouchable,
  onSwapPlayer,
  repricing = false,
  cardImpact = null,
  onPlayerMenu,
  fitTargetPositions,
  onKeepSide,
  onEditInCalculator,
  onRemoveAsset,
  hideMatchStrength = false,
  hideLockButton = false,
  disposition,
  reasonsAsOverlay = false,
  footer,
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
  // …and whether this particular one clears the app's own balanced bar
  // (0.75). Computed unconditionally — it is a pure call on a number — and
  // read only inside the `isConsensus` block below.
  const note = consensusNote(data.fairness);
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
  // #384 ruling 1 — in the merged calculator experience the ✕ stays ONE
  // button and the reasons arrive as an overlay over the page, instead of
  // three inline tiles replacing the ✕. `reasonsAsOverlay` is a PROP (see the
  // Props comment): the host owns the "arrived from the calculator" fact.
  const [reasonOverlayOpen, setReasonOverlayOpen] = useState(false);
  // Review #1 — a layer-1 tile BANKS the pass (`advance('pass', {
  // deferDeckAdvance: true })`) and the host only fronts the next card from
  // layer 2. So the sheet must stay up through layer 2, and a backdrop
  // dismiss AFTER a tile has been banked has to tell the host to commit that
  // deferred advance — otherwise ✓/✕/swipe/VoiceOver are all inert and the
  // card is a dead end. Ref, not state: read inside the dismiss handler only.
  const reasonBankedRef = useRef(false);
  // Review #3c — n19 spotlights `trades.pass-btn`, which was never registered
  // as a guide target (only four ids are, TradesScreen :3003-3006). Registered
  // per-instance from here because ONLY the deck's top card is given
  // `disposition` (TradesScreen :6972 is the single call site), so exactly one
  // node can ever claim the id. Skipped when the inline-tile form removes the
  // button — an id pointing at an unmounted node measures to null anyway.
  const passBtnRef = useRef<View | null>(null);
  const passBtnMounted = !!disposition && !(disposition.reasons && !reasonsAsOverlay);
  useEffect(() => {
    if (!passBtnMounted) return;
    registerGuideTarget('trades.pass-btn', passBtnRef);
    return () => unregisterGuideTarget('trades.pass-btn');
  }, [passBtnMounted]);
  // #384 device feedback (report 4) — n20 ("Swap arrows change any player")
  // shipped untargeted because the affordance is per-row. It only needs ONE
  // row to teach the control, so the FIRST give row's swap button carries the
  // id. Same scoping rule as `trades.pass-btn` above: registered only when
  // `disposition` is present, i.e. only on the deck's top card, so exactly one
  // node can ever claim it. Also gated on `onSwapPlayer` — without it the slot
  // renders null and an empty wrapper measures to nothing.
  const swapFirstRef = useRef<View | null>(null);
  const swapFirstMounted = !!disposition && !!onSwapPlayer && givePlayers.length > 0;
  useEffect(() => {
    if (!swapFirstMounted) return;
    registerGuideTarget('trades.swap-first', swapFirstRef);
    return () => unregisterGuideTarget('trades.swap-first');
  }, [swapFirstMounted]);
  // Device feedback 2026-08-23 (v2 note 17) — n22 ("the fairness meter") used
  // to target `trades.fairness-help`, the ⓘ in TradesScreen's "Trade fairness"
  // row. That row renders inside `{!firstRun && …}`, so on a first-run deck —
  // precisely when a new user is being toured — the node never mounts and the
  // beat degrades to a bubble with no ring and no scroll. Retargeted at the
  // meter itself, which is what the note asked to see highlighted.
  //
  // Same scoping rule as `trades.pass-btn` and `trades.swap-first` above: only
  // the deck's top card is given `disposition`, so exactly one node can ever
  // claim the id — a peek card, a match card or a read-only mount would
  // otherwise race for it and the spotlight would ring whichever won.
  // `hasValueVerdict`/`repricing` are the same conditions the bar renders
  // under; registering while it is hidden would measure null.
  const cardMeterRef = useRef<View | null>(null);
  const cardMeterMounted = !!disposition && hasValueVerdict && !repricing;
  useEffect(() => {
    if (!cardMeterMounted) return;
    registerGuideTarget('trades.card-meter', cardMeterRef);
    return () => unregisterGuideTarget('trades.card-meter');
  }, [cardMeterMounted]);

  // Backdrop / system dismiss of the reason overlay. BEFORE any tile the card
  // is simply left undecided (today's intent). AFTER a tile, the pass is
  // already written server-side and the deck advance is the only thing still
  // owed — the host commits it with layer 2 = none, which is exactly the row
  // an inline-mode user leaves when they answer layer 1 and stop.
  function dismissReasonOverlay() {
    const banked = reasonBankedRef.current;
    reasonBankedRef.current = false;
    setReasonOverlayOpen(false);
    disposition?.reasons?.onOverlayDismissed?.(banked);
  }
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
  // FB-147 — "OTB" (on the block) micro-tag: the backend stamps `on_block`
  // on a card player when the league's synced Sleeper trade block (flag
  // sleeper.trade_block) names them. Chalkline Badge construction, flare =
  // informational (ADR-005). Absent field = no tag, so legacy payloads and
  // flag-off builds render exactly as before. Label shortened from
  // "ON THE BLOCK" (#153 — the long badge overlapped the position tags);
  // screen readers still hear the full phrase via rowA11y below.
  // #226 — the badge now renders via PlayerCard's badgeSlot (inside the
  // wrapping header badge row, both columns) instead of the overlay
  // rightSlot, so it reflows next to the position tag rather than
  // colliding with it on narrow split columns / large text sizes.
  const blockBadge = (p: Player) =>
    p.on_block ? <Badge label="OTB" color={flare.base} colorText /> : null;

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
  // #249: hosts can hide the button (MatchesScreen) — the context menu +
  // a11y action remain the untouchable path there.
  const lockSlot = (p: Player) =>
    !hideLockButton && onPlayerMenu && onToggleUntouchable ? (
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

  // #194 — per-asset remove (swipe deck only): 28px ✕ beside the swap
  // affordance. The last asset on a side renders dimmed (a trade needs at
  // least one per side) but stays tappable — the screen's handler answers
  // with the honest hint instead of silently ignoring the tap.
  const removeSlot = (p: Player, side: 'give' | 'receive') => {
    if (variant !== 'swipe' || !onRemoveAsset) return null;
    const sideCount = side === 'give' ? givePlayers.length : receivePlayers.length;
    const canRemove = sideCount > 1;
    return (
      <Pressable
        testID={`trade-card.remove-asset.${p.id}`}
        hitSlop={8}
        onPress={() => onRemoveAsset(p, side)}
        accessibilityRole="button"
        accessibilityState={{ disabled: !canRemove }}
        accessibilityLabel={
          canRemove
            ? `Remove ${p.name} from this trade`
            : `Cannot remove ${p.name} — a trade needs at least one asset on each side`
        }
        style={({ pressed }) => [
          styles.swapBtn,
          !canRemove && styles.removeBtnDisabled,
          pressed && styles.swapBtnPressed,
        ]}
      >
        <Icon name="x" size={14} color={chalk.dim} />
      </Pressable>
    );
  };

  // #186 — per-side keep affordance (swipe deck only): pins that side's
  // players and regenerates, so the OTHER side gets re-shopped. Compact
  // bordered-chalk construction (ice stays on the deck's primary actions).
  const keepSlot = (side: 'give' | 'receive') =>
    variant === 'swipe' && onKeepSide ? (
      <Pressable
        testID={side === 'give' ? 'trade-card.keep-give' : 'trade-card.keep-receive'}
        accessibilityRole="button"
        accessibilityLabel={
          side === 'give'
            ? 'Keep the players you send and see other returns'
            : 'Keep the players you get and see other offers'
        }
        onPress={() => onKeepSide(side)}
        style={({ pressed }) => [styles.keepBtn, pressed && styles.keepBtnPressed]}
      >
        <Text style={styles.keepBtnText}>Keep · more offers</Text>
      </Pressable>
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
    if (variant === 'swipe' && onRemoveAsset) {
      actions.push({ name: 'remove', label: 'Remove from this trade' });
    }
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
            else if (nativeEvent.actionName === 'remove') onRemoveAsset?.(p, side);
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

      {/* #362 — the SENDER's own standing-offer chip. Server-stamped
          (`standing_offer_mine`), so there is no client-side join, and it
          appears only on the offer owner's own deck. Ice, not flare: this
          is an action-state marker on the user's OWN commitment, where the
          counterparty-side pill below stays flare (informational).
          Provenance-chip construction, reusing the wildcard chip's shape —
          no new pill or badge component. The chip is bound to the offer
          record and dies with it; there is deliberately no global "open to
          1sts" badge on the player anywhere in the app, which would
          outlive the intent and leak the offer to excluded league-mates. */}
      {data.standingOfferMine ? (
        <View
          style={[styles.wildcardChip, styles.standingChip]}
          accessibilityLabel={`Open to ${roundWordFor(data.standingOfferMine.round)}s in ${data.standingOfferMine.seasons.join(', ')}`}
          testID="trade-card.standing-offer-chip"
        >
          <View style={[styles.wildcardTick, styles.standingTick]} />
          <Text style={styles.wildcardLabel}>
            {`OPEN TO ${roundWordFor(data.standingOfferMine.round).toUpperCase()}S · ${seasonSpan(data.standingOfferMine.seasons)}`}
          </Text>
        </View>
      ) : null}

      {/* F7 exploration wildcard (server flag deck.exploration) — honest
          labeling: this card was deliberately drawn from OUTSIDE the user's
          learned taste (gate-passing quality, off-taste pick). Provenance-
          chip construction (ProvenanceChip.tsx: hairline chip + tick +
          mono micro-label); flare = informational highlight (ADR-005).
          Backend serializes `wildcard` only when true, so legacy payloads
          and flag-off builds render exactly as before. F4's session
          re-rank already position-locks wildcard cards (sessionRerank). */}
      {data.wildcard === true && (
        <View
          style={styles.wildcardChip}
          accessibilityLabel="Wildcard — outside your usual"
          testID="trade-card.wildcard-chip"
        >
          <View style={styles.wildcardTick} />
          <Text style={styles.wildcardLabel}>WILDCARD — OUTSIDE YOUR USUAL</Text>
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

      {/* #362 — "Why you're seeing this", when the card came from a
          league-mate's standing offer rather than an exact mirror. The
          string is composed SERVER-SIDE and rendered verbatim: it names the
          sender, the player, the round and the seasons, and by construction
          carries no team count, no roster list and no other member's name
          (R-19). Never rebuild it client-side. Without this line a boosted
          card is indistinguishable from a lucky generation. */}
      {data.standingOfferReason ? (
        <View style={styles.consensusNote} testID="trade-card.standing-offer-reason">
          <Text style={type.label}>Why you're seeing this</Text>
          <Text style={type.bodySm} testID="trade-card.standing-offer-reason.body">
            {data.standingOfferReason}
          </Text>
        </View>
      ) : null}

      {/* FB-47 — partner-fit line. Muted, hint-tier: it narrates why this
          counterparty ranks where they do in the deck, nothing more. */}
      {fitLine && (
        <View style={styles.fitRow}>
          <View style={styles.fitDot} />
          <Text style={type.bodySm}>{fitLine}</Text>
        </View>
      )}

      {/* Counterparty breaker — "their likely hesitation" (flag
          trade.breaker_narrative; the server serializes `breaker` only for
          narrated cards, so payload presence IS the gate — a client-side
          flag check would add a second gate that can only disagree, fit
          precedent). The fixed lead-in label "Their likely hesitation:" is
          part of the server-composed sentence (LLD §1.6 template table);
          the client holds no copy of its own and never switches on
          `code`/`severity`. Optional chaining is the null-safety: an absent
          or malformed `breaker` renders nothing, so older payloads and
          flag-off decks are byte-identical to today.
          Chalkline: type tokens + flare for the informational dot
          (ADR-005) — no new colors, no emoji, radius within spec. */}
      {data.breaker?.sentence && (
        <View style={styles.breakerRow} testID="trade-card.breaker-hesitation">
          <View style={styles.breakerDot} />
          <Text style={type.bodySm} testID="trade-card.breaker-hesitation.body">
            {data.breaker.sentence}
          </Text>
        </View>
      )}

      {/* Consensus basis — subtle label so users know this card isn't
          built on real ranking disagreement. No tooltip pattern in the
          app, so the hint renders inline as a muted sub-line.

          The sub-line USED to assert "this is a balanced trade by consensus
          value" on `isConsensus` alone, with no fairness check — and the
          live generation floor is 0.50, not the app's own 0.75 bar, so 805
          of 7,293 served consensus cards said "balanced" while sitting below
          it. `consensusNote` now derives the copy from `data.fairness`:
          below the bar the line TRUNCATES to its true half and stops. No
          replacement wording (operator, 2026-08-19) — the TradeValueBar
          below already shows direction and magnitude via favors/gap, so
          prose about value would restate it. utils/consensusNote.ts carries
          the reasoning; check-consensus-balance-claim.js pins it. */}
      {isConsensus && (
        <View style={styles.consensusNote} testID="trade-card.consensus-note">
          <Text style={type.label}>{note.label}</Text>
          <Text style={type.bodySm} testID="trade-card.consensus-note.body">
            {note.body}
          </Text>
        </View>
      )}

      {/* Match strength was computed for the ORIGINAL package; after a
          player swap it's stale, so edited cards hide it and lean on the
          re-priced value bar below. #276 — `compact` (existing prop) trims
          its internal gap; the meter itself is unchanged. */}
      {!data.edited && !hideMatchStrength && (
        <StrengthBar value={matchPct} label="Match strength" compact />
      )}

      <View style={styles.split}>
        <View style={styles.side}>
          <TickLabel>YOU SEND</TickLabel>
          <View style={styles.sideStack}>
            {givePlayers.map((p, i) => (
              <PlayerCard
                key={p.id}
                player={p}
                compact
                {...rowA11y(p, 'give')}
                onLongPress={longPressFor(p, 'give')}
                // #226 — informational badges live in the wrapping header
                // row; the in-flow rightSlot keeps only the interactive
                // controls (stacked, so the narrow column keeps its width).
                badgeSlot={
                  p.on_block || untouchableIds?.has(p.id) ? (
                    <>
                      {blockBadge(p)}
                      {untouchableIds?.has(p.id) ? (
                        <Badge label="UNTOUCHABLE" color={flare.base} />
                      ) : null}
                    </>
                  ) : undefined
                }
                rightSlot={
                  onSwapPlayer ||
                  (variant === 'swipe' && onRemoveAsset) ||
                  (!hideLockButton && onPlayerMenu && onToggleUntouchable) ? (
                    <View style={styles.rightSlotStack}>
                      {lockSlot(p)}
                      {/* n20's spotlight rides the FIRST give row's swap
                          control — one row is enough to teach a per-row
                          affordance, and the top card is the only card that
                          ever has one (#384 report 4). */}
                      {i === 0 ? (
                        <View ref={swapFirstRef} collapsable={false}>
                          {swapSlot(p, 'give')}
                        </View>
                      ) : (
                        swapSlot(p, 'give')
                      )}
                      {removeSlot(p, 'give')}
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
          {keepSlot('give')}
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
                // #226 — same treatment as the give column: badge in the
                // header row, controls stacked in the in-flow rightSlot.
                badgeSlot={p.on_block ? blockBadge(p) : undefined}
                rightSlot={
                  onSwapPlayer || (variant === 'swipe' && onRemoveAsset) ? (
                    <View style={styles.rightSlotStack}>
                      {swapSlot(p, 'receive')}
                      {removeSlot(p, 'receive')}
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
          {keepSlot('receive')}
        </View>
      </View>

      {/* #169 (card frame C) — check / x disposition row, moved inside the
          card directly beneath the players being traded. Same outcome as
          swiping right/left: the host wires both to advance(), so the deck
          advance, haptics, and the API call are identical to the swipe
          path. Disabled while a swipe mutation is in flight to prevent
          double-firing. */}
      {disposition ? (
        <>
          <View style={styles.dispositionRow}>
            {/* Decline-reason capture (flag `feedback.decline_reasons`,
                SPEC §1): with `reasons` wired, the three layer-1 tiles ARE
                the pass, so the ✕ is removed and this row holds the ✓
                alone — unchanged in every other respect. `reasons` absent
                (flag off, and on every non-deck mount) ⇒ this renders
                byte-identically to the shipped ✓/✕ row. */}
            {disposition.reasons && !reasonsAsOverlay ? null : (
              <Pressable
                ref={passBtnRef}
                collapsable={false}
                testID="trades.pass-btn"
                onPress={
                  // Overlay mode: the ✕ opens the reason sheet, and the
                  // PANEL commits the pass (its layer-1 tap is the
                  // disposition — same contract as the inline form). Without
                  // reasons wired it is the plain pass it has always been.
                  disposition.reasons && reasonsAsOverlay
                    ? () => {
                        reasonBankedRef.current = false;
                        setReasonOverlayOpen(true);
                        disposition.reasons!.onOverlayOpened?.();
                      }
                    : disposition.onPass
                }
                disabled={disposition.disabled}
                style={({ pressed }) => [
                  styles.dispositionBtn,
                  styles.dispositionBtnPass,
                  pressed && styles.dispositionBtnPassPressed,
                  disposition.disabled && styles.dispositionDisabled,
                ]}
                accessibilityLabel="Pass on this trade"
                accessibilityRole="button"
              >
                {({ pressed }) => (
                  <Icon name="x" color={pressed ? ink.ink0 : semantic.neg} />
                )}
              </Pressable>
            )}
            <Pressable
              testID="trades.like-btn"
              onPress={disposition.onLike}
              disabled={disposition.disabled}
              style={({ pressed }) => [
                styles.dispositionBtn,
                styles.dispositionBtnLike,
                pressed && styles.dispositionBtnLikePressed,
                disposition.disabled && styles.dispositionDisabled,
              ]}
              accessibilityLabel="Like this trade"
              accessibilityRole="button"
            >
              {({ pressed }) => (
                <Icon name="check" color={pressed ? ink.ink0 : semantic.pos} />
              )}
            </Pressable>
          </View>
          {disposition.reasons && !reasonsAsOverlay ? (
            <DeclineReasonPanel {...disposition.reasons} />
          ) : null}
          {disposition.reasons && reasonsAsOverlay ? (
            <Modal
              visible={reasonOverlayOpen}
              transparent
              animationType="fade"
              onRequestClose={() => dismissReasonOverlay()}
            >
              {/* The "Other" composer's send button opens BELOW its text box.
                  Inside a Modal the host ScrollView's inset machinery cannot
                  reach it, so the sheet lifts itself. */}
              <KeyboardAvoidingView
                style={styles.reasonOverlayFill}
                behavior={Platform.OS === 'ios' ? 'padding' : undefined}
              >
                <Pressable
                  style={styles.reasonOverlayBackdrop}
                  onPress={() => dismissReasonOverlay()}
                  accessibilityRole="button"
                  accessibilityLabel="Dismiss the decline reasons"
                />
                <View style={styles.reasonOverlaySheet} testID="trades.pass-reason-overlay">
                  {/* The sheet STAYS UP through layer 1 (review #1): the tile
                      tap banks the pass but defers the deck advance, and the
                      host only fronts the next card from layer 2. Closing here
                      left the card banked and every control inert. Only the two
                      ADVANCING callbacks close. */}
                  <DeclineReasonPanel
                    onLayer1={(r, from) => {
                      reasonBankedRef.current = true;
                      disposition.reasons!.onLayer1(r, from);
                    }}
                    onLayer2Select={(r, d) => {
                      setReasonOverlayOpen(false);
                      disposition.reasons!.onLayer2Select(r, d);
                    }}
                    onLayer2Bank={(r, d) => disposition.reasons!.onLayer2Bank(r, d)}
                    onLayer2Send={(r, d, t) => {
                      setReasonOverlayOpen(false);
                      disposition.reasons!.onLayer2Send(r, d, t);
                    }}
                    onRevealRequest={disposition.reasons!.onRevealRequest}
                  />
                </View>
              </KeyboardAvoidingView>
            </Modal>
          ) : null}
        </>
      ) : null}

      {/* #190 — full-editor path: the manual calculator, prefilled with
          this exact package. Sits at hint-tier prominence below the sides;
          the in-place swap affordances above remain the quick edit. */}
      {variant === 'swipe' && onEditInCalculator ? (
        <Pressable
          testID="trade-card.edit-in-calc"
          accessibilityRole="button"
          accessibilityLabel="Edit this trade in the calculator"
          onPress={onEditInCalculator}
          style={({ pressed }) => [
            styles.editCalcBtn,
            pressed && styles.keepBtnPressed,
          ]}
        >
          <Icon name="trade" size={14} color={chalk.dim} />
          <Text style={styles.editCalcText}>Edit in calculator</Text>
        </Pressable>
      ) : null}

      {hasValueVerdict && !repricing && (
        // n22's spotlight target (see `cardMeterRef` above). The wrapper adds
        // no layout of its own; `collapsable={false}` keeps Android from
        // flattening a styleless View away, which would leave the ref
        // measuring nothing — the same guard `trades.fairness-help` carries.
        // It spans the WHOLE bar including the "Why?" disclosure the beat's
        // copy now names, so the ring frames the control it talks about.
        <View ref={cardMeterRef} collapsable={false} testID="trades.card-meter">
          <TradeValueBar
            giveValue={data.give_value as number}
            receiveValue={data.receive_value as number}
            favors={data.favors ?? null}
            gap={data.gap ?? null}
            youLabel="You"
            themLabel={`@${data.opponent_username}`}
          />
        </View>
      )}

      {/* #357 — lineup movement + playoff-odds shift for THIS trade.
          Mounted here on purpose: D-025 fixed the card's vertical order as
          disposition pair -> TradeValueBar -> "any future card odds block",
          and this is that block. Host-fetched (see useCardImpact) and only
          for the fronted card, so a peek/match/read-only mount passes
          nothing and costs nothing. */}
      {cardImpact ? (
        <CardImpactBlock
          loading={cardImpact.loading}
          evaluation={cardImpact.evaluation}
          failed={cardImpact.failed}
        />
      ) : null}

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

      {/* Mutual-match CTAs: Dismiss (archive, ELO-neutral) + the send column.
          Flag-gated: with trade.send_in_sleeper off the button renders null on
          every platform, so a flag-off build shows Dismiss alone. On a
          non-Sleeper league (audit P0-6) the same slot renders a stated reason
          plus "Copy trade" instead of a send that cannot work. */}
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
              givePlayerNames={data.give_players.map((p) => p.name)}
              receivePlayerNames={data.receive_players.map((p) => p.name)}
              opponentUsername={data.opponent_username}
              leagueName={leagueName}
              surface="match"
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
              givePlayerNames={data.give_players.map((p) => p.name)}
              receivePlayerNames={data.receive_players.map((p) => p.name)}
              opponentUsername={data.opponent_username}
              leagueName={leagueName}
              surface="awaiting"
            />
          </View>
        )
      )}
      {footer ?? null}
    </View>
  );
}

export default React.memo(TradeCardComp);

const styles = StyleSheet.create({
  // #384 ruling 1 — the decline reasons as an overlay over the page. Bottom
  // sheet rather than a centred dialog: the panel's layer 2 opens a text
  // composer, and a keyboard under a centred dialog would cover it.
  reasonOverlayFill: { flex: 1 },
  reasonOverlayBackdrop: { flex: 1, backgroundColor: '#0009' },
  reasonOverlaySheet: {
    maxHeight: '80%',
    padding: space.md,
    backgroundColor: ink.ink2,
    borderTopWidth: 1,
    borderTopColor: ink.line,
  },
  // #276 — vertical-cost audit (typical 2-for-2 must fit an 852pt viewport
  // alongside the pick-valuation line): padding lg→md and the outer stack
  // gap md→sm trim ~28pt across a typical card's ~6 sections without
  // dropping any content. No information removed.
  card: {
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    padding: space.md,
    gap: space.sm,
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
  // F7 wildcard chip: ProvenanceChip's data-encoding chip construction
  // (1px hairline on ink-1, radius xs, flare tick, mono micro-label).
  wildcardChip: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    minHeight: 24,
    paddingHorizontal: space.sm,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: flare.base,
    backgroundColor: ink.ink1,
  },
  wildcardTick: {
    width: 3,
    height: 10,
    backgroundColor: flare.base,
  },
  wildcardLabel: {
    fontFamily: fonts.dataSemi,
    fontSize: 10,
    letterSpacing: 0.5,
    color: chalk.base,
  },
  // #362 sender-side chip: the same construction as the wildcard chip,
  // re-accented ice. Ice because this marks the user's OWN standing
  // commitment (an action state); flare stays reserved for the
  // informational counterparty-side "They're interested" pill.
  standingChip: { borderColor: ice.base },
  standingTick: { backgroundColor: ice.base },
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
  // Counterparty-breaker hesitation line: same hint-tier row construction as
  // fitRow, with the 6px square marker filled in flare — informational
  // highlight only (ADR-005); ice stays reserved for actions. Colors by token
  // reference; check-breaker-card.js bans hex literals here.
  breakerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  breakerDot: {
    width: 6,
    height: 6,
    backgroundColor: flare.base,
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

  // Player-swap (feedback #86) — per-row icon buttons. #226: the slot is
  // in-flow now (PlayerCard reserves its width), and the controls stack
  // VERTICALLY so the slot stays one button wide — the narrow split
  // columns keep room for the name/badges beside up to three controls.
  rightSlotStack: {
    flexDirection: 'column',
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
  // #194 — remove ✕ on the last asset of a side: visibly inert (the tap
  // still lands so the screen can voice the min-one-per-side hint).
  removeBtnDisabled: {
    opacity: 0.35,
  },
  // Untouchable lock twin — marked state borrows the active treatment
  // (ice border) from the queue button's queued state.
  lockBtnMarked: {
    borderColor: ice.base,
  },
  // #186 — per-side keep affordance: compact bordered-chalk button.
  keepBtn: {
    minHeight: 32,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.sm,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: ink.ink1,
  },
  keepBtnPressed: {
    backgroundColor: ink.ink3,
  },
  keepBtnText: {
    ...type.bodySm,
    color: chalk.dim,
  },
  // #169 (FB-05 construction) — check / x disposition button row, inside
  // the card beneath the player tiles. Icon-button construction
  // (components.md → Buttons): square radius, 1px semantic border;
  // pressed = semantic fill + ink icon (color-only state change, no
  // transforms). 56px keeps the touch floor. Row margin trimmed to the
  // card's rhythm (marginTop sm, no bottom margin).
  dispositionRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: space.xl,
    marginTop: space.sm,
  },
  dispositionBtn: {
    width: 56,
    height: 56,
    borderRadius: radii.sm,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'transparent',
  },
  dispositionBtnPass: {
    borderColor: semantic.neg,
  },
  dispositionBtnPassPressed: {
    backgroundColor: semantic.neg,
  },
  dispositionBtnLike: {
    borderColor: semantic.pos,
  },
  dispositionBtnLikePressed: {
    backgroundColor: semantic.pos,
  },
  dispositionDisabled: {
    opacity: 0.45,
  },
  // #190 — edit-in-calculator row: hint-tier inline action.
  editCalcBtn: {
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  editCalcText: {
    ...type.bodySm,
    color: chalk.dim,
  },
  repricingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
});

import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  View,
  type LayoutChangeEvent,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import {
  chalk,
  ice,
  ink,
  radii,
  scrim,
  semantic,
  shadowSheet,
  space,
  type,
} from '../theme/chalkline';
import { posColor } from '../theme/colors';
import { Button, Icon, Text, TickLabel } from './chalkline';
import PositionChip from './PositionChip';
import { TRADE_INTENT_LABEL } from './TradeDnaSheet';
import { useReducedMotionSafe } from '../hooks/useReducedMotionSafe';
import { fetchAssetIdeas, swipeTrade, type AssetIdea } from '../api/trades';
import { track } from '../api/events';
import { haptics } from '../utils/haptics';
import { assetIdeaKey, ideaToCard } from '../utils/ideaToCard';
import { queueCalcTrade, type QueueToast } from '../utils/queueCalcTrade';
import {
  SHOP_MODES,
  SHOP_MODE_GROUP,
  type ShopMode,
} from '../utils/shopMode';
import type { Player, TradeCard } from '../shared/types';

// #402/#403 — the inline shop strip (lld-delta.md §0.3, rulings 2026-08-27).
//
// "Shop a player" IS what the deck's give-side "More offers" button does:
// TradesScreen mounts this strip directly below the top deck card while
// shopping is open (no pushed screen, no route — the deck stays put and its
// like/pass pan is disabled by the host, §0.4). Three mode chips (Tier up /
// Tier down / Same value — R-13 vocabulary, tier labels read from the shipped
// TRADE_INTENT_LABEL so the DNA sheet and this strip can never diverge) select
// one group of the existing `POST /api/trades/asset-ideas` response
// (direction 'give'; W1 sends no `swap_positions`); a `FlatList horizontal
// pagingEnabled` pages the group's idea tiles — deliberately NO `Gesture.Pan`,
// no `PanResponder`, no react-native-gesture-handler import (HLD D-2: the
// pager must never arbitrate with the deck's pan, so it isn't a pan at all).
//
// Decisions per tile:
//   ✓ like    — `queueCalcTrade` → POST /api/trades/queue AS-IS (ruling A:
//               the like moves the Elo board exactly like the calculator's ✓;
//               `record_elo` was ruled out). Refusals render the shipped
//               `queueRefusalLine` copy; `calc_trade_queued` fires with
//               screen 'Trades'. The HOST owns the Toast mount (`onToast`).
//   ✕ dismiss — full deck-pass semantics via POST /api/trades/swipe
//               `decision:'pass'`, but the POST is HELD for UNDO_HOLD_MS and
//               Undo cancels the timer so the request is never sent — the
//               "Dismissed · Undo" copy is true unconditionally (lld §6).
//               At most ONE pending dismiss: a second dismiss, a mode
//               change, a refetch, close or unmount flushes the pending one
//               first — a disposition is never silently lost.
//
// NO FeedbackFAB here: TradesScreen is a tab screen covered by the global
// mount in RootNav (#188); a second FAB is the #196/#197 double-FAB bug.

// Same value as the three shipped precedents (TradesScreen.tsx,
// MatchesScreen.tsx, TradeCalculatorScreen.tsx): how long the dismiss POST
// is held (and the Undo toast shown) before committing.
const UNDO_HOLD_MS = 5000;

/** Toast descriptor the host renders — the strip owns no Toast mount.
 *  Subsumes §0.3's `onQueued` (queue results) plus the dismiss-undo toast. */
export interface ShopToast extends QueueToast {
  holdMs?: number;
  action?: { label: string; onPress: () => void };
}

interface Props {
  leagueId: string;
  /** The shopped give-side asset (player or pick pseudo-asset). */
  asset: Player;
  /** ✕ in the strip header. Close = unmount; the deck never moved, so
   *  nothing restores. */
  onClose: () => void;
  /** Host-owned toast mount (queue outcomes + the Dismissed·Undo toast). */
  onToast: (t: ShopToast) => void;
}

// R-13 — labels: the two tier labels come from the shipped constant; only
// "Same value" is new vocabulary (the DNA sheet has no lateral lane).
const MODE_LABEL: Record<ShopMode, string> = {
  tier_up: TRADE_INTENT_LABEL.tier_up,
  tier_down: TRADE_INTENT_LABEL.tier_down,
  same_value: 'Same value',
};

const MODE_TID: Record<ShopMode, string> = {
  tier_up: 'shop.mode.tier-up',
  tier_down: 'shop.mode.tier-down',
  same_value: 'shop.mode.same-value',
};

// R-15 — honest per-mode empty copy (mockup R2 frames; never a fabricated
// card, never an endless spinner, never blames the user).
const EMPTY_HEAD: Record<ShopMode, string> = {
  tier_up: 'No tier-up offers cleared the bar',
  tier_down: 'No tier-down offers cleared the bar',
  same_value: 'No same-value offers cleared the bar',
};
function emptyBody(mode: ShopMode, name: string): string {
  if (mode === 'tier_up') {
    return `Nobody in this league holds a bigger piece that a package around ${name} can reach under the fairness rules.`;
  }
  if (mode === 'tier_down') {
    return 'Nobody in this league holds a cheaper piece that still makes the trade worth your while under the fairness rules.';
  }
  return `No like-for-like swap for ${name} clears the fairness band right now.`;
}

function sideLabel(players: Player[]): string {
  return players.map((p) => p.name).join(' + ') || '?';
}

// One side of an idea tile — the AssetIdeasPanel row vocabulary (pos dot +
// name), stacked vertically under a TickLabel column header like the deck
// card's own split.
function TileSide({ label, players }: { label: string; players: Player[] }) {
  return (
    <View style={styles.tileSide}>
      <TickLabel>{label}</TickLabel>
      <View style={styles.tileStack}>
        {players.map((p) => (
          <View key={p.id} style={styles.tileRow}>
            <View
              style={[styles.posDot, { backgroundColor: posColor(p.position as any) }]}
            />
            <View style={styles.tileRowText}>
              <Text style={[type.body, styles.tileName]} numberOfLines={1}>
                {p.name}
              </Text>
              <Text style={[type.bodySm, styles.tileMeta]} numberOfLines={1}>
                {[p.position, p.team, p.age != null ? `${p.age} yo` : null]
                  .filter(Boolean)
                  .join(' · ')}
              </Text>
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

export default function ShopOffersStrip({ leagueId, asset, onClose, onToast }: Props) {
  const [mode, setMode] = useState<ShopMode>('tier_up');
  const [index, setIndex] = useState(0);
  // Optimistic local removals (pending + committed dismisses) — keys are
  // `assetIdeaKey`. Cleared on every fresh fetch (committed dismisses are
  // cooldowned server-side and drop out of fresh data on their own).
  const [locallyRemoved, setLocallyRemoved] = useState<Set<string>>(new Set());
  // Per-idea in-flight guard for the ✓ — disables the pair while queueing.
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [pagerW, setPagerW] = useState(0);
  const listRef = useRef<FlatList<AssetIdea>>(null);

  const ideasQuery = useQuery({
    // Same query/key pattern as TradesScreen's `assetIdeasQuery`; distinct
    // key ('shop-ideas') so shopping never evicts the single-pin panel's
    // cache entry.
    queryKey: ['shop-ideas', leagueId, asset.id],
    queryFn: () =>
      fetchAssetIdeas({
        league_id: leagueId,
        asset_id: asset.id,
        direction: 'give',
      }),
    staleTime: 60_000,
  });
  const groups = ideasQuery.data?.groups;

  // The pager's list AND the `1 / X` counter AND the chip counts all derive
  // from this one shape — locally dismissed tiles excluded everywhere, so
  // the counter cannot lie (R-5) and an emptied chip count is honest.
  const visibleByMode = useMemo(() => {
    const out = {} as Record<ShopMode, AssetIdea[]>;
    for (const m of SHOP_MODES) {
      out[m] = (groups?.[SHOP_MODE_GROUP[m]] ?? []).filter(
        (i) => !locallyRemoved.has(assetIdeaKey(i)),
      );
    }
    return out;
  }, [groups, locallyRemoved]);
  const visibleIdeas = visibleByMode[mode];

  // ── Dismiss: held POST + true undo (lld-delta.md §6, host renamed) ────
  const pendingDismissRef = useRef<{
    idea: AssetIdea;
    key: string;
    restoreIndex: number;
    timer: ReturnType<typeof setTimeout>;
  } | null>(null);

  function commitDismiss(idea: AssetIdea) {
    // The real POST — full deck-pass semantics (Elo at trade_k_pass + the
    // D-067 dismiss-cooldown), reconstructed server-side from the echoed
    // context under the deterministic `asset-idea:<key>` id `ideaToCard`
    // mints (FB-46). Failure after the window closed: refetch so the card
    // reappears rather than staying invisibly un-dismissed (the S-9
    // honesty rule MatchesScreen states for the same shape).
    swipeTrade(ideaToCard(idea, leagueId), 'pass').catch(() => {
      setLocallyRemoved((s) => {
        const n = new Set(s);
        n.delete(assetIdeaKey(idea));
        return n;
      });
      ideasQuery.refetch();
    });
  }

  function flushPendingDismiss() {
    const p = pendingDismissRef.current;
    if (!p) return;
    pendingDismissRef.current = null;
    clearTimeout(p.timer);
    commitDismiss(p.idea);
  }
  // Latest-instance ref (the TradesScreen `pendingPassRef` convention) so
  // the unmount flush never closes over a stale query/state instance.
  const flushPendingDismissRef = useRef(flushPendingDismiss);
  flushPendingDismissRef.current = flushPendingDismiss;

  function undoDismiss() {
    const p = pendingDismissRef.current;
    if (!p) return;
    pendingDismissRef.current = null;
    // The ENTIRE undo — the POST never fired, so nothing needs reversing
    // and the toast copy needs no caveat.
    clearTimeout(p.timer);
    setLocallyRemoved((s) => {
      const n = new Set(s);
      n.delete(p.key);
      return n;
    });
    jumpToIndex(p.restoreIndex);
    track('shop_dismiss_undone', { mode }, 'Trades');
  }

  function handleDismiss(idea: AssetIdea) {
    haptics.selection();
    const key = assetIdeaKey(idea);
    if (pendingDismissRef.current?.key === key) return; // double-fire guard
    flushPendingDismiss(); // at-most-one pending
    const restoreIndex = index;
    // Optimistic removal — the tile leaves the pager at once and X
    // decrements; the counter reads the same filtered list (R-5).
    setLocallyRemoved((s) => new Set(s).add(key));
    jumpToIndex(Math.min(index, Math.max(0, visibleIdeas.length - 2)));
    pendingDismissRef.current = {
      idea,
      key,
      restoreIndex,
      // Timer armed BEFORE any network call — Undo cancels it and the
      // request is never sent (R-9).
      timer: setTimeout(() => flushPendingDismissRef.current(), UNDO_HOLD_MS),
    };
    onToast({
      msg: 'Dismissed',
      tone: 'success',
      holdMs: UNDO_HOLD_MS,
      action: { label: 'Undo', onPress: undoDismiss },
    });
  }

  // Close/unmount flushes — leaving the strip ends the undo window; the
  // disposition must not be silently lost (lld §6.1).
  useEffect(() => () => flushPendingDismissRef.current(), []);

  // A fresh payload invalidates old idea references: flush any pending
  // dismiss first, then reset the local removals and rewind the pager.
  const ideasUpdatedAt = ideasQuery.dataUpdatedAt;
  useEffect(() => {
    flushPendingDismissRef.current();
    setLocallyRemoved(new Set());
    jumpToIndexRef.current(0);
  }, [ideasUpdatedAt]);

  // ── Like: the calculator's ✓, verbatim (ruling A) ─────────────────────
  async function handleLike(idea: AssetIdea) {
    const key = assetIdeaKey(idea);
    if (busyKey) return;
    setBusyKey(key);
    try {
      const res = await queueCalcTrade({
        leagueId,
        opponent: {
          userId: idea.counterparty_user_id,
          name: idea.counterparty_username,
        },
        giveIds: idea.give_player_ids,
        receiveIds: idea.receive_player_ids,
        screen: 'Trades',
      });
      onToast(res.toast);
    } finally {
      setBusyKey(null);
    }
  }

  // ── Pager mechanics ───────────────────────────────────────────────────
  function jumpToIndex(i: number) {
    setIndex(i);
    if (pagerW > 0) {
      listRef.current?.scrollToOffset({ offset: i * pagerW, animated: false });
    }
  }
  const jumpToIndexRef = useRef(jumpToIndex);
  jumpToIndexRef.current = jumpToIndex;

  function handleSelectMode(m: ShopMode) {
    if (m === mode) return;
    haptics.selection();
    flushPendingDismiss(); // mode change flushes the pending dismiss (R-9)
    setMode(m);
    jumpToIndex(0);
    track('shop_mode_selected', { mode: m, n_ideas: visibleByMode[m].length }, 'Trades');
  }

  const shown = Math.min(index + 1, visibleIdeas.length);

  return (
    <View style={styles.strip} testID="shop.strip">
      {/* Header: "Shopping {asset}" + close ✕ */}
      <View style={styles.header}>
        <View style={styles.headerTitle}>
          <TickLabel>{`Shopping ${asset.name}`}</TickLabel>
        </View>
        <Pressable
          testID="shop.close-btn"
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Close shop"
          hitSlop={8}
          style={({ pressed }) => [styles.closeBtn, pressed && styles.closeBtnPressed]}
        >
          <Icon name="x" size={14} color={chalk.dim} />
        </Pressable>
      </View>

      {/* Mode chips — single-select, ice = the active (actionable) one;
          per-mode counts keep an empty mode navigable, not a dead end. */}
      <View style={styles.modes}>
        {SHOP_MODES.map((m) => {
          const active = m === mode;
          return (
            <Pressable
              key={m}
              testID={MODE_TID[m]}
              onPress={() => handleSelectMode(m)}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              accessibilityLabel={`${MODE_LABEL[m]}, ${visibleByMode[m].length} offers`}
              style={({ pressed }) => [
                styles.modeChip,
                active && styles.modeChipActive,
                pressed && !active && styles.modeChipPressed,
              ]}
            >
              <Text
                scale="dense"
                style={[styles.modeChipText, active && styles.modeChipTextActive]}
              >
                {MODE_LABEL[m]}
              </Text>
              <Text scale="dense" style={styles.modeChipCount}>
                {`· ${visibleByMode[m].length}`}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {ideasQuery.isLoading ? (
        <View style={styles.loadingRow}>
          <ActivityIndicator color={chalk.dim} size="small" />
          <Text style={type.bodySm}>Sweeping rosters…</Text>
        </View>
      ) : ideasQuery.isError ? (
        <View style={styles.empty} testID="shop.error">
          <Text style={[type.body, styles.emptyHead]}>
            Couldn't sweep the league
          </Text>
          <Button
            label="Try again"
            variant="ghost"
            compact
            onPress={() => ideasQuery.refetch()}
          />
        </View>
      ) : visibleIdeas.length === 0 ? (
        // R-15 — honest empty, named per mode; the second line renders only
        // when it is TRUE (another mode actually has offers).
        <View style={styles.empty} testID="shop.empty">
          <Text style={[type.body, styles.emptyHead]}>{EMPTY_HEAD[mode]}</Text>
          <Text style={[type.bodySm, styles.emptyBody]}>
            {emptyBody(mode, asset.name)}
          </Text>
          {SHOP_MODES.some((m) => m !== mode && visibleByMode[m].length > 0) ? (
            <Text style={[type.bodySm, styles.emptyHint]}>
              The other modes have offers — the counts on the chips are live.
            </Text>
          ) : null}
        </View>
      ) : (
        <>
          {/* R-5 — `1 / X` from the SAME array the pager renders. Chalk-dim
              label, never flare (informational, but the counter sits inside
              an actionable surface — Ice/Flare division of labor). */}
          <View style={styles.counterRow} testID="shop.counter">
            <Text scale="dense" style={styles.counterText}>
              {`${shown} / ${visibleIdeas.length}`}
            </Text>
          </View>
          <View
            onLayout={(e: LayoutChangeEvent) => setPagerW(e.nativeEvent.layout.width)}
            style={styles.pagerWrap}
          >
            <FlatList
              ref={listRef}
              testID="shop.pager"
              data={visibleIdeas}
              horizontal
              pagingEnabled
              showsHorizontalScrollIndicator={false}
              keyExtractor={(i) => assetIdeaKey(i)}
              getItemLayout={(_d, i) => ({
                length: pagerW,
                offset: pagerW * i,
                index: i,
              })}
              onMomentumScrollEnd={(e) => {
                if (pagerW > 0) {
                  setIndex(Math.round(e.nativeEvent.contentOffset.x / pagerW));
                }
              }}
              renderItem={({ item }) => {
                const key = assetIdeaKey(item);
                const busy = busyKey === key;
                const gain = item.difference >= 0;
                return (
                  <View style={[styles.tile, { width: pagerW || 1 }]} testID={`shop.card.${key}`}>
                    <View style={styles.tileSplit}>
                      <TileSide label="You send" players={item.give} />
                      <View style={styles.vrule} />
                      <TileSide label="You get" players={item.receive} />
                    </View>
                    {/* Counterparty + signed diff chip — the AssetIdeasPanel
                        meta-line vocabulary. */}
                    <View style={styles.cpLine}>
                      <Text style={[type.bodySm, styles.cpName]} numberOfLines={1}>
                        {`with @${item.counterparty_username}`}
                      </Text>
                      <View
                        style={[
                          styles.diffChip,
                          gain ? styles.diffChipPos : styles.diffChipNeg,
                        ]}
                      >
                        <Text
                          scale="dense"
                          style={[
                            type.data,
                            styles.diffText,
                            { color: gain ? semantic.pos : semantic.neg },
                          ]}
                        >
                          {gain ? '+' : ''}
                          {Math.round(item.difference)}
                        </Text>
                      </View>
                    </View>
                    <View style={styles.decideRow}>
                      <Pressable
                        testID="shop.dismiss-btn"
                        onPress={() => handleDismiss(item)}
                        disabled={busy}
                        accessibilityRole="button"
                        accessibilityLabel="Dismiss this offer"
                        style={({ pressed }) => [
                          styles.dismissBtn,
                          pressed && styles.dismissBtnPressed,
                          busy && styles.btnDisabled,
                        ]}
                      >
                        <Icon name="x" size={16} color={chalk.dim} />
                      </Pressable>
                      <View style={styles.likeWrap}>
                        <Button
                          testID="shop.like-btn"
                          label="Send this offer"
                          icon="check"
                          variant="primary"
                          compact
                          loading={busy}
                          onPress={() => handleLike(item)}
                        />
                      </View>
                    </View>
                    {visibleIdeas.length > 1 ? (
                      <Text style={[type.bodySm, styles.pageHint]}>
                        Swipe for the next offer
                      </Text>
                    ) : null}
                  </View>
                );
              }}
            />
          </View>
        </>
      )}
    </View>
  );
}

// ── "Shop which player?" chooser (lld-delta.md §0.2) ─────────────────────
// Give side > 1: a modal bottom sheet — the PlayerContextMenu construction,
// NEVER navigation (the deck stays mounted underneath). Pick a row → the
// host opens the strip for that asset (and re-emits `shop_opened` with the
// picked position); Cancel → nothing. No FeedbackFAB (modal exception).
export function ShopWhichPlayerSheet({
  visible,
  card,
  onPick,
  onClose,
}: {
  visible: boolean;
  card: TradeCard | null;
  onPick: (asset: Player) => void;
  onClose: () => void;
}) {
  // Slide falls back to fade under Reduce Motion — the PlayerContextMenu
  // construction, verbatim.
  const reduceMotion = useReducedMotionSafe();
  return (
    <Modal
      visible={visible}
      transparent
      animationType={reduceMotion ? 'fade' : 'slide'}
      onRequestClose={onClose}
    >
      <Pressable
        style={styles.backdrop}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <View style={styles.sheet} testID="shop.chooser">
        <SafeAreaView edges={['bottom']}>
          <View style={styles.grabber} />
          <View style={styles.sheetHeader}>
            <Text style={type.title}>Shop which player?</Text>
            <Text style={type.bodySm}>
              Offers are built around one player at a time
            </Text>
          </View>
          {(card?.give_players ?? []).map((p) => (
            <Pressable
              key={p.id}
              testID={`shop.chooser.${p.id}`}
              accessibilityRole="button"
              accessibilityLabel={`Shop ${p.name}`}
              onPress={() => onPick(p)}
              style={({ pressed }) => [styles.sheetRow, pressed && styles.sheetRowPressed]}
            >
              <PositionChip position={p.position} size="sm" />
              <View style={styles.sheetRowText}>
                <Text style={type.body} numberOfLines={1}>
                  {p.name}
                </Text>
                <Text style={[type.bodySm, styles.sheetRowMeta]} numberOfLines={1}>
                  {[p.team || null, p.age != null ? `${p.age} yo` : null]
                    .filter(Boolean)
                    .join(' · ') || ' '}
                </Text>
              </View>
            </Pressable>
          ))}
          <Button variant="ghost" label="Cancel" onPress={onClose} style={styles.cancel} />
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  // The strip — a card-like well directly below the deck card (mockup R2·2).
  strip: {
    marginTop: space.sm,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    backgroundColor: ink.ink1,
    padding: space.md,
    gap: space.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  headerTitle: { flex: 1, minWidth: 0 },
  closeBtn: {
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.line,
  },
  closeBtnPressed: { backgroundColor: ink.ink3 },
  modes: {
    flexDirection: 'row',
    gap: space.xs,
  },
  // Subnav-pill construction (components.md § Navigation): hairline chip,
  // radius xs; active = ice border + raised well + chalk text.
  modeChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: space.sm,
    paddingVertical: 6,
    borderRadius: radii.xs,
    borderWidth: 1,
    borderColor: ink.line,
  },
  modeChipActive: {
    borderColor: ice.base,
    backgroundColor: ink.ink2,
  },
  modeChipPressed: { backgroundColor: ink.ink3 },
  modeChipText: { ...type.label, color: chalk.dim },
  modeChipTextActive: { color: chalk.base },
  modeChipCount: { ...type.label, color: chalk.faint },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.md,
  },
  empty: {
    paddingVertical: space.md,
    gap: space.xs,
  },
  emptyHead: { color: chalk.base },
  emptyBody: { color: chalk.dim },
  emptyHint: { color: chalk.faint },
  counterRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
  },
  // Chalk-dim label — NOT flare (design-system.md § Ice/Flare).
  counterText: { ...type.label, color: chalk.dim },
  pagerWrap: { marginHorizontal: -space.md },
  tile: {
    paddingHorizontal: space.md,
    gap: space.sm,
  },
  tileSplit: {
    flexDirection: 'row',
    gap: space.md,
  },
  tileSide: { flex: 1, minWidth: 0, gap: space.xs },
  tileStack: { gap: space.xs },
  tileRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
  },
  tileRowText: { flex: 1, minWidth: 0 },
  tileName: { color: chalk.base },
  tileMeta: { color: chalk.dim },
  posDot: { width: 6, height: 6, borderRadius: 3 },
  vrule: { width: 1, backgroundColor: ink.line },
  cpLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  cpName: { color: chalk.dim, flex: 1 },
  diffChip: {
    paddingHorizontal: space.sm,
    paddingVertical: 2,
    borderRadius: radii.xs,
    borderWidth: 1,
  },
  diffChipPos: { borderColor: 'rgba(34,197,94,0.4)' },
  diffChipNeg: { borderColor: 'rgba(239,68,68,0.4)' },
  diffText: { fontSize: 12, lineHeight: 16 },
  decideRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  dismissBtn: {
    width: 72,
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
  },
  dismissBtnPressed: { backgroundColor: ink.ink3 },
  btnDisabled: { opacity: 0.5 },
  likeWrap: { flex: 1 },
  pageHint: {
    color: chalk.faint,
    textAlign: 'center',
  },
  // Chooser sheet — the PlayerContextMenu construction, verbatim tokens.
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    paddingHorizontal: space.lg,
    paddingBottom: space.md,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
    marginBottom: space.sm,
  },
  sheetHeader: {
    gap: 2,
    paddingVertical: space.sm,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    marginBottom: space.xs,
  },
  sheetRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 48,
    paddingVertical: space.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  sheetRowPressed: { backgroundColor: ink.ink3 },
  sheetRowText: { flex: 1, minWidth: 0, gap: 2 },
  sheetRowMeta: { color: chalk.dim },
  cancel: { marginTop: space.sm },
});

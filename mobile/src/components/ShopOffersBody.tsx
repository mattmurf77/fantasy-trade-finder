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
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  chalk,
  fonts,
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
import { useFlag } from '../state/useFeatureFlags';
import { getLeaguePreferences } from '../api/league';
import {
  fetchAssetIdeas,
  swipeTrade,
  type AssetIdea,
  type AssetIdeasResponse,
} from '../api/trades';
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
// (direction 'give'; W2 adds the position multi-select inside the Same-value
// pane, sent as `swap_positions` and OMITTED when nothing is selected); a
// `FlatList horizontal pagingEnabled` pages the tiles — deliberately NO `Gesture.Pan`,
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
//               first — a disposition is never silently lost. An EARLY
//               flush (anything but the natural expiry / the Undo itself)
//               also retracts the "Dismissed · Undo" toast if it is still
//               on screen (QA B-4): a dead Undo button is never shown.
//
// NO FeedbackFAB here: TradesScreen is a tab screen covered by the global
// mount in RootNav (#188); a second FAB is the #196/#197 double-FAB bug.

// Same value as the three shipped precedents (TradesScreen.tsx,
// MatchesScreen.tsx, TradeCalculatorScreen.tsx): how long the dismiss POST
// is held (and the Undo toast shown) before committing.
const UNDO_HOLD_MS = 5000;

// W2 — the swap-position chip domain: exactly the server's VALID_POSITIONS
// (R-12). "PICK" is deliberately absent — the server 400s it (the lateral
// predicate reads raw `position`, which generic pick rungs fake; see the
// route comment at server.py:12095). The pin's OWN position IS offered as a
// chip like any other (ruling R-2026-08-28-B, lld-delta.md §3.4 row 4):
// "WR laterals plus RB laterals" must be expressible. Empty selection keeps
// its meaning — same-position swaps, field omitted — and selecting ONLY the
// own position sends swap_positions:[own], server-equivalent to the default
// (consistent on purpose, not a special case).
const SWAP_POSITIONS = ['QB', 'RB', 'WR', 'TE'] as const;
type SwapPos = (typeof SWAP_POSITIONS)[number];

// How long a chip tap sits before the selection settles into a fetch — the
// shipped calculator convention (TradeCalculatorScreen / InLeagueCalculator
// both debounce their evaluate keys 250ms; each keeps a local copy of this
// helper, neither exports it).
const SWAP_SETTLE_MS = 250;
function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** "RB", "RB and TE", "QB, RB and TE" — copy-grade position lists. */
function humanList(ps: readonly string[], conj: 'and' | 'or'): string {
  if (ps.length <= 1) return ps[0] ?? '';
  return `${ps.slice(0, -1).join(', ')} ${conj} ${ps[ps.length - 1]}`;
}

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
  /** QA B-4 — retract ONE toast this strip issued, IF it is still the one
   *  on screen. The host compares by reference (`cur === t`) so a newer
   *  toast that already replaced it is never clobbered. Called only when a
   *  held dismiss commits EARLY (mode chip, position toggle, clear, fresh
   *  payload, close/unmount) while its Undo toast may still be showing. */
  onToastRetract: (t: ShopToast) => void;
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

// W2 — one swap-position chip. The DnaToggle construction from TradeDnaSheet
// (the app's SHIPPED selected-position-chip pattern — Chasing/Shopping/
// Avoiding rows): selected = solid position-color fill + check glyph + bold
// on-ice text; unselected = hairline chip with the position-color dot. NOT
// the mockup's ink-well + ice-ring — on component construction the app wins
// over the mockup's CSS, and the position hex stays a pure data encoding
// (docs/cross-client-invariants.md) on fill/dot in both states.
function SwapPosChip({
  pos,
  selected,
  onPress,
}: {
  pos: SwapPos;
  selected: boolean;
  onPress: () => void;
}) {
  const color = posColor(pos as any) ?? ink.lineStrong;
  return (
    <Pressable
      testID={`shop.pos.${pos}`}
      accessibilityRole="checkbox"
      accessibilityState={{ checked: selected }}
      accessibilityLabel={`Offer ${pos} back`}
      onPress={onPress}
      style={({ pressed }) => [
        styles.posChip,
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
        <View style={[styles.posChipDot, { backgroundColor: color }]} />
      )}
      <Text style={[styles.posChipText, selected && styles.posChipTextSel]}>
        {pos}
      </Text>
    </Pressable>
  );
}

export default function ShopOffersStrip({
  leagueId,
  asset,
  onClose,
  onToast,
  onToastRetract,
}: Props) {
  const [mode, setMode] = useState<ShopMode>('tier_up');
  const [index, setIndex] = useState(0);
  // PENDING local removals only — keys are `assetIdeaKey` for a held
  // dismiss whose tile has already left the pager. An entry either returns
  // via Undo or is promoted into `suppressed` the moment the held POST
  // commits; nothing else adds or clears here.
  const [locallyRemoved, setLocallyRemoved] = useState<Set<string>>(new Set());
  // Fix A (rulings 2026-08-28 R-A — B-3 + P-2, ONE mechanism).
  // UNIVERSAL RULE: a COMMITTED dismissal is client-authoritative for the
  // strip session. Keys enter this set only when a held dismiss COMMITS
  // (never while merely pending — that's `locallyRemoved` above), and
  // NOTHING clears it: not dataUpdatedAt, not a warm cache row on a
  // selection switch, not a racing refetch, not a fresh payload. It dies
  // only with the strip instance — close/unmount, including the host's
  // `key={asset.id}` remount (a new shop session starts clean; the server
  // dismiss-cooldown is authoritative across sessions). An UNDONE dismiss
  // never enters: Undo nulls `pendingDismissRef` and cancels the timer
  // before any flush path can reach `commitDismiss`, so the key never
  // leaves `locallyRemoved` for here. The one subtraction is the
  // commit-failure path in `commitDismiss`, where the server never
  // recorded the pass and honesty requires the tile back.
  const [suppressed, setSuppressed] = useState<Set<string>>(new Set());
  // Per-idea in-flight guard for the ✓ — disables the pair while queueing.
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [pagerW, setPagerW] = useState(0);
  const listRef = useRef<FlatList<AssetIdea>>(null);
  const queryClient = useQueryClient();

  // ── W2: the Same-value position multi-select (R-10/R-11/R-12) ─────────
  // Multi-select posture on purpose: spike S-2 measured single-position
  // selections empty 30–60% of the time, but 89–97% of pins find a lateral
  // at SOME other position — the chips are checkboxes, not radios.
  const [positions, setPositions] = useState<Set<SwapPos>>(new Set());
  // The settled selection key: sorted so {RB,TE} and {TE,RB} share a cache
  // row, debounced so a chip flurry coalesces into ONE fetch. A picker
  // change refetches; a mode change does NOT (all three groups arrive in
  // one response — the rev-1 `swapKey` spec, lld-delta.md §4.3).
  const swapKey = useMemo(() => [...positions].sort().join('+'), [positions]);
  const debouncedSwapKey = useDebounced(swapKey, SWAP_SETTLE_MS);

  // #360 — a position the user is AVOIDING is never offered as a chip
  // (lld-delta.md §3.5 client rule; the server enforces the same outcome
  // at pool construction either way). Same query key as TradesScreen's
  // prefsQuery, so this reads the warm cache and adds no request; the flag
  // is dark today (`trade.avoid_positions` false), making this latent.
  const avoidOn = useFlag('trade.avoid_positions');
  const prefsQuery = useQuery({
    queryKey: ['league-prefs', leagueId],
    queryFn: () => getLeaguePreferences(leagueId),
    staleTime: 5 * 60_000,
    enabled: avoidOn,
  });
  const avoided = useMemo(
    () =>
      new Set(
        (avoidOn ? prefsQuery.data?.avoid_positions ?? [] : []).map((p) =>
          String(p).toUpperCase(),
        ),
      ),
    [avoidOn, prefsQuery.data],
  );
  const pinPos = String(asset.position || '').toUpperCase();
  // A pick pseudo-asset pin runs pure value bands server-side and IGNORES
  // swap_positions (spike S-2 — pick pins already return cross-position
  // laterals), so the picker renders only for a real-position pin: dead
  // chips that change nothing would be worse than no chips.
  const pickerApplies = (SWAP_POSITIONS as readonly string[]).includes(pinPos);
  // Ruling R-2026-08-28-B ("Offer it"): the pin's own position is in the
  // row like any other — only the #360 avoided-position omission applies,
  // and it applies to the own position exactly like the rest.
  const offeredPositions = SWAP_POSITIONS.filter((p) => !avoided.has(p));
  // Mockup D7 — a silently shortened row and a bug look identical, so an
  // avoid-omitted chip gets one chalk-faint line of explanation.
  const avoidOmitted = SWAP_POSITIONS.filter((p) => avoided.has(p));

  const ideasQuery = useQuery({
    // Same query/key pattern as TradesScreen's `assetIdeasQuery`; distinct
    // key ('shop-ideas') so shopping never evicts the single-pin panel's
    // cache entry. The settled swap key is the fourth element ('' = no
    // selection), so every selection owns its own cache row.
    queryKey: ['shop-ideas', leagueId, asset.id, debouncedSwapKey],
    queryFn: () =>
      fetchAssetIdeas({
        league_id: leagueId,
        asset_id: asset.id,
        direction: 'give',
        // W2 (lld-delta.md §2.4) — the key is OMITTED, never sent as
        // undefined/[], when nothing is selected: the no-selection request
        // stays byte-identical to W1 (and to the flag-off state) over the
        // wire. One or more chips ⇒ the settled tokens go up verbatim.
        ...(debouncedSwapKey
          ? { swap_positions: debouncedSwapKey.split('+') }
          : {}),
      }),
    staleTime: 60_000,
  });
  const groups = ideasQuery.data?.groups;

  // Settled selection as a list, for copy that must describe the DATA on
  // screen (the fetched payload), not a chip tapped 100ms ago.
  const settledSelection = useMemo(
    () => (debouncedSwapKey ? debouncedSwapKey.split('+') : []),
    [debouncedSwapKey],
  );

  // Last-known unfiltered-SELECTION lateral count, read straight from the
  // empty-selection cache row (the strip opens with no selection, so it is
  // nearly always warm). Powers the honest count on the Clear-positions
  // escape (mockup D10 — the RankImportSheet "Apply N ranks" pattern); when
  // the row is cold the label simply drops the count, never invents one.
  // Fix A rider: the count runs through the SAME pending-removal +
  // suppression filter as the pager, so the "Clear positions — N at X"
  // label never counts a just-dismissed tile (QA reviewer nit).
  const baselineLateralCount = (
    queryClient.getQueryData<AssetIdeasResponse>([
      'shop-ideas',
      leagueId,
      asset.id,
      '',
    ])?.groups.lateral ?? []
  ).filter((i) => {
    const k = assetIdeaKey(i);
    return !locallyRemoved.has(k) && !suppressed.has(k);
  }).length;

  // The pager's list AND the `1 / X` counter AND the chip counts all derive
  // from this one shape — pending removals AND session-suppressed commits
  // excluded everywhere (Fix A), so the counter cannot lie (R-5), an
  // emptied chip count is honest, and no cache row or refetch ordering can
  // resurrect a committed dismiss anywhere counts, pager, or labels look.
  const visibleByMode = useMemo(() => {
    const out = {} as Record<ShopMode, AssetIdea[]>;
    for (const m of SHOP_MODES) {
      out[m] = (groups?.[SHOP_MODE_GROUP[m]] ?? []).filter((i) => {
        const k = assetIdeaKey(i);
        return !locallyRemoved.has(k) && !suppressed.has(k);
      });
    }
    return out;
  }, [groups, locallyRemoved, suppressed]);
  const visibleIdeas = visibleByMode[mode];

  // ── Dismiss: held POST + true undo (lld-delta.md §6, host renamed) ────
  const pendingDismissRef = useRef<{
    idea: AssetIdea;
    key: string;
    restoreIndex: number;
    timer: ReturnType<typeof setTimeout>;
  } | null>(null);
  // QA B-4 — the exact "Dismissed · Undo" descriptor the host is (as far as
  // this strip knows) currently showing for the pending dismiss. Kept so an
  // early flush can retract it BY REFERENCE; nulled the moment the pending
  // dismiss resolves any way at all (undo, expiry, early flush).
  const undoToastRef = useRef<ShopToast | null>(null);

  function commitDismiss(idea: AssetIdea) {
    const key = assetIdeaKey(idea);
    // Fix A — the commit is the ONE gate into the suppression set: from
    // here the dismissal is client-authoritative for the strip session
    // (B-3/P-2), and the pending entry is dropped in the same breath so
    // the two sets stay disjoint (pending vs committed).
    setSuppressed((s) => new Set(s).add(key));
    setLocallyRemoved((s) => {
      const n = new Set(s);
      n.delete(key);
      return n;
    });
    // The real POST — full deck-pass semantics (Elo at trade_k_pass + the
    // D-067 dismiss-cooldown), reconstructed server-side from the echoed
    // context under the deterministic `asset-idea:<key>` id `ideaToCard`
    // mints (FB-46). Failure after the window closed: un-suppress and
    // refetch so the card reappears rather than staying invisibly
    // un-dismissed (the S-9 honesty rule MatchesScreen states for the
    // same shape) — the one legal subtraction from the suppression set.
    swipeTrade(ideaToCard(idea, leagueId), 'pass').catch(() => {
      setSuppressed((s) => {
        const n = new Set(s);
        n.delete(key);
        return n;
      });
      ideasQuery.refetch();
    });
  }

  function flushPendingDismiss(opts?: { expired?: boolean }) {
    const p = pendingDismissRef.current;
    if (!p) return;
    pendingDismissRef.current = null;
    clearTimeout(p.timer);
    // QA B-4 — every flush except the natural UNDO_HOLD_MS expiry is an
    // EARLY commit: the "Dismissed · Undo" toast may still be on screen
    // with a now-dead Undo button, so it is retracted at the moment the
    // affordance dies. Retraction is by reference (the host no-ops when a
    // NEWER toast already holds the slot — e.g. a ✓ queue success), which
    // pins the shipped semantic: the commit follows the DISAPPEARANCE of
    // the Undo affordance. If a later toast replaced it, the affordance is
    // already gone and the pending dismiss simply keeps its timer until a
    // flush path (or the expiry) commits it — the harm B-4 names was the
    // dead button on screen, never the replacement itself.
    if (!opts?.expired && undoToastRef.current) {
      onToastRetract(undoToastRef.current);
    }
    undoToastRef.current = null;
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
    // and the toast copy needs no caveat. The toast dismisses itself after
    // the action press (Toast.tsx), so no retraction here — just drop the
    // reference so a later flush can't retract a toast that already left.
    undoToastRef.current = null;
    clearTimeout(p.timer);
    // P-1 — restore the DATA first, then let the reactive scroll effect
    // move the pager once the list actually contains the restored tile
    // (see the universal rule at requestPagerScroll). Calling the scroll
    // here directly raced the FlatList's data growth and could clamp on a
    // last-tile undo.
    requestPagerScroll(p.restoreIndex);
    setLocallyRemoved((s) => {
      const n = new Set(s);
      n.delete(p.key);
      return n;
    });
    track('shop_dismiss_undone', { mode }, 'Trades');
  }

  function handleDismiss(idea: AssetIdea) {
    haptics.selection();
    const key = assetIdeaKey(idea);
    if (pendingDismissRef.current?.key === key) return; // double-fire guard
    flushPendingDismiss(); // at-most-one pending
    const restoreIndex = index;
    // Optimistic removal — the tile leaves the pager at once and X
    // decrements; the counter reads the same filtered list (R-5). The
    // pager holds its index against the SHRUNK list: the request below is
    // clamped by the reactive scroll effect after the data change lands
    // (P-1 — never race the FlatList).
    requestPagerScroll(index);
    setLocallyRemoved((s) => new Set(s).add(key));
    pendingDismissRef.current = {
      idea,
      key,
      restoreIndex,
      // Timer armed BEFORE any network call — Undo cancels it and the
      // request is never sent (R-9). The natural expiry is the ONE flush
      // that must not retract the toast: it dismisses itself at the same
      // holdMs, and yanking it a frame early would flicker (QA B-4).
      timer: setTimeout(
        () => flushPendingDismissRef.current({ expired: true }),
        UNDO_HOLD_MS,
      ),
    };
    const undoToast: ShopToast = {
      msg: 'Dismissed',
      tone: 'success',
      holdMs: UNDO_HOLD_MS,
      action: { label: 'Undo', onPress: undoDismiss },
    };
    undoToastRef.current = undoToast;
    onToast(undoToast);
  }

  // Close/unmount flushes — leaving the strip ends the undo window; the
  // disposition must not be silently lost (lld §6.1).
  useEffect(() => () => flushPendingDismissRef.current(), []);

  // A fresh payload invalidates old idea references: flush any pending
  // dismiss first (R-9), then rewind the pager — via the reactive scroll
  // request, never a direct scroll (P-1). What this effect deliberately
  // does NOT do any more (Fix A): reset the removal/suppression sets. A
  // committed dismissal is client-authoritative for the strip session, so
  // a dataUpdatedAt tick — warm cache row, racing refetch, fresh payload —
  // must never resurrect it; only Undo (pending) or the commit-failure
  // path restores a tile.
  const ideasUpdatedAt = ideasQuery.dataUpdatedAt;
  useEffect(() => {
    flushPendingDismissRef.current();
    requestPagerScroll(0);
  }, [ideasUpdatedAt]);

  // W2 — `shop_positions_selected` fires when a selection change SETTLES
  // into a fetch (the debounced key committing is exactly that moment; a
  // 4-tap flurry emits once). COUNT ONLY, never the set — the taxonomy's
  // closed prop set is {n}; the selected positions are user preference
  // data (lld-delta.md §8). The initial '' key matches the ref's initial
  // value, so nothing fires on mount; clearing back to '' fires n: 0.
  const lastTrackedSwapKeyRef = useRef('');
  useEffect(() => {
    if (debouncedSwapKey === lastTrackedSwapKeyRef.current) return;
    lastTrackedSwapKeyRef.current = debouncedSwapKey;
    const n = debouncedSwapKey ? debouncedSwapKey.split('+').length : 0;
    track('shop_positions_selected', { n }, 'Trades');
  }, [debouncedSwapKey]);

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
  // P-1 UNIVERSAL RULE (rulings 2026-08-28 R-C): the pager position
  // derives from the rendered data — scrolls REACT to data changes, they
  // never race them. Nothing in the strip calls scrollToOffset at event
  // time; every mover (dismiss advance, last-tile undo restore, mode-
  // change rewind, fresh-payload rewind) REQUESTS a target index here and
  // makes its data/state change, and the single effect below performs the
  // scroll on the render whose FlatList already holds the new content,
  // clamped to what is actually on screen — so the pager, the counter,
  // and the data can never disagree.
  const pendingScrollRef = useRef<number | null>(null);
  function requestPagerScroll(i: number) {
    pendingScrollRef.current = i;
  }
  useEffect(() => {
    const want = pendingScrollRef.current;
    if (want == null) return;
    pendingScrollRef.current = null;
    const clamped = Math.min(want, Math.max(0, visibleIdeas.length - 1));
    setIndex(clamped);
    if (pagerW > 0) {
      listRef.current?.scrollToOffset({
        offset: clamped * pagerW,
        animated: false,
      });
    }
    // ideasUpdatedAt is a dep on purpose: react-query's structural sharing
    // can keep visibleIdeas reference-stable across an identical refetch,
    // and a rewind requested for that payload must still be consumed here
    // rather than fire as a stale jump on some later data change.
  }, [visibleIdeas, pagerW, ideasUpdatedAt]);

  function handleSelectMode(m: ShopMode) {
    if (m === mode) return;
    haptics.selection();
    flushPendingDismiss(); // mode change flushes the pending dismiss (R-9)
    requestPagerScroll(0); // consumed when the new mode's list renders (P-1)
    setMode(m);
    track('shop_mode_selected', { mode: m, n_ideas: visibleByMode[m].length }, 'Trades');
  }

  // W2 — a selection change IS a refetch (once it settles), so it goes
  // through the same R-9 contract as a mode change: flush the held dismiss
  // NOW, at tap time — never let it race the debounce window. The settled
  // key then lands in the ideasUpdatedAt effect above like any fresh
  // payload (reset removals, rewind pager).
  function handleTogglePosition(p: SwapPos) {
    haptics.selection();
    flushPendingDismiss();
    setPositions((prev) => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else next.add(p);
      return next;
    });
  }

  // The empty state's escape (mockup D10): back to the shipped
  // same-position laterals in one tap.
  function clearPositions() {
    flushPendingDismiss();
    setPositions(new Set());
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

      {/* W2 (R-10) — the position multi-select lives INSIDE the Same-value
          pane only (chips for tier up/down would claim a filter the server
          never applies — R-11). Mounted outside the loading/empty ternary
          so the user's chips stay visible while a re-sweep is in flight. */}
      {mode === 'same_value' && pickerApplies ? (
        <View style={styles.picker} testID="shop.picker">
          <View style={styles.pickerRow}>
            {offeredPositions.map((p) => (
              <SwapPosChip
                key={p}
                pos={p}
                selected={positions.has(p)}
                onPress={() => handleTogglePosition(p)}
              />
            ))}
          </View>
          <Text style={[type.bodySm, styles.pickerHint]}>
            {positions.size === 0
              ? `Positions offered back · leave all clear for same-position swaps at ${pinPos}`
              : `Ideas come back at ${humanList([...positions].sort(), 'and')}.`}
          </Text>
          {avoidOmitted.length > 0 ? (
            // Mockup D7 — an omitted chip and a bug look identical without
            // this line (#360 latent: `trade.avoid_positions` ships dark).
            <Text style={[type.bodySm, styles.pickerHint]}>
              {`${humanList(avoidOmitted, 'and')} ${
                avoidOmitted.length > 1 ? "aren't" : "isn't"
              } offered — you're avoiding ${
                avoidOmitted.length > 1 ? 'those positions' : avoidOmitted[0]
              } in this league.`}
            </Text>
          ) : null}
        </View>
      ) : null}

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
        mode === 'same_value' && settledSelection.length > 0 ? (
          // W2 (R-15 + mockup D10/D11) — the FILTERED empty is first-class,
          // not an edge: spike S-2 measured single-position selections empty
          // 30–60% of the time. Name the selection, say why in one plain
          // sentence, and hand over the real escapes: clear the positions
          // (with the baseline count when the unfiltered payload can vouch
          // for it) or switch mode (live counts on the chips above).
          <View style={styles.empty} testID="shop.empty">
            <Text style={[type.body, styles.emptyHead]}>
              {`Nothing at ${humanList(settledSelection, 'or')}`}
            </Text>
            <Text style={[type.bodySm, styles.emptyBody]}>
              {`No same-value offer for ${asset.name} comes back at ${humanList(
                settledSelection,
                'or',
              )} right now.`}
            </Text>
            <Text style={[type.bodySm, styles.emptyHint]}>
              A same-value offer has to land close to his value and leave both
              rosters better off — across a position line that window is
              narrow, so an empty answer here is normal, not a failure.
            </Text>
            <Button
              testID="shop.clear-positions"
              label={
                baselineLateralCount > 0
                  ? `Clear positions — ${baselineLateralCount} at ${pinPos}`
                  : 'Clear positions'
              }
              variant="ghost"
              compact
              onPress={clearPositions}
            />
            {SHOP_MODES.some((m) => m !== mode && visibleByMode[m].length > 0) ? (
              <Text style={[type.bodySm, styles.emptyHint]}>
                The other modes have offers — the counts on the chips are live.
              </Text>
            ) : null}
          </View>
        ) : (
          // R-15 — honest empty, named per mode; the second line renders
          // only when it is TRUE (another mode actually has offers). No
          // Clear-positions button here: nothing is selected to clear, and
          // a dead control is worse than none (mockup D11).
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
        )
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
// host opens the strip for that asset through its single strip-open path,
// which is where `shop_opened` fires with the picked position (P-3: the
// chooser itself emits nothing — not on open, not on Cancel). No
// FeedbackFAB (modal exception).
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
  // W2 picker — chips follow the DnaToggle (ptb) construction from
  // TradeDnaSheet, compacted to the strip's 36px control height.
  picker: { gap: space.xs },
  pickerRow: { flexDirection: 'row', gap: space.xs },
  posChip: {
    flex: 1,
    minHeight: 36,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    paddingHorizontal: 2,
  },
  posChipDot: { width: 7, height: 7, borderRadius: radii.xs },
  posChipText: { ...type.bodySm, color: chalk.base, fontFamily: fonts.uiSemi },
  posChipTextSel: { color: ice.on, fontFamily: fonts.uiBold },
  pickerHint: { color: chalk.faint },
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

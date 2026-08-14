import React, { useRef, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { Button, Icon, Text } from './chalkline';
import TradeValueBar from './TradeValueBar';
import { evaluateTrade } from '../api/calc';
import { track } from '../api/events';
import { useSession } from '../state/useSession';
import { chalk, ice, ink, radii, semantic, space, type } from '../theme/chalkline';

// MatchValueSection — #319. The Matches inbox's expandable trade-value
// disclosure + open-in-calc CTA, mounted through TradeCard's `footer` slot on
// BOTH segments (mutual + awaiting). The matches/awaiting payloads carry asset
// ids + names only — no give_value/receive_value — so the section fetches the
// verdict lazily from the same public POST /api/trade/evaluate that stamps
// deck cards (Path A, plan 2026-08-13). The bar is `TradeValueBar` VERBATIM —
// no fork — so the inbox can never disagree with the deck about the same
// package. Fetch is disclosure-gated: a scroll through the inbox costs zero
// extra requests (S-1 pins `enabled: expanded`).
//
// Scoring-format caveat (plan, decided): pricing uses the session
// activeFormat fallback chain (the TradeCalculatorScreen rule) — a
// cross-league row viewed under a different active format prices by the
// active format. Documented approximation; the CTA path switches leagues
// first, which re-detects format.

export interface MatchValueSectionProps {
  /** Stable identity for query key + analytics. Mutual: match_id. Awaiting: `${league_id}:${trade_id}`. */
  matchKey: string;
  /** match_id when this row is a mutual match — drives the match_opened event; undefined on awaiting rows. */
  matchId?: string;
  leagueId: string;
  giveIds: string[];        // my_side_player_ids (assets I send)
  receiveIds: string[];     // their_side_player_ids (assets I get)
  opponentUsername: string;
  opponentUserId: string;
  /** Same-league fast path vs cross-league league-switch path (screen owns it). */
  isActiveLeague: boolean;
  onOpenInCalc: () => void; // screen owns navigation + league switching
}

export default function MatchValueSection({
  matchKey,
  matchId,
  giveIds,
  receiveIds,
  opponentUsername,
  onOpenInCalc,
}: MatchValueSectionProps) {
  // Per-instance disclosure state — every row starts collapsed (#243 precedent).
  const [expanded, setExpanded] = useState(false);
  // match_opened fires once per row per mount, on FIRST expand only, and only
  // for mutual rows (the event's taxonomy allows only match_id; awaiting rows
  // have none — waived in writing, plan § Analytics).
  const openedFiredRef = useRef(false);

  // TradeCalculatorScreen's format fallback rule: the session activeFormat
  // when it is a known format, else 1qb_ppr.
  const sessionFormat = useSession((s) => s.activeFormat);
  const format =
    sessionFormat === 'sf_tep' || sessionFormat === '1qb_ppr' ? sessionFormat : '1qb_ppr';

  const evalQuery = useQuery({
    queryKey: ['match-eval', matchKey, format],
    queryFn: ({ signal }) => evaluateTrade(giveIds, receiveIds, format, signal),
    // Load-bearing: the evaluate POST fires only once the user expands (S-1).
    enabled: expanded,
    staleTime: 5 * 60_000,
  });

  function toggle() {
    setExpanded((open) => {
      const next = !open;
      if (next && matchId && !openedFiredRef.current) {
        openedFiredRef.current = true;
        track('match_opened', { match_id: matchId }, 'Matches');
      }
      return next;
    });
  }

  const ev = evalQuery.data;
  const droppedCount = ev?.dropped_player_ids?.length ?? 0;

  return (
    <View style={styles.wrap}>
      {/* Collapsed row — the shipped disclosure grammar (TradeValueBar's
          "Why?" toggle / AdjustmentsDisclosure construction). */}
      <Pressable
        testID="matches.value-details"
        onPress={toggle}
        accessibilityRole="button"
        accessibilityLabel={expanded ? 'Hide trade value details' : 'Show trade value details'}
        style={styles.toggle}
        hitSlop={6}
      >
        <Text scale="dense" style={styles.toggleText}>Trade value</Text>
        <Icon name={expanded ? 'chevron-up' : 'chevron-down'} size={14} color={chalk.dim} />
      </Pressable>

      {expanded ? (
        <View style={styles.body}>
          {evalQuery.isPending ? (
            // The repricingRow construction (TradeCard).
            <View style={styles.loadingRow}>
              <ActivityIndicator size="small" color={ice.base} />
              <Text style={type.bodySm}>Valuing…</Text>
            </View>
          ) : evalQuery.isError ? (
            // Error is local to the disclosure — no toast.
            <View style={styles.errorWrap}>
              <Text style={styles.errorText}>Could not value this trade.</Text>
              <Button
                variant="ghost"
                compact
                label="Retry"
                onPress={() => evalQuery.refetch()}
              />
            </View>
          ) : ev ? (
            <>
              {/* Honesty rail: Mode A dropped assets it could not value —
                  say so above the bar. When either side dropped to zero
                  valued assets, ev.gap is null and TradeValueBar renders
                  null, so the caveat stands alone — never a fake "Even". */}
              {droppedCount > 0 ? (
                <Text style={styles.caveat}>
                  {droppedCount} asset{droppedCount === 1 ? '' : 's'} couldn't be valued —
                  verdict excludes {droppedCount === 1 ? 'it' : 'them'}
                </Text>
              ) : null}
              <TradeValueBar
                giveValue={ev.give_value}
                receiveValue={ev.receive_value}
                favors={ev.favors ?? null}
                gap={ev.gap ?? null}
                youLabel="You"
                themLabel={`@${opponentUsername}`}
              />
            </>
          ) : null}

          {/* Open-in-calc CTA — the #190 hint-tier construction (editCalcBtn
              grammar). Rendered inside the expanded state only ("under that
              section", per the item). */}
          <Pressable
            testID="matches.open-in-calc"
            accessibilityRole="button"
            accessibilityLabel="Open this trade in the calculator"
            onPress={onOpenInCalc}
            style={({ pressed }) => [styles.calcBtn, pressed && styles.calcBtnPressed]}
          >
            <Icon name="trade" size={14} color={chalk.dim} />
            <Text style={styles.calcBtnText}>Open in calculator</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.sm },
  toggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 32,
  },
  toggleText: { ...type.label, color: chalk.dim },
  body: { gap: space.sm },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  errorWrap: { gap: space.xs, alignItems: 'flex-start' },
  errorText: { ...type.bodySm, color: semantic.neg },
  caveat: { ...type.bodySm, color: chalk.dim },
  // #190 editCalcBtn grammar: hint-tier inline action, hairline border.
  calcBtn: {
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
  calcBtnPressed: { backgroundColor: ink.ink3 },
  calcBtnText: { ...type.bodySm, color: chalk.dim },
});

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import ChalkText from '../components/chalkline/Text';
import { Button } from '../components/chalkline';
import FeedbackFAB from '../components/FeedbackFAB';
import { chalk, flare, ice, ink, radii, semantic, space, type } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { track } from '../api/events';
import {
  getLeagueReceipts, RECEIPTS_WINDOWS,
  type ReceiptsResponse, type ReceiptsRow, type ReceiptsWindowDays,
  type ReceiptsWindowSummary,
} from '../api/receipts';

// RECEIPTS — the graded track record of the app's own suggestions.
// Plan suite: docs/plans/receipts/ (PRD §FR-5 for the states below).
//
// TWO STATES, BOTH DESIGNED. The maturity/"preregistration ledger" state is
// the LAUNCH HERO, not an apology for having no data: "23 suggestions on
// record since Aug 16, first full report ~Oct 11, and we publish every result"
// is the trust pitch. A screen that hid itself until the numbers looked good
// would be making the opposite argument.
//
// LOSSES RENDER IDENTICALLY TO WINS. There is one row format and it shows both
// sides of every trade. Best call is never shown without worst call, and both
// are max/min edge_pct over the same displayed rows — symmetric by
// construction, so there is no editorial step to get wrong later.
//
// THE WINDOW CHIPS DO NOT REFETCH. One payload carries 14/28/56d; the chips
// select a field of data already in memory. That is what makes cherry-picking
// a window structurally impossible rather than merely discouraged.
//
// #188 — this is a ROOT-STACK push, so it mounts its OWN FeedbackFAB. (The
// global mount in RootNav covers tab-stack screens only; a second one there is
// the #196/#197 double-FAB bug.)
//
// Chalkline (ADR-004/005): ledger tone. No streaks, no letter grades, no
// confetti, no emoji. `flare` appears exactly once — on the preregistration
// lock explainer, which is informational — and `ice` is reserved for
// tappables. Gain/loss use the semantic tokens AND a sign glyph, so meaning is
// never carried by colour alone.

const HEADLINE_WINDOW: ReceiptsWindowDays = 28;

/** 56d cannot mature before ~Oct 11 given the 2026-08-16 cohort start, so the
 *  ETA is computed from the first tracked date rather than hardcoded. */
function firstReportEta(firstTrackedAt: string | null): string | null {
  if (!firstTrackedAt) return null;
  const start = new Date(`${firstTrackedAt}T00:00:00Z`);
  if (Number.isNaN(start.getTime())) return null;
  start.setUTCDate(start.getUTCDate() + 56);
  return start.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function formatDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function signed(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return '—';
  const sign = n > 0 ? '+' : n < 0 ? '−' : '±';
  return `${sign}${Math.abs(n).toFixed(digits)}`;
}

function signedPct(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  const sign = n > 0 ? '+' : n < 0 ? '−' : '±';
  return `${sign}${(Math.abs(n) * 100).toFixed(1)}%`;
}

function deltaColor(n: number | null | undefined): string {
  if (n === null || n === undefined || n === 0) return chalk.dim;
  return n > 0 ? semantic.pos : semantic.neg;
}

function assetLine(assets: ReceiptsRow['give']['assets']): string {
  if (!assets.length) return '—';
  return assets.map((a) => a.name || (a.is_pick ? 'Draft pick' : a.id)).join(' + ');
}

// ── Window chips ───────────────────────────────────────────────────────────
// Every window is always rendered, including the empty ones. A window with no
// data says so; it is never hidden, because hiding it is how a payload with
// three windows becomes a screen with one.
function WindowChips({
  windows, selected, onSelect,
}: {
  windows: ReceiptsWindowSummary[];
  selected: ReceiptsWindowDays;
  onSelect: (w: ReceiptsWindowDays) => void;
}) {
  return (
    <View style={styles.chipRow}>
      {RECEIPTS_WINDOWS.map((w) => {
        const summary = windows.find((x) => x.window_days === w);
        const active = w === selected;
        const status = summary?.status ?? 'pending';
        return (
          <Pressable
            key={w}
            testID={`receipts-window-chip-${w}`}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            accessibilityLabel={`${w} day window, ${status}`}
            onPress={() => onSelect(w)}
            style={({ pressed }) => [
              styles.chip,
              active && styles.chipActive,
              pressed && styles.chipPressed,
            ]}
          >
            <ChalkText variant="label" style={active ? styles.chipTextActive : styles.chipText}>
              {`${w}D`}
            </ChalkText>
            <ChalkText variant="data" style={styles.chipMeta}>
              {status === 'ready' ? `n=${summary?.n ?? 0}`
                : status === 'insufficient' ? `n=${summary?.n ?? 0}`
                : '—'}
            </ChalkText>
          </Pressable>
        );
      })}
    </View>
  );
}

// ── One graded suggestion ──────────────────────────────────────────────────
// Deliberately NOT named `Receipt`: `OutlookBiasReceipt.tsx` already owns that
// noun in this codebase, and two components called the same thing is how the
// wrong one gets imported.
function ReceiptsRowCard({
  row, window: win, isBest, isWorst,
}: {
  row: ReceiptsRow;
  window: ReceiptsWindowDays;
  isBest: boolean;
  isWorst: boolean;
}) {
  const w = row.windows[String(win)];
  return (
    <View testID="receipts-row" style={styles.card}>
      <View style={styles.cardHead}>
        <ChalkText variant="label" style={styles.cardDate}>
          {formatDate(row.served_at)}
          {row.shape_bucket ? ` · ${row.shape_bucket}` : ''}
        </ChalkText>
        {/* Both markers exist or neither does — the payload picks them as
            max/min of the same row set. */}
        {isBest ? (
          <ChalkText variant="label" style={styles.markerBest}>BEST CALL</ChalkText>
        ) : null}
        {isWorst ? (
          <ChalkText variant="label" style={styles.markerWorst}>WORST CALL</ChalkText>
        ) : null}
      </View>

      <View style={styles.sideRow}>
        <ChalkText variant="label" style={styles.sideLabel}>GAVE</ChalkText>
        <ChalkText variant="body" style={styles.sideAssets}>{assetLine(row.give.assets)}</ChalkText>
        <ChalkText variant="data" style={[styles.sideDelta, { color: deltaColor(w?.give_delta) }]}>
          {signed(w?.give_delta)}
        </ChalkText>
      </View>
      <View style={styles.sideRow}>
        <ChalkText variant="label" style={styles.sideLabel}>GOT</ChalkText>
        <ChalkText variant="body" style={styles.sideAssets}>{assetLine(row.receive.assets)}</ChalkText>
        <ChalkText variant="data" style={[styles.sideDelta, { color: deltaColor(w?.receive_delta) }]}>
          {signed(w?.receive_delta)}
        </ChalkText>
      </View>

      <View style={styles.edgeRow}>
        <ChalkText variant="label" style={styles.edgeLabel}>SWAP EDGE</ChalkText>
        <ChalkText variant="data" style={[styles.edgeValue, { color: deltaColor(w?.edge) }]}>
          {w ? `${signed(w.edge)}  (${signedPct(w.edge_pct)})` : 'not graded yet'}
        </ChalkText>
      </View>

      {row.has_picks || w?.imputed ? (
        <ChalkText variant="bodySm" style={styles.flagLine}>
          {[
            row.has_picks ? 'Picks held flat — pick prices are our own numbers, not the market’s.' : null,
            w?.imputed ? 'A player left the value pool; counted at the pool floor rather than dropped.' : null,
          ].filter(Boolean).join(' ')}
        </ChalkText>
      ) : null}
    </View>
  );
}

export default function ReceiptsScreen() {
  const leagueId = useSession((s) => s.league?.league_id);
  const [win, setWin] = useState<ReceiptsWindowDays>(HEADLINE_WINDOW);

  const query = useQuery({
    queryKey: ['receipts', leagueId],
    queryFn: () => getLeagueReceipts(leagueId as string),
    enabled: !!leagueId,
    staleTime: 5 * 60_000,
  });

  const data: ReceiptsResponse | undefined = query.data;
  const headline = useMemo(
    () => data?.windows.find((w) => w.window_days === HEADLINE_WINDOW),
    [data],
  );
  const isMature = headline?.status === 'ready';

  // `receipts_opened` — INTENT (deliberate feature engagement, the
  // find_trades_tapped class). Fires once per resolved payload, not per render.
  useEffect(() => {
    if (!data || !leagueId) return;
    const share = headline?.win_share;
    track('receipts_opened', {
      league_id: leagueId,
      status: isMature ? 'ready' : 'ledger',
      n_graded_28d: data.maturity.graded_n['28'] ?? 0,
      headline_bucket:
        share === undefined || share === null ? 'flat'
          : share > 0.5 ? 'pos' : share < 0.5 ? 'neg' : 'flat',
    }, 'Receipts');
  }, [data, leagueId, isMature, headline?.win_share]);

  const onWindow = useCallback((next: ReceiptsWindowDays) => {
    setWin(next);
    // NON_INTENT (navigation, the tab_selected class). No refetch: the payload
    // already holds every window.
    track('receipts_window_changed', { league_id: leagueId, window_days: next },
          'Receipts');
  }, [leagueId]);

  if (query.isLoading) {
    return (
      <SafeAreaView testID="receipts-screen" style={styles.safe} edges={['bottom']}>
        <View style={styles.centerFill}>
          <ActivityIndicator color={ice.base} />
        </View>
        <FeedbackFAB activeScreen="Receipts" aboveTabBar={false} />
      </SafeAreaView>
    );
  }

  if (query.isError || !data) {
    return (
      <SafeAreaView testID="receipts-screen" style={styles.safe} edges={['bottom']}>
        <View style={styles.centerFill}>
          <ChalkText variant="body" style={styles.errorText}>
            Couldn’t load your track record.
          </ChalkText>
          <Button label="Try again" onPress={() => query.refetch()} />
        </View>
        <FeedbackFAB activeScreen="Receipts" aboveTabBar={false} />
      </SafeAreaView>
    );
  }

  const eta = firstReportEta(data.maturity.first_tracked_at);
  const since = data.maturity.first_tracked_at
    ? formatDate(`${data.maturity.first_tracked_at}T00:00:00Z`)
    : null;
  const rows = data.rows;

  return (
    <SafeAreaView testID="receipts-screen" style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        {/* The preregistration explainer — the one informational `flare`
            accent on this screen, and the claim the whole feature rests on. */}
        <View style={styles.lockPanel}>
          <ChalkText variant="label" style={styles.lockLabel}>PREDICTIONS LOCKED AT SERVE</ChalkText>
          <ChalkText variant="bodySm" style={styles.lockBody}>
            We record what a suggestion asked you to swap the moment we show it,
            then grade it against market consensus later. We publish every
            result, wins and losses.
          </ChalkText>
        </View>

        {isMature ? (
          <View style={styles.headlinePanel}>
            <ChalkText variant="dataLg" style={styles.headlineNumber}>
              {`${Math.round((headline!.win_share ?? 0) * 100)}%`}
            </ChalkText>
            <ChalkText variant="body" style={styles.headlineCaption}>
              {`${Math.round((headline!.win_share ?? 0) * headline!.n)} of ${headline!.n} suggestions moved your way over 28 days`}
            </ChalkText>
            <ChalkText variant="bodySm" style={styles.headlineSub}>
              {`Median swap edge ${signedPct(headline!.median_edge_pct)} · a coin-flip swap breaks even at 50%`}
            </ChalkText>
          </View>
        ) : (
          // The ledger state — the launch hero, not an empty state.
          <View testID="receipts-maturity" style={styles.maturityPanel}>
            <ChalkText variant="dataLg" style={styles.headlineNumber}>
              {String(data.maturity.tracked_n)}
            </ChalkText>
            <ChalkText variant="body" style={styles.headlineCaption}>
              {since
                ? `suggestions on record since ${since}`
                : 'suggestions on record'}
            </ChalkText>
            <ChalkText variant="bodySm" style={styles.headlineSub}>
              {eta
                ? `First full report around ${eta}. We need ${data.maturity.min_n} graded suggestions before publishing a number.`
                : `We need ${data.maturity.min_n} graded suggestions before publishing a number.`}
            </ChalkText>
          </View>
        )}

        <WindowChips windows={data.windows} selected={win} onSelect={onWindow} />

        {rows.length === 0 ? (
          <ChalkText variant="bodySm" style={styles.emptyRows}>
            Nothing has finished grading yet. Suggestions appear here as their
            windows close.
          </ChalkText>
        ) : (
          rows.map((row) => (
            <ReceiptsRowCard
              key={row.impression_id}
              row={row}
              window={win}
              isBest={row.impression_id === data.best_call_impression_id}
              isWorst={row.impression_id === data.worst_call_impression_id}
            />
          ))
        )}

        {/* Selection disclosure sits WITH the numbers, not in a footnote a
            future redesign can drop. */}
        <View style={styles.disclosure}>
          <ChalkText variant="bodySm" style={styles.disclosureText}>
            {data.disclosure.methodology}
          </ChalkText>
          {data.disclosure.gradeable_share !== null ? (
            <ChalkText variant="bodySm" style={styles.disclosureText}>
              {`${Math.round(data.disclosure.gradeable_share * 100)}% of tracked suggestions could be graded. ` +
               `${Object.values(data.disclosure.excluded).reduce((a, b) => a + b, 0)} were excluded (mostly pick-heavy packages or missing market data).`}
            </ChalkText>
          ) : null}
          {data.disclosure.pre_telemetry > 0 ? (
            <ChalkText variant="bodySm" style={styles.disclosureText}>
              {`${data.disclosure.pre_telemetry} older suggestions can never be graded — we didn’t record their assets at the time.`}
            </ChalkText>
          ) : null}
          {data.grader_version && data.grader_version !== 'receipts-1' ? (
            <ChalkText variant="bodySm" style={styles.disclosureText}>
              {`Regraded under ${data.grader_version}. Earlier grades are kept.`}
            </ChalkText>
          ) : null}
        </View>
      </ScrollView>
      {/* #188 — root-stack push, so this screen carries its own FAB. */}
      <FeedbackFAB activeScreen="Receipts" aboveTabBar={false} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  scroll: { padding: space.lg, paddingBottom: space.xxxl },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.lg },
  errorText: { color: chalk.dim, textAlign: 'center' },

  lockPanel: {
    borderLeftWidth: 2,
    borderLeftColor: flare.base,
    backgroundColor: ink.ink1,
    borderRadius: radii.md,
    padding: space.md,
    marginBottom: space.lg,
  },
  lockLabel: { color: flare.base, marginBottom: space.xs },
  lockBody: { color: chalk.dim },

  headlinePanel: {
    backgroundColor: ink.ink1,
    borderRadius: radii.md,
    padding: space.lg,
    marginBottom: space.lg,
  },
  maturityPanel: {
    backgroundColor: ink.ink1,
    borderRadius: radii.md,
    padding: space.lg,
    marginBottom: space.lg,
  },
  headlineNumber: { color: chalk.base },
  headlineCaption: { color: chalk.base, marginTop: space.xs },
  headlineSub: { color: chalk.dim, marginTop: space.sm },

  chipRow: { flexDirection: 'row', gap: space.sm, marginBottom: space.lg },
  chip: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: space.sm,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: ink.line,
    backgroundColor: ink.ink1,
  },
  chipActive: { borderColor: ice.base },
  chipPressed: { backgroundColor: ink.ink3 },
  chipText: { color: chalk.dim },
  chipTextActive: { color: ice.base },
  chipMeta: { color: chalk.faint, fontSize: 11 },

  card: {
    backgroundColor: ink.ink1,
    borderRadius: radii.md,
    padding: space.md,
    marginBottom: space.md,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginBottom: space.sm },
  cardDate: { color: chalk.faint, flex: 1 },
  markerBest: { color: semantic.pos },
  markerWorst: { color: semantic.neg },

  sideRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, marginBottom: space.xs },
  sideLabel: { color: chalk.faint, width: 38 },
  sideAssets: { color: chalk.base, flex: 1 },
  sideDelta: { minWidth: 64, textAlign: 'right' },

  edgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: space.sm,
    paddingTop: space.sm,
    borderTopWidth: 1,
    borderTopColor: ink.line,
  },
  edgeLabel: { color: chalk.dim },
  edgeValue: {},

  flagLine: { color: chalk.faint, marginTop: space.sm },
  emptyRows: { color: chalk.dim, marginBottom: space.lg },

  disclosure: { marginTop: space.lg, gap: space.sm },
  disclosureText: { color: chalk.faint },
});

// 200 ms path — the paged deck's quiet states (Trades-only; TradesScreen is
// the one host). Specs:
//   - DeckUpdatingLabel: design-lead #339 §5.4.1–2/6 (chalk-dim body-sm +
//     the standard Spinner, trailing in an EXISTING row, never a new one;
//     static "Updating" under reduced motion). Never disables Like or Pass.
//   - WithdrawnTradeCard: design-lead §5.4.4 + U1.7 (keeps its slot; one
//     chalk-dim reason line + the `x` icon in chalk-dim; no red, no amber).
//   - DeckEndCard: design-lead "P30: the end-of-deck card" + head-eng
//     ruling 13 / D14 (EmptyState in the card frame; one Primary, one
//     Secondary; the D-171 tally as one chalk-dim line; no Like/Pass; no
//     count, no third action, no "new trades" notice).
//   - DeckOfflineCard / DeckMoreErrorCard: ux-lead U3 rows 3a and 3b (one
//     honest static line in the card rect, Retry as a Secondary).
//   - DeckRefreshFailedLine: PRD #339 §5.4 "Refresh failed" (design-lead 3
//     and 5): the Banner construction (ink-2, hairline, body-sm chalk-dim),
//     inline in the deck under the card, non-dismissable, Secondary Retry.
//     Shown when a device-held page could not be revalidated (C).
// VoiceOver per ux-lead U3: every announcement is polite and fires once,
// when the state appears. Copy owner: marketing-lead (the P30 lines are
// Product's verbatim); the other lines are placeholders from ux-lead's spec.
import React, { useEffect, useRef } from 'react';
import { AccessibilityInfo, ActivityIndicator, StyleSheet, View, findNodeHandle } from 'react-native';
import { Button, Card, Icon, Text } from './chalkline';
import { chalk, fonts, ice, ink, radii, space } from '../theme/chalkline';
import { useReducedMotionSafe } from '../hooks/useReducedMotionSafe';

// P30 copy: marketing-lead's copy file, rows p30.* (final, 2026-10-23).
export const DECK_END_TITLE = "You've seen every trade for now.";
export const DECK_END_BODY = 'New ideas show up as rosters and values change.';
export const WITHDRAWN_REASON = 'This trade is no longer available.';
export const DECK_OFFLINE_LINE = "You're offline. More trades load when you're back online.";
export const DECK_MORE_ERROR_LINE = "Couldn't load more trades.";
// Placeholder per §5.4 ("says the deck may be out of date"); copy owner
// marketing-lead.
export const DECK_REFRESH_FAILED_LINE = "Couldn't refresh. These trades may be out of date.";

function announcePolitely(line: string) {
  // `queue: true` lets VoiceOver finish what it is reading (polite).
  if (AccessibilityInfo.announceForAccessibilityWithOptions) {
    AccessibilityInfo.announceForAccessibilityWithOptions(line, { queue: true });
  } else {
    AccessibilityInfo.announceForAccessibility(line);
  }
}

function useAnnounceOnMount(line: string) {
  useEffect(() => {
    announcePolitely(line);
    // Once per appearance: the line is fixed for the mount's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

// Moves VoiceOver focus to `ref` once, after the frame lands.
function useFocusOnMount(ref: React.RefObject<View | null>) {
  useEffect(() => {
    const t = setTimeout(() => {
      const node = ref.current ? findNodeHandle(ref.current) : null;
      if (node != null) AccessibilityInfo.setAccessibilityFocus(node);
    }, 150);
    return () => clearTimeout(t);
  }, [ref]);
}

/** Trailing "Updating" status for the deck's existing header row. Purely
 *  informational: it takes no props that could touch Like or Pass. */
export function DeckUpdatingLabel() {
  const reduceMotion = useReducedMotionSafe();
  useAnnounceOnMount('Updating trades');
  return (
    <View testID="trades.deck-updating" style={styles.updating} accessible accessibilityLabel="Updating trades">
      {reduceMotion ? null : <ActivityIndicator size="small" color={ice.base} style={styles.spinner} />}
      <Text variant="bodySm">Updating</Text>
    </View>
  );
}

/** U2 — the fronted card the server no longer serves, withdrawn in place.
 *  It keeps the card's slot (`minHeight` = the measured card height) and
 *  offers the one move forward. No Like or Pass: there is no trade left to
 *  judge. */
export function WithdrawnTradeCard({ minHeight, onNext }: { minHeight?: number | null; onNext: () => void }) {
  const bodyRef = useRef<View>(null);
  useFocusOnMount(bodyRef);
  return (
    <View testID="trades.withdrawn">
      <Card style={minHeight ? { minHeight } : undefined}>
        <View
          ref={bodyRef}
          style={styles.withdrawnRow}
          accessible
          accessibilityLabel={WITHDRAWN_REASON}
        >
          <Icon name="x" size={16} color={chalk.dim} />
          <Text variant="bodySm" testID="trades.withdrawn.reason" style={styles.flex}>
            {WITHDRAWN_REASON}
          </Text>
        </View>
        <Button
          testID="trades.withdrawn.next"
          label="Next trade"
          variant="secondary"
          onPress={onNext}
          style={styles.fullWidth}
        />
      </Card>
    </View>
  );
}

/** P30 — the honest end of the deck, in the card slot. Rendered only when
 *  the server said `pool_exhausted` and nothing is in flight or retrying
 *  (utils/tradePages.deckEndState), then held in place (TradesScreen's
 *  latch): cards that arrive later go BEHIND it, silently. */
export function DeckEndCard({
  minHeight,
  tally,
  onAdjust,
  onHome,
}: {
  minHeight?: number | null;
  /** D-171 ruling 4's end-of-deck tally (head-eng D14b), one chalk-dim line
   *  (p30.tally). Null only when the tally source (deck.replenishment) is off. */
  tally: { passed: number; liked: number; proposed: number } | null;
  onAdjust: () => void;
  /** Absent when the app has no Home tab (`nav.home_tab` off). */
  onHome?: () => void;
}) {
  const copyRef = useRef<View>(null);
  useFocusOnMount(copyRef);
  return (
    <View testID="trades.deck-end">
      <Card style={minHeight ? { minHeight } : undefined}>
        <View ref={copyRef} accessible accessibilityLabel={`${DECK_END_TITLE} ${DECK_END_BODY}`}>
          <Text variant="heading">{DECK_END_TITLE}</Text>
          <Text variant="bodySm" style={styles.endBody}>{DECK_END_BODY}</Text>
          {/* TODO(trades-pm): suppress at 0·0·0? Shown at zero for now. */}
          {tally ? (
            <Text variant="bodySm" testID="trades.deck-end.tally" style={styles.endBody}>
              <Text style={styles.tallyNum}>{tally.passed}</Text>
              {' passed · '}
              <Text style={styles.tallyNum}>{tally.liked}</Text>
              {' liked · '}
              <Text style={styles.tallyNum}>{tally.proposed}</Text>
              {' proposed'}
            </Text>
          ) : null}
        </View>
        <View style={styles.endActions}>
          <Button
            testID="trades.deck-end.adjust"
            label="Adjust your search"
            variant="primary"
            onPress={onAdjust}
            style={styles.fullWidth}
          />
          {onHome ? (
            <Button
              testID="trades.deck-end.home"
              label="Back to Home"
              variant="secondary"
              onPress={onHome}
              style={styles.fullWidth}
            />
          ) : null}
        </View>
      </Card>
    </View>
  );
}

/** U3 row 3a — offline, and the user is past the last card on the device.
 *  On reconnect the next page appends and replaces this card in place. */
export function DeckOfflineCard({ minHeight, onRetry }: { minHeight?: number | null; onRetry: () => void }) {
  useAnnounceOnMount(DECK_OFFLINE_LINE);
  return (
    <View testID="trades.deck-offline">
      <Card style={minHeight ? { minHeight } : undefined}>
        <Text variant="bodySm">{DECK_OFFLINE_LINE}</Text>
        <Button
          testID="trades.deck-offline.retry"
          label="Retry"
          variant="secondary"
          onPress={onRetry}
          style={styles.fullWidth}
        />
      </Card>
    </View>
  );
}

/** U3 row 3b — online, but the next page will not come (fetches failing, or
 *  the job errored), and the user is past the last card. It ends; the
 *  header Back stays usable. */
export function DeckMoreErrorCard({ minHeight, onRetry }: { minHeight?: number | null; onRetry: () => void }) {
  useAnnounceOnMount(DECK_MORE_ERROR_LINE);
  return (
    <View testID="trades.deck-more-error">
      <Card style={minHeight ? { minHeight } : undefined}>
        <Text variant="bodySm">{DECK_MORE_ERROR_LINE}</Text>
        <Button
          testID="trades.deck-more-error.retry"
          label="Try again"
          variant="secondary"
          onPress={onRetry}
          style={styles.fullWidth}
        />
      </Card>
    </View>
  );
}

/** C — the device-held page could not be revalidated (offline at the tap,
 *  a failed request, or past DEVICE_REVALIDATE_MAX_MS). The cards stay
 *  usable; Like/Pass are governed by I-2 at action time, not by this. */
export function DeckRefreshFailedLine({ onRetry }: { onRetry: () => void }) {
  useAnnounceOnMount(DECK_REFRESH_FAILED_LINE);
  return (
    <View testID="trades.deck-refresh-failed" style={styles.refreshFailed}>
      <Text variant="bodySm" style={styles.flex}>{DECK_REFRESH_FAILED_LINE}</Text>
      <Button
        testID="trades.deck-refresh-failed.retry"
        label="Retry"
        variant="secondary"
        onPress={onRetry}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  updating: { flexDirection: 'row', alignItems: 'center', gap: space.xs },
  // The standard Spinner is 20px; RN's "small" indicator is that size.
  spinner: { width: 20, height: 20 },
  flex: { flex: 1 },
  withdrawnRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  fullWidth: { alignSelf: 'stretch', marginTop: space.md },
  endBody: { marginTop: space.sm },
  // Plex Mono numerals (the tally's data), in the line's chalk-dim.
  tallyNum: { fontFamily: fonts.data, fontVariant: ['tabular-nums'] },
  endActions: { marginTop: space.sm },
  refreshFailed: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    marginTop: space.md,
    padding: space.md,
    backgroundColor: ink.ink2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ink.line,
    borderRadius: radii.md,
  },
});

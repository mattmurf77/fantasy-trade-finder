// 200 ms path — the paged deck's quiet states (Trades-only; TradesScreen is
// the one host). Specs:
//   - DeckEndCard: design-lead "P30: the end-of-deck card" + head-eng
//     ruling 13 / D14 (EmptyState in the card frame; one Primary, one
//     Secondary; the D-171 tally as one chalk-dim line; no Like/Pass; no
//     count, no third action, no "new trades" notice).
//   - DeckOfflineCard / DeckMoreErrorCard: ux-lead U3 rows 3a and 3b (one
//     honest static line in the card rect, Retry as a Secondary).
// VoiceOver per ux-lead U3: every announcement is polite and fires once,
// when the state appears. Copy owner: marketing-lead (the P30 lines are
// Product's verbatim); the other lines are placeholders from ux-lead's spec.
import React, { useEffect, useRef } from 'react';
import { AccessibilityInfo, StyleSheet, View, findNodeHandle } from 'react-native';
import { Button, Card, Text } from './chalkline';
import { space } from '../theme/chalkline';

export const DECK_END_TITLE = "You've seen every trade we have for now.";
export const DECK_END_BODY = 'New ideas show up as rosters and values change.';
export const DECK_OFFLINE_LINE = "You're offline. More trades load when you're back online.";
export const DECK_MORE_ERROR_LINE = "Couldn't load more trades.";

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
  /** D-171 ruling 4's end-of-deck tally (head-eng D14b), one chalk-dim line. */
  tally: string | null;
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
          {tally ? (
            <Text variant="bodySm" testID="trades.deck-end.tally" style={styles.endBody}>
              {tally}
            </Text>
          ) : null}
        </View>
        <View style={styles.endActions}>
          <Button
            testID="trades.deck-end.adjust"
            label="Adjust what I'm looking for"
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

const styles = StyleSheet.create({
  fullWidth: { alignSelf: 'stretch', marginTop: space.md },
  endBody: { marginTop: space.sm },
  endActions: { marginTop: space.sm },
});

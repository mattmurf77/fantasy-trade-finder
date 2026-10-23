// 200 ms path — the paged deck's quiet states (Trades-only; TradesScreen is
// the one host). Specs:
//   - DeckOfflineCard / DeckMoreErrorCard: ux-lead U3 rows 3a and 3b (one
//     honest static line in the card rect, Retry as a Secondary).
// VoiceOver per ux-lead U3: every announcement is polite and fires once,
// when the state appears. Copy owner: marketing-lead (the P30 lines are
// Product's verbatim); the other lines are placeholders from ux-lead's spec.
import React, { useEffect } from 'react';
import { AccessibilityInfo, StyleSheet, View } from 'react-native';
import { Button, Card, Text } from './chalkline';
import { space } from '../theme/chalkline';

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
});

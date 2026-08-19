import React from 'react';
import { View, StyleSheet } from 'react-native';
import { ink, chalk, ice, flare, space, radii, type, position as posColor } from '../../theme/chalkline';
import { Text, TickLabel, Badge, Button, Card } from '../chalkline';
import DeclineReasonPanel, {
  type DeclineReasonPanelProps,
} from '../DeclineReasonPanel';
import FairnessRangeBand from './FairnessRangeBand';
import { ConfidenceChip, ConfidenceCapNote } from './ConfidenceChip';
import {
  confidenceBand,
  fairnessBand,
  userSideBullets,
  counterpartyStatement,
  type ConfidenceCap,
} from '../../utils/tradePresentation';
import type { TradeCard, Player } from '../../shared/types';

// EndorsedTradeCard — "Today's Trade", the one endorsed hero per league per
// cycle. Flag `trades.presentation_v2`; approved lab
// mockups/trade-suggestion-redesign/01-todays-trade.html.
//
// THE ASYMMETRY IS THE FEATURE, NOT THE LAYOUT. The user's side gets up to
// three concrete bullets naming players and rooms on this very card; the
// counterparty gets ONE confidence sentence and nothing else. That shape is
// simultaneously the privacy-safe form (their board is never exposed) and the
// socially safe one — in a twelve-person league every endorsement is audited
// by people who will still be in the league next season. `userSideBullets`
// and `counterpartyStatement` in utils/tradePresentation.ts enforce it at the
// type level; do not reach around them.
//
// Fairness renders through FairnessRangeBand ONLY. FairnessMeter/Meter and
// TradeValueBar are winner-oriented and are banned on this surface — see that
// component's header.
//
// The endorsement badge is BINARY. There is no ladder, no "very strong", no
// numeric score anywhere on this card.

interface Props {
  card: TradeCard;
  /** Board-coverage ceiling, or null when nothing is being withheld. */
  cap: ConfidenceCap | null;
  onInterested: () => void;
  /** Fallback pass when decline-reason capture is off (flag
   *  `feedback.decline_reasons`). Exactly one of `onPass` / `reasons`
   *  renders, mirroring the deck's own rule that the ✕ disappears whenever
   *  the reason panel is mounted. */
  onPass?: () => void;
  /** The SAME DeclineReasonPanel props object the deck builds, so a dismiss
   *  here writes the identical two-layer signal. */
  reasons?: DeclineReasonPanelProps;
  onRankMore?: () => void;
  /** Reported by the host so the hero can announce the refresh cadence. */
  refreshNote?: string | null;
}

function AssetRow({ p, last }: { p: Player; last: boolean }) {
  const key = String(p.position ?? '').toLowerCase();
  const rail = (posColor as Record<string, string>)[key] ?? ink.lineStrongA11y;
  const meta = [p.position, p.team, p.age != null ? String(p.age) : null]
    .filter(Boolean)
    .join(' · ');
  return (
    <View style={[styles.asset, last && styles.assetLast]}>
      <View style={[styles.rail, { backgroundColor: rail }]} />
      <View style={styles.assetBody}>
        <Text scale="body" style={styles.assetName}>
          {p.name}
        </Text>
        {meta ? <Text scale="dense" style={styles.assetMeta}>{meta}</Text> : null}
      </View>
    </View>
  );
}

function Side({ label, players, testID }: { label: string; players: Player[]; testID: string }) {
  return (
    <View style={styles.side} testID={testID}>
      <TickLabel>{label}</TickLabel>
      {players.length === 0 ? (
        <Text variant="bodySm">Nothing</Text>
      ) : (
        players.map((p, i) => (
          <AssetRow key={`${p.id}-${i}`} p={p} last={i === players.length - 1} />
        ))
      )}
    </View>
  );
}

export default function EndorsedTradeCard({
  card,
  cap,
  onInterested,
  onPass,
  reasons,
  onRankMore,
  refreshNote,
}: Props) {
  const band = confidenceBand(card);
  const fair = fairnessBand(card.fairness);
  const bullets = userSideBullets(card);
  const who = card.opponent_username?.trim() || 'this manager';

  return (
    <View style={styles.wrap} testID="presentation.hero">
      <View style={styles.endorseRow}>
        <Badge label="Today's Trade" color={flare.base} colorText />
        <ConfidenceChip band={band} />
        {refreshNote ? (
          <Text scale="dense" style={styles.refresh}>
            {refreshNote}
          </Text>
        ) : null}
      </View>

      <Card padding={space.md}>
        <Text variant="title" testID="presentation.hero-title">
          Trade idea with {who}
        </Text>
        <Text variant="bodySm">Found between your board and league-wide activity</Text>

        {/* Two columns on wide phones; the flexWrap lets them stack rather
            than truncate once OS text scaling pushes a name past the column
            (a11y: wrap, never clip). */}
        <View style={styles.cols}>
          <Side label="You send" players={card.give_players ?? []} testID="presentation.hero-give" />
          <View style={styles.colDivider} />
          <Side label="You get" players={card.receive_players ?? []} testID="presentation.hero-receive" />
        </View>

        {fair ? <FairnessRangeBand band={fair} /> : null}

        <View style={styles.explain}>
          <TickLabel>Why it works for you</TickLabel>
          {bullets.length === 0 ? (
            // Honest degradation: an empty explanation beats a generic one.
            <Text variant="bodySm">
              We don't have enough on your board to explain this one in detail yet.
            </Text>
          ) : (
            bullets.map((b, i) => (
              <View key={i} style={styles.bullet}>
                <View style={styles.dot} />
                <Text scale="body" style={styles.bulletText}>
                  {b}
                </Text>
              </View>
            ))
          )}

          {/* Their half: a confidence STATEMENT. Never their board, never
              their values, never a number. */}
          <View style={styles.their} testID="presentation.hero-their-side">
            <Text variant="bodySm">{counterpartyStatement(card)}</Text>
          </View>
        </View>

        {cap ? <ConfidenceCapNote cap={cap} onRank={onRankMore} /> : null}

        {reasons ? (
          // Dismiss with reason — the SAME panel the deck mounts, so the
          // taxonomy, the progressive writes and the testIDs are identical.
          // The "I'm interested" action stays above it; the ✕ is gone, exactly
          // as on the deck card, because the layer-1 tile IS the pass.
          <View style={styles.actionsStack}>
            <Button
              label="I'm interested"
              variant="like"
              icon="check"
              onPress={onInterested}
              testID="presentation.hero-interested"
            />
            <DeclineReasonPanel {...reasons} />
          </View>
        ) : (
          <View style={styles.actions}>
            <Button
              label="I'm interested"
              variant="like"
              icon="check"
              onPress={onInterested}
              testID="presentation.hero-interested"
              style={styles.action}
            />
            <Button
              label="Pass"
              variant="pass"
              icon="x"
              onPress={onPass}
              testID="presentation.hero-pass"
              style={styles.action}
            />
          </View>
        )}

        <Text scale="dense" style={styles.privacy}>
          Passing is private — {who} never sees it.
        </Text>
      </Card>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: space.sm },
  endorseRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    flexWrap: 'wrap',
  },
  refresh: {
    ...type.data,
    fontSize: 11,
    lineHeight: 14,
    color: chalk.faint,
    marginLeft: 'auto',
  },
  cols: { flexDirection: 'row', gap: space.md, marginTop: space.sm },
  colDivider: { width: 1, backgroundColor: ink.line, alignSelf: 'stretch' },
  side: { flex: 1, minWidth: 0, gap: space.xs },
  asset: {
    flexDirection: 'row',
    gap: space.sm,
    paddingVertical: 7,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  assetLast: { borderBottomWidth: 0 },
  rail: { width: 3, alignSelf: 'stretch' },
  assetBody: { flex: 1, minWidth: 0 },
  assetName: { ...type.body, fontSize: 13, lineHeight: 17, color: chalk.base },
  assetMeta: { ...type.label, letterSpacing: 0.33, color: chalk.dim },
  explain: {
    borderTopWidth: 1,
    borderTopColor: ink.line,
    marginTop: space.md,
    paddingTop: space.sm,
    gap: space.xs,
  },
  bullet: { flexDirection: 'row', gap: space.sm, paddingVertical: 3 },
  dot: { width: 5, height: 5, marginTop: 8, backgroundColor: ice.base },
  bulletText: { flex: 1, ...type.bodySm, color: chalk.base },
  their: {
    marginTop: space.sm,
    padding: space.sm,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
  },
  actions: { flexDirection: 'row', gap: space.sm, marginTop: space.md },
  actionsStack: { gap: space.sm, marginTop: space.md },
  action: { flex: 1 },
  privacy: {
    ...type.bodySm,
    fontSize: 11,
    lineHeight: 14,
    textAlign: 'center',
    marginTop: space.sm,
    color: chalk.dim,
  },
});

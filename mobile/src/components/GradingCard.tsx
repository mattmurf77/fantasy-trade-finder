import React from 'react';
import { StyleSheet, View } from 'react-native';
import { chalk, ink, space, type } from '../theme/chalkline';
import { Badge, Card, PositionBadge, Text, TickLabel } from './chalkline';
import type { GradingAsset, GradingTrade } from '../api/grading';

// Calibration — the NEUTRAL trade card (docs/plans/blind-grading/lld.md §10.4).
//
// This is deliberately NOT components/TradeCard.tsx. The grading session mixes
// cards from today's trade engine and the value core, and the grader must not
// be able to tell which produced a card. TradeCard renders the things that
// would give it away — meters, lanes, "They're interested", narrative copy —
// so this card renders exactly the GradingTrade fields the server's neutral
// formatter emits (partner name, two asset lists, a value per asset) and
// nothing else. mobile/tests/check-blind-grading.js pins the import list and
// scans this file for engine-identifying tokens.
//
// Chalkline only: Card, Text, TickLabel, Badge/PositionBadge and theme tokens.
// No hex literals, no flare (nothing here is an informational highlight), no
// radius above 8, no emoji, no gradients.

type PlayerPos = 'QB' | 'RB' | 'WR' | 'TE';
const PLAYER_POS: readonly PlayerPos[] = ['QB', 'RB', 'WR', 'TE'];
const isPlayerPos = (p: string): p is PlayerPos => (PLAYER_POS as readonly string[]).includes(p);

// `title-compact` composition (docs/design/design-system.md → Typography):
// title's family/weight at body-sm's metrics, for the two-column canvas only.
const NAME_STYLE = [
  type.title,
  { fontSize: type.bodySm.fontSize, lineHeight: type.bodySm.lineHeight },
];

const sumValues = (assets: GradingAsset[]): number =>
  assets.reduce((acc, a) => acc + (a.value ?? 0), 0);

function AssetRow({ asset }: { asset: GradingAsset }) {
  const isPick = asset.position === 'PICK';
  // Picks show neither team nor age; players fall back to 'FA' when teamless.
  const meta = isPick
    ? null
    : asset.age != null
      ? `${asset.nfl_team ?? 'FA'} · ${asset.age}`
      : (asset.nfl_team ?? 'FA');
  return (
    <View style={styles.assetRow}>
      <Text scale="body" style={NAME_STYLE} numberOfLines={2}>{asset.name}</Text>
      <View style={styles.metaRow}>
        {isPlayerPos(asset.position)
          ? <PositionBadge pos={asset.position} />
          : <Badge label={isPick ? 'PICK' : asset.position} />}
        {meta ? <Text variant="data" style={styles.metaText}>{meta}</Text> : null}
        <View style={styles.spacer} />
        <Text variant="data">{asset.value == null ? '—' : String(asset.value)}</Text>
      </View>
    </View>
  );
}

function Column({ label, assets }: { label: string; assets: GradingAsset[] }) {
  return (
    <View style={styles.column}>
      <TickLabel>{label}</TickLabel>
      <View style={styles.assets}>
        {assets.map((a) => <AssetRow key={a.id} asset={a} />)}
      </View>
      <View style={styles.footer}>
        <Text variant="label">TOTAL</Text>
        <Text variant="data">{String(sumValues(assets))}</Text>
      </View>
    </View>
  );
}

export default function GradingCard({ trade }: { trade: GradingTrade }) {
  return (
    <Card>
      <View style={styles.header}>
        <Text variant="label">TRADE WITH</Text>
        <Text variant="title" numberOfLines={1}>{trade.partner_name}</Text>
      </View>
      {/* GIVE-LEFT / GET-RIGHT, the house rule every two-sided surface obeys
          (#209/#216; pinned elsewhere by check-dna-side-order.js). */}
      <View style={styles.columns}>
        <Column label="You give" assets={trade.give} />
        <View style={styles.rule} />
        <Column label="You get" assets={trade.receive} />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  header: { gap: space.xs, marginBottom: space.md },
  columns: { flexDirection: 'row', gap: space.md },
  column: { flex: 1, minWidth: 0, gap: space.sm },
  rule: { width: 1, backgroundColor: ink.line },
  assets: { gap: space.sm },
  assetRow: { gap: space.xs },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: space.sm, minWidth: 0 },
  metaText: { color: chalk.dim, flexShrink: 1 },
  spacer: { flex: 1 },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: ink.line,
    paddingTop: space.sm,
    marginTop: space.xs,
  },
});

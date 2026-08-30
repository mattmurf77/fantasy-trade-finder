import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import MemberEnteredMarker from './MemberEnteredMarker';
import PositionChip from './PositionChip';
import TierBadge from './TierBadge';
import { Button, Card, Icon, TickLabel } from './chalkline';
import { CalcPlayer } from '../data/calcTypes';
import { ink, type, space, radii } from '../theme/chalkline';
import type { Tier } from '../shared/types';

interface Props {
  title: string;
  teamName: string;
  players: CalcPlayer[];
  /** Value of each selected player on the viewer-relevant board. */
  valueOf: (p: CalcPlayer) => number;
  /** #263 — pick-value ladder tier for the row's display (replaces the raw
   *  `valueOf` number). #320/D-320-1 superseded #263's "picks keep their
   *  numeric value" carve-out: the in-league caller now resolves owned
   *  picks too (server-computed off the pick's discounted pool_value).
   *  Omitted or null for a given row still falls back to the numeric
   *  value — old servers, unpriced rows, or a caller that hasn't wired
   *  tier data. */
  tierOf?: (p: CalcPlayer) => Tier | null | undefined;
  accent: string;
  onAdd: () => void;
  onRemove: (id: string) => void;
  /** UI-test harness id for the Add button (registry: components/CLAUDE.md). */
  addTestID?: string;
  /** W3 M-C (D17) — the league whose assignment grid holds any asserted
   *  pick on this side. Only the In-league mount passes it; without it the
   *  marker has no correction target and renders nothing. */
  leagueId?: string | null;
  /** #384 — column mode. The merged calculator layout stands the two sides
   *  side by side, which halves the available width to roughly 165pt on a
   *  375pt screen. The stacked row (44pt chip slot + name + tier + a 32pt
   *  remove target) does not fit in that, so column mode re-flows each row
   *  to two lines and drops the fixed chip slot.
   *
   *  It does NOT shrink type: the Chalkline 11pt floor holds, and the 32pt
   *  remove control keeps its hit area (it gains `hitSlop` rather than
   *  losing size). Only layout changes — no row is removed, no value is
   *  hidden, and `MemberEnteredMarker` still renders. */
  compact?: boolean;
  /** #384 W4 — spotlight target for the tour's "add a player" beat. The
   *  guide measures a real node, so the ref must reach the actual button;
   *  registering a target that can never measure is the "points at nothing"
   *  defect the script lint exists to catch. */
  addRef?: React.RefObject<View | null>;
  /** #412 — host-supplied content rendered directly beneath "Add player",
   *  inside the same Card. Presentational only: TradeSide reads no flag and
   *  owns no handler. Absent ⇒ byte-identical for the receive column, the
   *  stacked page, FeaturedTradeWindow and the #270 experiment. */
  belowAdd?: React.ReactNode;
}

// One side of a hand-built trade (You send / You receive) for the Trade
// Calculator: selected players with their pick-value tier + an add button.
export default function TradeSide({ title, teamName, players, valueOf, tierOf, accent, onAdd, onRemove, addTestID, leagueId, compact, addRef, belowAdd }: Props) {
  return (
    <Card>
      <View style={styles.inner}>
        <View style={[styles.header, compact && styles.headerCompact]}>
          <TickLabel color={accent}>{title}</TickLabel>
          {/* Clamped in COLUMN mode only. The stacked page is unchanged
              behind the flag: a long "@username" wrapped there before and
              must keep wrapping, not start ellipsizing. */}
          <Text style={type.bodySm} numberOfLines={compact ? 1 : undefined}>{teamName}</Text>
        </View>

        {players.length === 0 ? (
          <Text style={styles.empty}>No players yet — add someone to start the trade.</Text>
        ) : (
          players.map((p) => (
            <View key={p.id} style={[styles.row, compact && styles.rowCompact]}>
              {/* #320 — fixed-width chip slot: PICK (4 chars) is wider than
                  QB/RB/WR/TE, so a self-sized chip pushed pick rows' names
                  right. The slot pins one name x-position for every row.
                  PositionChip itself is untouched — it's shared with
                  Tiers/Trades/Matches (no drive-by). Same 44pt constant as
                  PlayerPickerModal's chipCol; keep the two in lockstep
                  (mobile/tests/check-picker-chip-alignment.js). */}
              {compact ? null : (
                <View style={styles.chipCol}>
                  <PositionChip position={p.pos} size="sm" />
                </View>
              )}
              <View style={styles.info}>
                {/* #411 — line 1 is the NAME ALONE in column mode. The
                    position chip used to share it, leaving ~67pt for the
                    name and ellipsizing all but one of the top 100 dynasty
                    assets; it moved to the meta line below (it is MOVED,
                    never dropped — the hex is a cross-client data
                    encoding). Still one line: wrapping was declined. */}
                {compact ? (
                  <Text style={[type.title, styles.compactName]} numberOfLines={1}>
                    {p.name}
                  </Text>
                ) : (
                  <Text style={type.title}>{p.name}</Text>
                )}
                <View style={compact ? styles.compactMetaLine : undefined}>
                  {compact ? (
                    // #411 — the chip leads the meta line. flexShrink 0: a
                    // data encoding is never the thing that yields.
                    <View style={styles.compactChipSlot}>
                      <PositionChip position={p.pos} size="sm" />
                    </View>
                  ) : null}
                  {/* flexShrink so this line yields before the tier badge:
                      without it the badge is pushed out of the ~97pt of
                      info width a 375pt screen leaves, which is the price
                      silently disappearing again. #411 adds minWidth 0 so
                      it can actually reach zero — with the chip now sharing
                      the line, the chip+badge pair is the binding
                      constraint and the TEXT must be the only yielder. */}
                  <Text
                    style={[type.bodySm, compact && styles.compactMetaText]}
                    numberOfLines={compact ? 1 : undefined}
                  >
                    {p.pick ? 'Draft capital' : `${p.nflTeam} · ${p.age} yrs`}
                  </Text>
                  {/* Column mode has no room for a trailing value column, so
                      the tier/value rides the meta line. It is MOVED, never
                      dropped — a narrower row that silently stops pricing an
                      asset would be worse than a wrapped one. #411: `sm` in
                      COLUMN MODE ONLY — the chip's arrival costs the line
                      ~30pt and `md` would push the badge's right edge under
                      Card's overflow:'hidden'. The stacked mount below keeps
                      the default `md`. */}
                  {compact
                    ? (() => {
                        const t = tierOf?.(p);
                        return (
                          <View style={styles.compactPriceSlot}>
                            {t ? (
                              <TierBadge tier={t} size="sm" />
                            ) : (
                              <Text style={type.data}>{valueOf(p).toLocaleString()}</Text>
                            )}
                          </View>
                        );
                      })()
                    : null}
                </View>
                {/* D17 — priced surface 4 of 5: the calculator's pick rows.
                    UNCONDITIONAL by design; the marker self-gates on the
                    flag AND `source === 'user'`, so wrapping this in a
                    ternary would only create a way for a priced assertion
                    to render as platform truth. */}
                <MemberEnteredMarker
                  source={p.pickSource}
                  pickId={p.id}
                  season={p.pickSeason}
                  leagueId={leagueId}
                  testID={`calc.member-entered.${p.id}`}
                />
              </View>
              {compact ? null : (() => {
                const t = tierOf?.(p);
                return t ? (
                  // TierBadge hardcodes alignSelf:'flex-start' (fine in its
                  // usual flex-wrap header contexts); this row centers its
                  // children, so re-center the badge itself rather than
                  // let it fight the row's alignItems.
                  <View style={styles.tierSlot}>
                    <TierBadge tier={t} />
                  </View>
                ) : (
                  <Text style={type.data}>{valueOf(p).toLocaleString()}</Text>
                );
              })()}
              <Pressable
                onPress={() => onRemove(p.id)}
                // Column mode narrows the row, not the target: the control
                // keeps its 32pt box and gains slop instead of shrinking.
                hitSlop={compact ? 12 : 6}
                style={({ pressed }) => [styles.remove, pressed && styles.removePressed]}
                accessibilityRole="button"
                accessibilityLabel={`Remove ${p.name}`}
              >
                <Icon name="x" size={16} />
              </Pressable>
            </View>
          ))
        )}

        {/* Wrapped rather than ref-forwarded: `Button` is shared across the
            app and does not forward refs, and adding forwardRef to it for one
            spotlight would be a drive-by change to every caller. A wrapper
            View measures the same box the spotlight needs. */}
        <View ref={addRef}>
          <Button label="Add player" variant="secondary" compact testID={addTestID} onPress={onAdd} style={styles.addBtn} />
        </View>
        {/* #412 — the host's slot, UNDER the Add button ("move more offers
            underneath the add a player button"). Above it would read as a
            second Add affordance. `styles.inner`'s gap spaces it. */}
        {belowAdd}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  inner: { gap: space.sm },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  empty: { ...type.bodySm, paddingVertical: space.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  info: { flex: 1 },
  // #320 — fixed chip slot so PICK/QB/RB/WR/TE rows all start the name
  // column at the same x. 44 clears the sm PICK chip; same constant in
  // PlayerPickerModal.chipCol.
  chipCol: { width: 44, alignItems: 'flex-start' },
  remove: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  removePressed: { backgroundColor: ink.ink3 },
  addBtn: { marginTop: space.xs },
  tierSlot: { alignSelf: 'center' },
  // #384 column mode. Type sizes are untouched (Chalkline 11pt floor); only
  // the row's flow changes — chip+name on line 1, meta+value on line 2.
  headerCompact: { flexDirection: 'column', alignItems: 'flex-start', gap: 2 },
  rowCompact: { alignItems: 'flex-start', gap: space.xs },
  // #411 — one step down the Chalkline scale (16/22 → 13/18) so the compact
  // name clears the 97.5pt info column on far more rows. Weight and color
  // stay `type.title`'s: the name is still the row's primary identifier,
  // just smaller. Sizes come from `type.bodySm`, never a literal — the 11pt
  // floor (docs/design/design-system.md) is 2pt below this and is not
  // approached.
  compactName: {
    fontSize: type.bodySm.fontSize,
    lineHeight: type.bodySm.lineHeight,
    flexShrink: 1,
  },
  compactMetaText: { flexShrink: 1, minWidth: 0 },
  // #411 — the meta line's two DATA ENCODINGS (position hex, tier label).
  // Neither shrinks or clips: the meta text yields first, always.
  compactChipSlot: { flexShrink: 0 },
  compactPriceSlot: { flexShrink: 0 },
  compactMetaLine: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.xs,
  },
});

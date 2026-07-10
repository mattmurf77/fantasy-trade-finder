import React, { useMemo } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  SectionList,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import PositionChip from './PositionChip';
import { Button, TickLabel } from './chalkline';
import type { CalcValueRow } from '../api/calc';
import {
  chalk,
  ice,
  ink,
  radii,
  scrim,
  shadowSheet,
  space,
  type,
} from '../theme/chalkline';

// Swap-player sheet (feedback #86). Opened from a suggested trade card's
// per-player swap affordance; replaces one player with another from the
// SAME roster (give side → the user's roster, receive side → the
// counterparty's). Two sections, per the owner's spec:
//   1. "Suggested swaps" — the roster players closest in consensus value
//      to the player being replaced (a keeps-it-fair shortlist).
//   2. "Full roster" — everyone else, grouped QB → RB → WR → TE (→ Other).
// Values come from /api/trade/values (consensus board — same numbers the
// calculator picker shows). Sheet construction mirrors PlayerPickerModal
// (components.md → Sheets, modals, menus).

const SUGGESTED_COUNT = 6;
const POS_ORDER = ['QB', 'RB', 'WR', 'TE'] as const;

interface SheetSection {
  key: string;
  /** Big section banner (TickLabel) — 'SUGGESTED SWAPS' / 'FULL ROSTER'. */
  banner: string | null;
  /** Muted helper line under the banner. */
  bannerHint?: string;
  /** Position-group label within the full roster ('QB', 'RB', …). */
  posLabel: string | null;
  data: CalcValueRow[];
}

interface Props {
  visible: boolean;
  /** Player being replaced. `value` null when they're not in the consensus
   *  pool (suggestions are skipped then — only the full roster renders). */
  replacing: { name: string; value: number | null } | null;
  /** Whose roster the candidates come from, e.g. "your roster" / "@handle". */
  rosterLabel: string;
  /** Pool-valued players on that roster, minus everyone already in the trade. */
  candidates: CalcValueRow[];
  loading?: boolean;
  onPick: (p: CalcValueRow) => void;
  onClose: () => void;
}

export default function SwapPlayerSheet({
  visible,
  replacing,
  rosterLabel,
  candidates,
  loading = false,
  onPick,
  onClose,
}: Props) {
  const replacingValue = replacing?.value ?? null;

  const sections = useMemo<SheetSection[]>(() => {
    // Suggested = closest by |consensus value delta| to the outgoing player.
    let suggested: CalcValueRow[] = [];
    if (replacingValue != null) {
      suggested = [...candidates]
        .sort(
          (a, b) =>
            Math.abs(a.value - replacingValue) - Math.abs(b.value - replacingValue),
        )
        .slice(0, SUGGESTED_COUNT);
    }
    const suggestedIds = new Set(suggested.map((p) => p.id));
    const rest = candidates.filter((p) => !suggestedIds.has(p.id));

    const byPos = new Map<string, CalcValueRow[]>();
    for (const p of rest) {
      const key = (POS_ORDER as readonly string[]).includes(p.position)
        ? p.position
        : 'Other';
      const bucket = byPos.get(key);
      if (bucket) bucket.push(p);
      else byPos.set(key, [p]);
    }

    const out: SheetSection[] = [];
    if (suggested.length > 0) {
      out.push({
        key: 'suggested',
        banner: 'SUGGESTED SWAPS',
        bannerHint: replacing
          ? `Closest in value to ${replacing.name} — keeps the trade fair`
          : undefined,
        posLabel: null,
        data: suggested,
      });
    }
    let firstGroup = true;
    for (const pos of [...POS_ORDER, 'Other']) {
      const rows = (byPos.get(pos) ?? []).sort((a, b) => b.value - a.value);
      if (rows.length === 0) continue;
      out.push({
        key: `pos-${pos}`,
        banner: firstGroup ? 'FULL ROSTER' : null,
        posLabel: pos,
        data: rows,
      });
      firstGroup = false;
    }
    return out;
  }, [candidates, replacing, replacingValue]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} accessibilityLabel="Close" />
      <View style={styles.sheet}>
        <SafeAreaView style={styles.sheetInner} edges={['bottom']}>
          <View style={styles.grabber} />
          <View style={styles.header}>
            <View style={styles.headerText}>
              <Text style={type.heading} numberOfLines={1}>
                Replace {replacing?.name ?? 'player'}
              </Text>
              <Text style={type.bodySm}>from {rosterLabel}</Text>
            </View>
            <Button label="Cancel" variant="ghost" onPress={onClose} />
          </View>

          {loading ? (
            <View style={styles.loadingRow}>
              <ActivityIndicator color={ice.base} />
              <Text style={type.bodySm}>Loading roster values…</Text>
            </View>
          ) : candidates.length === 0 ? (
            <Text style={styles.empty}>
              No other valued players found on this roster.
            </Text>
          ) : (
            <SectionList
              sections={sections}
              keyExtractor={(p) => p.id}
              stickySectionHeadersEnabled={false}
              contentContainerStyle={{ paddingBottom: space.xl }}
              renderSectionHeader={({ section }) => (
                <View style={styles.sectionHeader}>
                  {section.banner ? (
                    <View style={styles.banner}>
                      <TickLabel>{section.banner}</TickLabel>
                      {section.bannerHint ? (
                        <Text style={type.bodySm}>{section.bannerHint}</Text>
                      ) : null}
                    </View>
                  ) : null}
                  {section.posLabel ? (
                    <Text style={[type.label, styles.posLabel]}>{section.posLabel}</Text>
                  ) : null}
                </View>
              )}
              renderItem={({ item, section }) => {
                const showDelta = section.key === 'suggested' && replacingValue != null;
                const delta = showDelta ? item.value - replacingValue : 0;
                return (
                  <Pressable
                    style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
                    onPress={() => onPick(item)}
                    accessibilityRole="button"
                    accessibilityLabel={`Swap in ${item.name}`}
                  >
                    <PositionChip position={item.position} size="sm" />
                    <View style={styles.info}>
                      <Text style={type.title} numberOfLines={1}>{item.name}</Text>
                      <Text style={type.bodySm}>
                        {item.team ?? 'FA'}
                        {item.age != null ? ` · ${item.age} yo` : ''}
                      </Text>
                    </View>
                    <View style={styles.values}>
                      <Text style={type.data}>{Math.round(item.value).toLocaleString()}</Text>
                      {showDelta ? (
                        <Text style={styles.delta}>
                          {delta >= 0 ? '+' : ''}{Math.round(delta).toLocaleString()}
                        </Text>
                      ) : null}
                    </View>
                  </Pressable>
                );
              }}
            />
          )}
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '85%',
    backgroundColor: ink.ink2,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    borderWidth: 1,
    borderColor: ink.line,
    ...shadowSheet,
  },
  sheetInner: { paddingHorizontal: space.lg },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    borderRadius: radii.xs,
    backgroundColor: ink.lineStrong,
    marginTop: space.sm,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
  },
  headerText: { flex: 1, gap: space.xs },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.xl,
  },
  empty: {
    ...type.bodySm,
    textAlign: 'center',
    paddingVertical: space.xl,
  },
  sectionHeader: {
    paddingTop: space.md,
    paddingBottom: space.xs,
    gap: space.sm,
    backgroundColor: ink.ink2,
  },
  banner: { gap: space.xs },
  posLabel: { color: chalk.base },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  rowPressed: { backgroundColor: ink.ink3 },
  info: { flex: 1 },
  values: { alignItems: 'flex-end' },
  delta: { ...type.data, color: chalk.dim },
});

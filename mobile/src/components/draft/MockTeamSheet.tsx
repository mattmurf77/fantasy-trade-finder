// #326 — the mock-draft room's "Your team" sheet.
//
// A Modal bottom sheet (components.md § Sheets — ink2 fill, top radius
// radii.md, 1px line border, solid scrim, 32×4 grabber), NEVER navigation:
// the draft screen stays mounted underneath and the clock state is intact
// on dismiss. Mounted by MockDraftScreen as a sibling of PlayerContextMenu /
// AnchorSheet, inside the screen's single return.
//
// Two sections, in the SwapPlayerSheet sectioned-picker construction
// (TickLabel banners; rows = position chip + name + right-aligned data
// value). Distinct banners keep real-roster vs simulation legible:
//   1. ROSTER — the user's real dynasty roster grouped by position, from
//      the shared power-rankings read (react-query key
//      ['league-power-rankings', leagueId, 'consensus'] — the same source
//      InLeagueCalculator uses, usually already cached). The caller's team
//      is the payload's `is_you` row — the server's rendering of the
//      caller's league identity (ADR-012). Loading/error get honest
//      one-line copy, no spinner states beyond the standing pattern.
//   2. DRAFTED IN THIS MOCK — `my_picks` with position + tier (#323's R-7
//      rendering: the tier comes off `pick.tier`, server-computed, through
//      TierBadge — never client-derived).
//
// v1 always shows the SESSION USER's team, including manual-mode turns
// taken for another team (per-team rosters deferred — PRD §4). "Mine" here
// is `my_picks`, the server's user_owner_id filter — never a `by` read
// (#305 / R-16).

import React, { useMemo } from 'react';
import {
  Modal,
  Pressable,
  SectionList,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';

import PositionChip from '../PositionChip';
import TierBadge from '../TierBadge';
import { Button, TickLabel } from '../chalkline';
import { getPowerRankings } from '../../api/league';
import type { MockPick } from '../../api/mockDraft';
import type { Tier } from '../../shared/types';
import {
  chalk,
  ink,
  radii,
  scrim,
  shadowSheet,
  space,
  type,
} from '../../theme/chalkline';

const POS_ORDER = ['QB', 'RB', 'WR', 'TE'] as const;

interface SheetRow {
  key: string;
  name: string;
  position: string;
  /** Muted secondary line — NFL team for roster rows, slot for picks. */
  sub: string | null;
  tier: Tier | null;
  /** Numeric fallback for a roster row without a tier (old server). */
  value: number | null;
}

interface SheetSection {
  key: string;
  banner: string | null;
  /** Honest one-line state (loading / error / empty) under the banner. */
  note: string | null;
  posLabel: string | null;
  data: SheetRow[];
}

interface Props {
  visible: boolean;
  leagueId: string | null | undefined;
  myPicks: MockPick[];
  onClose: () => void;
}

export default function MockTeamSheet({ visible, leagueId, myPicks, onClose }: Props) {
  const powerQ = useQuery({
    queryKey: ['league-power-rankings', leagueId, 'consensus'],
    queryFn: () => getPowerRankings(leagueId as string, 'consensus'),
    enabled: visible && !!leagueId,
    staleTime: 5 * 60_000,
  });

  const sections = useMemo<SheetSection[]>(() => {
    const out: SheetSection[] = [];

    // ── 1. The real roster, grouped by position ─────────────────────────
    const myTeam = powerQ.data?.teams?.find((t) => t.is_you) ?? null;
    const note = powerQ.isLoading
      ? 'Loading your roster…'
      : powerQ.isError
        ? 'Couldn’t load your roster right now.'
        : myTeam == null
          ? 'We couldn’t find your team in this league.'
          : myTeam.roster.length === 0
            ? 'No players on this roster.'
            : null;
    out.push({ key: 'roster', banner: 'ROSTER', note, posLabel: null, data: [] });
    if (myTeam) {
      const byPos = new Map<string, SheetRow[]>();
      for (const p of myTeam.roster) {
        const key = (POS_ORDER as readonly string[]).includes(p.position)
          ? p.position
          : 'Other';
        const row: SheetRow = {
          key: `roster-${p.player_id}`,
          name: p.name,
          position: p.position,
          sub: p.team,
          tier: p.tier ?? null,
          value: p.value,
        };
        const bucket = byPos.get(key);
        if (bucket) bucket.push(row);
        else byPos.set(key, [row]);
      }
      for (const pos of [...POS_ORDER, 'Other']) {
        const rows = byPos.get(pos) ?? [];
        if (rows.length === 0) continue;
        out.push({ key: `roster-${pos}`, banner: null, note: null, posLabel: pos, data: rows });
      }
    }

    // ── 2. This mock's picks ────────────────────────────────────────────
    out.push({
      key: 'mock',
      banner: 'DRAFTED IN THIS MOCK',
      note: myPicks.length === 0 ? 'No picks yet — your turn will come.' : null,
      posLabel: null,
      data: myPicks.map((p) => ({
        key: `mock-${p.pick_no}`,
        name: p.name || p.player_id,
        position: p.position,
        sub: `${p.round}.${String(p.slot).padStart(2, '0')}`,
        // R-7 — server-computed; absent (old server) reads as null and
        // TierBadge no-ops. Never derived here.
        tier: p.tier ?? null,
        value: null,
      })),
    });
    return out;
  }, [powerQ.data, powerQ.isLoading, powerQ.isError, myPicks]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable
        style={styles.backdrop}
        onPress={onClose}
        accessibilityRole="button"
        accessibilityLabel="Close your team"
      />
      <View testID="mock-draft.team-sheet" style={styles.sheet}>
        <SafeAreaView style={styles.sheetInner} edges={['bottom']}>
          <Pressable onPress={onClose} accessibilityRole="button" accessibilityLabel="Close">
            <View style={styles.grabber} />
          </Pressable>
          <View style={styles.header}>
            <Text style={type.heading} accessibilityRole="header">
              Your team
            </Text>
            <Button
              label="Close"
              variant="ghost"
              testID="mock-draft.team-sheet.close"
              onPress={onClose}
            />
          </View>

          <SectionList
            sections={sections}
            keyExtractor={(r) => r.key}
            stickySectionHeadersEnabled={false}
            contentContainerStyle={{ paddingBottom: space.xl }}
            renderSectionHeader={({ section }) => (
              <View style={styles.sectionHeader}>
                {section.banner ? <TickLabel>{section.banner}</TickLabel> : null}
                {section.note ? <Text style={styles.note}>{section.note}</Text> : null}
                {section.posLabel ? (
                  <Text style={[type.label, styles.posLabel]}>{section.posLabel}</Text>
                ) : null}
              </View>
            )}
            renderItem={({ item }) => (
              <View style={styles.row}>
                <PositionChip position={item.position} size="sm" />
                <View style={styles.info}>
                  <Text style={type.title} numberOfLines={1}>
                    {item.name}
                  </Text>
                  {item.sub ? <Text style={type.bodySm}>{item.sub}</Text> : null}
                </View>
                <View style={styles.values}>
                  {/* #277 rule: the row's value reads as its tier label when
                      the server sent one; numeric fallback only for a
                      roster row from an old-server payload. */}
                  {item.tier ? (
                    <View style={styles.tierSlot}>
                      <TierBadge tier={item.tier} size="sm" />
                    </View>
                  ) : item.value != null ? (
                    <Text style={type.data}>{Math.round(item.value).toLocaleString()}</Text>
                  ) : null}
                </View>
              </View>
            )}
          />
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
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: space.sm,
  },
  sectionHeader: { paddingTop: space.md, gap: 2 },
  note: { ...type.bodySm, color: chalk.dim },
  posLabel: { color: chalk.dim, paddingTop: space.xs },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: space.xs,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    minHeight: 44,
  },
  info: { flex: 1 },
  values: { alignItems: 'flex-end' },
  tierSlot: { alignItems: 'flex-end' },
});

// Shared Draft-surface rows — extracted from DraftRoomScreen, VERBATIM.
//
// draft-extensions W2 (mock draft UI, placement C). The mock's board is the
// same three sections over the same entry shapes as `GET /api/draft/board`
// (`state_payload()` returns the I-6 vocabulary deliberately, lld §2.3), so
// the mock surface renders the ROOM's rows rather than a parallel set. That
// is only honest if there is exactly ONE copy of each row — a second copy
// would drift, and "the same list" would stop being true by construction.
//
// Nothing here is redesigned. The styles, the a11y vocabulary (long-press +
// an `accessibilityActions` custom action — the shipped TradeCard idiom;
// deliberately NO "⋯" glyph, which would be net-new to Chalkline and needs
// a components.md spec under ADR-004/005), the D7 "No value" treatment and
// the my-board fallback copy are the room's, moved not rewritten.
//
// NOTE on what is NOT here. `UndraftedRowView` stays in
// `screens/DraftRoomScreen.tsx` and is EXPORTED from there, because
// `backend/tests/test_draft_extensions_w1.py` pins W1's kill switch and its
// per-player testID to that file by source text. Moving the row would have
// been the tidier layering and would have broken a green backend test this
// wave is not allowed to touch — so the mock imports the room's row rather
// than owning a second copy. The reuse is real either way; only the file it
// lives in is the compromise.

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  chalk,
  ice,
  ink,
  position as positionColor,
  radii,
  space,
  type,
} from '../../theme/chalkline';
import type { UndraftedRow } from '../../api/draft';

// ── shared copy ──────────────────────────────────────────────────────────
// Lives here so the room and the mock cannot say different things about
// the same list.

export const MY_BOARD_FALLBACK_COPY =
  'Ordered by your board. Anyone you haven’t ranked falls back to the consensus value.';

export const NO_CONSENSUS_VALUE_COPY =
  'Some rookies have no consensus value yet. They’re listed last rather than hidden — a prospect with no price is still on the board.';

// ── helpers ──────────────────────────────────────────────────────────────

export function positionOf(pos: string): string {
  switch ((pos || '').toUpperCase()) {
    case 'QB': return positionColor.qb;
    case 'RB': return positionColor.rb;
    case 'WR': return positionColor.wr;
    case 'TE': return positionColor.te;
    default:   return chalk.dim;
  }
}

/** `1.04`, or `R1` when the platform has not published an order. */
export function slotLabel(slot: { slot: number | null; round: number }): string {
  if (slot.slot == null) return `R${slot.round}`;
  return `${slot.round}.${String(slot.slot).padStart(2, '0')}`;
}

// ── Consensus | My board ─────────────────────────────────────────────────

export function BasisChip({
  label,
  active,
  onPress,
  testID,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  testID: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={({ pressed }) => [
        draftRow.basisChip,
        active && draftRow.basisChipActive,
        pressed && { backgroundColor: ink.ink3 },
      ]}
    >
      <Text style={[type.label, active ? draftRow.basisChipTextActive : null]}>
        {label}
      </Text>
    </Pressable>
  );
}

// ── styles (moved from DraftRoomScreen, unchanged) ───────────────────────

export const draftRow = StyleSheet.create({
  orderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    paddingVertical: space.sm,
  },
  slotCell: { ...type.data, color: chalk.dim, width: 48 },
  orderMain: { flex: 1, gap: 2 },
  ownerText: { ...type.bodySm, color: chalk.base },
  tradedTag: { ...type.bodySm, fontSize: 11, color: chalk.faint },
  pickedText: { ...type.bodySm, color: chalk.dim },
  onTheClock: { ...type.bodySm, color: chalk.faint },

  basisRow: { flexDirection: 'row', gap: space.sm },
  basisChip: {
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  basisChipActive: { backgroundColor: ink.ink3, borderColor: ice.base },
  basisChipTextActive: { color: chalk.base },
  fallbackNote: {
    ...type.bodySm,
    color: chalk.base,
    backgroundColor: ink.ink1,
    borderColor: ink.line,
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },

  undraftedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    paddingVertical: space.sm,
  },
  // Mock only — the room never marks a row selected.
  undraftedRowSelected: { backgroundColor: ink.ink1, borderBottomColor: ice.base },
  rankCell: { ...type.data, color: chalk.faint, width: 28 },
  playerName: { ...type.bodySm, color: chalk.base },
  playerMeta: { ...type.bodySm, fontSize: 11, color: chalk.faint },
  valueCell: { ...type.data, color: chalk.base },
  noValueCell: { ...type.bodySm, fontSize: 11, color: chalk.faint },
  rowAction: {
    ...type.label,
    color: ice.base,
    borderWidth: 1,
    borderColor: ice.base,
    borderRadius: radii.xs,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
  },
});

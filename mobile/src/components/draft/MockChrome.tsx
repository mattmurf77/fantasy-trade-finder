// Mock-mode chrome — the segmented mode switch and the persistent mode
// marker (draft-extensions W2, placement option C).
//
// ── Why the rail is a hard requirement, not polish ──────────────────────
// The design pass recommended option B and argued AGAINST C on one serious
// ground: the Draft Room PRINTS its own no-platform-writes guarantee
// ("Picks are made on the platform — Fantasy Trade Finder never drafts for
// you", D9), and a mode switch sitting above that sentence makes it
// ambiguous on the one screen where mistaking a simulation for the real
// draft can cost a real pick. The operator chose C anyway. The obligations
// that answer the objection are structural, and they live here:
//
//   1. `MockRail` renders OUTSIDE the host ScrollView, so it is visible at
//      EVERY scroll position — a screenshot of any part of a mock surface
//      contains the word MOCK. A rail inside the scroll would satisfy the
//      letter of "persistent marker" and fail its point.
//   2. Flare, not ice. ADR-005 reserves ice for actions; flare is the
//      informational highlight, and "this is a simulation" is exactly that.
//      It is also the only accent the real room never uses at full width,
//      so the two modes cannot be confused at a glance.
//   3. Hosts must render the rail in EVERY mock sub-state (loading, the
//      entry card, every honest refusal, the live board, the confirm step
//      and the recap). That is pinned by
//      `mobile/tests/check-mock-mode-marker.js`, which fails the build if a
//      mock branch renders without it.
//
// The corollary lives in the hosts, not here: in mock mode the platform
// deep link and the "never drafts for you" note are NOT RENDERED AT ALL,
// so the guarantee can never appear above a board that accepts picks.

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { chalk, flare, ice, ink, radii, space, type } from '../../theme/chalkline';

export type DraftMode = 'real' | 'mock';

/** The always-visible "this is a simulation" marker. */
export function MockRail({
  status,
  testID = 'mock.rail',
}: {
  /** Right-hand line — the sub-state in plain words. Defaults to the
   *  boundary statement itself, which is what most frames want. */
  status?: string;
  testID?: string;
}) {
  return (
    <View
      testID={testID}
      accessible
      accessibilityRole="header"
      accessibilityLabel={`Mock draft. ${status ?? "Not your league's real draft."}`}
      style={styles.rail}
    >
      <Text style={styles.railLabel}>Mock draft</Text>
      <Text style={styles.railStatus} numberOfLines={1}>
        {status ?? 'not your league’s real draft'}
      </Text>
    </View>
  );
}

/** `Real draft | Mock` — the option-C entry, pinned above the scroll so it
 *  never scrolls out from under the rail it controls. */
export function DraftModeToggle({
  mode,
  onMode,
  testIDPrefix = 'draft-room.mode',
}: {
  mode: DraftMode;
  onMode: (m: DraftMode) => void;
  testIDPrefix?: string;
}) {
  return (
    <View style={styles.seg} accessibilityRole="tablist">
      <Segment
        testID={`${testIDPrefix}.real`}
        label="Real draft"
        active={mode === 'real'}
        accent={ice.base}
        onPress={() => onMode('real')}
      />
      <Segment
        testID={`${testIDPrefix}.mock`}
        label="Mock"
        active={mode === 'mock'}
        accent={flare.base}
        onPress={() => onMode('mock')}
      />
    </View>
  );
}

function Segment({
  label,
  active,
  accent,
  onPress,
  testID,
}: {
  label: string;
  active: boolean;
  accent: string;
  onPress: () => void;
  testID: string;
}) {
  return (
    <Pressable
      testID={testID}
      onPress={onPress}
      accessibilityRole="tab"
      accessibilityLabel={label}
      accessibilityState={{ selected: active }}
      style={({ pressed }) => [
        styles.segItem,
        active && { backgroundColor: ink.ink3, borderBottomColor: accent },
        pressed && { backgroundColor: ink.ink2 },
      ]}
    >
      <Text style={[type.label, active ? styles.segTextActive : null]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  rail: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    // Flare wash + a full-width bottom edge: legible as "mock" in a crop
    // that contains nothing else.
    backgroundColor: 'rgba(240,80,140,0.09)',
    borderBottomWidth: 1,
    borderBottomColor: flare.base,
    paddingHorizontal: space.lg,
    paddingVertical: space.sm,
  },
  railLabel: {
    ...type.label,
    color: flare.base,
    letterSpacing: 1,
  },
  railStatus: { ...type.bodySm, fontSize: 11, color: chalk.dim, flex: 1, textAlign: 'right' },

  seg: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
    marginHorizontal: space.lg,
    marginTop: space.md,
  },
  segItem: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  segTextActive: { color: chalk.base },
});

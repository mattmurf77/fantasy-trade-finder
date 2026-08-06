import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';

import Icon from './chalkline/Icon';
import { chalk, flare, ice, ink, radii, space, type } from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import {
  CONSOLIDATED_VIEW,
  SCOPE_OPTIONS,
  scopeEmptyCopy,
  useRookieScope,
} from '../state/rookieScope';
import type { ScopedEmpty } from '../api/rankings';

// THE rookie-scope control (rookie-draft M2). ONE component rendered by
// every ranking surface — Pick Anchors, the Tiers board, Quick Set, Quick
// Rank, Overall ranks and Trios — so the six can never diverge in labels,
// behaviour, testIDs or state (the rankChooserModel lesson applied to a
// control instead of a chooser).
//
// Renders NOTHING when `ranks.rookie_subset` is off: no pills, no link, no
// entry point to the consolidated view. That is the whole feature's kill
// switch on the client side, and it pairs with the server never parsing the
// `scope` parameter — either half alone is sufficient.
//
// Construction: the #133 PositionTabs scope-pill precedent (hairline
// segmented group, active segment = ink-3 fill + 2px underline). The
// underline is ice for "All players" (an action, not a data encoding) and
// flare for "Rookies" — flare is the informational-highlight accent
// (ADR-005), which is exactly what "you are looking at a subset" is.
//
// When the rookie segment is active the control also carries the entry to
// the consolidated cross-position rookie view (operator decision
// O1-expanded: "reachable from any rank page as a new section"). Surfaces
// that ARE the consolidated view pass `hideConsolidatedLink`.

interface Props {
  /** testID namespace of the host surface, e.g. `tiers` → `tiers.scope-rookie`. */
  surface: string;
  /** Fires after the scope changes, for surfaces that must reset walk state
   *  (Quick Set's tier ladder, Quick Rank's step list, a trio selection). */
  onChange?: (scope: 'all' | 'rookie') => void;
  /** Suppress the consolidated-view link (the consolidated view itself). */
  hideConsolidatedLink?: boolean;
  /** Disable the pills while a save/switch is in flight. */
  disabled?: boolean;
  /** Drop the built-in gutter — for hosts whose container already pads
   *  (PickAnchorScreen). Default false matches the full-bleed rank screens. */
  flush?: boolean;
}

export default function RookieScopeControl({
  surface,
  onChange,
  hideConsolidatedLink,
  disabled,
  flush,
}: Props) {
  const navigation = useNavigation<any>();
  const { enabled, scope, isRookie, setScope } = useRookieScope();

  if (!enabled) return null;

  return (
    <View style={[styles.wrap, flush && styles.wrapFlush]}>
      <View
        style={styles.group}
        accessibilityRole="tablist"
        testID={`${surface}.scope`}
      >
        {SCOPE_OPTIONS.map((opt) => {
          const active = opt.scope === scope;
          return (
            <Pressable
              key={opt.key}
              testID={`${surface}.scope-${opt.key}`}
              accessibilityRole="tab"
              accessibilityState={{ selected: active, disabled: !!disabled }}
              accessibilityLabel={opt.a11yLabel}
              disabled={disabled}
              onPress={() => {
                if (opt.scope === scope) return;
                haptics.selection();
                setScope(opt.scope);
                onChange?.(opt.scope);
              }}
              style={({ pressed }) => [
                styles.segment,
                active && [
                  styles.segmentActive,
                  { borderBottomColor: opt.scope === 'rookie' ? flare.base : ice.base },
                ],
                pressed && !active && { backgroundColor: ink.ink3 },
                disabled && { opacity: 0.45 },
              ]}
            >
              <Text style={[styles.segmentText, active && styles.segmentTextActive]}>
                {opt.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {isRookie && !hideConsolidatedLink ? (
        <Pressable
          testID={`${surface}.scope-consolidated`}
          accessibilityRole="button"
          accessibilityLabel={CONSOLIDATED_VIEW.linkLabel}
          accessibilityHint={CONSOLIDATED_VIEW.body}
          hitSlop={space.sm}
          onPress={() => {
            haptics.selection();
            navigation.navigate(CONSOLIDATED_VIEW.route);
          }}
          style={({ pressed }) => [styles.link, pressed && { opacity: 0.6 }]}
        >
          <Text style={styles.linkText}>{CONSOLIDATED_VIEW.linkLabel}</Text>
          <Icon name="chevron-right" size={14} color={ice.base} />
        </Pressable>
      ) : null}
    </View>
  );
}

/** The shared rendering of the server's typed empty response. Every scoped
 *  surface uses THIS — a thin or unloaded rookie class is a designed state,
 *  not a failure, and it must read the same everywhere. Offers the one
 *  action that always works: go back to the full board. */
export function RookieScopeEmpty({
  surface,
  empty,
  position,
  flush,
}: {
  surface: string;
  empty: ScopedEmpty;
  position?: string | null;
  flush?: boolean;
}) {
  const { setScope } = useRookieScope();
  return (
    <View
      style={[styles.emptyBox, flush && styles.emptyBoxFlush]}
      testID={`${surface}.scope-empty`}
    >
      <Text style={styles.emptyText}>
        {scopeEmptyCopy(empty.reason, position ?? empty.position)}
      </Text>
      <Pressable
        testID={`${surface}.scope-empty.all`}
        accessibilityRole="button"
        accessibilityLabel="Show all players"
        hitSlop={space.sm}
        onPress={() => {
          haptics.selection();
          setScope('all');
        }}
        style={({ pressed }) => [styles.link, pressed && { opacity: 0.6 }]}
      >
        <Text style={styles.linkText}>Show all players</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginHorizontal: space.lg, marginTop: space.sm, gap: space.xs },
  wrapFlush: { marginHorizontal: 0, marginTop: 0 },
  // #133 PositionTabs construction: 1px hairline group at radii.sm; active
  // segment = ink-3 fill + a 2px underline in the segment's accent.
  group: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.sm,
    overflow: 'hidden',
  },
  segment: {
    flex: 1,
    height: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
    backgroundColor: 'transparent',
  },
  segmentActive: { backgroundColor: ink.ink3 },
  segmentText: { ...type.label },
  segmentTextActive: { color: chalk.base },
  link: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-end',
    gap: space.xs,
    minHeight: 32,
  },
  linkText: {
    ...type.bodySm,
    color: chalk.dim,
    textDecorationLine: 'underline',
    textDecorationColor: ice.base,
  },
  emptyBox: {
    margin: space.lg,
    padding: space.md,
    gap: space.sm,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    alignItems: 'flex-start',
  },
  emptyBoxFlush: { margin: 0 },
  emptyText: { ...type.bodySm, lineHeight: 19 },
});

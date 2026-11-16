import React, { useEffect, useMemo, useRef } from 'react';
import {
  AccessibilityInfo, Modal, PanResponder, Pressable, StyleSheet, View, findNodeHandle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Icon, Text } from '../chalkline';
import { chalk, ice, ink, radii, scrim, shadowSheet, space, type } from '../../theme/chalkline';
import { useReducedMotionSafe } from '../../hooks/useReducedMotionSafe';
import { DIRECTION_CARD_COPY as K } from '../../utils/directionCardCopy';
import type { SheetRow } from '../../utils/directionCard';

// The playoff card's half sheet (flag `league.direction_view_sheet`, cell C;
// spec docs/plans/league-projections/direction-pages/spec.md §5.6, D-270).
// "View ›" on the card opens it instead of going to Standings.
//
// It READS NOTHING (S-9): the rows come from `utils/directionCard.sheetRows`
// over the block the card already holds. Three rows, the same order for every
// team (S-3): "View projected standings" (always enabled), "Improve Playoff
// Chances", "Improve Draft Pick"; a direction the server does not offer is
// disabled with its one-line reason, one whose feature flag is off is not
// listed (S-4 to S-6).
//
// The existing sheet pattern (AnchorSheet, S-8): a Modal over the scrim,
// slide (fade under Reduce Motion), bottom safe-area padding, ink-2 panel
// with radius md on the top corners and the one sheet shadow. VoiceOver
// focus moves to the first row on open (the ClaimSheet pattern) and the
// panel is a modal region. Closes (S-7) on a row tap, a scrim tap, a
// downward drag, Android back (onRequestClose) or the VoiceOver escape
// gesture; closing without choosing changes nothing.
//
// Modal ⇒ no FeedbackFAB (root CLAUDE.md: "Exceptions: modals/sheets").

// Static literals (testid-lint and check-home-hub 11b cannot read template
// testIDs): one per row key, and its disabled-reason line.
const ROW_ID = {
  standings: 'home.playoff.sheet.standings',
  playoffs: 'home.playoff.sheet.improve-playoffs',
  draft_pick: 'home.playoff.sheet.improve-pick',
} as const;
const NOTE_ID = {
  standings: 'home.playoff.sheet.standings.note',
  playoffs: 'home.playoff.sheet.improve-playoffs.note',
  draft_pick: 'home.playoff.sheet.improve-pick.note',
} as const;

/** A downward drag of at least this many points closes the sheet. */
export const DRAG_CLOSE_DY = 48;

interface Props {
  visible: boolean;
  rows: SheetRow[];
  onClose: () => void;
  /** An enabled row was tapped: the card closes the sheet and hands the tap on. */
  onChoose: (row: SheetRow) => void;
}

export default function DirectionSheet({ visible, rows, onClose, onChoose }: Props) {
  const reduceMotion = useReducedMotionSafe();
  const firstRef = useRef<View>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  // A drag that is mostly downward is the sheet's; a release past the
  // threshold closes it. Taps still reach the rows.
  const drag = useMemo(() => PanResponder.create({
    onMoveShouldSetPanResponder: (_e, g) => g.dy > 8 && Math.abs(g.dy) > Math.abs(g.dx),
    onPanResponderRelease: (_e, g) => {
      if (g.dy >= DRAG_CLOSE_DY) closeRef.current();
    },
  }), []);

  useEffect(() => {
    if (!visible) return;
    const t = setTimeout(() => {
      const node = firstRef.current ? findNodeHandle(firstRef.current) : null;
      if (node != null) AccessibilityInfo.setAccessibilityFocus(node);
    }, 150);
    return () => clearTimeout(t);
  }, [visible]);

  return (
    <Modal visible={visible} transparent animationType={reduceMotion ? 'fade' : 'slide'} onRequestClose={onClose}>
      <Pressable testID="home.playoff.sheet.scrim" style={styles.backdrop} onPress={onClose}
        accessibilityRole="button" accessibilityLabel={K['SHEET.close']} />
      <View testID="home.playoff.sheet" style={styles.sheet} accessibilityViewIsModal
        accessibilityLabel={K['SHEET.label']} onAccessibilityEscape={onClose} {...drag.panHandlers}>
        <SafeAreaView edges={['bottom']}>
          <View style={styles.grabber} />
          {rows.map((row, i) => (
            <Pressable key={row.key} ref={i === 0 ? firstRef : undefined} testID={ROW_ID[row.key]}
              accessibilityRole="button" accessibilityState={{ disabled: !row.enabled }}
              accessibilityLabel={row.note ? `${row.label}. ${row.note}` : row.label}
              disabled={!row.enabled} onPress={() => onChoose(row)}
              style={[styles.row, i > 0 ? styles.divider : null]}>
              <View style={styles.rowText}>
                <Text style={row.enabled ? styles.label : styles.labelDisabled}>{row.label}</Text>
                {row.note ? <Text testID={NOTE_ID[row.key]} style={styles.note}>{row.note}</Text> : null}
              </View>
              {row.enabled ? <Icon name="chevron-right" size={16} color={chalk.base} /> : null}
            </Pressable>
          ))}
        </SafeAreaView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  sheet: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: ink.ink2, borderTopLeftRadius: radii.md, borderTopRightRadius: radii.md,
    borderWidth: 1, borderColor: ink.line, paddingHorizontal: space.lg, paddingBottom: space.md,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center', width: 32, height: 4, borderRadius: radii.xs,
    backgroundColor: ink.lineStrong, marginTop: space.sm, marginBottom: space.sm,
  },
  // S-8: every row a 44pt target at minimum; Dynamic Type grows it.
  row: { minHeight: 44, flexDirection: 'row', alignItems: 'center', gap: space.sm, paddingVertical: space.sm },
  divider: { borderTopWidth: 1, borderTopColor: ink.line },
  rowText: { flex: 1, minWidth: 0, gap: 2 },
  label: { ...type.body, color: ice.base },
  labelDisabled: { ...type.body, color: chalk.dim },
  note: { ...type.bodySm, color: chalk.dim },
});

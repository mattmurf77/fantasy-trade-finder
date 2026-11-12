import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  StyleSheet,
  Pressable,
  ScrollView,
  BackHandler,
  AccessibilityInfo,
  findNodeHandle,
  useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ink, chalk, ice, space, radii, type, fonts, scrim } from '../theme/chalkline';
import { Text, Icon } from './chalkline';
import type { Layer1Code, Layer2Code } from '../api/declineReasons';
import { PASS_REASON_CHIPS, placeWhyPassPanel } from '../utils/passReasonCadence';
import { getGuideScroller } from '../state/guideTargets';

// PassReasonChips — the deck card's occasional "why pass?" frame (flag
// `trade.pass_reason_cadence`, offer-learnings WS3). TradeCard mounts it over
// the whole card (absolute fill, a solid scrim over the card content) only
// when the ✕ is tapped on the card the cadence asks on. The frame ALWAYS ends
// in a pass — there is no way back to the card (operator, 2026-11-11):
//   • a chip is the pass and the reason together (the host advances the deck
//     at once, no second layer);
//   • "Just pass", the close control, a tap on the scrim, the VoiceOver
//     escape gesture and Android back are all the plain pass with no reason
//     (`onSkip`).
// A top-right close (neutral chalk, never the red pass colour) is there
// because users expect one (operator, 2026-11-11); it is one more exit, so it
// runs `onSkip` exactly like Just pass, and its label says so.
// It is a modal region: VoiceOver focus moves to the label on open and the
// card's own elements (the frame's siblings) are hidden from it while open.
//
// PLACEMENT INVARIANT (the build-186 bug was a control the user could not
// see): whenever the frame opens, the whole panel — label, copy line and
// first chips first — ends up inside the deck's visible scroll viewport. The
// card can be taller than the screen, so the panel is NOT centred in the
// card: `placeWhyPassPanel` centres it on the ✓/✕ row (`anchorY`) and clamps
// it into the part of the card that is on screen (the viewport comes from
// the deck's registered scroller, `measureViewport`); only if that part is
// shorter than the panel does it scroll the page to bring the panel in. The
// panel stays invisible until placed, so it never jumps. The scrim still
// covers the whole card.
// Built from existing tokens only: the `scrim` token, an ink-2 panel on a
// hairline, chips at radius xs, ice on press (an action).

export interface PassReasonChipsProps {
  /** Centre of the card's ✓/✕ row in the card's coordinates (TradeCard
   *  measures it); the panel is anchored here. Null ⇒ the card's middle. */
  anchorY: number | null;
  onChip: (reason: Layer1Code, detail: Layer2Code) => void;
  onSkip: () => void;
  /** Fired once when the frame opens (it mounts on the ✕ tap and unmounts
   *  with the card, so once per mount is once per asking card). */
  onShown?: () => void;
  disabled?: boolean;
}

export default function PassReasonChips({ anchorY, onChip, onSkip, onShown, disabled }: PassReasonChipsProps) {
  const labelRef = useRef<View | null>(null);
  const frameRef = useRef<View | null>(null);
  const [frameH, setFrameH] = useState(0);
  const [panelH, setPanelH] = useState(0);
  const [panelTop, setPanelTop] = useState<number | null>(null);
  const { height: winH } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  // Latest props for the mount-only listeners below.
  const skipRef = useRef(onSkip);
  skipRef.current = onSkip;
  const disabledRef = useRef(disabled);
  disabledRef.current = disabled;

  useEffect(() => {
    onShown?.();
    // Once per mount: the frame mounts on the ✕ tap and leaves with the card.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Place the panel once both heights are known (latched: it never moves
  // after it appears). See the PLACEMENT INVARIANT above.
  useEffect(() => {
    if (!frameH || !panelH || panelTop !== null) return;
    let live = true;
    const scroller = getGuideScroller('Trades');
    const base = { anchorY: anchorY ?? frameH / 2, panelH, frameH, pad: space.md, edge: space.sm };
    const place = (visTop: number, visBottom: number) => {
      frameRef.current?.measureInWindow((_x, frameWinY) => {
        if (!live) return;
        live = false;
        const p = placeWhyPassPanel({ ...base, frameWinY, visTop, visBottom });
        setPanelTop(p.top);
        if (p.scrollBy !== 0 && scroller) {
          scroller.scrollTo(Math.max(0, scroller.getScrollY() + p.scrollBy), true);
        }
      });
    };
    if (scroller?.measureViewport) scroller.measureViewport((top, height) => place(top, top + height));
    else place(insets.top, winH - insets.bottom);
    // A measurement that never answers must not leave the panel invisible:
    // fall back to the card-only clamp (anchored on the row, no viewport).
    const fallback = setTimeout(() => {
      if (!live) return;
      live = false;
      setPanelTop(placeWhyPassPanel({ ...base, frameWinY: 0, visTop: -1e6, visBottom: 1e6 }).top);
    }, 400);
    return () => {
      live = false;
      clearTimeout(fallback);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frameH, panelH, panelTop]);

  const placed = panelTop !== null;
  useEffect(() => {
    if (!placed) return;
    // Focus into the frame once the panel is visible (the ClaimSheet pattern).
    const t = setTimeout(() => {
      const node = labelRef.current ? findNodeHandle(labelRef.current) : null;
      if (node != null) AccessibilityInfo.setAccessibilityFocus(node);
    }, 150);
    return () => clearTimeout(t);
  }, [placed]);

  useEffect(() => {
    // Android back is an exit too, and every exit is the plain pass.
    const sub = BackHandler.addEventListener('hardwareBackPress', () => {
      if (!disabledRef.current) skipRef.current();
      return true;
    });
    return () => sub.remove();
  }, []);

  const skip = () => {
    if (!disabled) onSkip();
  };

  return (
    <View
      ref={frameRef}
      collapsable={false}
      style={styles.frame}
      onLayout={(e) => setFrameH(e.nativeEvent.layout.height)}
      testID="trades.pass-reason-chips"
      accessibilityViewIsModal
      onAccessibilityEscape={skip}
    >
      {/* The scrim: a tap outside the panel is Just pass. Not an a11y element —
          the escape gesture is VoiceOver's exit. */}
      <Pressable
        testID="trades.pass-reason-scrim"
        style={styles.scrim}
        onPress={skip}
        accessible={false}
        importantForAccessibility="no"
      />
      <View
        style={[
          styles.panel,
          { top: panelTop ?? 0, maxHeight: frameH ? frameH - 2 * space.md : undefined, opacity: placed ? 1 : 0 },
        ]}
        onLayout={(e) => setPanelH(e.nativeEvent.layout.height)}
      >
        <ScrollView contentContainerStyle={styles.panelBody} bounces={false}>
          <View style={styles.headRow}>
            <View ref={labelRef} accessible collapsable={false}>
              <Text scale="dense" style={styles.label} accessibilityRole="header">
                WHY PASS?
              </Text>
            </View>
            {/* The standard close (operator, 2026-11-11): expected, not
                needed — it is another exit, so it passes like Just pass. */}
            <Pressable
              testID="trades.pass-reason-close"
              onPress={skip}
              disabled={disabled}
              accessibilityRole="button"
              accessibilityLabel="Close and pass on this trade"
              style={styles.close}
            >
              {({ pressed }) => <Icon name="x" size={16} color={pressed ? chalk.base : chalk.dim} />}
            </Pressable>
          </View>
          <Text scale="body" style={styles.copy}>
            Your answer helps us find better trades for you.
          </Text>
          <View style={styles.row}>
            {PASS_REASON_CHIPS.map((c) => (
              <Pressable
                key={c.detail}
                testID={`trades.pass-reason-chip.${c.detail}`}
                onPress={() => onChip(c.reason, c.detail)}
                disabled={disabled}
                accessibilityRole="button"
                accessibilityLabel={`Pass — ${c.label}`}
                accessibilityHint="Passes on this trade and records why"
                style={({ pressed }) => [styles.chip, pressed && styles.chipPressed]}
              >
                <Text scale="body" style={styles.chipText}>
                  {c.label}
                </Text>
              </Pressable>
            ))}
            <Pressable
              testID="trades.pass-reason-skip"
              onPress={skip}
              disabled={disabled}
              accessibilityRole="button"
              accessibilityLabel="Just pass"
              accessibilityHint="Passes on this trade without a reason"
              style={({ pressed }) => [styles.chip, styles.skip, pressed && styles.chipPressed]}
            >
              <Text scale="body" style={styles.skipText}>
                Just pass
              </Text>
            </Pressable>
          </View>
        </ScrollView>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // Covers the card exactly (the card's padding box) at the card's radius.
  frame: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: radii.md,
  },
  scrim: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: radii.md,
    backgroundColor: scrim,
  },
  // Absolutely placed by `placeWhyPassPanel` (top) inside the frame's
  // padding; a tall chip list on a short card scrolls inside it, never clips.
  panel: {
    position: 'absolute',
    left: space.md,
    right: space.md,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
  },
  panelBody: {
    padding: space.md,
    gap: space.sm,
  },
  // "WHY PASS?" left, close right; the close's 44pt box overhangs into the
  // panel padding so the header row stays label-height.
  headRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  close: {
    width: 44,
    height: 44,
    marginVertical: -space.md,
    marginRight: -space.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: {
    fontFamily: fonts.data,
    fontSize: 11,
    lineHeight: 14,
    letterSpacing: 1.1,
    textTransform: 'uppercase',
    color: chalk.dim,
  },
  copy: {
    ...type.bodySm,
    color: chalk.dim,
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.sm,
  },
  // 44pt touch floor via minHeight; labels wrap rather than truncate.
  chip: {
    minHeight: 44,
    justifyContent: 'center',
    paddingVertical: space.xs,
    paddingHorizontal: space.md,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.lineStrongA11y,
    borderRadius: radii.xs,
  },
  chipPressed: {
    borderColor: ice.base,
    backgroundColor: ink.ink3,
  },
  chipText: {
    ...type.bodySm,
    fontFamily: fonts.uiSemi,
    color: chalk.base,
  },
  skip: {
    borderColor: ink.line,
  },
  skipText: {
    ...type.bodySm,
    color: chalk.dim,
  },
});

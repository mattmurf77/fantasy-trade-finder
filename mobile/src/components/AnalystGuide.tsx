import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  Pressable,
  StyleSheet,
  Animated,
  useWindowDimensions,
} from 'react-native';
import { ink, chalk, ice, space, radii, fonts, type } from '../theme/chalkline';
import { useGuide } from '../state/useGuide';
import { measureGuideTarget, type TargetFrame } from '../state/guideTargets';
import { AnalystAvatar } from './analyst';

// The Analyst — guided-tour overlay host (guided-avatar-script.md §2).
// Mounted ONCE in RootNav, above the nav tree, below system modals (native
// sheets/alerts always render above RN views, satisfying "system modals win").
//
// Placement rules (operator review 2026-07-19, binding):
//  • bubble + avatar live in the BOTTOM BAND; bubble never overlaps the
//    spotlight cutout or a primary CTA — if the target is in the bottom
//    band, avatar+bubble relocate to the top.
//  • when a step has CTAs they render INSIDE the bubble.
// Never-trap: ✕ skips the step; "Skip tour" is the permanent opt-out.

const AVATAR = 96;

export default function AnalystGuide() {
  const active = useGuide((s) => s.active);
  const onAccept = useGuide((s) => s.onAccept);
  const onDismissCta = useGuide((s) => s.onDismissCta);
  const advance = useGuide((s) => s.advance);
  const skipStep = useGuide((s) => s.skipStep);
  const dismissTour = useGuide((s) => s.dismissTour);
  const { width: winW, height: winH } = useWindowDimensions();

  const [frame, setFrame] = useState<TargetFrame | null>(null);
  const slide = useRef(new Animated.Value(0)).current;

  // Measure the spotlight target when a step activates; degrade to
  // bubble-only on any failure (never a blank cutout).
  useEffect(() => {
    let cancelled = false;
    setFrame(null);
    if (active?.target) {
      measureGuideTarget(active.target).then((f) => {
        if (!cancelled) setFrame(f);
      });
    }
    if (active) {
      slide.setValue(0);
      Animated.spring(slide, {
        toValue: 1,
        useNativeDriver: true,
        speed: 16,
        bounciness: 7,
      }).start();
    }
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id]);

  // Auto-advance steps (celebrations, pre-modal setup lines).
  useEffect(() => {
    if (!active || active.advance !== 'auto') return;
    const t = setTimeout(() => advance('auto'), active.autoMs ?? 2400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id]);

  if (!active) return null;

  // ── Placement solver (simplified per spec) ────────────────────────────
  const targetInBottomBand = !!frame && frame.y + frame.height > winH * 0.6;
  const atTop = targetInBottomBand;
  const side = active.side ?? 'left';
  const pad = 8 + (frame ? 6 : 0);

  const cutout = frame
    ? {
        left: Math.max(0, frame.x - 8),
        top: Math.max(0, frame.y - 8),
        width: Math.min(winW, frame.width + 16),
        height: frame.height + 16,
      }
    : null;

  const tapToAdvance = active.advance === 'tap';

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none" testID="guide.overlay">
      {/* Scrim with cutout — four panels around the target so the target
          itself stays LIVE (the guide observes; it never intercepts the
          real action). No target → no scrim. */}
      {cutout ? (
        <View style={StyleSheet.absoluteFill} pointerEvents="none">
          <View style={[styles.scrim, { left: 0, top: 0, right: 0, height: cutout.top }]} />
          <View style={[styles.scrim, { left: 0, top: cutout.top + cutout.height, right: 0, bottom: 0 }]} />
          <View style={[styles.scrim, { left: 0, top: cutout.top, width: cutout.left, height: cutout.height }]} />
          <View style={[styles.scrim, { left: cutout.left + cutout.width, top: cutout.top, right: 0, height: cutout.height }]} />
          <View
            style={[styles.ring, {
              left: cutout.left, top: cutout.top,
              width: cutout.width, height: cutout.height,
            }]}
          />
        </View>
      ) : null}

      {/* Tap-anywhere catcher for talk-only steps. Sits UNDER the bubble/
          avatar so their controls win; action steps get no catcher (the
          real UI stays fully interactive). */}
      {tapToAdvance ? (
        <Pressable
          style={StyleSheet.absoluteFill}
          onPress={() => advance('tap')}
          testID="guide.tap-catcher"
        />
      ) : null}

      {/* Avatar + bubble band */}
      <Animated.View
        pointerEvents="box-none"
        style={[
          styles.band,
          atTop ? { top: 54 } : { bottom: 92 },
          {
            opacity: slide,
            transform: [{
              translateY: slide.interpolate({
                inputRange: [0, 1],
                outputRange: [atTop ? -24 : 24, 0],
              }),
            }],
          },
        ]}
      >
        <View style={[styles.row, side === 'right' && { flexDirection: 'row-reverse' }]}>
          <View style={{ width: AVATAR }} pointerEvents="none" testID={`guide.avatar.${active.pose}`}>
            <AnalystAvatar pose={active.pose} size={AVATAR} flip={active.flip} />
          </View>
          <View style={[styles.bubble, { maxWidth: winW - AVATAR - 3 * pad }]} testID="guide.bubble">
            <View style={styles.bubbleHead}>
              <Text style={styles.who}>The Analyst</Text>
              <Pressable onPress={skipStep} hitSlop={10} testID="guide.step-x">
                <Text style={styles.x}>✕</Text>
              </Pressable>
            </View>
            <Text style={styles.line}>{active.line}</Text>
            {active.ctas?.length ? (
              <View style={styles.ctaCol}>
                {active.ctas.map((c) => (
                  <Pressable
                    key={c.label}
                    testID={`guide.cta.${c.action}`}
                    onPress={() => {
                      if (c.action === 'accept') onAccept?.();
                      else onDismissCta?.();
                      advance('cta');
                    }}
                    style={({ pressed }) => [
                      c.kind === 'primary' ? styles.ctaPrimary : styles.ctaGhost,
                      pressed && { opacity: 0.75 },
                    ]}
                  >
                    <Text style={c.kind === 'primary' ? styles.ctaPrimaryText : styles.ctaGhostText}>
                      {c.label}
                    </Text>
                  </Pressable>
                ))}
              </View>
            ) : null}
            <Pressable onPress={dismissTour} hitSlop={8} testID="guide.skip-tour" style={styles.skip}>
              <Text style={styles.skipText}>Skip the tour</Text>
            </Pressable>
          </View>
        </View>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  scrim: { position: 'absolute', backgroundColor: 'rgba(6,8,11,0.62)' },
  ring: {
    position: 'absolute',
    borderWidth: 2,
    borderColor: ice.base,
    borderRadius: radii.md,
  },
  band: { position: 'absolute', left: 10, right: 10 },
  row: { flexDirection: 'row', alignItems: 'flex-end', gap: 8 },
  bubble: {
    flexShrink: 1,
    backgroundColor: '#0A0C0F',
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.md,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
  },
  bubbleHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  who: {
    color: ice.base,
    fontFamily: fonts.uiSemi,
    fontSize: 12,
  },
  x: { color: chalk.faint, fontSize: 14, paddingLeft: 10 },
  line: { ...type.bodySm, color: chalk.base, marginTop: 4 },
  ctaCol: { marginTop: space.md, gap: 6 },
  ctaPrimary: {
    backgroundColor: ice.base,
    borderRadius: radii.sm,
    minHeight: 40,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.lg,
  },
  ctaPrimaryText: { color: ice.on, fontFamily: fonts.uiSemi, fontSize: 13 },
  ctaGhost: { minHeight: 32, alignItems: 'center', justifyContent: 'center' },
  ctaGhostText: { ...type.bodySm, fontFamily: fonts.uiSemi },
  skip: { marginTop: 6, alignSelf: 'flex-end' },
  skipText: { color: chalk.faint, fontSize: 10.5, textDecorationLine: 'underline' },
});

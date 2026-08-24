import React, { useEffect, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  Keyboard,
  View,
  Text,
  Pressable,
  StyleSheet,
  Animated,
  useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ink, chalk, ice, space, radii, fonts, type } from '../theme/chalkline';
import { useGuide } from '../state/useGuide';
import { useOnboardingFeature } from '../state/useFeatureFlags';
import {
  getGuideScroller,
  measureGuideTarget,
  subscribeGuideTargetsMoved,
  type TargetFrame,
} from '../state/guideTargets';
import { AnalystAvatar } from './analyst';
import { mascotName } from '../utils/mascotCopy';

// The Analyst — guided-tour overlay host (guided-avatar-script.md §2).
// Mounted ONCE in RootNav, above the nav tree, below system modals (native
// sheets/alerts always render above RN views, satisfying "system modals win").
//
// Placement rules (operator review 2026-07-19, binding; ADJACENCY added
// 2026-08-22 from the #384 device report):
//  • an untargeted step's bubble + avatar live in the BOTTOM BAND.
//  • a TARGETED step's band sits ADJACENT to its cutout — above it when the
//    band fits fully above and clear of the top inset, otherwise below it,
//    otherwise the bottom band. The bubble never overlaps the cutout.
//  • when a step has CTAs they render INSIDE the bubble.
// Never-trap: ✕ skips the step; "Skip tour" is the permanent opt-out.

const AVATAR = 96;
/** Gap between the spotlight ring and the avatar+bubble band. */
const BAND_GAP = 12;
/** Minimum clearance between the band and a safe-area edge. */
const BAND_EDGE = 8;
/** The legacy bottom band — still the fallback when nothing fits adjacent. */
const BAND_BOTTOM = 92;
/** Bottom chrome a tab screen draws over the window: the tab bar plus the
 *  strip that can float above it. Scroll-into-view keeps targets above it. */
const BOTTOM_CHROME = 96;

export interface BandPlacement {
  from: 'top' | 'bottom';
  offset: number;
}

/**
 * #384 device report 3 — place the band ADJACENT to its cutout.
 *
 * The shipped solver parked the band at a fixed `top: 54` whenever the
 * target's bottom edge fell below 60 % of the window. Every calculator beat
 * after the outlook has a low target, so all five landed there — on a screen
 * that carries a native-stack header (`subScreenOptions` in TabNav), far from
 * the ring they were explaining. The operator reported five correct rings with
 * no Analyst beside any of them, and saw the avatar return on the deck, which
 * has no header. Adjacency removes the whole class: the band is always next to
 * the thing it is pointing at, or it is the bottom band.
 *
 * Pure, and a function of the cutout + window only, so
 * `tests/check-guide-spotlight-tracking.js` lifts it out of this file and RUNS
 * it rather than pinning its shape.
 */
export function solveBandPlacement(
  cutout: { top: number; height: number } | null,
  bandH: number,
  winH: number,
  insets: { top: number; bottom: number },
  pin?: 'top',
): BandPlacement {
  // #397/#398 — a step may PIN the band to the top of the window
  // (`GuideStep.band: 'top'`). This precedes every other branch, the
  // null-cutout / unmeasured-band early return included, so a degraded or
  // not-yet-measured step still honors the ask. With `pin` undefined the
  // adjacency behavior below is unchanged.
  if (pin === 'top') return { from: 'top', offset: insets.top + BAND_EDGE };
  // No ring, or the band has not been measured yet — nothing to be adjacent
  // to, so the honest answer is the band an untargeted step would use.
  if (!cutout || bandH <= 0) return { from: 'bottom', offset: BAND_BOTTOM };
  // Preferred: ABOVE the ring, but only if the whole band clears the top
  // inset. Clamping into the inset instead is what put it under the header.
  const above = cutout.top - bandH - BAND_GAP;
  if (above >= insets.top + BAND_EDGE) return { from: 'top', offset: above };
  // Otherwise BELOW the ring, if the whole band fits above the bottom inset.
  // Floored at the top inset as well: a ring sitting at y=0 (a target the user
  // has scrolled up past) would otherwise put the band under the status bar,
  // which is the same defect one screen edge over.
  const below = Math.max(cutout.top + cutout.height + BAND_GAP, insets.top + BAND_EDGE);
  if (below <= winH - insets.bottom - bandH) return { from: 'top', offset: below };
  return { from: 'bottom', offset: BAND_BOTTOM };
}

export default function AnalystGuide() {
  const active = useGuide((s) => s.active);
  const onAccept = useGuide((s) => s.onAccept);
  const onDismissCta = useGuide((s) => s.onDismissCta);
  const advance = useGuide((s) => s.advance);
  const skipStep = useGuide((s) => s.skipStep);
  const dismissTour = useGuide((s) => s.dismissTour);
  const dismissActiveStep = useGuide((s) => s.dismissActiveStep);
  // guide_v2: the ENGINE owns the measurement (it needs the outcome for
  // `guide_step_shown.spotlight` and the degrade contract), so the overlay
  // reads the resolved frame instead of measuring a second time. With the
  // flag off the local measure below is the only path — unchanged.
  const guideV2 = useOnboardingFeature('onboarding.guide_v2');
  const spotlight = useGuide((s) => s.spotlight);
  const engineFrame = useGuide((s) => s.spotlightFrame);
  const trackSpotlightFrame = useGuide((s) => s.trackSpotlightFrame);
  const { width: winW, height: winH } = useWindowDimensions();
  const insets = useSafeAreaInsets();

  const [localFrame, setLocalFrame] = useState<TargetFrame | null>(null);
  const [reduceMotion, setReduceMotion] = useState(false);
  // Measured height of the avatar+bubble band. The adjacency solver cannot
  // place the band above a ring without knowing how tall it is, and the copy
  // (and the CTA row) make that per-step — so it is measured on layout and
  // LATCHED for the step, exactly like the placement it feeds.
  const [bandH, setBandH] = useState(0);
  const slide = useRef(new Animated.Value(0)).current;
  // B1 — band placement, latched per step (see the solver above).
  const bandRef = useRef<{ id: string; place: BandPlacement } | null>(null);
  // #384 report 5 — a step scrolls its target into view at most once.
  const scrolledForRef = useRef<string | null>(null);

  // NFR-2 — honor the OS "Reduce Motion" setting for the entry spring.
  useEffect(() => {
    let cancelled = false;
    AccessibilityInfo.isReduceMotionEnabled()
      .then((v) => { if (!cancelled) setReduceMotion(v); })
      .catch(() => { /* non-fatal — default to animating */ });
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => { cancelled = true; sub?.remove?.(); };
  }, []);

  // Measure the spotlight target when a step activates; degrade to
  // bubble-only on any failure (never a blank cutout).
  useEffect(() => {
    let cancelled = false;
    setLocalFrame(null);
    bandRef.current = null;
    setBandH(0);
    scrolledForRef.current = null;
    if (!guideV2 && active?.target) {
      measureGuideTarget(active.target).then((f) => {
        if (!cancelled) setLocalFrame(f);
      });
    }
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id]);

  // B1 — keep the cutout locked to its target while the host scrolls.
  // `measureInWindow` returns absolute window coordinates, so the one-shot
  // frame above goes stale the instant the host ScrollView moves; hosts call
  // `notifyGuideTargetsMoved()` and we re-measure. This effect only ever
  // MOVES an existing spotlight — it is armed after a frame resolved, and a
  // null re-measure (250 ms timeout, target unmounted mid-fling) keeps the
  // last good frame rather than degrading, because degrading here would
  // re-fire `guide_step_shown`.
  const spotlightTarget = active?.target;
  // The resolved frame, in absolute WINDOW coordinates. Hoisted above the
  // effects below because both of them need it and hooks cannot live after
  // the early returns further down.
  const frame = guideV2 ? engineFrame : localFrame;
  const frameResolved = !!frame;
  useEffect(() => {
    if (!spotlightTarget || !frameResolved) return;
    let cancelled = false;
    let raf: number | null = null;
    let inFlight = false;
    let pending = false;
    const remeasure = (): void => {
      // Coalesce to one measure per frame. A notification arriving while a
      // measure is outstanding is REMEMBERED, not dropped: a one-shot shift
      // (a keyboard inset, a banner mounting) emits a single event, and
      // losing it would strand the ring off by the whole delta until the
      // next scroll.
      if (raf !== null || inFlight) { pending = true; return; }
      raf = requestAnimationFrame(() => {
        raf = null;
        inFlight = true;
        measureGuideTarget(spotlightTarget).then((f) => {
          inFlight = false;
          if (cancelled) return;
          if (f) {
            if (guideV2) trackSpotlightFrame(f);
            else setLocalFrame(f);
          }
          if (pending) { pending = false; remeasure(); }
        });
      });
    };
    const unsubscribe = subscribeGuideTargetsMoved(remeasure);
    // The keyboard is the one shifter no host can announce. SignIn spotlights
    // the username field and asks the user to type; its KeyboardAvoidingView
    // (behavior 'padding') shrinks a `justifyContent:'center'` body, so the
    // field travels UP while the ring stays — and that screen has no scroll
    // container, so the onScroll path above can never fire there. Listening
    // here rather than in the host keeps every future screen covered for
    // free, and avoids putting a notifier in a screen with nothing to scroll.
    const kShow = Keyboard.addListener('keyboardDidShow', remeasure);
    const kHide = Keyboard.addListener('keyboardDidHide', remeasure);
    return () => {
      cancelled = true;
      if (raf !== null) cancelAnimationFrame(raf);
      unsubscribe();
      kShow.remove();
      kHide.remove();
    };
  }, [spotlightTarget, frameResolved, guideV2, trackSpotlightFrame]);

  // ── Scroll-into-view (#384 device report 5) ──────────────────────────────
  // A resolved frame can still be off-screen, or so close to an edge that the
  // adjacency solver has nowhere to put the band — the operator's case was
  // n23, whose send button sits below the fold with the tour's own overlay
  // suppressing the scroll that would have reached it. The overlay does not
  // own any scroll container, so it asks the scroller the ACTIVE STEP'S SCREEN
  // registered (`state/guideTargets`) to bring the target in, and the host's
  // existing `onScroll` → `notifyGuideTargetsMoved` path re-measures.
  //
  // Exactly ONCE per step: the scroll notifies, the notify re-measures, and a
  // re-measure that re-entered here would chase its own tail forever.
  const bandMeasured = bandH > 0;
  useEffect(() => {
    if (!active?.target || !frame || !bandMeasured) return;
    if (scrolledForRef.current === active.id) return;
    const scroller = getGuideScroller(active.screen);
    if (!scroller) return;
    scrolledForRef.current = active.id;
    // Reserve room for a band ABOVE the target, so a step that scrolls also
    // arrives with the preferred placement available.
    const wantTop = insets.top + BAND_EDGE + bandH + BAND_GAP;
    // The window's bottom edge is not the visible edge on a tab screen: the
    // tab bar (and any strip floating above it) covers the last ~96 pt, and
    // a target "in view" by window math sits under them. Seen in the
    // simulator 2026-08-22 — the action row's ring drawn beneath the verify
    // strip. Reserve that chrome; a non-tab host merely scrolls a little
    // higher than it strictly needed to.
    const wantBottom = winH - insets.bottom - BAND_EDGE - BOTTOM_CHROME;
    let delta = 0;
    if (frame.y < wantTop) delta = frame.y - wantTop;
    else if (frame.y + frame.height > wantBottom) {
      // Never chase a tall target's BOTTOM past its own top edge — align to
      // the top instead, which is the most of it we can show.
      delta = Math.min(frame.y + frame.height - wantBottom, frame.y - wantTop);
    }
    if (Math.abs(delta) < 4) return;
    scroller.scrollTo(Math.max(0, scroller.getScrollY() + delta), true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id, frame, bandMeasured, bandH, insets.top, insets.bottom, winH]);

  // Auto-advance steps (celebrations, pre-modal setup lines).
  useEffect(() => {
    if (!active || active.advance !== 'auto') return;
    const t = setTimeout(() => advance('auto'), active.autoMs ?? 2400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id]);

  // v2 — `lifetimeMs`: a cta step that is never answered expires instead of
  // sitting on screen forever. Expiry is a terminal transition (`timeout`),
  // not an auto-advance, so it marks the step seen and fires `onComplete`.
  useEffect(() => {
    if (!guideV2 || !active?.lifetimeMs) return;
    const t = setTimeout(() => dismissActiveStep('timeout'), active.lifetimeMs);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id, guideV2]);

  const spotlightPending = guideV2 && spotlight === 'pending';
  const degraded = guideV2 && spotlight === 'degraded';
  // D-155 — the mascot swap also carries copy. `lineRam` exists on exactly one
  // beat today (s0.1, the introduction); every other beat falls through to
  // `line`, so flag-off is byte-identical. A degraded step still prefers
  // `degradeLine` — the spotlight failing outranks which mascot is speaking.
  const ramOn = useOnboardingFeature('onboarding.mascot_ram');
  const baseLine = (ramOn ? active?.lineRam : undefined) ?? active?.line ?? '';
  const displayLine = degraded ? (active?.degradeLine ?? baseLine) : baseLine;
  const who = mascotName(ramOn);

  // Announce the line to screen readers once its final form is known
  // (a degraded step swaps in `degradeLine`, so announcing on activation
  // would read copy the user never sees).
  useEffect(() => {
    if (!guideV2 || !active || spotlightPending) return;
    AccessibilityInfo.announceForAccessibility(displayLine);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id, spotlightPending, guideV2]);

  // The entry slide. Keyed on the band actually RENDERING, not on the step
  // activating: a targeted step returns null while its spotlight is pending,
  // so an animation started on activation runs against an UNMOUNTED band.
  // With the native driver that view then remounted initialised from the
  // stale JS-side value (0) and never received another native frame — the
  // ring drew, the avatar and bubble were fully transparent (operator
  // device report, 2026-08-22, reproduced in the simulator on the sign-in
  // username beat). JS-driven on purpose: one bubble, one spring, and the
  // mounted view must always carry the real value.
  useEffect(() => {
    if (!active || spotlightPending) return;
    if (guideV2 && reduceMotion) {
      slide.setValue(1);
      return;
    }
    slide.setValue(0);
    const anim = Animated.spring(slide, {
      toValue: 1,
      useNativeDriver: false,
      speed: 16,
      bounciness: 7,
    });
    anim.start();
    return () => anim.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active?.id, spotlightPending]);

  if (!active) return null;
  // A targeted step whose spotlight has not resolved yet: hold the bubble
  // back (≤400 ms) rather than render copy that may swap to `degradeLine`
  // mid-display — the round-6 rule is that copy never changes after render,
  // and this also keeps the visible bubble in sync with the deferred
  // `guide_step_shown` emit. Suppress-class steps may be retracted entirely.
  if (spotlightPending) return null;

  const side = active.side ?? 'left';
  const pad = 8 + (frame ? 6 : 0);

  // B1 — a tracked target can scroll clean out of the viewport. The cutout
  // clamps x/y but not width/height, so clamping would smear the ring flat
  // against the edge; drop the scrim and ring instead (the bubble stays —
  // the step is still on screen, it just has nothing to point at).
  const frameOffscreen =
    !!frame &&
    (frame.y + frame.height <= 0 ||
      frame.y >= winH ||
      frame.x + frame.width <= 0 ||
      frame.x >= winW);

  // Clamp the SPAN by the same delta the origin was clamped by, or a target
  // mid-transit past an edge keeps its full height while its top sticks at 0
  // — a frozen, oversized ring glued to the edge for the whole transit (the
  // dominant case: scrolling down past a full-height deck card).
  const cutout = frame && !frameOffscreen
    ? (() => {
        const rawLeft = frame.x - 8;
        const rawTop  = frame.y - 8;
        const left = Math.max(0, rawLeft);
        const top  = Math.max(0, rawTop);
        return {
          left,
          top,
          width:  Math.max(0, Math.min(winW - left, frame.width  + 16 - (left - rawLeft))),
          height: Math.max(0, Math.min(winH - top,  frame.height + 16 - (top  - rawTop))),
        };
      })()
    : null;

  // ── Placement solver — ADJACENT to the cutout (#384 report 3) ─────────
  // B1 — LATCH the band for the life of the step. The solver re-runs every
  // render, so once the frame tracks scroll the band would slide (and flip
  // sides) mid-fling. Latched on the first RESOLVED frame with a MEASURED
  // band: latching earlier would freeze the pre-measure fallback and park the
  // bubble in the bottom band for a step whose ring is right there.
  const solved = solveBandPlacement(cutout, bandH, winH, insets, active.band);
  // Latch only on an ON-SCREEN cutout. The first frame of a step can resolve
  // while the native-stack push is still sliding the screen in — the target
  // measures OFF-screen to the right, `cutout` is null, the solver answers
  // "bottom band", and a latch taken then pins the band to the wrong SIDE for
  // the life of the step (simulator, 2026-08-22: the bubble stayed across the
  // In-league tab while its ring tracked the scroll correctly).
  if (frame && cutout && bandH > 0 && bandRef.current?.id !== active.id) {
    bandRef.current = { id: active.id, place: solved };
  }
  // The SIDE is latched for the life of the step (no flip-flop mid-scroll);
  // the OFFSET is live whenever the solver agrees on the side, so the band
  // follows its ring when the ring moves — a post-transition re-measure, a
  // scroll, a keyboard. Latching the offset too parked the band over a ring
  // that had since corrected itself (simulator, 2026-08-22, first landing on
  // the calculator: bubble drawn across the In-league tab it pointed at).
  const latched = bandRef.current?.id === active.id ? bandRef.current.place : null;
  const place = latched && latched.from === solved.from ? solved : (latched ?? solved);
  const atTop = place.from === 'top';
  // A targeted step is held invisible for the one frame between mount and the
  // band's `onLayout`, because placing it needs its height. An untargeted step
  // (or a degraded one, which has no ring to be adjacent to) shows at once.
  const bandPending = !!cutout && bandH <= 0;

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
          accessibilityRole="button"
          accessibilityLabel="Continue"
          accessibilityHint="Advances the tour"
        />
      ) : null}

      {/* Avatar + bubble band */}
      <Animated.View
        pointerEvents="box-none"
        onLayout={(e) => {
          // Latched: the copy never changes after render (round-6 rule), so
          // one measurement per step is the whole story — and re-setting on
          // every layout would re-solve the placement mid-scroll.
          const h = e.nativeEvent.layout.height;
          if (h > 0 && bandH <= 0) setBandH(h);
        }}
        style={[
          styles.band,
          atTop ? { top: place.offset } : { bottom: place.offset },
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
        {/* The pending hide lives on the ROW, not on the Animated.View: the
            outer opacity is driven by `slide`, and overriding an animated
            style prop with a literal for one frame detaches and re-attaches
            the animated node for nothing. The row still lays out, so the
            measurement above is unaffected. */}
        <View
          style={[
            styles.row,
            side === 'right' && { flexDirection: 'row-reverse' },
            bandPending && styles.bandPending,
          ]}
        >
          <View style={{ width: AVATAR }} pointerEvents="none" testID={`guide.avatar.${active.pose}`}>
            <AnalystAvatar pose={active.pose} size={AVATAR} flip={active.flip} />
          </View>
          <View style={[styles.bubble, { maxWidth: winW - AVATAR - 3 * pad }]} testID="guide.bubble">
            <View style={styles.bubbleHead}>
              <Text style={styles.who}>{who}</Text>
              <Pressable
                onPress={skipStep}
                hitSlop={10}
                testID="guide.step-x"
                accessibilityRole="button"
                accessibilityLabel="Skip this step"
              >
                <Text style={styles.x}>✕</Text>
              </Pressable>
            </View>
            <Text style={styles.line}>{displayLine}</Text>
            {active.ctas?.length ? (
              <View style={styles.ctaCol}>
                {active.ctas.map((c) => (
                  <Pressable
                    key={c.label}
                    testID={`guide.cta.${c.action}`}
                    accessibilityRole="button"
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
            {/* #187 — permanent opt-out, present on EVERY bubble (never-trap
                principle). Distinct from the ✕ (skips one step): this turns
                The Analyst off for good; Settings → "Guided tour" re-enables. */}
            <Pressable
              onPress={dismissTour}
              hitSlop={8}
              testID="guide.dismiss-tour"
              style={styles.skip}
              accessibilityRole="button"
              accessibilityLabel="Turn off the guided tour"
              accessibilityHint={`Stops ${who} from appearing. You can turn it back on in Settings.`}
            >
              <Text style={styles.skipText}>Skip the tour — don't show again</Text>
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
  // One frame only — the band is laid out (so `onLayout` can measure it) but
  // not shown, so the user never sees it jump from the fallback band to its
  // adjacent placement.
  bandPending: { opacity: 0 },
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

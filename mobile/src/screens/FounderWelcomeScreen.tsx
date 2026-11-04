import React, { useEffect, useRef } from 'react';
import {
  AccessibilityInfo,
  Animated,
  findNodeHandle,
  StyleSheet,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import AsyncStorage from '@react-native-async-storage/async-storage';

import ChalkText from '../components/chalkline/Text';
import { Button } from '../components/chalkline';
import { RamAvatar } from '../components/mascot/ram';
import { chalk, duration, flare, ink, radii, space } from '../theme/chalkline';
import { useReducedMotionSafe } from '../hooks/useReducedMotionSafe';
import { FOUNDER_TAG, MON, clubSince, welcomeBody, type PlanPeriod } from '../copy/monetization';

// FOUNDER WELCOME — the Founding GMs welcome (#393 M3; D10; design-lead
// §4.1; ux-lead flow §4.1; copy §9.5). The ONE celebration, and only in
// response to the user's own purchase:
//   - shown ONCE per user, ever (claimFounderWelcome below, the offer
//     memory's per-user AsyncStorage shape);
//   - only after Apple's sheet succeeds (a trial start or a purchase) on the
//     paywall, never after a Restore, never on its own;
//   - only INSIDE the club window (clubWindowOpen below). From the cut-off
//     there is no welcome: the user goes straight back to the same card.
// PaywallScreen replaces itself with this screen, so Back (`mon.club.back`)
// returns to where the paywall was opened: the same card.
//
// Layout (design §4.1): an ink-0 full-screen column. The ram's `celebrate`
// pose in its own ink-1 box (hairline, radius 8), the FounderTag, the title
// (`display`), the plan's body (`body` chalk-dim), "Founding GM since" with
// the date in Plex Mono, and one Primary. No confetti, glow or gradient.
// Motion: one staggered entry (6 items, 40 ms apart, fade + 8 px rise,
// duration.base); static under Reduce Motion. VoiceOver starts on the title.
//
// The tester title (`mon.club.welcome_tester`) is not used: nothing on the
// client knows who was a TestFlight tester, so every member gets
// `mon.club.welcome_title`.
//
// No countdown, days-left or end date: the only date is the JOIN date (D10).
// `closes_at` is read in clubWindowOpen alone, to decide; it never renders.
//
// #188: a full-screen MODAL, so no FeedbackFAB (modals are the exemption).

const WELCOME_SHOWN_KEY_PREFIX = 'ftf_founder_welcome_shown_';

/** The club window, from /api/paywall/config `club` (S1): the server says
 *  open AND the cut-off hasn't passed on this clock either, so a config
 *  cached before the cut-off can't welcome a purchase made after it.
 *  Absent, closed or unreadable → no welcome. */
export function clubWindowOpen(
  club: { open?: boolean; closes_at?: string } | null | undefined,
  nowMs: number,
): boolean {
  if (!club || club.open !== true) return false;
  const cut = Date.parse(club.closes_at ?? '');
  return Number.isFinite(cut) && nowMs < cut;
}

/** Claim this user's one welcome. True exactly once per user (remembered
 *  BEFORE it shows); false when it already showed, or when storage can't
 *  say (a broken read never shows it twice). */
export async function claimFounderWelcome(userId: string): Promise<boolean> {
  if (!userId) return false;
  const key = `${WELCOME_SHOWN_KEY_PREFIX}${userId}`;
  try {
    if ((await AsyncStorage.getItem(key)) === '1') return false;
    await AsyncStorage.setItem(key, '1');
    return true;
  } catch {
    return false;
  }
}

const ITEMS = 6;

export default function FounderWelcomeScreen({ navigation, route }: any) {
  const period: PlanPeriod = route?.params?.period === 'monthly' ? 'monthly' : 'annual';
  const since = clubSince(route?.params?.since);
  const reduceMotion = useReducedMotionSafe();
  const titleRef = useRef<View>(null);
  const items = useRef(
    Array.from({ length: ITEMS }, () => new Animated.Value(reduceMotion ? 1 : 0)),
  ).current;

  // The screen's one orchestrated moment. Under Reduce Motion everything is
  // simply there.
  useEffect(() => {
    if (reduceMotion) {
      items.forEach((v) => v.setValue(1));
      return;
    }
    Animated.stagger(
      40,
      items.map((v) =>
        Animated.timing(v, { toValue: 1, duration: duration.base, useNativeDriver: true }),
      ),
    ).start();
    // Once per appearance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // VoiceOver starts on the title, once the frame lands.
  useEffect(() => {
    const t = setTimeout(() => {
      const node = titleRef.current ? findNodeHandle(titleRef.current) : null;
      if (node != null) AccessibilityInfo.setAccessibilityFocus(node);
    }, 150);
    return () => clearTimeout(t);
  }, []);

  const back = () => {
    if (navigation?.canGoBack?.()) navigation.goBack();
    else navigation?.navigate?.('Main');
  };

  const enter = (i: number) => ({
    opacity: items[i],
    transform: [{ translateY: items[i].interpolate({ inputRange: [0, 1], outputRange: [8, 0] }) }],
  });

  return (
    <SafeAreaView style={styles.root} testID="founder-welcome" edges={['top', 'bottom']}>
      <View style={styles.column}>
        <Animated.View style={[styles.ramBox, enter(0)]}>
          <RamAvatar pose="celebrate" size={120} />
        </Animated.View>
        <Animated.View style={[styles.founderTag, enter(1)]}>
          <ChalkText variant="label" style={styles.founderTagText}>
            {FOUNDER_TAG}
          </ChalkText>
        </Animated.View>
        <Animated.View style={enter(2)}>
          <View
            ref={titleRef}
            accessible
            accessibilityRole="header"
            accessibilityLabel={MON['mon.club.welcome_title']}
          >
            <ChalkText variant="display" testID="founder-welcome-title">
              {MON['mon.club.welcome_title']}
            </ChalkText>
          </View>
        </Animated.View>
        <Animated.View style={enter(3)}>
          <ChalkText variant="body" style={styles.dim}>
            {welcomeBody(period)}
          </ChalkText>
        </Animated.View>
        <Animated.View style={enter(4)}>
          {since ? (
            <ChalkText variant="body" testID="founder-welcome-since">
              {`${since.lead} `}
              <ChalkText variant="data">{since.date}</ChalkText>
            </ChalkText>
          ) : null}
        </Animated.View>
        <Animated.View style={[styles.action, enter(5)]}>
          <Button testID="founder-welcome-back" label={MON['mon.club.back']} onPress={back} />
        </Animated.View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  column: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: space.lg,
    gap: space.md,
  },
  // The ram in its own ink-1 box: hairline, radius 8, nothing outside it.
  ramBox: {
    alignSelf: 'flex-start',
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.line,
    borderRadius: radii.md,
    padding: space.sm,
  },
  // FounderTag (design-lead): flare label, 1px flare border, r-xs, no fill.
  founderTag: {
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: flare.base,
    borderRadius: radii.xs,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  founderTagText: { color: flare.base },
  dim: { color: chalk.dim },
  action: { marginTop: space.md },
});

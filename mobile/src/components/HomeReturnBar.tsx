import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { useNavigation } from '@react-navigation/native';

import { Icon, Text } from './chalkline';
import { chalk, fonts, ink, space } from '../theme/chalkline';
import { useFlag } from '../state/useFeatureFlags';
import { useHomeReturn } from '../state/homeReturn';
import { HOME_RETURN_FLAG, homeReturnVisible } from '../navigation/navContinuity';

// The "‹ Home" control (flag `nav.home_return`, D-275; decision Q1 option
// (a), generalising D-269). Mounted ONCE by TabNav between the global TopBar
// and the tabs, so it sits at the top of whichever page the arrival lands on
// (the Acquire landing or whatever Acquire page was last open, League
// rankings, Matches) without each page drawing its own. It renders only
// while the tab a Home tile armed is the focused tab: leaving that tab by
// any route (the tab bar, this control, another link) ends the visit.
//
// Same chevron-and-word treatment as the in-tab "‹ Back" (TabNav HeaderBack);
// one tap returns to the Home tab as it was. Nothing is closed or popped on
// the destination, so the page is as the user left it if they come back.
export default function HomeReturnBar() {
  const navigation = useNavigation<any>();
  const flagOn = useFlag(HOME_RETURN_FLAG);
  const visible = useHomeReturn((s) => homeReturnVisible(s, s.focusedTab, flagOn));
  if (!visible) return null;
  return (
    <View style={styles.bar}>
      <Pressable
        testID="home-return.back"
        accessibilityRole="button"
        accessibilityLabel="Back to Home"
        hitSlop={space.md}
        onPress={() => navigation.navigate('Main', { screen: 'Home' })}
        style={({ pressed }) => [styles.back, pressed && { opacity: 0.6 }]}
      >
        <Icon name="chevron-left" size={16} color={chalk.base} />
        <Text style={styles.backText}>Home</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    backgroundColor: ink.ink0,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    paddingHorizontal: space.lg,
    paddingVertical: space.xs,
    flexDirection: 'row',
  },
  // TabNav's headerBack / headerBackText, so it reads as the app's Back.
  back: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingVertical: space.xs,
    paddingRight: space.md,
  },
  backText: { color: chalk.base, fontFamily: fonts.uiSemi, fontSize: 14 },
});

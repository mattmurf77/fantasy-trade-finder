import React, { useEffect, useState } from 'react';
import { Alert } from 'react-native';

import MflSignInSheet from './MflSignInSheet';
import { navigationRef } from '../navigation/RootNav';
import { clearRelink, useTestProfile } from '../state/testProfile';

// After "Back to my profile" (state/testProfile.exitTestProfile): if the real
// profile's ESPN or MFL link was connected when the test profile started and
// is not connected now, surface the app's NORMAL re-link prompt instead of
// letting the next send fail:
//   ESPN → EspnConnect with reason 'send' (what SendInEspnButton opens)
//   MFL  → MflSignInSheet (what SendInMflButton opens)
// Mounted once in App.tsx, outside the test-profile banner, so it is live in
// the real profile. Renders nothing unless a link was found broken.

const NAME = { espn: 'ESPN', mfl: 'MFL' } as const;

export default function TestProfileRelinkPrompt() {
  const relink = useTestProfile((s) => s.relink);
  const [mflOpen, setMflOpen] = useState(false);
  const next = relink[0];

  useEffect(() => {
    if (!next) return;
    Alert.alert(
      `Re-link ${NAME[next]}`,
      `Your profile's ${NAME[next]} sign-in is no longer connected. Sign in again so trades ` +
        `can be sent from this league.`,
      [
        { text: 'Later', style: 'cancel', onPress: () => clearRelink(next) },
        {
          text: `Sign in to ${NAME[next]}`,
          onPress: () => {
            clearRelink(next);
            if (next === 'mfl') setMflOpen(true);
            else if (navigationRef.isReady()) {
              navigationRef.navigate('EspnConnect', { reason: 'send' });
            }
          },
        },
      ],
    );
  }, [next]);

  return (
    <MflSignInSheet
      visible={mflOpen}
      onClose={() => setMflOpen(false)}
      onSignedIn={() => setMflOpen(false)}
    />
  );
}

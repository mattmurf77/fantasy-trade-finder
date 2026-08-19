// Settings — the destructive "Sign out" row (plus the spacer above it).
//
// Lifted verbatim from SettingsScreen.tsx (origin/main) `signOutBlock` at
// :1461-1474, plus `signOut = useSession((s) => s.signOut)` (:86).
//
// It is its own module because plan §3/§4 MOVE it: operator decision
// 2026-08-18 puts Sign out on the Account page, directly under the identity
// block it terminates, deliberately far from Delete account so the two
// destructive controls are never neighbours.
//
// TickLabel: NONE — the shipped block has no banner.
//
// Intentional behavior changes: NONE, with one wiring note. The shipped
// handler ran `navigation.replace('SignIn')` after signOut(); this module has
// no navigation object, so the host supplies that as `onSignedOut`. A REPLACE
// (not a navigate) is load-bearing — the signed-out user must not be able to
// swipe back into the authenticated stack. Plan §5 lists it as a code-walk
// item for the modal→push flip.
//
// No queries, no loading state.

import React from 'react';
import { View, Text, Pressable } from 'react-native';

import { space } from '../../../theme/chalkline';
import { useSession } from '../../../state/useSession';
import { styles } from '../styles';

export interface SignOutRowProps {
  /** Called after the local session is cleared. The host performs the
   *  shipped `navigation.replace('SignIn')`. */
  onSignedOut: () => void;
}

export default function SignOutRow({ onSignedOut }: SignOutRowProps) {
  const signOut = useSession((s) => s.signOut);

  return (
    <>
      <View style={{ height: space.xxl }} />
      <Pressable
        accessibilityRole="button"
        onPress={async () => {
          await signOut();
          onSignedOut();
        }}
        style={({ pressed }) => [styles.signOut, pressed && styles.rowPressed]}
      >
        <Text style={styles.signOutText}>Sign out</Text>
      </Pressable>
    </>
  );
}

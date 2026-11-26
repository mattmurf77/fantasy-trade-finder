import React from 'react';
import { StyleSheet, View } from 'react-native';

import { gateSignalFor } from '../api/client';
import { MON } from '../copy/monetization';
import { isUnverifiedSession, openPaywall, openVerify } from '../state/usePaywallGate';
import { space } from '../theme/chalkline';
import { haptics } from '../utils/haptics';
import Button from './chalkline/Button';
import Text from './chalkline/Text';

// The in-place answer for a gated surface whose request the server refused
// (paid launch, 2026-11-21). The deck has its own (DeckEndCard previewEnd,
// #393 M2 D5); this is the same lock line + ONE Primary for the surfaces
// that otherwise fell through to a generic "Couldn't sweep the league" or a
// false empty state after a 402: Shop a player and the single-pin ideas panel.
//
// WHEN IT RENDERS: only after the server answered a request this surface
// made with a gate answer (`gateNoticeFor(error, path)` non-null). The
// paywall (or the VerifySheet) has already opened once from api/client; this
// stays behind it so a user who chose Not now still sees why the surface is
// empty and has one way back. It is never a pre-tap teaser and never a
// locked-feature card (legal R28.8 #5): nothing renders before the user's
// own gated action.
//
// ROUTING READS NO ENTITLEMENT FIELD (legal R28.9, D15): verify vs paywall
// comes from the server's answer and the session's verified-ness only, the
// usePaywallGate rule. Copy is the existing mon.* keys, verbatim.

export interface GateNotice {
  /** The server answered verify (or the session is unverified / demo):
   *  Continue → the VerifySheet. Otherwise See plans → the paywall. */
  verify: boolean;
  gate: string | null;
  kind: 'find' | 'send';
}

/** The notice a failed request warrants, or null when it isn't a gate answer
 *  (and ALWAYS null while monetize.paywall is off: gateSignalFor). */
export function gateNoticeFor(error: unknown, path: string): GateNotice | null {
  const signal = gateSignalFor(error, path);
  if (!signal || signal.action === 'verify_mismatch') return null;
  return { verify: signal.action === 'verify', gate: signal.gate, kind: signal.kind };
}

export default function PaywallGateNotice({
  notice,
  testID,
  onVerified,
}: {
  notice: GateNotice;
  testID: string;
  /** Runs once the VerifySheet closes `verified` (e.g. refetch). */
  onVerified?: () => void;
}) {
  const verify = notice.verify || isUnverifiedSession();
  const line = notice.kind === 'send' ? MON['mon.lock.send'] : MON['mon.lock.find'];
  return (
    <View testID={testID} style={styles.root} accessible={false}>
      <Text variant="bodySm" accessibilityRole="text">
        {line}
      </Text>
      <Button
        testID={`${testID}-cta`}
        label={verify ? MON['mon.verify.continue'] : MON['mon.pay.see_plans']}
        variant="primary"
        compact
        onPress={() => {
          haptics.selection();
          if (verify) {
            void openVerify(onVerified ? { onVerified } : {});
            return;
          }
          void openPaywall({
            source: 'gate',
            kind: notice.kind,
            ...(notice.gate ? { gate: notice.gate } : {}),
          });
        }}
        style={styles.cta}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { gap: space.sm, paddingVertical: space.sm },
  cta: { alignSelf: 'flex-start' },
});

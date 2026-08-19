// Settings › Account & data — second-level page.
//
// Implements plan §3 (`SettingsAccount` row of the page table) and §4. Composes
// three Phase-0 section modules, in this exact order:
//
//   1. AccountIdentitySection — demo-session row, linked identities
//      (Apple/Google), Link Apple card, Sleeper identity, the account-only
//      LinkSleeperForm, verification row + explainer, "Verify account".
//   2. SignOutRow             — the destructive sign-out control.
//   3. AccountDataSection     — public profile (flag-dark in prod), Download my
//      data, and Delete account LAST.
//
// ORDER IS LOAD-BEARING (operator decision, 2026-08-18; plan §3 grouping call
// 4). Sign out sits directly under the identity block it terminates, and Delete
// account stays the last row on the page. The two destructive controls are at
// opposite ends deliberately — stacking them adjacent invites a mis-tap on the
// irreversible one. Do not "tidy" these together.
//
// BANNER: AccountIdentitySection carries the single
// <TickLabel>Account</TickLabel> inherited from the shipped `accountSection`;
// the other two modules emit none. This page adds none.
//
// The three platform disconnect rows that ship inside today's Account section
// are NOT here — plan §4 moves them to SettingsLeagues (finding F2).
//
// Data (plan §6): this page owns ['account'] and ['profile-visibility'].
//
// Two REPLACE wirings the sections cannot perform themselves (plan §5 lists
// both as code-walk items for the modal→push flip): a signed-out or deleted
// user must not be able to swipe back into the authenticated stack, so both
// land on SignIn via `navigation.replace`, not `navigate`.

import React, { useState } from 'react';
import { ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import FeedbackFAB from '../../components/FeedbackFAB';
import Toast from '../../components/Toast';
import { styles } from './styles';
import AccountIdentitySection from './sections/AccountIdentitySection';
import SignOutRow from './sections/SignOutRow';
import AccountDataSection from './sections/AccountDataSection';

export default function SettingsAccountScreen({ navigation }: any) {
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);

  // Plan §5 — pushed page, so a plain navigate (no goBack-first hack). Back
  // from SleeperConnect now returns to this page rather than to the tabs.
  const navigate = (route: string, params?: object) => navigation.navigate(route, params);
  const onNotice = (msg: string, tone?: 'success' | 'warn') => setToast({ msg, tone });

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <AccountIdentitySection
          onNotice={onNotice}
          navigate={navigate}
          // Shipped behavior (SettingsScreen:1338): a stack REPLACE onto the
          // picker after the account-only Sleeper link succeeds.
          onSleeperLinked={() => navigation.replace('LeaguePicker')}
        />
        <SignOutRow onSignedOut={() => navigation.replace('SignIn')} />
        <AccountDataSection
          onNotice={onNotice}
          navigate={navigate}
          onAccountDeleted={() => navigation.replace('SignIn')}
        />
      </ScrollView>
      <Toast
        visible={!!toast}
        message={toast?.msg ?? ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
      <FeedbackFAB activeScreen="SettingsAccount" aboveTabBar={false} />
    </SafeAreaView>
  );
}

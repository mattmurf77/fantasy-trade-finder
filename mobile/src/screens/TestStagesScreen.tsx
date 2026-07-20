import React, { useState } from 'react';
import { View, Text, Pressable, ScrollView, StyleSheet, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { TickLabel } from '../components/chalkline';
import { api, getDeviceId, setSessionToken } from '../api/client';
import { useSession } from '../state/useSession';
import { replaceOnboardingState } from '../state/useOnboardingState';
import type { OnboardingPersisted } from '../state/useOnboardingState';

// Test Stages — operator QA tool (flag `testing.stage_users` + server-side
// tester allowlist; the row into this screen only renders when the flag is
// on, and the backend 403s non-allowlisted devices regardless).
//
// Spawns a synthetic `qa_*` user materialized at an adoption stage (demo-
// league machinery, no Sleeper dependency, excluded from analytics), swaps
// this device into it (session token + user + league + matching
// ftf_onboarding_state), so any point of the onboarding flow is reachable
// in two taps, repeatably. "Factory reset" is device-only: wipes local
// first-run state and signs out for the full from-scratch S0 tour.

interface SpawnResponse {
  session_token: string;
  user_id: string;
  username: string;
  display_name: string;
  league_id: string;
  league_name: string;
  stage: string;
  client_state: Partial<OnboardingPersisted>;
}

const STAGES: Array<{
  key: 'fresh' | 'activated' | 'board_owner' | 'converted' | 'power';
  name: string;
  desc: string;
}> = [
  { key: 'fresh', name: 'Fresh', desc: 'Signed in, consensus board, zero activity — first-run Trades experience.' },
  { key: 'activated', name: 'Activated', desc: '5 swipes on record — Quick Set pitch territory (S3).' },
  { key: 'board_owner', name: 'Board owner', desc: 'WR quickset persisted — next-position ask territory (S5.5).' },
  { key: 'converted', name: 'Converted', desc: 'Board owner + verified; Apple prompts consumed.' },
  { key: 'power', name: 'Power user', desc: 'All four positions ranked + verified; tour complete → reactive-only.' },
];

export default function TestStagesScreen({ navigation }: any) {
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const setUser = useSession((s) => s.setUser);
  const setLeague = useSession((s) => s.setLeague);
  const setLeagues = useSession((s) => s.setLeagues);
  const signOut = useSession((s) => s.signOut);
  const currentUser = useSession((s) => s.user);

  async function factoryReset() {
    setBusy('factory');
    try {
      replaceOnboardingState({});
      await signOut();
      // RootNav's gate flips to SignIn on the cleared session.
    } finally {
      setBusy(null);
    }
  }

  async function spawn(stage: (typeof STAGES)[number]['key']) {
    setBusy(stage);
    setNote(null);
    try {
      const res = await api.post<SpawnResponse>(
        '/api/test-users',
        { stage },
        { headers: { 'X-Device-Id': await getDeviceId() } },
      );
      await setSessionToken(res.session_token);
      await setUser({
        user_id: res.user_id,
        username: res.username,
        display_name: res.display_name,
        avatar_id: null,
      });
      await setLeagues([]);
      await setLeague({ league_id: res.league_id, league_name: res.league_name });
      replaceOnboardingState(res.client_state || {});
      setNote(
        `Now ${res.username} (${res.stage}). Force-quit and reopen for a fully clean run — ` +
          'some once-per-session guards only reset on relaunch.',
      );
    } catch (e: any) {
      setNote(e?.message || 'Spawn failed — is the flag on and this device allowlisted?');
    } finally {
      setBusy(null);
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body}>
        <TickLabel>Operator QA · synthetic users</TickLabel>
        <Text style={styles.h1}>Test Stages</Text>
        <Text style={styles.sub}>
          Spawn a throwaway qa_* user at an adoption stage and swap this device into it.
          Synthetic users ride a seeded demo league, never touch Sleeper, and are excluded
          from analytics. Current: {currentUser?.username || '—'}.
        </Text>

        <Pressable
          testID="test-stages.factory-reset"
          style={({ pressed }) => [styles.card, styles.cardDanger, pressed && styles.pressed]}
          onPress={() =>
            Alert.alert(
              'Factory reset this device?',
              'Clears first-run/tour state and signs out. Server data is untouched.',
              [
                { text: 'Cancel', style: 'cancel' },
                { text: 'Reset', style: 'destructive', onPress: factoryReset },
              ],
            )
          }
          disabled={!!busy}
        >
          <Text style={styles.name}>Factory reset (device only)</Text>
          <Text style={styles.desc}>
            Wipe onboarding + tour state and sign out — the full from-scratch S0 experience.
          </Text>
        </Pressable>

        {STAGES.map((s) => (
          <Pressable
            key={s.key}
            testID={`test-stages.spawn.${s.key}`}
            style={({ pressed }) => [styles.card, pressed && styles.pressed]}
            onPress={() => spawn(s.key)}
            disabled={!!busy}
          >
            <Text style={styles.name}>{busy === s.key ? 'Spawning…' : s.name}</Text>
            <Text style={styles.desc}>{s.desc}</Text>
          </Pressable>
        ))}

        {note ? <Text testID="test-stages.note" style={styles.note}>{note}</Text> : null}

        <Text style={styles.foot}>
          Spawned users persist server-side until deleted (DELETE /api/test-users/&lt;id&gt;).
          To return to your real account: sign out and sign back in with your username.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  body: { padding: space.xl, gap: space.md },
  h1: { ...type.heading, marginTop: space.sm },
  sub: { ...type.bodySm, color: chalk.dim, marginBottom: space.md },
  card: {
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.md,
    padding: space.lg,
    gap: 4,
  },
  cardDanger: { borderColor: semantic.neg },
  pressed: { backgroundColor: ink.ink3 },
  name: { ...type.title },
  desc: { ...type.bodySm, color: chalk.dim },
  note: {
    ...type.bodySm,
    color: ice.base,
    fontFamily: fonts.uiSemi,
    marginTop: space.sm,
  },
  foot: { ...type.bodySm, color: chalk.faint, marginTop: space.lg },
});

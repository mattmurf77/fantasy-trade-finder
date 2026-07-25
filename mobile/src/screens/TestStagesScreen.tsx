import React, { useEffect, useState } from 'react';
import { View, Text, Pressable, ScrollView, StyleSheet, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { TickLabel } from '../components/chalkline';
import { api, apiRequest, getDeviceId, setSessionToken } from '../api/client';
import { useSession } from '../state/useSession';
import { replaceOnboardingState } from '../state/useOnboardingState';
import type { OnboardingPersisted } from '../state/useOnboardingState';

// Test Stages — operator QA tool (flag `testing.stage_users` + server-side
// tester allowlist). Spawns a synthetic `qa_*` user at an adoption stage and
// swaps this device into it (token + user + league + ftf_onboarding_state),
// so any point of the onboarding flow is reachable in two taps, repeatably.
//
// League source: either the seeded DEMO fixture (default) or a CAPTURED
// TEMPLATE — an isolated snapshot of the operator's real Sleeper league(s)
// (real player pool, real opponents' rosters, real format), invisible to
// normal users and excluded from analytics. Templates + overrides let the
// SF/1QB, single/multi-league, and ranked-opponent branches all be tested.

interface TemplateRow {
  template_id: string;
  source_league_name: string;
  format: string;
  team_count: number;
  is_dynasty: boolean;
}

interface SpawnResponse {
  session_token: string;
  user_id: string;
  username: string;
  display_name: string;
  league_id: string;
  league_name: string;
  stage: string;
  format: string;
  template_id: string | null;
  leagues: Array<{ league_id: string; league_name: string }>;
  client_state: Partial<OnboardingPersisted>;
}

const STAGES: Array<{
  key: 'fresh' | 'activated' | 'board_owner' | 'converted' | 'power';
  name: string;
  desc: string;
}> = [
  { key: 'fresh', name: 'Fresh', desc: 'Signed in, consensus board, zero activity — first-run Trades.' },
  { key: 'activated', name: 'Activated', desc: '5 swipes on record — Quick Set pitch territory (S3).' },
  { key: 'board_owner', name: 'Board owner', desc: 'WR quickset persisted — next-position ask (S5.5).' },
  { key: 'converted', name: 'Converted', desc: 'Board owner + verified; Apple prompts consumed.' },
  { key: 'power', name: 'Power user', desc: 'All four positions ranked + verified; tour complete.' },
];

const FORMATS: Array<{ key: string; label: string }> = [
  { key: '1qb_ppr', label: '1QB PPR' },
  { key: 'sf_tep', label: 'SF TEP' },
];

// Radio dot (Chalkline has no circle icon) — filled ice when selected.
function Radio({ on }: { on: boolean }) {
  return (
    <View style={[styles.radio, on && styles.radioOn]}>
      {on ? <View style={styles.radioDot} /> : null}
    </View>
  );
}

// Small segmented control (Chalkline pills; ice = selected).
function Segmented<T extends string>({
  options, value, onChange, disabled,
}: {
  options: Array<{ key: T; label: string }>;
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
}) {
  return (
    <View style={styles.segRow}>
      {options.map((o) => {
        const on = o.key === value;
        return (
          <Pressable
            key={o.key}
            testID={`test-stages.seg.${o.key}`}
            accessibilityRole="button"
            disabled={disabled}
            onPress={() => onChange(o.key)}
            style={[styles.seg, on && styles.segOn, disabled && styles.segDisabled]}
          >
            <Text style={[styles.segText, on && styles.segTextOn]}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function TestStagesScreen() {
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [templates, setTemplates] = useState<TemplateRow[]>([]);
  // Source: null = demo fixture; else a template_id.
  const [source, setSource] = useState<string | null>(null);
  const [format, setFormat] = useState<string>('1qb_ppr');
  const [leagues, setLeagues] = useState<1 | 2>(1);
  const [oppRanked, setOppRanked] = useState(false);

  const setUser = useSession((s) => s.setUser);
  const setLeague = useSession((s) => s.setLeague);
  const setLeagues2 = useSession((s) => s.setLeagues);
  const signOut = useSession((s) => s.signOut);
  const currentUser = useSession((s) => s.user);

  async function loadTemplates() {
    try {
      const res = await api.get<{ templates: TemplateRow[] }>('/api/test-users/templates', {
        headers: { 'X-Device-Id': await getDeviceId() },
      });
      setTemplates(res.templates || []);
    } catch {
      /* non-fatal — demo path still works */
    }
  }
  useEffect(() => { void loadTemplates(); }, []);

  // Keep format synced to the selected template's real format.
  useEffect(() => {
    if (source) {
      const t = templates.find((x) => x.template_id === source);
      if (t) setFormat(t.format);
    }
  }, [source, templates]);

  async function captureTemplates() {
    setBusy('capture');
    setNote(null);
    try {
      const res = await api.post<{ templates: TemplateRow[]; captured: number }>(
        '/api/test-users/templates',
        {},
        { headers: { 'X-Device-Id': await getDeviceId() } },
      );
      setTemplates(res.templates || []);
      setNote(
        `Captured ${res.captured} league snapshot${res.captured === 1 ? '' : 's'} from your account. ` +
          'Pick one as the source below.',
      );
    } catch (e: any) {
      setNote(
        e?.message ||
          'Capture failed — sign in as yourself (not a qa_ user) so your real leagues are resolvable.',
      );
    } finally {
      setBusy(null);
    }
  }

  function confirmDeleteTemplate(t: TemplateRow) {
    Alert.alert(
      `Delete template?`,
      `Removes the snapshot of "${t.source_league_name}" and every qa_ user bound to it. Your real league is untouched.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await apiRequest(`/api/test-users/templates/${t.template_id}`, {
                method: 'DELETE',
                headers: { 'X-Device-Id': await getDeviceId() },
              });
              if (source === t.template_id) setSource(null);
              void loadTemplates();
            } catch (e: any) {
              setNote(e?.message || 'Delete failed.');
            }
          },
        },
      ],
    );
  }

  async function factoryReset() {
    setBusy('factory');
    try {
      replaceOnboardingState({});
      await signOut();
    } finally {
      setBusy(null);
    }
  }

  async function spawn(stage: (typeof STAGES)[number]['key']) {
    setBusy(stage);
    setNote(null);
    try {
      const body: Record<string, unknown> = { stage };
      if (source) {
        body.template_id = source;
        body.format = format;
        body.leagues = leagues;
        body.opponents_ranked = oppRanked;
      }
      const res = await api.post<SpawnResponse>('/api/test-users', body, {
        headers: { 'X-Device-Id': await getDeviceId() },
      });
      await setSessionToken(res.session_token);
      await setUser({
        user_id: res.user_id,
        username: res.username,
        display_name: res.display_name,
        avatar_id: null,
      });
      // Multi-league spawns populate the picker list; single leaves it empty
      // so the auto-skip path is exercised.
      await setLeagues2(
        (res.leagues || []).length > 1
          ? res.leagues.map((l) => ({
              league_id: l.league_id,
              name: l.league_name,
              total_rosters: undefined,
            }))
          : [],
      );
      await setLeague({ league_id: res.league_id, league_name: res.league_name });
      replaceOnboardingState(res.client_state || {});
      const src = res.template_id ? 'cloned league' : 'demo league';
      setNote(
        `Now ${res.username} · ${res.stage} · ${res.format} · ${src}. ` +
          'Force-quit and reopen for a fully clean run.',
      );
    } catch (e: any) {
      setNote(e?.message || 'Spawn failed — is this device allowlisted?');
    } finally {
      setBusy(null);
    }
  }

  const usingTemplate = !!source;

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body}>
        <TickLabel>Operator QA · synthetic users</TickLabel>
        <Text style={styles.h1} accessibilityRole="header">Test Stages</Text>
        <Text style={styles.sub}>
          Spawn a throwaway qa_* user at an adoption stage and swap this device into it.
          Excluded from analytics. Current: {currentUser?.username || '—'}.
        </Text>

        {/* ── League source ─────────────────────────────────────────── */}
        <View style={styles.section}><TickLabel>League source</TickLabel></View>

        <Pressable
          testID="test-stages.source.demo"
          accessibilityRole="button"
          onPress={() => setSource(null)}
          style={[styles.srcRow, !source && styles.srcRowOn]}
        >
          <Radio on={!source} />
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>Demo fixture</Text>
            <Text style={styles.desc}>Seeded synthetic league — fast, no Sleeper data.</Text>
          </View>
        </Pressable>

        {templates.map((t) => {
          const on = source === t.template_id;
          return (
            <Pressable
              key={t.template_id}
              testID={`test-stages.source.${t.template_id}`}
              accessibilityRole="button"
              onPress={() => setSource(t.template_id)}
              onLongPress={() => confirmDeleteTemplate(t)}
              style={[styles.srcRow, on && styles.srcRowOn]}
            >
              <Radio on={on} />
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{t.source_league_name}</Text>
                <Text style={styles.desc}>
                  {t.format === 'sf_tep' ? 'SF TEP' : '1QB PPR'} · {t.team_count} teams · cloned from your account
                </Text>
              </View>
            </Pressable>
          );
        })}

        <Pressable
          testID="test-stages.capture"
          accessibilityRole="button"
          onPress={captureTemplates}
          disabled={!!busy}
          style={({ pressed }) => [styles.captureBtn, pressed && styles.pressed]}
        >
          <Text style={styles.captureText}>
            {busy === 'capture' ? 'Capturing…' : '+ Capture my leagues'}
          </Text>
        </Pressable>
        <Text style={styles.hint}>
          Snapshots your real Sleeper league(s) into isolated test copies. Sign in as yourself
          first (not a qa_ user). Long-press a template to delete it.
        </Text>

        {/* ── Config (template-only overrides) ──────────────────────── */}
        {usingTemplate ? (
          <>
            <View style={styles.section}><TickLabel>Config</TickLabel></View>
            <Text style={styles.cfgLabel}>Scoring format</Text>
            <Segmented options={FORMATS} value={format} onChange={setFormat} disabled={!!busy} />
            <Text style={styles.cfgLabel}>Leagues (multi exercises the picker)</Text>
            <Segmented
              options={[{ key: '1', label: '1 · auto-skip' }, { key: '2', label: '2 · picker' }]}
              value={String(leagues)}
              onChange={(v) => setLeagues(v === '2' ? 2 : 1)}
              disabled={!!busy || templates.length < 2}
            />
            {templates.length < 2 ? (
              <Text style={styles.hint}>Capture ≥2 leagues to test the multi-league picker.</Text>
            ) : null}
            <Pressable
              testID="test-stages.opp-ranked"
              accessibilityRole="switch"
              accessibilityState={{ checked: oppRanked }}
              onPress={() => setOppRanked((v) => !v)}
              disabled={!!busy}
              style={styles.toggleRow}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>Ranked opponents</Text>
                <Text style={styles.desc}>Seed a couple of opponents with boards (mutual-match / likes-you).</Text>
              </View>
              <View style={[styles.switch, oppRanked && styles.switchOn]}>
                <View style={[styles.knob, oppRanked && styles.knobOn]} />
              </View>
            </Pressable>
          </>
        ) : null}

        {/* ── Factory reset ─────────────────────────────────────────── */}
        <View style={styles.section}><TickLabel>Stages</TickLabel></View>
        <Pressable
          testID="test-stages.factory-reset"
          accessibilityRole="button"
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
            accessibilityRole="button"
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
          Spawned users persist server-side until deleted. To return to your real account:
          sign out and sign back in with your username.
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
  section: { marginTop: space.md },
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
  hint: { ...type.bodySm, color: chalk.faint },
  // source rows
  srcRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.md,
    padding: space.lg,
  },
  srcRowOn: { borderColor: ice.base },
  radio: {
    width: 18, height: 18, borderRadius: 9,
    borderWidth: 1.5, borderColor: chalk.faint,
    alignItems: 'center', justifyContent: 'center',
  },
  radioOn: { borderColor: ice.base },
  radioDot: { width: 9, height: 9, borderRadius: 4.5, backgroundColor: ice.base },
  captureBtn: {
    borderWidth: 1,
    borderColor: ice.base,
    borderRadius: radii.sm,
    alignItems: 'center',
    paddingVertical: space.md,
  },
  captureText: { color: ice.base, fontFamily: fonts.uiSemi, fontSize: 14 },
  // config
  cfgLabel: { ...type.bodySm, color: chalk.dim, marginTop: space.sm },
  segRow: { flexDirection: 'row', gap: space.sm },
  seg: {
    flex: 1,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingVertical: space.sm,
    alignItems: 'center',
  },
  segOn: { borderColor: ice.base, backgroundColor: ink.ink3 },
  segDisabled: { opacity: 0.4 },
  segText: { ...type.bodySm, color: chalk.dim },
  segTextOn: { color: ice.base, fontFamily: fonts.uiSemi },
  toggleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.md,
    padding: space.lg,
    marginTop: space.sm,
  },
  switch: {
    width: 44, height: 26, borderRadius: 13,
    backgroundColor: ink.ink3, borderWidth: 1, borderColor: ink.lineStrong,
    justifyContent: 'center', paddingHorizontal: 2,
  },
  switchOn: { backgroundColor: ice.base, borderColor: ice.base },
  knob: { width: 20, height: 20, borderRadius: 10, backgroundColor: chalk.faint },
  knobOn: { backgroundColor: ice.on, alignSelf: 'flex-end' },
  note: { ...type.bodySm, color: ice.base, fontFamily: fonts.uiSemi, marginTop: space.sm },
  foot: { ...type.bodySm, color: chalk.faint, marginTop: space.lg },
});

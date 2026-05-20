import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Switch,
  ScrollView,
  ActivityIndicator,
  Pressable,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { colors } from '../theme/colors';
import { spacing, radius, fontSize } from '../theme/spacing';
import Toast from '../components/Toast';
import { getNotifPrefs, updateNotifPrefs } from '../api/notifications';
import { useSession } from '../state/useSession';
import type { NotificationPrefs } from '../shared/types';

// Settings sheet shown as a modal from the gear icon in the global TopBar.
// Currently a single section (notification prefs); designed to grow as more
// preferences land.
//
// Optimistic toggles: each Switch flips local state immediately, fires a
// PUT, and only reverts on server error. We surface a toast for failures
// rather than a full-screen error so the user can keep flipping.
export default function SettingsScreen({ navigation }: any) {
  const queryClient = useQueryClient();
  const signOut = useSession((s) => s.signOut);
  // B3 — Multi-league controls (Switch / Add another league).
  const leagues       = useSession((s) => s.leagues);
  const activeLeague  = useSession((s) => s.league);
  const switchLeague  = useSession((s) => s.switchLeague);
  const connectLeague = useSession((s) => s.connectLeague);
  const switching     = useSession((s) => s.switching);
  const [busyLeagueId, setBusyLeagueId] = useState<string | null>(null);
  const [connectUrl, setConnectUrl] = useState('');
  const [connectBusy, setConnectBusy] = useState(false);
  const [toast, setToast] = useState<{ msg: string; tone?: 'success' | 'warn' } | null>(null);
  // Local mirror of server prefs so toggles feel instant. Hydrated from the
  // query below; updates push through `mutation` and the query is invalidated
  // on success.
  const [local, setLocal] = useState<NotificationPrefs | null>(null);

  const prefsQuery = useQuery({
    queryKey: ['notif-prefs'],
    queryFn: getNotifPrefs,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (prefsQuery.data) setLocal(prefsQuery.data);
  }, [prefsQuery.data]);

  const mutation = useMutation({
    mutationFn: (patch: Partial<NotificationPrefs>) => updateNotifPrefs(patch),
    onError: () => {
      // Roll back local state to last-known-good server value.
      if (prefsQuery.data) setLocal(prefsQuery.data);
      setToast({ msg: "Couldn't save — try again.", tone: 'warn' });
    },
    onSuccess: (next) => {
      setLocal(next);
      queryClient.setQueryData(['notif-prefs'], next);
    },
  });

  const flip = (key: keyof NotificationPrefs) => {
    if (!local) return;
    const nextVal = local[key] ? 0 : 1;
    setLocal({ ...local, [key]: nextVal as 0 | 1 });
    mutation.mutate({ [key]: nextVal as 0 | 1 } as Partial<NotificationPrefs>);
  };

  // ── B3 multi-league handlers ───────────────────────────────────
  async function handleSwitch(lgId: string, lgName: string) {
    if (busyLeagueId) return;
    if (lgId === activeLeague?.league_id) return;
    setBusyLeagueId(lgId);
    try {
      await switchLeague({ league_id: lgId, league_name: lgName });
      setToast({ msg: `Switched to ${lgName}`, tone: 'success' });
    } catch (e: any) {
      setToast({ msg: e?.message || 'Failed to switch', tone: 'warn' });
    } finally {
      setBusyLeagueId(null);
    }
  }

  async function handleConnect() {
    const url = connectUrl.trim();
    if (!url || connectBusy) return;
    setConnectBusy(true);
    try {
      const result = await connectLeague(url);
      if (!result.ok) {
        // Backend recognized a non-Sleeper URL — surface as a soft warn.
        const label =
          result.platform === 'espn' ? 'ESPN' :
          result.platform === 'mfl'  ? 'MyFantasyLeague' :
          'That platform';
        setToast({
          msg: `${label} sync isn't supported yet — Sleeper URLs only.`,
          tone: 'warn',
        });
        return;
      }
      setConnectUrl('');
      // Refresh portfolio so the newly-connected league lights it up
      // immediately if the user navigates there next.
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      setToast({ msg: `Connected ${result.league_name}`, tone: 'success' });
    } catch (e: any) {
      setToast({ msg: e?.message || 'Could not connect that league', tone: 'warn' });
    } finally {
      setConnectBusy(false);
    }
  }

  if (prefsQuery.isLoading || !local) {
    return (
      <SafeAreaView style={styles.root} edges={['bottom']}>
        <View style={styles.loading}>
          <ActivityIndicator color={colors.accent} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.root} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        {/* B3 — Multi-league: switch + add. The Switch section is hidden
            when the user only has one league so single-league users see
            just the "Connect another league" card. */}
        {leagues.length > 1 ? (
          <>
            <Text style={styles.section}>Switch league</Text>
            {leagues.map((lg) => {
              const isActive = lg.league_id === activeLeague?.league_id;
              const isBusy   = busyLeagueId === lg.league_id || (switching && isActive);
              const dim      = (busyLeagueId !== null && !isBusy) || (switching && !isActive);
              return (
                <Pressable
                  key={lg.league_id}
                  onPress={() => handleSwitch(lg.league_id, lg.name)}
                  disabled={busyLeagueId !== null || switching || isActive}
                  style={({ pressed }) => [
                    styles.leagueRow,
                    isActive && styles.leagueRowActive,
                    dim && styles.leagueRowDim,
                    pressed && !dim && !isActive && { opacity: 0.7 },
                  ]}
                >
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={styles.leagueName} numberOfLines={1}>{lg.name}</Text>
                    <Text style={styles.leagueMeta}>
                      {(lg.total_rosters as number | undefined) || 12} teams
                    </Text>
                  </View>
                  {isBusy ? (
                    <ActivityIndicator color={colors.accent} />
                  ) : isActive ? (
                    <Text style={styles.check}>✓</Text>
                  ) : null}
                </Pressable>
              );
            })}
          </>
        ) : null}

        <Text style={styles.section}>
          {leagues.length > 1 ? 'Add another league' : 'Connect another league'}
        </Text>
        <View style={styles.connectCard}>
          <Text style={styles.connectHelp}>
            Paste a Sleeper league URL (or bare league ID) to sync it.
          </Text>
          <TextInput
            value={connectUrl}
            onChangeText={setConnectUrl}
            placeholder="sleeper.com/leagues/..."
            placeholderTextColor={colors.muted}
            autoCapitalize="none"
            autoCorrect={false}
            editable={!connectBusy}
            style={styles.connectInput}
          />
          <Pressable
            onPress={handleConnect}
            disabled={!connectUrl.trim() || connectBusy}
            style={({ pressed }) => [
              styles.connectBtn,
              (!connectUrl.trim() || connectBusy) && styles.connectBtnDisabled,
              pressed && connectUrl.trim() && !connectBusy && { opacity: 0.85 },
            ]}
          >
            {connectBusy ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.connectBtnText}>Connect</Text>
            )}
          </Pressable>
        </View>

        <Text style={styles.section}>Notifications</Text>

        <Row
          title="Trade matches"
          sub="New matches, counter-offers, league activity"
          value={!!local.trade_matches}
          onChange={() => flip('trade_matches')}
        />
        <Row
          title="Weekly digest"
          sub="Tuesday/Wednesday morning roundup"
          value={!!local.weekly_digest}
          onChange={() => flip('weekly_digest')}
        />
        <Row
          title="Stay in the game"
          sub="Occasional nudges if you've been away"
          value={!!local.reengagement}
          onChange={() => flip('reengagement')}
        />

        <Text style={styles.section}>Quiet hours</Text>
        <Row
          title="Pause overnight (10pm – 8am)"
          sub="Notifications will bundle into one summary at 8am local"
          value={!!local.quiet_hours_enabled}
          onChange={() => flip('quiet_hours_enabled')}
        />
        <View style={styles.tzRow}>
          <Text style={styles.tzLabel}>Time zone</Text>
          <Text style={styles.tzValue}>{local.tz}</Text>
        </View>

        <View style={{ height: spacing.xxl }} />
        <Pressable
          onPress={async () => {
            await signOut();
            navigation.replace?.('SignIn');
          }}
          style={({ pressed }) => [styles.signOut, pressed && { opacity: 0.7 }]}
        >
          <Text style={styles.signOutText}>Sign out</Text>
        </Pressable>
      </ScrollView>
      <Toast
        visible={!!toast}
        message={toast?.msg ?? ''}
        tone={toast?.tone}
        onDismiss={() => setToast(null)}
      />
    </SafeAreaView>
  );
}

function Row({
  title, sub, value, onChange,
}: { title: string; sub?: string; value: boolean; onChange: () => void }) {
  return (
    <View style={styles.row}>
      <View style={{ flex: 1, paddingRight: spacing.md }}>
        <Text style={styles.rowTitle}>{title}</Text>
        {sub ? <Text style={styles.rowSub}>{sub}</Text> : null}
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: colors.border, true: colors.accent }}
        thumbColor="#fff"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  body: { padding: spacing.lg, gap: spacing.sm },
  section: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginTop: spacing.lg,
    marginBottom: spacing.xs,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  rowTitle: { color: colors.text, fontSize: fontSize.base, fontWeight: '700' },
  rowSub: { color: colors.muted, fontSize: fontSize.xs, marginTop: 2, lineHeight: 18 },
  tzRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  tzLabel: { color: colors.text, fontSize: fontSize.base, fontWeight: '700' },
  tzValue: { color: colors.muted, fontSize: fontSize.base },
  signOut: {
    padding: spacing.md,
    alignItems: 'center',
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  signOutText: { color: colors.red, fontWeight: '700', fontSize: fontSize.base },
  // B3 — Switch league row + Connect another league card
  leagueRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  leagueRowActive: {
    borderColor: colors.accent,
    backgroundColor: 'rgba(79,124,255,0.08)',
  },
  leagueRowDim: { opacity: 0.45 },
  leagueName: { color: colors.text, fontSize: fontSize.base, fontWeight: '700' },
  leagueMeta: { color: colors.muted, fontSize: fontSize.xs, marginTop: 2 },
  check: { color: colors.accent, fontSize: 22, fontWeight: '800' },
  connectCard: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  connectHelp: {
    color: colors.muted,
    fontSize: fontSize.xs,
    lineHeight: 18,
  },
  connectInput: {
    color: colors.text,
    fontSize: fontSize.sm,
    backgroundColor: colors.bg,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
  },
  connectBtn: {
    backgroundColor: colors.accent,
    paddingVertical: spacing.sm + 2,
    borderRadius: radius.md,
    alignItems: 'center',
  },
  connectBtnDisabled: {
    opacity: 0.45,
  },
  connectBtnText: {
    color: '#fff',
    fontSize: fontSize.base,
    fontWeight: '800',
  },
});

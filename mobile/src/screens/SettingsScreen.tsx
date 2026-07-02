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

import { ink, chalk, volt, semantic, space, radii, type } from '../theme/chalkline';
import { TickLabel, Button, Card, Icon } from '../components/chalkline';
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
          <ActivityIndicator color={volt.base} />
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
            <View style={styles.section}>
              <TickLabel>Switch league</TickLabel>
            </View>
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
                    dim && styles.rowDim,
                    pressed && !dim && !isActive && styles.rowPressed,
                  ]}
                >
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={styles.leagueName} numberOfLines={1}>{lg.name}</Text>
                    <Text style={styles.leagueMeta}>
                      <Text style={styles.leagueMetaCount}>
                        {(lg.total_rosters as number | undefined) || 12}
                      </Text>
                      {' teams'}
                    </Text>
                  </View>
                  {isBusy ? (
                    <ActivityIndicator color={chalk.dim} />
                  ) : isActive ? (
                    <Icon name="check" color={volt.base} />
                  ) : null}
                </Pressable>
              );
            })}
          </>
        ) : null}

        <View style={styles.section}>
          <TickLabel>
            {leagues.length > 1 ? 'Add another league' : 'Connect another league'}
          </TickLabel>
        </View>
        <Card>
          <View style={styles.connectBody}>
            <Text style={styles.connectHelp}>
              Paste a Sleeper league URL (or bare league ID) to sync it.
            </Text>
            <TextInput
              value={connectUrl}
              onChangeText={setConnectUrl}
              placeholder="sleeper.com/leagues/..."
              placeholderTextColor={chalk.faint}
              autoCapitalize="none"
              autoCorrect={false}
              editable={!connectBusy}
              style={styles.connectInput}
            />
            <Button
              label="Connect"
              onPress={handleConnect}
              disabled={!connectUrl.trim() || connectBusy}
            />
          </View>
        </Card>

        <View style={styles.section}>
          <TickLabel>Notifications</TickLabel>
        </View>

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

        <View style={styles.section}>
          <TickLabel>Quiet hours</TickLabel>
        </View>
        <Row
          title="Pause overnight (10pm – 8am)"
          sub="Notifications will bundle into one summary at 8am local"
          value={!!local.quiet_hours_enabled}
          onChange={() => flip('quiet_hours_enabled')}
        />
        <View style={styles.kvRow}>
          <Text style={styles.rowKey}>Time zone</Text>
          <Text style={styles.kvValue}>{local.tz}</Text>
        </View>

        <View style={styles.section}>
          <TickLabel>Testing</TickLabel>
        </View>
        <Pressable
          onPress={() => navigation.navigate?.('FeedbackInbox')}
          style={({ pressed }) => [styles.linkRow, pressed && styles.rowPressed]}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.rowKey}>Test feedback</Text>
            <Text style={styles.rowSub}>
              Review and share notes you captured with the floating button.
            </Text>
          </View>
          <Icon name="chevron-right" color={chalk.dim} size={16} />
        </Pressable>

        <View style={{ height: space.xxl }} />
        <Pressable
          onPress={async () => {
            await signOut();
            navigation.replace?.('SignIn');
          }}
          style={({ pressed }) => [styles.signOut, pressed && styles.rowPressed]}
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
      <View style={{ flex: 1, paddingRight: space.md }}>
        <Text style={styles.rowKey}>{title}</Text>
        {sub ? <Text style={styles.rowSub}>{sub}</Text> : null}
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: ink.ink3, true: volt.base }}
        thumbColor={chalk.base}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: ink.ink0 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  body: { padding: space.lg },
  section: {
    marginTop: space.xl,
    marginBottom: space.sm,
  },
  // Hairline key-value / toggle rows — surface stays ink-0, depth via lines.
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  rowKey: type.label,
  rowSub: {
    ...type.bodySm,
    marginTop: space.xs,
  },
  kvRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  kvValue: type.body,
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  rowPressed: { backgroundColor: ink.ink3 },
  rowDim: { opacity: 0.45 },
  signOut: {
    minHeight: 44,
    paddingVertical: space.md,
    justifyContent: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ink.line,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  signOutText: {
    ...type.body,
    color: semantic.neg,
  },
  // B3 — Switch league rows + Connect another league card
  leagueRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    minHeight: 44,
    paddingVertical: space.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: ink.line,
  },
  leagueName: type.title,
  leagueMeta: {
    ...type.bodySm,
    marginTop: space.xs,
  },
  leagueMetaCount: {
    ...type.data,
    color: chalk.dim,
  },
  connectBody: { gap: space.md },
  connectHelp: type.bodySm,
  connectInput: {
    ...type.body,
    height: 44,
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
  },
});

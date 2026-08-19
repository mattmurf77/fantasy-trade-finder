// Leagues — switch-league rows + the "connect a league" card.
//
// Extracted verbatim from SettingsScreen.tsx (origin/main):
//   • `leagueSwitchRows`            :767-808
//   • `leagueConnectCard`           :811-834
//   • `handleSwitch` / `handleConnect` :695-746
//   • the useSession slice they read  :86-95
//
// SECTION BANNER: none. The host page owns the <TickLabel>Leagues</TickLabel>
// (plan §3 — `SettingsLeagues` owns the banner; today's flat v2 list renders it
// at SettingsScreen.tsx:1483). This module exports the rows only.
//
// Behavior changes: none. No network query lives here, so there is nothing to
// gate on — the rows render from the session store, exactly as shipped.

import React, { useState } from 'react';
import { ActivityIndicator, Pressable, Text, TextInput, View } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';

import { chalk, ice } from '../../../theme/chalkline';
import { Button, Card, Icon } from '../../../components/chalkline';
import { useSession } from '../../../state/useSession';
import { styles } from '../styles';
import type { SettingsSectionProps } from './types';

export default function LeaguesSection({ onNotice }: SettingsSectionProps) {
  const queryClient = useQueryClient();
  // B3 — Multi-league controls (Switch / Add another league).
  const leagues       = useSession((s) => s.leagues);
  const activeLeague  = useSession((s) => s.league);
  const switchLeague  = useSession((s) => s.switchLeague);
  const connectLeague = useSession((s) => s.connectLeague);
  const switching     = useSession((s) => s.switching);
  const user          = useSession((s) => s.user);
  const [busyLeagueId, setBusyLeagueId] = useState<string | null>(null);
  const [connectUrl, setConnectUrl] = useState('');
  const [connectBusy, setConnectBusy] = useState(false);

  // ── B3 multi-league handlers ───────────────────────────────────
  async function handleSwitch(lgId: string, lgName: string) {
    if (busyLeagueId) return;
    if (lgId === activeLeague?.league_id) return;
    setBusyLeagueId(lgId);
    try {
      await switchLeague({ league_id: lgId, league_name: lgName });
      onNotice(`Switched to ${lgName}`, 'success');
    } catch (e: any) {
      onNotice(e?.message || 'Failed to switch', 'warn');
    } finally {
      setBusyLeagueId(null);
    }
  }

  async function handleConnect() {
    const url = connectUrl.trim();
    if (!url || connectBusy) return;
    if (user?.account_only) {
      // Account-first (P2.6): no Sleeper user to attach leagues to yet.
      onNotice('Link your Sleeper username under Account first.', 'warn');
      return;
    }
    setConnectBusy(true);
    try {
      const result = await connectLeague(url);
      if (!result.ok) {
        // Backend recognized a non-Sleeper URL — surface as a soft warn.
        const label =
          result.platform === 'espn' ? 'ESPN' :
          result.platform === 'mfl'  ? 'MyFantasyLeague' :
          'That platform';
        onNotice(`${label} sync isn't supported yet — Sleeper URLs only.`, 'warn');
        return;
      }
      setConnectUrl('');
      // Refresh portfolio so the newly-connected league lights it up
      // immediately if the user navigates there next.
      queryClient.invalidateQueries({ queryKey: ['portfolio'] });
      onNotice(`Connected ${result.league_name}`, 'success');
    } catch (e: any) {
      onNotice(e?.message || 'Could not connect that league', 'warn');
    } finally {
      setConnectBusy(false);
    }
  }

  // B3 — Multi-league: switch + add. The Switch section is hidden when the
  // user only has one league so single-league users see just the "Connect
  // another league" card.
  const leagueSwitchRows = leagues.length > 1 ? (
    <>
      {leagues.map((lg) => {
        const isActive = lg.league_id === activeLeague?.league_id;
        const isBusy   = busyLeagueId === lg.league_id || (switching && isActive);
        const dim      = (busyLeagueId !== null && !isBusy) || (switching && !isActive);
        return (
          <Pressable
            key={lg.league_id}
            accessibilityRole="button"
            accessibilityLabel={`${lg.name}, ${(lg.total_rosters as number | undefined) || 12} teams`}
            accessibilityState={{
              selected: isActive,
              disabled: busyLeagueId !== null || switching || isActive,
            }}
            accessibilityHint={isActive ? 'Currently active league' : 'Switches to this league'}
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
              <Icon name="check" color={ice.base} />
            ) : null}
          </Pressable>
        );
      })}
    </>
  ) : null;

  const leagueConnectCard = (
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
  );

  return (
    <>
      {leagueSwitchRows}
      {leagueConnectCard}
    </>
  );
}

import React, { useCallback, useRef, useState } from 'react';
import { Alert, Linking, ViewStyle } from 'react-native';
import * as Haptics from 'expo-haptics';
import { useNavigation } from '@react-navigation/native';
import Button from './chalkline/Button';
import { useFlag } from '../state/useFeatureFlags';
import { proposeTradeToSleeper } from '../api/sendInSleeper';
import { ApiError } from '../api/client';

// Slice 3 of "Send in Sleeper". Renders on any real trade surface (found /
// matched / suggested). Flag-gated: returns null when `trade.send_in_sleeper`
// is off. Not linked / expired → routes to the SleeperConnect webview; a hard
// Sleeper failure → deep-links into Sleeper so the user can finish manually.

interface Props {
  leagueId: string;
  theirUserId: string;
  givePlayerIds: string[];
  receivePlayerIds: string[];
  compact?: boolean;
  style?: ViewStyle;
}

type State = 'idle' | 'sending' | 'sent';

export default function SendInSleeperButton({
  leagueId,
  theirUserId,
  givePlayerIds,
  receivePlayerIds,
  compact,
  style,
}: Props) {
  const enabled = useFlag('trade.send_in_sleeper');
  const navigation = useNavigation<any>();
  const [state, setState] = useState<State>('idle');
  // Guards the reconnect bounce so a link that "succeeds" but still can't
  // propose can't loop the login webview forever. Reset per button instance.
  const reconnectedRef = useRef(false);

  const openInSleeper = useCallback(() => {
    const url = /^\d+$/.test(leagueId)
      ? `https://sleeper.com/leagues/${leagueId}`
      : 'https://sleeper.com';
    Linking.openURL(url).catch(() => {});
  }, [leagueId]);

  const doPropose = useCallback(async () => {
    setState('sending');
    try {
      await proposeTradeToSleeper({
        league_id: leagueId,
        their_user_id: theirUserId,
        give_player_ids: givePlayerIds,
        receive_player_ids: receivePlayerIds,
      });
      setState('sent');
      reconnectedRef.current = false;
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
      Alert.alert('Trade sent ✅', 'Check your Sleeper app for the pending offer.');
    } catch (err) {
      setState('idle');
      const body = err instanceof ApiError ? (err.body as any) : undefined;
      const code: string | undefined = body?.error;
      const detail: string | undefined = body?.detail;

      if (code === 'sleeper_not_linked' || code === 'sleeper_expired') {
        // Legitimate "need a (fresh) token" — send them to reconnect ONCE.
        // If we already reconnected this session and it STILL comes back
        // unlinked, that's a persistence problem, not a login problem — stop
        // looping and say so.
        if (reconnectedRef.current) {
          Alert.alert(
            'Couldn’t connect',
            'Your Sleeper connection didn’t stick. Please try again in a moment.',
          );
          return;
        }
        reconnectedRef.current = true;
        navigation.navigate('SleeperConnect');
      } else if (code === 'sleeper_rejected') {
        // Sleeper accepted the login but rejected the trade write. Reconnecting
        // re-captures the SAME token, so do NOT bounce to login. Surface the
        // reason so we can fix the integration.
        Alert.alert(
          'Sleeper wouldn’t accept the send',
          `Sleeper rejected the request${detail ? `:\n\n${detail}` : '.'}`,
        );
      } else if (code === 'sleeper_unconfigured' || code === 'feature_disabled') {
        Alert.alert('Send in Sleeper', 'Sending isn’t available right now.');
      } else if (code === 'roster_not_found' || code === 'opponent_roster_not_found') {
        Alert.alert(
          'Couldn’t send',
          'Couldn’t match one of the teams to a roster in this Sleeper league.',
        );
      } else {
        Alert.alert(
          'Couldn’t send',
          detail || 'Something went wrong sending to Sleeper. Please try again.',
        );
      }
    }
  }, [leagueId, theirUserId, givePlayerIds, receivePlayerIds, navigation]);

  const onPress = useCallback(() => {
    if (state !== 'idle') return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});

    // No real league/opponent to send to → hand off to Sleeper directly.
    if (!leagueId || !theirUserId) {
      openInSleeper();
      return;
    }

    Alert.alert(
      'Send this trade?',
      'This proposes the trade directly in Sleeper — your leaguemate gets it as a pending offer.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Send', onPress: () => { void doPropose(); } },
      ],
    );
  }, [state, leagueId, theirUserId, openInSleeper, doPropose]);

  if (!enabled) return null;

  const label =
    state === 'sent' ? 'Proposal sent' : state === 'sending' ? 'Sending…' : 'Send in Sleeper';

  return (
    <Button
      label={label}
      variant="secondary"
      compact={compact}
      disabled={state !== 'idle'}
      onPress={onPress}
      style={style}
    />
  );
}

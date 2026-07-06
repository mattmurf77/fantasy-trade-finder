import React, { useCallback, useState } from 'react';
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

  const openInSleeper = useCallback(() => {
    const url = /^\d+$/.test(leagueId)
      ? `https://sleeper.com/leagues/${leagueId}`
      : 'https://sleeper.com';
    Linking.openURL(url).catch(() => {});
  }, [leagueId]);

  const onPress = useCallback(async () => {
    if (state !== 'idle') return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});

    // No real league/opponent to send to → hand off to Sleeper directly.
    if (!leagueId || !theirUserId) {
      openInSleeper();
      return;
    }

    setState('sending');
    try {
      await proposeTradeToSleeper({
        league_id: leagueId,
        their_user_id: theirUserId,
        give_player_ids: givePlayerIds,
        receive_player_ids: receivePlayerIds,
      });
      setState('sent');
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    } catch (err) {
      setState('idle');
      const code = err instanceof ApiError ? (err.body as any)?.error : undefined;
      if (code === 'sleeper_not_linked' || code === 'sleeper_expired') {
        navigation.navigate('SleeperConnect');
      } else if (code === 'sleeper_unconfigured' || code === 'feature_disabled') {
        Alert.alert('Send in Sleeper', 'Sending isn’t available right now.');
      } else {
        // sleeper_write_failed / network / anything else → manual handoff.
        openInSleeper();
      }
    }
  }, [state, leagueId, theirUserId, givePlayerIds, receivePlayerIds, navigation, openInSleeper]);

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

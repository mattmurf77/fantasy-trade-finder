import React, { useCallback, useState } from 'react';
import { Alert, Linking, ViewStyle } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Button from './chalkline/Button';
import { haptics } from '../utils/haptics';
import { maybeRequestReview } from '../utils/ratingPrompt';
import { useFlag } from '../state/useFeatureFlags';
import { proposeTradeToMfl } from '../api/sendInMfl';
import { validateTradeSend } from '../api/sendInSleeper';
import { ApiError } from '../api/client';
import type { SendSurface } from '../utils/tradeText';

// "Send in MFL" — the MFL twin of SendInSleeperButton, mounted FOR MFL
// leagues BY SendInSleeperButton's platform branch (never mount this
// directly; the platform routing lives in one place so no surface can fire
// the wrong platform's API). Flag-gated: the router only mounts this when
// `trade.send_in_mfl` is ON (flag-off MFL leagues get the P0-6 reason +
// Copy-trade fallback there instead); the internal null below is
// defense-in-depth for a direct mount, never the user-visible flag-off path.
//
// Differences from the Sleeper twin, deliberate:
//   • No up-front link-status check — there is no GET status route for the
//     MFL cookie; the propose itself answers (409 mfl_not_connected /
//     mfl_auth_expired) and we route that to reconnect guidance.
//   • Reconnect = MFL sign-in (username/password via PlatformLinkSheet on
//     the league picker), not a token-capture webview — so the reconnect
//     CTA navigates to LeaguePicker rather than a dedicated connect screen.
//   • The server HARD-BLOCKS on any asset it can't map (422
//     mfl_asset_unmapped) — surfaced honestly, nothing partial is sent.
//   • Picks ride along: the asset arrays every trade surface passes are
//     MIXED (players + FTF pick ids). The server splits them and encodes
//     owned picks to MFL `FP_…` strings against the league's stored
//     futureDraftPicks snapshot; a pick it can't ground-truth (including
//     generic "Early 1st" rungs) hard-blocks the send like any other
//     unmapped asset. No client-side encoding, no client-side filtering.

interface Props {
  leagueId: string;
  /** Synthetic MFL member id (`mfl:{league}.f{franchise}`) — what MFL league
   *  members carry as opponent_user_id on every trade surface. */
  theirUserId: string;
  /** Mixed FTF asset ids (players + picks) — passed through verbatim; the
   *  server owns all MFL encoding and the never-drop-an-asset hard block. */
  givePlayerIds: string[];
  receivePlayerIds: string[];
  impressionId?: string;
  onSent?: () => void;
  compact?: boolean;
  style?: ViewStyle;
  /** P0-7 parity: which mount this is. REQUIRED (threaded by the router in
   *  SendInSleeperButton) so a missed mount is a compile error, matching the
   *  Sleeper twin. No MFL client events exist YET (`sleeper_send_*` are
   *  Sleeper-named and MFL siblings are unregistered in the taxonomy), so
   *  today this prop is carried, not fired — the moment MFL attempt/failure
   *  events are registered, the dimension is already at hand. */
  surface: SendSurface;
}

type State = 'idle' | 'checking' | 'sending' | 'sent';

export default function SendInMflButton({
  leagueId,
  theirUserId,
  givePlayerIds,
  receivePlayerIds,
  impressionId,
  onSent,
  compact,
  style,
  // Carried for P0-7 parity (see Props); intentionally unread until MFL
  // attempt/failure events are registered in the taxonomy.
  surface: _surface,
}: Props) {
  const enabled = useFlag('trade.send_in_mfl');
  const navigation = useNavigation<any>();
  const [state, setState] = useState<State>('idle');

  const openMfl = useCallback(() => {
    Linking.openURL('https://www.myfantasyleague.com').catch(() => {});
  }, []);

  // MFL sign-in lives in PlatformLinkSheet on the league picker ("Add
  // league" → MFL → Sign in). No dedicated connect screen exists to deep
  // link into, so reconnect guidance lands the user there.
  const goReconnect = useCallback(() => {
    navigation.navigate('LeaguePicker');
  }, [navigation]);

  const doPropose = useCallback(async () => {
    setState('sending');
    try {
      await proposeTradeToMfl({
        league_id: leagueId,
        their_user_id: theirUserId,
        give_player_ids: givePlayerIds,
        receive_player_ids: receivePlayerIds,
        impression_id: impressionId,
      });
      setState('sent');
      haptics.success();
      try {
        onSent?.();
      } catch {
        /* tally must never break the send flow */
      }
      Alert.alert('Trade sent', 'Check MFL for the pending offer.', [
        { text: 'OK', onPress: () => void maybeRequestReview('send_in_mfl') },
      ]);
    } catch (err) {
      setState('idle');
      const body = err instanceof ApiError ? (err.body as any) : undefined;
      const code: string | undefined = body?.error;
      const detail: string | undefined = body?.detail || body?.message;

      if (code === 'mfl_not_connected' || code === 'mfl_auth_expired') {
        Alert.alert(
          'Sign in with MFL',
          'Your MFL sign-in is missing or expired. Sign in again from the league list (Add league → MFL).',
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Go to leagues', onPress: goReconnect },
          ],
        );
      } else if (code === 'verification_required') {
        Alert.alert(
          'Verify your account',
          'Sending trades needs a quick account verification first — sign in from Settings, then try again.',
        );
      } else if (code === 'mfl_asset_unmapped') {
        const n = Array.isArray(body?.unmapped) ? body.unmapped.length : 0;
        Alert.alert(
          'Couldn’t send',
          `${n || 'Some'} asset${n === 1 ? '' : 's'} in this trade couldn’t be matched to MFL, so nothing was sent.`,
        );
      } else if (code === 'mfl_not_linked' || code === 'mfl_franchise_unknown') {
        Alert.alert(
          'Couldn’t send',
          'This MFL league needs to be re-linked before trades can be sent.',
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Go to leagues', onPress: goReconnect },
          ],
        );
      } else if (code === 'feature_disabled') {
        Alert.alert('Send in MFL', 'Sending isn’t available right now.');
      } else if (code === 'mfl_write_failed') {
        Alert.alert(
          'MFL wouldn’t accept the send',
          detail
            ? `MFL rejected the request:\n\n${detail}`
            : 'MFL rejected the request. You can still propose it on the MFL site.',
          [
            { text: 'OK', style: 'cancel' },
            { text: 'Open MFL', onPress: openMfl },
          ],
        );
      } else {
        Alert.alert(
          'Couldn’t send',
          detail || 'Something went wrong sending to MFL. Please try again.',
        );
      }
    }
  }, [leagueId, theirUserId, givePlayerIds, receivePlayerIds, impressionId, onSent, goReconnect, openMfl]);

  // #180-parity pre-flight — the shared /api/trades/validate branches to a
  // fresh MFL rosters export server-side. Never throws; findings are
  // surfaced honestly but the user can still send — MFL is the final
  // authority on its own rules.
  const confirmSend = useCallback(async () => {
    setState('checking');
    const { warnings } = await validateTradeSend({
      league_id: leagueId,
      their_user_id: theirUserId,
      give_player_ids: givePlayerIds,
      receive_player_ids: receivePlayerIds,
    });
    setState('idle');

    if (warnings.length > 0) {
      const blocking = warnings.some((w) => w.severity === 'blocking');
      Alert.alert(
        blocking ? 'This trade will likely fail' : 'Heads up before sending',
        warnings.map((w) => `• ${w.message}`).join('\n\n'),
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Send anyway', onPress: () => { void doPropose(); } },
        ],
      );
      return;
    }

    Alert.alert(
      'Send this trade?',
      'This proposes the trade directly in MFL — your leaguemate gets it as a pending offer (it expires in 7 days).',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Send', onPress: () => { void doPropose(); } },
      ],
    );
  }, [leagueId, theirUserId, givePlayerIds, receivePlayerIds, doPropose]);

  const onPress = useCallback(() => {
    if (state !== 'idle') return;
    haptics.pickup();
    if (!leagueId || !theirUserId) {
      openMfl();
      return;
    }
    void confirmSend();
  }, [state, leagueId, theirUserId, openMfl, confirmSend]);

  if (!enabled) return null;

  const label =
    state === 'sent' ? 'Proposal sent'
    : state === 'sending' ? 'Sending…'
    : 'Send in MFL';

  return (
    <Button
      testID="trades.send-mfl-btn"
      label={label}
      variant="secondary"
      compact={compact}
      disabled={state === 'sending' || state === 'checking' || state === 'sent'}
      onPress={onPress}
      style={style}
    />
  );
}

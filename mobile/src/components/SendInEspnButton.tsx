import React, { useCallback, useState } from 'react';
import { Alert, Linking, ViewStyle } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Button from './chalkline/Button';
import { haptics } from '../utils/haptics';
import { maybeRequestReview } from '../utils/ratingPrompt';
import { useFlag } from '../state/useFeatureFlags';
import { proposeTradeToEspn } from '../api/sendInEspn';
import { validateTradeSend } from '../api/sendInSleeper';
import { ApiError } from '../api/client';
import type { SendSurface } from '../utils/tradeText';

// "Send in ESPN" — the ESPN twin of SendInSleeperButton/SendInMflButton,
// mounted FOR ESPN leagues BY SendInSleeperButton's platform branch (never
// mount this directly; the platform routing lives in one place so no surface
// can fire the wrong platform's API). Flag-gated: the router only mounts this
// when `espn.send` is ON (flag-off ESPN leagues get the P0-6 reason +
// Copy-trade fallback there instead); the internal null below is
// defense-in-depth for a direct mount, never the user-visible flag-off path.
//
// `espn.send` ships OFF and ABSENT from config/features.json until the
// server-side auth probe clears (D-026 + the live-capture doc) — so this
// component is dark everywhere today; building it flag-complete means the
// graduation is a config flip, not a client release.
//
// Differences from the twins, deliberate:
//   • No up-front link-status check — the propose itself answers
//     (409 espn_not_connected / espn_auth_expired) and we route that to
//     reconnect guidance (the ESPN connect flow lives in EspnLinkSheet on
//     the league picker, so reconnect navigates to LeaguePicker).
//   • PLAYERS ONLY. ESPN pick assets are unverified server-side, so any pick
//     id in the arrays HARD-BLOCKS the whole send (422
//     espn_pick_unsupported) — surfaced honestly, nothing partial is sent.
//   • The server also hard-blocks any player the crosswalk can't map
//     (422 espn_asset_unmapped) — never a silent drop.

interface Props {
  leagueId: string;
  /** Synthetic ESPN member id (`espn:{SWID}` or `espn:{league}.t{team}`) —
   *  what ESPN league members carry as opponent_user_id on every trade
   *  surface. The server resolves both team ids from it. */
  theirUserId: string;
  /** FTF asset ids passed through verbatim; the server owns all mapping and
   *  BOTH hard blocks (unmapped player, any pick asset). */
  givePlayerIds: string[];
  receivePlayerIds: string[];
  impressionId?: string;
  onSent?: () => void;
  compact?: boolean;
  style?: ViewStyle;
  /** P0-7 parity: which mount this is. REQUIRED (threaded by the router in
   *  SendInSleeperButton) so a missed mount is a compile error, matching the
   *  other twins. No ESPN client events exist YET (`sleeper_send_*` are
   *  Sleeper-named and ESPN siblings are unregistered in the taxonomy), so
   *  today this prop is carried, not fired. */
  surface: SendSurface;
}

type State = 'idle' | 'checking' | 'sending' | 'sent';

export default function SendInEspnButton({
  leagueId,
  theirUserId,
  givePlayerIds,
  receivePlayerIds,
  impressionId,
  onSent,
  compact,
  style,
  // Carried for P0-7 parity (see Props); intentionally unread until ESPN
  // attempt/failure events are registered in the taxonomy.
  surface: _surface,
}: Props) {
  const enabled = useFlag('espn.send');
  const navigation = useNavigation<any>();
  const [state, setState] = useState<State>('idle');

  const openEspn = useCallback(() => {
    Linking.openURL('https://fantasy.espn.com').catch(() => {});
  }, []);

  // The ESPN connect flow (WebView cookie capture / paste) lives in
  // EspnLinkSheet on the league picker ("Add league" → ESPN). No dedicated
  // connect screen exists to deep link into, so reconnect guidance lands the
  // user there — same pattern as the MFL twin.
  const goReconnect = useCallback(() => {
    navigation.navigate('LeaguePicker');
  }, [navigation]);

  const doPropose = useCallback(async () => {
    setState('sending');
    try {
      await proposeTradeToEspn({
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
      Alert.alert('Trade sent', 'Check ESPN for the pending offer.', [
        { text: 'OK', onPress: () => void maybeRequestReview('send_in_espn') },
      ]);
    } catch (err) {
      setState('idle');
      const body = err instanceof ApiError ? (err.body as any) : undefined;
      const code: string | undefined = body?.error;
      const detail: string | undefined = body?.detail || body?.message;

      if (code === 'espn_not_connected' || code === 'espn_auth_expired') {
        Alert.alert(
          'Connect ESPN',
          'Your ESPN sign-in is missing or expired. Connect again from the league list (Add league → ESPN).',
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
      } else if (code === 'espn_pick_unsupported') {
        Alert.alert(
          'Couldn’t send',
          'Draft picks can’t be sent to ESPN yet, so nothing was sent. Remove the picks or copy the trade instead.',
        );
      } else if (code === 'espn_asset_unmapped') {
        const n = Array.isArray(body?.unmapped) ? body.unmapped.length : 0;
        Alert.alert(
          'Couldn’t send',
          `${n || 'Some'} asset${n === 1 ? '' : 's'} in this trade couldn’t be matched to ESPN, so nothing was sent.`,
        );
      } else if (code === 'espn_not_linked' || code === 'espn_team_unknown') {
        Alert.alert(
          'Couldn’t send',
          'This ESPN league needs to be re-linked before trades can be sent.',
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Go to leagues', onPress: goReconnect },
          ],
        );
      } else if (code === 'feature_disabled') {
        Alert.alert('Send in ESPN', 'Sending isn’t available right now.');
      } else if (code === 'espn_write_failed') {
        Alert.alert(
          'ESPN wouldn’t accept the send',
          detail
            ? `ESPN rejected the request:\n\n${detail}`
            : 'ESPN rejected the request. You can still propose it on the ESPN site.',
          [
            { text: 'OK', style: 'cancel' },
            { text: 'Open ESPN', onPress: openEspn },
          ],
        );
      } else {
        Alert.alert(
          'Couldn’t send',
          detail || 'Something went wrong sending to ESPN. Please try again.',
        );
      }
    }
  }, [leagueId, theirUserId, givePlayerIds, receivePlayerIds, impressionId, onSent, goReconnect, openEspn]);

  // #180-parity pre-flight — the shared /api/trades/validate has no ESPN
  // branch yet, so this degrades to checked:false (plain confirm). Never
  // throws; kept so an ESPN branch server-side lights up with no client
  // change — ESPN is the final authority on its own rules either way.
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
      'This proposes the trade directly in ESPN — your leaguemate gets it as a pending offer (it expires in 48 hours).',
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
      openEspn();
      return;
    }
    void confirmSend();
  }, [state, leagueId, theirUserId, openEspn, confirmSend]);

  if (!enabled) return null;

  const label =
    state === 'sent' ? 'Proposal sent'
    : state === 'sending' ? 'Sending…'
    : 'Send in ESPN';

  return (
    <Button
      testID="trades.send-espn-btn"
      label={label}
      variant="secondary"
      compact={compact}
      disabled={state === 'sending' || state === 'checking' || state === 'sent'}
      onPress={onPress}
      style={style}
    />
  );
}

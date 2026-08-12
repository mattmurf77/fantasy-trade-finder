import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Linking, ViewStyle } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Button from './chalkline/Button';
import { haptics } from '../utils/haptics';
import { maybeRequestReview } from '../utils/ratingPrompt';
import { useFlag } from '../state/useFeatureFlags';
import { getEspnLinkStatus, proposeTradeToEspn } from '../api/sendInEspn';
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
//   • Sleeper-style LAZY auth (send-auth gap fix, 2026-08-11): an up-front
//     GET /api/espn/link decides the FIRST message. Unlinked → we navigate
//     in-flow to EspnConnectScreen with reason:'send' (it stores the
//     captured pair server-side itself); on return the focus handler
//     re-checks and tells the user to tap Send again — the same one-button
//     loop as SendInSleeperButton. ESPN cookies are needed for EVERY send,
//     public league or not, so this is the primary path for the many users
//     whose public league never triggered the private-league capture.
//     League-level problems (espn_not_linked / espn_team_unknown) still
//     route to LeaguePicker — those genuinely need a re-link, not a login.
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
  // True while we're waiting for the user to come back from the ESPN connect
  // webview — the screen-focus handler consumes it to report the result
  // (same mechanism as the Sleeper twin's awaitingLinkRef).
  const awaitingLinkRef = useRef(false);

  const openEspn = useCallback(() => {
    Linking.openURL('https://fantasy.espn.com').catch(() => {});
  }, []);

  // ACCOUNT sign-in (send-auth lazy flow): in-flow push to the existing
  // EspnConnectScreen. reason:'send' makes the screen (a) show send-oriented
  // copy — never "this league is private" — and (b) store the captured pair
  // server-side itself via the credential-only POST /api/espn/link.
  const goConnect = useCallback(() => {
    awaitingLinkRef.current = true;
    navigation.navigate('EspnConnect', { reason: 'send' });
  }, [navigation]);

  // LEAGUE re-link (espn_not_linked / espn_team_unknown only): the league
  // row itself is missing or unbound, which the connect webview can't fix —
  // that flow lives in EspnLinkSheet on the league picker.
  const goReconnect = useCallback(() => {
    navigation.navigate('LeaguePicker');
  }, [navigation]);

  // When the user returns from the connect webview (success, failure, OR a
  // manual back-out), re-check the link from the server and tell them where
  // they stand. Gated on awaitingLinkRef so only the button that sent them
  // there speaks up, and only once.
  useEffect(() => {
    const unsub = navigation.addListener('focus', async () => {
      if (!awaitingLinkRef.current) return;
      awaitingLinkRef.current = false;
      let connected = false;
      try {
        const status = await getEspnLinkStatus();
        connected = !!status.connected && !status.expired;
      } catch {
        /* fall through to the "couldn't confirm" copy */
      }
      if (connected) {
        haptics.success();
        Alert.alert(
          'ESPN connected',
          'Tap “Send in ESPN” again to send your trade.',
        );
      } else {
        Alert.alert(
          'Not connected',
          'Your ESPN sign-in didn’t complete. Tap “Send in ESPN” to try again.',
        );
      }
    });
    return unsub;
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
        // Credential vanished/expired between the status check and the send
        // (the server drops a dead pair on a rejected pre-flight) — send
        // them to the in-flow sign-in; the focus handler reports the result
        // on return. Never a cross-surface punt to the league list.
        Alert.alert(
          'Sign in to ESPN',
          'Your ESPN sign-in is missing or expired. We’ll open ESPN so you can sign in again — your league stays linked.',
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Sign in', onPress: goConnect },
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
  }, [leagueId, theirUserId, givePlayerIds, receivePlayerIds, impressionId, onSent, goConnect, goReconnect, openEspn]);

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

  const onPress = useCallback(async () => {
    if (state !== 'idle') return;
    haptics.pickup();
    if (!leagueId || !theirUserId) {
      openEspn();
      return;
    }

    // Decide the FIRST message by whether an ESPN credential is stored for
    // this user (send-auth lazy flow — ESPN cookies are captured only on
    // demand, so a public-league owner reaches here with none stored).
    setState('checking');
    let connected: boolean;
    try {
      const status = await getEspnLinkStatus();
      connected = !!status.connected && !status.expired;
    } catch {
      // Status unknown (network / older server) — try the send; doPropose
      // routes to connect if it turns out we're not linked.
      setState('idle');
      void confirmSend();
      return;
    }
    setState('idle');

    if (connected) {
      void confirmSend();
    } else {
      Alert.alert(
        'Sign in to ESPN to send trades',
        'To send this trade we’ll open ESPN so you can sign in and connect your account. We never see your password.',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Sign in', onPress: goConnect },
        ],
      );
    }
  }, [state, leagueId, theirUserId, openEspn, confirmSend, goConnect]);

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

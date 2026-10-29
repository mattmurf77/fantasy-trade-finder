import React, { useCallback, useState, useSyncExternalStore } from 'react';
import { Alert, Linking, ViewStyle } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Button from './chalkline/Button';
import MflSignInSheet from './MflSignInSheet';
import { haptics } from '../utils/haptics';
import { maybeRequestReview } from '../utils/ratingPrompt';
import { useFlag } from '../state/useFeatureFlags';
import { getMflLinkStatus, proposeTradeToMfl } from '../api/sendInMfl';
import { validateTradeSend } from '../api/sendInSleeper';
import { ApiError } from '../api/client';
import { isSendOutcomeUnknown } from '../api/sendOutcome';
import { beginSend, getSendRecord, settleSend, subscribeSends, tradeSendKey } from '../api/sendRegistry';
import {
  SEND_NOT_SENT_TITLE,
  SEND_OUTCOME_UNKNOWN_TITLE,
  sendNotSentFallback,
  sendOutcomeUnknownBody,
  sendOutcomeUnknownMessage,
} from '../utils/sendOutcomeCopy';
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
//   • Sleeper-style LAZY auth (send-auth gap fix, 2026-08-11): an up-front
//     GET /api/mfl/auth-link decides the FIRST message. Unlinked → the
//     in-flow MflSignInSheet opens right here (username/password →
//     POST /api/mfl/auth-link stores the cookie AND verifies the session);
//     on success the send resumes immediately — the sheet's callback runs
//     confirmSend, whose "Send this trade?" alert still gates the actual
//     write. No LeaguePicker punt for a missing/expired sign-in.
//     League-level problems (mfl_not_linked / mfl_franchise_unknown) still
//     route to LeaguePicker — those genuinely need a re-link, not a login.
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

// The pre-send checks only. Sending / sent live in api/sendRegistry.ts.
type State = 'idle' | 'checking';

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
  // This trade's send, from the registry (api/sendRegistry.ts), so it
  // survives a remount: leave and reopen the trade during the wait and the
  // button still says "Sending…". It re-renders when the send settles; the
  // result alert is shown once, by the doPropose call that sent it.
  const sendKey = tradeSendKey('mfl', leagueId, theirUserId, givePlayerIds, receivePlayerIds);
  const sendState = useSyncExternalStore(subscribeSends, () => getSendRecord(sendKey)?.state);
  // In-flow MFL sign-in (send-auth lazy flow) — a focused sheet, right on
  // the send surface, instead of a cross-surface punt to the league picker.
  const [signInVisible, setSignInVisible] = useState(false);

  const openMfl = useCallback(() => {
    Linking.openURL('https://www.myfantasyleague.com').catch(() => {});
  }, []);

  const openSignIn = useCallback(() => setSignInVisible(true), []);

  // LEAGUE re-link (mfl_not_linked / mfl_franchise_unknown only): the league
  // row itself is missing or unbound, which a sign-in can't fix — that flow
  // lives in PlatformLinkSheet on the league picker.
  const goReconnect = useCallback(() => {
    navigation.navigate('LeaguePicker');
  }, [navigation]);

  const doPropose = useCallback(async () => {
    // Synchronous, before any await: a second send of this trade while one is
    // in flight (another mount, a same-frame double tap) is refused here,
    // with no request (#527 QA P3-5).
    if (!beginSend(sendKey)) return;
    try {
      await proposeTradeToMfl({
        league_id: leagueId,
        their_user_id: theirUserId,
        give_player_ids: givePlayerIds,
        receive_player_ids: receivePlayerIds,
        impression_id: impressionId,
      });
      settleSend(sendKey, 'sent');
      haptics.success();
      try {
        onSent?.();
      } catch {
        /* tally must never break the send flow */
      }
      // Alert.alert is global, not tied to this component, so this one alert
      // shows even if the button unmounted during the wait. A remount never
      // alerts: it only re-renders from the registry.
      Alert.alert('Trade sent', 'Check MFL for the pending offer.', [
        { text: 'OK', onPress: () => void maybeRequestReview('send_in_mfl') },
      ]);
    } catch (err) {
      settleSend(sendKey, isSendOutcomeUnknown(err) ? 'unknown' : 'not_sent');
      const body = err instanceof ApiError ? (err.body as any) : undefined;
      const code: string | undefined = body?.error;
      const detail: string | undefined = body?.detail || body?.message;

      if (isSendOutcomeUnknown(err)) {
        // Timed out, no answer, or the server's mfl_outcome_unknown: the
        // trade may be in MFL. No Retry or Send-again here (api/sendOutcome.ts).
        Alert.alert(SEND_OUTCOME_UNKNOWN_TITLE, sendOutcomeUnknownBody('MFL', code, detail), [
          { text: 'OK', style: 'cancel' },
          { text: 'Open MFL', onPress: openMfl },
        ]);
      } else if (code === 'mfl_not_connected' || code === 'mfl_auth_expired') {
        // Credential vanished/expired between the status check and the send
        // — open the in-flow sign-in sheet; a successful sign-in resumes
        // the send. Never a cross-surface punt to the league list.
        Alert.alert(
          'Sign in with MFL',
          'Your MFL sign-in is missing or expired. Sign in again to send this trade — your league stays linked.',
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Sign in', onPress: openSignIn },
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
          SEND_NOT_SENT_TITLE,
          detail || sendNotSentFallback('MFL'),
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
  }, [sendKey, leagueId, theirUserId, givePlayerIds, receivePlayerIds, impressionId, onSent, openSignIn, goReconnect, openMfl]);

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

    // Each dialog captures this trade's registry state when it is built. A
    // queued second dialog (a same-frame double tap) can be pressed long
    // after the first send went out, so its Send only sends if the state is
    // unchanged. If the trade has since gone in flight or been sent, it does
    // nothing (the button already says so). Otherwise (now unknown, or
    // cleared) the dialog opens again, current.
    function showConfirm(): void {
      const shown = getSendRecord(sendKey)?.state;
      const send = () => {
        const now = getSendRecord(sendKey)?.state;
        if (now === shown) void doPropose();
        else if (now !== 'in_flight' && now !== 'sent') showConfirm();
      };
      // After an unknown outcome on this trade, the dialog that gates the
      // send starts with marketing's 8f line (utils/sendOutcomeCopy.ts, no
      // new copy).
      const reminder = shown === 'unknown' ? `${sendOutcomeUnknownMessage('MFL')}\n\n` : '';

      if (warnings.length > 0) {
        const blocking = warnings.some((w) => w.severity === 'blocking');
        Alert.alert(
          blocking ? 'This trade will likely fail' : 'Heads up before sending',
          reminder + warnings.map((w) => `• ${w.message}`).join('\n\n'),
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Send anyway', onPress: send },
          ],
        );
        return;
      }

      Alert.alert(
        'Send this trade?',
        reminder + 'This proposes the trade directly in MFL — your leaguemate gets it as a pending offer (it expires in 7 days).',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Send', onPress: send },
        ],
      );
    }
    showConfirm();
  }, [sendKey, leagueId, theirUserId, givePlayerIds, receivePlayerIds, doPropose]);

  // A successful sign-in resumes the send immediately — the confirm alert
  // inside confirmSend ("Send this trade?") still gates the actual write,
  // so nothing sends without an explicit yes.
  const onSignedIn = useCallback(() => {
    setSignInVisible(false);
    void confirmSend();
  }, [confirmSend]);

  const onPress = useCallback(async () => {
    if (state !== 'idle' || sendState === 'in_flight' || sendState === 'sent') return;
    haptics.pickup();
    if (!leagueId || !theirUserId) {
      openMfl();
      return;
    }

    // Decide the FIRST message by whether an MFL sign-in is stored for this
    // user (send-auth lazy flow — MFL credentials are captured only on
    // demand, so a zero-auth-linked league reaches here with none stored).
    setState('checking');
    let connected: boolean;
    try {
      const status = await getMflLinkStatus();
      connected = !!status.connected;
    } catch {
      // Status unknown (network / older server) — try the send; doPropose
      // routes to sign-in if it turns out we're not connected.
      setState('idle');
      void confirmSend();
      return;
    }
    setState('idle');

    if (connected) {
      void confirmSend();
    } else {
      Alert.alert(
        'Sign in with MFL to send trades',
        'To send this trade, sign in to your MyFantasyLeague account. Your password goes to MFL’s login only — we never store it.',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Sign in', onPress: openSignIn },
        ],
      );
    }
  }, [state, sendState, leagueId, theirUserId, openMfl, confirmSend, openSignIn]);

  if (!enabled) return null;

  const label =
    sendState === 'sent' ? 'Proposal sent'
    : sendState === 'in_flight' ? 'Sending…'
    : 'Send in MFL';

  return (
    <>
      <Button
        testID="trades.send-mfl-btn"
        label={label}
        variant="secondary"
        compact={compact}
        disabled={state === 'checking' || sendState === 'in_flight' || sendState === 'sent'}
        onPress={onPress}
        style={style}
      />
      <MflSignInSheet
        visible={signInVisible}
        onClose={() => setSignInVisible(false)}
        onSignedIn={onSignedIn}
      />
    </>
  );
}

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Linking, ViewStyle } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Button from './chalkline/Button';
import SendInMflButton from './SendInMflButton';
import { haptics } from '../utils/haptics';
import { maybeRequestReview } from '../utils/ratingPrompt';
import { useFlag } from '../state/useFeatureFlags';
import { useSession } from '../state/useSession';
import {
  proposeTradeToSleeper,
  getSleeperLinkStatus,
  validateTradeSend,
} from '../api/sendInSleeper';
import { ApiError } from '../api/client';

// "Send in Sleeper" — and the single PLATFORM ROUTER for the send action.
// Renders on any real trade surface (found / matched / suggested).
// Flag-gated: returns null when `trade.send_in_sleeper` is off.
//
// Platform-gated centrally here (every mount passes leagueId) so no mount
// can fire the wrong platform's API (#146, extended for Send-in-MFL):
//   • sleeper (or unknown/missing from the cache — fail-open, pre-#146
//     behavior) → this button, Sleeper propose
//   • mfl → SendInMflButton (flag `trade.send_in_mfl`; MFL's documented
//     import API — previously this button WRONGLY rendered on MFL leagues
//     and a tap would have fired at Sleeper's API and failed)
//   • espn / fleaflicker / anything else non-Sleeper → null (no write path)
//
// One button, two paths — chosen by whether the Sleeper account is linked in
// this session (checked up front via GET /api/sleeper/link):
//   • linked   → "Send this trade?" confirm → propose → "Trade sent ✅"
//   • unlinked → "Connect Sleeper first" heads-up → login webview; on return we
//                re-check the link and tell them whether it worked so they can
//                tap Send again. The user always presses the SAME button.

interface Props {
  leagueId: string;
  theirUserId: string;
  givePlayerIds: string[];
  receivePlayerIds: string[];
  // F1 signal spine (flag deck.signal_v2): deck-served cards pass their
  // impression_id so a successful propose appends a `propose` outcome
  // server-side. Undefined (flag off / non-deck mounts) changes nothing.
  impressionId?: string;
  // F10 (flag deck.replenishment): fires once after a SUCCESSFUL propose —
  // TradesScreen counts it into the deck-done summary's "proposed" tally.
  // Undefined (flag off / non-deck mounts) changes nothing.
  onSent?: () => void;
  compact?: boolean;
  style?: ViewStyle;
}

type State = 'idle' | 'checking' | 'sending' | 'sent';

export default function SendInSleeperButton({
  leagueId,
  theirUserId,
  givePlayerIds,
  receivePlayerIds,
  impressionId,
  onSent,
  compact,
  style,
}: Props) {
  const enabled = useFlag('trade.send_in_sleeper');
  // Platform routing — reactive twin of api/espn.isEspnLeague etc. Fail-open
  // for Sleeper: a league id missing from the cached list (demo league,
  // stale cache) keeps this button, matching pre-#146 behavior. Any league
  // the cache DOES know as non-Sleeper never reaches the Sleeper API.
  const leagues = useSession((s) => s.leagues);
  const platform =
    leagues.find((lg) => lg.league_id === leagueId)?.platform ?? 'sleeper';
  const navigation = useNavigation<any>();
  const [state, setState] = useState<State>('idle');
  // True while we're waiting for the user to come back from the connect
  // webview — the screen-focus handler consumes it to report the result.
  const awaitingLinkRef = useRef(false);

  // When the user returns from the login webview (success, failure, OR a manual
  // back-out), re-check the link from the server and tell them where they
  // stand. Gated on awaitingLinkRef so only the button that sent them there
  // speaks up, and only once.
  useEffect(() => {
    const unsub = navigation.addListener('focus', async () => {
      if (!awaitingLinkRef.current) return;
      awaitingLinkRef.current = false;
      let connected = false;
      try {
        const status = await getSleeperLinkStatus();
        connected = !!status.connected && !status.expired;
      } catch {
        /* fall through to the "couldn't confirm" copy */
      }
      if (connected) {
        haptics.success();
        // Emoji strip (W1B handoff ride-along, ADR-004: no emoji as icons).
        Alert.alert(
          'Sleeper connected',
          'Tap “Send in Sleeper” again to send your trade.',
        );
      } else {
        Alert.alert(
          'Not connected',
          'Your Sleeper account didn’t connect. Tap “Send in Sleeper” to try again.',
        );
      }
    });
    return unsub;
  }, [navigation]);

  const openInSleeper = useCallback(() => {
    const url = /^\d+$/.test(leagueId)
      ? `https://sleeper.com/leagues/${leagueId}`
      : 'https://sleeper.com';
    Linking.openURL(url).catch(() => {});
  }, [leagueId]);

  const goConnect = useCallback(() => {
    awaitingLinkRef.current = true;
    navigation.navigate('SleeperConnect');
  }, [navigation]);

  const doPropose = useCallback(async () => {
    setState('sending');
    try {
      await proposeTradeToSleeper({
        league_id: leagueId,
        their_user_id: theirUserId,
        give_player_ids: givePlayerIds,
        receive_player_ids: receivePlayerIds,
        impression_id: impressionId,
      });
      setState('sent');
      haptics.success();
      // F10 — deck-done summary tally (no-op when the caller passed nothing).
      try {
        onSent?.();
      } catch {
        /* tally must never break the send flow */
      }
      // Emoji strip (W1B handoff ride-along). S7 PRD-02: a successful send
      // is the primary demonstrated-satisfaction moment — evaluate the
      // rating-prompt gate once the user acknowledges the alert
      // (maybeRequestReview is fully gated behind growth.rating_prompt and
      // no-ops flag-off).
      Alert.alert('Trade sent', 'Check your Sleeper app for the pending offer.', [
        { text: 'OK', onPress: () => void maybeRequestReview('send_in_sleeper') },
      ]);
    } catch (err) {
      setState('idle');
      const body = err instanceof ApiError ? (err.body as any) : undefined;
      const code: string | undefined = body?.error;
      const detail: string | undefined = body?.detail;

      if (code === 'sleeper_not_linked' || code === 'sleeper_expired') {
        // Token vanished/expired between the status check and the send — send
        // them to reconnect; the focus handler reports the result on return.
        Alert.alert(
          'Connect Sleeper first',
          'Your Sleeper connection needs a refresh. We’ll open Sleeper so you can log in again.',
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Connect', onPress: goConnect },
          ],
        );
      } else if (code === 'verification_required') {
        // Account-auth P1: sends require a VERIFIED session. A linked-but-
        // unverified session (e.g. linked before verification shipped, or a
        // fresh app session) re-verifies via the same connect webview — the
        // capture doubles as proof.
        Alert.alert(
          'Verify your account',
          'Sending trades needs a quick account verification. We’ll open Sleeper so you can log in — that’s it.',
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Verify', onPress: goConnect },
          ],
        );
      } else if (code === 'sleeper_rejected') {
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
  }, [leagueId, theirUserId, givePlayerIds, receivePlayerIds, impressionId, onSent, goConnect]);

  // #180 — pre-flight validation before the confirm. validateTradeSend never
  // throws (unreachable/flag-off degrades to checked:false → plain confirm);
  // findings are surfaced honestly but the user can still send — Sleeper is
  // the final authority on its own rules.
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
      'This proposes the trade directly in Sleeper — your leaguemate gets it as a pending offer.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Send', onPress: () => { void doPropose(); } },
      ],
    );
  }, [leagueId, theirUserId, givePlayerIds, receivePlayerIds, doPropose]);

  const onPress = useCallback(async () => {
    if (state !== 'idle') return;
    // Routed through utils/haptics (W1B handoff): pickup = impact-medium,
    // the same physical feedback as the previous direct expo-haptics call.
    haptics.pickup();

    // No real league/opponent to send to → hand off to Sleeper directly.
    if (!leagueId || !theirUserId) {
      openInSleeper();
      return;
    }

    // Decide the FIRST message by whether Sleeper is linked in this session.
    setState('checking');
    let connected: boolean;
    try {
      const status = await getSleeperLinkStatus();
      connected = !!status.connected && !status.expired;
    } catch {
      // Status unknown (network) — assume we can try to send; doPropose will
      // route to connect if it turns out we're not linked.
      setState('idle');
      confirmSend();
      return;
    }
    setState('idle');

    if (connected) {
      confirmSend();
    } else {
      Alert.alert(
        'Connect Sleeper first',
        'To send this trade we’ll open Sleeper so you can log in and connect your account. ' +
          'We never see your password.',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Connect', onPress: goConnect },
        ],
      );
    }
  }, [state, leagueId, theirUserId, openInSleeper, confirmSend, goConnect]);

  // Platform routing (see header). MFL leagues delegate to the MFL twin —
  // one mount point, so the reconnect/confirm/pre-flight UX stays per
  // platform while no surface can pick the wrong API.
  if (platform === 'mfl') {
    return (
      <SendInMflButton
        leagueId={leagueId}
        theirUserId={theirUserId}
        givePlayerIds={givePlayerIds}
        receivePlayerIds={receivePlayerIds}
        impressionId={impressionId}
        onSent={onSent}
        compact={compact}
        style={style}
      />
    );
  }
  if (!enabled || platform !== 'sleeper') return null;

  const label =
    state === 'sent' ? 'Proposal sent'
    : state === 'sending' ? 'Sending…'
    : state === 'checking' ? 'Send in Sleeper'
    : 'Send in Sleeper';

  return (
    <Button
      testID="trades.send-sleeper-btn"
      label={label}
      variant="secondary"
      compact={compact}
      disabled={state === 'sending' || state === 'checking' || state === 'sent'}
      onPress={onPress}
      style={style}
    />
  );
}

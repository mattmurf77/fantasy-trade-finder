import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Linking, StyleSheet, Text, View, ViewStyle } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import Button from './chalkline/Button';
import { chalk, space, type } from '../theme/chalkline';
import { copyText } from '../utils/clipboard';
import {
  formatTradeForClipboard,
  resolveSendPlatform,
  NO_SEND_REASON,
  type SendSurface,
} from '../utils/tradeText';
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
import { track } from '../api/events';

// "Send in Sleeper" — and the single PLATFORM ROUTER for the send action.
// Renders on any real trade surface (found / matched / suggested).
// Flag-gated: returns null when `trade.send_in_sleeper` is off.
//
// Platform-gated centrally here (every mount passes leagueId) so no mount
// can fire the wrong platform's API (#146, widened by audit P0-6, extended
// for Send-in-MFL):
//   • sleeper (or unknown/missing from the cache — fail-open, pre-#146
//     behavior) → this button, Sleeper propose
//   • mfl with `trade.send_in_mfl` ON → SendInMflButton (MFL's documented
//     import API — previously this button WRONGLY rendered on MFL leagues
//     and a tap would have fired at Sleeper's API and failed)
//   • mfl with `trade.send_in_mfl` OFF, espn, fleaflicker → the P0-6
//     fallback: a stated reason (NO_SEND_REASON) plus a "Copy trade"
//     action — never null; the send path itself is unreachable there.
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
  // audit P0-6 — copy-trade fallback payload. Names are preferred; the
  // formatter falls back per-index to givePlayerIds/receivePlayerIds, so a
  // mount that forgets a prop degrades to ids, never to an empty clipboard.
  // Undefined changes nothing on a Sleeper league (the branch never renders).
  givePlayerNames?: string[];
  receivePlayerNames?: string[];
  opponentUsername?: string;
  // Matches only — TradeMatch/AwaitingTrade carry league_name; the deck and
  // the calculator do not, and the copy text drops the line when absent.
  leagueName?: string;
  // P0-7 (analytics): which mount this is. REQUIRED so a missed mount is a
  // compile error, not a null dimension in the send funnel. Read by the
  // track() calls in onPress/catch.
  surface: SendSurface;
}

type State = 'idle' | 'checking' | 'sending' | 'sent';

// How long the "Copied" acknowledgement holds before reverting.
const COPIED_MS = 2500;

export default function SendInSleeperButton({
  leagueId,
  theirUserId,
  givePlayerIds,
  receivePlayerIds,
  impressionId,
  onSent,
  compact,
  style,
  givePlayerNames,
  receivePlayerNames,
  opponentUsername,
  leagueName,
  surface,
}: Props) {
  const enabled = useFlag('trade.send_in_sleeper');
  // MFL has its own send path and its own rollback lever (`trade.send_in_mfl`,
  // gating the backend routes too). Read here, at the router, so an MFL
  // league with the flag OFF falls through to the P0-6 copy fallback below
  // instead of SendInMflButton's internal null (which would regress P0-6).
  const mflEnabled = useFlag('trade.send_in_mfl');
  // #146 + audit P0-6 — reactive twin of api/espn.isEspnLeague, widened from
  // "is it ESPN" to "which platform is it". Reactive (a useSession SELECTOR,
  // not getState()) because this runs in render, unlike the imperative twins
  // FreeAgentsScreen uses from callbacks. Fail-open, unchanged: a league id
  // missing from the cached list (demo league, stale cache) resolves to
  // 'sleeper' and keeps the button, matching pre-#146 behavior.
  //
  // The widening is a bug fix, not a generalization for its own sake: MFL and
  // Fleaflicker league ids are NUMERIC, so POST /api/sleeper/propose's
  // `league_id.isdigit()` check does not exclude them — those leagues rendered
  // a live Send button that always 400s roster_not_found. Non-Sleeper leagues
  // now render the copy fallback instead of a send that cannot work.
  const leagues = useSession((s) => s.leagues);
  const platform = resolveSendPlatform(leagueId, leagues);
  const canSend = platform === 'sleeper';
  const navigation = useNavigation<any>();
  const [state, setState] = useState<State>('idle');
  // True while we're waiting for the user to come back from the connect
  // webview — the screen-focus handler consumes it to report the result.
  const awaitingLinkRef = useRef(false);
  // Copy-affordance acknowledgement (audit P0-6). Local label flip, not a
  // toast: this component mounts inside three different screens and has no
  // toast host, and an Alert would put a dismiss between the user and their
  // next action.
  const [copied, setCopied] = useState(false);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (copiedTimer.current) clearTimeout(copiedTimer.current);
    },
    [],
  );

  // No confirm — copying is non-destructive, instant, and reversible by not
  // pasting. haptics.success() is honest here in a way it would not be for an
  // async call: the write is synchronous and cannot fail. Re-tapping while
  // "Copied" is showing re-arms the timer; the button is never disabled
  // because, unlike the send path, there is no in-flight state to protect.
  const onCopy = useCallback(() => {
    copyText(
      formatTradeForClipboard({
        giveNames: givePlayerNames,
        giveIds: givePlayerIds,
        receiveNames: receivePlayerNames,
        receiveIds: receivePlayerIds,
        opponentUsername,
        leagueName,
      }),
    );
    haptics.success();
    setCopied(true);
    if (copiedTimer.current) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopied(false), COPIED_MS);
  }, [
    givePlayerNames, givePlayerIds, receivePlayerNames, receivePlayerIds,
    opponentUsername, leagueName,
  ]);

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
      const body = err instanceof ApiError ? (err.body as any) : undefined;
      // P0-7 — the FAILURE leg. Client-fired because this is the ONLY
      // place that sees network errors, timeouts, and the pre-identity
      // refusals (feature_disabled / no_user / test_mode_propose_disabled)
      // the server cannot attribute to a user — and the only place that
      // knows `surface`. Closed enum: 12 server codes ∪ network | timeout
      // | unknown = 15 values, forever.
      track('sleeper_send_failed', {
        surface,
        error_code: err instanceof ApiError
          ? (err.isTimeout ? 'timeout' : (body?.error ?? 'unknown'))
          : 'network',
        status: err instanceof ApiError ? (err.status ?? null) : null,
        kind: body?.kind ?? null,
        give_n: givePlayerIds.length,
        receive_n: receivePlayerIds.length,
        from_deck: !!impressionId,
      });
      setState('idle');
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
    // P0-7 — the ATTEMPT leg. Fired in the HANDLER, never at render:
    // after P0-6 a non-Sleeper mount renders a copy affordance rather
    // than a send button, so a mount-time impression event would conflate
    // copy-affordance impressions with send impressions and corrupt the
    // send-funnel denominator (hld.md §1.4).
    // has_target=false means this tap becomes the openInSleeper() handoff
    // below, NOT a real send — the denominator needs that distinction.
    track('sleeper_send_attempted', {
      surface,
      give_n: givePlayerIds.length,
      receive_n: receivePlayerIds.length,
      from_deck: !!impressionId,
      has_target: !!leagueId && !!theirUserId,
    });
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

  // Platform routing (see header). An MFL league with `trade.send_in_mfl` ON
  // delegates to the MFL twin — one mount point, so the reconnect/confirm/
  // pre-flight UX stays per platform while no surface can pick the wrong
  // API. Deliberately BEFORE the `trade.send_in_sleeper` kill switch: the
  // MFL send's rollback lever is its own flag (same one gating the backend
  // routes), not Sleeper's.
  if (platform === 'mfl' && mflEnabled) {
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
        surface={surface}
      />
    );
  }

  // The flag is still the kill switch for the WHOLE component on EVERY
  // platform (bar the MFL-send branch above): off ⇒ null everywhere, i.e.
  // exactly today's ESPN behaviour applied universally. That is why the copy
  // fallback needs no flag of its own, and why `trade.send_in_sleeper`
  // remains its rollback lever.
  if (!enabled) return null;

  // Non-Sleeper league: a send is impossible (ESPN/Fleaflicker are read-only
  // imports, MFL with its flag off has no live send path, and POST
  // /api/sleeper/propose talks only to Sleeper's roster space). State the
  // reason, offer the one action that works.
  if (!canSend) {
    return (
      <View testID="send-in-sleeper.unavailable" style={[styles.unavailable, style]}>
        <Text style={styles.reason} numberOfLines={2}>
          {NO_SEND_REASON[platform]}
        </Text>
        <Button
          testID="send-in-sleeper.copy"
          label={copied ? 'Copied' : 'Copy trade'}
          variant="ghost"
          compact={compact}
          onPress={onCopy}
        />
      </View>
    );
  }

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

const styles = StyleSheet.create({
  // Column, not row: the reason is a sentence and the action sits under it,
  // so a narrow mount (the deck's compact action column) wraps the prose
  // instead of squeezing the button.
  unavailable: { gap: space.xs, alignItems: 'flex-start' },
  reason: { ...type.bodySm, color: chalk.dim },
});

import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Modal,
  ScrollView,
  TextInput,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from 'react-native';
import { ink, chalk, semantic, space, radii, type, shadowSheet, scrim } from '../theme/chalkline';
import { Button, Icon } from './chalkline';
import { useFlag } from '../state/useFeatureFlags';
import { ApiError } from '../api/client';
import { navigationRef } from '../navigation/RootNav';
import { onEspnCookiesCaptured } from '../state/espnConnectBus';
import {
  linkEspnLeague,
  isEspnPreview,
  parseEspnLeagueInput,
  EspnLinkPreview,
  EspnImportSummary,
} from '../api/espn';

interface Props {
  visible: boolean;
  onClose: () => void;
  /** Fired after a successful import — the caller merges the league into
   *  the cached list and activates it. */
  onLinked: (league: { league_id: string; name: string; total_rosters: number }) => void;
}

// Copy for the backend's `espn_auth_required` 403. Two honest variants
// (2026-08-09): when cookies were actually SENT and rejected, saying "this
// league is private, sign in" gaslights a user who just signed in — name the
// rejection and offer the retry; only a cookie-less attempt gets the plain
// "it's private" explanation. `webviewCapture` picks sign-in vs paste as the
// primary fix.
function espnAuthErrorCopy(webviewCapture: boolean, cookiesWereSent: boolean): string {
  if (cookiesWereSent) {
    return webviewCapture
      ? "ESPN didn't accept that sign-in — it may have expired. Sign in to ESPN again below and we'll retry, or paste the two cookies yourself."
      : "ESPN didn't accept those cookies — they may have expired. Paste fresh espn_s2 and SWID values from a logged-in espn.com session.";
  }
  return webviewCapture
    ? "This league is private. Sign in to ESPN below and we'll fetch it."
    : 'This league is private — paste your espn_s2 and SWID cookies below.';
}

// Flag-gated (`espn.link`) three-step link flow, Chalkline sheet construction:
//   1. input  — ESPN league ID (or fantasy.espn.com URL); optional
//               espn_s2/SWID paste for private leagues (WebView capture is
//               Phase 1b — manual paste is the fallback the plan ships now)
//   2. team   — preview came back; "which team is yours?"
//   3. done   — import summary: teams, match rate, skipped players,
//               read-only expectations copy
export default function EspnLinkSheet({ visible, onClose, onLinked }: Props) {
  const [step, setStep] = useState<'input' | 'team' | 'done'>('input');
  const [input, setInput] = useState('');
  const [showCookies, setShowCookies] = useState(false);
  const [espnS2, setEspnS2] = useState('');
  const [swid, setSwid] = useState('');
  const [busy, setBusy] = useState(false);
  const [busyTeamId, setBusyTeamId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<EspnLinkPreview | null>(null);
  const [summary, setSummary] = useState<EspnImportSummary | null>(null);

  // Teardown PRD 01-01 (S1B-04), flag `ux.sheet_guard`:
  //   OFF — every close resets, so a stray backdrop tap wipes the league ID
  //   and pasted espn_s2/SWID cookies (painful to re-paste).
  //   ON  — close does NOT reset; reopening resumes the step with fields
  //   intact. Accidental dismiss vectors (backdrop tap, Android back) get a
  //   Keep editing / Discard confirm while there's anything to lose; the
  //   explicit Cancel button closes keeping the draft (resume on reopen).
  const guardOn = useFlag('ux.sheet_guard');
  // Phase 1b (flag `espn.webview_capture`): the "Sign in to ESPN" WebView
  // capture path. Off ⇒ the private-league section is manual-paste only,
  // byte-identical to before. Requires the sheet itself (gated by
  // `espn.link`) to be visible at all.
  const webviewCapture = useFlag('espn.webview_capture');
  // While the ESPN Connect WebView is pushed we HIDE this Modal: a
  // native-stack push lands on the navigator behind an open RN Modal, so we
  // reveal it by dropping our own Modal, then restore it when the cookies
  // (or an abandon) come back through the bus.
  const [hiddenForWebView, setHiddenForWebView] = useState(false);
  // Anything worth protecting: typed fields on step 1, or a fetched
  // preview mid-flow. The 'done' step has nothing to lose (import already
  // completed server-side).
  const dirty =
    step === 'team' ||
    (step === 'input' && !!(input.trim() || espnS2.trim() || swid.trim()));

  function reset() {
    setStep('input');
    setInput('');
    setShowCookies(false);
    setEspnS2('');
    setSwid('');
    setBusy(false);
    setBusyTeamId(null);
    setError(null);
    setPreview(null);
    setSummary(null);
    setHiddenForWebView(false);
  }

  // Launch the ESPN Connect WebView (flag-gated button). Hide our Modal for
  // the push, then navigate. The bus subscription below restores the Modal
  // with the captured cookies (or on abandon).
  function launchWebViewCapture() {
    setError(null);
    setHiddenForWebView(true);
    navigationRef.navigate('EspnConnect');
  }

  // Receive the captured cookies (or null on abandon) from EspnConnectScreen.
  // Subscribing from the component body — NOT the Modal children — because a
  // hidden Modal unmounts its children, which would drop the subscription
  // exactly while the WebView is up. Auto-advances to the preview when a
  // league ID is already entered, so capture continues the normal flow.
  useEffect(() => {
    const off = onEspnCookiesCaptured((pair) => {
      setHiddenForWebView(false);
      if (!pair) return;
      setShowCookies(true);
      setEspnS2(pair.espnS2);
      setSwid(pair.swid);
      if (parseEspnLeagueInput(input)) {
        void fetchPreview({ espnS2: pair.espnS2, swid: pair.swid });
      }
    });
    return off;
  }, [input]);

  function close() {
    if (busy || busyTeamId !== null) return;
    if (guardOn) {
      // Keep all state — reopening resumes where the user left off.
      onClose();
      return;
    }
    reset();
    onClose();
  }

  // Backdrop tap + onRequestClose: possibly accidental — confirm first when
  // the guard is on and there's unsaved progress. Flag off: same as close().
  function requestClose() {
    if (busy || busyTeamId !== null) return;
    if (guardOn && dirty) {
      Alert.alert(
        'Discard this league link?',
        'Your league ID and cookies will be cleared.',
        [
          { text: 'Keep editing', style: 'cancel' },
          {
            text: 'Discard',
            style: 'destructive',
            onPress: () => {
              reset();
              onClose();
            },
          },
        ],
      );
      return;
    }
    close();
  }

  // `override` lets the WebView-capture path pass freshly-delivered cookies
  // without waiting for the espnS2/swid state to flush (setState is async).
  async function fetchPreview(override?: { espnS2: string; swid: string }) {
    const leagueId = parseEspnLeagueInput(input);
    if (!leagueId) {
      setError('Enter a numeric ESPN league ID or a fantasy.espn.com league URL.');
      return;
    }
    const s2 = (override?.espnS2 ?? espnS2).trim();
    const sw = (override?.swid ?? swid).trim();
    if (!!s2 !== !!sw) {
      setError('Private leagues need both espn_s2 and SWID.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await linkEspnLeague({
        espnLeagueId: leagueId,
        espnS2: s2 || undefined,
        swid: sw || undefined,
      });
      if (isEspnPreview(res)) {
        setPreview(res);
        setStep('team');
      } else {
        // Backend only imports when team_id is sent, so this is unexpected —
        // treat it as done anyway.
        setSummary(res);
        setStep('done');
      }
    } catch (e: any) {
      // #126 R-7: the write gate's 403 carries the raw code
      // `verification_required` as its message — map it to human copy.
      // The central _onVerificationRequired listener still raises the banner.
      if (e instanceof ApiError && e.isVerificationRequired) {
        setError('Verify your account to link a league.');
      } else if (e instanceof ApiError && e.isEspnAuthRequired) {
        // Private league (or rejected/expired cookies): self-serve instead
        // of a dead-end message — auto-expand the private section so the fix
        // (sign-in button flag-on, paste fields flag-off) is on screen. The
        // copy branches on whether cookies were actually sent (see
        // espnAuthErrorCopy) so a user who just signed in isn't told to
        // "sign in" as if nothing happened.
        setShowCookies(true);
        setError(espnAuthErrorCopy(webviewCapture, !!(s2 && sw)));
      } else {
        setError(e?.message || "Couldn't reach ESPN — try again shortly.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function pickTeam(teamId: number) {
    if (!preview || busyTeamId !== null) return;
    setBusyTeamId(teamId);
    setError(null);
    try {
      const res = await linkEspnLeague({
        espnLeagueId: preview.league.espn_league_id,
        season: preview.league.season,
        teamId,
        espnS2: espnS2.trim() || undefined,
        swid: swid.trim() || undefined,
      });
      if (!isEspnPreview(res)) {
        setSummary(res);
        setStep('done');
      }
    } catch (e: any) {
      // #126 R-7: same verification_required mapping as fetchPreview.
      if (e instanceof ApiError && e.isVerificationRequired) {
        setError('Verify your account to link a league.');
      } else if (e instanceof ApiError && e.isEspnAuthRequired) {
        // Cookies expired between preview and import (same 403 as
        // fetchPreview). The cookie affordances live on the input step, so
        // land there with the private section open and the fix on screen.
        setStep('input');
        setShowCookies(true);
        setError(
          espnAuthErrorCopy(webviewCapture, !!(espnS2.trim() && swid.trim())),
        );
      } else {
        setError(e?.message || 'Import failed — try again.');
      }
    } finally {
      setBusyTeamId(null);
    }
  }

  function openLeague() {
    if (!summary) return;
    const lg = {
      league_id: summary.league_id,
      name: summary.name,
      total_rosters: summary.total_teams,
    };
    reset();
    onLinked(lg);
  }

  const report = step === 'done' ? summary?.report : preview?.report;

  return (
    <Modal
      visible={visible && !hiddenForWebView}
      transparent
      animationType="slide"
      onRequestClose={requestClose}
    >
      <Pressable
        style={styles.backdrop}
        onPress={requestClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      {/* #129: keyboard-avoiding wrapper (FeedbackSheet pattern) — without it
          the absolutely-positioned sheet's content is hidden behind the iOS
          keyboard, leaving Continue unreachable while typing the league ID. */}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.kav}
      >
      <View style={styles.sheet}>
        <View style={styles.grabber} />
        <Text style={type.heading} accessibilityRole="header">Link an ESPN league</Text>

        {step === 'input' ? (
          <>
            <Text style={[type.bodySm, styles.sub]}>
              Read-only import: we read team names and rosters — we never post
              or change anything in ESPN.
            </Text>
            <TextInput
              testID="espn-link.input"
              accessibilityLabel="ESPN league ID or league URL"
              style={styles.field}
              value={input}
              onChangeText={setInput}
              placeholder="ESPN league ID or league URL"
              placeholderTextColor={chalk.dim}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="default"
              editable={!busy}
            />
            <Pressable
              testID="espn-link.private-toggle"
              onPress={() => setShowCookies((v) => !v)}
              style={styles.cookieToggle}
              accessibilityRole="button"
              accessibilityState={{ expanded: showCookies }}
            >
              <Icon name={showCookies ? 'chevron-down' : 'chevron-right'} size={14} color={chalk.dim} />
              <Text style={type.bodySm}>Private league? Paste your ESPN cookies</Text>
            </Pressable>
            {showCookies ? (
              <>
                {/* Phase 1b (flag `espn.webview_capture`): the primary path —
                    sign in to ESPN in-app and we capture the two cookies for
                    you. Manual paste below stays as the fallback. Flag off ⇒
                    this block is absent and the section is paste-only,
                    byte-identical to before. */}
                {webviewCapture ? (
                  <>
                    <Button
                      testID="espn-connect.sign-in"
                      label="Sign in to ESPN"
                      onPress={launchWebViewCapture}
                      disabled={busy}
                    />
                    <Text style={[type.bodySm, styles.cookieHint]}>
                      We’ll open ESPN’s login and read the two cookies it
                      issues (espn_s2 and SWID) — we never see your password.
                      Prefer to paste them yourself? Do it below.
                    </Text>
                  </>
                ) : null}
                <Text style={[type.bodySm, styles.cookieHint]}>
                  From a logged-in espn.com session: the espn_s2 and SWID
                  cookies. They're stored encrypted and only used to read this
                  league. Public leagues need nothing.
                </Text>
                <TextInput
                  testID="espn-link.s2-input"
                  style={styles.field}
                  value={espnS2}
                  onChangeText={setEspnS2}
                  placeholder="espn_s2"
                  placeholderTextColor={chalk.dim}
                  autoCapitalize="none"
                  autoCorrect={false}
                  editable={!busy}
                />
                <TextInput
                  testID="espn-link.swid-input"
                  style={styles.field}
                  value={swid}
                  onChangeText={setSwid}
                  placeholder="SWID (with braces)"
                  placeholderTextColor={chalk.dim}
                  autoCapitalize="none"
                  autoCorrect={false}
                  editable={!busy}
                />
              </>
            ) : null}
            {error ? (
              <Text testID="espn-link.error" style={styles.error}>{error}</Text>
            ) : null}
            <Button
              testID="espn-link.continue"
              label={busy ? 'Fetching league…' : 'Continue'}
              onPress={() => fetchPreview()}
              disabled={busy}
              style={styles.cta}
            />
          </>
        ) : null}

        {step === 'team' && preview ? (
          <>
            <Text style={[type.bodySm, styles.sub]}>
              {preview.league.name} · {preview.league.total_teams} teams ·{' '}
              season {preview.league.season}. Which team is yours?
            </Text>
            {error ? (
              <Text testID="espn-link.error" style={styles.error}>{error}</Text>
            ) : null}
            <ScrollView style={styles.teamList}>
              {preview.teams.map((t, idx) => {
                const isBusy = busyTeamId === t.team_id;
                const dim = busyTeamId !== null && !isBusy;
                return (
                  <Pressable
                    key={t.team_id}
                    testID={`espn-link.team.${t.team_id}`}
                    accessibilityRole="button"
                    accessibilityLabel={`${t.name}${t.owner_display ? `, ${t.owner_display}` : ''}, ${t.mapped_players} players mapped`}
                    accessibilityHint="Imports this team as yours"
                    accessibilityState={{ disabled: busyTeamId !== null, busy: isBusy }}
                    onPress={() => pickTeam(t.team_id)}
                    disabled={busyTeamId !== null}
                    style={({ pressed }) => [
                      styles.teamRow,
                      idx === preview.teams.length - 1 && styles.teamRowLast,
                      dim && styles.rowDim,
                      pressed && !dim && styles.rowPressed,
                    ]}
                  >
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={type.title} numberOfLines={1}>{t.name}</Text>
                      <Text style={[type.bodySm, styles.rowMeta]}>
                        {t.owner_display ? `${t.owner_display} · ` : ''}
                        {t.mapped_players} players mapped
                      </Text>
                    </View>
                    {isBusy ? (
                      <ActivityIndicator color={chalk.dim} />
                    ) : (
                      <Icon name="chevron-right" size={16} color={chalk.dim} />
                    )}
                  </Pressable>
                );
              })}
            </ScrollView>
          </>
        ) : null}

        {step === 'done' && summary ? (
          <>
            <Text style={[type.bodySm, styles.sub]}>
              {summary.name}: imported {summary.teams_imported} teams
              {report ? ` · ${Math.round(report.match_rate * 100)}% of players matched` : ''}.
            </Text>
            {report && report.unmatched.length > 0 ? (
              <Text style={[type.bodySm, styles.skipNote]}>
                Skipped (no dynasty value data yet):{' '}
                {report.unmatched.map((u) => u.name).join(', ')}
              </Text>
            ) : null}
            <Text style={[type.bodySm, styles.readOnlyNote]}>
              ESPN leagues are read-only imports. Rankings, tiers, and trios
              fully work today; trade features for ESPN leagues come later.
              Draft picks aren't available from ESPN, so suggestions stay
              players-only.
            </Text>
            <Button
              testID="espn-link.open"
              label="Open league"
              onPress={openLeague}
              style={styles.cta}
            />
          </>
        ) : null}

        <Button
          label="Cancel"
          variant="ghost"
          onPress={close}
          disabled={busy || busyTeamId !== null}
          style={styles.cancel}
        />
      </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: scrim },
  kav: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    maxHeight: '88%',
    backgroundColor: ink.ink2,
    borderWidth: 1,
    borderColor: ink.line,
    borderTopLeftRadius: radii.md,
    borderTopRightRadius: radii.md,
    padding: space.lg,
    paddingBottom: space.xxl,
    gap: space.sm,
    ...shadowSheet,
  },
  grabber: {
    alignSelf: 'center',
    width: 32,
    height: 4,
    backgroundColor: ink.lineStrong,
    marginBottom: space.sm,
  },
  sub: { marginBottom: space.xs },
  field: {
    ...type.body,
    backgroundColor: ink.ink1,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    minHeight: 44,
    color: chalk.base,
  },
  cookieToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingVertical: space.xs,
  },
  cookieHint: { color: chalk.dim },
  error: { ...type.bodySm, color: semantic.neg },
  cta: { marginTop: space.sm },
  cancel: { marginTop: space.xs },
  teamList: { maxHeight: 340 },
  teamRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
    paddingHorizontal: space.xs,
    minHeight: 44,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
  },
  teamRowLast: { borderBottomWidth: 0 },
  rowPressed: { backgroundColor: ink.ink3 },
  rowDim: { opacity: 0.45 },
  rowMeta: { marginTop: 2 },
  skipNote: { color: chalk.dim },
  readOnlyNote: { color: chalk.dim, marginTop: space.xs },
});

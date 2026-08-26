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
import { ink, chalk, ice, semantic, space, radii, type, shadowSheet, scrim } from '../theme/chalkline';
import { Button, Icon } from './chalkline';
import { useFlag } from '../state/useFeatureFlags';
import { ApiError } from '../api/client';
import { navigationRef } from '../navigation/RootNav';
import { onEspnCookiesCaptured } from '../state/espnConnectBus';
import {
  linkEspnLeague,
  isEspnPreview,
  parseEspnLeagueInput,
  getMyEspnLeagues,
  EspnLinkPreview,
  EspnImportSummary,
  EspnMyLeague,
} from '../api/espn';
import { entryEspnPreview, entryPlatformMint } from '../api/platformEntry';

interface Props {
  visible: boolean;
  onClose: () => void;
  /** Fired after a successful import — the caller merges the league into
   *  the cached list and activates it. */
  onLinked: (league: { league_id: string; name: string; total_rosters: number }) => void;
  /** Sessionless entry mode (landing platform options v2, D-164): the sheet
   *  is hosted by SignInScreen with NO session. Preview goes through the
   *  sessionless /api/entry/platform; picking a team MINTS the entry session
   *  first (delivered via onEntrySession), then runs the canonical import
   *  under the fresh token. Session-dependent niceties are suppressed: the
   *  `espn.league_picker` my-leagues list reads STORED credentials, which an
   *  entry user doesn't have yet. Default off — linked flow byte-identical. */
  entry?: boolean;
  /** Entry mode only: the minted session's user, delivered BEFORE the import
   *  runs so the host can pin it into useSession. */
  onEntrySession?: (user: { user_id: string; display_name: string }) => void;
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
export default function EspnLinkSheet({
  visible,
  onClose,
  onLinked,
  entry,
  onEntrySession,
}: Props) {
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
  // League picker state. `myLeagues`: null = not fetched (or the fetch
  // failed — e.g. no stored ESPN cookies yet, which is the ordinary case
  // for a brand-new capture that hasn't linked anything before); an array
  // (possibly empty) = a successful fetch. `useManualEntry` lets the user
  // fall back to the text field even when a picker is available (their
  // league isn't listed, or they'd rather type it).
  const [myLeagues, setMyLeagues] = useState<EspnMyLeague[] | null>(null);
  const [myLeaguesBusy, setMyLeaguesBusy] = useState(false);
  const [useManualEntry, setUseManualEntry] = useState(false);

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
  // League picker (2026-08-09, feedback: "fetch all their ESPN leagues and
  // let them pick, instead of asking for a league ID"). Off ⇒ myLeagues
  // stays null forever (fetchMyLeagues no-ops) and the input step is
  // byte-identical to before — plain league-id text field only.
  const leaguePicker = useFlag('espn.league_picker');
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
  // The picker replaces the text field (and its Continue button — picking a
  // row already calls fetchPreview directly) whenever it has rows to show
  // and the user hasn't asked for manual entry instead.
  const showingPicker = leaguePicker && !useManualEntry && !!myLeagues && myLeagues.length > 0;

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
    setMyLeagues(null);
    setMyLeaguesBusy(false);
    setUseManualEntry(false);
  }

  // Optimistic league-discovery fetch — never surfaces an error. A 403
  // (no stored ESPN cookies yet, the ordinary case for a brand-new capture
  // that hasn't linked anything before) or any other failure just leaves
  // `myLeagues` null, which is exactly "no picker available, show the text
  // field" (see the render logic below). Guarded by the flag so it's a
  // true no-op with `espn.league_picker` off.
  async function fetchMyLeagues() {
    // Entry mode: /api/espn/my-leagues reads the session user's STORED
    // credentials — neither exists before the mint. Skip, keep the text field.
    if (!leaguePicker || entry) return;
    setMyLeaguesBusy(true);
    try {
      const leagues = await getMyEspnLeagues();
      setMyLeagues(leagues);
      if (leagues.length > 0) setUseManualEntry(false);
    } catch {
      setMyLeagues(null);
    } finally {
      setMyLeaguesBusy(false);
    }
  }

  // Picking a league from the list proceeds through the SAME preview flow
  // manual entry uses — just with the id supplied directly instead of
  // parsed from the text field.
  function selectMyLeague(lg: EspnMyLeague) {
    setInput(lg.league_id);
    void fetchPreview({ leagueId: lg.league_id });
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
      } else {
        // No league id typed yet — this is exactly the case the picker is
        // for. A capture only fills local state; cookies aren't stored
        // server-side until a link actually happens, so this call 403s
        // (harmlessly) on a user's FIRST-ever ESPN link and succeeds from
        // their second onward (or immediately if they'd linked before).
        void fetchMyLeagues();
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
  // (without waiting for the espnS2/swid state to flush — setState is
  // async) and the league-picker path pass the picked id directly instead
  // of parsing it back out of the text field.
  async function fetchPreview(override?: {
    espnS2?: string;
    swid?: string;
    leagueId?: string;
  }) {
    const leagueId = override?.leagueId ?? parseEspnLeagueInput(input);
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
      // Entry mode previews through the sessionless route — same wire shape,
      // same errors (incl. the private-league 403 handled below).
      const res: EspnLinkPreview | EspnImportSummary = entry
        ? await entryEspnPreview({
            espnLeagueId: leagueId,
            espnS2: s2 || undefined,
            swid: sw || undefined,
          })
        : await linkEspnLeague({
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
      // Entry mode: the claim MINTS the session first (deterministic
      // entry:espn:… id; the api fn stores the token), hands the user to the
      // host, then the canonical import below runs under the fresh token —
      // exactly the linked flow from here on.
      if (entry) {
        const minted = await entryPlatformMint({
          platform: 'espn',
          espnLeagueId: preview.league.espn_league_id,
          season: preview.league.season,
          teamId,
          espnS2: espnS2.trim() || undefined,
          swid: swid.trim() || undefined,
        });
        onEntrySession?.({
          user_id: minted.user_id,
          display_name: minted.display_name,
        });
      }
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
            {/* League picker (flag `espn.league_picker`): once we know the
                account's ESPN cookies (WebView capture, or already stored
                from a prior link), skip asking for a league id entirely —
                list what the account actually has. Manual entry is always
                one tap away (below), and is what renders here with the
                flag off or before any leagues are known. */}
            {showingPicker && myLeagues ? (
              <View testID="espn-link.my-leagues">
                <Text style={[type.bodySm, styles.sub]}>Pick your ESPN league:</Text>
                <ScrollView style={styles.teamList}>
                  {myLeagues.map((lg, idx) => (
                    <Pressable
                      key={lg.league_id}
                      testID={`espn-link.my-league.${lg.league_id}`}
                      accessibilityRole="button"
                      accessibilityLabel={`${lg.league_name}${lg.season ? `, ${lg.season}` : ''}${lg.team_name ? `, ${lg.team_name}` : ''}`}
                      onPress={() => selectMyLeague(lg)}
                      disabled={busy}
                      style={({ pressed }) => [
                        styles.teamRow,
                        idx === myLeagues.length - 1 && styles.teamRowLast,
                        busy && styles.rowDim,
                        pressed && !busy && styles.rowPressed,
                      ]}
                    >
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <Text style={type.title} numberOfLines={1}>{lg.league_name}</Text>
                        <Text style={[type.bodySm, styles.rowMeta]}>
                          {lg.season ? `${lg.season}` : ''}
                          {lg.team_name ? `${lg.season ? ' · ' : ''}${lg.team_name}` : ''}
                        </Text>
                      </View>
                      <Icon name="chevron-right" size={16} color={chalk.dim} />
                    </Pressable>
                  ))}
                </ScrollView>
                <Pressable
                  testID="espn-link.manual-entry-toggle"
                  onPress={() => setUseManualEntry(true)}
                  style={styles.cookieToggle}
                  accessibilityRole="button"
                >
                  <Text style={[type.bodySm, styles.learnMoreText]}>
                    Don’t see it? Enter a league ID instead
                  </Text>
                </Pressable>
              </View>
            ) : (
              <>
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
                {leaguePicker && myLeagues && myLeagues.length === 0 ? (
                  <Text testID="espn-link.my-leagues-empty" style={[type.bodySm, styles.cookieHint]}>
                    No fantasy football leagues found on this ESPN account.
                  </Text>
                ) : null}
                {leaguePicker && useManualEntry && myLeagues && myLeagues.length > 0 ? (
                  <Pressable
                    testID="espn-link.picker-toggle"
                    onPress={() => setUseManualEntry(false)}
                    style={styles.cookieToggle}
                    accessibilityRole="button"
                  >
                    <Text style={[type.bodySm, styles.learnMoreText]}>
                      Back to my leagues
                    </Text>
                  </Pressable>
                ) : null}
                {leaguePicker && myLeaguesBusy ? (
                  <ActivityIndicator testID="espn-link.my-leagues-busy" color={chalk.dim} />
                ) : null}
              </>
            )}
            <Pressable
              testID="espn-link.private-toggle"
              onPress={() => {
                setShowCookies((v) => !v);
                // Opening the private section is also the "stored creds
                // exist" trigger (a user who linked ESPN before, or
                // captured earlier this session) — try the picker without
                // requiring another WebView round-trip. No-ops past the
                // first successful/attempted fetch.
                if (!showCookies && myLeagues === null) void fetchMyLeagues();
              }}
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
            {!showingPicker ? (
              <Button
                testID="espn-link.continue"
                label={busy ? 'Fetching league…' : 'Continue'}
                onPress={() => fetchPreview()}
                disabled={busy}
                style={styles.cta}
              />
            ) : null}
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
  // League-picker ↔ manual-entry toggle links — ice = action color (Chalkline).
  learnMoreText: { color: ice.base },
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

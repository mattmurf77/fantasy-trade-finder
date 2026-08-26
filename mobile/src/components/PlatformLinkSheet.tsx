import React, { useState } from 'react';
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
import {
  LinkPlatform,
  PlatformLinkPreview,
  PlatformImportSummary,
  linkPlatformLeague,
  isPlatformPreview,
  parseMflLeagueInput,
  parseFleaflickerLeagueInput,
  discoverFleaflickerLeagues,
  FleaflickerDiscovered,
  MflAuthLeague,
  MflAuthImportResult,
  mflAuthLink,
  mflAuthImport,
} from '../api/platformLink';
import { entryMflPreview, entryPlatformMint } from '../api/platformEntry';

interface Props {
  visible: boolean;
  platform: LinkPlatform;
  onClose: () => void;
  /** Fired after a successful import — the caller merges + activates the league. */
  onLinked: (league: { league_id: string; name: string; total_rosters: number; platform: LinkPlatform }) => void;
  /** Sessionless entry mode (landing platform options v2, D-164; MFL only —
   *  SignInScreen hosts this sheet with NO session). Preview goes through
   *  the sessionless /api/entry/platform; picking a franchise MINTS the
   *  entry session first (delivered via onEntrySession), then runs the
   *  canonical import under the fresh token. The `mfl.auth_link`
   *  username/password path is suppressed — its routes require a session.
   *  Default off — linked flow byte-identical. */
  entry?: boolean;
  /** Entry mode only: the minted session's user, delivered BEFORE the
   *  import runs so the host can pin it into useSession. */
  onEntrySession?: (user: { user_id: string; display_name: string }) => void;
}

const LABEL: Record<LinkPlatform, string> = { mfl: 'MFL', fleaflicker: 'Fleaflicker' };

// Zero-auth (no cookie paste) platform link flow for MFL + Fleaflicker,
// mirroring EspnLinkSheet's three steps:
//   1. input — league URL/ID (MFL adds a season year; Fleaflicker adds an
//              optional "find by email" lookup)
//   2. team  — preview came back; "which team is yours?"
//   3. done  — import summary: teams, match rate, skipped players, read-only note
export default function PlatformLinkSheet({
  visible,
  platform,
  onClose,
  onLinked,
  entry,
  onEntrySession,
}: Props) {
  const [step, setStep] = useState<'input' | 'team' | 'done' | 'auth-pick' | 'auth-done'>('input');
  const [input, setInput] = useState('');
  const [year, setYear] = useState('2026');
  const [email, setEmail] = useState('');
  const [showEmail, setShowEmail] = useState(false);
  const [discovered, setDiscovered] = useState<FleaflickerDiscovered[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyTeamId, setBusyTeamId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<PlatformLinkPreview | null>(null);
  const [summary, setSummary] = useState<PlatformImportSummary | null>(null);

  // #177 — "Sign in with MFL" path (flag `mfl.auth_link`, MFL only).
  // The password lives in component state just long enough to make the ONE
  // auth-link call (our backend uses it for MFL's login and never stores it);
  // it is cleared the moment the call returns and never logged or echoed.
  // Entry mode suppresses the sign-in path: /api/mfl/auth-link requires a
  // session, and entry's whole point is that none exists yet.
  const mflAuthEnabled = useFlag('mfl.auth_link') && platform === 'mfl' && !entry;
  const [showMflAuth, setShowMflAuth] = useState(false);
  const [mflUser, setMflUser] = useState('');
  const [mflPass, setMflPass] = useState('');
  const [authLeagues, setAuthLeagues] = useState<MflAuthLeague[] | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [authResult, setAuthResult] = useState<MflAuthImportResult | null>(null);

  // Teardown PRD 01-01 audit hit (same hazard as EspnLinkSheet), flag
  // `ux.sheet_guard`: OFF — every close resets (backdrop tap wipes typed
  // league ID / lookup email mid-flow). ON — close keeps state so reopening
  // resumes the step; backdrop/back get Keep editing / Discard while dirty;
  // the explicit Cancel button closes keeping the draft.
  const guardOn = useFlag('ux.sheet_guard');
  const dirty =
    step === 'team' ||
    step === 'auth-pick' ||
    (step === 'input' && !!(input.trim() || email.trim() || mflUser.trim() || mflPass));

  function reset() {
    setStep('input');
    setInput('');
    setYear('2026');
    setEmail('');
    setShowEmail(false);
    setDiscovered(null);
    setBusy(false);
    setBusyTeamId(null);
    setError(null);
    setPreview(null);
    setSummary(null);
    setShowMflAuth(false);
    setMflUser('');
    setMflPass('');
    setAuthLeagues(null);
    setSelected({});
    setAuthResult(null);
  }

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
        'Your entries will be cleared.',
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

  function parseInput(raw: string): string | null {
    return platform === 'mfl' ? parseMflLeagueInput(raw) : parseFleaflickerLeagueInput(raw);
  }

  async function findByEmail() {
    if (!email.trim().includes('@')) {
      setError('Enter the email on your Fleaflicker account.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const leagues = await discoverFleaflickerLeagues(email.trim());
      setDiscovered(leagues);
      if (leagues.length === 0) setError('No NFL leagues found for that email.');
    } catch (e: any) {
      setError(e?.message || "Couldn't reach Fleaflicker — try again shortly.");
    } finally {
      setBusy(false);
    }
  }

  async function fetchPreview(leagueId?: string) {
    const id = leagueId || parseInput(input);
    if (!id) {
      setError(
        platform === 'mfl'
          ? 'Enter a numeric MFL league ID or a myfantasyleague.com URL.'
          : 'Enter a numeric Fleaflicker league ID or paste a lookup email below.',
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // Entry mode (MFL only) previews through the sessionless route —
      // normalized to the same PlatformLinkPreview shape.
      const res = entry
        ? await entryMflPreview({
            leagueInput: id,
            year: parseInt(year, 10) || undefined,
          })
        : await linkPlatformLeague({
            platform,
            leagueInput: id,
            year: platform === 'mfl' ? parseInt(year, 10) || undefined : undefined,
          });
      if (isPlatformPreview(res)) {
        setPreview(res);
        setStep('team');
      } else {
        setSummary(res);
        setStep('done');
      }
    } catch (e: any) {
      if (e instanceof ApiError && e.isVerificationRequired) {
        setError('Verify your account to link a league.');
      } else {
        setError(e?.message || `Couldn't reach ${LABEL[platform]} — try again shortly.`);
      }
    } finally {
      setBusy(false);
    }
  }

  async function pickTeam(teamId: string) {
    if (!preview || busyTeamId !== null) return;
    setBusyTeamId(teamId);
    setError(null);
    try {
      // Entry mode: the claim MINTS the session first (deterministic
      // entry:mfl:… id; the api fn stores the token), hands the user to the
      // host, then the canonical import below runs under the fresh token.
      if (entry) {
        const minted = await entryPlatformMint({
          platform: 'mfl',
          leagueInput: preview.league.league_id,
          year: preview.league.season,
          teamId,
        });
        onEntrySession?.({
          user_id: minted.user_id,
          display_name: minted.display_name,
        });
      }
      const res = await linkPlatformLeague({
        platform,
        leagueInput: preview.league.league_id,
        year: preview.league.season,
        teamId,
      });
      if (!isPlatformPreview(res)) {
        setSummary(res);
        setStep('done');
      }
    } catch (e: any) {
      if (e instanceof ApiError && e.isVerificationRequired) {
        setError('Verify your account to link a league.');
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
      platform,
    };
    reset();
    onLinked(lg);
  }

  // ── #177 Sign in with MFL ──────────────────────────────────────────────────

  async function mflSignIn() {
    if (!mflUser.trim() || !mflPass) {
      setError('Enter your MFL username and password.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await mflAuthLink(mflUser.trim(), mflPass, parseInt(year, 10) || undefined);
      setMflPass(''); // transient — done with it the moment the call returns
      setAuthLeagues(res.leagues);
      // Default: import ALL leagues at once (auto-bindable ones pre-checked).
      const pre: Record<string, boolean> = {};
      for (const lg of res.leagues) pre[lg.league_id] = !!lg.franchise_id;
      setSelected(pre);
      if (res.leagues.length === 0) {
        setError(`No MFL leagues found for ${year}.`);
      } else {
        setStep('auth-pick');
      }
    } catch (e: any) {
      setMflPass('');
      if (e instanceof ApiError && (e.body as any)?.error === 'mfl_bad_credentials') {
        setError("MFL didn't accept that username and password.");
      } else if (e instanceof ApiError && e.isVerificationRequired) {
        setError('Verify your account to link a league.');
      } else {
        setError(e?.message || "Couldn't reach MFL — try again shortly.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function mflImportSelected() {
    const ids = (authLeagues || [])
      .map((lg) => lg.league_id)
      .filter((id) => selected[id]);
    if (ids.length === 0) {
      setError('Pick at least one league to import.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await mflAuthImport(ids, parseInt(year, 10) || undefined);
      setAuthResult(res);
      setStep('auth-done');
    } catch (e: any) {
      if (e instanceof ApiError && (e.body as any)?.error === 'mfl_auth_expired') {
        setAuthLeagues(null);
        setStep('input');
        setError('Your MFL sign-in expired — sign in again.');
      } else if (e instanceof ApiError && e.isVerificationRequired) {
        setError('Verify your account to link a league.');
      } else {
        setError(e?.message || 'Import failed — try again.');
      }
    } finally {
      setBusy(false);
    }
  }

  function openAuthImported() {
    const first = authResult?.imported?.[0];
    reset();
    if (first) {
      onLinked({
        league_id: first.league_id,
        name: first.name,
        total_rosters: first.total_teams,
        platform,
      });
    } else {
      onClose();
    }
  }

  const report = step === 'done' ? summary?.report : preview?.report;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={requestClose}>
      <Pressable
        style={styles.backdrop}
        onPress={requestClose}
        accessibilityRole="button"
        accessibilityLabel="Close"
      />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.kav}
      >
        <View style={styles.sheet}>
          <View style={styles.grabber} />
          <Text style={type.heading} accessibilityRole="header">Link a {LABEL[platform]} league</Text>

          {step === 'input' ? (
            <>
              <Text style={[type.bodySm, styles.sub]}>
                Read-only import: we read team names and rosters — we never post
                or change anything in {LABEL[platform]}.
              </Text>
              <TextInput
                testID="platform-link.input"
                style={styles.field}
                value={input}
                onChangeText={setInput}
                placeholder={
                  platform === 'mfl'
                    ? 'MFL league ID or league URL'
                    : 'Fleaflicker league ID or URL'
                }
                placeholderTextColor={chalk.dim}
                autoCapitalize="none"
                autoCorrect={false}
                editable={!busy}
              />
              {platform === 'mfl' ? (
                <TextInput
                  testID="platform-link.year"
                  style={styles.field}
                  value={year}
                  onChangeText={setYear}
                  placeholder="Season year (e.g. 2026)"
                  placeholderTextColor={chalk.dim}
                  keyboardType="number-pad"
                  editable={!busy}
                />
              ) : null}

              {mflAuthEnabled ? (
                <>
                  <Pressable
                    testID="platform-link.mfl-auth-toggle"
                    onPress={() => setShowMflAuth((v) => !v)}
                    style={styles.cookieToggle}
                    accessibilityRole="button"
                    accessibilityState={{ expanded: showMflAuth }}
                  >
                    <Icon name={showMflAuth ? 'chevron-down' : 'chevron-right'} size={14} color={chalk.dim} />
                    <Text style={type.bodySm}>Or sign in with MFL to import all your leagues</Text>
                  </Pressable>
                  {showMflAuth ? (
                    <>
                      <Text style={[type.bodySm, styles.skipNote]}>
                        Your password goes to MFL's sign-in only — we keep just
                        the session it returns, never the password. Private
                        leagues work too.
                      </Text>
                      <TextInput
                        testID="platform-link.mfl-username"
                        style={styles.field}
                        value={mflUser}
                        onChangeText={setMflUser}
                        placeholder="MFL username"
                        placeholderTextColor={chalk.dim}
                        autoCapitalize="none"
                        autoCorrect={false}
                        editable={!busy}
                      />
                      <TextInput
                        testID="platform-link.mfl-password"
                        style={styles.field}
                        value={mflPass}
                        onChangeText={setMflPass}
                        placeholder="MFL password"
                        placeholderTextColor={chalk.dim}
                        autoCapitalize="none"
                        autoCorrect={false}
                        secureTextEntry
                        textContentType="password"
                        editable={!busy}
                      />
                      <Button
                        testID="platform-link.mfl-signin"
                        label={busy ? 'Signing in…' : 'Sign in & find my leagues'}
                        variant="secondary"
                        compact
                        onPress={() => { void mflSignIn(); }}
                        disabled={busy}
                      />
                    </>
                  ) : null}
                </>
              ) : null}

              {platform === 'fleaflicker' ? (
                <>
                  <Pressable
                    testID="platform-link.email-toggle"
                    onPress={() => setShowEmail((v) => !v)}
                    style={styles.cookieToggle}
                    accessibilityRole="button"
                    accessibilityState={{ expanded: showEmail }}
                  >
                    <Icon name={showEmail ? 'chevron-down' : 'chevron-right'} size={14} color={chalk.dim} />
                    <Text style={type.bodySm}>Don't know the ID? Find leagues by email</Text>
                  </Pressable>
                  {showEmail ? (
                    <>
                      <TextInput
                        testID="platform-link.email"
                        style={styles.field}
                        value={email}
                        onChangeText={setEmail}
                        placeholder="Fleaflicker account email"
                        placeholderTextColor={chalk.dim}
                        autoCapitalize="none"
                        autoCorrect={false}
                        keyboardType="email-address"
                        editable={!busy}
                      />
                      <Button
                        testID="platform-link.email-lookup"
                        label={busy ? 'Looking up…' : 'Find my leagues'}
                        variant="secondary"
                        compact
                        onPress={findByEmail}
                        disabled={busy}
                      />
                      {discovered && discovered.length > 0 ? (
                        <ScrollView style={styles.teamList}>
                          {discovered.map((lg) => (
                            <Pressable
                              key={lg.league_id}
                              testID={`platform-link.discovered.${lg.league_id}`}
                              accessibilityRole="button"
                              accessibilityState={{ disabled: busy }}
                              onPress={() => fetchPreview(lg.league_id)}
                              disabled={busy}
                              style={({ pressed }) => [styles.teamRow, pressed && styles.rowPressed]}
                            >
                              <Text style={type.title} numberOfLines={1}>{lg.name}</Text>
                              <Icon name="chevron-right" size={16} color={chalk.dim} />
                            </Pressable>
                          ))}
                        </ScrollView>
                      ) : null}
                    </>
                  ) : null}
                </>
              ) : null}

              {error ? (
                <Text testID="platform-link.error" style={styles.error}>{error}</Text>
              ) : null}
              <Button
                testID="platform-link.continue"
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
                {preview.league.name} · {preview.league.total_teams} teams
                {preview.league.season ? ` · season ${preview.league.season}` : ''}. Which
                team is yours?
              </Text>
              {error ? (
                <Text testID="platform-link.error" style={styles.error}>{error}</Text>
              ) : null}
              <ScrollView style={styles.teamList}>
                {preview.teams.map((t, idx) => {
                  const isBusy = busyTeamId === t.team_id;
                  const dim = busyTeamId !== null && !isBusy;
                  return (
                    <Pressable
                      key={t.team_id}
                      testID={`platform-link.team.${t.team_id}`}
                      accessibilityRole="button"
                      accessibilityLabel={`${t.name}, ${t.mapped_players} players mapped`}
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
                {LABEL[platform]} leagues are read-only imports. Rankings, tiers,
                and trios fully work today; trade features come later.
                {platform === 'mfl' && summary.future_picks_stored
                  ? ' Future draft picks were saved for upcoming pick-inclusive trades.'
                  : ''}
              </Text>
              <Button
                testID="platform-link.open"
                label="Open league"
                onPress={openLeague}
                style={styles.cta}
              />
            </>
          ) : null}

          {step === 'auth-pick' && authLeagues ? (
            <>
              <Text style={[type.bodySm, styles.sub]}>
                Found {authLeagues.length} MFL league{authLeagues.length === 1 ? '' : 's'} for {year}.
                All are selected — uncheck any you don't want.
              </Text>
              {error ? (
                <Text testID="platform-link.error" style={styles.error}>{error}</Text>
              ) : null}
              <ScrollView style={styles.teamList}>
                {authLeagues.map((lg, idx) => {
                  const bindable = !!lg.franchise_id;
                  const isOn = !!selected[lg.league_id];
                  return (
                    <Pressable
                      key={lg.league_id}
                      testID={`platform-link.mfl-league.${lg.league_id}`}
                      accessibilityRole="checkbox"
                      accessibilityLabel={lg.name}
                      accessibilityState={{ checked: isOn, disabled: !bindable || busy }}
                      onPress={() =>
                        setSelected((s) => ({ ...s, [lg.league_id]: !s[lg.league_id] }))
                      }
                      disabled={!bindable || busy}
                      style={({ pressed }) => [
                        styles.teamRow,
                        idx === authLeagues.length - 1 && styles.teamRowLast,
                        !bindable && styles.rowDim,
                        pressed && bindable && styles.rowPressed,
                      ]}
                    >
                      <View style={[styles.checkbox, isOn && styles.checkboxOn]}>
                        {isOn ? <Icon name="check" size={12} color={chalk.base} /> : null}
                      </View>
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <Text style={type.title} numberOfLines={1}>{lg.name}</Text>
                        <Text style={[type.bodySm, styles.rowMeta]}>
                          {bindable
                            ? `Your team: ${lg.franchise_name || `franchise ${lg.franchise_id}`}`
                            : "Couldn't detect your team — link this one manually"}
                        </Text>
                      </View>
                    </Pressable>
                  );
                })}
              </ScrollView>
              <Button
                testID="platform-link.mfl-import"
                label={
                  busy
                    ? 'Importing…'
                    : `Import ${Object.values(selected).filter(Boolean).length} league${
                        Object.values(selected).filter(Boolean).length === 1 ? '' : 's'
                      }`
                }
                onPress={() => { void mflImportSelected(); }}
                disabled={busy}
                style={styles.cta}
              />
            </>
          ) : null}

          {step === 'auth-done' && authResult ? (
            <>
              <Text style={[type.bodySm, styles.sub]}>
                Imported {authResult.imported.length} of {authResult.requested} league
                {authResult.requested === 1 ? '' : 's'}.
              </Text>
              <ScrollView style={styles.teamList}>
                {authResult.imported.map((lg) => (
                  <View key={lg.league_id} style={styles.teamRow}>
                    <Icon name="check" size={16} color={semantic.pos} />
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={type.title} numberOfLines={1}>{lg.name}</Text>
                      <Text style={[type.bodySm, styles.rowMeta]}>
                        {lg.teams_imported} teams · {Math.round(lg.match_rate * 100)}% of
                        players matched
                      </Text>
                    </View>
                  </View>
                ))}
                {authResult.failed.map((f) => (
                  <View key={f.league_id} style={styles.teamRow}>
                    <Icon name="x" size={16} color={semantic.neg} />
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={type.title} numberOfLines={1}>League {f.league_id}</Text>
                      <Text style={[type.bodySm, styles.rowMeta]}>{f.message}</Text>
                    </View>
                  </View>
                ))}
              </ScrollView>
              <Text style={[type.bodySm, styles.readOnlyNote]}>
                MFL leagues are read-only imports. Rankings, tiers, and trios
                fully work today; trade features come later.
              </Text>
              <Button
                testID="platform-link.mfl-open"
                label={authResult.imported.length > 0 ? 'Open league' : 'Close'}
                onPress={openAuthImported}
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
  checkbox: {
    width: 20,
    height: 20,
    borderWidth: 1,
    borderColor: ink.lineStrong,
    borderRadius: radii.xs,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxOn: { borderColor: ice.base, backgroundColor: ink.ink3 },
  rowPressed: { backgroundColor: ink.ink3 },
  rowDim: { opacity: 0.45 },
  rowMeta: { marginTop: 2 },
  skipNote: { color: chalk.dim },
  readOnlyNote: { color: chalk.dim, marginTop: space.xs },
});

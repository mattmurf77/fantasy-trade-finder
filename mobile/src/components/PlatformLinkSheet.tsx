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
import { ink, chalk, semantic, space, radii, type, shadowSheet, scrim } from '../theme/chalkline';
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
} from '../api/platformLink';

interface Props {
  visible: boolean;
  platform: LinkPlatform;
  onClose: () => void;
  /** Fired after a successful import — the caller merges + activates the league. */
  onLinked: (league: { league_id: string; name: string; total_rosters: number; platform: LinkPlatform }) => void;
}

const LABEL: Record<LinkPlatform, string> = { mfl: 'MFL', fleaflicker: 'Fleaflicker' };

// Zero-auth (no cookie paste) platform link flow for MFL + Fleaflicker,
// mirroring EspnLinkSheet's three steps:
//   1. input — league URL/ID (MFL adds a season year; Fleaflicker adds an
//              optional "find by email" lookup)
//   2. team  — preview came back; "which team is yours?"
//   3. done  — import summary: teams, match rate, skipped players, read-only note
export default function PlatformLinkSheet({ visible, platform, onClose, onLinked }: Props) {
  const [step, setStep] = useState<'input' | 'team' | 'done'>('input');
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

  // Teardown PRD 01-01 audit hit (same hazard as EspnLinkSheet), flag
  // `ux.sheet_guard`: OFF — every close resets (backdrop tap wipes typed
  // league ID / lookup email mid-flow). ON — close keeps state so reopening
  // resumes the step; backdrop/back get Keep editing / Discard while dirty;
  // the explicit Cancel button closes keeping the draft.
  const guardOn = useFlag('ux.sheet_guard');
  const dirty =
    step === 'team' ||
    (step === 'input' && !!(input.trim() || email.trim()));

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
      const res = await linkPlatformLeague({
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

  const report = step === 'done' ? summary?.report : preview?.report;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={requestClose}>
      <Pressable style={styles.backdrop} onPress={requestClose} />
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.kav}
      >
        <View style={styles.sheet}>
          <View style={styles.grabber} />
          <Text style={type.heading}>Link a {LABEL[platform]} league</Text>

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

              {platform === 'fleaflicker' ? (
                <>
                  <Pressable
                    testID="platform-link.email-toggle"
                    onPress={() => setShowEmail((v) => !v)}
                    style={styles.cookieToggle}
                    accessibilityRole="button"
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
  rowPressed: { backgroundColor: ink.ink3 },
  rowDim: { opacity: 0.45 },
  rowMeta: { marginTop: 2 },
  skipNote: { color: chalk.dim },
  readOnlyNote: { color: chalk.dim, marginTop: space.xs },
});

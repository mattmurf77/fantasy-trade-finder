import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  FlatList,
  Pressable,
  ActivityIndicator,
  StyleSheet,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ink, chalk, ice, semantic, space, type } from '../theme/chalkline';
import { Badge, Button, Icon } from '../components/chalkline';
import { useSession } from '../state/useSession';
import { useFlag, onboardingEnabled } from '../state/useFeatureFlags';
import { getLeagues } from '../api/sleeper';
import { getEspnLeagues } from '../api/espn';
import { getPlatformLeagues, LinkPlatform } from '../api/platformLink';
import { buildSessionInitBody, submitSessionInit } from '../api/auth';
import { maybePregenTrades } from '../api/tradePregen';
import { track } from '../api/events';
import EspnLinkSheet from '../components/EspnLinkSheet';
import PlatformLinkSheet from '../components/PlatformLinkSheet';
import type { LeagueSummary } from '../shared/types';

// Platform → league-list badge text (ESPN keeps 'ESPN'; MFL/Fleaflicker are
// the new short badges — cross-client-invariants platform-badge rule).
const PLATFORM_BADGE: Record<string, string> = {
  espn: 'ESPN',
  mfl: 'MFL',
  fleaflicker: 'FLEA',
};

interface Props {
  onLeaguePicked: () => void;
  onSignOut: () => void;
  /** #130 — open the ESPN link sheet on mount (Settings CTA). Honored only
   *  while the `espn.link` flag is on. */
  autoOpenEspnLink?: boolean;
}

// Show user's leagues → tap one → run sessionInit against it → done.
// Matches the web app's selectLeague flow but without the overlay modals.
export default function LeaguePickerScreen({ onLeaguePicked, onSignOut, autoOpenEspnLink }: Props) {
  const user = useSession((s) => s.user);
  const cached = useSession((s) => s.leagues);
  const setLeagues = useSession((s) => s.setLeagues);
  const setLeague = useSession((s) => s.setLeague);

  const [loading, setLoading] = useState(cached.length === 0);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slowLoad, setSlowLoad] = useState(false);
  // League linking (read-only import). Each platform gates on its own flag.
  const espnEnabled = useFlag('espn.link');
  const mflEnabled = useFlag('mfl.link');
  const fleaflickerEnabled = useFlag('fleaflicker.link');
  const [espnOpen, setEspnOpen] = useState(false);
  // Which zero-auth platform sheet is open (MFL / Fleaflicker), if any.
  const [platformOpen, setPlatformOpen] = useState<LinkPlatform | null>(null);

  // #130 — Settings' ESPN CTA lands here with `espnLink: true`; open the
  // sheet once the flag confirms. Effect (not initial state) because the
  // flag store may hydrate after mount.
  useEffect(() => {
    if (autoOpenEspnLink && espnEnabled) setEspnOpen(true);
  }, [autoOpenEspnLink, espnEnabled]);

  // Onboarding item 6 (F9): exactly one league → skip the picker (free step
  // removal). Once-only per mount; never when the user came here to link
  // ESPN. Failure falls back to this screen's existing inline error +
  // retry — the single league row on screen names the league.
  const autoSkipTried = useRef(false);
  useEffect(() => {
    if (autoSkipTried.current) return;
    if (loading || error || selectingId || autoOpenEspnLink) return;
    if (cached.length !== 1) return;
    if (!onboardingEnabled('onboarding.league_autoskip')) return;
    autoSkipTried.current = true;
    void pickLeague(cached[0], { auto: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cached, loading, error, selectingId, autoOpenEspnLink]);

  // Render free-tier cold starts run 30–60s. Hold the friendly default for
  // the first 4s so warm requests never show the alarming "waking up" copy.
  useEffect(() => {
    if (!loading) {
      setSlowLoad(false);
      return;
    }
    const t = setTimeout(() => setSlowLoad(true), 4000);
    return () => clearTimeout(t);
  }, [loading]);

  useEffect(() => {
    if (!user) return;
    if (cached.length > 0) {
      setLoading(false);
      return;
    }
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.user_id]);

  async function refresh() {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      const lgs = await getLeagues(user.user_id);
      // Merge in imported non-Sleeper leagues (each flag-gated; backend 404s
      // dark). Best-effort — a hiccup on one platform must not hide the rest.
      const merged: LeagueSummary[] = [...lgs];
      const seen = new Set(lgs.map((lg) => lg.league_id));
      const addAll = (rows: LeagueSummary[]) => {
        for (const row of rows) {
          if (!seen.has(row.league_id)) {
            merged.push(row);
            seen.add(row.league_id);
          }
        }
      };
      if (espnEnabled) {
        try {
          const espn = await getEspnLeagues();
          addAll(espn.map((lg) => ({
            league_id: lg.league_id,
            name: lg.name || `ESPN league ${lg.league_id}`,
            total_rosters: lg.total_rosters ?? undefined,
            platform: 'espn',
          })));
        } catch {
          /* non-fatal */
        }
      }
      for (const p of ['mfl', 'fleaflicker'] as LinkPlatform[]) {
        if (p === 'mfl' ? !mflEnabled : !fleaflickerEnabled) continue;
        try {
          const rows = await getPlatformLeagues(p);
          addAll(rows.map((lg) => ({
            league_id: lg.league_id,
            name: lg.name || `${PLATFORM_BADGE[p]} league ${lg.league_id}`,
            total_rosters: lg.total_rosters ?? undefined,
            platform: p,
          })));
        } catch {
          /* non-fatal */
        }
      }
      setLeagues(merged);
    } catch (e: any) {
      setError(e?.message || 'Could not load leagues');
    } finally {
      setLoading(false);
    }
  }

  // Post-import handler (any platform): put the league in the cached list
  // first (buildSessionInitBody detects imported leagues via that cache's
  // `platform` field), then run the normal pick flow.
  async function onLeagueLinked(lg: {
    league_id: string; name: string; total_rosters: number; platform?: string;
  }) {
    setEspnOpen(false);
    setPlatformOpen(null);
    const summary: LeagueSummary = {
      league_id: lg.league_id,
      name: lg.name,
      total_rosters: lg.total_rosters,
      platform: lg.platform || 'espn',   // EspnLinkSheet omits platform
    };
    const merged = [
      ...cached.filter((x) => x.league_id !== lg.league_id),
      summary,
    ];
    await setLeagues(merged);
    await pickLeague(summary);
  }

  async function pickLeague(lg: LeagueSummary, opts?: { auto?: boolean }) {
    if (!user || selectingId) return;
    setSelectingId(lg.league_id);
    setError(null);
    track(
      'league_selected',
      {
        league_index: cached.findIndex((x) => x.league_id === lg.league_id),
        league_count: cached.length,
        auto: !!opts?.auto,
        // F12 segment tag: redraft users are excluded from activation
        // denominators (dynasty values are wrong for them by construction).
        league_type:
          lg.settings_type === 0
            ? 'redraft'
            : lg.settings_type === 1
              ? 'keeper'
              : lg.settings_type === 2
                ? 'dynasty'
                : 'unknown',
      },
      'LeaguePicker',
    );
    try {
      // INIT-08-client: two-phase optimistic navigation.
      //
      // Phase 1 (~2-3s): fetch rosters + users from Sleeper and build the
      // session_init payload. This is the "data-gather" leg — fast enough
      // that we block on it so we can surface Sleeper errors inline.
      const body = await buildSessionInitBody(user, { league_id: lg.league_id, name: lg.name });

      // Persist the league so RootNav gates to 'Main' immediately and the
      // user sees their tabs while the backend is still processing.
      await setLeague({ league_id: lg.league_id, league_name: lg.name });
      onLeaguePicked();

      // Phase 2 (~5-10s, background): POST to /api/session/init. Runs
      // detached so it doesn't block the tab transition. On failure we
      // can't navigate back (the user is already in Main) — surface a
      // toast or let the tabs' query retry handle it gracefully. Any
      // queries that fire before this lands will see a 401 or "session
      // not initialized" and retry via their own error/refetch logic.
      submitSessionInit(body)
        .then(() => {
          // Onboarding item 4 (hazard H3 — hook the EXISTING init path):
          // pregen the trade deck the moment the league session exists so
          // cards are ready/streaming when the user reaches Trades.
          // Flag-gated + deduped inside; fire-and-forget, never throws.
          maybePregenTrades(lg.league_id);
        })
        .catch((e) => {
          // Non-fatal: the tabs will retry their queries. Log for Sentry
          // triage but don't interrupt the user's session.
          console.warn('[INIT-08] background sessionInit failed:', e?.message);
        });
    } catch (e: any) {
      setError(e?.message || 'Failed to import this league');
      setSelectingId(null);
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Choose a League</Text>
          <Text style={styles.sub}>Leagues for {user?.display_name || '…'}</Text>
        </View>
        <Button label="Sign out" variant="ghost" compact onPress={onSignOut} />
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator color={ice.base} />
          <Text style={styles.loadingText}>
            {slowLoad
              ? 'Waking up server — first request after a quiet period can take 30s.'
              : 'Loading your leagues…'}
          </Text>
        </View>
      ) : error ? (
        <View style={styles.centered}>
          <Text style={styles.error}>{error}</Text>
          <Button label="Try again" variant="secondary" compact onPress={refresh} />
        </View>
      ) : cached.length === 0 ? (
        <View style={styles.centered}>
          <Text style={styles.error}>
            No 2026 NFL leagues found for this account.
          </Text>
        </View>
      ) : (
        <FlatList
          data={cached}
          keyExtractor={(lg) => lg.league_id}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={false} onRefresh={refresh} tintColor={ice.base} />
          }
          renderItem={({ item }) => {
            const isBusy = selectingId === item.league_id;
            return (
              <Pressable
                testID={`leagues.row.${item.league_id}`}
                style={({ pressed }) => [
                  styles.row,
                  pressed && styles.rowPressed,
                  isBusy && styles.rowBusy,
                ]}
                onPress={() => pickLeague(item)}
                disabled={!!selectingId}
              >
                <View style={styles.rowBody}>
                  <View style={styles.rowNameRow}>
                    <Text style={[styles.rowName, styles.rowNameText]} numberOfLines={1}>
                      {item.name}
                    </Text>
                    {item.platform && PLATFORM_BADGE[item.platform] ? (
                      <Badge label={PLATFORM_BADGE[item.platform]} />
                    ) : null}
                  </View>
                  <Text style={styles.rowMeta}>
                    {item.total_rosters || 12} teams
                  </Text>
                </View>
                {isBusy ? (
                  <ActivityIndicator color={chalk.dim} />
                ) : (
                  <Icon name="chevron-right" size={16} color={chalk.dim} />
                )}
              </Pressable>
            );
          }}
        />
      )}

      {/* Flag-gated link affordances. Each platform gates on its own flag and
          appears in every non-loading state — including "no leagues found",
          where a non-Sleeper-only manager would otherwise dead-end. */}
      {!loading && (espnEnabled || mflEnabled || fleaflickerEnabled) ? (
        <View style={styles.espnFooter}>
          {espnEnabled ? (
            <Button
              testID="leagues.link-espn"
              label="Link an ESPN league"
              variant="secondary"
              compact
              onPress={() => setEspnOpen(true)}
              disabled={!!selectingId}
            />
          ) : null}
          {mflEnabled ? (
            <Button
              testID="leagues.link-mfl"
              label="Link an MFL league"
              variant="secondary"
              compact
              onPress={() => setPlatformOpen('mfl')}
              disabled={!!selectingId}
              style={styles.linkBtnGap}
            />
          ) : null}
          {fleaflickerEnabled ? (
            <Button
              testID="leagues.link-fleaflicker"
              label="Link a Fleaflicker league"
              variant="secondary"
              compact
              onPress={() => setPlatformOpen('fleaflicker')}
              disabled={!!selectingId}
              style={styles.linkBtnGap}
            />
          ) : null}
        </View>
      ) : null}

      <EspnLinkSheet
        visible={espnOpen}
        onClose={() => setEspnOpen(false)}
        onLinked={onLeagueLinked}
      />
      {platformOpen ? (
        <PlatformLinkSheet
          visible={platformOpen !== null}
          platform={platformOpen}
          onClose={() => setPlatformOpen(null)}
          onLinked={onLeagueLinked}
        />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: ink.ink0 },
  header: {
    paddingLeft: space.xl,
    paddingRight: space.lg,
    paddingTop: space.lg,
    paddingBottom: space.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: { ...type.heading },
  sub: { ...type.bodySm, marginTop: 2 },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: space.xl,
    gap: space.md,
  },
  loadingText: { ...type.bodySm, textAlign: 'center' },
  error: { ...type.bodySm, color: semantic.neg, textAlign: 'center' },
  list: { paddingVertical: space.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 56,
    paddingHorizontal: space.xl,
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: ink.line,
    gap: space.md,
  },
  rowPressed: { backgroundColor: ink.ink3 },
  rowBusy: { opacity: 0.6 },
  rowBody: { flex: 1, minWidth: 0 },
  rowName: { ...type.title },
  rowNameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  rowNameText: { flexShrink: 1 },
  rowMeta: { ...type.bodySm, marginTop: 2 },
  espnFooter: {
    paddingHorizontal: space.xl,
    paddingVertical: space.md,
    borderTopWidth: 1,
    borderTopColor: ink.line,
  },
  linkBtnGap: { marginTop: space.sm },
});

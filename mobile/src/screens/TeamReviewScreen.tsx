import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, ScrollView, Pressable, ActivityIndicator, StyleSheet,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigation } from '@react-navigation/native';

import ChalkText from '../components/chalkline/Text';
import { AnalystAvatar } from '../components/analyst';
import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { useFlag } from '../state/useFeatureFlags';
import { useFinderTargets } from '../state/useFinderTargets';
import { track } from '../api/events';
import {
  saveLeaguePreferences, getLeaguePreferences, getAssetPrefs,
} from '../api/league';
import { FAIRNESS_PREF_KEY, fairnessOnFromPref } from '../api/tradePregen';
import { markTeamReviewCompleted } from '../components/TeamReviewEntryCard';
import {
  getTeamReview, type BeatId, type OutlookOption, type TeamReviewResponse,
  type PlayoffBand,
} from '../api/teamReview';

// #357 / #358 / #359 — TEAM REVIEW.
//
// Tester jonbonjourvi: *"basically an idiot version of wtf do I do next with
// this team"*. Operator framing: a Team Review button INSIDE the find-a-trade
// experience, ANALYST-GUIDED rather than a static dashboard, built from
// valuations that already exist, with two jobs — help the user set their trade
// preferences, and determine team strategy.
//
// THE FORM IS STEPPED BEATS, AND THAT IS A DECISION (D-092), not a default.
// A narrated scroll was rejected because it is a dashboard with prose on top
// and has nowhere to put a decision — a user scrolls past a preference control
// exactly as fast as past a chart, so the "set your preferences" job never
// happens. A Q&A was rejected because canned questions are a worse menu and
// open input needs an LLM, which contradicts "reuse what exists" and breaks the
// deterministic-copy precedent (trade_narrative.py is templates, no LLM).
//
// Stepped wins on its merits: it is the only form where the two jobs are the
// SAME GESTURE. On the `window` beat, reading the strategy verdict and setting
// `team_outlook` are one interaction — agreeing with the analyst IS configuring
// the engine. Four of the six beats write `league_preferences`, which the trade
// engine already reads, so the flow's exit is a deck reshaped by what the user
// just agreed to rather than a report.
//
// WE REUSE THE ANALYST PERSONA, NOT THE AnalystGuide OVERLAY. That overlay
// exists to teach a CONTROL by cutting a spotlight hole over it; this presents
// DATA, so a cutout over a chart would be theatre. It also mounts once in
// RootNav above the whole nav tree, whereas a data surface needs to be a routed
// screen with real back behavior. `useGuide` is likewise coupled to the
// onboarding tour's lifecycle, and borrowing it would tie a Trades feature's
// kill switch to an onboarding flag.
//
// NO FeedbackFAB HERE. This is a TAB-STACK screen, already covered by the
// single global mount in RootNav (#188). A local mount is the #196/#197
// double-FAB bug.
//
// meta.beats_skipped is AUTHORITATIVE — we render `beats` minus
// `beats_skipped`, in `beats` order, and never decide for ourselves that a beat
// is empty. The analytics `beat` property and the step indices bind to the
// server's list.

const OUTLOOK_LABEL: Record<OutlookOption, string> = {
  championship: 'All-in',
  contender: 'Contender',
  rebuilder: 'Rebuilder',
  jets: 'Full teardown',
  not_sure: 'Not sure',
};

const BAND_LABEL: Record<PlayoffBand, string> = {
  likely: 'Likely', tossup: 'Toss-up', unlikely: 'Unlikely',
};
const BAND_COLOR: Record<PlayoffBand, string> = {
  likely: semantic.pos, tossup: semantic.warn, unlikely: semantic.neg,
};

const CORE = ['QB', 'RB', 'WR', 'TE'] as const;

// #369 — the `plan` beat's position levers. WIDER than CORE on purpose: the
// trade engine and the Trade DNA sheet both accept `PICK` in
// acquire/trade_away_positions (`TradeDnaSheet.tsx` DNA_POSITIONS), and a
// summary that claims to show every lever cannot silently drop one. The depth
// beat still offers only CORE because it is talking about STARTABLE BODIES,
// which picks are not.
const PLAN_POSITIONS = ['QB', 'RB', 'WR', 'TE', 'PICK'] as const;
const PLAN_POS_LABEL: Record<string, string> = {
  QB: 'QB', RB: 'RB', WR: 'WR', TE: 'TE', PICK: 'Picks',
};

const pct = (n: number) => `${Math.round(n * 100)}%`;
// #365 — model numbers are small and signed; the sign is the whole point
// (a positive term pushes you toward contending, a negative one away).
// #364 — the unpriced slots, named. `unpriced_slots` repeats a slot once per
// lineup seat (2 DL, 2 LB, ...), so collapse to distinct names in roster order.
const slotList = (slots: string[]) => Array.from(new Set(slots)).join(', ');
const signed = (n: number) => `${n >= 0 ? '+' : '−'}${Math.abs(n).toFixed(2)}`;

export default function TeamReviewScreen() {
  const nav = useNavigation<any>();
  const league = useSession((s) => s.league);
  const leagueId = league?.league_id ?? null;

  const [step, setStep] = useState(0);
  const [outlook, setOutlook] = useState<OutlookOption | null>(null);
  const [acquire, setAcquire] = useState<string[]>([]);
  const [shed, setShed] = useState<string[]>([]);
  const [scoped, setScoped] = useState<{ id: string; name: string } | null>(null);
  const [saving, setSaving] = useState(false);
  // Actions actually COMMITTED this session — the `plan` beat recaps only what
  // the user did, never what they skipped past.
  const done = useRef<Set<string>>(new Set());

  const q = useQuery({
    queryKey: ['team-review', leagueId],
    queryFn: () => getTeamReview(leagueId as string),
    enabled: !!leagueId,
    staleTime: 60_000,
  });
  const data = q.data as TeamReviewResponse | undefined;

  const beats = useMemo<BeatId[]>(() => {
    if (!data) return [];
    const skip = new Set(data.meta.beats_skipped);
    return data.meta.beats.filter((b) => !skip.has(b));
  }, [data]);

  const beat = beats[step];

  const emit = useCallback((name: string, props: Record<string, unknown>) => {
    try { track(name, { league_id: leagueId, ...props }); } catch { /* never block */ }
  }, [leagueId]);

  const next = useCallback(() => {
    setStep((s) => {
      const n = Math.min(s + 1, Math.max(beats.length - 1, 0));
      if (beats[n]) emit('team_review_beat_viewed', { beat: beats[n], index: n + 1 });
      return n;
    });
  }, [beats, emit]);

  // Returns whether the write LANDED. The window and depth beats ignore the
  // result (they advance either way, by design); the `plan` beat uses it to
  // show the inline failure the LLD's §4 always called for.
  const savePrefs = useCallback(async (
    patch: Record<string, unknown>, action: string,
  ): Promise<boolean> => {
    if (!leagueId) return false;
    setSaving(true);
    try {
      // #369 ROOT CAUSE. `POST /api/league/preferences` REQUIRES `team_outlook`
      // and 400s on a body without one (`backend/server.py:15788-15790`);
      // `apiRequest` throws on non-2xx (`mobile/src/api/client.ts:553`). The
      // depth beat posted a positions-only body, so its write threw every
      // time, `done.current.add('positions_set')` on the next line never ran,
      // the catch swallowed it, and no analytics fired — which is why the plan
      // beat could only ever show the window. Backfill the field here, in the
      // one place every beat writes through: session choice, then the stored
      // declaration, then the inference. An explicit value in `patch` still
      // wins, because the spread comes second.
      const fallbackOutlook: OutlookOption =
        outlook ?? data?.window.declared ?? data?.window.inferred ?? 'not_sure';
      await saveLeaguePreferences(
        leagueId, { team_outlook: fallbackOutlook, ...patch } as any,
      );
      done.current.add(action);
      emit('team_review_action_taken', { beat, action });
      // The shared adoption receipt — deliberately the SAME event the guide and
      // the Trade DNA sheet fire, with a `review` source, so this surface joins
      // the existing series instead of splitting it.
      if (action === 'outlook_set') emit('outlook_saved', { source: 'review' });
      return true;
    } catch {
      // A failed write emits NO action event — the flow continues rather than
      // trapping the user on a beat.
      return false;
    } finally {
      setSaving(false);
    }
  }, [leagueId, beat, emit, outlook, data]);

  if (!leagueId) {
    return (
      <View style={styles.center}>
        <ChalkText style={styles.dim}>Pick a league first.</ChalkText>
      </View>
    );
  }
  if (q.isLoading || !data) {
    return (
      <View style={styles.center} testID="team-review.loading">
        <ActivityIndicator color={ice.base} />
      </View>
    );
  }
  if (q.isError || beats.length === 0) {
    return (
      <View style={styles.center} testID="team-review.error">
        <ChalkText style={styles.dim}>
          We couldn&apos;t read this team right now.
        </ChalkText>
      </View>
    );
  }

  const declared = outlook ?? data.window.declared ?? data.window.inferred;

  return (
    <View style={styles.wrap}>
      <View style={styles.progress}>
        {beats.map((b, i) => (
          <View
            key={b}
            style={[
              styles.tick,
              i < step && styles.tickDone,
              i === step && styles.tickOn,
            ]}
          />
        ))}
      </View>

      <ScrollView contentContainerStyle={styles.body}>
        {beat === 'standing' && <Standing data={data} />}
        {beat === 'window' && (
          <Window
            data={data}
            selected={declared}
            onSelect={setOutlook}
          />
        )}
        {beat === 'depth' && (
          <Depth
            data={data}
            acquire={acquire.length ? acquire : data.depth.acquire_positions}
            shed={shed.length ? shed : data.depth.trade_away_positions}
            onAcquire={setAcquire}
            onShed={setShed}
          />
        )}
        {beat === 'divergence' && <Divergence data={data} />}
        {beat === 'partners' && (
          <Partners data={data} onScope={(id, name) => {
            setScoped({ id, name });
            done.current.add('partner_scoped');
            emit('team_review_action_taken', { beat, action: 'partner_scoped' });
          }} />
        )}
        {beat === 'plan' && (
          <Plan
            data={data}
            leagueId={leagueId}
            scoped={scoped}
            onSave={savePrefs}
            saving={saving}
          />
        )}
      </ScrollView>

      <View style={styles.footer}>
        {beat === 'window' ? (
          <Pressable
            testID="team-review.action.outlook_set"
            style={styles.cta}
            disabled={saving}
            onPress={async () => {
              await savePrefs({ team_outlook: declared }, 'outlook_set');
              next();
            }}
          >
            <ChalkText style={styles.ctaText}>Confirm</ChalkText>
          </Pressable>
        ) : beat === 'depth' ? (
          <Pressable
            testID="team-review.action.positions_set"
            style={styles.cta}
            disabled={saving}
            onPress={async () => {
              await savePrefs({
                acquire_positions: acquire.length ? acquire : data.depth.acquire_positions,
                trade_away_positions: shed.length ? shed : data.depth.trade_away_positions,
              }, 'positions_set');
              next();
            }}
          >
            <ChalkText style={styles.ctaText}>Save &amp; continue</ChalkText>
          </Pressable>
        ) : beat === 'plan' ? (
          <Pressable
            testID="team-review.finish"
            style={styles.cta}
            onPress={() => {
              emit('team_review_exited', {
                beat, index: step + 1, outcome: 'completed',
              });
              // #369 — APPLY the scoped partner. The partners beat recorded a
              // manager in local state and emitted `partner_scoped`, but
              // nothing ever handed it to the deck, so the plan beat's "I've
              // already pointed the finder at it" was a false claim and the
              // "Scoped to" row was decoration. The LLD (§4, writes table)
              // always specified the #330 handoff store for this; it was
              // simply never wired. Same contract LeagueSummaryScreen.tsx:1193
              // uses, consumed one-shot on focus by TradesScreen.tsx:2382-2393
              // — no new state layer, no new route, and nothing fires when the
              // user never scoped anyone.
              if (scoped) {
                useFinderTargets.getState().setHandoff({
                  opponent: { userId: scoped.id, name: scoped.name },
                  autoRun: true,
                });
              }
              // Operator 2026-08-20 — completion is recorded so TradesHome
              // shows the minimized row from here on. Deliberately NOT awaited:
              // the write is local and the navigation must not wait on it, and
              // a storage failure costs the minimization, never the exit.
              // No new analytics event: `team_review_exited` with
              // outcome='completed' IS the completion signal and is already
              // registered + classified. A `team_review_completed` peer would
              // split the terminator series, which is exactly what the
              // taxonomy comment on this block warns against.
              void markTeamReviewCompleted(leagueId as string);
              nav.navigate('TradesHome');
            }}
          >
            <ChalkText style={styles.ctaText}>Find my trades</ChalkText>
          </Pressable>
        ) : (
          <Pressable testID="team-review.next" style={styles.cta} onPress={next}>
            <ChalkText style={styles.ctaText}>Next</ChalkText>
          </Pressable>
        )}

        {beat !== 'plan' ? (
          <Pressable testID="team-review.skip" style={styles.skip} onPress={next}>
            <ChalkText style={styles.skipText}>Skip this</ChalkText>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

// ── Beats ─────────────────────────────────────────────────────────────────

function Bubble({ pose, children }: { pose: any; children: React.ReactNode }) {
  return (
    <View style={styles.bubbleRow}>
      <AnalystAvatar pose={pose} size={44} />
      <View style={styles.bubble}>
        <ChalkText style={styles.bubbleText}>{children}</ChalkText>
      </View>
    </View>
  );
}

function Standing({ data }: { data: TeamReviewResponse }) {
  const s = data.standing;
  const o = s.outlook;
  const cov = o?.priced_slot_coverage;
  return (
    <View testID="team-review.beat.standing">
      <Bubble pose="point">Here&apos;s where you actually sit.</Bubble>

      <View style={styles.card}>
        <ChalkText style={styles.kicker}>Roster value · league rank</ChalkText>
        <View style={styles.statRow}>
          <ChalkText style={styles.big}>
            {s.value_rank ? ordinal(s.value_rank) : '—'}
          </ChalkText>
          <ChalkText style={styles.of}>of {s.value_total}</ChalkText>
        </View>
        <View style={styles.chips}>
          {s.position_value.map((p) => (
            <View key={p.position} style={styles.chip}>
              <ChalkText style={styles.chipText}>
                {p.position} {pct(p.share)}
                {p.rank ? ` · ${ordinal(p.rank)}` : ''}
              </ChalkText>
            </View>
          ))}
        </View>
      </View>

      {o ? (
        <View style={styles.card} testID="team-review.beat.standing.outlook">
          <View style={styles.rowBetween}>
            <ChalkText style={styles.kicker}>Playoff outlook</ChalkText>
            <ChalkText style={styles.ribbon}>
              {o.beta ? 'PROJECTED · BETA' : 'PROJECTED'}
            </ChalkText>
          </View>
          <ChalkText style={[styles.band, { color: BAND_COLOR[o.band] }]}>
            {BAND_LABEL[o.band]}
          </ChalkText>
          {cov && cov.affects_strength && cov.fraction < 1 ? (
            <ChalkText style={styles.fine} testID="team-review.standing.coverage">
              Offensive positions only. We rank QB, RB, WR and TE — we do not rank
              IDP or kickers, so {cov.total_slots - cov.priced_slots} of your{' '}
              {cov.total_slots} starting slots
              {cov.unpriced_slots.length ? ` (${slotList(cov.unpriced_slots)})` : ''}
              {' '}carry no value here. This outlook reads your offense.
            </ChalkText>
          ) : null}
        </View>
      ) : null}

      <View style={styles.card}>
        <ChalkText style={styles.kicker}>Points per game</ChalkText>
        {s.scoring ? (
          <ChalkText style={styles.read}>
            {s.scoring.ppg} PPG · {ordinal(s.scoring.ppg_rank)} in the league
          </ChalkText>
        ) : (
          <ChalkText style={styles.dim}>
            {data.meta.scoring_unavailable_reason === 'platform_unsupported'
              ? "Not available for this platform yet — we can't read weekly scores there. Everything else in this review works."
              : "No games played yet — the season hasn't started. This fills in from week 1."}
          </ChalkText>
        )}
      </View>
    </View>
  );
}

function Window({
  data, selected, onSelect,
}: {
  data: TeamReviewResponse;
  selected: OutlookOption;
  onSelect: (o: OutlookOption) => void;
}) {
  const w = data.window;
  const m = w.model;
  const pickVsEven = w.signals.pick_share - w.signals.equal_pick_share;
  // #365 — the ledger card and the arithmetic row are driven by the PAYLOAD,
  // never by a flag the client holds: `signals.firsts` and `model.w_net_firsts`
  // ship together or not at all, so there is no state in which the beat can
  // show a ledger it did not score, or score a term it did not show.
  const f = w.signals.firsts;
  const wFirsts = m?.w_net_firsts;
  const firstsScored = !!f && f.applied && typeof wFirsts === 'number';
  // #371 — `source` is absent while `trades.window_from_odds` is off, and the
  // beat then reads exactly as it did before, off the roster heuristic.
  const fromOdds = w.source === 'odds';
  return (
    <View testID="team-review.beat.window">
      <Bubble pose="thinking">
        {w.inferred === 'rebuilder'
          ? "You're built for later, not for now."
          : w.inferred === 'contender'
            ? "You're built to win now — but check I've got that right."
            : "I can't tell which way you're pointed. You can."}
      </Bubble>

      <View style={styles.card}>
        <ChalkText style={styles.kicker}>
          {fromOdds
            ? 'Your window · from your playoff odds'
            : 'Your window · inferred from roster shape'}
        </ChalkText>
        <ChalkText style={styles.headline}>{OUTLOOK_LABEL[w.inferred]}</ChalkText>
        {/* #371 — when the odds drove, the roster model's own answer stays on
            screen. Two models disagreeing is information; hiding one is not. */}
        {fromOdds && w.odds ? (
          <ChalkText style={styles.read}>
            {`Your playoff odds read ${BAND_LABEL[w.odds.band].toLowerCase()}, `}
            {`so that is the call. Roster shape alone said `}
            {`${OUTLOOK_LABEL[w.roster_inferred ?? w.inferred].toLowerCase()}.`}
          </ChalkText>
        ) : null}
        {!fromOdds && w.odds_reason === 'preseason' && w.odds ? (
          <ChalkText style={styles.fine}>
            {`Your playoff odds read ${BAND_LABEL[w.odds.band].toLowerCase()}, but `}
            {'nobody has played a game yet, so we are not letting a preseason '}
            {'simulation set your window. Roster shape below.'}
          </ChalkText>
        ) : null}
        {!fromOdds && w.odds_reason === 'odds_unavailable' ? (
          <ChalkText style={styles.fine}>
            We do not have playoff odds for this league, so this is roster shape only.
          </ChalkText>
        ) : null}
        {/* #365 — the age thresholds come from the payload. Hardcoding them is
            how this shipped saying "23 and under" against a youth_age of 26. */}
        <Row
          label={m ? `Value age ${m.vet_age} and over` : 'Veteran value share'}
          value={pct(w.signals.vet_share)}
        />
        <Row
          label={m ? `Value age ${m.youth_age} and under` : 'Young value share'}
          value={pct(w.signals.youth_share)}
        />
        <Row
          label="Pick capital vs an even split"
          value={`${(w.signals.pick_share / Math.max(w.signals.equal_pick_share, 1e-6)).toFixed(1)}×`}
        />
      </View>

      {/* #365 — "number of 1sts owned vs traded away". The counts are shown
          whenever the backend computed them, INCLUDING when it refused to
          score them: a league whose pick history predates capture must read
          as "we cannot see this", never as a confident zero. */}
      {f ? (
        <View style={styles.card} testID="team-review.window.firsts">
          <ChalkText style={styles.kicker}>First-round picks</ChalkText>
          <Row label="You hold" value={`${f.held}`} />
          <Row label="Yours, traded away" value={`${f.traded_away}`} />
          <Row label="Acquired from others" value={`${f.acquired}`} />
          {f.provenance === 'observed' ? (
            <ChalkText style={styles.fine}>
              {f.net === 0
                ? 'Net even — you have replaced every first you moved.'
                : f.net > 0
                  ? `Net +${f.net}: you are collecting firsts, which reads as building for later.`
                  : `Net ${f.net}: you have spent firsts, which reads as going for it now.`}
            </ChalkText>
          ) : f.provenance === 'none_traded' ? (
            <ChalkText style={styles.fine}>
              No first-round pick in this league is recorded as having changed
              hands. That could mean none has, or that the trade history predates
              what we can see — so we are not counting this signal.
            </ChalkText>
          ) : (
            <ChalkText style={styles.fine}>
              We have no draft-pick records for this league, so this signal is not
              counted.
            </ChalkText>
          )}
        </View>
      ) : null}

      {m ? (
        <View style={styles.card} testID="team-review.window.inputs">
          <ChalkText style={styles.kicker}>Every input behind that call</ChalkText>
          <Row
            label={`Veteran share ${pct(w.signals.vet_share)} × ${m.w_vet_share}`}
            value={signed(m.w_vet_share * w.signals.vet_share)}
          />
          <Row
            label={`Young share ${pct(w.signals.youth_share)} × −${m.w_youth_share}`}
            value={signed(-m.w_youth_share * w.signals.youth_share)}
          />
          <Row
            label={`Pick capital ${signed(pickVsEven)} vs even × −${m.w_pick_share}`}
            value={signed(-m.w_pick_share * pickVsEven)}
          />
          {/* #365 — a term that scores must also appear here. D-101 exists
              because the beat once described a model it was not running. */}
          {firstsScored && f ? (
            <Row
              label={`Net firsts ${f.net >= 0 ? '+' : '−'}${Math.abs(f.net)} of ${f.own_total} × −${wFirsts}`}
              value={signed(-(wFirsts as number) * f.net_share)}
            />
          ) : null}
          <Row label="Total score" value={signed(w.signals.score)} accent />
          <ChalkText style={styles.fine}>
            {`Contending at ${signed(m.contender_cut)} or above, rebuilding at `}
            {`${signed(m.rebuilder_cut)} or below, anything between is "not sure".`}
          </ChalkText>
          {/* This sentence becomes a lie the moment the net-firsts term is
              scored, so it is conditional on the term rather than fixed copy. */}
          {firstsScored ? (
            <ChalkText style={styles.fine}>
              That is the whole model — roster age, pick capital, and the firsts you
              have moved. It still does not read your record or your starting lineup.
              You have the final say below.
            </ChalkText>
          ) : (
            <ChalkText style={styles.fine}>
              That is the whole model — roster age and pick capital. It does not read
              your record, your starting lineup, or which picks you have already traded
              away, so a young team going all-in reads as rebuilding here. You have the
              final say below.
            </ChalkText>
          )}
          {fromOdds ? (
            <ChalkText style={styles.fine}>
              Your playoff odds outrank this arithmetic while the season is running —
              the numbers above are what roster shape alone says.
            </ChalkText>
          ) : null}
        </View>
      ) : null}

      <ChalkText style={styles.dim}>Is that right? This steers every trade we show you.</ChalkText>
      <View style={styles.chips}>
        {w.options.map((o) => (
          <Pressable
            key={o}
            testID={`team-review.outlook.${o}`}
            onPress={() => onSelect(o)}
            style={[styles.chip, selected === o && styles.chipSel]}
          >
            <ChalkText style={[styles.chipText, selected === o && styles.chipTextSel]}>
              {OUTLOOK_LABEL[o]}
            </ChalkText>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function Depth({
  data, acquire, shed, onAcquire, onShed,
}: {
  data: TeamReviewResponse;
  acquire: string[]; shed: string[];
  onAcquire: (v: string[]) => void; onShed: (v: string[]) => void;
}) {
  const d = data.depth;
  const toggle = (list: string[], v: string) =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
  return (
    <View testID="team-review.beat.depth">
      <Bubble pose="computing">Two studs and a hole isn&apos;t a starting lineup.</Bubble>

      <View style={styles.card}>
        <ChalkText style={styles.kicker}>Startable bodies by position</ChalkText>
        {CORE.map((pos) => {
          const t = d.tier_depth[pos] || { elite: 0, starter: 0, bench: 0 };
          const thin = d.position_needs.includes(pos);
          const deep = d.position_surplus.includes(pos);
          // #366 — the third layer the report asked for. `replacement` is an
          // ALIAS the backend adds when `trade.position_tiers` is on; `bench`
          // is what every build before it sent and is never omitted. Reading
          // `replacement ?? bench` is what makes this screen render correctly
          // against BOTH backends, which is the point of shipping the alias.
          const replacement = t.replacement ?? t.bench ?? 0;
          return (
            <View key={pos} style={styles.line}>
              <ChalkText style={styles.lineLabel}>{pos}</ChalkText>
              <ChalkText style={styles.lineVal}>
                {t.elite || 0} Elite · {t.starter || 0} Starter · {replacement} Replacement
              </ChalkText>
              <ChalkText
                style={[
                  styles.tag,
                  thin && { color: semantic.warn },
                  deep && { color: semantic.pos },
                ]}
              >
                {thin ? 'thin' : deep ? 'deep' : 'ok'}
              </ChalkText>
            </View>
          );
        })}
        {/* #366 — the RB handcuff count, from Sleeper's own depth chart.
            Rendered on PRESENCE of the key, never `?? 0`: an absent key means
            the read was not performed (flag off), which is a different claim
            from "you own none" and must not print as one. The copy states the
            fact the field carries — RB2 on an NFL depth chart — and makes no
            usage or value claim, because a committee back can hold order 2. */}
        {d.handcuff_rb !== undefined ? (
          <ChalkText style={styles.dim} testID="team-review.depth.handcuff">
            {d.handcuff_rb === 0
              ? 'No handcuffs — none of your RBs is the RB2 on his NFL depth chart.'
              : `${d.handcuff_rb} handcuff${d.handcuff_rb === 1 ? '' : 's'} — ${
                  d.handcuff_rb === 1 ? 'one of' : `${d.handcuff_rb} of`
                } your RBs ${d.handcuff_rb === 1 ? 'is' : 'are'} the RB2 on his NFL depth chart.`}
          </ChalkText>
        ) : null}
      </View>

      {d.weakest_slot ? (
        <View style={styles.card}>
          <ChalkText style={styles.kicker}>Your weakest starting slot</ChalkText>
          <ChalkText style={styles.read}>
            {d.weakest_slot.slot} — {d.weakest_slot.name}
          </ChalkText>
        </View>
      ) : null}

      <ChalkText style={styles.dim}>Chase</ChalkText>
      <View style={styles.chips}>
        {CORE.map((p) => (
          <Pressable
            key={p}
            testID={`team-review.chase.${p}`}
            onPress={() => onAcquire(toggle(acquire, p))}
            style={[styles.chip, acquire.includes(p) && styles.chipSel]}
          >
            <ChalkText style={[styles.chipText, acquire.includes(p) && styles.chipTextSel]}>
              {p}
            </ChalkText>
          </Pressable>
        ))}
      </View>

      <ChalkText style={styles.dim}>Shop</ChalkText>
      <View style={styles.chips}>
        {CORE.map((p) => (
          <Pressable
            key={p}
            testID={`team-review.shop.${p}`}
            onPress={() => onShed(toggle(shed, p))}
            style={[styles.chip, shed.includes(p) && styles.chipSel]}
          >
            <ChalkText style={[styles.chipText, shed.includes(p) && styles.chipTextSel]}>
              {p}
            </ChalkText>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function Divergence({ data }: { data: TeamReviewResponse }) {
  const d = data.divergence;
  return (
    <View testID="team-review.beat.divergence">
      <Bubble pose="point">
        Your board disagrees with the market. That&apos;s where trades come from.
      </Bubble>

      {/* #367 — SELLS FIRST, and each list says what it is for. This shipped
          crossed: the buy list sat under "Skip these". You sell the players
          the market rates ABOVE your board, and buy the ones it rates below. */}
      <View style={styles.card}>
        <ChalkText style={styles.kicker}>Sell — you&apos;re lower than the market</ChalkText>
        {d.lower_than_market.length === 0 ? (
          <ChalkText style={styles.dim}>Nothing stands out yet.</ChalkText>
        ) : d.lower_than_market.map((r) => (
          <View key={r.player_id} style={styles.line}>
            <ChalkText style={styles.lineLabel}>{r.position}</ChalkText>
            <ChalkText style={styles.lineVal}>{r.name}</ChalkText>
            <ChalkText style={[styles.tag, { color: semantic.pos }]}>
              +{Math.round(r.gap)}
            </ChalkText>
          </View>
        ))}
        <ChalkText style={styles.fine}>
          Yours, and the market likes them more than you do — someone pays you
          more than you think they&apos;re worth.
        </ChalkText>
      </View>

      <View style={styles.card}>
        <ChalkText style={styles.kicker}>Buy — you&apos;re higher than the market</ChalkText>
        {d.higher_than_market.length === 0 ? (
          <ChalkText style={styles.dim}>Nothing stands out yet.</ChalkText>
        ) : d.higher_than_market.map((r) => (
          <View key={r.player_id} style={styles.line}>
            <ChalkText style={styles.lineLabel}>{r.position}</ChalkText>
            <ChalkText style={styles.lineVal}>{r.name}</ChalkText>
            <ChalkText style={[styles.tag, { color: semantic.pos }]}>
              +{Math.round(r.gap)}
            </ChalkText>
          </View>
        ))}
        <ChalkText style={styles.fine}>
          Not yours, and their owner rates them below you — you&apos;d be paying
          less than you think they&apos;re worth.
        </ChalkText>
      </View>

      <ChalkText style={styles.fine}>
        {d.source === 'league_community'
          ? `Compared against ${d.baseline_user_count} ranked leaguemates.`
          : 'Compared against the consensus market board.'}
      </ChalkText>
    </View>
  );
}

function Partners({
  data, onScope,
}: {
  data: TeamReviewResponse;
  onScope: (id: string, name: string) => void;
}) {
  const p = data.partners;
  // #374 — "Still unclear what 'pointed the other way' means". It was a phrase
  // the beat never defined: the user has to hold their OWN window in their head
  // and infer the complement. Name both sides instead, in the user's own terms.
  const mine = data.window.declared ?? data.window.inferred;
  const youContend = mine === 'contender' || mine === 'championship';
  const youRebuild = mine === 'rebuilder' || mine === 'jets';
  const heading = youContend
    ? 'Rebuilding teams — they want picks, you want players'
    : youRebuild
      ? 'Contending teams — they want players, you want picks'
      : 'Teams pointed the other way from you';
  return (
    <View testID="team-review.beat.partners">
      <Bubble pose="neutral">
        {youContend
          ? "You're going for it. The teams who aren't are your best partners."
          : youRebuild
            ? "You're building. The teams going for it are your best partners."
            : 'Trades happen between teams that want different things.'}
      </Bubble>

      <View style={styles.card}>
        <ChalkText style={styles.kicker}>{heading}</ChalkText>
        {p.opposed_window.length === 0 ? (
          <ChalkText style={styles.dim}>Nobody obvious right now.</ChalkText>
        ) : p.opposed_window.map((m) => (
          <Pressable
            key={m.user_id}
            testID="team-review.action.partner_scoped"
            style={styles.line}
            onPress={() => onScope(m.user_id, m.username)}
          >
            <ChalkText style={styles.lineVal}>{m.username}</ChalkText>
            <ChalkText style={styles.tag}>
              {m.value_rank ? `#${m.value_rank}` : ''} · {m.first_round_picks} firsts
            </ChalkText>
          </Pressable>
        ))}
        <ChalkText style={styles.fine}>
          {youContend
            ? 'These teams are building for later, so this year\u2019s production is worth less to them than it is to you \u2014 and their picks are worth less to you than they are to them. That gap is the trade.'
            : youRebuild
              ? 'These teams are trying to win now, so their picks are worth less to them than they are to you \u2014 and your veterans are worth more to them than they are to you. That gap is the trade.'
              : 'When two teams want different things, each can give up what it values less. That gap is the trade.'}
          {' Tap a team to point the finder at them.'}
        </ChalkText>
      </View>

      {p.fills_your_need.length > 0 ? (
        <View style={styles.card}>
          <ChalkText style={styles.kicker}>Deep where you&apos;re thin</ChalkText>
          {p.fills_your_need.map((m) => (
            <View key={`${m.user_id}-${m.position}`} style={styles.line}>
              <ChalkText style={styles.lineVal}>{m.username}</ChalkText>
              <ChalkText style={styles.tag}>
                {m.startable_count} startable {m.position}
              </ChalkText>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

// #369 — THE PLAN BEAT IS A STANDING SUMMARY, NOT A SESSION RECEIPT (D-130).
//
// Operator: *"The plan summary page only shows window.. it's a good page intent
// but needs more detail. I think we just show the full set of adjustments a
// user can make with the trade finder."*
//
// The old version rendered `outlook` only if `done.current.has('outlook_set')`,
// positions only if `positions_set`, and the scoped partner — i.e. only what
// the user changed in THIS mount. Skip a beat and it showed nothing for it, and
// `positions_set` could never be true at all (see the savePrefs comment). So
// the page is rebuilt around a different question: every lever the trade finder
// exposes, and where you stand on each, read from the SAVED preferences rather
// than session-local React state.
//
// WHAT IS EDITABLE HERE, AND WHY NOT EVERYTHING (D-131). The three
// `league_preferences` levers — outlook, chasing, shopping — are edited in
// place, through the SAME `saveLeaguePreferences` path the flow already writes
// with (no new route, autosave per tap, exactly the #236 contract Trade DNA
// uses). Everything else is shown with its home named: the asset lists would
// need a second `asset_preferences` writer beside the deck's own toggles, and
// fairness / trade idea / focus / pinned players live in TradesScreen's own
// state, which cannot be written across a navigation boundary without
// inventing a shared store. Naming the lever and where it lives answers the
// operator's ask; duplicating four controls to do it does not.
//
// Levers 9 and 10 (trade idea, focus) are `TradesScreen` useState and reset on
// every deck mount, so this beat states where they live rather than claiming a
// current value it cannot read. That honesty is deliberate — a fabricated
// "None" would read as a setting.
function Plan({
  data, leagueId, scoped, onSave, saving,
}: {
  data: TeamReviewResponse;
  leagueId: string;
  scoped: { id: string; name: string } | null;
  onSave: (patch: Record<string, unknown>, action: string) => Promise<boolean>;
  saving: boolean;
}) {
  const qc = useQueryClient();
  // Read-only flag consumption, so a lever that is dark is never advertised.
  const listsOn = useFlag('trade.preference_lists');
  const intentOn = useFlag('trades.intent_modes');
  const pinnedGive = useFinderTargets((s) => s.pinnedGive);
  const pinnedReceive = useFinderTargets((s) => s.pinnedReceive);

  // SOURCE OF TRUTH. The saved preferences, re-read on entry to this beat —
  // NOT `data.depth.acquire_positions` (a 60s-stale snapshot taken at screen
  // mount, before this session's own writes) and not the session refs. Same
  // query key TradeDnaSheet uses, so the two surfaces share one cache entry
  // and one invalidation. `refetchOnMount: 'always'` is the whole point: "where
  // you stand" must mean now.
  const prefsQ = useQuery({
    queryKey: ['league-prefs', leagueId],
    queryFn: () => getLeaguePreferences(leagueId),
    enabled: !!leagueId,
    staleTime: 0,
    refetchOnMount: 'always',
  });
  const assetsQ = useQuery({
    queryKey: ['asset-prefs', leagueId],
    queryFn: () => getAssetPrefs(leagueId),
    enabled: !!leagueId && listsOn,
    staleTime: 60_000,
  });

  // Device-local, so it is readable from here without touching the deck.
  const [fairnessOn, setFairnessOn] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    AsyncStorage.getItem(FAIRNESS_PREF_KEY)
      .then((raw) => { if (alive) setFairnessOn(fairnessOnFromPref(raw)); })
      .catch(() => { if (alive) setFairnessOn(fairnessOnFromPref(null)); });
    return () => { alive = false; };
  }, []);

  const saved = prefsQ.data;
  const [draft, setDraft] = useState<{
    outlook: OutlookOption; acquire: string[]; shed: string[];
  } | null>(null);
  useEffect(() => {
    if (!saved) return;
    setDraft({
      outlook: saved.team_outlook ?? data.window.declared ?? data.window.inferred,
      acquire: saved.acquire_positions ?? [],
      shed: saved.trade_away_positions ?? [],
    });
  }, [saved, data]);

  const [failed, setFailed] = useState(false);

  // Every tap posts the FULL triple — last-write-wins, the same autosave shape
  // the Trade DNA sheet uses (#236). Sending all three is also what makes a
  // positions edit safe: the body can never be missing `team_outlook`.
  const commit = async (
    next: { outlook: OutlookOption; acquire: string[]; shed: string[] },
    action: string,
  ) => {
    setDraft(next);
    const ok = await onSave({
      team_outlook: next.outlook,
      acquire_positions: next.acquire,
      trade_away_positions: next.shed,
    }, action);
    setFailed(!ok);
    if (ok) qc.invalidateQueries({ queryKey: ['league-prefs', leagueId] });
  };

  const toggle = (list: string[], v: string) =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v];

  const assets = assetsQ.data;
  const pinned = pinnedGive.length + pinnedReceive.length;

  return (
    <View testID="team-review.beat.plan">
      <Bubble pose="celebrate">
        Here&apos;s every dial the finder has, and where you stand on each.
      </Bubble>

      <View style={styles.card} testID="team-review.plan.levers">
        <ChalkText style={styles.kicker}>What the finder uses · change any of it here</ChalkText>

        {!draft ? (
          <ChalkText style={styles.dim}>Reading your saved settings…</ChalkText>
        ) : (
          <>
            <ChalkText style={styles.planLbl}>Window</ChalkText>
            <View style={styles.chips}>
              {data.window.options.map((o) => (
                <Pressable
                  key={o}
                  testID={`team-review.plan.outlook.${o}`}
                  disabled={saving}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: draft.outlook === o }}
                  accessibilityLabel={OUTLOOK_LABEL[o]}
                  onPress={() => commit({ ...draft, outlook: o }, 'outlook_set')}
                  style={[styles.chip, draft.outlook === o && styles.chipSel]}
                >
                  <ChalkText
                    style={[styles.chipText, draft.outlook === o && styles.chipTextSel]}
                  >
                    {OUTLOOK_LABEL[o]}
                  </ChalkText>
                </Pressable>
              ))}
            </View>

            <ChalkText style={styles.planLbl}>Chasing · want more of</ChalkText>
            <View style={styles.chips}>
              {PLAN_POSITIONS.map((p) => (
                <Pressable
                  key={p}
                  testID={`team-review.plan.chase.${p}`}
                  disabled={saving}
                  accessibilityRole="button"
                  accessibilityState={{ selected: draft.acquire.includes(p) }}
                  accessibilityLabel={`Chase ${PLAN_POS_LABEL[p]}`}
                  onPress={() => commit(
                    { ...draft, acquire: toggle(draft.acquire, p) }, 'positions_set',
                  )}
                  style={[styles.chip, draft.acquire.includes(p) && styles.chipSel]}
                >
                  <ChalkText
                    style={[styles.chipText, draft.acquire.includes(p) && styles.chipTextSel]}
                  >
                    {PLAN_POS_LABEL[p]}
                  </ChalkText>
                </Pressable>
              ))}
            </View>

            <ChalkText style={styles.planLbl}>Shopping · happy to move</ChalkText>
            <View style={styles.chips}>
              {PLAN_POSITIONS.map((p) => (
                <Pressable
                  key={p}
                  testID={`team-review.plan.shop.${p}`}
                  disabled={saving}
                  accessibilityRole="button"
                  accessibilityState={{ selected: draft.shed.includes(p) }}
                  accessibilityLabel={`Shop ${PLAN_POS_LABEL[p]}`}
                  onPress={() => commit(
                    { ...draft, shed: toggle(draft.shed, p) }, 'positions_set',
                  )}
                  style={[styles.chip, draft.shed.includes(p) && styles.chipSel]}
                >
                  <ChalkText
                    style={[styles.chipText, draft.shed.includes(p) && styles.chipTextSel]}
                  >
                    {PLAN_POS_LABEL[p]}
                  </ChalkText>
                </Pressable>
              ))}
            </View>

            {failed ? (
              <ChalkText style={styles.planErr} testID="team-review.plan.save-error">
                That didn&apos;t save. Tap it again — your other settings are untouched.
              </ChalkText>
            ) : null}
          </>
        )}
      </View>

      {listsOn ? (
        <View style={styles.card} testID="team-review.plan.assets">
          <ChalkText style={styles.kicker}>Player rules</ChalkText>
          <Row
            label="Never trade away"
            value={countLabel(assets?.untouchables?.length, 'player')}
          />
          <Row
            label="Targeting"
            value={countLabel(assets?.targets?.length, 'player')}
          />
          <Row
            label="Not interested in"
            value={countLabel(assets?.not_interested?.length, 'player')}
          />
          <ChalkText style={styles.fine}>
            Set these on a player in the deck — tap a name on any trade card.
          </ChalkText>
        </View>
      ) : null}

      <View style={styles.card} testID="team-review.plan.search">
        <ChalkText style={styles.kicker}>This search</ChalkText>
        <Row
          label="Trade with"
          value={scoped ? scoped.name : 'Anyone in the league'}
          accent={!!scoped}
        />
        <Row
          label="Trade fairness"
          value={fairnessOn === null
            ? '—'
            : fairnessOn ? 'Balanced trades' : 'Ranked by mismatch'}
        />
        {intentOn ? (
          <Row label="Trade idea" value="Consolidate · tier up · tier down" />
        ) : null}
        <Row label="Focus" value="Team-fit or value moves" />
        <Row
          label="Specific players"
          value={pinned ? `${pinned} pinned` : 'None pinned'}
          accent={pinned > 0}
        />
        <ChalkText style={styles.fine}>
          Fairness sticks on this device. The rest of this card is set on the
          deck and starts fresh each time you open it — everything above is
          saved for this league.
        </ChalkText>
      </View>
    </View>
  );
}

// A count we have not loaded yet is an em-dash, never a fabricated zero — the
// same rule the standing beat applies to a missing PPG.
function countLabel(n: number | undefined, noun: string) {
  if (n === undefined) return '—';
  if (n === 0) return 'None';
  return `${n} ${noun}${n === 1 ? '' : 's'}`;
}

function Row({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <View style={styles.line}>
      <ChalkText style={styles.lineVal}>{label}</ChalkText>
      <ChalkText style={[styles.tag, accent && { color: ice.base }]}>{value}</ChalkText>
    </View>
  );
}

function ordinal(n: number) {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

const styles = StyleSheet.create({
  wrap: { flex: 1, backgroundColor: ink.ink0 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.xl },
  progress: { flexDirection: 'row', gap: 3, paddingHorizontal: space.lg, paddingTop: space.sm },
  tick: { flex: 1, height: 2, backgroundColor: ink.ink3, borderRadius: radii.xs },
  tickOn: { backgroundColor: ice.base },
  tickDone: { backgroundColor: ink.lineStrongA11y },
  body: { padding: space.lg, gap: space.md, paddingBottom: space.xxl },

  bubbleRow: { flexDirection: 'row', gap: space.sm, alignItems: 'flex-start' },
  bubble: {
    flex: 1, backgroundColor: ink.ink2, borderWidth: 1, borderColor: ink.line,
    borderRadius: radii.md, padding: space.md,
  },
  bubbleText: { ...type.body, color: chalk.base },

  card: {
    backgroundColor: ink.ink1, borderWidth: 1, borderColor: ink.line,
    borderRadius: radii.md, padding: space.md, gap: space.xs,
  },
  kicker: { ...type.label, color: chalk.dim, letterSpacing: 1, textTransform: 'uppercase' },
  headline: { fontFamily: fonts.displayBold, fontSize: 24, color: chalk.base, textTransform: 'uppercase' },
  statRow: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
  big: { fontFamily: fonts.displayBold, fontSize: 38, color: chalk.base },
  of: { ...type.body, color: chalk.dim },
  read: { ...type.body, color: chalk.base },
  dim: { ...type.bodySm, color: chalk.dim },
  fine: { ...type.bodySm, color: chalk.faint },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  ribbon: {
    ...type.label, color: semantic.warn, borderWidth: 1, borderColor: semantic.warn,
    borderRadius: radii.xs, paddingHorizontal: 5, paddingVertical: 1,
  },
  band: { fontFamily: fonts.displayBold, fontSize: 22, textTransform: 'uppercase' },

  line: {
    flexDirection: 'row', alignItems: 'center', gap: space.sm,
    paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: ink.line,
  },
  lineLabel: { ...type.bodySm, color: chalk.faint, width: 34 },
  lineVal: { ...type.bodySm, color: chalk.base, flex: 1 },
  tag: { ...type.bodySm, color: chalk.dim },

  // #369 plan beat — a lever's own label, above its chip row. `dim` reads as
  // body copy next to a card kicker; this is a control label, so it takes the
  // label type without the kicker's uppercase (the kicker stays the one
  // all-caps line per card).
  planLbl: { ...type.label, color: chalk.dim, marginTop: space.xs },
  planErr: { ...type.bodySm, color: semantic.neg },

  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    borderWidth: 1, borderColor: ink.lineStrongA11y, borderRadius: radii.sm,
    paddingHorizontal: 10, paddingVertical: 6,
  },
  chipSel: { borderColor: ice.base, backgroundColor: 'rgba(86,217,236,0.08)' },
  chipText: { ...type.bodySm, color: chalk.dim },
  chipTextSel: { color: ice.base },

  footer: { padding: space.lg, gap: space.sm, borderTopWidth: 1, borderTopColor: ink.line },
  cta: { backgroundColor: ice.base, borderRadius: radii.sm, paddingVertical: 12, alignItems: 'center' },
  ctaText: { ...type.body, color: ice.on, fontFamily: fonts.uiBold },
  skip: { alignItems: 'center', paddingVertical: 8 },
  skipText: { ...type.bodySm, color: chalk.dim },
});

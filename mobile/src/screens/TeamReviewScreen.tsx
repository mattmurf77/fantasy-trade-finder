import React, { useCallback, useMemo, useRef, useState } from 'react';
import {
  View, ScrollView, Pressable, ActivityIndicator, StyleSheet,
} from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useNavigation } from '@react-navigation/native';

import ChalkText from '../components/chalkline/Text';
import { AnalystAvatar } from '../components/analyst';
import { ink, chalk, ice, semantic, space, radii, type, fonts } from '../theme/chalkline';
import { useSession } from '../state/useSession';
import { track } from '../api/events';
import { saveLeaguePreferences } from '../api/league';
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

  const savePrefs = useCallback(async (
    patch: Record<string, unknown>, action: string,
  ) => {
    if (!leagueId) return;
    setSaving(true);
    try {
      await saveLeaguePreferences(leagueId, patch as any);
      done.current.add(action);
      emit('team_review_action_taken', { beat, action });
      // The shared adoption receipt — deliberately the SAME event the guide and
      // the Trade DNA sheet fire, with a `review` source, so this surface joins
      // the existing series instead of splitting it.
      if (action === 'outlook_set') emit('outlook_saved', { source: 'review' });
    } catch {
      // A failed write surfaces nothing and emits NO action event — the flow
      // continues rather than trapping the user on a beat.
    } finally {
      setSaving(false);
    }
  }, [leagueId, beat, emit]);

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
            outlook={done.current.has('outlook_set') ? declared : null}
            acquire={done.current.has('positions_set') ? acquire : []}
            shed={done.current.has('positions_set') ? shed : []}
            scoped={scoped}
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
        <ChalkText style={styles.kicker}>Your window · inferred from roster shape</ChalkText>
        <ChalkText style={styles.headline}>{OUTLOOK_LABEL[w.inferred]}</ChalkText>
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
          <Row label="Total score" value={signed(w.signals.score)} accent />
          <ChalkText style={styles.fine}>
            {`Contending at ${signed(m.contender_cut)} or above, rebuilding at `}
            {`${signed(m.rebuilder_cut)} or below, anything between is "not sure".`}
          </ChalkText>
          <ChalkText style={styles.fine}>
            That is the whole model — roster age and pick capital. It does not read
            your record, your starting lineup, or which picks you have already traded
            away, so a young team going all-in reads as rebuilding here. You have the
            final say below.
          </ChalkText>
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
          const startable = (t.elite || 0) + (t.starter || 0);
          const thin = d.position_needs.includes(pos);
          const deep = d.position_surplus.includes(pos);
          return (
            <View key={pos} style={styles.line}>
              <ChalkText style={styles.lineLabel}>{pos}</ChalkText>
              <ChalkText style={styles.lineVal}>
                {t.elite || 0} elite · {t.starter || 0} starter
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
  return (
    <View testID="team-review.beat.partners">
      <Bubble pose="neutral">Deal with the teams pointed the other way.</Bubble>

      <View style={styles.card}>
        <ChalkText style={styles.kicker}>Pointed the other way</ChalkText>
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

function Plan({
  outlook, acquire, shed, scoped,
}: {
  outlook: OutlookOption | null;
  acquire: string[]; shed: string[];
  scoped: { id: string; name: string } | null;
}) {
  const nothing = !outlook && !acquire.length && !shed.length && !scoped;
  return (
    <View testID="team-review.beat.plan">
      <Bubble pose="celebrate">
        {nothing
          ? "No changes — your deck stays as it was."
          : "Here's the plan. I've already pointed the finder at it."}
      </Bubble>
      <View style={styles.card}>
        <ChalkText style={styles.kicker}>Your plan</ChalkText>
        {outlook ? <Row label="Window" value={OUTLOOK_LABEL[outlook]} accent /> : null}
        {acquire.length ? <Row label="Chasing" value={acquire.join(', ')} accent /> : null}
        {shed.length ? <Row label="Shopping" value={shed.join(', ')} accent /> : null}
        {scoped ? <Row label="Scoped to" value={scoped.name} accent /> : null}
        {nothing ? (
          <ChalkText style={styles.dim}>You skipped every step — that&apos;s fine.</ChalkText>
        ) : null}
      </View>
      <ChalkText style={styles.fine}>
        You can change any of this later in Trade DNA.
      </ChalkText>
    </View>
  );
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

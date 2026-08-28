# Trade model — data readout (Phase 2), 2026-08-27

> **Purpose:** what presented trades already tell us, measured from a fresh read-only prod mirror.
> Every number here is **measured** unless labeled otherwise. Per-cut power labels: **POWERED** =
> 95% CI half-width ≤ 5 pp; **weak** = ≤ 10 pp; **anecdote** = wider. The ±5%/95% read needs ~385
> outcomes per cell; most cells are below that — treat "weak"/"anecdote" rows as direction, not
> magnitude. Companion docs: [current-state.md](current-state.md),
> [hypothesis-results.md](hypothesis-results.md).

## Contents

- [Provenance](#provenance)
- [Data seams — do not trend across these](#data-seams--do-not-trend-across-these)
- [Funnel](#funnel)
- [Like-rate cuts (served deck cards)](#like-rate-cuts-served-deck-cards)
- [Bake-off arm reads](#bake-off-arm-reads)
- [Guardrail metrics](#guardrail-metrics)
- [Value freshness and churn (H4 inputs)](#value-freshness-and-churn-h4-inputs)
- [Power appendix](#power-appendix)

## Provenance

**measured.** Production Postgres (`DATABASE_URL_PROD`, Render) accessed read-only on 2026-08-27
(mirror completed ~01:50 UTC 2026-08-28) via the SELECT-copy-to-local-SQLite method of
[deck-eval-report-2026-08-15.md](../onboarding-conversion/deck-eval-report-2026-08-15.md)
§Data provenance — `backend.database`'s metadata with `DATABASE_URL` pointed at the local mirror
before import; `backend.server` never imported; prod received SELECTs only. Script:
`mirror_prod.py` (session scratchpad; method reproducible from the deck-eval report).

Row counts, vs the 2026-08-15 copy: `trade_impressions` **18,830** (was 7,664) ·
`deck_impressions` **16,675** (4,965) · `swipe_decisions` **5,693** (2,513) · `trade_decisions`
**1,452** (544) · `deck_outcomes` **1,454** · `user_events` **34,181** (8,600) · `bad_trade_flags`
**18** (5) · `trade_matches` 15 · `sleeper_trades` 565 · `suggestion_trade_links` 131 ·
`model_config` 234. The dataset roughly tripled in 12 days.

## Data seams — do not trend across these

| Date | Seam |
|---|---|
| 2026-07-27 | Deck spine begins: `deck_impressions`/`deck_outcomes`/`features_json` start here; earlier funnel rows live only in `trade_impressions`/`trade_decisions` |
| 2026-08-17T22:30Z | `pass_cooldown_start_epoch` amnesty — decline semantics change |
| 2026-08-19 → 21 | Bake-off starts dark (arm labels appear); **2026-08-21T00:43Z interleaved serving ON** (`bakeoff_serve_interleaved` 0→1, deck limit 30→60, group quotas off) |
| 2026-08-21 | 1QB QB compression hand-tuned twice (`qb_1qb_cap_elo` 1785→1644→1717, knee →1200) |
| 2026-08-24T04:22Z | D-159 knob bundle: `filler_min_frac` →0.15, `trade_elo_gap_max` →0, `v3_shape_max_delta` →2, **`overpay_adjusted` →0** — card mix changes |
| 2026-08-25 | Quick Set `via` seam (v1.16.6/EAS 132) — analytics only, but noted per NEXT.md |

## Funnel

**measured**, all-time unless noted:

| Leg | n | Notes |
|---|---|---|
| Deck cards logged (non-ghost, since 07-27) | 16,131 | Includes interleave-period cards from all rostered arms |
| … of which fronted/acted (`deck_outcomes`) | 1,454 | **Only 3.7% of logged cards ever get a decision** (596 like/pass with features; 723 viewed-only events, 95 cards viewed-only net) |
| Deck like / pass | 187 / 530 | like-rate 26.1% raw; 31.4% over decided cards with features |
| All-surface like / pass (`trade_decisions`, since 2026-04) | 501 / 951 | Aug: 293/670 (30.4% like) |
| Matches | 15 | 3 accepted · 2 declined · 10 pending |
| `trade_proposed` events | 462 | Emitted on like decisions (≈ likes), not on real proposals |
| Real proposals sent (`trade_sent`) | 2 | |
| Real league trades synced (`sleeper_trades`) | 565 | Whole-league history, most predating the app |
| Real trades matching an app suggestion (`suggestion_trade_links.was_recommended`) | **1 of 131** scanned (match_type `partial`) | Aug 2026: 11 real trades in synced leagues, 1 partial match |

**The operator's field report stands**: likes → matches → accepts is a trickle (15 matches, 3
accepts, ever), and the off-app conversation channel is invisible here. The "discussed?" proxy the
plan mentions remains a candidate feature; nothing in the data substitutes for it today. The
end-to-end "our suggestion became a real trade" read is 1 partial match — at this volume the
funnel's bottom is unmeasurable, which is itself the §11 round-2 finding (~385 outcomes needed;
match-level outcomes are at n=15).

## Like-rate cuts (served deck cards)

Base: 596 non-ghost deck cards with `features_json` and a like/pass outcome (2026-07-27 →
2026-08-28). Overall **187/596 = 31.4% [27.8–35.2] POWERED**.

### Basis (H7 core)

| Cut | Like-rate |
|---|---|
| consensus | 127/367 = **34.6%** [29.9–39.6] POWERED |
| divergence | 60/229 = **26.2%** [20.9–32.3] weak |
| consensus, interleave period only (≥08-21) | 37/86 = 43.0% [33.1–53.6] anecdote |
| divergence, interleave period only | 37/92 = 40.2% [30.8–50.4] anecdote |

Per-user (every user with both cuts, all periods): u…598400 consensus 21.1% vs divergence **9.1%**;
u…169408 34.1% vs 31.5%; u…370624 61.3% vs 48.5%. **Direction is consistent: no user likes
divergence cards more than consensus cards.** Confound: basis correlates with partner
(boarded vs not) and package mix; the interleave-period read is near parity. Verdict in
[hypothesis-results.md](hypothesis-results.md) §H7.

### Package shape

| Cut | Like-rate |
|---|---|
| 1:1 | 121/328 = 36.9% [31.8–42.2] weak |
| consolidate 2→1 (user gives 2) | 21/62 = 33.9% [23.3–46.3] anecdote |
| consolidate 3→1 | 5/11 = 45.5% anecdote |
| balanced multi (2:2, 3:3) | 18/80 = 22.5% [14.7–32.8] weak |
| expand (user gets more back) | 10/56 = 17.9% [10.0–29.8] weak |
| 3:1-family decided post-08-24 unlock | 0/5 — no read yet |

Post-unlock shape mix (all served cards ≥08-24, n=4,576): 1x1 60.7%, 3x1 4.6%, 4x1 1.0% — the
unlock is producing 3:1 supply, but almost none has been acted on yet.

### Picks (H1)

| Cut | Like-rate |
|---|---|
| player-only | 95/245 = **38.8%** [32.9–45.0] weak |
| any pick | 73/286 = 25.5% [20.8–30.9] weak |
| pick:premium attr | 63/233 = 27.0% weak |
| pick:mid attr | 10/53 = 18.9% anecdote |
| **user GIVES far-year 1st (2027+), no pick back** | **7/75 = 9.3%** [4.6–18.0] weak |
| user receives far-year 1st, no pick given | 25/69 = 36.2% [25.9–48.0] anecdote |
| user gives current-year 1st | 12/33 = 36.4% anecdote |
| user receives current-year 1st | 10/26 = 38.5% anecdote |
| far-1st both ways | 4/22 = 18.2% anecdote |

The give-far-first CI upper bound (18.0%) sits below the player-only lower bound (32.9%): despite
cell sizes, **"give a far-year 1st" cards are genuinely the worst-performing pick cut**, echoing the
D-084-era measurement (1st-on-give 15.6% vs 1st-on-receive 47.1%).

### Age (H3)

| Receive-side headliner age | Like-rate | Give-side age | Like-rate |
|---|---|---|---|
| u23 | 22/46 = **47.8%** anecdote | u23 | 15/80 = 18.8% weak |
| 23–26 | 96/303 = 31.7% weak | 23–26 | 97/302 = 32.1% weak |
| 27–29 | 23/117 = 19.7% weak | 27–29 | 34/82 = 41.5% anecdote |
| 30+ | 6/40 = **15.0%** anecdote | 30+ | 30/74 = **40.5%** anecdote |

Monotone both ways: users like receiving youth and like shipping vets. The *users* are
youth-biased; the engine (no age input, see current-state) is not.

### Position / tier / format (H5)

| Cut | Like-rate |
|---|---|
| centerpiece WR / RB / PICK | 33.7% / 35.2% / 36.6% (n=193/193/101) weak |
| centerpiece TE | 13/64 = 20.3% weak |
| **centerpiece QB** | **4/45 = 8.9%** [3.5–20.7] weak |
| league format `sf_tep` (4 leagues by `leagues.default_scoring`) | 21/128 = **16.4%** [11.0–23.8] weak |
| other leagues (incl. the biggest, format unrecorded in `leagues`) | 166/468 = 35.5% POWERED |
| receive band elite / high / mid / low | 40.4% / 28.9% / 27.0% / 31.4% |

Caveats: `leagues.default_scoring` is NULL for most Sleeper leagues (format is detected at runtime,
not persisted), and `bad_trade_flags` shows the biggest league flagged under both formats at
different times — the format cut is league-cluster-confounded. QB-centerpiece n=45 spans both
formats (12.5% in unlabeled leagues, 4.8% in sf_tep).

### Fit / lane / likes-you (H6)

| Cut | Like-rate |
|---|---|
| lane value / window | 32.4% [28.1–37.1] POWERED / 30.0% weak |
| need_fit ≥0.6 / 0.3–0.6 | 30.7% / 31.4% — **flat** |
| likes_you true / false | 25.5% anecdote / 31.9% POWERED |

Need-fit and window alignment do not separate like-rates at current n — the fit machinery is not
visibly buying acceptance on the deck surface.

### Per-league / per-user

Biggest league 34.0% [29.6–38.6] POWERED (n=430); others 15.7%/52.6%/14.3% (n=89/38/35). Users:
16.5% / 33.3% / 55.5% / 13.6% (n=230/189/146/22). **User identity is the strongest single
correlate in the data** — any cut not controlled for user is confounded (3 users = 95% of
decided cards).

## Bake-off arm reads

Arm labels exist since ~08-19; **only the interleave window (≥08-21) is a fair comparison** — arm
`current`'s earlier decided cards were dark-mode (sole served arm, different period). Two config
regimes inside the window (seam 08-24):

| Arm | 08-21→08-24 | ≥08-24 | Interleave total |
|---|---|---|---|
| current | 4/11 | 11/21 | 15/32 = 46.9% anecdote |
| challenger | 21/46 | 12/28 | 33/74 = 44.6% anecdote |
| gen_v2 | 18/34 | 1/13 | 19/47 = 40.4% anecdote |

**No arm separates at these n** (pairwise CIs fully overlap). A ±5 pp read per arm needs ~385
decided per arm; the window accrued ~153 across all three in ~7 days ⇒ **≈5–7 weeks per arm at
current traffic** for a powered read. Note gen_v2's collapse post-08-24 (1/13) is exactly when the
shape unlock let it serve more consolidation cards — watch, don't conclude.

**Offline per-arm profiles** (ALL logged cards during the bake-off, served or not — this is what
each engine *wants* to show):

| Metric | current (n=4,634) | challenger (n=2,775) | gen_v2 (n=1,403) |
|---|---|---|---|
| 1:1 share | 77.4% | 64.8% | **3.6%** |
| consolidation (give>receive) | 10.9% | 10.5% | **58.2%** |
| pick-bearing | 44.5% | 36.4% | **58.2%** |
| **give-far-1st share** | 10.3% | 13.8% | **46.4%** |
| QB-centerpiece | 5.6% | 6.5% | 4.1% |
| divergence-basis | 21.3% | 33.5% | 100% |
| fairness median / p10 | 0.840 / 0.653 | 0.886 / 0.764 | 0.906 / 0.859 |
| first-5 I1 insult (floor 500, raw rule) | 5.37% (n=857) | 7.98% (n=326) | 6.15% (n=179) |

gen_v2's profile is radically different: it concentrates on exactly the card type the users
measurably hate (give-far-1st, 9.3% like-rate cut above) at 4.5× the incumbent's rate.

## Guardrail metrics

**Empty-deck rate** (`trades_generated.props.count == 0`, the serving-path measure): overall
32/655 = **4.89%**; 2026-07: 3.96%; 2026-08: **5.05%** — sitting exactly on the 5% gate. Decks
under 5 cards: 12.8% of generations. (`bakeoff_runs.deck_size` shows 0 empties in 265 runs at
median 33 cards — the emptiness is concentrated in non-bakeoff jobs: targeted/finder decks, which
bypass the bake-off.)

**Insult rate** (2026-08-15 report's rule: Δ = consensus receive − give on the card as stamped;
I1 = Δ<0, |Δ|/give ≥ 20%; I2 = star-for-scraps; materiality floor |Δ| ≥ 500; applied to SERVED
non-ghost first-5 cards, n=2,732):

| Population | floor 0 | floor 250 | floor 500 |
|---|---|---|---|
| All served first-5 | 4.90% | 4.36% | **4.03%** |
| **consensus-basis only** (the population the 08-15 rule was designed for) | — | — | **1.48% (25/1,693) — PASS, identical to the 08-15 offline run's 1.48%** |
| divergence-basis only | — | — | **8.18% (85/1,039)** |

I2 fired zero times on evaluable cards. Reading this honestly: the comparable guardrail
(consensus-basis, where consensus IS what the viewer is shown) is stable and passing. The 8.18%
divergence number is the same arithmetic applied where its premise breaks — a divergence card can be
deliberately consensus-negative for the viewer because their own board says they win. It is NOT a
pass: it quantifies H8's exposure ("KTC-fair weaponization" — the *counterparty* anchors on
consensus, and these cards ask the viewer to accept a ≥20%+≥500 consensus haircut on faith in their
own board). It needs its own rule, not this one. See
[hypothesis-results.md](hypothesis-results.md) §H8.

## Value freshness and churn (H4 inputs)

`player_value_history` snapshots: daily and unbroken 2026-07-27 → 2026-08-28 (one 17-day gap
before 07-27 = pre-spine). Day-over-day mean |Δ%| of the top-200 1qb consensus values: **median
1.14%**; the two biggest single days are **our own recalibrations, not market news** — 14.3% on
07-27 (spine restart) and 8.2% on 08-22 (the #313 QB-compression / blend-tuning session). Values
refresh at most ~daily (20 h TTL + daily tick; code-verified in current-state §Value inputs), and a
failed DP fetch silently serves yesterday's pool. So: the incumbent tools' "knee-jerk volatility"
gripe does not reproduce here — our risk runs the other way (staleness ≤ 24 h + deploy-driven
jumps), and the §11 "freshness moat" is not yet built.

## Power appendix

Cells at n≈385 decided reach ±5 pp at p≈0.3. Today's largest cells: overall (596), consensus-basis
(367), biggest league (430), lane-value (407). Everything else is direction-only. Decided-card
accrual is ~25–30/day at current traffic; doubling the powered-cut count is a ~3-week wait, and a
per-arm powered interleave read is ~5–7 weeks. All cuts here are impression-weighted with
per-impression outcomes; 3 users contribute 95% of decisions, so nothing in this readout
generalizes beyond this tester population.

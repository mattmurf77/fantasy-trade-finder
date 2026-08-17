# G6 plan — Trade presentment rules (#304, #336, #339, #340, #341)

> Planner deliverable for the 2026-08-16 wave, group G6 (heaviest). Backend
> feature path. Base: `origin/main` @ `d3fe3ac` (v1.13.4). All file:line
> citations are against that sha. Binding operator decisions are in
> [batch-plan.md](batch-plan.md) § G6 and are restated inline where they bind.

**The decision in one paragraph.** Five presentment rules, two layers. Part 1
(construction: overpay ceiling #340, per-position net cap #341, pick-is-the-gap
#339) and the #304 need gate run *inside* the candidate generators, so killed
candidates are replaced from the enumeration rather than leaving holes in the
deck. Part 2's #336 (already-matched / awaiting exclusion) is a presentment-time
dedup against DB state. Measured against the 2026-08-15 production deck-eval
corpus (540 first-5 cards, 108 first-run decks, 9 production leagues), the
combined rules would kill **18.4%** of currently served organic first-5 cards —
including **all 8** of the D-055 insult-rule cards — with a worst-case first-5
wipeout of 5/108 decks (4.6%, under the D-055 <5% empty-deck bar even before
the refill effect is counted). Everything is knob-disable-able; one new feature
flag reverts the whole group.

---

## 1. Pipeline map (where a trade card comes from)

Generation entry: `/api/trades/generate` → background worker
`_run_trade_job` (`backend/server.py:4776`). Worker steps in order:

| Step | Site | Notes |
|---|---|---|
| Session/service resolve, real member boards injected | `server.py:4789-4836` | `member.has_rankings` decides divergence vs consensus path |
| User outlook: declared pref, else inferred | `server.py:4838-4857` (`_infer_user_outlook`, flag `trade.outlook_seed`) | values: `championship\|contender\|not_sure\|rebuilder\|jets` |
| Opponent outlooks + pick shares | `server.py:4870-4896` (flag `trade.outlook_infer`) | |
| Asset pref lists (untouchable/target/not-interested) | `server.py:4902-4912` (flag `trade.preference_lists`) | existing hard-filter precedent for new gates |
| Owned-pick injection as `PICK` pseudo-assets | `server.py:4928-4945` → `_inject_owned_picks` (`server.py:9452`), guard `_owned_picks_available` (`server.py:9335`), cap `picks_pool_cap` (default 6) | picks flow through the same generators — Part 1 covers them natively |
| **`TradeService.generate_trades`** | `backend/trade_service.py:2286` → `_generate_trades_impl:2296` → v2 orchestrator `_generate_trades_v2:2957` | |
| — per-pair divergence gen (v3 ON in prod) | `backend/trade_optimizer.py:193` `generate_pair_trades_v3`; v2 fallback `trade_service.py:3367` `_generate_for_pair_v2` | `config/features.json`: `trade_engine.v3: true` |
| — consensus fallback gen (unranked members + zero-divergence fallback) | `trade_service.py:3791` `_generate_consensus_for_pair`; fallback wiring `:3206-3209` (flag `trade.divergence_fallback`) | |
| — post-gen reorder stack (fit, need_fit `w=0.15`, block boost, #175 outlook direction, lanes, aggression) | `trade_service.py:3210-3346`; `need_fit` blend at `:3228-3238` | all bounded multipliers, none gate — this is the "light multiplier" posture #304 supersedes *for presentment* |
| — dedup + past-decision filter + sort | `trade_service.py:2492` `_dedup_and_sort` (also feeds streaming snapshots `:3354`) | past keys = 7-day window, `server.py:15227` — see #336 root cause |
| — relaxed fallback for empty *targeted* jobs | `trade_service.py:2509` `_relaxed_targeted_pass` (never relaxes #108 gates — `:2522-2525`) | |
| — intent filter (#172) | `trade_service.py:2404` `_filter_by_trade_intent:2220` | post-gen filter precedent |
| Exploration split (F7) | `server.py:4995-5009` | |
| **likes-you injection** | `server.py:5016-5026` → `_inject_likes_you_cards_impl` (`server.py:2872`); D-055 floor `likes_you_min_user_delta=-500` at `:2968` | **stays UNfiltered by quality rules per Q21**; floor precedent for "kill the insult, keep the surface" |

Gates already inside each generator (order as executed), v3 shown; v2
`_consider` (`trade_service.py:3568`) and consensus `_emit`
(`trade_service.py:3881`) mirror them:

1. pinned give/receive (`trade_optimizer.py:497-506`)
2. `abs(len(g)-len(r)) <= 1` (`:507`) — shapes are 1-3 × 1-3
3. `_positions_ok` acquire/away prefs (`:509`)
4. `_gap_ok` Elo-gap (`:511`, knob `trade_elo_gap_max`)
5. #108 `fit_premium_1for1` user-board 1-for-1 gate (`:519`, exception knob `fit_premium_max_loss=300`)
6. #227 `pick_swap_ok` (`:526`)
7. #141 `filler_ok` junk-filler (`:531`, knob `filler_min_frac=0.25`)
8. 3.2 lineup feasibility (`:533`)
9. both-sides surplus ≥ `min_side_surplus_marginal=60` (`:537`)
10. consensus fairness with range overlap, floored at
    `fairness_floor_divergence=0.55` for divergence cards
    (`trade_optimizer.py:276-277`, `trade_service.py:3436-3437`); consensus
    cards keep the caller's threshold plus `user_gain_epsilon` +
    `consolidation_raw_loss_frac` (`trade_service.py:3903-3915`)
11. v3 sweetener rescue of near-misses (`trade_optimizer.py:609-640`,
    `_try_sweeten:645`) — players only, never picks (`:240-242`)

**"Fairness OFF" plumbing:** the mobile toggle maps to
`fairness_threshold = 0.5` (`mobile/src/api/tradePregen.ts:25-26`,
`TradesScreen.tsx:812`); server default 0.75 (`server.py:9911-9912`). For
divergence cards the effective gate is `min(threshold, 0.55)` regardless — so
today, with fairness ON or OFF, a divergence card may carry up to a 45%
package-value gap. That is #340's mechanism (measured: all Part-1 kills in the
corpus are `basis=divergence`).

---

## 2. Rule spec

One new feature flag gates the whole group: **`trade.presentment_rules`**
(config/features.json, ship ON — this is a bug-fix wave; the flag is the
instant group-wide revert). Each rule additionally has its own model_config
kill switch so tuning never needs a deploy. Flag OFF ⇒ every path
byte-identical to today.

### Part 1 — construction rules (is this package sane?)

Hook points (all four rules, identical predicates, evaluated on **raw summed
consensus values** — `seed_value(pid)` per side, the same units as the D-055
insult Δ and the `likes_you_min_user_delta` floor, deliberately NOT the
depth-discounted `package_value_v2` numbers):

- v3: in the enumeration loop with gates 5-7, **before** the near-miss
  collection at `trade_optimizer.py:543-546` so the sweetener pass cannot
  rescue a killed shape (mirror of the #227 comment at `:523-525`), AND
  re-validated on the sweetened combo inside the sweetener pass (a sweetener
  changes both position nets and the gap) — pass a predicate into
  `_try_sweeten` like `filler_ok_fn` (`trade_optimizer.py:626`).
- v2: in `_consider` after `filler_ok` (`trade_service.py:3599`).
- consensus: in `_emit` with the #108/#227/#141 gates
  (`trade_service.py:3899-3927`).
- relaxed pass: inherits automatically (it re-runs `_generate_trades_v2`);
  add Part 1 + R5 to the **never-relaxed** list in the docstring at
  `trade_service.py:2522-2525`. These are safety properties like #108.
- Out of scope: likes-you injection (Q21), asset-ideas
  (`trade_service.py:2571` — a different, user-pinned surface), the manual
  calculator, and eveners (`server.py:992-1004` — eveners add to the
  *lighter* side by construction, so they cannot create the #339 shape).

**R1 — #340 max-overpay ceiling.** Let `g = Σ seed_value(give)`,
`r = Σ seed_value(receive)` (players + picks), `gap = |g − r|`.

> KILL when `gap ≥ max_overpay_min_value` AND `gap / max(g, r) ≥ max_overpay_frac`.

- Applies to **both sides** (measured: 37 of 42 corpus violations are the
  *opponent* overpaying — those are the "horrid" cards; a trade no human would
  accept is noise even when the user wins it).
- Enforced unconditionally — it never reads `fairness_threshold`, so the
  client's fairness toggle cannot relax it (the operator's "even with trade
  fairness turned off").
- Keys: `max_overpay_frac` (default **0.25**; ≤0 disables),
  `max_overpay_min_value` (default **500.0**, the D-055 materiality floor).
  0.25 was chosen against the corpus sweep (§4): 0.20 kills 14-18% (too hot
  vs consolidations), 0.35 leaves the 25-35% band of D-055's I1 insult rule
  (≥20% haircut) alive. 0.25 kills 8.9% and covers every corpus insult card.
- Coexistence: `fit_premium_max_loss=300 < 500` — the flagged need-fill
  exception can never trip R1. `consolidation_raw_loss_frac=0.15` (consensus
  path, user side only) is tighter but narrower; keep both.

**R2 — #341 per-position net cap.** For each position
`P ∈ {QB, RB, WR, TE}`: `net_P = |receive at P| − |give at P|`, counting
players only (`position == "PICK"` excluded — a pick is not a positional
body; picks are #339's domain).

> KILL when any `|net_P| > pos_net_cap`.

- Key: `pos_net_cap` (default **1.0**; 0 disables, following the
  `filler_min_frac` convention).
- Semantics check against the operator's words: "give 2 RBs, get 2 WRs" →
  net RB −2 → killed. "Give 2 RBs unless getting 1 back" → net −1 → passes.
  Every 1-for-1 passes trivially (nets are −1/0/+1).

**R3 — #339 pick-is-the-gap.** For candidates containing ≥1 pick asset
(`is_pick_asset`, `trade_service.py:998`; injected `PICK` pseudo-assets,
`server.py:9425`): let H be the heavier side (larger raw consensus sum),
`gap` as in R1.

> KILL when `gap ≥ pick_gap_min_value` AND some pick `p ∈ H` has
> `seed_value(p) ≥ pick_gap_frac × gap`.

- Reading: the overpaying side is shipping a pick that single-handedly
  explains (≥80% of) the excess — exactly "the side giving up more is giving
  up a mid 1st more". The correct construction was the same trade without
  the pick, and the enumerator *does* generate that sibling (subset shapes
  are enumerated independently), so killing this shape loses nothing.
- Keys: `pick_gap_frac` (default **0.8**; 0 disables), `pick_gap_min_value`
  (default **300.0** — below `fit_premium_max_loss` would gut legitimate
  pick-sweetened near-fair trades; 300 ≈ a late-3rd, the smallest pick that
  reads as "a pick" rather than a rounding error).
- **Defaults are judgment, not measurement** — the corpus contains zero
  first-5 cards with picks (0/540; itself a finding: pick cards rarely crack
  the top of a first-run deck). Ship behind the knobs, then tune with the
  build-phase pick-league replay (§4, limitation L3). Per the 2026-08-10
  lesson these two defaults are flagged as unmeasured; the alternative
  (block until a pick corpus exists) leaves #339 unfixed this wave.

### Part 2 — eligibility rules (worth showing this user?)

**R4 — #336 matched/awaiting hard exclusion.**

*Root cause (measured in code):* generation dedup uses
`past_decision_keys` loaded with **`since_days=7`**
(`server.py:15227`, second site `:16438`; consumed at
`trade_service.py:2497-2502`). A trade the user liked more than 7 days ago —
still sitting in Awaiting, or already a mutual match — falls out of the
window and legitimately regenerates. The key also carries no partner and no
match-state awareness.

*Spec:* build a windowless exclusion-key set at job start in
`_run_trade_job` (with the pref loads, `server.py:4898-4912`):

- **Awaiting:** `load_awaiting_trades(user_id)` (`backend/database.py:7058`)
  — already excludes `retracted_at` rows (#318, so a retracted like may
  legitimately reappear) and already subtracts matured matches; filter to
  this `league_id`; key each row `(frozenset(my_give), frozenset(my_receive))`.
- **Matches:** `trade_matches` rows (`backend/database.py:406`) for this
  user + league with `status IN ('pending', 'accepted')`, keyed from the
  user's orientation (`user_a_give`/`user_a_receive`, mirrored for user_b).
  `declined` rows do NOT block — the existing 7-day past-decision filter
  covers the immediate re-show, and a market-rejected trade regenerating
  weeks later is defensible (flagged as open question Q-G6-2).

Thread the set into `generate_trades` as a new kwarg and apply it in
`_dedup_and_sort` (`trade_service.py:2492`) alongside `_past_decision_keys`,
so streaming snapshots (`:3354`) honor it too. Exact set-match only in v1;
a fuzzy layer (per-side Jaccard ≥ `fuzzy_match_tau=0.8`, the 2.3b machinery)
is a noted follow-up, not this wave.

Also apply the same exclusion set in `_inject_likes_you_cards_impl` next to
its `past_decision_keys` skip (`server.py:2958`): re-injecting an
already-matched trade as a likes-you card at deck position 1 IS #336.
**Interpretation note:** Q21 exempts likes-you from the *quality* rules
(Part 1 + R5); R4 is duplicate-state dedup, which the injector already
practices — extending it is the bug fix, not new filtering. Surfaced for
operator confirmation (Q-G6-1) but planned in by default.

No new knob (the group flag reverts it); no schema change (reads existing
tables).

**R5 — #304 positional-need gate, window-scaled.**

Window resolution reuses the existing state verbatim: declared
`league_preferences.team_outlook`, else inferred (`server.py:4838-4857`,
flags `trade.outlook_seed` / `trade.outlook_infer`; engine-side inference
`infer_team_outlook`, `trade_service.py:1688`).

Need machinery reused verbatim: `analyze_roster_strengths`
(`trade_service.py:1057` — bodies-vs-slots `position_needs` /
`position_surplus` from `_STARTER_NEED` / `_SURPLUS_AT`, SF-aware) and
starter slots `_starters_at` (`trade_service.py:1248`).

Predicate — evaluated on the card's **primary received asset** only (highest
consensus value, players only; picks-primary cards exempt; secondary pieces
are #141's domain — killing on any piece would gut 2-for-1s):

Let P = primary's position, `v` its consensus value, `S = _starters_at(P)`,
`user_P` = user's consensus values at P sorted desc, `incumbent` = `user_P[S-1]`
(the worst current starter at P) when `len(user_P) ≥ S`.

- `v < need_gate_min_value` (default **500.0**) → PASS (sub-floor churn is
  not the headline; D-055 materiality precedent).
- P fills a hole: `len(user_P) < S`, i.e. P ∈ `position_needs` territory → PASS.
- Lineup upgrade: `v > incumbent × (1 + need_gate_upgrade_margin)`
  (default margin **0.0** — any strict starter upgrade) → PASS.
- Otherwise, by window:
  - `championship` / `contender` → **KILL**. (The operator's Loveland case:
    TE3 offered, McBride TE2 rostered, S=1 → no hole, no upgrade → killed.)
  - `not_sure` → KILL only if additionally P ∈ `position_surplus`
    (half-strength: the gate only fires where the roster is demonstrably
    stacked at P).
  - `rebuilder` / `jets` / no resolvable window → PASS (gate off — the
    operator: rebuilders accumulate value, needs matter less).

Hooked at construction time in the same four sites as Part 1 (the
generators already receive `user_needs` — extend that plumbing:
`trade_service.py:3093-3094`, `trade_optimizer.py:217`), so killed
candidates refill from the heap instead of thinning the deck. Q19 honored:
`need_fit_weight=0.15` reorder underneath is untouched.

Keys: `need_gate_min_value` (default 500.0; ≤0 disables the whole gate),
`need_gate_upgrade_margin` (default 0.0).

---

## 3. Interaction analysis

| Interaction | Analysis |
|---|---|
| Rules × fairness-OFF (threshold 0.5) | R1 reads raw sums, never the threshold — the ceiling binds identically ON/OFF. Divergence floor 0.55 currently makes ON≈OFF for divergence cards anyway; R1 at 0.25 becomes the operative bound on both. |
| Rules × #189 relaxed pass | Relaxed stages loosen fairness band + surplus floor only (`trade_service.py:2536-2545`); Part 1 + R5 ride the generators and are **never relaxed** (documented in the same never-relaxed block as #108). Net effect: targeted jobs may go honestly empty slightly more often — the #172/#189 honest-empty-state precedent covers the UX. |
| Rules × sweetener (v3 3.4) | Gates run before near-miss collection (can't rescue a killed shape) AND re-run on the sweetened result (a sweetener shifts `net_P` and `gap`). Sweeteners are players-only, so R3 can't be triggered *by* a sweetener. |
| Rules × window (#175 / lanes / D-060) | R5 uses the same resolved outlook object; no second resolution path (D-060's rejected-alternative lesson). The #175 directional *multiplier* still reorders beneath the gate — penalty vs filter now layered, not conflicting. |
| Rules × likes-you (Q21) | Part 1 + R5 skip injection entirely (injector runs after `generate_trades`, `server.py:5016-5026` — no code change needed to skip). R4 extends the injector's existing dedup (§2, Q-G6-1). D-055 floor remains the injection's only quality gate. |
| Rules × picks-in-pool | Picks enter as roster pseudo-assets and hit Part 1 naturally. R2 ignores picks; R3 only fires on picks. Pick-eveners (calculator) are out of scope and structurally can't violate R3. |
| Rules × intent modes (#172) | Intent filter stays post-gen (`trade_service.py:2404`); an intent deck already gated to sane shapes just gets smaller — same honest-empty toast. |
| R4 × #318 retract | Retracted likes are excluded from `load_awaiting_trades` at source (`database.py:7091`), so a retracted trade may regenerate — consistent with #318's documented "legitimately reappears" semantics. |
| G4 (offer prefill, auto-run) | Consumes deck output client-side; no payload change (§5) ⇒ no contract impact. G4's pinned/opponent-scoped jobs skip likes-you injection already; Part 1 + R5 apply to them like any targeted job, with #189 relax as the safety valve. Build order (batch-plan): G6 lands first. |

## 4. Measured kill rates

**Corpus:** `feedback-workspace/deck-eval/deck_eval_20260815T220047Z.json` —
the D-055 gate run: 108 first-run decks across the 9 production Sleeper
leagues (production Postgres mirror), 540 recorded first-5 cards, of which
474 organic (66 likes-you injections excluded per Q21). Same artifact and
same value units the deck-quality bars were ratified on. Method: replayed
each proposed predicate over the per-card records (positions, ages, raw
consensus values, package values, `need_fit`, outlook per deck).

| Rule (at proposed defaults) | Kill rate (organic first-5) |
|---|---|
| R1 #340 @ frac 0.25, floor 500 | **42/474 = 8.9%** (sweep: 0.20→14-18%, 0.30→7.2%, 0.35→6.1%) |
| R2 #341 @ net cap 1 | **37/474 = 7.8%** (only multi-asset shapes; 420/540 corpus cards are 1-for-1 and pass trivially) |
| R3 #339 | **not measurable** — 0/540 corpus cards contain a pick (L3) |
| R4 #336 | **not measurable on this corpus** — first-run sims have no like/match history by construction; kill rate is per-user duplicate state, not deck quality |
| R5 #304 (proxy, L2) | **25/474 = 5.3%** overall; within contender decks 14.8%, not_sure 8.9%, rebuilder 0% (62/108 corpus decks are rebuilders) |
| **Combined P1 (R1∪R2)** | **64/474 = 13.5%** (overlap 15) |
| **Combined P1+R5** | **87/474 = 18.4%** |

**The headline numbers:** combined kill **18.4%** of currently served organic
first-5 cards; **8/8** of the corpus's D-055 primary-rule insult cards are
covered (killed by R1/R2 or already dead to the ratified likes-you floor);
every R1/R2 kill is a `basis=divergence` card — consensus cards are already
gated by `user_gain_epsilon` + 0.75 fairness.

**Empty-deck risk vs the D-055 <5% bar:** worst case, treating the recorded
first-5 as the whole deck: 5/108 decks (4.6%) lose all recorded organic
cards — under the bar even under this deliberately pessimistic reading. Two
strong mitigating structures: (1) Part 1 + R5 run at construction, so the
per-pair top-K refills from candidates that today lose the heap race to
killed cards — served-card kill rate strictly overstates deck shrinkage;
(2) decks are ~30 cards and all 5 worst-case decks retain their likes-you
cards. Residual risk and its tripwire are in §6.

**Limitations (stated per the 2026-08-10 measured-thresholds lesson):**
- **L1** — first-5 only: the JSON records 5 of ~30 cards per deck. First-5 is
  the D-055 scoring surface and the top of the composite order, where
  divergence (R1-prone) cards concentrate; deck-wide rates are likely lower.
- **L2** — R5 measured by proxy (`need_fit < 0.45` on contender/not_sure
  decks), because the corpus lacks rosters and the exact incumbent-value
  predicate needs them. The proxy brackets the same anti-fit population; the
  build phase must add exact R5 counters to `scripts/deck_eval.py` and re-run
  (one flag-off run = the pre-ship measurement, see §7).
- **L3** — R3 defaults unmeasured (no pick cards in corpus). Build phase runs
  the deck-eval against at least one pick-synced league with
  `picks_in_pool` active before tuning `pick_gap_frac`.

## 5. API / payload changes

**None.** No new request params; card dict shape unchanged
(`trade_card_to_dict`, `server.py:9743+`). Deck size may shrink; the
existing empty/no-fair-trades states cover it. Docs rows: `docs/api-reference.md`
gets a behavior note on `/api/trades/generate` (new gates + flag);
`docs/config-reference.md` gets the 7 new keys + flag;
`docs/cross-client-invariants.md` n/a (no shared enums/colors);
`docs/data-dictionary.md` n/a (no schema change); `living-memory/LLD.md`
convention note (construction-gate vs presentment-filter layering);
DECISIONS.md entry for the filter-not-reorder supersession of the 2026-07-17
interview posture.

## 6. Risks

- **Empty/thin decks (G-046/G-047-class compounding — the compressed-board
  incident family):** the 2026-08-15 field bug taught that stacked silent
  filters can zero a pair. Mitigations: construction-time hooks (refill), the
  divergence→consensus fallback stays beneath the rules, likes-you unfiltered,
  and a **tripwire**: log per-job `presentment_killed` counts; if a job's
  post-rule deck < 5 cards where pre-rule > 15, log at WARNING with rule
  attribution. Re-run deck-eval flag-ON before ship; bar: empty-deck < 5%.
- **R3/R5 defaults partially unmeasured** (L2/L3): shipped as knobs; deck-eval
  re-run is the tuning loop, not a deploy.
- **Contender decks thin most** (14.8% R5 kill): acceptable per the operator's
  explicit intent (#304 is a contender complaint); watch the tripwire on
  contender-heavy leagues.
- **R4 partner-orientation bugs** (user_a/user_b mirroring): covered by
  dedicated orientation tests (§7); `load_awaiting_trades`' 500-row bounds
  keep the exclusion set cheap.
- **Concurrent-wave conflict:** G6 owns the three backend engine files this
  wave (batch-plan build order); G4's backend param touches the generate
  route request surface — coordinate the `server.py` merge (disjoint
  functions, same file).

## 7. File ownership (G6 — backend only; G4 consumes deck output client-side)

- `backend/trade_service.py` — R1/R2/R3/R5 predicates (one shared module-level
  fn each), `_consider` + `_emit` hooks, `_dedup_and_sort` exclusion kwarg,
  never-relaxed docstring.
- `backend/trade_optimizer.py` — v3 loop + sweetener re-validation hooks.
- `backend/server.py` — R4 exclusion-set build in `_run_trade_job`, likes-you
  injector R4 hook, tripwire logging.
- `backend/database.py` — 7 model_config seeds (no schema change).
- `config/features.json` — `trade.presentment_rules`.
- `backend/tests/test_presentment_rules.py` (new), plus touched fixtures.
- `scripts/deck_eval.py` — R-rule counters (measurement, not product).
- Docs: `docs/api-reference.md`, `docs/config-reference.md`,
  `living-memory/LLD.md`, `living-memory/DECISIONS.md`, this folder's
  `status.md`.

## 8. Test plan (per D-056 — no Maestro; pytest + code-walk + operator checklist)

**Unit (pytest, every behavioral test proven-to-fail on sabotage** — e.g.
invert the predicate or zero the knob in a fixture override and assert the
test catches it before landing it):

- R1: both-sides kill (user-overpay and opponent-overpay fixtures); gap just
  under floor passes; frac boundary; `fairness_threshold=0.5` (OFF) still
  kills; knob ≤0 restores byte-identical decks; fit-premium card (loss 300)
  survives.
- R2: 2RB-for-2WR killed; 2RB-for-1RB+1WR passes; picks don't count; cap 0
  disables; sweetened card re-checked (sabotage: skip the re-check, assert a
  sweetener-created violation is caught).
- R3: pick ≥ 0.8×gap on heavier side killed; same pick on lighter side
  passes; pick-for-pick already dead via #227; sub-`pick_gap_min_value` gap
  passes.
- R5: the Loveland fixture (TE-primary, incumbent better, contender → killed;
  same card, rebuilder → served; not_sure + no surplus → served; not_sure +
  surplus → killed); hole-filling receive passes; strict-upgrade passes;
  sub-500 primary passes; pick-primary exempt; declared-beats-inferred window.
- R4: >7-day-old awaiting like excluded (the root-cause regression test);
  pending and accepted matches excluded in both user_a/user_b orientations;
  declined and retracted regenerate; likes-you injector refuses an
  already-matched mirror; exclusion visible in streaming snapshots.
- Flag OFF: full-pipeline byte-identity test (existing
  `test_user_gain_gate.py` pattern of flipping config and asserting the same
  card surfaces).

**Two-sided distributional bars (deck-eval re-run, flag ON vs OFF, same
leagues):** empty-deck < 5% (D-055 bar) AND mean deck size ≥ 80% of flag-OFF;
insult rate ≤ flag-OFF run's (must not rise); R1∪R2 served-card violation
rate == 0 flag-ON (one-sided) while flag-OFF baseline reproduces ±2pp of §4
(guards against measuring a changed corpus).

**Code-walk proof (D-056):** file:line trace that every generator path
(v3 organic, v3 sweetened, v2, consensus, relaxed, likes-you) passes through
its stated gate set, committed to this folder.

**Operator TestFlight checklist:** (1) generate on your main league with
fairness OFF — confirm no card shows a >25% one-sided value gap in the value
bar; (2) confirm no 2-same-position-for-none package anywhere in a full deck
swipe; (3) contender league: confirm no card whose headline acquisition sits
behind your current starter at that position; rebuild league: confirm value
plays still appear; (4) like a trade, wait for the deck to regenerate (or
pull-to-refresh next day) — confirm it does not reappear; open Matches and
confirm no deck card duplicates a pending match; (5) if any league has synced
picks: confirm no offer where the *other* side's extra value is exactly a
1st they're dumping.

## 9. Open questions

- **Q-G6-1:** confirm R4 applies to likes-you injection (planned default:
  yes — it's dedup, not quality filtering; Q21 read as exempting quality
  rules only).
- **Q-G6-2:** should `declined` matches also hard-exclude (planned default:
  no — 7-day dedup covers the immediate window)?
- **Q-G6-3:** `trade.presentment_rules` ship-state ON (planned default) vs a
  staged flip after one TestFlight pass.

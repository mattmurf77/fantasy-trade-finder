# LLD delta — Trade presentment rules (G6: #304, #336, #339, #340, #341)

> Author-round deliverable, 2026-08-16 wave. Exact interfaces for the build
> agents. **All file:line cites verified against `origin/main @ 0b2dcee`**
> (the current tip build branches fork from — 6 commits past the Planner's
> `d3fe3ac` base; drifts from the plan's cites are footnoted in §7). Units:
> "raw consensus value" = `seed_value(pid)` summed per side — the D-055 Δ
> currency.

## 1. Feature flag

**`trade.presentment_rules`** — gates R1/R2/R3/R5 hooks, the R4 exclusion
set, and the tripwire. OFF ⇒ every path byte-identical to today (R-8 in the
PRD; enforced by a byte-identity test).

Registration (three touch points, all backend — this flag has **no client
surface**, so `mobile/src/state/useFeatureFlags.ts` `LAUNCHED_FLAG_DEFAULTS`
is *not* touched):

| Site | Change |
|---|---|
| `backend/feature_flags.py` `FLAG_KEYS` (line 47) | add `"trade.presentment_rules"` with a comment block naming this folder |
| `backend/feature_flags.py` `DEFAULT_FLAGS` (line 718) | nothing — it derives `False` for every key |
| `config/features.json` | `"trade.presentment_rules": true` — **launches ON** (recommendation + rollout step in prd.md § For the operator; final call is Q-G6-3) |

Read as `FLAGS.trade_presentment_rules` (dot→underscore convention, e.g.
`FLAGS.trade_fit_premium` at `trade_service.py:3094`).

Revert levers, fastest first: (a) any single rule → `PUT
/api/admin/config/<knob>` with its disable value, deploy-free, live; (b) whole
group → flip the JSON key to `false`, one-line commit + Render deploy.

## 2. model_config knobs (7 new keys)

All added to `_MODEL_CONFIG_DEFAULTS` in `backend/trade_service.py` (the
`_cfg` dict, near `fairness_floor_divergence` at `:154`) **and** DB-seeded in
`backend/database.py` (`INSERT OR IGNORE` seed block, `database.py:2286`
pattern) so every one is live-tunable without a deploy. All documented in
`docs/config-reference.md` at build.

| Key | Default | Disable | Rule |
|---|---|---|---|
| `max_overpay_frac` | `0.25` | `≤ 0` | R1 #340 |
| `max_overpay_min_value` | `500.0` | — (floor; D-055 materiality) | R1 |
| `pos_net_cap` | `1.0` | `0` (follows `filler_min_frac` convention) | R2 #341 |
| `pick_gap_frac` | `0.8` | `0` | R3 #339 |
| `pick_gap_min_value` | `300.0` | — (floor) | R3 |
| `need_gate_min_value` | `500.0` | `≤ 0` disables the whole gate | R5 #304 |
| `need_gate_upgrade_margin` | `0.0` | — (0 = any strict upgrade passes) | R5 |

R3's two defaults are **unmeasured** (zero pick cards in the corpus) —
flagged per the 2026-08-10 measured-thresholds lesson; tuning is a named
build-phase task (prd.md R-12), not a silent gap. R1's 0.25 comes from the
corpus sweep (0.20 → 14–18% kill, too hot; 0.35 leaves D-055's 25–35% insult
band alive; 0.25 → 8.9% and covers every corpus insult card).

## 3. Predicates and insertion points

### Shared predicate module

One module-level function per rule in `backend/trade_service.py`, alongside
`filler_ok`/`pick_swap_ok` (so `trade_optimizer.py` imports them the same way
it imports those — see its existing `filler_ok` usage at
`trade_optimizer.py:626`). Common inputs: `give_ids`, `recv_ids`,
`seed_value` (consensus), `players` dict. Let `g = Σ seed_value(give)`,
`r = Σ seed_value(receive)` (players **and** picks), `gap = |g − r|`.

**R1 — `overpay_ok(give_ids, recv_ids, seed_value)` (#340)**

```
KILL when gap ≥ max_overpay_min_value
     AND gap / max(g, r) ≥ max_overpay_frac
```
- Both sides (37/42 corpus violations are the *opponent* overpaying — those
  are the "horrid" cards; a trade no human accepts is noise even when the
  user wins it).
- **Never reads `fairness_threshold`** — the mobile fairness toggle
  (`mobile/src/api/tradePregen.ts:25-27`: ON = 0.75, OFF = 0.5) cannot relax
  it; today's divergence floor `min(threshold, 0.55)`
  (`trade_optimizer.py:277`, `trade_service.py:3436-3437`, default at
  `trade_service.py:154`) is what lets a 45% gap through — R1 becomes the
  operative absolute bound on both settings.
- Coexistence check (verified): `fit_premium_max_loss = 300 < 500` — a
  flagged need-fill exception card can never trip R1;
  `consolidation_raw_loss_frac` (consensus path, `trade_service.py:3911-3915`)
  is tighter but user-side/consolidation-only — both stay.

**R2 — `pos_net_ok(give_ids, recv_ids, players)` (#341)**

```
for P in {QB, RB, WR, TE}:  net_P = count(recv at P) − count(give at P)
KILL when any |net_P| > pos_net_cap
```
- `net_P` is **one signed quantity per position** (not a per-side count):
  2RB→2RB is net 0 and passes. Players only: `position == "PICK"`
  pseudo-assets excluded (a pick is not a positional body; picks are R3's
  domain). Injected picks carry position `"PICK"` (`_inject_owned_picks`,
  `server.py:9452`). Positions outside {QB, RB, WR, TE} (K/DEF/IDP in exotic
  leagues) are uncounted by design.
- Semantics (operator's words): 2RB→2WR kills (net RB = −2); "give 2 RBs
  unless getting 1 back" passes (net −1); every 1-for-1 passes trivially.

**R3 — `pick_gap_ok(give_ids, recv_ids, seed_value, players)` (#339)**

Only evaluated when the package contains ≥1 pick (`is_pick_asset`,
`trade_service.py:998`). H = heavier side by raw consensus sum.

```
KILL when gap ≥ pick_gap_min_value
     AND ∃ pick p ∈ H with
         pick_gap_frac × gap ≤ seed_value(p) ≤ gap / pick_gap_frac
```
- **Two-sided band** (round-1 B1): the pick must *be* the gap — within the
  band of it in both directions — not merely exceed 80% of it. The one-sided
  form killed fair pick-centerpiece consolidations (gap 300, mid-1st 3,000:
  3,000 ≥ 240 → killed one-sided; passes the band since 3,000 > 375) — the
  operator's own stud-scaled consolidation style (2026-07-17 interview).
  The #339 shape still dies: heavier by exactly one mid-1st (gap 3,000,
  pick 3,000) sits inside [2,400, 3,750]. Same knob, no new key.
- Reading: the overpaying side is shipping a pick that single-handedly
  explains its excess. The enumerators generate the pick-less sibling shape
  independently, so the kill loses nothing.
- One-sidedness re-audit of the other predicates (round-1 B1 follow-up):
  R1 is a pure ceiling on `gap/max(g,r)` — no upper-bound counterpart exists
  (a *small* relative gap is simply fair); R2 uses `|net_P|`, symmetric by
  construction. Neither has the B1 bug class.

**R5 — `need_gate_ok(recv_ids, *, seed_value, players, user_pos_values, outlook, position_needs, position_surplus, scoring_format)` (#304)**

Evaluated on the **primary received asset** only (highest consensus value,
players only; pick-primary cards exempt; secondary pieces are #141's domain).
**Applies only to untargeted discovery decks** — see the bypass predicate
below. P = primary's position, `v` its consensus value, `S = _starters_at(P,
scoring_format)` (`trade_service.py:1248`), `user_P` = consensus values at P
over the **post-give roster** — `roster − give_ids` — sorted desc,
`incumbent = user_P[S−1]` when `len(user_P) ≥ S`. The post-give subtraction
(round-1 B2) is load-bearing: computed on the full pre-trade roster, a
contender's tier-down at a stacked position (give McBride, receive Loveland
+ 2nd) compares Loveland against the very starter leaving in the trade and
kills a legitimate consolidation — emptying `tier_down` intent decks
wholesale, since R5 runs before the post-gen intent filter
(`trade_service.py:2404`).

```
PASS when v < need_gate_min_value                      (sub-floor churn)
PASS when len(user_P) < S                              (P fills a hole)
PASS when v > incumbent × (1 + need_gate_upgrade_margin)   (starter upgrade)
otherwise, by resolved window:
  championship | contender      → KILL
  not_sure                      → KILL only if P ∈ position_surplus
  rebuilder | jets | unresolved → PASS  (gate off)
```
Window/needs inputs are the **already-resolved** objects — declared
`league_preferences.team_outlook` else inferred (`server.py:4838-4857`
region, flags `trade.outlook_seed`/`trade.outlook_infer`; engine-side
`infer_team_outlook`, `trade_service.py:1688`) — and
`analyze_roster_strengths` output (`trade_service.py:1057`). **No second
resolution path** (D-060 lesson). The Loveland acceptance case: TE-primary
offered, better TE rostered (and not in the give side), S=1, contender ⇒ no
hole, no upgrade ⇒ KILL.

**R5 bypass predicate (round-1 B3 + orchestrator arbitration, final):**
R5 applies **only to untargeted discovery decks** — the proactive surface
#304 complained about. Any targeted job bypasses R5; R1/R2/R3/R4 apply to
everything. The bypass is **derived server-side in `_run_trade_job`, never
read from the request body** — no request-surface change, no G4 contract
impact:

```python
# in _run_trade_job, after prefs resolution (server.py:4840-4847 region):
bypass_need_gate = bool(
    pinned_give            # job arg — "what can I get for X?"
    or pinned_receive      # job arg — "get me this player"
    or opponent_user_id    # job arg — opponent-scoped (#156 / #330 handoff)
    or acquire_positions   # saved league pref, resolved server-side —
)                          #   explicit acquire REPLACES inferred need
                           #   (established semantic: trade_service.py:3841,
                           #   `list(acquire_positions) or list(...needs)`)
```

Threaded into `generate_trades` as a kwarg down the existing `user_needs`
plumbing; the R5 hook is a no-op when set. Explicitly **not** in the field
list: `trade_away_positions` alone (targets the give side; R5 judges the
receive side) and `trade_intent` (#172 modes are discovery-with-a-lens, and
the B2 post-give fix is what protects `tier_down` decks). Precedent for
server-derived targetedness: the likes-you injector's own skip condition
(`not pinned_give and not pinned_receive and not opponent_user_id`,
`server.py:5011-5031` region). One test per field branch (prd U-R5-B*).

### Hook sites (all behind `FLAGS.trade_presentment_rules`)

| # | Site | Insertion (verified @ `0b2dcee`) |
|---|---|---|
| 1 | v3 loop — `generate_pair_trades_v3`, `backend/trade_optimizer.py:193` | immediately after the `filler_ok` gate (`:530-532`), **before** `_both_feasible`/surplus/fairness — so a killed shape can never reach the near-miss collection (`:543-546`) and be sweetener-rescued (mirrors the #227 comment at `:523-525`) |
| 2 | v3 sweetener — `_try_sweeten` (`trade_optimizer.py:645`), called at `:618` | re-validate the **sweetened** combo: pass predicates in like the existing `filler_ok_fn` kwarg (`:626`), e.g. `presentment_ok_fn`; a sweetener changes both `net_P` and `gap` |
| 3 | v2 — `_consider` (`trade_service.py:3568`) | after its `filler_ok` (`:3599-3600`), same position as v3 |
| 4 | consensus — `_emit` (`trade_service.py:3881`) | with the #108/#227/#141 gate block (`:3901-3927`) |

R5's extra inputs ride the existing `user_needs` plumbing
(`trade_service.py:3091-3094` → `trade_optimizer.py:217` kwarg): widen what
is threaded (needs + surplus + outlook + per-position user consensus values)
rather than adding a parallel channel. Note `_user_needs` is currently
`None` when `trade.fit_premium` is off — R5's plumbing must not inherit that
coupling (compute its inputs when `trade_presentment_rules` is on,
independent of `trade.fit_premium`).

**Relaxed pass:** `_relaxed_targeted_pass` (`trade_service.py:2509`) re-runs
`_generate_trades_v2`, so the hooks apply automatically; its stage overrides
(`:2536-2547`) touch only fairness/surplus knobs. Add Part 1 + R5 to the
NEVER-relaxed docstring list (`:2522-2529`, currently #108 + untouchables).

**Out of scope (unhooked, verified):** likes-you quality (Q21;
injector runs after `generate_trades`, `server.py:5011-5031` — no code
needed to skip), asset-ideas (`_generate_asset_ideas_impl`,
`trade_service.py:2571`), the manual calculator, eveners
(`server.py:992-1004` — they add to the *lighter* side by construction, so
the R3 shape is impossible).

## 4. R4 #336 — windowless exclusion set

**Root cause (verified):** generation dedup uses `past_decision_keys` loaded
with `since_days=7` at both load sites — `server.py:15227` (session init)
and `server.py:16439` (trade job) — consumed in `_dedup_and_sort`
(`trade_service.py:2497-2502`). Likes older than 7 days that still sit in
Awaiting, and consummated matches, legitimately regenerate.

**Construction** — once per job in `_run_trade_job` (`server.py:4773`), with
the pref loads (`server.py:4898-4912` region):

```python
exclusion_keys: set[tuple[frozenset, frozenset]] = set()
# (a) Awaiting: likes not yet matured into matches, NO time window.
for t in load_awaiting_trades(user_id):          # database.py:7058
    if t["league_id"] != league_id: continue
    exclusion_keys.add((frozenset(t["my_give"]), frozenset(t["my_receive"])))
# (b) Matches: pending/accepted rows for this user+league, keyed from the
#     user's orientation (user_a_give/receive, mirrored when user is user_b).
for m in load_matches_for_exclusion(user_id, league_id):   # new narrow helper
    exclusion_keys.add((frozenset(m["my_give"]), frozenset(m["my_receive"])))
```

- `load_awaiting_trades` already excludes retracted likes (`database.py:7090`,
  #318 — a retracted like may legitimately reappear) and already subtracts
  matured matches; both properties are relied on, not re-implemented.
- The match helper is a small query over `trade_matches`
  (`database.py:406`) with `status IN ('pending','accepted')` using the
  existing `ix_trade_matches_user_{a,b}_league` indexes (`database.py:2318-2319`).
  `declined` rows do **not** block (Q-G6-2, recommended no).
- Exact set-match only this wave; fuzzy (Jaccard/2.3b) is a noted follow-up.
- Cost bound: `load_awaiting_trades` is 500-row-bounded; the match query is
  index-hit per user+league. Set build failure is non-fatal (log + empty set),
  matching the surrounding pref-load try/except posture. Noted follow-up
  (round-1 N7), not this wave: `load_awaiting_trades` is cross-league and
  fans out league-member fetches per job — a league-scoped variant is the
  obvious later trim if job-start cost ever shows up.

**Application — two hook sites:**

1. `generate_trades` gains kwarg `exclusion_keys: set | None = None`;
   `_dedup_and_sort` (`trade_service.py:2492`) filters against
   `self._past_decision_keys | self._exclusion_keys` — which also covers
   streaming snapshots (`:3354` calls `_dedup_and_sort`) and the relaxed
   pass. **Overwrite-per-call semantics** (round-1 N3): the kwarg *replaces*
   the stored set on every `generate_trades` call, and `None` ⇒ empty set,
   never "keep previous" — the TradeService instance is per-session/
   per-format and serves multiple leagues (`add_league`), while the
   exclusion set is league-scoped per job; carry-over would let league A's
   awaiting keys false-exclude identical asset sets in league B (same
   players roster across leagues) or leak stale exclusions to a follow-up
   caller. Test: two-league sequence (prd U-R4-7).
2. `_inject_likes_you_cards_impl` (`server.py:2872`): alongside its existing
   `_past_decision_keys` skip (`server.py:2957-2959`), skip when
   `(key[0], key[1]) ∈ exclusion_keys` (Q-G6-1 — dedup, not quality; the
   D-055 floor at `:2968-2969` is untouched).

R4 is flag-gated with the group but has **no knob** — the flag is its revert.
No schema change: reads existing tables only.

## 5. Tripwire logging shape

Per-job counters, collected in a plain dict threaded to the generators (or
accumulated on the service instance per job, mirroring how
`_past_decision_keys` lives there):

```python
kills = {"R1": 0, "R2": 0, "R3": 0, "R5": 0, "R4": 0}   # R4 counted at dedup
rule_kills = kills["R1"] + kills["R2"] + kills["R3"] + kills["R5"]
served = len(final_cards)
# Always, at job end (INFO):
log.info("trade-job %s: presentment kills=%s served=%d", job_id, kills, served)
# Tripwire (WARNING) — thin deck AND the new rules account for the thinness:
if served < 5 and served + rule_kills > 15:
    log.warning("presentment-tripwire: job=%s league=%s served=%d kills=%s",
                job_id, league_id, served, kills)
```

Attribution form per round-1 N2: the hooks sit *before* feasibility/surplus/
fairness (§3 hook table — placement the near-miss guarantee requires), so a
"candidates that passed everything except the new rules" count is unknowable
at hook time, and a naive pre-count would blame presentment rules for decks
thinned by fairness — false alarms that train everyone to ignore the
tripwire. `served + rule_kills > 15` fires only when the rules' own kills
explain the gap between a thin deck and a healthy one. Grep-able prefix
`presentment-tripwire` goes in `docs/runbook.md` at build.

## 6. API / payload change: NONE (guarantee for G4)

Stated as a contract guarantee, with evidence @ `0b2dcee`:

- **No request change:** `/api/trades/generate` body is untouched — no new
  params; the flag and all 7 knobs are server-resident (`features.json` /
  `model_config`), and the R5 bypass (§3) is derived from *existing* job
  fields, adding nothing a client could pass.
- **No response change:** the card dict is produced solely by
  `trade_card_to_dict` (`server.py:9727`); this feature adds **no field, no
  enum value, no rename** there or anywhere in the job-status payload. R4/R1–
  R5 only remove candidates before that serializer runs.
- **Only observable delta:** deck composition/size. The existing
  empty/no-fair-trades states cover the shrink case — G4's #330 honest-empty
  state is specified against exactly that surface.
- Enforced by test (prd.md R-10): flag-ON serialized card keys ==
  flag-OFF serialized card keys, plus the byte-identity test flag-OFF.

## 7. Plan-cite verification record

**Round-1 update (N5):** `origin/main` moved again to `2c67ea0` (PR #133,
premium import — `server.py` +55/−? lines, rankings-import-scoped).
Re-verified @ `2c67ea0`: `trade_service.py`, `trade_optimizer.py`, and
`database.py` are **untouched** between `0b2dcee` and `2c67ea0` (not in the
diffstat), so every cite into them below stands verbatim; in `server.py`,
`_run_trade_job` is still `:4773` and `acquire_positions` prefs resolution is
`:4840-4847` → `generate_trades` call `:4974-4975`. Per N5, build agents
should treat `server.py` numbers as **symbol + nearest-anchor** cites (the
function names are the contract, the numbers are a courtesy) and re-grep on
their freshly-fetched fork point.

Verified true @ `0b2dcee` exactly as the plan stated: `trade_service.py`
2286 / 2296 / 2492 / 2497-2502 / 2509 / 2522-2529 / 2536-2547 / 2571 / 2957 /
3091-3094 / 3367 / 3436-3437 / 3568 / 3599 / 3791 / 3881 / 3901-3927 / 998 /
1057 / 1248 / 1688 / 2220; `trade_optimizer.py` 193 / 217 / 277 / 497-546 /
609-640 / 626 / 645 / 239-241; `server.py` 2872 / 2957-2959 / 2968-2969 /
4838-4857 / 4898-4912 / 5011-5031 / 9335 / 9452 / 15227 / 992-1004;
`database.py` 406 / 7058 / 7090 / 2318-2319; `features.json` +
`feature_flags.py` flag mechanics; mobile fairness constants
`tradePregen.ts:25-27`; corpus artifact exists on disk (§ prd.md).

Drifted (plan → verified, all caused by the 6 post-`d3fe3ac` commits, none
semantic): `_run_trade_job` 4776 → **4773**; `trade_card_to_dict` 9743 →
**9727**; second `since_days=7` site 16438 → **16439**; likes-you floor cite
2968 → **2968-2969** (unchanged in substance). One coupling the plan did not
call out, added in §3: `_user_needs` is gated on `trade.fit_premium` at
`trade_service.py:3093-3094` — R5 must not silently depend on that flag.

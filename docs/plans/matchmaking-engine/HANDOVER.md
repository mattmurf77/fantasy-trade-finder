# Matchmaking engine — standing handover

> **Read this before changing trade generation, the ranking/board math, or the bake-off.**
> Written 2026-08-18 at the end of a long session that rebuilt much of this area. It records
> what is live, what is dark, what was deliberately NOT done, and — most importantly — the
> traps that already bit us, so the next session does not rediscover them.
>
> This is **reference** (what the system is). Motion lives in `living-memory/`. Where they
> disagree, `docs/` wins and living-memory gets fixed.

---

## 1. The thesis

FTF is **matchmaking for trade partners**: suggest a trade that BOTH managers want. The
operating model is deliberately the dating-app one — reciprocal scoring, mutual acceptance,
scarce endorsed suggestions. Research corpus (3 rounds, 11 memos, ~400 sources) is in
[`docs/research/matchmaking/`](../../research/matchmaking/) with an index README. Read the
round-1 memos before proposing changes to how suggestions are scored or presented; most
"obvious" ideas in this space are already covered there with evidence for or against.

**The structural moat, worth not losing:** FTF holds BOTH managers' honest private
valuations (per-user Elo boards from matchup votes). Myerson–Satterthwaite says two
bargainers with private values systematically fail to find trades that would benefit both.
A trusted third party holding both boards does not have that limitation. Nothing else in
the market has this.

---

## 2. What is LIVE right now

| Change | Flag / knob | State | Merge |
|---|---|---|---|
| Suggestion telemetry (counterfactual logging, ghost holdout, executed-trade linking) | `suggestion.telemetry` | **ON** | `1ba148c` |
| Decline-reason capture (two-layer Value/Fit/Neither) | `feedback.decline_reasons` | **ON, all users** | `c95a70a` / `00b2a2c` |
| G6 presentment rules (#304/#336/#339/#340/#341) | `trade.presentment_rules` | **ON** | another session's wave |
| Engine quality: divergence-gated fairness, minimal-package preference, pick-pair strip, headliner cap, confidence-damped mismatch | 5 knobs, all default ON | **ON** | `60cbe11` |
| Phase 0: pinned players stop inflating confidence; `force:true` honoured with supersede | `pin_exclude_comparisons`, `force_supersedes_running` | **ON** | `e8ae476` |
| Tier-bounded voting (a tier placement BOUNDS a player, no longer freezes him) | `pin_tier_bounded` | **ON** | `9d24da3` |
| G-049 swipe replay guard | — | **ON** | `3760f12` |
| Fairness preference default flipped to OFF (client) | AsyncStorage `ftf:trades:fairness_on` | **OFF by default** | `00b2a2c` |

## 3. What is BUILT BUT DARK

| Thing | Flag | Notes |
|---|---|---|
| `trade_gen.v2` — divergence-driven staged pipeline (dual-board ε, MESO, exposure shaping) | `trade_gen.v2` = **false** | Never served a card. Becomes bake-off **arm C**. When off, the module is never imported. |
| Bake-off runner — fan-out, team-draft interleave, per-arm attribution | `trade.bakeoff` = **false** | Inside it, `bakeoff_serve_interleaved=0` = Phase-4 dark mode (all arms generate + log, only arm B serves). |
| Arm A profile + golden (`MODEL_A_PROFILE`, `model_a()`) | — | Inert until a caller enters the context. |

---

## 4. What was deliberately NOT done

Each of these is a decision, not an oversight. Do not "fix" them without reading why.

1. **The mobile presentation redesign was never built.** Nine approved Chalkline states exist
   at [`mockups/trade-suggestion-redesign/`](../../../mockups/trade-suggestion-redesign/) —
   endorsed "Today's Trade" hero, MESO variant picker, uncapped browse with dismiss-as-signal,
   turn-state chips, honest-empty state. **The engine work shipped; the presentation did not.**
   This is the largest single piece of unbuilt value. It is user-visible, so it needs full
   gates and an app build.
2. **User-facing trade settings were NOT removed** (operator, 2026-08-18): re-adding removed
   UI costs more than instructing 3–5 testers. Both settings are now RECORDED per card
   (`fairness_threshold`, and `trade_intent` in flight) so a tester changing them mid-test is
   detectable rather than a silent confound.
3. **Existing board pins were NOT bulk-cleared.** 2,735 pins existed; wiping them would
   discard deliberate tier placements. Tier-bounded voting made the question moot — all pins
   thaw (bounded) with no data write. `pin_unpin_on_newer_swipe` / `pin_legacy_at_epoch`
   remain as the Phase 0 revert path, defaulted OFF and documented as superseded.
4. **Arm A was removed from SERVING, not deleted.** Profile, golden and knob-inventory guard
   stay and keep passing. Rebuilding that baseline later would be expensive; keeping it dark
   is free.
5. **3-team trades not built.** Kidney-exchange literature caps cycles at 3 because failure
   compounds; the gen-v2 scoring is decomposed so a cycle layer can bolt on. Do not build
   4-way — every fielded exchange system on earth refuses.
6. **Sim gate waived** by the operator 2026-08-17 for this line of work. Maestro flows for
   decline-reasons were **authored but never executed**. TestFlight is the only runtime
   evidence this feature has.
7. **The band-edge / pinned-player UI cue** is backlogged in `NEXT.md`, not built. It is the
   durable fix for the class of bug that started all this — a user voting against a control
   that cannot move, with nothing on screen saying so.

---

## 5. Open decisions (nobody has answered these)

1. **The skew ratio for the bake-off deck.** Operator specified 30 cards: 10 arm-B
   divergence, 10 arm-B consensus, 10 arm C; 5 value / 5 outlook within each.
   **Caveat that has NOT been resolved:** the 2.5× consensus-over-divergence quality gap
   (33.2% vs 13.3% like rate) was measured on the BROKEN engine, and divergence cards were
   **81% picks** vs consensus at 39% — so that gap was very likely measuring the pick-spam
   defect we fixed. Re-measure on post-fix data before treating the ratio as evidence-based.
2. **Job budget.** Fan-out is 2.35× (3.1s → 7.4s on a fixture), worst case ~33–45 s against
   `_JOB_HARD_TIMEOUT = 60`, past which a job is marked **error** and yields no deck at all.
   Phase 4's dark run exists to measure p95 before Phase 5. The timeout may need raising.
3. **Engine-quality knob defaults are unmeasured** — reasoned from fixtures, never tuned
   against the live corpus. Re-running the impression queries is the tuning pass.
4. **`fairness_threshold` is only recorded for bake-off decks** (NULL otherwise), because
   unconditional capture would break Phase 3's flag-off golden. Recording it for ALL decks is
   better instrumentation and belongs in its own change with a golden re-capture.
5. **`model_config` has no `updated_at`** — knob-change dates are unknowable after the fact.
   `bakeoff_runs.config_json` sidesteps it for the bake-off only.

---

## 6. Traps that already bit us

**These cost real time. Read them.**

1. **`eas build` archives the LOCAL working directory, not `origin/main`.** This repo's main
   checkout sits on an old session branch, 141 commits behind at one point. A build was
   queued that contained none of the feature and carried an older version number — it would
   have shipped to TestFlight as an apparent downgrade. **Always build from a checkout you
   have verified contains the feature files.**
2. **Verify a branch merged by CONTENT MARKERS, never whole-file diff.** This repo
   squash-merges and several sessions push daily, so `git diff main <branch> -- <file>`
   surfaces *main's newer content* as though the branch were unmerged. A first pass reported
   five already-merged branches as unmerged.
3. **`save_deck_impressions` uses `executemany`, which compiles from the FIRST row's keys.**
   Stamping a column on only some rows silently drops it for the ENTIRE deck. Write every
   column on every row.
4. **Record the gate a row PASSED, never the gate that was requested.** The engine composes
   `fairness_threshold` differently per basis (consensus = requested; divergence =
   `min(requested, floor)`; relaxed = widened; `gen_v2` = none). Persisting the request would
   have mislabeled two cards in three. Now an LLD convention.
5. **Post-generation re-rankers void the bake-off.** Five layers (`thompson_v2`, `fatigue`,
   `session_rerank`, `taste_vectors`, `exploration`) reorder decks after generation. If any
   touches an interleaved deck, team-draft's position balance is destroyed **silently** and
   you measure deck position instead of model quality. Bypassed via
   `bakeoff_runner.bypass_rerankers()`; a run with them live must be **discarded, not
   caveated**.
6. **Arm A is a config profile, not a code branch.** It drifts the moment someone adds a knob.
   Protected by a golden against SHA `92c31d5` PLUS a 189-key `_DEFAULT_CFG` inventory that
   fails BY NAME on any knob added or removed — because a golden alone only catches drift
   that happens to move that one fixture.
7. **A golden fixture must pin its own inputs.** Arm A's fixture supplies players, seed Elo,
   user Elo, rosters and confidence as literals, so board-computation changes (pins,
   tier-bounding, premium import) cannot drift it. Otherwise it fails for unrelated reasons
   and gets "fixed" by loosening it, and the baseline quietly stops meaning anything.
8. **`inspect.getsource` tests prove a gate's TEXT exists, not that it works.** A peer session
   replaced several with route-level tests that POST twice and count rows, then
   sabotage-verified by deleting the gate. Prefer that.
9. **Concurrent sessions collide on living-memory IDs.** Three D-number collisions happened in
   three days. Re-grep `max+1` immediately before writing, and never renumber someone else's
   entry.
10. **`.easignore` needs leading slashes.** A bare `screens/` once matched `mobile/src/screens/`
    and killed two builds at the bundle step. Anchored now — keep it that way.

---

## 7. Corrections to earlier claims (do not re-propagate)

- **Adams was NOT overvalued** — FTF had him WR43/1138.8; KTC WR43, DynastyProcess WR43,
  FantasyCalc WR35. The consensus seed is fine.
- **The ladder does NOT under-penalise age** — median board-to-consensus ratio is 1.00 in
  every age bucket; 30+ players are 14.4% of suggested assets vs 13.5% of rostered.
- **The "+12.5% from down-votes" figure was wrong.** Those 18 Adams comparisons were
  `decision_type='trade'`, and trade decisions have never entered `comparison_counts`. The
  inversion mechanism is real for RANKING votes on pinned players; it did not happen to Adams.
- **`trade.outlook_blend` is false in prod** — the app's only explicit age curve has never run.
  Hygiene, not a fix; values are not age-broken.

---

## 8. Where the evidence lives

| Question | Document |
|---|---|
| How do matchmaking services actually work? | [`docs/research/matchmaking/`](../../research/matchmaking/) (README indexes 11 memos) |
| Is a player mis-valued? Is the ladder age-broken? | [`docs/reviews/2026-08-18-valuation-age-audit.md`](../../reviews/2026-08-18-valuation-age-audit.md) |
| When did trade quality degrade, and why? | [`docs/reviews/2026-08-18-trade-logic-archaeology.md`](../../reviews/2026-08-18-trade-logic-archaeology.md) |
| What do real leagues actually trade? | [`docs/business/analytics/2026-08-16-organic-trade-corpus.md`](../../business/analytics/2026-08-16-organic-trade-corpus.md) — 529 trades, 22 league-seasons |
| The bake-off design | [`docs/plans/three-model-bakeoff/PLAN.md`](../three-model-bakeoff/PLAN.md) + scope-phase0/2/3/tier-bounded/composition |
| Decline-reason spec | [`docs/plans/decline-reason-capture/SPEC.md`](../decline-reason-capture/SPEC.md) |
| Engine-quality fixes | [`docs/plans/engine-quality/scope.md`](../engine-quality/scope.md) |

**Decisions:** D-066 (pass Elo only on `value_giving`), D-069/D-070 (pin fixes), D-073
(ungated in-memory signal), D-075 (arm A pinning), D-076 (tier-bounded), D-077 (re-ranker
bypass + threshold capture).

---

## 9. How to check the live state in 30 seconds

```bash
# what's on / off in prod
curl -s https://fantasy-trade-finder.onrender.com/api/feature-flags | python3 -m json.tool | grep -E "trade_gen|bakeoff|presentment|decline_reasons|telemetry"

# are reasons flowing? (prod, READ-ONLY — SELECT only, never write)
#   SELECT reason, detail, COUNT(*) FROM trade_pass_reasons GROUP BY 1,2 ORDER BY 3 DESC;

# is the deck still pick-stuffed? (the defect that started this)
#   SELECT SUBSTRING(served_at,1,10) d,
#          ROUND(100.0*AVG((features_json::json->>'involves_pick')::int),1) pick_pct
#   FROM deck_impressions WHERE served_at > '2026-08-15' GROUP BY d ORDER BY d;
```

Baseline for that last one: pick share ran 14.3% (08-08) → 64.4% (08-18) BEFORE the fix.
If it has not fallen materially since 2026-08-18, the engine-quality knobs are not doing
what their tests say they do, and that is the first thing to investigate.

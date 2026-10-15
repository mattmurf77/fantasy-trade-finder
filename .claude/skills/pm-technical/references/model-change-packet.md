# Model-change packet

Field list agreed with models-lead, 2026-10-15.

This is the one packet for all three departments, used for any change to what a model
outputs or to how model output is shown. Scope §8 links it. Save it beside the scope as
`model-change.md` (`docs/plans/<slug>/` or `docs/feedback/items/<id>-<slug>/`). Eng's
model-change skill links this file and never copies it.

## Route

1. The area PM fills every field it can answer and attaches the packet to scope §8.
2. **Plan sign-off (13a), before the build:** `head-product` → `head-bizops` →
   `models-lead`, and the verdict comes back the same way. A bake-off design change also
   needs `analytics-lead`'s sign-off (field 7).
3. With 13a, `head-product` sends the spec to `head-eng`, which assigns `models-eng`.
   Eng supplies the eng-side fields into this same packet through `head-eng`: the D-056
   evidence, the eval output (field 8), the surface impact (field 9) and the rollback
   lever (field 12).
4. **Result sign-off (13b), before ship:** `models-eng` returns its ship packet, the
   eval output against field 6. `head-eng` → `head-bizops` → `models-lead`. Only then
   does `release-lead` ship.
5. The area PMs whose surfaces show the output (field 9) update their own scopes.

**Readouts:** `analytics-lead` owns metric definitions, the method and validity. It can
veto a read as invalid (SRM, arm mis-stamping, non-comparable windows), and then no
verdict is given. `models-lead` owns the bars and the verdict. Neither overrules the
other.

## Fields

1. **Which model.** Name the engine files, `model_config` keys
   (`docs/config-reference.md`) and flags the change touches. Engine code is
   `models-eng`'s; trio selection code is `rankings-eng`'s.

   | Model | Start here |
   |---|---|
   | Elo ranking | `backend/ranking_service.py` |
   | Tier bands | `backend/tier_config.json` |
   | Trio matchup selection | `backend/smart_matchup_generator.py` |
   | Value core | `backend/value_core/`, `backend/value_model.py`; flag `trade.value_core` |
   | Trade scoring and packaging | `backend/trade_service.py` (v2), `backend/trade_optimizer.py` (v3), `backend/trade_gen_*.py`, `backend/fit_engine.py` |
   | Deck rules and filters | `backend/deck_quality.py`; flag `deck.quality_filters` |
   | Outlook | `backend/outlook/` |
   | Pick values | `backend/pick_values.py` |

   Trio selection needs `models-lead`'s sign-off only for selection-policy changes:
   which players or trios are chosen, the algorithmic fallback, the LLM prompt, or the
   Claude model id. It doesn't need sign-off for UI, latency or caching changes that a
   seeded determinism test shows leave selection identical.
2. **Downstream models.** Other models that read this output. For example: the shared
   bad-card rules (value core, fit engine and `deck_quality`; D-206, D-207); pick values
   (every engine); the Elo board (every engine prices off it).
3. **Hypothesis.** What changes, the expected effect (direction and rough size), and the
   evidence behind it, such as Calibration tags, feedback IDs or a backtest.
4. **Strategy owner.** `models-lead` for model behavior. If the change began as an
   operator ask, also quote it with its date.
5. **Bars.** **5a** is the primary bar. **5b** lists guardrails that must not regress.
   Cite each bar by ID from `docs/model-evaluation/bars.md` (held by `models-lead`).
   Until that file exists, cite it by source: the D- entry, or the script and line.
   - **An insult rate names its definition.** Never mix definitions across arms or
     rounds. There are three:
     - D-055: the |Δ| ≥ 500 materiality floor (bar: < 3%, with empty decks < 5%);
     - the value-core bench: the other side loses > 20% of raw value
       (`backend/eval/value_core_bench.py:43`, `TARGETS["insult_loss"]`);
     - D-207 `deck_quality`: breakup (best piece received < 0.70 × best piece given)
       and filler (a piece below max(450, 25% of the headliner)).
   - **The bench guardrails:** the value-core bench `TARGETS` (insult rate < 3%,
     real-piece share ≥ 70%, median value given ≥ −10%, max appearances ≤ 3).
   - **Calibration would-send:** `share_ge_4` per arm in
     `GET /api/admin/grading/report` (D-208). A legacy 3 counts as No. Report it per
     grader and pooled.
   - **Outlook and Win Now:** Brier skill against climatology, with the 90% CI lower
     bound > 0. This bar is a draft.
   - **Elo, tiers and trio selection:** "no bar exists yet" is an allowed answer. It
     sends the packet to `models-lead` to set a bar before the run.
6. **Pre-registration.** Record all of this before the run, and before the window opens
   for a live read:
   - the pass number;
   - what a miss means: don't ship, ship dark, or ship as an experiment arm;
   - any operator override of a miss, verbatim with its date (D-200 shipped two arms
     that missed their bar on an operator call);
   - the decision rule, the minimum n and the horizon; no interim reads.

   For a Calibration arm, add:
   - n per arm: the floor is 40; the decision-grade target is about 175, which detects
     ±15 pp at 80% power (100 per arm detects only ±20 pp);
   - the horizon date, no interim reads, and at most 3 arms per round;
   - grader coverage: at least 2 graders with at least 20 cards each, or the packet
     declares the round single-grader;
   - for board-level questions (does a value board predict grades?), paired AUC on
     unique cards, with n stated as Yes and No counts;
   - whether values were hidden from or shown to graders.

   Pre-registration is joint. `models-lead` writes the bar, the decision rule, the
   minimum n and the horizon; `analytics-lead` confirms the metric definition, the
   method and the power. If a definition must change mid-window, the read is
   re-registered and the verdict waits.
7. **Eval route and online path.** One or more of:
   - offline: a bench, backtest or replay (`backend/eval/`, `scripts/deck_eval.py`);
   - a Calibration arm;
   - **the bake-off**, for card-level outcomes (like, send or accept per card);
   - **`experiments.py`**, for user-level outcomes (retention, sessions, conversion),
     through its `engine` layer with `model_overlay`.

   Say whether offline evidence is enough or a live arm is needed.

   **A bake-off design change** (adding or retiring an arm, changing an arm's profile,
   interleaving or lane allocation, group quotas, any `bakeoff_*` `model_config` value,
   or which deck surfaces run the bake-off) adds an experiment-design block:
   - the arms and the unit (deck or user-league);
   - the interleaving method and per-card arm stamping;
   - the primary metric: decided like-rate by arm (`scripts/bakeoff_readout.sql` §2);
   - guardrails, including per-arm `deck_quality` drop counts (the D-207 filters can
     starve one arm);
   - the minimum n per arm, the horizon and the decision rule;
   - a layer-collision check against `experiments.py` on the same users.

   Route for that block: `models-eng` drafts it. `head-eng` sends it both to
   `head-bizops` → `models-lead` (arms, bars, decision rule) and to `head-product` →
   `analytics-lead` (method, stamping validity, layer collision). Both sign. The prod
   `model_config` write is `release-lead`'s, on the operator's word.
8. **Evidence provenance.**
   - the branch head sha and the base sha;
   - the eval script and its exact args;
   - the data source: a local SQLite path, prod read-only plus the timestamp, or a
     frozen fixture path plus its hash;
   - hashes of the `model_config` snapshot and of the flags dict;
   - `PYTHONHASHSEED`, the clock freeze and the RNG seed (G-065: wall-clock deadlines,
     not hash order, are the main non-determinism);
   - for Calibration, the report query (`since`, `include_open`);
   - the dates of any value snapshot (DynastyProcess and others).
9. **Surfaces affected,** per area: the screens, routes and clients (mobile, web,
   extension) that show this output.
10. **Calibration integrity.** Does the change alter which cards Calibration samples
    (its current arm reads served decks through `deck_impressions`), or its grading
    content (scale, tags, arms)? Say how open rounds are protected. A grading-content
    change needs `analytics-lead`'s review of the definitions and `models-lead`'s of
    comparability.
11. **Data sources and rights.** List every third-party input and its terms status.
    Anything beyond today's use is a pending operator yes/no, raised through
    `head-bizops`.
12. **Rollback lever.**
    - the flag or key that turns the change off, and whether that is deploy-free
      (`POST /api/feature-flags/reload`);
    - where the knob lives: a `model_config` key (no deploy) or a code constant
      (deploy);
    - the flag-off byte-identity evidence: the golden test's name (for example the
      `trade.bakeoff` flag-off golden in `backend/tests/test_bakeoff_serving.py`, built
      on `backend/tests/support/bakeoff_harness.py`), or "none".

    "None" is an answer for any of these, and a reason to ask for one.
13. **Sign-off lines.**
    - **13a, plan,** before the build:

      ```
      models-lead (plan): approve | approve with changes | reject — YYYY-MM-DD — via head-product → head-bizops — <note>
      ```

    - **13b, result,** on `models-eng`'s ship packet (the eval output against field 6),
      before `release-lead` ships:

      ```
      models-lead (result): approve | approve with changes | reject — YYYY-MM-DD — via head-eng → head-bizops — <note>
      ```

## Worked example: fit-first arms in Calibration

This change shipped before the org existed. The packet below is reconstructed from
D-199, D-200, `docs/plans/fit-scorecard/scope.md`, `living-memory/TEST_LEDGER.md`,
#317 (`9cfcac7a`), #324 (`4d880833`) and the 2026-10-14 CHANGELOG entry. "Not recorded"
means the history holds no answer.

1. **Model:** trade scoring and packaging, as fit-first generation: approach A
   (`fit-a-1`) and approach B (`fit-b-2`). Files: `backend/fit_engine.py` (new),
   `blind_grading.add_fit_arms`, and `server._build_grading_session` (#324). No
   `model_config` keys, because the multipliers are code constants frozen before the
   first run. No new flag: the arms show only inside Calibration (`grading.blind`).
2. **Downstream models:** not recorded.
3. **Hypothesis:** generating trades from two-way team fit yields cards graders would
   send more often than today's engine.
4. **Strategy owner:** the operator's direct ask. The operator proposed fit-first
   generation and approved the plan doc. Today this would be `models-lead`.
5. **Bars:**
   - **5a:** does the viewer's gain separate would-send grades from No on Calibration
     cards? Measured by Q1 of `backend/eval/fit_scorecard_test.py`.\*
   - **5b:** not recorded as guardrails. The plan also pre-registered Q2 (the partner's
     gain predicts the "they won't accept" tag, AUC ≥ 0.65): A 0.50, B 0.32.
6. **Pre-registration:** Q1 AUC ≥ 0.70, and ≥ 0.10 over the best baseline. Result:
   A 0.58, B 0.43; the best baseline (best-piece ratio) was 0.66. Both missed. Operator
   override, 2026-10-09: chose "Add A + fixed B" (D-200). Minimum n and horizon for the
   live arms: not recorded.
7. **Eval route:** offline on round-1 grades, then Calibration arms `fit_a` / `fit_b` as
   the out-of-sample test. Round 1 had 120 graded cards (D-199), and 99 of them were
   scorable offline (TEST_LEDGER; the script drops a card when an asset has since left
   the league or the partner can't be matched). #324 (2026-10-14) folded the arms into every new deck
   after a tester's self-started deck got none. Round 2 so far (3 graders): fit A mean
   3.36 (n=47, 55% would send), today's engine 3.19 (n=100, 50%), fit B 2.38 (n=13,
   23%). Fit B is below the 40-per-arm floor, and no arm reaches the decision-grade
   target.
8. **Evidence provenance:** the script `backend/eval/fit_scorecard_test.py` against prod
   read-only, built on #317 (`9cfcac7a`). Exact args, seeds and hashes: not recorded.
9. **Surfaces:** the Calibration tab only. The Results screen still shows only the two
   original arms (`ARM_ORDER` in `mobile/src/components/GradingResults.tsx`); the fit
   arms read in the admin report. Live Trades decks are unchanged.
10. **Calibration integrity:** the arms were folded into open sessions. Answered cards
    never move; unanswered and new cards are blind-shuffled; the fold is idempotent and
    aborts if a moving card was answered
    (`test_blind_grading_service.py::test_fold_aborts_when_a_moving_card_was_answered`).
11. **Data sources and rights:** approach B reads Sleeper's weekly projections
    (`fit_engine.fetch_ros_points`). Terms status: not recorded.
12. **Rollback lever:** none at the arm level. The knobs are code constants in
    `fit_engine.py` (a deploy). Setting `grading.blind` false turns off all of
    Calibration. Flag-off byte-identity evidence: none. Compare D-207:
    `deck.quality_filters` false plus a flag reload undoes it with no deploy.
13. **Sign-off:** **13a:** the operator, 2026-10-09 (D-200). **13b:** not recorded; the
    round-2 readout was still awaiting the operator's call on 2026-10-14.

\* This bar uses the drop-3s convention of `fit_scorecard_test.py` and D-200 (4–5 vs
1–2). The current rule counts a legacy 3 as No (field 5), so a re-run should report
both.

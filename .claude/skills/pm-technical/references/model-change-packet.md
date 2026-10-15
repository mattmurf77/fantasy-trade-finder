# Model-change packet

> **DRAFT: fields pending models-lead review.** The field list below goes to
> `models-lead` through `head-product` → `head-bizops` before this file is final.

A one-page packet an area PM fills for any change to what a model outputs, or to how
model output is shown. Scope §8 links it. Save it beside the scope as
`model-change.md` (`docs/plans/<slug>/` or `docs/feedback/items/<id>-<slug>/`).

## Route

1. The area PM fills the packet and attaches it to scope §8.
2. `head-product` checks it is complete and sends it to `head-bizops`.
3. `head-bizops` passes it to `models-lead`, who returns a verdict (field 9) the same
   way.
4. With sign-off, `head-product` sends the spec to `head-eng`, which assigns
   `models-eng`. `models-eng` builds the change and accepts it against the bar in
   field 5.
5. The area PMs whose surfaces show the output (field 7) update their own scopes.

## Fields

1. **Which model.** One of the models below. Name the engine files, `model_config` keys
   (`docs/config-reference.md`) and flags the change touches. Engine code is
   `models-eng`'s per the org chart, except trio matchup selection, which the starting
   file map gives to `rankings-eng`.

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

2. **Hypothesis.** What changes, the expected effect (direction and rough size), and
   why: the evidence behind it, such as Calibration tags, feedback IDs or a backtest.
3. **Strategy owner.** `models-lead` for model behavior (P1). If the change began as an
   operator ask, quote it with its date as well.
4. **Quality bar it is measured against,** with its source:
   - the D-055 deck-quality bars: insult rate < 3%, empty decks < 5%, insults scored
     with the |Δ| ≥ 500 materiality floor;
   - the Calibration Yes rate: `share_ge_4` per arm in
     `GET /api/admin/grading/report` (D-208);
   - a backtest or bench metric: name the script and the metric.
5. **Pre-registered pass bar, and what happens if it fails.** Set the number before the
   run. Then say what a miss means: don't ship, ship dark, or ship as an experiment arm.
   If the operator overrides a miss, record their words verbatim with the date. D-200
   shipped two arms that missed their bar on an operator call.
6. **Eval route,** one or more of:
   - an offline backtest or bench (`backend/eval/`, `scripts/deck_eval.py`);
   - a Calibration arm;
   - a live experiment through `analytics-lead` (`/an-experiment`; the operator approves
     launches).

   Give the sample size and the result that would change the decision.
7. **Surfaces affected,** per area: the screens, routes and clients (mobile, web,
   extension) that show this output.
8. **Rollback lever.** The flag or `model_config` key that turns it off, and whether
   that is deploy-free (`POST /api/feature-flags/reload`). "None" is an answer, and a
   reason to ask for one.
9. **Sign-off line:**

   ```
   models-lead: approve | approve with changes | reject — YYYY-MM-DD — via head-product → head-bizops — <note>
   ```

   Then the spec goes to `head-eng` → `models-eng`, and `models-eng` accepts the build
   against the bar in field 5.

## Worked example: fit-first arms in Calibration

This change shipped before the org existed. The packet below is reconstructed from
D-200, `docs/plans/fit-scorecard/scope.md`, #317 (`9cfcac7a`), #324 (`4d880833`) and
the 2026-10-14 CHANGELOG entry.

1. **Model:** trade scoring and packaging, as fit-first generation: approach A
   (`fit-a-1`) and approach B (`fit-b-2`). Files: `backend/fit_engine.py` (new),
   `blind_grading.add_fit_arms`, and `server._build_grading_session` (#324). No
   `model_config` keys, because the multipliers are code constants frozen before the
   first run. No new flag: the arms show only inside Calibration (`grading.blind`).
2. **Hypothesis:** generating trades from two-way team fit yields cards graders would
   send more often than today's engine.
3. **Strategy owner:** the operator's direct ask. The operator proposed fit-first
   generation and approved the plan doc. Under P1 today this is `models-lead`.
4. **Bar:** does the viewer's gain separate would-send grades (4–5) from no (1–2) on
   Calibration cards? Measured by Q1 of `backend/eval/fit_scorecard_test.py`.
5. **Pass bar:** Q1 AUC ≥ 0.70, and ≥ 0.10 over the best baseline. Result: A 0.58,
   B 0.43; the best baseline (best-piece ratio) was 0.66. Both missed. Operator
   override, 2026-10-09: chose "Add A + fixed B" (D-200).
6. **Eval route:** offline on round-1 grades (99 cards, one grader), then Calibration
   arms `fit_a` / `fit_b` as the out-of-sample test. #324 (2026-10-14) folded the arms
   into every new deck after a tester's self-started deck got none. Round 2 so far
   (3 graders): fit A mean 3.36 (n=47, 55% would send), today's engine 3.19 (n=100,
   50%), fit B 2.38 (n=13, 23%). What a packet would have added: the n per arm that
   decides the question, fixed before the round starts.
7. **Surfaces:** the Calibration tab only. Product ownership moves to `trades-pm` under
   decision P2, and the arms, gates and bars are `models-lead`'s. The Results screen
   still shows only the two original arms (`ARM_ORDER` in
   `mobile/src/components/GradingResults.tsx`); the fit arms read in the admin report.
   Live Trades decks are unchanged.
8. **Rollback lever:** none at the arm level. Setting `grading.blind` false turns off
   all of Calibration. Compare D-207: `deck.quality_filters` false plus a flag reload
   undoes it with no deploy.
9. **Sign-off:** the operator, 2026-10-09 (D-200). Under the org it would be
   `models-lead`, then `head-eng` → `models-eng`.

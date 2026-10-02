# PRD — Calibration: in-app blind grading (value-core Gate 2)

**Date:** 2026-10-02 · **Status:** spec, not built · **Owner:** operator, read by the lead
Companion: [scope.md](scope.md) · [hld.md](hld.md) · [lld.md](lld.md) · [specs.md](specs.md) · parent plan [../value-core-engine/](../value-core-engine/prd.md)

Users see the feature as **Calibration**. The code and data keep the `grading` name (scope.md "Naming").

## 1. The decision in one paragraph

Testers get a **Calibration** tab in the bottom bar, in the slot the Draft tab used. There they grade trade ideas one at a time. For each idea they answer one question: **would I send this?** They answer on a scale of 1 to 5, can add reason tags, or can skip.

They are never told which engine made a card.
- Some cards come from the tester's latest real deck in Acquire. That is today's engine.
- The rest come from the new value-core engine, run for the same team in the same league.
- A trade both engines suggest is shown once and counts for both.

After the last card, the app reveals how each engine scored. The lead reads the totals across testers from an admin report. That is Gate 2: **does the plain value core grade as well as today's engine?**

At the same time, **the Draft tab leaves the bar for everyone**. Its seasonal switch `draft.tab` goes to false, and its code stays. The Draft Room is still one tap away, from League › Rookie draft and from the Draft chip in Acquire.

## 2. Problem

The value-core plan has two measuring sticks: bench guardrails ([../value-core-engine/prd.md §6](../value-core-engine/prd.md#6-success-metrics)) and a CSV blind grade (`backend/eval/blind_grade.py`). The CSV route has three problems:

- **The wrong surface.** The operator grades spreadsheet rows on a laptop, but he judges trades on his phone, inside the card layout he uses.
- **Testers are locked out.** It needs prod read-only tooling and private files, so the one or two testers who should grade cannot.
- **The incumbent's cards come from prod tooling.** They are pulled through `prod_analytics` (`blind_grade.py:143-203`), not from the app.

The operator asked for grading as an app feature, given the Draft tab's place in the bar (2026-10-02).

## 3. Goals

1. **G1 — Blind by construction.** Nothing a grader can see before finishing says which engine made a card. That covers field names, ids, order, values and counts. [hld.md §4](hld.md#4-blinding-guarantees) lists the guarantees, and one test enforces them.
2. **G2 — Same brief for both engines.** Both arms use the same user, team and league. Every card's values come from one consensus source.
   - The current arm is the deck the grader was actually served.
   - The value-core arm is the engine's own deck with default settings, built from the same database inputs the bench uses.
3. **G3 — No side effects.** Grading never changes Acquire's deck, likes, passes, impressions, the Elo board or match state.
4. **G4 — Resumable and quick.** Up to 40 cards, one at a time, with progress shown. A session survives tab switches and app restarts.
5. **G5 — A readout the lead can act on.** Per arm: n graded, mean grade, share of 4s and 5s, and tag counts. Reported per session, per grader and overall.
6. **G6 — Tester-only, reversible.** The tab exists only for allowlisted testers, and opening it to everyone later is a one-line change. Both the tab and the Draft-tab removal reverse without a deploy.

## 4. Non-goals

- **Not a user feature yet.** Testers only (operator, 2026-10-02).
- **No change to how either engine builds decks.**
- **No deletion of the Draft tab's code** (operator, 2026-10-02). A future season turns it back on with `draft.tab`.
- **No new analytics events** (scope §1 waiver). The tab tap rides the existing `tab_selected`.
- **No web or extension surface, and no CSV export.** The admin report is JSON. The CSV tool stays as is.
- **No "previous card" control.** Re-grading exists only so retried requests are idempotent.
- **No significance testing.** With n ≈ 40–120 per arm, the lead reads means, shares and tags.
- **No per-card reveal.** Results show arm totals, never which card came from which arm.

## 5. Users and entry

- **Graders:** the operator plus 1–2 testers (value-core [prd.md Q4](../value-core-engine/prd.md#8-open-questions-lead-to-take-to-the-operator-before-build)).
- **Audience gate:** two conditions, both required:
  1. **The tester allowlist.** The account is in `config/tester_allowlist.json` ∪ `FTF_TESTER_ALLOWLIST`, read by `experiments.load_tester_allowlist`, `experiments.py:120`.
  2. **The overlay.** The account receives `grading.blind = true` through the `calibration_rollout` overlay experiment, which targets `is_tester_allowlist` ([lld.md §8.2](lld.md#82-the-calibration_rollout-overlay)).
- **Entry:** the **Calibration** tab, third in the bar: Rank · Acquire · Calibration · Matches · League.
  - It is present only when the app's merged flag map says `grading.blind` at launch, read once at mount like every other tab-presence decision (`TabNav.tsx:700-718`).
  - The server checks the same per-caller flag **and** the allowlist on every call.
- **League:** always the app session's active league.

## 6. User flow

1. **Calibration tab.**
   - With an open session for the active league: **Resume (k of N answered)**.
   - Otherwise: a two-sentence explanation and **Start**.
2. **Start.** The server builds the session in up to ~15 s, behind a spinner.
   - If the grader's latest Acquire deck for this league is missing, older than 7 days, or has fewer than 10 usable cards, the screen says: "Open Acquire for this league first so there's a fresh deck to compare against, then come back." An **Open Acquire** button switches to the Acquire tab.
3. **Grading.** One card at a time:
   - progress "12 / 38";
   - the partner's name;
   - "You give" and "You get" lists: each asset with its position badge (or PICK), NFL team, age and value;
   - a total per side.

   Below the card:
   - the prompt "Would you send this?";
   - five buttons, 1–5, with the ends labelled "No way" and "Send it";
   - seven optional tag chips: Overpay · They won't accept · Junk filler · Too small · Wrong for my window · Wrong for their window · Same guy again;
   - **Next**, enabled once a grade is picked;
   - **Skip**.
4. **Results.** After the last answer, the screen reveals two blocks, **Today's engine** and **New engine**. Each shows cards, graded, skipped, average, the share graded 4 or 5, and top reasons. A line notes how many trades both engines suggested; those count for both. **Done** returns to the intro, which offers a fresh **Start**.
5. **Leaving and coming back.** Switching tabs mid-session keeps the place. Relaunching offers **Resume**.

## 7. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | **Server gate**, checked before anything else, including the verified-session gate, on every `/api/grading/*` route. The caller must pass both: **(a)** `grading.blind` resolves true for them (the global flag, overlaid by their device and account experiment overlays, the same merge as `/api/feature-flags`); **(b)** `_calibration_allowed(sess)`, the ONE audience predicate (tester allowlist on session user id or league user id). Otherwise 404 `{"error":"not_found"}`. |
| FR-2 | Opening Calibration to everyone later takes two changes: `_calibration_allowed` returns `True` (one line), and `grading.blind` is set true globally or the overlay is retargeted. |
| FR-3 | `POST /api/grading/sessions {league_id}` builds a session for the caller's own team in the session's active league. It resumes an open session for the same user and league rather than creating a second one. |
| FR-4 | **Current arm.** Up to 20 cards from the caller's latest served legacy deck for the league ([hld.md §3.1](hld.md#31-current-arm-todays-engine)).<ul><li>"Latest deck" is the newest job with qualifying rows. A qualifying row is not a ghost, not value core, not unattributed (a likes-you injection), not a standing offer, and not from an intent-filtered deck.</li><li>Take the first 20 by served position, then drop any whose assets have since left the respective rosters.</li><li>A deck that is missing, more than 7 days old, or has fewer than 10 usable cards ⇒ 409 `needs_fresh_deck`.</li></ul> |
| FR-5 | **Value-core arm.** The first 20 entries of `value_core.pipeline.run` with `CoreConfig()` / `RankConfig()` defaults, for the same seat.<ul><li>Inputs come from the same DB reads the bench uses (`value_core_bench.read_league_inputs` → `league_record` → `snapshot_for_seat`).</li><li>Standings come from the server's fail-soft `_value_core_standings`; lineup slots and roster limit come from the serving helpers.</li><li>The caller's untouchables and not-interested lists apply, as in serving.</li><li>Fewer than 10 cards ⇒ 409 `value_core_too_few`.</li></ul> |
| FR-6 | A trade in both arms (same partner, same give ids, same receive ids) becomes ONE card, credited to both arms. |
| FR-7 | Order is a shuffle seeded by a per-session secret seed. Card and session ids are random 18-digit decimal strings. |
| FR-8 | Every card payload comes from ONE neutral formatter, with keys exactly `{partner_name, give, receive}`. Each asset has exactly `{id, name, position, nfl_team, age, value}`, and `value` comes from the session's single consensus catalog. |
| FR-9 | `GET …/current?league_id=` returns the open session or `null`. `GET …/<id>/next` returns the lowest-position unanswered card, or `{done: true}`. |
| FR-10 | `POST /api/grading/cards/<id>` takes `{grade: 1–5, tags?: [...]}` or `{skip: true}`, with tags from the fixed 7. Re-answering overwrites. The last answer completes the session atomically. Any answer after completion ⇒ 409 `session_completed`. |
| FR-11 | `GET …/<id>/results` works only for a completed session; otherwise 409 `session_incomplete`. Per arm it returns cards, n, skipped, mean, share ≥ 4 and tag counts. A shared card counts for both arms. |
| FR-12 | `GET /api/admin/grading/report` (`X-Cron-Secret`) aggregates completed sessions per arm: overall, per grader, per session. Optional `since` and `include_open`. Not flag-gated. |
| FR-13 | Grading writes only `grading_sessions` and `grading_cards`. It never registers a `TradeCard`, logs an impression, records a swipe or touches Elo. |
| FR-14 | Account deletion removes both tables' rows, and the data export includes them. |
| FR-15 | **Mobile.** A new bottom tab **Calibration** (`CalibrationStackNav` → `CalibrationHome` → `CalibrationScreen`, testID `tab.calibration`) in the third slot.<ul><li>Presence is decided once at mount from `grading.blind`. It takes the slot ahead of Draft: `showCalibrationTab ? Calibration : showDraftTab ? Draft : none`.</li><li>Taps are tracked with `trackTab('calibration', …)`.</li><li>As a tab-stack screen it mounts **no** FeedbackFAB; RootNav's global mount covers it.</li><li>It uses a dedicated minimal `GradingCard`, not `TradeCard`. Only `GradingResults` names an arm. Chalkline tokens and primitives only.</li></ul> |
| FR-16 | **Draft tab off.** `draft.tab` → false in `config/features.json` and every flags fixture that carries it. The Draft tab's code is unchanged. The Draft Room stays reachable from League › Rookie draft and the Acquire Draft chip. |

## 8. Gate 2 readout (success metrics)

The lead reads `GET /api/admin/grading/report` once the graders are done.

| Quantity | Reading |
|---|---|
| `overall.arms.value_core.mean` vs `overall.arms.current.mean`; `overall.delta_mean` | **The Gate 2 question:** does the value core grade as well as today's engine? |
| `…share_ge_4` per arm | The share of cards the grader would actually send |
| `…tag_counts` per arm | Why cards lose: overpay, window fit, junk filler, and so on. This feeds value-core tuning. |
| `by_grader[*].delta_mean` | Whether the verdict holds per grader or only in aggregate |
| `overall.shared` | How much the engines overlap. Shared cards count for both arms, which narrows the gap. |

**Minimum sample before a verdict:** ≥ 40 graded cards per arm overall, which is about two complete sessions. The parent PRD's targets frame the decision: value-core mean ≥ 4.0, clearly above the incumbent ([../value-core-engine/prd.md §6](../value-core-engine/prd.md#6-success-metrics)). The verdict is the lead's and the operator's. The report computes no pass/fail.

## 9. Rollout and kill switch

1. **Build dark.** `grading.blind` false globally. Full suite green. TestFlight build with P3. Calibration is new client code, so a release is required.
2. **Draft tab off.** It ships in the same merge (`draft.tab` → false). After the deploy, `POST /api/feature-flags/reload`. The tab disappears at each user's next launch.
3. **Allowlist.** The operator adds each grader's account id to `config/tester_allowlist.json` (deploy).
4. **Overlay on.** Create and launch `calibration_rollout` ([lld.md §8.2](lld.md#82-the-calibration_rollout-overlay)). Each grader sees Calibration after the next flag fetch plus a relaunch.
5. **Keep `trade.value_core` off while grading** ([D2](#11-decisions)).
6. **Grade.** Graders open Acquire for a league, then Calibration.
7. **Read.** The lead pulls the report and records the Gate 2 outcome in `living-memory/DECISIONS.md`.
8. **Off.** Stop `calibration_rollout`. The data and the report remain.

**Kill.** Stop the experiment, which is deploy-free. Server routes 404 within the 60 s experiment cache, and the tab goes at the next launch.

**Draft-tab rollback.** `draft.tab` → true, then reload. It returns at the next launch for everyone except testers who still have Calibration.

## 10. Risks and residuals

- **Familiarity leak, the largest residual.** The current arm is, by design, the deck the grader just opened in Acquire. A grader who studied it may recognise its cards, and every recognised card is a current-arm card.
  - Mitigations: brief graders to open Acquire just long enough for it to load, and to prefer leagues they haven't studied. The 20-card cap keeps half the session novel.
  - It cannot be engineered away without generating a hidden legacy deck server-side. That would mean the 13–60 s trade job inside the grading request ([hld.md §7](hld.md#7-performance)), which this spec rejects.
- **Card properties hint at the engine.** Value-core cards always sit inside its band (give at most +20%, take at most +10%); legacy cards may not. Value totals hint at the engine. That is inherent to what is being graded.
- **Sync worker blocked during creation.** The value core runs inline (budget 8 s, typically 1–4 s) plus the Sleeper standings and meta fetches. Render runs one sync worker, so requests serialise (`render.yaml:16`). Acceptable for 1–3 graders ([D5](#11-decisions)).
- **Value-core inputs follow the bench path, not the live session.**
  - The board comes from `member_rankings`, without the placement clamp.
  - Picks are priced at the stored `draft_picks.pool_value` and labelled "2027 1st (from X)", without the D-090 slot.
  - Consensus comes from the latest `player_value_history` snapshot.

  This matches Gate 1, and both arms display the same catalog values. It is not byte-equal to value-core serving.
- **The data export reveals arms.** A grader who downloads their own data mid-session sees `arms_json`. Accepted; brief graders.
- **Draft-tab loss for users.** Anyone who used the Draft tab now goes through League › Rookie draft or the Acquire chip. It is outside draft season, and the switch is seasonal by design (`config/features.json:229`).
- **Overlay layer occupancy.** Experiment layers bucket exclusively, and `onboarding` and `growth` are full (`../ram-mascot/experiment.md §3`). `calibration_rollout` needs a free layer ([D3](#11-decisions)).
- **Bench bug found while specifying this.** `value_core_bench._freeze_league` filters `draft_picks … AND source = 'platform'` (`value_core_bench.py:245-247`), but the platform sync leaves `source` NULL (`database.py:11074-11085`; `sync_draft_picks` never sets it). **The frozen Gate 1 bench very likely has no picks.** P1 fixes the predicate ([lld.md §5](lld.md#5-bench-refactor-backendevalvalue_core_benchpy)). Re-freeze ([D6](#11-decisions)).

## 11. Decisions

**Confirmed by the operator, 2026-10-02:**
- the entry is a **Calibration** tab in the Draft slot, replacing the Settings › Testing row;
- the Draft tab is removed by `draft.tab` → false, with its code kept;
- the audience is testers only: `grading.blind` per user via the allowlist overlay, plus the server allowlist predicate.

**Still the lead's call:**

| # | Decision | Recommendation in this spec |
|---|---|---|
| **D1** | Which legacy job is "the latest deck" | **The newest job that has qualifying rows**, not simply the newest job. Pinned, partner and intent decks carry `model_arm` NULL or `trade_intent` set (`bakeoff_runner.py:455-467`, `server.py:5428-5458`). Otherwise one "what can I get for X" search would force a 409. |
| **D2** | Grading while `trade.value_core` is on for testers | **Don't.** Run Gate 2 before tester-live, with the flag off as it is today. Otherwise the 7-day freshness rule fails for allowlisted graders, whose decks would then be value-core decks. |
| **D3** | Layer and unit for `calibration_rollout` | **Account unit,** so the server resolves the overlay from the session alone. The client also sends `X-Device-Id` on grading calls, so a device-unit overlay would resolve too. The layer must have free buckets: check `GET /api/admin/experiments` before creating. `ranking` or `engine` are likely candidates, since `onboarding` and `growth` are occupied. |
| **D4** | Should the admin report be flag-gated? | **No.** Cron secret only, so results stay readable after the kill. |
| **D5** | Inline vs background session creation | **Inline** (simplest). The mobile timeout goes to 30 s (`client.ts:249`). Revisit only if creation exceeds ~10 s on Render. |
| **D6** | Bench pick-source bug | Fix it in the extracted reader (P1). Count the PICK assets in the frozen file. If there are none, re-freeze and re-run the Gate 1 guardrails. |
| **D7** | Tag vocabulary | This spec's set (`they_wont_accept`, `wrong_for_my_window`, `wrong_for_their_window`, …). The CSV `TAGS` (`blind_grade.py:30-31`) uses `never_accept`, `wrong_my_window`, `wrong_their_window`. Leave the CSV alone, or align it later. |
| **D8** | Value-core configuration | **Dataclass defaults:** `CoreConfig()`, `RankConfig()`, standings weight 0.30, i.e. the bench "default" variant. The alternative is the live `vc_*` knobs (`adapter.core_config_from(trade_service._cfg)`), if `model_config` was tuned after Gate 1. Either way, the config is recorded in `source_json`. |
| **D9** | Analytics | **Waiver (c)** for grading events; `tab_selected` gains `calibration` ([scope.md §1](scope.md#1-analytics-scope)). Needs the operator's yes. |

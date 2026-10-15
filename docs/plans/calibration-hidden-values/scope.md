# Feature Scope — Calibration hidden-values variant (D-W5)

**Date:** 2026-10-15
**Entry point:** direct ask. `head-product` ruling P24 (2026-10-15): "Yes, draft the D-W5 scope block (hide values and totals on 50% of Calibration cards from round 4). It's scope only; the build needs models-lead and analytics-lead review." D-W5 is option A of the joint eval plan, which `models-lead` agreed.
**Owner:** `trades-pm`, who owns grading content. **Builder:** `rankings-eng`, via `head-eng`. Nothing is built from this file until the §7 reviews are in and `head-product` gives the go.
**Operator sign-off on waivers:** not needed (no waivers).
**Status:** scoping, 2026-10-15. Scope only, no code.

**Sources.**
- **Code:** citations are to `origin/main` at `678834ab`.
- **"Eval plan":** `docs/plans/trade-model-vs-ktc/eval-plan.md` on `origin/plan/trade-model-vs-ktc` at `0063f895` (a draft PR, not on main).
- **"T1–T4":** `models-lead`'s four read thresholds for D-W5, in §4.2 of its wave-2 working file (`docs/plans/org-bringup/leads/models-lead-wave2.md`). That file is uncommitted and not on origin. This scope cites the thresholds by number and doesn't restate them.

## Why

- The Calibration card shows FTF's value on every asset and a total under each side.
- Graders anchor on those numbers. That biases any test of whether another value board predicts their verdicts better than FTF's: the test tilts toward FTF's board (eval plan §1.3, bias 1, :86).
- Option A hides values and totals on a random half of the cards, from round 4. That half gives labels free of anchoring, and the gap between hidden and shown would-send measures the anchoring itself (eval plan §4.3, :294-350).

---

## 0. Behavior (what changes for whom)

| Who | Before | After |
|---|---|---|
| Graders in a session created while the setting is on (round 4 onward, in rounds that judge value boards) | Every card shows a value per asset and a TOTAL per side | About half the cards show neither. The rest look exactly as today. Nothing says which kind a card is |
| Graders in any other session (rounds 1–3, and later rounds with the setting off) | as today | **Unchanged**, byte for byte |
| Everyone else | — | Nothing. Calibration is the only surface touched |

### 0.1 The display condition

- **Two values.** Every card written while the setting is on gets one display condition: `values_shown` or `values_hidden`.
- **Assigned when the card row is first written.** That happens in the build (`blind_grading.build_session`, `backend/blind_grading.py:256-262`) or in a fit-arm fold (`add_fit_arms`, :174-179).
- **It never changes after that.** That holds through:
  - resume and re-answer;
  - a later fold that merges another arm into the card (:163-167);
  - a change to the setting;
  - a retire.
- **`unassigned`.** Cards written while the setting is off carry no condition. They render exactly as today. Every card from rounds 1–3 is in this bucket.

### 0.2 Balance rule (stratified per session)

- **Stratum.** A card's stratum is its arm signature when written: the set of arm keys in its `arms_json`.
  - A shared card (one with several arms, `blind_grading.py:726`) forms its own stratum, for example `{current, value_core}`.
- **Split.** Within each stratum, among the cards that one write creates, exactly floor(n/2) or ceil(n/2) are `values_hidden`. When n is odd, the session seed decides the last card.
- **Randomness.**
  - Assignment is random within the stratum, drawn from the session seed.
  - It is **independent of card position**, so fatigue and order effects fall equally on both conditions.
  - It draws from its own stream off the seed, and **it does not change today's card order for a given seed**. Today the order comes from `shuffle_cards` (:647-651) and the fold's `seed ^ 0x5F17` (:184).
- **What it guarantees.**
  - Within a session, each arm's hidden and shown counts differ by at most:
    - the number of strata that arm appears in, plus
    - the number of existing cards a fold merged that arm into. Those cards keep their earlier condition.
  - Across a round, every arm is close to 50/50 in every grader's sessions.
  - That is what T3 needs: Q-C read across both conditions, balanced by arm.
- **Blinding.** Each arm's cards are split evenly, so the condition says nothing about which engine made a card. This is eval plan requirement 2 (:339).

### 0.3 What a hidden card hides

Every element on or behind the card that carries FTF's valuation:

| # | Element | Where | On a `values_hidden` card |
|---|---|---|---|
| 1 | Per-asset value: the `data` text at the right end of each asset's meta row | `mobile/src/components/GradingCard.tsx:53` | **Hidden.** Nothing in that slot |
| 2 | The "—" shown for a null value | `GradingCard.tsx:53` | **Hidden.** No placeholder either, since "—" would read as "value withheld" |
| 3 | The "TOTAL" label and each side's sum | `GradingCard.tsx:66-69`, summed by `sumValues` at :33-34 | **Hidden.** The whole footer goes. Not "TOTAL —" |
| 4 | Order within each side, highest FTF value first | `blind_grading.neutral_trade` sorts by (−value, name, id), `backend/blind_grading.py:627-630`; `docs/data-dictionary.md:1958` | **Hidden.** Each side is served in a value-free order. Proposed: name A–Z, then id. `design-lead` may choose another value-free key (decision 5) |
| 5 | The `value` field on every asset in the wire payload | `trade_json` is served verbatim by `next_card` (`blind_grading.py:306-308`) as `GradingAsset.value` (`mobile/src/api/grading.ts:46`) | **Hidden.** A hidden card's payload carries no FTF value in any form. It is neither rendered nor sent |
| 6 | Fairness meters, value bars, verdict pills, tier chips | **Not on this card.** It is deliberately not `TradeCard` (`GradingCard.tsx:9-16`), and `mobile/tests/check-blind-grading.js:73` already bans `fairness`, `valuation`, `composite` and `score` from it | Nothing to hide. They must stay absent |
| 7 | Position badge, or the `PICK` badge | `GradingCard.tsx:48-50` | **Stays.** It encodes position, not value |
| 8 | Pick name, e.g. "2027 1st (from Kim)" | `blind_grading.pick_label`, `blind_grading.py:422-429` | **Stays.** The round is part of the asset's identity, not FTF's price. There is no slot or tier in the name |

**What stays on both conditions:**
- the partner name (`GradingCard.tsx:78-79`) and player names (:46);
- team and age (:39-43, :51);
- position badges and pick names;
- the give-left / get-right columns (:83-87).

**What can't be hidden on the card.** These are caveats for the read, not build items:
- **Cross-card memory.** Shown and hidden cards share a session, and the same players recur. A grader may remember a value from a shown card, so "hidden" means "not on this card", not "never seen".
- **The rest of the app.** Graders see FTF values in Rank and Acquire.
- **The deck itself.** Every arm serves only trades that are fair by C0, FTF's consensus board (bias 2, eval plan :87).

All three pull the shown-vs-hidden gap toward zero, so T1 measures the effect of values *on the card*. Decision 6 asks `models-lead` to accept that reading.

### 0.4 Never labelled

- **The card.** Nothing tells the grader that a card hides its values: no copy, badge, icon, color, placeholder or accessibility text. The missing numbers are the only difference.
- **VoiceOver.** On a hidden card it reads no FTF number. The card sets no accessibility labels today (`GradingCard.tsx:36-90`), so this holds as long as the hidden branch adds none that carry a value.
- **Results.** Unchanged:
  - `GET /api/grading/sessions/<id>/results` and `GradingResults.tsx` carry no condition key, count or split;
  - Would send per arm pools both conditions, as today (`GradingResults.tsx:44-65`; `blind_grading.results`, :328-339).
- **Other routes.** `SessionView` (`session_view`, :696-703), `GET /api/grading/sessions/current` and `POST /api/grading/sessions` carry no condition.
- **One allowed exception.** A single neutral intro line (for example, "Some cards show values, some don't.") is allowed only if `design-lead` and `ux-lead` approve it (decision 5; eval plan §4.3, requirement 4, :341). It is static intro copy, never shown per card.
- **Layout.** The hidden layout uses Chalkline only, and `design-lead` reviews it. Shown cards render exactly as today, so round-4 shown cards stay comparable with rounds 1–3.

### 0.5 Storage keeps the values

- `trade_json` is stored exactly as today under both conditions: every asset's C0 value, sides sorted by value (`docs/data-dictionary.md:1958`).
- E-1a scores cards from it (eval plan :63).
- Hiding happens only in the copy served to the grader (eval plan requirement 1, :337).

### 0.6 How a round turns it on

- **One global setting.**
  - It is read when a session is created (`start_session`, :63-96, which `pregenerate` at :205-233 and the targeted rebuild also call).
  - It is recorded in that session's hidden provenance (`source_json`).
  - It applies to every card the session ever gets, including cards a later fit-arm fold adds.
- **Default off.** Off is byte-identical to today: no condition stored, the same payloads, the same report keys.
- **Deploy-free.** A prod config write flips it, with no deploy.
  - On means the 50/50 rule in §0.2.
  - A different share would be a new scope change, reviewed by `models-lead`.
- **The same for every grader.** It must not be a per-device or per-account flag overlay. (`grading.blind` resolves per caller that way, `backend/server.py:27033`.) If some graders were in the variant and others not, every per-grader read would be confounded.
- **Proposed mechanism:** a `model_config` key. Eng decides (decision 2).
- **Round boundaries only.**
  - Nothing changes inside round 3 (D-W3; eval plan §4.2, :292).
  - Round 4 is the first round with it on: `models-lead` asked to start then, before D-W1 or D-W6 settle (eval plan :319).
  - For each later round, `models-lead` says whether the round judges value boards, and that decides on or off (decision 8).
- **Opening round 4.**
  - The setting goes on.
  - Unanswered round-3 sessions are retired and rebuilt with the existing targeted `"rebuild": true` (`docs/runbook.md:513`), so every round-4 deck carries conditions.
  - A session with any answered card keeps running as round 3 (`unassigned`).
  - `report?since=<round-4 date>` separates the two by session `created_at`.

### 0.7 App builds that predate this feature

**The problem.**
- An older build renders a hidden card's missing values as "—" on every row and "TOTAL 0" (`GradingCard.tsx:33-34,53`; eval plan :338). **No pre-feature build may display a hidden card.**
- On today's build, any non-404 error from `/next` leaves the screen on a spinner for good: phase `grading` with no card (`mobile/src/screens/CalibrationScreen.tsx:293-304,412-419`).
- A 404 lands on "Not available" (:296, :311-316).

**Two ways to prevent it** (decision 3):
- **Recommended: a server check.**
  - `next_card` reads `X-App-Version`, which every client sends (`mobile/src/api/client.ts:57-58`).
  - It refuses a hidden card to builds below a minimum that `rankings-eng` names, and the card stays unanswered.
  - The refusal's status code decides what an old build shows: a 404 gives "Not available", anything else the spinner.
- **Alternative: an upgrade check.** Round 4 opens only once the operator confirms every active grader is on the new build.

---

## 1. Analytics scope

- [x] **(b) Existing grading storage covers it.** No new event, no new event property, and no taxonomy grant is requested.
  - **The record.** `grading_cards` (`grade`, `skipped`, `tags_json`, `graded_at`) plus the one new stored field in §2, read through `GET /api/admin/grading/report`. The blind-grading scope made the same choice for all grading data (`docs/plans/blind-grading/scope.md` §1).
  - **Why no event.** A client event would duplicate the table. A per-card condition on an event would also put the condition into the analytics stream, joinable to a user.
  - **If `analytics-lead` wants one anyway,** it is a request for its grant: registered in `backend/analytics_taxonomy.py` and classified in `analytics_queries.NON_INTENT_EVENTS`, both in the emitter's commit. None is specced here.
  - **Existing events, unchanged:**
    - `tab_selected`;
    - `screen_viewed` / `screen_left` (`CalibrationHome`);
    - `api_request_failed`: an old-build refusal (§0.7) shows up here as a failed `/next` call, with ids folded to `:id`.

**Metric definitions for `analytics-lead` to confirm before round 4 opens** (decision 7):

| Metric | Definition | Cut by |
|---|---|---|
| **Would-send by condition** | Share of non-skipped grades ≥ 4 (`share_ge_4`, `blind_grading.summarize`, :706-714). Yes = 5 and No = 1 (D-208). A legacy 1–5 answer counts as Yes at ≥ 4, so a legacy 3 counts as No (eval plan bias 5, :90) | condition × arm × grader. Shared cards are attributed by `arms_json` (bias 3) |
| **Skip rate by condition** | Skipped ÷ cards, per condition per grader. T4, the pre-registered uneven-skip check, reads it | condition × grader (× arm, descriptive only) |
| **Time-to-grade by condition** (secondary, descriptive) | Seconds between a card's `graded_at` and the previous answered card's `graded_at` in the same session. Two exclusions: the session's first card, and gaps above a break cap (proposed: 10 minutes). Re-answering overwrites `graded_at` (`docs/api-reference.md:1124`) | condition × grader: median and n |
| **Balance** | Hidden vs shown cards per arm, per session and overall | condition × arm |

- **Timing needs no new column.**
  - A cleaner measure, a per-card first-served time, would be a second schema field and a scope change. Take it only if `analytics-lead` asks.
  - Otherwise the derived gap is enough for a descriptive read, or `analytics-lead` drops the metric.
- **Tags are reported by condition** (eval plan :333). On a hidden card, "Overpay" is the grader's own valuation, not a reaction to FTF's numbers.

## 2. Schema & flag scope

### New columns: one per-card field on `grading_cards`

- **Values:** `values_shown` | `values_hidden`.
- **Null** means `unassigned`: the card was written while the setting was off, shows values, and isn't randomized.
- **Column vs JSON is eng decision 1** (`rankings-eng`, with `head-eng`'s review):

| Option | Shape | For | Against |
|---|---|---|---|
| **A (trades-pm's preference)** | New nullable column `grading_cards.display` (String) | `models-eng`'s reads (E-1a, E-3) can query it in plain SQL. One value, one meaning | Needs a `migration_cols` entry (`backend/database.py:3354`) on SQLite and Postgres, and an update to `test_blind_grading_db.py::test_tables_created_with_expected_columns` (:65) |
| B | New nullable column `grading_cards.display_json` (Text), e.g. `{"values": "hidden"}` | Room for later display variants without another migration | JSON parsing on every read. The extensibility is speculative |

**Rejected:**
- **A key in `arms_json`.**
  - `arm_summaries` treats every key as an arm, and counts a card with more than one key as shared (`blind_grading.py:726,729`). A non-arm key would mark every card shared.
  - `arms_json` holds per-arm provenance, and the condition is per card.
- **A key in `trade_json`.** It is both the C0 store E-1a scores from and the served payload. Mixing a display flag into it invites leaking the flag, or the values.
- **A per-card map in the session's `source_json`.** It isn't per card, and the fit-arm fold rewrites `source_json` (`add_fit_arms`, :191-196).

### Other schema and flags

- **Session-level record.** `grading_sessions.source_json` gains the setting in force when the session was created, e.g. `display: {rule, version}`. That lets the report tell randomized sessions from unassigned ones, and lets a fold apply the session's own setting. It is a JSON key, so no migration.
- **Privacy coverage is unchanged.** Both tables are already in `accounts._ADDITIONAL_PRIVATE_TABLES`, so account deletion and export cover the new field (`docs/plans/blind-grading/scope.md` §2).
- **New or changed feature flags: none.**
  - A flag resolves per caller and could split graders (§0.6).
  - `grading.blind` (`config/features.json:277-278`) stays the kill switch for Calibration as a whole.
- **New `model_config` keys: one, if eng picks that mechanism (decision 2).**
  - Proposed: `grading_hidden_values` (Float: 0 off, 1 on; default 0). `model_config`'s value column is a Float.
  - **Rollback lever:** set it to 0. New sessions stop getting conditions, and existing cards keep theirs.

### Doc rows (written at build)

- **`docs/data-dictionary.md`:**
  - the new field on `grading_cards`;
  - the `source_json` key (:1942);
  - the `trade_json` row (:1958), which is no longer "served verbatim" for hidden cards;
  - the hidden-columns paragraph (:1926), because `next_card` becomes a reader of the condition.
- **`docs/config-reference.md`:** the `model_config` row.
- **`docs/api-reference.md`:** see §4.

## 3. Evidence scope

**Structural guard.**
- [x] New `mobile/tests/check-calibration-hidden-values.js`, run with `npm run test:calibration-hidden-values`.
  - It is live in CI: `mobile-typecheck` runs every `tests/check-*.js` (`.github/workflows/ci.yml:47`).
  - It needs nothing beyond the `typescript` parser that `check-blind-grading.js` already uses.
- **It pins:**
  1. **Values and totals live in the shown branch.** In `GradingCard.tsx`, each of these render sites sits inside the shown branch of the card's display condition:
     - an asset value;
     - the "—" placeholder;
     - `sumValues`;
     - the `TOTAL` literal.

     The check is an AST walk: each such JSX node needs a conditional ancestor that tests the condition. So a hidden card renders none of them.
  2. **The shared fields are outside it.** Name, position badge, team and age render outside that branch, so both conditions show them.
  3. **No label names the condition.** No string literal or JSX text in `GradingCard.tsx`, `CalibrationScreen.tsx` or `GradingResults.tsx` matches a pattern such as `/hidden|values? (are )?(hidden|shown)/i`. The one exception is the intro line, if decision 5 approves it; that line is pinned verbatim.
  4. **Results stay clean.** `GradingResults.tsx` reads no condition field, and the `GradingResults` wire type has no condition key.
  5. **Self-test.** A planted violation (a value rendered outside the branch) must make the walk fail, as `check-blind-grading.js` assertion 0 does.
- **Same commit:** update `check-blind-grading.js`'s wire-type pin (:255-259) to the new `GradingAsset` / `GradingCard` shape, or CI fails.

**Backend pytest.**
- [x] `test_blind_grading_service.py`:
  - **Balance:** across many seeds and arm mixes, shared cards included, each stratum is split floor(n/2) / ceil(n/2).
  - **Fold:** a fold balances its new cards and never changes an existing card's condition, answered or merged.
  - **Order:** card positions for a given seed are the same as today.
  - **Setting off:** no condition is stored, and every payload is byte-identical to today (golden).
  - **Session setting:** the session records the setting, and a fold uses the session's setting, not the current one.
- `test_blind_grading_routes.py`:
  - **`/next` on a hidden card:** no asset carries a value key or any number derived from C0, and the sides come in the value-free order.
  - **`/next` on a shown card:** byte-identical to today.
  - **Other routes:** the `/results`, `/current` and `POST /sessions` responses carry no condition key.
  - **The report:**
    - it splits by condition at the overall, by-grader and session levels;
    - existing keys are unchanged;
    - per arm, the condition blocks sum to the pooled block.
  - **Old builds:** the refusal by `X-App-Version` (§0.7), if decision 3 picks it.
- `test_blind_grading_e2e.py`:
  - **Blinding walk:** extend `test_no_response_reveals_an_arm_until_results` (:259). No response before the admin report may carry a C0 value on a hidden card or name the condition.
  - **Order:** add an analogue of `test_order_is_not_blocked_by_arm` (:315): order is not blocked by condition.
  - **Persistence:** the condition holds across answer, skip, resume and fold.
- `test_blind_grading_db.py::test_tables_created_with_expected_columns` (:65) covers the new column.

**Code-walk proof.**
- [x] `docs/plans/calibration-hidden-values/code-walk.md`, written by `rankings-eng` at build and cited file:line at the build sha. It traces:
  1. the setting;
  2. `start_session` recording it in `source_json`;
  3. `build_session` and `add_fit_arms` assigning by the §0.2 rule;
  4. the card row storing it;
  5. `next_card` stripping values and reordering for hidden cards;
  6. the old-build guard;
  7. `GradingCard`'s hidden branch;
  8. `answer_card`, untouched;
  9. `report` splitting by condition;
  10. `results` never reading the condition.

**Manual TestFlight checklist** (the operator).
- [x] Phase A runs before round 4 opens; phase B on the first round-4 deck.

*Phase A: the new build, setting still off (before round 4 opens).*
1. Calibration → Start or Resume. **Expected:** every asset row shows a number at its right end, each side ends with a TOTAL row, and assets in each side run highest number first, exactly as on 1.21.x.
2. Answer a few cards, then finish or leave. **Expected:** nothing differs from 1.21.x, results included.

*Phase B: round 4 open, setting on, a new round-4 deck.* Answer honestly: these cards are round-4 data.

3. Grade the first 10 cards. **Expected:** both kinds appear, cards with numbers and TOTAL rows and cards with neither, roughly half each.
4. On a card without numbers, check each row:
   - Player rows show name, position badge, and team · age.
   - Pick rows show the pick name and PICK.

   **Expected:** nothing at the right end of any row (no number, no "—"), no TOTAL row, and the layout `design-lead` specified.
5. Same card. **Expected:** nothing on the screen says the values are hidden, missing or withheld: no label, badge, icon or color change. The only exception is the one intro line, if approved.
6. Same card. **Expected:** each side follows the value-free order `design-lead` picked (default: A–Z by name), not highest value first.
7. Turn VoiceOver on and swipe through a card without numbers. **Expected:** the only numbers read aloud are ages and pick years.
8. On a card with numbers. **Expected:** it looks exactly as in step 1.
9. Answer three cards:
   - Yes on a card without numbers;
   - No with "Overpay" on a card with numbers;
   - Skip on a card without numbers.

   **Expected:** each one saves, progress rises by 1 each time, and no error toast appears.
10. Leave the tab mid-deck, then resume. **Expected:** the card you come back to is the same kind as when you left it.
11. Finish the deck. **Expected:**
    - The results screen matches 1.21.x: per engine, Would send, Cards, Answered, Skipped and Top reasons.
    - Nothing counts or splits cards by whether numbers were shown.
12. Run `GET /api/admin/grading/report?since=<round-4 date>&include_open=1` (X-Cron-Secret; `docs/runbook.md` § Gate 2). **Expected:**
    - The step-9 cards appear under the right condition: grade 5; grade 1 with overpay; and a skip.
    - Each arm's hidden and shown counts are close, within §0.2.
    - The pooled `arms` block equals the condition blocks summed.
13. Only if a device still runs a build from before this feature: open a round-4 deck on it. **Expected:** no card shows "—" on every row with "TOTAL 0". Instead you get the behavior decision 3 picked.

**testIDs.** None required. If eng adds one, it must be a static `calibration.`-namespaced literal, and it joins `REQUIRED_IDS` in `check-blind-grading.js` (:186), which pins the set exactly.

## 4. Docs scope

Every row below is written by `rankings-eng` with the build.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **update at build** | <ul><li>`GET /api/grading/sessions/<id>/next` (:1123): the hidden-card payload and the old-build refusal.</li><li>`GET /api/admin/grading/report` (:965): the condition split.</li><li>`GET …/results` (:1125): states that it carries no condition.</li><li>`POST /api/grading/sessions` (:1121): the session records the setting.</li></ul> |
| `living-memory/LLD.md` | n/a | No cross-cutting convention shifts. The serve-time strip is local to `blind_grading.next_card`, and it is recorded in the data dictionary and the blind-grading change-control line |
| `docs/architecture.md` | n/a | No module added or rewired |
| `living-memory/HLD.md` | n/a | No new module, client or major flow |
| `docs/cross-client-invariants.md` | **update at build** | § Calibration tags and scale (:1283). The neutral-card-keys line (:1299) gains the hidden-card shape and the condition vocabulary `values_shown` / `values_hidden`, which are server-side and never rendered |
| `docs/glossary.md` | **update at build** | A "display condition (Calibration)" entry, next to "Grading card" (:576) |
| ADR or `DECISIONS.md` | **at build** | A DECISIONS entry for D-W5's outcome, under the next free D- ID. No ADR: there is no architectural choice |
| `docs/data-dictionary.md` | **update at build** | The §2 rows |
| `docs/config-reference.md` | **update at build**, if decision 2 picks `model_config` | The key's row |
| `docs/runbook.md` | **update at build** | § Gate 2 — Calibration (:483): turning the setting on or off at a round boundary, the round-open rebuild, and the report check |
| `docs/plans/blind-grading/specs.md` §3.3 (:446) | **update at build** | A dated change-control line. The neutral card gains a field, and hidden state gains a reader (`docs/data-dictionary.md:1926`; eval plan requirement 5, :342) |

## 5. Ship gate declaration

- **CI green** on the pushed sha: `pytest backend/tests`, `tsc --noEmit` plus every `check-*.js`, and `testid-lint`.
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming:
  - the new guard;
  - the pytest additions;
  - the code-walk;
  - the outcome of TestFlight phase A.

  The push uses `FTF_SKIP_SIM_GATE=1`, per D-056.
- **Order:**
  1. The build merges, and the new iOS build reaches graders' devices.
  2. The operator runs phase A.
  3. Round 3 closes (the D-W3 horizon: 175 cards per arm or 2026-11-05).
  4. The setting goes on, and the unanswered round-3 sessions are rebuilt.
  5. The operator runs phase B on the first round-4 deck, and the outcome is logged.
- **Express lane: no.** It touches schema, an API contract, and the data the eval reads.

## 6. Read rules (by reference)

This scope pins what is stored and reported. `models-lead` owns how it is read, and nothing here restates that:
- **When and how the condition split is read:** T1–T4 (models-lead §4.2):
  - T1: the anchoring estimate;
  - T2: board contrasts on hidden cards;
  - T3: Q-C across both conditions;
  - T4: the skip-rate check.

  The thresholds and n are in that file.
- **How hidden cards feed the decision rules:**
  - eval plan §1.5A (:140-142), which confirms or rules out K-2;
  - eval plan §1.5B (:150), which confirms R3.
- **Costs and comparability:** eval plan §4.3 (:321-333).
  - About 600 graded cards under option A for the hidden-card read point.
  - Round-4 numbers compare with rounds 1–3 only on shown cards.
  - Criterion 2 is read on shown cards only.
- **What this scope adds for the read:** the report keeps `unassigned` cards apart from `values_shown` cards. That lets the shown-vs-hidden comparison use randomized sessions only, and lets the comparison with rounds 1–3 pool `unassigned` with `values_shown`.

## 7. Reviews and build owner

| Reviewer | Reviews |
|---|---|
| `design-lead` | <ul><li>The hidden card's layout without the value slot and the footer (§0.3–§0.4), in Chalkline.</li><li>The value-free order key.</li><li>The intro line.</li></ul> |
| `ux-lead` | <ul><li>The grader flow across mixed cards.</li><li>The intro line.</li><li>What an old build shows when refused (§0.7).</li></ul> |
| `models-lead` | <ul><li>The balance rule (§0.2) against T3.</li><li>Round enablement (§0.6).</li><li>The caveats (§0.3).</li><li>The report split against T1–T4.</li></ul> |
| `analytics-lead` | The §1 metric definitions, and confirming that no event or property is needed |

**Build owner:** `rankings-eng`, via `head-eng`. The Calibration code is Rankings' area (`CalibrationScreen.tsx:433` mounts `GradingCard`).

## 8. Out of scope

- **The grade scale and the tags** (D-208; `docs/cross-client-invariants.md:1297`). That includes D-208's not-adopted "require a reason on No". If it also goes to round 4, it needs its own scope block (eval plan :292).
- **Arms:** arms per round, their configs, and the round-3 shape (D-W3; `models-eng`'s config).
- **Other surfaces:** the Acquire trade deck, `TradeCard`, the calculator and Rank. Values stay everywhere else.
- **The comparisons themselves:** E-1a, E-1b, E-3, E-4 and the decision rules (eval plan §1.5–§1.6).
- **The deck's range restriction** (bias 2): every arm still serves only trades that are fair by C0.
- **A per-card served timestamp,** unless `analytics-lead` asks for it (§1).

---

## Decisions needed

| # | Decision | Who decides | Recommendation |
|---|---|---|---|
| 1 | **Approve this scope for build** (D-W5, option A) | `head-product`, with the operator's go | Yes, once the §7 reviews are in |
| 2 | **Storage:** a `display` column or `display_json` (§2). **Round-enable mechanism** (§0.6) | `head-eng` → `rankings-eng` | A `display` column. A `model_config` Float key, read at session creation and recorded in `source_json` |
| 3 | **Old-build guard** (§0.7) | `head-eng` → `rankings-eng` | A server refusal by `X-App-Version`. Choose its status knowing that on old builds a 404 shows "Not available" and anything else a permanent spinner |
| 4 | **Round-4 open:** the setting on, plus the rebuild of unanswered round-3 sessions (§0.6) | `head-eng` → `rankings-eng`, after `models-lead` confirms that round 4 judges value boards | At the D-W3 horizon, after phase A passes |
| 5 | **Hidden layout, order key, intro line** (§0.3–§0.4) | `design-lead` and `ux-lead` | <ul><li>**Layout:** drop the value slot and the footer.</li><li>**Order:** name A–Z.</li><li>**Intro line: yes,** one neutral line, so a card without numbers doesn't read as a bug. Confused graders skip, and uneven skipping is what T4 guards against.</li></ul> |
| 6 | **Randomize per card within a session,** accepting the cross-card memory caveat (§0.3) | `head-bizops` → `models-lead` | Accept, and read T1 as the effect of values on the card. The alternative, hiding whole sessions, loses the within-grader, within-session pairing that T1 relies on |
| 7 | **Metric definitions** (§1), including time-to-grade's break cap or dropping that metric | `analytics-lead` | As specced, with a 10-minute cap |
| 8 | **Which rounds after round 4 turn it on** | `head-bizops` → `models-lead` | Decide per round, at each round boundary |

## Handoffs

Through org boxes only.

| From → to | What |
|---|---|
| `trades-pm` → `head-product` | This draft PR, and decision 1. There are no waivers |
| `head-product` → `head-bizops` → `models-lead` | <ul><li>Review §0.2, §0.3's caveats, §0.6 and §6.</li><li>Decisions 6 and 8.</li><li>Confirm round 4 for decision 4.</li></ul> |
| `head-product` → `analytics-lead` | The §1 metric definitions and the call on no new event; decision 7 |
| `head-product` → `design-lead`, `ux-lead` | §0.3–§0.4: the hidden layout, the order key and the intro line; decision 5. `ux-lead` also reviews the old-build path in §0.7 |
| `head-product` → `head-eng` → `rankings-eng` | <ul><li>Build after decision 1.</li><li>Decisions 2–4.</li><li>The §3 evidence and the §4 doc rows.</li><li>At round-4 open: the setting, the rebuild, and phase B for the operator.</li></ul> |

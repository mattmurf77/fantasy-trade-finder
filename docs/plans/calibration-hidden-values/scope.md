# Feature Scope — Calibration hidden-values variant (D-W5)

**Date:** 2026-10-15
**Entry point:** direct ask. `head-product` ruling P24 (2026-10-15): "Yes, draft the D-W5 scope block (hide values and totals on 50% of Calibration cards from round 4). It's scope only; the build needs models-lead and analytics-lead review." D-W5 is option A of the joint eval plan, which `models-lead` agreed.
**Owner:** `trades-pm`, who owns grading content. **Builder:** `rankings-eng`, via `head-eng`. Nothing is built from this file until the §7 reviews are in and `head-product` gives the go.
**Operator sign-off on waivers:** not needed (no waivers).
**Status:** scoping, 2026-10-15. Scope only, no code. **Reviews folded:** `models-lead` and `ux-lead`, 2026-10-15. **Pending:** `design-lead` and `analytics-lead` (§7).

**Sources.**
- **Code:** citations are to `origin/main` at `678834ab`.
- **"Eval plan":** `docs/plans/trade-model-vs-ktc/eval-plan.md` on `origin/plan/trade-model-vs-ktc` at `0063f895` (a draft PR, not on main).
- **"T1–T4":** `models-lead`'s read rules for D-W5. They are pasted verbatim into §6.1, so this file is their committed record.
- **Reviews of this scope at `64aaca79`.** Both files are uncommitted and not on origin.
  - **`models-lead`:** § "R.d PR #344" of its wave-2 working file (`docs/plans/org-bringup/leads/models-lead-wave2.md`). Changes C1–C5, plus answers to decisions 4, 6 and 8.
  - **`ux-lead`:** § "UX review — Calibration hidden-values variant (PR #344)" of its report (`docs/plans/org-bringup/reports/ux-lead.md`). Changes C-F1 to C-F3, plus decision 5.
  - Each change below is tagged with its reviewer and item, e.g. *(models-lead C2)* or *(ux-lead C-F1)*.

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
| 1 | Per-asset value: the `data` text at the right end of each asset's meta row | `mobile/src/components/GradingCard.tsx:53` | **Hidden.** The slot keeps its width but stays empty *(ux-lead C-F1)* |
| 2 | The "—" shown for a null value | `GradingCard.tsx:53` | **Hidden.** No placeholder either, since "—" would read as "value withheld" |
| 3 | The "TOTAL" label and each side's sum | `GradingCard.tsx:66-69`, summed by `sumValues` at :33-34 | **Hidden.** No label and no sum, not even "TOTAL —". The footer keeps its height as an empty slot *(ux-lead C-F1)* |
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

All three pull the shown-vs-hidden gap toward zero, so T1 measures the effect of values *on the card*.
- **`models-lead` accepted that reading** (decision 6). It reads T1 as the on-card effect: a lower bound on total anchoring *(models-lead R.d check 2)*.

### 0.4 Never labelled

- **The card.** Nothing tells the grader that a card hides its values: no copy, badge, icon, color, placeholder or accessibility text. The missing numbers are the only difference.
- **VoiceOver.** On a hidden card it reads no FTF number. The card sets no accessibility labels today (`GradingCard.tsx:36-90`), so this holds as long as the hidden branch adds none that carry a value.
- **Results.** Unchanged:
  - `GET /api/grading/sessions/<id>/results` and `GradingResults.tsx` carry no condition key, count or split;
  - Would send per arm pools both conditions, as today (`GradingResults.tsx:44-65`; `blind_grading.results`, :328-339).
- **Other routes.**
  - `SessionView` (`session_view`, :696-703), `GET /api/grading/sessions/current` and `POST /api/grading/sessions` carry no per-card condition, count or split.
  - The one exception is a session-level indicator the intro line needs (below).
- **The intro line** *(ux-lead C-F2; decision 5)*. Exactly one static intro line, under ux-lead's three rules:
  1. **Placement.** It appears on the intro screen only (the `intro` phase, `COPY.intro` at `CalibrationScreen.tsx:72-73`), and only when the session being opened has the setting on. It never appears on a card. With the setting off, the intro stays byte-identical to today.
  2. **Content.** It says both kinds of card exist and asks for a grade on what's shown. It never says which cards, why, or how many.
     - **Words:** `marketing-lead`, via `head-product`. ux-lead's example: "Some cards show values and some don't. Grade each on what you see."
  3. **Frequency.** It shows on every Start and Resume in round 4 and later, not once per device, so a grader who comes back mid-round still sees it.
- **What the intro needs from the server.** The intro has to know whether the session it opens has the setting on:
  - for Resume, from that session's provenance;
  - for Start, from the setting in force, which the new session will record.

  That means one **session-level** on/off indicator in a grader-facing response, for example a boolean on `GET /api/grading/sessions/current`. It is never per card and never a count. The field and route are eng's call, under decision 2.
- **Support.** `models-lead` supports the line from the measurement side: it cuts the "looks like a bug" skips that T4 guards against, and it carries no per-card information *(models-lead R.d, "Not mine")*. `design-lead`'s view is pending.
- **Layout: constant across conditions** *(ux-lead C-F1)*.
  - **The hidden card keeps today's shape.** It reserves the footer's height and the value slot's width, as empty slots: no text, no "—", no label.
  - **Why.** The Yes/No row, the reason chips and Next/Skip follow the card in the same scroll view (`CalibrationScreen.tsx:432-500`). Dropping the footer would move them up on hidden cards only. That shift would track the condition, the very variable T1 measures, and it invites mis-taps.
  - **Design.** `design-lead` specs the reserved space, in Chalkline only.
  - **Shown cards** render exactly as today, so round-4 shown cards stay comparable with rounds 1–3.

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
  - **Round 4 is on.** `models-lead` asked to start then, before D-W1 or D-W6 settle (eval plan :319). It has confirmed that round 4 judges value boards (Q-K: C0 vs C1), so round 4 opens at the D-W3 horizon once phase A passes *(models-lead R.d, decisions 4 and 8)*.
  - **Later rounds** are decided at each boundary by `models-lead`'s rule *(R.d, decision 8)*:
    - **on** while T1 is inconclusive, or while a board contrast is still open (T2 below 150 / 150);
    - **off** once T1 lands on (a), or once T2 has been read and no board contrast is pending.

    Turning it off restores criterion-2 evidence to full speed.
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

**The rule** (decision 3; trades-pm, 2026-10-15). This reconciles *models-lead C4* and *ux-lead C-F3*.
- **Refuse at the session level, with a 404.**
  - A session created with the setting on is refused, whole, to any build below the minimum. The server reads `X-App-Version`, which every client sends (`mobile/src/api/client.ts:57-58`).
  - Every card in the session is refused, whatever its condition.
  - The status is **404**: "Not available" is the only state an old build can show that ends.
  - **Never per card,** and never a status that leaves an old build spinning.
- **Why session level.** Refusing card by card would leave hidden cards unanswered for old-build graders only. That is missingness that depends on the condition, and it would bias T1 and T4 *(models-lead C4)*.
- **Exclusion.** Any session that still ends up with refusals that depend on the condition is excluded from T1, T2 and T4 *(models-lead C4)*.
- **Left to eng** (`rankings-eng`, under decision 3): the minimum build, and which routes carry the refusal.

**The new build: loading always ends** *(ux-lead C-F3)*.
- Every `/next` error ends in a state that stops loading:
  - an error message with Retry, for any non-404 error (an airplane-mode failure, a 5xx);
  - today's "Not available", for a 404 (the kill switch's state, `:296`, `:311-316`).
- Today's permanent spinner (`:412-419`) goes away.
- A guard assertion in `mobile/tests/check-blind-grading.js` pins this (§3).

---

## 1. Analytics scope

- [x] **(b) Existing grading storage covers it.** No new event, no new event property, and no taxonomy grant is requested.
  - **The record.** `grading_cards` (`grade`, `skipped`, `tags_json`, `graded_at`) plus the one new stored field in §2, read through `GET /api/admin/grading/report`. The blind-grading scope made the same choice for all grading data (`docs/plans/blind-grading/scope.md` §1).
  - **Why no event.** A client event would duplicate the table. A per-card condition on an event would also put the condition into the analytics stream, joinable to a user.
  - **If `analytics-lead` wants one anyway,** it is a request for its grant: registered in `backend/analytics_taxonomy.py` and classified in `analytics_queries.NON_INTENT_EVENTS`, both in the emitter's commit. None is specced here.
  - **Existing events, unchanged:**
    - `tab_selected`;
    - `screen_viewed` / `screen_left` (`CalibrationHome`);
    - `api_request_failed`: an old-build refusal (§0.7) shows up here as a failed call (404), with ids folded to `:id`.

**Metric definitions for `analytics-lead` to confirm before round 4 opens** (decision 7):

| Metric | Definition | Cut by |
|---|---|---|
| **Would-send by condition** | Share of non-skipped grades ≥ 4 (`share_ge_4`, `blind_grading.summarize`, :706-714). Yes = 5 and No = 1 (D-208). A legacy 1–5 answer counts as Yes at ≥ 4, so a legacy 3 counts as No (eval plan bias 5, :90) | condition × arm × grader. Shared cards are attributed by `arms_json` (bias 3) |
| **Skip rate by condition** | Skipped ÷ cards, per condition per grader. T4, the pre-registered uneven-skip check, reads it | condition × grader (× arm, descriptive only) |
| **Time-to-grade by condition** (secondary, descriptive) | Seconds between a card's `graded_at` and the previous answered card's `graded_at` in the same session. Two exclusions: the session's first card, and gaps above a break cap (proposed: 10 minutes). Re-answering overwrites `graded_at` (`docs/api-reference.md:1124`) | condition × grader: median and n |
| **Balance** | Hidden vs shown cards, per arm and per grader, per session and overall. It is a validity check on the randomization *(models-lead C5)* | condition × arm × grader |

- **Timing needs no new column.**
  - A cleaner measure, a per-card first-served time, would be a second schema field and a scope change. Take it only if `analytics-lead` asks.
  - Otherwise the derived gap is enough for a descriptive read, or `analytics-lead` drops the metric.
- **Tags are reported by condition** (eval plan :333). On a hidden card, "Overpay" is the grader's own valuation, not a reaction to FTF's numbers.
- **More than the definitions.** `analytics-lead` also owns the readout method and its validity veto: the balance check, the T4 skip-asymmetry check, and the derived time-to-grade (§7) *(models-lead C5)*.

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
  3. **No label names the condition.** No string literal or JSX text in `GradingCard.tsx`, `CalibrationScreen.tsx` or `GradingResults.tsx` matches a pattern such as `/hidden|values? (are )?(hidden|shown)/i`. The one exception is the intro line (§0.4):
     - its text is pinned verbatim, once `marketing-lead` supplies the words;
     - it renders only in the `intro` phase;
     - it renders only behind the session-level indicator.
  4. **Results stay clean.** `GradingResults.tsx` reads no condition field, and the `GradingResults` wire type has no condition key.
  5. **Self-test.** A planted violation (a value rendered outside the branch) must make the walk fail, as `check-blind-grading.js` assertion 0 does.
- **In `check-blind-grading.js`, in the same commit:**
  - Update its wire-type pin (:255-259) to the new `GradingAsset` / `GradingCard` / `GradingSession` shape, or CI fails.
  - Add an assertion that a non-404 `/next` error leads to an error phase that renders a Retry control, never the `grading` phase without a card (the spinner at `CalibrationScreen.tsx:412-419`) *(ux-lead C-F3)*.

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
  - **Other routes:** the `/results`, `/current` and `POST /sessions` responses carry no per-card condition. The only exception is the session-level indicator (§0.4), which is on exactly when the session (or, before a Start, the setting) is on.
  - **The report:**
    - it splits by condition at the overall, by-grader and session levels;
    - existing keys are unchanged;
    - per arm, the condition blocks sum to the pooled block.
  - **Old builds** (§0.7):
    - A build below the minimum gets a 404 for every card of a setting-on session, hidden and shown alike.
    - It is never refused card by card.
    - Sessions with the setting off are unaffected.
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
  6. the old-build guard, refusing whole sessions;
  7. `GradingCard`'s hidden branch with the reserved space, the intro line's gate, and the `/next` error state;
  8. `answer_card`, untouched;
  9. `report` splitting by condition;
  10. `results` never reading the condition.

**Manual TestFlight checklist** (the operator).
- [x] Phase A runs before round 4 opens; phase B on the first round-4 deck.

*Phase A: the new build, setting still off (before round 4 opens).*
1. Calibration → Start or Resume. **Expected:** every asset row shows a number at its right end, each side ends with a TOTAL row, and assets in each side run highest number first, exactly as on 1.21.x.
2. Look at the intro screen before Start or Resume. **Expected:** it reads exactly as on 1.21.x, with no line about values *(ux-lead C-F2, rule 1)*.
3. Answer a few cards, then finish or leave. **Expected:** nothing differs from 1.21.x, results included.
4. Mid-deck, turn airplane mode on, then make the app load the next card: leave the tab and come back, or reopen the deck with Resume. **Expected:**
   - Within a few seconds the screen shows an error message with Retry.
   - **Fail** on a spinner that doesn't end.

   Then turn airplane mode off and tap Retry. **Expected:** the same card loads *(ux-lead C-F3)*.

*Phase B: round 4 open, setting on, a new round-4 deck.* Answer honestly: these cards are round-4 data.

5. On the intro screen, before Start or Resume. **Expected:**
   - The one approved intro line appears, in `marketing-lead`'s words.
   - Leave the tab and come back to Resume: it appears again.
   - It never appears on a card *(ux-lead C-F2, rules 1 and 3)*.
6. Grade the first 10 cards. **Expected:** both kinds appear, cards with numbers and TOTAL rows and cards with neither, roughly half each.
7. On a card without numbers, check each row:
   - Player rows show name, position badge, and team · age.
   - Pick rows show the pick name and PICK.

   **Expected:**
   - Nothing at the right end of any row: no number, no "—".
   - No TOTAL label or sum, though the footer's space is still there, empty.
   - The layout matches `design-lead`'s spec.
8. Find two cards in a row with the same number of assets, one of each kind. **Expected:** Yes and No sit at the same height on both *(ux-lead C-F1)*.
9. On a card without numbers. **Expected:** nothing on the card or the screen says the values are hidden, missing or withheld: no label, badge, icon or color change.
10. Same card. **Expected:** each side runs A–Z by name (or the value-free order `design-lead` picks), not highest value first.
11. Turn VoiceOver on and swipe through a card without numbers. **Expected:** the only numbers read aloud are ages and pick years.
12. On a card with numbers. **Expected:** it looks exactly as in step 1.
13. Answer three cards:
    - Yes on a card without numbers;
    - No with "Overpay" on a card with numbers;
    - Skip on a card without numbers.

    **Expected:** each one saves, progress rises by 1 each time, and no error toast appears.
14. Leave the tab mid-deck, then resume. **Expected:** the card you come back to is the same kind as when you left it.
15. Finish the deck. **Expected:**
    - The results screen matches 1.21.x: per engine, Would send, Cards, Answered, Skipped and Top reasons.
    - Nothing counts or splits cards by whether numbers were shown.
16. Run `GET /api/admin/grading/report?since=<round-4 date>&include_open=1` (X-Cron-Secret; `docs/runbook.md` § Gate 2). **Expected:**
    - The step-13 cards appear under the right condition: grade 5; grade 1 with overpay; and a skip.
    - Each arm's hidden and shown counts are close, per arm and per grader, within §0.2.
    - The pooled `arms` block equals the condition blocks summed.
17. Only if a device still runs a build from before this feature: open the Calibration tab there and Start or Resume a round-4 deck. **Expected:**
    - The screen shows **"Not available"**.
    - No card ever renders, so there is no "—" on every row and no "TOTAL 0".
    - **Fail** on a spinner that doesn't end *(models-lead C4; ux-lead C-F3)*.

**testIDs.** None required. If eng adds one, it must be a static `calibration.`-namespaced literal, and it joins `REQUIRED_IDS` in `check-blind-grading.js` (:186), which pins the set exactly.

## 4. Docs scope

Every row below is written by `rankings-eng` with the build.

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **update at build** | <ul><li>`GET /api/grading/sessions/<id>/next` (:1123): the hidden-card payload, and the session-level 404 for old builds.</li><li>`GET /api/admin/grading/report` (:965): the condition split.</li><li>`GET …/results` (:1125): states that it carries no condition.</li><li>`POST /api/grading/sessions` (:1121) and `GET …/current` (:1122): the session records the setting, and the session-level indicator for the intro line.</li></ul> |
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

## 6. Read rules

This scope pins what is stored and reported. `models-lead` owns how it is read.

### 6.1 Read rules [models-lead] (C1)

**Provenance.**
- **Source:** pasted verbatim from `models-lead`'s review, § "R.d PR #344", block "Read rules to paste into §6 (C1)": `docs/plans/org-bringup/leads/models-lead-wave2.md:548-561`, an uncommitted working file.
- **The one change:** each line's leading `> ` quote marker is removed. On the blank separator lines, that leaves an empty line.
- **How to check:** the lines strictly between the two comment markers below are the block, nothing else.
  - **SHA-1 of the 14 source lines, quote markers removed** (with the final newline): `fe49ac1e44a2f22e21627cc67214d46a1083b515`. The pasted lines hash to the same value.
  - **SHA-1 of the same 14 source lines as quoted** (markers kept): `6c225e12b126c15ebb230be77600f89c71a0ef57`.
- **References inside the block:**
  - "§0.2" is this file's §0.2.
  - C2 and C3 are in §6.2.

<!-- [models-lead] C1 read rules: start -->
**Data:** answered, non-skipped cards in sessions created with the setting on (`values_shown` / `values_hidden`). `unassigned` cards never enter T1, T2 or T4. CIs are clustered by session and stratified by grader. **No interim reads.** **Horizon:** 250 answered cards per condition, or 4 weeks after round 4 opens, whichever comes first. A read at the horizon without n is **inconclusive**, and the setting stays on next round.

**T1, the anchoring estimate (primary).** The gap is would-send(shown) − would-send(hidden), grader-stratified, over the same arms. The test is two-sided. **Minimum n:** 250 answered cards per condition, with ≥ 2 graders contributing ≥ 50 per condition. *Decision rule:*
- (a) the gap's 90% CI lies inside **±10 pp** → anchoring is **small**: rounds 1–3 board contrasts regain full weight, and later board contrasts may pool both conditions, with condition as a stratum;
- (b) the gap's 95% CI excludes 0 → anchoring is **real**: board contrasts (Q-K, Q-B) are read on hidden cards only (T2), and shown-card board results, rounds 1–3 included, keep the asymmetric reading (eval-plan §1.3, bias 1);
- (c) anything else → **inconclusive**: keep the asymmetric reading and the 50% share.

At 250 per condition the 90% CI half-width is about ±7.4 pp before clustering, so (a) is reachable when the true gap is near 0. If clustering widens it past ±10 pp, extend the read to the next round, still with no interim reads.

**T2, board contrasts on hidden cards.** Q-K and Q-B are re-read on `values_hidden` cards once they reach **150 Yes / 150 No** (detectable ΔAUC about 0.08). They follow eval-plan §1.5. They confirm or rule out K-2, and they confirm R3.

**T3, Q-C across both conditions.** Arm would-send is estimated stratified by condition, balanced by arm (§0.2), with the C3 interaction rule. Graduation criteria 2 and 3 use shown cards only (C2).

**T4, skip asymmetry.** For each grader, skip rate hidden − shown. If the gap is **≥ 10 pp** for a grader, that grader's hidden cards are reported separately and leave T1 and T2.
<!-- [models-lead] C1 read rules: end -->

### 6.2 Graduation, the condition interaction, and exclusions

- **Graduation reads shown cards only** *(models-lead C2)*.
  - **Criteria 2 and 3 count only `values_shown` and `unassigned` cards.**
    - Criterion 2: operator would-send ≥ 75% on ≥ 40 cards (the O1 draft, eval plan §2).
    - Criterion 3: per-grader direction against the incumbent.
  - **Hidden cards don't count toward the 40.**
  - **Never a graduation source:** the report's pooled `arms` block and the grader's Results screen. Both mix the two conditions (§0.4; §3, step 16).
  - **Cost.** While the setting is on, criterion-2 evidence accrues at half speed. A candidate engine needs about 80 operator-graded cards to get 40 shown.
- **T3: the condition interaction rule** *(models-lead C3)*.
  - Arm differences are estimated stratified by condition.
  - If an arm's advantage over E1 **reverses sign between the conditions, or differs between them by ≥ 15 pp,** R2 (eval plan §1.5B) can't fire on that round. The engine would be winning on how FTF's values look, not on the trade.
  - The pattern is reported to `models-lead` as a finding.
- **Excluding refused sessions** *(models-lead C4)*. Any session with refusals that depend on the condition is excluded from T1, T2 and T4 (§0.7).
- **Read-side requirements** *(models-lead R.d, check 2)*.
  - **CIs** are clustered by session and stratified by grader, because cards within a session aren't independent.
  - **T1 measures a bundled treatment:** no values, no totals, *and* a value-free order (§0.3, rows 1–4). The bundle is intended, since value order leaks value.
- **Open question for `models-lead`, from `ux-lead`:** does C-F1's constant layout bear on T1?
  - ux-lead thinks it does.
  - C-F1 is adopted either way, so card height doesn't vary with the condition.
- **Comparability** (eval plan §4.3, :321-333). Round-4 numbers compare with rounds 1–3 only on shown cards.
  - The report keeps `unassigned` cards apart from `values_shown` cards. That lets T1, T2 and T4 use randomized sessions only.
  - Comparisons with rounds 1–3 can pool `unassigned` with `values_shown`.

## 7. Reviews and build owner

| Reviewer | Reviews | Status |
|---|---|---|
| `models-lead` | <ul><li>The balance rule (§0.2) against T3.</li><li>Round enablement (§0.6).</li><li>The caveats (§0.3).</li><li>The read rules (§6).</li></ul> | **Sign-off with changes, folded at `FOLDSHA`.** C1–C5 are applied (§6.1, §6.2, §0.7, and the `analytics-lead` row below). Decisions 4, 6 and 8 are answered |
| `ux-lead` | <ul><li>The grader flow across mixed cards.</li><li>The intro line.</li><li>What an old build shows when refused (§0.7).</li></ul> | **Approve with changes, folded.** C-F1 (§0.3, §0.4), C-F2 (§0.4) and C-F3 (§0.7), plus their TestFlight steps (§3) |
| `design-lead` | <ul><li>The hidden card's reserved empty space for the value slot and the footer (§0.3–§0.4, ux-lead C-F1), in Chalkline.</li><li>The value-free order key.</li><li>The intro line's placement.</li></ul> | **Pending** |
| `analytics-lead` | <ul><li>The §1 metric definitions, and confirming that no event or property is needed.</li><li>**The readout method and its validity veto** *(models-lead C5)*:<ul><li>the balance check on condition assignment, per arm and per grader;</li><li>the T4 skip-asymmetry check;</li><li>the derived time-to-grade.</li></ul></li><li>A read that `analytics-lead` rules invalid suppresses the verdict.</li></ul> | **Pending** |

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

| # | Decision | Who decides | Recommendation, or the answer where one exists |
|---|---|---|---|
| 1 | **Approve this scope for build** (D-W5, option A) | `head-product`, with the operator's go | Yes, once the §7 reviews are in |
| 2 | **Storage:** a `display` column or `display_json` (§2). **Round-enable mechanism** (§0.6). **The session-level indicator** for the intro line (§0.4) | `head-eng` → `rankings-eng` | <ul><li>A `display` column.</li><li>A `model_config` Float key, read at session creation and recorded in `source_json`.</li><li>A boolean on `GET …/current`.</li></ul> |
| 3 | **Old-build guard** (§0.7) | **Settled by `trades-pm`, 2026-10-15**, reconciling *models-lead C4* and *ux-lead C-F3*. The minimum build and the routes are `head-eng` → `rankings-eng` | <ul><li>Refuse at the session level with a **404** ("Not available").</li><li>Never per card, and never a status that spins.</li><li>The new build ends every `/next` error in a state that stops loading (Retry, or "Not available" on a 404), pinned in `check-blind-grading.js`.</li><li>Sessions with refusals that depend on the condition leave T1, T2 and T4.</li></ul> |
| 4 | **Opening round 4:** turn the setting on and rebuild the unanswered round-3 sessions (§0.6) | `head-eng` → `rankings-eng`, after `models-lead` confirms | **Confirmed by `models-lead`** *(R.d)*: round 4 judges value boards (Q-K: C0 vs C1). It opens at the D-W3 horizon, after phase A passes |
| 5 | **Hidden layout, order key, intro line** (§0.3–§0.4) | `design-lead` and `ux-lead` | **`ux-lead`: approve** *(C-F2)*. **`design-lead`: pending.** <ul><li>**Layout:** reserve the value slot's width and the footer's height, empty (ux-lead C-F1).</li><li>**Order:** name A–Z.</li><li>**Intro line:** one static line under C-F2's three rules. Words: `marketing-lead`, via `head-product`.</li></ul> `models-lead` supports the intro line from the measurement side |
| 6 | **Randomize per card within a session,** accepting the cross-card memory caveat (§0.3) | `head-bizops` → `models-lead` | **Accepted by `models-lead`** *(R.d, check 2)*: per-card randomization, with T1 read as the on-card effect |
| 7 | **Metric definitions** (§1), including time-to-grade's break cap or dropping that metric | `analytics-lead` | As specced, with a 10-minute cap. **Pending** |
| 8 | **Which rounds after round 4 turn it on** | `head-bizops` → `models-lead` | **Answered by `models-lead`** *(R.d)*: round 4 is on. Later rounds are decided at each boundary by its rule (§0.6) |

## Handoffs

Through org boxes only.

| From → to | What |
|---|---|
| `trades-pm` → `head-product` | This draft PR with the two reviews folded, and decision 1. There are no waivers |
| `head-product` → `head-bizops` → `models-lead` | <ul><li>A check that C1–C5 landed as asked (§6.1 is byte-checkable against the SHA-1s).</li><li>`ux-lead`'s open question: does C-F1's constant layout bear on T1 (§6.2)?</li></ul> |
| `head-product` → `analytics-lead` | <ul><li>The §1 metric definitions and the call on no new event; decision 7.</li><li>The readout method and its validity veto (§7, models-lead C5).</li></ul> |
| `head-product` → `design-lead` | The C-F1 reserved-space layout, the order key, and the intro line's placement; decision 5 |
| `head-product` → `marketing-lead` | The intro line's words, under ux-lead C-F2's rule 2 |
| `head-product` → `head-eng` → `rankings-eng` | <ul><li>Build after decision 1.</li><li>Decision 2, and the minimum build for decision 3.</li><li>The §3 evidence, including the new `check-blind-grading.js` assertion.</li><li>The §4 doc rows.</li><li>At round-4 open: the setting, the rebuild, and phase B for the operator.</li></ul> |

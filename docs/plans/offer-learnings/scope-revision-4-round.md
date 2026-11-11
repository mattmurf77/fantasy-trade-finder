# Feature Scope — A Calibration round of its own for revision 4 (`outlook-v2-v4-1`)

**Date:** 2026-11-10
**Entry point:** direct operator ask, offer-learnings [plan](plan.md) §3 WS1b (the operator chose a
new round over leaving opened decks out, 2026-11-10)
**Builder:** WS1b builder agent, branch `feat/revision-4-round` (from `feat/offer-learnings`)
**Operator sign-off on waivers:** backend-only (no app change, proven below); operator decisions
listed in §8.

---

## 1. Analytics scope

- [x] **(c) WAIVED — no analytics needed because:** Calibration records every answer, tag and arm
  credit in `grading_cards`, and the per-round admin report is the readout. No event is emitted by
  the round machinery today, and none is added.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. `grading_sessions.round_id` gains a second value,
  `outlook-v2-v4-1`; `grading_build_leases` gains at most one row for it. Data dictionary note
  added.
- New feature flag: **`grading.revision4_round`**, default **false**: `feature_flags.FLAG_KEYS`,
  `config/features.json`, `release.json` / `onboarding-v2.json` / `profiles-on.json`,
  `docs/config-reference.md`. It is the round's single switch (builds and exposure; no separate
  prepare flag). Graduation: none; it is a measuring tool. Rollback lever: the flag.
- `grading.revision4_arm` (WS1): **superseded**, inert while the round is on (§6).
- New env vars / `model_config` keys: none.

## 3. Evidence scope

- [ ] **Structural guard:** WAIVED, no app change. The installed app already reaches the second
  round (route-sequence test and code walk below).
- [x] **Unit tests:** `backend/tests/test_calibration_revision_4_round.py` (17). Each proven red
  against a named sabotage, green on revert (TEST_LEDGER).
- [x] **Code-walk proof:** §7.
- [x] **Manual TestFlight checklist** (after the operator steps in §6; use three linked leagues:
  **A** with a current deck you have part-way graded, **B** with a current deck you never opened
  (or no deck), **C** whose current deck you finished):
  1. League A: open Calibration. Expect the same deck as before, same progress ("Resume (k of n
     answered)"), same "League as of" date. Finish it; results look exactly as before. Tap
     **Done**: expect **Resume (0 of N answered)** (revision-4 deck pre-generated) or **Start**.
  2. Start/Resume the revision-4 deck: "Building your deck…" opens within the poll window, or
     "Still preparing trades" (tap Check again). The first card's "League as of" date is **today's
     capture**. No card names an engine, version or round.
  3. Grade all N cards. Results show "Today's engine" / "New engine". Tap Done, then Start: the
     revision-4 results come back (no third deck).
  4. League B: open Calibration. Expect the **revision-4 deck first** (Resume 0 of N or Start), not
     the old deck. Finish it, tap Done: expect the old current deck offered (**Resume (0 of n
     answered)** with its old "League as of" date if its inputs are unchanged; if they changed, Start
     shows "Building your deck…" and a fresh date — the current round's own staleness rule). Grade it
     to the end; then Start shows the revision-4 results.
  5. League C: open Calibration. Expect the revision-4 deck (Resume 0 of N or Start). Finish it;
     Done then Start shows the revision-4 results.
  6. A league whose current deck shows "This league's roster rules aren't supported yet": expect
     the same message for the revision-4 deck (it is attempted and fails the same way).
  7. Rollback: with the flag off, reopen Calibration on league C. Expect the first round's state
     again (intro, Start shows the first round's results). A revision-4 deck that was on screen when
     the flag went off can still be answered to the end while the screen stays open; after leaving,
     the app does not offer it again until the flag is back on (its answers are kept).
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | Calibration § "Revision-4 round": `round_id` on start/current, routing, pregenerate/report |
| `living-memory/LLD.md` | updated | "Calibration rounds side by side" |
| `docs/architecture.md` | updated | "Bilateral revision 4": the round, `ROUNDS`, per-round leases/worker |
| `living-memory/HLD.md` | updated | 2026-11-10 revision-4 entry: superseded by a round |
| `docs/cross-client-invariants.md` | n/a because the wire aliases `current`/`value_core` and the labels are unchanged |
| `docs/glossary.md` | updated | "Revision-4 round"; additive arm marked superseded |
| ADR or `DECISIONS.md` | updated | `D-NEXT` (unnumbered); ADR-029 consequence line |
| `docs/config-reference.md` | updated | flag row; arm row marked superseded |
| `docs/data-dictionary.md` | updated | Blind grading tables: round values, one lease per round |

## 5. Ship gate declaration

- CI: `pytest backend/tests` on the branch (TEST_LEDGER). `test_deck_pipeline_digest` is not
  touched by this branch (no deck-pipeline function changed). No mobile change, so `tsc`,
  `check-*.js` and testid-lint are unaffected.
- Evidence recorded in `living-memory/TEST_LEDGER.md`.
- Express lane declared: no.

## 6. What the round is

**Pair.** `outlook_calibration.ROUNDS[R4_ROUND_ID]`: `current` = `owner-v2-bilateral-2` (live in
production), `value_core` = `owner-v2-bilateral-4`. One frozen capture per deck
(`outlook_calibration_adapter.capture`), both arms run through `CapturedComparison.run_arm` with the
same gates, ownership and proof-identity checks, the same equal top-n selection
(`PER_ARM` = 20, `MIN_PER_ARM` = 1) and the same blind balanced order. So a deck holds at most 40
cards (20 + 20 − shared trades, each shared trade once with a credit to both) and answers "is 4
better than what is live" on identical inputs. `run_arm` already pins the revision-4 selector per
arm (WS1), so the v2 arm is v2 whatever the serving knob says.

**Why reuse, not a sibling.** The only difference from the current round is the pair. Reusing
`build_session` keeps every guarantee of the current round (frozen as-of, fences, interruption
handling, cooperative yield, deletion behaviour) without a second copy to drift. The round never
folds the additive arm.

**Blind.** Cards are `neutral_trade` payloads; SessionView carries no round, arm or version; arm
attribution lives in hidden `arms_json` and `source_json`. Results, after completion only, keep the
two aliases and labels ("Today's engine" / "New engine"), which are true for this pair.

**Offer order** (set by the coordinator on 2026-11-10, operator away; the operator's aim:
"everyone gets fresh revision 4 trades alongside their existing decks"). With the flag on and no
`round_id`, `default_round` answers start/current per account/league:

1. The `outlook-v2-v3-1` deck is **part-way through** — status `open` and *started* — the current
   round, exactly as today. *Started* is the current round's own frozen-deck test, used by
   `start_session`, `next_card`, the start/current routes and the report's `started` readiness:
   `grading_sessions.first_exposed_at` is set **or** `grading_progress(session_id)["answered"] > 0`
   (`grading_cards.grade` not null or `skipped` ≠ 0). `_started()` states it once.
2. Otherwise, while the account/league has **no completed** `outlook-v2-v4-1` session — the
   revision-4 round. This covers a completed, unstarted (unexposed), building, failed or missing
   current deck.
3. Otherwise (revision 4 completed): the current round again, so an existing unstarted deck is
   reachable ("additive") and a missing or failed one can be started; if the current round is also
   completed, the revision-4 results.

An explicit `round_id` addresses either round; an unknown one is 400 `invalid_round`.
`next`/`cards`/`results` route by the session's own `round_id`.

**An unstarted current deck that is skipped** is not read, retired or rebuilt by the revision-4
path; it is offered again after revision 4 as **the same deck** (same session, cards and capture).
The one exception is the current round's own rule, unchanged: on Start or the first card,
`start_session`/`next_card` retire an unexposed, unanswered deck whose inputs are no longer current
(`is_current`, which includes the code revision) and build a fresh one. That would happen anyway
without the new round; any deploy in between makes it likely. Both cases are tested.

**A failed current deck** (too few trades, unsupported league, missing credentials) moves the pair
on to the revision-4 round, which is attempted: it runs the same capture, so an unsupported league
fails with the same error code and the app shows the same message; "too few" depends on revision
2's inventory, which both rounds share. Attempting is safe: a failed revision-4 session holds no
cards and Start retries it as the current round does. After revision 4 completes, the pair goes
back to the current round, where Start retries the failed deck as today.

**Isolation.** One building/open/completed session per account/league/round (`active_round_key`
hashes the round id), one build lease per round (`lease_key` = round id, as the database's
finish/fail fences require), one worker thread draining enabled rounds in order. Nothing in the
revision-4 path reads or writes a current-round row.

**The additive arm.** Superseded: `revision4_enabled()` is false while `grading.revision4_round`
is on, so the arm neither extends new current-round builds nor retires unexposed ones. Reason: two
ways to grade revision 4 would split answers across two denominators, and the arm could only reach
unopened decks. The operator should use the round and leave the arm off. Decks already built with
the arm keep their cards and answers.

**Off is today.** `default_round` returns `None` before any read; start/current ignore `round_id`
exactly as before; pregenerate with the new id is 400 `invalid_round`; the worker drains only the
current round. The one deliberate difference: `GET /api/admin/grading/report?round_id=outlook-v2-v4-1`
is readable with the flag off, so results survive a rollback (the report route is not flag-gated
by design).

### Operator steps (production; none run by this builder)

1. Deploy with the flag off. (Any deploy changes the code revision, so unexposed ready decks of the
   current round go stale and rebuild on next open, as after every deploy. Exposed and completed
   decks never change.)
2. Leave `grading.revision4_arm` off. Turn on `grading.revision4_round`: add it to Render's
   `FTF_FLAGS` (it wins over the file, G-076), then
   `curl -X POST "$BASE/api/feature-flags/reload" -H "X-Cron-Secret: $CRON_SECRET"`.
   `grading.blind` and `grading.outlook_round` stay as they are.
3. Pre-generate every connected user and linked league, 100 at a time, until `next_offset` is null:
   ```
   curl -X POST "$BASE/api/admin/grading/pregenerate" -H "X-Cron-Secret: $CRON_SECRET" \
     -H 'Content-Type: application/json' \
     -d '{"round_id":"outlook-v2-v4-1","offset":0,"limit":100}'
   ```
   Repeat with each returned `next_offset`. Re-running is safe (open decks resume). The serial
   worker builds one deck at a time; progress is `readiness_counts` in step 4.
4. Read `GET /api/admin/grading/report?round_id=outlook-v2-v4-1&include_open=1` (same
   `X-Cron-Secret`): `readiness_counts` (not_queued / queued / ready / started / completed /
   failed), `failures`, `completed` and `partial` groups with `arms["owner-v2-bilateral-2"]` vs
   `arms["owner-v2-bilateral-4"]` (`n`, `mean`, `share_ge_4`, `tag_counts`), `shared`, and
   `arm_inventory_totals`. The current round's report (`round_id=outlook-v2-v3-1`) is unchanged.
5. Rollback: remove the flag from `FTF_FLAGS` and reload. Unopened revision-4 decks pause
   (`round_paused`); exposed ones still accept answers by session id, but the app's start/current
   return to the current round, so a user mid-deck finishes only if the screen is still open. The
   report stays readable. No row is deleted or rebuilt; turning the flag back on resumes every deck
   where it stopped.

## 7. Code walk

- Round table and pair: `backend/outlook_calibration.py:27-32` (`R4_ROUND_ID`, `ROUNDS`).
- Flags: `:75` `round_enabled`, `round_build_enabled`, `_build_rounds`; `:87` `revision4_enabled`
  (arm inert under the round).
- Offer order: `:93` `_started` (the round's frozen-deck test); `:99` `default_round` (flag off →
  `None` before any read; rules 1–3 of §6).
- Session: `:133` `start_session(round_id=…)` (round-keyed lookup, `active_round_key`, source
  `version` and `model_versions`); `:177` `next_card` pauses or restarts by the row's round.
- Build: `:304` `build_session` accepts any round in `ROUNDS`, uses that round's pair; `:389` the
  arm folds only into `outlook-v2-v3-1`.
- Leases and worker: `:479` `_claim_lease(…, round_id)`; `:515` `drain_queue(round_id=…)`; `:555`
  `_worker_main` drains enabled rounds in order.
- Results/report/pregenerate: `:584`, `:598`, `:701`, each by round.
- Routes: `backend/server.py:36141` (POST sessions → `default_round`), `:36189` (GET current),
  `:36333` (pregenerate accepts the new id only while on), `:36433` (report per round).
  `next`/`cards`/`results` already dispatch by row round (`backend/blind_grading.py:306`, `:342`).
- Deletion: `backend/deletion_scrub.py:1177` discards the replay snapshot for every round in
  `ROUNDS`.
- App (unchanged): `mobile/src/screens/CalibrationScreen.tsx:339` `handleDone` clears the
  selection and invalidates `current`; `:195` the refetch; `:485-503` intro renders **Resume** for
  an `open` session or **Start**; `:207-217` Start's `onSuccess` selects `building`/`open`; `:202`
  polls while building; `:236-239` opens the deck. `GradingResults.tsx:20-21` renders
  `current`/`value_core` with fixed labels.

## 8. Not verified, assumptions, operator decisions

- **Not verified:** nothing ran against production; the real capture + revision 4 on one frozen
  input is WS1's adapter test (`test_calibration_revision_4.py`), not repeated here with a real
  league; the app path is a route-sequence test plus the code walk, not a device run.
- **Offer order: settled** by the coordinator on 2026-11-10 (operator away), §6. Not an open
  decision any more.
- **Consequence:** once both rounds are completed, the app's Start shows the revision-4 results, not
  the current round's (those stay in the admin report).
- **Decision — the arm.** Superseded and inert under the round; its code stays dark. Remove it in a
  later clean-up if the operator agrees.
- **Assumption:** prod keeps `grading.blind` and `grading.outlook_round` on. With
  `grading.outlook_round` off the order still holds; "the current round" in rules 1 and 3 is then
  today's flag-off path (the legacy exercise, or a v2/v3 deck already part-way through).
- **Not exercised here:** rule 3 with the current round off, and an account/league switching
  seats between the rounds (each round captures its own seat).

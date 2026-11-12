# Win-now season signal — build plan

**Date:** 2026-11-11 · **Status:** not started · Contract: [lld.md](lld.md). Gates:
[validation.md](validation.md). Scope block: [scope.md](scope.md).

Rules for every item: branch from a freshly fetched `origin/main`; tests first, each proven red
against its named sabotage and green on revert, the result logged in
`living-memory/TEST_LEDGER.md`; no simulator, no Maestro (D-056); `git grep` only; no user names,
ids or roster contents in any committed file. Builders run on Opus; the coordinating session
reviews and merges.

- [1. Work items](#1-work-items)
- [2. What runs in parallel with rules-first](#2-what-runs-in-parallel-with-rules-first)
- [3. Rollout and the kill switch](#3-rollout-and-the-kill-switch)
- [4. Manual TestFlight checklist (draft)](#4-manual-testflight-checklist-draft)
- [5. Size](#5-size)

## 1. Work items

Dependency order. "Collides with rules-first" names the files both builds edit.

### WI-1 · Backend · Season evidence, league profile, labels (pure)

- **Files (new):** `backend/league_projections/season_points.py`, `backend/season_value.py`,
  `backend/tests/test_season_points.py`, `backend/tests/test_season_value.py`, a small snapshot
  fixture built from `backend/tests/fixtures/outlook-calibration/sleeper-projections-2026.json`
  and the fixture pool (public players only).
- **Does:** [lld §1](lld.md#1-season-evidence), [§2](lld.md#2-league-profile-and-labels), and
  `plan_conflict(...)`, the one conflict predicate.
- **Tests and sabotages:**

  | Test | Sabotage that must turn it red |
  |---|---|
  | derived points reproduce the snapshot's stored lineup totals (I10) | score with the raw scoring settings, not the slot-normalised ones |
  | an unprojected player has no points, no label, never zero (I11) | default a missing player to `0.0` |
  | a week already kicked off is not in the horizon | compare kickoff with `captured_at` instead of `as_of` |
  | digest is stable inside one horizon and changes with a new snapshot (I12) | hash `as_of` |
  | each `unavailable` reason is produced by its own input and by nothing else | return `stale` for an old-model run |
  | label table: one test per row of the definitions, with the PRD's named players as fixtures (McCaffrey win-now, Jefferson cornerstone, Lemon rebuild, a QB inside the band unlabelled) | use `_now_lean ≥ 0.05` as the cliff test (Jefferson turns win-now) |
  | a 29-year-old startable RB with future ≥ 1,500 is a win-now piece | drop the cliff clause |
  | conflict predicate: All-in at −0.5, Contending at −1.0, the Rebuilding mirror, never for "Not sure" or an unsaved plan | use 0.5 for Contending |

- **Collides with rules-first:** nothing.
- **Size:** ~340 lines + ~450 of tests. One session.

### WI-2 · Backend · Revision 5

- **Depends on:** WI-1.
- **Files:** `backend/trade_gen_bilateral_season.py` (new), `backend/bakeoff_runner.py` (selector,
  three dispatch branches, `owner_presentment_version`), `backend/trade_gen_owner.py` (pop the dark
  keys), `backend/trade_service.py` and `backend/database.py` (three knobs),
  `backend/tests/test_trade_gen_bilateral_season.py` (new).
- **Does:** [lld §3](lld.md#3-revision-5), [§4](lld.md#4-proof-fields), stage 2 included behind
  `season_partner_matching`.
- **Tests and sabotages:** I2–I9 of [lld §10](lld.md#10-invariants-and-their-tests), plus:

  | Test | Sabotage |
  |---|---|
  | the operator's card: flagged, same terms, still in the inventory, below its twin | skip the penalty for `personal_board` |
  | a target-list card is flagged and not demoted | demote every flagged card |
  | candidate seats: a player who would start for the viewer and whom the board is neutral on is in the receive pool | leave `_pool` untouched |
  | stage 2 off: the other team's `_plan_asset` equals revision 2's for every asset | read the label table for partners unconditionally |
  | revision 2, 3 and 4 modules import and behave as before with the new knobs present (their own golden tests) | leave a season key in `search.config` when revision 5 is not selected |
  | proof carries `plan_fit` and `lineup_gain` separately and `team_plan` equals their combination | store only `team_plan` |

- **Collides with rules-first:** nothing (it edits no `trade_gen_*` or `bakeoff_runner`).
- **Size:** ~380 lines + ~600 of tests. One to two sessions.
- *Amended 2026-11-11, operator direction:* Rebuilding / Tanking viewers (saved or read) are
  season-scored in the shed direction as a ranking term only (lld §3.1, two knobs
  `season_shed_weight_tanking` 1.0 / `_rebuilding` 0.5, popped from every other search's config),
  with the points mirror conflict (`CONFLICT_ADD`) and `viewer.season_direction`; I4 restated.
- *Amended 2026-11-12, operator direction:* the viewer's label fit (`season_viewer_label_fit`,
  default 1): a Rebuilding / Tanking viewer's re-scored team plan reads the mirror label table
  with stage 2 off; order only (`_plan_asset` untouched). Stage 2 is partner matching only from
  now on. Tests and sabotages: `test_trade_gen_bilateral_season.py` (the `test_label_fit_*`
  block), the I18 admissibility audit and page-equals-gated cases. See the README's amendment.

### WI-3 · Backend · Card copy

- **Depends on:** the proof contract in lld §4 (can start beside WI-2 against fixture proofs).
- **Files:** `backend/trade_narrative.py`, `backend/tests/test_season_copy.py` (new).
- **Does:** [lld §5.1, §5.2](lld.md#5-card-payload-and-copy); PRD §5.3 and §6.
- **Tests and sabotages:**

  | Test | Sabotage |
  |---|---|
  | "Win-now" appears only under copy rule 1 when evidence is usable (I14) | leave `_fit_plan`'s age branch reachable for a scored side |
  | label printed = label the plan-fit table read (I13) | recompute the label in the composer |
  | each conflict sentence: above market, below market, target list, each plan name | name the most valuable asset instead of the one whose ranking qualified the card |
  | a revision 2 proof, and a revision 5 proof without usable evidence, give today's fit block byte for byte and no `season_block` | emit an empty `season_block` |
  | no figure or label for an unprojected asset | print `0.0` |
  | every lead fits one line: ≤ 44 characters with the longest name in the fixture pool | — (a length assertion) |
  | `FIT_TMPL_VERSION` is still `fit-2` | bump it |

- **Collides with rules-first:** nothing.
- **Size:** ~150 lines + ~350 of tests. One session.
- *Amended 2026-11-11, operator direction:* `season_shed.you` (`Tanking: -3.2 pts/wk, adds
  {asset}`), the points conflict lead for Rebuilding / Tanking (`Away from Tanking: +2.1 pts/wk`),
  and the season line for these viewers (lld §5.1).

### WI-4 · Backend · Operator tools

- **Depends on:** WI-1, WI-2.
- **Files (new):** `backend/eval/season_replay.py`, `backend/eval/season_label_review.py`, tests
  for their aggregate output.
- **Does:** [lld §8](lld.md#8-operator-tools); the arms and metrics of
  [validation §3](validation.md#3-offline-replay). Output is aggregates only; the review page is
  written to a git-ignored folder.
- **Tests and sabotages:** the report contains no player id, user id or name from a request
  (sabotage: print a card); the four arms run on the synthetic league and arm 1 equals revision 2's
  own output (sabotage: pass season evidence to arm 1).
- **Collides with rules-first:** imports its `backend/eval/served_deck_replay.py` stand-in if that
  has merged; otherwise carries a stand-in marked for removal.
- **Size:** ~320 lines + ~150 of tests. One session.
- *Amended 2026-11-11, operator direction:* the replay reports Rebuilding / Tanking before/after
  (points, shedding, adding, deck, first-30 overlap, set identity) and measures stage 2 by the
  partner's plan and source, with the corrected bars of validation §7.

### WI-5 · Backend · Worker wiring, flag, admin route, payload

- **Depends on:** WI-1, WI-2, WI-3.
- **Files:** `backend/server.py`, `backend/feature_flags.py`, `config/features.json`, the flag
  fixtures, `backend/tests/test_season_signal_worker.py` (new),
  `backend/tests/test_deck_pipeline_digest.py`; docs per the scope block.
- **Does:** [lld §6](lld.md#6-worker-wiring) and `season_block` in `trade_card_to_dict`.
- **Tests and sabotages:** I1, I15, I16, plus:

  | Test | Sabotage |
  |---|---|
  | one snapshot read per job, none when the flag is off | read inside `trade_card_to_dict` |
  | a read failure serves today's deck and logs `read_failed` | let the exception reach the job |
  | the viewer completeness rule: an unprojected viewer asset worth ≥ 450 → `viewer_unprojected_asset` | apply the rule to any roster in the league |
  | evidence is on the request record with revision 2 selected, and is not a generator keyword | pass it to revision 2 (TypeError) |
  | non-Sleeper league → `platform_unsupported`, no read | call the store first |
  | admin route: 401/404 without `X-Cron-Secret`; rows carry no user id | drop `_require_cron_auth()` |
  | presentment accepts revision 5 proofs | keep the literal version tuple |

- **Collides with rules-first:** `backend/server.py` (`_run_trade_job`: one line at the presentment
  call; `DECK_PIPELINE_VERSION` and its pin; `_ENGINE_CODE_MODULES`), `feature_flags.py`,
  `config/features.json`, flag fixtures, `test_deck_pipeline_digest.py`, `docs/architecture.md`,
  `docs/config-reference.md`, `docs/glossary.md`, `backend/CLAUDE.md`. All are additive lines.
  **Rebase on whichever build merged first; take the next pipeline version.**
- **Size:** ~130 lines + ~400 of tests. One session.

### WI-6 · Backend · Calibration round

- **Depends on:** WI-5.
- **Files:** `backend/outlook_calibration.py`, `backend/outlook_calibration_adapter.py`,
  `backend/tests/test_calibration_season_round.py` (new), flag `grading.season_round`.
- **Does:** [lld §7](lld.md#7-calibration-round). No app change: same aliases, same routes (the
  revision-4 round's code-walk is the precedent).
- **Tests and sabotages:** I17; the round is refused with `season_round_not_applicable` without
  usable evidence or a saved outlook (sabotage: build anyway); existing rounds' decks, answers and
  offer order are untouched (the revision-4 round's own tests stay green); flag off = today.
- **Collides with rules-first:** nothing.
- **Size:** ~70 lines + ~300 of tests. One session.

### WI-7 · Mobile · Season line, labels, conflict sentence

- **Depends on:** the payload contract in lld §5.2 (can start beside WI-3).
- **Files:** `mobile/src/shared/types.ts`, `mobile/src/api/trades.ts`,
  `mobile/src/components/TradeCard.tsx`, `mobile/tests/check-season-signal.js` (new),
  `mobile/package.json`.
- **Does:** [lld §5.3](lld.md#53-mobile). Chalkline tokens only (`docs/design/design-system.md`,
  `docs/design/components.md`): text in existing type styles, no emoji, no new colour, no radius.
- **Evidence:** `npx tsc --noEmit`; `npm run test:season-signal`; `npm run test:fit-first-copy`
  still green; `mobile/scripts/testid-lint.sh`.
- **Collides with rules-first:** nothing.
- **Size:** ~110 lines + a ~150-line check. One session. Rides the next TestFlight build; nothing
  waits for it.

### WI-8 · Backend · The join with rules-first

- **Depends on:** rules-first merged; WI-2.
- **Files:** `backend/trade_first_page.py`, `backend/trade_fast_deck.py`,
  `backend/tests/test_trade_first_page.py`, `backend/tests/test_rules_first_deck.py` (its file).
- **Does:** [hld §11 point 4](hld.md#11-the-seam-with-the-rules-first-build): a per-team lineup
  asset value hook; the lineup memo for a search that overrides `_lineup`; revision 5 in the
  supported set.
- **Tests and sabotages:** I18: page path = gated full solve = rank of the admitted survivors, card
  for card and proof for proof, for revision 5 with usable evidence, several seeds, 12/14/16 teams
  (sabotage: read `_lineup_assets` directly in the bound; expect a missed card). Revisions 1 and 2
  stay byte-identical on the page path (their existing suites).
- **Size:** ~40 lines + ~250 of tests. One session. Stage C does not strictly need it (§3).

### WI-9 · Validation runs (operator and coordinator)

Not code. In order: replay (validation §3) → label review (§4) → Calibration round (§5) → stage 2
replay and round (§7). Each result into `TEST_LEDGER.md`.

### Web

No work item. The web deck does not render the fit block (no `fit_block` reader in
`web/js/app.js`), and the season block rides the same surface. If the fit block ever comes to web,
the season line comes with it.

## 2. What runs in parallel with rules-first

| Item | Parallel now? | Why |
|---|---|---|
| WI-1, WI-2, WI-3, WI-4, WI-6, WI-7 | **yes** | they share no file with the rules-first build |
| WI-5 | yes, with a rebase | additive lines in `server.py`, flags and docs; the second to merge takes the next pipeline version |
| WI-8 | no | it edits the two files rules-first is rewriting |
| WI-9 replay, label review, Calibration | yes | they run full solves and need nothing from rules-first |

Asks of the parallel builds, both small:

- **Rules-first:** keep the supported-generator set a named tuple; keep `gated_full` to the module
  protocol (`_Search` / `_GenerationSearch`, `VERSION`, `_rank`).
- **Forecast v6 (free-agent fill):** also store the best projected free agent per starting position
  per week, so a slot a trade empties has a replacement level ([hld §4](hld.md#4-the-season-map)).

## 3. Rollout and the kill switch

| Stage | Switches | What a user sees | Gate to enter |
|---|---|---|---|
| **A · capture** | `trade.season_signal` on; selector 0 | nothing | WI-1, 2, 3, 5 merged; CI green; byte-identity tests |
| **B · grade** | + `grading.season_round` on | Calibration offers a new blind deck to users with a forecast and a saved plan | replay bars met (validation §3.4) |
| **C · serve** | + `owner_bilateral_revision_5_enabled = 1` | win-now users: a different deck order, the season lead on the card; conflict cards lower and labelled. With the next app build: the season line, label tags, the full conflict sentence | label review bar (§4) **and** Calibration read (§5) recorded; TestFlight checklist run |
| **D · match** | + `season_partner_matching = 1` | every outlook: league-mates' willingness reads the labels | stage 2 replay and round (§7) |

Watch after C, per job: the `season-signal:` line (state, reason, scored), served count, first-batch
time, and if rules-first is on, its fallback reason for revision 5 requests.

**Kill switches, all deploy-free, in order of reach:**

1. `season_conflict_demotion = 0`: stops the push-down only.
2. `owner_bilateral_revision_5_enabled = 0`: every deck back to revision 2. Stored first pages
   rebuild once (the owner model changed).
3. `trade.season_signal` false + `POST /api/feature-flags/reload`: no forecast read at all.
   Revision 5, if still selected, then returns revision 2's cards and order.

**If rules-first is delayed or off:** stages A–C proceed. Revision 5 serves on today's full solve at
today's speed. **If rules-first is on and WI-8 has not landed:** revision 5 requests take the
unsupported path (full solve, rules after ranking), logged; the operator may hold stage C for WI-8.

## 4. Manual TestFlight checklist (draft)

For stage C. Needs: a Sleeper league in season with a saved forecast (its playoff forecast screen shows
a current one), where you have a saved outlook; a second league on ESPN or MFL, or one with no
forecast. Write down two facts first from your own lineup: a bench player you would never start,
and your weakest starter.

1. **All-in league, Find a Trade.** Within the first 15 cards, at least 8 bring back a player who
   would start for you. On those, the You line reads `Win-now: {name} starts, +x.x/wk` or
   `Starts for you: {name}, +x.x/wk`. Check two of the named players against your lineup: each
   outscores the starter he would replace. *Catches: season scoring not applied; wrong lineup.*
2. **No card in the first 30 says "Win-now" about a player who would sit on your bench.**
   *Catches: the age rule still firing.*
3. **Find a conflict card** (scroll; they sit low): the You line reads
   `Away from All-in: −x.x pts/wk`. It gives up one of your starters. Its trade terms look like any
   other card's; Send still works to the confirm step (do not send). *Catches: penalty changing
   terms; card removed.*
4. **Pin a player you rank far above market** who would not start for you and search: the cards
   appear, with **no** "Away from" line. *Catches: conflict on pinned searches.*
5. **Change your outlook to Not sure**, search again: no season wording on any card; cards read as
   they did before this release. Change it back. *Catches: scoring leaking to Not sure.*
6. **A Rebuilding or Tanking league:** the deck looks as before. If a card's best incoming player is
   a productive veteran while you send a pick or young player, it sits low and reads
   `Away from Rebuilding: adds a win-now piece`. *Catches: mirror rule missing or over-firing: more
   than 3 such cards in the first 30 is a failure.*
7. **The ESPN/MFL or no-forecast league:** cards read exactly as before. No season wording.
   *Catches: fallback broken.*
8. **Deck depth:** in the All-in league, page to the end. The deck has at least as many cards as
   you are used to (note the count; compare with last week's). *Catches: a thin deck.*
9. **Speed:** first cards arrive no slower than before (note seconds). *Catches: a slow read.*
10. **Thursday night check** (once): search after the Thursday game has kicked off. Cards still
    carry season wording; a player who played Thursday is still treated as a starter.
    *Catches: horizon handling.*
11. **With the new build only:** the line `Season +x.x pts/wk · Dynasty cost y%` shows under the You
    lead; tags `Win-now piece` / `Cornerstone` / `Rebuild piece` sit beside players; the conflict
    card shows the full sentence on two lines. Edit a card's package: all three disappear.
12. **Rollback drill** (coordinator sets the selector to 0): search again; cards read as before
    this release within one search.

## 5. Size

| | New or changed code | Tests | Sessions |
|---|---:|---:|---:|
| Backend (WI-1 to WI-6, WI-8) | ~1,400 lines | ~2,500 lines | 7–8 |
| Mobile (WI-7) | ~110 lines | ~150 lines | 1 |
| Web | 0 | 0 | 0 |
| Operator time | — | — | label review (about 240 rows), one Calibration deck or more, the checklist |

No schema change, no new table, no new user route, no new client event. One app build for the full
card; the first serve does not wait for it.

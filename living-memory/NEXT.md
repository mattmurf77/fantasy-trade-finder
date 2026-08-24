# Next — Fantasy Trade Finder

> **Purpose:** forward priority queue. 3–7 items, ordered, each with a one-line *why now*.
>
> **Read at:** session start, after CHANGELOG and HANDOFF. **Write at:** when something finishes or priorities shift.
>
> Companion files: [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) for items blocked on external input; [`CHANGELOG.md`](CHANGELOG.md) for what was done.

---

## Table of Contents
- [2026-08-24 — Quick Set `via` gap PR: operator confirm + merge, then the TestFlight check](#2026-08-24--quick-set-via-gap-pr-operator-confirm--merge-then-the-testflight-check)
- [2026-08-23 — Onboarding × calc tour merge: operator decisions, then Wave A](#2026-08-23--onboarding--calc-tour-merge-operator-decisions-then-wave-a)
- [2026-08-22 — Full sweep: merge the review PR, then the build, then the operator flips](#2026-08-22-full-sweep-merge-the-review-pr-then-the-build-then-the-operator-flips)
- [2026-08-22 — negmem: BUILT dark; rollout is two operator flips](#2026-08-22--negmem-built-dark-rollout-is-two-operator-flips)
- [2026-08-21 — Receipts: the P0 prod read, then grade dark, then the screen](#2026-08-21--receipts-the-p0-prod-read-then-grade-dark-then-the-screen)
- [2026-08-20 — Fit-challenger: operator decisions, then the W1 re-light](#2026-08-20--fit-challenger-operator-decisions-then-the-w1-re-light)
- [2026-08-20 — Team Review defect batch: TestFlight pass, merge, then the four planned reports](#2026-08-20--team-review-defect-batch-testflight-pass-merge-then-the-four-planned-reports)
- [2026-08-19 — likes-you gates: TestFlight pass, merge, then watch the volume](#2026-08-19--likes-you-gates-testflight-pass-merge-then-watch-the-volume)
- [2026-08-19 — Settings IA follow-ups (branch `feat/settings-ia-hub`)](#2026-08-19--settings-ia-follow-ups-branch-featsettings-ia-hub)
- [Queue cap status — the 7-item cap is blown; proposed drops](#queue-cap-status--the-7-item-cap-is-blown-proposed-drops)
- [2026-08-18b — Follow-on batch status (3/4/5 built; 6/7 resolved)](#2026-08-18b--follow-on-batch-status-345-built-67-resolved)
- [2026-08-18 — Bug-sweep follow-ons (B1–B5)](#2026-08-18--bug-sweep-follow-ons-b1b5)
- [2026-08-16 — Matchmaking engine follow-ons](#2026-08-16--matchmaking-engine-follow-ons)
- [2026-08-16 — Presentment-rules follow-ons (G6, D-062)](#2026-08-16--presentment-rules-follow-ons-g6-d-062)
- [2026-08-15 — Guided Onboarding v2 built dark; graduation + Phase 2 queued](#2026-08-15--guided-onboarding-v2-built-dark-graduation--phase-2-queued)
- [2026-08-15 — Open-access Phase A SHIPPED; B/C queued](#2026-08-15--open-access-phase-a-shipped-bc-queued)
- [2026-08-15 — Compressed-board engine fixes SHIPPED (PR #122)](#2026-08-15--compressed-board-engine-fixes-shipped-pr-122)
- [2026-08-15 — Co-owned roster follow-on](#2026-08-15--co-owned-roster-follow-on)
- [2026-08-14 — Year-in-Review capture follow-ons](#2026-08-14--year-in-review-capture-follow-ons)
- [2026-08-13 — Notification inbox follow-ons](#2026-08-13--notification-inbox-follow-ons)
- [2026-08-11 — P0 remediation status + deferrals](#2026-08-11--p0-remediation-status--deferrals)
- [2026-08-08 — Priority Queue](#2026-08-08--priority-queue)
- [Queue Hygiene Rules](#queue-hygiene-rules)

---

## 2026-08-24 — Quick Set `via` gap PR: operator confirm + merge, then the TestFlight check

1. **Operator: confirm + merge the `claude/elegant-feynman-c3689e` PR** ([D-160](DECISIONS.md), [scope](../docs/plans/quickset-analytics-via/scope.md), [addendum](../docs/business/analytics/2026-08-24-quickset-via-gap.md)). One mobile emitter change lighting up three dark server reads (`quickset_completed`, `tier_save.via`, point-of-use `ranking_method='quickset'`) + the semantics correction (per tagged commit, never per completed position). Held unmerged because analytics events are a bright-line surface. *Why now: Group F (quickset tier-drop fix) planning surfaced it; every day unmerged is another day the Quick Set funnel reads zero.*
2. After the next mobile release containing it: run the **TestFlight checklist** in scope §3 and log in TEST_LEDGER; remember the seam — don't trend `rank_quickset` / `tier_save.via` splits across that release.

## 2026-08-23 — Onboarding × calc tour merge: operator decisions, then Wave A

1. **Operator: remaining [plan §4](../docs/plans/onboarding-tour-merge/plan.md) decisions** —
   1 and 6 are DECIDED ([D-158](DECISIONS.md) merged page, [D-157](DECISIONS.md) Clear button);
   still open: bridge-vs-full-spine (§4.2), auto-dispatch cost (§4.3), `growth.invite_join_link`
   (§4.4), multi-platform-landing timing (§4.5). D-158's two assumptions are CONFIRMED
   (2026-08-24). *Why now: Wave A and Wave B0 are both fully specified — each is one operator go
   from build.*
2. **Wave A on a go:** Next buttons on every onboarding talk beat (the W7 rule, applied to
   `s0.1`/`s2.1`/`s5.x`/`s8.1`/`n1`/err beats), `landing.try_before_sync` → false, `s0.1` +
   `s2.1` copy. Full gates; no schema/API surface.

## 2026-08-22 — Full sweep: merge the review PR, then the build, then the operator flips

1. **Rebase + PR `claude/trade-model-restrictiveness-7f3975`** (docs only; owns G-058 / Q-030 that the build cites). Then **PR `claude/full-sweep-0822-a1c3`** — CI green, `FTF_SKIP_SIM_GATE=1`. Merging lights nothing.
2. **Operator: run the [TestFlight checklist](../docs/plans/full-sweep/scope.md)** (§3, six steps, server-side flag) and log the numbers in TEST_LEDGER — that is what graduates `trade.full_sweep`.
3. **Knockout programme — R5/R1/R2/shape SHIPPED 2026-08-24 (D-159); remaining, in order** ([verdict](../docs/reviews/2026-08-22-knockout-rules-judged.html) §04): R5 dual-need rescue alone → consolidation bundle measured together in the replay harness (`filler_min_frac` sweep 0.15/0.10 with `asset_floor_abs` held; `trade_elo_gap_max` → 0; R1 in `package_value_v2`; `v3_shape_max_delta` knob) → R2 starter-depth predicate → the viewer-must-win form (operator, Q-030a). Audit `waiver_slot_cost` = 425 alongside.

## 2026-08-22 — negmem: BUILT dark; rollout is two operator flips

v1 is complete on `claude/vigilant-spence-8583f5` and lit nowhere ([D-147](DECISIONS.md),
[ADR-015](../docs/adr/adr-015-negmem-soft-prior-not-fourth-filter.md), CHANGELOG same date).
*Why now:* the remaining work is operator actions and a measurement window, not engineering.

1. **Merge the branch** when the operator wants it on main. Merging lights nothing — the
   ON-condition is flag **∧** allowlist, and both ship off/empty.
2. **Rollout, per [PRD](../docs/plans/negative-results-memory/PRD.md) §8.2 — at a bake-off
   ROUND BOUNDARY** (GR3; mid-round censors the window): add the operator's league to
   `config/negmem_leagues.json` → flip `trade.negmem` → ≥4-week arm-attributed read.
3. **The [TestFlight checklist](../docs/plans/negative-results-memory/testflight-checklist.md)
   is UNRUN** — the only runtime evidence this feature gets under D-056. Step 0 (the
   before-readout) has to happen *before* the flip or the baseline is gone.
4. **P2 gates, none of them started:** the RFPS baseline freeze + frozen-cohort artifact
   (`rfps-baseline-<date>.json`) must be committed at pre-registration, before the window
   opens; layer-2 tendency modeling stays behind the data-volume gate; and any future
   *persistence* of per-person profiles — which ruling D3(a) permits — carries its own scope
   block with the `delete_user_data` partner-keyed deletion path as a named requirement.
## 2026-08-21 — Receipts: the P0 prod read, then grade dark, then the screen

Built dark on `feat/receipts` (see CHANGELOG + TEST_LEDGER same date). Nothing is pushed.
*Why now:* the grading clock only starts once the flag is on, and every week dark is cohort
lost — the 56d window cannot mature before ~Oct 11 given the 2026-08-16 telemetry start.

1. **P0 prod counts** ([LLD §8](../docs/plans/receipts/LLD.md), read-only via
   `backend/tools/prod_analytics.py`): gradeable impressions + per-league histogram,
   pick-involvement share, snapshot gap rate since 2026-07-26, per-user×league counts. This is
   the A-1 gate; the local dev DB has zero impressions, so nothing about cohort size is known
   yet.
2. **Merge + flip `receipts.grading`**, then drain with `scripts/receipts_backfill.py`. The
   grader is inert until this happens.
3. **A-2 operator checkpoint** on `GET /api/admin/receipts/metrics` — the first real numbers.
   Pre-committed: a bad number changes **copy**, never the cohort, window or metric.
4. **TestFlight pass** ([testflight-checklist.md](../docs/plans/receipts/testflight-checklist.md),
   12 steps) — the only runtime evidence this feature gets — then flip `receipts.screen`.
5. **Three-way taxonomy reconciliation** still open (PLAN §7 Q-6): confirm sibling prefix
   claims with negmem + breaker now that `docs/plans/shared/trade-shape-taxonomy.md` v1.1.1 is
   on `main`.

## 2026-08-20 — Fit-challenger: operator decisions, then the W1 re-light

Built dark on `claude/trade-suggestions-review-69c9eb` (see HANDOFF + CHANGELOG same date).
*Why now:* the whole serving program is gated on operator calls, not engineering.

1. **Operator: work the [PRD-build decision register](../docs/plans/fit-challenger/PRD-build.md)** —
   9 items; K1 2-2/3-3 reading, `trade.outlook_direction` flip, R-8 rostering, ms bar are the
   live ones.
2. **Prod replay-board dry run** (league `1312140920132497408`, read-only) + baseline readout
   snapshot before any serving flip.
3. **W1 re-light** per [PLAN-v2 §5](../docs/plans/fit-challenger/PLAN-v2.md): screen round
   B+D+C, `bakeoff_group_size=0`, daily deck tripwires (investigate <22, revert <18 ×2 days).
4. Tester onboarding per [tester-protocol.md](../docs/plans/trade-engine-accuracy/tester-protocol.md)
   — boards ≥100 votes, declared outlooks; program goal ≥2 leagues with 3+ boards (gen_v2's
   re-entry condition).

*(Cap note: added while the 7-item cap is already blown — this is the current operative work;
the 2026-08-08/08-11 sections remain first in line to drop.)*
## 2026-08-20 — Team Review is shipped; what is owed is RUNTIME evidence, not code

All thirteen reports (#364–#376) are closed in code on `main` `25cc699`, builds 124/125.
*Why now:* four TestFlight checklists are unrun and one lit flag moves every deck.

1. **Operator: run the four checklists.** `364-team-review-fixes` (13 steps — **step 8**, the sell
   list holds players you are LOW on, is the whole of #367), plus `366-tier-ladder`,
   `369-plan-beat`, `372-window-composite`. Under [D-056](DECISIONS.md) this is the only runtime
   evidence any of it gets, and **#372 is in no build at all**.
2. **Watch `trade.position_tiers`.** Lit by operator call; it moves `position_needs`/`position_surplus`
   and therefore every deck, on evidence a green suite provably cannot supply. First suspect if deck
   composition looks off. Rollback: `false` + `POST /api/feature-flags/reload`.
3. **Run `scripts/deck_eval.py` on real leagues** — the evidence `position_tiers` was lit without,
   and the graduation criterion for `trade.outlook_composite` too.
4. **Decide the three dark flags** after the checklists: `trade.outlook_net_firsts`,
   `trades.window_from_odds`, `trade.outlook_composite`.
5. **Fix the test suite's blind spots.** Five dead tests surfaced today and every engine fixture is
   smaller than `_POS_TIER_MIN_POOL`, so the suite cannot see tier changes at all. A realistically
   sized shared fixture is worth more than the next feature.
6. **Still open, not from this batch:** #370 (repeat liked trades — needs a repro against
   `deck_impressions`, device vs account) and #367's consensus-vs-league toggle
   (`364-team-review-fixes/plan-remaining.md` §4).

---

## 2026-08-20 — Team Review defect batch: TestFlight pass, merge, then the four planned reports

Built and unmerged on **`claude/team-outlook-experience-27a7a1`** ([D-100](DECISIONS.md), [D-101](DECISIONS.md),
[scope](../docs/feedback/items/364-team-review-fixes/scope.md)). *Why now:* #367 is a live user-facing
defect on two surfaces — the app was telling users to sell the players the market **won't** pay for,
and offering their best buys under "Skip these."

1. **Operator: run the 13-step TestFlight checklist**
   ([checklist](../docs/feedback/items/364-team-review-fixes/testflight-checklist.md)). Only runtime
   evidence available under [D-056](DECISIONS.md). **Step 8** — the sell list holds players you are
   *lower* on than the league — is the whole change. Step 13 covers Trends, which moved with it.
2. ~~**Push + merge.**~~ **DONE 2026-08-20** — PR #152 merged `bc43b6f`, Render live on it, EAS build 124
   submitted to TestFlight. The payload half is serving now; the corrected copy needs build 124 to land.
3. **Know the rollback before you need it:** `trades.team_review` → `false` and `outlook.odds` → `false`
   are deploy-free, but **neither reverts #367** — `compute_consensus_gap` is ungated and shared, so
   that one is a code revert.
4. **Then the four planned reports**, in the order argued in
   [plan-remaining.md](../docs/feedback/items/364-team-review-fixes/plan-remaining.md): the #367
   consensus-vs-league toggle (smallest, finishes a half-shipped item) → **#370** repro (a live
   complaint, different surface) → **#365** net-firsts signal (needs two decisions first; it is a
   bright-line *engine* change) → **#366** re-tier, with Handcuff split out and gated on whether FTF
   ingests an NFL depth chart → #369 → #371 (decide alongside #365, not before it).

---

## 2026-08-19 — likes-you gates: TestFlight pass, merge, then watch the volume

Built and unmerged on **`fix/likes-you-quality-gates`** ([D-096](DECISIONS.md),
[scope](../docs/plans/likes-you-quality-gates/scope.md)). *Why now:* it is a live user-facing defect —
115 of 198 served likes-you cards show the user paying, at deck position 1–3, measured in prod.

1. **Operator: run the 10-step TestFlight checklist + the 2-step rollback rehearsal**
   ([checklist](../docs/plans/likes-you-quality-gates/testflight-checklist.md)). Only runtime evidence
   available under [D-056](DECISIONS.md). Step 2 — *no LIKES YOU card's value bar tilts against you* —
   is the whole change.
2. **Push + merge**, then confirm the deploy. Nothing is pushed.
3. **Watch the surface volume for a week** on `deck_impressions.features_json` (`likes_you: true`):
   user-pays share must read **0**, and the count of likes-you impressions should fall to roughly 40%
   of its prior level, not to zero. If it does hit zero for real users, the lever is
   `likes_you_min_user_gain`, **not** the gate level — level 1 and level 2 scored identically on the
   measured population, so the floor is what bites, not R1.

---

## 2026-08-19 — Settings IA follow-ups (branch `feat/settings-ia-hub`)

Built and unmerged; `account.settings_hub` default OFF (see [`CHANGELOG.md`](CHANGELOG.md) 2026-08-19,
[D-079](DECISIONS.md)). In order:

1. **Fix the 5 red backend tests on `origin/main`.** *(unowned; blocks EVERY branch, not just this one)*
   CLAUDE.md's pre-ship gate requires green CI. `test_seed_ui_test_db.py::test_release_flags_mirror_features_json`
   (`trade.bakeoff` fixture drift from `ecdbcb3`), three in `test_suggestion_telemetry.py`, one in
   `test_trade_decision_idempotency.py` (re-posted swipe expects Elo 1502.0, gets 1500.0). Reproduce on a
   clean checkout before assuming they are environmental.
2. **Operator: run the plan §9 TestFlight checklist** *(next EAS build, `account.settings_hub` on for your
   device)* — [`../docs/plans/settings-ia-hub/plan.md`](../docs/plans/settings-ia-hub/plan.md) §9, 10 items.
   It is the **only** runtime evidence this change can get under [D-056](DECISIONS.md), and graduating the
   flag hangs on it. Item 1 (push-from-right, swipe-down no longer dismisses) is the one to look at hardest —
   that behaviour changed in **both** flag states and cannot be rolled back by the flag.
3. **Phase 4** *(after item 2 passes)* — graduate `account.settings_hub` to default true, delete the flat
   `SettingsScreen` branch (and with it the `prefsQuery.isLoading` full-screen gate still live at
   `SettingsScreen.tsx:745`), retire `account.settings_v2` and its long-dead legacy branch. Also settles the
   two doc updates still owed from the scope block: `living-memory/LLD.md` and `mobile/src/screens/CLAUDE.md`.

---

## 2026-08-19 — ESPN pick-assignment horizon becomes a user setting (backlog)

**Operator ruling, 2026-08-19** (closing [Q-022](OPEN_QUESTIONS.md)): *"The user should be able to
decide how many future draft pick years to set in the espn assignment. Not critical for now, backlog
item."* Neither answer the question offered — not Sleeper's derived rolling three, not the recorded
`current + 3` — the span is a **league setting the assigning member owns**, which fits rows that are
already `source='user'`.

- **One commit, three parts, or it breaks:** a per-league setting (default 4 classes so no existing
  league moves) → `database.seed_pick_grid` reading it instead of `_ASSIGNMENT_SEASONS_AHEAD`
  (`backend/server.py:12202`) → the assignment progress denominator (`backend/server.py:12447`)
  deriving from the same value. Split them and every league's progress reads wrong.
- **Do NOT point this at `draft_status.pick_horizon`.** That one is derived from platform truth;
  this one is a user declaration. They are deliberately separate — see Q-022.
- **Not blocking:** zero exposure today, no ESPN rows in `draft_picks` in prod.
- Added while the cap below was already blown; it is operator-directed and current, so it is logged
  rather than dropped — but it makes the paydown one item more overdue.

## 2026-08-19 — Slot-driven pick pricing (operator-ruled, queued behind D-090)

**Operator ruling** closing the direction half of [Q-023](OPEN_QUESTIONS.md): *"Slot should drive price
but we can push this live first and then solve for that."* Slot labels (D-090) ship now; pricing follows
as its own change.

- **Bright line — this is not a follow-up commit.** It moves 48 of 48 current-year pick values and 38 of
  48 tier badges on the operator's league, and tier colour is a five-client invariant. Own scope block,
  own evidence, own TestFlight pass.
- **Ship labels first on purpose:** so a wrong-looking value can be attributed to pricing rather than to
  labelling.
- **Decide before building (see Q-023):** all picks or only under the opt-in `trade.slot_pricing`
  mode · unknown-order leagues fall back to the Mid rung or are excluded · does the TIER band follow the
  slot, or only the trade value.
- Future seasons keep the Mid rung regardless — their order is genuinely unknowable.

## Queue cap status — the 7-item cap is blown; proposed drops

*(Noted 2026-08-19 rather than silently overflowing, per the hygiene rules below.)* This file carries
**14 dated sections and ~45 active items** against a stated cap of **7 items / 1.5KB**. The section above
was added anyway because it is current work, but the drift is real and nobody has been paying it down.

Proposed drops, in order of least controversy — someone with the context should confirm before deleting:

1. **Completed items still sitting here as checkmarks**, which the hygiene rules explicitly forbid:
   2026-08-18b item 3 (struck through, shipped in `e8ae476`) and 2026-08-15 guide-v2 item 4 (marked
   "DONE in this build"). Move the outcome to `CHANGELOG.md` and delete the lines.
2. **`2026-08-08 — Priority Queue`** and **`2026-08-11 — P0 remediation status + deferrals`** — the two
   oldest sections. Their resolved parts belong in `CHANGELOG.md`; anything genuinely still open should be
   restated as one item in a current section rather than kept as a status page.
3. **`2026-08-15 — Compressed-board engine fixes SHIPPED (PR #122)`** — shipped; what remains is a watch
   item ("eyeball the rescued cards"), which is one line, not a section.

---

## 2026-08-18b — Follow-on batch status (3/4/5 built; 6/7 resolved)

On `feat/sweep-followups-2026-08-18`, **not shipped**. Items 3, 4, 5 built; 6 and 7 researched and
fixed. What remains:

1. **Operator: ship decision for the follow-on branch** — full gates green (pytest 3191, tsc clean, 56 suites). Needs a merge + a TestFlight build for the client half.
2. **Operator: does `swipe_guard_blocked` count toward DAU/WAU?** It was deliberately left out of `NON_INTENT_EVENTS` (D-071). Reasoning is pinned by a test; one line to reverse if you disagree.
3. ~~**`/api/trades/generate` ignores `force_fresh` for in-flight jobs**~~ — **DONE**, shipped by the "Matchmaking model research agents" session in `e8ae476` (Phase 0 batch, on `main`). The obvious gate was not enough: there is **no cancellation mechanism in the job registry**, so gating the in-flight share on `force` alone orphans the running worker, which keeps going and still calls `_log_deck_signal_impressions` — impression rows for a deck no user is ever served, corrupting the corpus the three-model bake-off depends on. Shipped fix adds a supersede marker: the superseded worker finishes silently, publishing no snapshots and logging no impressions. Knob `force_supersedes_running` (default 1.0, kill 0.0).
4. **`/api/trade/evaluate`'s eveners hand-set `is_pick`** rather than deriving it from `trade_service.is_pick_asset`. Contract is correct today; rebinding it gives one derivation. Small.
5. **The web client still has B3's picks bug** (`web/index.html:635`, `web/js/app.js:3156/3184/3219`) — carried over, still open, now further diverged from mobile since mobile also gained the `is_pick` migration.
6. **Class-(b) re-fronting is untested** — a card can be re-fronted by the `sortedDeck` re-sort with neither `setDeckIdx` nor `setDeck([])`, so no current test can see it. `rerankRemaining` guards positions `≤ curIdx + 1`; the memo does not.
7. **Ledger hygiene: `D-039` is a duplicate on `main`** — "Tier-Board Share Routes…" and "ESPN Trade-Write…" share the ID. **Pre-existing**, not from this batch (the fresh `D-068` collision was fixed here by renumbering the later entry to `D-074`). Left alone deliberately: it is old enough that references may exist in shipped docs, so renumbering needs a reference sweep first. **Third collision in three days** — the grep-then-write rule can't see an unpushed sibling session, which is the actual root cause and worth solving properly (a reserved-range convention, or an ID lint in CI).
8. **Item 5's residuals, both accepted (D-073):** (a) the replay guard is read-then-write in one transaction, not a distributed lock — two simultaneous requests on separate workers could still both write; all 40 observed prod duplicates were sequential. (b) `record_trade_signal` is deliberately ungated, so a replay doubles the **in-memory** signal for the life of that session (~2 Elo points on the affected pair at `trade_k_pass = 4.0`). The persisted rows are correct, so it heals at the next `session_init`; pinned by a test so it stays a decision rather than drifting into a leak.

---

## 2026-08-18 — Bug-sweep follow-ons (B1–B5)

Five operator-reported bugs shipped (CHANGELOG 2026-08-18, D-068/069/070). What the sweep
deliberately did **not** do:

1. **Operator: on-device QA of the five fixes** *(next TestFlight build)* — the checklist is in `TEST_LEDGER.md` under this date. B1's scroll tracking and B2's chip placement have **no** automated behavioral coverage on device; both rest on structural tests plus review.
2. **The web client has B3's picks bug too** *(unfixed, now diverged from mobile)* — `web/index.html:635` renders a chip labeled "Picks"; `web/js/app.js:3156/3184/3219` filter roster-scoped pools that hold zero pick assets, so the tab is permanently empty with no empty state.
3. **`swipe_guard_blocked` analytics event** *(needs a taxonomy row)* — the B4 stall was invisible in every telemetry stream: a user could tap ✕ fifty times and produce zero events. Deferred because a new event crosses the CLAUDE.md bright line, not because it isn't worth having.
4. **`/api/trade/values` should emit `is_pick: true`** — five clients currently re-derive pick identity from the `team == "PICK"` magic string. Would have prevented both B3 and #222.
5. **Upsert or unique-constrain `trade_decisions`** *(G-049)* — `save_trade_decision` is a plain INSERT, so a duplicate pass double-counts `trade_k_pass`. D-068 narrowly widened the path to it.
6. **B1: layout-driven target movement is still unhandled** — a banner mounting shifts a spotlight target with **no scroll event**, reproducing the same stale-frame symptom. The pub/sub is named "targets moved" precisely so an `onLayout` notify can close this.
7. **Possible seventh guard-clear site** at `TradesScreen.tsx:3138` (Quick-Set regen) — safe today only because regenerated cards carry fresh uuids, which contradicts the comment at two sibling reset sites.

---

## 2026-08-15 — Guided Onboarding v2 built dark; graduation + Phase 2 queued

Phase 0+1 merged dark behind `onboarding.guide_v2: false` (see CHANGELOG + `docs/plans/guided-onboarding-v2/`).

1. **Operator: TestFlight checklist for guide-v2** *(next EAS build, flag on for your device)* — [`../docs/plans/guided-onboarding-v2/testflight-checklist.md`](../docs/plans/guided-onboarding-v2/testflight-checklist.md); graduation to default-true hangs on it.
2. **Phase 2 build after graduation:** N6.2 awaiting-send spotlight, N3 mutual-match walkthrough, N5/N7 spotlights, `trades.send-control.guide` per-instance registration, MFL/ESPN send-attempt events (retirement fails closed on those platforms until then).
3. **When `feat/premium-import-v1` merges:** N8's Upload arm becomes the premium chooser automatically; flip nothing, but re-run checklist walk A-4.
4. Item 4 below (s5.1 "1 new trades" copy nit) — **DONE in this build** (plural fix shipped in the script pass); drop it at next hygiene pass.

## 2026-08-15 — Open-access Phase A SHIPPED; B/C queued

Operator ratified **O-1…O-9** of [`../docs/business/product/2026-08-14-open-access-onboarding.md`](../docs/business/product/2026-08-14-open-access-onboarding.md); Phase A merged to `main` 2026-08-15 (PRs #131 → #132 → #129, tip `0d8d7bb`). Maestro retired entirely (D-056).

1. **Operator: TestFlight pass on the flipped first-run** *(next EAS build)* — the 5-step `s5.1` check in [`../docs/plans/open-access-phase-a-gates.md`](../docs/plans/open-access-phase-a-gates.md) § Manual TestFlight check; note an all-skip walk may honestly celebrate small N (engine stochasticity, see TEST_LEDGER).
2. **Operator: retire `onboarding_v2_rollout`** post-deploy — runbook § Retiring the onboarding experiment overlay (discover → snapshot → stop → decide → verify).
3. **Phase B build** (grading lane, new Elo inputs, `member_rankings` publish gate; coordinates the counterparty-basis clause G10 already appended to [`../docs/plans/audit-p1-remediation/PRD-p1-9.md`](../docs/plans/audit-p1-remediation/PRD-p1-9.md) §11) → eng-backend per plan §11. **Phase C** (platform door) after the notification batch.
4. Copy nit: `analystScript.ts` `s5_1` reads "1 new trades" at N=1 — newly reachable, one-line fix, fold into any mobile batch.

## 2026-08-15 — Compressed-board engine fixes SHIPPED (PR #122)

Shipped via [PR #122](https://github.com/mattmurf77/fantasy-trade-finder/pull/122)
(`main` @ `19d4174`), both flags live, deploy and post-deploy deck read verified
(see [`HANDOFF.md`](HANDOFF.md), [D-052](DECISIONS.md)). What's left is watching it.

1. **Eyeball the rescued cards in the app.** *(S — the real open item)* The zero-card cliff is gone in production and counts are verified, but **nobody has looked at a single rescued card**. MangoPatti and Bcork now show `basis:"consensus"` fair-value ideas; gdubs10 shows divergence cards. If any look silly, the kill switch is one `false` in `config/features.json`.
2. **Re-run the field probe on a second league.** *(S)* Every field number is from FFV3. The no-regression claim for healthy boards rests on a unit fixture, not on data from a league that isn't the one the bug was found in.
3. **[Q-017](OPEN_QUESTIONS.md) — quantile-matching the prune.** *(M, only if #1 says the consensus fallback isn't good enough)* A single scale factor can't undo a nonlinear compression, which is why MangoPatti and Bcork get consensus rather than divergence cards. Don't build it on speculation.

---

## 2026-08-15 — Co-owned roster follow-on

Co-owner support shipped ([ADR-012](../docs/adr/adr-012-co-owned-roster-identity.md)); one deliberate gap was left behind it.

1. **A co-owned team's board and outlook are invisible to its leaguemates.** *(S–M, product call first)* Two tables are keyed `(league_id, ACCOUNT user_id)` while leaguemates read them by the roster's `owner_id`: `member_rankings` (the team's board) and `league_preferences` (its declared outlook, read at [`server.py`](../backend/server.py) `load_league_preference(user_id=m.user_id, …)` under `trade_outlook_infer`). So a co-managed team reads as "no rankings, no declared outlook" to everyone else unless the **primary** owner uses FTF — its suggestions stay pure-consensus and its outlook falls back to roster-shape inference.
   Re-keying to the league identity is the obvious fix and is **wrong as stated for `member_rankings`**: the same table feeds cross-league Trends aggregation (`load_member_rankings(..., exclude_user_id="")`), so one person's board would be attributed to another person's Sleeper id in community data. `league_preferences` is a softer call but the same question. Decide whether a **team** board/outlook and an **account** board/outlook are the same object before any code moves. Today's behaviour is honest degradation, not corruption — which is why it shipped this way ([ADR-012](../docs/adr/adr-012-co-owned-roster-identity.md)).

## 2026-08-14 — Year-in-Review capture follow-ons

P0 capture is built on `feat/roster-history` (see [`HANDOFF.md`](HANDOFF.md)). In order:

1. **Gate 0 — the scheduler oracle.** *(operator, ½ day)* Run the `player_value_history` density query (plans README) against prod. It changes cron-migration urgency, never the capture design. Then, **one week post-ship**, the `source`-column liveness read (runbook § roster-snapshot monitoring) + its retirement rule.
2. **P1 — backfill audit + C3 hardening.** What did P0 miss before it landed? Sleeper transaction-log replay is the salvage tool (plan §2.3, a salvage not a plan). C5's cadence backstop is already covered by `league_board_history`.
3. **P2 — end-of-season fetchers (F1–F8).** Verify ESPN/MFL transaction-log retention BEFORE the recap design leans on it; degrade trade P&L to Sleeper-only rather than blocking the recap.
4. **P3 — recap compute + UI + the nine analytics events**, taxonomy addendum registered before any emitter, `wrapped_viewed` finally fires. Monetization call (free vs premium hook) is owed **before** P3 starts.

## 2026-08-16 — Matchmaking engine follow-ons

Phase 1 shipped dark 2026-08-16 (see [`HANDOFF.md`](HANDOFF.md) top entry). In order:

1. **Light `suggestion.telemetry`** *(S; it only collects — the learning loop is logging-gated and retroactively impossible)* then watch the ghost/organic ratio route for a week.
2. **Light `trade_gen.v2`** once telemetry accumulates accept/response stats for the EB prior; verify fixture-league behavior against prod boards first (its lighting checklist also owes the R2 pos-net port — [D-062](DECISIONS.md)).
3. **Mobile pyramid UI** from `mockups/trade-suggestion-redesign/` *(M-L; full gates — real Maestro flows, no waiver)*.

## 2026-08-16 — Presentment-rules follow-ons (G6, [D-062](DECISIONS.md))

1. **Prod-state deck-eval replay** *(S; operator-run — the build agent's environment was blocked from the prod DB)*: flag-OFF then flag-ON over the 9 corpus leagues with prod `DATABASE_URL`, `scripts/deck_eval.py` (now emits `presentment_audit` + `presentment_kills`) — confirms the R1/R2 bands on divergence decks and R4 on real like history (prd §2 bands; band miss = stop-and-report, prd's round-1 N8).
2. **Tune `pick_gap_frac`/`pick_gap_min_value` (R-12)** *(S; blocked on the above)*: zero R3-shaped candidates exist in every available corpus (local pick replay served only fair 1-for-1 player-for-pick swaps) — measure the pick-card kill rate on a prod-state divergence replay with `--with-picks`, then set/confirm the knobs. Until then R3 runs at unmeasured defaults (0.8 / 300) — the knob is the acknowledged lever.
3. **R5 user-board variant** *(M; named follow-up, not an oversight — D-062(3))*: re-judge the need gate on the user's raw board once comparison counts make it stable.

## 2026-08-13 — Notification inbox follow-ons

Phase 1 is built on `feat/notif-inbox-growth` and unmerged (see [`HANDOFF.md`](HANDOFF.md)). These are what comes after it, in order.

1. **Run one `npm run` step for the `check-*.js` suites in CI.** *(S, and overdue)* Seven structural suites — now including `check-notif-glyphs.js`, which guards a cross-client enum whose only failure mode is a silent grey bell — are `npm run`-only, so **none of them gates anything**. This has been noted in the ledger for three sessions running. `.github/workflows/ci.yml` already has a node job with `npm ci`.

2. **Post-deploy analytics probe for the three `notif_*` names.** *(S, blocks reading any of it)* Registration is unproven until each name round-trips through `POST /api/events` **with `X-Device-Id` set** — without the header the response is `{"accepted":0,...,"rejected":[{"reason":"no_identity"}]}`, which has `dropped == 0` and reads as a pass. Then leave `notif_inbox_opened` alone for 14 days: **the riskiest assumption in the whole exercise is that anyone opens the bell**, and it is completely unmeasured before this ships.

3. **Phase 2 — `referral_joined` push** (GD-5, `trade_matches` bucket, operator-only allowlist). Gated on the push rollout, not on phase 1.

4. **`counter_offer` has no emitter.** *(operator/product call)* The kind is plumbed end to end — bucket, both clients' glyphs, both clients' routing — and nothing in the backend ever fires it. Either a counter-offer feature is wanted, or the kind should be retired rather than left looking implemented.

5. **Roster-diff feasibility check for a re-rank prompt.** *(eng-backend, blocks GD-6)* Does league sync expose a usable roster diff? Phase-3 prompts wait on this **and** on item 2 showing the bell is used at all. A calendar-triggered re-rank is explicitly rejected — that is the `deck_replenished` mistake with a different noun.

6. **6 failing `test_rookie_scope.py` tests on `origin/main`.** *(unowned)* Pre-date this branch, verified by stashing. Nobody is tracking them.

---

## 2026-08-11 — P0 remediation status + deferrals

**Item 0 — the audit's nine launch blockers are settled.** Eight are **resolved** on `p0-remediation-2026-08-10` (commits 1-13); **P0-4 was withdrawn** by the operator before the build (the Mock Draft "dead end" was a stale config comment, not a dead end — see [`../docs/business/product/2026-08-09-mobile-ux-audit/06-resolutions.md`](../docs/business/product/2026-08-09-mobile-ux-audit/06-resolutions.md)). **P0-9 landed as test *preparation*, not the 32-tap first-session redesign** — the validation pass plus an operator runbook for the `trades_first_operator_test` experiment, in [`../docs/plans/audit-p0-remediation/prd-p0-8-9.md`](../docs/plans/audit-p0-remediation/prd-p0-8-9.md) §5 (summary in [`../docs/runbook.md`](../docs/runbook.md)). Running that first-session test is the operator's next move; the 32-tap question is still open and still wants pressure-testing before anyone acts on it.

**Deferred by this build, each with the evaluation on the record:**

0e. **Decide match accept/decline UX.** *(operator/product call)* — P0-6 option B. The route exists and web calls it; mobile has no accept/decline surface, so a matched user's only action is Send or Copy. Evaluation: [`lld-p0-6.md`](../docs/plans/audit-p0-remediation/lld-p0-6.md) §6.1. **The mobile `setMatchDisposition` wrapper was deleted; the route was deliberately kept** — deleting it would break the live web caller and the ELO consequences that ride it.

0f. **Add the `is_linked_platform_league` guard to `POST /api/sleeper/propose`.** *(backend, S)* — the client no longer offers Send on non-Sleeper leagues, but the route will still accept one and 400 late. Server-side is where the guarantee belongs. [`prd-p0-6.md`](../docs/plans/audit-p0-remediation/prd-p0-6.md) §6.2.

0g. **Fire `invite_shared` from the League tab's Invite module** (`LeagueScreen.tsx` `inviteLeaguemates`) — the name is registered now, but only the banner emits it, so **roughly half the invite volume is still unmeasured**.

0h. **SHIPPED 2026-08-14** (PR [#116](https://github.com/mattmurf77/fantasy-trade-finder/pull/116) → `main` @ `4733f78`, operator-confirmed bright-line change). Dropped-emitter backlog zeroed: 27 names registered as-shipped (+8 NON_INTENT rows), `quickset_completed` client emitter removed per the namespace-disjointness rule. Addendum: [`2026-08-13-dropped-emitter-backlog.md`](../docs/business/analytics/2026-08-13-dropped-emitter-backlog.md). Ship evidence in [`TEST_LEDGER.md`](TEST_LEDGER.md). [G-031]

0i. **Analytics prop gaps.** `source` is missing from `find_trades_tapped`'s server-side allowlist — generation-failure rate and retry uptake are unmeasurable until it is added (server side first). `unit` on `experiment_exposed` is registered but unemittable until `GET /api/feature-flags` returns `unit_type`. `FUNNEL_CRITICAL` and the mobile SDK mirror disagree on `app_opened_first` (in one, not the other, and in neither allowlist).

0k. **Derive mobile's three ladder-vocabulary copies from one constant, and give `tierForElo` its floor.** *(mobile, M — raised by P1-7, deliberately NOT built there)* Two facts, one item. (a) `mobile/src/utils/tierBands.ts` `tierForElo` ignores the `waivers` **1150 floor** that `backend/tier_config.json` and `RankingService.tier_for_elo` enforce, so a `no_value`-anchored player (Elo 1100) badges **FA** on mobile while the API answers `tier: null`. Fixing it makes `tierForElo` nullable and ripples into `autoBucket`/`autoBucketMixed` and `TiersScreen`'s zone model (its existing `unassigned` zone is the natural home). **P1-7's "no_value displays FA" decision leans on the current behaviour** — see [D-043](DECISIONS.md) — so this must be revisited together with it, not silently. (b) Mobile carries **three** copies of the ladder labels — `TIER_LABEL` (`tierBands.ts`), `TierBadge.tsx`, `chalkline/Badge.tsx`. They agree today and are not derived from one another; `anchorRows.ts` now shows the pattern to follow.

0j. **MFL / Fleaflicker harness profile.** No fixture profile covers them, so P0-6's non-Sleeper paths are proven by unit tests and one ESPN capture rather than by a flow. Waiver W2 in [`prd-p0-6.md`](../docs/plans/audit-p0-remediation/prd-p0-6.md).

---

## 2026-08-08 — Priority Queue

*(Refreshed during the living-memory revival pass; the 2026-06-10 queue was fully overtaken and lives in git history.)*

### Immediate

0. **Run the two Gate-C spikes.** *(sized, blocks S3)*
   *Why now:* device-auth **S0 shipped 2026-08-13** (FAAB fix, credential vault
   + legacy migration, Sentry credential-leak scrub; Maestro waived by the
   operator). The next stage, S3's GraphQL guard, is gated on two unanswered
   facts: **OI-9** the expo-updates evaluation memo (the PRD ordered it
   evaluated *first*, and nobody has), and **OI-12** whether Hermes provides
   `TextDecoder` — zero occurrences in `mobile/src`, and CI runs under node
   where it is a global, so every green build so far is non-evidence. If it is
   absent, the import-free rule forces a hand-written UTF-8 validating decoder
   *inside* the security control and S3 must be re-estimated at Gate C.
   Gates: [`../docs/plans/device-side-platform-auth-plan-2026-08-13.md`](../docs/plans/device-side-platform-auth-plan-2026-08-13.md) §8.

0a. **Verify #289 on the Dependables MFL league (62846).** *(5 minutes, live now)*
   *Why now:* it is the acceptance criterion the shipped batch never executed.
   Pass = franchise + player names; escalate = a high rate of `Player <mfl_id>`
   placeholders (stale player cache, not a code defect). The originally-proposed
   10% fallback bar was removed — real corpora measure 49%, so report the rate
   rather than gating on it. Detail in [`HANDOFF.md`](HANDOFF.md).

0b. **Run a mock draft in ffv3 and judge the board.** *(5 minutes, live now)*
   *Why now:* the engine shipped unflagged. If the top still reads wrong it is a
   **consensus values** question — Tate is the board's #2 rookie, so 4th is a
   two-slot fall — and belongs in a new item, not a reopened #290.

0c. **Decide the `feature_flags.py` `_load_from_env` hardening.** *(operator)*
   *Why now:* the patch is drafted and unapplied. It makes a malformed
   `FTF_FLAGS` fail loudly instead of silently returning `{}` — but `FTF_FLAGS`
   is a live Render kill-switch lever, so this turns a typo in a prod env var
   into a boot failure. Genuinely a blast-radius call, not a code-quality one.

0d. **Make the sim gate runnable end-to-end, or stop claiming it.** *(sized, not started)*
   *Why now:* the harness is honest for the first time (three flag-pin defects
   plus a bash-3.2 `$!` bug fixed and proven this session) — but the mock flow
   still cannot execute: `seed_ui_test_db.py` writes nothing for `mock_drafts`
   or draft status, and d1/d2/d3 target a league in no profile. Either fund the
   seeder work or drop the flows so the gap is visible instead of implied.

1. **Complete MFL client registration (form + cell-phone validation).** *(operator, external)*
   *Why now:* MFL send is **live and live-verified** — a real 2-for-2 proposal succeeded in
   prod 2026-08-12. Registration is the last pre-scale item: unregistered clients get MFL's
   tightest rate limits; registered ones get ~2.5x with a fixed `MFL_USER_AGENT`. Not urgent
   at one user, blocking before real volume. Still unexercised by any live call:
   `tradeResponse` and `pendingTrades` — `qa/verify-mfl-send.py` covers the revoke half.
2. **Make one real ESPN send from the app.** *(5 minutes, live now)*
   *Why now:* `espn.send` is ON and the write envelope is validated by negative probe
   (409 `TRAN_NOT_FOUND` for accept/decline; 409 `TRAN_INVALID_TRADE_TEAM_COUNT` for
   propose), but **no real ESPN send has been made from the app**. Three narrow unknowns
   need a real transaction: whether ESPN checks `teamId` is the true counterparty or derives
   it from SWID, whether `items` should be `[]` or omitted (persisted records disagree), and
   the success-response body the adapter parses. Treat the first real send as the confirming
   test, exactly as MFL's was. Requires build 103+.
3. **Resolve the two conflicting ESPN pick-assignment designs.** *(author/operator decision, not a merge)* — `teardown-remediation` reimplements a problem `origin/main` already shipped differently. Detail: [`HANDOFF.md`](HANDOFF.md).
4. **Execute the branch-triage verdicts.** *([`../docs/reviews/2026-08-08-branch-triage.md`](../docs/reviews/2026-08-08-branch-triage.md))* — 3 RECOVER are real gaps, 3 ASK need operator calls, 29 DELETEs pinned by worktrees.

### Near-term

5. **Decide `trade.finder_config_consolidated` (flag false).** +716 lines of `TradesScreen.tsx` sit uncommitted; docs already updated as though shipped.
6. **Graduate or kill `deck.value_model`.** The F8 replay harness runs nightly — the gate is checkable now. Now formalized as **P1-1 of [`../docs/plans/trade-relevance-engine/`](../docs/plans/trade-relevance-engine/)** (2026-08-14, HLD/LLD/PRDs shipped): the signed-off D4 criterion (pinned artifact, 21 counted nights, symmetric kill) + `train.value_model` flag split replace ad-hoc gate-reading; dev starts at PRD P0's B1, and the operator decision queue in `reconciliation-log.md` gates the rest.
7. ~~**Light `outlook.odds`**~~ — **DONE 2026-08-19 (operator override, [D-094](DECISIONS.md)).** The flag is `true` in `config/features.json`; the built-but-dark #169 layer (`f27c0f5`) goes live on the next merge to `main`. The Maestro flow this item owed is **waived by the operator** and was already void under D-056; the standing guard is `mobile/tests/check-outlook-bands.js` (7 assertions, all six sabotage cases proven red, gates CI via the `tests/check-*.js` glob). **What is lit and what is not:** playoff odds render as the three-band chip only; `title_pct` stays unrenderable at any week; `OUTLOOK_WEEK6_PERCENT_ENABLED` stays `false`. **Owed next:** the first TestFlight look at the lit surface — nobody has seen it on a device — and a decision on rendering `meta.priced_slot_coverage` on League Summary (Team Review specs the caption; League Summary still shows nothing, so IDP leagues read an offensive-core estimate as a whole-lineup one).

### Medium-term

8. **First public App Store release.** Checklist in `docs/business/ops/`; TestFlight-only through v1.11.0.
9. **Worktree/disk hygiene.** ~40+ worktrees (8.6 GB) already broke one EAS upload.

### Reserved

- **Browser-extension Chrome Web Store submission** — distribution strategy first (Q-008).
- **Mascot naming (Q-009)** — branding, no code dependency.
- **PR #91** (Depth tier color) — stale since 2026-07-04.

---

## Backlog — ranking-UI feedback (operator, 2026-08-18; not now)

**Tell the user when their votes can't do anything.** Two related gaps, both surfaced by the
override-pin work (see [`../docs/reviews/2026-08-18-valuation-age-audit.md`](../docs/reviews/2026-08-18-valuation-age-audit.md)
and D-069/D-070). Neither is urgent; both are the durable fix for the class of bug that
produced the Adams inversion.

1. **Analyst-driven "this vote can't move him" cue.** Under tier-bounded voting a player
   clamped at his tier floor cannot go lower — so a user who keeps passing on him gets no
   effect and no explanation. Surface it: *"You keep passing on X. He's at the bottom of
   his tier — re-tier him to move him lower."* Operator's framing: analyst-driven, reacting
   to a consistent pass pattern rather than a one-off.
2. **Show that a player is pinned at all.** Nothing on screen indicates a tier placement is
   constraining a player's value. The mechanism that let 17 down-votes do nothing is fixed;
   the *invisibility* that let it go unnoticed for weeks is not.

*Why it's backlog, not now:* the correctness bug is shipped-fixed (tier-bounded voting).
This is the affordance that stops it recurring silently — worth doing the next time anyone
is in the ranking UI, not as its own errand.

## Queue Hygiene Rules
- **Cap at 7 active items.** If you'd be adding an 8th, archive an old one or move it to "Reserved."
- **Each item has a clear *why now*.** Not a wish-list; an actionable next step.
- **Time-horizon labels** ("Immediate / Near-term / Medium-term") make commitment level explicit.
- **"Reserved" items have prerequisites** — note them.
- **After completing an item,** move it to [`CHANGELOG.md`](CHANGELOG.md) with the date and outcome; don't leave checkmarks here.
- **Queue caps at 1.5KB.** Delete superseded items outright (don't mark and keep them); trim any item's prose past ~3 lines while keeping its links.

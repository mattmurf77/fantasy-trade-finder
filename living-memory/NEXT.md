# Next — Fantasy Trade Finder

> **Purpose:** forward priority queue. 3–7 items, ordered, each with a one-line *why now*.
>
> **Read at:** session start, after CHANGELOG and HANDOFF. **Write at:** when something finishes or priorities shift.
>
> Companion files: [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) for items blocked on external input; [`CHANGELOG.md`](CHANGELOG.md) for what was done.

---

## Table of Contents
- [2026-08-14 — Year-in-Review capture follow-ons](#2026-08-14--year-in-review-capture-follow-ons)
- [2026-08-13 — Notification inbox follow-ons](#2026-08-13--notification-inbox-follow-ons)
- [2026-08-11 — P0 remediation status + deferrals](#2026-08-11--p0-remediation-status--deferrals)
- [2026-08-08 — Priority Queue](#2026-08-08--priority-queue)
- [Queue Hygiene Rules](#queue-hygiene-rules)

---

## 2026-08-14 — Year-in-Review capture follow-ons

P0 capture is built on `feat/roster-history` (see [`HANDOFF.md`](HANDOFF.md)). In order:

1. **Gate 0 — the scheduler oracle.** *(operator, ½ day)* Run the `player_value_history` density query (plans README) against prod. It changes cron-migration urgency, never the capture design. Then, **one week post-ship**, the `source`-column liveness read (runbook § roster-snapshot monitoring) + its retirement rule.
2. **P1 — backfill audit + C3 hardening.** What did P0 miss before it landed? Sleeper transaction-log replay is the salvage tool (plan §2.3, a salvage not a plan). C5's cadence backstop is already covered by `league_board_history`.
3. **P2 — end-of-season fetchers (F1–F8).** Verify ESPN/MFL transaction-log retention BEFORE the recap design leans on it; degrade trade P&L to Sleeper-only rather than blocking the recap.
4. **P3 — recap compute + UI + the nine analytics events**, taxonomy addendum registered before any emitter, `wrapped_viewed` finally fires. Monetization call (free vs premium hook) is owed **before** P3 starts.

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
7. **Light `outlook.odds` (decision + lighting checklist).** Corrected 2026-08-11 — the earlier claim that the flag was absent from `config/features.json` was stale: it is **present and `false`** there, so the endpoint is reachable, just flag-dark. Built on both ends (backend `/api/league/outlook` + LeagueSummary section; frame-E collapsed strip **shipped dark 2026-08-11**, `f27c0f5` — `docs/feedback/items/169-outlook-league-summary/`). Lighting owes: a Maestro flow for the section + strip states and a seeded outlook fixture for the harness (the `outlook_strip_toggled` event ships specced + wired with the strip build — operator rejected that waiver) — see `docs/feedback/items/169-outlook-league-summary/scope.md` §1/§3.

### Medium-term

8. **First public App Store release.** Checklist in `docs/business/ops/`; TestFlight-only through v1.11.0.
9. **Worktree/disk hygiene.** ~40+ worktrees (8.6 GB) already broke one EAS upload.

### Reserved

- **Browser-extension Chrome Web Store submission** — distribution strategy first (Q-008).
- **Mascot naming (Q-009)** — branding, no code dependency.
- **PR #91** (Depth tier color) — stale since 2026-07-04.

---

## Queue Hygiene Rules
- **Cap at 7 active items.** If you'd be adding an 8th, archive an old one or move it to "Reserved."
- **Each item has a clear *why now*.** Not a wish-list; an actionable next step.
- **Time-horizon labels** ("Immediate / Near-term / Medium-term") make commitment level explicit.
- **"Reserved" items have prerequisites** — note them.
- **After completing an item,** move it to [`CHANGELOG.md`](CHANGELOG.md) with the date and outcome; don't leave checkmarks here.
- **Queue caps at 1.5KB.** Delete superseded items outright (don't mark and keep them); trim any item's prose past ~3 lines while keeping its links.

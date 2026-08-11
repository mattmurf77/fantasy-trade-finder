# Next — Fantasy Trade Finder

> **Purpose:** forward priority queue. 3–7 items, ordered, each with a one-line *why now*.
>
> **Read at:** session start, after CHANGELOG and HANDOFF. **Write at:** when something finishes or priorities shift.
>
> Companion files: [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) for items blocked on external input; [`CHANGELOG.md`](CHANGELOG.md) for what was done.

---

## Table of Contents
- [2026-08-11 — P0 remediation status + deferrals](#2026-08-11--p0-remediation-status--deferrals)
- [2026-08-08 — Priority Queue](#2026-08-08--priority-queue)
- [Queue Hygiene Rules](#queue-hygiene-rules)

---

## 2026-08-11 — P0 remediation status + deferrals

**Item 0 — the audit's nine launch blockers are settled.** Eight are **resolved** on `p0-remediation-2026-08-10` (commits 1-13); **P0-4 was withdrawn** by the operator before the build (the Mock Draft "dead end" was a stale config comment, not a dead end — see [`../docs/business/product/2026-08-09-mobile-ux-audit/06-resolutions.md`](../docs/business/product/2026-08-09-mobile-ux-audit/06-resolutions.md)). **P0-9 landed as test *preparation*, not the 32-tap first-session redesign** — the validation pass plus an operator runbook for the `trades_first_operator_test` experiment, in [`../docs/plans/audit-p0-remediation/prd-p0-8-9.md`](../docs/plans/audit-p0-remediation/prd-p0-8-9.md) §5 (summary in [`../docs/runbook.md`](../docs/runbook.md)). Running that first-session test is the operator's next move; the 32-tap question is still open and still wants pressure-testing before anyone acts on it.

**Deferred by this build, each with the evaluation on the record:**

0e. **Decide match accept/decline UX.** *(operator/product call)* — P0-6 option B. The route exists and web calls it; mobile has no accept/decline surface, so a matched user's only action is Send or Copy. Evaluation: [`lld-p0-6.md`](../docs/plans/audit-p0-remediation/lld-p0-6.md) §6.1. **The mobile `setMatchDisposition` wrapper was deleted; the route was deliberately kept** — deleting it would break the live web caller and the ELO consequences that ride it.

0f. **Add the `is_linked_platform_league` guard to `POST /api/sleeper/propose`.** *(backend, S)* — the client no longer offers Send on non-Sleeper leagues, but the route will still accept one and 400 late. Server-side is where the guarantee belongs. [`prd-p0-6.md`](../docs/plans/audit-p0-remediation/prd-p0-6.md) §6.2.

0g. **Fire `invite_shared` from the League tab's Invite module** (`LeagueScreen.tsx` `inviteLeaguemates`) — the name is registered now, but only the banner emits it, so **roughly half the invite volume is still unmeasured**.

0h. **Register the 29 remaining dropped client `track()` names.** A sweep found 33 of 73 unregistered; this batch fixed 3. Full list: [`lld-p0-8-9.md`](../docs/plans/audit-p0-remediation/lld-p0-8-9.md) §4.3 and the [P0-7 addendum](../docs/business/analytics/2026-08-11-p0-7-addendum.md). Start with `guide_tour_reenabled` (blocks a manual QA check). **`quickset_completed` is different** — it is server-authoritative and the namespaces are disjoint by assertion, so the fix is to **remove the client emitter** (`QuickSetTiersScreen.tsx:330`), not register the name. Its client emission was dropped from this build for that reason. [G-029]

0i. **Analytics prop gaps.** `source` is missing from `find_trades_tapped`'s server-side allowlist — generation-failure rate and retry uptake are unmeasurable until it is added (server side first). `unit` on `experiment_exposed` is registered but unemittable until `GET /api/feature-flags` returns `unit_type`. `FUNNEL_CRITICAL` and the mobile SDK mirror disagree on `app_opened_first` (in one, not the other, and in neither allowlist).

0j. **MFL / Fleaflicker harness profile.** No fixture profile covers them, so P0-6's non-Sleeper paths are proven by unit tests and one ESPN capture rather than by a flow. Waiver W2 in [`prd-p0-6.md`](../docs/plans/audit-p0-remediation/prd-p0-6.md).

---

## 2026-08-08 — Priority Queue

*(Refreshed during the living-memory revival pass; the 2026-06-10 queue was fully overtaken and lives in git history.)*

### Immediate

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

1. **Review + graduate `feat/send-in-mfl`.** *(built this session, unmerged)* — complete build (adapter, `/api/trades/propose-mfl`, `trade.send_in_mfl` OFF, platform-aware button fix, 2412 tests green). Blocked on the 8-item live-verification checklist + MFL client registration + 3 operator questions (MFL-login-as-verified?, single-linker leagues?, `trade_sent` event?). Detail: [`HANDOFF.md`](HANDOFF.md), scope: `../docs/feedback/items/177-mfl-auth-link/send-in-mfl-scope.md`.
2. **Decide the ESPN send NO-GO reversal + run probe #1.** *(operator)* — `spike/send-in-espn-write` scaffolds the write path (all football values UNVERIFIED, `espn.send` OFF + absent from `config/features.json`). First live probe = capture one real browser Propose-Trade in a throwaway ESPN dynasty league (resolves the `espn_id`==`playerId` load-bearer). Reversal is a hand-added `DECISIONS.md` D-entry, post-scorecard. Artifacts: `../docs/plans/espn-send-spike-verification-2026-08-11.md`, `...decision-reversal-draft-2026-08-11.md`.
3. **Resolve the two conflicting ESPN pick-assignment designs.** *(author/operator decision, not a merge)* — `teardown-remediation` reimplements a problem `origin/main` already shipped differently. Detail: [`HANDOFF.md`](HANDOFF.md).
4. **Execute the branch-triage verdicts.** *([`../docs/reviews/2026-08-08-branch-triage.md`](../docs/reviews/2026-08-08-branch-triage.md))* — 3 RECOVER are real gaps, 3 ASK need operator calls, 29 DELETEs pinned by worktrees.

### Near-term

5. **Decide `trade.finder_config_consolidated` (flag false).** +716 lines of `TradesScreen.tsx` sit uncommitted; docs already updated as though shipped.
6. **Graduate or kill `deck.value_model`.** The F8 replay harness runs nightly — the gate is checkable now.
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

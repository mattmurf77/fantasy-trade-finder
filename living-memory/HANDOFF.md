# Handoff — Fantasy Trade Finder

> **Purpose:** forward-looking session handoff. Where am I right now, what's half-done, what's next, what's blocking. Like a doctor's shift handoff sheet — different from CHANGELOG (which is backward-looking).
>
> **Read at:** session start. **Write at:** session end (or before stopping for the day).
>
> Companion files: [`CHANGELOG.md`](CHANGELOG.md), [`NEXT.md`](NEXT.md).

---

## Table of Contents
- [2026-08-12 — Send in MFL + Send in ESPN live; device-side auth designed, not built](#2026-08-12--send-in-mfl--send-in-espn-live-device-side-auth-designed-not-built)
- [2026-08-11 — #169 frame E + card frame C shipped; sim debt owed](#2026-08-11--169-frame-e--card-frame-c-shipped-sim-debt-owed)
- [2026-08-11 — Send-in-MFL built + Send-in-ESPN spiked; both on branches, unmerged](#2026-08-11--send-in-mfl-built--send-in-espn-spiked-both-on-branches-unmerged)
- [Handoff Template (for future sessions)](#handoff-template-for-future-sessions)

---

## 2026-08-12 — Send in MFL + Send in ESPN live; device-side auth designed, not built

### Where things stand

**Shipped and live.** `main` @ `cad99fb`. Both new send paths are ON in production —
verified by content, not by a deploy badge: `/api/feature-flags` serves
`trade.send_in_mfl: true` and `espn.send: true`. TestFlight 1.13.1 **build 107** is the
current build. **MFL send is live-verified end-to-end** (a real 2-for-2 proposal
succeeded; `trade_sent {platform:"mfl", outcome:"proposed"}`). ESPN send is shipped and
its write envelope is validated, but **no real ESPN send has been made from the app yet**.

**Designed, not built:** device-side platform auth (ADR-011 + HLD on
`design/device-side-platform-auth`, unmerged). Its blocking unknown is **resolved** —
Sleeper's Cloudflare edge accepts iPhone requests, PASS 4/4.

### The five things a next session should know

1. **Do NOT port the Chrome spoof to the device.** Honest iOS headers passed identically
   (`docs/plans/sleeper-ios-reachability-probe-result-2026-08-12.md`). The server spoofs
   because a datacenter IP needs cover; a phone doesn't, FTF has Sleeper's permission, and
   a tolerated UA/fingerprint mismatch is a latent failure if Cloudflare tightens.
2. **ESPN pending-trade reads: trust `mPendingTransactions`, not `mTransactions2`.** The
   pending feed is self-pruning and authoritative. History freezes a proposal's `status` at
   creation, so a **declined** proposal reads `PENDING` there forever (8/8 across two
   leagues) and `isPending` is `true` even on `CANCELED` rows — it is junk, never branch on
   it. This makes the planned inbox read *simpler* than designed: one call, not two.
3. **MFL uses unix SECONDS; ESPN uses epoch MILLISECONDS.** Any normalized model across
   platforms must convert or expiry dates land in 1970.
4. **The MFL write path's only untested surfaces are `tradeResponse` and `pendingTrades`
   writes.** Propose is proven. `qa/verify-mfl-send.py` covers the revoke half.
5. **`eas build` exits 0 even when the remote build ERRORED.** Always read
   `eas-cli build:list --json`. A concurrent session lost two builds to this.

### Owed

- **MFL client registration** (form + phone validation) before real traffic — unregistered
  clients get the tightest rate limits. Operator, external.
- **Sim gate** — waived by operator all session (`FTF_SKIP_SIM_GATE=1`); CI never ran on
  any of today's pushes. Everything was verified by targeted tests instead.
- **A real ESPN send from the app**, to confirm the response parsing the same way MFL's was.
- **PRD/HLD/LLD/Plan for device-side auth** — the dual-agent run produced both PRD drafts
  and was stopped before merging. **Re-frame before resuming:** the drafts were told the
  goal was reducing blocking *volume*, and both optimized against that. The operator
  corrected it — the driver is the **terms**, which concern credentialed calls, so public
  reads staying on Render was never a gap and the "wrong traffic" critique mostly dissolves.
  Sleeper offers **no allowlist**, so that fallback is dead too.

### Traps this session paid for

- **A stale-checkout `DECISIONS.md` commit would have destroyed 13 decision records.** Main
  had issued D-026…D-038 from concurrent sessions while this session drafted its own D-026.
  Renumbered to **D-039** and appended to main's file. `origin/main` moved **four times**
  today. Claim IDs against `origin/main`, never your working tree.
- **`.easignore` uses gitignore semantics** — a bare `screens/` matched at any depth and
  stripped every app screen from the archive, killing two builds in another session. The fix
  (`53bd19f`) was merged in *before* building here. Anchor every root entry.
- **Adding any key to `config/features.json` requires mirroring it into three fixtures**
  (`release`, `onboarding-v2`, `profiles-on`) or `test_seed_ui_test_db.py` fails. Bit twice.
- **Three attempts to capture a live browser request by injecting a `fetch`/XHR hook all
  failed identically** — a full page load destroys the injection, and `sessionStorage`
  preserves captured *data* but not the *hook*. What worked was inverting it: make the call
  deliberately and report the outcome as an analytics event.
- **A permission-classifier block is not necessarily permanent** — the same
  `FTF_SKIP_SIM_GATE=1 git push` was refused four times and succeeded unchanged on the fifth.

---

## 2026-08-11 — P0 remediation batch shipped (sim gate skipped, owed next session)

### Where things stand
- **The eight-P0 audit remediation batch is merged to `main` and pushed** from branch
  `p0-remediation-2026-08-10` (15 code commits + the #169 merge). Render auto-deploys
  from `main`; verify the deploy dashboard on next session start.
- Suite at ship: **2448 passed / 1 skipped**, tsc clean, testid-lint OK, both node
  test suites green. Full planning corpus in `docs/plans/audit-p0-remediation/`.
- **Living-memory ID collision resolved at merge:** #169's session claimed D-025 and
  G-027/G-028 first; this batch's entries were renumbered to **D-026..D-033 and
  G-029..G-034** across all 26 referencing files. Root CLAUDE.md's "next ID" note
  already says grep-first.

### What's owed (highest priority first)
1. **The tier-1 sim run** — skipped by operator direction (usage). Full owed list in
   TEST_LEDGER's 2026-08-11 P0-batch entry: six new flows, five modified captures,
   the P0-9 beat validation, analytics destination checks, freshness sweep.
2. **`growth.invite_join_link` stays OFF** until AASA propagation is verified
   (~24h CDN) — the operator sequence is in `prd-p0-3.md` §4. The reader/route/claim
   shipped unflagged and are live.
3. **The operator's P0-9 test** — zero-code recipe in `prd-p0-8-9.md` §5
   (experiment overlay, device allowlist; confirm the operator device id in
   `config/tester_allowlist.json` is current first).
4. **Pre-merge experiment readback was documentary, not live** — the one-line
   authenticated `GET /api/admin/experiments` check (no live experiment targets
   `ranking_method`) is still worth running once against prod.

### Environment notes
- Worktree `ftf-p0-remediation` at `/Users/teresadickens/Documents/Claude/Projects/`
  now carries a REAL `mobile/node_modules` (npm ci) — the symlink convention is dead,
  see TEST_LEDGER. Sweep the worktree per the recovery-ledger convention once content
  is verified on `origin/main`.
- A P1 planning session ("Ping") was handed the 8-item P1 batch with the same
  pipeline; its plans should rebase on this merge.

---

## 2026-08-11 — Send-in-MFL built + Send-in-ESPN spiked; both on branches, unmerged

### Where I am right now

Two Fable subagents (isolated worktrees) extended the one-click trade-send beyond
Sleeper. **Nothing merged, nothing shipped** — both are complete-on-branch and
blocked on operator decisions + live third-party verification. Research that seeded
the work: [`../docs/plans/send-in-mfl-research-2026-08-11.md`](../docs/plans/send-in-mfl-research-2026-08-11.md),
[`../docs/plans/send-in-espn-research-2026-08-11.md`](../docs/plans/send-in-espn-research-2026-08-11.md).

**MFL — `feat/send-in-mfl` (based on `ab9368f`), a real build, ready for review.**
MFL has a *documented, sanctioned* write API (`import?TYPE=tradeProposal`) and FTF
already stores the required `MFL_USER_ID` cookie (#177) — this is the inverse of
Sleeper's ToS-adverse private-GraphQL replay. Landed: `backend/mfl_write.py`
adapter, `POST /api/trades/propose-mfl` route (verified-session gate,
server-authoritative franchise resolution, **hard-block 422 `mfl_asset_unmapped`**
on any un-reverse-mapped asset), `trade.send_in_mfl` flag (**OFF everywhere**),
36 new backend tests, and the mobile `SendInSleeperButton` turned into a true
platform router (`mfl` → new `SendInMflButton`; any non-Sleeper platform → null —
**this fixes the researched bug where the Sleeper button rendered on MFL/Fleaflicker
leagues and would fire at Sleeper's API**). Backend suite **2412 passed, 1 skipped**;
`tsc` clean; testid-lint OK. Players-only v1 (route already accepts pre-encoded pick
assets). No live MFL call was ever made.

**ESPN — `spike/send-in-espn-write` (based on `origin/main` @ `17eb62b`), a spike,
NOT a build.** `backend/espn_write.py` scaffolds the community-captured
`TRADE_PROPOSAL` envelope with **every football-specific value tagged `# UNVERIFIED`**
(the only live capture in the wild is *baseball*). 20 payload-construction tests.
`espn.send` flag added **default-OFF and deliberately kept OUT of
`config/features.json`** so it physically cannot be flipped. Two decision artifacts
for the operator: `../docs/plans/espn-send-spike-verification-2026-08-11.md`
(live-probe checklist + go/no-go scorecard) and
`../docs/plans/espn-send-decision-reversal-draft-2026-08-11.md` (a **draft** — the
standing "Send in ESPN write — NEVER" NO-GO in `../docs/plans/espn-league-linking-plan-2026-07-11.md`
§2/§7 is **untouched** and still binding).

### What blocks each — operator + live third-party, not code

- **ESPN load-bearing unknown:** does the DynastyProcess crosswalk's `espn_id`
  equal the write-API's `playerId`? If not, the whole player-mapping approach is
  invalid. **First probe:** capture one real browser Propose-Trade request in a
  throwaway ESPN dynasty test league — resolves that + "do read cookies authorize
  writes" + pick handling in one shot. Needs a real test league + fresh cookies.
- **ESPN decision gate:** reversing the NO-GO must be a hand-added `DECISIONS.md`
  D-entry, and only after the scorecard's blocking probes pass. Left to operator.
- **MFL live checklist (8 items, in the scope block):** import host (`wwwNN` vs
  `api.`), real success/error response body shape, `DP_`/`FP_` pick encoding
  against a live league, cookie-on-import auth, trade-disabled-league error,
  `EXPIRES` semantics, end-to-end staging send, and **MFL client registration**
  (form + phone) before real traffic (unregistered writes are most 429-exposed).
- **MFL open questions:** (1) should a successful MFL login (#177) count as session
  `verified` so MFL-only users (no Apple/Google sign-in) can send at all? (2) v1
  only lets the *linking* user send from a league — acceptable? (3) want a
  `trade_sent` analytics event (neither platform fires one today — spec both in one
  taxonomy change)?

### Not done, on purpose

- No `trade_sent` analytics event on either path. No `tradeResponse` route (adapter
  has the helper; revoke UX is a follow-up). MFL Maestro flow
  (`mobile/.maestro/flows/trade-send/mfl-send-gating.yaml`) is **authored but
  unrunnable** — `seed_ui_test_db.py` has no `mfl` seed profile (only sleeper/espn);
  a structural JS test (`mobile/tests/check-send-button-platform.js`) pins the
  routing in the meantime. Living-memory was reconciled by the parent session (here).

### Carryover still open from 2026-08-10 (below) — unchanged

Verify #289 on Dependables MFL league 62846; run a mock draft in ffv3; the
`_load_from_env` hardening operator call; and the sim-gate seeder gap all remain
open. See the next section.

---

## 2026-08-11 — #169 frame E + card frame C shipped; sim debt owed

### Where I am right now

**Shipped.** PR #107 squash-merged as `f27c0f5`, CI green (backend-tests /
mobile-typecheck / testid-lint), content verified on `origin/main`. League
Summary outlook strip (dark, `outlook.odds`), Pass/Like inside the top deck
card, `outlook_strip_toggled` in the taxonomy. Doc set + decisions record in
`docs/feedback/items/169-outlook-league-summary/` (all operator questions
resolved — §7/§8 + D-025). Build worktrees swept via
`docs/recovery/2026-08-11-169-worktree-sweep.md`.

### What a next session should actually do

1. **Pay the sim debt** (operator halted the Tier-1 run mid-gate for usage
   cost — scope.md §5): green full smoke run, the four re-captures
   (`trades`, `matches`, `sheets-trade-dna`, `league-summary`) +
   `screen-freshness.sh`, on-sim verify of the three re-derived
   `onboarding-tour@fresh` anchors, and the `06-trades-deck` like/pass
   tap-through (its positional `childOf` asserts already passed on-sim
   pre-halt; the tap-through was blocked only by the tour-overlay harness
   mistake, since fixed).
2. **`outlook.odds` lighting checklist** is NEXT item 7 — flow + fixture
   owed; the analytics event is already wired.

### Traps this session paid for — don't re-learn

- **Smoke flows declare `# flags: release`** — start Flask with
  `FTF_FLAGS="$(cat backend/tests/fixtures/flags/release.json)"` or the
  guided-avatar tour overlay swallows taps and 6 flows fail identically.
- **Long-lived processes must be harness-tracked background tasks** — a
  `nohup … &` Flask inside a tool call gets reaped by shell teardown.
- **G-027**: `npm ci` re-hoists packages → run `pod install` (with
  `LANG=en_US.UTF-8`) before `sim-build.sh`, and never read a build result
  through a `| tail` pipe.
- **Disk**: this 8 GB machine hit 0 bytes free mid-session (agent-worktree
  `npm ci`s) → 25 Hermes launch crash-loops that looked like an app bug.
  Check `df` before long sim sessions; the sweep freed ~4 GB.
- **After `simctl erase`, kill Maestro** (`pkill -f maestro`) — a stale
  XCTest driver session makes every flow fail at the first assert while the
  app is actually healthy.
- **G-028**: 6 `test_rookie_scope.py` failures in a data-carrying checkout
  are pre-existing and environmental — CI/clean worktrees pass.

### Open, not blocking

- Task chips filed: phantom testIDs in `docs/plans/mobile-testing/lld.md`
  (running in another session); rookie-scope hermeticity fix.
- The prior batch's two verification items (#289 Dependables check, ffv3
  mock-draft judgment) remain NEXT 0a/0b — untouched by this session.

# Handoff — Fantasy Trade Finder

> **Purpose:** forward-looking session handoff. Where am I right now, what's half-done, what's next, what's blocking. Like a doctor's shift handoff sheet — different from CHANGELOG (which is backward-looking).
>
> **Read at:** session start. **Write at:** session end (or before stopping for the day).
>
> Companion files: [`CHANGELOG.md`](CHANGELOG.md), [`NEXT.md`](NEXT.md).

---

## Table of Contents
- [2026-08-15 — Sleeper co-owner support built on `claude/epic-hellman-6af20f`, unmerged](#2026-08-15--sleeper-co-owner-support-built-on-claudeepic-hellman-6af20f-unmerged)
- [2026-08-14 — Deck-outcome ownership validation SHIPPED (PR #119)](#2026-08-14--deck-outcome-ownership-validation-shipped-pr-119)
- [2026-08-14 — Year-in-Review P0 roster capture built on `feat/roster-history` (worktree)](#2026-08-14--year-in-review-p0-roster-capture-built-on-featroster-history-worktree) — SHIPPED (PR #120), capture live
- [2026-08-14 — Dropped-emitter backlog SHIPPED (PR #116); G-031 backlog zeroed](#2026-08-14--dropped-emitter-backlog-shipped-pr-116-g-031-backlog-zeroed)
- [2026-08-13 — Mock draft repaired + manual mode shipped (v1.13.3 build 110); Tier-1 sim owed](#2026-08-13--mock-draft-repaired--manual-mode-shipped-v1133-build-110-tier-1-sim-owed)
- [2026-08-13 — Device-auth design programme complete; branch awaits operator push](#2026-08-13--device-auth-design-programme-complete-branch-awaits-operator-push)
- [2026-08-13 — Notification inbox growth surface SHIPPED (PR #113, build 109)](#2026-08-13--notification-inbox-growth-surface-shipped-pr-113-build-109)
- [2026-08-12 — Feedback #297–#302 and #300 both shipped; #300 is lit and unproven on-device](#2026-08-12--feedback-297302-and-300-both-shipped-300-is-lit-and-unproven-on-device)
- [2026-08-12 — Send in MFL + Send in ESPN live; device-side auth designed, not built](#2026-08-12--send-in-mfl--send-in-espn-live-device-side-auth-designed-not-built)
- [2026-08-11 — #169 frame E + card frame C shipped; sim debt owed](#2026-08-11--169-frame-e--card-frame-c-shipped-sim-debt-owed)
- [2026-08-11 — Send-in-MFL built + Send-in-ESPN spiked; both on branches, unmerged](#2026-08-11--send-in-mfl-built--send-in-espn-spiked-both-on-branches-unmerged)
- [Handoff Template (for future sessions)](#handoff-template-for-future-sessions)

---

## 2026-08-15 — Sleeper co-owner support built on `claude/epic-hellman-6af20f`, unmerged

### Where I am right now

Built, fully tested, **not pushed**. Branch `claude/epic-hellman-6af20f` (worktree
`.claude/worktrees/epic-hellman-6af20f`), branched from `origin/main` @ `21df73f`.

FTF had never read Sleeper's `co_owners`, so the operator's own co-managed
league (roster 3 of `1338231586314780672`) resolved to no team — and posted his
own roster back as a leaguemate for the engine to trade against. Fixed by making
a co-owner an **alias** of the roster's primary `owner_id`, and giving every
session two identities: ACCOUNT (`sess["user_id"]`) and LEAGUE
(`_league_user_id()`). Identical for a sole owner. Full reasoning — including
why the one-line client fix is *worse* than the bug — in
[ADR-012](../docs/adr/adr-012-co-owned-roster-identity.md) / [D-051](DECISIONS.md);
scope block `docs/plans/sleeper-co-owner-rosters/scope.md`.

### What's verified

- Backend suite **2796 passed / 1 skipped**; `tsc --noEmit` clean; testid-lint OK;
  all 24 mobile structural suites green. See [TEST_LEDGER.md](TEST_LEDGER.md).
- `test_co_owner_rosters.py` (33 tests) is a **proven** regression test: narrowing
  the predicate back to `owner_id` alone fails 7 of them.

### Next action

1. **Operator: review + push.** `git push -u origin claude/epic-hellman-6af20f`,
   open the PR, let CI confirm.
2. **Verify on the real league after deploy** — the whole point. Open Bush League
   (`1338231586314780672`) in the app: roster 3's 19 players should be *your*
   team, League rankings should show 12 teams with the "You" badge on Manager 3's
   row, and the acquire pool must not contain your own players.

### Watch items

- **`member_rankings` is deliberately untouched** — a co-owned team's board still
  reaches leaguemates only if the *primary* owner uses FTF. Logged in
  [NEXT.md](NEXT.md); needs a product call, not a code change, first.
- **Worktree hygiene:** this worktree has a symlinked `mobile/node_modules` and a
  **copied** `mobile/ios/Pods` + `mobile/ios/build/generated` (borrowed from the
  main checkout — lockfiles verified identical) so the sim build could run. All
  gitignored; delete with the worktree per the recovery-ledger procedure.

---

## 2026-08-14 — Deck-outcome ownership validation SHIPPED (PR #119)

### Where I am right now

The LLD-review validation hole in `_save_deck_outcome_safe` (any client-supplied
`impression_id` wrote `deck_outcomes` and, under `deck.taste_vectors`, the
**impression owner's** taste vector — cross-user taste poisoning) is **fixed,
tested and SHIPPED**: operator said ship,
[PR #119](https://github.com/mattmurf77/fantasy-trade-finder/pull/119) merged to
`main` (CI green: backend-tests, mobile-typecheck, testid-lint). Merge race
note: PR #120 (roster history) landed mid-ship and claimed D-049, so this
decision is **[D-050](DECISIONS.md)**; the merge resolved four living-memory
conflicts and the full suite was re-run on the merged tree.

- Helper now requires `acting_user_id` (route-resolved); writes only for an
  existing, self-owned, ≤30-day-old impression. Six call sites updated
  (swipe, flag, /api/events, Sleeper/MFL/ESPN propose). Rejects
  counted-and-dropped ([D-050](DECISIONS.md)); counters on
  `/api/admin/analytics/health` as `deck_outcome_rejects`.
- Scope block: `docs/plans/deck-outcome-validation/scope.md`; api-reference
  updated. Sim-gate tier 4 (backend-only) — no sim run owed.

### What a next session should know

1. **Behavior note:** the /api/events deck-signal side-channel now requires a
   live session token — dead-token batches drop deck signals as `no_user`.
   Watch `deck_outcome_rejects` after deploy; a high `no_user`/`stale` count
   would mean real clients are sending outcomes we now drop (offline queues
   older than 30 days are lost by design).
2. `docs/plans/trade-relevance-engine/` (landed on `main` the same day, mid-ship)
   specs this same validation inside the larger initiative (P0 PRD R6) — when
   P0 builds, reconcile against this shipped subset rather than rebuilding.

## 2026-08-14 — Year-in-Review P0 roster capture built on `feat/roster-history` (worktree)

### Where I am right now

**SHIPPED** — squash PR #120 → `main` @ `81dd6d2`, CI green, Render deployed, and **capture is
LIVE**: Writer C was fired once against prod and swept 11/12 leagues (131 roster rows + 16
board rows, `source='weekly'`, period `2026-W33`) across Sleeper, ESPN (stored-cookie) and
MFL. Branch + worktree swept per the recovery ledger. **FULL gates** — scope block filled.

### The load-bearing facts for whoever touches this

1. **Precedence, not recency:** `weekly` (server-fetched, orphans included) outranks `sync`
   (client-posted). The on-sync writer no-ops when a weekly row holds the period. Breaking
   this silently deletes orphan teams (YR-6).
2. **The snapshot block is LAST in the session-init daemon** — the pick fold-in reads
   `draft_picks`, which the owned-pick sibling block writes. Reordering makes `pick_ids`
   quietly short.
3. **Never move the platform snapshot call inside `replace_espn_league_members`'s
   transaction** (zero-members failure mode). Seven callers, all hooked after commit.
4. **Gate 0 is still with the operator** (the `player_value_history` density query — the
   plans README). It changes cron-migration urgency, not this design. One week post-ship,
   run the `source`-column liveness read (runbook).
5. **The review docs' ISO example was wrong** (2026-12-31 = `2026-W53`); tests pin the truth.
6. **C3 shipped in P0** — the mock-draft branches that blocked it are merged (PR #114),
   though the stale branch refs still exist on origin.

### Owed / next

- **P1:** C5 personal-Elo cadence backstop is COVERED by `league_board_history`; remaining
  P1 item is the backfill audit. **P2:** end-of-season fetchers + ESPN/MFL transaction-log
  retention check. **P3:** recap compute + UI + the nine analytics events (addendum first).
- ~~The sweep has never run live~~ — it has now (one manual Writer C run, above). Still
  owed: the FIRST scheduled `daily-tick` firing is the real liveness evidence (run the
  `source`-column read next week); the `espn_reconnect` path has no expired cookie to
  exercise it yet; mobile renders the new type as a grey bell until the next TestFlight
  build picks it up (deliberate — not worth a build alone).

---

## 2026-08-14 — Dropped-emitter backlog SHIPPED (PR #116); G-031 backlog zeroed

### Where I am right now

The G-031 dropped-emitter backlog (NEXT 0h — "29 remaining") is **SHIPPED**:
operator confirmed the bright-line taxonomy change, PR
[#116](https://github.com/mattmurf77/fantasy-trade-finder/pull/116) squash-merged
to `main` @ `4733f78` with CI green (backend-tests, mobile-typecheck,
testid-lint). Deploy-then-probe result in `TEST_LEDGER.md`. Branch + worktree
swept per `docs/recovery/2026-08-14-taxonomy-batch-sweep.md`.

- **27 names registered** in `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS`
  (props mirror the shipped emitters verbatim — no reserved keys, no renames);
  8 impression/dismissal/outcome-class names added to `NON_INTENT_EVENTS` in
  the same change (DAU-seam rule).
- **1 emitter deleted:** client `quickset_completed`
  (`QuickSetTiersScreen.tsx`) — server-authoritative name, disjointness
  assert makes registration impossible. Accepted loss: its `onboarding` prop.
- **Docs:** addendum `docs/business/analytics/2026-08-13-dropped-emitter-backlog.md`
  (per-event table: call sites, props, INTENT class, teardown-PRD source);
  cross-client-invariants updated (backlog 29 → 0); G-031 + NEXT 0h updated.
- **Verified:** import asserts + 243 backend tests green (events/analytics/
  observability/mock-draft/pick-assignment suites). Mobile `tsc` NOT run — no
  `node_modules` in the worktree; owed at merge.

### What a next session should know

1. **The seam:** rows for all 27 names begin 2026-08-14; 19 are INTENT, so
   INTENT coverage widens — don't trend per-feature action counts across it.
2. **The `onboarding` split on quickset completions is gone** (accepted loss,
   recorded in the addendum). If it's ever wanted, that's a NEW client name
   via a fresh addendum — never a resurrection of `quickset_completed`.
3. Most of the newly measurable surfaces sit behind still-dark teardown
   flags (`ux.*`, `growth.rating_prompt`) — zero rows for those is the flag,
   not a bug. The flagless ones (undo family, untouchable, settings modes,
   trios) should show rows immediately.

### Blocking

Nothing. Done end-to-end.

### Where I am right now

**#295/#296/#305 shipped** — `e71a654` (PR #114), TestFlight **build 110, v1.13.3**,
submitted and processing. The mock draft works for the first time: the user is in
their own draft, prompted at their slots, CPU resumes after each pick. New
`mode: "cpu" | "manual"` ("You pick for: Your team / Every team"). All three items
`fixed`. Analytics live and probe-verified in prod. **19 feedback items open.**

### The two things a next session should do first

1. **The Tier-1 sim run this ship owes.** Flows `d3` (retargeted to `draft-pre`)
   and `d4-mock-manual-mode` are authored, lint-clean, never executed. The PRD
   recommends Tier 1 explicitly; the operator shipped without it. This is the
   third consecutive mock-draft batch to skip the sim — the first skip is why
   the feature was broken for a week.
2. **Verify on the operator's live leagues** — ffv3 (Sleeper, assigned order,
   operator at slot 8) and Newton (ESPN 11896, 14 teams, randomized branch).
   Newton showing 14 picks/round with the user prompted is the acceptance test
   #305 stated.

### What bit us, so it doesn't again

- **The caller-excluded `sess["league"].members` convention claimed its third
  victim** (FB #41, #291, now the mock). Five membership sites this time; the
  fifth (`_mock_usernames`) was found only at LLD. When a surface reads
  "everyone in the league", grep for ALL its member reads.
- **The deploy-liveness poll trap:** the old build answers an unregistered event
  with `accepted:1, dropped:1` — a loose grep on `accepted` reads that as live.
  Require `accepted ≥ 1 AND dropped == 0`.
- **The test-world seeder had traded away the QA user's round-1 pick**, so a
  1-round mock completed at create in the fixtures too — the shipped bug
  reproduced in miniature where no test could see it. Fixture worlds need the
  same adversarial reading as prod.

### Owed / open

- Tier-1 sim run (above); `aggregate_tier_labels` still operator-only; #300
  decision-6 combined label still server-side-pending; none of the twelve
  `check-*.js` suites run in CI; 19 open feedback items (queue in the 2026-08-13
  triage in this session's log — G2 numerics, G3 send-copy two-liner, G4
  TradesHome batch are the natural next groups).

---

## 2026-08-13 — Device-auth: all 4 artifacts landed, decisions made, S0 half-shipped

### Where I am right now

**The whole design programme is on `main`** (PRD, HLD decisions, LLD, Plan, [G-040]/[G-041], D-047). The five operator defaults were ratified in chat → **D-047**. S0 (the ship-now bundle, Plan §12) is underway:

- **Lane A — FAAB GraphQL fix: SHIPPED to `main`** (`79123a0`). `_graphql_object_literal` emits bare keys with Name-grammar validation; `__DRAFT_PICKS__` untouched (scalar, valid in both syntaxes). Failing-first proven (2/3 fail pre-fix); full backend suite **2694 passed / 1 skipped**. Backend-only, so the sim gate did not apply. Render auto-deploys it.
- **Lane B — credential vault + Sentry scrub: BUILT + TESTED, HELD on the sim gate.** Committed on `feat/s0-vault-sentry` (`e240aae`) and folded into `feat/s0-bundle`. `credentialVault.ts` (WHEN_UNLOCKED_THIS_DEVICE_ONLY on every write; write-verify-then-delete migration; readEnvelope null-not-wipe per D-047); Sentry `beforeSend`/`beforeBreadcrumb`/`tracePropagationTargets:[]`. `tsc` exit 0; two new `check-*.js` (vault behavioral 5/5, keychain static — sabotage-proven; both registered as npm scripts). **The legacy `sleeper.link.jwt` writer in sendInSleeper.ts is deliberately intact** (migrate only reads it; it must keep persisting until the transport ships at S5).
- **Lane C — OI-9 + OI-12 spikes: NOT DONE.** The agent hit the session limit. These are Gate C prerequisites, not S0 blockers.

### The two things that need the operator

1. **Sim-gate call on the mobile half of S0.** `git push origin feat/s0-bundle:main` trips the pre-push simulator gate (touches `mobile/src/`). The change is **not user-visible** — a dormant unwired module + observability config, reachable by no screen — so the gate arguably does not apply, but the override (`FTF_SKIP_SIM_GATE=1`) is an operator decision and an agent may not self-select it. Either run the tier the runbook matrix assigns, or override.
2. **The two Gate-C spikes still owe their memos** before S3: the expo-updates evaluation (OI-9) and the on-device `typeof TextDecoder` check (OI-12). Prompts are ready; `feat/s0-spikes` worktree exists.

### Watch out for

- **Unpushed work in worktrees — do NOT sweep before landing:** `feat/s0-vault-sentry` / `feat/s0-bundle` (mobile S0, held on the gate) and `feat/s0-spikes` (empty). `design/device-auth-lld` is fully merged and safe to sweep.
- Session + Opus weekly limits were hit mid-session (Opus resets 10am ET, session 6pm ET); lane C and the Plan's lenses ran on Fable.
- Two ESPN pending trades to "Team VP" (league 11896) may still need revoking — carried forward.
## 2026-08-13 — Notification inbox growth surface SHIPPED (PR #113, build 109)

### Where I am right now

**SHIPPED to `main` 2026-08-13** — rebased onto `3b64a44` and merged; Render auto-deploys the
backend + web halves. Built from the pm-growth brief + operator decisions GD-1…GD-8; scope
block and tracking plan in [`../docs/plans/notif-inbox-growth/`](../docs/plans/notif-inbox-growth/).

| Commit | What |
|---|---|
| `3c7a69e` | pm-growth brief carried over + scope block + tracking plan |
| `393b33d` | analytics registration ONLY — no emitter |
| `5881a20` | backend: 4 inbox writes, GD-8 coalescing, server-side dismiss + column |
| `687cb98` | both clients: glyphs, routing, instrumentation, empty state, Clear all |
| `8e9bb5b` | docs + living-memory |

### Blockers, resolved by the operator's ship directive (2026-08-13)

1. **`counter_offer` ships as glyph + routing only, four write sites not five.** The kind has
   no emitter anywhere in the backend — a bucket mapping and two client kind sets, nothing
   more — so there was no push to write a row beside. Whether a counter-offer *feature* should
   exist stays on NEXT as its own item; the kind now renders correctly if it ever ships.
2. **Both adjacent dead-tap fixes stand as built**: mobile routing for
   `trade_accepted`/`trade_declined` (only the push kind `match_accepted` was listed), and
   web's `clickNotif` routing match rows to the Trades view while scrolling an element inside
   the hidden Matches view.

### What has never run

Every row template, the empty state, the invite gate and all three analytics emitters are
**unexecuted** — no simulator, no device, no browser. Sim gate + Maestro waived under D-P1-08;
TestFlight is primary QA. The backend write sites are covered at the DB-helper level, not
through their routes.

### Next moves

- ~~Merge~~ **DONE** — squash PR #113 → `main` @ `2b63511`; Render deploy confirmed live
  (dismiss-all route answers 401, not 404); branch swept per
  [`../docs/recovery/2026-08-13-notif-inbox-growth-sweep.md`](../docs/recovery/2026-08-13-notif-inbox-growth-sweep.md).
- ~~Analytics probe~~ **PASSED** — three names posted to prod with `X-Device-Id` →
  `{"accepted":3,"rejected":[]}`.
- **EAS iOS build 109 (v1.13.2) FINISHED**; TestFlight submission `9668b9b2` was scheduled
  at build time (`--auto-submit`). This eas-cli (21.6.x) has no submission-status command —
  confirm arrival in TestFlight / the expo.dev submissions dashboard.
- Watch `notif_inbox_opened` for 14 days before anyone argues about which rows earn a slot.
  At 3–5 users these are **directional reads, not experiments**.

### Blocking nothing, but owed

- **`.github/workflows/ci.yml` runs no `check-*.js` suite.** `check-notif-glyphs.js` gates
  nothing, on a cross-client enum whose entire failure mode is silence. Seven suites now sit
  in that position. One `npm run` step would fix it.
- **6 `test_rookie_scope.py` failures are live on `origin/main`** and predate this branch
  (verified by stashing). Nobody appears to be tracking them.
- A stash `stash@{0}` (`wip-session-169-living-memory`) holds another session's uncommitted
  living-memory + `.claude/settings.local.json` edits from `session-2026-08-11-169`. I moved
  them aside to branch cleanly and did **not** apply them here. They are still there.

---

## 2026-08-12 — Feedback #297–#302 and #300 both shipped; #300 is lit and unproven on-device

### Where I am right now

**Two batches shipped from this session, both live in TestFlight.**

- **#297/#298/#299/#302 + batch analytics** — `f8acd71`, v1.12.1 build 101.
- **#300 position-scoped trade candidates** — `5139b45`, **v1.13.1 build 106**, both flags **ON** (`league.pos_candidates`, `league.player_trade_handoff`). Operator confirmed it behaves in TestFlight.

All five items `fixed`; #301 `declined`; #205 parked. Analytics for both batches
**verified in production by deploy-then-probe** — every property echoed back out
of `user_events.props`, including the two #300 events and both mirror
combinations `(offer, below)` / `(target, above)`.

### The thing a next session most needs to know

**#300 shipped lit with the simulator gate and Maestro execution waived by the
operator.** The 44pt hit-slop treatment on the drill-in rows, the median divider
and the rule-A removal have **never executed on a device or simulator** — the
authored flow `06-position-trade-candidates.yaml` has never run. TestFlight is
the only runtime evidence that exists. Kill switch: set either flag `false`.

**Rule A and rule B were removed from `togglePos`** — a deliberate reversal of
#293/#294. A position filter no longer auto-adds `PICKS`; pick value is an
explicit opt-in. The original reasoning is preserved in the code comments and in
`config/features.json`'s flag block, not deleted. This was load-bearing for
#300: with rule A live, tapping WR ranked by WR **+ capital** while the median
measured WR alone, so no honest line could be drawn.

### Owed

1. **A simulator pass on #300** whenever one is next run — the flow exists.
2. **`aggregate_tier_labels` is still operator-only**, so per-team pick-tier
   labels are dark for most users. The **median's** label was de-gated
   (`_aggregate_pick_label` is a pure function), so the divider labels correctly
   for everyone — but the rows around it may not.
3. **Decision 6 is half-built:** single-position rows use pick tiers; 2+
   positions still falls back to a raw numeric. Closing it needs a server-side
   combined label.
4. **No `check-*.js` suite runs in CI** — now **six** of them, ~271 assertions
   in this session's work alone, all honour-system.
5. **22 open feedback items** as of close, up to #321.

### What bit us

- **`.easignore` cost two failed EAS builds** — a bare `screens/` matched
  `mobile/src/screens/`. Fixed (`53bd19f`); write-up in [`GOTCHAS.md`](GOTCHAS.md)
  **G-039**, with two adjacent traps: `eas build` exits 0 on a failed remote
  build, and its logs are brotli-encoded.
- **`main` moved 21 commits mid-batch and falsified two premises**, forcing a
  rebase and a complete analytics redo ([D-038](DECISIONS.md)).
- **Five false-passing tests** were caught across this session, in five
  independently authored suites, every one by running assertions against a
  deliberately sabotaged build rather than by review. Treat "my test passes" as
  unproven here until a sabotage fails it.

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

# CHANGELOG

Recent outcomes; current release state is in [HANDOFF](HANDOFF.md).

## 2026-09-06 — Clean workspace and bounded project knowledge

Created an independent current-main organization branch, consolidated product/workflow references, generated status indexes, archived closed plans and retired tooling, and preserved local-only work with integrity manifests. Startup memory is explicitly bounded. [Migration and validation](../docs/recovery/2026-09-06-project-organization.md). This is local repository work; no product rollout.

## 2026-09-06 — Feedback 419–421 released; smaller-package preference ON

PR #283 merged `988fa2d6` after exact-head CI: **5,645 backend passed / 1 skipped**, 95 mobile guards/typecheck/test-ID and 190 web checks; both independent Astra Ultra QA reviews passed. Render is LIVE; only `simple_player_presentment` changed to **1**, preserving all prior flags/settings and three arms. Fixes stale rejected-interest resurfacing and native Win Now initialization/timeout behavior. iOS **1.17.1 (149)** build and exact submission are FINISHED. Only 419–421 marked `fixed`; the 45-report audit made no unrelated closures. Apple availability and the 23-step physical checklist remain unverified/UNRUN. [Release evidence](../docs/feedback/items/419-rejected-interest-resurfacing/release.md), [trade-shape research](../docs/research/2026-09-06-trade-package-shapes.md).

## 2026-09-05 — Owner-contract first wave LIVE; mobile build uploaded (D-185)

PR #281 merged after explicit activation authorization: search continuity, personal-tier intent, tier-bounded feedback and scoped counterparty privacy. Final head `f88afabb` passed CI: **5,455 backend / 1 skip**, all 93 mobile guards/typecheck/test-ID and 190 web checks. Render `4026ebc8` live at **09:51:59 UTC**; smoke passed and all 207 flags, 258 model settings, tiers and experiment summaries were unchanged at that checkpoint. The owner then separately authorized [personal-market activation](../docs/plans/owner-contracts/policy-activation.md), live at **16:01:20 UTC** with exactly one flag changed; three arms preserved. iOS **1.17.0 (148)** uploaded for TestFlight; Apple/tester confirmation and physical QA remain. Raw interviews stayed local. [Release evidence, rollback and unfinished work](../docs/plans/owner-contracts/release.md).

---

## 2026-09-05 — Win Now experimental beta SHIPPED (D-184), PR #280

Season standings, win/playoff/championship projections and constrained Win Now trade discovery are live on web/backend. All three beta flags are enabled under explicit operator acceptance of exploratory evidence; probabilities remain uncalibrated. Parent reviewed Astra work and preserved account-security changes from #279. Final CI: **5,353 passed / 1 skipped**, all four gates green. Render `c28ec6d8` live at 05:07:28 UTC; public flags, exact served JS/CSS and protected endpoint 401s verified. iOS **1.17.0 (147)** built and uploaded to App Store Connect for TestFlight; Apple processing/tester availability and physical-device QA are not verified. Lakeview currently refuses unknown starter availability. [Release evidence and rollback](../docs/business/ops/2026-09-05-win-now.md).

---

## 2026-09-05 — Security findings 1–5 SHIPPED (D-183), PR #279

Verified ownership now gates private data; session initialization resolves identity/membership on the server; analytics excludes bearer tokens and admits only owned outcomes; deletion drains work and covers aliases, credentials and new private tables. Mobile rejects stale proof/session callbacks. Export v2 and privacy disclosures updated. Integrated main #277/#278 before release; CI **5,001 passed / 1 skipped**, all four jobs green; PostgreSQL **57 passed**. Render `a927e3a7` live 04:40 UTC, static content matched and invalid-session probes returned 401. iOS **1.16.16 (145)** build and TestFlight submission finished. Extension **0.1.1** published with unpacked-install instructions. Physical-device QA and historical production cleanup remain owed. [Deployment evidence](../docs/plans/archive/2026/security-data-hardening/deployment.md).

## 2026-09-04 — Win Now implementation reviewed, all flags off

Operator authorized the [Win Now build](../docs/plans/win-now/BUILD.md) using Astra subagents and parent review, isolated on `codex/win-now-20260904` from fetched main `606e512c`. Adds external weekly forecasts, legal-lineup season simulation, constrained search/calculator, durable evidence and separate season decisions in mobile/web. **Not merged, deployed, enabled or submitted to TestFlight.** [ADR-018](../docs/adr/adr-018-win-now-external-forecasts.md) / D-184 preserve dynasty Elo and the legacy title-display prohibition.

Client evidence: TypeScript, 24 feature checks, web 185/185, JS syntax and test-ID lint pass. Parent review is complete; backend evidence covers 4,846 passing cases plus one skip after corrected fixture reruns, and synthetic browser review passed. Hosted Python 3.12 CI, physical TestFlight and held-out calibration remain pending. All three flags stay false; current injuries, conservative game-date cutoff and absent game/team correlations remain explicit limits. [Evidence and checklist](../docs/plans/win-now/EVIDENCE.md).

---

## 2026-09-04 — Personal-market policy BUILT DARK (D-180/D-181) — consensus becomes a guardrail, personal rankings become the ordering signal
Prod (2026-09-04, 21,363 impressions / 598 decisions / 5 deciding users) said the thesis is right and
the implementation is not: the top quartile of stored mutual-surplus was liked 38.6% vs 15.5–25.9%,
yet the **final composite had ~zero correlation with likes**. The 70/30 blend loses the signal it
computes. Two structural faults underneath — confidence shrinkage applied to the user's board but not
a league-mate's (86.9% of boarded-pair cards existed in one orientation only), and a divergence path
composing the user's fairness preference with `min(...)`, so asking for a stricter 0.75 handed you a
looser 0.55. New leaf `backend/trade_policy.py` separates the jobs: consensus is a **non-bypassable
market floor** (point ratio only — range overlap can no longer rescue), two-sided personal
opportunity (the **weaker** manager's gain) is the primary sort, and symmetric ranking confidence
sets how far the floor may descend (0.80 → 0.65). Called by v2, v3 **and one server-side choke point
on the final deck**, so sweeteners / relaxed fallback / swaps / likes-you / wildcards / replenishment
stop being six routes to six different bars. `policy_variant` is orthogonal to `model_arm` — all
three generators keep generating inside both variants, **no fourth arm**, `MODEL_A_PROFILE`
untouched. Adds 16 nullable columns (`member_rankings` confidence ×3, `deck_impressions` ×4,
`trade_decisions` ×2, `trade_matches` ×7) + `trade_proposals` + `trade_policy_shadow`; no backfill,
because the board state behind a historical row no longer exists. 87 new tests; full suite green;
flag-off byte identity proved three ways and the choke point sabotage-proved.
**Both flags default false in code and in `config/features.json` — nothing enabled, nothing
deployed, no production migration run.** Open: [Q-038](OPEN_QUESTIONS.md) — the policy and the
generators judge "both managers gain" on two different value bases (raw vs marginal); that is why
two-sided gain gates Conviction rather than everything. [scope](../docs/plans/personal-market-policy/scope.md) ·
[code-walk](../docs/plans/personal-market-policy/code-walk.md) ·
[funnel](../docs/plans/personal-market-policy/two-user-funnel.md) ·
[TestFlight checklist](../docs/plans/personal-market-policy/testflight-checklist.md) (written, not run).

### Codex roster evaluator and balance review

Built the full-roster evaluator and reviewed the balance implementation on the same requested branch. Added exact shared-slot assignment, both-manager usable depth and capacity checks, outlook utility, uncertain-input handling, frozen telemetry and additive HTML mockup. Fixed pre-gate streaming, enforcement failure handling, small-deck quotas, confidence-value inconsistencies and impression attribution. All new switches remain false. See `docs/plans/post-trade-roster-evaluation/code-walk.md`.

## 2026-09-03d — Web ESPN entry leads with sign-in SHIPPED (D-179) + the entry-session 401 loop guarded (G-069) — PR #276 → `main` @ `0059a8a0`, live
Operator on the live V3 landing: "ESPN option is missing the log in prompt as primary." Correct —
V3 shipped ESPN league-ID-first with credentials behind a "Private league?" link, inverting mobile's
`EspnLinkSheet` entry order (sign-in first-class, "or enter a league ID" after). MFL already matched.
The panel now reads: read-only explainer → primary **"Sign in to ESPN"** → "we'll find your leagues,
no league ID needed" → the cookie block it expands (with a "Find my leagues" primary running the
v2.1 `my_leagues` action) → "or enter a league ID" → the id row. The web's sign-in is the
`espn_s2`/`SWID` paste because a browser cannot read espn.com's cookies and ESPN has no OAuth; no
ESPN password is ever asked for. `espn.league_picker` now picks the LAYOUT too — off, the promise is
withdrawn and V3's id-first order returns, one set of inputs serving both. Testing also caught four
error strings whose "above"/"below" pointed the wrong way (both error lines render after both
blocks); one was wrong in V3 already, inherited from mobile. Now direction-free.
**Also fixes a latent V3 defect the re-verification exposed ([G-069](GOTCHAS.md)):** for an entry
user whose session had died, `apiFetch`'s global `session_expired` recovery and the platform-snapshot
read formed a closed cycle — **hundreds of `/api/{espn,mfl}/leagues` 401s per second, forever**
(entry sessions are unverified, so never server-persisted, and a dead one is the NORMAL end of one).
The read now bypasses `apiFetch`, a 401 returns a sentinel all five call sites propagate, and the
user is returned to the landing to re-claim (deterministic ids, nothing lost). After: exactly 2
requests. Web gate 175/175, entry-route suite 25/25, browser E2E both flag states + the live-ESPN
403 force-open + the dead-token repro
([code-walk §V3.1](../docs/plans/archive/2026/landing-platform-options/code-walk.md)). **Shipped + verified live**
2026-09-03: PR [#276](https://github.com/mattmurf77/fantasy-trade-finder/pull/276) squash → `main` @ `0059a8a0`, CI ×4 green, Render serving it — prod shows
the sign-in-primary order, the expand focuses `espn_s2`, no stale directional copy, and the
dead-token repro against PROD makes **exactly 2** requests then returns to the landing with
everything cleared. Ledgered in `docs/recovery/2026-09-03c-espn-signin-primary-ship.md`.
## 2026-09-03c — API audit SHIPPED (D-178): PR #273 squash → `main` @ `c2775fe0`, Render live 16:33 UTC — session init 26 → 7 Sleeper calls, trade job 17 → 4 reads, cron sweeps scoped, web/mobile re-fetches removed

Branch `claude/api-audit-redundancies-9a6075` → squash `c2775fe0`. **Note:** the squash commit title says D-177; the correct id is **D-178** — PR #272 claimed D-177 for the web platform entry while this branch was open, and the ledger was renumbered in the merge. `DECISIONS.md` is authoritative. Source: [`docs/reviews/2026/2026-09-03-api-audit.md`](../docs/reviews/2026/2026-09-03-api-audit.md) (four-layer audit + 195-route caller table). Operator chose findings 1, 2, 4, 5, 6, 7, 8, 9, 10; **3 held** (ping-then-init would stop the per-foreground league resync — see NEXT), **7 shipped as poll-pause** (real web push = schema + dependency, needs a scope block).
- **Backend:** session-init daemon fetches rosters + league meta once and threads them to owned-picks / telemetry; trades sync is incremental (`sweep_weeks`: backfill once, then `[week-1, week]`, offseason `[1]`); trade job takes request-time prefs (`prefs_preload`), bulk opponent prefs, one memoized `load_draft_picks`; both cron loaders filter `leagues.updated_at` ≤ 30 d; `not_drafted` probe 24 h outside Apr 1 – Sep 15.
- **Web:** `/api/sleeper/players` → `/warm` (4.8 MB never read); `apiFetch` parses bodies on 401 only; swipe 5 → 3 requests; notification poll pauses on hidden tabs; `switchToLeague` saves + reloads (boot did it all again).
- **Mobile:** `initLeagueSession` / `buildSessionInitBody` hand back rosters + users; `state/queryClient.seedLeagueSessionCaches` seeds `['league-rosters'|'league-users', id]` on every init path (5-min staleTime already held by all five consumers).
- **Tests:** +4 pytest files / +23 cases; `check-session-seed.js`. pytest **4617 / 1 skipped**, tsc 0, testid-lint OK, web structure 175/175.
## 2026-09-03b — Web landing mirrors mobile platform entry SHIPPED: Sleeper · ESPN · MFL chips (D-177, PR #272 → `main` @ `ca5fac46`)
Operator ask: "update the landing page on web to mimic the mobile app with ESPN and MFL options."
`web/index.html` gains SignInScreen's chip row (flag `landing.platform_options` + `espn.link` /
`mfl.link`) and ESPN/MFL entry panels on the same sessionless `POST /api/entry/platform` (D-164):
preview → claim (mint) → canonical `/api/{espn,mfl}/link` import; private ESPN = cookie paste
(auto-opened on 403); "Find my leagues" / "Sign in with MFL" = the v2.1 actions. Entry users
(`entry:` ids) read leagues/rosters from `GET /api/{espn,mfl}/leagues` in every path that used
Sleeper proxies (league screen w/ single-league auto-skip, `selectLeague`, reload, switcher,
leaguemate pool) via `buildPlatformRosterData`. Web now emits `signin_*` (method sleeper/espn/mfl).
Drive-by: `selectLeague`'s undefined `userPlayerIds` toast (ReferenceError after every league pick)
fixed. No route/schema/flag changes. Evidence: web gate 175/175, `test_entry_platform_route` +2 (25),
browser E2E on the fixture-stubbed app for both platforms
([code-walk §V3](../docs/plans/archive/2026/landing-platform-options/code-walk.md)). **Shipped** 2026-09-03: PR
[#272](https://github.com/mattmurf77/fantasy-trade-finder/pull/272) squash → `main` @ `ca5fac46`, CI ×4 green, branch content-verified and ledgered
(`docs/recovery/2026-09-03b-web-platform-entry-ship.md`). Web-only — Render redeploys, no EAS build.
Owed: the operator's 4-step prod check (scope §V3).

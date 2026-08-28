# Test Ledger — Fantasy Trade Finder

> **Purpose:** authoritative record of what's been tested, what shipped, what was measured, and on what version of the stack. Prevents "works on my machine / claimed earlier without evidence" failure modes.
>
> Retention: entries dated within the last 2 months (2026-06-08 onward) plus standing sections live here; older run entries are archived in [`archive/TEST_LEDGER-pre-2026-06.md`](archive/TEST_LEDGER-pre-2026-06.md).
>
> **Read at:** before claiming a result, before proposing a new test that may duplicate a prior one, before shipping a feature.
> **Write at:** immediately after running a test, regardless of outcome.
>
> Companion files: [`MISTAKES.md`](MISTAKES.md), [`DECISIONS.md`](DECISIONS.md), [`Test_League_Trade_Matches.xlsx`](../Test_League_Trade_Matches.xlsx) (sample data), [`trade_output.json`](../trade_output.json).

---

## 2026-08-28d — IAP enablement code half (runbook 6–7): webhook delta + RevenueCat paywall — full gates, ALL DARK

Operator-directed cross-session handoff; two Opus build subagents (backend/mobile, disjoint file ownership), lead-session review of every load-bearing hunk. Branch `claude/monetization-features-feedback-a6fe77` off `origin/main` `69dc0cae`. Scope block: [docs/plans/monetization/iap-enablement/scope.md](../docs/plans/monetization/iap-enablement/scope.md). **Zero user-visible change until the operator flips `monetize.*` flags** — no route gained `@_require_pro`, no flag changed, no schema changed.

- **Backend** (`entitlements.py`, `server.py`): `resolve_rc_identity()` alias reconciliation (`$RCAnonymousID:*` → `acct_*`, prior anon-keyed billing rows re-keyed before upsert), `TRANSFER` projected as a move (not expire/revoke), `BILLING_ISSUE` grace extension (extend-only, never perpetual rows), `_product_mapping` tolerant of the runbook's divergent SKU spellings (Q-034), new `GET /api/paywall/config` (session-authed, `monetize.paywall` off → `{"enabled": false}` only). Five `paywall_*` client events registered in taxonomy + `NON_INTENT_EVENTS` same-commit.
- **Mobile**: `react-native-purchases@10.8.1` (single-seam `api/purchases.ts`, inert without `EXPO_PUBLIC_REVENUECAT_IOS_KEY`; never calls `logOut`), `initPurchases`/`logIn` identity bridge in `useSession` (bootstrap + sign-in halves), `useEntitlements` store (server-authoritative, CustomerInfo raise-only UI cache, 72h offline grace), `PaywallScreen` root-stack modal (3.1.2-complete: price+period, 14-day trial terms, auto-renew + cancel copy, working Restore, tappable /privacy + /terms; server `enabled:false` beats stale client flags; no FeedbackFAB per #188), flag-gated `settings-pro-row` on both settings surfaces.
- **Evidence (D-056):** `pytest backend/tests` **4397 passed, 1 skipped, 0 failed** (lead-run on the combined tree; targeted new coverage: 47 entitlements + 12 paywall-config tests, 7 named backend sabotages RED-then-green) · `npx tsc --noEmit` clean · `testid-lint OK` · new `mobile/tests/check-paywall.js` **11/11** (3 mutations verified failing) · full structural suite **84 guards, 0 failing** · code-walk proof + operator sandbox checklist in [docs/plans/monetization/iap-enablement/](../docs/plans/monetization/iap-enablement/).
- **Runtime evidence OWED (operator, blocked on Apple):** [sandbox-test-checklist.md](../docs/plans/monetization/iap-enablement/sandbox-test-checklist.md) — cannot run until the Paid Apps agreement (signed 2026-08-27) is active and RevenueCat/ASC are configured (runbook steps 3–5). The mobile purchase path has **no** runtime proof until then, by design.
- **Open for the operator:** Q-034 (ASC SKU naming — recommend `ftf_*`; **closed 2026-08-28, `ftf_*` confirmed**), `REVENUECAT_WEBHOOK_SECRET` absent from `secrets.local.env` + Render, `EXPO_PUBLIC_REVENUECAT_IOS_KEY` needed in EAS env before the next build, and note the next mobile release **must be a full EAS build, not OTA** (native module).
- **Addendum (2026-08-28e, operator ruling):** monthly gains a **3-day trial** — `trial_days` 0→3 in `_PAYWALL_PRODUCTS` + test + LLD §3 + checklist P2; `pytest test_paywall_config.py + test_entitlements.py` re-run green (59 passed) on the delta; mobile untouched (trial copy is generic over `trial_days`).

## 2026-08-28c — v1.16.9 (EAS build 135) BUILT + SUBMITTED to TestFlight; trade.shop_asset LIT in prod

Release run at operator order ("push, open PR, merge, push to testflight and flip the flags on").

- **Merge:** PR [#225](https://github.com/mattmurf77/fantasy-trade-finder/pull/225) squash-merged to `main` @ `a9d96435` on green CI (backend-tests 8m52s · mobile-typecheck · testid-lint). Branch `claude/new-feedback-71436e` @ `823bfb2d` content-verified (empty diff vs main), recovery-ledgered (`docs/recovery/2026-08-28-shop-branch-ship.md`), then swept — worktree removed clean, local + remote branch deleted.
- **Flag:** `trade.shop_asset` flipped `true` in the same PR (features.json + all three mirror fixtures; mirror suite 76 passed). **Verified LIVE on prod post-deploy** via `GET /api/feature-flags`: shop_asset / asset_ideas / calc.merged_layout / finder_targeting all `true`. Inert for pre-1.16.9 clients (no code reads the flag).
- **Build:** EAS `21504c65-a3ff-4003-8dee-9e902cdf792d` — v1.16.9, build **135**, status **finished**, from git commit `a9d96435` (the merged main squash — verified via `eas build:list`, not assumed). `--auto-submit` chained: *"Submitted your app to Apple App Store Connect!"* — Apple-side processing then TestFlight availability is the only remaining step and is not ours. Version bumped in BOTH `mobile/app.json` and `Info.plist` (G-012), `plutil` clean; build number from EAS remote autoIncrement (134 → 135).
- **Owed — operator, runtime, on build 135 (this build carries BOTH):** the 14-step #402/#403 shop checklist ([docs/feedback/items/402-more-offers-shop/testflight-checklist.md](../docs/feedback/items/402-more-offers-shop/testflight-checklist.md)) — now post-flip verification per the operator's confirmed sequencing — **and** the still-unrun 8-step #384 partner-summary checklist owed "on the next EAS build" since 2026-08-27, which this is.

## 2026-08-28b — #402/#403 QA round 2: B-3, own-position chip ruling, P-1..P-4 — universal-rule fixes, gates green

Operator rulings ("Fix B3, 2. Offer it. Resolve the runtime concerns by ensuring consistent/universal approach") recorded in `docs/feedback/items/402-more-offers-shop/rulings-2026-08-28.md`; fixed in `23b0cdf6` on `claude/new-feedback-71436e` (still HELD unmerged).

- **B-3 + P-2, one mechanism:** committed dismissals are client-authoritative for the strip session — a `suppressed` set added to only on commit, cleared by nothing but the strip instance dying (Undo-safety ordering verified; commit-failure un-suppresses). Pager, 1/X, chip counts and the Clear-positions label all filter through it, closing the baselineLateralCount nit with it.
- **Own-position chip (LLD §3.4 over the mockup, ruled):** offered unselected alongside the others; own-only selection sends `swap_positions:[own]` with no special case; PICK still never offered; suite j2c INVERTED (the pre-round-2 suite run against the new code reds only on j2c — proved by executing the HEAD copy: 78/1). Mockup Same-value frame updated to shipped semantics (WR chip added, its contradictory PICK chip removed).
- **P-1:** react-don't-race pager — one `pendingScrollRef` consumed by an effect keyed on the rendered data; all four movers request-then-mutate. **P-3:** `shop_opened` emits exactly once, in `openShopStrip` (chooser pick = one event with the real position; Cancel = zero). **P-4:** `shopEnabled` = `trade.shop_asset && trade.asset_ideas && calc.merged_layout`; flag comment names the chain plus the structural `trade.finder_targeting` prerequisite; any flag dying mid-session closes an open strip.
- **Suite:** 100 assertions (21 added: exactly-one-emitter h4, flag-chain n1, suppression n2, pager n3, and reviewer A's two missing pins — Chalkline scan n4, label-source n5). Sabotage 4/4 red-then-green with byte-identical restores (`cmp`-proved; file snapshots, not `git checkout --`).
- **Gates (orchestrator re-run):** `tsc --noEmit` clean · shop suite 100/100 · all `check-*.js` zero RED · `testid-lint OK` · `features.json` valid · `pytest test_seed_ui_test_db.py + test_analytics_taxonomy_384.py` 87 passed (backend diff = one taxonomy comment).
- **Checklist updated:** step 9 covers the chip + B-3 verification; Known-open now empty. Nothing remains open from either QA reviewer.

## 2026-08-28 — #402/#403 "More offers = shop a player" — full build + redundant QA + fix round, all gates green (branch, HELD unmerged)

Built by three parallel/sequential subagents on `claude/new-feedback-71436e` (docs+mockups branch, first re-based on `origin/main` `69dc0cae` via merge `bf125dac`): `5115265b` W1 mobile (entry fork, ShopOffersStrip, chooser, flag `trade.shop_asset` dark, 4 analytics events, `check-shop-deck.js`), `4b71f036` W2 backend (`swap_positions` on `/api/trades/asset-ideas` + spike S-2), `bc21ee0f` W2 UI (position multi-select), `472f6649` QA fixes. **Operator hold: nothing merged, nothing pushed.**

- **Gates, run by the orchestrator on the combined tree (not delegated claims):** full `pytest backend/tests` → **4,377 passed / 1 skipped / 0 failed** (5:12); `npx tsc --noEmit` exit 0; **all 84 `mobile/tests/check-*.js` suites green** including the new shop suite (90 assertions after the fix round) and a byte-untouched `check-single-pin-actions.js` (R-18); `testid-lint OK`; `features.json` valid. Re-run after every commit.
- **Spike S-2 (`docs/feedback/items/402-more-offers-shop/spike-s2-yield.md`):** single-position swap selections empty 30–60% of the time (TE worst), multi-select finds a lateral 89–97% — the picker ships multi-select-first with live counts and first-class empty copy. Generator output matched the analytic ±band window in all 32 grid cells.
- **Sabotage evidence (suite falsifiability proven by every agent):** W1 9 edits / 9 red (give-side guard, Gesture.Pan import, counter decoupled, mode-map corruption, pan gate deleted, label drift, ✕→like, undo-lie, taxonomy drop); W2 backend 2 (lateral leak into upgrade → 3 red; silent invalid-position accept → 3 red); W2 UI 4 (PICK chip, analytics position-set, `[]` sent, flush dropped); fix round 4 (k1/l1/m2/l2c). All restored green.
- **Redundant static QA (2 reviewers, independent):** A (spec) — every requirement PASS, flag-OFF byte-identical proven (early-return fork, exact legacy literal, zero diff on `/api/trades/queue`); B (regression) — 4 confirmed seam bugs B-1..B-4 + 4 plausible P-1..P-4. **Operator selected B-1/B-2/B-4 → fixed in `472f6649`** (deck holds still through buttons + VoiceOver + reason tiles + flag button + a topRawId close-on-card-change effect; shop state cleared by `resetDeckForNewTargets`/`handleClearPin`/kill-switch mount gate/`key={asset.id}`; Undo toast retracted by reference on every early commit). **Open by explicit selection:** B-3 (≤60 s warm-cache resurrection of a committed dismiss), A-1 (own-position chip — mockup vs LLD §3.4 contradiction, needs a ruling), P-1..P-4, plus two unpinned mechanical guards (Chalkline scan, label-source assertion) and two doc rows (api-reference "pending" note now stale; components.md row).
- **Owed (operator, runtime):** the 14-step checklist in [docs/feedback/items/402-more-offers-shop/testflight-checklist.md](../docs/feedback/items/402-more-offers-shop/testflight-checklist.md) on the first build carrying the branch — steps 3/8/11/12 are the QA-fix regressions, Part B is the flag-off byte-identity check. Elo note for the operator: the shop ✓ moves the board by explicit ruling A.

## 2026-08-27 — #384 partner team-shape summary restored to the merged calculator layout — full gates

Live shipped regression found by the [2026-08-27 calc-vs-guided-finder parity audit](../docs/reviews/2026-08-27-calc-vs-guided-finder-audit.md) (row 24, one of its five `partial` rows). Branch `claude/calc-merged-partner-summary` off `origin/main` `30070f36`. Scope block + code-walk + TestFlight checklist: [docs/feedback/items/384-calc-finder-merge/partner-summary-regression.md](../docs/feedback/items/384-calc-finder-merge/partner-summary-regression.md).

- **The defect, and that it was a regression:** the per-partner QB/RB/WR/TE + picks shape line has been on the In-league calculator's partner chips since `fbd55611` (2026-07-27), relabelled to pick-equivalents by #306 in `780c035c`. #384 W1 (`dfcd5321`) replaced the chip row with the #333 Team dropdown + sheet and did not carry the line across — its own commit message describes the new sheet as listing leaguemates "with their R/R*/NR rank state". `calc.merged_layout` is `true` in `config/features.json`, so every user since v1.16.0 has seen handle + badge only. **Checked before fixing:** neither the ten #384 operator rulings nor the four round-2 rulings touch the partner list (6/7 remove the utility row and the subnav), and `plan.md` §15 lists `calc.partner-summary.<id>` among the controls the page already had. Omission, not ruling.
- **Structural guard — extended, and proven falsifiable.** `mobile/tests/check-calc-merged-layout.js` gains section 22 (a–h): one shared implementation, the merged sheet mounts it, fed from the same memo, the sheet row *speaks* the shape, the row can shrink so the R-badge is never pushed off, and the flag-off stacked page keeps it. Four sabotages applied to the working tree and reverted — **against `origin/main`'s component verbatim (the shipped bug): 6 FAILED**; drop the mount from the sheet only: 22d; strip the spoken shape (sighted-only restore): 22f; hand-copy a block instead of the shared helper: 22a + 22d. The guard fails on the build that shipped the defect.
- **Suites (run in this worktree after `npm ci` — no symlinked node_modules):** `npx tsc --noEmit` exit 0 · **all 84 `mobile/tests/check-*.js` guards, 0 failures** (83 pre-existing + this one's new assertions) · `bash mobile/scripts/testid-lint.sh` → `testid-lint OK`. **`pytest backend/tests` not run — backend untouched**, the diff is `InLeagueCalculator.tsx` + `check-calc-merged-layout.js` plus docs.
- **No new data cost:** `powerQ` (`getPowerRankings(leagueId, 'consensus')`) is unconditional and already feeds `needsByTeam` in the merged layout, so the summaries were being computed and discarded. No route, flag, schema, analytics event or testID added.
- **Owed (operator):** the 8-step TestFlight checklist in the scope doc §B — the shape line's presence, per-team variation, the no-picks and picks tails, Dynamic Type / landscape two-line clamp with the badge still on screen, tap-to-select, and the **VoiceOver** row announcement (the sighted-only failure mode). Runtime is the only evidence left for layout truth under D-056.

## 2026-08-26e — v1.16.8 (EAS build 134) BUILT for TestFlight

Release run by the lead session at operator instruction ("push to testflight via EAS"), following the `ops-release` pre-flight.

- **Build:** `c12643d1-a22b-4dee-9e08-611c01f70366` — v1.16.8, build **134**, status **FINISHED**, from git commit **`dd2051bc`**. `--auto-submit` chained the submission: **`c6e58906-3cbc-4418-af97-d7a39a6cc6c3`** — *"Submitted your app to Apple App Store Connect"*, uploaded via the EAS-held ASC API key (`LA9UVSTV2N`). Apple-side processing (~5–10 min) then TestFlight availability is the only remaining step and it is not ours.
- **Version bump:** 1.16.7 → 1.16.8 in `mobile/app.json` AND `ios/DTFDynastyTradeFinder/Info.plist` — [G-012] says the plist literal is what actually ships in this bare workflow, so bumping only app.json would have shipped a build labelled 1.16.7. `plutil -lint` clean. Build number from EAS remote (`appVersionSource: remote`, autoIncrement), so 134 follows the concurrent session's 133.
- **Built-tree verification (not assumed):** `git show dd2051bc:` confirmed the entry v2.1 login actions in `backend/server.py`, `signin.platform-link-btn` in `analystScript.ts`, and `1.16.8` in the plist.
- **Pre-flight gates:** main CI green at every commit in the range; release PR #217 and onboarding PR #218 each had all three checks COMPLETED/SUCCESS **before** merge (the G-062 discipline); backend suite 4,359 passed; 83 mobile structural guards, 0 failing; tsc + testid-lint clean.
- **What 134 carries beyond 133:** entry v2.1 (#215 — "sign in to ESPN/MFL" as a first-class option) and the platform-aware Analyst beat (#218). 133 already carried the entry chips (#210) and the Apple decoupling (#213).
- **Owed (operator, on 134):** the TestFlight checklists in [landing-platform-options/scope.md](../docs/plans/landing-platform-options/scope.md) §3, §V2, §V2.1 — plus a spot-check that the tour's opening beat now points at the ESPN/MFL panel button (not the hidden username field) when a non-Sleeper chip is selected.
- **Rollback without a build:** `landing.platform_options: false` + `POST /api/feature-flags/reload` kills the whole entry surface; `espn.league_picker` / `mfl.auth_link` kill just the login actions.

## 2026-08-26c — Entry v2.1: login option (Opus subagent build, lead-session review) — full gates

Scope: [docs/plans/landing-platform-options/scope.md](../docs/plans/landing-platform-options/scope.md) §V2.1 · code-walk §V2.1

- **Backend pytest:** `test_entry_platform_route.py` **13 → 23 PASS** — the two account-discovery actions (ESPN `my_leagues`, MFL `auth_leagues`): shapes, flag gates (`espn.league_picker`/`mfl.auth_link` on top of the feature flag), cookie-XOR and missing-credential 400s, bad-login 403 `mfl_bad_credentials`, `bad_action` 400, and a shared `_assert_stored_nothing` helper proving no users/credentials/leagues/sessions are created. Full suite **4,359 passed / 1 skipped** (5:38) on a tree that also carries the concurrent v1.16.7 session's tests.
- **Structural guard:** `check-landing-platform-options.js` **36 → 61 PASS** — V2.1 pins incl.: discovery calls sessionless + analytics-free, ESPN capture→sessionless my-leagues→existing picker, soft-fail keeps the manual field, `mflAuthEnabled` no longer excludes entry, entry sign-in single-select mints directly and never touches the bulk `mflAuthImport`, the in-flight password is a ref (never state) dropped before the best-effort re-store. One V2 assertion ("entry suppresses the MFL password path") deliberately superseded.
- **Typecheck** clean · **testid-lint** OK.
- **Subagent sabotage runs** (reverted): dropping the `espn.league_picker` gate and restoring `&& !entry` each turned exactly the expected test/guard assertions red.
- **Review:** lead session verified the backend serializations/signatures against the real my-leagues and auth-link routes directly, confirmed linked-mode render identity, and tightened the SignInScreen panel copy.
- **Owed (operator):** TestFlight checklist §V2.1 (3 steps) on the FIRST build after v1.16.7 — 1.16.7 carries entry v1+v2 only.

## 2026-08-26 — #360/#361 + #362 REBUILT on current main; #362 SHIPPED LIT, #360 held dark

**Branch:** `feat/jon-360-362` — the 2026-08-19 build (base `2a492b6`) merged with
`origin/main` `867c3baa` (123 commits: knockout refine D-159, full sweep, #384, package
pricing honesty #162, pick YoY floor, receipts/breaker/negmem).
This entry REPLACES the stale 2026-08-19i entry — those were the pre-rebase numbers.
Flags at ship: **`trade.standing_offers` `true`** (graduated, [D-165](DECISIONS.md)) ·
**`trade.avoid_positions` `false`** (held — [Q-031](OPEN_QUESTIONS.md) gen_v2 gap is live in
prod, [Q-032](OPEN_QUESTIONS.md) upheld). Records:
[360-avoiding-positions/](../docs/feedback/items/360-avoiding-positions/) ·
[362-standing-offer/](../docs/feedback/items/362-standing-offer/) · [D-166](DECISIONS.md).

**Gates were run THREE times and all three runs are reported here**, because the flag flip
was made between them and the middle run failed:

1. **Pre-flip (both flags dark), run by this session independently of the build agent:**
   `4336 passed, 1 skipped` in 364.57s, exit 0 — matching the build agent's reported number
   exactly. That cross-check is why the agent's other claims were taken as measured.
2. **Post-flip, first run:** `1 failed, 4335 passed, 1 skipped` (443.25s). The single failure
   was `test_standing_offers.py::test_flag_and_knobs_registered`, which asserted
   `features["trade.standing_offers"] is False, "ships dark"`. **No behavior broke — the only
   thing that failed was a pin on the dark posture itself.**
3. **Final, after updating the two dark-posture pins:** the numbers in the table below.

**Two independent guards pinned this flag dark and BOTH were changed to ship it lit** —
`mobile/tests/check-standing-offer-362.js` SC-14a ("graduation is an operator action after a
TestFlight pass on a real league") and the backend assertion above. Each now asserts `true`
and carries an in-file comment recording that graduation happened **without** the TestFlight
pass, per [D-165](DECISIONS.md). A repo-wide search found no third pin. `SC-14b` — the
`LAUNCHED_FLAG_DEFAULTS` absence check, which is the assertion that actually protects the
kill switch ([D-166](DECISIONS.md)) — was **not** touched and holds in both flag states.

| Gate | Result (final run, measured 2026-08-26 on the merged tree, flag lit) |
|---|---|
| `python3 -m pytest backend/tests -q` | **4336 passed, 1 skipped, 0 failed** (320.07s) |
| `npx tsc --noEmit` (mobile) | **exit 0, zero errors** |
| `bash mobile/scripts/testid-lint.sh` | **testid-lint OK**, exit 0 |
| all `mobile/tests/check-*.js` | **82 passed, 0 failed** (80 pre-existing + `check-avoid-positions.js` + `check-standing-offer-362.js`) |
| Sim gate | `FTF_SKIP_SIM_GATE=1` — D-056 standing posture; substitute evidence: post-merge code-walks with merged-tree line cites (`360-avoiding-positions/code-walk.md` addendum, `362-standing-offer/code-walk.md`) |
| **Runtime evidence** | **NONE. Both TestFlight checklists remain UNRUN.** |

**Three merged-tree failures found and fixed (first full run: 4333 passed / 3 failed):**
1. `test_breaker_seam::test_bulk_readers_match_the_singular_loaders` — main's breaker
   added `load_league_preferences_bulk` promising per-row shape identity with the
   singular loader; it predated `avoid_positions`. The bulk row now carries the key.
2. `test_avoid_positions::test_no_avoided_position_received[v2]` and
   `::test_avoid_qb_keeps_pick_rungs` — NOT the avoid filter: main's `d42872f2`
   ("package pricing honesty + gap auto-sweetener", #162, bisected on pristine main)
   stopped admitting 1-for-1s that lose seed value for the giver, starving the tests'
   BASELINE premise. Fixture now seeds coveted receive assets at parity (1540);
   assertions unchanged.
Also: the merge union dropped `seasonSpan`'s closing brace in `TradeCard.tsx`
(caught by `tsc`, restored).

**ID de-collisions this session** (parallel sessions took the branch's IDs on main):
D-098→**D-166**, Q-026/027/028→**Q-031/032/033**, G-053→**G-062** (+ its missing
GOTCHAS index row added), M-005→**M-006**; PRD-local decisions renumbered item-scoped
D-093…D-096→**D-360-1…D-360-4**, #362's D-093→**D-362-1** (the D-306-1 convention —
main took D-093–D-097). Every cross-reference updated; `feature_flags.py` /
`features.json` stale "ships ON" comments corrected to the Q-032 dark ruling.

**Not claimed:** that either feature behaves correctly on a device — no runtime
evidence exists until the two TestFlight checklists run with the flags lit.

## 2026-08-26b — Platform entry decoupled from Apple (D-164) — full gates

Scope: [docs/plans/landing-platform-options/scope.md](../docs/plans/landing-platform-options/scope.md) §V2 · code-walk §V2 · decision: [D-164](DECISIONS.md)

- **Backend pytest:** new `backend/tests/test_entry_platform_route.py` — **13/13 PASS** (flag gating feature+platform, bad platform, MFL preview persists/mints nothing, deterministic `entry:mfl:` mint + users row + idempotent re-claim, bad franchise 400, ESPN preview shape, cookie XOR, SWID-keyed id, #321 wrong-account 403, bad team 400, private→`espn_auth_required`, and the end-to-end proof: minted token drives the real `/api/mfl/link` import and binds the claimed franchise to the entry user in `league_members`). Full suite **4,289 passed / 1 skipped** (5:42).
- **Structural guard:** `check-landing-platform-options.js` extended to **36/36 PASS** — V2 pins: no Apple in the panel, mint-before-canonical-import in both sheets, session-dependent paths suppressed in entry mode, `account_only` entry user, token stored + signin funnel in the api layer, route sessionless + dual-gated + deterministic `entry:` ids via `_extension_build_session`.
- **Typecheck:** `npx tsc --noEmit` clean · **testid-lint:** OK.
- **Owed (operator, next TestFlight build):** checklist v2 in scope §V2 — public ESPN claim with no Apple prompt anywhere, private ESPN via the ESPN WebView, MFL claim, relaunch persistence, Sleeper flow unchanged, sign-out→re-claim recovers the board. Supersedes v1 §3 steps 2–4.

## 2026-08-26 — Landing platform options (Sleeper · ESPN · MFL entry chips) — full gates

Scope: [docs/plans/landing-platform-options/scope.md](../docs/plans/landing-platform-options/scope.md) · code-walk: [code-walk.md](../docs/plans/landing-platform-options/code-walk.md) · decision: [D-163](DECISIONS.md)

- **Structural guard:** `mobile/tests/check-landing-platform-options.js` (`npm run test:landing-platform-options`) — **20/20 PASS**. Pins the dual flag gate, per-platform chip gates + de-flag fallback, intent forwarding on both Apple branches, the s0.2 guide advance, RootNav's intent→param mapping, the MFL auto-open's #266 deferral, the auto-skip block, and the two-sided flag registration.
- **Typecheck:** `npx tsc --noEmit` (strict) — clean.
- **testid-lint:** `bash mobile/scripts/testid-lint.sh` — OK (new `signin.platform-*` ids are flow-unreferenced).
- **Backend:** `pytest backend/tests` — **4275 passed, 1 skipped** on first run with one failure (`test_release_flags_mirror_features_json` — the new flag key missing from the mirror fixtures); fixed by adding `landing.platform_options: true` to `release.json` / `profiles-on.json` / `onboarding-v2.json`, after which `test_seed_ui_test_db.py` is **76/76 PASS**. No backend behavior changed (FLAG_KEYS + fixtures only).
- **Owed (operator, next TestFlight build):** the 6-step runtime checklist in scope.md §3 — chips render, ESPN chip → Apple → ESPN sheet auto-opens un-wedged (#266 class), MFL twin, Sleeper flow unchanged, single-league auto-skip yields to the MFL intent.

## 2026-08-25 — v1.16.6 (EAS build 132) BUILT + SUBMITTED to TestFlight

Carries PR #196's `via:'quickset'` tag ([D-162](DECISIONS.md)) — the first build in which the Quick Set funnel can emit anything.

| Gate | Result |
|---|---|
| Version sources (G-012) | All three iOS spots set to 1.16.6 — `app.json`, `Info.plist` `CFBundleShortVersionString` (the literal that actually ships here), both `MARKETING_VERSION` lines. Verified on the build source commit before upload |
| CI on the release sha (`cb691b25` → merged `c092f808`) | backend-tests · mobile-typecheck · testid-lint all **pass** |
| EAS build `8925880d` | **finished** — v1.16.6 (132), commit `c092f808`, profile production |
| Submission `b190d30b` | **finished** — ASC app 6771488431, auto-submit. Apple-side processing then TestFlight availability is out of our hands |
| Archive hygiene (G-022) | Built from the 561 MB worktree, NOT the 9.5 GB main checkout (5.9 GB of nested worktrees there — the condition that once failed an upload) |

**Owed runtime evidence, now runnable on 132:** the via-gap checklist ([scope §3](../docs/plans/quickset-analytics-via/scope.md)) — expect `quickset_completed` rows + `tier_save.props.via = "quickset"` for a real walk, and `via:"tiers"` with no `quickset_completed` for a plain Tiers save. Checklists **H** + **I1** (Wave A / flag-off regression) were owed on 130 and are also testable here.

## 2026-08-25 — Merge-day addendum to 2026-08-24b: main merged in, D-162 renumber, Aug-25 calendar flake pinned (G-061)

Merging `origin/main` (Group F + feedback wave + Waves A/B0 + pick YoY floor) into the via-gap branch surfaced two things. (1) Main took D-160/D-161 overnight → this branch's decision renumbered **D-162**; `via:'quickset'` verified intact alongside Group F's HOLD changes (`check-quickset-via` + `check-quickset-hold` + `tsc` green on the merged tree). (2) The merged-tree suite failed `test_notif_teardown`'s three winback tests — **because the run date was Aug 25**: the daily tick's `is_aug25` season_start fan-out skips every winback that day, so the real clock was a hidden test input ([G-061](GOTCHAS.md), the G-059 pattern). Fixed by pinning the tick clock in those tests + a new pinned `test_season_start_fanout_on_aug25`; file 19/19 green. Remaining local failure: `test_deck_signal_v2` only — **CORRECTED 2026-08-25: caused by the stale `data/trade_finder.db` in this worktree, not Python skew** (pristine data dir → passes). It reproduced on a clean git tree because `git stash` does not touch the gitignored DB, which is exactly why the clean-tree check looked like it exonerated the code.

## 2026-08-24b — Quick Set `via` gap fix — full gates, on `claude/elegant-feynman-c3689e` (D-162; held for operator)

Scope: [`docs/plans/quickset-analytics-via/scope.md`](../docs/plans/quickset-analytics-via/scope.md) · addendum [`2026-08-24-quickset-via-gap.md`](../docs/business/analytics/2026-08-24-quickset-via-gap.md). One emitter change (unscoped mobile Quick Set saves tag `via:'quickset'`); no server code change, no taxonomy registry change.

| Gate | Result |
|---|---|
| `pytest backend/tests -k "not calibration_gate"` | **4226 passed, 1 failed, 1 skipped** — the failure (`test_deck_signal_v2.py::test_flag_on_writes_impressions_in_served_order`) reproduces on the **clean origin/main tree** (`git stash` → still fails) under local Python **3.14.4**; the known 3.12-skew class (this file, 2026-08-13). Unrelated to the change; CI on the PR sha is the arbiter — and PR #196 CI came back **all green** (run 32762214700). **CORRECTED 2026-08-25:** the cause is NOT Python-version skew — it is the stale `data/trade_finder.db` in this worktree (the 2026-08-24 HANDOFF's banked sharp edge). Proven: `mv data data.bak` → the test passes on the same interpreter. The skew attribution was a guess that fit; it was wrong |
| Server branch coverage (pre-existing, all green in the run) | `test_analytics_p0.py::test_quickset_completed_fires_with_props` + `::test_quickset_event_absent_for_plain_tier_save`, `test_rookie_scope.py::test_rookie_via_tags_are_recorded_and_do_not_fire_quickset_completed`, `test_events_api.py` disjointness pins |
| New structural guard | `mobile/tests/check-quickset-via.js` (`npm run test:quickset-via`) — 13 asserts green. **Sabotage:** non-rookie save arm reverted to `undefined` (the original bug) → guard RED on exactly the pinned assert; restore → green |
| `tsc --noEmit` (strict) | green |
| `testid-lint.sh` | OK (no testIDs touched) |
| Runtime | operator TestFlight checklist in scope §3 — UNRUN, owed after the next mobile release containing this change |

## 2026-08-24 — Pick YoY floor (D-161) — full gates, live-curve verified, on `claude/pick-yoy-floor-0824`

Plan: [`docs/plans/pick-yoy-floor/`](../docs/plans/pick-yoy-floor/plan.md). One Opus builder, Fable adversarial review (verdict: approve after two one-line fixes, both applied: the Q-018 closure relocation and a `try/finally` knob restore in `test_pick_pricing_m6b`).

| Gate | Result |
|---|---|
| `pytest backend/tests` | **4275 passed, 1 skipped** (builder run 301 s, reviewer run 306 s; +37 `test_pick_yoy_floor.py`) |
| Sabotages | 8 by the builder (S1–S8, module docstring), 3 re-run independently by the reviewer (S1/S4/S6), all byte-copy restores + `__pycache__` cleared per [G-060](GOTCHAS.md) |
| Existing-test dispositions | 12 failures judged individually: market-semantics tests pinned at knob 0 (both regimes stay pinned), served-pricing tests now expect the floored value with floor-is-active side assertions, one test overturned by name (its docstring pinned the pre-ruling behavior D-161 reverses), one evener re-fixture verified to reproduce the original geometry to 4 decimals |
| **Live curve (read-only prod DP)** | 1qb r1: 2027 1,750.7 → **2,184.6** · 2028 1,459.4 → **2,184.6** · 2029 → **2,184.6** · current-year and rounds 2–4 unmoved · sf_tep floors at 2,434.0 |
| Reference case | The MangoPatti card family (A.J. Brown + depth for a player + three future firsts): the pick side reprices from ≈ 3 × 1,171–1,751 to 3 × 2,184.6 |
| Runtime | scope §3 checklist owed post-deploy: a served card carrying a 2027/2028 1st displays ≈ a current mid-first |

**Fable code-walk:** knob-0 byte-identity — at `market_r1_yoy_floor = 0`, `_r1_yoy_floored` returns the raw market value before the anchor read and before any second market lookup (loader-call counter pins 1 load at knob 0, 3 at default). Four paths untouched at every knob value: step-1 slotted picks (return before the clamp's path), rounds 2–4 (bail ahead of the anchor read — value and lookup count unchanged), `tier_ladder` (stored value before any DP read), the DP-absent fallback (stored, None-guard proven load-bearing). Anchor = DP's own earliest slotted season; a stale rung-only season cannot steal it (S8); the DP-reader seam guard still asserts the exact reader set both directions. Judgment calls ACCEPTED with reasoning: anchor-lag risk is bounded (floor too high by one year's class drift, transient on DP's 24 h TTL, and under the flat ruling the pick still serves ≈ a current mid); the [0,1] clamp mirrors `year_decay`'s for the mirrored arbitrage.

## 2026-08-24 — Feedback wave (5 groups, 11 items): full gates green on `claude/new-user-feedback-55320e`; TestFlight checklists owed

Batch: [`docs/feedback/items/346-quickset-tier-drop/plan.md`](../docs/feedback/items/346-quickset-tier-drop/plan.md).
Groups A (#376/#379/#394 outlook & filters row), B (#397/#398 tour pin), C (#395/#396 lineup impact),
D (#386/#391 guide layout notify), F (#346/#381 QuickSet HOLD, [D-160](DECISIONS.md)). All fast-track, full gates, no express.

- **Phase 1:** dual-agent plan/author/critique per group; every critique round found real defects
  (self-satisfying checklist steps in B/D, a blacklist-beatable guard spec in A, two self-satisfying
  pytest sabotages in C caught by hand-recomputation, 7 contract amendments in F). All resolved, logs in each folder.
- **Phase 2:** 7 build agents in isolated worktrees, disjoint ownership held; merges clean
  (one intended status.md both-halves conflict, resolved keep-both).
- **Phase 3 (round 1, agents A+B independently, commit `c8b0e224`):** both PASS all five groups.
  `tsc --noEmit` clean · **78/78** `mobile/tests/check-*.js` green · testid-lint OK · full
  `pytest backend/tests` **4238 passed / 1 skipped** (×3 independent clean runs) · every PRD sabotage
  mapping re-proven red→green by both agents independently (12 in A, 5+2 probes in B, 6+2 in C, 4 in D, 7+guard-13 in F)
  · `web/`+`extension/` diff empty · Group F mobile↔backend payload shape verified consistent.
  One convergent finding (F-1, minor): Group F T-2's sabotage wording overstated (conditional echo only) — PRD tightened, no code change.
- **Known environment gotcha (recorded):** `test_deck_signal_v2.py::test_flag_on_writes_impressions_in_served_order`
  fails against a `data/trade_finder.db` left by a previous full sweep in the same tree; fresh data dir passes.
  Not a code regression (bisected: same commit passes clean).
- **Version:** mobile 1.16.4 (app.json + Info.plist; `test_app_version_consistency` green).
- **Owed (the only runtime evidence, D-056):** the five operator TestFlight checklists —
  consolidated in [`docs/feedback/items/346-quickset-tier-drop/testflight-checklist-batch.md`](../docs/feedback/items/346-quickset-tier-drop/testflight-checklist-batch.md).
  CI on the pushed sha pending at entry time; ship gate = operator go/no-go.
## 2026-08-24c — Waves A + B0 SHIPPED — PRs #197/#199, EAS 1.16.4 (130) submitted

Wave A merged as `7452650` (CI green: backend 9m14s · typecheck · lint) with the Fable review's A1/A2/A4/A6 fixes on top (gates re-run on `274a0ea9`: tsc · 77/77 · lint · pytest 4230/1). Wave B0 rebased over it and merged as `14a4ce4` (CI green) with review fix B1 (MatchesScreen prefill) + the reviewer's doc-conflict resolutions (checklist H→I, steps 79–99); gates on the rebased tip: tsc · 78/78 · lint · pytest 4230/1. `git diff feat/inline-home-b0 origin/main` EMPTY at merge. EAS production **1.16.4 (130)** built and submitted to App Store Connect (submission `a7b08771`). `FTF_SKIP_SIM_GATE=1` on pushes (D-056). **Owed on 130:** checklist section H (63–78; 63–67 on a COLD league load) and I1 (79–83, flag-off regression). `calc.inline_home` stays false until Wave B.

## 2026-08-24b — Wave B0 the layout merge (`calc.inline_home`) — full gates, FLAG DARK, NOT MERGED, on `feat/inline-home-b0`

Scope: [`docs/plans/onboarding-tour-merge/scope-wave-b0.md`](../docs/plans/onboarding-tour-merge/scope-wave-b0.md) · [D-158](DECISIONS.md) · plan §3b. Branched from `origin/main` @ `ff153a0f`. **No PR, no merge.**

| Gate | Result |
|---|---|
| `mobile` `tsc --noEmit` | clean, exit 0 |
| Every `npm run test:*` guard | **78 ran, 0 failed** (77 existing + the new `test:inline-home`) |
| `bash mobile/scripts/testid-lint.sh` | `testid-lint OK` |
| `python3 -m pytest backend/tests -q` | **4230 passed, 1 skipped**, 336 s, exit 0 |

**New guard `mobile/tests/check-inline-home.js`** (10 sections, 46 assertions). Pins, in order: the flag ships **false** in `config/features.json` with a D-158/kill-switch comment, is mirrored false into `release.json` / `onboarding-v2.json` / `profiles-on.json`, and is registered in `backend/feature_flags.py`; **exactly one** `<TradeBuildCanvas>` mount, with `canvasHost` resolving the flag path AHEAD of the #270 experiment and the experiment's own `!firstRun && !singlePin` gates intact; the rail dies only on the flag path and `showSuggestionRail` defaults to `true`; no `onShowMeAround` reaches the inline mount; the pushed page's tour is refused at BOTH doors with the guard as an effect dep, and `utils/calcTour.ts` is untouched (Wave A owns it); the fork and the ✓ queue are each **one definition, two callers, no second emitter**; the inline search neither navigates nor writes a handoff, stamps `deckOrigin:'calculator'`, and adds no `generateMutation.mutate` site (count still 8); the receipt's **Clear IS `handleSearchAllTrades`** and both end-of-deck Search-all buttons stand aside for it; all three `navigate('TradeCalculator', {prefill})` calls survive for the flag-off path; `CHIPS` still says `Calc`.

**Existing guards updated to the new truth, none deleted:** `check-calc-merged-behavior.js` 13/13a/13b re-pointed at `utils/canvasSearch.ts` (the fork moved files, the contract did not) plus new 13c–13e; 18a–18f re-pointed at `utils/queueCalcTrade.ts` plus new 18h/18i. `check-offer-prefill-330.js` — the choke-point region/dep pattern now admits the added `canvasRunSeq` trigger, with the three original deps still required in order. `check-calc-tour.js` 15a — the auto-start dep list gained `inlineHomeOn`, the fifth guard.

**Caught by the gates, not by review:** the first full pytest run failed `test_entitlements.test_features_json_keys_known` — a new `config/features.json` key must also be registered in `backend/feature_flags.py` `FLAG_KEYS`. Fixed and re-run clean. (The three-fixture mirror was done up front; only release.json is exact-mirror-tested, but onboarding-v2/profiles-on are what other suites boot from.)

**Code-walk (flag-off byte-identity), full trace in the scope block §3.** Each behavior change is one gated site whose flag-off value is the original expression: `TradesScreen.tsx:4887` `canvasHost` collapses to the old mount condition; `:4901` `inlineAnchorShown` is unconditionally false, which makes the receipt unreachable and restores both end-of-deck conditions; `:1410/:2855/:2940` early-return above untouched `navigate` calls; `:2607`'s added dep `canvasRunSeq` is a frozen `0` (its only writer is inside a handler passed as a prop only on the flag path); `TradeCalculatorScreen.tsx:129/193/233/685/747/782` each reduce to the pre-wave expression; `TradeFinderModeBar.tsx:147` falls back to `c.label` with `CHIPS` untouched; `TradeBuildCanvas.tsx` reads no flag at all — every change is an optional prop with a today-preserving default.

**Runtime evidence: NONE, and that is the known gap.** Section **I** of [`docs/feedback/items/384-calc-finder-merge/testflight-checklist.md`](../docs/feedback/items/384-calc-finder-merge/testflight-checklist.md) is new and **unrun** — I1 is 5 flag-OFF regression steps (79–83, the pass that matters while the flag is dark) and I2 is 15 flag-ON steps (84–98). (Lettered H→I and renumbered at the Wave-A rebase; the content is unchanged.) The two things no structural guard can see: the **ordering** inside the #330 choke point when the inline search re-fires it (reset → fork → dispatch), and the **layout** of a full In-league calculator stacked above a swipe deck on a small screen. Under D-056 that checklist is the only runtime proof this can get.

**Pre-push gate:** `FTF_SKIP_SIM_GATE=1` (D-056 standing posture — the simulator marker `qa/sim-runs/last-sim-run.json` is retired); the evidence run instead is the four gates above plus the new guard.

## 2026-08-24 — Onboarding-tour Wave A — full gates green on `feat/tour-wave-a`; runtime evidence owed

Scope block: [`docs/plans/onboarding-tour-merge/scope-wave-a.md`](../docs/plans/onboarding-tour-merge/scope-wave-a.md)
(§5 carries the file:line code-walk for both new parks). Full gates, **not** express.

| Gate | Result |
|---|---|
| `pytest backend/tests` | **4230 passed, 1 skipped**, 333 s, exit 0 |
| `npx tsc --noEmit` (mobile) | clean, exit 0 |
| Every `npm run test:*` guard | **77/77 passed** (looped over `package.json`, none skipped) |
| `mobile/scripts/testid-lint.sh` | OK |
| Assertion counts on the three extended suites | `check-calc-tour` 168 ✓ · `check-guide-script` 455 PASS · `check-card-disposition` 17 PASS |
| `githooks/pre-push` simulator gate | **skipped** — `FTF_SKIP_SIM_GATE=1`, the standing posture under [D-056](DECISIONS.md). What ran instead is every other row of this table plus the scope block's §5 code-walk; `qa/sim-runs/last-sim-run.json` is deliberately not written |

**New structural coverage.** `check-calc-tour.js` §45 (a–n) pins both parks three ways each: the
park is taken at the right seam, it is **time-bounded** and expiry ends the run (an unbounded park
holds the interrupt hold and mutes every interstitial app-wide), and the resume is wired end to
end — screen prop → runner export → `requestAt`. 45c/45d/45e pin the **level** semantics of the
In-league ready signal; 45l/45m pin that the component's `inLeagueReady` predicate stays the
negation of the two early returns it derives from. §40d–40f cover n22's new target. New in
`check-card-disposition.js` §4: `trades.card-meter` is an effect registration gated on
`cardMeterMounted`, unregisters on teardown, and its wrapper is a non-collapsable `View`. New in
`check-guide-script.js` §10/§11: the ten converted beats are `cta` **with buttons**, and the only
`advance: 'tap'` beats left in the whole script are the two named exemptions (`s2.3` deprecated,
`n9` out of Wave A's scope) — the closed-set half is what catches a *new* tap beat.

**Sabotage verified (1).** Deleting the `if (inLeagueReady)` fast path from `calcTour.ts` turned
45c red; restoring it turned it green. The rest of §45 is regex-on-source and was written against
already-passing code, so it is pinned but not independently falsified.

**Two guards UPDATED to the new truth, not deleted.**
`check-guide-script.js` `8b` asserted `S.n6_1(false).ctas === undefined` — a statement about that
beat being tap-advance. Restated as the property that mattered: the router-less variant carries
exactly one plain `Next` and **none of the routing variant's buttons** (+ `8b-ii`, no lifetime
bound). `backend/tests/test_seed_ui_test_db.py::test_onboarding_v2_flags_are_release_plus_the_onboarding_surface`
asserted `landing.try_before_sync is True` in both flag files; now `is False` in both, with the
cross-file agreement — the thing that actually broke main CI on 2026-08-23a — left intact.

**Runtime evidence: ZERO, and two items genuinely need it.** New **section H** (steps 63–78) in
[the #384 checklist](../docs/feedback/items/384-calc-finder-merge/testflight-checklist.md), unrun.
Steps 63–67 must be run on a **cold** league load: both parks fix a *race*, and a warm React Query
cache is exactly what made the W8 simulator pass a false green while note 12 stayed open. Step 64
(airplane mode) is the one that proves a park that never resolves still releases the hold.

## 2026-08-24 — Knockout refine (R5/R1/R2/shape) — full gates, MEASURED on prod FFV3, on `claude/knockout-refine-0823`

Plan: [`docs/plans/knockout-refine/`](../docs/plans/knockout-refine/plan.md) · [D-159](DECISIONS.md). Built by Opus B1/B2, adversarially reviewed by a Fable reviewer (verdict: safe to merge; the D-159 renumber + two doc fixes, all done pre-merge).

| Gate | Result |
|---|---|
| Full `pytest backend/tests` | **4230 passed, 1 skipped** (lead run 454 s and reviewer run 442 s, both exit 0; +19 `test_knockout_refine.py`, +13 `test_shape_knob.py`) |
| Byte-identity at off settings | 210-pair verdict sweeps against predicates vendored from `c321958` (reviewer diffed the vendored copies against `git show` — the true old bodies) |
| Sabotages | B1: 8 · B2: 3 · reviewer re-ran 3 independently. All byte-copy restores; see [G-060](GOTCHAS.md) for the `.pyc` trap two of these hit |
| Operator invariants (reviewer, incl. scratch end-to-end) | #341 double-startable-RB strip dies at every knob setting; #304 Loveland dies with the rescue lit; a delta-2 3-for-1 that strips a position below startable depth is emitted by the optimizer and killed by R2 relief |
| **Measured (read-only prod replay, league `1312140920132497408`, 4 variants)** | baseline 280 cards / 270 ideas / 1 consolidation-family card / 18.1% sub-450 share · **bundle+raw-R1 280 / 267 / 8 / 19.4%** · bundle+adjusted-R1 275 / 260 / 8 / 17.9% · filler-0.10 276 / 263 / 10 / **27.0%** |
| Flip decision from the measurement | `filler_min_frac` **0.15** (0.10 doubles junk share) · `overpay_adjusted` **0** (adjusted killed ~7 consolidation ideas incl. 2x1s 28→21 for a 1.5pp junk benefit) · `trade_elo_gap_max` **0** · `v3_shape_max_delta` **2**. Applied via admin config API after the deploy seeds the new rows; each individually revertible |
| Runtime | scope §3 checklist owed post-flip (3-for-1s appear; no card strips a position below startable depth on either side) |

**Reviewer code-walk:** at the off settings every predicate is verdict-identical to origin/main @ c321958 — `overpay_ok` knob<1 takes the untouched raw-sum branch; `pos_net_ok` reduces to the old `all(abs(n)<=cap)` with the relief unread when the knob is 0 or ctx is None; `need_gate_ok` at knob 0 runs the refactored-but-equivalent primary-only checks; the optimizer's `SHAPE_D=int(_c(...))=1` reproduces the literal `>1`. `opp_ctx` is early-bound per member via a lambda default arg; the boarded-branch consensus fallback shares the member-scoped kwargs, so no caller sees another member's context.

## 2026-08-24 — `mascot_ram_rollout` gate verified on production

`GET /api/feature-flags` × 3, against live production:

| Request | `experiments` | overlay | base flag |
|---|---|---|---|
| allowlisted device id | `mascot_ram_rollout: treatment` | `{onboarding.mascot_ram: true}` | `false` |
| no device header | `{}` | absent | `false` |
| random device id | `{}` | absent | `false` |

**This proves the gate, not the render.** It shows the overlay reaches exactly one unit and no other. It does **not**
show a ram on a screen — the TestFlight checklist is still unrun, and section A (flag OFF is byte-identical) should be
run *before* trusting anything under flag ON.

## 2026-08-24 — v1.16.3 (129) to TestFlight: CI green on GitHub, runtime evidence still owed

**CI on the pushed sha (not just local):** `backend-tests` pass 8m58s · `mobile-typecheck` pass 1m2s ·
`maestro-testid-lint` pass 10s. Merge state `CLEAN` before squash.

**Local, post-merge, after the version bump:** pytest **4198 passed, 1 skipped**; `tsc --noEmit` clean; 77/77
`check-*.js`; testid-lint OK.

**`test_app_version_consistency` earned its place.** Bumping `app.json` to 1.16.3 without
`ios/DTFDynastyTradeFinder/Info.plist` failed immediately — exactly the bare-workflow trap D-057 documents.

**Runtime evidence: still ZERO.** The build exists and is processing at Apple, but
[the checklist](../docs/plans/ram-mascot/testflight-checklist.md) is unrun and cannot be run until the build is
installed **and** `mascot_ram_rollout` is launched. Until both, the app on TestFlight renders The Analyst — which is
itself checklist section A, and the first thing to verify.

## 2026-08-23b — `test_stud_tax_pinned_market` flake pinned: breaker wall-clock budget removed from test inputs

**Diagnosis, with a deterministic repro.** The CI failure on `8fd23e2` (run 32681703490) was the breaker's 250 ms
`breaker_ms_budget`: past the 0.6× pass-2 checkpoint (`trade_breaker.py:929`) a stamp's payload changes
(`skipped: {reason: "budget"}`, pass-2 classes emptied), so the stamp-twice-and-compare tests had wall clock as a
hidden input. Reproduced exactly (same assertion diff) by skewing `trade_breaker.time.monotonic` +12 ms/call during
the second stamp only — the asymmetry a loaded runner produces. Not fixture pollution, not iteration order. Full
write-up: [G-059](GOTCHAS.md).

**Fix + evidence.** `_env` autouse fixture in `backend/tests/test_trade_breaker.py` pins
`breaker_ms_budget = 10**9` (budget rungs keep their own coverage via `_snap_with` / fake clocks). Verified:
67/67 `test_trade_breaker.py` under a hostile clock (+12 ms on *every* `monotonic()` call — pre-fix this fails);
full suite `python3 -m pytest backend/tests -q` → **4198 passed, 1 skipped** (6m22s, local).

## 2026-08-23 — Fleeced mascot swap (`onboarding.mascot_ram`), CI green on `claude/ram-mascot-fleeced`

**Ran, and what each proved.**

| Gate | Result | What it actually proves |
|---|---|---|
| `pytest backend/tests` | **4198 passed, 1 skipped** | The new flag key registers cleanly. No server behaviour branches on it |
| `npx tsc --noEmit` | **clean** | The switch and `RamAvatar` typecheck under `strict` |
| `for f in tests/check-*.js` | **77/77 pass** | Including the new `check-mascot-ram.js`. No existing guard regressed |
| `mobile/scripts/testid-lint.sh` | **OK** | No testID moved — the `guide.avatar.<pose>` id is on the wrapper, not the avatar |

**`check-mascot-ram.js` was sabotage-tested, which is the only reason to trust it.** Forcing the gate
(`useOnboardingFeature(...) || true`) → caught. Re-exporting a sprite trimmed to its bounding box → caught, reporting
**97.9 % ink against the 70 % target**. Both reverted; guard green. The inset check decodes the PNG alpha channel
itself (RGBA8 and palette+tRNS) rather than trusting file size — and it caught its own blindness first, failing
"inset measurable" when it only handled RGBA and the sprites were palette PNGs.

**Copy pass (same day).** `check-guide-script.js` extended so `lineRam` takes the same per-class word cap as `line` — without it the ram variant would have been an uncapped side-door into the copy budget. Sabotage-tested: a 30-word `lineRam` on a `tap` beat (cap 20) → caught. `check-mascot-ram.js` gained six copy assertions; hardcoding `>The Analyst<` back into `AnalystGuide` → caught. Full re-run after the copy work: **4198 passed, 1 skipped**, `tsc` clean, 77/77 guards, testid-lint OK.

**A pre-existing CI failure was fixed, not introduced.** `test_release_flags_mirror_features_json` was **already red on
`origin/main`**: `trade.full_sweep` was lit in `config/features.json` by #182 without updating
`backend/tests/fixtures/flags/release.json`. Verified against `origin/main` before touching it — unrelated to this
feature, but it blocked the "CI green" gate for everyone.

**The drift was wider than one file, and the first fix was incomplete.** Correcting `release.json` alone then broke
`test_onboarding_v2_flags_are_release_plus_the_onboarding_surface` and `test_profiles_on_flags_turn_on_public_pages_only`,
because those fixtures assert an exact divergence set from release. #182 had updated **none of the three**. All three
now carry `trade.full_sweep: true` and the divergence sets are back to their single intended key each. Worth noting for
the next flag flip: lighting a flag in `config/features.json` means updating **three** fixtures, not one.

**NOT run — owed:** [the TestFlight checklist](../docs/plans/ram-mascot/testflight-checklist.md). It needs a build
containing `assets/mascot/ram/` (bundled sprites, no OTA channel) and the `mascot_ram_rollout` experiment running. Until
then there is **zero runtime evidence** for this change — the guard proves shape, `tsc` proves types, neither has seen a
sprite on a screen.

## 2026-08-23a — main CI red → green: full-sweep fixture mirrors flipped

The full-sweep flip (2026-08-22j, LIT at merge) updated `config/features.json` but not the fixture mirrors, so `test_seed_ui_test_db.py::test_release_flags_mirror_features_json` failed on every `main` run after it (first surfaced on docs-only PR #184). Fix: `trade.full_sweep` → `true` in `release.json` / `onboarding-v2.json` / `profiles-on.json` (`all-on`, `release-300`, `release-espn-send-off` never carried the key). `python3 -m pytest backend/tests -q` on the fix branch: **4198 passed, 1 skipped** (5:20). Reminder the mirror rule exists for: flag flips update the fixtures in the SAME commit.

## 2026-08-22j — Full sweep (`trade.full_sweep`) — full gates; LIT 2026-08-23 by operator instruction at merge

Plan + scope: [`docs/plans/full-sweep/`](../docs/plans/full-sweep/plan.md) · [D-154](DECISIONS.md). Built by Opus agents A1 (engine/flag/knobs/tests) and A2 (arm parity + docs), adversarially reviewed read-only by A3 (2 blockers, 7 should-fix, 5 nits — all closed before commit), lead-reconciled.

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q -x` | **4198 passed, 1 skipped** (+17 `test_full_sweep.py`, +8 `test_arm_sweep_parity.py`; bake-off arm-A golden green with two new `_PINNED_KNOBS` rows) |
| `tsc --noEmit` / `check-*.js` / `testid-lint` | unaffected — no client change (no new testID) |
| Sabotages, `test_full_sweep.py` | unconditional `break` restored at either loop → the matching `[legacy]`/`[v2]` visit test red (loops pinned independently); time rail deleted from either loop → red; `> 0` disable inverted → both budget-0 tests red; flag dropped from the rail → the flag-off leak test red; clamp dropped at either `server.py` site, or either site reverted to the bare constant → the AST pin red. All restored from byte copies (not `git checkout --` — uncommitted branch). |
| Sabotages, `test_arm_sweep_parity.py` | `trade_gen_v2.py` break after 2 members → 3 red; `trade_gen_fit.py` 2-member break → 2 red. A3 re-ran four of the above independently and reproduced every one. |
| Runtime | **none yet** — server-side flag, no client build needed. Operator lit the flag at merge (2026-08-23), ahead of the [scope §3 TestFlight checklist](../docs/plans/full-sweep/scope.md); the checklist (≥ 9 of 11 partners; `gen_ms` recorded; kill switch proven) is now the **post-flip verification**, still owed here. |

**A3 code-walk — `trade.full_sweep` OFF produces byte-identical output to `origin/main` @ `b6e906a`.** (a) `git grep -n trade_full_sweep -- backend/ config/` → exactly two executable reads, the guarded exits in `_generate_trades_impl` and `_generate_trades_v2`; the guard is `if not FLAGS.trade_full_sweep and len(new_cards) >= global_target: break` — flag off ⇒ the identical shipped test, same position; the time rail is `if FLAGS.trade_full_sweep and …`, never evaluated flag-off. (b) No other read: no `is_enabled("trade.full_sweep")`, no import-time capture; `DEFAULT_FLAGS` derives `false` from `FLAG_KEYS`; `features.json` ships `false`. (c) `_deck_cfg` returns a float, both `server.py` reads wrap `max(1, int(...))`; executed: key present → 5, key absent → fallback constant → 5; `_split_exploration_pool(cards, 5) == split(5.0)` on a 4×9 fixture — identical partitions. (d) `FLAGS` is a process-global `_FlagsProxy` (verified at runtime), so every bake-off arm reads the same value; `model_a()`/`model_challenger()` wrap only the thread-local `_cfg_override`. (e) The one addition on the flag-off path is a single `time.monotonic()` capture per loop entry (`_sweep_t0`) — no behavioural effect; "byte-identical output", not "no added instruction". (f) `git diff origin/main -- backend/trade_service.py backend/server.py` contains nothing beyond plan §3.2/§3.3/§3.5.

**A3 findings closed:** B1 v3 pairs have no deadline → `full_sweep_budget_s` rail (30 s) + every doc corrected; B2 flag is global so arm A sweeps too → accepted + recorded in `scope-phase2.md`; S1 `bakeoff_serve_interleaved` is **1 in prod** (A3 read the local DB) → docs state the dial under both postures; S2 wrong arm-A reason → rewritten in test + scope-phase2; S3 `max(1, …)` clamps; S4 G-058/Q-030 live on the review branch (`claude/trade-model-restrictiveness-7f3975`) — **merge that PR first**; S5/S6/S7/N1/N2/N4 wording; N5 `docs/plans/ram-mascot/brief.md` also proposes D-154 — first to land on `main` keeps it.

## 2026-08-22i — #384 W8 — simulator reproduction + mobile gates, v1.16.2 (EAS 128)

**First simulator evidence since D-056** (one-off debug of a live regression; the harness stays retired). Release build, iPhone 16 / iOS 18.4, against production. Reproduced the blank-band bug on the sign-in username beat on `origin/main` (`d79f9f4`), then on the fix: username beat, n10, n11 (Set outlook), n12, n13, n15, n16 all render ring + avatar + bubble + Next/CTA. Not reached: n18 → deck (session unverified → `verification_required` on generation and outlook writes). `npx tsc --noEmit` clean · 76/76 guards (spotlight §14 a–f, calc-tour 29/41/42 new; sabotage: native driver back on / activation-keyed spring → 3 red) · `testid-lint OK`. Backend untouched.

**Second simulator pass (same branch, pre-build):** after the first-landing fixes (timer fallback, latch-on-cutout + live offset, hold-before-teardown) — launch → Acquire → Manual calc auto-starts n10 with the ring on the In-league tab and the band directly beneath it (no overlap, no deck-beat hijack); tap In league → n11 rings the outlook row, bubble above with "Set outlook"; "Show me around" replays from n10 with ring + band. Found and fixed in the same pass: auto-start with n10 capped opened on n12's degrade line (calc-tour 44/44a). Final gates on the tip: `npx tsc --noEmit` clean · 76/76 guards · `testid-lint OK`. Simulator setup trap recorded as [G-057](GOTCHAS.md) (debug Hermes under a `Release` marker → SIGSEGV at launch). **Shipped:** squash PR [#179](https://github.com/mattmurf77/fantasy-trade-finder/pull/179) → `fe77b28`; CI on the PR green (backend-tests 8m53s, typecheck, testid-lint). EAS production build **1.16.2 (128)** `59b89897` finished and was submitted to App Store Connect 2026-08-22 (submission `338a1549`); checklist §G is owed against 128.

## 2026-08-22h — #384 W7 device-feedback fixes — mobile gates, v1.16.1 (EAS 127)

Branch `fix/384-tour-device-feedback`. `npx tsc --noEmit` clean · 76/76 `check-*.js` · `testid-lint OK`. Backend untouched (pytest unchanged from 2026-08-22g). Sabotages red: fixed `top: 54` band, constant ABOVE branch, solver ignoring `insets.top`, a beat back to `advance:'tap'`, n20 losing its target, `trades.send-btn` registration deleted, calculator dropping `onContentSizeChange`, auto-start not listening for `transitionEnd`. **Runtime:** the operator's device report on build 126 IS the evidence this wave answers; checklist section G (steps 50–62) is owed against build 127. The placement *mechanism* (occlusion vs. far-from-ring) is inferred from correlation, not observed — if step 54 still shows a bare ring, suspect native-header z-order.

## 2026-08-22g — #384 SHIPPED — PR #172 `80dee42`, flags LIT, EAS build 1.16.0 (126) submitted

Pre-ship gates at `304f55a` (flags lit, fixture mirrors updated): `pytest backend/tests -q` **4173 passed / 1 skipped** · `npx tsc --noEmit` clean · 76/76 `check-*.js` · `testid-lint OK`. `FTF_SKIP_SIM_GATE=1` on push (D-056 standing posture — the evidence is the structural suite + the rewritten, now POST-ship, TestFlight checklist). CI on `main` run 32585974208: typecheck + testid-lint green; backend job still in progress when this was written. EAS production build **1.16.0 (126)** `01465dd0` finished 16:57Z and auto-submitted to App Store Connect (submission `9a89555f`). **No device run yet** — the checklist in `docs/feedback/items/384-calc-finder-merge/testflight-checklist.md` is owed against build 126.

## 2026-08-22f — #384 W6-A + W6-B — full gates, FLAG DARK, NOT MERGED, on `claude/manual-calculator-e2e-review-39a467`

W6-A (`d6c54cf`, ✓ queue contract, [D-152](DECISIONS.md)) and W6-B (fairness-only packages +
tour reshape, [D-153](DECISIONS.md)), each lead-reviewed line by line before commit.

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **4173 passed, 1 skipped** (+26 `test_calc_trade_queue.py`, +19 `test_fair_packages.py`; asset-ideas + bake-off arm-A goldens untouched and green) |
| `cd mobile && npx tsc --noEmit` | clean |
| every `mobile/tests/check-*.js` (76, all `npm run`-wired) | 76 / 0 failed — `check-guide-spotlight-tracking` gained rule 10 (scroll announcement mandatory where guide targets sit in a ScrollView) |
| `bash mobile/scripts/testid-lint.sh` | OK |
| Sabotages | W6-A: 5 backend + 4 mobile red/restored · W6-B: toggle restored → red; fair anchor also arming the model → red (two guards); calculator `onScroll` dropped → red; idea give side ≠ anchor → red; random ids → red |
| Runtime | **none** — TestFlight checklist (`docs/feedback/items/384-calc-finder-merge/testflight-checklist.md`, rewritten for W6) UNRUN. Prerequisite flags incl. `onboarding.guide_v2` (false) still gate the tour |

## 2026-08-22e — #384 merged calculator W5 + guard hardening — full gates, FLAG DARK, NOT MERGED, on `claude/manual-calculator-e2e-review-39a467`

W5 answers the [2026-08-22 e2e review](../docs/feedback/items/384-calc-finder-merge/review-2026-08-22-e2e.md)
(5 P0 / 8 P1) in three build packages — `fcf3413` (analytics registration), `9dcd003` (the deck
side), `a52c91e` (the tour) — plus this evidence pass. Scope block:
[scope.md](../docs/feedback/items/384-calc-finder-merge/scope.md) (written retrospectively; gate 1
had been skipped). Decision: [D-150](DECISIONS.md), amended. Checklist:
[testflight-checklist.md](../docs/feedback/items/384-calc-finder-merge/testflight-checklist.md) —
rewritten against current behaviour, **still UNRUN**.

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **4128 passed, 1 skipped** (+11 over W4 — the taxonomy/NON_INTENT registration) |
| `cd mobile && npx tsc --noEmit` | clean, exit 0 |
| every `mobile/tests/check-*.js` | **76 files, 0 failed** |
| `mobile/scripts/testid-lint.sh` | **OK** |
| `npm run test:<name>` coverage | **76 / 76** — the last 19 unscripted guards wired into `mobile/package.json` (additions only, 19 insertions / 0 deletions) |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, standing posture under [D-056](DECISIONS.md) |

**Guard hardening — 15 sabotages, all GREEN before / RED after.** The review's QA pass ran 61
cycles against W4's guards and found **12 that stayed green**. Each named case below was patched
into the real source, run against the guard as it stood at `a52c91e` **and** against the hardened
guard, then reverted (`git status --short` confirmed only `mobile/tests/` + `mobile/package.json`
modified afterwards).

| # | Sabotage | Guard | Before | After | Assertion that catches it |
|---|---|---|---|---|---|
| 1 | `const merged = useFlag('calc.merged_layout') \|\| true;` | `check-calc-merged-layout` | GREEN | RED | 4 — the flag read anchored to its whole statement incl. `;` |
| 2 | `const merged = !useFlag('calc.merged_layout');` | `check-calc-merged-layout` | GREEN | RED | 4 (same anchor) |
| 3 | `compact={true}` at both `TradeSide` mounts | `check-calc-merged-layout` | GREEN | RED | 4b — every `compact=` prop must read exactly `merged` |
| 4 | target-registration effect loses `if (!merged) return;` | `check-calc-merged-layout` | GREEN | RED | 4c — the effect body must bail; 4d pins `[merged]` deps |
| 5 | `if (give.length \|\| receive.length)` — Include OFF still pins | `check-calc-merged-behavior` | GREEN | RED | 13a — `includePlayers &&` must be IN the pin condition |
| 6 | `reasonsAsOverlay = calcMergedOn && deckOrigin === 'calculator' \|\| true;` | `check-calc-merged-behavior` | GREEN | RED | 1c — anchored to the statement terminator |
| 7 | `endTourHold: () => {}` | `check-tour-suppression` | GREEN | RED | 8 — the store is now transpiled and EXECUTED, not modelled |
| 8 | `beginTourHold: () => {}` | `check-tour-suppression` | GREEN | RED | 2a — `tourHold` read back off the real store |
| 9 | the `blocked_by:'tour'` `track()` call deleted, doc comment kept | `check-tour-suppression` | GREEN | RED | 13 — anchored on the emitter, not the phrase |
| 10 | `cursor = 0` dropped from `startCalcTour` (re-entry resumes) | `check-calc-tour` | GREEN | RED | 29a — the reset triple before `requestAt(0)` |
| 11 | auto-start effect deps `[]` | `check-calc-tour` | GREEN | RED | 15a — `[calcMergedOn, prefill, hasLeague]` |
| 12 | demo-bridge surface deleted from `TradesScreen` | `check-demo-calc-removed` | GREEN | RED | 7 — three named anchors, replacing a ≥2-FILE threshold that prose could satisfy |
| 13 | "Retry, or switch to the demo league." copy restored | `check-demo-calc-removed` | GREEN | RED | 8 — comment-stripped copy scan (new) |
| 14 | n12 loses `target`, keeps "This is your canvas" | `check-guide-script` | GREEN | RED | 5b — a `degradeLine` may exist only on a beat with a `target` |
| 15 | n22 loses `target`, keeps "Tap the meter…" | `check-guide-script` | GREEN | RED | 5b (same rule) |

`check-tour-suppression` no longer re-implements the reducer it tests: it transpiles
`useInterruptCoordinator.ts` with the project's own TypeScript and executes it against a minimal
zustand `create`, the way `check-presentation-v2.js` executes `tradePresentation.ts`. That single
change is what makes cases 7 and 8 falsifiable — the old model was green through both because
nothing in the file ever ran the source's version. `check-guide-script`'s DEIXIS vocabulary was
also widened with the calculator beats' element nouns (`canvas`, `cross`, `check`, `meter`,
`columns`, `arrows`), and the copy budget was not loosened.

**What this run does NOT prove.** Nothing has executed on a device or a simulator. The feature is
almost entirely presentation and timing — two columns at SE width, 53pt tap targets, spotlight
geometry, the rhythm of a 15-beat tour — which is the class of claim a structural guard cannot
reach. The rewritten TestFlight checklist (46 steps, A/B/C/D + a five-flag Prerequisites table) is
the only runtime evidence available, and it is unrun.

## 2026-08-22d — #384 merged calculator W0–W4 — full gates, FLAG DARK, NOT MERGED, on `feat/calc-finder-merge`

Branch cut from `origin/main` `941a36d`. Five waves, each committed with its own gate run.
Scope/plan: [docs/feedback/items/384-calc-finder-merge/](../docs/feedback/items/384-calc-finder-merge/plan.md) ·
Decision: [D-150](DECISIONS.md) · Checklist: [testflight-checklist.md](../docs/feedback/items/384-calc-finder-merge/testflight-checklist.md) (**UNRUN**).

| Gate | Result (identical at every wave boundary) |
|---|---|
| `python3 -m pytest backend/tests -q` | **4117 passed, 1 skipped, 0 failed** — unchanged from the branch point; the only backend delta is a flag registration |
| `cd mobile && ./node_modules/.bin/tsc --noEmit` | clean, exit 0 (`npm ci` in the worktree, never a symlink) |
| every `mobile/tests/check-*.js` | **76 scripts, 0 failed** (71 at branch point; +5 new) |
| `mobile/scripts/testid-lint.sh` | **OK** |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, standing posture under [D-056](DECISIONS.md) |

**New guards, all red-proofed:** `check-demo-calc-removed` (11 sabotages) ·
`check-calc-merged-layout` (9) · `check-calc-merged-behavior` (8) · `check-tour-suppression`
(7) · `check-calc-tour` (7). **42 sabotage cycles**, every one watched failing with its
intended message, every file byte-compared against a saved baseline after restore.

**Two guards do more than grep.** `check-tour-suppression` **executes** the real claim/release
reducer — assertion 6 runs the exact between-two-steps sequence W3 exists to fix — and guards
the model with named checks that the source still contains each rule it mirrors, so model and
implementation cannot drift silently. `check-calc-merged-layout` excises flag-gated regions by
brace balancing and tests the remainder, which is by construction the flag-off render.

**FIVE DEAD ASSERTIONS FOUND AND FIXED, all mine, none in the product.** This is the finding.
(1) `/isDemo/` matched `isDemoRenamed`. (2) `/onDemo/` matched `onDemoStarted`. (3) The
flag-gating check was a backwards proximity search that stayed green when the action row's own
gate was replaced with `{true ?` — it simply found the header's gate instead. (4) A fixed-size
character window read the NEXT JSX prop's body and failed on a close that was not its own.
(5) A drift detector threw an exception instead of failing a named assertion, which is red but
illegible in CI. Every one was found by sabotage, not by review.

**An existing suite broke honestly and was NOT loosened.** `check-decline-reasons.js` pinned
the ✕ condition as a literal string; W2's conjunct changed it. Rather than relax to
`disposition\.reasons[^?]*\?` — which would also accept `disposition.reasons && false ?`, the
exact defect those assertions exist to catch — the two legal shapes are enumerated. Verified
by sabotage that the updated matcher still rejects `&& false`.

**Copy budget verified BEFORE authoring, not after.** All 15 tour lines were word-counted
against their advance class up front (worst case 14/16), so `check-guide-script.js` confirmed
the budget rather than discovering a violation.

**Runtime evidence: NONE.** No device has run any of this. The two least-proven things are
named in the checklist's own "known-unverified" section: the two-column layout on a 375pt
screen (column width, the wrapped value line, and the two ~53pt action cells are all sized by
reasoning) and tour copy read beside the controls it names.

## 2026-08-22c — Feedback capture cap (2000 → 8000) + the three silences — full gates, backend SHIPPED, client awaiting a build

**Branch:** `claude/new-user-feedback-d4c47d`, cut from `origin/main` `9e1a8be` (0 ahead / 0 behind at branch time).
Operator declared **express** on the cap; I flagged the CLAUDE.md bright line (it changes a documented
API contract) and got a confirming yes for 8000 before proceeding, so **full gates ran anyway**.
Scope: [docs/plans/feedback-capture-cap/scope.md](../docs/plans/feedback-capture-cap/scope.md) ·
Decision: [D-149](DECISIONS.md) · Gotcha: [G-055](GOTCHAS.md).

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **4117 passed, 1 skipped, 0 failed** (baseline 4114 on `9e1a8be`; +3 in `test_feedback_text_cap.py`) |
| `cd mobile && ./node_modules/.bin/tsc --noEmit` | clean, exit 0 (`npm ci` in the worktree — **not** a symlink) |
| every `mobile/tests/check-*.js` | **71 scripts, 0 failed**, incl. the new `check-feedback-capture.js` (6 assertions) |
| `mobile/scripts/testid-lint.sh` | **OK** (3 new testIDs: `feedback.char-count`, `feedback.note-error`, `feedback.save-error`) |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, standing posture under [D-056](DECISIONS.md) |

**Backend sabotage evidence — 3 cycles, each RED with the intended assertion, restored and byte-verified.**
S1 cap lowered back to 2000 → `test_the_report_the_old_cap_ate_now_lands`. S2 cap check deleted →
`test_one_character_past_the_cap_is_refused`. **S3 cap made to TRUNCATE at 2000 instead of refusing**
— this is the one that matters: it returns **`201`**, so every status-code assertion passes and only
the stored-length check (`len(stored[0]["text"]) == 2001`) catches it. Silent truncation is the same
data loss wearing a success code, and a boundary suite that only checks status codes would have
blessed it.

**Client guard red-proofed in BOTH directions.** `check-feedback-capture.js` run against the pristine
defect tree (`git show 9e1a8be:<path>`): **6 of 6 RED**, each message naming the real defect. Against
the fixed tree: 6/6 green. Then **20 sabotage cycles**, one per named failure branch — every one fired
the branch it targeted, every one restored and re-verified. The cross-file assertion (client cap ==
server cap == the number the 400 reports) **fired for real mid-build** when the two halves were
briefly out of step.

**Method note worth keeping.** The QA agent did *not* sabotage the live worktree: three agents were
holding uncommitted work, so `git checkout --` would have destroyed a peer's changes rather than
restored them. It ran every cycle against isolated file replicas and byte-compared afterwards. I hit
the same trap first-hand — a `git checkout -- backend/server.py` mid-sabotage reverted my own
uncommitted fix and I had to re-apply it. **Copy the good file aside before any sabotage cycle on an
uncommitted tree.**

**Runtime evidence: NONE, and the client half has none available.** Under D-056 the only runtime proof
mobile can get is an operator TestFlight pass, and these client changes are **in no build**. The
backend half is verifiable in prod directly (a >2000-char POST now returns 201).

## 2026-08-21d — Decision-ID attribution correction (docs only) — `fix/lld-decision-id-attribution`

Docs-only change: 12 wrong decision-ID citations for per-slot pick pricing corrected to **D-146**
across `LLD.md`, `api-reference`, `config-reference`, `data-dictionary` and `cross-client-invariants`.
**Zero code, schema, route, flag or analytics files touched** — `git diff --stat origin/main` is six
`.md` files.

| Gate | Result |
|---|---|
| `pytest backend/tests` | **not run — no Python file in the diff.** Nothing to exercise. |
| `tsc --noEmit` / testid-lint | **not run — no mobile file in the diff.** |
| CI (all three jobs) | runs on the PR; expected green by construction (no source files) |
| Simulator gate | **`FTF_SKIP_SIM_GATE=1`** — standing D-056 posture, and doubly moot here: markdown has no runtime. |

**Evidence actually run**, since the failure mode is *wrong prose*, not wrong behavior:

1. **Per-site verification against `DECISIONS.md`** — every one of the 12 sites read against the
   full text of D-144, D-146, D-147 and D-148 and attributed by *what the decision decided*, not by
   date or adjacency. D-146's own Status line (*"Renumbered from the draft's D-144"*) is the
   corroborating record; D-146's body names the LLD section by title.
2. **Anchor-resolution check over `LLD.md`** — slug every `^## ` heading, assert every `](#…)`
   target resolves AND equals the slug of its own link text. **Clean**, except a pre-existing
   `#section-1` inside a fenced markdown *template* block (illustrative, not a link).
3. **Residual grep** — `git grep D-144 -- living-memory/ docs/ ':!docs/plans'` returns only sites
   that genuinely mean Receipts, plus the CHANGELOG history of the #168 renumber. `docs/plans/**`
   drafts intentionally retain the old ID.

**Not evidence:** nothing here was executed. The claim is that the citations now match
`DECISIONS.md`, and that claim is checkable by re-running items 1–3.

## 2026-08-22b — negmem SHIPPED to `main` (PR #168) — deployed dark to Render

**Merged:** squash PR [#168](https://github.com/mattmurf77/fantasy-trade-finder/pull/168) → `main` `7b7c314`; branch tip `71f63da` ledgered ([recovery](../docs/recovery/2026-08-22-negmem-ship.md)) before the remote delete.

| Gate | Result |
|---|---|
| `pytest backend/tests` (local, merged tree) | **4097 passed, 1 skipped, 0 failed** |
| CI `backend-tests` (Python 3.12.3) | **pass** (9m27s) |
| CI `mobile-typecheck` | **pass** |
| CI `maestro-testid-lint` | **pass** |
| Mobile diff vs main | **empty** — zero mobile files; no EAS/TestFlight build cut or needed |
| Simulator gate | **`FTF_SKIP_SIM_GATE=1`** — the standing D-056 posture. Evidence run instead: the full suite above + 30+ named sabotages RED-then-restored + CI. No simulator exists to run; this is the documented replacement, not a waiver of evidence. |

**Post-deploy verification:** polled `GET /api/feature-flags` on Render — `trade.negmem` moved **ABSENT → false**, which is itself the proof the new build is live (the old build did not know the key). Deployed state: flag **false**, `config/negmem_leagues.json` **empty**, `MODEL_A_PROFILE` pins `negmem_strength = 0.0`. **The ON-condition is BOTH the flag and the allowlist, so nothing generates differently for anyone.**

**Owed, unchanged by the ship:** the [TestFlight checklist](../docs/plans/negative-results-memory/testflight-checklist.md) is **UNRUN** — the feature has structural evidence only and must not be described as validated.

## 2026-08-22 — Negative-results memory v1 (leaf · registration · four seams · runner forwarding · readout pack) — full gates, FLAG DARK + ALLOWLIST EMPTY, NOT MERGED, on `claude/vigilant-spence-8583f5`

**Branch:** `claude/vigilant-spence-8583f5`, cut from `origin/main`. Not pushed, not merged.
Full gates — the operator did **not** declare express, and the change is outside the express
lane by the bright-line rule anyway (new flag surface, six `model_config` keys, a new
`features_json` key).
Spec: [LLD](../docs/plans/negative-results-memory/LLD.md) §10 (the 27-test N-plan) ·
scope [§6-RULINGS](../docs/plans/negative-results-memory/scope.md) ·
[ADR-015](../docs/adr/adr-015-negmem-soft-prior-not-fourth-filter.md) · [D-147](DECISIONS.md).

**Flag `trade.negmem` = false AND `config/negmem_leagues.json` = `[]`.** The ON-condition is
both, so nothing in this entry is runtime evidence of the feature working — it is evidence that
the feature is correctly inert and internally correct.

| Gate | Result |
|---|---|
| `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest backend/tests -q` | **4025 passed, 1 skipped, 0 failed** (345 s). Wave-2 tip baseline on this tree: **4016 passed, 1 skipped**. The +9 are this wave's additions (5 through-the-runner + 4 pack-SQL); nothing removed, nothing newly skipped. Local interpreter is **3.14.4**; CI is 3.12.3 — check CI before attributing any red to this branch (the standing version-skew caveat) |
| `bash mobile/scripts/testid-lint.sh` | **testid-lint OK**. `git diff --stat -- mobile/` is **empty** — zero mobile files touched on the whole branch, so the mobile CI jobs are byte-identical to `origin/main`'s |
| `cd mobile && tsc --noEmit` · `check-*.js` | not run in this worktree (no `node_modules`); moot per the line above |
| Knob-inventory guard (`test_no_generation_knob_was_added_without_an_arm_a_decision`) + `test_model_a_profile_only_names_real_knobs` | green with all six `negmem_*` keys in `_PINNED_KNOBS` + disposition sentences, and `MODEL_A_PROFILE`'s `negmem_strength = 0.0` naming a real knob |
| Arm-A golden | **UNMOVED on first run, no recapture** (wave 2). The profile pin changes `snapshot_config` output and not deck bytes — which is the claim, asserted directly in `test_n7_serving_golden_strength0_is_stamp_inclusive_identity` |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence is this entry |

**Negmem test totals: 128** — `test_negmem.py` **87** (the leaf: admission closed list, undo
replay, decay/shrinkage worked examples incl. the five OQ-4b threshold assertions, MIN combine,
`effective_mult` invariants, netting/retraction/revive, determinism + immutability, M2 E-B
parity + feed guard, degraded taxonomy, identity hygiene, horizon/epoch boundaries, SQL
dialect, leaf-import contract, readout format) and `test_negmem_seams.py` **41** (the four
seams, the stamp trichotomy, the two goldens, T1, the relaxed pass, arm A, and this wave's
runner half).

**Sabotage discipline, by wave.** `PYTHONDONTWRITEBYTECODE=1` plus a `backend/__pycache__`
clear between every cycle — stale `.pyc` gave wave 1 a false GREEN, and that is the reason the
discipline is written down rather than assumed.

- **B1 (leaf):** 26/26 named sabotages RED-then-restored; LLD worked examples reproduced exact.
  One substitution recorded in-code: N-5's named sabotage is unreachable because the
  strength-0 short-circuit precedes the upper clamp, so an equivalent was used.
- **B2 (registration):** no behavioural sabotage — the inventory tests ARE the alarm, and they
  fail by name. Values in `_DEFAULT_CFG` and `_MODEL_CONFIG_DEFAULTS` verified identical.
- **B3 (seams):** 6 sabotage families RED-then-restored across the four seams and the stamp.
- **This wave (runner + pack):** 4 cycles, each RED then restored:
  1. delete `negmem_map = _nm` from `gen_v2_cards` → `test_runner_gen_v2_cards_forwards_the_map_and_the_m2_feed`,
     `..._carry_negmem_influence_to_arm_c` and `test_runner_bakeoff_job_carries_negmem_into_arm_c_and_arm_fit` RED;
  2. delete the `acceptance_stats` splat alone → the forwarding test RED, the rest green (the
     asymmetry is separable, which is the point of testing both);
  3. delete `negmem_map = kwargs.get("negmem")` from `gen_fit_cards` → the two fit runner tests
     + the bake-off test RED;
  4. paste `json_extract(...)` into `negmem-gr4-joint.sql`'s executable SQL → the pack
     banned-token scan RED.

**What the through-the-runner tests exist for.** `bakeoff_runner.gen_v2_cards` / `gen_fit_cards`
are the ONLY callers of their generators inside a bake-off job. Every pre-existing seam test
calls those generators directly, so a runner that dropped the forwarding would have left all 33
of them green while arms C and fit ran negmem-blind. Sabotage 1 and 3 above are the proof that
gap was real. The end-to-end test assembles the fan-out exactly as `server._run_trade_job` does
(one map, splatted into every arm's lambda) over the direct-engine world rather than the
bake-off harness world — the harness's opponents are unranked, so arms C and fit legitimately
emit zero cards there and the assertion would have been vacuous.

**Pack SQL is executed, not just scanned.** Both shipped files run against the seeded in-memory
SQLite engine with real binds, so a renamed column fails here rather than in the operator's
hands; the banned-token scan runs over the **executable** half (comments stripped) because both
files document their Postgres-only variant in a comment, per the `bakeoff_readout.sql`
convention. Comments are stripped before binding too — SQLAlchemy's `text()` harvests `:name`
binds out of comment prose, and both files name their binds there.

**Runtime evidence: NONE, and that is the honest state.** The
[TestFlight checklist](../docs/plans/negative-results-memory/testflight-checklist.md) is written
and **UNRUN**; no deck has ever been generated with this flag on for a real league. Its step 0
(the before-readout) must run before the flip or the baseline is unrecoverable.

---

## 2026-08-21c — League-surface pick-value alignment (Q-026 closed) — full gates, NOT PUSHED, on `feat/league-pick-value-alignment`

**Branch:** `feat/league-pick-value-alignment`, cut from `origin/main` @ `f01ac9f` (which contains PR #167 `3192d13`, the per-slot pricing ship this follows). Not pushed, not merged.
**`origin/main` advanced mid-build to `5472e70` (PR #168, negmem) and was MERGED IN**; every gate below was then re-run on the merged tree. That merge also forced a **D-id renumber: this ship's decision is D-148, not D-147** — PR #168 took D-147 while this branch was building. G-048, again, in the same week it was last logged.
Full gates — the operator did **not** declare express. Operator ruling: *"I want the league values to reflect the same pick values."*
Scope + code-walk + operator checklist: [docs/plans/league-pick-value-alignment/scope.md](../docs/plans/league-pick-value-alignment/scope.md) · ship-time entries **drafted, not applied**: [decisions-draft.md](../docs/plans/league-pick-value-alignment/decisions-draft.md) (D-148, Q-026 closure, new Q-027).

**No schema change, no flag change, no client change.** `git diff --name-only origin/main -- mobile web extension` = **zero files**.

**GOLDEN SET FIRST, IN ISOLATION, TWICE — the standing discipline, honoured.**

| when | files | result |
|---|---|---|
| before any source edit | `test_bakeoff_arm_a_golden` · `test_engine_quality_golden` · `test_fairness_gate_golden` · `test_rnk_elo_golden` | **29 passed** |
| after the source change, before any fixture was touched | same four | **29 passed, ZERO edits** |
| again after merging `origin/main` `5472e70` (which itself edited `test_bakeoff_arm_a_golden.py`) | same four | **29 passed, ZERO edits** |

Arm A's structural immunity (it never constructs a `draft_picks` row, so it never reaches `priced_pool_value`) was **verified, not assumed** — that is what the second isolated run is for. No tolerance widened, no golden fixture touched.

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` (pre-merge, base `f01ac9f`) | **3986 passed, 1 skipped, 0 failed** (331 s) against a measured baseline of **3969 passed, 1 skipped** (305 s) on the same tree at `f01ac9f` |
| `python3 -m pytest backend/tests -q` (**post-merge, base `5472e70` — the number that counts**) | **4114 passed, 1 skipped, 0 failed** (287 s). `origin/main` @ `5472e70` records **4097 passed, 1 skipped** in PR #168's own entry above. Delta **+17**, reconciling exactly on both baselines: **+5** from `test_league_picks_tier.py` (7 → 12) and **+12** from the new `test_league_pick_value_alignment.py`. Nothing removed, nothing newly skipped |
| `bash mobile/scripts/testid-lint.sh` | **green** (`testid-lint OK`) |
| `cd mobile && npx tsc --noEmit` · `check-*.js` | **NOT RUN in this worktree** — no `mobile/node_modules`, and `npm ci` needs network which is unavailable here. Evidence in its place: **zero mobile/web/extension diffs** against an `origin/main` whose CI is green. Asserted unaffected, **not observed — CI on the pushed sha must confirm** |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = everything in this entry |

**MEASURED BEFORE/AFTER — FFV3-shaped fixture** (12-team linear board, 2026 rounds 1–4 × 12 slots + 2027/2028 firsts and seconds = 96 picks, 1QB, pinned DP snapshot `dp_values_picks_2026-08-06.csv`).

Per-pick, 2026 round 1 — before → after (badge):

| 1.01 | 1.05 | 1.08 | 1.12 |
|---|---|---|---|
| 2117.0 → **4867.1** (`first_1`→`firsts_2`) | 2117.0 → 2343.2 (unmoved) | 2117.0 → 1435.5 (`first_1`→`second`) | 2117.0 → **820.8** (`first_1`→`second`) |

**Per-roster team-value pick totals** — monotonic by draft slot, which is the shape that proves the slot is reaching the price:

| roster | 1 | 2 | 3 | 6 | 9 | 12 | league |
|---|---:|---:|---:|---:|---:|---:|---:|
| before | 8590.4 | 8590.4 | 8590.4 | 8590.4 | 8590.4 | 8590.4 | 103084.8 |
| after | 9653.9 | 8722.1 | 7965.4 | 6439.9 | 5598.8 | 5124.6 | 80298.3 |
| Δ | **+12.4 %** | +1.5 % | −7.3 % | −25.0 % | −34.8 % | **−40.3 %** | **−22.1 %** |

**Badge movement: 50 of 96 picks (52 %).** 6 of the twelve 2026 firsts, 8 of the seconds, all 12 thirds, all 12 fourths, and all 12 **2028 firsts** (`first_1` → `second`). 2027 picks and the 2026 1.02–1.07 keep their badge. Bands untouched (`tier_config.json` + five client mirrors byte-identical); the inverse is still `value_to_elo` (D-088).

**Read the league row honestly: aggregate DEFLATION, not just dispersion.** The dispersion story holds within 2026 round 1; across a roster the round curve dominates because DP decays future firsts hard (2028 1st 2117.0 → 1263.0) where D-079's ladder held them flat. Those are the engine's prices as of `3192d13` — this ship stops one screen disagreeing with them, it does not create them.

**ADR-011 TIME-SERIES BOUNDARY AT THIS MERGE — named, and proven to be a boundary rather than a rewrite.** `roster_history.team_value` / `team_value_picks` are fed by `_power_picks_by_owner`, so the series steps here and is **not comparable across 2026-08-21** for any pick-holding team; the Wrapped/recap and trends consumers read across it. Nothing historical is recomputed, verified by `test_history_snapshot_reads_the_same_priced_picks_as_power_rankings`, which asserts `roster_history.py` contains no `priced_pool_value`, no `_priced_pick_value` and no `pick_pool_value` call at all — the writer is HANDED its prices and has no pricing path to re-run.

**Structural guard, sabotage-verified three ways** (`test_league_pick_value_alignment.py`, bidirectional AST walk over `server.py`). Each sabotage applied, suite run, reverted:

| # | sabotage | caught by |
|---|---|---|
| 1 | `_power_picks_by_owner` regresses to `p.get("pool_value")` — literally the pre-D-148 line | 4 tests, incl. both AST guards |
| 2 | a surface calls `priced_pool_value` directly with the **identical expression** (behaviourally a no-op) | 3 tests — proving the guard is structural, not behavioural |
| 3 | `_league_slot_order` resolved once per PICK instead of once per league | `test_power_rankings_resolves_the_draft_order_once_per_league` (48 picks, 12 rosters, asserts exactly 1 lookup) |

**Three fixture files re-derived from the pricing functions with literal inputs; no tolerance widened.**

- `test_league_picks_tier.py` (7 → 12): every badge literal re-derived. **All three original sabotages re-verified against the PRICED values** (S1 raw scale, S1b `seed_elo_for_value` inverse, S2 platform-only) — each still produces a different tier on ≥2 rows — and a fourth added (S3: leaving the stored column on the wire). The null-tier contract was re-anchored: a stored NULL now prices from the market like the engine already did, and null is reserved for "every step of the waterfall is empty".
- `test_power_rankings.py` (3 tests): **one trap had to be reshaped, not renumbered.** D-084's "u_a's one 3rd separates the literal from the dollar label scale" collapsed under the new prices — 2 seconds + 1 third is 1130.3 dollars, which rounds to ≈0.5 firsts, the same answer the literal count gives. Re-derived to **three** thirds (1654.9 ⇒ "≈1 firsts" vs literal "≈0.5 firsts"). Two thirds would not have worked (1392.6 still rounds to ≈0.5); the fixture note says so.
- `test_trade_evaluate.py` (1 test): the evener pick moved 2027 → 2028 so its priced value (1263.0) lands where the ordering assertion needs it, and the row now STORES 1005.3 so "priced, not stored" is provable rather than incidental.

**A real defect fixed in passing.** `_roster_eveners` (S4) priced sweetener candidates off the stored ladder while the `gap` they were sized against came from priced picks — both call sites are inside `_trade_evaluate_impl`. A one-tap "add their 2026 1.01" was offered as closing a 2117.0 hole the same response charged 4867.1 for.

**Two residues raised rather than buried, both needing an operator call:** pick-SHARE ratios (`_user_pick_share` + the trade job's opponent shares) stay on the legacy `pick_value` column, so the contend/rebuild classifier still weights every first alike (scope §6 waiver 3); and the Draft Room board vs engine mismatch in non-12-team leagues — a 10-team league's last first displays as 820.8 and prices as 1069.8 — pinned by a test and raised as **Q-027** (scope §6 waiver 2). 12-team leagues agree exactly, asserted slot by slot.

---
## 2026-08-21b — Gap auto-sweetener extended to bake-off arm C (`trade_gen_v2`) — full gates, NOT PUSHED, NOT MERGED, on `feat/gap-sweetener-arm-c`

**Branch:** `feat/gap-sweetener-arm-c`, **stacked on `fix/package-benchmark-sweetener` @ `480cce0`** — NOT cut from `origin/main`. `close_value_gap` does not exist on `origin/main` at all, so this work is unbuildable there; the operator chose the stacked branch over waiting for the Monday window (2026-08-21). **Merge order is load-bearing: the parent lands first, then this.**
Full gates ran — operator did **not** declare express.
Scope + code-walk: [docs/plans/package-benchmark-sweetener/scope-arm-c.md](../docs/plans/package-benchmark-sweetener/scope-arm-c.md) ·
ship-time entries **drafted, not applied**: [decisions-draft-arm-c.md](../docs/plans/package-benchmark-sweetener/decisions-draft-arm-c.md).

**No feature flag, no new knob.** Arm C reuses the parent's `sweetener_gap_threshold` (1539.0); ≤ 0 remains the deploy-free rollback and arm A's pin.

**Why it was needed, measured.** Arm C inherited the parent's trade-wide package benchmark — which WIDENS absolute consensus gaps — through `_consensus_packages` at card-build time, but did not run the closer. Its deck is card-for-card identical across the parent (the parent moves its *prices*, not its *selections*), so the entire rise is mispricing. Reproduced on this tree: **12-team 3/22 over the line (13.6 %), 16-team 2/19 (10.5 %)**, `sweetened: 0` in both, against 0–5.3 % for every other served arm.
## 2026-08-21b — Receipts (graded suggestion track record) built dark — full gates, NOT PUSHED, NOT MERGED, on `feat/receipts`

**Branch:** `feat/receipts` (worktree `agent-a60b48a57928d5895`), cut from `origin/main` at `eb9c1de`, then `plan/receipts` merged in (that merge IS the shared taxonomy's repo landing) and `origin/main` re-merged at `d42872f` after PRs #161/#162 landed mid-build. **Not pushed, not merged.**
Full gates — the operator did not declare express, and the change is outside the express lane by the bright-line rule anyway (2 new tables, 3 new routes, 2 new flags, 5 new knobs, 3 new analytics events).
Spec: [docs/plans/receipts/](../docs/plans/receipts/) (dual-agent reviewed, 3 adversarial rounds) · code-walk: [code-walk.md](../docs/plans/receipts/code-walk.md) · operator checklist: [testflight-checklist.md](../docs/plans/receipts/testflight-checklist.md).

**Everything ships dark.** `receipts.grading` and `receipts.screen` both default false; env kill switch `FTF_RECEIPTS_GRADE=0`.

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3795 passed, 1 skipped, 0 failed** (340 s). Baseline measured on this same tree at the parent tip `480cce0`: **3786 passed, 1 skipped**. The +9 are the new `test_gap_sweetener_arm_c.py`; no other delta, nothing removed, nothing newly skipped |
| `cd mobile && tsc --noEmit` · `check-*.js` · `testid-lint.sh` | **not run in this worktree** (no `node_modules`); **zero mobile files touched** — `git diff --stat <parent> -- mobile/` is empty, so the mobile CI jobs are byte-identical to the parent's |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = everything in this entry |

**Verify-by-revert on all nine new tests, three trees.** With `backend/trade_gen_v2.py` reverted to the parent, **8 of 9 go red**; with the *contained-pools* variant (equalizer drawn from `give_pool`/`extras` rather than the semantic universes) exactly **1 goes red** — `test_arm_c_equalizer_reaches_past_the_budget_slice`, the test that pins the §0b decision. Shipped tree: 9/9 green. The ninth test, `test_arm_c_kill_value_is_a_byte_identical_no_op`, passes on the parent **by design** — it asserts the threshold-0 deck IS the pre-sweetener deck, so a green there is the claim, not a gap in coverage. It pins the organic card's exact literals (`["G"] → ["R"]`, 10000.0 / 11600.0, band 0.862, gap 1600.0) so drift in the disabled path cannot be silently rebaselined.

**Two defects found by reading arm C rather than copying the other three hooks** (both would have shipped had this been a copy-paste; details in scope-arm-c.md §0):

1. **Placement.** The gap is only computable at the card-build call to `_consensus_packages`, but ten derived fields — `_dedup_batch` keys, `_meso_variants`, `_rationale`, `classify_package_shape` (whose `"consolidation"` label is literally `len(ids) == 1`), `card.health`'s seven entries, `mismatch_score`, `fairness_score`, `composite_score` and the Stage 6/7 exposure + tier ranking — are computed earlier from the `_Candidate`. Sweetening at the obvious site leaves every one of them describing the unsweetened trade: arm C's much larger analogue of the v3 stale-`fit_premium` defect. Fixed by hooking inside `_pair_survivors` and rebuilding the whole `_Candidate`.
2. **`past_decision_keys` was re-checkable and unchecked.** A sweetened combo is a different trade with a different key; the enumeration only ever tested the unsweetened shape. Without the re-test the pass could ship a combo the user had already rejected. Pinned by `test_arm_c_sweetened_combo_respects_past_decisions`.

**Pool containment — the round-2 lesson applied, and where it stops.** Arm C prunes in two layers and only one is semantic. `user_assets` (on BOTH boards, not untouchable) and `extras_all` (divergence-positive, not not-interested) encode real rules and are the equalizer universe. `[:gen2_give_pool]` / `[:gen2_recv_extra_pool]` are enumeration budget — documented as bounding "SEARCH BREADTH, never output length" alongside `gen2_centerpiece_top_k` — and the sweetener deliberately reaches past them. **Measured justification:** wired to the budget slices the pass fires but the deck metric does not move (3/22 and 2/19 unchanged), because **78 of 112 and 63 of 86 rejected equalizers are undershoot** — nothing in the slice is big enough — against only 8 and 13 killed by arm C's own gates. Reaching the semantic universe moves the 12-team fixture **3 → 1 over the line (13.6 % → 4.6 %), p90 1665 → 951**; the 16-team stays at 2 but its mean gap falls 551 → 488. Operator chose the widened reading with the numbers in front of them. This is NOT the `49c1d76` defect relaxed: that one crossed a semantic line (a #174 pinned "trade away G" job smuggling in an unpinned player — a broken user instruction).

**Golden disposition — re-verified deliberately, and they did NOT move. No re-capture, no kill-value pin.** The brief expected the gen2 goldens to move. Instrumented rather than assumed, with a probe counting arm-C sweetener invocations per file:

| File | `generate_league_suggestions` calls | arm-C cards | sweetener fired | verdict |
|---|---|---|---|---|
| `test_bakeoff_arm_a_golden.py` | 0 | 0 | 0 | never enters arm C — arm A is the v2/consensus path, and pins the knob at 0 besides |
| `test_engine_quality_golden.py` · `test_engine_quality.py` | 0 | 0 | 0 | never enters arm C |
| `test_bakeoff_runner.py` · `test_bakeoff_composition.py` · `test_bakeoff_challenger.py` | 0 | 0 | 0 | never enters arm C |
| `test_bakeoff_serving.py` | 10 | **0 cards** | 0 | enters, but the fixture yields empty arm-C decks |
| `test_trade_gen_v2.py` (arm C's own suite, not a golden) | 36 | 57 | **10 fired, 10 closed** | all 40 assertions still green |

Confirmed by forcing the gap line to **1.0** — a threshold every nonzero gap exceeds: still **0 invocations** in every golden file. So the goldens are stable because arm C's generator is not reached in them, not because the threshold happens to sit above their gaps. There is no baseline to re-capture and nothing to pin.

**Where the sweetener does real work, proven by the same probe on three trees** — `test_trade_gen_v2.py`, all 40 pre-existing tests green throughout:

| Tree | cards | max gap | over 1539 |
|---|---|---|---|
| parent (`480cce0`) | 58 | 1861.5 | **2** |
| contained pools | 57 | 1234.2 | 0 |
| shipped (widened) | 57 | 1234.2 | 0 |

**Known effect, deliberately accepted — for arm C the pass CAN shrink the deck by one, unlike the other three paths.** D-143 states the sweetener "narrows gaps, never shrinks the deck". That holds where it was written, but arm C is the only path with `_dedup_batch` downstream, and its bucket key is `(opponent, centerpiece, "{len(give)}x{len(recv)}")`. Sweetening changes a card's SHAPE, so it can land in an occupied bucket and the lower-ranked occupant is dropped. Diffed card-for-card on `test_trade_gen_v2.py` deck #11: parent held `u_rb1 → o_wr1` (gap 1671, over) and `u_rb2+u_wr1 → o_wr1` (gap 1861, over); shipped sweetens the first into a 2×1 (`+u_wr1`, gap 1234) which collides with the second's bucket and evicts it. Net 3 cards → 2, and **both over-the-line cards are gone**. Acceptable: the bucket rule exists precisely to stop two near-duplicate shapes serving together, and arm C emits its full survivor set with no truncation, so the loss is one near-dup rather than a suppressed idea.

**Harness determinism — see [G-053](GOTCHAS.md).** The first before/after run showed arm D moving, which cannot happen from a `trade_gen_v2` edit. Two consecutive runs on the identical tree reproduced the flip: the harness is seed-dependent. Every number in this entry was produced with `PYTHONHASHSEED=0` on both sides, verified byte-identical across two seeded runs. This retroactively qualifies single-card deltas in 2026-08-21a, which was measured unseeded.

**Not covered / owed at ship.** No runtime evidence: arm C serves quota-capped bake-off slots and rides the parent's [testflight-checklist.md](../docs/plans/package-benchmark-sweetener/testflight-checklist.md) rather than adding a second manual pass. Deck-level effects above are fixture-only and DIRECTIONAL — synthetic boards, `max_per_opponent=5` (the engine default is None, so production decks are larger than the harness's).
| `python3 -m pytest backend/tests -q` | **3951 passed, 1 skipped, 0 failed** (301 s), measured on the merged tree. Exactly **54** of those are the new `backend/tests/test_receipts_grading.py`, so the merged tree's pre-existing count is 3897 — no existing test was changed, removed, or newly skipped, and the only test file this branch adds is the receipts one. (The brief's 3651 baseline predates PRs #161/#162, which landed mid-build and brought their own suites.) |
| `cd mobile && npx tsc --noEmit` | **green** (`npm ci` first — the worktree had no `node_modules`) |
| `node tests/check-receipts.js` (`npm run test:receipts`) | **12 passed, 0 failed** |
| `bash mobile/scripts/testid-lint.sh` | **testid-lint OK** |
| Knob-inventory guard | green and **correctly silent**: the five `receipts_*` knobs are deliberately NOT in `trade_service._DEFAULT_CFG`, so `_PINNED_KNOBS` does not apply. A test asserts they never enter it, and each has an arm-A disposition sentence in `docs/plans/three-model-bakeoff/scope-phase2.md` |

**Sabotage discipline — 21 named sabotages, all confirmed RED then green on revert.**
Backend (12): edge sign flip · D-8 floor imputation dropped · serve anchor allowing a post-serve snapshot · pick weights read live from `GENERIC_PICK_SEEDS` · Wilson centre shift dropped · valuation leaking from the frozen card · ghosts entering the queue · queue ignoring existing grades · min-n gate removed · an UPDATE path on `receipts_grades` · pre-telemetry rows queued · dedup keeping the latest serve.
Mobile (9): FeedbackFAB removed from one render branch · FAB given tab-stack props · a second per-window fetch · worst call dropped while best call kept · route wrapped in the flag · entry point ungated · ledger state deleted · disclosure not rendered · give-side delta dropped.

**Six guards were BLIND on the first pass and were strengthened rather than logged as passing** — this is the part worth reading:
- **T-4 (deploy invariance)** compared two rows that BOTH became `pick_majority` under the sabotage, so a field-by-field equality check passed while proving nothing. Now pins `status == "graded"` on both sides, plus a direct assertion that the frozen weights survive `GENERIC_PICK_SEEDS` being emptied entirely.
- **T-1 (pre-telemetry)** ran against an empty cohort, so the run short-circuited and the test passed because *nothing happened at all*. Now seeds a gradeable neighbour and asserts the run did real work.
- **FAB check** passed with one of three render branches stripped — the error branch, i.e. the user with the most to report and no way to report it. Now counts mounts against render branches and prop-checks every mount.
- **Unconditional-route check** searched for the flag NAME, so `{true ? <Stack.Screen…}` slipped through. Now inspects the token before the tag.
- **Both-sides check** matched `give_delta` surviving inside a style callback after the rendered number was deleted. Now asserts the rendered value.

**Two real defects the discipline caught (not test bugs).**
1. `_dedup_earliest` was keeping the LATEST serve instead of the earliest — masked by a **stale `.pyc`**: the sabotage swapped `<`→`>`, identical byte length inside one mtime-second, so Python reused cached bytecode and `inspect.getsource` disagreed with what was actually running. Sabotage runs now clear bytecode between steps. **Worth remembering: a same-length edit inside one second is invisible to Python's import cache.**
2. The daily-tick guard serialized `receipts_grade_started` unconditionally, changing the flag-off tick payload — caught by `test_deck_replenishment`'s byte-identical assertion, fixed, and now pinned from the receipts side too.

**Backfill exercised end to end** against a synthetic fixture DB (420 impressions across 3 leagues / 2 formats / 3 users, 8 640 snapshot rows, a deliberate 2-day supply gap, 23 ghosts, 49 pre-telemetry rows): 565 resolvable → **542 graded + 23 ungradeable = 565 exactly**, terminating on two consecutive zero-work runs; re-run wrote 0; ledger showed 6 complete start/end pairs and 0 unmatched starts; **0 ghost rows graded**; 47 floor-imputed (D-8) rows retained. Win/loss landed at 283/259 on drift-only synthetic data — near the 50% null, which is what an unbiased grader should produce on random walks. `effective_window` for 28d: min 27, max 30, median 28.
The **real dev DB dry-run reports 0** and that is correct, not a failure: `data/trade_finder.db` holds zero `deck_impressions` rows, so there is nothing local to grade. The prod cohort is the P0 read, still outstanding.

**Code-ship boundary, examined rather than assumed (coordinator note).** `d42872f` (2026-08-22, package pricing + sweetener) changes package-value SEMANTICS in the engine. It does **not** affect grades: the grader reads only `player_value_history` consensus snapshots and never computes a package value, so no grade moves across that boundary — HL-4 recalibration immunity holds by construction. What it *does* affect is attribution: impressions served before and after `d42872f` come from different engine behaviour, and that is already carried by the `policy_version` slice key stamped on every impression and copied onto every grade row. No action; recorded so it is not re-examined.

**Not run:** anything on a device. Receipts has never rendered on real hardware — that is the operator's checklist above, and it is the only runtime evidence this feature will get.

---
## 2026-08-21a — Package-benchmark fix + gap auto-sweetener + ghost default, round-2 reviewed — full gates, NOT PUSHED, NOT MERGED, on `fix/package-benchmark-sweetener`

**Branch:** `fix/package-benchmark-sweetener` (worktree `agent-a8f35b1a442cb2147`), cut from `origin/main` at `eb9c1de`. **Not pushed, not merged** — the merge is the operator's Monday-boundary call (change-control rule, trade-engine-accuracy PLAN Phase 0.4).
Full gates ran — operator did **not** declare express, and the change is outside the express lane by the bright-line rule anyway (it adds three `model_config` keys and changes a shipped default).
Scope: [docs/plans/package-benchmark-sweetener/scope.md](../docs/plans/package-benchmark-sweetener/scope.md) (round-2 review in §6) ·
code-walk: [code-walk.md](../docs/plans/package-benchmark-sweetener/code-walk.md) ·
checklist: [testflight-checklist.md](../docs/plans/package-benchmark-sweetener/testflight-checklist.md) ·
ship-time entries **drafted, not applied**: [decisions-draft.md](../docs/plans/package-benchmark-sweetener/decisions-draft.md).

**No feature flag.** Knob-gated: `package_bench_trade_wide` 1.0, `package_floor_cross` 0.40, `sweetener_gap_threshold` 1539.0 — each ≤ 0 is a deploy-free rollback. Changed default: `ghost_holdout_one_in` 10 → 0.

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3786 passed, 1 skipped, 0 failed** (271 s). Baseline on the inherited tip `0e04d30`, measured on this same tree: **3782 passed, 1 skipped**. The +4 are the round-2 regression tests in `test_gap_sweetener.py`; no other delta, nothing removed, nothing skipped that was not already skipped |
| `cd mobile && tsc --noEmit` · `check-*.js` · `testid-lint.sh` | **not run in this worktree** (no `node_modules`); **zero mobile files touched** on the whole branch — `git diff --stat origin/main -- mobile/` is empty, so the mobile CI jobs are byte-identical to `origin/main`'s green |
| Knob-inventory guard (`test_no_generation_knob_was_added_without_an_arm_a_decision`) | green with all three new keys in `_PINNED_KNOBS` + disposition sentences in `docs/plans/three-model-bakeoff/scope-phase2.md` |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = everything in this entry |

**Round-2 adversarial review of the inherited commits — two real defects, both reproduced before they were fixed.** The operator re-delegated the sweetener for a hostile re-read. `72ecd51` (benchmark fix) came back **clean**: `v_max` verified trade-wide at all 14 constructions in `backend/`, the carve-outs verified surgical, kill-value identity verified test-proved rather than asserted. `0e04d30` (sweetener) shipped two defects, fixed in `49c1d76`:

1. **The consensus generator's pool pruning was bypassed.** `_generate_consensus_for_pair` prunes `give_pool` to the #174 pinned give players and `recv_pool` to the FB-47 pinned acquire targets / need positions, rather than gating per combo. `close_value_gap` drew from the raw rosters, so a `pinned_give_players=["G"]` job emitted `[G, X1] → [R]` with `X1` never offered up, and a WR-only acquire job could hand back an off-need RB. Fixed with optional `give_candidates`/`recv_candidates` (rosters still drive the 3.2 feasibility counts). v2 and v3 pass nothing — their pinned/position rules are per-combo and monotone under addition, verified callsite by callsite.
2. **v3 shipped a stale `fit_premium`.** `fit_premium_1for1` can only price a 1×1; the gap pass rewrote the card to a 1-for-2 and left the badge on. The v2 divergence path already nulled its `fit_paid`; v3 now does too.

**Verify-by-revert on all four new tests:** with `backend/trade_service.py` + `backend/trade_optimizer.py` stashed back to `0e04d30`, `test_helper_candidate_pools_narrow_the_equalizer_universe`, `test_consensus_sweetener_never_adds_an_unpinned_give_player`, `test_consensus_sweetener_respects_the_acquire_position_filter` and `test_v3_gap_sweetener_clears_the_stale_fit_premium` all go **red**; restored, all green. Each also carries its own non-vacuity half (the same fixture without the pin IS sweetened; the knob-off half proves the v3 organic winner really is a fit-premium 1-for-1 carrying a 1600 gap).

**Sabotage check on the extraction the predecessor claimed was byte-identical — it holds, but NOT where the commit said.** `0e04d30` pulled the v2 divergence surplus/composite math out of `_consider` into `_pair_surpluses` / `_composite_v2` and asserted the extraction was pinned by "the full suite plus the arm-A/challenger/engine-quality goldens". Sabotage: `u_max = max(uvals_give + uvals_recv)` → `max(uvals_give)` inside `_pair_surpluses`, `__pycache__` cleared. **Those three golden files all stayed GREEN** — they run with `trade_engine.v3` on, so `_generate_for_pair_v2` is never entered. The full suite DID catch it, at **`test_trade_optimizer.py::test_v3_top_card_matches_v2_on_1for1_fixture`** and **`test_trade_tier2.py::test_outlook_rebuilder_outranks_championship`** (2 failed, 3784 passed). Restored with `git checkout --`, proved restored with `git diff --quiet`, re-run green. So the claim is TRUE and the extraction is genuinely guarded — the commit message just named the wrong guards, which would have sent the next person debugging the wrong file.

**W0-style deck-size / gap-distribution measurement — `origin/main` `eb9c1de` vs this branch tip.** Fixture-only. Two constructed leagues (12-team 1QB 26-man, 16-team SF 21-man) drafted from `backend/tests/fixtures/player_pool_2026.json`, 3 owned-pick pseudo-assets per team, hash-offset synthetic boards, `fairness_threshold` 0.85, `max_per_opponent` 5, `_cfg` at code defaults, flags from `config/features.json`. Harness committed for reproducibility: [`measure_gap_distribution.py`](../docs/plans/package-benchmark-sweetener/measure_gap_distribution.py). The "before" side was produced by `git archive origin/main` into a scratch tree and running the same file there. **One deviation from the fit-challenger W0 recipe, and it is load-bearing:** W0's flat rank-ladder Elo seeds (1750 → 1250) compress the board into 286..3490 value units, where a 1539 gap is arithmetically almost unreachable — the measurement reads zero everywhere regardless of the engine. Seeds here come from the pool's own DynastyProcess values rescaled so the #1 asset lands on FTF's real top-asset price (~7737), reproducing the production value CURVE.

| League | Path | Arm | main cards | branch cards | Δ | main >1539 | branch >1539 | sweetened | main mean gap | branch mean gap |
|---|---|---|---|---|---|---|---|---|---|---|
| 12t 1QB | v2 only | B `current` | 14 | 13 | −1 (−7%) | 0 (0.0%) | 0 (0.0%) | 1 | 105.4 | 112.2 |
| 12t 1QB | v2 only | B, sweetener OFF | — | 13 | — | — | 1 (7.7%) | 0 | — | 211.5 |
| 12t 1QB | v2 only | D `challenger` | 14 | 13 | −1 (−7%) | 0 (0.0%) | 0 (0.0%) | 1 | 105.4 | 112.2 |
| 12t 1QB | v2 only | C `gen_v2` | 22 | 22 | +0 | 0 (0.0%) | **3 (13.6%)** | 0 | 427.0 | 583.5 |
| 12t 1QB | v2 only | A `baseline` | 30 | 30 | +0 | 3 (10.0%) | 3 (10.0%) | 0 | 312.4 | **312.4** |
| 12t 1QB | v3 | B `current` | 19 | 16 | −3 (−16%) | 1 (5.3%) | 0 (0.0%) | 1 | 284.9 | 393.9 |
| 12t 1QB | v3 | B, sweetener OFF | — | 16 | — | — | 1 (6.2%) | 0 | — | 492.0 |
| 12t 1QB | v3 | D `challenger` | 20 | 16 | **−4 (−20%)** | 1 (5.0%) | 0 (0.0%) | 1 | 287.3 | 379.9 |
| 12t 1QB | v3 | A `baseline` | 30 | 30 | +0 | 3 (10.0%) | 3 (10.0%) | 0 | 448.3 | **448.3** |
| 16t SF | v2 only | B `current` | 16 | 17 | +1 (+6%) | 0 (0.0%) | 0 (0.0%) | 0 | 305.9 | 125.4 |
| 16t SF | v2 only | D `challenger` | 16 | 17 | +1 (+6%) | 0 (0.0%) | 0 (0.0%) | 0 | 305.9 | 125.4 |
| 16t SF | v2 only | C `gen_v2` | 19 | 19 | +0 | 1 (5.3%) | **2 (10.5%)** | 0 | 468.3 | 551.5 |
| 16t SF | v2 only | A `baseline` | 30 | 30 | +0 | 0 (0.0%) | 0 (0.0%) | 0 | 178.5 | **178.5** |
| 16t SF | v3 | B `current` | 19 | 19 | +0 | 0 (0.0%) | 1 (5.3%) | 1 | 291.4 | 470.2 |
| 16t SF | v3 | B, sweetener OFF | — | 19 | — | — | 2 (10.5%) | 0 | — | 495.1 |
| 16t SF | v3 | D `challenger` | 19 | 19 | +0 | 0 (0.0%) | 1 (5.3%) | 1 | 284.3 | 470.2 |
| 16t SF | v3 | A `baseline` | 30 | 30 | +0 | 3 (10.0%) | 3 (10.0%) | 0 | 560.7 | **560.7** |

**Four readings.**

- **Deck shrink — the number the operator accepted in advance:** **−3.9%** across the served arm roster (B + C + D, 178 → 171 cards); **−4.4%** for arm `current` alone (68 → 65). Worst single cell **−20%** (12-team 1QB, v3, arm D: 20 → 16). No cell lost more than 4 cards.
- **Arm A is byte-identical at `origin/main` and at this branch tip** — same 30 cards, same 9 over-the-line count, same p90 and mean gaps to 0.1, on every league × path. That is LIVE evidence for the pin-instead-of-recapture choice, on top of the unit test, and it is the strongest single result in this run.
- **The sweetener works where it fires, and it fires narrowly.** The branch-only "sweetener OFF" rows isolate it from the benchmark fix: arm `current` would carry 1 / 1 / 2 over-the-line cards on the three cells where it matters, and the pass takes those to 0 / 0 / 1 — 3 of 4 closed. It sweetens roughly **one card per deck**, not a third of it.
- **Arm C gets WORSE, and this is the finding to act on.** Arm C's deck is identical card-for-card (22 and 19 on both trees) — only the DISPLAYED values moved, because it inherits `package_value_v2` through `_consensus_packages` but does not run the sweetener. Its over-the-line share goes 0 → 13.6% and 5.3 → 10.5%. Across the served roster that alone lifts the combined over-the-line share from 1.7% to 4.1%. The arm-C follow-up named in scope.md is a **priority item**, not a nicety.

**What is NOT proven, and is owed.** (a) The manual TestFlight checklist — it needs a build containing this branch, which does not exist; no runtime evidence exists for these cards yet. (b) A prod-replay half against real league boards — needs prod read access, operator item, same gap the fit W0 run had. (c) Fixture boards are synthetic (rank-drafted rosters, hash-offset personal Elo), so the LEVELS above are directional; the main-vs-branch DELTAS are the result. (d) The fixture decks carry a far lower over-the-line share (0–5% on arm B) than the 15% the CHANGELOG measured on real served cards, so the sweetener's real-world firing rate is likely HIGHER than one card per deck — read it from the checklist's readout SQL before trusting the fixture rate.

**Six operator ratification items** are listed in [scope.md §6](../docs/plans/package-benchmark-sweetener/scope.md) — headline ones: the arm-A golden was pinned rather than re-captured, and the flag-off serving golden's parity-with-the-pre-bake-off-SHA claim died with its re-capture and is now a drift detector.

### Addendum 2026-08-21b — the PROD-REPLAY half, on real boards. Owed item (b) above is now CLOSED.

Read-only prod replay of league `1312140920132497408` ("Fantasy Football Version 3", `1qb_ppr`) — the
only league with 3+ boards — against **`origin/main` `eb9c1de`** (pinned by SHA and materialized with
`git archive`, because main moves) **vs this branch tip `480cce0`**. Nothing was pushed, merged,
flagged or written; no engine file was touched by this measurement. (A concurrent session committed `e59650c` to this branch mid-run; it is docs-only — `git diff 480cce0 e59650c -- backend/ config/` is empty — so these numbers still describe the current tip.)

**Method** — the arm-B audit's recipe ([docs/reviews/2026-08-19-armb-audit-claims-3-4.md](../docs/reviews/2026-08-19-armb-audit-claims-3-4.md) §7),
extended to the full serving inputs. Prod was read **once** into a local JSON fixture and both trees
then ran against those FROZEN inputs — no per-generation prod access. Connection posture copied from
`backend/tools/prod_analytics.py`: `DATABASE_URL_PROD` from the gitignored root `secrets.local.env`,
session-level `default_transaction_read_only=on` + `statement_timeout`, SELECT only, DSN never printed.

- Pool + consensus seed: `player_value_history` @ `2026-08-21` / `1qb_ppr` (644 rows) joined to `players`.
- Each member's board: their **real** `swipe_decisions` replayed through the **real**
  `RankingService.replay_from_db` (1808 / 1080 / 956 / 175 / 120 / 42 rows), `users.tier_overrides`
  restored into `_elo_overrides` (with `__OVERRIDE_AT__` stamps), then `get_rankings()`,
  `comparison_counts()` → `confidence`, `placement_bands()` → `placements`.
- Rosters from `league_members.roster_data`; outlooks + acquire/trade-away positions from
  `league_preferences`; `asset_preferences` as untouchable/target/not-interested sets; opponent
  outlooks and pick shares assembled as `_run_trade_job` does.
- Owned picks injected exactly as `server._inject_owned_picks` does (144 rows, `picks_pool_cap`, and
  `trade.slot_pricing`'s default `tier_ladder` mode ⇒ the stored `pool_value`), with `_pick_asset_elos`
  priming every Elo map — so a pick can be an equalizer, as it is in prod.
- Prod `model_config` (185 rows) into both modules' `_cfg`; each viewer's real `stud_tax_mode` pinned;
  flags from `config/features.json`; cards from the real `TradeService.generate_trades` at the **organic
  serving parameters** (`fairness_threshold` 0.75, `max_per_opponent` 5).
- **Both trees ran against ONE shared throwaway SQLite `DATABASE_URL`** so neither could read a
  different local `experiments` / `model_config` table (the branch worktree has a populated
  `data/trade_finder.db`; the archived main tree does not — that asymmetry was found and removed).
- 6 boarded viewers × 2 paths (v3 = the live posture, and v2-only) × arms A/B/C/D, plus a branch-only
  `sweetener_gap_threshold = 0` control that isolates the sweetener from the benchmark fix.
- **Determinism proved, not assumed:** the whole branch run was repeated and the two result files are
  byte-identical.

Harness committed (DB-free half): [`replay_prod_boards.py`](../docs/plans/package-benchmark-sweetener/replay_prod_boards.py).
The prod extractor is deliberately **not** committed — it holds a prod connection helper, the same
posture the arm-B audit took with its probe scripts.

| Slice | main cards | branch cards | Δ | main >1539 | branch >1539 | sweetened | main mean gap | branch mean gap |
|---|---|---|---|---|---|---|---|---|
| **Served arm roster (B+C+D, both paths)** | 434 | 427 | **−7 (−1.6%)** | 45 (10.4%) | 33 (7.7%) | 28 | 614.0 | 568.6 |
| arm B `current`, both paths | 186 | 185 | −1 (−0.5%) | 15 (8.1%) | 7 (3.8%) | 17 | 552.6 | 486.2 |
| **arm B, v3 path — the live posture** | 105 | 106 | **+1 (+1.0%)** | 7 (6.7%) | **3 (2.8%)** | 9 | 538.1 | 501.3 |
| arm B, v2-only path | 81 | 79 | −2 (−2.5%) | 8 (9.9%) | 4 (5.1%) | 8 | 571.3 | 466.1 |
| **arm A `baseline` (pin check)** | 376 | 376 | **+0** | 71 (18.9%) | 71 (18.9%) | 0 | **835.6** | **835.6** |
| arm C `gen_v2` (inherits the fix, no sweetener) | 51 | 51 | +0 | 15 (29.4%) | **19 (37.2%)** | 0 | 1173.7 | 1253.0 |
| arm D `challenger` | 197 | 191 | −6 (−3.0%) | 15 (7.6%) | 7 (3.7%) | 11 | 527.2 | 465.7 |

By basis, arm B, both paths: **divergence** 96 → 94 cards, over-line 13 (13.5%) → 7 (7.4%), 15 sweetened;
**consensus** 90 → 91 cards, over-line 2 (2.2%) → **0 (0.0%)**, 2 sweetened. Sweetener fire rate splits
almost entirely by basis, not by path: divergence **15.9%** (v2) / **16.0%** (v3), consensus 2.9% / 1.8%.

**Fixture prediction vs real boards — four corrections and one confirmation.**

1. **Deck shrink is less than half what the fixture predicted.** Fixture: **−3.9%** served roster,
   −4.4% arm B, worst cell −20%. Real boards: **−1.6%** served roster, **−0.5%** arm B, and the live
   v3 path actually gains a card (**+1.0%**). Worst single cell is `v2_only` / arm D / MangoPatti,
   15 → 11 (−26.7%); worst arm-B cell is `v2_only` / johnstanfield, 17 → 15 (−11.8%). The operator
   accepted −3.9% in advance; the real cost is smaller than the number they accepted.
2. **The over-the-line LEVEL the fixture could not reach is confirmed, and the CHANGELOG's ~15% is
   located.** At `origin/main` on real boards: arm A **18.9%**, arm C **29.4%**, arm B **8.1%** — and
   arm B's **divergence** slice is **13.5%**. The fixture read 0–5% on arm B. So the ~15% figure is a
   divergence/mixed-arm number, not an arm-B-overall one, and the fixture was indeed measuring an
   arithmetically compressed board.
3. **The sweetener fires about twice as often as the fixture implied — confirmed as predicted.**
   Fixture: 3 sweetened cards across 65 arm-B cards (~4.6%), "roughly one card per deck". Real boards:
   **17 / 185 = 9.2%**, **1.42 cards per deck** on a mean deck of 15.4. Owed item (d) called this and
   was right.
4. **The sweetener's economics on real assets.** Mean gap **2173 → 850** (median 2010 → 814), mean
   1324 units closed. **17 of 17 sweetened cards land under the 1539 line** — when the pass fires it
   always succeeds. Equalizer came off the **give** side 14 times, the **receive** side 3, and was an
   owned **PICK** 5 of 17 (Bcork's 2027 1sts, johnstanfield's 2026 1sts) — the `close_value_gap`
   docstring correction in §6 is load-bearing in production, not theoretical. The 7 cards still over
   the line on the branch are **all unsweetened** (gaps 1648, 1648, 1812, 1876, 2171, 2547, 4105) —
   unclosable and kept, exactly as specced.
5. **NEW — the branch's two halves pull in opposite directions, and only the sweetener makes it a
   win.** The branch-only `sweetener_gap_threshold=0` control isolates them on identical decks
   (deck size is unchanged by the sweetener on real boards — every viewer's card count matches
   card-for-card between sweetener-on and sweetener-off, so the whole −1.6% deck delta is the
   BENCHMARK FIX, not the sweetener):

   | Path | main | branch, sweetener OFF | branch, sweetener ON |
   |---|---|---|---|
   | v3 | 7/105 = 6.7% | **12/106 = 11.3%** | 3/106 = **2.8%** |
   | v2-only | 8/81 = 9.9% | **12/79 = 15.2%** | 4/79 = **5.1%** |

   The benchmark fix ALONE would raise arm B's over-the-line share (6.7 → 11.3, 9.9 → 15.2) — the same
   mechanism that makes arm C worse. The sweetener then removes 9 of 12 and 8 of 12. **Shipping the
   benchmark fix without the sweetener would be a net regression on this metric**; they must ship
   together, and `sweetener_gap_threshold` is not an independent rollback lever for the benchmark fix.

**Arm A is byte-identical on REAL boards too** — 376 cards, 71 over the line, mean gap 835.6 to 0.1, on
both trees, across all six viewers and both paths. Ratification item 1 (the arm-A golden pinned rather
than re-captured) now has live-data evidence on top of the fixture and the unit test.

**Arm C is worse than the fixture said, and it is a pre-existing problem the branch deepens.** Real
boards: **29.4% → 37.2%** over the line on an identical 51-card deck (fixture: 0 → 13.6% and
5.3 → 10.5%). Most of that level is NOT this branch — jonbonjourvi's arm C is 11 of 13 over the line on
BOTH trees. Ratification item 5 stands, and the arm-C follow-up is confirmed as a priority.

**One caveat the headline numbers hide: net deck size barely moves, but deck CONTENT churns hard.**
Arm B across all 12 viewer-path decks: 107 cards common, 51 main-only, 50 branch-only — roughly a
third of the deck is different. Per-viewer worst case is Bcork on `v2_only`, 4 of 12 cards common. A
tester comparing decks before/after the merge will see much more change than "−1 card" suggests.

**Not measured here, still owed:** the manual TestFlight checklist (item (a)) — unchanged, it needs a
build. This replay covers generation only; the post-generation presentation stack (thompson, diversity,
fatigue, session rerank, first-session shaping, bake-off interleave) was not replayed, so these are
served-CANDIDATE decks, not final served decks.

**Ship recommendation: unchanged — ship.** Every headline moved in the branch's favour relative to the
fixture: less deck loss than the operator pre-accepted, a bigger over-the-line reduction on a higher
real baseline, and a sweetener that closes every gap it touches. The two findings that change anything
are (5) — the halves are not independently shippable — and the arm-C deepening, which is a follow-up,
not a blocker.

---
## 2026-08-21 — Counterparty breaker waves 1+2 (module · seam · narration · mobile element) — full gates, BOTH FLAGS DARK, NOT MERGED, on `claude/counterparty-breaker-plan`

**Branch:** `claude/counterparty-breaker-plan` (worktree `trading-engine-eval-8ab7bc`), tip `fdd1683`
(wave 1 `0b808b5` → wave 2 `9806d01` → taxonomy v1.1.1 `fdd1683`). **Not pushed, not merged.**
Full gates — the operator explicitly declared **NOT express**, and the change is outside the express
lane by the bright-line rule regardless (two new feature flags, 25 new `model_config` keys, a new
API payload field, two new `features_json` keys).
Scope: [docs/plans/counterparty-breaker/scope.md](../docs/plans/counterparty-breaker/scope.md) ·
code-walk: [code-walk.md](../docs/plans/counterparty-breaker/code-walk.md) ·
readout spec: [calibration-readout-spec.md](../docs/plans/counterparty-breaker/calibration-readout-spec.md) ·
checklist: [PRD](../docs/plans/counterparty-breaker/PRD.md) §8.3.
Decision: [D-142](DECISIONS.md).

**Flags, both default OFF and NEITHER graduated:** `trade.breaker` (compute + stamp),
`trade.breaker_narrative` (the on-card hesitation line; structurally requires the first).

**What ran, and what it proves.** Counts below were re-verified by collection in this checkout on
2026-08-21, not quoted from the commit messages.

| Gate | Result |
|---|---|
| `backend/tests/test_trade_breaker.py` | **67 collected, 67 passed** — predicates, determinism, vocabulary + evidence-key closure, degenerate inputs, tie-break, the whole rung ladder, budget, shadow, knob-snapshot freezing |
| `backend/tests/test_breaker_seam.py` | **30 collected, 30 passed** — seam placement, zero ordering effect (parametrized `bakeoff_group_size ∈ {0, N}` + organic), D-11 seam-creep grep guard, flag-off non-import + byte-identity, dark-window payload absence, the full republish matrix |
| `backend/tests/test_trade_narrative.py` | **22 collected, 22 passed** (file total; **10 of them new**) — the narration gate chain, repetition suppression, template snapshot + `brt-1` version pin, honesty (missing **or present-but-null** evidence ⇒ silence) |
| `backend/tests/test_bakeoff_serving.py` | **+4 collected rows / 3 new functions** (`test_impressions_breaker_uniform_keys` parametrized ×2, `test_midjob_flag_flip_no_crash`, `test_flag_off_features_json_carries_no_breaker_key`); file 42 passed. **Correction to the wave-2 hand-off, which said "+5"** — the true figure is 4 collected rows |
| three breaker files together, re-run 2026-08-21 | **119 passed** |
| `python3 -m pytest backend/tests -q` (full suite) | **3872 passed, 1 skipped, 0 failed** in 264 s — measured at tip `fdd1683` this session. (Wave 1 reported 3835/1, wave 2 reported 3869/1. The +3 over wave 2 is **explained**: wave 2 ran `-k "not calibration_gate"` and reported "3 deselected" — 3869 + 3 deselected = 3872 collected. Same suite, no discrepancy) |
| `mobile/tests/check-breaker-card.js` | **12 assertions, 12 passed / 0 failed**, re-run in this checkout. Sabotage-proven at build |
| `mobile/scripts/testid-lint.sh` | **OK**, re-run in this checkout (2 new testIDs: `trade-card.breaker-hesitation`, `trade-card.breaker-hesitation.body`) |
| `cd mobile && npx tsc --noEmit` | **NOT RUN LOCALLY — deferred to CI's `mobile-typecheck` job.** `mobile/node_modules` is absent in this worktree; this is pre-existing and not a property of the change |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = everything above plus the code-walk |

**Named sabotages that are permanent tests, not one-off cycles.** These landed as tests, so the
proof re-runs on every CI pass rather than living in a session log: `test_breaker_binding_sabotage`
(monkeypatch a `ts` knob ⇒ the next `stamp_breaker` verdict moves — T1 module-import discipline;
plus a module-attribute swap of `ts.package_value_v2` to a sentinel, which a value-binding
implementation would no-op on) · `test_knob_snapshot_frozen_within_job` (mutate `ts._cfg` between
pass 1 and pass 2 ⇒ stamps unchanged) · `test_per_class_exception_contained` (one predicate raises ⇒
that class stamps `skipped:"predicate_error"`, the other five score, card stays rung 0) ·
`test_budget_ladder_labeling` (tiny `breaker_ms_budget` + a slowed predicate ⇒ the correct rung at
each of three trip points, incl. mid-pass-2 buffered work **discarded**) · `test_exception_rungs`
(context-assembly raise ⇒ rung 4 for that card only; `stamp_breaker` monkeypatched to raise at the
seam ⇒ rung-5 marker on **every** card — `test_breaker_seam.py:111` is the injected failure) ·
`test_breaker_zero_ordering_effect` (delete-attribute variant included) ·
`test_flag_off_never_imports_breaker`. The mobile guard was likewise sabotage-proven at build
(each of its 12 assertions driven red by an edit to `TradeCard.tsx`, then restored).

**Gap in this record, stated rather than papered over:** wave 2's commit message reports "4 named
sabotages red→green" and wave 1's reports the guard as "sabotage-proven", but the **individual
wave-2 sabotage names and their red-run output were not written down in-session**. The permanent
sabotage tests above are re-runnable evidence and cover the same seams; the four cycles themselves
are not independently reconstructable from the repo. Recorded as a documentation miss.

**Not run — the load-bearing absence.** The [PRD](../docs/plans/counterparty-breaker/PRD.md) §8.3
manual TestFlight checklist (**19 numbered steps**; steps 1–4 are the dark-window sub-checklist)
is **UNRUN**. It is **operator-owed** and needs a build cut containing the hesitation element, which
does not exist. Per D-056 this checklist is the **only** runtime evidence this feature will ever get,
so as of today **no runtime evidence exists for the counterparty breaker at all** — everything above
is static. `trade.breaker_narrative` must not light before it passes.

**Also owed before `trade.breaker` lights** (preconditions, not stretch items): the TBD-operator
cells in the [calibration-readout spec](../docs/plans/counterparty-breaker/calibration-readout-spec.md)
§4.1 (per-class min n and margins), the §2.4 `fix/package-benchmark-sweetener` deploy timestamp (a
code-ship boundary that `model_config_changes` **cannot** see), the reviewed `scripts/`-style readout
SQL artifact, and the dry-run `ms` number to the operator.

## 2026-08-20f — Composite window model #372 (starter value + playoff likelihood + age at 40 %) — full gates, FLAG DARK, NOT MERGED, on `claude/372-window-composite`

**Branch:** `claude/372-window-composite`, cut from `origin/main` at `c00a9a6`. **Not pushed, not merged** — parent agent integrates.
Full gates ran — operator did **not** declare express, and the change is outside the express lane by the bright-line rule anyway (a new feature flag and new API fields).
Scope: [docs/feedback/items/372-window-composite/scope.md](../docs/feedback/items/372-window-composite/scope.md) ·
code-walk: [code-walk.md](../docs/feedback/items/372-window-composite/code-walk.md) ·
checklist: [testflight-checklist.md](../docs/feedback/items/372-window-composite/testflight-checklist.md).
Decisions: [D-140](DECISIONS.md), [D-141](DECISIONS.md).

**Flag, default OFF and NOT graduated:** `trade.outlook_composite`.

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3761 passed, 1 skipped, 0 failed** (bar was 3721 on `c00a9a6`; +38 new in `test_window_composite.py`, +2 parametrized fixture rows) |
| `cd mobile && ./node_modules/.bin/tsc --noEmit` | clean, exit 0 (`node_modules` symlinked from `jolly-leakey-d20295`) |
| every `mobile/tests/check-*.js` | **67 scripts, 0 failed**, including the new `check-window-composite.js` (14 assertions) |
| `mobile/scripts/testid-lint.sh` | **OK** (2 new testIDs: `team-review.window.starters`, `team-review.window.playoff`) |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = everything above plus the prod calibration below |

**Two structural guards on `origin/main` fired on this change and were answered, not silenced.** `test_no_generation_knob_was_added_without_an_arm_a_decision` caught all eight new `infer_composite_*` knobs — they are added to `_PINNED_KNOBS` with a written exclusion rationale (they cannot reach generation: the term they weight needs an applied starter signal, which needs a league-wide power-rankings call no generation path makes). `test_release_flags_mirror_features_json` caught the new flag missing from `backend/tests/fixtures/flags/release.json`, and two sibling fixtures (`onboarding-v2`, `profiles-on`) needed the same mirror.

**Sabotage evidence — 22 cycles, every one RED with the NAMED test in the failures, restored via `git checkout --`, proved restored with `git diff --quiet`, re-run GREEN. `__pycache__` cleared between every cycle.**

Backend (13, against `backend/tests/test_window_composite.py`): S1 composite branch drops the `starter_signal is not None` gate · S2 `composite` set regardless of `applied` · S3 flag gate removed · S4 `model` not re-stated at composite weights · S5 refused playoff term scored anyway · S6 starter index uncapped · S7 precedence rule deleted (band replaces AND scores) · S8 `_window` stops passing `starters` through · S9 `starter_value_signal` fakes `observed` on unreadable input · S10 age weights left at 1.00 inside the composite · S11 playoff index scale doubled · S12 starter term gated on `index != 0` instead of `applied` · S13 `index_raw` capped, so the card would print the model's number instead of the team's.

Mobile (9, against `check-window-composite.js`): M1 starter weight hardcoded · M2 `composite` derived from `st.applied` alone · M3 `lineup_unknown` copy branch removed · M4 `signals.starters` made required in the type · M5 `'composite'` dropped from the `source` union · M6 "whole model" sentence made unconditional · M7 `starterScored` gated on `st.index !== 0` · M8 playoff contribution row deleted · M9 starter card switched to the capped `index`.

**TWO DEAD ASSERTIONS FOUND AND FIXED — this is the finding, not a footnote.**

1. **S5 did not go red on the first run.** `test_a_refused_playoff_term_is_absent_from_the_score_not_a_zero` built its refused signal from `playoff_odds_signal`, which zeroes `index` whenever it refuses — so deleting the `applied` guard was a numeric no-op and the test passed against a broken function. Fixed by handing `infer_team_outlook` a refused block with a **loud** index of 0.8; only the `applied` check can now keep it out. Its starter-side sibling (`test_an_unapplied_starter_signal_with_a_LOUD_index_still_scores_nothing`, sabotage S12) was written at the same time for the same reason.
2. **M7 did not go red on the first run.** Mobile check 4 read `/starters[\s\S]{0,80}index\s*[!=]==?\s*0/` — it required the literal word "starters" within 80 characters of the comparison, but the real gate is written `st.index`. Rewritten to match the comparison itself anywhere in the beat, plus a new positive half (4b) asserting both `Scored` flags derive from `applied`.

Both were the exact class the brief warned about: an assertion that holds by accident and can never fail. They join the three found earlier the same day.

**Prod calibration — read-only, and it is the load-bearing evidence.** The #365 session concluded from `data/trade_finder.db` that this family of signal pointed the wrong way; **that corpus does not contain FFV3 at all**. Every number below comes from a read-only `DATABASE_URL_PROD` connection (`set_session(readonly=True)`) plus the league's real Sleeper lineup template.

- **`Fantasy Football Version 3` (`1312140920132497408`), `mattmurf77`: legacy `−0.4867 rebuilder` → composite `+0.2009 CONTENDER`.** His starters are worth 43,615 against a league mean of 23,963 — 82 % above average, the best starting lineup in the league — while he holds essentially no pick capital (0.004 share against an even 0.083). The league is `pre_draft`, so the playoff term is refused (`preseason` / `odds_disabled`) and the composite runs on starters, picks and down-weighted age alone.
- **The reverse sanity check:** `PaulSm3nis` is a legacy **contender** on age alone (vet share 0.65) while owning the league's *worst* starting lineup (3.2 % share) and sitting 12th of 12 in value. The composite calls him a rebuilder.
- **Across 12 prod leagues / 156 teams:** legacy = **101 rebuilder / 26 not_sure / 29 contender** (65 % rebuilder, and *zero* not_sure verdicts in FFV3 itself); composite = 62 / 40 / 54. Transitions run both ways (29 rebuilder→contender, 4 contender→rebuilder, 8 contender→not_sure), which is what a re-weighting looks like rather than a thumb on the scale. This distribution is the evidence for **leaving `infer_contender_cut` / `infer_rebuilder_cut` unmoved** (D-140).

**Not run:** the TestFlight checklist (8 numbered steps across all four flag combinations) — it needs a build containing this branch, which does not exist. No runtime mobile evidence exists for #372 yet; the flag stays dark until it does.

## 2026-08-20b — Fit challenger PR-F3 (filters + arm wiring + serve-bit) + W0 offline dry run (SHIPPED to `main` 2026-08-20)

**Branch:** `claude/trade-suggestions-review-69c9eb` (worktree), on top of PR-F2 `d8a80a5`. **Not committed, not merged** — the finishing package of the fit-challenger build ([PRD-build](../docs/plans/fit-challenger/PRD-build.md) PR-F3 + deferred docs rows).
## 2026-08-20c — Window signals #365 (net firsts) + #371 (playoff odds) — full gates, BOTH FLAGS DARK, NOT MERGED, on `worktree-agent-a3ea3b1d38e084930`

**Branch:** `worktree-agent-a3ea3b1d38e084930`, cut from `origin/main` at `bc43b6f`. **Not pushed, not merged.**
Full gates ran — operator did **not** declare express, and explicitly ruled the change outside the express lane (it adds two feature flags and two API fields).
Scope: [docs/feedback/items/365-window-signals/scope.md](../docs/feedback/items/365-window-signals/scope.md) · code-walk: [code-walk.md](../docs/feedback/items/365-window-signals/code-walk.md) · checklist: [testflight-checklist.md](../docs/feedback/items/365-window-signals/testflight-checklist.md).
Decisions: [D-110](DECISIONS.md), [D-111](DECISIONS.md).

**Flags, both default OFF and neither graduated:** `trade.outlook_net_firsts`, `trades.window_from_odds`.
## 2026-08-20e — Team Review `plan` beat rebuilt (#369) — full gates, NOT MERGED, on `worktree-agent-a7bed877f805980b0`

**Branch:** `worktree-agent-a7bed877f805980b0`, worktree at `origin/main` `bc43b6f`. **Not pushed, not merged** — parent agent integrates.
Full gates ran — operator did **not** declare express.
Scope: [docs/feedback/items/369-plan-beat/scope.md](../docs/feedback/items/369-plan-beat/scope.md) ·
Code-walk: [code-walk.md](../docs/feedback/items/369-plan-beat/code-walk.md) ·
Decisions: [D-130](DECISIONS.md), [D-131](DECISIONS.md).

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3645 passed, 1 skipped, 0 failed** (bar was ≥ 3629; +20 new fit/serving tests) |
| Knob-inventory guard (`test_no_generation_knob_was_added_without_an_arm_a_decision`) | green with **all 17** fit/bakeoff keys in `_PINNED_KNOBS` + 17 disposition sentences in scope-phase2.md |
| Organic isolation | `test_organic_never_imports_fit` (sys.modules + comment-stripped source grep) + the standing flag-off captured golden (`test_flag_off_is_byte_identical_to_the_captured_golden`) both green |
| `bash mobile/scripts/testid-lint.sh` | **OK** |
| `npx tsc --noEmit` | not run in this worktree (no `node_modules`); **zero mobile files touched** — the mobile CI jobs are byte-identical to `origin/main`'s green |
| Sim gate | `FTF_SKIP_SIM_GATE=1` standing posture (D-056); evidence = the suite above |

**Sabotage evidence (serve-bit, both draft paths — HLD F-6).** `test_serve_fit_bit_excludes_from_draft` is parametrized over `bakeoff_group_size ∈ {0, 10}`. Sabotage: the `group_size = 0` fallback's rotation was reverted from `serving_roster` to the full `roster` (the exact F-6 leak — one line in `run_bakeoff`). Result: **`[0]` went red, `[10]` stayed green** — proving the 0-path case guards the `team_draft` fallback specifically (the W1 live path), not just `compose_deck`. Reverted, re-ran green; full suite re-run green after.
Prior sabotages standing from PR-F1/F2: T1 binding (`overpay_ok` rebind), M3 inertness (`fit_diag` delete), C7b (`test_draft_rank_only`, new in this package: one arm's composite ×100 ⇒ identical deck).

**W0 offline dry run (PLAN-v2 §5 W0) — FIXTURE-ONLY.** No prod DB access from this worktree: the replay boards for league `1312140920132497408` are a prod artifact and were NOT run — that half of the W0 contract plus the baseline M2 readout snapshot is an **operator item**. Leagues below: (a) the literal bakeoff-test fixture league (`backend/tests/support/bakeoff_harness._POOL`); (b)/(c) leagues built deterministically from the committed 340-player pool `backend/tests/fixtures/player_pool_2026.json` with rank-ladder Elo seeds (1750→1250), hash-offset synthetic boards (±120 on ~40% of assets; viewer + half the opponents boarded), and 3 owned-pick pseudo-assets per team. Script: session scratchpad `w0_dry_run.py` (throwaway, not committed). All at PRD-default knobs unless noted; viewer outlook None unless noted.

| League | Cap | ms (module) | enumerated | scored | emitted | killed (nonzero) | one_sided | both_high/mixed/you_tilt | top_q pick/junk | capped_pairs |
|---|---|---|---|---|---|---|---|---|---|---|
| (a) harness fixture (8 players, 2 opp) | 20000 | **0** | 16 | 0 | 0 | K3 6, K4 10 | — | — | — | 0 |
| (b) 12-team 1QB, 26-man+3-pick | 20000 | **8396** (repeat 5769) | 195,783 | 38,634 | 253 | K2 520 · K3 416 · **K4 133,923** · K5 15,765 · K6 6,525 | 0.480 | .045/.100/.164 | **0.699** / 0.055 | 6/11 |
| (b') same, W3 posture cap 5000 | 5000 | **1826** | 55,000 | 11,326 | 248 | K4 37,389 · K5 4,254 · K6 1,764 · K2 158 · K3 109 | 0.446 | .081/.150/.209 | 0.648 / 0.059 | 11/11 |
| (b+outlook=contender) | 20000 | 5312 (wall) | 194,913 | 33,976 | 156 | **K7 6,925** + as (b) | 0.496 | — | — | — |
| (c) 16-team SF (`sf_tep`), 21-man+3-pick | 20000 | **5772** | 227,230 | 38,090 | 333 | K4 154,455 · K5 27,703 · K6 4,971 · K3 1,391 · K2 620 | 0.417 | .142/.166/.192 | 0.682 / **0.390** | 7/15 |
| (c') same, cap 5000 | 5000 | **1374** | 70,210 | 10,637 | 294 | K4 46,900 · K5 10,449 · K6 1,449 | 0.359 | .237/.178/.187 | 0.638 / 0.375 | 14/15 |

Emitted bucket mix (b, defaults): both_high 47 · mixed 101 · them_tilt 24 · you_tilt 22 · both_ok 5 · weak 54. Post-filters: **C4 centerpiece cap is the dominant post-score filter** (38,381 of 38,634 scored dropped on (b) — small-league centerpiece concentration; `deck_headliner_cap` 2). All other `post_filtered` counters 0 (no prefs in the fixture jobs).

**Readings for the operator (the decisions this run feeds):**

- **ms fail bar (scope.md §6, blocks rostering):** 12-team defaults ≈ **5.8–8.4 s** per job; at the W3 posture (`fit_max_packages_per_pair = 5000`) ≈ **1.4–1.8 s**; 16-team SF the same shape. The cap knob is the relief valve exactly as designed — W3's 5000 first looks right.
- **R-8 volume check:** fit **253** distinct ideas vs arm B **12** (engine-default `max_per_opponent=5`, same league, 307 ms) — ratio ≈ **21×**, far above the 1.2× bar ⇒ per R-8 the build **pauses at this readout for an operator call**; no auto-roster. (Also the PRD §11.6 read: `enumerated` 195,783 ≫ arm B's emitted set.)
- **`killed[K7]` (F7 evidence):** 0 with no declared outlook (live R5 is outlook-scoped), **6,925** under `contender` — the dual-R5 debate has its number, but only on outlook-declared jobs.
- **W3 soak-bar preview:** `top_q_junk_share` 0.055 on the 12-team fixture (bar ≤ 0.10: passes) but **0.375–0.390 on the constructed 16-team SF fixture** — likely an artifact of 21-man rosters built from a 340-player pool (deep tails sit under `asset_floor_abs` 450 in the rank-ladder Elo mapping), but it is exactly the C5 flooding signature the soak bar exists for: read it on real W3 data before trusting either interpretation. `top_q_pick_share` ≈ 0.64–0.70 everywhere (picks ride high consensus percentile under R-c) — the W3 bar is relative to arm B, which this fixture cannot supply.
- **(a) harness fixture emits 0 cards** — its 4-asset rosters put every cross-value package over K4's overpay ceiling; a fixture artifact, not a generator defect (the 26-man leagues emit 250+).

**What is NOT proven, and is owed.** Prod replay boards (league `1312140920132497408`) + baseline M2 readout snapshot — operator, needs prod read access. Constructed-league Elo/boards are synthetic (rank-ladder + hash offsets), so bucket mixes and junk shares are directional, not calibrated. `bakeoff_include_fit` stays 0 (decision 4) until the operator sets the ms bar and answers R-8; `bakeoff_serve_fit` stays 0 regardless.

---
| `python3 -m pytest backend/tests -q` | **3646 passed, 1 skipped** (259 s). Baseline before this work on the same tree: **3606 passed, 1 skipped** — +40, all in the new `backend/tests/test_window_signals.py` |
| `cd mobile && ./node_modules/.bin/tsc --noEmit` | **clean** |
| `mobile/tests/check-*.js` — **65** suites (64 pre-existing + the new `check-window-signals.js`) | **0 failed**. `check-window-signals` 10/10, `check-team-review` 7/7 still green |
| `mobile/scripts/testid-lint.sh` | **OK** |
| Sabotage proof — **20 of 20** | every one turned its **named** guard red, each source restored with `git checkout --` and verified **by content** (`git diff --quiet`), `__pycache__` cleared before every run, and re-run green |

**The load-bearing evidence is the flag-off invariant, and it is a golden, not a re-derivation.**
`infer_team_outlook` feeds `outlook_alpha` for the trade engine, the mock draft and the outlook seed,
so a score change is a deck change for every user. The goldens in `test_window_signals.py` were
captured by extracting the `bc43b6f` backend tree (`git archive`) and running the same fixtures
against it — code that had never heard of the new kwarg — rather than by re-deriving the formula the
module now contains, which would have proved nothing. Two invariants pinned:
**INV-365** flag OFF ⇒ the ledger kwarg is accepted and ignored, whole tuple equal;
**INV-365b** flag ON but no ledger ⇒ score still unchanged, because only the Team Review route
builds a ledger. Together they mean lighting `trade.outlook_net_firsts` moves the window beat and
**not one deck**.

**Sabotage table — 20 cases.** Harness `scratchpad/sabotage_365_371.py`; per case: apply one targeted
revert → clear `__pycache__` → run → require red **and** require the *named* guard to be the one that
failed → `git checkout --` → `git diff --quiet` → clear `__pycache__` → re-run → require green.

| # | Behaviour reverted | Guard | Red | Clean | Green |
|---|---|---|---|---|---|
| S1 | term applies with the flag OFF | `test_flag_off_ignores_a_supplied_ledger_entirely` | yes | yes | yes |
| S2 | term applies with the flag on but no ledger | `test_flag_on_without_a_ledger_is_still_the_golden` | yes | yes | yes |
| S3 | sign flipped (hoarding reads as contending) | `test_selling_firsts_raises_the_score_and_hoarding_lowers_it` | yes | yes | yes |
| S4 | `net_share` clamp removed | `test_net_share_is_clamped_by_the_knob` | yes | yes | yes |
| S5 | uncaptured pick history scores as a confident zero | `test_a_league_with_no_recorded_trades_is_none_traded_not_a_confident_zero` | yes | yes | yes |
| S6 | empty roster still reports the term applied | `test_empty_roster_never_reports_an_applied_term` | yes | yes | yes |
| S7 | `window.model` advertises unused knobs | `test_model_carries_the_new_knobs_whenever_the_term_is_live` | yes | yes | yes |
| S8 | NULL original owner read as a trade | `test_ledger_reader_treats_a_null_original_owner_as_never_moved` | yes | yes | yes |
| S9 | ledger counts every round, not just firsts | `test_ledger_reader_splits_held_owned_traded_and_acquired` | yes | yes | yes |
| S20 | ledger stops attributing acquisitions | `test_ledger_reader_splits_held_owned_traded_and_acquired` | yes | yes | yes |
| S19 | ledger computed then not passed through | `test_window_passes_the_firsts_ledger_through_untouched` | yes | yes | yes |
| S10 | preseason odds obeyed instead of refused | `test_preseason_refuses_the_band_but_still_reports_it` | yes | yes | yes |
| S11 | empty band dict treated as a real band | `test_no_band_falls_back_and_names_it` | yes | yes | yes |
| S12 | #371 keys ship with the flag off | `test_window_is_shape_identical_when_both_flags_are_off` | yes | yes | yes |
| S13 | heuristic verdict lost when odds override | `test_window_reports_which_model_drove_and_keeps_the_other_one` | yes | yes | yes |
| S14 | beat hardcodes an age threshold again | `check-window-signals` 1 | yes | yes | yes |
| S15 | ledger shown but contribution not itemised | `check-window-signals` 2 | yes | yes | yes |
| S16 | "we ignore traded picks" becomes fixed copy | `check-window-signals` 3 | yes | yes | yes |
| S17 | `none_traded` no longer distinguished | `check-window-signals` 4 | yes | yes | yes |
| S18 | a flag-gated field made required in the type | `check-window-signals` 7 | yes | yes | yes |

**One guard in this batch was vacuous, and the sabotage is what found it — recorded because it is the
more useful finding.** `check-window-signals` claim 2 originally asserted only that the identifier
`w_net_firsts` appeared somewhere in the `Window` component. It does, unconditionally: the weight is
destructured at `TeamReviewScreen.tsx:390`. So **S15 deleted the contribution row outright and the
check stayed green.** It now requires the *product* — the weight × `net_share` on one line, with the
alias discovered from the source rather than assumed. This is the same class of failure the
2026-08-20a batch hit (`test_divergence_ignores_unjudged_players` went vacuous while passing), which
is why the harness requires the **named** guard to fail rather than merely a red run.

**Three pre-existing structural guards fired on this change and were each resolved deliberately, not
suppressed.** All three are working exactly as designed and are recorded so the resolutions are
auditable:
- `test_bakeoff_arm_a_golden::test_no_generation_knob_was_added_without_an_arm_a_decision` — two new
  `_DEFAULT_CFG` knobs. **Excluded from `MODEL_A_PROFILE`**, with the reason recorded in
  `docs/plans/three-model-bakeoff/scope-phase2.md`'s exclusion table: they cannot reach generation at
  all, because the term is gated on a ledger no generator supplies (INV-365b). Pinning a kill value
  would imply they matter to a deck; they provably do not. Arm-A golden re-run green.
- `test_pick_assignment::test_w3_02_ast_only_sanctioned_call_sites_name_source` — `_first_round_ledgers`
  is the **eighth** sanctioned `load_draft_picks` opt-in, added to `_SEVEN_READ_SITES` with the
  rationale inline: it must count the same picks `_power_picks_by_owner` prices two lines away in the
  same route, so a literal `platform` would make the card and the beat above it disagree on any ESPN
  league with `picks.assign_tradeable` on.
- `test_seed_ui_test_db` (three assertions) — the flag fixtures. Both flags added `false` to
  `release.json`, `onboarding-v2.json` and `profiles-on.json`, which are asserted to share a key set;
  deliberately **not** added to `all-on.json` (a client overlay, not a full map), matching the
  `outlook.odds` precedent.

**Calibration evidence, and the finding that cuts against the feature.** `infer_w_net_firsts = 0.10`
was set against the only real pick corpus reachable from the session (`data/trade_finder.db`): across
24 member-league pairs in the two leagues that carry round-1 provenance, `|net_share| ≤ 0.75`, so the
contribution range is ±0.075 against a `not_sure` band of ±0.08 — one bucket at most, never two,
pinned by `test_the_term_can_move_one_bucket_and_never_two`. **In both of those leagues the operator
has traded away zero of his own firsts and acquired one**, so the signal he asked for points *him*
further toward rebuilder; and **FFV3, the league in the report, has no `draft_picks` rows in that DB
at all**. Prod Postgres would settle both and was not reachable (the read was denied by the sandbox).
This is why the flag ships dark and why its graduation criterion is an operator check on prod.

**CORRECTED SAME DAY by a read-only prod query.** The local corpus was the problem, and the conclusion above is BACKWARDS for the league that filed the report. Prod carries 276 round-1 rows across 7 leagues with a traded first; in **Fantasy Football Version 3 (FFV3, `1312140920132497408`) `mattmurf77` holds ZERO firsts having sold all three of his own — **3 sold, 0 acquired, 0 still owned** — stated as counts on purpose, because the two conventions in play have opposite signs: this prose had been reading "net +3" in a sold-minus-bought sense while the CODE scores `firsts.net_share` as owned-minus-traded, i.e. **−3**. Same fact, opposite sign, and neither had stated its convention. The scoring direction is correct either way (the score subtracts `w × net_share`, so a seller gains)**, the strongest all-in reading the term produces, pointing him toward CONTENDER. His other leagues run the other way (La Resistance −5, Lakeview −1). Lesson worth keeping: *a local DB that is missing the subject league is not a small sample, it is the wrong sample* — and it produced a confident, inverted finding that would have argued against shipping the right fix.

**Not run, and owed:** the manual TestFlight pass
([testflight-checklist.md](../docs/feedback/items/365-window-signals/testflight-checklist.md)). It is
the gate on graduating either flag. Note that §C4–C6 (the odds path actually driving) **cannot be
walked until week 1 is played** — `completed_weeks == 0` today, and the refusal is the designed
behaviour, so the in-season half of #371 has no runtime evidence yet and must not be claimed.

---

## 2026-08-20d — #366 position-relative tier bands + RB Handcuff — full gates, NOT MERGED, on `worktree-agent-a4ab94c51456abb78`

**Branch:** `worktree-agent-a4ab94c51456abb78`, worktree at `origin/main` `bc43b6f`. **Not pushed, not merged.**
Full gates ran — operator did **not** declare express. Both flags ship **OFF** and are **not graduated**.
Scope: [docs/feedback/items/366-tier-ladder/scope.md](../docs/feedback/items/366-tier-ladder/scope.md).
Code-walk: [code-walk.md](../docs/feedback/items/366-tier-ladder/code-walk.md).
Decisions: [D-120](DECISIONS.md), [D-121](DECISIONS.md).

**What ran.**

| Gate | Before | After |
|---|---|---|
| `python3 -m pytest backend/tests -q` | 3606 passed, 1 skipped (356s) | **3638 passed, 1 skipped** (352s) |
| `tsc --noEmit` | clean | **clean** |
| `mobile/tests/check-*.js` (65 suites) | 64 suites, 0 failed | **65 suites, 0 failed** (new `check-team-review-depth` 8/8; `check-team-review` still 7/7) |
| `bash mobile/scripts/testid-lint.sh` | OK | **OK** |
| Sabotage proof | — | **12 of 12 turned their guard red**, restored clean, re-run green |

New tests: `backend/tests/test_position_tiers.py` (**30**), `backend/tests/test_team_review.py` (**+2**),
`mobile/tests/check-team-review-depth.js` (**8 assertions**). Net +32 backend tests (3606 → 3638).

**Sabotage table.** Every cycle: apply one targeted revert → run → require RED **and** require the
*named* guard to be the one that failed → `git checkout --` → prove restoration with
`git diff --quiet` (never with a test result) → re-run → require GREEN.
`find backend -name __pycache__ -type d -exec rm -rf {} +` ran before **every** invocation, because a
`git checkout` restore leaves the source older than the sabotage run's `.pyc` and Python will happily
serve stale bytecode — a correct tree then tests red and the whole table becomes noise.

| # | Sabotage applied | Guard that caught it | Red | Restored clean | Green again |
|---|---|---|---|---|---|
| S1 | emit the `replacement` alias unconditionally | `test_flag_off_adds_no_keys_anywhere` | ✅ | ✅ | ✅ |
| S2 | band boundary `<=` → `<` | `test_relative_band_boundaries` | ✅ | ✅ | ✅ |
| S3 | drop the superflex QB widening | `test_superflex_widens_qb_and_nothing_else` | ✅ | ✅ | ✅ |
| S4 | `_POS_TIER_MIN_POOL` 40 → 0 | `test_thin_pool_falls_back_to_absolute_cuts` | ✅ | ✅ | ✅ |
| S5 | handcuff accepts `order in (1, 2)` | `test_handcuff_rejects_everything_that_is_not_an_rb2` | ✅ | ✅ | ✅ |
| S6 | reorder so `_is_handcuff` runs before the flag check | `test_flag_off_never_touches_the_depth_chart` | ✅ | ✅ | ✅ |
| S7 | composer emits `handcuff_rb` unconditionally | `test_depth_omits_366_keys_entirely_when_the_flags_are_off` | ✅ | ✅ | ✅ |
| S8 | mobile reads `replacement ?? 0` (drops the `bench` fallback) | `check-team-review-depth` #2 | ✅ | ✅ | ✅ |
| S9 | mobile gates on `(handcuff_rb ?? 0) >= 0` | `check-team-review-depth` #4 | ✅ | ✅ | ✅ |
| S10 | TS type makes `replacement` required | `check-team-review-depth` #3a | ✅ | ✅ | ✅ |
| S11 | force `relative = True` (relative path leaks with the flag OFF) | `test_flag_off_bins_follow_the_absolute_cuts_exactly` | ✅ | ✅ | ✅ |
| S12 | drop the "Replacement" label from the beat | `check-team-review-depth` #5a | ✅ | ✅ | ✅ |

**The finding that matters more than the table: 65 existing engine tests are BLIND to this change.**
Per the standing instruction to re-read the tests that *pass*, `test_roster_profile`, `test_need_fit`,
`test_finder_targeting` and `test_presentment_rules` were re-run with `relative` forced `True` in
source. **All 65 stayed green.** The cause was then confirmed rather than assumed: disabling
`_POS_TIER_MIN_POOL` as well turns exactly **1 of 65** red, so every fixture in those files is smaller
than the small-pool guard and cannot distinguish the bands even in principle. They are evidence for
the flag-**off** path only. Consequence, recorded in the scope block and D-120:
**`trade.position_tiers` must not graduate on a green suite** — it needs `scripts/deck_eval.py` on real
leagues plus step 6 of the TestFlight checklist.

**Measurements taken during the build** (not test results — inputs to the design):
- Absolute cuts against the live pool (`data/trade_finder.db`, 2 684 players): **elite = 33 RB, 33 WR,
  17 QB, 7 TE.** The reported defect, quantified.
- The three value thresholds are exactly overall-`search_rank` cuts at **73 / 151 / 238**
  (`1 + ln(ktc_max/T)/ktc_k`, `ktc_k = 0.0126`).
- Depth-chart coverage: **149 of 603** RB rows carry a real `depth_chart_order`, matching the 32 actual
  NFL charts. The nulls are camp bodies and FAs.
- `_positional_rank_map` build cost: **1.31 ms** over 2 684 players (50 iterations); memoized on pool
  identity, so ~1 build per request rather than 13 per deck run.

**TestFlight:** checklist written
([testflight-checklist.md](../docs/feedback/items/366-tier-ladder/testflight-checklist.md), 6 steps),
**not run** — owed by the operator, and moot until a flag is lit. Step 3 deliberately checks the
handcuff tag against nfl.com rather than merely checking that something rendered.

**Not covered by anything here:** whether the new bands make decks *better*. That is a judgement call
and it is the operator's; the flags ship off so it does not have to be made today.
| `python3 -m pytest backend/tests -q` | **3606 passed, 1 skipped** (339s) — unchanged from baseline; no backend code was touched |
| `tsc --noEmit` | **clean** |
| 64 `mobile/tests/check-*.js` suites | **0 failed**; `check-team-review` went **7 → 13 assertions**, all green |
| `mobile/scripts/testid-lint.sh` | **OK** |
| Sabotage proof — 9 of 9 | **every one turned its guard red on the EXPECTED assertion**, sources restored, guard re-run green after each |

**Sabotages, individually.** (5b) render `{o.playoff_pct}` as visible text → RED;
(6) source the plan chips from `data.depth.acquire_positions`, the stale mount-time snapshot → RED;
(6b) drop `refetchOnMount: 'always'` → RED;
(7) gate a plan-beat lever on `done.current` again → RED;
(8) rename the "Trade fairness" lever off the page → RED;
(9) add a second `asset_preferences` writer to the screen → RED;
(10) remove the `team_outlook` backfill, i.e. reinstate the shipped bug → RED;
(11a) stop handing the scoped partner to the #330 store → RED;
(11b) delete the deck-side handoff consumption in `TradesScreen.tsx` → RED.

**Two findings recorded because they are worth more than the pass count.**
- **A shipped write has never once succeeded.** The depth beat posted a positions-only body and
  `POST /api/league/preferences` **400s without `team_outlook`** (`server.py:15788-15790`);
  `apiRequest` throws on non-2xx, so `done.current.add('positions_set')` on the next line never ran and
  the empty `catch` hid it. `team_review_action_taken{action:'positions_set'}` has therefore **never been
  emitted in production** — do not read its history as a baseline. Now pinned by assertion 10.
- **An existing green assertion was about to go vacuous — the same failure mode as 2026-08-20a.**
  Assertion 5b guarded "never render a bare playoff percentage" with a whole-FILE escape hatch
  (`… && !/accessibilityLabel/.test(s)`). `TeamReviewScreen.tsx` at `HEAD` contained **zero**
  `accessibilityLabel` occurrences, which is the only reason the clause held; the plan beat's chips add
  three, so from this commit the condition could never be true and 5b would have kept passing while
  proving nothing. Rewritten per-occurrence in the same commit and sabotage-proven. *Two batches
  running, two dead-test escapes — re-reading the tests that PASS is now the cheapest gate we have.*

**What is NOT proven.** The manual TestFlight checklist
([testflight-checklist.md](../docs/feedback/items/369-plan-beat/testflight-checklist.md), 9 steps) is
**UNRUN**. Under [D-056](DECISIONS.md) it is the only runtime evidence this gets, and the central claim
— that the beat shows what is *actually saved* — is a network read whose failure mode is a stale but
entirely plausible page. Steps 2, 3 and 7 are the load-bearing ones. **Requires a client release**; none
of this is in build 122.

---
## 2026-08-20a — Team Review defect batch (#364/#367/#368) — full gates, NOT MERGED, on `claude/team-outlook-experience-27a7a1`

**Branch:** `claude/team-outlook-experience-27a7a1`, worktree at `origin/main` `a76498e`. **Not pushed, not merged** *(at time of writing — since merged to `origin/main` as PR #152, `bc43b6f`)*.
Full gates ran — operator did **not** declare express.
Scope: [docs/feedback/items/364-team-review-fixes/scope.md](../docs/feedback/items/364-team-review-fixes/scope.md).
Decisions: [D-100](DECISIONS.md), [D-101](DECISIONS.md).

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `pytest backend/tests` | **3606 passed, 1 skipped** (292s) |
| `tsc --noEmit` | **clean** |
| 64 `mobile/tests/check-*.js` suites | **0 failed** (incl. `check-team-review` 7/7, `check-outlook-bands` 7/7) |
| `mobile/scripts/testid-lint.sh` | **OK** |
| Sabotage proof — 5 of 5 | **every one turned its guard red**, sources restored, full suite re-run green |

**Sabotages, individually.** (1) drop the `#368` kwargs → `test_team_review_route_passes_the_pick_capital_it_computes` FAILED;
(2) re-cross the seed ladder → `test_seed_ladder_buys_are_off_roster_and_sells_are_on_roster` FAILED;
(3) re-cross the community ladder → `test_community_ladder_maps_buys_to_higher_and_sells_to_lower` FAILED;
(4) stop shipping `model` → `test_window_ships_the_model_so_no_client_restates_a_threshold` FAILED;
(5) restore `gap = u - c` → `test_consensus_gap_sells_are_where_the_market_is_higher_than_you` FAILED.

**Two pre-existing tests were not merely re-run — they were wrong, and are recorded here because
that is the more useful finding.**
- `test_consensus_gap_sells_expose_rank_gap` **asserted the defect**: it took a player the user rated
  300 *above* the community and asserted he was an "easiest sell". Re-encoded and renamed; it now holds
  **both** roster players so it proves a *selection* (the 200-below player in, the 300-above player out).
- `test_divergence_ignores_unjudged_players` went **vacuous** under the fix — its fixture put p1
  on-roster-and-high and p2 off-roster-and-low, so under the corrected rule both lists came back empty
  and its leak assertion proved nothing **while still passing green**. Roster re-aimed, plus an explicit
  non-emptiness assertion so it cannot silently hollow out again. *A green suite was hiding a dead test.*

**Gotcha worth the note.** After a sabotage cycle, restoring a file with `cp` from a backup gives it an
**older mtime than the `.pyc` written during the sabotage run**, so Python reuses the sabotaged bytecode
and the restored tree tests red. `find backend -name __pycache__ -type d -exec rm -rf {} +` between
cycles; verify restoration with `git diff`, not with a test result.

**Post-merge, on the pushed sha.** GitHub Actions on PR #152: `backend-tests` **pass** (6m33s),
`mobile-typecheck` **pass** (52s), `maestro-testid-lint` **pass** (8s). Merged `bc43b6f`; Render deploy
**live** on that sha (verified via the Render API, not by assumption). EAS build **124** (v1.15.0,
commit `bc43b6f`) finished and was **accepted by App Store Connect**; Apple processing pending.

**What is NOT proven.** The manual TestFlight checklist
([testflight-checklist.md](../docs/feedback/items/364-team-review-fixes/testflight-checklist.md), 13 steps)
is **UNRUN** — under [D-056](DECISIONS.md) it is the only runtime evidence this gets, and **nobody has
seen the corrected divergence beat on a device**. Step 8 (the sell list contains players you are LOW on)
is the whole change. Step 13 covers the Trends screen, which moved with the upstream fix.
---
## 2026-08-19h — `outlook.odds` LIT by operator override + its replacement guard (D-094, NOT MERGED, on `claude/team-review-analysis-plan-1f91e3`)

**Branch:** `claude/team-review-analysis-plan-1f91e3`, branched from `origin/main` `50e0451`. **Not pushed, not merged.**
Operator override 2026-08-19 (*"Outlook odds should be visible. Forward PPG cut. I waive maestro"*) flipped
`outlook.odds` `false` → **`true`**, reversing the same session's [D-093](DECISIONS.md) recommendation.
Decision: [D-094](DECISIONS.md). Docs: [docs/feedback/items/357-team-review/](../docs/feedback/items/357-team-review/status.md).

**What ran, and what it proves.**

| Gate | Result |
|---|---|
| `node mobile/tests/check-outlook-bands.js` (new) | **7 passed, 0 failed** against the real shipped sources |
| Sabotage proof — all six | **6 of 6 turned the guard red**, then sources restored and `git diff` verified empty |
| `config/features.json` JSON validity after the flip | parses; `outlook.odds == True` |
| CI pickup | automatic — `ci.yml` `mobile-typecheck` globs `tests/check-*.js`; **no CI edit needed** |

**The six sabotages, each with the assertion it was required to break:**

| Sabotage | Assertion that went red |
|---|---|
| `PLAYOFF_BAND_LIKELY_MIN` 0.65 → 0.70 | 1. thresholds are 0.65 / 0.35 |
| `likely: semantic.pos` → a raw hex literal | 2a. bands use the semantic tokens |
| `playoffBand`'s `p >= LIKELY_MIN` → `p > LIKELY_MIN` | 3. boundaries belong to the higher band |
| Add a `title_pct` read to the screen | 4. `title_pct` is never read |
| `OUTLOOK_WEEK6_PERCENT_ENABLED` false → true | 5. the bare percentage stays off |
| Strip the "unrenderable" warning from `api/league.ts` | 4b. league.ts warns title_pct is unrenderable |

**MERGED 2026-08-19 (PR #142, `6a3eab3`) — the gate set completed after this entry was first written.**
The original entry recorded pytest as *not run for this change*; that was true of the flag flip alone but
became false once the flip broke three tests. Corrected, final numbers on the merged sha:

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3525 passed, 1 skipped, 0 failed** |
| `npx tsc --noEmit` | **clean (exit 0)** — run after `npm ci`, which this worktree had been missing |
| Full structural glob, `for f in tests/check-*.js` | **61 passed, 0 failed** |
| `bash mobile/scripts/testid-lint.sh` | **OK** |
| Live verification | `/api/feature-flags` on Render serves `outlook.odds: true` |

**Three tests failed on the first attempt and all three were mine** — the flip is five touches, not one:
`test_flag_is_registered_and_defaults_off_everywhere`, `test_ships_off_route_is_unreachable_and_makes_no_sleeper_call`,
and `test_release_flags_mirror_features_json`. A peer session independently hit the same wall and flagged a
fourth trap I had not yet reached and verified myself before acting: `onboarding-v2.json` and `profiles-on.json`
are each asserted to differ from `release.json` by **exactly one key**, so moving `release` alone breaks both —
a failure that only surfaces on a full suite run, one cycle after the obvious fix.

**Sabotage proof for the rewritten kill-switch test:** removing the `is_enabled("outlook.odds")` guard from
`/api/league/outlook` made `test_flag_off_still_closes_the_route` fail (200 instead of 404); `backend/server.py`
restored and `git diff` verified empty.

**Evidence posture under D-056.** The operator **waived** the Maestro flow this lighting owed
(`NEXT.md` item 7) — it was already void when D-056 retired Maestro entirely. The guard above replaces it
as the standing structural net. **No backend test was run for this change and none was needed:** the flip
touches `config/features.json` only; the `/api/league/outlook` route, the pipeline and the serializer are
unmodified and were already covered by `backend/tests/test_outlook_odds.py` and `test_outlook_calibration.py`.

**What is NOT proven, and is owed.**

- **Nobody has seen the lit surface on a device.** The League-Summary outlook strip and section have shipped
  in every build since 2026-08-11 but have never rendered, because the flag was dark. The first TestFlight
  look is owed before this reaches users, and the operator's own league is the first read.
- **`meta.priced_slot_coverage` has never been rendered by any client.** In an IDP league (7 of 15 starting
  slots priced in the operator's FFV3) the bands are an offensive-core estimate presented as a whole-lineup
  one. Team Review's plan specs the caption; League Summary has none.
- **A preseason band can be confidently wrong for an individual league** — 2 of 6 backtested league-seasons
  lose to climatology outright, one with an ordering correlation of +0.022. Bands are immune to being
  *precisely* wrong, not to being wrong.

## 2026-08-19h — likes-you injector quality gates (D-096, NOT SHIPPED, on `fix/likes-you-quality-gates`)

**Branch:** `fix/likes-you-quality-gates`, branched from `origin/main` `50e0451`. **Not pushed, not merged.**
No feature flag: `trade.likes_you` already gates the surface. Knob-only, default **ON** at
`likes_you_gate_level = 2` (its OFF state, level 0, is the defect).
Scope + code-walk + checklist: [docs/plans/likes-you-quality-gates/](../docs/plans/likes-you-quality-gates/).

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q -p no:randomly` | **3540 passed, 1 skipped, 0 failed** |
| Baseline on the same branch point (`50e0451`), before any edit | **3524 passed, 1 skipped** — reproduced exactly, in a separate detached worktree |
| `npx tsc --noEmit` / `testid-lint.sh` / `check-*.js` | **n/a — ZERO mobile files touched.** Not run, and not claimed. |
| Maestro / simulator / `screens/` captures | n/a — retired by [D-056](DECISIONS.md). |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE. The 10-step operator TestFlight checklist + 2-step rollback rehearsal are UNRUN.** |

**Net +16 tests, all new** (`backend/tests/test_likes_you_gates.py`): the raw-vs-package unit split
(including a guard on the fixture itself, so the file cannot silently stop proving anything), the
gate-level ladder, `likes_you_gate_level = 0` as an exact revert, directional R1 in both directions,
`filler_ok` and its documented kill switch, the no-cap-slot-consumed semantics, that a gated-out
*existing* card keeps its organic deck position, that the card's bar values are the same objects the
gate compared, knob defaults, garbage-level clamping, `likes_you_min_user_gain == user_gain_epsilon`,
and a pin that R2/R3/R5 are deliberately NOT run.

**4 pre-existing tests touched, none loosened:**
- `test_trade_match_flow.py` ×3 (`..._floor_blocks_below_threshold_injection`,
  `..._floor_passes_above_threshold_injection`, `..._floor_knob_override_respected`) — the D-055
  floor block is **kept in full** and re-pinned to `likes_you_gate_level = 0` via `_inject_floor_deck`,
  so every assertion in it now stands guard over D-096's documented revert path instead of being
  deleted. Two docstrings updated to say which level they describe.
- `test_bakeoff_arm_a_golden.py` ×1 — the two new knobs added to `_PINNED_KNOBS`. Arm A is
  **not** pinned to level 0; the exclusion and its reason are recorded in
  [`scope-phase2.md`](../docs/plans/three-model-bakeoff/scope-phase2.md) § Excluded. `bakeoff_profiles.py`
  was **not** touched (a sibling session owns it).

### Prod measurement (READ-ONLY, `SET TRANSACTION READ ONLY`, SELECT only)

Population: **198 served likes-you impressions / 51 distinct cards**, one league, 2026-08-11 → 08-19
(`trade_impressions` for the asset ids, `deck_impressions.features_json` for prod's own logged bar
values). Per-card consensus values reconstructed from `player_value_history` daily snapshots +
`draft_picks.pool_value`; **reconstruction validated at median abs error 2.9** against 83 rows where
prod logged both the assets and the bar values, and it reproduces the audit's worst card to the
decimal (−6,019.4 on the recorded values).

| Option | Impressions surviving | Distinct cards | User-pays | Worst bar delta |
|---|---|---|---|---|
| **As served today** | 198 / 198 | 51 / 51 | **115** | **−5,571** |
| Package floor ≥ 0 only (level 1) | 83 (41.9%) | 16 | 0 | +32 |
| **Package floor ≥ 0 + directional R1 + `filler_ok` (level 2, SHIPPED)** | **83 (41.9%)** | **16** | **0** | **+32** |
| Package floor ≥ 0 + **blanket** R1 | 25 (12.6%) | 9 | 0 | +32 |
| Package floor ≥ 0 + blanket R1 + fairness ≥ 0.75 | 25 (12.6%) | 9 | 0 | +32 |
| Fairness ≥ 0.75 alone | 115 (58.1%) | — | 90 | −2,436 |
| R1 (blanket) alone | 120 (60.6%) | — | 95 | −2,136 |
| `filler_ok` alone | 191 (96.5%) | — | 108 | −5,571 |

Restricted to the 145 impressions served **after** the D-055 floor went live (2026-08-15), where the
old floor was already active: as served 145, user-pays **76**, worst **−4,672**; level 2 → **69
(47.6%)**, 15 distinct, user-pays **0**. Loosening the package floor to −500 was measured and
rejected: 74 survivors instead of 69, but 60 of them still show the user paying.

**The finding that shaped the design:** blanket R1 kills 58 of the 83 floor-surviving cards and
**58 of 58 of those kills are cards where the USER is the one being overpaid** — the largest a
**+6,325 one-for-one that the counterparty had already liked**. Directional R1 kills **0** of the 83.
On the post-D-055 slice the same shape holds: 55 of 69, all 55 user-favourable, 0 killed directionally.

### Sabotage tests (D-056 requirement) — all reverted

| Mutation | Result |
|---|---|
| Floor compared against the raw delta again (undo the unit fix) | 2 failed |
| Directional guard `g > r` removed (blanket R1) | 4 failed |
| `if gate_level <= 0:` → `if False:` (level 0 stops reverting) | 4 failed, incl. all 3 re-pinned D-055 tests |
| `filler_ok` call replaced with `return True` | 1 failed |
| Reverted | 49 passed |

**Files touched:** `backend/server.py`, `backend/trade_service.py` (`_DEFAULT_CFG` only, +14 lines,
no logic), `backend/tests/test_likes_you_gates.py` (new), `backend/tests/test_trade_match_flow.py`,
`backend/tests/test_bakeoff_arm_a_golden.py`, `docs/config-reference.md`,
`docs/plans/three-model-bakeoff/scope-phase2.md`, `docs/plans/likes-you-quality-gates/` (new),
`living-memory/{DECISIONS,LLD,TEST_LEDGER,CHANGELOG,NEXT,HANDOFF}.md`.

## 2026-08-19h — The "balanced trade" claim gets a fairness gate (audit bug 2, NOT SHIPPED, on `fix/balanced-claim-fairness-gate`)

**Branch:** `fix/balanced-claim-fairness-gate`, worktree off a freshly fetched `origin/main` **`50e0451`**.
**Not pushed, not merged.** Ships **unflagged** — a flag's OFF state here would re-enable a false
statement (see [D-097](DECISIONS.md)).
Scope: [docs/plans/consensus-balance-claim/scope.md](../docs/plans/consensus-balance-claim/scope.md)
(code-walk proof §7, TestFlight checklist §8).

| Gate | Result |
|---|---|
| `mobile/tests/check-*.js` (all) | **61 / 61 passed, 0 failed** (60 pre-existing + 1 new) |
| `mobile/tests/check-consensus-balance-claim.js` (new) | **36 / 36 assertions passed** |
| `mobile/scripts/testid-lint.sh` | **OK, exit 0** |
| `npx tsc --noEmit` (mobile) | **1 error, pre-existing + environmental, NOT from this diff** — `ImportRankingsSheet.tsx(11,33): TS2307 Cannot find module 'expo-document-picker'`. `mobile/node_modules` is **empty in the main checkout**, so it was symlinked from `ftf-test-clone`, whose install predates that dependency. **Proven, not assumed:** stashing this branch's `.tsx` + `package.json` edits and re-running produced byte-identical output. My diff adds **zero** type errors. |
| `pytest backend/tests -q` | **3524 passed, 1 skipped, 0 failed** — insurance only; **zero backend files touched** (`git status -- backend/` empty). No route, schema, migration, or engine line moves. |
| Maestro / simulator | n/a — retired by [D-056](DECISIONS.md). No flow authored, none run, no `screens/` capture. |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE. The scope §8 operator TestFlight checklist is UNRUN.** |

**Prod measurement (read-only, `SET TRANSACTION READ ONLY`, SELECT only, `deck_impressions`).**
Reproduces the audit's 805 / 7,282 exactly; the denominator moved to 7,293 because eleven more cards
were served between the audit snapshot and this run.

| Metric | Value |
|---|---|
| Consensus cards served | **7,293** |
| …carrying a non-NULL `fairness_score` | **7,293 (100%)** — this is the proof the field reaches the clients, not an inference |
| …**below the app's own 0.75 bar** while claiming "balanced" | **805 (11.04%)** |
| …below the 0.50 generation floor | **0** |
| Fairness distribution | min **0.5010**, p10 **0.7302**, p25 0.7890, p50 **0.8590**, p90 0.9750, max 1.0000 |

**Sabotage test — the check is only evidence if it goes red without the fix.** Four independent
reverts, each applied, measured, restored; final `git diff --stat` byte-identical to pre-sabotage:

| # | Sabotage | Result |
|---|---|---|
| S1 | Revert the gate — `balanced` forced `true`, i.e. always claim balanced | **RED, 14 failures**, exit 1 |
| S2 | Flip the fail-safe — unknown fairness returns the balanced claim | **RED, 7 failures**, exit 1 |
| S3a | Fix mobile, leave web stale — web ternary collapsed to the unconditional string | **RED, 5 failures**, exit 1 |
| S3b | **The subtle one** — web keeps its gate but *drifts the wording* (`— no rankings on file.`) | **RED, 2 failures**, exit 1 |
| S4 | Re-inline the literal into `TradeCard.tsx` JSX, bypassing `consensusNote` | **RED, 2 failures**, exit 1 |
| S5 | Re-add value prose below the bar (the copy the operator struck) | **RED, 12 failures**, exit 1 |
| — | Restore all | **GREEN, exit 0**, diff byte-identical to pre-sabotage |

**What the 36 assertions pin**, rather than "the string changed": the gate at the real band edges
(0.75 → balanced; 0.7499, 0.7302 = prod p10, 0.55, 0.501 = prod min → **truncated**); the fail-safe
direction for `undefined`/`null`/`NaN`/`±Infinity`; that the function yields **exactly two** distinct
strings and only the at-or-above-bar one contains the word "balanced"; that **every** state keeps the
`hasn't ranked players yet` explanation (the fix removes the claim — it does **not** hide the line);
that **no value prose is re-added** below the bar (`priced from public values` / `even split` /
`leans` must appear nowhere — this is the assertion that holds the operator's 2026-08-19 amendment in
place); that **no** state names a winner; that all **four** spellings of 0.75 agree (`NORMAL_LOW`,
`FAIRNESS_ON_THRESHOLD`, `CONSENSUS_BALANCED_MIN`, and web's `FAIRNESS_BALANCED_MIN` parsed back out
of `web/js/app.js`).

**The cross-client half is the most valuable part and is built to survive rewording.** §3 does not
look for remembered strings: it **extracts** web's `prefix` literal and both tooltip templates from
`web/js/app.js`, expands them, and compares the results **byte for byte against the mobile module's
own output**. That is why S3b — web still gating correctly but saying something different — goes red
at all. Those assertions are deliberately **not** wrapped in an `if (extraction succeeded)` guard: a
failed extraction means web no longer has the shape the parity depends on, which is itself the
divergence being guarded against, so it must fail rather than skip.

**Note on `mobile/package.json`:** the only edit is registering
`"test:consensus-balance-claim": "node tests/check-consensus-balance-claim.js"`. No dependency added,
removed, or bumped — `living-memory/DEPENDENCIES.md` needs no entry.

**Operator amendment, same day.** The first revision of this fix put replacement copy below the bar
(*"priced from public values, not an even split"*). The operator struck it — *"We don't need to add
the copy suggested.. We already have already features that provide the value summary/snap assessment
on trade valuation"* — and is right: `TradeValueBar` already renders `favors`/`gap` on these cards.
The sub-threshold line now **truncates** to `This league-mate hasn't ranked players yet.` and stops.
The gate, the fail-safe, the constant and the cross-client parity are unchanged; the replacement prose
is gone from both clients and from the module, and S5 exists to keep it gone. Directional wording
("leans your way"/"leans theirs") is settled as duplication and should not be re-opened.

**Not tested, and deliberately so:** `tradePresentation.counterpartyStatement()` asserts partner
interest unconditionally (same defect class) but is dark behind `trades.presentation_v2: false` and
belongs to a surface under separate review. Recorded in D-097 and scope §9; **not** touched.

## 2026-08-19h — Landability challenger, bake-off arm D (D-095, NOT SHIPPED, on `feat/bakeoff-arm-a-challenger`)

**Branch:** `feat/bakeoff-arm-a-challenger`, branched from `origin/main` `50e0451`. **Not pushed, not merged.**
Spec: [docs/plans/landability-challenger/PRD.md](../docs/plans/landability-challenger/PRD.md) §5 Track A (A1–A4).
No feature flag: `trade.bakeoff` already gates the fan-out and `bakeoff_serve_interleaved` stays **0**, so the arm is dark.

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3554 passed, 1 skipped, 0 failed** |
| Baseline re-measured on the same branch point before any edit | **3524 passed, 1 skipped** — reproduced exactly |
| PRD A4 done-when set | `test_bakeoff_challenger.py test_bakeoff_arm_a_golden.py test_bakeoff_composition.py test_bakeoff_runner.py test_user_gain_gate.py` — **120 passed** (the sabotage matrix ran a wider set including `test_bakeoff_serving.py`: 148) |
| `npx tsc --noEmit` / `testid-lint.sh` / `check-*.js` | **n/a — ZERO mobile files touched.** Not run, and not claimed. |
| Maestro / simulator / `screens/` captures | n/a — retired by [D-056](DECISIONS.md). |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE, and none is owed** — the arm generates and logs but is never served (PRD G7). The dark contract is asserted in tests instead: `test_the_challenger_generates_and_logs_but_is_never_served`. |

**Net +30 tests** — 25 new in `backend/tests/test_bakeoff_challenger.py`, 5 new in
`test_bakeoff_composition.py` / `test_bakeoff_serving.py`.

**The load-bearing invariant — arm B is byte-identical — is PROVED, not asserted.**
`test_bakeoff_challenger.py` carries two goldens captured by checking out `origin/main`
`50e0451` into a second worktree, copying the test file in, and running its capture mode
there: code that had never heard of the three new knobs. Today's live-defaults run must
reproduce both byte for byte. Surfaces: a full `generate_trades` deck (covers dedup, deck
caps, v2 orchestration) and `_generate_consensus_for_pair` called directly and uncapped —
the latter because deck-assembly caps hide most of the consensus path, so measured through
a deck alone the two consensus knobs would read as inert while being perfectly alive.
Backed by `test_every_new_knob_is_inert_at_its_default`, which sets each knob *explicitly*
to the value `_DEFAULT_CFG` already carries — that catches a knob inert only because some
other guard skips its code path, which a golden cannot distinguish.

**Arm A is byte-identical too**, per PRD N1: `MODEL_A_PROFILE`, `model_a()`,
`MODEL_A_REFERENCE_SHA` and the golden's captured deck are unchanged. The only edit to
`test_bakeoff_arm_a_golden.py` is five names added to `_PINNED_KNOBS` plus one sentence of
remedy text; its 10 tests pass unmodified.

**Code-walk proof** (file:line on this branch):

| Lever | Site | Live identity |
|---|---|---|
| `user_elo_shrink` | `trade_service.py:1339` — `if confidence is None or _c("user_elo_shrink") <= 0: return dict(user_elo)` | 1.0 ⇒ the early return never fires; the blend below is untouched |
| `consensus_both_ways` | `trade_service.py:5086` — `if not _both_ways and rv - gv < _c("user_gain_epsilon")` | 0.0 ⇒ `_both_ways` False ⇒ the original predicate, unchanged |
| 1-for-2 loop | `trade_service.py:5168` — `if _both_ways and len(cards) < max_cards` | 0.0 ⇒ loop never entered |
| `consensus_fairness_floor` | `trade_service.py:4998` (`_thr = max(requested, floor)`), read at `:5117` | 0.0 ⇒ `_thr is fairness_threshold` |
| profile entry point | `bakeoff_profiles.py` `model_challenger()` — `_cfg_override(MODEL_CHALLENGER_PROFILE)`, **no** `r4_bypass` | inert until entered |
| fan-out | `bakeoff_runner.py` `run_bakeoff` `elif arm == ARM_CHALLENGER:` — snapshot taken INSIDE the overlay | arm B's branch untouched |
| roster | `bakeoff_runner.arm_roster()` — `ALL_ARMS` filtered by four include knobs | `bakeoff_include_challenger` = 0 restores the pre-D-095 roster |

**Import-time binding checked, not assumed.** `trade_optimizer.py:51` and
`trade_gen_v2.py:112` import `_c` and `_shrink_user_elo` **by value**. All three knobs
are read *inside* existing function bodies rather than by wrapping or rebinding them, so
every bound site sees the change — the class of no-op that cost an audit agent a
perfect-zero measurement on a gate firing 1.17M times cannot occur here.

**Sabotage-tested: 13 deliberate breakages, 13 caught.** Each mutation applied, the A4
pytest set run, the mutation reverted:

| # | Sabotage | Caught by |
|---|---|---|
| 1 | `user_elo_shrink` ignored (shrink always off) | arm-B goldens, both shrink tests, **arm-A golden**, `test_user_gain_gate` Maye-for-Dart repro (v2 + v3) |
| 2 | sign test dropped for every arm | both arm-B goldens, `test_live_never_emits_a_card_the_user_pays_for` |
| 3 | both-ways knob never read | `test_both_ways_emits_the_user_pays_direction`, `test_one_for_two_exists_only_under_both_ways` |
| 4 | floor knob never read | 3 floor tests |
| 5 | floor OVERRIDES instead of tightening | `test_the_floor_only_ever_tightens` |
| 6 | 1-for-2 enumeration removed | `test_one_for_two_exists_only_under_both_ways` |
| 7 | overlay entered for arm B as well | 7 tests incl. both config-snapshot tests |
| 8 | `model_challenger` gains arm A's R4 bypass | `test_model_challenger_does_not_bypass_r4` |
| 9 | a challenger knob leaks into `MODEL_A_PROFILE` | **arm-A golden**, `test_the_two_profiles_do_not_collide`, `test_model_a_still_sees_the_live_identity_for_the_new_knobs` |
| 10 | tier ladder left uncompressed | both ladder tests |
| 11 | challenger dropped from the default roster | 8 tests across composition/serving/challenger |
| 12 | challenger stops being an engine arm (loses its consensus group) | 3 tests incl. the dark-mode group assertion |
| 13 | a new knob vanishes from `_PINNED_KNOBS` | the arm-A inventory guard **and** its cross-check |

**Known gap:** Track C's `measurement.md` (the offline four-cell count) is not written by
this work — C1 was run elsewhere and its numbers (0.75 both-ways = 200.5% of the one-way
baseline, 61.2% user-pays, damage capped at 25.0%) are quoted in the profile and
config-reference on that authority, not re-derived here.

---
## 2026-08-19g — Phantom draft-pick years: the league pick horizon (#355, NOT SHIPPED, on `fix/pick-horizon`)

**Branch:** `fix/pick-horizon`, branched from `origin/main` `7462c23`. **Not pushed, not merged.**
Flag `picks.league_horizon` default **ON** (its OFF state is the defect, so shipping it off ships nothing).
Scope + evidence + code-walk + checklist: [docs/feedback/items/355-phantom-pick-years/](../docs/feedback/items/355-phantom-pick-years/).

| Gate | Result |
|---|---|
| `python3 -m pytest backend/tests -q` | **3496 passed, 1 skipped, 0 failed** |
| Baseline on the same branch point, before any edit | **3480 passed, 1 skipped** — reproduced exactly |
| `npx tsc --noEmit` / `testid-lint.sh` / `check-*.js` | **n/a — ZERO mobile files touched.** Not run, and not claimed. |
| Maestro / simulator / `screens/` captures | n/a — retired by [D-056](DECISIONS.md). |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE. The 10-step operator TestFlight checklist is UNRUN.** |

**Net +16 tests, all new** (`backend/tests/test_pick_horizon.py`). Two layers: the pure helper
`draft_status.pick_horizon` (pre-draft window, post-draft roll-forward, the always-3-classes
invariant, existence-proof widening, the widening cap, garbage-input tolerance, unknown-horizon
degradation) and the grid builder `sync_draft_picks` (the operator's exact case, the post-draft case
where 2029 is *kept* because it is real, the kill switch restoring the old window, a reported far
pick pulling its whole class in, a "never widens past the legacy ceiling" safety bound, and the
#220 empty-roster guard surviving the change).

**5 pre-existing tests updated, each a deliberate encoding of the OLD 4-class window** — not
loosened to make the change pass:
- `test_owned_picks.py` ×4 — grid sizes written as `2 rosters × 4 seasons × 4 rounds = 32`. Now
  derived from `PICK_HORIZON_CLASSES` (`_GRID = 2 * PICK_HORIZON_CLASSES * 4` = 24) so the rule has
  exactly one home, plus an added explicit assertion that the classes are 2026/2027/2028.
- `test_seed_ui_test_db.py` ×1 (3 fixtures) — the flag-map mirrors. `release.json` must equal
  `config/features.json` key-for-key, and `onboarding-v2.json` / `profiles-on.json` are asserted to
  be "release plus exactly one differing key", so all three needed the new flag.

**Prod measurement (read-only, `SET TRANSACTION READ ONLY`, SELECT only)** — the numbers in
[evidence.md](../docs/feedback/items/355-phantom-pick-years/evidence.md): **339 of 2,651 served
cards (12.8 %; 23.2 % of pick-bearing cards)** carried an out-of-horizon pick, 360 mentions, all
2029, all in the operator's league. **12.9 % of the 845 recorded like/pass outcomes** landed on one,
skewed 6.7 % of likes vs 15.8 % of passes vs 21.4 % of not-interested. **The 2026-08-16 → 08-19
preference data is contaminated** and must not be cited as a clean propensity or bake-off baseline.

**What this does NOT prove.** The tests stub the Sleeper reads, so nothing here demonstrates the
horizon against live platform data — that is exactly what the TestFlight checklist is for, and it
is unrun. The rule itself was validated out-of-band by direct probes of the public Sleeper API
across every league in prod, recorded in `evidence.md`, including a positive 2029 reading on a
post-draft league so the rule is pinned at both ends rather than inferred from an absence.

## 2026-08-19g — Current-year pick slot labels (D-090); "2026 1.08", not "2026 1st"

**Branch:** `feat/pick-slot-labels`, worktree off a freshly fetched `origin/main` **`7462c23`**.
**Not pushed, not merged.** Flag `picks.slot_labels` ships **ON**.
Scope: [docs/plans/pick-slot-labels/scope.md](../docs/plans/pick-slot-labels/scope.md) (code-walk proof is §7,
TestFlight checklist §8).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` (branch) | **3508 passed, 1 skipped, 0 failed** |
| `pytest backend/tests -q` (clean `origin/main` `7462c23`, pristine worktree) | **3480 passed, 1 skipped** — the baseline, re-measured rather than assumed |
| Delta | **+28**, all in the new `backend/tests/test_pick_slot_labels.py`. No pre-existing test changed behaviour. |
| `mobile/scripts/testid-lint.sh` | **OK, exit 0** |
| `npx tsc --noEmit` (mobile) | **NOT RUN — typescript is not installed in `mobile/node_modules` on this machine** (`node_modules/.bin/tsc` absent in the main checkout too, so this is an environment gap and not a worktree artefact). The diff touches **zero** `.ts`/`.tsx` files, so it cannot move the typecheck; CI runs it on the pushed sha. Stated rather than claimed. |
| `mobile/tests/check-*.js` | not run and none added — the mobile diff is empty (see below) |
| Maestro / simulator | n/a — retired by [D-056](DECISIONS.md). |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE. The scope §8 operator TestFlight checklist is UNRUN.** |

**What the 28 new tests actually pin**, rather than "the label has a dot in it". Each of the two named
sabotages has a trap:

- **S1 — a slot invented where none exists.** Sleeper's pre-draft payload returns
  `slot_to_roster_id = {"1":1 … "12":12}`, an identity map that reads as a real order and is not one
  (the D5 rule in `draft_board_service`). `test_identity_slot_to_roster_is_never_read` hands the
  resolver that perfect identity map next to a NULL `draft_order` and demands `None`. The fixture's
  real order is deliberately **not** the identity — roster 1 drafts 8th — so anything falling back to
  the roster id labels `1.01` and fails every `1.08` assertion in the file.
- **S2 — a slot on a season that has no order.** `test_future_season_never_resolves_a_slot` pins `None`
  for 2027/2028/2029 *and* 2025; `test_future_year_keeps_its_round_ordinal` pins the literal strings
  `"2027 1st"` / `"2029 3rd"`.
- **The bright line.** `test_no_price_moves_with_or_without_an_order` asserts `pool_value` is not
  mutated and that every slot of a round still prices identically — the change must not creep into
  pricing (that question is [Q-023](OPEN_QUESTIONS.md)).
- **The kill switch.** `test_route_is_byte_identical_with_the_flag_off` pins a literal label map with
  the flag off, and `test_flag_off_never_reads_the_order` patches `load_draft_slot_order` to raise —
  a disabled feature must short-circuit **before** the read, not after.
- Plus: snake even-round reversal matching `PickAssignmentScreen.draftPosition` exactly, refusal on
  `reversal_round`, per-league caching (one lookup, not one per pick), degradation to generic labels on
  a raising DB, and that a slot label introduces no `' + '` (which `TradesScreen.tsx:3804` splits on).

**One pre-existing test was deliberately edited**, and it is the containment guard for this area:
`test_pick_assignment.py::test_w3_02_ast_only_sanctioned_call_sites_name_source`. It AST-enumerates every
`load_draft_picks` call site and fails on any unsanctioned `source=` opt-in — which is exactly how an
eighth site is supposed to get **decided** rather than silently added (its own docstring says so). The new
`_assigned_slot_order` is registered in `_SANCTIONED_SOURCE_CALLERS` (the assignment surface), **not** in
the seven engine sites, with the reasoning inline: it prices nothing, and numbering must not follow a
pricing flag or a trade card and the assignment screen would disagree about what "1.05" means.

**Verified against real data, not only fixtures** (2026-08-19):
- Live Sleeper read for league `1312140920132497408`: the resolver's `draft_order` × rosters composition
  reproduces Sleeper's own `slot_to_roster_id` **exactly, 12/12** — and the D5-compliant path is the one
  used, so agreement is corroboration rather than construction. The operator's own 2026 1st is the **1.08**.
- Prod Postgres, **read-only** (`SET TRANSACTION READ ONLY`, SELECT only): current-year picks appear in
  **469 of 2,651 served deck cards (17.7 %)**, 451 of them in that one league; only **3 of 12** leagues
  hold 2026 picks at all, and all three are `draft_status = not_drafted` (#228 deletes the rows at draft
  completion).

**Measured but NOT built** — what pricing by slot would do, so [Q-023](OPEN_QUESTIONS.md) can be decided on
evidence: against DynastyProcess's published 2026 curve a 1.01 is **+130 %** and a 1.12 **−61 %** versus our
flat 2117 (**5.9×** inside one round); on the operator's league that moves **48 of 48** current-year pick
values and **38 of 48** tier badges. Not shipped, not prototyped — computed with the shipped functions
against the checked-in `dp_values_picks_2026-08-06.csv`.

**Mobile evidence waived, with the reason:** the mobile diff is **empty** — `git status` shows zero files
under `mobile/`, `web/` or `extension/`. Every client renders the server's `label`/`name` verbatim
(`InLeagueCalculator.tsx:219`, `LeagueSummaryScreen.tsx:2148`, `MatchesScreen.tsx:1408/1414/1440/1446`,
deck cards via `give_players[].name`), so there is no client-side owned-pick formatter to pin structurally.

---
## 2026-08-19e — Settings IA: hub + second-level pages, sheet → page (SHIPPED to main + TestFlight)

**Branch:** `feat/settings-ia-hub`, rebased from `ecdbcb3` onto `origin/main` `28c12a0` and merged.
Flag `account.settings_hub` stays **OFF** (default false).
Plan + scope: [docs/plans/settings-ia-hub/](../docs/plans/settings-ia-hub/). Code-walk proof:
[code-walk-proof.md](../docs/plans/settings-ia-hub/code-walk-proof.md).

| Gate | Result |
|---|---|
| `npx tsc --noEmit` (mobile) | **exit 0** |
| `mobile/scripts/testid-lint.sh` | **OK, exit 0** |
| `mobile/tests/check-*.js` (whole suite) | **60 passed, 0 failed** post-rebase (59 pre-rebase; main added one) — includes the 3 new settings checks |
| `pytest backend/tests -q` | **3480 passed, 1 skipped, 0 failed** (post-rebase, final). Earlier in the session the same branch ran 3399/5-failed on base `ecdbcb3`; all 5 were pre-existing and `main` repaired them in `70d1f3b`, so the pre-ship gate is clear. |
| Maestro / simulator | n/a — retired by D-056. Replaced by the 3 structural checks + the code-walk proof. |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| **Runtime evidence** | **NONE. The plan §9 operator TestFlight checklist is UNRUN.** |

**New structural checks: 3** (`npm run test:settings-ia | test:settings-nav | test:settings-testids`).
- `check-settings-ia.js` — encodes plan §4's migration map: 12 section modules → owning page, 34 rows
  → owning module. Catches an orphaned module, a duplicated one, a row deleted from *inside* a
  surviving module, and the four IA moves.
- `check-settings-nav.js` — no settings route carries `presentation: 'modal'`; all 8 have a
  `HeaderBack`; all 8 page modules mount `FeedbackFAB aboveTabBar={false}`; 8 deep-link paths resolve.
- `check-settings-testids.js` — 11 shipped ids + 2 templated prefixes still resolve **inside
  `src/screens/settings/`** (not merely somewhere under `src` — the legacy screen would otherwise
  satisfy the search by itself); 9 new ids present; `settings.close-btn` gone from `src` **and** from
  `.maestro`.

**The checks were verified by mutation, not by reading.** Independently re-run at orchestration:
restoring `presentation: 'modal'` on the `Settings` route, swapping the Sign out / Delete account
render order, and renaming `settings.espn-disconnect` each FAIL with an accurate message. The modal
parse walks the TS AST per `<Stack.Screen>` and self-tests that it still *detects* the modal on
`FeedbackInbox` / `SleeperConnect`, so a broken walk fails loudly instead of passing forever.

**Destructive-path copy verified byte-for-byte** against `origin/main` by brace-matched extraction of
six functions (three platform disconnects, `confirmDeleteAccount`, `performDeleteAccount`,
`handleExportData`). Zero drift. Delete account keeps both `Alert` stages and both destructive
markers. An earlier fixed-line-window comparison produced false drift reports by bleeding into
adjacent functions and was discarded — the brace-matched result is the one recorded.

**Pre-existing red on `origin/main` (blocks the pre-ship gate for EVERY branch, not just this one):**
`test_seed_ui_test_db::test_release_flags_mirror_features_json` (`trade.bakeoff` set true in
`config/features.json` by `ecdbcb3` but left false in `backend/tests/fixtures/flags/release.json`),
three in `test_suggestion_telemetry.py`, and
`test_trade_decision_idempotency::test_re_posted_swipe_writes_exactly_one_set_of_swipe_decisions`
(expects Elo 1502.0 ± 0.001502, obtains 1500.0 — a re-posted swipe not applying its rating update).
Confirmed pre-existing by stashing this branch's flag change and re-running. This branch DID add the
one missing mirror entry its own flag required.

**The rebase onto `28c12a0` silently dropped phase 0, and the gate is what caught it.** `git rebase`
reported the commit as empty mid-run; it carried all 15 mobile source files plus the flag
registration. `tsc` then failed with 22 `TS2307` module-not-found errors, and the flag was left
HALF-registered — in `onboarding-v2.json`, `profiles-on.json` and `config-reference.md`, absent from
`features.json`, `FLAG_KEYS` and `release.json`. That combination would have shipped a dead flag and a
red mirror test. Recovered in `9a04ebc`: the mobile tree restored byte-identical from `4ea6895`, the
three flag files re-applied surgically (main changed them in the same window, so a wholesale restore
would have reverted 1.15.0's flag work). Parity re-checked by file set — 54 files before, 54 after,
no drops, no extras.

**A regression this branch caused, caught by running the full suite rather than trusting an earlier
run.** Registering `account.settings_hub` initially mirrored it into `backend/tests/fixtures/flags/release.json`
only. Two other fixtures — `onboarding-v2.json` and `profiles-on.json` — are asserted to be
**key-set-equal** to release (`assert set(release) == set(profiles_on)`, and the onboarding equivalent),
so the single new key broke both: 5 failures became 7. Fixed by mirroring the key into those two
fixtures as well. `all-on.json` (42 keys), `release-300.json` and `release-espn-send-off.json` (162 keys,
already missing 10 other keys) are deliberately NOT key-set-equal and no test requires them to be — they
were left alone rather than "fixed" into scope creep.

The lesson worth keeping: a new flag key is not registered until every fixture that asserts key-set
equality with `release.json` carries it. `git grep -l "account.settings_v2" backend/tests/fixtures/`
finds them.

**Correction to this branch's own record:** the phase-0 commit message claimed the full-screen
`prefsQuery.isLoading` gate "is gone". That is true only on the hub path. The gate is still live at
`SettingsScreen.tsx:746` on the flag-off flat list, which phase 0 never touched; it dies with the
legacy branch in phase 4. Corrected in the phase-1 commit message and in the code-walk proof.

---

## 2026-08-19d — Placement tier clamp (D-085); a placement now bounds PRICING, not just voting

**Branch:** `feat/placement-tier-clamp`, from `origin/main` `a130dfc`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/placement-tier-clamp/scope.md](../docs/plans/placement-tier-clamp/scope.md). Code-walk: [code-walk.md](../docs/plans/placement-tier-clamp/code-walk.md). Decision: [D-085](DECISIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3441 passed, 1 skipped (baseline at `a130dfc`) | **3463 passed, 1 skipped, 0 failed** (+22 new, all in `test_placement_tier_clamp.py`) |
| `tsc --noEmit` / `testid-lint` | n/a — **zero files under `mobile/` changed** | unaffected |
| Bake-off arm-A golden + knob-inventory guard | 34 passed | 34 passed; new knob pinned to 0 in `MODEL_A_PROFILE`, **no golden re-capture needed** (kill value is an identity on the valuation) |
| Kill-switch identity | — | `placement_tier_clamp = 0` reproduces the pre-D-085 blend for a whole populated board (`test_knob_at_zero_is_byte_identical`) |

**Evidence under D-056** (no Maestro, no simulator, no captures): 22 new unit tests plus a
written code-walk citing file:line for every hop of the path, including a
**gate-isolation proof by what the gate reads** — the range-overlap fairness gate
prices `gvals`/`rvals` from `seed_value` (consensus), so `user_value` never reaches
it and the clamp is structurally invisible to every gate. `_value_uncertainty`'s
placement-blindness is asserted via `inspect.signature`, so a future edit that adds
the parameter fails CI rather than sliding through.

**Band constants are read live from `tier_config.json`, not hardcoded.** D-084 moved
`second`.min 1400 → 1370 and `third`.max 1395 → 1365 while this work was in flight;
an earlier draft had hardcoded the old numbers and would have asserted the wrong
thing silently. `test_band_constants_match_the_shipped_config` guards the guard.

**What was measured, on prod, read-only (`SET TRANSACTION READ ONLY`, SELECT only).**
The operator's real board was rebuilt through the actual `RankingService` — 625-player
pool seeded from the latest `player_value_history` snapshot, all 624 stored
`tier_overrides` pins re-applied with stamps, all 1,679 in-pool `swipe_decisions`
replayed via `replay_from_db` — then `comparison_counts()` and `_shrink_user_elo` were
run with and without the clamp under the live configuration (`pin_tier_bounded=1.0`,
`pin_exclude_comparisons=1.0`, `shrink_pseudocount=4.0`).

- **Davante Adams, the driving case: priced 1490.8 (`second`) → 1365.0 (`third`)**, back
  into the tier he was placed in. Band [1280, 1365], consensus 1526.
- **The mechanism is not "he was barely compared".** Adams has **36 distinct comparison
  opponents** and is among the most-voted players on that board, but his live
  `comparison_counts` is **1**, because `pin_exclude_comparisons` (F1) correctly discards
  votes a tier-bounded player's band edge swallowed. `w = 0.2` ⇒ the engine priced him
  **80 % consensus** despite 36 votes and an explicit placement. An estimate from raw
  distinct-opponent counts gives `n = 36`, `w = 0.9`, and wrongly concludes the clamp is
  a no-op here. **Only the replay reveals this** — recorded so the shortcut is not retried.
- **Whole board: 162 of 615 banded placements (26 %) move**, median 32 Elo, max 343
  (Travis Hunter). Largest movers are `n = 0` players whose blend was pure consensus.
- **Placements are not rare:** 5 of 18 users have them; the three active boards carry
  547 / 644 / 737 each.

**Negative finding — the `basis: consensus` framing does not hold.** The work was
motivated by "every one of the 40 most recently served cards came back `basis:
consensus`". Prod on 2026-08-19: last 40 impressions = **30 consensus / 10 divergence
(25 %)**; last 400 = 7.8 %; all time = 12 % (1,263 of 10,550). Divergence *is* being
found. Further, `basis` is decided at `trade_service.py:4105` by
`member.has_rankings and member.elo_ratings` — a property of the **opponent's** board,
evaluated before any user value is read — or by the zero-divergence fallback at `:4175`.
The clamp can only influence the second, and the impressions table does not record which
branch fired. **This clamp must not be reported as the cause of the consensus share.**
Recommended follow-up: instrument the fallback to distinguish "opponent unboarded" from
"divergence path came back empty".

**Not covered:** `bakeoff_runner.gen_v2_cards` never passes `placements`, so the clamp is
inert on every bake-off arm and the bake-off cannot currently measure this feature.
Left that way deliberately — two sibling agents were editing `bakeoff_runner.py`
concurrently. `MODEL_A_PROFILE` pins the knob to 0 regardless.

## 2026-08-19f — Bake-off lane reallocation (D-086); the outlook lane that filled zero

**Branch:** `fix/bakeoff-outlook-lane`, from `origin/main` `a130dfc`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/three-model-bakeoff/scope-outlook-lane.md](../docs/plans/three-model-bakeoff/scope-outlook-lane.md). Decision: [D-086](DECISIONS.md). Follow-up: [Q-020](OPEN_QUESTIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3441 passed, 1 skipped (baseline at `a130dfc`) | **3448 passed, 1 skipped, 0 failed** (+7 new) |
| `tsc --noEmit` / `testid-lint` | n/a — **zero files under `mobile/` changed** | unaffected |
| Bake-off arm-A golden + knob-inventory guard | 10 passed | 10 passed; new knob added to `_PINNED_KNOBS` and excluded from `MODEL_A_PROFILE` (composition, not generation — row added to `scope-phase2.md`), **no golden re-capture needed** |
| `test_bakeoff_composition.py` | 35 passed | **38 passed** (7 added, 3 rewritten to pin the pre-D-086 path under `reallocate=False`) |

**What was measured, on prod, read-only (`SET TRANSACTION READ ONLY`, SELECT only).** All 18
`bakeoff_runs` rows of 2026-08-19 — 54 group-runs, 527 pooled cards, 3 leagues.

| Group | cards/run | `value` | `window` | `(none)` | window share | outlook slots filled |
|---|---:|---:|---:|---:|---:|---:|
| `current_divergence` | 1.3 | 23 | **0** | 0 | **0.0 %** | 0 / 90 |
| `current_consensus` | 22.5 | 291 | 114 | 0 | 28.1 % | 63 / 90 |
| `gen_v2` | 5.5 | 83 | 16 | 0 | 16.2 % | 16 / 90 |
| **all** | 29.3 | 397 | **130** | **0** | **24.7 %** | 79 / 270 |

The single number that decides the diagnosis: **`(none)` is 0 in all 54 group-runs**, so every
pooled card carried a lane and the label plumbing is healthy — `window` is 24.7 % of live supply,
not ~0 %. The zero-fill is a quota/supply result, not a missing field. Deck arithmetic per run:

| | cards/run |
|---|---:|
| target (`bakeoff_deck_limit`) | 30.0 |
| supply generated | 29.3 |
| within-group capacity `Σ min(pool, 10)` | 16.0 |
| **served (before)** | **13.8** |
| **served (after D-086)** | **16.0** |

Counterfactual replay of the same 54 pools through candidate quotas — the arithmetic that
rejected a re-tuned split in favour of reallocation:

| `bakeoff_group_value_slots` | fixed quota | with reallocation |
|---|---:|---:|
| 5 (today) | 13.8 /run | **16.0** /run |
| 6 | 14.9 | 16.0 |
| 7 | 15.6 | 16.0 |
| 8 | 15.7 | 16.0 |
| 10 | 15.0 | 16.0 |

**Evidence per D-056 (no simulator, no Maestro):** 7 new pytest cases in
`backend/tests/test_bakeoff_composition.py` — the core claim, the no-op case, both reallocation
directions, the supply ceiling, composition with `bakeoff_fill_policy`, end-to-end knob wiring,
and a regression pinned to the **real measured 10:33 pools** (7/0, 10/0, 13/3 → 18 cards before,
27 after). Plus a file:line-cited code-walk proof in §6 of the scope block, covering the two
properties no unit test can state directly: that `res.short` is written before any reallocation
statement and never rewritten, and that reallocation slices only from the receiving lane's own
bucket, so every `lane_slot` stamp remains a true statement about its card.

**Not verified at runtime, and it does not need to be:** the bake-off is dark
(`bakeoff_serve_interleaved` 0.0, **not changed by this work**), so no served deck moves for any
user. The next organic deck writes the proof itself — `filled.value + filled.outlook` should equal
`min(pool total, 10)` per group in `bakeoff_runs.groups_json`, with `short` unchanged in character.

## 2026-08-19d — Arm C (`gen_v2`) per-stage kill counts; the forfeit was a supply fact, not a bug

**Branch:** `fix/armc-gen-v2-forfeits`, from `origin/main` `a130dfc`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/three-model-bakeoff/scope-arm-c-diagnostics.md](../docs/plans/three-model-bakeoff/scope-arm-c-diagnostics.md). Decision: [D-087](DECISIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3441 passed, 1 skipped (baseline at `a130dfc`) | **3449 passed, 1 skipped, 0 failed** (+8 new) |
| `tsc --noEmit` / testid-lint | unaffected | unaffected — no TS, mobile or web file touched |

**New tests (8).** `backend/tests/test_trade_gen_v2.py` (+5): each starvation mode pinned to a distinct stage (`no_boarded_opponents`, `no_board_overlap`, `no_divergence`); the GATED case pinned to `starvation_reason is None` with the ε-gate owning the kills; the `kill_counts()` key set and order pinned as a contract. `backend/tests/test_bakeoff_serving.py` (+3): forfeits summed over an arm's groups (arm `current` no longer reports 0 when its groups forfeited), arm-C diagnostics reaching `arms_json` with the starving stage named, and drain-on-read so one run's counters cannot leak into the next.

**What was measured (read-only prod, `SET TRANSACTION READ ONLY`, SELECT only).** All 18 `bakeoff_runs` rows and 8,112 `deck_impressions`:

- Arm C's `cards=0` is **per-league, not per-time**: it happens only in `62846` and `11896`; league `1312140920132497408` returned 6–16 cards in all 11 of its runs. The reported "9 forfeits → 2 improvement overnight" was two different leagues, not one improving.
- `member_rankings`: `62846` has **zero** rows; `11896` has rows for one user — the requester himself; `1312…` has 4,416 across 6 users. Arm C is divergence-only by design, so a league with no boarded *opponent* gives it nothing.
- **Divergence supply is real but concentrated:** 96.8 % of all-time divergence impressions (1,196/1,235) come from the one league with ≥3 boards. `62846`, `11896`, and both 1-board leagues have **zero divergence impressions ever**. The 15.2 % all-time rate is not evidence arm C had input.
- **The control:** arm `current`'s own `current_divergence` group pool is **0 in all six runs** in those leagues — identical to arm C. In the boarded league arm C's pool is 6–16 (median 7) against arm `current`'s 0–7 (median 1), and arm `current` produced no divergence at all in 8 of 11 runs. **Arm C out-produces arm `current` on the divergence axis in 11 of 11 runs where input exists.**
- **Zero `gen_v2` impressions is serving, not generation:** `served_arm` is `'current'` on every run (`bakeoff_serve_interleaved = 0.0`, dark), so `server.py:3950` can only stamp `current` or NULL. Arm C already contributed 6 of 6 composed cards to the interleaved deck it does not serve.

**Local reproduction.** All four shapes (boarded+divergent / no boarded opponent / boarded with zero divergence / boarded with no overlap) reproduced on the `_base_pair` fixture. Under the OLD counters three of the four were byte-identical all-zero reports — that indistinguishability is the defect fixed.

**Not proven here.** Arm C's card *quality* — it has still never been evaluated by a user, and cannot be until `bakeoff_serve_interleaved` is lit (operator's call, deliberately untouched). Board supply, not model quality, is the binding constraint: only one production league can exercise arm C at all.

## 2026-08-19c — Pick-badge value→Elo inverse (D-088); the round-3 "overprice" was arithmetic

**Branch:** `fix/pick-round3-value`, worktree `wt-round3`, from `origin/main` `a130dfc`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/pick-badge-scale/scope.md](../docs/plans/pick-badge-scale/scope.md). Decision: [D-088](DECISIONS.md). Memo: [docs/reviews/2026-08-19-pick-badge-scale.md](../docs/reviews/2026-08-19-pick-badge-scale.md). Gotcha: [G-052](GOTCHAS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3441 passed, 1 skipped (baseline at `a130dfc`) | **3443 passed, 1 skipped, 0 failed** (+2 new tests, 5 retargeted) |
| `tsc --noEmit` | — | **clean, exit 0** (mobile diff is a JSDoc comment only) |
| `mobile/scripts/testid-lint.sh` | — | **OK** (no testIDs added or renamed) |
| `test_tier_occupancy.py` | 47 passed | **47 passed, file not opened** — no band or seed moved, so occupancy could not move |
| `test_pick_anchor.py` · `test_pin_tier_bounded.py` · `test_pick_pricing_m6b.py` · `test_slot_values.py` | green | green, **untouched** — none of them reads the badge path |

**What the tests now prove that the old ones did not.** The pre-existing pins in
`test_league_picks_tier.py` were literal Elos (`1383.5 → 'second'`) written by reading the buggy
output back, so they *confirmed* the defect rather than catching it. The replacement is a
**property**: `test_current_year_rungs_badge_their_own_round` asserts, through the route and for
all four rounds, that a current-year pick of round R badges exactly where
`GENERIC_PICK_SEEDS[(R, "Mid")]` sits — which is what `tier_config.json`'s `_calibration` already
defines to be true. No wrong inverse satisfies it for all four rounds. A second test pins that a
pick priced below the `waivers` floor carries `null` rather than a flattering rung.

**Arithmetic verified rather than quoted.** Executed against the shipped functions:

| Claim | Verified |
|---|---|
| The compression the D-084 memo cited | Real. On `dp_values_snapshot_2026-07-10.json` (641 players, `1qb_ppr`), ranks 200→300 span Elo **1262.9 → 1208.0 = 54.9 points**, vs 2.508 Elo/rank at 100–200 and 4.417 at 50–100 |
| ...but not the cause | The badge never reads the player board. `pool_value` → Elo is the whole path |
| The two maps cross once | At **Elo 1548.0** exactly (`223.130 + 0.824487·v = v` ⟹ `v = 1270.9`) |
| Badge inflation, by rung | Mid 2nd +35.2 · Mid 3rd **+63.4** · Mid 4th **+99.3** · Late 4th +109.5 Elo |
| 1383.5 reproduces end to end | `elo_to_value(1320) = 406.570` → `seed_elo_for_value(406.570) = 1383.5` (wrong) vs `value_to_elo(406.570) = 1320.0` (right) |

**Measured on prod, read-only (`SET TRANSACTION READ ONLY`, SELECT only, no writes).**

| Question | Answer |
|---|---|
| Pick rows at risk | **1,104** across **7** leagues, all with a non-NULL `pool_value` |
| Badges that change, recomputed both ways over the *actual stored* values | **600 (54.3 %)** — 538 down, 62 up |
| Named transitions | `third`→`fourth` 188 · `third`→`waivers` 152 · `second`→`third` 136 · `second`→`first_1` 62 · `third`→`null` 62 |
| Unchanged | `first_1`→`first_1` 164 · `second`→`second` 252 · `third`→`third` 88 |
| 3rd-round picks in served cards | **27 of 2,376 = 1.1 %** (1.4 % of 1,909 pick mentions) |
| 4th-round picks in served cards | **0** |
| Picks overall | 1,329 of 2,376 cards = **55.9 %**; firsts **80.9 %** of pick mentions, 2nds 17.7 % |

**Honest read of that last block:** deep picks barely touch real decks, so this was never worth a
repricing — which is the measured argument for fixing the badge and leaving the ladder alone
(and for parking [Q-021](OPEN_QUESTIONS.md)).

**Not run:** the manual TestFlight checklist (7 steps, in the scope block §3) — it needs the
operator and a build. Step 7 is the one that matters most: build a trade containing a 2026 3rd and
confirm the **values and fairness verdict are unchanged**, since any numeric movement would mean
the fix leaked out of the display layer.

---
## 2026-08-19b — Give-side headliner cap (D-082); the flood C4 could not see

**Branch:** `fix/deck-give-headliner-cap`, from `origin/main` `8b7689a`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/deck-give-headliner-cap/scope.md](../docs/plans/deck-give-headliner-cap/scope.md). Decision: [D-082](DECISIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3416 passed, 1 skipped (baseline at `8b7689a`) | **3427 passed, 1 skipped, 0 failed** (+11 new) |
| `tsc --noEmit` / `testid-lint` | n/a — **zero files under `mobile/` changed** | unaffected |
| Bake-off arm-A golden + knob-inventory guard | 10 passed | 10 passed; new knob pinned to 0 in `MODEL_A_PROFILE`, **no golden re-capture needed** (kill value returns the list unchanged) |
| `test_engine_quality_golden` byte-identity vs `origin/main` | 5 knobs killed | 6 knobs killed, still byte-identical |

**What was measured, on prod, read-only (`SET TRANSACTION READ ONLY`, SELECT only).** The defect,
on the operator's own deck `deck_job_id` 2740a7fc — 22 cards, **20 distinct `centerpiece_id`s**,
C4 killed 0, and three players supplied **17 of the 22 give sides** (6 Adams / 6 `1466` / 5
Mayfield). Then the fix, replayed over **66 `deck_candidate_sets` pools of ≥20 candidates**
(1,925 served cards) in `base_score` order:

| Cap | Cards lost | Median deck size | Per-deck max repeat (median) | Decks under `_DECK_MIN_CARDS` (5) |
|---|---|---|---|---|
| 2 | 458 (23.8 %) | 29 → 24 | 6 → 2 | 0 |
| **3 (shipped)** | **194 (10.1 %)** | **29 → 26.5** | **6 → 3** | **0** |
| 4 | 62 (3.2 %) | 29 → 28 | 6 → 4 | 0 |

At the shipped default: 19 of 66 decks unchanged, worst single deck 36 → 24, 3 decks under 20
cards, per-deck worst repeat `{3:1,4:13,5:16,6:14,7:7,8:1,9:4,10:2,11:3,12:2,13:3}` → `{3:66}`.

**Evidence per D-056 (no simulator, no Maestro):** 11 new pytest cases in
`backend/tests/test_engine_quality.py` + a file:line code-walk proof in the scope block §3.1 +
a manual TestFlight checklist for the operator (§3.2), since "how the deck reads" is the one
claim no unit test can settle.

**Proven-to-fail, both applied → observed RED → reverted.** (a) default `3.0 → 0.0`: 3 behaviour
tests fail. (b) delete the `cap_give_headliners` call from `_dedup_and_sort`: 4 fail — the three
above plus `test_both_generation_paths_apply_the_give_cap`, which is the guard that arm C
(`bakeoff_runner.gen_v2_cards`) and the `trade_gen.v2` serving branch keep their own calls; both
bypass `_dedup_and_sort` entirely, so without them the bake-off would compare arms under
different deck-assembly rules.

**One pre-existing test-fixture interaction, resolved deliberately rather than by loosening an
assertion.** Every card in the C4 flood fixture gives `hub`, so C4b bound first and 4 C4 cases
went red. `_flood_deck` and `_ORTHOGONAL_GATES_OPEN` now pin `deck_give_headliner_cap = 0`, the
same isolation technique those fixtures already used for `deck_headliner_cap` — C4b has its own
fixture (`_c4b_*`) built from the real defect shape (one player for one pick, six distinct picks).

---

## 2026-08-19 — Round-2 pick recalibration (D-084); the `second` tier floor moves with it

**Branch:** `feat/round2-pick-recalibration`, from `origin/main` `93ac695`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/round2-pick-recalibration/scope.md](../docs/plans/round2-pick-recalibration/scope.md). Memo: [docs/reviews/2026-08-19-ktc-pick-value-comparison.md](../docs/reviews/2026-08-19-ktc-pick-value-comparison.md) (carried on this branch; not on main). Decision: [D-084](DECISIONS.md). Open question: [Q-019](OPEN_QUESTIONS.md). Gotcha: [G-051](GOTCHAS.md).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` | **3429 passed, 1 skipped, 0 failed** — byte-identical to the `93ac695` baseline (3429/1) |
| `tsc --noEmit` (TypeScript 5.9.3, worktree-local `npm ci`) | clean, exit 0 |
| `mobile/scripts/testid-lint.sh` | `testid-lint OK` |
| `mobile/tests/check-*.js` — `calc-pick-tiers`, `anchor-labels`, `picks-subset-invariance`, `contrast` | 4/4 pass |
| `test_tier_occupancy.py` | **47 passed** — `second` peaks at 32 against its ceiling of 35, exactly as the memo predicted |
| Bake-off knob-inventory guard | untouched — **no `trade_service._DEFAULT_CFG` key added**; `trade_service.py` is not in the diff |

**The blast radius was predicted and then measured to match, exactly.** Applying the seed + band edit before retargeting anything produced **11 failed / 3418 passed** — the same eleven the memo named on a throwaway copy, no more and no fewer. Nothing outside the predicted set moved. Retargeted: `test_pick_anchor` ×2 (1460 → 1400), `test_pin_tier_bounded` ×4 (one constant, `SECOND_LO` 1400 → 1370), `test_pick_pricing_m6b` ×3, `test_league_picks_tier` ×1, `test_power_rankings` ×1. Two extras retargeted deliberately although green: `test_tier_occupancy::test_anchor_rungs_land_in_matching_tiers` asserted `1460.0 → "second"`, a seed that no longer exists, and the `pin_tier_bounded_golden.json` fixture.

**The honest scorecard moved and was rewritten, not silenced.** `test_pick_pricing_m6b::test_the_measured_reshaping_direction_is_deflation_not_inflation` measures how far our ladder sits above DynastyProcess's real market slot prices. `delta(2026, 2)` was `< -0.40`; it is now **−0.284**, and `delta(2027, 2)` **−0.244**. Both are now pinned with `pytest.approx` rather than a loose bound so drift in *either* direction must be acknowledged, with a docstring recording that the remaining ~28 % is intentional (Option B was measured and rejected). It also records that **the ranking flipped**: 2nds are no longer the biggest outlier — a 2026 3rd now deflates hardest (−0.355 vs −0.284), which is the Q-019 residue.

**The golden fixture was re-captured against pristine code, not re-derived.** `pin_tier_bounded_golden.json` pins `edge_lo` to the `second` floor, so the floor move changed its *input*. Its docstring forbids regenerating from new code, so a separate **pristine `origin/main` worktree at 93ac695** was created and the harness validated first by re-capturing at 1400 and confirming it reproduced the checked-in golden **byte-for-byte**; only then was it re-run at 1370. Seven numbers moved, all forced by the one changed input (`elo.edge_lo`, plus ripples in `free` — his opponent in six comparisons — and `quiet`).

**Production validation, read-only** (`SET TRANSACTION READ ONLY`, SELECT only, credentials read from the gitignored `secrets.local.env`, never printed). Question: *is the overpriced 2nd costing accepted trades?* **Answer: no, not measurably.** Cards containing a 2nd are liked at **34.8 % (n=46)** vs **35.2 % (n=565)** for cards with no pick at all — Fisher **p = 1.00**; 2nds appear on only **13.7 %** of 2,184 served cards. A 3-day impression-level sample points the *opposite* way (17.6 %, n=17, p=0.26); two samples disagreeing on sign is the finding. Zero of 23 free-text passes mention a 2nd. The real signal is **1sts by side** — 1st-on-give 15.6 % liked vs 1st-on-receive 47.1 % (n=128). **D-084 is justified on the rank measurement, not on acceptance data, and no lift should be expected.**

Two incidental prod findings, out of scope and not fixed here: **`backend/database.py` on `main` is stale against prod** (26 vs 13 `deck_impressions` columns; `trade_pass_reasons` missing entirely), and **`model_arm` is 97.5 % NULL with zero `gen_v2` rows** — the bake-off is not producing labelled data.

**Not yet run: the manual TestFlight checklist** (scope §8, 10 steps). It is the only runtime evidence this change gets under D-056, and step 9 deliberately points the operator at the one odd consequence — a current-year 3rd now badges "2nd".

## 2026-08-19 — Per-round draft-pick year decay (D-079); firsts stop decaying

**Branch:** `feat/pick-year-decay`, from `origin/main` `02e27dd`. **Not shipped** — not pushed, not merged.
Scope block: [docs/plans/pick-year-decay/scope.md](../docs/plans/pick-year-decay/scope.md). Review: [docs/reviews/2026-08-19-pick-year-valuation.md](../docs/reviews/2026-08-19-pick-year-valuation.md). Decision: [D-079](DECISIONS.md). Open question: [Q-018](OPEN_QUESTIONS.md).

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3404 passed, 1 skipped (baseline at `02e27dd`) | **3416 passed, 1 skipped, 0 failed** (+12 new) |
| `tsc --noEmit` / `testid-lint` | n/a — **zero files under `mobile/` changed** | unaffected |
| Bake-off arm-A golden + knob-inventory guard | 10 passed | 10 passed, after recording the exclusion decision |

Mid-run the change produced **8 failures, every one of them the intended behaviour change** — seven
behavioural tests asserting the old round-1 discount, plus the bake-off knob-inventory guard demanding
a written decision for the four new `_DEFAULT_CFG` keys. None were suppressed. Each of the seven was
**retargeted to assert the new intent plus a still-decaying round**, so "someone flattened every round"
now fails loudly rather than passing silently: `test_owned_picks.py`, `test_dynasty_value_pick_scale.py`,
`test_league_picks_tier.py`, `test_pick_value_scaling.py`, `test_pick_pricing_m6b.py`,
`test_pick_rung_year_labels.py`, `test_pick_values_in_suggestions.py`.

**One of those retargets was a near-miss worth recording.** `test_pick_values_in_suggestions.py` seeded
its player fixture at a hard-coded Elo `1552.0`, chosen because it matched the *old* 2029 1st value
(~1300). After the repricing that literal would have quietly turned "a player against a 1st" into
"a mid player against a 1st" and the test would still have passed — measuring nothing. The seed is now
**derived** from `pick_pool_value(1, 3)`, so the fixture moves with the ladder.

**New coverage — 12 tests in `backend/tests/test_pick_year_decay.py`:** default rates; deep-round
clamping onto `_r4`; live `model_config` reads; the `[0,1]` clamp (a rate > 1 would invert the
arbitrage); **the deploy-free revert** — all four keys at 0.85 reproducing the pre-D-079 ladder on both
value scales, including the literal 1300.1 that was the bug; a 2029 1st equalling a 2027 1st; later
rounds still decaying with round ordering intact at every horizon; **zero value gradient between any
two 1sts** (the anti-swap invariant); `compute_pick_value` on the same clock; round-aware rung
relabelling; and a no-config fallback so a DB outage cannot take pricing down.

**Code-walk proof (replaces a simulator capture, per D-056).** The evidence that *served cards* change
is `trade_service.overpay_ok` (`backend/trade_service.py:1502–1521`) flipping verdict on the operator's
actual card, impression `c67c2fd1e97cb6bf`: Adams 1138.8 vs the 2029 1st at 1300.1 → gap 161.3, ratio
0.124, under both floors (500 / 0.25) → **served**, which is what prod did. At 2117.0 → gap 978.2,
ratio 0.462, over both floors → **killed**. Asserted as the gate's boolean, not as a number.

**Prod corpus measurement (read-only, `SET TRANSACTION READ ONLY`, SELECT only).** 2048
`deck_impressions` rows with `assets_json`: **58.5 %** contain a pick; firsts are **84 %** of all pick
mentions; **99 cards (4.8 %)** moved a 1st one way and a *different-year* 1st the other — the arbitrage,
counted. Re-run that query after merge; the expected post-fix count is **0**, structurally.

**NOT run:** the manual TestFlight checklist (§3 of the scope block) — it needs the operator on a build.
Nothing here is runtime evidence from a device.

## 2026-08-19 — Decline reasons: player preference under "Neither" (branch only, NOT merged)

**Branch:** `feat/decline-reason-player-pref`, from `origin/main` `02e27dd`. **Not shipped** — not pushed, not merged. Flag `feedback.decline_reasons` unchanged (already on for all users).
Scope block: [docs/plans/decline-reason-capture/scope-player-preference.md](../docs/plans/decline-reason-capture/scope-player-preference.md). Decision: [D-080](DECISIONS.md#d-080). Contract: [SPEC §2a](../docs/plans/decline-reason-capture/SPEC.md).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` (before) | **3404 passed, 1 skipped** — baseline at `02e27dd` |
| `pytest backend/tests -q` (after) | **3417 passed, 1 skipped, 0 failed** — +13 tests, zero regressions |
| `npx tsc --noEmit` (mobile) | **clean**, exit 0 |
| `mobile/tests/check-*.js` | **56 suites, 0 failing** (the CI `mobile-typecheck` job globs all of them) |
| `mobile/scripts/testid-lint.sh` | **testid-lint OK** |
| Maestro / simulator | n/a — retired by D-056. The two `mobile/.maestro/flows/decline-reasons-*.yaml` are historical artifacts and were **not** run or extended |
| Sim gate | `FTF_SKIP_SIM_GATE=1`, the standing posture under D-056 |
| Manual TestFlight checklist | **written, NOT run** — 8 steps in scope block §3b, awaiting the operator |

**New tests: 13.** Nine `test_player_preference_*` in `backend/tests/test_decline_reasons.py` (both codes parent to `other` and not to `value`; a foreign layer-1 is a `detail_reason_mismatch` 400 that writes nothing; a layer-2-first write derives `reason='other'` from the prefix; the two directions plus the residual free text land as three distinguishable stored answers), plus four from the `_ELO_MATRIX` parametrisation growing 8 codes → 10 across both knob positions. The two existing enumerations — `test_every_specced_code_is_accepted` and `test_pass_reason_writes_elo_rule_is_pure` — were extended rather than left to pass vacuously.

**Structural suite extended, not just kept green.** `mobile/tests/check-decline-reasons.js` gains a §6 that reads the `TILES` table through the **TypeScript AST** rather than by regex, so a re-order or re-wrap of the source cannot fake a pass. It fails on either of the two silent reversions: reverting "Neither" to free-text-only (the `freeOnly` shortcut is asserted gone), or collapsing the two player codes into one (they are asserted as a pair, each committing on tap rather than opening a text box, each carrying `trades.pass-reason.l2.<code>`, with `other_text` still free and still last).

**A check that had never once executed now does.** The suite's "transcribed codes still match SPEC §2" cross-check was guarded on `fs.existsSync(SPEC.md)` — and **SPEC.md was untracked**, present only in the main checkout's working tree and committed to no branch in the repo. The guard had always taken its SKIP branch, so the transcription had never actually been compared to the spec. SPEC.md is committed on this branch and the cross-check runs and passes. Committing it also surfaced a real spec/implementation divergence: SPEC §2 wrote the free-text step as `value_other` → a second `value_other_text` code, which does not exist and which the route 400s as `invalid_detail`. Corrected in the same amendment.

**What was NOT verified here:** runtime behaviour on a device. Under D-056 that is the manual TestFlight checklist and nothing else — it is written but unrun, so no runtime claim is made about this change. The code-walk proof in scope block §3a is a file:line trace, not evidence of execution.

## 2026-08-18f — Trade-suggestion presentation v2 (additive Acquire surface, flag OFF)

**Branch:** `feat/trade-presentation-v2`, from `origin/main` `a7f8783`. **Not shipped** — not pushed, not merged. Flag `trades.presentation_v2` ships **OFF**.
Scope block: [docs/plans/trade-presentation-v2/scope.md](../docs/plans/trade-presentation-v2/scope.md). Decision: [D-081](DECISIONS.md#d-079--the-confidence-band-is-derived-from-provenance-because-no-confidence-field-exists).

| Gate | Result |
|---|---|
| `npx tsc --noEmit` (mobile) | **clean** — baseline at `a7f8783` was also clean, so the delta is zero new errors |
| `mobile/tests/check-*.js` (all 57) | **all pass**, including the new `check-presentation-v2.js` (**87 assertions**) |
| `npm run test:presentation-v2` | **87 PASS, 0 FAIL** |
| `bash mobile/scripts/testid-lint.sh` | **OK** (8 template-literal globs added to `testid-lint-allow.txt`, each with its constructing file:line) |
| `pytest backend/tests` | **NOT RUN** — no Python environment in this worktree. Backend delta is one `FLAG_KEYS` string + one `config/features.json` entry; `test_entitlements.test_features_json_keys_known` is the covering test and **must be green on the pushed sha before merge** |
| Maestro / simulator | **Not run.** Three flows AUTHORED (`presentation-v2-hero`, `-browse-dismiss`, `-honest-empty`) because the build brief required it — which directly contradicts D-056's "do not author, extend, or execute". Each carries a banner recording the conflict. Execution, and whether authoring was correct at all, is an **operator decision** (scope.md §6 item 1) |
| Sim gate | `FTF_SKIP_SIM_GATE=1` — standing posture under D-056 |
| Manual TestFlight | **Not run** — 12-step checklist written in scope.md §3; operator action |

**What the structural guard actually proves** (not a grep-count — these are the four things that fail silently):
1. **Flag-off byte-identity.** Both `onTodaysTrade` pass sites are ternaries on the flag passing `undefined`; both components build their control list *from the handler's presence*; `'today'` is asserted **not** to be in the static `CHIPS` array; the routes are asserted registered *and* asserted **not** flag-wrapped. A no-op-handler "simplification" — which still renders the chip — fails here.
2. **Instrumentation parity.** Shared `swipeTrade` / `postDeclineReason` imports, `SwipeSignal` imported as a type, no hand-rolled `api.post`/`api.get` in the signals hook, the three event names cross-checked against `TradesScreen`'s own source, the four signal fields, the two-part `signal_v2 && impression_id` gate, boolean-only free text, explicit `platform`, and `VIEWED_MIN_MS`/`DWELL_CAP_MS` matched against `TradesScreen`'s literals.
3. **The server cache-slot agreement.** Shared fairness helpers only, no raw threshold constants, never `force: true` — so the new surface cannot kick a second generation or serve a different card set to the same user.
4. **The design laws, executed.** The pure module is transpiled and RUN: band derivation across all four provenance combinations plus the `likesYou` promotion, "no band label contains a digit", the fairness band exposing no winner/margin, `userSideBullets` naming a concrete asset and never leaking `opponent_surplus`, `counterpartyStatement` returning a number-free single string, `partitionDeck` returning **no hero** when nothing is endorsable, browse uncapped, dismissed cards excluded from hero but retained in browse, and the empty-state copy omitting an unknown roster count rather than rendering zero. Plus source-level bans: no `TradeValueBar`, no `Meter`/`fairnessColor`, no `partner_fit`, no `match_score`, no `showPercent`, no `.slice()` in browse, no `numberOfLines` anywhere on the surface.

**Not proven by anything here, and stated so it is not mistaken for covered:** that the surface renders correctly on a device. Nothing in this branch has run on a simulator or a phone. The 12-step TestFlight checklist is the only runtime evidence available under D-056 and has not been executed.

---
## 2026-08-18e — Bake-off deck composition (three groups of ten; arm A out of the roster)

**Branch:** `feat/bakeoff-composition`, from `origin/main` `217a8e1`. **Not shipped** — not pushed, not merged. Flag `trade.bakeoff` stays **OFF**.
Scope block: [docs/plans/three-model-bakeoff/scope-composition.md](../docs/plans/three-model-bakeoff/scope-composition.md). Decision: [D-078](DECISIONS.md#d-078--a-bake-off-deck-is-composed-of-groups-and-an-unfilled-quota-is-the-finding).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` (before) | **3363 passed, 1 skipped, 0 failed** — baseline at `217a8e1` |
| `pytest backend/tests -q` (after) | **3404 passed, 1 skipped, 0 failed** — +41 tests, zero regressions |
| `npx tsc --noEmit` (mobile) | n/a — zero mobile files changed |
| `check-*.js` / `testid-lint.sh` | n/a — zero mobile files changed |
| Maestro / simulator | n/a — retired by D-056; backend-only, nothing user-visible while the flag is off |
| Sim gate | Tier 4 (backend-only); `FTF_SKIP_SIM_GATE=1` is the standing posture under D-056 |

**New tests: 41.** `backend/tests/test_bakeoff_composition.py` (31 unit) + 10 integration added to `backend/tests/test_bakeoff_serving.py` (real `server._run_trade_job`).

**Flag-off golden extended, not weakened.** `backend/tests/fixtures/bakeoff/flag_off_golden.json` is byte-for-byte unchanged and the flag-off test still asserts byte-identity against it. The four new columns (`group_key`, `group_rank`, `lane_slot`, `trade_intent`) joined Phase 3's admitted-additive list and are asserted **NULL on every row**, exactly as Phase 3's three were.

**Phase 2 verified still intact.** The arm-A golden, the R4-bypass tests and the 189-key knob-inventory guard all still pass; the four new knobs were added to `_PINNED_KNOBS`. `test_bakeoff_composition.py::test_arm_a_leaves_serving_but_phase_2_stays_intact` asserts the profile, its entry point and its knob set directly, so "arm A left by configuration, not deletion" is a tested property rather than a claim.

**Measured — three-group interleave, 500 decks (30 cards each):**

| | group 1 `current_divergence` | group 2 `current_consensus` | group 3 `gen_v2` |
|---|---|---|---|
| mean served position (of 30) | 14.48 | 14.55 | 14.48 |
| cards per deck | 10.0 | 10.0 | 10.0 |
| decks led (of 500) | 164 | 160 | 176 |

Per-lane mean served position: value 14.52, outlook (`window`) 14.48. Both distributions are flat, which is the whole point — a per-**arm** rotation instead puts arm `gen_v2` at mean position **24.5** (measured on identical inputs by `test_grouping_by_arm_would_bury_arm_c_and_the_group_draft_does_not`).

**Measured — outlook-slot under-fill** (slots left empty of 5, at the live lane ratios: divergence 80.5% value / 19.5% window, consensus 73.2% / 26.8% / 6.1% unlabelled), sweeping per-deck supply:

| surviving cards in the group's pool | divergence group | consensus group |
|---|---|---|
| 10 | 3.0 | 3.0 |
| 15 | 2.0 | 1.0 |
| 20 | 1.0 | **0.0** |
| 25 | **0.0** | 0.0 |
| 30 / 40 / 60 | 0.0 | 0.0 |

A divergence group needs ~25 surviving cards before it can expect five outlook cards; a consensus group clears at ~20. That gap is why groups 1 and 3 are the ones expected to serve short, and why the default fill policy records the hole instead of topping it up from the value lane. Pinned by `test_measured_under_fill_across_realistic_divergence_supply`.

**Two plumbing gaps closed** so the comparison is of generators, not of which post-generation steps each arm received: arm C now gets the same `_filter_by_trade_intent` and the same `classify_lane` the engine arms already get. Without the lane label, group 3's outlook quota would have under-filled **100% of the time** and read as "arm C cannot produce outlook ideas".

**Not measured here, needs Phase 4:** real per-deck supply. Every under-fill number above is from the live lane *ratios* applied to swept supply sizes, because the 3,163-card total does not say how many cards one deck's arm produces. Phase 4 dark validation writes `groups_json` on every run, so the true rate is one query away once it runs.

---
## 2026-08-18d — Three-model bake-off Phase 3 (the runner)

**Branch:** `feat/bakeoff-runner`, rebased onto `origin/main` `9d24da3` (which carries bake-off Phase 2 and tier-bounded pins). **Not shipped** — not pushed, not merged. Flag `trade.bakeoff` ships **OFF**.
Scope block: [docs/plans/three-model-bakeoff/scope-phase3.md](../docs/plans/three-model-bakeoff/scope-phase3.md).

| Gate | Result |
|---|---|
| `pytest backend/tests -q` | **3363 passed, 1 skipped, 0 failed** — full suite re-run after the final rebase onto `9d24da3` AND after the fairness-threshold capture |
| `npx tsc --noEmit` (mobile) | n/a — zero mobile files changed |
| `check-*.js` / `testid-lint.sh` | n/a — zero mobile files changed |
| Maestro / simulator | n/a — retired by D-056; backend-only change with no user-visible surface |

**New tests: 49.** `backend/tests/test_bakeoff_runner.py` (35 unit) + `backend/tests/test_bakeoff_serving.py` (14 integration through the real `server._run_trade_job`).

**Third contamination channel closed (coordinator addition, same session).**
[The trade-logic archaeology review](../docs/reviews/2026-08-18-trade-logic-archaeology.md)
found `fairness_threshold` persisted **nowhere** — not a column, not one of the 28
`features_json` keys — while arriving per-request from the client (0.75 toggle on / 0.50 off).
A per-arm comparison spanning sessions with different client settings would have compared arms
AND thresholds at once. Now `deck_impressions.fairness_threshold` (a column, not a JSON key: the
analysis groups by it), written **per card** because the effective bar is card-dependent, and
per arm in `bakeoff_runs.arms_json`. `bakeoff_runs.config_json` snapshots the effective config
each arm ran under, since `model_config` has no `updated_at`.

The composition is proven, not assumed: `test_served_cards_record_the_threshold_they_were_generated_under`
runs the job at **0.75** and asserts the divergence card records **0.55**
(`min(requested, fairness_floor_divergence)`), the consensus card **0.75**, and the arm-C card
**NULL** — i.e. recording the requested value would have misdescribed two of the three.
`test_arm_a_config_snapshot_is_taken_inside_the_profile` pins that arm A's snapshot is taken
INSIDE `model_a()` (outside it the overlay is gone and arm A would be recorded as running on live
defaults). `test_threshold_clean_query_answers_itself_from_the_table` executes the documented
"was this comparison threshold-clean?" `GROUP BY`, so the query cannot rot into documentation-only.

**Flag-off byte-identity is proven by a CAPTURED golden, not an assertion.**
`backend/tests/support/bakeoff_harness.py` was copied into a **separate worktree detached at
pre-bake-off `origin/main` (9a20ca8)**, run there, and its output committed as
`backend/tests/fixtures/bakeoff/flag_off_golden.json`. With the flag off this branch reproduces it
byte for byte — identical served card payloads and identical `deck_impressions` rows. The only
admitted difference is the three additive columns (`model_arm`, `arm_rank`,
`fairness_threshold`), asserted NULL on every row. The harness deliberately imports nothing from `bakeoff_runner`, which is what let it run on
the pre-change SHA.

**§3.4 Channel 2 (the silent-failure risk) is tested, not asserted.**
`test_post_generation_rerankers_cannot_touch_the_merged_deck` turns every reordering layer ON and
replaces each with a spy that REVERSES the deck (F2 `_order_deck`, F3 fatigue multipliers, F5 taste,
F6 value model, F7 wildcard, F9 shaping), then asserts the served arm sequence is still the
interleaver's. Its mirror `test_rerankers_do_run_when_the_bakeoff_is_off` proves the same spies fire
with the flag off, so the bypass is a bake-off property and not a broken harness. F3 decline
suppression is asserted STILL LIVE (it only removes cards).

**§3.4 Channel 1** is guarded structurally: `test_every_swipe_k_multiplier_runs_through_the_elo_freeze`
scans `backend/server.py` for every `fit_congruence_mult` K site and fails if one is missing
`_bakeoff.elo_freeze_mult` — a new swipe path that forgot the freeze would contaminate the shared
board with no visible symptom.

**Real bug found and fixed while testing (would have been silent in prod):** `save_deck_impressions`
inserts the batch with SQLAlchemy `executemany`, which compiles the statement from the **first row's
keys**. Stamping `model_arm` only on attributed cards meant a deck led by an unattributed likes-you
injection dropped attribution for the **entire deck**. Both columns (and the arm-stamped
`policy_version`) are now written on every row, with a regression assertion in
`test_likes_you_injection_does_not_reorder_the_interleave`.

**Generation cost measured** on a synthetic 12-team / 168-asset league with 11 boarded opponents
(scratch harness, 5 repeats, medians):

| | ms | cards |
|---|---|---|
| single generation (today) | 3127 | 19 |
| bake-off fan-out (3 arms) | **7359 (2.35×)** | 140-card interleaved deck |
| — arm `baseline` | 4187 | 30 |
| — arm `current` | 2733 | 19 |
| — arm `gen_v2` | 424 | 105 |

Arm A is the slowest because its profile zeroes every gate, so more candidates survive. Arm C
over-produced **on this fixture only** — the synthetic boards carry gaussian noise, so divergence is
everywhere; PLAN.md §3.2 still expects it to under-produce in production, which is exactly what the
empty-arm rate is there to measure. Agreement on the fixture: `baseline+current` 14.

**Budget finding for the operator:** the per-opponent enumeration deadline is 1 s, so an 11-opponent
league's worst case is ~11 s per arm and ~33–45 s for the fan-out, against
`server._JOB_HARD_TIMEOUT = 60` s. Inside the limit but thin, with no margin for a slow Postgres.
Phase 4 must watch p95 job duration directly; `_JOB_HARD_TIMEOUT` may need raising before Phase 5.
`bakeoff_deck_limit` defaults to uncapped, so an interleaved deck is ~3× today's — set it before
Phase 5 unless a very long deck is wanted.

**Arm-A seam: real, not stubbed.** Phase 3 was built against a temporary local stub of
`backend/bakeoff_profiles.py` (Phase 2 had not yet landed), then **rebased onto `origin/main`, which carries Phase 2's real module** (`3760f12`). The stub was dropped in the rebase and
the runner now calls Phase 2's `model_a()` — the only supported entry point, because it applies the
pinned `MODEL_A_PROFILE` and the R4 bypass together. Arm A is therefore golden-tested against
reference SHA `92c31d5` by Phase 2's own tests, and the R4 bypass is really enforced
(`trade_service.r4_bypassed()`). Full suite re-run after the rebase.

---
## 2026-08-18c — G-049 caller-side finish: route-level proof + the ungated-signal decision

**Branch:** `feat/sweep-followups-2026-08-18` (continues the 2026-08-18b entry below). **Not shipped.**

| Gate | Before | After |
|---|---|---|
| `pytest backend/tests -q` | 3216 passed, 1 skipped | **3219 passed, 1 skipped** |

Both `save_trade_swipes` gates (`swipe_trade`, `_apply_reasoned_pass`) were already in place from
2026-08-18b; this pass added the **runtime** evidence they lacked and settled the one open design
question.

**New coverage — 3 route-level tests** in `test_trade_decision_idempotency.py`. They POST
`/api/trades/swipe` twice through the Flask test client against an in-memory DB with the **real**
`save_trade_swipes` (only `record_event` / `create_notification` / `check_for_match` stubbed), so the
count is of rows the route actually wrote:
1. `test_re_posted_swipe_writes_exactly_one_set_of_swipe_decisions` — one `swipe_decisions` row, one
   `trade_decisions` row, and a `replay_from_db` + `_compute_elo` check that a restart sees exactly
   one application of `trade_k_pass`.
2. `test_route_replay_leaves_the_in_session_signal_doubled` — pins the accepted residual.
3. `test_route_replayed_like_still_runs_match_detection` — `check_for_match` called twice.

**Sabotage:** deleting the `if wrote_decision:` gate in `swipe_trade` turns tests 1 and 3 RED
(`assert 2 == 1` on real rows), alongside the existing source pin. The `inspect.getsource` pins alone
could not have caught a gate that was present but ineffective.

**Design question closed:** `RankingService.record_trade_signal` stays **before** the DB write and
**ungated** (D-073). `_trade_swipes` is derived state that `replay_from_db` rebuilds from
`swipe_decisions` at every `session_init`, and the persist block around it is best-effort by design —
gating it would trade a bounded, self-healing 2x overcount for an unbounded 0x undercount whenever
the DB is unreachable. `backend/database.py`'s docstring and `docs/data-dictionary.md` both said
callers "must skip both", which the shipped code never did; corrected to match.

**Not run:** `tsc --noEmit` / `check-*.js` / testid-lint — this pass touched backend and docs only.
**Count note:** the 2026-08-18b entry recorded 3191; the branch was rebased onto a newer `main`
mid-session (engine-quality wave + navdoc refresh), which brings `test_engine_quality.py` and
`test_engine_quality_golden.py` — hence 3216 as the real pre-change baseline. Nothing was lost.

## 2026-08-18c — Bake-off Phase 2: arm A pinned + golden (branch only, NOT merged)

Branch `feat/bakeoff-arm-a`, off `origin/main` @ `9a20ca8`. Scope block:
[`docs/plans/three-model-bakeoff/scope-phase2.md`](../docs/plans/three-model-bakeoff/scope-phase2.md).
Backend-only: `backend/bakeoff_profiles.py` (`MODEL_A_PROFILE`, `model_a()`), a thread-local
R4 bypass in `trade_service`, and `backend/tests/test_bakeoff_arm_a_golden.py`.
**Not pushed, not merged** — build-agent output; Phase 3 (`feat/bakeoff-runner`) consumes it.

| Gate | Baseline (`origin/main`) | After |
|---|---|---|
| `pytest backend/tests -q` | 3267 passed, 1 skipped (3268 collected with the new file ignored) | **3277 passed, 1 skipped, 0 failed** (250s) |
| `npx tsc --noEmit` (mobile) | n/a | **not run — zero files under `mobile/`** |
| `testid-lint.sh` | n/a | **not run — no mobile files touched** |
| Simulator gate | — | **D-056 standing posture, `FTF_SKIP_SIM_GATE=1`**; backend-only, no runtime surface |

**What the golden actually proves.** Reference SHA **`92c31d5`** (`20b40db^` on `--first-parent
main` — the last commit before the G6 wave). Captured by adding a detached worktree at that SHA,
copying the test file in, and running its `__main__` capture mode. Arm A (`MODEL_A_PROFILE` + the
R4 bypass) reproduces **30 deck cards and the asset-ideas groups byte-identically**; arm B (live
defaults) on the same fixture returns **8 cards** and different ideas.

**Board-drift immunity.** The fixture pins every generation input as a literal (player table,
`seed_elo`, `user_elo`, each opponent's `elo_ratings`, confidence counts, roster, outlook,
fairness threshold) and calls `TradeService.generate_trades` directly — no DB read, no
`ranking_service` call, no `comparison_counts`, no pin resolution. So Phase 0's pin fix,
`feat/tier-bounded-pins` and premium import cannot move it: the comparison isolates generation
logic only.

**Non-vacuity, per rule** (a golden that stopped disabling anything would otherwise still pass):
arm B records kills for **R1 2822 / R2 251 / R3 513 / R5 405** on this fixture; C1, C4 and C5 each
move the deck alone; C2 moves the asset-ideas alone. **C3 (`pick_pair_strip_frac`) is the one
profile entry the deck fixture cannot reach** — no matched-pick-pair shape survives the other gates
on a realistic league (R3 kills the candidates first) — so it is asserted at its own gate
(`pick_swap_ok`), with byte-identity already pinned by `test_engine_quality_golden.py`. Recorded as
a known gap in the scope block rather than papered over.

**Both drift alarms negative-controlled** (verified by breaking them on purpose, not by inspection):
injecting a fake `_DEFAULT_CFG` key fails the inventory test naming `shiny_new_knob`; removing
`deck_headliner_cap` from the profile produces a drift report listing the 22 dropped cards.

**Not covered:** no runtime/TestFlight evidence exists or is claimed — nothing reaches a client.
The new code is unreachable in production until Phase 3 wires a caller behind `trade.bakeoff`.

**Second rebase, same session** (onto `origin/main` `9a20ca8`, picking up the bake-off Phase 0 batch
`e8ae476`): clean, no conflicts, despite that batch touching `backend/database.py`,
`backend/server.py` and `docs/data-dictionary.md` — the same three files this work edits. Re-verified
after: both `save_trade_swipes` gates present (`server.py:11010`, `:11347`), guard intact, and
**pytest 3270 passed / 1 skipped** (the +51 over 3219 is Phase 0's own
`test_force_supersedes_running_job.py` and `test_override_pin_unpin.py`). The three route-level tests
count real rows after two POSTs, so their passing is itself the evidence the guard still works — no
second sabotage run needed.

---
## 2026-08-18d — Tier-bounded voting (a pin confines a player to a tier)

**Branch:** `feat/tier-bounded-pins`, rebased onto `origin/main` `74620a7`. **Not shipped, not pushed.**
**Scope block:** [`docs/plans/three-model-bakeoff/scope-tier-bounded.md`](../docs/plans/three-model-bakeoff/scope-tier-bounded.md) · **Decision:** [D-076](DECISIONS.md).

| Gate | Baseline (`origin/main`) | After |
|---|---|---|
| `pytest backend/tests -q` | 3280 passed, 1 skipped (`74620a7`) | **3314 passed, 1 skipped** |

The +34 is this branch's own: 33 in the new module, plus one from splitting a `test_elo_memoization.py` test in two. Suite was run green at both bases — 3267 → 3301 on `9a20ca8` before the rebase, 3280 → 3314 after it; `9a20ca8..74620a7` does not touch `ranking_service.py`, `trade_service._shrink_user_elo`/`_value_uncertainty` or `tier_config.json`, so the captured golden is unaffected by the rebase.

| `npx tsc --noEmit` (mobile) | n/a — zero files under `mobile/` in the diff | n/a |
| `mobile/scripts/testid-lint.sh` | n/a — same reason | n/a |

- **New: `backend/tests/test_pin_tier_bounded.py` — 33 tests.** The Adams scenario (pinned
  1565.28 in `second` [1400, 1575], 17 down-votes → Elo 1426.6, materially down, never outside
  the band); clamp at both edges; a pin exactly on a band boundary; a pin in a band gap; a pin
  above the top band; unranked/`None`-tier pins frozen rather than crashed or floated; a
  zero-vote pin untouched by the clamp; a clamped player climbing back into the band; both
  scoring formats plus monkeypatched bands proving the clamp reads the service's own format and
  the player's own position; the `pin_exclude_comparisons` narrowing in both directions and its
  `_value_uncertainty` sharing; monotonicity, direction-awareness, and the disclosed n=0→1
  residual; the F2 interaction both ways; the knob in both memo keys.
- **Byte identity proved by CAPTURE.** `backend/tests/fixtures/pin_tier_bounded_golden.json`
  was produced by copying the new module's own `build_service`/`snapshot` verbatim into a
  detached worktree of pristine `origin/main` (`9a20ca8`; `git diff e8ae476..9a20ca8 --
  backend/` is empty) and running it there before a line of production code changed. Asserted
  as a whole document at `pin_tier_bounded=0` + `pin_unpin_on_newer_swipe=1`. A guard test
  asserts the golden still *exhibits* the freeze (every pinned player exactly on his pin, every
  pinned count 0, the un-pinned control moved), so the proof cannot rot.
- **Mutation matrix — every guard bites.** Each mutation applied to a clean tree:
  remove the clamp → **11 fail**; drop the `min(lo,pin)`/`max(hi,pin)` widening → **2 fail**;
  let an unranked pin float free → **1 fails**; count clamped-away votes as confidence →
  **3 fail**. Restored → 33 pass.
- **Updated, not deleted:** `test_override_pin_unpin.py` (41 tests) now states the Phase 0
  configuration explicitly instead of reading today's defaults, so it keeps gating the Phase 0
  contract, which is still reachable by knob. `test_elo_memoization.py` had two tests asserting
  a pinned Elo *exactly* — that was the freeze contract; split into the memo contract
  (cold == warm, and inside the band) plus a new test asserting exactness under the kill switch.
- **Prod measured read-only** (`DATABASE_URL_PROD`, `SELECT` only under
  `default_transaction_read_only=on`), 2026-08-18. Every board replayed through the **real**
  `RankingService._compute_elo`/`_pin_bounds` via `replay_from_db`; the "today" column
  reproduces the audit's 2,721-inert figure exactly, which is what validates the replay.

  | | Comparisons | Effective | Pins | Players who move |
  |---|---|---|---|---|
  | Today (freeze) | 4,013 | 1,292 (32.2%) | 2,735 | 0 |
  | **Tier-bounded** | 4,013 | **3,938 (98.1%)** | 2,735 | **667 (24.4%)** |

  Ceiling on the second number is 739 — the pins that have ever appeared in a comparison at all
  — so **90.3% of every pin the user has ever voted on now moves**. The 72 that do not are 47
  pins below the lowest band (frozen by design) and 25 clamped hard at an edge.
- **Correction to the 2026-08-18 audit, found by the replay:** the operator's 18 Davante Adams
  comparisons are `decision_type = 'trade'`, and trade decisions have **never** entered
  `comparison_counts` for any player (`_compute_stats` walks only `_swipes`). His Elo now moves
  (1565.28 → 1530.15) but his effective value is the consensus seed 1138.8 both before and
  after. The audit's `n = 6` came from unfiltered SQL over `swipe_decisions`; it flagged its own
  confidence on that arithmetic as medium-high. The mechanism is real — the 353 → 1,666 jump in
  live *ranking* comparisons is what measures it — the per-player +12.5% is not.
- **Sim gate: Tier 4 (none, CI only).** Backend-only diff; zero files under `mobile/`.
  `qa/sim-runs/last-sim-run.json` not written — under D-056 there is nothing to run.
  `FTF_SKIP_SIM_GATE=1` is the standing posture for any push.
- **Not covered by any test here:** whether the thawed boards produce better decks. That is
  empirical and the lever is `pin_tier_bounded` — one `PUT /api/admin/config` to set and to
  undo. Also untested: the band-edge UI affordance, which is a client change and deliberately
  not built (scope §5).

---
## 2026-08-18b — Bug-sweep follow-ons (items 3/4/5) + research 6/7

**Branch:** `feat/sweep-followups-2026-08-18` (off `origin/main` `90fb19a`). **Not shipped** — awaiting operator go.

| Gate | Sweep baseline | After |
|---|---|---|
| `pytest backend/tests -q` | 3148 passed, 1 skipped | **3191 passed, 1 skipped** |
| `npx tsc --noEmit` (mobile) | clean | **clean** |
| `check-*.js` | 54 suites | **56 suites, all pass** |
| `testid-lint.sh` | OK | **OK** |

**Two false-confidence findings, both caught by sabotage rather than by review:**
1. `test_trade_decision_idempotency.py` defined its own `swipe_once()` caller, proving the *contract*
   while leaving `server.py`'s two call-site gates unpinned — both could be deleted with every test
   green. Closed with `inspect.getsource` route pins (the `test_pass_cooldown.py` idiom).
2. `check-swipe-failure-recovery.js` exempted rewinds that called `setDeck([])`. Unsound — the guard
   is a ref that outlives the deck — and its only real effect was to let the one site that forgot
   (QuickSet regen) pass. Exemption removed; scan went **4 → 9 sites**.

**Sabotage coverage:** item 3 ran 65 mutations (all RED, three initially-weak assertions rewritten
after they survived); item 4 ran 9; item 5 ran 9; the orchestrator separately sabotage-verified the
QuickSet guard clear, the picker `loading` assertion, and both new route pins.

**Prod reads (read-only, `DATABASE_URL_PROD`):** `trade_decisions` 933 rows — 40 double-writes
(0.015–0.200 s) vs 23 genuine re-decisions (147.7 s+), 738× empty band; 62 duplicate `swipe_decisions`
rows ≤1 s apart, 48 correlating with a duplicated decision.

**On-device checks owed (next build):** (1) **SignIn keyboard** — fresh install, tour on, tap the
username field: the ring must follow it up. This is the highest-value check in the batch and is a
30-second visual confirm. (2) QuickSet regen: pass a card, take the Quick-Set prompt mid-generation,
return, confirm the deck rebuilds and the card can still be passed. (3) Calculator PICK chip still
correct with the server field live.

---

## 2026-08-18 — Phase 0: board-override pins + forced regeneration (branch only, NOT merged)

Branch `feat/unpin-overrides`, rebased onto `origin/main` @ `355bddb`. Scope block:
[`docs/plans/three-model-bakeoff/scope-phase0.md`](../docs/plans/three-model-bakeoff/scope-phase0.md).
Three knobbed fixes for the defect diagnosed in
[`docs/reviews/2026-08-18-valuation-age-audit.md`](../docs/reviews/2026-08-18-valuation-age-audit.md)
plus the `force`-ignored-while-running bug from the bug-sweep ticket.
**Not pushed, not merged** — build-agent output awaiting operator review.

| Gate | Baseline (`origin/main`) | After |
|---|---|---|
| `pytest backend/tests -q` | 3175 passed, 1 skipped | **3224 passed, 1 skipped, 0 failed** (271s) |
| `npx tsc --noEmit` (mobile) | n/a | **not run — zero files under `mobile/`** |
| `mobile/scripts/testid-lint.sh` | n/a | **not run — no testIDs touched** |

- **+49 tests, zero regressions.** `test_override_pin_unpin.py` (41) and
  `test_force_supersedes_running_job.py` (8). Every knob has a behaviour test AND a
  kill-value test.
- **Kill-value byte-identity is proven against captured output, not asserted.**
  `backend/tests/fixtures/override_pin_golden.json` was produced by running the test's
  exact fixture against pristine `origin/main` **before a line of production code
  changed**, and is compared as a whole document (elo / comparison counts / shrunk elo /
  uncertainty / effective value). A companion test asserts the golden still *exhibits*
  the defect (`value > consensus` while `elo` never moved), so the proof cannot rot into
  a tautology if the fixture drifts.
- **The fixture reproduces the audited numbers exactly**: consensus value 1138.83, pinned
  board value 1385.95, and at the kill values the effective value sits at 1215.87 —
  *above* consensus purely because the player was voted on. With F1 on it is 1138.83,
  i.e. exactly consensus.
- **Mutation-checked.** Reverting the impression gate makes
  `test_a_superseded_job_writes_no_impressions` fail with **4 orphaned impression rows**;
  reverting the route gate makes `test_forced_request_while_running_spawns_a_new_job`
  fail. A control test proves the same harness *does* write impressions normally, so the
  zero-rows assertion is not vacuous.
- **Two existing test files changed, both because the contract genuinely moved, neither
  weakened.** `test_rnk_elo_golden.py`'s "an overridden player's Elo never moves" was the
  pre-F2 contract; it is now three tests (pinned against *earlier* swipes; released by a
  *newer* one; the old contract restored by the kill switch). `test_elo_memoization.py`'s
  spy reconstructed `_elo_cache_key` by hand and needed the pin knobs added after they
  were folded into the key (so a kill pulled via `PUT /api/admin/config` takes effect on
  warm sessions immediately).
- **Prod blast radius measured read-only** (`DATABASE_URL_PROD`, `SELECT` only under
  `default_transaction_read_only=on`), 2026-08-18: 4,013 comparisons, 2,721 inert
  (67.8%); 2,735 pinned entries, 739 of them carrying at least one vote. With the shipped
  defaults live comparisons stay at **1,292/4,013 (32.2%)** — F2 is inert on legacy pins
  by design. What F1 changes immediately: **6,250 of 8,026 confidence-contributing
  player-sides (77.9%) stop counting.**
- **Sim gate: Tier 4 (none, CI only).** Backend-only diff; zero files under `mobile/`.
  `qa/sim-runs/last-sim-run.json` not written — under D-056 there is nothing to run.
  `FTF_SKIP_SIM_GATE=1` is the standing posture for any push.
- **Not covered by any test here:** whether released boards actually produce better decks.
  That is an empirical question and the named lever is `pin_legacy_at_epoch` — a single
  `PUT /api/admin/config` to set and to undo. See scope §6.

---
## 2026-08-18 — Operator bug sweep B1–B5 (five fixes, two adversarial rounds)

**Branch:** `fix/bug-sweep-2026-08-18` (off `origin/main` `90fb19a`). **Ticket:** [`docs/reviews/2026-08-18-bug-sweep/ticket.md`](../docs/reviews/2026-08-18-bug-sweep/ticket.md).

| Gate | Baseline (pre-change) | After |
|---|---|---|
| `pytest backend/tests -q` | 3125 passed, 1 skipped | **3148 passed, 1 skipped** |
| `npx tsc --noEmit` (mobile) | clean | **clean** |
| `mobile/tests/check-*.js` | 48 suites, all pass | **54 suites, all pass** |
| `mobile/scripts/testid-lint.sh` | OK | **OK** |

Baseline was captured on a clean worktree **before any edit**, so every post-change result is
attributable. Note the baseline required a real `npm ci` — an initial copied `node_modules` was
stale and produced a phantom `expo-document-picker` error that was **not** a real failure.

**Six new suites** (+23 tests): `test_pick_labels_in_matches.py` (16), `test_tier_order_roundtrip.py`
(7), `check-guide-spotlight-tracking.js`, `check-tier-move-placement.js`,
`check-picker-pick-filter.js`, `check-swipe-failure-recovery.js`. None registered in
`mobile/package.json` — CI globs `tests/check-*.js`.

**Every new test was sabotage-verified RED→GREEN.** Notable, because the first attempts were not
sound:
- `check-tier-move-placement.js` was **polarity-blind** — a reviewer inverted both direction guards (shipping the opposite of the requested behavior) and all 12 assertions stayed green. Rewritten to lift the updater bodies out of source and assert real placement; the same inversion now fires 10 assertions.
- `test_digit_only_ids_skip_the_pick_query` was **vacuous** — it raised `AssertionError` inside a block guarded by `except Exception`. Rewritten against a connection spy with a positive control. See **G-050**.
- `check-swipe-failure-recovery.js` asserted the guard clear by text containment, so keying it on `ctx.tradeId` instead of `ctx.rawId` would have passed while silently restoring the bug for edited cards. Now pins `ctx.rawId`.
- `check-guide-spotlight-tracking.js` check 8 asserted only that a viewport predicate existed, and pinned an incomplete clamp. Now executes the arithmetic.

**Simulator gate:** not run — Maestro/simulator work is retired (**D-056**, 2026-08-15);
`FTF_SKIP_SIM_GATE=1` is the standing posture. TestFlight is primary QA.

**Shipped:** `main` `60105ca` (sweep) → Render **live**; `7583358` is the final tip. TestFlight
**build 117**, submitted and processing. Note the marketing version stayed **1.14.0**, not 1.14.1:
`eas.json` sets `appVersionSource: remote` and the project has an `ios/` directory, so EAS reads
`CFBundleShortVersionString` from `Info.plist` — the `app.json` bump was inert (the #131 bare-workflow
gotcha, `docs/runbook.md:452`) and was reverted so the repo states what actually shipped. A real
version bump means editing `Info.plist` and cutting another build.

**Sim gate skipped** (`FTF_SKIP_SIM_GATE=1` on all three pushes): Maestro/simulator work is retired
per **D-056**; this is the standing posture, not a deviation.

**Not covered by automation:** B1's spotlight tracking is verified structurally only — no test
exercises a real scroll, so the visual behavior rests on review plus on-device QA. B2's client-side
ordering is now behavioral, but no flow drives the multi-select chip row (TiersScreen still exposes
only four testIDs). **On-device checks owed:** (1) analyst tour on Trades — scroll during `s2.2`,
ring must track and must vanish cleanly when the card leaves the viewport; (2) Tiers **single-position**
tab (not "All" — its per-position re-spread confounds the read), chip-move a player down, confirm top
placement, then tap the same chip again and confirm nothing moves; (3) calculator "Real values" →
PICK chip shows rungs, and RB no longer lists them; (4) Matches both segments on a Sleeper league
with traded picks — expect `2026 1st` / `2026 2nd (from Jared)`; (5) force a swipe failure and
confirm the card can still be passed afterward.

---

## 2026-08-18 — Engine quality wave (D-074, renumbered from D-068) built, NOT shipped

Branch `feat/engine-pick-and-diversity` off `origin/main` @ `90fb19a`. Five knobbed
ranking/gating fixes for the two live-corpus defects (picks buying fairness for free;
one asset flooding a whole deck). **Not pushed, not merged** — build-agent output awaiting
operator review.

- **pytest 3150 passed / 1 skipped / 0 failed** (264s) on the branch tip.
  Baseline on `origin/main` before any edit: **3125 passed / 1 skipped** — so **+25 new
  tests, zero regressions**.
- **25 tests** across `backend/tests/test_engine_quality.py` (22) and
  `backend/tests/test_engine_quality_golden.py` (3). Each of the five knobs has a
  behaviour test AND a kill-value no-op test; C1 additionally pins the brief's explicit
  property, *adding a pick to a fair package does not raise composite*, with a
  fixture-validity assertion that the defect IS live at the kill value (bare 1.554 →
  padded 1.584 uncapped; 1.554 → 1.554 with C1 on).
- **Kill-value byte-identity is proven against real pre-wave output**, not asserted:
  goldens for a deck and an asset-ideas run were captured by executing the same fixtures
  in a throwaway worktree at `origin/main` @ `90fb19a`, and `test_engine_quality_golden.py`
  asserts all-five-knobs-killed reproduces them exactly. A third test asserts the goldens
  are **not** vacuous (live defaults must differ), so the proof cannot silently rot into a
  tautology. Re-capture procedure is in that file's docstring.
- **Defect B fixture deck, before/after:** the flood source headlines **21 of 36** cards
  across three counterparties uncapped; **2** with `deck_headliner_cap=2`. The fixture
  floods ACROSS opponents on purpose — a per-opponent cap of 2 would still have served six.
- **Three existing tests moved and one guard was added as a result of the wave, all
  understood:** `test_fairness_gate_golden.py::test_v2_v3_fairness_score_parity` exposed
  that C1's ties let a padded sibling evict the bare deal (fixed by the tie-break, no test
  edit); `test_outlook_direction.py` (6 tests) exposed that an EMPTY job seed map makes
  "centerpiece" degenerate to "largest player id" (fixed by disabling the cap with no seed
  map, no test edit); `test_asset_ideas.py::test_receive_direction_mirrors_grouping`
  exposed that an absolute-gap C2 band mis-ranks a 0.572-fairness bare deal above its
  0.697 sibling (fixed by re-basing the band on fairness, no test edit). **No existing
  test was weakened to make this wave pass.**
- **Sim gate: Tier 4 (none, CI only)** per the operator's build brief — backend-only diff,
  zero files under `mobile/`. `qa/sim-runs/last-sim-run.json` not written; nothing to run.
- **Not covered by any test here:** the live-corpus effect. The five defaults are reasoned
  from fixtures, not fitted to the 563-impression corpus — each knob is the named tuning
  lever and a re-run of the corpus query is the measurement.

## 2026-08-18 — Dismiss cooldown (D-067) shipped

- **pytest 3125 passed / 1 skipped / 0 failed** on the merged tree (`505ca2c`), run pre-push.
- **15 tests** in `backend/tests/test_pass_cooldown.py`; **8 named sabotages** applied → RED → reverted: `shrink-window`, `unbounded-window`, `one-window`, `fail-open`, `db-only`, `alias-only`, `ignore-amnesty`, `amnesty-everything`, `amnesty-likes`. `alias-only` REDs **only** the format-switch test — that test earns its place catching the alias trap rather than duplicating its neighbour.
- Two-sided bars included by design: the cooldown must **expire** (a 20-day dismiss returns) and the amnesty must be a **boundary** (a post-cutoff dismiss still suppresses).
- **Sim gate: n/a per D-057** (Maestro/simulator retired). No TestFlight build cut — backend-only change; mobile identical to v1.14.0 build 116.
- Deploy verified **by content** (`pass_cooldown_days` present in prod `/api/admin/config`), not by uptime.


## 2026-08-17 — Decline reason capture SHIPPED + v1.14.0 build 116 to TestFlight

**Code.** Two squash merges: backend `feat/decline-reasons-backend` @ `5056d1e`, mobile
`feat/decline-reasons-mobile` @ `4d57aae` (main `b97744c..8082aa2`), plus the gen-v2 G6 knob
reconciliation `92d2358`. Flag `feedback.decline_reasons` ships **true for all users**.

- **Merged-state backend suite: 3110 passed / 1 skipped / 0 failed** (254s), incl. 58 new tests in
  `test_decline_reasons.py` — gate + kill-switch byte-identity, progressive-write idempotency,
  impression_id fallback matrix, the mobile payload verbatim, the per-code Elo matrix with the knob
  on AND off, analytics props.
- **Mobile:** `tsc --noEmit` **clean** and `testid-lint OK` on a worktree at `main` after `npm ci`
  from main's lockfile. 38/38 mobile check suites green on the branch tip; merged mobile files were
  verified byte-identical to that tip, so the result carries.
- **Correction to an earlier claim:** the `ImportRankingsSheet.tsx` → `expo-document-picker` TS error
  previously recorded as "pre-existing on origin/main" is **not a real defect** — it is an artifact of
  a stale shared `node_modules`. A correct install yields zero TS errors.

**SIM GATE: WAIVED by operator, 2026-08-17.** Tier-1-class mobile screen change; operator waived the
requirement and accepted "green on touched flows + documented notes on the rest". The two Maestro
flows (`decline-reasons-fixed-option.yaml`, `decline-reasons-other-free-text.yaml`) were **authored
but never executed** — they were blocked on the all-on flag fixture, which this merge supplies, so
they are runnable from now on with no passing run behind them. Pushed with `FTF_SKIP_SIM_GATE=1`.
**TestFlight is the only runtime evidence this feature has.** Not covered by any executed test: the
on-device keyboard/send-button interaction, and the real device → route write path.

**Release.** EAS build `d57f593e` = **v1.14.0 build 116**, production profile, built from a clean
worktree at `main` @ `67b54f6`; status `finished`; `eas submit` uploaded to App Store Connect
(submission `e834b0bf`) during an active EAS Submit partial outage — build and submit were
deliberately decoupled for that reason.

- **Build-source trap caught (worth remembering).** The first attempt, build `e26e0fc6`/115, was
  **cancelled**: `eas build` archives the *local working directory*, and this repo's main checkout sits
  on `session-2026-08-13-notif-ship`, **141 commits behind main**. That archive contained neither
  `DeclineReasonPanel.tsx` nor `declineReasons.ts` and carried version 1.13.2 — it would have shipped
  the feature-less old app to TestFlight labelled as a downgrade. Always build from a checkout you have
  confirmed contains the feature files.
- **Prod flags verified live** post-deploy via `GET /api/feature-flags`: `feedback.decline_reasons: true`,
  `trade_gen.v2: false`, `trade.presentment_rules: true`.

---

## 2026-08-17 — 2026-08-16 feedback wave shipped (17 items, v1.13.5 build 114)

- **Merged-tree gates (orchestrator-run, integration branch):** pytest **3050 passed / 1 skipped / 0 failed**; `tsc --noEmit` clean; **48/48** `check-*.js` structural suites; `testid-lint.sh` OK.
- **Sabotage discipline:** every new behavioral test across all 7 groups proven RED on its named sabotage then green on revert (G6 14/14, G5 13/13, G3 8 sabotage classes, G2 T-P1..T-S10, G4 U-1..U-4 + BT-1, G9 U-1..U-5 + S-10a..e, G1 backend 4 + mobile 7). Phase-4 added 5 more; two of them (F-5 consensus `_emit`, F-7 hide-sites) REDded **only** the new test while the pre-existing suite stayed green — the coverage gaps were real.
- **Cross-group tripwire:** G4's `test_offer_hard_lock_330.py` (BT-1) green against G6's rewritten engine on the merged tree — the single-pin hard lock survived the presentment rewrite.
- **Sim gate: NOT run — n/a per D-056** (Maestro/simulator retired). Runtime evidence for this wave is the per-group operator TestFlight checklists on **build 114**, still owed.
- **Deploy verified by content:** `trade.presentment_rules = True` in prod `/api/feature-flags` (170 flags). Render auto-deploy did NOT fire; deploy triggered explicitly (see `docs/recovery/2026-08-16-feedback-wave-sweep.md`).
- **Owed:** operator prod-DB deck-eval replay (G6 bands on divergence boards + real like history); #339 `pick_gap_frac` tuning (no pick-carrying candidates in any corpus); TestFlight checklists; first-week `presentment-tripwire` watch.



## 2026-08-13 — Notification inbox growth surface phase 1 (SHIPPED to `main`)

- **Change:** five commits, rebased onto `3b64a44` and merged to `main` on the operator's ship directive (which also resolved the `counter_offer` four-not-five question and ratified the two adjacent dead-tap fixes). Taxonomy registration → backend inbox rows + coalescing + server-side dismiss → both clients (glyphs, routing, instrumentation, empty state) → docs. `express`-equivalent gate posture: **sim gate SKIPPED, `FTF_SKIP_SIM_GATE=1`**, per D-P1-08 restated in the build brief.
- **Backend:** `pytest backend/tests -q` → **2685 passed / 6 failed / 1 skipped**. The 6 failures are all in `test_rookie_scope.py`, are **pre-existing on `origin/main`** (verified by `git stash`-ing every change and re-running that file alone, which failed identically), and are **local-only**: CI runs Python 3.12 and is green on `main` (`gh run list --workflow ci.yml`); local is 3.14. **Not caused by this work, and not fixed by it.**
- **New:** `backend/tests/test_notif_inbox_growth.py` — 13 tests over the three things whose failure mode is silent: GD-8 coalescing (one row per league per UTC day, incl. the yesterday boundary and the dismissed-row-is-not-a-target case), the `match_expiring` idempotency gate (incl. cross-type metadata comparison and the fail-closed path), and server-side dismissal (retention, per-user scoping, and that clearing is point-in-time rather than a mute).
- **Mobile:** `npx tsc --noEmit` exit 0; `bash scripts/testid-lint.sh` OK; `node tests/check-notif-glyphs.js` **5/5**.
- **`check-notif-glyphs.js` earned its keep on its first run.** It failed immediately on `trade_accepted` / `trade_declined` — the DB writes `f"trade_{outcome}"` while only the push kind `match_accepted` was in `V2_MATCH_KINDS`, so two of the four ORIGINAL inbox types had a glyph and a dead tap. Code review had not caught it; the test did, before any of this shipped.
- **Web:** `node --check web/js/app.js` clean. **No web test harness exists**, so web's glyph map, tap router and the new `dismiss-all` call are covered only by the parity test's source-text assertions. The `switchView('matches')` fix and the dismiss round-trip have **never executed in a browser**.
- **NOT verified anywhere:** every row template, the new empty state, the empty-state invite gate, and all three analytics emitters. Nothing has rendered on a simulator or a device. The four backend write sites have not fired against a real DB — their tests exercise the DB helpers directly, not the routes.
- **Simulator gate + Maestro: WAIVED** under **D-P1-08**, restated by the operator in the build brief. No `qa/sim-runs/last-sim-run.json` written — **not fabricated**.
- **Standing caveat, unchanged and now one suite worse:** no `check-*.js` suite runs in CI (`.github/workflows/ci.yml` runs pytest, `tsc`, and testid-lint only). `check-notif-glyphs.js` therefore **gates nothing**, on a cross-client enum whose whole failure mode is silence.

---

## 2026-08-12 — Feedback #300 (position-scoped trade candidates), shipped LIT with gates waived

- **Change:** `5139b45` (PR #112), v1.13.1 **build 106**, both flags **ON**. Backend `medians` field on `/api/league/power-rankings`; mobile divider + Buyer/Seller bands + stacked-roster drill-in + Offer/Target handoff; rules A and B removed ([D-044](DECISIONS.md)); two analytics events.
- **Verified on the merged tree, re-run by the orchestrator rather than taken from agent reports:** `pytest backend/tests -q` **2610 passed / 1 skipped**; `tsc --noEmit` exit 0; `testid-lint OK`; `check-league-drill-in` 29; `check-analytics-297-302` 35; `check-single-pin-actions` 17; `check-league-candidates-300` 67; `check-picks-subset-invariance` 72; `check-analytics-300` 51. **271 structural assertions.**
- **Falsification:** 40 + 12 + 42 sabotages executed across the three build rounds. **One genuine false pass found and fixed** (S21: dropping `if (!query.isFetched) return` left the suite green because the assertion matched an identifier that also appears in the dep array). That is the **fifth** false-passing test caught in this session across five independently authored suites.
- **Simulator gate: WAIVED by operator. Maestro execution: WAIVED by operator.** `06-position-trade-candidates.yaml` is authored and **has never run**. No `last-sim-run.json` written — not fabricated. **The 44pt hit-slop treatment, the divider and the rule-A removal have never executed on a device or simulator.** The operator confirmed the shipped build behaves in TestFlight, which is the only runtime evidence in existence for this feature.
- **Analytics verified in production.** Deploy-then-probe run post-merge: 4 events posted, `{"accepted":4,"dropped":0,"rejected":[]}`, then every property read back out of `user_events.props` — both `league_pos_candidates_viewed` rows and both `league_candidate_pinned` mirror combinations `(offer, below)` / `(target, above)`. Note the trap this gate exists for: without `X-Device-Id` the response is `{"accepted":0,"dropped":0,"rejected":[{"reason":"no_identity"}]}`, which has `dropped == 0` and reads as a pass.
- **Still true and worth repeating:** none of the six `check-*.js` suites run in CI. They are `npm run`-only, so **none of the 271 assertions gate anything**.

---

## 2026-08-12 — P1 audit remediation shipped (sim gate retired by operator, not waived)

- **`express`: P1 remediation shipped — simulator gate SKIPPED, `FTF_SKIP_SIM_GATE=1`.** Not a
  one-off waiver: operator decision **D-P1-08** retires the Maestro/simulator/screenshot
  apparatus as standing policy — it consumed more budget than it returned and its quality
  degraded as the surface grew. **TestFlight is now the primary QA method.** No
  `qa/sim-runs/last-sim-run.json` written — **not fabricated**. The pre-push hook fired and was
  overridden deliberately, with the operator's explicit go. `CLAUDE.md`, `githooks/pre-push` and
  `docs/runbook.md` still describe the old policy and are **owed an update** (D-P1-08).
- **Verified instead:** full backend suite **2663 passed / 1 skipped** (3m51s) on the rebased
  tree; `npx tsc --noEmit` clean against a fresh in-worktree `npm ci`; `testid-lint` exit 0;
  `check-anchor-labels.js` 20/20; `check-invite-social-proof.js` 13/13. Baselines measured on
  this tree before editing, never quoted from another branch: 2467 → 2504 (P1-7) → 2663 (after
  rebase onto `main` plus the two pre-ship fixes).
- **NOT verified on device.** Five changed anchor rung labels, the anchor progress hint, both new
  invite surfaces and the share-image footer are visual and have never rendered on a simulator or
  a phone. This is the accepted cost of D-P1-08 and is owed on the TestFlight pass.
- **Sabotage-proven guards.** The anchor-label AST walker **false-passed on its first cut** — it
  inspected only the root of each initializer, so `key === '1_second' ? '1 2nd' : anchorLabel(key)`
  slipped through; fixed to walk the whole subtree, all five mutations now fail as intended. The
  tier-route 404 was proven to come from the flag guard rather than a missing route (body shape +
  `url_map` membership). The `league_id` scrub exemption was proven narrow three ways: an email
  under the same key is still redacted, a long digit run under any other key is still redacted,
  and the allowlist is exact-key rather than substring.
- **Analytics NOT yet proven end-to-end.** T1 registration ships in this push, but the corrected
  probe (**HLD §H-6**: `X-Device-Id`, valid envelope, `accepted > 0` **and** `dropped == 0`, then
  a read-back of `user_events.props`) runs against production **after** the Render deploy. Until
  it passes, treat every new event as unproven — the endpoint returns 200 while dropping. The
  original probe spec in this round would have passed against a broken build; that is why it was
  corrected before use.
- **Not shipped, deliberately:** email capture (built, then **reverted in full** — flag, policy,
  docs and living-memory — by operator decision: the sequencing was backwards and no
  email-sending infrastructure exists to consume it), P1-9 trade push and P1-10 Sleeper analytics
  (both still hold unanswered build-blocking decisions), P1-11 (dropped, D-P1-01).

---

## 2026-08-12 — Send in MFL + Send in ESPN shipped live (sim gate WAIVED all session, CI never ran)

- **`express`: Send in MFL + Send in ESPN + platform unlink + ESPN credential verification shipped — gates skipped by operator.** `FTF_SKIP_SIM_GATE=1` on every push (warning emitted each time); **no `qa/sim-runs/last-sim-run.json` written — not fabricated**. CI never ran: the operator directed direct-to-`main` pushes rather than PRs. `main` moved `3293f4a` → `cad99fb`.
- **Verified instead of CI**, per push: targeted backend suites (178 → 135 → 123 → 122 depending on surface), 12→18 `mobile/tests/check-*.js` including main's own P0-6/P0-7 pins, `testid-lint` exit 0, `tsc --noEmit` clean on a fresh in-worktree `npm ci`. The full ~2,400-test suite was **deliberately not run** — it stalled four separate agents mid-session.
- **Sabotage-proven guards** (each failed first, then restored): MFL pick hard-block (guard removed ⇒ the mocked write was reached with the pick silently dropped); ESPN pick + unmapped-asset hard-blocks; **cross-user unlink isolation** (removing the `WHERE user_id` clause made another user's row deletable — the security property that mattered most).
- **TestFlight 1.13.0 builds 102/103/104/105, then 1.13.1 build 107.** Every status read from `eas-cli build:list --json`, never the exit code — **`eas build` exits 0 even when the remote build ERRORED** (a concurrent session lost builds 99/100 that way). Build 106 was another session's. **Build-ordering lesson: flags are server-side, so `espn.send` could not be enabled until a build containing the lazy send-triggered auth existed (103) — enabling a flag whose client code is absent from the installed build *degrades* it.**
- **Live production verification, by content not by uptime:** `/api/feature-flags` serves `trade.send_in_mfl: true` and `espn.send: true` (neither key existed before); `DELETE /api/espn/link` and `DELETE /api/mfl/auth-link` both return 401 unauthenticated (route live and auth-gated, not 405).
- **MFL write path LIVE-VERIFIED** — a real 2-for-2 proposal succeeded from the app (`trade_sent {platform:"mfl", outcome:"proposed"}`). Because the adapter **refuses ambiguous success**, that outcome is positive evidence the real import response parsed unambiguously. `pendingTrades` also read live: field vocabulary confirmed, `FP_0002_2028_2` confirms the pick encoder against a real trade.
- **ESPN write validated without spending a real trade** — negative probes with a nonexistent `relatedTransactionId` returned 409 `TRAN_NOT_FOUND` for both `TRADE_ACCEPT` and `TRADE_DECLINE`, and `items:[]` returned 409 `TRAN_INVALID_TRADE_TEAM_COUNT` for propose. Both are validation-class errors only reachable *after* auth, so auth + envelope + `type` are all confirmed while nothing real was touched. **No real ESPN send has been made from the app — that remains owed.**
- **Sleeper iOS reachability probe: PASS 4/4** (Chrome-spoofed and honest headers × Wi-Fi and cellular, all HTTP 200), run from TestFlight build 107 and reported via `sleeper_probe_result` analytics rather than transcription. Probe shipped, run, and **deleted the same day**; result in `../docs/plans/sleeper-ios-reachability-probe-result-2026-08-12.md`.
- **Analytics correctness checked, not assumed:** `trade_sent`'s NULL top-level `platform` column initially looked like a repeat of the NULL-`platform` incident. It is not — that column is the *emitter* (`ios`/`server`), the fantasy platform lives in `props.platform`, and `sleeper_send_succeeded` behaves identically. New event names were added to `NON_INTENT_EVENTS` in the same commit that registered them.
- **Flag-mirror trap fired twice.** Any new key in `config/features.json` must be mirrored into `release.json`, `onboarding-v2.json`, and `profiles-on.json` or `test_seed_ui_test_db.py` fails (69 tests). Caught both times before push.
## 2026-08-11 — P1-7 anchor + manual unlock, derived rung labels (NOT merged, branch-only)

- **Change:** branch `p1-remediation-2026-08-11`, three commits. (1) Per-method unlock ladder — `'anchor'` gains its first arm (audit A-16: it could never unlock), `'manual'` loses its unconditional `True` (A-17), both reading `RankingService.board_override_count()`; `_tiers_rule()` extracted; `database.backfill_anchor_unlocked_formats` added as the first-unlock fan-out suppression; additive `anchor_count`/`anchor_required` on `GET /api/rankings/progress`. (2) Anchor rung labels derived from `TIER_LABEL` (five of eight had drifted, not the two the audit found) + `mobile/tests/check-anchor-labels.js` + the wizard's unlock hint + `anchors.rung.*` testIDs. (3) The `anchors-done` seed profile and its `app_user.anchors` seeder handler.
- **Verified (this worktree, re-run after every commit):** `pytest backend/tests -q` **2504 passed / 1 skipped**, against a **2467 / 1 baseline measured on this same tree before the first edit**. The +37 is fully accounted for and contains no pre-existing failures: `test_anchor_unlock.py` **29 new** (one case parametrized ×2), `test_pick_anchor.py` 17 → **18** (the D15 lane-separation assertion), `test_seed_ui_test_db.py` 69 → **76**. `npx tsc --noEmit` exit 0, no output; `testid-lint.sh` → `testid-lint OK`; `check-anchor-labels.js` **20/20**.
- **Falsification — and it earned its keep.** Every assertion in `check-anchor-labels.js` was run against a deliberately sabotaged tree. **The first cut false-passed on the single most important mutation:** re-typing a label as `label: key === '1_second' ? '1 2nd' : anchorLabel(key)` — the original defect wearing a ternary — because the assertion inspected only the *root* of each `label` initializer. This is exactly the case the design cited as the reason an AST walk beats a grep, and the AST walk fell into it anyway. Fixed to search the whole initializer subtree and to whitelist two exact initializer shapes; all five mutations (ternary, template literal, indirection through another function, `no_value → 'waivers'`, inlined `BELOW_LADDER_LABEL`, dropped `ANCHOR_TIER` key) now fail as intended. Same family as [G-035](GOTCHAS.md).
- **The seed fixture proves the unlock rather than assuming it.** `anchors-done.json` seeds `unlocked: false` deliberately — a seeded `unlocked_formats` row satisfies the monotonic floor *before* the new branch is consulted, so the obvious fixture would have gone green with the fix reverted ([G-037](GOTCHAS.md)). `_validate_anchors` now **refuses** the incoherent shape, and `test_anchors_done_actually_clears_the_unlock_bar` builds a real `RankingService` from the seeded board and asserts it clears the bar — so the fixture and the branch are proven to meet, not assumed to.
- **Sim run: none.** Per [D-P1-08](../docs/plans/audit-p1-remediation/DECISIONS-p1.md) the Maestro/simulator apparatus is retired and TestFlight is primary QA. No `last-sim-run.json` written — **not fabricated**.
- **Not verified on device, and it should be:** the wizard's new unlock hint (`anchors.unlock-hint`) and the five changed rung labels are visual changes no automated gate here can see. `check-anchor-labels.js` proves the labels are *derived*; it cannot prove they *render*. **Owed on the next TestFlight pass.**
- **Same pre-existing gap as the batch below:** none of the `mobile/tests/check-*.js` scripts run in `.github/workflows/ci.yml`, so `check-anchor-labels.js` **gates nothing** until that job is wired. It is a `npm run test:anchor-labels` a human has to remember.

## 2026-08-11 — Feedback #297/#298/#299/#302 + batch analytics (sim gate DEFERRED, operator-directed)

- **Change:** branch `feedback-integration-v2`, cut from `origin/main` @ `f65bab7`, merging `feedback-build-league-299-302` and `feedback-build-trades-297-298` plus an analytics round. #297 honest-empty lineup row; #298 single-pin deck recovery (V1) + the team-pill regenerate defect; #299 32pt League roster tiles (−47%, 728pt reclaimed on a 26-man roster, 4 → 8 players above the fold); #302 stack-header drill-in exit + the first Android `BackHandler` on that screen. Analytics: two new client events (`lineup_impact_unavailable`, `league_team_closed`), three widened props (`mode` on `find_trades_tapped` + `trade_card_viewed`, `source` on `find_trades_tapped` — the last a **bug fix**, that prop had been sent into an empty registry and popped on every row since #257).
- **Verified (merged tree, this worktree, re-run by the orchestrator — not taken from agent reports):** `pytest backend/tests -q` **2452 passed / 1 skipped**; `npx tsc --noEmit` exit 0, no output; `testid-lint.sh` → `testid-lint OK`; `check-single-pin-actions.js` **17/17**; `check-league-drill-in.js` **29/29**; `check-analytics-297-302.js` **35/35**. 81 structural assertions total.
- **Falsification:** every behavioural assertion was run against a deliberately sabotaged tree — 30 (league) + 9 (trades, four aimed at the seam #169 created) + 20 (analytics). **Four false-passing tests were caught this way and fixed**, in four independently authored suites: an ancestor-walking JSX gate check ([G-035](GOTCHAS.md)); a first-element-only testID lookup; a platform assertion that survived a sabotage leaving the lookup line in place; and three raw-source scans matched by comments naming the constructs they forbade. Treat "my test passes" as unproven here until a sabotage fails it.
- **Sim run: DEFERRED by operator** ("Good to signoff that we ship without a flag & defer the sim gate"), after the bright-line disclosure that the batch touches analytics surfaces. **No `last-sim-run.json` written — not fabricated.** Two Maestro flows authored but **NOT executed**: `mobile/.maestro/flows/league/05-drill-in-back-affordance.yaml` and `mobile/.maestro/flows/smoke/12-trades-single-pin.yaml`.
- **The Android hardware `BackHandler` was WITHDRAWN from this ship, not verified** (operator, 2026-08-11) — precisely because no Android device or emulator was involved at any point and TestFlight is iOS-only. Removing it is what closes the batch's largest unverified-code gap. Two assertions now pin the withdrawal (a live registration turns both suites red), and both were **sabotage-proven** by re-adding the effect and confirming each suite fails. `'hardware_back'` remains a reserved analytics value with no emitter. **Owed with the first non-App-Store release:** restore the effect, flip both assertions in the same commit, and exercise it on a real Android device.
- **Owed at ship, not skippable by the sim-gate deferral — the deploy-then-probe gate.** After merge + Render deploy, hand-roll one `POST /api/events` per new name with its **full** property set and assert both `dropped == 0` **and** every property echoed back out of `user_events.props`. Name-survival and prop-survival are separate silent failures: `analytics_ingest.py` pops unregistered props with only a counter bump, and `trade_card_shared.landing` is a live in-tree example of a registered name whose prop is discarded. **Do not substitute `GET /api/admin/analytics/health`** — its counters are in-process and reset on deploy.
- **Pre-existing gap, now three times larger:** none of the ten `mobile/tests/check-*.js` scripts run in `.github/workflows/ci.yml`; they are `npm run`-only. **None of the 81 assertions above gate anything** until that is wired. Proposed job in `docs/feedback/items/297-lineup-impact-single-pin/status.md` §5.5.

## 2026-08-11 — P0 remediation batch (sim gate SKIPPED, operator-directed express)

- **Change:** branch `p0-remediation-2026-08-10` — eight P0 launch blockers from the 2026-08-09 mobile UX audit (P0-1/2/3/5/6/7/8 + P0-9 test-prep), 15 code commits + merge of #169. Full corpus in `docs/plans/audit-p0-remediation/`.
- **Verified (merged tree, this worktree):** `pytest backend/tests -q` **2448 passed / 1 skipped / 0 failed** (clean worktree — the 6 environmental `test_rookie_scope` failures of the data-carrying main checkout do not reproduce here, consistent with G-030[#169]); `npx tsc --noEmit` clean; `testid-lint.sh` OK; `check-trade-text.js` 28/28; `check-card-disposition.js` 10/10; taxonomy registration verified name-by-name (16 client + 1 server, zero unregistered emissions — grep table in the W2-P07 build record).
- **Sim run: tier-1 SKIPPED entirely** (operator: "proceed without the sim gate — eating up too much usage", confirmed after bright-line disclosure: batch touches route + flag + analytics surfaces). Push via `FTF_SKIP_SIM_GATE=1`; **no `last-sim-run.json` written (not fabricated)**. Pre-skip on-sim work: app built green (Release, localhost-pinned), dedicated simulator created, pre-flight of all six new flows (every copy string + testID resolves in source), control-run evidence prepared (`git grep` at ab9368f proves the new testIDs absent pre-fix, so the flows fail by construction on the unfixed tree). Runs were blocked twice by another session holding :7001/:5001 before the operator called the skip.
- **Tier decision (recorded for the record): tier 1**, not 2 — the batch adds a screen, changes navigation, and changes rendered state on six screens; tier 2 is "mobile logic, no UI change".
- **Owed at next sim session:** the full tier-1 set + the batch's six new flows (`p0-1-quickset-unlock`, `p0-5-account-only-picker`, `p0-6-espn-copy-trade`, `trades-generation-failure`, `guide-no-false-signoff@release`, `league/invite-join`) + modified captures (`trades`, `matches@espn`, `league@quickset-done`, `leagues@account-only`, `onboarding-tour@fresh`); the P0-9 flag-pinned beat validation incl. the s5.1 proof (use the now-registered `deck_regenerated` row); analytics destination checks; re-captures + freshness sweep (note: TabNav changes are analytics-only — PNGs stay visually accurate, hash-staleness flags under the corrected manifest are false positives).
- **Toolchain gotcha (load-bearing for every future worktree build):** the standing convention of symlinking `mobile/node_modules` from the main checkout makes the app UNBUILDABLE — expo's CLI branches on whether its own directory resolves inside the project root and then requires `metro-runtime`, which is not top-level in this lockfile. Real in-worktree `npm ci` + `pod install` required; `rm -rf mobile/ios/build` also deletes RN codegen sources, so re-run `pod install` before rebuilding.

## 2026-08-11 — #169 frame E + card frame C (sim gate DEVIATION mid-run, operator-directed)

- **Change:** branch `feedback-169-e-and-card` — League Summary collapsed outlook strip (flag-dark, `outlook.odds`) + Pass/Like moved inside the top deck card + `outlook_strip_toggled` analytics event (taxonomy + tracking plan; operator rejected the dark-flag analytics waiver). Doc set (plan/HLD/LLD/PRD/scope rev 2, adversarially reviewed, 21 findings applied) in `docs/feedback/items/169-outlook-league-summary/`.
- **Verified (merged tree):** `npx tsc --noEmit` clean; `testid-lint.sh` OK; `check-card-disposition.js` 10/10 **with double sabotage proof** (guard flip → FAIL; reintroduced TradesScreen testID → FAIL; restored → pass); taxonomy test 18/18 **with sabotage proof** (event removed from allowlist → FAIL → restored). Full `pytest backend/tests -q`: **2371 passed / 6 failed / 1 skipped** — all 6 in `test_rookie_scope.py`, **proven pre-existing and environmental** (fail with origin/main-identical backend bytes in the data-carrying main checkout; 34/34 pass in a clean worktree of the same commit; G-028, fix chip filed). CI on the PR is the clean-environment authority.
- **Sim run: Tier-1 HALTED mid-gate by operator** ("proceed without sim testing — eating up too much usage"); push via `FTF_SKIP_SIM_GATE=1`; no `last-sim-run.json` written (not fabricated). **Partial on-sim evidence before the halt:** extended `06-trades-deck` positional `childOf` asserts PASSED (both disposition buttons proven inside `trades.card-top`, no scroll — fails by construction on the old layout); screenshot proof of the operator's layout; `01-signin` full pass in the final harness config; manual launch-health check. Suite-level failures across 4 attempts were ALL environmental, diagnosed in sequence: `# flags: release` fixture not loaded (guided-avatar tour overlay swallowed taps), backend process reaped by shell teardown, **disk exhaustion to 0 bytes** (25 launch crash-loops in Hermes init — G-027 adjacent; ~4 GB freed), stale Maestro XCTest driver after `simctl erase`. None traced to the change under test.
- **Owed at next sim session:** green full-suite run; post-overlay like/pass tap-through of `06-trades-deck`; the four re-captures (`trades`, `matches`, `sheets-trade-dna`, `league-summary`) + `screen-freshness.sh` sweep; on-sim verification of the three re-derived `onboarding-tour@fresh` anchors.

## 2026-08-10 — Screen-library capture suite (sim gate tier-2 evidence)

- Full consolidated sweep on FTF-iOS18 (iOS 18.4): 43 capture flows, 7 cells
  (5 profiles × release/onboarding-v2), **102 captures, rails all zero in every
  cell** (vcr_misses / sleeper_live_egress_attempts / completed_proposes /
  propose_route_hits). One flaky flow (trios@near-unlock, tab-race — settle fix
  applied, still ~50% per run) recaptured green individually. tsc clean,
  testid-lint green, screen-freshness green ×25, backend suite 2207 passed
  (fixtures commit). Mobile app-code delta this branch: testRouteEntry.ts +
  one RootNav line — exercised by every launch-arg capture cell above.
## 2026-08-10 — Feedback batch #289-#294 (sim gate DEVIATION, operator-directed bypass)

- **SHIPPED 2026-08-10.** Squash-merged as `6c304c7` via PR #103; CI green (backend-tests, mobile-typecheck, maestro-testid-lint). Render deploy **verified by content**, not by uptime: `/api/feature-flags` serves `league.picks_always_counted = true` (155 flags), which only the new build can produce. iOS **1.12.0 build 98** uploaded to App Store Connect (submission `0095a36f`).
- **Version-bump trap, cost one wasted build.** `mobile/app.json` was bumped to 1.12.0 and **build 97 still shipped as 1.11.0**. This is a bare workflow — `mobile/ios/` is tracked — so EAS reads the version from the native Xcode project and ignores the Expo config. `eas build:version:set` manages the **build number** only. The three values that actually ship are two `MARKETING_VERSION` entries in `project.pbxproj` and the literal `CFBundleShortVersionString` in `Info.plist` (PR #104, `7553874`). Bumping `app.json` is necessary for the JS layer and **not sufficient for the binary**.

- **Change:** six feedback items in three groups on branch `feedback-289-294` (base `origin/main` @ `16b1dcb`), 16 commits, 51 files, +15,738/−106. **G1 #289** MFL Draft Room resolves franchise *and* player names (four ordered tiers, never a bare id). **G2 #290/#291/#292** value-aware mock run model + `need_pressure` + mock lifecycle (`abandon_completed_mock_drafts`) + pick affordance before tap + MFL owner names in the mock. **G3 #293/#294** draft-pick value counted in every subset and position filter, behind new flag `league.picks_always_counted`, **graduated to ON at ship by operator direction** ("293/294 ship live") together with its `LAUNCHED_FLAG_DEFAULTS` entry so it is visible from first paint; the flag remains the kill switch. Plus: `mobile/scripts/sim-run.sh` flag-pin repairs, five stale "mock is OFF" doc locations corrected, D-022/D-023/D-024.
- **Suite:** baseline `2308 passed / 1 skipped` after G1+G3 → **2326 passed / 1 skipped**, exit 0 (+18, all new). `npx tsc --noEmit` **exit 0** (real `npm ci` in-worktree — the main checkout's `node_modules` is ~190 commits stale and lacks `@react-native-cookies/cookies`, which yields a phantom error). `testid-lint.sh` **exit 0**. **All nine** `mobile/tests/check-*.js` pass, including two new ones (`check-picks-subset-invariance.js` 71 assertions, `check-mock-lifecycle.js` 52).
- **Sim run: NOT PERFORMED** — operator-directed bypass (`FTF_SKIP_SIM_GATE=1`) after being presented with the coverage gap and choosing it explicitly. **This is a Tier-1 deviation and the batch's largest change is the least covered:** G2's mock engine ships with unit + distributional evidence only and **no end-to-end run**. **Both groups ship live.** G3 was built dark and graduated to ON at ship on operator direction; it keeps a per-feature kill switch (`league.picks_always_counted` -> false, no redeploy). G2 has no per-change switch — `draft.mock` was already ON and the engine change is unflagged — so its only lever turns off the whole mock feature. G2 is therefore the largest change, the least covered, AND the least reversible.
- **Why the mock flow could not run:** `d3-mock-draft-loop.yaml` was authored but is unrunnable — `backend/tests/fixtures/profiles/standard.json` declares one league (`990000000000000001`) while d1/d2/d3 all target `1312140920132497408`, which is in no profile, and the seeder writes **nothing** for `mock_drafts` or draft status. The build agent's "one `leagues[]` entry" estimate was checked and does not hold; this is real seeder work. Pre-existing, unfixed, named.
- **Uncovered by any automated test** (do not read a green suite as covering these): G3 **R-5** and **R-0.4**, and the kill-switch drill **T-S6c** (manual). G1 has **no Maestro flow at all** by design — its acceptance surface is a live check against the operator's Dependables MFL league (62846), also not yet performed.
- **Harness findings — the gate had never actually run.** Every prior ledger entry since the gate's introduction reads "NOT PERFORMED", which is why three defects survived: `--flags` *replaced* the seeded flag map instead of merging; `--flags @file` was documented but unimplemented (the literal string was exported, JSON parsing failed with a stdout warning only, and the run continued with flags OFF); and the handshake fetched `/api/feature-flags` but **only archived it, never asserting** — so a flag-ON tier could assert flag-OFF behavior and exit 0. Additionally `$!` captured the subshell rather than python under bash 3.2 (macOS system bash), so the stale-Flask assertion fired on a clear port **every time** and the EXIT trap orphaned Flask on the port for the next run to talk to. All repaired and each proven by constructing the failure first; nine consecutive runs left no orphan.
- **Failing-first evidence captured** for every behavioral test (G2 T-290-04/10/11/14, T-292-01, D-16 keying; G1 T-289-06; G3 assertions 13/14). Three separate lanes found tests that **passed on the very defect they named** — G1's collision test (its stub raised on the triggering input), G2's one-sided distributional bars (a fully collapsed `sf_tep` board scored *higher* variety than a healthy one), and G3's atomicity assertions (`picksAlwaysCounted={false}` satisfied all twelve). G2's mobile agent also found two of its own first-cut assertions passing on their defects — one because the JSX comment explaining the behavior contained the string it was grepping for.
- **G2 measured results at pinned N=1500, both formats** (`1qb_ppr` / `sf_tep`): P(#1 at 1.01) 0.4553 / 0.6380; P(#1 past pick 3) 0.0893 / 0.0420 (shipped 0.1553); P(#7 at pick ≤4) 0.0000 / 0.0000 (shipped 0.1147); median run size 5.0 / 5.0. Calibration tripwire `test_w2_16` **did not fire**.
- **Fixed in passing:** two G2 tests used fixed user+league ids against the persistent SQLite DB and accumulated rows across runs (second full run reported `cleared 5 rows, expected 3`) — would have surfaced in QA as an unreproducible failure on any machine that had run the suite before. Both now self-clear.

## 2026-08-10 — Outlook: seed-type + IDP-coverage wiring, combined post-fix calibration (NOT merged, no flag change)

- **Change:** two wiring gaps closed, then one combined re-measurement. (1) `scripts/outlook_calibration_backtest.py` gains `seed_type(fx)` and threads `playoff_seed_type` into every `run_outlook` / `get_playoff_format` call, plus a **BUG-3 A/B block** mirroring the existing BUG-1 one; same wiring in `scripts/outlook_preseason_backtest.py`. (2) `pipeline.run_outlook` now calls `strength.lineup_pricing()` and `serialize.py` emits `meta.priced_slot_coverage = {fraction, total_slots, priced_slots, unpriced_slots[], affects_strength}`. `outlook.odds` untouched, `config/features.json` untouched, no `model_config` key, mobile diff is a **type-only** addition (`OutlookPricedSlotCoverage` in `mobile/src/api/league.ts`) with no UI/behaviour change.
- **Suite:** baseline on a fresh `origin/main` reset (`234a018`) **2284 passed / 1 skipped / 0 xfailed** (301 s) → **2297 passed / 1 skipped**, exit 0 (+13). `npx tsc --noEmit` clean (node_modules symlinked from a sibling worktree, removed after). New coverage: 4 payload/coverage tests in `test_outlook_odds.py` (fraction + named unpriced slots, full-coverage league, `affects_strength` false on `trailing_scores`, **prediction-neutrality vs a run serialized without the instrument**), 9 in `test_outlook_playoff_seed_type.py` (an **AST guard** that fails if any `run_outlook`/`get_playoff_format` call in either script omits the setting, the per-fixture seed-type helper, and a load-bearing check that fixed vs reseed brackets give different title distributions and identical playoff odds), plus the `meta` contract pin in `test_outlook_route_cache.py`.
- **Sim run: NOT PERFORMED** — measurement + dark-surface wiring with zero user-visible change (`outlook.odds` false everywhere, mobile diff is a type declaration); branch left unmerged for operator review.
- **Result — in-season, 6 league-seasons / 288 team-week predictions, 10k sims:** playoff Brier **0.0997** vs climatology 0.2500 (**+60.1 %**, cluster-bootstrap 90 % CI [+47.6, +72.2] — excludes 0); title Brier **0.0732** vs 0.0764 (**+4.2 %**, CI [−13.1, +20.0] — **includes 0**). Per week 0.2012 / 0.1065 / 0.0538 / 0.0372. Split by league: all six beat climatology on playoff, **three of six lose to climatology on title**.
- **Result — preseason (week 0), 72 team-seasons:** playoff Brier **0.1968** (+21.3 %, CI **[+2.9, +39.1]**); title 0.0746 (+2.3 %, CI [−18.9, +24.5]). Preseason − week-3 paired Δ **−0.0043** (CI spans 0) — preseason still nominally better than the week-3 model. Median-match leagues 0.2326, H2H 0.1789.
- **Result — the BUG-3 wiring in isolation:** pooled title Brier **0.0733 → 0.0732**; fixed-bracket leagues only 0.0817 → 0.0815; **playoff Brier bit-identical (max \|Δ\| = 0.000000)** and `playoff_seed_type: 1` leagues **bit-identical** (value 1 == reseed == pre-fix behaviour). The bracket rule was wrong for 4 of 6 league-seasons and correcting it moved the pooled title number by 0.0001 — **a null, reported as one.**
- **Over-confidence SURVIVED the fix wave.** Preseason top bucket 0.947 predicted → **0.778** realized (n = 9; was 0.949 → 0.750, n = 8); bottom bucket 0.034 → 0.167. In-season populated buckets stay inside ±0.05 (n = 99 and n = 100). Preseason skill lower CI bound moved the **wrong** way: +4.1 % → **+2.9 %**.
- **Also re-confirmed unchanged:** bye-week μ multiplier still NO-SHIP (Δ +0.0031, CI [−0.0054, +0.0125]; mechanism OLS slope −0.218 vs the naive −1.000); random-re-pairing fallback still costs ~7 % of playoff Brier.
- **Verdict:** (1) **bands, not percentages — stands, and is better supported than before**; a 5 %-rounded playoff percentage from week 6 is an operator risk call, not a validated result (calibration is pooled, not week-stratified). (2) **Gate numbers at week 6, allow bands from week 0, never gate at week 3** — week 3 is dominated by both neighbours and is the only week where title odds lose to a constant 1/12. Report: `docs/feedback/items/169-outlook-league-summary/calibration-combined-2026-08-10.md`; dated corrections issued to the three prior #169 reports.

## 2026-08-10 — Combined post-fix outlook calibration (sim gate DEVIATION, standing operator bypass)

- **Change:** seed-type + coverage wiring and the definitive combined calibration. Mobile diff is **type-only** (`mobile/src/api/league.ts` gains the `priced_slot_coverage` payload field) — no UI, no behaviour, `outlook.odds` false everywhere.
- **Sim run: NOT PERFORMED** — `FTF_SKIP_SIM_GATE=1` under standing operator authority; the smoke suite still doesn't exist and this change class renders nothing.
- **Verified:** full suite **2297 passed / 1 skipped**, exit 0; `tsc --noEmit` clean. Deliverable `docs/feedback/items/169-outlook-league-summary/calibration-combined-2026-08-10.md`.

## 2026-08-09 — ESPN numeric-id guard fix (backend-only, merged to main)

- **Change:** `server._fetch_sleeper_league_meta` + `trade_block_service.sync_league_trade_block` now pair their `isdigit()` guard with `database.is_linked_platform_league`, so ESPN/MFL/Fleaflicker-imported leagues (numeric native ids) no longer fire Sleeper requests that 404 on `/api/session/init` (prod noise + false `vcr_misses` in FTF_TEST_MODE). Same convention as the #149/#150 proxy fix. Commit `e7d0da7`.
- **Suite:** full `pytest backend/tests -q` → **2219 passed / 1 skipped / 1 xfailed**, exit 0 (562 s) — +2 regression tests in `test_espn_link_route.py` pinning both helpers to zero Sleeper calls on a linked ESPN league.
- **Sim run: NOT PERFORMED** — backend-only, no mobile diff, no schema/API/flag surface; pre-push hook gate not triggered (no `mobile/src/` change).
- **Follow-up:** revert the two harness workarounds in worktree `~/ftf-worktrees/screens-wt` (espn.json `sleeper.trade_block:false` pin; 404-cassette sentinel + gap-guard carve-out) once that branch rebases onto this fix.

## 2026-08-09 — BUG-5: IDP/K starting slots are unpriced (fix + backtest, NOT merged, no flag change)

- **Change:** `backend/outlook/strength.py` only — IDP slot eligibility in `select_starting_lineup()` (a `DL` slot now accepts DE/DT/NT, `DB` accepts CB/S/SS/FS, `IDP_FLEX` accepts any defender) plus a new `lineup_pricing()` instrument. New `scripts/outlook_idp_pricing_backtest.py`, `backend/tests/test_outlook_idp_pricing.py`, and one records fixture. No flag, no `config/features.json`, no `model_config` key, no mobile diff; `outlook.odds` still dark.
- **Suite:** baseline on a fresh `origin/main` reset (`359a0ff`) **2217 passed / 1 skipped / 1 xfailed** (706 s) → **2247 passed / 1 skipped / 1 xfailed**, exit 0 (+30). New file alone: 30 passed in 4.8 s.
- **Sim run: NOT PERFORMED** — validation-plus-neutral-fix change class with zero user-visible surface (`outlook.odds` false everywhere, no mobile diff), branch left unmerged for operator review.
- **Damage measured:** the DynastyProcess board carries QB/RB/WR/TE only, so in the operator's **FFv3** league **8 of 15 starting slots price at exactly 0.0** — **53.3 % of slots**, covering **33.0–34.3 % of the points those teams actually scored** (Sleeper `starters_points`, weeks 1–14). FFv3 is **4 of the 6 backtested league-seasons**; Lakeview is 0 %. The unpriced third is weakly differentiating: sd 58–65 season points vs 160–211 for the priced slots.
- **Result — five-variant preseason backtest, 10k sims, split by league.** V0 status quo reproduces the published baseline exactly (pooled playoff Brier **0.1959**, +21.6 %; FFv3 0.1789; Lakeview 0.2298). **Eligibility fix: 0 of 72 predictions moved** (asserted, not assumed). **League-mean fallback Δ +0.0005** (CI [−0.0056, +0.0061]); **coverage attenuation √ Δ −0.0019** (CI [−0.0167, +0.0070]), **linear Δ +0.0042**. Lakeview bit-identical under every variant.
- **Verdict: real defect, no available fix beats the status quo.** No license-clean dynasty IDP board exists (DynastyProcess, nflverse, FantasyCalc, KTC, Sleeper `search_rank` all checked). Shipped the correctness fix + the coverage instrument; the pricing gap is documented, not papered over. Preseason ship verdict unchanged; IDP-league odds must be **labelled offence-only** before the flag lights. Report: `docs/feedback/items/169-outlook-league-summary/idp-pricing-2026-08-09.md`; gotcha G-026.

## 2026-08-09 — Dated DP value boards + preseason-source revalidation (validation only, NOT merged, no flag change)

- **Change:** no product behaviour touched. New `backend/dp_values_history.py` (research-only dated DynastyProcess boards), 24 committed board fixtures + index in `backend/tests/fixtures/dp-values-history/` (484 KB), three scripts (`scripts/dp_values_history_capture.py` — the only one that uses the network, `scripts/outlook_preseason_backtest.py`, `scripts/outlook_pick_capital_dated_values.py`), and two test files. `backend/outlook/` unchanged, `config/features.json` unchanged, `outlook.odds` still dark, no mobile diff.
- **Suite:** baseline on a fresh `origin/main` reset (`ea19d4b`) **2194 passed / 1 skipped / 1 xfailed** (151 s) → **2217 passed / 1 skipped / 1 xfailed**, exit 0 (+23). New files alone: `test_dp_values_history.py` 15 passed, `test_outlook_preseason_source.py` 8 passed, 0.5 s combined.
- **New coverage:** commit resolution (`until=`/`path=` query shape, empty-result `LookupError`), raw-URL sha pinning, `slim_csv` filtering, all three crosswalk join tiers + position-strictness, scoring-column selection, **offline path asserted against an opener that raises on any network call**, refusal-not-substitution for an uncaptured date, fixture-index integrity, **no-look-ahead invariant** (`scrape_date <= key` on all 24 boards), roster rewind to real week-1 rosters, `auto` → `roster_value` at week 0, board-is-load-bearing check, and four re-scoring guards on the committed per-team records (including a deliberate assertion that preseason title odds do **not** beat climatology, so the null cannot rot away).
- **Sim run: NOT PERFORMED** — validation-only change class with zero user-visible surface (`outlook.odds` false everywhere, no mobile diff), and the branch is left unmerged for operator review.
- **Result — preseason `roster_value`, as-of week 0, 6 league-seasons / 72 team-seasons / 6 champion events:** playoff Brier **0.1959** vs climatology 0.2500 (**+21.6 %**, cluster-bootstrap 90 % CI **[+4.1, +38.3]** — excludes 0); title Brier 0.0740 vs 0.0764 (+3.1 %, CI [−17.7, +24.9] — **includes 0, no skill**). Indistinguishable from the week-3 model (paired delta −0.0013, CI [−0.0573, +0.0470]). Over-confident at the extremes (0.9–1.0 bucket: 0.949 predicted, 0.750 realized, n = 8); beats climatology in 4/6 league-seasons. Board coverage 96.8–99.3 % roster, 100 % starting-slot; unmatched DP rows 0.2–1.8 %.
- **Result — hypothesis 1b re-test:** sub-test (i) −0.113 → **+0.076, CI spanning zero**; confound −0.349 → **−0.415**; (ii)/(iii)/buy:sell bit-identical. Verdict **WEAKENED**.
- **Verdict:** preseason **title** odds — do not render. Preseason **playoff** odds — conditional go, banded not precise, BUG-1 (G-024) first. Report: `docs/feedback/items/169-outlook-league-summary/dated-values-revalidation-2026-08-09.md`.

## 2026-08-09 — Outlook odds calibration backtest (validation only, no ship, no flag change)

- **Change:** no product code touched. Added `backend/tests/test_outlook_calibration.py` (22 permanent invariant/fixture tests + 1 strict `xfail` tracking BUG-1), two offline analysis scripts (`scripts/outlook_calibration_backtest.py`, `scripts/outlook_strength_source_compare.py`), 9 committed Sleeper fixtures, and the calibration report. `outlook.odds` remains dark.
- **Suite:** baseline **2136 passed / 1 skipped** → **2158 passed / 1 skipped / 1 xfailed**, exit 0 (142 s). New file alone: 22 passed / 1 xfailed in 3.6 s.
- **Sim run: NOT PERFORMED for the wave push** (`FTF_SKIP_SIM_GATE=1`, standing operator bypass) — the mobile diff is dark-flagged contract/nullability fixes only (`outlook.odds` false everywhere); zero user-visible change.
- **Backtest result:** as-of weeks 3/6/9/12 over 6 real captured Sleeper seasons (72 team-seasons, 6 champion events). Playoff Brier **0.1113** vs climatology 0.2500 (**+55.5 %** skill, cluster-bootstrap 90 % CI [+44.5, +65.9] — excludes 0). Title Brier **0.0725** vs 0.0764 (**+5.1 %**, CI [−13.2, +22.3] — **includes 0, no demonstrated skill**).
- **Verdict:** MARGINAL PASS, conditional — playoff odds ship-worthy after BUG-1 (median-match ingestion, G-024) is fixed; title odds not validated. Report: `docs/feedback/items/169-outlook-league-summary/calibration-report-2026-08-09.md`.

## 2026-08-09 — ESPN round-2 ship (sim gate DEVIATION, standing operator bypass)

- **Change:** cold-load login warm-up reload + reload control + wedge hint; league picker (`espn.league_picker` ON, `GET /api/espn/my-leagues`). Push `89c61b4`, build 96.
- **Sim run: NOT PERFORMED** (`FTF_SKIP_SIM_GATE=1`, standing authority). Maestro flow WAS extended (reload control) but not executed — no runnable dev client.
- **What WAS verified:** 2136 passed / 1 skipped, exit 0 (+27); tsc clean; testid-lint OK; **fan-API shape live-verified against an authenticated fetch on the operator's real ESPN session** — caught the lowercase-"ffl" filter bug (real abbrev is "FFL") pre-merge; fixture now mirrors the real payload. Round-1 fixes field-validated by the operator's successful private-league link (league_read 200 in events, 22:44 UTC).

## 2026-08-09 — ESPN-fix + morning-batch + observability ship (sim gate DEVIATION, standing operator bypass)

- **Change:** the wave below (ESPN webview fixes, #285, #286-288, integrations docs, api_observability) merged and pushed as one; combined suite **2109 passed / 1 skipped, exit 0**, tsc clean on final branch. `FTF_SKIP_SIM_GATE=1` under standing operator authority; ESPN fix's REAL validation is the operator's TestFlight walkthrough with the private league (checklist in `docs/feedback/items/espn-webview-escape/status.md`) — build 95.

## 2026-08-09 — API observability build (flag `obs.api_events` ON; worktree agent, merged/shipped same day — see entry above)

- **Change:** operator-directed observability program (`docs/feedback/items/api-observability/status.md`): `backend/api_observability.py` — outbound wrapper around every external egress chokepoint (Sleeper REST/GraphQL incl. the 3 documented bypass sites, ESPN, MFL, Fleaflicker, DP CSVs, KTC, Anthropic, Expo, Apple/Google) + inbound Flask hooks; events land in `user_events` (`api_call`/`api_request`, `user_id='system:api'`), errors always + successes 1-in-10 sampled (`model_config obs_success_sample_n`), 30 d retention purge, admin report `GET /api/admin/analytics/apihealth`. Backend + docs only; no mobile/web changes.
- **Sim run: NOT PERFORMED** — backend-only change class, and the branch is deliberately left unmerged for operator review (build agent has no merge authority; sim gate applies at ship).
- **What WAS verified:** baseline `pytest backend/tests -q` on the release base → **2086 passed / 1 skipped, exit 0**; after build → **2109 passed / 1 skipped, exit 0** (+23 in `backend/tests/test_api_observability.py`: per-service wrapper capture with cookie/JWT-never-stored redaction assertions, inbound hook capture + exclusions, 1-in-N sampling vs errors-always, kill-switch zero-writes, poisoned-event-store failure isolation, retention purge, apihealth report + `service` filter). `tsc --noEmit` n/a (no mobile diff).

## 2026-08-09 — Design-decision batch (#270/#272 A/B, #169, #279) (sim gate DEVIATION, standing operator bypass)

- **Change:** experiment `trades_home_inline` (strip/canvas variants, operator on strip), flag `trade.position_impact` ON, experiment `aggregate_tier_labels` (operator-only), two mock-lab revisions. Batched at operator direction ("Don't push E1 until we resolve these other two items too").
- **Sim run: NOT PERFORMED.** Standing bypass (`FTF_SKIP_SIM_GATE=1`). Both experiment builds carry explicit Maestro waivers (allowlist-gated to one real account, invisible to the QA harness identity).
- **What WAS verified:** `pytest backend/tests -q` → 2072 passed / 1 skipped, exit 0 (+8 new: experiment assignment/byte-identity ×2 builds, starter_impact tier/rank ×4 incl. tie-break determinism and the pure-weight-revise switch test); `tsc --noEmit` clean on the final combined branch; testid-lint OK; config-reference merge conflict union-resolved and re-gated.

## 2026-08-09 — Feedback wave 3 (#277/#278/#280/#281, #273-275, #269/#276) (sim gate DEVIATION, standing operator bypass)

- **Change:** tier labels app-wide (+3 routes gain additive `tier`), PickAssignment future-year/sheet fixes, sheet targeting (flag `trades.sheet_targeting` ON), scroll-to-trade, inline-home mockup lab. #282 held unmerged pending operator sign-off on prod-name fixtures.
- **Sim run: NOT PERFORMED.** Standing operator bypass (`FTF_SKIP_SIM_GATE=1`); smoke suite still doesn't exist.
- **What WAS verified:** `pytest backend/tests -q` → 2059 passed / 1 skipped, exit 0 (+6 tier-route tests); `tsc --noEmit` clean after every merge and post deferred-fix; flag mirror + testid-lint green; per-branch review before each merge.

## 2026-08-08 — Feedback wave #268/#267/#265/#263/#260/#257/#172 (sim gate DEVIATION, standing operator bypass)

- **Change:** 6 fixes/features + 2 mockup labs (see CHANGELOG same date). Two new flags ON (`trades.edit_full_sheet`, `trades.intent_modes`); one additive API field (`tier` on GET /api/trade/values); intent field in trade prefs.
- **Sim run: NOT PERFORMED.** Smoke suite still doesn't exist; standing operator bypass ("You can bypass the gate and push live to testflight", 2026-08-08) via `FTF_SKIP_SIM_GATE=1`.
- **What WAS verified:** `pytest backend/tests -q` → 2053 passed / 1 skipped, exit 0 (+12 new: #268 repro, 11 intent-mode tests); `tsc --noEmit` clean after each merge and on the final combined branch; flag mirror tests green; `testid-lint.sh` OK; node tests (league-unlocks 4/4); per-branch code review before every merge. #268's fix carries a test that reproduces the exact pre-fix client request (405) and proves the corrected URL (200).

## 2026-08-08 — Context-slim batch (sim gate SKIP, express-class: docs/config only)

- express: context-overload remediation (branch `context-slim-2026-08-08`) — gates skipped by operator direction. Diff touches `mobile/src/**/CLAUDE.md` (docs), living-memory, docs/, skills, hook config — zero app code. `FTF_SKIP_SIM_GATE=1` used for the push; CI (pytest + tsc + testid-lint) is the verification gate.

## 2026-08-08 — Feedback #266/#258 fixes (sim gate DEVIATION, standing operator bypass)

- **Change:** #266 ESPN-path link buttons dead on LeaguePicker (transition-settled auto-open) + #258 MFL team-name HTML entities (startup backfill of pre-#210 stored rows). Merge `b682ee2`.
- **Sim run: NOT PERFORMED.** Same blocker as the two entries below: the 11-flow smoke suite doesn't exist. Bypass is now STANDING operator authority ("You can bypass the gate and push live to testflight", 2026-08-08) until the flows land; exercised via `FTF_SKIP_SIM_GATE=1`.
- **What WAS verified:** `pytest backend/tests -q` → 2041 passed / 1 skipped, exit 0 (+4 new backfill tests, verified failing-first); `tsc --noEmit` clean under fresh `npm ci` (includes tonight's `@react-native-cookies/cookies` dep); fix-agent reproduced both root causes in code before changing anything.

## 2026-08-08 — ESPN Connect WebView ship (sim gate DEVIATION, recorded)

- **Change:** Phase 1b ESPN cookie capture (`EspnConnectScreen`, `EspnLinkSheet` auth-error self-serve, League-tab re-sync recovery), flag `espn.webview_capture` shipped ON. Commits `989343f`/`365e815`/`81a16a2` → pushed to `main` @ `d745146`.
- **Sim run: NOT PERFORMED.** Declared tier 2, waived by operator order at merge ("Merge now and push to testflight with the flag on" + explicit gate-bypass confirmation, 2026-08-08), exercised via `FTF_SKIP_SIM_GATE=1`. Same underlying blocker as the entry below: the new native dep (`@react-native-cookies/cookies`) needs a rebuilt dev client before any Maestro run, and the smoke flows don't exist yet.
- **What WAS verified:** `tsc --noEmit` clean (post-rebase); `node tests/check-espn-cookies.js` 14/14; `pytest -k "flag or feature or taxonomy"` 149 passed (post-rebase, flag ON + release-mirror green); manual testID cross-check (flow + registry + source agree); independent adversarial review — security clean, 8 findings fixed in `365e815`.
- **Compensating control:** EAS build 90 (v1.11.0) auto-submitted to TestFlight; QA checklist in `docs/plans/espn-connect-webview/scope.md` §3 (fresh capture / OTP hint / auth-recovery, real private league 493554) is the validation gate, with the flag flip-off as rollback.

## 2026-08-08 — ESPN auto-derived draft order (sim gate DEVIATION, recorded)

- **Change:** `suggested_order` prefill on PickAssignmentScreen (+ espn_service derivation). Tier 1 by the matrix (mobile screen change).
- **Sim run: NOT PERFORMED — the required artifact cannot exist yet.** The gate's tier-1 requirement is the 11-flow smoke suite; `mobile/maestro/` contains zero flows (the mobile-testing program has built seams/scripts/testIDs, not the flows). Maestro itself IS installed.
- **Deviation authority:** operator directive to ship ("Pick up and finish 3", 2026-08-08), exercised via the documented `FTF_SKIP_SIM_GATE=1` override. Receipts per the gate spec: this entry + the deviation note in `docs/plans/draft-extensions/build-espn-auto-order.md`.
- **What WAS verified:** `pytest backend/tests -q` → 2037 passed / 1 skipped, exit 0 (+42 new tests incl. the live-captured league-11896 fixture pinning the operator's inverse-regular-season decision); `tsc --noEmit` clean; all 4 mobile AST/behaviour check scripts pass. The mobile delta is a prefill of an existing editable list — no new writes.
- **Follow-up owed:** the 11 smoke flows are now the gate's own blocking dependency — until they exist, every tier-1/2 push needs this same override. Build them or re-tier the gate.

## Table of Contents
- [2026-08-28d — IAP enablement code half (runbook 6–7): webhook delta + RevenueCat paywall — full gates, ALL DARK](#2026-08-28d--iap-enablement-code-half-runbook-67-webhook-delta--revenuecat-paywall--full-gates-all-dark)
- [2026-08-28c — v1.16.9 (EAS build 135) BUILT + SUBMITTED to TestFlight; trade.shop_asset LIT in prod](#2026-08-28c--v1169-eas-build-135-built--submitted-to-testflight-tradeshop_asset-lit-in-prod)
- [2026-08-28b — #402/#403 QA round 2: B-3, own-position chip ruling, P-1..P-4 — universal-rule fixes, gates green](#2026-08-28b--402403-qa-round-2-b-3-own-position-chip-ruling-p-1p-4--universal-rule-fixes-gates-green)
- [2026-08-28 — #402/#403 "More offers = shop a player" — full build + redundant QA + fix round, all gates green (branch, HELD unmerged)](#2026-08-28--402403-more-offers--shop-a-player--full-build--redundant-qa--fix-round-all-gates-green-branch-held-unmerged)
- [2026-08-27 — #384 partner team-shape summary restored to the merged calculator layout — full gates](#2026-08-27--384-partner-team-shape-summary-restored-to-the-merged-calculator-layout--full-gates)
- [2026-08-26e — v1.16.8 (EAS build 134) BUILT for TestFlight](#2026-08-26e--v1168-eas-build-134-built-for-testflight)
- [2026-08-26c — Entry v2.1: login option (Opus subagent build, lead-session review) — full gates](#2026-08-26c--entry-v21-login-option-opus-subagent-build-lead-session-review--full-gates)
- [2026-08-26b — Platform entry decoupled from Apple (D-164) — full gates](#2026-08-26b--platform-entry-decoupled-from-apple-d-164--full-gates)
- [2026-08-26 — Landing platform options (Sleeper · ESPN · MFL entry chips) — full gates](#2026-08-26--landing-platform-options-sleeper--espn--mfl-entry-chips--full-gates)
- [2026-08-25 — v1.16.6 (EAS build 132) BUILT + SUBMITTED to TestFlight](#2026-08-25--v1166-eas-build-132-built--submitted-to-testflight)
- [2026-08-24c — Waves A + B0 SHIPPED — PRs #197/#199, EAS 1.16.4 (130) submitted](#2026-08-24c--waves-a--b0-shipped--prs-197199-eas-1164-130-submitted)
- [2026-08-24b — Wave B0 the layout merge (`calc.inline_home`) — full gates, FLAG DARK, NOT MERGED](#2026-08-24b--wave-b0-the-layout-merge-calcinline_home--full-gates-flag-dark-not-merged-on-featinline-home-b0)
- [2026-08-24 — Onboarding-tour Wave A — full gates green on `feat/tour-wave-a`; runtime evidence owed](#2026-08-24--onboarding-tour-wave-a--full-gates-green-on-feattour-wave-a;-runtime-evidence-owed)
- [2026-08-23b — `test_stud_tax_pinned_market` flake pinned: breaker wall-clock budget removed from test inputs](#2026-08-23b--test_stud_tax_pinned_market-flake-pinned-breaker-wall-clock-budget-removed-from-test-inputs)
- [2026-08-23a — main CI red → green: full-sweep fixture mirrors flipped](#2026-08-23a--main-ci-red--green-full-sweep-fixture-mirrors-flipped)
- [2026-08-22j — Full sweep — full gates; LIT at merge](#2026-08-22j--full-sweep-tradefull_sweep--full-gates-lit-2026-08-23-by-operator-instruction-at-merge)
- [2026-08-22i — #384 W8 — simulator reproduction, v1.16.2 (EAS 128)](#2026-08-22i--384-w8--simulator-reproduction--mobile-gates-v1162-eas-128)
- [2026-08-22h — #384 W7 device-feedback fixes — v1.16.1 (EAS 127)](#2026-08-22h--384-w7-device-feedback-fixes--mobile-gates-v1161-eas-127)
- [2026-08-22g — #384 SHIPPED — PR #172, flags LIT, EAS 1.16.0 (126)](#2026-08-22g--384-shipped--pr-172-80dee42-flags-lit-eas-build-1160-126-submitted)
- [2026-08-22f — #384 W6-A + W6-B — full gates, FLAG DARK, NOT MERGED](#2026-08-22f--384-w6-a--w6-b--full-gates-flag-dark-not-merged-on-claudemanual-calculator-e2e-review-39a467)
- [2026-08-22e — #384 merged calculator W5 + guard hardening — full gates, FLAG DARK, NOT MERGED, on `claude/manual-calculator-e2e-review-39a467`](#2026-08-22e--384-merged-calculator-w5--guard-hardening--full-gates-flag-dark-not-merged-on-claudemanual-calculator-e2e-review-39a467)
- [2026-08-22d — #384 merged calculator W0–W4 — full gates, FLAG DARK, NOT MERGED, on `feat/calc-finder-merge`](#2026-08-22d--384-merged-calculator-w0w4--full-gates-flag-dark-not-merged-on-featcalc-finder-merge)
- [2026-08-22c — Feedback capture cap (2000 → 8000) + the three silences — full gates, backend SHIPPED, client awaiting a build](#2026-08-22c--feedback-capture-cap-2000--8000--the-three-silences--full-gates-backend-shipped-client-awaiting-a-build)
- [2026-08-20b — Fit challenger PR-F3 (filters + arm wiring + serve-bit) + W0 offline dry run](#2026-08-20b--fit-challenger-pr-f3-filters--arm-wiring--serve-bit--w0-offline-dry-run-not-merged-worktree-claudetrade-suggestions-review-69c9eb)
- [2026-08-20a — Team Review defect batch (#364/#367/#368) — full gates](#2026-08-20a--team-review-defect-batch-364367368--full-gates-not-merged-on-claudeteam-outlook-experience-27a7a1)
- [2026-08-20d — #366 position-relative tier bands + RB Handcuff — full gates, NOT MERGED, on `worktree-agent-a4ab94c51456abb78`](#2026-08-20d--366-position-relative-tier-bands--rb-handcuff--full-gates-not-merged-on-worktree-agent-a4ab94c51456abb78)
- [2026-08-20e — Team Review `plan` beat rebuilt (#369) — full gates, NOT MERGED, on `worktree-agent-a7bed877f805980b0`](#2026-08-20e--team-review-plan-beat-rebuilt-369--full-gates-not-merged-on-worktree-agent-a7bed877f805980b0)
- [2026-08-20a — Team Review defect batch (#364/#367/#368) — full gates, NOT MERGED, on `claude/team-outlook-experience-27a7a1`](#2026-08-20a--team-review-defect-batch-364367368--full-gates-not-merged-on-claudeteam-outlook-experience-27a7a1)
- [2026-08-19h — `outlook.odds` LIT by operator override + its replacement guard (D-094, NOT MERGED, on `claude/team-review-analysis-plan-1f91e3`)](#2026-08-19h--outlookodds-lit-by-operator-override--its-replacement-guard-d-094-not-merged-on-claudeteam-review-analysis-plan-1f91e3)
- [2026-08-08](#2026-08-08)
- [2026-07-04](#2026-07-04)
- [2026-06-11](#2026-06-11)
- [Archive: pre-2026-06 entries](archive/TEST_LEDGER-pre-2026-06.md)
- [Manual Verification History](#manual-verification-history)
- [Custom-Skill Benchmarks](#custom-skill-benchmarks)
- [Tests Planned but Not Yet Run](#tests-planned-but-not-yet-run)
- [Verification Discipline](#verification-discipline)

---

## 2026-08-08

### ESPN Connect WebView build (worktree `espn-webview-capture` off `origin/main` @ `cb6aacb`)
- **`cd mobile && npx tsc --noEmit` → clean, exit 0** (run after both the feature commit and the review-fix commit).
- **`node mobile/tests/check-espn-cookies.js` → 14/14 checks pass** — pure extractor `pickEspnCookies` (pair/half-pair/trim/braces/multi-bag), `readEspnCookies` polls both ESPN domains, `clearEspnCookies` clears 2 names × 2 domains × 2 native stores (the fresh-login guarantee).
- **`python3 -m pytest backend/tests/ -q -k "flag or feature"` → 148 passed**; broader `-k "taxonomy or analytics or events or flag or feature or seed_ui"` → **320 passed** (new flag `espn.webview_capture` in registry + release-mirror; 4 `espn_connect_*` events in the taxonomy with prop entries).
- **testID cross-check (manual):** every id referenced by `mobile/.maestro/flows/espn-connect-capture.yaml` and the components CLAUDE.md registry resolves in `mobile/src/`. `mobile/scripts/testid-lint.sh` does not exist on this branch (`mobile/scripts/` is gitignored — see below); a tracked lint script is a separate task.
- **NOT run:** the Maestro flow itself (needs a rebuilt dev client carrying the new `@react-native-cookies/cookies` native pod) and the in-WebView login leg (waived per scope §3 — live third-party page; covered by the scope block's TestFlight QA checklist). `pod install` fails on this machine (CocoaPods 1.16.2/Ruby 4.0.3 `Unicode Normalization not appropriate for ASCII-8BIT` on the spaces-in-path repo); the EAS build regenerates the lockfile.

### Suite trajectory, 2026-07-09 → 2026-08-06
- **252 → 1466.** Reconstructed from commit messages during the living-memory revival pass; each figure is the count the committing session reported. Checkpoints: 272 → 285 → 382 → 521 (accounts P1/P2) → 558 → 632 → 781 (v1.9.0) → 855 (analytics P3/P4) → 937 (teardown W2) → 979 (owned picks) → 998 → 1025 → 1209 → 1336 (deck engine) → 1359 → 1378 → 1405 → 1445 → 1455.
- **Counts are not strictly monotonic in log order.** Parallel worktree agents committed against different baselines — the 1414/1415 pair on 2026-08-03 is the clearest example. Treat a lower count in a later commit as a branch artifact, not a regression.

### Measured live on 2026-08-08 (this checkout, `teardown-remediation` @ `30492ac`)
- **`python3 -m pytest backend/tests/ -q` → 1466 passed, 1 skipped, 41.7s.**
- **`cd mobile && npx tsc --noEmit` → clean, exit 0.**
- ⚠️ **This is the 62-commits-behind base, not the project's test posture.** The rookie-draft QA handoff cites **1685 passed / 1 skipped on `origin/main` @ `cee4324`**. Quote the origin/main number when describing the project; quote this one only when describing this checkout.
- The 1466 includes two untracked test files not yet committed: `test_espn_pick_assignment.py` (6 tests), `test_finder_config_consolidated.py` (5 tests).

### Practices worth keeping (observed in this window)
- **Failing-first is used and stated in commit messages** — `#238` lineup before/after and the `market.movers` work both note tests written failing-first; several 07-25 fixes note the regression shape was "verified failing pre-fix via stash".
- **Flag-gated waves re-run the suite twice** — once as built, then again with flags ON as a separate gate. The deck-engine waves all did this.
- **A contrast guard runs in CI-shape** — `mobile/scripts/check-contrast.js` over 13 token pairs, `npm run test:contrast`.
- **`mobile/scripts/` is gitignored**, so JS regression checks live in `mobile/tests/` instead.

## 2026-07-04

### TC-API-001 — Manual Trade Calculator endpoints (/api/trade/evaluate, /api/trade/values)
- **Test:** 8 pytest cases over an injected universal pool ([backend/tests/test_trade_evaluate.py](../backend/tests/test_trade_evaluate.py)): symmetric→even, lopsided→unfair+favors, per-player values match `elo_to_value` exactly, unknown-id graceful drop, one-sided packages (no verdict), empty→400, bogus format→default, values-endpoint shape + ETag 304.
- **Result:** **PASS 8/8**; full suite **252 green**. Real-pool smoke (local Flask, live DP data): 671 valued players; top-vs-mid → `unfair/favors: give/ratio 0.008`; mirror trade → `even/1.0`.
- **Also verified:** mobile live mode end-to-end in Expo web with a contract-shaped fetch stub (backend has no CORS, so browser-origin calls can't hit it — native is unaffected); demo mode unchanged (Bijan parity scenario byte-identical since 07-02: 2,536/2,874, +9%/+12%).
- **Not yet run:** live mode against prod from a real device (needs deploy).

### TC-API-002 — Send in Sleeper error-contract hardening (/api/sleeper/link, /api/trades/propose)
- **Test:** +6 route tests ([backend/tests/test_sleeper_write_route.py](../backend/tests/test_sleeper_write_route.py)) locking each branch the mobile `SendInSleeperButton` depends on: no-key→503 `sleeper_unconfigured`; `bad_request` (non-numeric league / no counterparty); pre-flight **expired stored token**→409 `sleeper_expired` + credential dropped (the #1 real reconnect trigger, distinct from the mid-call auth-error branch); non-auth write failure→502 `sleeper_write_failed`; rosters-fetch exception degrades to 400 `roster_not_found` (never an unhandled 500); GET surfaces `expired:true`.
- **Result:** **PASS 14/14** in the file (8 prior + 6 new); full backend suite **258 green**; mobile tsc clean. These run the real Flask handlers against a real in-memory DB + real Fernet key, mocking only the Sleeper network — so they double as the local route smoke.
- **Reviewed, no code change needed:** runtime paths already fail safe (`_fetch_league_rosters` catches all → None → structured 400; adapter maps auth vs generic failures correctly). Hardening was coverage, not bug-fixing.
- **Still deferred by design:** slice-4 calculator Send surface (needs a real counterparty); flag `trade.send_in_sleeper` stays OFF; on-device link→propose against real Sleeper (needs a full EAS build — `react-native-webview` is native — + throwaway account).

## 2026-06-11

### TC-ENG-004 — 3-team cycle clearing (find_three_team_cycles)
- **Test:** 4 pytest goldens for the dark/uncovered kidney-exchange 3-team cycle clearer — Pareto A→B→C→A detection, no-benefit→empty, <3 members→empty, lineup-feasibility blocks a roster-breaking handoff.
- **Result:** **PASS 4/4** ([backend/tests/test_three_team_cycles.py](../backend/tests/test_three_team_cycles.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Findings:** **F-1 (P3 dead code)** `find_three_team_cycles` is implemented + exported but **never called** (no caller; trade.three_team flag only in a comment). Correct + now tested — a product decision away from wiring on.
- **Artifacts:** [`qa/results/TC-ENG-004.md`](../qa/results/TC-ENG-004.md).

### TC-DB-002 — DB concurrency, write integrity, recency
- **Test:** concurrent member_rankings upserts (atomic replace), concurrent distinct trade decisions (no loss), concurrent ranking swipes (WAL under contention), check_for_match 90-day recency bound. Threaded against scratch DB.
- **Result:** **PASS 5/5.** 8 concurrent upserts → exactly 20 rows (atomic), 16 decisions all persisted, 24 swipe rows no lock errors, stale (>90d) like excluded.
- **Findings:** none at thread scale. Postgres multi-process pool saturation remains a pre-scale Render load-test follow-up (not reproducible with threads on SQLite).
- **Artifacts:** [`qa/db/tc_db_002.py`](../qa/db/tc_db_002.py), [`qa/db/_concurrency_probe.py`](../qa/db/_concurrency_probe.py), [`qa/results/TC-DB-002.md`](../qa/results/TC-DB-002.md).

### TC-INT-001 — Sleeper-boundary input handling (G-003..G-008)
- **Test:** session_init defensive handling of null roster slots, int IDs, garbage IDs, empty roster, dup IDs; passthrough error handling (bad username, parse-url).
- **Result:** **PASS 8/8.** Nulls filtered, int IDs coerced, garbage filtered, empty roster degrades gracefully, bad username → 404 (not 500).
- **Findings:** F-1 (P3) duplicate roster IDs not deduped (3→6); harmless today, one-line `dict.fromkeys` fix.
- **Artifacts:** [`qa/sec/tc_int_001.py`](../qa/sec/tc_int_001.py), [`qa/results/TC-INT-001.md`](../qa/results/TC-INT-001.md).

### TC-CFG-001 — feature flags + model_config live-tuning contract
- **Test:** flag map + FTF_FLAGS env precedence; admin config auth (401)/unknown(404)/badval(400); live write→reload→readback; reload endpoint auth.
- **Result:** **PASS 11/11.** FTF_FLAGS override wins; config write persists + reloads (v3 reads same live _cfg).
- **Findings:** **F-1 (P3 operational)** surplus floors gate *divergence* cards only — *consensus-basis* decks (cold/low-coverage leagues) are fairness-gated, so cranking surplus floors has NO effect there (use fairness_threshold/consensus_score_scale). F-2 (P3) marginal flag makes min_side_surplus_marginal the live floor. Documented in config-reference.md.
- **Artifacts:** [`qa/api/tc_cfg_001.py`](../qa/api/tc_cfg_001.py), [`qa/results/TC-CFG-001.md`](../qa/results/TC-CFG-001.md).

### TC-PERF-001 — performance: cold-start, warm latency, concurrent load
- **Test:** measured backend vs charter budgets — cold boot, cold/warm session_init, warm GET p50/p95, generate end-to-end, per-opponent enumeration bound, 8-way concurrent init+generate, error-free-under-load.
- **Result:** **PASS 9/9.** Cold boot 1.0s; warm GET p50/p95 = 20/58ms; generate 31 cards in 1.28s; 8 concurrent users 0 errors. All within budget at local scale.
- **Caveats (honest):** concurrency test shares the trade-job cache (same fixture user) → proves session/cache thread-safety, not N independent generations. Real prod risks (cold Sleeper fetch in session_init, v3 enumeration on large league) NOT exercised locally — flagged for a Render-side load test.
- **Artifacts:** [`qa/perf/tc_perf_001.py`](../qa/perf/tc_perf_001.py), [`qa/results/TC-PERF-001.md`](../qa/results/TC-PERF-001.md).

### TC-ENG-003 — engine gate config-responsiveness (admin tuning surface)
- **Test:** 4 pytest goldens proving the tuning knobs are monotone/predictable — min_side_surplus (↑→fewer cards), trade_elo_gap_max knife-edge, waiver_slot_cost erodes extra-player side, tier_mult_elite scales composite.
- **Result:** **PASS 4/4** ([backend/tests/test_engine_gates_config.py](../backend/tests/test_engine_gates_config.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Observation:** the legacy parity fixture yields 4 cards legacy / 0 v2 — v2 correctly rejects one-sided trades legacy surfaced (reinforces "kill-switch is a real downgrade").
- **Artifacts:** [`qa/results/TC-ENG-003.md`](../qa/results/TC-ENG-003.md).

### TC-API-002 — public-route auth-intent audit
- **Test:** classify all public routes read vs mutating; allowlist-check public mutations; empty/garbage-body robustness; CORS posture.
- **Result:** **PASS 4/4.** 13 public /api routes (8 read, 5 mutating); all 5 mutations intentional (session/init, demo, feedback, extension/auth, parse-url). No 5xx on garbage; CORS same-origin-only. **No unauthenticated state-mutating routes** — recon "44 none-auth" concern resolved.
- **Findings:** F-1 (P3) no rate limiting on pre-auth mutations (session/init, extension/auth); F-2 (P3 process) new `_require_initialized_session` gate (25 routes) added since TC-API-001 → those counts stale.
- **Artifacts:** [`qa/api/tc_api_002.py`](../qa/api/tc_api_002.py), [`qa/results/TC-API-002.md`](../qa/results/TC-API-002.md).

### TC-E2E-004 — cross-league flow + cross-league disposition
- **Test:** matches/all across leagues; awaiting; portfolio over 2 leagues; create match in league A, switch session to league B, disposition the A match (cross-league branch).
- **Result:** **PASS 9/9.** Cross-league accept (session on B, match in A) → 200, decision persisted on the match's own league, Elo signal queued for replay. Correctly league-scoped.
- **Findings:** none. Observation: match fires on whichever swipe completes the mirror (locate by DB state, not response id).
- **Artifacts:** [`qa/e2e/tc_e2e_004.py`](../qa/e2e/tc_e2e_004.py), [`qa/results/TC-E2E-004.md`](../qa/results/TC-E2E-004.md).

### TC-RNK-001 — Elo math golden fixtures (engine input quality)
- **Test:** 6 pytest goldens for the Elo update — exact pairwise math (K=32 → ±16), K-factor by decision type (rank 32 / like 8 / pass 4, linear), zero-sum conservation, 3-player decomposition + order preservation, override pinning, replay determinism.
- **Result:** **PASS 6/6** ([backend/tests/test_rnk_elo_golden.py](../backend/tests/test_rnk_elo_golden.py)) — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job since the file lives under `backend/tests/`.
- **Observation:** displayed Elo is rounded to 1 decimal in `get_rankings`, and that rounded value is what's published to member_rankings + fed to `elo_to_value` — whole valuation pipeline runs at 0.1-Elo precision. Zero-sum only holds without tier overrides.
- **Artifacts:** [`qa/results/TC-RNK-001.md`](../qa/results/TC-RNK-001.md).

### TC-E2E-003 — superflex (sf_tep) format path + isolation
- **Test:** sf_tep trio→rank3→generate via X-Scoring-Format header; format-partitioned persistence; 1qb_ppr isolation; per-format independent Elo; sf_tep card validity.
- **Result:** **PASS 8/8.** +9 sf_tep rank rows, 1qb_ppr unchanged (222→222, isolated), sf_tep member_rankings 0→685, sf_tep generate → 31 valid cards. **Same player 1qb=1605 vs sf=1800 Elo** (QB premium in superflex working as intended).
- **Artifacts:** [`qa/e2e/tc_e2e_003.py`](../qa/e2e/tc_e2e_003.py), [`qa/results/TC-E2E-003.md`](../qa/results/TC-E2E-003.md).

### TC-API-001 — API consistency + doc-drift audit
- **Test:** static analysis of all 92 server.py routes (naming, error-shape taxonomy, auth-gate distribution) + doc-drift vs api-reference.md + live envelope/error-contract sampling.
- **Result:** **COMPLETE 7/8** (the 1 FAIL is the surfaced naming finding). Error contracts solid (every error body has an `error` key; 401/404/400 correct). Auth gates: session 35 / none 44 / cron 13 / bearer 1.
- **Findings:** F-1 (P2) 39 `jsonify({"error": str(e)})` raw-exception leaks; F-2 (P3) error-value vocabulary split (42 code-style vs 44 sentence-style vs 23 code+message); F-3 (P3) 2 undocumented routes (`/api/feedback/admin`, `/api/tiers/copy-from-format`); F-4 (P3) lone snake_case segment `/api/sleeper/league_users`; F-5 (P3) no envelope standard / no version prefix.
- **Docs updated this cycle:** added `/api/trades/awaiting` + stochastic-deck-order note to api-reference.md; v3-feasibility "no trades" failure mode to runbook.md.
- **Artifacts:** [`qa/api/tc_api_001.py`](../qa/api/tc_api_001.py), [`qa/results/TC-API-001.md`](../qa/results/TC-API-001.md).

### TC-E2E-002 — restart resilience (in-memory session + job loss)
- **Test:** generate a deck, restart the server process against the same DB, verify graceful degradation: stale token→401, stale job→404 (no hang), data survives, FB-46 swipe of a pre-restart card reconstructs + persists, new session fully functional.
- **Result:** **PASS 9/9.** Old job 404 in 0.00s; 646 member_rankings survived; FB-46 swipe persisted +1 decision; post-restart generate → 31 cards.
- **Findings:** none. In-memory job/session loss is a graceful degradation, not a failure mode; recon operability concern closed.
- **Artifacts:** [`qa/e2e/tc_e2e_002.py`](../qa/e2e/tc_e2e_002.py), [`qa/results/TC-E2E-002.md`](../qa/results/TC-E2E-002.md).

### TC-DB-001 — schema integrity, migration idempotency, SQLite↔Postgres parity
- **Test:** fresh-init schema parity on SQLite AND a real local Postgres (table set + per-table columns), `_migrate_db()` idempotency on both, dialect-branched upsert smoke (leagues/league_members/member_rankings/skips + the F-1 second-member upsert), and a read-only live-DB quality audit (orphans, enum domains, ISO timestamps, boolean storage, dup guards).
- **Result:** **PASS 24/24** incl. Postgres plane. Exact 24-table/all-column parity; migrations idempotent both dialects; **F-1 fix verified cross-dialect** (works on Postgres too, leagues stays 1 row).
- **Findings:** the 41 orphaned `league_members` (recon "HIGH, fix before scale") are **benign** — 0 have rankings, 0 in trade_matches; never-logged-in leaguemates. Recon item downgraded P3. data-dictionary.md confirmed in sync (24 tables; recon "22/23" was a miscount).
- **Env note:** `psycopg2-binary` (declared dep) was missing locally; installed to run the PG plane. Throwaway PG db `ftf_qa_parity` created + dropped.
- **Artifacts:** [`qa/db/tc_db_001.py`](../qa/db/tc_db_001.py), [`qa/db/_dialect_probe.py`](../qa/db/_dialect_probe.py), [`qa/results/TC-DB-001.md`](../qa/results/TC-DB-001.md), `qa/db/scratch/TC-DB-001-run.json`.

### F-1 (TC-E2E-001) RESOLVED — verified
- Commit `ddf67df` fixed the second-member `upsert_league` UNIQUE-constraint crash (dialect-aware `on_conflict_do_update` on the `sleeper_league_id` PK) + added `backend/tests/test_league_upsert.py` (3 tests). Re-verified: IntegrityError gone, TC-E2E-001 back to 67/67, regression test passes. E2E harness allowlist updated (no longer masks the error; now allowlists only the synthetic-league Sleeper 404).

### TC-SEC-001 — operator-endpoint auth enforcement
- **Test:** sweep all 8 operator routes (`/api/admin/*`, `/api/feedback/admin*`, `/api/debug/log`, `/api/feature-flags/reload`, `/api/cron/*`) across CRON_SECRET set/unset; in-proc test of `_require_cron_auth` prod branch (fail-closed) without a real Postgres; session-gate control on mutating routes.
- **Result:** **PASS 35/35.** Cron-gate enforces (401 missing/wrong/near-miss, success on match); prod fails closed (503 when secret unset); session routes 401 tokenless/bogus.
- **Refutes recon:** the discovery report's "5 unprotected admin endpoints (P0)" is **FALSE** — every route calls `_require_cron_auth()`. Lesson: recon findings are hypotheses until a TC verifies them.
- **Findings:** **F-1 (P2)** `run.py` binds `0.0.0.0` + `debug=True` with no local CRON_SECRET → operator routes exposed on LAN for local/self-host runs (prod on Render unaffected: fail-closed).
- **Artifacts:** [`qa/sec/tc_sec_001.py`](../qa/sec/tc_sec_001.py), [`qa/results/TC-SEC-001.md`](../qa/results/TC-SEC-001.md), `qa/sec/scratch/TC-SEC-001-run.json`.

### TC-ENG-002 — fairness-gate golden fixtures (1-for-1 gate + package-discount watch item)
- **Test:** 8 pytest golden fixtures in `backend/tests/` covering `package_value_v2` discount math (exact + monotone in `package_adj_gamma`), 1-for-1 gate config-driven knife-edge, discount→`fairness_score` propagation, FR8 outlook market-neutrality, and v2↔v3 fairness-floor parity + monotonicity. Self-calibrating where exact propagation is hard to hand-predict.
- **Result:** **PASS 8/8**, stable ×3; full backend suite now **178 passed** with the new file (no pollution). Graduated into the pytest suite — written before CI existed (added 2026-08-08); now covered by CI's `backend-tests` job.
- **Findings:** **F-1 (P3)** `_fairness_v3` is a hand-copied mirror of v2 `_fairness` (standing TODO) — drift risk; this test now guards parity, but a shared `score_trade` extraction is the real fix (already planned in competitor-top20/03).
- **Key observation:** v3 lineup-feasibility is all-or-nothing — a roster that can't field a full QB1/RB2/WR2/TE1 lineup gets ZERO v3 cards (v2 still serves). Sharp edge worth a runbook note for "no trades" diagnosis.
- **Artifacts:** [`backend/tests/test_fairness_gate_golden.py`](../backend/tests/test_fairness_gate_golden.py), [`qa/results/TC-ENG-002.md`](../qa/results/TC-ENG-002.md).

### TC-ENG-001 — trade-engine kill-switch regression (legacy/v2/v3)
- **Test:** three FTF_FLAGS-pinned server instances (legacy / v2 / v3), ordering flags off; per-engine card-validity battery, flag-routing proof, legacy≠v2 divergence, v2→v3 top-card stability. Same user+league.
- **Result:** **PASS 30/30**, stable across 3 runs. Deck sizes legacy 13 / v2 33 / v3 33; all roster-ownership + fairness checks clean on all engines. v2's #1 trade always survives into v3; v2 top-10 → v3 overlap a deterministic 5/10.
- **Findings:** none. Observations: legacy fallback is a real UX downgrade (random opp Elo, smaller deck) not a transparent swap; v2→v3 top-10 continuity is exactly 50% (watch item if product wants tighter migration continuity).
- **Artifacts:** [`qa/eng/tc_eng_001.py`](../qa/eng/tc_eng_001.py), [`qa/results/TC-ENG-001.md`](../qa/results/TC-ENG-001.md), `qa/eng/scratch/TC-ENG-001-run.json`.

### TC-E2E-001 — full-stack happy path (automated harness)
- **Test:** session_init → trio/rank3 ×3 → trade generate (async job) → swipe → mirrored-like match (likes_you instant + two-session two-step) → disposition lifecycle (accept/accept → accepted, 409 repeat, 404 unknown, 400 bad input) → DB integrity sweep. Driven via HTTP against a local Flask on a scratch copy of `data/trade_finder.db`; mobile client timeout budgets as pass bar. Flags: v3 engine + all Tier 2 trade flags on.
- **Result:** **PASS 67/67 checks**, reproducible across runs. 31 cards in 0.8–1.5 s; cache-hit re-generate ≤4 ms; all calls within mobile budget.
- **Findings:** **F-1 (P1)** `upsert_league` keys on `(league_id, user_id)` but PK is league_id alone → IntegrityError swallowed on every second-member session_init, their league row never persisted. **F-2 (P2)** 7-day card-dedup vs unbounded match-dedup mismatch → already-accepted trade re-served then silently no-ops on like.
- **Artifacts:** harness [`qa/e2e/tc_e2e_001.py`](../qa/e2e/tc_e2e_001.py), report [`qa/results/TC-E2E-001.md`](../qa/results/TC-E2E-001.md), machine-readable run `qa/e2e/scratch/TC-E2E-001-run.json`.
- **Planned variants:** TC-E2E-002 restart-resilience, TC-E2E-003 sf_tep format, TC-E2E-004 Postgres parity.

## Manual Verification History

*Historical — predates the pytest suite. As of 2026-08-08 the project has a pytest suite of ~2000 tests (`backend/tests/`, run in CI's `backend-tests` job per `.github/workflows/ci.yml`); the ad-hoc methods below were the verification approach before that suite existed and are largely superseded. The 2026-05-21 entry that used to open this file (living-memory layer adoption, status pending) is archived in [`archive/TEST_LEDGER-pre-2026-06.md`](archive/TEST_LEDGER-pre-2026-06.md).*

| Verification artifact | What it tests |
|---|---|
| [`Test_League_Trade_Matches.xlsx`](../Test_League_Trade_Matches.xlsx) | Expected trade matches for a test league configuration |
| [`Trade_Matches.xlsx`](../Trade_Matches.xlsx) | Reference trade-match output for validation |
| `dump_mismatches.py` | DynastyProcess ↔ Sleeper player-name mismatches |
| `tmp_check_db.py`, `tmp_check_db2.py` | Ad-hoc DB integrity scripts |
| `GET /api/debug/log?n=100` | In-memory ring-buffer log (last 200 entries) for forensic checks |
| Manual smoke: `python3 run.py` → web client login → roster import → swipe → trade card | End-to-end happy-path verification |

**Caveat (historical):** at the time this table was written there was no automated regression suite, so a change that broke one of these flows was detectable only by manual re-run. That gap is closed — see the pytest suite note above. [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) Q-002 (pytest adoption) is resolved.

## Custom-Skill Benchmarks

| Skill | Benchmark | Result |
|---|---|---|
| **`project-reorganizer.skill`** | 6-phase methodology (scan, propose, cross-reference, execute, update imports, verify) vs ad-hoc reorganization | ~83% pass rate WITH skill vs ~43% WITHOUT (+40pp improvement). See [`project-reorganizer-eval-review.html`](../project-reorganizer-eval-review.html) |
| **`feature-evaluator.skill`** | Evaluates code across 7 dimensions (structure, readability, performance, error handling, security, testability, maintainability); produces severity-rated reports | Used in-repo for ongoing code review; no formal pass/fail benchmark yet |

---

## Tests Planned but Not Yet Run

See [`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md) and [`NEXT.md`](NEXT.md). High-priority:

- **Pytest suite for backend services** — `ranking_service.py`, `trade_service.py`, and `data_loader.py` would benefit most. Currently zero coverage.
- **Integration test for full Sleeper flow** — mock Sleeper API responses; verify session/league/roster import.
- **Elo regression test** — golden-file comparison: given a fixed sequence of swipe inputs, verify Elo outputs match a recorded baseline.
- **Trade-card generation regression** — given a fixed league snapshot, verify trade cards generated.
- **Tiered matchup engine A/B** — compare global-Elo vs tier-prioritized matchup selection on information gain per swipe.
- **Postgres migration smoke test** — `DATABASE_URL` pointing at local Postgres; run through full flow.
- **Mobile client Elo parity** — verify mobile and web compute the same Elo values for the same swipe sequence.

---

## Verification Discipline

Rules of evidence for this ledger:
- **No claim without a verification artifact.** Either a docs file, a script output, a manual screenshot, or a recorded test run.
- **State the input set.** "Tested on test-league X with N players" beats "tested it."
- **Distinguish smoke from regression.** Smoke = "it ran"; regression = "the output matches a saved baseline."
- **When manual: name the path.** Click sequence in mobile? Curl call in web? Specifics make it reproducible.
- **When fixing a bug: capture the failing input.** Add to verification artifacts.

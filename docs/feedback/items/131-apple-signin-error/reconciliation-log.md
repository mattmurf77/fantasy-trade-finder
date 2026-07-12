# #131 — Reconciliation log (Planner ↔ Author)

Phase 1, group G1, fast-track-bug path. Planner input: `plan.md`. Author
output: `prd.md`. This log seeds the Planner's three open questions with the
Author's dispositions, plus verification deltas found while grounding the
PRD in source.

## Open questions from the plan

### OQ1 — Friendlier failure copy: in or out?

**Disposition: OUT.** Agree with the Planner's default and rationale:

- The root-cause fix (entitlement) makes the entitlement error unreachable;
  mapping ASAuthorization "unknown" codes to friendlier copy is speculative
  hardening against a config error being removed (coding-guidelines
  "Simplicity First" / "no error handling for impossible scenarios").
- Both catch blocks already behave correctly (verified):
  `SignInScreen.tsx:141–144` and `SettingsScreen.tsx:136–139` suppress
  `ERR_REQUEST_CANCELED` and show a controlled message on our own surfaces.
- The Sentry-breadcrumb sub-suggestion is likewise out — it only has value
  if we adopt the copy mapping, which we are not.

Consequence in the PRD: R-2 pins zero app-logic changes;
`SignInScreen.tsx` is untouched (the plan's file-ownership table row for it
goes unused).

### OQ2 — Exact pre-fix error copy (operator screenshot needed?)

**Disposition: RESOLVED without operator input.** The exact strings are
pinned from the installed native source, not from a device screenshot —
`mobile/node_modules/expo-apple-authentication/ios/AppleAuthenticationExceptions.swift`
(package version 8.0.8, matching what builds 40/41 shipped):

- `.unknown` (code 1000) → `RequestUnknownException` → JS `err.code =
  ERR_REQUEST_UNKNOWN`, `err.message = "The authorization attempt failed
  for an unknown reason"` — the Planner's "or similar" hedge is now exact.
- `.failed` (1004) → `"The authorization attempt failed"`
  (`ERR_REQUEST_FAILED`).
- `.canceled` (1001) → `"The user canceled the authorization attempt"`
  (`ERR_REQUEST_CANCELED`) — suppressed by both catches, never surfaces.

No cause text is appended to the message:
`AppleAuthenticationRequest.swift:71` rejects with
`exceptionForAuthorizationError(error)` and chains no cause, and
expo-modules-core `Exception.description` (Core/Exceptions/Exception.swift:51)
is the bare `reason` string when `cause` is nil.

The Maestro assertion therefore uses the stable substring shared by both
non-cancel failure modes: regex `.*The authorization attempt failed.*`
(PRD R-4/R-5). An operator screenshot from build 40/41 is no longer needed
for QA; it remains a nice-to-have for the feedback reply narrative only —
do not block on it.

### OQ3 — Version/build sequencing (1.7.3 / build 42)

**Disposition: NON-BLOCKING — batch orchestrator owns it.** The PRD treats
1.7.3 / build 42 as defaults, not assumptions (R-6). If another G1 item
bundles into the same EAS build, the orchestrator coordinates a single bump.
Build number is EAS-remote-owned (`mobile/eas.json`:
`appVersionSource: "remote"` + production `autoIncrement: true`) — nobody
hand-edits it. Build agent must not gate on this question.

## Author verification deltas vs. the plan

1. **Settings testID already exists.** Plan hedged "needs a testID if it
   lacks one" — it doesn't lack: `settings.link-apple-btn` is at
   `SettingsScreen.tsx:536`. No new testID on either Apple button
   (`signin.apple-btn` is at `SignInScreen.tsx:277`).
2. **A different additive testID IS needed:** the Settings gear in
   `mobile/src/components/TopBar.tsx` (~L70) has only
   `accessibilityLabel="Settings"`, and LLD §4.4 bans tapping by text — PRD
   R-3 adds `topbar.settings`. No existing Maestro flow opens Settings
   today, so this is the only reachability gap for the Settings leg.
3. **Registry gap:** neither Apple testID is listed in
   `mobile/src/components/CLAUDE.md` (SignIn row, line 36) — R-3 registers
   all three ids per the LLD "PRs adding screens add IDs" rule.
4. **Third version carrier:** plan's ownership table listed `app.json` +
   `Info.plist` for the 1.7.3 bump; `project.pbxproj` also carries
   `MARKETING_VERSION = 1.7.2` (lines 378/409). R-6 bumps all four
   occurrences to prevent drift.
5. **`isAvailableAsync` claim confirmed from source:** it returns
   unconditionally `true` on iOS (`AppleAuthenticationModule.swift:12–14`),
   which both explains the pre-fix button-renders-then-errors behavior and
   guarantees the button renders in the simulator smoke cell
   (`auth.accounts` = true in `backend/tests/fixtures/flags/release.json:42`).
6. **Root-cause and backend-clearance claims re-verified:** entitlements
   dict contains only `aps-environment` (entitlements file lines 4–7);
   `CODE_SIGN_ENTITLEMENTS` at pbxproj lines 365/401;
   `PRODUCT_BUNDLE_IDENTIFIER = com.fantasytradefinder.app` (385/416)
   matches `backend/accounts.py:47` `APPLE_AUDIENCE`. All as the plan
   stated.
7. **Simulator caveat added (PRD R-5 note):** a sim runtime with no Apple
   ID signed in may reject code 1000 even post-fix (runtime-dependent), so
   the Maestro flow is a regression guard, not the entitlement ground truth
   — that's the R-8 codesign checkpoint. Flake handling: quarantine per LLD
   §4.2 if R-8 passes while the flow reds.

## Status

All three planner OQs dispositioned; no operator input required before the
build phase. Build agent inputs: `prd.md` R-1…R-9. No unresolved questions.

## Planner review — round 2

Reviewed `prd.md` + this log against source (2026-07-12). The Author's
verification deltas all check out; two BLOCKING objections against the R-5
Maestro flow's negative-assertion design, three NON-BLOCKING notes.

### Author corrections — verified, accepted

1. **`settings.link-apple-btn` exists** — confirmed at
   `mobile/src/screens/SettingsScreen.tsx:536`. Plan's hedge withdrawn.
2. **`topbar.settings` is the real reachability gap** — confirmed: the
   TopBar settings Pressable (`mobile/src/components/TopBar.tsx` ~L74–84)
   has only `accessibilityLabel="Settings"`, no testID; no existing Maestro
   flow opens Settings; `topbar` is in the LLD Appendix-A screen vocabulary
   and `topbar.bell`/`topbar.bell-badge` are already reserved as shared
   chrome. The id is grammar-conformant. (testID goes on the Pressable
   itself — the tap target — so the registry's container-swallows-child-IDs
   caveat doesn't apply.)
3. **Third version carrier** — confirmed: `MARKETING_VERSION = 1.7.2` at
   `project.pbxproj` lines 378 (Debug) and 409 (Release), in addition to
   `app.json` and the literal `CFBundleShortVersionString` in Info.plist.
   R-6's four-occurrence bump is correct.

Additionally re-verified from source: `signin.error-text` exists
(`SignInScreen.tsx:329`, already in the registry); the R-4 strings are
byte-exact against the installed
`node_modules/expo-apple-authentication/ios/AppleAuthenticationExceptions.swift`
(8.0.8, lockfile-pinned) and are hardcoded Swift literals (not
`NSLocalizedString`) — locale-safe; `isAvailableAsync` returns
unconditionally `true` (`AppleAuthenticationModule.swift:12–14`);
`auth.accounts` is true in the release flags fixture; `GET /api/account`
(`backend/server.py:9785`) returns `ok` with `account: null` for a
Sleeper-keyed session, so the SettingsScreen link-card gate
(`accountQuery.data && !hasAppleIdentity && appleAvailable`, line 549)
holds for `qa_standard`; flow header/format matches
`smoke/02-league-pick.yaml` conventions and smoke slot 11 is free.

### BLOCKING objections

**B-1 — R-5 Part 2 can NEVER catch the regression: the Settings failure
surface auto-dismisses before the negative assert can bite.** The failure
copy lands in a `Toast` (`SettingsScreen.tsx:692–697`) that passes no
`holdMs`, so the default applies: `holdMs = 1500`
(`mobile/src/components/Toast.tsx:30`) — the toast fades out ~1.7 s after
appearing. Maestro's `assertNotVisible` retries until the element is *not*
visible and only fails if it is still visible at timeout; likewise
`extendedWaitUntil: notVisible` succeeds the moment the condition holds.
On a regressed build, both commands simply wait out the toast's 1.7 s
lifetime inside their 10 s windows and pass green. The Part 2 assertion is
structurally blind, not merely flaky. Remedy options, in preference order:
  (a) **Recommended:** downgrade Part 2 to reachability-only — assert the
      card/button renders (`settings.link-apple-btn` visible), tap,
      screenshot; drop the failure-copy negative assert. Honest scope: the
      entitlement is binary-wide, so Part 1's persistent inline error is
      the regression sensor for both surfaces. Stays inside the R-2 diff
      whitelist; zero app edits.
  (b) Positive-assert the in-flight state post-fix (Settings `appleBusy`
      indicator stays mounted while the native sheet holds the promise
      open) — requires a new testID in `SettingsScreen.tsx`, i.e. an R-2
      whitelist amendment; only take this if (a) is deemed too weak.
  (c) Persist warn toasts (`holdMs=0`) — app-logic change; conflicts with
      R-2 and the OQ1 disposition. Rejected.
The Author must pick and rewrite R-5 Part 2 accordingly.

**B-2 — R-5 Part 1's negative asserts have zero guaranteed settle after the
tap (racy in the passing direction).** Sequence as written: `tapOn` →
`extendedWaitUntil: notVisible` → `assertNotVisible`. Pre-fix, the
rejection → `setError` → re-render takes ~200–400 ms; at t≈0 the error text
is not yet visible, so `extendedWaitUntil: notVisible` returns immediately
and `assertNotVisible` can also evaluate inside that window. Whether the
flow catches the regression then depends on incidental command-dispatch
latency — the pass criterion "flow exits green" doesn't prove regression
sensitivity. Since the SignIn surface IS persistent
(`signin.error-text` renders until the next attempt), any deterministic
post-tap settle makes the catch reliable. Required PRD change: R-5 must
mandate a bounded settle (≥2 s) between the tap and the negative asserts —
exact mechanism left to the QA agent (e.g. a fixed-window probe such as an
`optional: true` `extendedWaitUntil: visible` on the error regex, which
waits the full window when the error never appears, or the harness's
accepted delay idiom), and the flow comment must state why the settle
exists so it isn't "optimized away".

### NON-BLOCKING notes

**N-1 — Pinned-string stability across package versions** (coordinator's
question): the R-4 strings are pinned from 8.0.8; `package.json` floats
`~8.0.8`, so a patch bump on a future `npm install` could reword them (they
are expo-authored literals, not Apple/OS strings). Locale is not a risk
(hardcoded English, no localization). Mitigation: the R-5 flow header
comment should carry the pin — "failure copy pinned from
expo-apple-authentication@8.0.8; re-verify AppleAuthenticationExceptions.swift
on upgrade" — and the R-7 runbook entry can mention it in one line.

**N-2 — Regex scope:** `.*The authorization attempt failed.*` matches only
the `.unknown` (1000) and `.failed` (1004) reasons. `.invalidResponse`,
`.notHandled`, and `.notInteractive` produce different copy and would slip
past the guard. Acceptable — the entitlement failure is deterministically
code 1000 — but R-4 should state the guard is scoped to those two codes by
design, so a future reader doesn't mistake it for a general Apple-auth
failure net.

**N-3 — R-2 whitelist omits this item's own docs folder.** The mechanical
pass criterion lists every allowed file but not
`docs/feedback/items/131-apple-signin-error/*` (status.md, QA notes), which
the pipeline must write. A literal-minded build agent could refuse to
update status.md. Add the folder to the whitelist.

### Round-2 verdict

**NOT APPROVED — 2 blocking (B-1, B-2).** Both are confined to R-5's
assertion design; R-1 (the fix), R-2–R-4, R-6–R-9, and all OQ dispositions
are approved as-is. One Author pass rewriting R-5 (Part 2 per B-1 remedy
(a) or an explicitly amended whitelist for (b); Part 1 settle per B-2)
clears the path.

## Author round 3 — incorporation of round-2 review

Both blockers accepted and incorporated in `prd.md`; changes confined to
R-5 (rewritten), plus one-paragraph touches to R-2, R-4, and R-7 for the
non-blocking notes. Nothing else in the PRD was altered — the Planner
approved R-1, R-3, R-6, R-8, R-9, and all OQ dispositions as-is, and they
stand unchanged.

**B-1 — ACCEPTED, remedy (a) taken.** The Planner is right that the
Settings warn toast (`SettingsScreen.tsx` toast path, `Toast.tsx` default
`holdMs = 1500`, ~1.7 s visible lifetime) makes any `notVisible` assert
structurally blind — on a regressed build the toast expires inside the
assert window and the check passes green. R-5 Part 2 is downgraded to
reachability-only: assert `settings.link-apple-btn` renders for the
`standard` profile, tap it, screenshot
(`smoke-11b-apple-settings-link-reachable`). All failure-copy asserts
removed from Part 2, with an in-flow comment stating why so they aren't
reintroduced. Regression sensing is explicitly assigned to Part 1: the
entitlement is binary-wide and the SignIn inline error
(`signin.error-text`) is persistent, so Part 1 covers both surfaces.
Remedies (b) (new `appleBusy` testID + whitelist amendment) and (c)
(`holdMs=0` app-logic change) were not taken — (a) is sufficient, keeps
R-2's zero-app-logic pin intact, and matches the OQ1 disposition.

**B-2 — ACCEPTED.** R-5 now mandates a bounded ≥2 s settle between the
Part 1 tap and the negative asserts, and the flow YAML implements the
Planner's suggested fixed-window probe: `extendedWaitUntil: visible` on
`.*The authorization attempt failed.*` with `optional: true` and
`timeout: 3000`. Pre-fix it returns early when the error mounts
(~200–400 ms) and the following `assertNotVisible` reds; post-fix it waits
out the full 3 s window, then the asserts evaluate against a settled
screen. The step carries a "SETTLE — DO NOT REMOVE" comment explaining the
race, R-5's prose makes the comment's verbatim preservation part of the
requirement, and R-5's mechanical pass criterion now includes "the shipped
flow file contains the settle step with its comment" so a lint-minded QA
agent can't strip it as a redundant wait. The QA agent may swap in an
equivalent harness-accepted bounded-settle idiom, but not remove the
settle.

**N-1 — incorporated.** The flow header now carries the pin ("Failure copy
pinned from expo-apple-authentication@8.0.8 … re-verify
AppleAuthenticationExceptions.swift on any package upgrade"); R-4 gained a
"Version pin" paragraph noting the strings are expo-authored literals and
`package.json` floats `~8.0.8`; R-7's runbook entry now requires the
one-line pin mention, and its pass criterion checks for it.

**N-2 — incorporated.** R-4 gained a "Scoping (deliberate)" paragraph: the
regex covers only `.unknown` (1000) and `.failed` (1004); `.invalidResponse`,
`.notHandled`, `.notInteractive` are intentionally outside the net because
the entitlement failure is deterministically code 1000 — with an explicit
"do not widen the regex" instruction for future readers.

**N-3 — incorporated.** R-2's diff whitelist now includes
`docs/feedback/items/131-apple-signin-error/*` (status.md, QA findings) so
the pipeline's own outputs can't trip a literal-minded build agent.

**Round-3 status: both blockers resolved per the Planner's prescribed
remedies; all three non-blocking notes incorporated. No new open
questions. PRD ready for Planner sign-off / build phase.**

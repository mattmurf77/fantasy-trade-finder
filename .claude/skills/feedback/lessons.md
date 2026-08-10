# Feedback-pipeline lessons

Self-learning log. The orchestrator reads this at the start of every run and
appends after every phase: `- YYYY-MM-DD [phase] lesson`. Keep entries
actionable ("do X instead of Y because Z"), prune ones folded into the skill
files. Seeded from history before this skill existed:

- 2026-07-12 [build] Tiers drag is `react-native-draggable-flatlist` with
  `PlayerCard` in `<View pointerEvents="none">`; any new gesture capturing
  list touches crashes — this broke TestFlight builds #11/#12.
- 2026-07-12 [build] Group items on the same screen under one agent (same
  file → one owner); disjoint ownership tables made feedback-batch-4's
  parallel worktrees merge cleanly.
- 2026-07-12 [qa] Most Maestro flows still match visible text, not testID —
  copy changes break flows. When a flow flakes after a UI tweak, fix the
  matcher, don't loosen it; prefer adding testIDs (registry in
  docs/plans/mobile-testing/lld.md).
- 2026-07-12 [qa] Maestro needs JAVA_HOME exported and a booted simulator
  with the app installed via `npx expo run:ios` (first build ~10 min).
- 2026-07-12 [ship] EAS `production` profile auto-increments build number;
  ASC app id lives in mobile/eas.json. auth.accounts is dark pending ASC
  setup (docs/runbook.md) — don't flip it as a side effect of a batch.
- 2026-07-12 [ship] Operator granted a standing ship-without-review waiver for
  the 126/131/127/130/134/135/136 batch (recorded in chat): Phase 5 go/no-go
  is pre-authorized once QA is green; report the ship summary after pushing.
  Waivers are per-batch — do not carry to future runs without re-asking.
- 2026-07-17 [build] Do NOT let parallel build agents each run simulator
  verification — one shared sim + one harness Flask + a shared
  mobile/ios/build output dir means they reseed each other's DBs, strand
  Flask on deleted inodes, and wait-loop on each other's xcodebuild. Rule:
  build agents verify statically (tsc/pytest/grep); runtime verification
  belongs to the batch QA round, EXCEPT at most ONE agent whose fix is
  behavior-only (gesture/keyboard/resume) may hold the sim, with --out to
  its own scratchpad and its own Flask port.
- 2026-07-17 [build] Agents that end their turn "waiting for the build"
  stall forever — the completion event may not re-invoke them. Prompts must
  say: poll the artifact path yourself each turn; never end a turn to wait.
- 2026-07-17 [build] Parallel agents MUST NOT each pursue simulator
  verification — 5 agents contended one sim/Flask (port conflicts, DB
  reseeds over each other, stranded Flask on deleted inodes). Rule: build
  agents do static verification only (tsc/pytest/grep proofs) + write a QA
  checklist into their status.md; runtime verification belongs to the
  batch QA round, serialized. Exception: at most ONE agent may hold the
  sim, with its own --out dir and Flask port.
- 2026-07-17 [build] Flag-gated launched features must fail OPEN client-side
  (LAUNCHED_FLAG_DEFAULTS in useFeatureFlags.ts): an empty first-boot flag
  map hid live ESPN linking on the operator's device (FB-115 recurrence).
  When launching a flag, add it to the defaults in the same change.
- 2026-08-08 [triage] Three of eight items in this batch were NOT what the
  report said: #262's "RookieRanks" was a route name (RootNav's global FAB
  reports the focused route verbatim, so `activeScreen` strings are route
  names, not files — grep TabNav registrations, don't conclude "screen
  doesn't exist"); #208 and #262 were both already fixed on the branch but
  reported against the older TestFlight binary. Rule: always ask "does this
  still reproduce on current code?" in the agent prompt, and have the agent
  answer it in the PRD before writing any fix. Two agents correctly wrote
  zero production code because of this.
- 2026-08-08 [triage] Testers report against the shipped build, but this repo
  carries a long-lived unshipped branch. Record the tester's build number vs
  the branch state in triage; a "fix" for something already fixed is pure
  regression risk.
- 2026-08-08 [build] Worktree agents branched from an OLDER commit than the
  working branch HEAD (merge-base 20548ff vs HEAD 30492ac, 4 commits behind).
  Check `git merge-base` per branch before merging and rebase first — agents
  don't notice they're on a stale base.
- 2026-08-08 [build] Disjoint SOURCE-file ownership held perfectly across 5
  parallel agents, but three of them independently edited the same shared
  docs (`docs/cross-client-invariants.md`, `mobile/src/*/CLAUDE.md`). Assign
  shared doc files an owner too, or expect trivial-but-real merge conflicts.
- 2026-08-08 [build] Every worktree lacked `mobile/node_modules`; all five
  agents independently symlinked the main checkout's to run tsc. Put this in
  the build-agent prompt template so each one doesn't rediscover it.
- 2026-08-08 [build] Parallel mockup + fix agents on the same item cluster can
  diverge on copy: the #257 mockup used "Win-now moves" while the #256 fix
  agent shipped "Team-fit moves" (correctly rejecting win-now, since the
  `window` lane means youth+picks for a rebuilder). When a fix and a mockup
  touch one surface, the fix agent's decisions win — tell the mockup agent to
  read the fix's PRD, and reconcile at report time.
- 2026-08-08 [build] A polish item surfaced a real defect the report didn't
  name: #260's "explain the ^3" was actually a 9px delta chip violating the
  11px Chalkline type floor — the glyph was unreadable, not unexplained. Two
  keys already existed. Ask "why did the existing affordance fail?" before
  designing a new one.
- 2026-08-08 [ship] origin/main was 62 commits AHEAD of the session's
  checked-out branch (concurrent sessions ship to main). Integration must
  target a fresh worktree off origin/main, never the session branch —
  CLAUDE.md now mandates branching from origin/main. Verify with the W3 pin
  scripts (mobile/tests/check-*.js) as well as tsc/pytest; they need the
  node_modules symlink too.
- 2026-08-08 [ship] `eas build` and multi-item status loops can be blocked by
  the permission classifier in some sessions — hand the EAS command to the
  operator as a runnable block, and set statuses one call at a time.
- 2026-07-17 [ship] eas build --non-interactive cannot regenerate a
  provisioning profile after an App ID capability change (Apple login
  required) — the operator must run one interactive `eas build`; subsequent
  non-interactive builds reuse the regenerated profile fine.
- 2026-08-10 [plan] The dual-agent loop earned its cost three times in one batch:
  every group's Round-2 review returned NOT-READY, and each found a test that
  **passed on the very defect it named** — G1's collision test (its stub raised
  on the triggering input, so the colliding row never entered the map), G2's
  one-sided distributional bars (a fully collapsed `sf_tep` board scored HIGHER
  variety than a healthy one, so `>= 12` passed), G3's atomicity assertions
  (`picksAlwaysCounted={false}` satisfied all twelve). Rule: every new
  behavioral test must be **proven to fail** on a deliberately sabotaged build
  before it is accepted, and every distributional bar must be **two-sided**.
- 2026-08-10 [plan] Commit each group's spec at its **Phase 1 exit**, not on a
  shared timer. G2's build agent branched from a commit holding only Round 1 of
  its own PRD, found its instructions contradicted the documents, and had to
  reconstruct the contract from code. It did so correctly — but "it's in the
  working tree" is not "it's in the repo", and that was an orchestrator error
  covered by agent diligence.
- 2026-08-10 [build] Never symlink the main checkout's `mobile/node_modules`
  into a worktree (the lesson from 08-08 is now actively harmful): it was ~190
  commits stale and lacked `@react-native-cookies/cookies`, producing a phantom
  `tsc` error that would have polluted every gate. Run `npm ci` in the worktree.
- 2026-08-10 [build] Verify a build agent's BASE, not just its diff. One
  worktree came up carrying four commits from a concurrent session; another came
  up on a superseded spec. `git log --oneline -5` in the agent's prompt, and the
  agent reporting what its base contains, caught both.
- 2026-08-10 [build] A clean auto-merge is not a correct merge. A concurrent
  session rewrote `LeagueSummaryScreen.tsx` — the same file G3 rewrote — and git
  merged it without conflict. The 71-assertion AST check is what proved the
  result was actually sound (exactly two `activeTotal` call sites, both gated).
  When two sessions touch one file, re-run the structural checks, don't trust
  the merge.
- 2026-08-10 [triage] Reference docs drift *away* from live code and hide real
  bugs. FIVE locations (`config/features.json`, two `config-reference.md` rows
  incl. a default column reading `false` for a flag shipping `true`,
  `architecture.md`, `glossary.md`) all claimed the mock draft was OFF and
  unvalidated. It had been live for two days. That is *why* #290 went unnoticed.
  Grep the docs for the feature under investigation before concluding anything
  about its state.
- 2026-08-10 [ship] **`mobile/app.json` does not ship a version.** Bare
  workflow — `mobile/ios/` is tracked, so EAS reads the native Xcode project and
  ignores the Expo config. Build 97 shipped 1.11.0 with `app.json` at 1.12.0.
  Bump all three: two `MARKETING_VERSION` in `project.pbxproj` +
  `CFBundleShortVersionString` in `Info.plist`. `eas build:version:set` sets the
  **build number only**. Cost one wasted build.
- 2026-08-10 [ship] Verify a deploy **by content**, not uptime. Polling `/` for
  200 proves nothing — the old build also returns 200. Poll for something only
  the new build can produce (here: the new flag key in `/api/feature-flags`).
- 2026-08-10 [qa] A QA gate that fails on first contact with real data teaches
  its reader to ignore gates. The #289 PRD invented a "≤10% fallback rate" bar;
  replaying all four corpora measured **49%**. Replaced with report-the-rate +
  escalate, keeping only absolute FAILs. Prefer measured thresholds or none.
- 2026-08-10 [qa] The pre-ship sim gate had **never actually run** — every prior
  ledger entry reads "NOT PERFORMED", which is how three flag-pin defects and a
  bash-3.2 `$!` bug survived (stale-Flask assertion firing on a *clear* port;
  the EXIT trap orphaning Flask for the next run to talk to). Before trusting
  any harness, check whether its evidence trail shows it ever passed.
- 2026-08-10 [qa] Harness claims don't survive verification: "no lint exposure"
  (six failures), "zero seeder work needed" (the seeder writes no `mock_drafts`
  at all), "one `leagues[]` entry fixes it" (wrong). Make agents RUN the harness
  command rather than reason about it.

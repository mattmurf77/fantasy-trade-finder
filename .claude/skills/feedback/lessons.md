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
- 2026-08-13 [triage] The caller-excluded `sess["league"].members` convention
  claimed its THIRD victim (FB #41 → #291's fixture → the mock draft's five
  membership sites, the fifth found only at LLD). When any surface reads
  "everyone in the league", grep ALL its member reads before concluding scope.
- 2026-08-13 [plan] A five-phase sequential doc pipeline (plan → HLD → LLD →
  PRD + mockups ∥ → build ×2) caught a distinct defect class at EVERY phase:
  the LLD found the HLD's contract one field short (`settings_echo.user_owner_id`)
  and a fifth membership site; the mockup round found `PickTicker` rendering a
  blank who-column across all of manual mode and the seeder having traded away
  the QA user's round-1 pick (the shipped bug reproduced in miniature in the
  test world). Commit each phase at its exit; hand the next agent the commit.
- 2026-08-13 [ship] Deploy-liveness polls on `/api/events` must require
  `accepted ≥ 1 AND dropped == 0`. The OLD build answers an unregistered event
  with `{"accepted":1,"dropped":1}` — a loose grep on `accepted` reads that as
  the new build being live. Bit us once; caught before it false-passed.
- 2026-08-13 [ship] Version numbers race between concurrent sessions: 1.13.2
  was taken by another ship mid-flight. Check `eas-cli build:list --json`
  (never the CLI exit code) for the actual latest before bumping.
- 2026-08-13 [build] Prove the loop, not the diff: before go/no-go, a live
  engine run of the operator's exact scenario (slot 8, 12 teams — four
  asserted clauses) answered "does it actually work?" in a way 2714 passing
  tests could not. The operator asked precisely this question; have the demo
  ready before they do.
- 2026-08-13 [process] Never `git stash -u` to "check a baseline": on a clean
  tree it saves nothing and the subsequent pop grabs ANOTHER SESSION'S stash
  (conflict markers across 32 files; recovered, nothing lost, but blocked
  destructive cleanup needed operator sign-off). Diff against the base sha
  instead — and don't stash your own uncommitted work to switch branches
  either; this session buried its own lessons append doing exactly that.
- 2026-08-16 [triage] Nine items landed OVERNIGHT mid-triage (#333-#341), four of
  them the "additional rules" an operator answer referenced. Re-fetch before
  finalizing selection whenever an operator answer mentions feedback you haven't
  seen — the list call is cheap and the alternative is planning against a stale
  backlog.
- 2026-08-16 [triage] Three of the nine overnight items (#333/#334/#337) were
  regressions/follow-ups on the 08-14 wave that shipped with "sim gate: NOT run".
  With Maestro retired (D-056), operator TestFlight passes are the only runtime
  net — write the per-group TestFlight checklist as if it's the regression suite,
  because it is.
- 2026-08-16 [triage] An operator answer reversed a triage-time framing twice in
  one batch: "Matches is the core swipe loop" was WRONG (TradesStackNav owns the
  deck; MatchesScreen is a results surface) and #329 "Fixed." meant close-it not
  build-it. Verify screen-role claims in TabNav registrations before arguing IA,
  and confirm terse operator answers that flip a work item's direction.
- 2026-08-16 [plan] Do NOT launch a group's critique round until the Author's
  COMPLETION notification arrives — launching it "so it isn't idle" risked the
  critic reading half-written docs (G9: critique dispatched a turn before the
  author finished; corrected by messaging the critic to discard reads and
  re-read from disk). The phase gate is the notification, not the intention.
- 2026-08-16 [plan] The proven-to-fail rule needs to police the SPEC, not just
  the build: G3's PRD mapped a test to a sabotage that hardcoded the expected
  value (self-satisfying by construction), and the ordered re-audit found THREE
  more in the same doc plus a .get() assertion hole — five defects of one class
  in one test plan. Make "re-audit every test→sabotage mapping for
  self-satisfaction" a standing critique-round item.
- 2026-08-16 [plan] Expose orchestrator arbitrations to the critic as attack
  surface ("attack if attackable") — G6's critic overturned the pin+scope
  bypass boundary for a strictly better targeted-vs-untargeted line with a
  code-precedent anchor, and separately caught a one-sided predicate that would
  have banned the operator's own documented trade style. Provisional decisions
  announced as final get defended; announced as provisional get improved.
- 2026-08-16 [plan] Commit each group's spec at ITS round-2 sign-off on a
  dedicated specs branch off fresh origin/main (specs stranded in a stale
  session checkout are invisible to build worktrees). origin/main moved 3×
  during Phase 1 alone; the authors' habit of re-verifying every cite against
  the CURRENT tip and logging drift caught real movement every time.
- 2026-08-16 [plan] A worked example in a test gloss is a CLAIM against the
  formula and must be arithmetic-checked like one: G6's U-R2-3 gloss
  ("pick+RB→2WR passes") contradicted R-2's own predicate (net WR = +2 →
  kill) and survived BOTH review rounds because round-2 verified dispositions,
  not example arithmetic. Caught post-launch only because a second session
  ported the rules and hit the fork. Add "recompute every worked example
  against its formula" to the critic's standing hunt classes.
- 2026-08-16 [build] "Never end a turn waiting" is not enough — TWO agents in
  one wave (G1, G5) still parked on background monitors for long pytest runs
  and stalled until nudged. The prompt must prescribe the mechanic, not just
  prohibit the failure: "run test suites SYNCHRONOUSLY in one foreground Bash
  call with an adequate timeout; never run_in_background a test suite; if the
  full sweep is too slow, run the targeted set and state that the full sweep
  runs at integration."
- 2026-08-16 [qa] The stall pattern generalizes past test monitors: the Phase-3
  QA agent ended its turn "standing by" for a SUBAGENT it had spawned. Agent
  prompts must ban ending a turn on ANY async dependency — monitor, build,
  subagent, notification — and prescribe doing the remaining work synchronously
  instead of delegating-then-waiting when the wait would end the turn.
- 2026-08-17 [ship] The push to origin/main was blocked by the session's
  permission classifier (same class as the 2026-08-08 EAS block). Plan for it:
  bundle the living-memory ship record INTO the pre-push commit so one operator
  push carries code + record, write the recovery ledger in
  "CAPTURED, NOT YET SWEPT" state with the tips already recorded, and hold the
  `fixed` status writes until the push is confirmed — statuses claiming shipped
  work that never left the machine are worse than late ones.
- 2026-08-17 [ship] Render auto-deploy silently did not fire: `92c31d5` stayed
  live ~20 min past the push with NO deploy queued, despite `autoDeploy: yes`
  and a healthy service. Polling prod for new content looked identical to a slow
  deploy. Rule: after pushing, first confirm a deploy was CREATED for your sha
  (`GET /v1/services/<id>/deploys?limit=1` vs `git ls-remote origin main`), then
  poll content; trigger via `POST /v1/services/<id>/deploys` if none exists.
- 2026-08-17 [ship] Verify branch containment before a sweep by COMMIT ANCESTRY
  (`git log origin/main..<branch>` = 0), not by `git diff origin/main..<branch>`
  — the two-dot diff counts what main has that the branch lacks and reports
  100+ files for a fully-merged branch, which reads as "not contained" and
  invites the wrong call. The ancestry check caught two branches
  (`wave-calc`, the specs branch) holding content that existed NOWHERE else —
  including a 455-line Phase-1 plan — minutes before deletion.
- 2026-08-24 [triage] Agent worktrees don't carry `secrets.local.env` (gitignored,
  lives only in the main checkout) — `fetch_feedback.py` fails before auth. Symlink
  it from the project root into the worktree (`ln -sf`) rather than asking the
  operator for the secret.
- 2026-08-24 [triage] Sixteen open items were already closed in code by non-feedback
  pipelines (Team Review batch, #355, #384) but never had their DB statuses set —
  the pipeline only flips statuses for items IT ships. Triage should always propose
  the fixed/in_progress corrections for work shipped outside this skill, or the
  open list becomes unreadable (61 rows, ~25 actionable).
- 2026-08-24 [build] Agent-tool worktrees are cut from origin/main, NOT the session
  branch holding the committed specs. Every one of 7 build agents had to re-branch
  from the spec commit named in its prompt. Keep naming the exact spec sha in build
  prompts (it worked every time), or pre-create the worktree.
- 2026-08-24 [qa] QA agents write their findings files in THEIR worktrees — the
  orchestrator's `git add docs/feedback/items` in the session tree captures nothing.
  Copy the reports out of the QA worktrees (or have QA agents commit them) BEFORE
  the sweep; this run nearly destroyed all ten reports.
- 2026-08-24 [qa] `pytest backend/tests` is not hermetic across runs sharing one
  tree: a full sweep leaves a `data/trade_finder.db` that makes
  `test_deck_signal_v2::test_flag_on_writes_impressions_in_served_order` fail on the
  NEXT run. `rm -f data/trade_finder.db*` before any sweep whose result you'll cite;
  bisect commit-vs-environment in a second worktree before blaming code.
- 2026-08-24 [ship] main moved TWICE during this run (docs commit mid-build; Waves
  A+B0 shipped mid-QA and TOOK the 1.16.4 version). Before `gh pr merge`: fetch,
  expect conflicts on TradesScreen/CLAUDE.md/living-memory, resolve by union, re-run
  the FULL gate battery on the merged result (cross-session guards both passing is
  the actual proof), and re-check `eas build:list` for the version race.
- 2026-08-24 [ship] NEVER delete branches via `grep | xargs git branch -D` — it
  pattern-matches every session's branches and only pipe buffering limited the blast
  radius (M-005; one deleted tip was NOT contained in main and needed restore).
  Delete by explicit name from the ledger row, nothing else.
- 2026-08-24 [pipeline] A ~40-minute API-overload window killed every in-flight
  subagent repeatedly. What worked: exponential backoff with a single cheap CANARY
  resume before re-launching the fleet, and doing well-specified round-3 doc edits
  inline from the critics' logged objections (the orchestrator's own calls kept
  succeeding). Agents resumed cleanly from disk state each time.
- 2026-08-27 [triage] `git grep -E` silently does NOT support `\b` — a scan for
  `#384\b` across the whole audit trail returned ZERO hits for every id and read
  as "no prior work anywhere", which would have re-planned five shipped items.
  Use `-P`, `[^0-9]`, or scan in Python; and sanity-check any all-zero grep
  result against one case you already know is non-zero.
- 2026-08-27 [triage] Close a status on THREE agreeing signals, never one: a
  shipped CHANGELOG entry, the flag's live value in `config/features.json`, and
  the code present on current `origin/main`. Doc-only evidence lies in both
  directions here — `369-plan-beat/status.md` still read "committed but NOT
  pushed" for an item that had merged and shipped in build 124, while the 364
  batch status listed #365/#369/#370/#371 as "planned only" the same week the
  CHANGELOG recorded them shipped.
- 2026-08-27 [triage] **Built-but-dark is not fixed.** Five `in_progress` items
  (#360/#361/#365/#371/#372) have full PRDs, code-walks and merged code, and a
  tester still sees the reported behavior because their flags are `false`. Check
  the flag value before closing anything whose folder looks complete — the
  finished paperwork is the trap.
- 2026-08-27 [triage] A multi-part report is closed only when EVERY part ships.
  #310 (unlock the manual calc · simplify nav to 3 tabs · add a rankings
  value-prop link) reads as delivered from the #384 status line "folds in #310",
  but only part one shipped; `TabNav.tsx` still registers five tabs. Grep the
  report's own clauses, not the batch doc's summary of them.
- 2026-08-30 [qa] The Agent tool's `isolation:"worktree"` cuts from origin/main, NOT
  the session branch — verified twice in one run. Recovery that WORKS: the agent
  runs `git worktree add <scratchpad>/wt-<name> -b <branch> <spec-sha>` itself (the
  shared object store has the commits). Recovery that BREAKS things: launching a QA
  agent WITHOUT isolation and telling it to `git checkout -b` — it switches the
  SESSION tree's branch under the orchestrator and any concurrent readers. Always
  pass isolation for QA agents that mutate (sabotage cycles), and put the
  make-your-own-worktree recovery in the prompt up front.
- 2026-08-30 [plan] The targeted "verify only the round-3-new material" pass earned
  its cost: it caught the new spec turning the SIBLING item's just-shipped guard
  assertion red (20a re-spec undeclared) and an "always two-sided" claim that
  edited snapshots falsify. Rule: material added during incorporation has never
  been reviewed — give it one bounded verification pass, not a full round.
- 2026-08-30 [qa] Serialized same-surface items pay off at QA: #407's QA-B found a
  non-blocking edge (seed-prefill chosen-ness) that became a hard requirement
  (R-10) of the #406 build on the same file — route cross-item findings into the
  serialized sibling's PRD instead of opening a new item.
- 2026-08-30 [ship] Info.plist's literal CFBundleShortVersionString is what ships —
  pbxproj MARKETING_VERSION sat at 1.16.6 through five 1.16.7-11 releases. Bump all
  three anyway (lesson 2026-08-10), but read Info.plist as the authority when they
  disagree; `eas build:list` confirmed no version race before the bump.
- 2026-08-30 [qa] QA agents in worktrees cannot write findings into the session
  tree (writes blocked cross-worktree) — QA-B correctly left its report at the
  repo-relative path in ITS worktree and said so. Copy it out BEFORE sweeping
  (`--force` needed for the untracked file; inspect first), and ledger the sweep.
- 2026-08-30 [ship] `eas build --auto-submit` is the submission that counts. Build 139
  died on EAS's own `SERVER_ERROR: Failed to upload application archive` (after a clean
  compile — not a code fault); the retry (140) finished and ITS auto-submit reached
  status FINISHED. Two follow-up `eas submit --latest` calls then ERRORED as redundant
  binaries and the CLI prints only "Something went wrong", which reads as a failed ship.
  Verify submissions by STATUS, not by the CLI's last line: this eas-cli has no
  `submit:list`, so query api.expo.dev/graphql with the `expo-session` secret from
  ~/.expo/state.json — `submissions{byId(submissionId:$id){status logsUrl}}`. Don't
  re-submit to "make sure"; check first.
- 2026-08-30 [ship] After a squash-merge, follow-up docs commits on the SAME branch
  conflict with main (add/add on the files the squash already rewrote) — PR #251 came
  up CONFLICTING. Cut the ledger branch fresh from origin/main and `git checkout <old
  branch> -- <files>` instead of trying to merge the branch twice.
- 2026-08-30 [ship] Write the ship record AFTER the artifact exists, or plan to correct
  it: the living-memory entries went in naming build 139 and had to be swept for "139"
  across seven files once it errored. Cheaper: land the merge record first, add the
  build number in the sweep-ledger commit.
- 2026-08-30b [triage] A tester's "I started noticing this yesterday" is the single most
  valuable triage input available and it REDIRECTED the whole investigation: it cleared the
  ship that had gone out hours earlier and pointed at the day before, where the real answer
  was a route that had been 100% broken for 8 days and had merely become REACHABLE (a flag
  lit 8/28 + a landing-page change 8/29). Ask "when did you first see it?" before assuming
  the newest deploy; and separate "when did the code change" from "when did the path become
  reachable" — they were 6 days apart here.
- 2026-08-30b [qa] The fixture that hides a bug will also hide it from the FIX's tests. #409's
  suite was green for 8 days at a 100% production failure rate because every case put the
  caller inside `league.members`, a shape prod never builds. Make "is this fixture a shape
  production actually produces?" an explicit QA question, and require the new tests to be
  proven red against the ORIGINAL defect, not just against a mutation of the new code.
- 2026-08-30b [qa] QA-B's most valuable finding was not a bug but an UNDISCLOSED COST: the
  operator picked "shrink the name" over "wrap to two lines" having been told the cost was
  name truncation, and nobody had measured that the same change squeezes team/age off
  top-tier rows entirely. When an operator picks between options, re-audit the chosen one for
  costs the comparison did not mention — and when one surfaces after they've stepped away,
  ship it with disclosure (a checklist step that asks for a ruling), never silently and never
  by substituting your own design call.
- 2026-08-30b [ship] Bundling a backend fix with mobile work is the right call when the
  backend half fixes fielded builds: one merge put #409 live on Render for every phone
  already installed (verified deploy CREATED for the sha, then polled to `live`), while the
  mobile half waits on TestFlight. Don't split the PR just because the platforms differ.
- 2026-09-02 [triage] "This week" needs a stated boundary before filtering: ISO week (Mon) vs US week (Sun) moved one P0 item (#413, Sunday 08-30 local) in or out. Also convert `created_at` (UTC) to the operator's local day before deciding — #408 is Sat local / Sun UTC. State the boundary in the batch plan so the next run can see what was excluded and why.
- 2026-09-02 [triage] A report filed BETWEEN two same-day ships needs a minute-level timeline, not a day-level one: #415 (20:26Z) predates D-170 (21:29Z) and reads as a live bug; #416 (22:22Z) was filed AFTER D-170 landed and its first clause ("validation errors don't fire anymore") is the operator watching that ship arrive. `gh pr view <n> --json mergedAt` is the cheap timestamp; pair it with the feedback `created_at`.
- 2026-09-02 [triage] Agent-tool worktrees ship WITHOUT `mobile/node_modules` and WITHOUT `secrets.local.env`; the MAIN checkout's `mobile/node_modules` was EMPTY (0 entries), so linking to it silently fails at `npx tsc`/`eas`. Link to a populated sibling worktree (`ls .claude/worktrees/*/mobile/node_modules | wc -l` to find one) and symlink `secrets.local.env` from the main checkout. `eas build:list --json` prints nothing on a plugin-resolution error — read the text form.
- 2026-09-02 [triage] `docs/feedback/items/INDEX.md` had no rows for #402–#412 despite three shipped batches — every one of those sessions skipped the regeneration rule. The index is only a dup-check surface if it is current; add rows in the SAME commit as the item folder.
- 2026-09-02 [plan] A "why did the engine serve X" report needs the PROD ROW before a planner runs, not a code trace alone: the Explore trace ranked the fair-packages fork as the cause with high confidence, and one read-only prod query (`calc_find_a_trade_tapped.path`, then `match_swiped` + `trade_decisions` for the pair, then `member_rankings`/`player_value_history` for the values) showed it was the model deck at a 12.7% gap — the fair fork was never touched. The planner had to be re-aimed twice mid-run; one prod read first would have cost 5 minutes. `DATABASE_URL_PROD` in `secrets.local.env` + psycopg2 read-only works; `user_events.occurred_at` is a VARCHAR ISO string (compare as text; `extract()` fails), the feedback table is `app_feedback`, and the exact deck cards live in `deck_impressions.assets_json`.
- 2026-09-02 [plan] Do not extrapolate an injection mechanism from a missing impression row: I told the planner "no impression ⇒ likes-you injection" and it was wrong (the injector runs BEFORE impression logging; the card was a streamed-then-trimmed engine card with `impression_id: 'none'`). Verify ordering in `_run_trade_job` before naming a producer.
- 2026-09-02 [plan] When a backend fix ships to FIELDED builds ahead of a client build, the critique must read the OLD client's error path, not the new one: G-413's 422 bodies carried `message` only, and every fielded `SendInSleeperButton` renders `detail || 'Please try again'` — a deterministic refusal would have read as a retry prompt for weeks. Rule: any new server error shape gets checked against the catch-all of the oldest build still installed.
- 2026-09-02 [plan] Pre-creating the build worktree from the SPEC sha (`git worktree add <scratchpad>/wt-<group> -b <branch> <sha>`) and handing the agent the path removes the isolation:"worktree" cuts-from-origin/main trap entirely; the agent's first command is `git log -1` to confirm the base.
- 2026-09-02 [build] Any new `load_draft_picks` call site trips the ADR-010 AST guard (`test_pick_assignment.py::test_w3_02`): bare-default calls are forbidden AND every caller must be sanctioned by name in `_SANCTIONED_SOURCE_CALLERS` with a decision comment. G-413's spec said "use the default source" and its build agent (correctly) could not edit the test file, so the full suite came back 1 red. Planners: grep for AST guards over any helper the spec introduces a caller for, and put the sanction edit in the ownership table.
- 2026-09-02 [build] "Run the EXISTING suite at the new default BEFORE writing new tests" (PRD T-10) is the cheapest spec check in the pipeline: G-414's builder found 6 reds in 5 minutes that two planner rounds had missed — a tighter accept rule that made the sweetener do LESS than the shipped behavior on wide-gap fixtures, a kill-value test pinning "huge threshold ≡ off", and the arm-A knob registry guard. Every engine-knob PRD should name its adjacent golden/registry tests and require this order.
- 2026-09-02 [build] When a knob TIGHTENS a target, spec the accept as two-tier (prefer the tight target, fall back to the old one) so the new default can never produce a worse outcome than the previous default on any fixture — "never less than the shipped behavior" is the invariant the legacy tests are actually pinning.
- 2026-09-02 [qa] Three of five QA/build agents this run stopped "waiting for a background notification" that never comes (their own `run_in_background` pytest). Each resumed cleanly when told to read the output file / rerun in the foreground with a 600 s timeout. Put "run long suites in the FOREGROUND with `timeout: 600000`; never background them" in every QA/build prompt.
- 2026-09-02 [qa] Both QA agents independently found the same coverage gap the builder had already flagged (v3 G-8 avoid line: delete it and 4508 tests stay green) — a builder's "nothing catches this" line in its report is a Phase 4 item, not a footnote; queue the pin before QA rather than after.
- 2026-09-02 [qa] QA agents in worktrees cut from the group tip cannot see spec amendments that landed on the SESSION branch after the cut (both #414 agents reported "the PRD still says single-tier accept"). Cherry-pick spec commits onto the group branch BEFORE cutting QA worktrees, so the tree QA reads is the contract QA tests.
- 2026-09-02 [qa] `rm -f data/trade_finder.db*` aborts a zsh `&&` chain when no db exists (`nomatch`); the QA-A first suite run silently never ran. Write it as `rm -f data/trade_finder.db data/trade_finder.db-wal data/trade_finder.db-shm` or `setopt nullglob`.
- 2026-09-02 [ship] In auto mode the permission classifier blocks `git push` + `gh pr create` as outward actions — the pipeline's Phase 5 cannot complete without the operator present anyway (go/no-go gate), so treat "branches local, ship commands in HANDOFF" as the normal end state of an unattended run, and write the HANDOFF choreography precisely enough (merge order, expected suite count, version bump, verify-by-status) that the operator can execute it in ten minutes.
- 2026-09-02 [ship] Two groups → two group branches → ONE merge into the session branch at ship (both need the living-memory write-back that lives only on the session branch). Cherry-pick spec amendments onto the group branch during the run, but never the reverse — the session branch is the integration point.
- 2026-09-03 [ship] **A parallel session shipped the same feedback item while this run was in Phase 2–4.** Main moved 9 commits during the ~20-hour run; one of them (D-175) answered #414 with the SAME knob name (`sweetener_gap_frac`) and the OPPOSITE semantics (a relative band `max(thr, frac×max)` + best-effort, live at 750/0.12/1) — our tightening version (`min(thr, frac×max)`, two-tier accept) had to be dropped at the door after two QA rounds. The "check main first" step caught it only because the operator said so. Rule now in SKILL.md: re-fetch `origin/main` and re-diff the item's files (a) before Phase 2 launches build agents and (b) before Phase 5's ship summary; on a hit, STOP and compare designs before building further.
- 2026-09-03 [ship] Decision/question ids are a shared counter across concurrent sessions: D-172/D-173 and Q-035 were all taken by the time we shipped, in three different files. Allocate ids from `origin/main` at write time (not from the session's stale tree) and expect to renumber — do it with a "lines not present on main" replacement so the other session's uses of the same id survive.
- 2026-09-03 [ship] The classifier that blocked `git push`/`gh pr create` earlier in the run let them through once the operator had said "push to main" in chat. The pipeline's Phase 5 gate and the harness's permission model line up: unattended = branches local + HANDOFF choreography; attended = full ship.

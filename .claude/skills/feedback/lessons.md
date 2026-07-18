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
- 2026-07-17 [ship] eas build --non-interactive cannot regenerate a
  provisioning profile after an App ID capability change (Apple login
  required) — the operator must run one interactive `eas build`; subsequent
  non-interactive builds reuse the regenerated profile fine.

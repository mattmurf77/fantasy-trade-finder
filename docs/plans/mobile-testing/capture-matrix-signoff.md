# Capture matrix — orchestrator sign-off (2026-08-09)

Rulings on the 41 ⚠ rows in [capture-matrix-2026-08-09.md](capture-matrix-2026-08-09.md),
binding for flow-authoring agents:

- **A — flag-off in `release` (11 rows): the library captures RELEASE TRUTH.**
  Capture what ships. When a flag flips on later, the freshness contract forces
  recapture. Prerequisite: refresh `backend/tests/fixtures/flags/release.json`
  from current `config/features.json` before the sweep (it may be stale —
  draft.tab etc. flipped recently); rows whose flag is ON in the refreshed
  release set are captured normally.
- **B — native `Alert` states (7 rows): EXCLUDED from v1.** OS chrome, not RN
  surface. Listed in the matrix as `excluded--native-alert` for the record.
- **C — fixture gaps (13 rows + draft/ESPN block): AUTHORIZED — build two new
  profiles (`draft`, `espn`) + the three `/__test__` pins** (deck size,
  QC-trio selection, streak seed) proposed by the inventory pass. Without them,
  five screens (draft-room, mock-draft, pick-assignment, record-picks,
  LeagueScreen ESPN branch) have zero coverage. This is a P3 backend workstream
  with its own agent.
- **D — nondeterministic (4 rows):** the pins above cover deck/trio; residual
  variance is accepted — captures need to be representative, not byte-stable
  (already documented in `screens/CLAUDE.md`).
- **E — gesture/timer-only (6 rows): EXCLUDED from v1** (mid-gesture states
  aren't reachable by Maestro reliably). Recorded as `excluded--gesture`.

- **OPERATOR DIRECTIVE — analyst onboarding experience IS captured (exception
  to ruling A).** The guided onboarding-conversion flow (The Analyst mascot —
  poses neutral/point/celebrate/computing/thinking/oops — speech-bubble scenes
  per `docs/plans/onboarding-conversion/guided-avatar-script.md`, spanning
  SignIn → LeaguePicker → QuickSetTiers → Rank surfaces) is captured under a
  dedicated flag fixture with the `onboarding.*` sub-flags forced ON
  (`backend/tests/fixtures/flags/onboarding-v2.json`, honoring the launch
  pairing: `landing.try_before_sync` + `onboarding.landing` flip together or
  the demo endpoint 404s). Storage: `screens/mobile/onboarding/<scene>.png`,
  one capture per scripted scene + each analyst pose in situ; profile `fresh`
  (onboarding starts with a new user). Manifest rows carry
  `flags: onboarding-v2` so the exception is self-documenting.

Also adopted from the inventory pass: `TradeFinderHubScreen` gets zero rows
(verified unrouted dead code — separate cleanup candidate); `EspnLinkSheet`
steps ARE captured (input/team/done/private-fields), only the pushed WebView
screens are excluded; the testID-vocabulary drift vs LLD Appendix A and the
missing `testid-lint-allow.txt` entries are owed a lint sweep (P4 wiring).

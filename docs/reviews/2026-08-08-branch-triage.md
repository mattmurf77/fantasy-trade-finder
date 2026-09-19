# Branch triage — 2026-08-08

**Scope:** every local branch holding at least one commit whose content is absent from
`origin/main`. Re-derived on 2026-08-08 after `git fetch`: **50 branches** (the earlier
audit counted 52; the list drifted). Verification was done **by content, at file
granularity** — `git cherry` candidates were checked against `origin/main`'s current
blobs, because this repo squash-merges PRs and both ahead-counts and `git branch -d`
lie about merged-ness. All inspection was read-only, from committed refs (the working
tree mutates concurrently).

**Verdict counts: 3 RECOVER · 3 ASK · 44 DELETE.**

Cross-cutting finding: the vast majority of "commits absent from main" are squash-merge
residue. Four squash commits alone account for 41 branch-commits:
`bfa3837` (PR #13, the whole 19-commit web batch), `247d9b5` (PR #40, all of mobile
parity B1–B8 + integration), `7a05f4e` (PR #88, feedback batch 4), and
`e9467b1`/`af22867`/`c22e731` (feedback pipeline PRs #43/#41/#55).

**Worktree note:** 31 of the 50 branches are checked out in worktrees (marked ⚓ below)
and cannot be deleted until their worktree is removed (`git worktree remove <path>` or
`git worktree prune` after deleting the directory). `teardown-remediation` is special:
it is the branch checked out in the **primary repo checkout itself** — deleting it
requires switching the main checkout to another branch first, not pruning.

---

## 1. Decision table

Ranked: RECOVER, then ASK, then DELETE.

| Branch | Commits absent | Age / behind | Verdict | Basis |
|---|---|---|---|---|
| `teardown-remediation` ⚓(primary checkout) | 2 | 2026-08-06 / 76 | **RECOVER** | `969f454`: three #207 rookie-draft-detection docs (`docs/feedback/items/207-rookie-draft-detection/{plan,research-codebase,research-platforms}.md`, 1,087 lines) — verified absent from main. `30492ac`: `enabled: hasToken` query gates on RankScreen, TiersScreen, QuickRankScreen, QuickSetTiersScreen, ManualRanksScreen, PickAnchorScreen — main has the producer (`useSession.ts` sets `hasToken:false` on 401) but **zero consumers** in those six screens (verified 2026-08-08), so a dead session still fires token-less requests that can only 401. Everything else in both commits is on main. |
| `mobile/yellow-followups` | 2 | 2026-04-27 / 456 | **RECOVER** | 4 of 6 fixes in `f6732ce8` are on main (atomic `switchLeague` acquire `useSession.ts:314-331`, unread cap `useNotifications.ts:53`, unlock-poll stop `RootNav.tsx:251`, narrowed deps `TradesScreen.tsx:1117`); one is moot (MatchesScreen rewritten). **Missing:** the push-permission-status feature — `permissionStatus` slice on `useNotifications`, "push notifications off" banner on LeagueScreen with `Linking.openSettings()` deep-link, and `f7aa9775`'s AppState-foreground re-read of `getPermissionsAsync()`. Zero trace on main (`git grep permissionStatus` → 0 hits). Real user-facing gap: users who denied push get no signal and no path to re-enable. |
| `chalkline-primitives` | 1 | 2026-07-03 / 351 | **RECOVER (cherry-pick only — do NOT merge)** | `794c296`: two whole primitives never landed — `mobile/src/components/chalkline/SegmentedTabs.tsx` (109 lines) and `Spinner.tsx` (48 lines), zero hits on main — plus prop additions `Card.onPress` and `Badge` icon/mono/dim. **Danger:** the same commit *removes* things main added later (Button's `useFlag` gates for `a11y.text_scaling`/`ux.touch_polish`/`visual.chalkline_cleanup`, `testID`, `Card.padding`); its message carries unresolved-conflict markers from a rebase. Take the two new files and hand-apply the prop additions; discard the 24 stale screen migrations. |
| `claude/loving-wright-c2e9e2` ⚓ | 3 | 2026-04-21 / 465 | **ASK** | Holds the only copy of a 54-file, ~5.6k-line SwiftUI client (`DTF/` — iOS 17 + macOS 14, APIClient/Keychain/ViewModels/4 view trees; `f802f5b` + `9758691`) that never touched main. It's an abandoned April architecture pivot — the product shipped on React Native, and the branch's own message says Trades/Matches 500'd. **Decision needed:** archive the DTF spike (tag or `archive/`) or drop it. Also: `a587456` deletes all of `mobile/` — never rebase/merge this branch. Worktree: `.claude/worktrees/loving-wright-c2e9e2`. |
| `audit/perf-optimization` | 1 | 2026-06-07 / 400 | **ASK** | `71ed60b`: 38 files / ~8,791 lines of audit docs (`docs/code-audit/perf-optimization/` — research deep-dives, 38 RICE-P findings with file:line evidence, 16 per-initiative requirement files) absent from main. This is a **known, documented open question**: main's `docs/plans/perf-optimization/artifacts/questions-for-user.md` Q2 asks exactly "merge the audit docs to main?" with default "leave on branch". Wave 3 (INIT-08/10/11b/16) is still open, so those requirement files have forward value. **Decision needed: answer Q2.** |
| `feat/wave1-perf` | 1 | 2026-06-07 / 400 | **ASK (resolves with Q2)** | Its only absent commit is the same `71ed60b` docs commit; all wave-1 *code* patch-id-matched to main. Whatever Q2 decides for `audit/perf-optimization` applies here; the branch itself is then deletable. |
| `web/feedback-batch-2026-04-29` | 19 | 2026-04-29 / 448 | DELETE | Squash-merged same day as PR #13 (`bfa3837`); `git diff bfa3837 <branch>` is empty tree-wide. All 19 spot-verified on today's main. One commit (`397d8f1`) superseded by a better rewrite (`_match_body()`). |
| `feat/mobile-parity-2026-04` | 10 | 2026-05-20 / 426 | DELETE | Squash-merged as PR #40 (`247d9b5`); branch diff vs merge-base ≡ squash diff (132 files, +10049/−63). All 8 bundles verified on today's main. `equalOnly` was merged then intentionally replaced by PR #54's fairness toggle. |
| `fix/tiers-rework` | 5 | 2026-06-09 / 382 | DELETE | The June drag-engine arc: discarded custom engine leaves no trace on main; the surviving design (`react-native-draggable-flatlist`, Pressable fixes, multi-select) is on main with the branch's comments carried verbatim (`TiersScreen.tsx:18-21/508/935/956`). |
| `claude/hungry-allen-8615ed` | 4 | 2026-04-27 / 456 | DELETE | Haptics taxonomy, Keychain last-username, and the whole streaks feature (schema, `/api/me/streak`, flame chip) all on main incl. the PR-review race fix; main is strictly ahead (extra streak events, tests). |
| `feat/feedback-batch-4-polish` ⚓ | 3 | 2026-06-19 / 358 | DELETE | FB4 integration branch; shipped as PR #88 (`7a05f4e`). All five docs blobs byte-identical on main (sha equality); components present and extended. Worktree: `fb4-integration`. |
| `mobile/tiers-multi-select` | 2 | 2026-04-30 / 432 | DELETE | Within-tier reorder superseded (the library main adopted provides it natively); multi-select present and evolved — main has 3 bulk ops vs the branch's 1. |
| `fix/trios-hide-unlock-promo-when-unlocked` | 2 | 2026-04-29 / 453 | DELETE | Unlock floor at `server.py:5987-6018` (since extended); promo hide at `app.js:1956-1962`. |
| `feat/in-app-feedback-capture` | 2 | 2026-05-20 / 425 | DELETE | Direct ancestor of the shipped FeedbackFAB system (PR #41 `af22867`); all files present on main with sync fields layered on. `eas.json` on main is a superset. |
| `feat/feedback-liked-trades-waiting` | 2 | 2026-05-21 / 407 | DELETE | "Awaiting them" feature fully on main (PR #55) and grown since. Caution: branch's query ordering (`created_at`) was later corrected on main (`matched_at`) — reapplying would regress. |
| `feat/feedback-backend-sync` | 2 | 2026-05-20 / 423 | DELETE | Origin of `/api/feedback` (PR #43 `e9467b1`); table, `save_feedback`, route, and mobile retry sweep all on main with admin/status/mine built on top. |
| `claude/leaderboards-phase4-5` | 2 | 2026-04-27 / 455 | DELETE | Leaderboards shipped: route `server.py:5608`, `load_leaderboard` `database.py:2772`, `LeaderboardsSection.tsx`, and all PR-review SQL-pushdown helpers on main; main added ContrarianLeaderboard on top. |
| `feat/wave2-init07` | 2 | 2026-06-07 / 394 | DELETE | Merged as PR #71 (confirmed by main's own `docs/plans/perf-optimization/status.md`); persisted query cache + format-scoped keys all on main, superset (`formatExplicit`). |
| `worktree-agent-ade0db7c` ⚓ | 1 | 2026-04-29 / 449 | DELETE | `_enterMainApp()` on session-restore merged (`app.js:381-399`), comment extended on main. |
| `worktree-agent-ad7046bc` ⚓ | 1 | 2026-04-29 / 449 | DELETE | Emoji-strip superseded by #225 de-chalk pass — strict superset on both server and client. |
| `worktree-agent-ab5ed8ed` ⚓ | 1 | 2026-04-29 / 449 | DELETE | Trends anchor verbatim at `positional-tiers.html:1310`. |
| `worktree-agent-a9b33518` ⚓ | 1 | 2026-04-29 / 449 | DELETE | ELO→Tier column merged (`_eloToTierLabel` `app.js:2078`, `<th>Tier</th>` `index.html:462`). |
| `worktree-agent-a729a704` ⚓ | 1 | 2026-04-29 / 449 | DELETE | Trends-never-loading fix merged, both hunks (`app.js:2919`, `:4968`). |
| `worktree-agent-a651d045` ⚓ | 1 | 2026-04-29 / 449 | DELETE | League-summary in-place switcher merged whole; only drift is de-emoji'd status text. |
| `worktree-agent-a05d00e6` ⚓ | 1 | 2026-04-29 / 449 | DELETE | Leaguemates roster + `/api/league/members` (`server.py:13000`) merged and since hardened (60s cache, `include_self`, error sanitization). |
| `fix/trios-subtab-active-highlight` ⚓ | 1 | 2026-04-29 / 449 | DELETE | Active-class fix at `index.html:252`, ARIA added on top. |
| `fix/trios-remove-info-icon-2026-04-26` ⚓ | 1 | 2026-04-29 / 449 | DELETE | Removal merged, comment carried. (Dead `.gesture-info-btn` CSS lingers on main — cruft, not lost work.) |
| `fix/trios-remove-college` ⚓ | 1 | 2026-04-29 / 449 | DELETE | `p.college` gone from trio tiles; survives only in the info sheet, as intended. |
| `fix/tiers-manual-routing` ⚓ | 1 | 2026-04-29 / 449 | DELETE | `?view=` routing absorbed by main's `_enterMainApp()` refactor (`app.js:387`, `:662-691`), whose comment credits the exact bug. |
| `fix/manual-rankings-remove-kebab-col` ⚓ | 1 | 2026-04-29 / 449 | DELETE | `rt-drag-col` zero hits anywhere on main. |
| `fix/league-summary-include-self-in-joined-count` ⚓ | 1 | 2026-04-29 / 449 | DELETE | `+ 1` both sides + "(including you)" label verbatim at `app.js:5020-5022`. |
| `fix/account-menu-hover-bridge` ⚓ | 1 | 2026-04-29 / 449 | DELETE | `.account-chip::after` bridge verbatim at `styles.css:393-401`. |
| `agent-12-consolidate-skip-button` ⚓ | 1 | 2026-04-29 / 449 | DELETE | `dont-know-btn`/`skipTrio` zero hits on main; single Skip button remains. |
| `feat/picker-select-all` ⚓ | 1 | 2026-04-29 / 449 | DELETE | Select all / Clear all toggle merged incl. label flip (`app.js:3194-3250`). |
| `feat/notifications-clear-button-v2` ⚓ | 1 | 2026-04-29 / 449 | DELETE | `LS_DISMISSED_NOTIFS`, `_visibleNotifs()`, `clearVisibleNotifs()` all on main (`app.js:4630-4802`). |
| `feat/manual-ranking-up-down-arrows` ⚓ | 1 | 2026-04-29 / 449 | DELETE | Move-column markup and handlers byte-identical on main (`app.js:2111-2144`). |
| `feat/mobile-parity-plan` | 1 | 2026-05-20 / 426 | DELETE | Docs-only strict subset of the parity branch; both docs on main under `docs/plans/mobile-feature-parity/` (plan.md byte-identical). |
| `feat/mobile-b1-manual-rankings-and-copy-tiers` ⚓ | 1 | 2026-05-20 / 426 | DELETE | In PR #40 squash; ManualRanksScreen + `copyTiersFromFormat` on main, extended (`via` param, TradesScreen reuse). |
| `feat/mobile-b2-trends-screen` ⚓ | 1 | 2026-05-20 / 426 | DELETE | In PR #40; TrendsScreen/TrendBar on main, APIs reused by TiersScreen and MarketPulseStrip. |
| `feat/mobile-b3-portfolio-and-multi-league` ⚓ | 1 | 2026-05-20 / 426 | DELETE | In PR #40; PortfolioScreen on main; inline switcher superseded by `LeagueSwitcherSheet` + `LeaguePickerScreen`. |
| `feat/mobile-b4-trade-card-improvements` ⚓ | 1 | 2026-05-20 / 426 | DELETE | In PR #40; `human_explanations` + `real_opponent` live; `equalOnly` deliberately removed by PR #54 (slider→toggle). |
| `feat/mobile-b5-trade-queue` ⚓ | 1 | 2026-05-20 / 426 | DELETE | In PR #40; `useTradeQueue` + `QueueChip` + `trades.queue_2k` flag on main with the branch's comments preserved. |
| `feat/mobile-b6-rookie-draft-board` ⚓ | 1 | 2026-05-20 / 426 | DELETE | In PR #40; RookieDraftBoardSheet on main (relocated to LeagueScreen by #83); Aug rookie-draft program supersedes the rest. |
| `feat/mobile-b7-league-surfaces` ⚓ | 1 | 2026-05-20 / 426 | DELETE | In PR #40; all four surfaces + literal "(B7 — flag …)" section headers on main. |
| `feat/mobile-b8-growth-loop` ⚓ | 1 | 2026-05-20 / 426 | DELETE | In PR #40; ProfileScreen, demo session, landing flags, deep links on main; referral capture hardened since (`consumeInvitedBy` dual-path). |
| `feat/feedback-backend-sync-plan` | 1 | 2026-05-20 / 423 | DELETE | 216-line plan doc byte-identical on main at `docs/plans/feedback-backend-sync/plan.md` (renamed by `2e9d542`). |
| `feat/fb4-trades-gate` ⚓ | 1 | 2026-06-19 / 358 | DELETE | FormatGate on main with identical props/call-site; diff is the deliberate Chalkline redesign. Cherry-picking would reintroduce the banned indigo CTA. Worktree: `fb4-trades`. |
| `feat/fb4-tiers-polish` ⚓ | 1 | 2026-06-19 / 358 | DELETE | TileStats/TierStickyHeader/TierTargetChips all on main as strict evolutions (+70–110 lines each); PRDs on main too. Worktree: `fb4-tiers`. |
| `claude/stoic-mccarthy-e56da9` | 1 | 2026-07-03 / 369 | DELETE | Depth-tier color fix targets a token deleted by the `920a638` 8-tier ladder migration; nothing left to apply. (Same topic as stale PR #91 — close that too.) |
| `claude/sentry-phase3` | 1 | 2026-04-27 / 454 | DELETE | Sentry wrapper + pinned SDK on main; main completed the branch's own TODO list (real DSN, Expo plugin, `sentry.properties`). Branch's placeholder DSN would regress. |

---

## 2. Recovery plans (ordered by value)

### 2.1 `teardown-remediation` → the `hasToken` query gates (highest value — production 401 fix, half-wired)

- **What:** from `30492ac`, only the `enabled: hasToken` (and matching `useSession`
  selector) additions to the six screens: `RankScreen.tsx`, `TiersScreen.tsx`,
  `QuickRankScreen.tsx`, `QuickSetTiersScreen.tsx`, `ManualRanksScreen.tsx`,
  `PickAnchorScreen.tsx`. Do **not** take the rest of the commit (verified already on
  main via other routes).
- **Onto:** a fresh branch from `origin/main`.
- **How:** hand-apply per screen (the six files have drifted since 2026-08-06, so a
  straight `git cherry-pick 30492ac` will drag in the already-landed 90% and conflict).
  Extract each screen's hunk with `git show 30492ac -- mobile/src/screens/<f>.tsx`
  and re-apply just the `hasToken` gate lines.
- **Conflicts to expect:** minor context drift in the six screens' `useQuery` options;
  the pattern to replicate is exactly what `RootNav.tsx:251` already does on main.
- **Also from this branch:** `git checkout 969f454 -- docs/feedback/items/207-rookie-draft-detection/`
  lands the three #207 docs verbatim (docs-only, no conflict risk).
- **Note:** this branch is the primary checkout's current branch; after recovery,
  switch the checkout off it before deleting.

### 2.2 `mobile/yellow-followups` → push-permission-status feature

- **What:** from `f6732ce8`, item 2b only — `permissionStatus` slice in
  `mobile/src/state/useNotifications.ts` + the permission-denied banner in
  `LeagueScreen.tsx` with `Linking.openSettings()`; plus **all of** `f7aa9775`
  (AppState-foreground re-read of `getPermissionsAsync()` in
  `mobile/src/hooks/usePushNotifications.ts`). The two must land together — the second
  exists to keep the first fresh.
- **Onto:** fresh branch from `origin/main`.
- **How:** re-implement rather than cherry-pick — `LeagueScreen.tsx` has been
  Chalkline-reskinned since April, and the April banner styling would violate the
  design system. Treat the branch as a spec (and drop the 🔕 emoji per current
  UI rules / the #225 de-chalk convention). `useNotifications.ts` and
  `usePushNotifications.ts` hunks may apply nearly clean.
- **Conflicts to expect:** heavy in `LeagueScreen.tsx` (rewrite, don't merge);
  trivial elsewhere.

### 2.3 `chalkline-primitives` → two primitives + two prop extensions

- **What:** `SegmentedTabs.tsx` and `Spinner.tsx` (net-new files under
  `mobile/src/components/chalkline/`), plus additive props `Card.onPress`
  (Pressable wrapper) and `Badge` `icon`/`mono`/`dim`.
- **Onto:** fresh branch from `origin/main`.
- **How:** `git checkout 794c296 -- mobile/src/components/chalkline/SegmentedTabs.tsx mobile/src/components/chalkline/Spinner.tsx`,
  then export them from `chalkline/index.ts`; hand-apply the `Card`/`Badge` prop
  additions on top of main's current versions.
- **Do NOT** merge or cherry-pick the whole commit: it would revert Button's three
  feature-flag behaviors (`a11y.text_scaling`, `ux.touch_polish`,
  `visual.chalkline_cleanup`), `testID`s, and `Card.padding`, and its 24 screen
  migrations are stale. Review the two new files against `docs/design/components.md`
  before wiring them anywhere — they predate the teardown-S2 flag conventions.

---

## 3. ASK items — decisions needed from the operator

1. **`claude/loving-wright-c2e9e2` (SwiftUI `DTF/` client, 54 files, ~5.6k lines).**
   The only copy of the abandoned SwiftUI pivot. Archive it (a tag like
   `archive/dtf-swiftui-spike` costs nothing and keeps the ref-reachable history) or
   drop it outright? Either way, never rebase/merge it — commit `a587456` deletes all
   of `mobile/`.
2. **`audit/perf-optimization` + `feat/wave1-perf` (the Q2 question).** Main's own
   `docs/plans/perf-optimization/artifacts/questions-for-user.md` Q2 already asks
   whether to merge the 38-file audit-docs commit (`71ed60b`) to main; documented
   default is "leave on branch". Since Wave 3 initiatives (INIT-08/10/11b/16) remain
   open and their requirement files live only in this commit, recommending: merge the
   docs (docs-only, no code risk), then delete both branches. If Q2 is answered
   "leave", the branches must be kept (deleting them orphans the docs).
3. Not a branch decision, but surfaced twice by this triage: **PR #91** (Depth tier
   color) targets a token deleted by the 8-tier ladder migration — close it.

---

## 4. Summary

Of the 50 branches holding commits content-absent from `origin/main`, **44 are DELETE**
(squash-merge residue or deliberately superseded work — four squash commits account for
most of it), **3 are ASK** (the abandoned SwiftUI `DTF/` spike, and the perf-audit docs
pair whose fate is literally an already-written open question, Q2), and **3 are
RECOVER**. The single highest-value find is on the already-triaged
`teardown-remediation`: the `enabled: hasToken` query gates for six mobile screens — a
production 401 fix that shipped its producer half but none of its consumers, meaning
dead sessions still fire doomed requests today. Second: the never-shipped
push-permission-denied banner (`mobile/yellow-followups`), a real user-facing gap for
anyone who declined push. Third: two Chalkline primitives (`SegmentedTabs`, `Spinner`)
that exist nowhere on main. 31 branches are pinned by worktrees and need
`git worktree remove` before deletion; `teardown-remediation` is the primary checkout's
own branch and needs a branch switch instead.

*Method note for future triages: `git cherry` was a candidate filter only; every verdict
above rests on per-file content comparison against `origin/main` blobs. The fast
dispositive check, when it applies: an on-main squash commit whose diff equals
`git diff <merge-base>..<branch>` settles a whole branch at once (worked for PR #13 and
PR #40, i.e. 29 of the 50 branches' commits).*

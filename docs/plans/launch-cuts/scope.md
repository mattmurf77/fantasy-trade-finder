# Feature Scope — Launch cuts (owner keep/cut calls, 2026-11-25)

**Date:** 2026-11-25
**Entry point:** direct ask. The owner gave a keep / cut call on each of the 62 rows the launch feature audit (2026-11-21) recommended cutting: 22 keep, 36 cut, 4 undecided (the paywall rows, untouched). This change applies the 36 cuts.
**Builder:** main session with three builder subagents (flags + backend, mobile, web)
**Operator sign-off on waivers:** the analytics waiver below is surfaced in the PR; no other waiver.

---

## What is cut

| Area | Cut | How |
|---|---|---|
| Calibration tab | for users; kept for tester-allowlisted accounts | `grading.blind` off, allowlist check in `_calibration_allowed`, `calibration_rollout` overlay in the new `operator` layer |
| Rank | Trends, Pick Anchors, rookie ranks and scope control | chooser rows, Settings stop, saved preference and deep links closed; `ranks.rookie_subset` off (code stays, wanted back in the offseason) |
| Home | "Check trends" tile | removed |
| Acquire | Draft chip, Team Review card and flow | `draft.room`, `trades.team_review` off |
| League | "Redraft (soon)" chip, Season outlook, Rookie draft and Rookie board tiles, Market pulse | chip removed; `outlook.odds`, `draft.room`, `league.rookie_board_entry`, `market.movers` off |
| Draft family | Draft Room, live polling, MFL board, slot prices, rank from the board, mock draft, record picks | seven `draft.*` / `picks.slot_values` flags off; an old link shows a closed state |
| Free agents | the Add sheet, until real adds work (the list stays) | Add shows only where the server's `move` capability can submit that row |
| Website | sign-in and every page behind it | landing is marketing-only; four standalone pages 302 to `/` |
| Extension | distribution | download links and wording removed from the site; `extension/` untouched |
| AI matchup selection | stays off | no change (off while `ANTHROPIC_API_KEY` is unset) |

## 1. Analytics scope

- [x] **(c) WAIVED — no new analytics.** Nothing is added. One loss to know about: the website no longer loads `events.js`, so `app_opened` with `launch_type: web` and the web capture of invite `?ref=` / `?league=` stop. No taxonomy change.

## 2. Schema & flag scope

- New/changed tables or columns: none. `experiment_layers` gains one seeded row (`operator`) at boot through the existing `_seed_experiment_layers()`; no migration.
- New/changed feature flags: no new flag. Thirteen defaults go to `false` in `config/features.json` and the three mirrored fixtures: `grading.blind`, `ranks.rookie_subset`, `draft.room`, `league.rookie_board_entry`, `draft.live_poll`, `draft.mfl`, `picks.slot_values`, `draft.rank_inline`, `draft.mock`, `draft.manual_picks`, `trades.team_review`, `outlook.odds`, `market.movers`. Graduation: each returns by flipping it back; rookie ranks is expected back in the offseason.
- New env vars / `model_config` keys: none. Rollback lever: an `FTF_FLAGS` override plus `POST /api/feature-flags/reload` restores any flag without a deploy.

## 3. Evidence scope

- [x] **Structural guard:** new `mobile/tests/check-launch-cuts.js` (closed Trends / Pick Anchors doors, Draft Room closed state, ESPN pick assignment independent of draft flags, Team Review's single gated entry); `check-fa-move` F2 and `check-usage-trends` 2i (Add rule); `check-monetization-cut-features` (deny-list realigned); `check-playoff-odds-display` B2 (script order on any page that loads the callers).
- [x] **Unit tests:** `test_calibration_tester_overlay.py` (12), `test_cut_web_pages.py`, `test_draft_board.py` (platform stamp), plus the fixtures that pin the old posture.
- [x] **Web checks:** `qa/web/check_web_structure.py` (new `CUT` group), `qa/web/check_ranking_method_page.py`.
- [x] **Runtime:** simulator pass on a local test server, recorded in TEST_LEDGER (2026-11-25).
- [x] **Manual TestFlight checklist** (owner, after the next build):
  1. Force-quit and reopen twice. The Calibration tab is there for the owner's account and Founders' review opens.
  2. On a second, non-tester account: no Calibration tab.
  3. Home shows no "Check trends" tile; Usage Rates and Search free agents are there.
  4. Rank › More ways to rank lists only Overall ranks. Settings › ranking method has four stops.
  5. Acquire has no Draft chip and no Team Review card. Win Now still opens.
  6. Free agents lists players with no Add button.
  7. League rankings has no "Redraft (soon)" chip; League home has no Rookie draft tile and no Market pulse strip.
- `testID`s added/renamed: the Draft Room closed-state ids (testid-lint passes).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | grading gate, `/api/admin/experiments` (layer list, new 400), `/api/sleeper/leagues` (`platform`), the cut-page redirect |
| `living-memory/LLD.md` | n/a | no convention shifted |
| `docs/architecture.md` | n/a | no module wiring changed |
| `living-memory/HLD.md` | n/a | the website losing its app shell is recorded in D-284 and `web/CLAUDE.md`; no new module or client |
| `docs/cross-client-invariants.md` | n/a | no shared constant changed |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` entry | updated | D-284 |

Also updated: `docs/runbook.md` (Calibration posture), `docs/config-reference.md`, `docs/data-dictionary.md`, `docs/plans/blind-grading/lld.md` §8.2, `docs/plans/ram-mascot/experiment.md` §8, `web/CLAUDE.md`, the mobile CLAUDE.md maps.

## 5. Ship gate declaration

- **CI green:** required on the pushed sha before merge.
- **Evidence recorded:** TEST_LEDGER 2026-11-25.
- **TestFlight verification:** the checklist in §3, by the owner, after the next build.
- Express lane declared by the operator? No.

## Not done here

- Legal wording that the web cut makes untrue (`terms.html` §14.1 and others) is listed for the owner and not edited.
- The `calibration_rollout` overlay is an operator action after deploy; until it is launched Calibration is off for everyone.
- Draft PR 456 (web release flip) needs a rebase onto this.

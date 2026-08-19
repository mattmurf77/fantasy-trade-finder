# screens/ — the screen library (FROZEN 2026-08-11)

> **This tree is frozen and no longer being refreshed.** Operator decision **D-056**
> (2026-08-15, Active — `living-memory/DECISIONS.md`) retired Maestro and the simulator
> entirely, including screen captures, for any change in any pipeline. `manifest.json` was
> last generated **2026-08-11**; the newest captures are 2026-08-10/11.
>
> **What that means in practice:**
> - Every PNG here is a true capture of the app **as of 2026-08-11** — still exact ground truth for that build, still far better than a redrawn approximation.
> - Any screen changed after 2026-08-11 is **not** reflected here, and there is no process to make it so. Check `git log` on the screen's source before trusting a capture as current.
> - **Do not request or attempt a capture run.** `mobile/scripts/screen-capture.sh` and `screen-freshness.sh` still exist and still work; running them is out of policy. Say the library is frozen instead.
> - Never hand-edit PNGs or `manifest.json` to fake freshness.

## Layout

- `mobile/<screen>/<state>.png` — screen dirs use the testID prefixes
  (`signin`, `trades`, `tiers`, …); state names: `idle | loading | empty |
  error | populated | busy | done` + `--modifier` variants (`loading--slow`).
- `mobile/sheets-<sheet>/` — modal surfaces, same flat level with a `sheets-`
  prefix (`sheets-rank-menu`, `sheets-trade-dna`, …), not a nested `sheets/` dir.
- `manifest.json` — per capture: flow, profile, injections, captured_at; per
  screen: source files + `source_sha256` (the freshness anchor); global: app sha + device.
- Captures were taken hermetically from the real app on the canonical simulator
  (FTF-iOS18, iOS 18.4, dark mode — the app is dark-only).

## Index — 32 screen dirs, 141 captures

Directory → the app surface it captured. **`manifest.json` is the authority** on which
states exist and when each was taken; this table is the name→surface map.

| Dir | Primary source | Dir | Primary source |
|---|---|---|---|
| `anchors` | `PickAnchorScreen.tsx` | `pick-assignment` | `PickAssignmentScreen.tsx` |
| `calc` | `TradeCalculatorScreen.tsx` | `portfolio` | `PortfolioScreen.tsx` |
| `draft-room` | `DraftRoomScreen.tsx` | `profile` | `ProfileScreen.tsx` |
| `feedback-inbox` | `FeedbackInboxScreen.tsx` | `quick-rank` | `QuickRankScreen.tsx` |
| `free-agents` | `FreeAgentsScreen.tsx` | `quick-set` | `QuickSetTiersScreen.tsx` |
| `league` | `LeagueScreen.tsx` | `rank-home` | `RankHomeScreen.tsx` |
| `league-summary` | `LeagueSummaryScreen.tsx` | `record-picks` | `RecordPicksScreen.tsx` |
| `leagues` | `LeaguePickerScreen.tsx` | `rookie-ranks` | `RookieRanksScreen.tsx` |
| `manual-ranks` | `ManualRanksScreen.tsx` | `settings` | `SettingsScreen.tsx` |
| `matches` | `MatchesScreen.tsx` | `signin` | `SignInScreen.tsx` |
| `mock-draft` | `MockDraftScreen.tsx` | `tiers` | `TiersScreen.tsx` |
| `onboarding` | `OnboardingScreen.tsx` | `trades` | `TradesScreen.tsx` |
| `topbar` | `TopBar.tsx` | `trends` | `TrendsScreen.tsx` |
| | | `trios` | `RankScreen.tsx` |

Modal surfaces (`sheets-` prefix): `sheets-espn-link` (`EspnLinkSheet.tsx`),
`sheets-feedback` (`FeedbackSheet.tsx`), `sheets-league-switcher`
(`LeagueSwitcherSheet.tsx`), `sheets-rank-menu` (`TabNav.tsx` RankMenu),
`sheets-trade-dna` (`TradeDnaSheet.tsx`).

`screens/web/` is empty and reserved — see [`web/README.md`](web/README.md).

**Coverage was never total.** Some surfaces were unreachable from a hermetic capture flow
and are absent by design (live WebViews such as SleeperConnect/EspnConnect can't be
reproduced); others were absent only until a flow or a feature flag landed. Post-freeze,
every one of those gaps is permanent. Check `manifest.json` before assuming an absence was
deliberate — but either way, the answer now is "not captured", not "request a capture".

## For mockup agents (load-bearing — see feedback lessons #256/#257)

Before designing any change to screen X, **open every PNG under `mobile/<x>/`**. A mockup's
"current" pane embeds the actual capture via
`<img src="../../screens/mobile/<x>/<state>.png">` — never redraw "current" from memory or
from reading source alone.

**The freeze creates a real conflict here.** For a screen changed after 2026-08-11, or one
that never had a capture, the embed rule cannot be satisfied and a capture cannot be
requested. In that case: say so explicitly in the deliverable, state which source files
changed since the capture, and reconstruct from source with the reconstruction labelled as
such on the page — the way `mockups/candidates-300/` already does. Never present a
reconstruction as a capture. Full mockup-side rule and the exact relative depth:
[`mockups/CLAUDE.md`](../mockups/CLAUDE.md).

## For the operator

Extraction is a plain folder copy: `cp -R screens/ ~/Desktop/` or drag in Finder — ordinary
PNGs, no LFS, no build step.

## Tooling (present, out of policy to run)

`mobile/scripts/screen-capture.sh` (writer) and `mobile/scripts/screen-freshness.sh`
(compares each screen's source hash vs the manifest) are still in the tree and still
functional. They are kept the way `mobile/.maestro/` flows are kept — as a record of how
the library was built, not as a live workflow. Reviving either is an operator decision that
would have to reverse D-056.

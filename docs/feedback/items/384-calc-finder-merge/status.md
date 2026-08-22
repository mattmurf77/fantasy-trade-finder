# Status — #384 Manual calculator becomes the merged trade surface

**Status:** **BUILT DARK** — all five waves on `feat/calc-finder-merge`, `calc.merged_layout` **false**, not merged, not pushed. TestFlight checklist UNRUN.
**Date:** 2026-08-22
**Covered feedback IDs:** #384 canonical. Folds in **#310** (don't lock the manual calc behind trades; simplify nav), **#379** (filters back in-page, minimized default), **#380** (clicking a partner minimizes that section and raises the calculator). Touches **#333** (league/team as side-by-side dropdowns under the fold).
**Reported:** `mattmurf77`, screen `TradesHome`, v1.15.0, filed 2026-08-22T03:04Z
**Filed severity:** `bug` — **it is a feature/IA spec**; treat as such.

> **This report is the one the 2000-char cap ate.** Written 03:04Z, delivered 04:26Z after the
> cap raise ([D-149](../../../living-memory/DECISIONS.md), [G-055](../../../living-memory/GOTCHAS.md)).
> 2,803 characters — it would have been lost permanently under the old limit.

---

## Scope, per the operator

**Only the manual calculator page changes.** The Find a Trade page is left alone this round.
*"Eventually will replace it. For now we're leaving that page alone and just editing the manual
calc page."* The eventual merge of the two surfaces is the direction; this is the test of it.

## Operator rulings — 2026-08-22, in answer to the report's own step 13

The report asked to be prompted on any Find a Trade controls its tour missed. Ten were found.
All ten were ruled on:

| # | Control found | Ruling |
|---|---|---|
| 1 | `feedback.decline_reasons` is **on** — the ✕ is *replaced* by three inline tiles (Value · Fit · Neither) | **✕ stays a single button.** Tapping it **pops the decline reasons as an overlay over the page**. This is a presentation change from the shipped inline-tile form |
| 2 | Three send buttons exist (`trades.send-sleeper-btn` / `-espn-btn` / `-mfl-btn`) | **Show the one that matches the user's league platform.** The tour names that platform, not Sleeper unconditionally |
| 3 | `trade-card.edit-in-calc` already bridges deck → calculator | Left alone; superseded eventually by the merge |
| 4 | `trade-card.remove-asset.<id>` is distinct from swap | **Both removal and add-a-player are explicit buttons** on the page |
| 5 | Untouchable/lock via long-press (`trade.preference_lists` on) | Covered by the end-of-deck ruling below |
| 6 | The utility row carries six entries (conditions · draft · free agents · manual calc · today's trade · track record) | **Hidden on this page for now** |
| 7 | Subnav is three tabs (Trades · Portfolio · Calculator) | **Does not exist.** The report's own step 2 "tabs" are a NEW two-way in-league/manual control, not this |
| 8 | End of deck is a summary state (See liked · Done · Pin), not an automatic next card | **Add a "back to calculator" button.** If the user had a player locked/pinned, **also offer "find a trade without that player pinned"** |
| 9 | `trades.package-toggle` and `trades.fairness-help` unexplained | **Add both to the tour** |
| 10 | Interstitials can interrupt (quick-set prompt, outlook receipt, banners) | **Mute all other interstitials and analyst prompts for the duration of the scripted tour** |

**Also settled:** the Sleeper password claim in tour step 14 is accurate as written — operator
confirmed, no verification needed. The report's step numbering starting at 2 was a typo, not a
missing beat.

## One reading I had to make — flag if wrong

Rulings 6 and 7 both arrived as short lines ("For now that tab view is hidden on this page" /
"The tab subnav doesn't exist"). I read them as: **the six-entry utility row is hidden on this
page**, and **the three-tab Trades/Portfolio/Calculator subnav is gone entirely**. Both point the
same way — neither appears on the new page — so the plan is written to that reading. If "that tab
view" meant something else, the layout section is the part to correct.

## Where the plan is

[`plan.md`](plan.md) — layout spec, the tour as authorable guide steps, and the four things that
need a decision before a build agent starts.

## Round-2 rulings — 2026-08-22, answering plan §5

| # | Ruling |
|---|---|
| 1 | ✕ → decline-reason overlay applies to **this calculator only**; the deck keeps its inline tiles |
| 2 | **Include Players ON ⇒ the search must include the players on the canvas**; OFF ⇒ unconstrained by the canvas |
| 3 | The new surface **replaces the manual calc tab and lives within the league calc**. **Remove the demo calculator** — "it's pointless" |
| 4 | Tour is **re-runnable** via a **"Show me around"** link, **top right** of the page |
| + | The tour **auto-starts on landing** on the manual calc page, since its first beat carries the user to the league version |

**Two things surfaced by ruling 3, both recorded in [`plan.md`](plan.md) §6:**

1. **"Demo" is two systems.** The demo *calculator mode* (mock dual-board league) is the one being
   deleted. The demo *session* (`/api/session/demo`, try-before-signin, `onboarding.demo_bridge`)
   must not be touched — they share only a word.
2. **Ruling 3 collides with #310 and with the tour's own first step.** `TradesScreen.tsx:4944`
   records the current intent — *"Calculator … is always reachable — it needs no league"* — and
   #310 is the report that asked for it. The plan proceeds on a stated assumption (two tabs,
   `Manual` | `In league`, demo deleted, rich spec on the league side) which needs a yes/no.


## Build record — 2026-08-22, waves W0–W4

| Wave | Commit | What |
|---|---|---|
| W0 | `224a830` | Demo CALCULATOR removed (net −239 lines). Demo SESSION untouched — verified by empty `git diff` over its five files |
| W1 | `dfcd532` | Merged layout behind `calc.merged_layout` (OFF): outlook beat, league/team dropdowns, two columns, the 40/30/15/15 action row |
| W2 | `56111a0` | ✕→overlay reasons, end-of-deck exits, include-players via the finder pin store. Send button: **already platform-aware, no code** |
| W3 | `4ff15f3` | Tour-long hold on the EXISTING prompt arbiter (it already existed — the plan overpriced this) |
| W4 | `ae605ad` | 15 tour beats compressed to the CI copy budget + `utils/calcTour.ts` runner + both entry points |

**Gates, every wave:** pytest 4117 passed / 1 skipped · `tsc --noEmit` clean · testid-lint OK ·
structural suites 71 → **76**. Four new guards, all red-proofed: `check-demo-calc-removed`,
`check-calc-merged-layout`, `check-calc-merged-behavior`, `check-tour-suppression`,
`check-calc-tour`.

**Five dead assertions found and fixed while red-proofing** — in my own guards, not in the
product: two substring anchors that survived their own sabotage (`/isDemo/` matched
`isDemoRenamed`, `/onDemo/` matched `onDemoStarted`), a backwards proximity search for the
flag gate that passed when the gate it should have been reading was replaced, a fixed-size
window that read the next JSX prop's body, and a drift detector that threw instead of failing
a named assertion.

**Two things the build corrected in the plan:**
- W3 was priced as "build a suppression gate across six surfaces". `useInterruptCoordinator`
  already was that gate, live behind `ux.prompt_arbiter`. The real gap was narrower and more
  interesting: the slot frees BETWEEN steps, so a tour needs a hold, not a per-step claim.
- The send-button ruling needed no code at all — `resolveSendPlatform` already routes
  Sleeper/MFL/ESPN.

**Pre-existing defect reported, not absorbed:** `InLeagueCalculator.lineupHeadText` is
`fontSize: 10`, under the Chalkline 11pt floor, on `origin/main` since #297. Not introduced
here and not fixed here.

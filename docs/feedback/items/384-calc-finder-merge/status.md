# Status — #384 Manual calculator becomes the merged trade surface

**Status:** `planned` — rulings captured, plan drafted, **not built**
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

# Manual TestFlight checklist — #369, the plan beat

**Date:** 2026-08-20 · Operator to run · outcome → `living-memory/TEST_LEDGER.md`

**Requires a new build.** This is mobile code; it is not in build 122 or any
existing TestFlight build. `trades.team_review` is already lit, so no flag flip
is needed — but nothing below is visible until the client ships.

Under D-056 this is the only runtime evidence this change gets. Steps 2, 3 and 7
are the ones that catch a regression a static check cannot see; do not skip them.

**Setup:** a Sleeper dynasty league you manage. Trades tab → the Team Review
entry card on TradesHome.

---

| # | Do this | Expect |
|---|---|---|
| 1 | Open Team Review. Tap **Skip this** on every beat until you reach the last one. | The final beat shows three cards — "What the finder uses", "Player rules", "This search" — **not** an empty "Your plan" card and not "You skipped every step". This is the reported bug: skipping used to leave the page blank. |
| 2 | On that beat, read the Window / Chasing / Shopping selections. Now background the app, open Trades → the deck's outlook receipt → **Change** (the Trade DNA sheet), and compare. | Identical. Same outlook selected, same Chasing and Shopping positions — including **Picks** if you have it set. If Team Review shows fewer positions than the DNA sheet, the beat is reading the stale payload snapshot instead of the saved prefs. |
| 3 | Restart the flow. On the **depth** beat, change a Chasing position and tap **Save & continue**. Continue to the last beat. | The last beat shows the position you just picked. Before this change the depth beat's save returned a 400 and was silently swallowed, so it never appeared — this step is the direct proof of the fix. |
| 4 | On the last beat, tap a different **Window** chip. | It highlights immediately; no error line appears. Back out to Trades, open the DNA sheet: the new outlook is selected there too. |
| 5 | On the last beat, tap **Picks** under Chasing, then tap it again to clear. | Toggles on and off. Re-open the DNA sheet after each: the Picks toggle matches. |
| 6 | Turn on airplane mode. On the last beat, tap any Window or position chip. | A single line in `--neg` red: *"That didn't save. Tap it again — your other settings are untouched."* The flow does **not** get stuck and the other cards still render. Turn airplane mode off, tap again — the line clears. |
| 7 | Restart the flow, go to the **partners** beat, tap a manager, continue to the last beat, confirm "Trade with" shows their name, then tap **Find my trades**. | The deck opens **scoped to that manager** — the "Trading with" strip names them — and a search runs on its own. Before this change the scope was recorded and then dropped, so you landed on an unscoped deck. |
| 8 | Repeat step 7 but **do not** scope anyone on the partners beat. | "Trade with" reads *"Anyone in the league"*, and **Find my trades** lands on a normal unscoped deck with no auto-run. (Guards against the handoff firing when nothing was chosen.) |
| 9 | On the last beat, check the **Player rules** card against reality: lock a player as untouchable from a trade card in the deck, then re-enter Team Review and skip to the end. | The "Never trade away" count includes them. A count that is loading shows `—`; a genuine zero shows `None`. It must never show `0 players` while still loading. |

**Also confirm, on any screen of the flow:** exactly **one** feedback button is
visible (the global one from RootNav). Two means the #196/#197 double-FAB bug is
back — `check-team-review.js` assertion 2 should have caught it, but this is the
cheap visual confirmation.

**Non-Sleeper / preseason leagues:** if you have an ESPN or MFL league handy, run
steps 1, 2 and 4 there too. The plan beat has no platform dependency — it reads
preferences, not scores — so it must render fully even where the standing beat's
PPG card says it cannot read weekly scores.

# Manual TestFlight checklist — feedback #355, phantom draft-pick years

D-056 retired the simulator, so this is the only runtime evidence this change gets. It matters here
because the user-visible outcome is produced by a **background sync against live Sleeper data**,
which the unit tests necessarily stub.

**Build:** first TestFlight build off `fix/pick-horizon` (or the release that carries it).
**Precondition:** `picks.league_horizon = true` in the deployed `config/features.json`.

Two leagues are needed, because the whole point of the rule is that the window rolls. League A is
the operator's own; league B must be one whose 2026 rookie draft is `complete`.

* **League A — pre-draft:** `1312140920132497408` (2026 draft `pre_draft`). Expected classes: 2026, 2027, 2028.
* **League B — post-draft:** e.g. `1312583962966650880` (2026 draft `complete`). Expected classes: 2027, 2028, 2029.

| # | Step | Expected result | Pass? |
|---|---|---|---|
| 1 | Launch the app on League A and let session-init finish (pull-to-refresh on TradesHome once). | App loads normally; no error banner. The sync must run, or steps 2-5 prove nothing. | |
| 2 | Open **League Summary → draft capital / picks list** for League A. | Pick years shown are **2026, 2027, 2028 only**. **No 2029 pick appears anywhere.** | |
| 3 | On TradesHome, swipe through **at least 25** cards on League A, reading every pick chip. | Every pick names 2026, 2027 or 2028. A single 2029 pick is a FAIL — record the card. | |
| 4 | Open the **Trade Calculator** on League A and open the pick picker for your own team and for one opponent. | The selectable pick list offers 2026-2028 only; no 2029 row. | |
| 5 | On a card that includes a pick, tap through to detail and open **Send in Sleeper**. | The proposal builds and Sleeper accepts the asset — i.e. the offered pick is one that really exists. Cancel rather than sending, if preferred. | |
| 6 | Switch to **League B** (post-draft) and let session-init finish. | — | |
| 7 | Open League Summary → picks for League B. | Pick years are **2027, 2028, 2029**. **2029 IS present** — its absence is a FAIL, and a different bug from the one being fixed (the window failed to roll). | |
| 8 | Swipe ~15 cards on League B. | Picks named are 2027-2029; **no 2026** pick appears (that class was already drafted). | |
| 9 | Regression check — League A, **power rankings / league rankings** chart. | Draft-capital bars still render and are non-zero for every team. A team dropping to zero pick value would mean the horizon filter removed too much. | |
| 10 | Regression check — the trade calculator's one-tap **evener / sweetener** suggestions on League A. | Pick sweeteners are still offered (just never 2029). An empty evener list is a FAIL. | |

**If any row fails:** set `picks.league_horizon = false` and `POST /api/feature-flags/reload`. No
deploy is needed, and because the sync is a replace-sync the previous grid rebuilds on the next
session-init.

**Log the outcome** in `living-memory/TEST_LEDGER.md` against the #355 entry.

# Code-walk proof — feedback #355, phantom draft-pick years

D-056 retired the simulator, so this file is the runtime-behaviour proof: a file:line trace from
the operator's screen back to the line that invented the asset, and forward again to show the fix
closes it. Line numbers are on branch `fix/pick-horizon`.

## 1. What the operator saw

A TradesHome card offering a **2029** pick in Sleeper league `1312140920132497408`. That league's
2026 rookie draft has not been held (`pre_draft`), and Sleeper does not carry a 2029 class for it —
so the offer was unactionable: the user could accept the card and then find no such asset to send.

## 2. The trace, screen → source

The pick is a real row in `draft_picks`, not a rendering artifact. Walking backwards:

| # | Site | What it does |
|---|---|---|
| 1 | `backend/server.py:10132` `_owned_pick_assets` | Builds the PICK pseudo-assets for the deck. |
| 2 | `backend/server.py:10169` | `for p in load_draft_picks(league_id=…, source=_pick_read_source())` — reads **every** pick row for the league. |
| 3 | `backend/server.py:10182` | The only rejection in the whole function is `if pool_v <= 0: continue`. |
| 4 | `backend/database.py:9455` `load_draft_picks` | `select(draft_picks_table).where(league_id == …)`; `season` appears **only** in `order_by` (`database.py:9494`). |
| 5 | `backend/server.py:10261-10270` `_inject_owned_picks` | Writes each pick pseudo-`Player` into `trade_service._players` and appends its id onto `user_roster` and every `league.members[*].roster`. |
| 6 | `backend/trade_gen_v2.py:527-560`, `backend/trade_optimizer.py:399-415`, `backend/trade_service.py:4931-4959` | All three engines build their pools **off rosters**. Once step 5 put the pick on a roster, every engine treats it as an ordinary tradeable asset. |

**Conclusion of the backward trace: there is no season filter anywhere in the serving path.** A pick
row that exists is a pick the engine may offer. So the defect cannot be in the read path — the row
should never have existed.

## 3. Where the row was created

`backend/database.py:9275` `sync_draft_picks`, step 1, at the pre-fix line:

```python
for season in range(current_season, current_season + seasons_ahead + 1):
```

with `seasons_ahead = 3` hardcoded by the only Sleeper caller
(`backend/server.py:10448`, inside `_sync_sleeper_owned_picks`). For `current_season = 2026` that
enumerates **2026, 2027, 2028, 2029** — four classes.

The reason this was wrong for only *some* leagues is the interaction with #228. That rule
(`backend/server.py:10430-10439`) puts the current season into `exclude_seasons` when its rookie
draft reads `complete`, and the grid loop skips excluded seasons (`database.py:9363`). So:

* **post-draft league** — 2026 excluded ⇒ grid is 2027/2028/2029 ⇒ **3 classes, correct by accident**.
* **pre-draft league** — nothing excluded ⇒ grid is 2026/2027/2028/2029 ⇒ **4 classes, one phantom**.

That is exactly the split the prod data shows (`evidence.md`): every league whose grid starts at
2027 is fine, and the two leagues whose grid starts at 2026 both carry a phantom 2029.

The correct rule is not a width measured from `current_season`; it is **three consecutive classes
anchored to the first class that has not been drafted**. Verified against the live Sleeper API in
`evidence.md`, including a *positive* reading (a post-draft league that really does have 2029
traded picks) so the rule is pinned at both ends rather than inferred from an absence.

## 4. The fix

**`backend/draft_status.py:92` `pick_horizon(current_season, exclude_seasons, observed_seasons, classes)`**
— a pure, dependency-free function returning the inclusive `[first, last]` class window:

* `backend/draft_status.py:84` — `PICK_HORIZON_CLASSES = 3`, the window width.
* The anchor walks forward past every excluded (already-drafted) class, so the window rolls.
* `observed_seasons` — any season the *platform itself* reported a traded pick for — can widen the
  window, because a reported pick is existence proof. `backend/draft_status.py:89`
  `PICK_HORIZON_MAX_CLASSES = 5` bounds that widening so a malformed feed cannot re-open the defect.

**`backend/database.py:9335-9358`** — step 0 computes the window before the grid is built, gated on
the kill switch (`database.py:9341`, `is_enabled("picks.league_horizon")`), passing the league's
`traded_picks` seasons as the existence proof (`database.py:9349`). Flag OFF restores
`first_season = current_season`, `last_season = current_season + seasons_ahead`
(`database.py:9356-9358`) — the historical window, exactly.

**`backend/database.py:9362`** — the grid loop now runs `range(first_season, last_season + 1)`.

**`backend/database.py:9398`** — the traded-pick overlay floors at `first_season` instead of
`current_season`. Deliberately **no upper bound** here: a pick the platform actually reports is
ground truth, and `pick_horizon` has already widened `last_season` to cover it. (In practice this
line is behaviour-neutral — the very next statement, `database.py:9400`, already skipped excluded
seasons — but it makes the floor read from the same anchor as the grid.)

## 5. Why fixing the writer is sufficient

`sync_draft_picks` finishes with `replace_draft_picks(league_id, rows)`
(`backend/database.py:9432`), which **deletes the league's platform rows and bulk-inserts the new
set** (`backend/database.py:9411`). So the fix is self-healing in both directions:

* existing phantom 2029 rows in prod are deleted on the league's next `session_init` sync — no
  migration, no backfill;
* flipping the kill switch off rebuilds them just as automatically.

And because every serving site reads through `load_draft_picks` (step 2/4 above), removing the row
removes the asset from the deck, the asset-ideas route, the calculator, the evener suggestions and
the power-rankings pick capital simultaneously — which is the reason to fix the writer rather than
add a filter at presentation. A presentation filter would have left the phantom consuming
generation work and distorting every score computed over the pool.

## 6. What was deliberately NOT changed

* **`_owned_pick_label` / pick display (`backend/server.py:9891`)** — owned by the sibling session
  working feedback #356 (real draft slots for current-year picks). Untouched here.
* **MFL (`backend/server.py:10358`)** — enumerates the real `futureDraftPicks` export, so it has no
  phantom to remove. Prod confirms: the one MFL league holds 2027/2028 only.
* **ESPN** — has no platform pick source at all; `git grep` finds no pick fetch in
  `espn_service.py` / `espn_write.py`.
* **`seed_pick_grid` / `_ASSIGNMENT_SEASONS_AHEAD` (`backend/server.py:12202`)** — the manual
  assignment grid. Left alone on purpose; see **Q-022** and D-091's scope note.

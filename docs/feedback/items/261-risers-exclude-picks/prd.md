# #261 — Exclude draft picks from Risers / Fallers

**Report (app v1.11.0, screen LeagueHome, severity bug):** "Draft picks
should be excluded from the 'risers and fallers' section."

## 1. Repro

**Reported surface — League home → Market pulse (`MarketPulseStrip`)**

1. Sign in, land on the League tab (flag `market.movers` on).
2. Below the Explore tiles, the one-line **Market pulse** strip shows the
   top riser + top faller; tap it to open the **Market movers** sheet
   (`market-movers.sheet`) with full **Risers** / **Fallers** columns.
3. A generic draft-pick rung ("Early 1st Round Pick" / the #207
   year-explicit "2026 Early 1st") can occupy a row in either column.

**Second surface with the same defect — Rank → Trends**

1. Rank tab → More ways to rank → **Trends** (`TrendsScreen`).
2. The **Risers and fallers** section (the section whose visible header is
   literally the reporter's phrase) is fed by
   `GET /api/trends/risers-fallers` — the caller's *personal* Elo movement.
3. Because the 12 generic pick rungs are rankable assets that appear in
   trios (they carry a real position so they mix into the position tabs),
   ranking a trio that contains one writes an `elo_history` row for it, and
   the pick shows up as a riser or faller with a position-group badge.

Neither surface is reproducible against the local dev DB
(`data/trade_finder.db` holds a single `player_value_history` snapshot day,
`2026-06-13`, so every mover computes to a flat 0 % and both lists are
empty). The defect is established structurally — see §2 — and by the fact
that the 12 pick rungs *are* present in that table on every snapshot day.

## 2. Root cause

Both lists are computed **server-side**, and neither has any notion of a
draft pick.

**`GET /api/market/movers`** (`backend/server.py`,
`market_movers_route`) walks `player_value_history` (the daily consensus
snapshot written by `_write_daily_value_snapshots`) and enriches each id
from the universal pool:

```python
players, _seed = _get_universal_pool(fmt)
meta = {p.id: p for p in players}
for pid, then_v in then_vals.items():
    ...
```

`_write_daily_value_snapshots` iterates the **whole pool seed**, and the
pool builder appends the 12 generic pick rungs (`generic_pick_<round>_<tier>`,
`team = "PICK"`) into that seed. So picks are snapshotted daily and are
first-class candidates for the movers list. The route's noise guards
(missing-from-pool, junk baseline < 100 value, `pct == 0`) are all
value-shaped; none of them is an asset-class filter.

Today a pick only *sometimes* surfaces, and that is an accident rather than
a design: `GENERIC_PICK_SEEDS` is a static ladder, so as long as nothing
touches the value scale a pick's `consensus_value` is identical on both
snapshot dates and the `pct == 0` guard silently drops it. Anything that
moves the whole scale — a `model_config` retune of `elo_value_base/k/ref`
(`trade_service.elo_to_value` reads them at call time), a rescale migration
like #117's `player_value_history` rewrite, or a future seed recalibration —
gives every rung a non-zero `pct_30d` at once and floods the columns with
picks. The user-visible bug is therefore intermittent by construction; the
missing exclusion is permanent.

**`GET /api/trends/risers-fallers`** (`backend/server.py` →
`trends_service.compute_risers_fallers`) has the same gap with no
accidental mask: it emits a row for every id that has both a current Elo
and in-window `elo_history`, and pick rungs legitimately accrue both.

## 3. Where the fix belongs — and why

**Server, in both endpoints.** Not the clients.

- **Every client benefits.** `MarketPulseStrip` is not the only consumer of
  this data: `web/js/app.js` renders the same Trends risers/fallers lists
  (`trends-risers-list` / `trends-fallers-list`) from the same endpoint. A
  fix in `mobile/` would leave the web client showing picks and would have
  to be re-implemented per client forever.
- **A client-side filter would silently shorten the list.** Both endpoints
  cap at `top_n` *before* serializing. Dropping picks after the response
  arrives yields 8 rows where 10 were asked for; dropping them before the
  cap backfills with the next real player, which is what the reporter
  expects to see.
- **Precedent.** The identical decision was already made server-side for
  the free-agent finder — "#222 — picks are never FAs",
  `backend/free_agent_service.py`, using the same predicate. Consistency
  with that call is worth more than a one-line client patch.
- **Both endpoints, one report.** The reporter tagged LeagueHome, but the
  phrase names a section that exists twice with the same defect. Fixing
  only the strip would leave the section actually *titled* "Risers and
  fallers" still showing picks to the same tester.

### The canonical pick predicate

Not a heuristic — the codebase already has one, `trade_service.is_pick_asset`:

> True for any draft-pick asset in the player maps: owned-pick
> pseudo-players (`position == "PICK"`, injected by
> `server._owned_pick_assets`) and the universal pool's generic picks
> (which carry a REAL position so they mix into the trio tabs, but are
> always `team == "PICK"`).

`backend/free_agent_service.py` and `backend/taste_service.py` both route
through it (taste adds the `generic_pick_` id-prefix arm as a belt-and-braces
third check). Per `docs/cross-client-invariants.md` §"Generic pick-rung
labels are a SERVED STRING", the rung **id** is the stable key and the name
must never be parsed — so the exclusion keys off `position`/`team`/`id`,
never the label.

Applied per endpoint:

| Endpoint | Enrichment shape | Predicate |
|---|---|---|
| `/api/market/movers` | universal-pool `Player` objects | `trade_service.is_pick_asset(p)` directly |
| `/api/trends/risers-fallers` | `{player_id: {name, position, team}}` dicts (`_players_by_id_for`) | a module-local mirror in `trends_service` — `is_pick_asset` is `getattr`-based and returns False for a dict, and `trends_service` is deliberately dependency-free (pure functions, no DB, no `trade_service` import). It applies the same two fields plus the `pick_values.GENERIC_PICK_ID_PREFIX` fallback for ids with no enrichment row. |

### Explicit non-goal: rank numbers do not move

`compute_risers_fallers` derives `overall_rank` / `pos_rank` from the full
`current_elo` pool. Picks stay in those rank maps — they are real board
assets and appear as ranked tiles elsewhere (Tiers, the pick ladder), so
removing them from the denominator would make Trends disagree with every
other rank surface. Only the emitted **rows** are filtered.

## 4. Scope

**In:**
- `backend/server.py` — `market_movers_route` skips pick assets.
- `backend/trends_service.py` — `compute_risers_fallers` skips pick assets.
- `docs/api-reference.md` — both route rows note the exclusion (response
  *shape* is unchanged; the row set narrows).
- Backend tests for both.

**Out:** no client change. `MarketPulseStrip.tsx` and `TrendsScreen.tsx`
are correct as written — they render what the server sends, and their
existing empty states ("No risers yet." / "No risers in this window.")
already cover a list that a pick used to occupy. No flag: this is a
correctness fix inside the already-flagged `market.movers` surface and the
long-shipped Trends surface.

## 5. Success criteria

1. `GET /api/market/movers` never returns a row whose pool player has
   `team == "PICK"` or `position == "PICK"`, at any `window_days` /
   `top_n`, regardless of how much the pick ladder moved.
2. Excluding a pick **backfills** — a request for `top_n = N` still returns
   N rows when N real players qualify.
3. `GET /api/trends/risers-fallers` returns no pick row in any position
   bucket, including `ALL`.
4. `overall_rank` / `pos_rank` / `*_rank_delta` values for the surviving
   player rows are byte-identical to before the change.
5. Both endpoints stay empty-safe: a pool of nothing but picks returns 200
   with empty lists, not an error.
6. `cd mobile && npx tsc --noEmit` clean; `pytest backend/tests` green.

## 6. Maestro regression flow

`mobile/.maestro/flows/smoke/12-market-movers.yaml` (tags `[smoke, league]`,
profile `standard`, flags `release`) — extends the `09-league.yaml` path:

```
- launchApp (clearState) → signin.username-input "qa_standard" → signin.continue-btn
- leagues.row.990000000000000001
- tab.league → wait league.hero
- (flag market.movers on ⇒) wait id: "league.market-pulse"
- tapOn id: "league.market-pulse"
- extendedWaitUntil visible id: "market-movers.sheet"
- assertNotVisible text: ".*Round Pick.*"      # year-less rung label
- assertNotVisible text: "20[0-9]{2} (Early|Mid|Late) (1st|2nd|3rd|4th)"  # #207 year-explicit label
- takeScreenshot: smoke-12-market-movers
- back (backdrop tap) → assert league.hero
```

Both label forms are asserted because `picks.rank_year_labels` decides
which one the server serves, and the flow must fail on either.

**Runtime caveat — this flow is NOT written or run in this change.** The
`market.movers` strip renders `null` on thin history, and the UI-test
profile's seed DB (`backend/tests/fixtures/seed_ui_test_db.py`) would need
two `player_value_history` days *including a moved pick rung* for the sheet
to exist at all. Authoring that fixture is runtime work owned by the batch
QA round; this PRD specifies the flow so that round can land it. Static
verification for this change is `pytest` + `tsc` + grep proofs.

## 7. QA checklist (batch round)

- [ ] League home: Market pulse strip shows two player names, no pick rung.
- [ ] Movers sheet: neither column contains a pick rung, in either format
      (1QB and SF TEP — the strip re-queries on `activeFormat`).
- [ ] Movers sheet still fills to 10 rows per column where data allows.
- [ ] Rank → Trends: Risers and fallers shows no pick in All / QB / RB /
      WR / TE.
- [ ] Trends rank chips ("#12", "RB4") unchanged vs pre-fix for the same
      player.
- [ ] Web Trends page (`web/index.html`) — same absence of picks.
- [ ] Flag `market.movers` off ⇒ strip absent (unchanged 404 path).

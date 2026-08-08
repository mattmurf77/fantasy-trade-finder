# #261 — Exclude draft picks from Risers / Fallers

**Report (app v1.11.0, screen LeagueHome, severity bug):** "Draft picks
should be excluded from the 'risers and fallers' section."

**Status: built (2026-08-08, branch `teardown-remediation`, worktree
`agent-a795927256b2f29e7`). Not merged, not pushed.**

PRD: [`prd.md`](prd.md).

## What shipped

**Server-side in both endpoints. No client change.** Rationale in
[`prd.md` §3](prd.md): the web client renders the same Trends lists from
the same endpoint, and both endpoints cap at `top_n` *before* serializing —
a client-side filter would return short lists instead of backfilling.

### `GET /api/market/movers` — the reported surface

`backend/server.py`, `market_movers_route`: the enrichment loop now skips
any pool player the canonical `trade_service.is_pick_asset` predicate
matches, before the junk-baseline / flat-mover guards and therefore before
the `top_n` cap.

Root cause: `_write_daily_value_snapshots` snapshots the whole universal-pool
seed, which includes the 12 generic `generic_pick_*` rungs, so picks were
first-class movers candidates. `GENERIC_PICK_SEEDS` being a static ladder
meant the `pct == 0` guard usually hid them *by accident* — any value-scale
change (a `model_config` `elo_value_*` retune, a rescale migration like
#117's) gives every rung the same non-zero `pct_30d` at once and floods
both columns. The exclusion is now explicit.

### `GET /api/trends/risers-fallers` — same section, same defect

`backend/trends_service.py`, `compute_risers_fallers`: rows for pick assets
are skipped. Included in scope because the reporter's phrase names the
section whose visible header *is* "Risers and fallers" (`TrendsScreen` +
the web Trends page), which had the same gap with no accidental mask — the
generic rungs are rankable in trios, so ranking one writes `elo_history`
and puts a pick in a position bucket.

`trends_service` is deliberately dependency-free (pure functions, no DB, no
`trade_service` import) and receives enrichment **dicts**, which the
`getattr`-based `is_pick_asset` cannot read. New module-local
`_is_pick_asset(player_id, meta)` applies the same two fields
(`position == "PICK"`, `team == "PICK"`) plus the
`pick_values.GENERIC_PICK_ID_PREFIX` id arm that `taste_service._is_pick`
also carries, for pool rungs with no enrichment row. Ids only — never the
label, per `docs/cross-client-invariants.md` on served rung strings.

**Deliberate non-change:** the filter runs AFTER the rank maps are built,
so picks stay in the rank denominator. They are real board assets on every
other rank surface (Tiers, the pick ladder), so `overall_rank` / `pos_rank`
/ `*_rank_delta` on the surviving rows are byte-identical to pre-#261.
`sample_size` now counts the surviving players.

## Files touched

| File | Change |
|---|---|
| `backend/server.py` | `market_movers_route`: local `is_pick_asset` import + 2-line skip |
| `backend/trends_service.py` | `GENERIC_PICK_ID_PREFIX` import, `_is_pick_asset` helper, 1-line skip in `compute_risers_fallers` |
| `backend/tests/test_market_movers.py` | +2 tests (exclusion + backfill; pick-only pool empty-safe) |
| `backend/tests/test_trends_rank_deltas.py` | +1 test (every bucket, all three pick shapes, ranks unchanged) |
| `docs/api-reference.md` | both route rows note the exclusion (CLAUDE.md docs table) |
| `docs/feedback/items/261-risers-exclude-picks/` | this folder |

No files under `mobile/`, `web/`, or `extension/` changed
(`git status --porcelain mobile/ web/ extension/` → empty).

## Verification (static only — runtime is the batch QA round's)

```
$ python3 -m pytest backend/tests -q
1930 passed, 1 skipped in 127.33s

$ cd mobile && ./node_modules/.bin/tsc --noEmit
(exit 0, no output)
```

`mobile/` has no `node_modules` in this worktree; typecheck ran against a
temporary symlink to the main checkout's install, removed afterward. It is
a no-op proof either way — no client file changed.

Grep proofs:

```
$ grep -n "is_pick_asset" backend/server.py
18389:    from .trade_service import is_pick_asset
18409:        if is_pick_asset(p):

$ grep -n "_is_pick_asset\|GENERIC_PICK_ID_PREFIX" backend/trends_service.py
34:from .pick_values import GENERIC_PICK_ID_PREFIX
101:def _is_pick_asset(player_id: str, meta: dict | None) -> bool:
120:            or str(player_id).startswith(GENERIC_PICK_ID_PREFIX))
650:        if _is_pick_asset(pid, (players_by_id or {}).get(pid)):
```

**Not run** (batch QA round owns these): iOS simulator, Maestro, any live
Flask server. The regression flow is specified but not authored — see
[`prd.md` §6](prd.md) for why (`mobile/.maestro/flows/smoke/12-market-movers.yaml`
needs the UI-test seed DB to carry two `player_value_history` days with a
moved pick rung before the sheet exists at all).

## QA checklist

- [ ] League home: Market pulse strip shows two player names, no pick rung.
- [ ] Movers sheet: neither column contains a pick rung, in **both** formats
      (1QB and SF TEP — the strip re-queries on `activeFormat`).
- [ ] Movers sheet still fills to 10 rows per column where data allows.
- [ ] Rank → Trends: Risers and fallers shows no pick in All / QB / RB /
      WR / TE.
- [ ] Trends rank chips ("#12", "RB4") unchanged vs pre-fix for the same
      player.
- [ ] Web Trends page (`web/index.html`) — same absence of picks.
- [ ] Flag `market.movers` off ⇒ strip absent (unchanged 404 path).

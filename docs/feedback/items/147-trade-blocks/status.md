# #147 — Import trade blocks from Sleeper as a trade-engine data point

**Owner report:** "Import trade blocks from Sleeper as another data point for
the trade engine." Managers flag players "on the block" in Sleeper's Trade
Center; that intent should feed FTF (display + a signal the engine can weight).

**Status: DONE (data import + display + engine hook WIRED)** — 2026-07-17,
branch `trade-engine-v2`. Engine *weighting* landed 2026-07-18 as the SOFT,
acquire-side `block_boost` (flag `trade.block_boost`) — see "Engine hook" below
and [engine-hook.md](engine-hook.md).

---

## 1. What Sleeper actually exposes (with evidence)

Trade-block state is **NOT** in the documented v1 REST API. Confirmed:
- `https://docs.sleeper.com/` lists rosters/users/matchups/transactions/etc. —
  zero mentions of "trade block". Roster `metadata` carries only team nicknames
  (`p_nick_*`) and push-pref keys (`allow_pn_*`); no block field. Probed
  `/v1/league/<id>/{trade_block,tradeblock,blocks}` → all **404**.
- League `users[].metadata` has a `trade_block_pn` key — that's the *push
  notification toggle*, not the block contents.

It **IS** publicly readable (no auth token) via the same GraphQL endpoint the
Sleeper app uses, `POST https://sleeper.com/graphql`. Introspection is stripped
(`__schema.types` returns empty), but the error-suggestion ("Did you mean…")
channel is open, which surfaced the root field `league_players`. Live probe
against the operator's leagues (2026-07-17):

```
query { league_players(league_id: "<id>") { player_id settings } }
```

returns one row per rostered asset; flagged assets carry:

```json
{ "player_id": "4943", "settings": { "otb": 7, "otb_added_at": 1777754069841 } }
```

- `settings.otb` = the **roster_id** that put the asset on the block.
- `settings.otb_added_at` = epoch **ms** when flagged (absent on older leagues —
  e.g. league `1101407304802574336` returned `otb` with no timestamp).
- Pick assets appear too, with `player_id` like `"7,2026,1"`.

Cross-checked `otb` against `/v1/…/rosters` ownership across 4 leagues (23, 6,
24, 73 flags): most `otb` values match the current owner, but a meaningful
minority are **stale** — Sleeper never clears `otb` after a player is
traded/dropped (e.g. league `…050048` player `5045` flagged by roster 7 but now
owned by roster 10). So the raw feed must be validated against live rosters.

**Consistency with existing code:** we already POST to `sleeper.com/graphql`
for the *write* surface (`backend/sleeper_write.py`). This is the same endpoint
but a **public read** (no `authorization` header), so it's lower-risk than the
write path and needs no token. It is NOT in the documented REST API, so it's
treated as best-effort (flag-gated, fail-open).

## 2. Schema + sync design

New table **`trade_block`** (`backend/database.py`), replace-on-sync snapshot
per league (same semantics as `member_rankings`):

| col | notes |
|---|---|
| `league_id`, `player_id` | unique `(league_id, player_id)` |
| `user_id`  | Sleeper user who owns + flagged the player |
| `roster_id`| raw `otb` value |
| `flagged_at` | ISO UTC from `otb_added_at`; NULL on legacy leagues |
| `synced_at` | ISO UTC of the snapshot |

Helpers: `replace_trade_block(league_id, entries)` (delete+insert in one txn;
empty list = valid "clear the league" snapshot), `load_trade_block(league_id)`.

`backend/trade_block_service.py`:
- `fetch_league_players(league_id, _opener=…)` — public GraphQL read.
- `parse_trade_block(league_players, rosters)` — pure fn: keeps a flag only when
  the flagging roster still **owns** the player (drops stale flags), skips pick
  pseudo-ids (`","` in id — picks need traded-pick resolution; **follow-up**),
  converts `otb_added_at` ms → ISO.
- `sync_league_trade_block(league_id)` — fetch + parse + store; no-op (returns 0)
  for non-Sleeper league ids (ESPN/demo).

**Sync path:** called from `session_init`'s existing background-writes daemon
(`backend/server.py`), right after `upsert_league_members`, behind flag
`sleeper.trade_block`. One GraphQL + one REST read per init, best-effort
(a Sleeper flake leaves the prior snapshot in place). No new route — it rides
the league sync that already runs, matching the `league_members` pattern.

## 3. Where the tag renders

Serializer `trade_card_to_dict` (`backend/server.py`) stamps `on_block: true`
onto involved `give`/`receive` player objects that the league's block names,
via a 5-min TTL cache (`_league_on_block_ids`, invalidated after each sync).
Additive + **omit-when-absent** (never `false`); flag-off / no-data payloads
are byte-identical to pre-147.

Mobile `TradeCard.tsx` (shared by TradesScreen deck **and** MatchesScreen)
renders an **"ON THE BLOCK"** micro-tag from `player.on_block` — Chalkline
`Badge`, `flare` = informational (ADR-005) — in the player row's `rightSlot`,
co-existing with the UNTOUCHABLE badge and swap button. One additive edit in
TradeCard's own region; the platform gating of SendInSleeperButton (owned by a
separate thread) is untouched.

FA-finder / roster contexts: **follow-up, not done** — those surfaces don't go
through `trade_card_to_dict`, so wiring them is a separate additive pass
(`load_trade_block` is the ready read hook). Noted here rather than force-fit.

## 4. Engine hook (WIRED — 2026-07-18)

The trade engine reads the signal at **`database.load_trade_block(league_id)`**
(returns `[{player_id, user_id, roster_id, flagged_at, synced_at}]`) via
`trade_service._load_on_block_by_uid`, which groups the rows by the flagging
owner. `_generate_trades_v2` then applies the SOFT, acquire-side **`block_boost`**
(flag `trade.block_boost`, knob `block_boost_weight`): a card whose acquire side
holds ≥1 player the *counterparty* flagged gets a flat `1 + block_boost_weight`
composite bump, applied AFTER all gates so it only reorders acceptable trades and
never rescues a gated one (mirrors `need_fit`). Give-side / the user's own
flagged players are out of scope (operator-approved acquire-side only). Full
design, wiring location, and gate-authority argument in **[engine-hook.md](engine-hook.md)**.

## 5. Tests

`backend/tests/test_trade_block.py` (10 tests, all green):
- fetch/parse from a trimmed real-shape GraphQL fixture (+ GraphQL-error raise),
- ownership validation (stale flag dropped, pick id skipped, ownerless roster
  dropped, ms→ISO timestamp, legacy-league NULL timestamp),
- storage round-trip + re-sync-replaces + empty-clears + league isolation,
- end-to-end `sync_league_trade_block` via injected `_opener`,
- non-Sleeper-id no-op,
- serializer tags only blocked players (omit-when-absent),
- **flag-off / no-data parity** (identical payload; flag-off does no DB read),
- TTL cache + post-sync invalidation.

Full backend suite: **694 passed** (was 684). Mobile `tsc --noEmit`: clean.

## Files

- `backend/database.py` — `trade_block` table + `replace_trade_block` / `load_trade_block`
- `backend/trade_block_service.py` — new: fetch + parse + sync
- `backend/server.py` — `_league_on_block_ids` cache, `on_block` in `trade_card_to_dict`, sync call in `session_init` daemon, `load_trade_block` import
- `backend/feature_flags.py` + `config/features.json` + `backend/tests/fixtures/flags/release.json` — `sleeper.trade_block` flag
- `mobile/src/shared/types.ts` — `Player.on_block`
- `mobile/src/components/TradeCard.tsx` — "ON THE BLOCK" badge
- `backend/tests/test_trade_block.py` — new tests
- docs: `data-dictionary.md`, `api-reference.md`, `glossary.md`, `architecture.md`

## Follow-ups

1. ~~Trade-engine weighting of the block signal (trade-logic thread).~~ **DONE 2026-07-18** — SOFT acquire-side `block_boost`; see [engine-hook.md](engine-hook.md).
2. Draft-pick block flags (needs traded-pick ownership resolution).
3. FA-finder / roster-context "on the block" surfacing.

# #142 + #144 — League summary (power rankings) — status

Owner items (mattmurf77, League):
- **#142** — "Add a league summary page that ranks each team in the league by consensus rankings and lets user view league rankings by their personal rankings too. This should also have a way to view league rankings by redraft rankings."
- **#144** — "The league summary page should display each team in rank order and clicking on a team should bring up their roster sorted by position and by value within the position."

**Status: built (backend + mobile + tests + docs), 2026-07-17.** Branch `trade-engine-v2`.

## What shipped

### Backend

- **`GET /api/league/power-rankings?league_id=&basis=consensus|personal|redraft`** (`backend/server.py`, appended route; math in new **`backend/power_rankings.py`**).
  - Every team in the league ranked by **summed roster value**; response embeds each team's full roster (grouped QB→RB→WR→TE→other, value-desc within group — #144) so the client drill-in needs no second request.
  - `basis=consensus` (default): universal-pool consensus values (`elo_to_value` over the pool seed — the exact `/api/trade/values` numbers). League-shared aggregate → open, like `/api/league/coverage`.
  - `basis=personal`: the **caller's live board** for the active format (their per-format `RankingService` Elo, which starts at the consensus seed and diverges as they rank) — i.e. consensus fallback for unranked players falls out naturally. Board-derived content → P2.5 read gate applied **inline** (mirrors `/api/trade/evaluate` Mode B; the route can't take the decorator wholesale because the consensus basis is deliberately open).
  - `basis=redraft`: **501 `{error: not_available}`** — see descope note below. Any other basis → 400.
  - Ordering is deterministic: `total_value` desc, `user_id` asc tiebreak; ranks 1..N stamped after sort.
  - Out-of-pool players (K/DEF, deep stashes) contribute **0** — a 1500-Elo default would hand every deep bench ~1000 phantom points per player.
  - Demo-league fix discovered in route smoke: demo player ids never appear in the universal pool, so consensus totals were all zero. The route merges the session service's seed ratings as a *fallback* value source (pool seed wins); real leagues unaffected.
  - Member source: `league_members` snapshot (includes the caller; ESPN-imported leagues store synthetic `espn:` member ids with **crosswalked Sleeper player ids**, so value resolution is identical — verified in code path). Fallback for fresh/demo sessions with no DB snapshot: session league members + the caller's `user_roster`.

### Mobile

- **`mobile/src/screens/LeagueSummaryScreen.tsx`** (new; root-stack route `LeagueSummary`, header "League rankings"): teams in rank order — rank numeral, name (+ ice "You" badge), per-position value mini-summary (QB/RB/WR/TE in position colors), total value, chevron. Basis toggle **Consensus | My board** + disabled **"Redraft (soon)"** chip. Tap a team → overlay (same pattern as the League tab's member overlay) with the roster grouped by position, value-sorted within group, rendered as **dense `PlayerCard` rows**.
- **`mobile/src/screens/LeagueScreen.tsx`**: new "Explore" section with two LeagueRow-style entry rows — **"League rankings"** → `LeagueSummary` and **"Free agents"** → `FreeAgents` (the parallel #143 agent's screen; this file is owned by the #142 build per the file-ownership split).
- **`mobile/src/api/league.ts`**: `getPowerRankings()` + `PowerRankingsResponse`/`PowerRankedTeam`/`PowerRankedPlayer` types (additive).
- **`mobile/src/navigation/RootNav.tsx`**: registered `LeagueSummary` + `FreeAgents` on the root stack (additive; both use the Chalkline header).

### Tests / evidence

- **`backend/tests/test_power_rankings.py`** — 7 tests: consensus totals + rank order, personal basis override with consensus fallback (order inversion), out-of-pool → 0 (player still listed with metadata), deterministic user_id tiebreak, #144 roster grouping contract, position-summary counts/values, blank-user_id row skipped.
- Full backend suite: **617 passed** (baseline requirement was 558+).
- Route smoke (injected session, Flask test client): consensus + personal 200 with correct rank order/grouping, redraft → 501 `not_available`, bogus basis → 400, no session → 401.
- `tsc --noEmit`: no errors in any file touched by this item (pre-existing/parallel-agent errors remain in `TiersScreen.tsx` and `TradeCalculatorScreen.tsx`, owned by other in-flight agents).

### Docs

- `docs/api-reference.md` — League table row for `/api/league/power-rankings` (contract, bases, 501 redraft, determinism, ESPN note).
- `docs/glossary.md` — "Power rankings" entry.
- `mobile/src/components/CLAUDE.md` — testID tranche: `league-summary.basis.<consensus|personal|redraft>`, `league-summary.team.<user_id>`, `league-summary.roster-close`, `league.rankings-row`, `league.free-agents-row`.
- `mobile/src/screens/CLAUDE.md` + `mobile/src/navigation/CLAUDE.md` — screen/route rows.

## Redraft descope (#142 partial)

FTF's value source (DynastyProcess via `data_loader.py`) ships **dynasty values only** — there is no redraft value pool anywhere in the system. Rather than fake it (e.g. age-discounting dynasty values would be an invented ranking, not "redraft rankings"), the API **reserves** `basis=redraft` and answers `501 {error: not_available, message: …}`; the mobile UI shows a permanently disabled "Redraft (soon)" chip and never issues the request. When a redraft value source lands (e.g. DP's FantasyPros redraft columns), the shape is already in place: implement the basis server-side and enable the chip.

## Follow-ups

- Maestro flow for the new screen (registry IDs are in place; per LLD Appendix A tax, ~1–2 h with a profile touch).
- Web parity: no web League Summary surface exists yet; the API is client-agnostic.

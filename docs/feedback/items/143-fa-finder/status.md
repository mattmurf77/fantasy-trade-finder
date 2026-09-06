# Status — 143-fa-finder

```project-status
{
  "status": "shipped",
  "updated": "2026-07-17",
  "summary": "#143 — Free agent finder — status",
  "evidence": "Carried forward as the last documented disposition, not a fresh production audit. Prior index merge corrections take precedence over older pre-merge notes. Last documented index disposition: shipped 2026-07-17 — FB-143 `backend/free_agent_service.py` — CHANGELOG 2026-07-17. Prior row preserved at ../../../reviews/2026/2026-09-06-project-status-migration/feedback-index.md."
}
```

## Historical notes

The material below is retained evidence. Its former status wording does not override the record above.

# #143 — Free agent finder — status

**State:** built + tested (2026-07-17, branch `trade-engine-v2`). Backend
contract pinned by pure-function tests; full backend suite green (617);
mobile screen tsc-clean. Awaiting the league-summary agent's nav wiring
(League tab "Free agents" row → route `FreeAgents`) + QA/ship.

**Owner ask (mattmurf77, League):** see best free agents across all
positions, filter by position, ranked by the user's own valuations, with
drop suggestions from those same valuations.

## Contract

`GET /api/league/free-agents?league_id=...&position=QB|RB|WR|TE|ALL`
(both params optional — defaults: session league, ALL). Session-gated
(`_require_initialized_session`) + **read-gated** (`@_gate_unverified_read`,
added to the gated-read matrix in `docs/api-reference.md` §"The read gate"
and `backend/tests/test_verified_reads.py::GATED_READS`) because the list
is priced by the caller's board, like `/api/rankings`.

```
{
  "league_id": str,
  "scoring_format": "1qb_ppr" | "sf_tep",     // _active_format(sess)
  "position": "QB"|"RB"|"WR"|"TE"|"ALL",
  "user_has_rankings": bool,                  // false ⇒ pure-consensus list
  "free_agents": [                            // top 50 AFTER position filter
    { "player_id", "name", "position", "team", "age",
      "value": float,                         // caller-board dynasty value
      "pos_rank": int,                        // within-position, across ALL FAs
      "drop_suggestion": {                    // or null
        "player_id", "name", "position",
        "value": float,
        "delta": float                        // FA value − drop value, > 0
      } }, ... ]
}
```

Errors: 401 session_expired · 409 session_not_initialized · 403
verification_required (read gate) · 400 missing league_id / invalid
position.

## Rules (logic in `backend/free_agent_service.py`, pure + unit-tested)

- **FA pool** = active format's universal pool minus every rostered player
  in the league — session `league.members` rosters + `sess["user_roster"]`
  when `league_id` matches the session league (covers Sleeper,
  ESPN-imported and demo leagues, since session init builds all three);
  DB `league_members` snapshot for any other league_id. PICK pseudo-players
  are never FAs (`FA_POSITIONS = QB/RB/WR/TE`).
- **Ranking basis** = the caller's board: personal Elo where present,
  consensus seed per unranked player, through the same `elo_to_value`
  transform every other surface prices with. Fallback is per-player —
  unranked players are priced at consensus, never dropped or zeroed.
- **Drop rule** = for each surfaced FA, the caller's LOWEST-valued
  same-position rostered player, suggested only when its value is
  **strictly below** the FA's; `delta` = FA value − drop value. Same
  position only; equal value ⇒ no suggestion; roster ids outside the
  universal pool can't be priced and are skipped as candidates.
- **pos_rank** is computed across the whole FA pool before filtering, so
  "RB3" is the same player under every filter; the 50-row cap applies
  after the filter so each position gets a full page.

### Drop-rule examples (from the tests)

- Roster RB1 (high) + RB3 (low); FA RB2 between them → suggest **RB3**
  (lowest, below the FA) — never RB1.
- Only QB rostered outvalues the FA QB → **no suggestion** (never suggest
  dropping a better player).
- Weak TE rostered, strong FA RB → **no suggestion** (no cross-position).
- Caller tanks their consensus-best RB below an FA RB on their own board →
  that RB becomes the suggestion under THEIR values.

## Mobile

`mobile/src/screens/FreeAgentsScreen.tsx` (new; League-stack route
`FreeAgents` — nav registration + the League tab entry row belong to the
league-summary agent, coordinated on the exact route name `FreeAgents`):

- Position filter pills All/QB/RB/WR/TE (PositionTabs construction —
  segmented hairline group, active = ink3 fill + position-color underline,
  ice for ALL; same as Trends).
- Dense `PlayerCard` rows: value + FA positional rank (`RB3`) in the right
  cluster; line 2 = "Drop: <player> (+delta)" (delta in `semantic.pos`)
  when a suggestion exists, else a faint "No drop worth making".
- Empty/edge states: **no league** ("Connect a league to see its free
  agents."), **unranked** (`user_has_rankings:false` → persistent notice
  card "…this list uses consensus values. Rank players to make it yours."
  — list still renders, since consensus fallback makes it useful), empty
  list per filter, read-gate 403 via `readErrorCopy` ("Verify your
  account…"), pull-to-refresh + Retry.
- API: `getFreeAgents(leagueId, position?)` appended to
  `mobile/src/api/league.ts` (`FreeAgentRow` / `FreeAgentsResponse` types).
- testIDs (registry `mobile/src/components/CLAUDE.md`):
  `free-agents.pos-tab.<all|qb|rb|wr|te>` · `free-agents.list` ·
  `free-agents.row.<player_id>` · `free-agents.empty-text`.

## Files

- `backend/free_agent_service.py` — NEW: `compute_free_agents`,
  `board_value`, `board_is_personalized`, `FA_POSITIONS`, `DEFAULT_LIMIT`.
- `backend/server.py` — appended route `league_free_agents_route`.
- `backend/tests/test_free_agents.py` — NEW: 18 tests (exclusion /
  personal-value ranking + consensus fallback / drop rule / filter+limit /
  personalization flag).
- `backend/tests/test_verified_reads.py` — route added to `GATED_READS`.
- `mobile/src/api/league.ts` — additive `getFreeAgents` + types.
- `mobile/src/screens/FreeAgentsScreen.tsx` — NEW screen.
- Docs: `docs/api-reference.md` (League table row + gated-reads list),
  `docs/glossary.md` ("Free agent finder"), `mobile/src/screens/CLAUDE.md`
  + `mobile/src/components/CLAUDE.md` (registry tranche).

## Test results

- `backend/tests/test_free_agents.py` — 18 passed.
- Full backend suite — **617 passed** (2026-07-17).
- `npx tsc --noEmit` — zero errors in this feature's files; the only
  remaining errors are in `TiersScreen.tsx` / `TradeCalculatorScreen.tsx`,
  both owned by other in-flight parallel agents.

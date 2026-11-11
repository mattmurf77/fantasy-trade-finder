# Manager revealed-preference profiles — design

**Date:** 2026-11-10 · **Status:** shipped (#635, `9b14c47b`); flag `market.manager_profiles` on in `config/features.json` (operator, 2026-11-10), code default off; capture only, no consumer
**Scope block:** [scope.md](scope.md)

## Open questions for the operator

1. **Profiling league-mates who never signed up.** A profile describes how a real person bids,
   trades and drafts, built from public Sleeper data, and is kept for people who have no
   account with us. Does the privacy page cover "we derive behavioral summaries of league-mates
   from public league history", and should a deleted account's profile be blocked from being
   rebuilt (today any league-mate's next sync rebuilds it; `accounts.delete_user_data` deletes
   it and `GET /api/account/export` includes it)? *The design recommended keeping the flag off
   until this was answered; the operator turned it on in `config/features.json` on 2026-11-10.
   The question itself is still open. Since then the profile write holds the daemon caller's
   users-row lock, so a user's own session never rebuilds their profile after they delete their
   account; a league-mate's sync still can.*
2. **Prior seasons.** Trade signals are thin within one season (median 2 trades per manager).
   `scripts/backfill_sleeper_trades.py` already stores up to 3 prior seasons of trades in
   `sleeper_trades`, under the prior seasons' league ids. Reading them needs one `/rosters` read
   per prior league, once ever (a completed season never changes), to map those roster ids to
   people. Approve that cost for v2? Recommended: yes.
3. **Rookie-draft signal.** Not captured in v1 (see §4.5). It needs two Sleeper reads per
   league per season (`/league/<id>/drafts`, `/draft/<id>/picks`) and a dated consensus board at
   draft time, which we only have from 2026-07-26 on. Build it for the 2027 rookie drafts?
4. **Which consumer first.** Recommendation in §6 (an offline evaluation, then a response
   prior on partner ordering). Nothing reads the profile until that is decided.

## 1. Why

The 2026-11-10 offline evaluation found ~80% of suggested trades go to a league-mate who has
never ranked in the app, and testers liked those far less (17–23% vs 46–65%). For those managers
the engine knows only consensus value and a roster-inferred outlook
(`trade_service.infer_team_outlook`). Public league history shows what they actually do. This
work starts collecting that history as a per-manager profile. It changes nothing a user sees.

## 2. What already exists (citations at `origin/main` d6fc338f + this branch)

| Piece | Where | What it does |
|---|---|---|
| Weekly transaction fetch | `backend/sleeper_trades_service.py:70` `fetch_week_transactions` | `GET /v1/league/<id>/transactions/<week>`, injectable `_opener`, inside the 429 circuit (`sleeper_http.guard`) and `api_observability` |
| Trade filter | `sleeper_trades_service.py:99` `parse_trade_transactions` | keeps `type=trade`, `status=complete` only; **every waiver and free-agent row is thrown away** |
| Sweep | `sleeper_trades_service.py:159` `sweep_weeks`, `:189` `sync_league_trades` | legs 1–18 once per league (`database.has_sleeper_trades`), then the live leg and the one before it; leg 1 in the offseason |
| Storage | `backend/database.py:753` `sleeper_trades` | raw payload + roster_ids / adds / drops / draft_picks / waiver_budget; idempotent on `transaction_id` (`record_sleeper_trades`, `:10698`) |
| Call site | `backend/server.py` session-init daemon, the `market.trade_capture` block (~`:30178`) | Sleeper numeric leagues only, best-effort, off the request path |
| Prior seasons | `scripts/backfill_sleeper_trades.py` | operator-run; walks `previous_league_id` up to 3 seasons, trades only |
| Roster → person | `backend/sleeper_roster.py` (`owns_roster`, `canonical_owner_id`) | the one predicate: `user_id == owner_id or user_id in co_owners`; a co-owner is an alias of `owner_id` |
| Manager identity | `database.py:695` `league_members` (`league_id`, `user_id` = the roster's `owner_id`) | one row per roster; `backend/CLAUDE.md` § Identity |
| Shared payloads in the daemon | `server.py` `_rh_roster_rows` (one `/rosters` read per init) and `_league_meta()` (one `/league/<id>` read) | handed to every consumer; pinned by `test_session_init_sleeper_calls.py` |
| Draft selections | `backend/draft_board_service.py:298-306` (`drafts`, `draft_detail`, `draft_picks`) | read live for the Draft Room; **not stored**. `draft_picks` table (`database.py`, `draft_picks_table`) is pick *ownership*, not selections |
| Dated consensus | `backend/dp_values_history.py` `values_as_of` | research only: reads committed snapshots under `backend/tests/fixtures/dp-values-history/` for 2022–2025, Sept–Dec dates only, no network unless `allow_network=True` |
| Dated consensus (prod) | `database.py:2188` `player_value_history` | one row per player per format per day since 2026-07-26 |

### The public transactions payload (observed 2026-11-10)

Every row, whatever its type, carries `type, status, transaction_id, leg, roster_ids, creator,
consenter_ids, adds, drops, draft_picks, waiver_budget, settings, metadata, created,
status_updated`.

| Type / status | Fields that matter |
|---|---|
| `waiver` / `complete` | `settings.waiver_bid` (FAAB $), `settings.seq`, `adds {player: roster}`, `drops`, `metadata.notes` "processed successfully" |
| `waiver` / `failed` | same, plus `metadata.notes` saying why: "This player was claimed by another owner." (outbid), "…too many players…" (roster full), "…already started playing." (locked) |
| `free_agent` / `complete` | `adds`, `drops`; `settings` and `metadata` null; no bid |
| `trade` / `complete` | `adds`, `drops`, `draft_picks [{season, round, roster_id, previous_owner_id, owner_id}]`, `waiver_budget [{sender, receiver, amount}]` |

Ids in `adds`/`drops` are Sleeper player ids, or a team abbreviation for a defense (`"TB"`).
`roster_ids` on a waiver row is the one claiming roster. `creator` is the Sleeper user who
submitted it: the owner, a co-owner, or the commissioner. The league's budget is
`settings.waiver_budget` on `/league/<id>` and FAAB is `settings.waiver_type == 2`; each roster's
`settings.waiver_budget_used` is on `/rosters`. Pending claims did not appear in any sampled leg.

## 3. The profile (v1, as built)

One `manager_profiles` row per **owned roster** per league, keyed by the roster's `owner_id`
(league identity). Built by `backend/manager_profiles.py:build_league_profiles` from everything
stored for the league. The `profile` JSON:

| Section | Contents |
|---|---|
| `trade_activity` | `n` completed trades, `last_trade_at`, `days_since_last_trade`, distinct `counterparties`, `league_mean_n` (the league's average, for a relative read) |
| `trade_style` | per trade side, by net direction: `picks_for_players`, `players_for_picks`, `players_only`, `picks_only`, `mixed`; `faab_net_in_trades` |
| `trade_assets` | `acquired` and `given`: player count, `by_position`, `by_age_band` (≤23, 24–26, 27–29, 30+, at the trade date, from `players.birth_date`), pick count, `picks_by_round` |
| `waiver_bids` | `faab`, `budget`, `n`, `won`, `outbid`, `failed_other`, `claims_without_bid`, `spent`, `reported_spent` (Sleeper's own `waiver_budget_used`, a check on completeness), `median_won_share`, `max_share`, and every bid: player, position, leg, dollars, `share_of_budget`, `share_of_remaining` (budget − won so far + FAAB received in trades so far), outcome, and for an outbid claim the `clearing_bid` (the winning bid on that player in the same run) |
| `free_agents` | `n` adds and `by_position` (activity only, no price) |
| `rookie_draft` | `{"captured": false}` in v1 |
| `excluded` | `foreign_creator_moves`: waiver/FA moves whose `creator` neither owns nor co-owns the roster |

Each signal carries `usable`, false when it is too thin (§4). The counts are stored either way.

**Attribution.** By `roster_id` through the current `/rosters` map. A co-owner's claim lands on
the owner's profile (no second row). An ownerless roster gets no row. A waiver/FA move whose
`creator` fails `sleeper_roster.owns_roster` (a commissioner action, or the previous manager of
a roster taken over mid-season) is excluded and counted. Trades have no such check: `creator` is
only the proposer, so both sides are attributed by roster. A mid-season takeover therefore
inherits the old manager's trades for that season; the count of foreign moves is the hint.

## 4. Signals: how many observations, and when too thin

Trade figures: prod `sleeper_trades`, 622 trades over 27 league-seasons (read-only query,
2026-11-10). Waiver figures: one real 12-team FAAB league, two seasons (public reads,
2026-11-10). Treat the waiver figures as one league's, not a distribution.

| Signal | Typical per manager | `usable` when | Notes |
|---|---|---|---|
| 4.1 Trade activity | median **2** trades per season; 19% make 0, 49% make ≥3; deciles 0,1,1,2,2,3,5,6,10.5 | always | Zero is information. Read relative to `league_mean_n` (league-seasons ranged 10 → 31 trades at the quartiles). One season is a weak prior; three seasons (open question 2) makes it a real one |
| 4.2 Picks vs players | same n; 86% of trades include a pick, so most trades classify | n ≥ 3 (`MIN_TRADES_FOR_STYLE`) | ~half of managers reach it in one season; most would with 3 prior seasons |
| 4.3 Position / age mix | ~1–2 players each way per trade, so ~4–6 players a season | ≥ 6 traded players (`MIN_TRADED_PLAYERS_FOR_MIX`) | Thinnest trade signal. Position counts mean little without the roster's need at the time (a future join with `league_roster_history`) |
| 4.4 FAAB bids | 2025 full season: 150 claims (91 won, 59 failed) ≈ **12.5** per manager. 2026 to leg 10: 0–16 per manager, median ~5 | FAAB league and n ≥ 5 (`MIN_FAAB_BIDS`) | The densest dollar-denominated signal: a bid is a stated price on one player. Most claims are on bench and streaming players, so it says more about how aggressive a manager is than about how they value core dynasty assets. Non-FAAB leagues store claims without a price |
| 4.5 Rookie-draft picks vs consensus | 3–5 picks per manager per year | — (not captured) | See below |
| Free-agent adds | 6–24 per manager per season | never a valuation signal | Activity only |

**4.5 Why the rookie-draft signal is deferred.** (a) It needs Sleeper reads the trade sweep does
not make (`/league/<id>/drafts`, then `/draft/<id>/picks` per completed draft); cheap, since a
completed draft never changes, but new. (b) "Relative to consensus at the time" needs a board
dated to the draft. `dp_values_history` cannot supply one: it is research-only, its committed
snapshots are September–December of 2022–2025 (rookie drafts run May–August, before most of
those boards and with rookies valued differently after camp), and production code must not read
`backend/tests/fixtures/`. The production source is `player_value_history`, which starts
2026-07-26 and so covers only drafts finished after that date. Rookie draft 2027 is the first
season with full coverage. Proposed shape for v2: store each completed rookie draft's picks once
(round, pick, roster_id, player_id, `picked_at`), and price each pick as its rank in
`player_value_history` among that class on the draft date versus its pick slot.

**Deliberately excluded.** Anything private (no GraphQL, no Sleeper credentials, no trade
offers, no chat). Pending and rejected trades (not in the public payload). Commissioner moves.
Player names (ids only). Lineup decisions. Any scoring, ranking or "who will accept" model:
this is the capture, and the profile stores counts and prices, not judgments.

## 5. Capture and call budget

- **No new endpoint.** `sync_league_trades(profiles=True, rosters=…, league_meta=…)` parses the
  waiver and free-agent rows out of the payloads it already fetched
  (`manager_profiles.parse_waiver_transactions`), stores them in `sleeper_waiver_moves`
  (idempotent on `transaction_id`, terminal rows only), then rebuilds the league's
  `manager_profiles` rows from everything stored (`capture_manager_profiles`). The rosters and
  league meta are the daemon's shared reads, so they add no call.
- **One justified extra cost:** an 18-leg backfill, **once per league**, the first time the flag
  is on for a league whose trade capture is already incremental. Without it the season's waiver
  history before the live legs is lost. The marker is the presence of `manager_profiles` rows,
  which are only written after a backfill with no failed leg, so a lossy backfill retries whole.
  After that, zero extra calls: the incremental sweep fetches the same ≤2 legs as today.
- **Skips.** No roster map → the profile step does nothing, backfill included, so it can never
  cost 18 calls per sync. Flag off → `sweep_weeks` and `sync_league_trades` are unchanged.
  A failing profile step is logged and never touches the trade capture.
- **Leaf.** `backend/manager_profiles.py` imports only the standard library and
  `sleeper_roster`. The I/O half lives in `sleeper_trades_service`.

## 6. First consumer — recommendation

1. **Offline first.** Join `manager_profiles` to the 2026-11-10 evaluation set and to
   `suggestion_trade_links` / deck decisions: do managers with `trade_activity.n == 0` over a
   full season accept or answer offers less often, and does `trade_style` predict which side of
   a picks-for-players offer they take? No production change, and it tells us whether the signal
   is worth wiring at all.
2. **Then a response prior on partner order.** If (1) holds, the safest live use is a small
   tie-break in partner ordering for non-ranking league-mates (prefer managers who trade), behind
   its own flag with the usual flag-off byte-identity test. It changes which partner is shown
   first, never the value of a trade.
3. **Later.** FAAB-share bids as a per-manager adjustment to consensus for the specific players
   bid on; style as a hint for what to offer (picks to a pick buyer). Both need the prior-season
   history first.

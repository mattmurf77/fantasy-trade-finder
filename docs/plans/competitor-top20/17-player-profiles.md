# 17. Player profiles (value history + you-vs-market)
> Tier 1 · #17 · NEW · Effort M · Sources: all (includes #57 value-history retention job as immediate prerequisite)

## Summary

Every competitor has player pages; FTF has none — there is nowhere in the product to answer "what does FTF think of this player, and why?" Dynasty Daddy's data model treats value history as a core concept, not a chart add-on: per player it stores all-time / 3-month / 1-month highs, lows, and best/worst ranks, updated daily. FTF has a partial precedent: `elo_history` (`backend/database.py`) already logs the *user's personal* Elo per player on every ranking event (written via `record_elo_snapshot` in the `/api/rank3` path, consumed by `/api/tiers/stability` and `/api/trends/risers-fallers`). What FTF does **not** record is consensus value over time — the DynastyProcess-seeded universal pool (`build_universal_pool`) is rebuilt from the live CSV and yesterday's numbers are gone forever.

Hence the #57 prerequisite, which is time-sensitive: **start a daily consensus value-snapshot job now**, before the profile page exists, because every week not logging is chart history lost. The profile page itself is a single template fed by data already in the DB: player core fields (`players` table: age, position, team, `adp`, `search_rank`, injury fields), consensus value + trend (new snapshot table), the user's Elo-vs-market diff (#9's per-player view), the user's personal Elo sparkline (existing `elo_history`), and recent appearances in suggestions (`trade_impressions`). Every player name app-wide becomes a link here, making profiles the connective tissue between rankings, tiers, league pages, and trade cards — and the SEO/share surface later.

## PRD

### Problem & user story
As a user staring at a trade card or a leaguemate's roster, I want one tap to see who a player is, what the market thinks he's worth, where his value has been heading, and how my own opinion differs — without leaving FTF for KTC or Dynasty Daddy. Today every such tap exits the app.

### Goals / Non-goals
**Goals**
- #57 first: daily snapshot of consensus Elo/value per player per scoring format, starting immediately.
- Player profile template: identity + age/position context, consensus value + trend chart, you-vs-market diff, personal Elo history, recent suggestion appearances.
- Player names across web become links to the profile (mobile follows).

**Non-goals**
- No news feed integration (#51 — link out at most), no stats/production data, no comparison tool (#34 — companion, later).
- No public/SEO version in v1 (the `profiles.public_pages` flag and `/u/<username>` pattern exist for *user* profiles; player pages stay session-authed until launch QA decides otherwise).
- No backfill fabrication: history charts start the day the cron starts. Show honest "tracking since {date}" labels.

### Functional requirements
- FR1 (#57 job): once daily, for each scoring format, write one row per universal-pool player: `(player_id, scoring_format, consensus_elo, consensus_value, search_rank, adp, snapshot_date)`. Idempotent per day (unique constraint; re-runs upsert).
- FR2: Profile API returns: player core fields; current consensus value + 7/30/90-day deltas; all-time high/low since tracking began (computed, Dynasty Daddy precedent); user diff (`your_value`, `market_value`, badge state per #9's thresholds); personal Elo series (existing `load_elo_history`); last N (default 5) suggestion appearances for this user (`trade_impressions` rows whose give/receive arrays contain the player), each with league, counterparty, basis, and date.
- FR3: Value chart renders consensus series; overlays the user's personal-value series when ≥2 personal snapshots exist.
- FR4: Picks are players too: pick assets in the universal pool (Early/Mid/Late, rounds 1–4) get profiles with their seed-value history — cheap and unique once #15's scale work lands.
- FR5: Player-name linkification: web rankings, tiers, trade cards, league/power-rankings drill-downs all route to the profile.
- FR6: Unknown/insufficient data degrades gracefully: no chart with <2 snapshots, no diff badge below #9's confidence threshold.

### UX notes
- **Web:** new page `web/player.html?id=<player_id>` (multi-page convention; standalone like `positional-tiers.html`, shared dark-theme `:root` palette from `web/ranking-method.html`, linked rather than nav-tabbed). Layout: header (name, position chip, team, age — copy DynastyGM's row anatomy: position color chip + age to one decimal), hero number (consensus value) with trend arrow + deltas, chart, "You vs Market" card, "Seen in your suggestions" list.
- **Mobile:** `mobile/src/screens/PlayerProfileScreen.tsx` (second release), pushed from any player row; register in `mobile/src/navigation/`.
- Chart: no charting library on web today — keep to a dependency-free SVG/canvas sparkline consistent with the vanilla-stack convention.
- The "You vs Market" card carries #9's advocate copy ("You're 28% higher than market — buy-low target").

### Success metrics
- ≥3 profile views per active session within 2 weeks of linkification (validates connective-tissue thesis).
- Profile → "find trades involving this player" CTA click-through ≥8% (wires into FB-47 pinned-receive targeting).
- Snapshot job: 100% daily success over 30 days (monitor via cron logging; runbook entry).

### Acceptance criteria
- [ ] Snapshot job live in prod and writing rows for both formats **before** profile UI work starts (#57 ordering).
- [ ] Re-running the job same-day does not duplicate rows.
- [ ] Profile API correct for: ranked player with history, never-ranked player, pick asset, unknown id (404 — existing `/api/players/<player_id>` behavior).
- [ ] Trend deltas verified against fixture snapshots.
- [ ] Suggestion-appearance query returns only the session user's impressions.
- [ ] All web player names link; no dead links for players outside the universal pool (fallback: plain text).
- [ ] `docs/data-dictionary.md` (new table), `docs/api-reference.md` (routes), `docs/runbook.md` (cron monitoring), `docs/architecture.md` (cron ticks section) updated.

## HLD

### Components touched
`backend/database.py` (new table + accessors), `backend/server.py` (snapshot step in the cron path + profile route), `web/player.html` (new), `web/js/app.js` (linkification), `web/index.html` (no nav change; links only), mobile screen + nav later.

### Data flow
Daily cron (Render hits `POST /api/cron/daily-tick`, `_require_cron_auth` with `CRON_SECRET`) → `_ensure_universal_pools()` → iterate `g_universal_by_format[fmt]["seed"]` → upsert into `player_value_history`. Profile request → `load_player` + history query + session rankings diff + `trade_impressions` lookup → single JSON. No engine involvement.

### Flags & config interplay
- Snapshot job runs **unflagged** (it's data retention; cost is one insert batch/day; turning it off loses history — the whole point is continuity).
- New flag `players.profile_pages` (default false) gates the profile route + web links.
- Interplay with `tiers.community_diff` / `trade.diff_angles` (#9): the diff card uses the same thresholds/config keys; share the helper, don't fork the math.
- Retention config key `value_history_keep_days` (default 0 = keep forever; ~700 players × 2 formats × 365 days ≈ 0.5M rows/year — acceptable in SQLite and trivial in Postgres; revisit with a downsample-to-weekly policy after year one).

## LLD

### Engine/backend changes
None to trade math. New `backend/database.py` functions: `record_value_snapshots(rows)`, `load_value_history(player_id, scoring_format, since)`, `load_value_extremes(player_id, scoring_format)`. Cron: extend `cron_daily_tick` in `backend/server.py` with a snapshot step (counter in its existing `counters` dict + log line), or a dedicated `POST /api/cron/value-snapshot` if daily-tick's push-notification scan shouldn't share failure modes with data retention — **recommendation: dedicated endpoint**, same `_require_cron_auth`, so a push bug can't silently stop history collection (verify Render cron can add a second schedule).

### API changes
- `GET /api/players/<player_id>/profile` (session-authed):
```json
{
  "player": {"player_id": "4034", "full_name": "...", "position": "RB",
             "team": "KC", "age": 26, "years_exp": 5, "injury_status": null},
  "consensus": {"value": 4263, "elo": 1790,
                "delta_7d": -120, "delta_30d": 310, "delta_90d": null,
                "high": {"value": 4500, "date": "2026-07-02"},
                "low":  {"value": 3900, "date": "2026-06-14"},
                "tracking_since": "2026-06-12"},
  "you_vs_market": {"your_value": 5100, "market_value": 4263,
                    "diff_pct": 0.20, "state": "higher", "comparisons": 11},
  "history": [{"date": "2026-06-12", "consensus_value": 4100, "your_value": 4800}],
  "recent_suggestions": [{"league_id": "12345", "counterparty": "bkey5",
                          "side": "receive", "basis": "divergence",
                          "shown_at": "2026-06-10T14:01:00Z"}]
}
```
- Keep `GET /api/players/<player_id>` as-is (raw row; existing consumers).

### Schema changes
SQLAlchemy Core, SQLite+Postgres compatible:
```python
player_value_history_table = Table("player_value_history", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("player_id",       String,  nullable=False),
    Column("scoring_format",  String,  nullable=False),   # '1qb_ppr' | 'sf_tep'
    Column("consensus_elo",   Float,   nullable=False),
    Column("consensus_value", Float),                     # elo_to_value at snapshot time
    Column("search_rank",     Integer),
    Column("adp",             Float),
    Column("snapshot_date",   String,  nullable=False),   # "YYYY-MM-DD" UTC
    UniqueConstraint("player_id", "scoring_format", "snapshot_date",
                     name="uq_value_snapshot"),
)
```
Index `(player_id, scoring_format, snapshot_date)` — covered by the unique constraint; add to the existing index-creation block alongside `ix_elo_history_user_fmt_at`. Storing `consensus_value` denormalized (alongside elo) means later `elo_value_*` config changes don't silently rewrite history.

### Client changes
- `web/player.html` new page; `web/js/app.js`: a `playerLink(pid, name)` helper used at every render site (rankings rows, tier cards, trade card give/receive lists, league drill-downs).
- Mobile: `PlayerProfileScreen.tsx` + nav registration + a shared `PlayerName` pressable component (second release).

### Rollout (flag name proposal, default state)
1. **Now:** snapshot table + cron endpoint, no flag, deploy immediately (this is #57; do not wait for the rest of #17).
2. `players.profile_pages` (default false) gating route + links; flip on web after QA, mobile next TestFlight cycle.

### Open questions
1. Suggestion-appearance query: `trade_impressions.give_player_ids/receive_player_ids` are JSON-in-Text columns — a `LIKE '%"<pid>"%'` scan is fine at current volume but unindexable; acceptable for v1, or add a normalized impression-asset table later? (verify current `trade_impressions` row counts)
2. Snapshot both formats daily, or only formats with ≥1 active user? (Recommend both — storage is cheap, gaps are forever.)
3. Should the profile expose *league-mate* opinions of the player (their `member_rankings` Elo) — powerful for #9's angles but possibly socially sensitive? Default: aggregate only ("2 leaguemates are below market on him").
4. Public/SEO player pages (no session): defer decision to launch QA; the `/u/<username>` + `profiles.public_pages` machinery is the pattern if yes.

## Dependencies & sequencing
- **#57 is part one of this item and gates nothing else** — ship it this week regardless of #17 scheduling; #33 (value-movers digest), #46 (Wrapped), and #25 (watchlist alerts) all consume the same table.
- **Consumes:** #9 (diff helper + copy), #16 (confidence ranges could annotate the you-vs-market card), #15 (pick profiles need the pick-scale reconciliation).
- **Feeds:** #34 (player comparison = two profiles side by side), #12/#19 (share/overlay surfaces deep-link to profiles), FB-47 targeting ("find trades involving him" CTA pins the player as a receive target).
- Wave 3 per backlog sequencing, with the #57 job pulled forward to now.

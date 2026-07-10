# API Reference

All routes live in `backend/server.py`. Same-origin from web; mobile + extension hit the deployed host. Keep this file in sync when adding/renaming/removing routes.

Auth: session cookie via `/api/session/init`. Extension uses a bearer token from `/api/extension/auth`.

---

## Session / Auth

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/session/init` | Establish session for a Sleeper username |
| GET | `/api/session/ping` | Liveness / session check |
| POST/GET | `/api/session/demo` | Demo session bootstrap |
| POST | `/api/extension/auth` | Issue extension bearer token |
| POST | `/api/reset` | Wipe current user's rankings + decisions |

## Sleeper passthrough

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/sleeper/user/<username>` | Resolve Sleeper user |
| GET | `/api/sleeper/leagues/<user_id>` | List user's leagues |
| GET | `/api/sleeper/rosters/<league_id>` | League rosters |
| GET | `/api/sleeper/league_users/<league_id>` | League members |
| GET | `/api/sleeper/players` | Bulk player payload |
| GET | `/api/sleeper/players/warm` | Hydrate player cache; returns `{ok, count}` |

## Players

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/players` | All players (filterable by `?position=`, projection via `?view=summary\|detail\|full`) |
| GET | `/api/players/<player_id>` | One player |
| GET | `/api/players/<player_id>/profile` | Player profile aggregate (#17): identity, consensus value + 7/30/90-day deltas + all-time extremes, caller's you-vs-market diff, zipped value history, recent appearances in the caller's suggestions. Session-authed; gated by `players.profile_pages` (404 when off). |
| GET | `/api/rookies` | Rookie list |

## Ranking — Trio

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/trio` | Next 3-player matchup |
| POST | `/api/trio/skip` | Skip current trio |
| POST | `/api/rank3` | Submit ordered (best→worst) result |
| POST | `/api/rankings/submit` | Bulk submit pre-computed rankings |
| POST | `/api/rankings/reorder` | Manually reorder ranks |
| GET | `/api/rankings` | Read current rankings. Each player may carry `consensus_pos_rank` (1-based rank within position by consensus seed value over the active format's universal pool) and `consensus_pos_rank_delta_30d` (30d movement of that rank vs. the oldest prior-day `player_value_history` snapshot in-window; positive = moved up). Both omit-when-absent — the delta is absent until snapshot history accrues (FB4-61 tile stats, 2026-07-10) |
| GET | `/api/skips` | Skipped matchups log |

## Progress / method

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/progress` | Per-position completion |
| GET | `/api/rankings/progress` | Same, alternate shape |
| POST | `/api/ranking-method` | Set ranking method (`trio` / `manual` / `tiers` / `anchor`). Since 2026-07-10 the mobile rank-home chooser + Settings steer slider record the user's preferred ranking flow here; launch routing itself is client-side (`useSession.rankingMethodPref`) |
| POST | `/api/scoring/switch` | Switch scoring format |

## Tiers

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/tiers/save` | Persist tiered roster |
| GET | `/api/tiers/status` | Tier completion status; returns `{saved, all_done, scoring_format}` (`scoring_format` added 2026-07-03, FB-76 — mobile re-buckets by it) |
| GET | `/api/tiers/community-diff` | Compare against community |
| GET | `/api/tiers/stability` | Tier stability indicator |
| POST | `/api/tiers/dismiss` | Dismiss a tier suggestion (writes `user_player_skips`) |
| GET | `/api/tier-config` | Shared tier band table (`backend/tier_config.json`); used by web to bucket players |
| POST | `/api/anchor/save` | Pick-anchor wizard (2026-07-10, mobile). Body `{player_id, anchor}`; `anchor` ∈ the cross-client enum `4_firsts, 3_firsts, 2_firsts, 1_first, 1_second, 1_third, 1_fourth, no_value` (see [cross-client-invariants.md](cross-client-invariants.md#pick-anchor-keys)). Pins the player's Elo to a pick-denominated value: single-pick anchors → that generic pick's Elo seed (`GENERIC_PICK_SEEDS`), N-firsts → N × value(Mid 1st) mapped back via `value_to_elo`, `no_value` → Elo 1100 (below every band → unranked). Position-uniform value by design; tier falls out of the band walk. Writes the same authoritative override as `/api/tiers/save`, persists via `save_tier_overrides`, publishes to `member_rankings`. Returns `{ok, player_id, anchor, elo, value, tier, scoring_format}` (`tier: null` = no value). 400 invalid anchor, 404 unknown player. |

## Trades

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/trades/generate` | Generate trade cards. Optional `pinned_give_players` ("what can I get for X") and, behind `trade.finder_targeting`, `pinned_receive_players` ("what does X cost") — pinned jobs bypass the cache. Cards may carry `partner_fit` (0–1 counterparty positional fit) when targeting is active, and `need_fit` (0–1 automatic positional-need fit, FB-96) when `trade.need_fit` is on |
| GET | `/api/trades/status` | Generation job status |
| GET | `/api/trades` | List current trade cards |
| POST | `/api/trades/swipe` | Like/pass a trade. Optional card-context fields (`give_player_ids`, `receive_player_ids`, `target_user_id`, `target_username`, `league_id`) let the server reconstruct the card after a restart wiped the in-memory deck (FB-46) |
| POST | `/api/trades/flag` | Flag a card as a **bad trade** (feedback #85) — engine-quality signal, distinct from pass; writes `bad_trade_flags` for operator review. Body: `give_player_ids` + `receive_player_ids` (required), optional `trade_id` (pulls live engine telemetry when it still resolves), `league_id` (defaults to session league), `target_user_id`/`target_username`, `reason` (≤500 chars), and client-echoed telemetry fallback (`mismatch_score`, `fairness_score`, `composite_score`, `need_fit`, `partner_fit`, `basis`). Idempotent per (user, league, give set, receive set): `201 {ok, flag_id, created_at, duplicate:false}` on insert, `200 {…, duplicate:true}` on re-flag |
| GET | `/api/trades/liked` | Trades the user liked |
| GET | `/api/trades/matches` | Mutual matches (current league) |
| GET | `/api/trades/matches/all` | Mutual matches across all leagues |
| GET | `/api/trades/awaiting` | Cross-league trades the user liked that haven't matured into a mutual match yet ("Awaiting them"); bare array, mirrors `/api/trades/matches/all` shape. One entry per underlying trade — repeat likes of the same give/receive sets across deck regenerations are deduped (#91) |
| POST | `/api/trades/matches/<match_id>/disposition` | Accept/decline a match (records an ELO signal). Re-sending the **same** decision is idempotent → `200 {ok, idempotent: true, both_decided, outcome}` with **no** `matches` key and no second ELO signal (feedback #77 — clients ≤1.3.0 render Accept/Decline on already-decided tiles); a **conflicting** decision → 409 |
| POST | `/api/trades/matches/<match_id>/dismiss` | Archive a match from the caller's inbox only — persisted, per-user, **ELO-neutral** (not a decline). Powers the mobile "Dismiss" CTA. 404 if the caller isn't a participant. |
| POST | `/api/trades/propose` | **Flagged beta** (`trade.send_in_sleeper`, default off). Send a built trade to Sleeper as a real proposal — see [Send in Sleeper](#send-in-sleeper-flagged-beta) |

**Deck order is not strictly score-sorted.** With `trade.thompson_deck` on (prod default), the returned card order is Thompson-sampled (bounded 0.5–1.5× multiplier on `composite_score`) and `trade.deck_diversity` can demote league-saturated targets — so order is intentionally stochastic and varies run-to-run. Clients must not assume `cards[0]` is the strict `composite_score` max. With both flags off the deck is composite-sorted descending (TC-ENG-001 / TC-E2E-001).

### Trade card object

Shape of each card in `/api/trades`, `/api/trades/status` snapshots, and `/api/trades/liked` (serialized by `trade_card_to_dict` in `backend/server.py`):

```
{
  "trade_id":        "8-char id",
  "league_id":       "...",
  "target_username": "...",
  "give":            [ player, ... ],          // player objects, user's give side
  "receive":         [ player, ... ],
  "mismatch_score":  float,                    // v2: harmonic mean of the two sides' surpluses
  "fairness_score":  float,                    // 0–1, ALWAYS serialized; clients render as a percent meter
  "composite_score": float,
  "basis":           "divergence" | "consensus",  // consensus = opponent has no real rankings
  "decision":        "like" | "pass" | null,
  "expires_at":      "...",
  "likes_you":       true,                     // OPTIONAL — present only when true (counterparty
                                               // pre-liked the mirror trade); absent otherwise
  "sweetener":       { "player_id": "...",     // OPTIONAL — Tier 3 (trade_engine.v3): low-value
                       "side": "give"|"receive" }, // asset already in give/receive, added to balance
  "reasons":         [ "...", ... ],           // optional, flag trade_math.human_explanations
  "narrative":       "...",                    // optional templated rationale
  "match_context":   { ... }                   // optional roster-fit context
}
```

Notes:
- `fairness_score` is true consensus fairness in `[0, 1]` (lesser/greater package-value ratio). Mobile and web both multiply by 100 for the fairness meter — see [cross-client-invariants.md](cross-client-invariants.md).
- `basis: "consensus"` cards are fair-by-consensus ideas generated for opponents with no rankings; clients show the "Fair-value idea" label.
- The job snapshot additionally sets `real_opponent` (bool) and `outlook` per card.

## Open trade calculator (public — no auth)

Backlog #27. The consensus-only sibling of the (session-authed) trade engine: it prices two asset-id lists on **pure consensus values** (`elo_to_value` over the universal-pool seed) — **no session, no league, no user Elo, no DB write**. Powers the public `web/calculator.html` SEO landing page. Both routes are gated by the `calc.open_calculator` flag (404 when off; default false).

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/calc/score` | **Public.** Score two asset lists on consensus values for one format. Returns give/receive package values + a backlog #6 `verdict`. |
| GET | `/api/calc/values` | **Public.** Consensus value map `{player_id: value}` for `?format=` so the picker can show a value per row before scoring. ETag + `Cache-Control: public, max-age=300`. |

## Manual trade calculator (public — no auth) — LIVE

The mobile Trade Calculator's server side ([docs/plans/manual-trade-calculator-plan.md](plans/manual-trade-calculator-plan.md)). Same consensus basis as backlog #27 above but implemented and unflagged; when the staged #27 web routes land, consolidate the two surfaces onto one contract (they price identically — both are `elo_to_value` over the universal-pool seed).

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/trade/evaluate` | Dual-mode. **Mode A (public):** consensus values + fairness verdict for a hand-built trade. Body `{give_player_ids, receive_player_ids, scoring_format?, fairness_threshold?}` (≤6 ids/side; unknown ids dropped, reported in `dropped_player_ids`). Reuses `trade_optimizer._consensus_packages`/`_fairness_v3` (confidence=None → point-ratio gate). Returns `{give_value, receive_value, point_ratio, fairness, verdict: even\|fair\|unfair, favors, per_player, basis: "consensus", ...}`. One-sided → `verdict: null`. **Mode B (in-league — add `{league_id, opponent_user_id}`, requires a session):** prices each side by the caller's AND the opponent's real rankings (`member_rankings`), adding `{basis: divergence\|consensus, opponent_has_rankings, your_value_delta, their_value_delta, mutual_gain, your_/their_give_/receive_value}`. Unranked opponent → `basis: "consensus"`. This is the finder's mutual-gain math on one fixed package. **`gap` (2026-07-10):** when both sides have a valued asset, the response includes `gap: {value, add_to: give\|receive\|null, firsts, pick_equivalent: {pick_id, label, value}\|null}` — the consensus package delta expressed in generic-pick terms (`firsts` = gap in units of a Mid 1st; `pick_equivalent` = nearest single generic pick, null when the gap is negligible (< ½ a Mid 4th) or bigger than any single pick). `add_to` is the LIGHTER side (the one needing the sweetener). One-sided → `gap: null`. |
| GET | `/api/trade/values` | **Public.** Universal-pool player list with consensus values for `?scoring_format=` — `{players: [{id, name, position, team, age, value}]}` sorted value-desc, for pickers + client-side suggestion search. ETag + `Cache-Control: public, max-age=300`. |

## Send in Sleeper (flagged beta)

⚠️ **ToS-adverse** — reproduces Sleeper's *undocumented* private write API. Gated everywhere by `trade.send_in_sleeper` (default **false**; 404 when off). The user's Sleeper token is a full-account credential, stored **encrypted** (`sleeper_credentials` table, Fernet via `SLEEPER_TOKEN_KEY`) and never logged. Capture + rationale: [docs/plans/sleeper-write-capture-runbook.md](plans/sleeper-write-capture-runbook.md). Backend: `backend/sleeper_write.py` (adapter) + routes in `backend/server.py`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sleeper/link` | Store a freshly captured Sleeper JWT (`{token}`) encrypted. Validates it is an unexpired JWT; extracts `sleeper_user_id` + `exp`. → `{connected, sleeper_user_id, expires_at}` |
| GET | `/api/sleeper/link` | Link status (never returns the token): `{connected, sleeper_user_id, expires_at, expired}` |
| DELETE | `/api/sleeper/link` | Disconnect — deletes the stored token → `{connected: false}` |
| POST | `/api/trades/propose` | Send a trade. Body `{league_id, their_user_id (or their_roster_id), give_player_ids[], receive_player_ids[], draft_picks?[]}`. Server resolves **both** roster_ids from one public-rosters fetch (caller's from the linked Sleeper account, counterparty's from `their_user_id` — FTF user_id == Sleeper user_id); the client never asserts its own roster_id. → `{status: "proposed", transaction_id}` |

`/api/trades/propose` error contract (client maps these to a reconnect prompt / deep-link fallback):

| Status | `error` | Meaning |
|---|---|---|
| 404 | `feature_disabled` | Flag off |
| 409 | `sleeper_not_linked` | No stored token → prompt the webview login |
| 409 | `sleeper_expired` | Token time-expired → cleared server-side → prompt reconnect (a fresh token fixes it) |
| 409 | `sleeper_rejected` | Sleeper's write API rejected the (valid-shape) token — 401/403 or auth GraphQL error; cleared server-side. Carries `detail`. Reconnecting re-captures the SAME token, so the client must NOT loop to login — surface the reason. |
| 503 | `sleeper_unconfigured` | `SLEEPER_TOKEN_KEY` unset/invalid |
| 502 | `sleeper_write_failed` | Sleeper accepted auth but the write failed (non-auth). Carries `kind` + `detail`. |
| 400 | `bad_request` / `roster_not_found` / `opponent_roster_not_found` | Malformed body / caller or counterparty not in that league |

**v1 scope:** players (+ FAAB) only; draft picks are accepted only pre-encoded as `"orig,season,round,from,to"` strings.

**`POST /api/calc/score`** — body `{give_player_ids: [...], receive_player_ids: [...], scoring_format?: "1qb_ppr"|"sf_tep"}`. At least one side must be non-empty (both empty → 400). Unknown format falls back to `1qb_ppr`. Response:

```
{
  "scoring_format": "1qb_ppr",
  "give_value":     5240.0,        // package_value_v2 over consensus values (trade-wide v_max)
  "receive_value":  4760.0,
  "verdict":        { "band": "slight", "favored": "you", "gap_value": 480, "gap_pct": 9.2 },
  "give":           [ { "player_id", "name", "position", "team", "value" }, ... ],
  "receive":        [ ... ],
  "unknown_ids":    [ ]            // ids not in the pool for this format (dropped, never silently 0)
}
```

Verdict math is `trade_service.classify_verdict(give_value, receive_value)` (no `fix`/sweetener on the public path); `favored` is from the page-user's view (`receive_value > give_value` → `"you"`). Bands read the same `verdict_*` `model_config` keys as in-app trade cards, so the public calc and a logged-in consensus card agree on the same trade. Errors: `400` (both sides empty / malformed), `404` (flag off), `503` (universal pool not yet built — client retries).

## League

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/leagues` | User's leagues |
| GET | `/api/league/picks` | Draft picks in current league |
| GET | `/api/league/preferences` | Read outlook + position prefs. When `trade.outlook_seed` is on and no outlook is declared, adds `inferred_outlook` + `inferred_signals` (#8) |
| POST | `/api/league/preferences` | Write outlook + position prefs |
| GET | `/api/league/asset-prefs` | Read untouchables + targets (#2) → `{untouchables:[], targets:[]}` |
| POST | `/api/league/asset-prefs` | Tag a player: body `{league_id, player_id, list: "untouchable"\|"target"\|"none"}`; single membership; invalidates the league's cached deck (#2) |
| GET | `/api/league/summary` | League summary roll-up. Match tiles (#91): `matches_mutual` (non-dismissed `trade_matches` rows involving the caller, any status — equals the Matches tab's "Mutual matches" segment for the league) + `matches_awaiting` (caller's one-sided likes not yet matured — equals "Awaiting them"). Every trade is in exactly one bucket. Legacy `matches_pending`/`matches_accepted` (status-split, dismissal-blind) still emitted for pre-1.4 clients — do not use in new UI. `total_teams` (FB #41): TOTAL teams in the league, caller included — Sleeper's `total_rosters` when persisted, else `leaguemates_total + 1`; clients must show this in the teams tile, not a derived count |
| POST | `/api/league/scoring` | Set scoring format |
| GET | `/api/league/coverage` | Member ranking coverage |
| GET | `/api/league/member-unlock-states` | Per-member unlock badges |
| GET | `/api/league/members` | League member roster + invite metadata (League Summary "Leaguemates Joined") |
| GET | `/api/leaderboard` | League + Universal leaderboards (rendered inside the League tab) |
| GET | `/api/league/activity` | Activity feed |
| GET | `/api/league/contrarian` | Contrarian rankings within league |
| GET | `/api/league/format-stats` | Scoring format breakdown |
| POST | `/api/league/parse-url` | Parse a Sleeper league URL |

## Notifications

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/notifications` | Inbox |
| POST | `/api/notifications/read` | Mark one read |
| POST | `/api/notifications/read-all` | Mark all read |
| POST | `/api/notifications/register-device` | Register Expo push token (writes `device_tokens`) |
| GET | `/api/notifications/prefs` | Read push preferences (`notification_prefs`) |
| PUT | `/api/notifications/prefs` | Update push preferences (buckets + quiet hours) |

## Cron ticks

Triggered by an external scheduler (Render cron). All POST.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/cron/realtime-tick` | Real-time event hook drains (queued pushes ready to deliver) |
| POST | `/api/cron/hourly-tick` | Hourly bundle drain + quiet-hours summary push at user's local 8am |
| POST | `/api/cron/daily-tick` | Daily digests + re-engagement scans |
| POST | `/api/cron/value-snapshot` | Daily consensus value snapshot → `player_value_history` (#57). Dedicated (not in daily-tick) so a push-scan bug can't stop history collection. Idempotent per UTC day. |

## Trends

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/trends/risers-fallers` | Risers/fallers (uses `elo_history`) |
| GET | `/api/trends/contrarian` | Contrarian movers |
| GET | `/api/trends/consensus-gap` | Gap from consensus |

## Profiles + Sharing

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/portfolio` | User's cross-league exposure. Optional `?league_ids=a,b,c` (FB-48) scopes to the caller's current-season leagues — Sleeper mints a new league_id per season, so unscoped queries double-count carried-over players |
| GET | `/u/<username>` | Public profile page |
| GET | `/api/profile/<username>` | Profile JSON |
| GET | `/og/tiers/<pos>/<username>.png` | OG image (tiers) |
| GET | `/og/trade/<match_id>.png` | OG image (trade) |
| GET | `/s/tiers/<pos>/<username>` | Share page (tiers) |
| GET | `/s/trade/<match_id>` | Share page (trade) |

## Extension

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/extension/rankings` | Pull current rankings for the extension |

## Feature flags

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/feature-flags` | Read flags |
| POST | `/api/feature-flags/reload` | Reload from `config/features.json`. **Auth: X-Cron-Secret** |

## Admin

All routes in this section require the `X-Cron-Secret` header (see `CRON_SECRET` in [config-reference.md](config-reference.md)); unauthenticated calls return 401 (or 503 if the secret is unset in a prod env).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/config` | Read all `model_config` entries. **Auth: X-Cron-Secret** |
| PUT | `/api/admin/config/<key>` | Update one `model_config` value (hot-reloads ranking + trade math). **Auth: X-Cron-Secret** |
| GET | `/api/admin/engine-metrics` | Trade-engine telemetry: like/pass rates by basis, likes-you, deck position, shape, league; match conversion (`?days=30&league_id=`). **Auth: X-Cron-Secret** |
| PUT | `/api/feedback/admin/<id>/status` | Operator update for a feedback note: `status` (`new\|planned\|in_progress\|fixed\|shipped\|declined`) and/or `severity` (`bug\|polish\|idea`). **Auth: X-Cron-Secret** |
| GET | `/api/trades/flags/admin` | Operator readback of bad-trade flags (`?since_id=N&limit=M`, max 500) → `{items, count, next_since_id}` — same paging contract as `/api/feedback/admin`. **Auth: X-Cron-Secret** |
| GET | `/api/debug/log` | Last N debug ring-buffer entries (`?n=100`). **Auth: X-Cron-Secret** |

## Misc

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serve `web/index.html` |
| GET | `/api/invite/impact` | Invite-program impact stats |
| GET | `/api/me/streak` | Current user's daily-activity streak |

## In-app feedback

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/feedback` | Capture a single feedback note from the mobile FeedbackSheet. Idempotent on `client_id`. |
| GET | `/api/feedback/mine` | The caller's own notes with operator-set lifecycle status (session auth). Backs the status chips in the mobile feedback inbox. Strictly scoped to the session's `user_id` (anonymous/NULL-user notes never returned). Closed notes (`shipped`/`declined` — `FEEDBACK_CLOSED_STATUSES`) are excluded as of 2026-07-04; `fixed` stays visible until it ships. Admin readback is unaffected. |

**Body** (JSON):

```
{
  "client_id":         "<mobile local id>",
  "screen":            "Trades",
  "severity":          "bug" | "polish" | "idea",
  "text":              "free text 1..2000 chars",
  "client_created_at": "2026-05-21T03:14:15Z"
}
```

**Responses:**
- `201 Created` — new row inserted; `{ ok, server_id, created_at, duplicate: false }`
- `200 OK` — `client_id` already exists; `{ ok, server_id, created_at, duplicate: true }`
- `400` — `{ error: "missing_field" | "invalid_severity" | "text_too_long" }`

Auth is best-effort. `X-Session-Token`, when present, attributes the row to the matching `user_id` + `username`; when absent the row stores `user_id = null` (anonymous submission allowed).

Stores into `app_feedback` (see data-dictionary). The mobile client also retains a local AsyncStorage copy and re-POSTs unsynced items on app foreground.

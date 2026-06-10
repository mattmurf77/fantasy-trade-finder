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
| GET | `/api/rookies` | Rookie list |

## Ranking — Trio

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/trio` | Next 3-player matchup |
| POST | `/api/trio/skip` | Skip current trio |
| POST | `/api/rank3` | Submit ordered (best→worst) result |
| POST | `/api/rankings/submit` | Bulk submit pre-computed rankings |
| POST | `/api/rankings/reorder` | Manually reorder ranks |
| GET | `/api/rankings` | Read current rankings |
| GET | `/api/skips` | Skipped matchups log |

## Progress / method

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/progress` | Per-position completion |
| GET | `/api/rankings/progress` | Same, alternate shape |
| POST | `/api/ranking-method` | Set ranking method (`trio` / `manual` / `tiers`) |
| POST | `/api/scoring/switch` | Switch scoring format |

## Tiers

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/tiers/save` | Persist tiered roster |
| GET | `/api/tiers/status` | Tier completion status |
| GET | `/api/tiers/community-diff` | Compare against community |
| GET | `/api/tiers/stability` | Tier stability indicator |
| POST | `/api/tiers/dismiss` | Dismiss a tier suggestion (writes `user_player_skips`) |
| GET | `/api/tier-config` | Shared tier band table (`backend/tier_config.json`); used by web to bucket players |

## Trades

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/trades/generate` | Generate trade cards |
| GET | `/api/trades/status` | Generation job status |
| GET | `/api/trades` | List current trade cards |
| POST | `/api/trades/swipe` | Like/pass a trade. Optional card-context fields (`give_player_ids`, `receive_player_ids`, `target_user_id`, `target_username`, `league_id`) let the server reconstruct the card after a restart wiped the in-memory deck (FB-46) |
| GET | `/api/trades/liked` | Trades the user liked |
| GET | `/api/trades/matches` | Mutual matches (current league) |
| GET | `/api/trades/matches/all` | Mutual matches across all leagues |
| POST | `/api/trades/matches/<match_id>/disposition` | Accept/decline a match |

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

## League

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/leagues` | User's leagues |
| GET | `/api/league/picks` | Draft picks in current league |
| GET | `/api/league/preferences` | Read outlook + position prefs |
| POST | `/api/league/preferences` | Write outlook + position prefs |
| GET | `/api/league/summary` | League summary |
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
| POST | `/api/feature-flags/reload` | Reload from `config/features.json` |

## Admin

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/config` | Read all `model_config` entries |
| PUT | `/api/admin/config/<key>` | Update one `model_config` value |
| GET | `/api/admin/engine-metrics` | Trade-engine telemetry: like/pass rates by basis, likes-you, deck position, shape, league; match conversion (`?days=30&league_id=`) |
| GET | `/api/debug/log` | Last N debug ring-buffer entries (`?n=100`) |

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

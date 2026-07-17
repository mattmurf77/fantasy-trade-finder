# API Reference

All routes live in `backend/server.py`. Same-origin from web; mobile + extension hit the deployed host. Keep this file in sync when adding/renaming/removing routes.

Auth: session cookie via `/api/session/init`. Extension uses a bearer token from `/api/extension/auth`.

---

## Session / Auth

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/session/init` | Establish session for a Sleeper username. Response includes the additive `verification` field (below) |
| GET | `/api/session/ping` | Liveness / session check |
| POST/GET | `/api/session/demo` | Demo session bootstrap |
| POST | `/api/extension/auth` | Issue extension bearer token |
| POST | `/api/reset` | Wipe current user's rankings + decisions (in-memory service state) |
| POST | `/api/account/reset-rankings` | **Verified-only** (403 `verification_required`, no grace). Squatter remedy (account-auth P1 §2d): deletes the caller's persisted ranking inputs across all formats — `swipe_decisions`, published `member_rankings`, `users.tier_overrides`/`tiers_saved`/`ranking_method` — and resets this session's in-memory services. → `{ok, counts}`. UI entry point ships with P2's Settings account section |

### Verified sessions & the write gate (account-auth P1)

A session is **verified** when the app captured a Sleeper JWT whose `user_id` claim matches the session's user **and** the token was proven live against Sleeper's authenticated GraphQL API (`sleeper_write.verify_token_live` — Sleeper is the signature oracle, since the JWT's HS256 signature can't be checked locally). Verification happens in `POST /api/sleeper/link`; it stamps `sess["verified"]` and persists `users.verified_at`/`verified_via='sleeper'` (shared with P2's Apple/Google anchors).

Every mutating user route (`rank3`, `reset`, `rankings/reorder`, `rankings/submit`, `tiers/save|copy-from-format|dismiss`, `anchor/save|scale`, `ranking-method`, `scoring/switch`, `trades/swipe|generate|flag`, `trades/matches/*/dismiss|disposition`, `league/preferences|asset-prefs|scoring`, `notifications/read|read-all|register-device|prefs`, `feedback`, `sleeper/link` DELETE) runs the gate (`@_gate_unverified_write`):

| Caller | Result |
|---|---|
| Verified session | allow |
| Unverified, user_id has a verified controller (`users.verified_via` set) | **403 `{error: verification_required}`** — first-verified-controller-wins, even during grace |
| Unverified, no controller, grace (`auth.enforce_verified_writes` false) | allow + one `AUTH-GRACE` log line (runbook monitors the funnel) |
| Unverified, no controller, enforcement on | **403 `verification_required`** |

Hard-verified regardless of grace: `POST /api/sleeper/link` (carries its own proof — see Send in Sleeper below), `POST /api/trades/propose`, `POST /api/account/reset-rankings`.

### The read gate (account-auth P2.5 — read privacy)

"Ranks hidden behind an account" (#102) covers reads too: the write gate alone still let a username-only session *view* the victim's board. Board-content READ routes run `@_gate_unverified_read`, which mirrors **only** the write gate's verified-controller branch:

| Caller | Result |
|---|---|
| Verified session | allow |
| Unverified, user_id has a verified controller (`users.verified_via` set) | **403 `{error: verification_required}`** — no grace: the owner has proven control, squatters get nothing (`AUTH-DENY unverified_read` log line) |
| Unverified, no controller | allow — onboarding users must see their own board, so `auth.enforce_verified_writes` is deliberately **not** consulted for reads |

**Gated reads** (the user's own board / board-derived content): `GET /api/rankings`, `/api/progress`, `/api/rankings/progress`, `/api/me/streak`, `/api/tiers/status`, `/api/tiers/community-diff`, `/api/tiers/stability`, `/api/anchor/scale` (GET side; POST side keeps the write gate), `/api/trades`, `/api/trades/status`, `/api/trades/liked`, `/api/trades/matches`, `/api/trades/matches/all`, `/api/trades/awaiting`, `/api/league/preferences` (GET), `/api/league/asset-prefs` (GET), `/api/league/free-agents` (priced by the caller's board — #143), `/api/feedback/mine`, `/api/notifications`, `/api/trends/risers-fallers`, `/api/trends/contrarian`, `/api/trends/consensus-gap`, `/api/extension/rankings`, plus **Mode B of `POST /api/trade/evaluate`** (gated inline — it prices by the caller's board; Mode A stays public).

**Deliberately left open** (documented decisions, not omissions): `/api/trade/values` + `/api/trade/evaluate` Mode A (public calculator by design), `/api/tier-config` (global band table, no user data), `/api/leaderboard` (community content; `is_self` tagging only), `/api/trio` + `/api/skips` (onboarding surface — the trio/skip list doesn't expose the board's ordering), `/api/portfolio` (Sleeper-public roster exposure, no Elo), `/api/leagues`, `/api/league/summary` (counts of the caller's matches, no content), `/api/league/coverage|members|member-unlock-states|activity|contrarian|format-stats` (league-shared aggregates by design), `/api/notifications/prefs` GET (settings toggles, not board content), `/api/session/init` + `/api/session/ping` + `/api/sleeper/link` GET (must work for unverified sessions — they drive the verify prompt itself), `/og/*`, `/s/*`, `/u/*`, `/api/profile/*` (public share surfaces by explicit product design).

**Client contract:** the mobile API client (`mobile/src/api/client.ts`) treats any 403 `verification_required` as a central signal — it flips `useSession.verification` so the existing `VerifyAccountBanner` appears; gated screens' load-error states show "Verify your account to view your data." **Known limitation:** web + extension clients have no verification flow yet, so once an owner verifies on mobile, their own username-only web/extension sessions read-403 until those clients grow a capture path (same asymmetry the write gate already has).

`/api/session/init` response — additive field:

```
"verification": {
  "session_verified": false,   // THIS session proved control
  "user_verified":    false,   // some controller has verified this user_id
  "verified_via":     null,    // 'sleeper' | 'apple' | 'google' | null
  "enforced":         false    // auth.enforce_verified_writes (grace over)
}
```

## Account auth (identity anchors — `auth.accounts` flag, ships dark)

Account-auth plan P2 + P2.6 account-first (docs/plans/account-auth-plan-2026-07-11.md). Logic in `backend/accounts.py`; routes are thin wrappers. **P2.6:** the account is the primary identity — an account with no linked Sleeper source works under the synthetic key `acct_<account_id>` (rank/tiers/anchors fully functional; league features empty until a source is linked).

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/apple` | Verify a Sign in with Apple identity token (JWKS RS256 + iss + aud=`com.fantasytradefinder.app` + exp). Find-or-create the account, then: with a session → bind the session's Sleeper user + mark session `verified_via='apple'`; no session + bound account → device-loss restore (returns `session_token`); no session + new account → **account-first (P2.6)**: mints an account-keyed session — `{account_only:true, session_token, user_id:"acct_<account_id>", league_id:"no_league"}` — with per-format ranking services and a real EMPTY league (never the demo fallback). Optional body `display_name` (Apple sends the name only to the client, first auth only). Binding is sticky — a session for a different user gets `conflict:true`, never a rebind; `acct_*` keys are never bound as Sleeper sources. 404 while flag off. |
| POST | `/api/auth/google` | Same flow, Google JWKS + `GOOGLE_OAUTH_CLIENT_ID` as `aud`. 503 `not_configured` until that env var is set. 404 while flag off. |
| GET | `/api/account` | Current account: `{sleeper_user_id, verified_via, account: {account_id, sleeper_user_id, identities:[{provider, linked_at}]} \| null, account_only, sleeper_username}`. 404 while flag off. |
| POST | `/api/account/link-sleeper` | **P2.6.** Link a Sleeper username as a source on the session's account. Body `{username, strategy?}`; requires `sess.account_id` (400 `no_account`). Rules: sticky binding (409 `sleeper_conflict` if bound elsewhere); **first-verified-wins** — target id already has a verified controller → 403 `sleeper_already_claimed`, no takeover; both boards have data and no `strategy` → 409 `merge_choice_required` + `{account_board, sleeper_board}` summaries; `strategy='keep_sleeper'` wipes the account board, `'keep_account'` wipes the Sleeper board and migrates the account board in; account-board-only → migrated automatically. On success: binds, marks the Sleeper user `verified_via=<provider>`, evicts the `acct_*` sessions, returns a fresh session for the Sleeper user `{session_token, user_id, username, merge}`. 404 while flag off. |
| DELETE | `/api/account` | **In-app account deletion (App Store 5.1.1(v)) — NOT flag-gated.** Deletes/anonymizes per the matrix in `accounts.delete_user_data` (honors `web/privacy.html` §6): own rows deleted; shared rows (trade matches, others' impressions/flags naming this user) anonymized so counterparties keep their records; feedback anonymized; non-user-keyed aggregates kept. If `users.verified_via` is set, the calling session must itself be verified (403 `verification_required` otherwise). Evicts all of the user's live sessions. |

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
| GET | `/api/rankings` | Read current rankings. Each player may carry `consensus_pos_rank` (1-based rank within position by consensus seed value over the active format's universal pool) and `consensus_pos_rank_delta_30d` (30d movement of that rank vs. the oldest prior-day `player_value_history` snapshot in-window; positive = moved up). Both omit-when-absent — the delta is absent until snapshot history accrues (FB4-61 tile stats, 2026-07-10). Each player may also carry ONE of `tradeability` / `acquirability` (0–1 tile trade meters, TestFlight #71, 2026-07-10): tradeability on players the user owns in the session's league (gap vs community-mean Elo), acquirability on leaguemate-owned players (gap vs that owner's Elo, community-mean fallback); scaling `clamp01(0.5 + gap/800)` via `trends_service.compute_tile_trade_scores`. Omitted when there's no basis: demo/no league, < 3 community rankers, free agent, or owned player absent from the community pool |
| GET | `/api/skips` | Skipped matchups log |

## Progress / method

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/progress` | Per-position completion |
| GET | `/api/rankings/progress` | Same, alternate shape |
| POST | `/api/ranking-method` | Set ranking method (`trio` / `manual` / `tiers` / `anchor` / `quickset`). Since 2026-07-10 the mobile rank-home chooser + Settings steer slider record the user's preferred ranking flow here; launch routing itself is client-side (`useSession.rankingMethodPref`). `quickset` (#119, 2026-07-12) unlocks like `tiers` in `/api/progress` |
| POST | `/api/scoring/switch` | Switch scoring format |

## Tiers

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/tiers/save` | Persist tiered roster. Body `{position, tiers: {<tier_key>: [pids]}, cleared_pids}`; tier keys are the 8-tier pick-value ladder enum `firsts_4plus, firsts_3, firsts_2, first_1, second, third, fourth, waivers` (2026-07-12 #117 — see [cross-client-invariants.md](cross-client-invariants.md); unknown/retired keys no-op) |
| POST | `/api/tiers/copy-from-format` | Value-aware cross-format board copy (2026-07-17, #124/#139). Body `{from_format}` (+optional `to_format`; target defaults to the active format, `X-Scoring-Format` honoured). Keeps the user's per-position **rank order** from the source board but re-seeds each player's Elo from the **target format's consensus seed curve** at that rank (`RankingService.apply_value_map` — a permutation of the copied group's own target-format seeds), so the pick-denominated tier labels re-price to the target format — QBs shift most between SF and 1QB, by design. (Previously the copy preserved tier labels verbatim, which overvalued QBs on SF→1QB and undervalued them on 1QB→SF — #124.) Wholesale-replaces the target format's overrides; deterministic and idempotent for an unchanged source board; a copied player may land below the target waivers floor and render unranked. Returns `{ok, from_format, to_format, mapping: 'value_rank', position_counts: {pos: N}, total}` (`mapping` is new/additive). 400 on invalid/equal formats or empty source. Tests: `backend/tests/test_copy_from_format.py` |
| GET | `/api/tiers/status` | Tier completion status; returns `{saved, all_done, scoring_format}` (`scoring_format` added 2026-07-03, FB-76 — mobile re-buckets by it) |
| GET | `/api/tiers/community-diff` | Compare against community |
| GET | `/api/tiers/stability` | Tier stability indicator |
| POST | `/api/tiers/dismiss` | Dismiss a tier suggestion (writes `user_player_skips`) |
| GET | `/api/tier-config` | Shared tier band table (`backend/tier_config.json`); used by web + mobile to bucket players. Returns `{tiers: [firsts_4plus, firsts_3, firsts_2, first_1, second, third, fourth, waivers], config: {fmt: {pos: {tier: {min, max}}}}}` — since 2026-07-12 (#117) the bands are the 8-tier pick-value ladder, identical across positions/formats |
| POST | `/api/anchor/save` | Pick-anchor wizard (2026-07-10, mobile). Body `{player_id, anchor}`; `anchor` ∈ the cross-client enum `4_firsts, 3_firsts, 2_firsts, 1_first, 1_second, 1_third, 1_fourth, no_value` (see [cross-client-invariants.md](cross-client-invariants.md#pick-anchor-keys)). Pins the player's Elo to a pick-denominated value: single-pick anchors → that generic pick's Elo seed (`GENERIC_PICK_SEEDS`), N-firsts → N × value(Mid 1st) mapped back via `value_to_elo` — re-spaced by the user's pick-value scale when one is set (#111, see `/api/anchor/scale`) — `no_value` → Elo 1100 (below every band → unranked). Position-uniform value by design; tier falls out of the band walk (since the pick-value ladder, every anchor lands in the tier carrying its name at the default scale). Writes the same authoritative override as `/api/tiers/save`, persists via `save_tier_overrides`, publishes to `member_rankings`. Returns `{ok, player_id, anchor, elo, value, tier, scoring_format, top_tier_firsts}` (`tier: null` = no value). 400 invalid anchor, 404 unknown player. |
| GET/POST | `/api/anchor/scale` | Per-user pick-value scale (1.5.4 #111, re-derived 2026-07-12 for #117): `{top_tier_firsts: 2\|3\|4}` = "a top-tier dynasty asset is worth N firsts". Persisted per user + scoring format (`users.anchor_scale`); default 4 (the #117-recalibrated consensus top asset sits at the 4-firsts rung) reproduces the plain `m × base` anchor math exactly. Recalibrates ONLY the wizard's multi-first anchors via a power curve (`m firsts → value(Mid 1st) × m^γ`, `γ = log 4 / log N` — exact at `m=1` (the actual Mid 1st) and at `m=N`, which pins to the default top-tier Elo ≈ 1927). Single-pick anchors, the generic pick pool assets, and the public `/api/trade/evaluate` `gap` line stay consensus-denominated. GET returns `{top_tier_firsts, scoring_format}`; POST body `{top_tier_firsts}` (400 unless ∈ {2,3,4}). |

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
  "match_context":   { ... },                  // optional roster-fit context
  "lane":            "window" | "value",       // OPTIONAL — flag trade.lanes; absent when the
                                               // user has no declared/seeded window
  "fit_premium":     { "value_paid": float,    // OPTIONAL — flag trade.fit_premium; honest flag on
                       "position": "WR" },     // a need-filling 1-for-1 that loses a little raw value
  "aggression_variant": "light"|"fair"|"generous"  // OPTIONAL — flag trade.aggression_ab (A/B joins)
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
| POST | `/api/sleeper/link` | Store a freshly captured Sleeper JWT (`{token}`) encrypted — **and verify the session (account-auth P1)**. Requires the JWT's `user_id` claim to equal the session user (403 `token_user_mismatch`), then exercises the token once against Sleeper's authed GraphQL (`verify_token_live`, a no-op `__typename` query): Sleeper rejects it → 403 `token_rejected`, nothing stored; probe passes → session verified + `users.verified_via='sleeper'` persisted; probe unreachable (network/config) → link stores but `verified:false`. → `{connected, sleeper_user_id, expires_at, verified}` |
| GET | `/api/sleeper/link` | Link status (never returns the token): `{connected, sleeper_user_id, expires_at, expired}` |
| DELETE | `/api/sleeper/link` | Disconnect — deletes the stored token → `{connected: false}`. Standard write gate (grace applies) |
| POST | `/api/trades/propose` | Send a trade. **Hard-verified: requires a verified session (403 `verification_required`), no grace** — highest blast radius (writes into the user's real Sleeper league). Body `{league_id, their_user_id (or their_roster_id), give_player_ids[], receive_player_ids[], draft_picks?[]}`. Server resolves **both** roster_ids from one public-rosters fetch (caller's from the linked Sleeper account, counterparty's from `their_user_id` — FTF user_id == Sleeper user_id); the client never asserts its own roster_id. → `{status: "proposed", transaction_id}` |

`/api/trades/propose` error contract (client maps these to a reconnect prompt / deep-link fallback):

| Status | `error` | Meaning |
|---|---|---|
| 404 | `feature_disabled` | Flag off |
| 403 | `verification_required` | Session not verified (P1 hard gate) → route into the SleeperConnect capture, which verifies in one login |
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
| GET | `/api/league/power-rankings` | League power rankings (#142/#144): every team ranked by summed roster value. Query `league_id` (default: session league) + `basis`: **`consensus`** (default — universal-pool values, the same numbers as `/api/trade/values`; league-shared aggregate, open like `/api/league/coverage`) \| **`personal`** (the CALLER's live board for the active format, consensus fallback for unranked players; board-derived → P2.5 read gate applied inline, like `/api/trade/evaluate` Mode B) \| **`redraft`** (**501 `not_available`** — FTF's value source is dynasty-only; parameter reserved, clients render a disabled "(soon)" chip). → `{league_id, basis, scoring_format, teams:[{rank, user_id, username, display_name, is_you, total_value, positions:{QB\|RB\|WR\|TE:{count,value}}, roster:[{player_id,name,position,team,age,value}]}]}` — teams sorted `total_value` desc (user_id asc tiebreak, deterministic); each `roster` grouped QB→RB→WR→TE→other, value-desc within group, so the client's team drill-in needs no second call. Out-of-pool players (K/DEF, deep stashes) contribute value 0. ESPN-imported leagues work unchanged (synthetic `espn:` member ids carry crosswalked Sleeper player ids). Math: `backend/power_rankings.py` |
| GET | `/api/league/free-agents` | Free-agent finder (#143). Query `league_id` (default: session league) + optional `position` (QB\|RB\|WR\|TE\|ALL). FA pool = active format's universal pool minus every rostered player in the league (session-league rosters when `league_id` matches the session — Sleeper / ESPN-imported / demo alike; `league_members` snapshot otherwise), ranked by the **caller's board value** (personal Elo, consensus seed fallback per unranked player; `user_has_rankings:false` = whole list is consensus). Top 50 rows after the position filter: `{player_id, name, position, team, age, value, pos_rank, drop_suggestion}` — `pos_rank` is within-position across ALL FAs (stable under filters); `drop_suggestion` = the caller's lowest-valued same-position rostered player whose value is strictly below the FA's (`{player_id, name, position, value, delta}`, `delta` = FA value − drop value; `null` when no such player). Read-gated (`@_gate_unverified_read`) — priced by the caller's board |
| POST | `/api/league/parse-url` | Parse a Sleeper league URL |

## ESPN league linking (flag `espn.link`)

Read-only import of ESPN Fantasy leagues via the community-reverse-engineered v3 API ([plan](plans/espn-league-linking-plan-2026-07-11.md)). Gated everywhere by `espn.link` (default **false**; every route 404s `feature_disabled` when off). Rosters are crosswalked to **Sleeper player ids** at import (`backend/espn_service.py`, DynastyProcess `db_playerids.csv`, 24h-TTL cache with bundled-snapshot fallback); unmatched players are skipped and reported by name — never placeholder-invented. Private-league cookies (`espn_s2`+`SWID`, manual paste; WebView capture is Phase 1b) are Fernet-encrypted at rest (`espn_credentials`, same `SLEEPER_TOKEN_KEY`). No ESPN write path exists or is planned.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/espn/link` | Body `{espn_league_id, season?, team_id?, espn_s2?, swid?}`. Without `team_id` → **preview**: `{status:"choose_team", league, teams:[{team_id,name,owner_display,mapped_players}], report}` — nothing persisted. With `team_id` → **import**: persists the league (`platform='espn'`) + full membership snapshot; the chosen team binds to the session `user_id`, counterparties get synthetic `espn:` ids. Idempotent re-link. → `{ok, league_id, name, season, auth, total_teams, teams_imported, my_team_id, my_roster, report}` |
| GET | `/api/espn/leagues` | Linked ESPN leagues for the session user, each with the full `members` snapshot (Sleeper player ids) — the client builds a standard `/api/session/init` body from this (ESPN leagues never touch the Sleeper roster proxies) |
| POST | `/api/espn/import` | Re-sync rosters for a linked league. Body `{league_id}`. Uses the stored auth mode (public / decrypted cookies); preserves the user's team binding. → same summary shape as link |

Error contract (shared): 404 `feature_disabled` (flag off) / `espn_league_not_found` (ESPN purged or wrong season) / `espn_not_linked` (import only) · 403 `espn_auth_required` (private league or expired cookies → paste fresh ones) · 400 `espn_bad_league_id` / `espn_bad_season` / `espn_bad_team_id` / `espn_cookies_incomplete` · 409 `espn_team_missing` (bound team left the league → re-link) · 502 `espn_unavailable` · 503 `espn_unconfigured` (encryption key missing). The `report` field carries `{pool_players, matched_by_id, matched_by_name, match_rate, out_of_pool, unmatched:[{name,position}]}` — K/D-ST count as `out_of_pool`, not failures. Mutating routes use the standard unverified-write gate (grace applies).

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
| GET | `/privacy` | Serve `web/privacy.html` (clean URL; App Store Connect privacy-policy URL) |
| GET | `/terms` | Serve `web/terms.html` (clean URL) |
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

## Test support (`FTF_TEST_MODE=1` only — never mounted in normal operation)

UI-test harness blueprint (`backend/test_support.py`, spec: `docs/plans/mobile-testing/lld.md` §4.3c). These routes 404 unless the backend was started in test mode, which itself startup-aborts without `FTF_SLEEPER_FIXTURES_DIR` + `FTF_PLAYERS_CACHE_FILE`. Under test mode, `POST /api/trades/propose` unconditionally fails closed with 599.

| Method | Path | Purpose |
|---|---|---|
| POST | `/__test__/fail_next` | Arm a response override: `{path (glob), status, count=1, body?}`. Any status incl. 2xx (precondition overrides) — except overrides matching `/api/trades/propose`, which refuse status <400 (propose can never be faked to success) |
| POST | `/__test__/latency` | `{path (glob), ms}` — delay matching requests until reset |
| POST | `/__test__/reset` | Clear injections + all in-memory sessions (`{"counters": true}` also zeroes guardrail counters — pytest only) |
| GET | `/__test__/whoami` | `{profile, test_mode, fixtures, active_injections, counters}` — the run report's guardrail source (`vcr_misses`, `sleeper_live_egress_attempts`, `propose_route_hits`, `completed_proposes`) |

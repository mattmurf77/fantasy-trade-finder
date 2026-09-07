# Team overhaul — v1 build contract

Date: 2026-09-07. Author: engineering scoping session (Claude). Status: **the binding contract for the v1 build.** Where this file and [ENGINEERING-SPEC.md](ENGINEERING-SPEC.md) differ, this file wins for v1; the engineering spec remains the long-form rationale and the target for later phases.

This revision exists because the engineering spec describes a complete execution platform (durable workers, leases, provider reconciliation adapters, withdrawal) that cannot be built and verified in one pass. v1 ships the **whole user flow** (entry → outlook → pool → targets → review → roadmaps → priorities → summary → send → resume) with a **narrow, honest execution layer**: Sleeper sends through the existing verified propose path, everything else is planning + manual handoff, and status is reconciled from ownership changes plus explicit user assertions. Nothing in v1 claims a provider capability it has not exercised.

## 0. Engineering decisions on the nine open choices

These adopt the product spec §8 *proposed defaults* as v1 engineering decisions. They are **not** owner approvals; they are recorded in `living-memory/DECISIONS.md` (D-321) as reversible.

| ID | v1 decision |
|---|---|
| D1 launch scope | iOS client only. Sleeper is the only platform that can **send** in v1 (`capabilities.canPropose = true` only for `platform == 'sleeper'` with a linked, verified credential). MFL and ESPN leagues get the full planning flow and a **copy-to-clipboard handoff** on the summary ("Send in MFL/ESPN" is not offered). Web and extension: no surface. |
| D2 draft-order rules | Copy states a draft-position benefit only as *possible* and names the rule as unknown (`draft_order_rule: 'unknown'`) unless the league payload carries a known rule. No specific slot is ever claimed. |
| D3 review completion | Complete-review flow. Generation batch size is `model_config`-free: constant `OVERHAUL_BATCH_SIZE = 24` in `overhaul_service.py`. "Build roadmaps" is enabled once every card in the current batch has a decision. |
| D4 same counterparty | Assembly prefers distinct counterparties (diversity penalty). Within one package tier, **at most one offer per counterparty** (server rejects the priorities write with `tier_duplicate_counterparty`). Two *different* packages may target the same counterparty only if the combined two-sided roster check passes. |
| D5 pending offers | Later tiers are held while any attempt in the package is `proposed` or `outcome_unknown`. No timeouts. The user may assert a decline/withdrawal (user-reported) to unblock. |
| D6 combined roster | Strict independence. No offer may depend on receiving an asset from another offer. Capacity is checked with the arithmetic worst case (see §5.4); lineup legality on the final union per counterparty. |
| D7 counteroffers | Platform-only negotiation in v1. Refresh shows ownership-derived outcomes; the user records a counter as a manual `declined` assertion and negotiates in the platform. No in-app counter promotion. |
| D8 refresh | Preserve completed and pending work. When ownership changes make an unsent offer's assets unavailable, that offer becomes `stale` and cannot be sent until regeneration; the roadmap is not regenerated automatically. |
| D9 resume entry | `OverhaulEntryCard` on the Acquire landing directly below `TeamReviewEntryCard`. One **active** overhaul per (account, league); starting a new one archives the previous only if it has no `proposed`/`outcome_unknown` attempts (else 409 `active_sends_exist`). |

## 1. Vocabulary (wire and code)

Use exactly these names in code, JSON, analytics and docs.

| Term | Wire name | Meaning |
|---|---|---|
| Overhaul | `overhaul` | The durable planning session (one row in `overhauls`). |
| Outlook | `outlook` | `push_all_in` \| `blow_it_up`. Evaluator adapter maps to existing utility semantics `championship` / `jets` respectively. |
| Eligible pool | `eligible_asset_ids` | Asset ids (player ids and FTF pick ids, mixed, same convention as `give_player_ids` everywhere else) the user permits to leave. |
| Offer | `offer` | One generated exchange with one counterparty. `offer_id` is server-minted (`ovh_` + 12 hex). |
| Decision | `decision` | `like` \| `pass` \| `undecided` per offer. |
| Package | `package` | A fixed outgoing asset set inside one roadmap plus its liked alternatives. Wire key `packages[]`; product copy "Package N of M". (Engineering spec calls this "sell group"; the wire uses `package`.) |
| Tier | `tier` | Integer priority rank ≥ 1 inside a package. Same tier = sends together (race). |
| Roadmap | `roadmap` | One alternative full plan; `roadmap_id` = `rm_` + 12 hex; `version` increments on every priorities write. |
| Attempt | `attempt` | One send attempt of one offer inside one batch. |
| Batch | `batch` | The set of attempts created by one confirmed send. |

Asset id conventions are unchanged from the rest of the app: a player id is the Sleeper player id string; an owned pick id is `{league_id}_{season}_{round}_{original_roster_id}` (`draft_picks.pick_id`). Generic pick rungs (`generic_pick_*`) are **never** valid in an overhaul (400 `generic_pick_not_allowed`).

## 2. Feature flag, analytics, config

- **Flag** `overhaul.enabled` — default `false` in `config/features.json`, added to `FLAG_KEYS` and every fixture the mirror test checks. Gates: the entry card (mobile), `POST /api/overhauls`, `/generate`, `/assemble`, `/send`. **Not gated** (so live sends stay reachable after a rollback): `GET` routes, `/decisions`, `/priorities`, `/prepare-send`, `/refresh`, `/attempts/{id}/status`. Graduation criterion: operator TestFlight checklist in [QA.md](QA.md) passed on a build.
- **Analytics** (register in `backend/analytics_taxonomy.py` in the same commit as the emitters):
  - client (`ALLOWED_CLIENT_EVENTS`): `overhaul_started` `{league_id, outlook?, entry}` · `overhaul_roadmap_selected` `{overhaul_id, roadmap_id, package_count}` · `overhaul_batch_requested` `{overhaul_id, batch_id, package_count, offer_count, tied_package_count}` · `overhaul_fallback_requested` `{overhaul_id, package_id, tier, offer_count}`.
  - server (`SERVER_FIRED_EVENTS`, written with `database.record_event`): `overhaul_generation_completed` `{overhaul_id, candidate_count, compatible_roadmap_count, shortfall_reason}` · `overhaul_batch_reconciled` `{overhaul_id, batch_id, sent_count, failed_count, unknown_count}`.
  - `NON_INTENT_EVENTS`: add `overhaul_generation_completed`, `overhaul_batch_reconciled`.
  - Properties are ids, counts, enums only. Never asset names, notes, or tokens.
- **No new env vars, no `model_config` keys.** Search bounds are module constants in `overhaul_service.py`: `OVERHAUL_BATCH_SIZE = 24`, `OVERHAUL_MAX_SUBSETS = 40`, `OVERHAUL_MAX_ROADMAPS = 5`, `OVERHAUL_MIN_PACKAGES = 4`, `OVERHAUL_MAX_PACKAGES = 5`, `OVERHAUL_MAX_ALTS_PER_PACKAGE = 6`, `OVERHAUL_GENERATION_BUDGET_S = 20.0`.

## 3. Backend module split (file ownership: backend agent)

| File | Responsibility |
|---|---|
| `backend/overhaul_service.py` (new) | **Pure domain, no Flask, no I/O except through injected callables.** Pool enforcement, own-first identity resolution, candidate subset enumeration, offer normalization + `exact_package_hash`, roadmap assembly (compat solver), priority validation, prepare-send validation, capacity/legality union checks, state transitions. Everything unit-testable with fixtures. |
| `backend/overhaul_store.py` (new) | SQLAlchemy Core persistence for the five tables (§4): create/load/update helpers, reservation claim (transactional), attempt transitions with compare-and-swap on `state`. |
| `backend/overhaul_api.py` (new) | Flask routes, installed from `server.py` with an `install(app, *, ...)` call exactly like `win_now_api.install` (`backend/server.py:31292`). Receives the server-private helpers it needs as keyword callables: `require_session=_require_initialized_session`, `read_denial`, `write_denial`, `active_format`, `league_user_id`, `owner_generation_context=_owner_generation_context`, `roster_context=_build_trade_roster_context`, `sleeper_propose=<helper extracted in §6>`, `fetch_rosters=_fetch_league_rosters`, `load_picks=load_draft_picks`, plus whatever the deck route at `server.py:7416` passes to `_owner_generation_context` (service, players, seed_map, user_elo, user_roster, scoring_format, fairness_threshold). |
| `backend/database.py` | Five new `Table`s + `_migrate_db` rows (§4). Nothing else changes. |
| `backend/server.py` | (a) the `install` call next to Win Now's; (b) **surgical extraction** of the body of `propose_trade_to_sleeper` (`server.py:18222`) into `_sleeper_propose_core(sess, *, league_id, their_user_id, give_ids, receive_ids, proposal_event_id, source, impression_id=None) -> tuple[dict, int]` returning `(payload, http_status)` with the identical error codes; the route becomes a thin wrapper that parses the body and returns `jsonify(payload), status`. Behavior of the existing route must be byte-identical (existing tests prove it). |
| `backend/feature_flags.py`, `config/features.json`, `backend/analytics_taxonomy.py`, `backend/analytics_queries.py` | Flag + events per §2. |
| `backend/tests/test_overhaul_service.py`, `test_overhaul_api.py`, `test_overhaul_store.py` (new) | See §8. |

## 4. Schema (five tables)

All JSON columns are `Text` holding `json.dumps`. Timestamps ISO-8601 UTC via `database._now()`. Add each table to `metadata` and each column to `_migrate_db`'s list is **not** needed for new tables (`create_all` creates them); only add migration rows if a later change adds columns.

```
overhauls
  id INTEGER PK autoincrement
  overhaul_id TEXT UNIQUE NOT NULL          -- 'ovh_' + 12 hex
  account_user_id TEXT NOT NULL             -- sess['user_id']
  league_user_id TEXT NOT NULL              -- _league_user_id(sess)  (roster owner identity)
  league_id TEXT NOT NULL
  platform TEXT NOT NULL
  scoring_format TEXT NOT NULL
  status TEXT NOT NULL                      -- 'setup'|'reviewing'|'assembled'|'executing'|'complete'|'archived'
  revision INTEGER NOT NULL DEFAULT 1       -- bumps on every settings PATCH
  settings_json TEXT NOT NULL               -- OverhaulSettings (§5.1)
  snapshot_json TEXT                        -- roster/pick ownership snapshot at last generate/refresh (§5.2)
  recovery_json TEXT                        -- RecoveryRequirement (§5.3)
  generation_json TEXT                      -- last generation run summary (state, counts, shortfall, revision, ts)
  selected_roadmap_id TEXT
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
  INDEX (account_user_id, league_id), INDEX (league_id, status)

overhaul_offers
  id PK; offer_id TEXT UNIQUE NOT NULL; overhaul_id TEXT NOT NULL
  revision INTEGER NOT NULL                 -- settings revision it was generated under
  package_hash TEXT NOT NULL                -- sha1 of platform|league|seller|counterparty|sorted give|sorted receive
  counterparty_user_id TEXT NOT NULL, counterparty_username TEXT
  give_ids_json TEXT NOT NULL, receive_ids_json TEXT NOT NULL
  card_json TEXT NOT NULL                   -- public TradeCard dict exactly as trade_card_to_dict emits it (+ offer_id)
  evidence_json TEXT                        -- private: OwnerDecisionContext.as_dict() etc. NEVER returned to clients
  is_recovery INTEGER NOT NULL DEFAULT 0    -- targets the user's own next-season first
  decision TEXT NOT NULL DEFAULT 'undecided'
  decided_at TEXT; availability TEXT NOT NULL DEFAULT 'fresh'   -- 'fresh'|'stale'
  created_at TEXT NOT NULL
  UNIQUE (overhaul_id, package_hash)        -- regeneration cannot resurrect a passed exact offer

overhaul_roadmaps
  id PK; roadmap_id TEXT NOT NULL; overhaul_id TEXT NOT NULL
  version INTEGER NOT NULL                  -- immutable rows; new version per priorities write
  revision INTEGER NOT NULL
  packages_json TEXT NOT NULL               -- Package[] (§5.5)
  compat_json TEXT NOT NULL                 -- ValidationReceipt (§5.6)
  summary_json TEXT NOT NULL                -- {outgoing_ids, incoming_ids, counterparties, unused_eligible_ids, score, diversity_key}
  is_current INTEGER NOT NULL DEFAULT 1     -- 0 once superseded by a newer version
  created_at TEXT NOT NULL
  UNIQUE (roadmap_id, version)

overhaul_attempts
  id PK; attempt_id TEXT UNIQUE NOT NULL; batch_id TEXT NOT NULL; overhaul_id TEXT NOT NULL
  roadmap_id TEXT NOT NULL, roadmap_version INTEGER NOT NULL
  package_id TEXT NOT NULL, tier INTEGER NOT NULL, offer_id TEXT NOT NULL
  idempotency_key TEXT NOT NULL             -- batch-level client key
  request_hash TEXT NOT NULL                -- sha1 of the exact offer set + roadmap version
  state TEXT NOT NULL                       -- §7 enum
  state_source TEXT NOT NULL                -- 'server'|'provider'|'ownership_refresh'|'user_reported'
  provider_transaction_id TEXT
  proposal_event_id TEXT                    -- the id handed to _sleeper_propose_core / trade_proposals
  error_json TEXT
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, observed_at TEXT
  UNIQUE (batch_id, offer_id); INDEX (overhaul_id, state)

overhaul_reservations
  id PK; league_id TEXT NOT NULL; seller_user_id TEXT NOT NULL; asset_id TEXT NOT NULL
  overhaul_id TEXT NOT NULL, package_id TEXT NOT NULL, batch_id TEXT NOT NULL
  active INTEGER NOT NULL DEFAULT 1
  created_at TEXT NOT NULL, released_at TEXT
  UNIQUE (league_id, seller_user_id, asset_id, active)   -- one ACTIVE reservation per asset (use active=1 / NULL trick if SQLite treats NULL distinct: store released rows with active=NULL)
```

`docs/data-dictionary.md` gets one section per table.

## 5. Domain shapes (JSON)

### 5.1 `OverhaulSettings` (in `settings_json`, echoed on every overhaul read)
```json
{
  "outlook": "push_all_in" | "blow_it_up" | null,
  "eligible_asset_ids": ["4046", "L1_2027_1_3"],
  "preferred_positions": ["WR", "RB"],
  "rebuild_return": "picks" | "young_players" | "mixed" | null,
  "pick_budget": { "max_picks": 3, "max_round": 2, "seasons": [2027, 2028] } | null,
  "target_package_count": 4 | 5
}
```
`pick_budget` applies only to `push_all_in`; `rebuild_return` only to `blow_it_up`. Server validates that every id in `eligible_asset_ids` is currently owned by the user's roster per the snapshot (400 `asset_not_owned`).

### 5.2 `snapshot_json`
`{ "captured_at", "season": <league season int>, "my_roster_ids": [...], "my_pick_ids": [...], "rosters": {user_id: [asset ids]}, "picks_supported": bool, "source": "sleeper"|"mfl"|"espn" }`. Built from `sess['league']`, `_fetch_league_rosters` (Sleeper) or the stored snapshot (MFL/ESPN), and `load_draft_picks(league_id, source=PICK_SOURCE_PLATFORM)`.

### 5.3 `RecoveryRequirement` (`recovery_json`)
```json
{ "applicable": true,                      // outlook == blow_it_up
  "season": 2027,                          // league season + 1
  "state": "owned"|"missing_with_known_holder"|"unknown"|"unsupported"|"not_yet_available",
  "pick_id": "L1_2027_1_3" | null,
  "holder_user_id": "…" | null, "holder_username": "…" | null,
  "resolved": false,                       // true only when a liked recovery offer is in the selected roadmap
  "draft_order_rule": "unknown" }
```
Identity: original roster = the user's roster id (co-owner aware via `_league_user_id`), season = `league.season + 1` (or the league payload's season field), round 1, exact `pick_id`. `not_yet_available` when the platform has not published that season's picks. An empty pick table is `unknown`, never `missing`.

### 5.4 Roster union checks (D6)
- **Capacity**: `worst_case = len(my_roster_players) + sum(max(0, len(receive_players_i) - len(give_players_i)))` over one chosen alternative per package, computed for every combination of alternatives across packages **capped at 200 combinations** (beyond that, use the per-package max net gain — strictly more conservative). Must be ≤ roster capacity from `manager_preferences[uid].roster_capacity` when known; when unknown → `unknowns: ['capacity_unknown']` (reported, not blocking).
- **Legality**: run `trade_roster.evaluate` for the user vs each counterparty on the *final union* (viewer roster after applying every package's featured alternative). Blockers of kind `legal_deficits:*` / `cuts_required` block; `backup_depth:*` / `deficits:*` are reported as warnings (an intentional blow-up legitimately reduces depth; **do not** remove the global engine rule, just classify it as advisory at plan level). Record this classification in an ADR (`docs/adr/adr-020-overhaul-plan-roster-policy.md`).

### 5.5 `Package`
```json
{ "package_id": "pk_…", "give_ids": [...], "reason": "outlook_move"|"recover_own_first",
  "advisory_rank": 1,                        // 1 only for recover_own_first, else 0
  "tiers": [ { "tier": 1, "offer_ids": ["ovh_a", "ovh_b"] }, { "tier": 2, "offer_ids": ["ovh_c"] } ],
  "status": "open"|"pending"|"complete"|"blocked" }
```
Every offer in a package has `give_ids` equal (as a set) to the package `give_ids`. Initial tiers after assembly: all alternatives in tier 1 ordered by server rank? **No** — initial state is one alternative per tier in server rank order (tier 1 = best), so a user who never edits sends one offer per package. Ties are always a deliberate user action.

### 5.6 `ValidationReceipt` (`compat_json`, also returned by prepare-send)
```json
{ "ok": true, "checked_at": "…", "blockers": [ {"code": "…", "package_id": "…", "offer_id": "…", "message": "…"} ],
  "warnings": [ … same shape … ], "unknowns": ["capacity_unknown"],
  "outgoing_ids": [...], "incoming_ids": [...] }
```
Codes: `give_overlap`, `receive_overlap`, `asset_not_owned`, `counterparty_asset_not_owned`, `pool_violation`, `capacity_exceeded`, `lineup_illegal`, `offer_stale`, `offer_not_liked`, `recovery_unresolved` (warning only), `tier_duplicate_counterparty`, `asset_reserved`, `depth_reduced` (warning).

## 6. Generation (how candidates are produced)

Run synchronously inside `POST /generate` under `OVERHAUL_GENERATION_BUDGET_S`. Steps:

1. Refresh snapshot (§5.2); 409 `stale_revision` if the client's `revision` ≠ current.
2. Enumerate candidate outgoing subsets from the eligible pool, bounded by `OVERHAUL_MAX_SUBSETS`, in this order: every single asset; pairs ranked by combined consensus value; for `push_all_in`, pick-only subsets within `pick_budget`; for `blow_it_up`, top-value player pairs first. Skip subsets already exhausted in prior runs (`generation_json.exhausted_subsets`).
3. For each subset call `generate_owner_trades(**ctx, pinned_give_players=subset, exact_give=True, max_cards=3)` where `ctx = owner_generation_context(...)` built exactly as the deck route does. The plan outlook is passed as `outlook` in ctx (**override in the ctx dict only**, never write league preferences). `acquire_positions = preferred_positions` as a preference. For `blow_it_up` with `rebuild_return == 'picks'` pass `pinned_receive_players` empty and post-filter to receive sides that contain ≥1 pick (`'mixed'`: no filter; `'young_players'`: post-rank by average age ascending using `players` metadata when present).
4. **Recovery**: when `recovery.state == 'missing_with_known_holder'`, additionally call the generator with `opponent_user_id = holder`, `pinned_receive_players=[pick_id]`, over the top 6 subsets. Mark results `is_recovery = 1`.
5. Post-filter every card: `set(give) ⊆ eligible pool`, no generic picks, both sides non-empty, counterparty ≠ self. **Any card violating the pool is dropped and counted in `generation_json.pool_rejections`** (this is the E01 guarantee).
6. Normalize to `overhaul_offers` rows (dedupe on `package_hash`; existing rows keep their decision). Stop when `OVERHAUL_BATCH_SIZE` new undecided offers exist or the budget expires.
7. Write `generation_json = {state:'completed', revision, new_offers, total_offers, pool_rejections, exhausted_subsets, shortfall_reason|null, budget_exhausted}` and fire `overhaul_generation_completed`.

`shortfall_reason` enum: `insufficient_likes`, `overlapping_sells`, `competing_incoming`, `no_return_supply`, `recovery_unresolved`, `roster_limitation`, `stale_ownership`, `budget_restriction`, `search_exhausted`.

## 7. Routes (`backend/overhaul_api.py`) — all under `/api/overhauls`

All require `_require_initialized_session` + the read/write denial helpers; every route checks the overhaul row's `account_user_id == sess['user_id']` **and** `league_id == sess['league'].league_id` (404 `not_found` otherwise; never 403 — do not leak existence). Errors are `{"error": <code>, "detail"?: …}`; codes: `feature_disabled`, `not_found`, `stale_revision`, `stale_version`, `bad_request`, `asset_not_owned`, `generic_pick_not_allowed`, `pool_violation`, `offer_not_liked`, `offer_stale`, `tier_duplicate_counterparty`, `active_sends_exist`, `prepare_expired`, `summary_mismatch`, `idempotency_conflict`, `capability_unavailable`, `reconnect_required`, `verification_required`, `asset_reserved`, `supply_exhausted`.

| Route | Body → Response |
|---|---|
| `POST /api/overhauls` (flag) | `{league_id, client_key}` → **201** `OverhaulView`. Idempotent on `client_key` within (account, league). If an active (non-archived, non-complete) overhaul exists and has no live attempts, it is archived and a new one is created; if it has live attempts → 409 `active_sends_exist` with `{overhaul_id}`. |
| `GET /api/overhauls?league_id=` | → `{ "active": OverhaulView \| null }` (the newest non-archived overhaul for this account+league). |
| `GET /api/overhauls/{id}` | → `OverhaulView` |
| `PUT /api/overhauls/{id}/settings` | `{revision, settings: Partial<OverhaulSettings>}` → `OverhaulView` with `revision+1`. (PUT, not PATCH: the mobile client only speaks GET/POST/PUT/DELETE; body still carries a partial settings object.) Changing `outlook` or `eligible_asset_ids` marks every undecided offer of the old revision `stale`; decided offers keep their decision but are excluded from assembly if their give set is no longer within the pool. |
| `POST /api/overhauls/{id}/generate` (flag) | `{revision}` → `{ "generation": generation_json, "offers": Offer[] (undecided, current revision, fresh) }` |
| `GET /api/overhauls/{id}/offers?decision=undecided|like|pass|all` | → `{ "offers": Offer[], "progress": {"decided": n, "total": n, "liked": n} }` |
| `POST /api/overhauls/{id}/decisions` | `{revision, decisions: [{offer_id, decision: 'like'|'pass'|'undecided', client_key}]}` → `{progress}`. Idempotent per `(offer_id, client_key)`. Decisions on overhaul offers **do not** call the swipe/Elo learning path (explicit policy: plan review is not taste learning). |
| `POST /api/overhauls/{id}/assemble` (flag) | `{revision}` → `{ "roadmaps": RoadmapView[] (≤5, ranked), "shortfall": {"reason": …, "detail": …} \| null }`. When fewer than `OVERHAUL_MIN_PACKAGES` compatible packages can be formed, `roadmaps` is `[]` and `shortfall.reason` is set; the client then offers "Get more ideas" (→ `/generate`) and "Change my pool". |
| `PUT /api/overhauls/{id}/roadmaps/{roadmap_id}/select` | `{version}` → `OverhaulView` (sets `selected_roadmap_id`, status `assembled`). |
| `PUT /api/overhauls/{id}/roadmaps/{roadmap_id}/priorities` | `{version, package_id, tiers: [{tier, offer_ids}]}` → `RoadmapView` with `version+1`. Validates: offer ids ∈ package, every liked alternative appears exactly once, tiers contiguous from 1, D4 rule. |
| `POST /api/overhauls/{id}/roadmaps/{roadmap_id}/prepare-send` | `{version, offer_ids}` (the user-selected exact offers; default = tier 1 of every open package) → `PrepareView` = `{ prepare_token, expires_at (now+120s), summary_hash, receipt: ValidationReceipt, counts: {offers, packages, max_accepted}, races: [{package_id, offer_ids, counterparties}], capabilities: Capabilities, handoff: {mode: 'send'|'copy', text?: string} }`. No provider writes. |
| `POST /api/overhauls/{id}/send` (flag) | `{prepare_token, summary_hash, version, idempotency_key}` → `{ batch_id, attempts: AttemptView[] }`. Same key + same summary hash → the existing batch (200). Same key + different hash → 409 `idempotency_conflict`. Flow: validate token/hash/version → claim reservations for every outgoing asset transactionally (409 `asset_reserved` lists the conflicts, nothing sent) → create attempts `queued` → for each attempt sequentially: `sending` → call `_sleeper_propose_core` → `proposed` (store `provider_transaction_id`) or `send_failed` (error json) or `outcome_unknown` (timeout/transport exception after dispatch). Attempts are persisted **before** each provider call. Fires `overhaul_batch_reconciled`. `handoff.mode == 'copy'` platforms: 409 `capability_unavailable`. |
| `POST /api/overhauls/{id}/refresh` | `{}` → `OverhaulView`. Re-captures the snapshot; for each `proposed`/`outcome_unknown` attempt: if every give asset has left the user's roster **and** every receive asset arrived → `accepted` (`state_source: ownership_refresh`); if a give asset left but the receive side did not arrive → `resolved_elsewhere`; else unchanged. Accepted → package `complete`, alternatives `invalidated`, reservations released for the package, remaining packages revalidated (offers whose assets are gone become `stale`). Never sends. Rate-limited to one call / 15 s per overhaul (429). |
| `POST /api/overhauls/{id}/attempts/{attempt_id}/status` | `{state: 'declined'|'withdrawn'|'expired', note?}` → `AttemptView` with `state_source: 'user_reported'`. Only allowed from `proposed`/`outcome_unknown`. Releases that attempt's share of the reservation only when no other attempt in the package is live. |

### Views
```
OverhaulView = { overhaul_id, league_id, platform, status, revision, settings, snapshot: {captured_at, season, picks_supported},
                 recovery, generation, selected_roadmap_id, roadmaps: RoadmapView[] (current versions only),
                 progress: {decided, total, liked}, attempts: AttemptView[], capabilities: Capabilities,
                 eligible_assets: AssetView[] (the user's whole roster + owned picks, with `recommended: bool` and `reason` for the outlook) }
AssetView   = { id, kind: 'player'|'pick', name, position, team, age?, value, label (picks), recommended, reason }
Offer       = { offer_id, is_recovery, decision, availability, counterparty_user_id, counterparty_username,
                give_ids, receive_ids, card: TradeCard(public dict) }
RoadmapView = { roadmap_id, version, packages: Package[], compat: ValidationReceipt, summary, rank, offers: {offer_id: Offer} }
AttemptView = { attempt_id, batch_id, package_id, tier, offer_id, state, state_source, provider_transaction_id?, error?, created_at, updated_at, observed_at? }
Capabilities= { platform, can_propose, can_read_terminal_status: false, can_withdraw: false, supports_conflicting_offer_race: 'unverified',
                auth_state: 'linked'|'unlinked'|'expired'|'unverified'|'n/a', checked_at }
```
`recommended` on `AssetView`: for `push_all_in`, picks (within budget) and bench players below starter tier; for `blow_it_up`, players ≥ 27 years old (age from `players` metadata when known) with starter-tier value. Use `team_review` depth signals when available in the session; otherwise the age/value heuristic. Recommendations are advisory and clearly labelled.

Attempt states (cross-client enum, document in `docs/cross-client-invariants.md`): `queued`, `sending`, `proposed`, `send_failed`, `outcome_unknown`, `accepted`, `declined`, `expired`, `withdrawn`, `invalidated`, `resolved_elsewhere`, `stale`. Live = `queued|sending|proposed|outcome_unknown`.

## 8. Backend tests (minimum)

`test_overhaul_service.py` (pure, no Flask): E01 pool violation dropped incl. sweetener; E02 unused eligible asset allowed; E03 pick-only give (all-in) and pick-only receive (rebuild); E04/E05 recovery identity (two firsts with different original rosters; owned/missing/unknown/not_yet_available); E07 give overlap → not independent; E08 same give set → same package, tier race explicit; E09 regrouping produces distinct roadmaps (diversity key differs); E10 incoming collision rejected; E11 shortfall reason when < 4 packages; E12 position preference is soft; E15 union capacity arithmetic + a fixture where every single offer passes but the union exceeds capacity; D4 tier duplicate counterparty rejected.

`test_overhaul_store.py`: reservation uniqueness across two overhauls; attempt CAS transition refuses regressing `accepted` → `proposed`.

`test_overhaul_api.py` (Flask client + injected session, pattern `backend/tests/test_avoid_positions.py:117`; fake generator + fake `sleeper_propose` injected through `install`): create idempotent on `client_key`; flag off → 404 on gated routes, 200 on GET; foreign account → 404; settings revision conflict → 409; generate stores offers and never returns `evidence_json`; decisions idempotent; assemble → ≤5 roadmaps or shortfall; priorities version conflict; prepare-send → counts (AC12: 4 packages + one tie = 5 offers, max_accepted 4, race named); send: idempotent replay, different-hash conflict, reserved asset conflict, partial success (fake propose fails on 2nd) yields per-attempt states, `outcome_unknown` on transport exception; refresh marks accepted from ownership change and invalidates alternatives; status assertion only from live states; existing `/api/trades/propose` tests still pass after extraction.

## 9. Mobile surface (file ownership: two mobile agents)

Registered in the **Trades stack** (`TabNav.tsx`, next to `TeamReview`, using `subScreenOptions`), so **no local FeedbackFAB** on any overhaul screen. Flag-gated screens register unconditionally; the flag gates the entry card. Route names and params (untyped stack, `navigate(name as never, params as never)`):

| Route | Screen file | Owner | Purpose |
|---|---|---|---|
| — | `components/OverhaulEntryCard.tsx` | Mobile A | Acquire landing card below `TeamReviewEntryCard`; "Team overhaul / Start overhaul" or "Resume overhaul" + outlook + compact attempt summary. Shown when `overhaul.enabled` **or** an active overhaul exists. |
| `OverhaulOutlook` `{overhaulId?}` | `screens/OverhaulOutlookScreen.tsx` | Mobile A | Two cards (`Push all in`, `Blow it up`), creates the overhaul on continue ("Choose my trade pool"). |
| `OverhaulAssets` `{overhaulId}` | `screens/OverhaulAssetsScreen.tsx` | Mobile A | Whole roster by position + picks section, recommendations, select/deselect, pick budget (all-in) or return mix (blow-it-up), recovery warning, **Continue**. |
| `OverhaulTargets` `{overhaulId}` | `screens/OverhaulTargetsScreen.tsx` | Mobile A | Optional position preferences (recommended pre-ticked, user can clear), **Continue** → triggers `/generate` then navigates to review. |
| `OverhaulReview` `{overhaulId}` | `screens/OverhaulReviewScreen.tsx` | Mobile A | Like/pass deck reusing `TradeCard` with `disposition` (no swipe learning), progress "n of N", compatible-like coverage hint, **Build roadmaps** (enabled when all decided), "More ideas". |
| `OverhaulRoadmaps` `{overhaulId}` | `screens/OverhaulRoadmapsScreen.tsx` | Mobile B | Compare ≤5 roadmaps (packages, counterparties, committed vs unused eligible assets, Priority 1 recovery highlight), shortfall state with "Get more ideas"/"Change my pool", **Set priorities** (select). |
| `OverhaulPriorities` `{overhaulId, roadmapId, packageIndex}` | `screens/OverhaulPrioritiesScreen.tsx` | Mobile B | One package per page: header "Package N of M", outgoing assets, DraggableFlatList tiers (recipe from TiersScreen), accessible Move actions, Back / Continue (last → summary). Saves via `/priorities`. |
| `OverhaulSummary` `{overhaulId, roadmapId}` | `screens/OverhaulSummaryScreen.tsx` | Mobile B | Calls `/prepare-send`; shows counts (offers / packages / max accepted), each package's tier-1 offers, race warnings **on the affected packages**, recovery advisory, receipt blockers/warnings, **Send all offers** (or "Copy offers" handoff when `handoff.mode == 'copy'`); on send navigates to plan. |
| `OverhaulPlan` `{overhaulId}` | `screens/OverhaulPlanScreen.tsx` | Mobile B | Saved roadmap: per-package status, attempts with state pills, Refresh, "Send next tier" (→ prepare-send with that tier's offers → summary), "Mark declined / withdrawn" (status assertion), stale/blocked explanations. |

Shared: `mobile/src/api/overhaul.ts` (types + fetchers; **written by the scoping session, both agents consume it, backend implements it**). Query keys: `['overhaul', leagueId]` for the active lookup, `['overhaul', overhaulId]` for the plan, invalidate both after every mutation.

Copy and visuals: Chalkline tokens only; ice for the single primary CTA per screen; flare for the "Priority 1: Recover your first" highlight (informational); position colors for asset badges. testID families (static prefixes): `overhaul.entry-card`, `overhaul.entry-start`, `overhaul.entry-resume`, `overhaul.outlook.<key>`, `overhaul.asset.<id>`, `overhaul.continue`, `overhaul.review.like`, `overhaul.review.pass`, `overhaul.review.build`, `overhaul.roadmap.<id>`, `overhaul.priority.list`, `overhaul.priority.move.<id>`, `overhaul.summary.send-all`, `overhaul.summary.copy`, `overhaul.plan.refresh`, `overhaul.plan.send-next`.

Structural guard `mobile/tests/check-team-overhaul.js` (Mobile B) pins: every overhaul screen registered once, in the Trades stack, none in RootNav; no `FeedbackFAB` import in any overhaul screen; entry card rendered in `TradesScreen` directly after `TeamReviewEntryCard` and gated on `useFlag('overhaul.enabled')` or an active overhaul; no overhaul file imports `saveLeaguePreferences`/`/api/league/preferences` or `/api/tiers/save` or `swipeTrade` (preference isolation, no taste learning); priorities screen imports `react-native-draggable-flatlist` and defines `accessibilityActions`; summary screen renders the race warning keyed by `package_id`; the `AttemptState` union in `api/overhaul.ts` has a matching label in the plan screen; every testID family above appears literally. Add `"test:team-overhaul"` to `package.json`.

## 10. Docs each agent updates (row-by-row, in the same PR)

| Doc | Owner |
|---|---|
| `docs/api-reference.md` — new section "Team overhaul (flag `overhaul.enabled`)" with every route, errors, idempotency | backend |
| `docs/data-dictionary.md` — five tables | backend |
| `docs/config-reference.md` — flag row; `docs/cross-client-invariants.md` — attempt-state enum, outlook enum, shortfall enum, validation codes | backend |
| `docs/architecture.md` — "Team overhaul" module wiring paragraph; `docs/adr/adr-020-overhaul-plan-roster-policy.md` | backend |
| `docs/glossary.md` — overhaul / package / tier / roadmap / attempt | backend |
| `mobile/src/screens/CLAUDE.md`, `mobile/src/api/CLAUDE.md`, `mobile/src/components/CLAUDE.md` registry rows | mobile A (api + entry + setup rows), mobile B (execution rows) |
| `docs/plans/team-overhaul/scope.md` (fill final names), `status.md`, `living-memory/*` | scoping session |

## 11. Out of scope for v1 (explicitly)

Durable async workers and leases; provider withdrawal; MFL pending-export correlation; ESPN sends; counter promotion; automatic fallback; web/extension surfaces; multi-league overhauls; the separate single-asset "first come, first served" feature (NEXT item 7).

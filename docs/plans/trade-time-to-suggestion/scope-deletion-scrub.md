# Feature Scope — Deletion scrub: a deleted user's partner records in other users' decks (legal R28.20 (ii), R28.22)

**Date:** 2026-10-31
**Entry point:** direct ask. Legal R28.20 (ii) requires the redaction; R28.20 addendum (vii) says start 10-31, and its rulings are final for building. R28.22 accepts the field and store lists with conditions. head-eng routed it (`head-eng-r28-22-routing.md` § trades-eng, group notes).
**Builder:** trades-eng
**Operator sign-off on waivers:** not needed. Analytics is waived below for a reason that is not a gap: a server log line, never an event, and never an id.

**The rules, final** (`docs/plans/org-bringup/leads/legal-lead.md` R28.20 (ii), (viii), (ix); R28.22; models-lead addendum G):
- **(ii) c1:** each deleted user gets one random token per deletion run, `redacted:<uuid4 hex>`. No mapping is stored. The token replaces every partner id of theirs in other users' decks, in every store.
- **(ii) c2:** every field taken from the deleted user's Fleeced account is dropped: likes, board values, declared settings.
- **R28.22 b2, uniformity:** whatever the scrub does to a field, it does to EVERY redacted card of that partner, in packs, full rows and the page store, in the same run. A key that is only ever true may simply be removed.
- **G-a1:** "cleared" means the key is REMOVED, never set to False.
- **G-a3:** packs and candidate packs change only through the codec: `unpack_run`, then the four changes, then `pack_run`, which refuses an inexact pack. No hand-patching.
- **R28.22 b, blended scalars:** a value kept beside a dropped one must not let anyone solve the dropped one back, and must not be a copy of it. Each is tested, with the result recorded here and in the PR (§1.3).
- **(viii):** `trade_hash`, `trade_concept_id`, `retest_trade_hash` and the other partner-embedding hashes stay. No one may use them to work out whose a redacted record was.
- **(ix):** the job row holding the ids is deleted when the scrub finishes. Past 24 h unfinished, it keeps retrying for up to 30 days and alerts eng with a count. Ids never go to logs, Sentry or the audit line.
- **R28.22 e:** `trade_matches.match_valuation_json` is scrubbed in both directions. When the deleted user was `user_a`, the second liker, their own board and preference values go too.
- **R28.22 f:** before ship, trace `owner_generation`, the slim `bakeoff_run` / `presentation` records and the narrative text. Any username or display name of the deleted user in stored text becomes the placeholder.
- **#523 (d1):** the deletion and export fix stays unconditional, never behind the prune's switch.

---

## 0. Design

### 0.1 The job: a durable work row, written in the deletion's own transaction

- **New table `deletion_scrub_jobs`**, one row per deletion:
  - `job_id`;
  - `token`;
  - `partner_ids_json`, the deleted user's resolved ids (`_user_data_scope`);
  - `league_ids_json`;
  - `deleted_at`;
  - `db_done_at`, `model_done_at`;
  - `attempts`, `claimed_until`;
  - `last_error`, a class name only, never a message (or `row_failures` when a pass left a row it couldn't redact);
  - `scan_json`, an unfinished pass's cursor.
- **The row is inserted inside `_delete_user_data`'s transaction.** So a committed deletion always has its scrub, and a rolled-back deletion has none. The leagues are captured in that transaction too, before `league_members` loses the person's rows.
- **Leagues** are the union of:
  - the person's `league_members` rows;
  - `leagues` rows they imported;
  - `league_roster_history` rows naming them;
  - the leagues of their own decks (`deck_impressions` and `deck_evidence_packs` by `user_id`).
  - **The fallback scan closes the residual** (head-eng, 10-31): a league they left before deleting, which none of these still names. After the league pass, the DB phase scans every row of each store up to the cutoff.
    - It reads keyset pages of 2,000 rows by primary key, 50 pages a run. The database does the text match, so only matched rows come back. A packed candidate set is decoded to be checked: one per deck, a few KB.
    - The cursor is kept on the job row (`scan_json`), so the next cleanup tick resumes it.
    - **Sizing:** about 100k rows a 5-minute tick, so 1M rows in about 50 minutes, twice per deletion (the pass and the grace pass). Deletions are rare.
    - **The grace pass is keyed on its start** (#562 QA P2-3). `db_done_at` is the time a pass began, kept in its cursor, because a long resumable pass covers only what was written before it began. A first pass that runs across the 6 h grace therefore isn't the grace pass: another one runs.
    - **The alternative,** a partner→deck side index written at deck time, covers only new writes. Existing rows would need the same full read as a backfill, plus a change on the hot evidence writer. So the scan was picked.
    - Stage 2 scans packs' `header_json` and the page store the same way.
- **Two phases.** The row is deleted only when both are done.
  - **DB phase:** every store in §0.2, first the league pass, then the fallback scans. It runs in a background thread the deletion route kicks, and the cleanup loop retries any row past its lease and resumes an unfinished scan. The lease is a CAS claim on `claimed_until`, so two instances during a deploy never run one job twice.
  - **Model phase:** `eval.redaction.redact_model_store(tokens)`, in the daily-tick step `deletion_scrub`, placed **before** `value_model_refit` (models-eng 8b, #542). It runs only for jobs whose DB pass is current, so the refit trains on scrubbed rows. A test pins the order. A raise leaves the row for the next tick.
  - **The DB phase runs once more after `IN_FLIGHT_GRACE` (6 h),** from the cleanup loop. That catches rows a deck already in flight at deletion wrote later from its build-time snapshot (§0.4).
  - **Until every stage was built, finished rows were kept,** so a later stage's `SCRUB_VERSION` re-ran them. Stage 3 sets `COMPLETE`: a row is deleted once its grace pass and the model store are done (legal (ix)).
- **Alert:** each tick, if any row is older than 24 h, the log gets `[scrub] unfinished jobs=<n> oldest_h=<h>` at ERROR (counts only). **Past 30 days a job stops** (`RETRY_LIMIT`, `_abandon` in the tick). Its row, which holds the ids, is deleted, and the log gets `[scrub] abandoned jobs=<n> after_days=30 last_errors={<class>: <n>}` at ERROR, with counts and classes only. A store row the scrub couldn't rewrite (a poison row: it never sets `db_version`, so `_finish` would never delete the job) stays for eng to fix by hand, which the 24 h alert has asked for daily since. This is trades-eng's reading of (ix), "retrying for up to 30 days": the ids aren't kept past the retries. The alternative was to keep the row and escalate. Legal to confirm through head-eng (release-lead's #559 delta QA).

### 0.2 Stores and what each card loses

The rows to touch are found per captured league and per viewer (the league's members and importers) through the existing `(user_id, league_id)` indexes, then filtered to rows that mention an id.
- **Which decks:** a deck's rows carry its first delivery as `served_at`, so a deck built before the deletion can be first delivered after it. Decks served up to `deleted_at` + `IN_FLIGHT_GRACE` (6 h) are touched, and later ones never: they treat the person as any non-user leaguemate (legal (vii)).
- **Which cards:** a card whose partner is a deleted id is redacted in full. Any other row that names an id gets the token in its place.

| Store | Partner id → token | Removed (c2) | Nulled (blended, §1.3) |
|---|---|---|---|
| `deck_impressions` rows | `features_json.partner_user_id`; `owner_request.members[].id` and `manager_preferences` keys; `roster_evaluation.teams` keys. **On any row naming the person** (not only their own cards), the owner request loses their outlooks, sources, preferences and board: it rides on every card of its run with every member's outlook | `likes_you`, `standing_offer`, `standing_offer_reason`, `negmem.exempt`, column `source_like_impression_id`, the partner's side of `fit` / `fit_diag` (`them`, `lenses.them`, `vs_consensus`, `aggregate`, `bucket`), the partner's objections in `breaker`, explicit-source `roster_evaluation.teams[partner]`, the owner request's partner `elo` / `board_updated_at` / `manager_preferences`; in `valuation_json`, the partner-board keys of the trade_policy, owner and value_core shapes (c2 list) | `surplus_margin`, `base_score`, `final_score` |
| `deck_evidence_packs` (codec) | the packed `partner_user_id`; the taste attr `partner:<id>` in the vocabulary; the `run.filter_inputs.qb_te` key is dropped | `likes_you` | `surplus_margin`, `base_score`, `final_score` |
| | header: the partner's hashes leave `run.filter_inputs.protected`; `run.redacted_at` is added (G-a3's four changes) | | |
| `deck_candidate_sets` | packed (`pack_candidates`) or legacy `candidates_json` member `partner` | — | `base_score` |
| `bakeoff_runs` (other users'; found by legal f's trace, 10-31, so a correction to the c3 list's "partner-free") | any id in `config_json`, `arms_json`, `agreement_json` and `groups_json` (#557 QA P1-3); an owner arm's `diagnostics.pools[<id>]` (that member's preference-ordered assets) goes. Fallback scan only: a league pass over megabyte rows isn't bounded | the owner engine's frozen `input` holds every league member's board, sources, preferences and declared and inferred outlooks, under `owner_request` (organic runs) or at the top level (owner-selected runs: fair packages, asset ideas; #557 QA P1-2); the person's member loses `elo` / `board_updated_at`, and their `opponent_sources`, `manager_preferences`, `opponent_outlooks` and `inferred_outlooks` entries go | — |
| `trade_page_store` (stage 2) | `pages_blob` `target_user_id` (→ token) and `target_username` (→ the placeholder); `evidence_blob` rows and ghosts, the same as `deck_impressions`; its candidate set; `trade_impressions[].target_user_id` → NULL (as deletion does to the table); `run_meta.filter_inputs` the same as the pack run; any other id mention → token | a redacted page card loses `likes_you`, `standing_offer_reason`, `reasons`, `rationale`, `fit`, `breaker` and `match_context.opponent_outlook`; a page card's `roster_evaluation` (stored when `trade.roster_protection` is on) loses the deleted ids' `teams` entries on any card, and `mutual_benefit` on a redacted card, as a deck row does (#559 QA); the narrative is stage 3's trace | `mismatch_score`, `composite_score` (and the row's scores) |
| `user_taste` (other users) | attribute `partner:<id>` → `partner:<token>`; two aliases of the person merge into one row (weights summed). In the deletion transaction | — | — |
| `standing_offers` (other users) | `team_user_ids`, in the deletion transaction | — | — |
| `grading_cards` / `grading_sessions` (other users; stage 3) | a building session's hidden `source_json`, the cards' `arms_json`, and `grading_cards.partner_user_id` (→ token) | **The person's card** (#562 QA P1-2). It's matched by `grading_cards.partner_user_id` (hidden, written by `build_session` and `add_fit_arms`): a built session keeps no partner ids anywhere else.<br>A card built before that column is traced instead by its current arm's deck row (`impression_id` → the row's partner, an id or the token), by a raw id shown as its name (a member with neither name), or by one of the person's names in that league that no remaining member uses. A league they had left has no names captured, so any of their names count there, with the same guard.<br>Such a card's `trade_json.partner_name` takes the placeholder, and every arm loses `gain_partner` (fit arms: the gain on the partner's own board) and `reasons` (value core: "they rank X at 1.4× market", "Fits their rebuild"), uniformly (P1-1, R28.22 b2).<br>**Any card:** a traded pick's label "(from <their name>)" takes the placeholder (P2-4).<br>**Passes:** the league pass covers the captured leagues and the fallback scan covers only leagues they had left, so each is tested on its own. Grades are kept.<br>**Older cards** (#562 re-QA P2-B): the boot backfill (`database.backfill_grading_card_partners`) gives NULL cards their partner while names and deck rows are still live. A current-arm card takes its deck row's partner. Any other takes the one member shown by its `partner_name`, provided that member's roster holds the card's received players (at least one) and the member isn't the session's own user. A pick-only card, or one whose players have since been traded, stays NULL.<br>**The backfill runs from `_migrate_db`, so during a Render build too, against prod while the old instance serves** (#562 delta QA). Its first read and each chunk of 500 run in their own transaction, on Postgres under `SET LOCAL lock_timeout` (3 s) and `statement_timeout` (30 s), with one deck-row lookup per chunk. A failed chunk is skipped until the next boot and summarised in one warning. The counts are rows committed, and it never raises. The fallback scan looks at every NULL card, since Postgres's LIKE is case-sensitive and the deck row isn't visible to SQL. Failed and retired sessions keep their building source, so they're scrubbed too (P2-A).<br>**Residual:** an older card that the backfill couldn't resolve (its partner was renamed or had left, or the name was ambiguous) and that has no deck row (they prune at 90 days, while sessions live 365) or is outside the current arm. Such a card stays if its name is one a remaining member uses (the collision guard), or one not captured. A name fill is wrong only if the card's name is another current member's name and its players have since moved to that member: a member who took another's old name, or two who share a name. Leaving such a card NULL wouldn't have traced it either. Testers only (`grading.blind`) | — |
| `trade_matches` | ids are already the placeholder today | `match_valuation_json` cleared whole when either side is the person, in the deletion transaction (it holds user_a's own board as the viewer and user_b's as the partner; the `trade_proposals.valuation_json` precedent) | — |
| model store | E-b3 (`redact_model_store`) | — | — |
| `deck_diagnostic_snapshots` (stage 3) | — | a row past the 14-day retention (`FTF_DECK_DIAGNOSTIC_RETENTION_DAYS`; a purge that fell behind) naming them is deleted; younger ones go with the 14-day purge, inside legal's 30 days | — |
| `notifications` (other users'; head-eng 10-31, found in release-lead's #557 QA) | ids in `metadata_json` | a match / disposition notification naming them in `metadata_json.partner_username`.<br>**A match notification** (`metadata.match_id`) to one of the match's sides: its `trade_matches` row decides (#562 re-QA P3). The person's match ids are captured at deletion, before their side becomes the placeholder. On one of those, or any match whose other side is the placeholder, the partner name is theirs whatever it says, including a name never captured or since changed (#562 delta QA). The scan reads the notifications of those matches' counterparties, rather than a SQL term per match id, which stays cheap for a person with thousands of matches. A leaguemate whose display name is their username is never redacted, and a copy sent in a league they had left is.<br>**Without a match row:** by **username** (unique, matched anywhere); by **display name** (the second liker's copy, #562 QA P2-2) only for a recipient who shared a captured league; or by a raw id.<br>That name becomes the placeholder there and as `@name` in the title and body, and so does any `@<id>`. Names are matched raw and as `json.dumps` escapes them (a non-ASCII name) | — |
| `user_events` (other users'; the same) | ids in `props` (e.g. `partner_user_id`) | — | — |

Already handled by deletion today, untouched: `trade_proposals`, `trade_impressions`, `bad_trade_flags` (NULL), `prepared_trade_*` (deleted), `trade_matches` ids.

### 0.3 Packs: the codec path and the writers' cached state (stage 2, built)

- **Each pack:** `deletion_scrub.redact_pack` runs `unpack_run`, the four changes, then `pack_run(run, cards, card_count=same)`. The four changes:
  - a redacted card's `partner_user_id` takes the token, `likes_you` is removed and its blended scores are nulled;
  - `partner:<id>` taste attrs take the token on any card;
  - `run.filter_inputs.qb_te[<id>]` and the protected hashes of the person's cards go;
  - `run.redacted_at` is added.
  - The row is written by CAS on the stored checksum, and a miss re-reads and redoes. `card_count`, `PACK_VERSION` and every non-redacted card are unchanged, which G-a2's tests check bit for bit and through eval's own reader.
- **The writer's cached state can neither undo nor leak around it** (head-eng's ruling 2): `server._fresh_pack_state`.
  - A cached `_PackState` whose stored header changed outside its run (only the codec rewrites the dictionaries) reloads from the row in place. Its pending run changes merge onto the stored run, where the stored keys win, `redacted_at` among them. That runs on `_deck_pack_commit`'s CAS miss and before every upgrade.
  - An upgrade's row from a deck's build-time snapshot takes the pack's token (`_redacted_held_row`): the redacted pack card names the token where the snapshot names the person, which gives the mapping with no id kept.
  - Tests drive the race, the stale cache and the held row.
- **A redacted card never serves, in any I-1 mode** (models-lead addendum J4, head-eng's option (b); moved from stage 3 into stage 2 so #559 merges on its own, release-lead's #559 QA P1). At prod's `trade_i1_mode` 1, I-1 alone would serve it while a stale page rebuilds.
  - `_roster_serve_rules`, which /generate, /status (legacy and paged) and the page-store serve share, drops any card whose target is a redaction token before I-1.
  - It's recorded as a withdrawal with its own reason, `partner_deleted`, counted apart so G10's mode-1 rule on `i1_dropped` stays clean. `served_before` is 1 when an earlier response had delivered the card (a deck served before the deletion, or one built after it within the 6 h grace), else 0.
  - It runs before `deck_i1_check`, so a redacted card is in neither of that event's `cards` / `kept` counts.

### 0.4 Decks in flight at deletion

- A live job's `_DeckEvidence` holds unwritten rows from its build-time snapshot. A delivery after the scrub writes them, and with them the old id and the c2 fields.
- **The tick's second DB pass rewrites them.** The window is at most until that tick.
- **Jobs held in this process are revoked when the deletion commits** (release-lead's #559 QA P2). The scrub rewrites stored decks, never an in-memory job, which at `trade_i1_mode` 0 or 1 would keep serving the person's original cards (their id, name and reasons) until it left memory.
  - The delete route reads the person's leagues before the deletion removes their rows (`_deletion_scrub_leagues`). After it commits, `_revoke_trade_jobs_naming` revokes every job whose cards name a deleted id (dicts or `TradeCard` objects) and every job still running in one of those leagues (it may yet publish such cards): superseded, cards cleared, a running one errored. The next request builds a fresh deck. The response's `deleted` counts gain `trade_jobs_revoked`.
  - **The reason is the neutral `inputs_changed`** (release-lead's re-QA P2-a). A running job's error reaches its owner, a leaguemate. Mobile retries `inputs_changed` on its own; `partner_deleted` would show a dead-end error card, and web would toast the raw code, telling them someone deleted their account. A revoked complete job already reported `inputs_changed`.
  - **Each session's TradeService card store is purged too** (re-QA P2-b). It's shared with the session's trade jobs and served by `GET /api/trades` with no expiry, so it kept the person's cards (id, name, narrative) after the revoke and the scrub. `_purge_session_trade_cards` removes every card whose partner is a deleted id from every session's services, every format's; the counts gain `trade_cards_purged`. A job still running at the deletion writes its cards straight into that store, after the purge, so `GET /api/trades` also hides a card naming a deleted id that was built before that id's window closes, an hour after the deletion (`_deleted_partner_ids`, twelve job hard-timeouts).
    - A card built after the window comes from a search started after the deletion, from public league data (legal (vii): the person is now a non-user leaguemate), and it serves. That includes a re-signup with the same platform id, and another person on a slot-keyed entry id (release-lead's delta QA P3: hiding them for the life of the process over-filtered).
  - Both run after the commit, each in its own `try`: one failing never skips the other (delta QA P3), and a failure is logged by class and never turns a committed deletion into a 500.
  - **Cost:** the revoke holds `_trade_jobs_lock` for O(jobs × cards), measured by release-lead at 61–67 ms for 2,000 jobs × 150 cards and 0.34–0.75 s for 5,000 × 200. The purge holds `_sessions_lock` only to list the sessions. Fine at today's volume; revisit if the job registry grows past a few thousand.
  - **What a revoked deck still writes:** an outcome on one of its cards that the client already holds writes a full row, as any outcome does. The scrub's grace pass redacts it.
  - Another process's jobs and sessions aren't reached. Prod runs one (`render.yaml`: `--workers 1`); with more, they'd keep them until they leave memory. Their stored decks are the scrub's.
- A stored page's redacted cards are dropped by the serve rules above, whatever the I-1 mode.
- **The pre-scrub window** (release-lead's re-QA P3): between the deletion's commit and the scrub's page-store league pass, a stored page still holds the person's cards with their id, so a serve in that window can deliver them. The kick starts the scrub off the request, so the window is about 0.1 s; if the kick fails, it's up to one cleanup tick (5 min). I-1 doesn't close it at prod's `trade_i1_mode` 1; only mode 2 would withdraw such a card. Eval is safe either way: redacted cards are counted, never audited (G-a4 to G-a6). Whether the window is acceptable is with legal.

## 1. Analytics scope

- [x] **(c) WAIVED. No analytics needed.**
  - The scrub emits no event and changes none. It is a deletion step.
  - Its observable is one server log line per job phase, `[scrub] job db_done counts={store: n}` / `model_done changed=<n>`, plus the 24 h alert. They carry counts, never ids.
  - Eval's side is models-eng's, in PR C (models-lead addendum J1): redacted decks are a `partner_redacted` exclusion, not compared (G-a5 as revised), and redacted cards are never training rows.

### 1.3 Blended scalars: the solve-back test (R28.22 b)

| Value | What it is | Kept beside it | Result |
|---|---|---|---|
| `basis` | `"divergence"` / `"consensus"` | — | **keep** (legal: it only says the partner has a board) |
| `surplus_margin` (= `mismatch_score`) | harmonic mean of `fit.you` / `fit.them` (`trade_gen_fit.py:470-472`); v2 `user_gain` / `opp_gain` | `fit.you` (the viewer's) | **FAILS:** `them` solves from `you` and the mean. **Nulled** (legal's list) |
| owner_v2_bilateral `bilateral.{weaker_support,total_support,preference_fulfillment}` (#557 QA P1-1) | min / sum of the viewer's and the counterparty's support and net preference (`trade_gen_bilateral.py:257-262`) | `viewer.support`, `viewer.intent` | **FAILS:** the counterparty's side solves back. **`bilateral` removed**; and `term_efficiency` (each companion classed by its recipient's preference-derived `benefits`) and `assets[].counterparty_preference` (their tier, percentile, direction) go, and every id in `valuation_json` takes the token |
| `base_score` (= `composite_score`) and `fit.aggregate` | `aggregate_raw = you_raw + them_raw` on fit cards (`trade_gen_fit.py:475`, `:778-788`); on a liked card, the likes boost sets it to the deck's max + 1.0 (`server.py:8319`) | `fit.you` | **FAILS, both:** `them = aggregate − you`, and the +1.0 over the deck's max encodes the like. **Both go:** `base_score` nulled, `fit.aggregate` removed |
| `final_score` | `base × propensity × fatigue × taste × diversity` (`server.py:9300-9328`, the post-multiplier key) | `propensity`, `taste_pref_*` | **FAILS:** with the stored multipliers it recovers `base_score` (fatigue is 1 on most cards). **Nulled** |
| value_core `scores.outlook`, `scores.priority`, `effective` (stage 3) | `outlook = (viewer + partner) / 2` (`value_core/ranking.py:115-118`); `priority` and `effective` are built from it with the weights | `detail.outlook.viewer`, `scores.value`, `scores.rank` | **FAIL:** the partner's outlook score solves back. **Removed** on a redacted card; `value` and `rank` (market, the viewer's own board) stay |
| `propensity` | the Thompson multiplier the viewer's sampler drew (`server.py:9206`) | — | **keep:** the viewer's own sampling, with no partner input |

**Consequence for eval** (models-eng and models-lead, G-a5): a redacted card's blended scores are null or removed in every store (E-b2 item 5, models-lead addendum J2). Eval doesn't exclude redacted cards yet: today a null score reads as 0. models-lead's J1 makes `partner_redacted` a deck exclusion for replay, e(k) and calibration, and skips redacted cards in the fit, in models-eng's PR C. head-eng was told 10-31 that `base_score` and `final_score` fail, where the routing expected them kept. If Eng wants to keep either, it goes to legal; until then they're nulled.

## 2. Schema & flag scope

- **New table `deletion_scrub_jobs`** (§0.1). Private: it holds the deleted user's ids, only until the scrub finishes. It's not a user's data to export, since the user is gone, and it's not in `_ADDITIONAL_PRIVATE_TABLES`.
  - It's a new, empty table, so `create_all` makes it with no boot DDL.
  - An index on `deleted_at` serves the alert scan.
  - → `docs/data-dictionary.md`.
- **New/changed feature flags:** none. The scrub runs on every deletion, unconditionally, like #523's deletion fix (d1).
- **New `model_config` keys:** none.
- **Rollback lever:** none needed for correctness; it only rewrites a deleted user's traces. A runaway job is stopped by deleting its row (an operator action, documented in the runbook).

## 3. Evidence scope

- [x] **Unit tests** (`backend/tests/test_deletion_scrub.py`):
  - **the job:**
    - written in the deletion transaction (and not on a rollback);
    - leagues captured before `league_members` goes;
    - the lease (two runners, one claims);
    - retried after a raise;
    - the 24 h alert's counts;
    - no id in any log line;
  - **each store:** a seeded deck with one card for the deleted partner and one for another member. The partner's card is tokenized, its c2 keys are removed and its blended scalars nulled; the other card is untouched.
  - **uniformity:** every card of the partner, in every store, the same way;
  - **G-a2:**
    - a real pack scrubbed and unpacked: every non-redacted card is bit-identical, and the redacted ones differ only in the four changes;
    - a fixture replay leaves non-redacted **decks** bit-identical, and redacted decks are excluded, not compared (models-lead J2; models-eng's, in PR C);
  - **the CAS race:** a live writer's header commit after a scrub keeps the scrub;
  - **idempotence:** a second run changes nothing;
  - **decks built after the deletion are untouched;**
  - **the tick:**
    - `deletion_scrub` runs right before `value_model_refit` (order pinned);
    - a raise keeps the row;
    - the second DB pass after the grace;
  - **export:** another user's export after the scrub holds no id and no c2 field of the deleted user.
- [x] **Sabotages** recorded in TEST_LEDGER: one per store, plus the lease, the order and the CAS rebuild.
- [x] **Structural guard / TestFlight checklist: WAIVED.** Backend only, with no client surface.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `DELETE /api/account`: the job, the side tables and their counts in `deleted`; `POST /api/cron/daily-tick`: step 9 `deletion_scrub`, ten steps |
| `living-memory/LLD.md` | updated | deletion: the scrub job and its two phases |
| `docs/architecture.md` | updated | account deletion's data flow: the scrub after the transaction |
| `living-memory/HLD.md` | n/a | no new module class or client; one step inside deletion |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md` | updated | "redaction token" |
| ADR or `DECISIONS.md` | updated | DECISIONS: the scores nulled (§1.3), and the job-in-transaction design |
| `docs/data-dictionary.md` | updated | `deletion_scrub_jobs`; `deck_impressions` / packs: what a redacted card holds |
| `docs/runbook.md` | updated | the 24 h alert; stopping a job |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck`, `testid-lint`.
- **Evidence recorded:** TEST_LEDGER, one entry per PR.
- **Staging, three PRs:**
  1. the job, the deletion hook, the runner and tick, rows, candidate sets, the side tables (`user_taste`, `standing_offers`, `trade_matches`) and the model store;
  2. packs through the codec, the CAS fix, the page store and the in-flight pass;
  3. the traced items (f), `grading_cards` and diagnostics (built: #559's follow-up). It sets `COMPLETE`. The trace found `features.presentation` partner-free (indexes and player counts only); the narrative goes from a redacted page card, and value_core's blended scores go (§1.3).
  - Packs and the page store are empty in prod until the flip (`trade.packed_evidence` off). PR 2 lands before the flip.
- **The three ship together, #557 → #559 → #562, in one release** (release-lead's plan). The job rows that hold the deleted ids are only deleted once #562 sets `COMPLETE` (`_finish`) and the 30-day stop (`_abandon`). Deployed alone, #557 or #559 would keep every deletion's row until #562 deployed. The merge waits on the flip's 24 h read, models-lead's R-G and the operator's go.
- Express lane declared by the operator? No.

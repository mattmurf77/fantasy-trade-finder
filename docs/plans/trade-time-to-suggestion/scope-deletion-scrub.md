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
  - `last_error_code`, a class name only, never a message.
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
    - **The alternative,** a partner→deck side index written at deck time, covers only new writes. Existing rows would need the same full read as a backfill, plus a change on the hot evidence writer. So the scan was picked.
    - Stage 2 scans packs' `header_json` and the page store the same way.
- **Two phases.** The row is deleted only when both are done.
  - **DB phase:** every store in §0.2, first the league pass, then the fallback scans. It runs in a background thread the deletion route kicks, and the cleanup loop retries any row past its lease and resumes an unfinished scan. The lease is a CAS claim on `claimed_until`, so two instances during a deploy never run one job twice.
  - **Model phase:** `eval.redaction.redact_model_store(tokens)`, in the daily-tick step `deletion_scrub`, placed **before** `value_model_refit` (models-eng 8b, #542). It runs only for jobs whose DB pass is current, so the refit trains on scrubbed rows. A test pins the order. A raise leaves the row for the next tick.
  - **The DB phase runs once more after `IN_FLIGHT_GRACE` (6 h),** from the cleanup loop. That catches rows a deck already in flight at deletion wrote later from its build-time snapshot (§0.4).
  - **Until every stage is built (`COMPLETE`), finished rows are kept,** so a later stage's `SCRUB_VERSION` re-runs them. legal (ix) is about finishing the scrub, and the scrub isn't finished until then.
- **Alert:** each tick, if any row is older than 24 h, the log gets `[scrub] unfinished jobs=<n> oldest_h=<h>` at ERROR (counts only). A row older than 30 days isn't abandoned: it keeps retrying and keeps alerting (ix).

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
| `bakeoff_runs` (other users'; found by legal f's trace, 10-31, so a correction to the c3 list's "partner-free") | any id in `config_json` | the owner request's frozen `input` holds every league member's board, sources, preferences and declared and inferred outlooks; the person's member loses `elo` / `board_updated_at`, and their `opponent_sources`, `manager_preferences`, `opponent_outlooks` and `inferred_outlooks` entries go | — |
| `trade_page_store` (stage 2) | `pages_blob` `target_user_id` (→ token) and `target_username` (→ the placeholder); `evidence_blob` rows and ghosts, the same as `deck_impressions`; its candidate set; `trade_impressions[].target_user_id` → NULL (as deletion does to the table); `run_meta.filter_inputs` the same as the pack run; any other id mention → token | a redacted page card loses `likes_you`, `standing_offer_reason`, `reasons`, `rationale`, `fit`, `breaker` and `match_context.opponent_outlook`; the narrative is stage 3's trace | `mismatch_score`, `composite_score` (and the row's scores) |
| `user_taste` (other users) | attribute `partner:<id>` → `partner:<token>`; two aliases of the person merge into one row (weights summed). In the deletion transaction | — | — |
| `standing_offers` (other users) | `team_user_ids`, in the deletion transaction | — | — |
| `grading_cards` (other users) | — | `trade_json.partner_name` → placeholder (stage 3: the cards hold a display name, not an id, so finding them needs the trace) | — |
| `trade_matches` | ids are already the placeholder today | `match_valuation_json` cleared whole when either side is the person, in the deletion transaction (it holds user_a's own board as the viewer and user_b's as the partner; the `trade_proposals.valuation_json` precedent) | — |
| model store | E-b3 (`redact_model_store`) | — | — |
| `deck_diagnostic_snapshots` | — | stage 3: rows older than 30 days are deleted by the scrub (they expire at 14 days today) | — |

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
- **A redacted page card never serves** (`_redacted_target`): it leaves with the I-1 drops as a withdrawal, whatever the I-1 mode.

### 0.4 Decks in flight at deletion

- A live job's `_DeckEvidence` holds unwritten rows from its build-time snapshot. A delivery after the scrub writes them, and with them the old id and the c2 fields.
- **The tick's second DB pass rewrites them.** The window is at most until that tick.
- The page store's cards keep serving through S0's I-1 check. The person's `league_members` rows are gone, so a card receiving their assets fails I-1 and is withdrawn, never served.

## 1. Analytics scope

- [x] **(c) WAIVED. No analytics needed.**
  - The scrub emits no event and changes none. It is a deletion step.
  - Its observable is one server log line per job phase, `[scrub] job db_done counts={store: n}` / `model_done changed=<n>`, plus the 24 h alert. They carry counts, never ids.
  - Eval's side (G-a4 to G-a6: redacted cards counted, not auditable, explained replay differences) is models-eng's.

### 1.3 Blended scalars: the solve-back test (R28.22 b)

| Value | What it is | Kept beside it | Result |
|---|---|---|---|
| `basis` | `"divergence"` / `"consensus"` | — | **keep** (legal: it only says the partner has a board) |
| `surplus_margin` (= `mismatch_score`) | harmonic mean of `fit.you` / `fit.them` (`trade_gen_fit.py:470-472`); v2 `user_gain` / `opp_gain` | `fit.you` (the viewer's) | **FAILS:** `them` solves from `you` and the mean. **Nulled** (legal's list) |
| `base_score` (= `composite_score`) and `fit.aggregate` | `aggregate_raw = you_raw + them_raw` on fit cards (`trade_gen_fit.py:475`, `:778-788`); on a liked card, the likes boost sets it to the deck's max + 1.0 (`server.py:8319`) | `fit.you` | **FAILS, both:** `them = aggregate − you`, and the +1.0 over the deck's max encodes the like. **Both go:** `base_score` nulled, `fit.aggregate` removed |
| `final_score` | `base × propensity × fatigue × taste × diversity` (`server.py:9300-9328`, the post-multiplier key) | `propensity`, `taste_pref_*` | **FAILS:** with the stored multipliers it recovers `base_score` (fatigue is 1 on most cards). **Nulled** |
| `propensity` | the Thompson multiplier the viewer's sampler drew (`server.py:9206`) | — | **keep:** the viewer's own sampling, with no partner input |

**Consequence for eval** (models-eng and models-lead, G-a5): a redacted card's three scores are null in every store. Replay already counts redacted cards apart (G-a4 to G-a6). head-eng was told 10-31 that `base_score` and `final_score` fail, where the routing expected them kept. If Eng wants to keep either, it goes to legal; until then they're nulled.

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
    - a fixture replay leaves non-redacted cards bit-identical;
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
  3. the traced items (f), `grading_cards` and diagnostics. It sets `COMPLETE`, so finished jobs are deleted from then on.
  - Packs and the page store are empty in prod until the flip (`trade.packed_evidence` off). PR 2 lands before the flip.
- Express lane declared by the operator? No.

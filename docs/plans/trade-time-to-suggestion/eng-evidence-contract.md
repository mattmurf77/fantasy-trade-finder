# Evidence contract: scorer inputs, page contracts, and the C8 archive

> **Purpose.** This is the spec trades-eng's evidence writer and page store implement against. It covers: the scorer inputs a narrow or packed card must keep (C7), what a paged deck must preserve (AC-9 and P2), how the whole-deck archive is chosen and stored (C8), which decks are never stored at all, and the packed-evidence row, its version discipline and how eval reads it (C1, C7 (i)–(iv)). Source: `docs/plans/org-bringup/leads/models-lead-launch.md` §DEC-2, conditions C1–C9, and §Reviews-2 R2.2 / R2.5. Built and tested on branches `eng/eval-scorer-contract` (2026-10-20) and `eng/packing-stage-2` (2026-10-24). If this file and the code disagree, the code and its tests win, and this file gets fixed.

## Contents

- [1. The C7 contract as built](#1-the-c7-contract-as-built)
- [2. AC-9 and P2 page contracts](#2-ac-9-and-p2-page-contracts)
- [3. C8 archive spec](#3-c8-archive-spec)
- [4. The safety-ceiling rule](#4-the-safety-ceiling-rule)
- [5. Field-set note](#5-field-set-note)
- [6. The pack row contract](#6-the-pack-row-contract)
- [7. Pack version discipline](#7-pack-version-discipline)
- [8. Reading packs, and the exclusion-rule version](#8-reading-packs-and-the-exclusion-rule-version)
- [9. Candidate-set packing](#9-candidate-set-packing)
- [Decisions needed](#decisions-needed)
- [Handoffs](#handoffs)

## 1. The C7 contract as built

**Where:** `backend/eval/contract.py`. These are the exact sets.

| Set | Keys | Meaning |
|---|---|---|
| `COMPACT_KEYS` | `give_value`, `receive_value`, `surplus_margin`, `fairness_score`, `ranked_player_count`, `shape`, `lane`, `basis`, `give_positions`, `receive_positions`, `involves_pick`, `likes_you`, `relaxed`, `user_value_basis` | Exactly the card keys `value_model.extract_features` reads |
| `INJECTED_COMPUTED_KEYS` | `_pref_long`, `_pref_short`, `_partner_rate`, `_position` | Written into the model input by `ValueModel._inject`. **Never stored** |
| `INJECTED_CARD_INPUTS` | `partner_user_id`, `taste_pref_long`, `taste_pref_short` | Read from the card by `_inject` to compute the keys above. **Must be frozen.** The two taste matches are the prefMatch values `taste_service.taste_multipliers` ordered the card by (R4.1): float8, absent when the taste layer didn't run, read as 0.0 |
| `INJECTED_KEYS` | `INJECTED_COMPUTED_KEYS` ∪ `INJECTED_CARD_INPUTS` | |
| `FROZEN_PROVENANCE_KEYS` | `taste_attrs` | Frozen with the block but read by no scorer: the source of the frozen taste matches |
| `FROZEN_INPUT_KEYS` | `COMPACT_KEYS` ∪ `INJECTED_CARD_INPUTS` ∪ `FROZEN_PROVENANCE_KEYS` (18 keys) | What a narrow or packed card's frozen block must hold |
| `IDENTITY_KEYS` | `impression_id`, `deck_job_id`, `user_id`, `league_id`, `trade_hash`, `archetype`, `shape_bucket`, `served_at` | Logged columns `card_dict` always merges in. Any scorer may read them |
| `LOGGED_POLICY_KEYS` | `card_index`, `propensity`, `base_score`, `final_score` | Encode the logged policy. Readable only where `PERMITTED_LOGGED` grants them |

`PERMITTED_LOGGED`, per registered scorer:

| Scorer | Logged columns it may read |
|---|---|
| `logged` | `card_index` |
| `production` | `final_score`, `base_score` |
| `base_score` | `base_score` |
| `random` | none |
| `value_model` | none (compact plus injected only) |

**The contract:** the keys a scorer reads from `card_dict(card)` must be a subset of `COMPACT_KEYS ∪ INJECTED_KEYS ∪ IDENTITY_KEYS ∪ PERMITTED_LOGGED[name]`, which is `allowed_keys(name)`.

**Rule for adding a feature (from 2026-10-20):** a feature joins `COMPACT_KEYS`, and the writer that freezes the block, **before** any scorer reads it. Unseen cards written before that date can't be backtested on the new feature, except on the C8 archive (§3). A new scorer without a `PERMITTED_LOGGED` entry fails the registry guard.

**Reader** (`backend/eval/data.py`):
- `LoggedCard.features_compact`, `LoggedCard.evidence_tier` and `LoggedCard.delivered_at` are filled from columns of the same names (`data.OPTIONAL_COLUMNS`), but only for a column the live table has; otherwise the field is `None`. #370 adds `evidence_tier` and `delivered_at`; `features_compact` is in no schema yet. **The optional columns are read from the live table:** `load_decks` inspects the DB's own columns on every read, never the code's table metadata. So a DB that #370's migration hasn't reached (an old SQLite snapshot) still loads while the code's metadata declares the columns, and a DB column the metadata lacks is still read.
- `card_dict` uses `features_json` when it is present, else the compact block. Logged columns win key collisions.
- Packed cards are merged in from `deck_evidence_packs` when that table exists (§8).

**Exclusion rules:**
- **Replay** (`backend/eval/replay.py`):
  - A deck in which **any** card has `evidence_tier == 'partial_run'` is excluded whole, under `partial_run`. This check runs before `missing_scorer_inputs`, so such a deck is never counted twice. Cards are counted in `EvalRun.excluded` and decks in `EvalRun.partial_run_decks`; both appear in the report and the run record.
  - A deck in which **any** card has neither `features_json` nor a compact block is excluded whole, under `missing_scorer_inputs`. It is never sunk.
  - The excluded cards are counted in `EvalRun.excluded`, and the decks in `EvalRun.missing_inputs_decks`. Both appear in the rendered report and the persisted run record (`backend/eval/persistence.py`).
  - Replay no longer has the per-card `bad_features` reason.
  - Six more whole-deck reasons come from the loader (§8), at most one per deck: `calibration_refresh`, `pack_integrity`, `withdrawal_conflict`, `in_flight`, `incomplete_deck` and `no_delivery_evidence`. Replay's order is `calibration_refresh`, `partial_run`, then the other loader reasons (`in_flight`, `pack_integrity`, `withdrawal_conflict`, `incomplete_deck`, `no_delivery_evidence`), then `missing_scorer_inputs`, then `scorer_error`, so no deck is counted twice.
- **Calibration** (`backend/eval/calibration.py`):
  - Exclusion is per card, since there are no ranks here.
  - A card with neither input is excluded alone, as `bad_features`.
  - A card with only a compact block is scored.
  - Every card of a `calibration_refresh` deck (§8) is excluded under that reason, first.
  - A card with `evidence_tier == 'partial_run'` is excluded alone, as `partial_run`, next, before the other per-card checks.
  - Every card of a deck with any other loader exclusion (`pack_integrity`, `withdrawal_conflict`, `in_flight`, `incomplete_deck`, `no_delivery_evidence`) is excluded under that reason, next.
  - A never-delivered withdrawn card (§8) was removed by the loader, so calibration never sees it or counts it.
- **Who writes `partial_run`:** trades-eng, on the delivered rows of a partial run (head-eng ruling 21). Calibration's `select_current_cards` must also skip such jobs; that file belongs to trades-eng.

**Lean nightly** (`backend/eval/nightly.py`; the eval pass runs last in the daily tick):
- `run_all` decides which scorers are due **before** loading anything. With nothing due, it returns without calling `load_decks`, and no baseline is evaluated or recorded.
- `load_decks` selects only `EVAL_COLUMNS`, never `select(imp)`. Those columns are `impression_id`, `user_id`, `league_id`, `deck_job_id`, `card_index`, `trade_hash`, `features_json`, `propensity`, `base_score`, `final_score`, `archetype`, `shape_bucket`, `served_at` and `is_ghost`. It adds `features_compact`, `evidence_tier` and `delivered_at` only when the live table has them.
- The nightly passes `project_features=True`, which keeps only `contract.PROJECTION_KEYS` in each parsed features dict. `PROJECTION_KEYS` is every key some registered scorer may read; it contains `FROZEN_INPUT_KEYS ∪ IDENTITY_KEYS`. Nightly estimates and a value-model fit are bit-identical with and without projection.
- On a synthetic 30-day window of 9,000 rows, tracemalloc's peak for `load_decks` went from 146 MB (`select(imp)`) to 53 MB.

**Reproducibility (R4.1, R5.2): inputs are frozen per card; configuration is pinned and recorded per run.**
- No fit or eval path reads live taste state. `ValueModel._inject` reads the frozen `taste_pref_long` / `taste_pref_short`; only `value_model.serving_scores` (live serving) calls `taste_service.load_taste_vectors`.
- `value_model.train_model(decks, as_of=..., config=...)` takes its clock explicitly. It also takes its 3 hyperparameters as a recorded `pin_config` record (`meta["config"]`).
- The value_model scorer takes the V-vector the same way, as a constructor argument: `get_scorer("value_model", config=...)`. The replay CLI (`--config`) and the nightly pin once and pass the pin to every scorer; scorers that read no config ignore it. `replay.evaluate` records `scorer.config` on `EvalRun.config` and in `run_record["config"]`. Each record carries the values used and the `model_config` SHA-256.
- A re-fit at the same `as_of`, on the same evidence and config, is bit-identical, whatever the taste rows, boards, clock or live `model_config` do in between.
- The rule is in `docs/model-evaluation/evidence-contract.md` §"Frozen inputs". Tests: `backend/tests/test_value_model_frozen_taste.py`.

**Tests:**
- `backend/tests/test_eval_scorer_contract.py`:
  - `test_scorer_reads_only_contract_keys[<every registered scorer>]`
  - `test_value_model_contract_run_actually_reads_the_card`
  - `test_compact_keys_are_exactly_what_extract_features_reads`
  - `test_injected_keys_are_exactly_what_inject_reads_and_writes`
  - `test_card_dict_logged_columns_are_all_classified`
  - `test_every_registered_scorer_declares_its_logged_columns`
  - `test_compact_block_scores_like_full_features[<every registered scorer>]`
  - `test_compact_keys_alone_do_not_replay_value_model`
  - `test_card_dict_prefers_features_and_logged_fields_win`
  - How value_model is checked: a model is fitted in-test with `value_model.train_model` and graded through the registered scorer. The card is wrapped in a dict that records every key read through `[]`, `get`, `in` and iteration.
- `backend/tests/test_eval_replay.py`:
  - `test_exclusion_accounting_adds_up`
  - `test_deck_missing_scorer_inputs_is_excluded_whole_not_sunk`
  - `test_compact_only_card_is_scored_not_excluded`
  - `test_run_record_persists_missing_inputs_decks`
  - `test_partial_run_deck_is_excluded_whole_and_persisted`
  - `test_load_decks_compact_block_absent_without_the_column`
  - `test_load_decks_reads_features_compact_when_the_column_exists`
- `backend/tests/test_eval_calibration.py`: `test_calibration_scores_compact_only_cards`, `test_calibration_excludes_partial_run_cards`.
- `backend/tests/test_eval_pack_reader.py` and `backend/tests/test_evidence_pack.py`: the pack reader, the codec and the golden (§8).
- `backend/tests/test_eval_nightly_lean.py`: the early return when nothing is due, the selected column set, projection keys, and bit-identical nightly estimates and value-model fit with and without projection.
- `backend/tests/test_eval_archive_selection.py`: C8 selection (§3).

## 2. AC-9 and P2 page contracts

**Where:** `backend/tests/support/deck_contracts.py`. Self-tests are in `backend/tests/test_deck_contracts.py`.

**Identity:**
- `card_identity(card)` = sha256 of `sorted give ids joined by "," | sorted receive ids joined by "," | partner or ""`, truncated to 16 hex characters.
- This is the formula of `server._deck_trade_hash`, so it equals the `trade_hash` logged on the card's `deck_impressions` row. It is restated rather than imported, because importing it would import the server. `test_identity_matches_server_hash_for_every_card_shape` pins the two together.
- It is never `trade_id`, which is a uuid4 minted per build.
- It accepts four card shapes:
  - a `TradeCard`;
  - a served card dict from `trade_card_to_dict` (`give` and `receive` lists of player dicts);
  - a dict with `give_player_ids` and `receive_player_ids`;
  - a `deck_impressions` row, which has only `trade_hash`.

**The two assertions:**
- `assert_page_is_top_n(page_cards, full_deck_cards, n, page_engine_version, full_engine_version)` checks that page 1 equals the full deck's top N: the same identities, in the same order, from the same engine version. If the full deck is shorter than N, the page must be the whole deck.
- `assert_prefix_stable(delivered_pages, later_deck_pages)` compares pages flattened, since `card_index` is a position in the whole deck. The cards already delivered must keep their identities and order at the head of the later deck, and the later deck's other cards must repeat none of them.

Both raise `AssertionError` with a position-by-position diff.

**How trades-eng calls them from its page-store tests:**

```python
from backend.tests.support.deck_contracts import (
    assert_page_is_top_n, assert_prefix_stable, card_identity)

# full_deck: the job's complete ranked deck. page_1: what the store sent first.
assert_page_is_top_n(page_1, full_deck, PAGE_SIZE,
                     page_engine_version=..., full_engine_version=...)

# After each later delivery (prefetch, scroll) and after any rebuild that
# keeps delivered pages: all pages served so far vs the deck as served now.
assert_prefix_stable(delivered=[page_1, page_2], later_deck_pages=later_pages)
```

**Precondition:** the engine is deterministic on frozen inputs. Two harness runs give identical decks by identity and order (`test_trade_job_is_deterministic_on_frozen_inputs`, via `backend/tests/support/bakeoff_harness.py`).

## 3. C8 archive spec

**Selection:**
- `backend/eval/contract.py` holds the one definition. trades-eng's writer imports it:

  ```python
  is_archive_deck(deck_job_id) = int(sha256(("c8-archive-v1|" + deck_job_id).encode()).hexdigest()[:8], 16) % 10000 < ARCHIVE_RATE_BP
  ARCHIVE_RATE_BP = 200   # 2% of served decks
  ARCHIVE_DAYS = 90
  ```

- It takes the deck id only: no user, league, content or clock.
- Only **served** decks are candidates. Under C2, a pre-build that is never served writes nothing, so it is never an archive deck.
- Tests (`test_eval_archive_selection.py`) check four things: the result is deterministic and matches the formula; the rate on 100,000 synthetic uuid4-hex ids is within 2.0% ± 0.2 pp; the function takes exactly one parameter; and the constants are as above.

**Writes:**
- **The pack is written for every served deck, archive decks included.** The archive adds rows. It never replaces the pack.
- An archive deck also gets a full `deck_impressions` row for every card that isn't otherwise full: not delivered, not in the first 30, and not a ghost. Each row is written from the build-time snapshot (C6), never recomputed.
- Those rows carry a tier marker. The proposed column is `evidence_tier` ∈ `delivered | first30 | ghost | archive`. **The schema belongs to trades-eng, under head-eng's grant.**

**Retention:**
- A daily, bounded prune deletes `archive`-tier rows older than `ARCHIVE_DAYS` (90).
- It leaves the pack intact, so the deck stays replayable from the pack plus its surviving full rows.

**Eval side:**
- Archive decks are read through a loader filter, built after the column exists.
- When a card has both a full row and a pack entry for the same `card_index`, **the full row wins** (built: §8).

**Cost:** about 2% × (N − 30) × ~9 KB per served deck. With N ≈ 1,700 cards per served job (models-lead-launch §DEC-2 §1), that is about +0.3 MB per served deck on average, held for 90 days.

## 4. The safety-ceiling rule

The following decks are **never stored, paged, served or packed**:
- a deck from a run where `CoreDiagnostics.safety_ceiling_hit` is true;
- a deck from a failed job;
- a deck from a partial job.

They write no `deck_impressions` rows, no pack and no archive rows. The diagnostic is on the value-core branch `eng/value-core-count-bounded`, which isn't on main yet. That branch's `blind_grading.py:581` already refuses such runs for Calibration. The evidence writer and the page store apply the same refusal.

## 5. Field-set note

A narrow row's compact block, or a packed card, must freeze `FROZEN_INPUT_KEYS`: `COMPACT_KEYS` ∪ {`partner_user_id`, `taste_pref_long`, `taste_pref_short`, `taste_attrs`}. `COMPACT_KEYS` alone isn't enough.
- Without `partner_user_id` and the frozen taste matches, `_inject` falls back to the global like rate and the 0.0 taste anchor, and value_model's score moves.
- `test_compact_keys_alone_do_not_replay_value_model` pins the gap.
- `test_compact_block_scores_like_full_features` shows the 18-key block replays every registered scorer exactly.
- models-lead-launch §DEC-2 §2 lists the 14 keys only. R4.1 added the two taste matches.

The packed format was accepted by models-lead with conditions (models-lead-launch §Reviews-2 R2.2). It ships from `eng/packing-stage-2` as `PACK_VERSION = 1`, with the checksum extended to the header and run metadata (§6, §7), and with R4.1's two taste matches and R4.2's deliveries added before the format froze, so no version bump. `test_codec_carries_every_key_the_contract_names` pins the codec to the contract: every key in `FROZEN_INPUT_KEYS`, `IDENTITY_KEYS`, `LOGGED_POLICY_KEYS` and every `PERMITTED_LOGGED` column is carried by the pack, except `impression_id`, which is deterministic (§8). A contract key the codec doesn't carry fails it.

## 6. The pack row contract

**Spec for trades-eng, who builds the table** in `backend/database.py` under head-eng's schema grant. The same definition is test-local in `backend/tests/test_eval_pack_reader.py` (`pack_table`); the eval tests run against it.

**Table `deck_evidence_packs`**, one row per served run:

| Column | Type | Meaning |
|---|---|---|
| `run_id` | String, **primary key** | The deck's `deck_job_id` |
| `user_id` | String, NOT NULL | The user the deck was served to |
| `league_id` | String, NOT NULL | |
| `served_at` | String (ISO UTC), NOT NULL | The deck's **first delivery** (ruling 21). It must equal the `served_at` on the deck's `deck_impressions` rows |
| `pack_version` | Integer, NOT NULL | Stored verbatim from `PackedRun.pack_version` |
| `header_json` | Text, NOT NULL | Stored verbatim from `PackedRun.header_json` |
| `cards_blob` | LargeBinary (BLOB on SQLite, BYTEA on Postgres), NOT NULL | Stored verbatim from `PackedRun.cards_blob` |
| `checksum` | String(64), NOT NULL | Stored verbatim from `PackedRun.checksum` (sha256 hex) |
| `card_count` | Integer, NOT NULL | Stored verbatim from `PackedRun.card_count` |
| `created_at` | String (ISO UTC), NOT NULL | When the row was written |

Indexes: `(served_at)` and `(user_id, league_id)`.

**The writer's call** (the codec is pure; it does no I/O):

```python
from backend.eval import evidence_pack

packed = evidence_pack.pack_run(
    run={"values_snapshot_id": ..., "built_at": ..., "config_ref": ...,
         "deliveries": [[last_card_index, delivered_at], ...]},   # JSON-serializable run metadata
    cards=[...],          # the packed card dicts, in card_index order
    card_count=N,         # the served deck's card count, ghosts excluded
)
# then insert one row: run_id, user_id, league_id, served_at, created_at,
# plus pack_version, header_json, cards_blob, checksum, card_count taken verbatim
# from the PackedRun (dataclasses.asdict(packed) gives exactly those five).
```

- **When** (models-eng, 2026-10-26): the pack row is written at the deck's **first delivery**, and its header is rewritten on every later delivery and when the deck retires (superseded by a newer deck, or the 24 h display cap, PRD #339 §5.1). **The cards blob is fixed at build:** it holds every built card, ghosts excluded, including cards withdrawn later (§8). Each rewrite repacks the same cards with the new run metadata (`pack_run`), so `header_json` and `checksum` change and `cards_blob` doesn't. Every packed field is the build-time value (C1, E1). Until the pack is final, replay skips the deck as `in_flight` (§8), which is not an error. A pack written before this change, at retirement, has no `retired` key and is final.
- `run` is the caller's per-run metadata. It comes back verbatim from `unpack_run` and is under the checksum. At least the values snapshot id (`vsn1`), `built_at` (R2.6), the config reference and **`deliveries`** (R4.2 U1, required). A pack written at first delivery also carries **`retired`** (bool: false until the deck retires) and, once retired, **`retired_at`** (ISO UTC). Optional keys eval reads: `page_store` (1 on the page-store path, §8) and `deck_source`. `deck_source` isn't a pack key, so if a Calibration refresh deck is ever packed (S8), the writer must carry `deck_source` here; today refresh decks keep full rows (#370).
- **`deliveries`** = the delivered page boundaries, `[[last_card_index, delivered_at], …]`, one entry per page sent to a client, `last_card_index` strictly increasing within `[0, card_count)`, `delivered_at` ISO UTC. Pages are delivered from card 0, so the delivered cards are 0..the last boundary. `pack_run` refuses a missing or malformed list (`evidence_pack.check_deliveries`). A device-held page counts when it is first sent.
- **Impression ids (R4.2 U2):** every non-ghost card of a served deck, whether its row is full or it is packed, has `impression_id = contract.card_impression_id(run_id, card_index)` = `f"{run_id}:{card_index}"`. The writer gives full rows that id, the page payload carries it, and **the client posts outcomes with it**. Import the function; don't restate the format. A ghost row keeps a different id (a uuid4): its would-have-been rank can equal a served card's index.
- **Upgrade on view (R4.2):** a card's first outcome of any kind upgrades it to a full row with the same id. It stays in the pack too, and the row wins. If the upgrade never happens, the outcome still joins the packed card by id.
- **U4, as reworded by models-lead (addendum C (c4), U4-R1, replacing addendum A's wording):** "A display past snapshot retention is impossible, with two named exceptions, both for a card at or past the deck's effective stored count (its current page-row count, else 0): `restart_split`, when this process never held the deck's job, and `evicted_split`, when this process evicted it. Each is counted per run, its outcome joins the packed card by `impression_id`, and it scores normally in eval. Any other miss is a defect (`other`, must be 0)." The count is the run metadata's **`upgrade_misses`**, an object with every key always present, `{"restart_split": <int>, "evicted_split": <int>, "other": <int>}` (U4-R2, refined by #428 QA): `restart_split` iff the card is at or past the deck's effective stored count (addendum C (c1): the page store's count now, the job's, or on the stored path the deck's current page row's `card_count`, 0 with no row, option A; with option A off it would be the pack's `stored_count`, else 0). The pack's `stored_count` is the count recorded when the deck was stored, and it is never rewritten (addendum C (d3): the store miss, the late store and the CAS merge only fill it when absent; the effective count is computed at miss time, for classification only). The writers record it: a store that wrote its row, its card count, set on the deck only once the save is known and under the write lock, so a delivery never packs a refused store's count (#438 QA P3-2); a store that wrote no row (it raised, the supersede guard refused it, the deck wasn't page-eligible or was revoked, or the kill knob turned the store off), 0; a pack first written on the stored path, the row's count (#438 QA P2-1). With no record (a process that died between its pack's first write and its store) it reads 0, the fallback; the knobs are never read. A miss below the effective count is `other`, whatever the provenance), the pack records its delivery (a card its `deliveries` don't reach, the update lost, is `other` for both named causes), and this process never held the deck's job, i.e. another process built it (a restart, a deploy overlap, a re-fork); `evicted_split` iff the same card's job was evicted by this process (4 h), named per addendum C (C1) (`server._EVICTED_SPLIT_NAMED`, True; off, those misses would count as `other`); this process's records of the decks it built and evicted (`_deck_held`, `_deck_evicted_at`) keep each entry at least the 24 h display cap (addendum C (c2): OrderedDicts trimmed by age, O(1) per entry; a 131,072-entry count cap is only a memory guard, and it logs a warning, at most once a minute, if it ever trims a younger entry; an eviction drops the deck's held entry, so a view after its eviction record ages out reads `restart_split`); anything else is `other`, which must be 0 (the writer logs each `other` at error level). The cause comes from provenance, not a clock (#428 QA: an import-time stamp called a deploy overlap's or a re-fork's misses `other`), through one hook, `server._upgrade_miss_cause`; it assumes one gunicorn worker per instance (`render.yaml` `--workers 1`, pinned by a test; `--preload`, Render's default through `GUNICORN_CMD_ARGS`, is fine because the ledgers are empty after import, pinned by a child-interpreter test). Eval reads any key but `other` as a named cause. Each miss also logs one server line with the cause its header commit kept: in a deploy overlap the CAS merge keeps the stored cause, and the second writer's line logs that one with its own as `local_cause=`, at WARNING, so only a kept `other` is an ERROR line (#439/#445 QA P3-1). A pre-built deck whose evidence F5 dropped undelivered (`_drop_stale_deck_evidence`, 30 min) is this process's eviction (models-lead addendum D1): the drop records it in the evicted ledger, kept ≥ 24 h (C3 (c2)), instead of removing it from the held one, so a miss on it once its stored pages are served and its row goes reads `evicted_split`. Below the effective stored count a miss is still `other` (C3 (c1)). An F5-evicted miss at or past the pack-recorded stored count should be impossible (only an F5 deck's stored pages can be delivered); it logs `[evidence] f5_past_stored …` at ERROR, apart, for models-lead. Beside it the run carries **`upgrade_miss_cards`**, `{"<card_index>": cause}` (string keys, the same causes; absent reads as `{}`): each card that missed, once, its first cause standing. `upgrade_misses` is always that map's tally (the writer's invariant, pinned by a test). Concurrent header writers merge the maps as the union, the stored cause winning a conflict, and re-tally, so a card two writers missed counts once. Eval reads only the named run keys; #424's reader (`database.load_viewed_without_full_row`) takes each acted-on, no-full-row card's cause from this map (no pack or no entry: `other`). The run also carries **`upgrade_miss_row_gone`**, `{"<card_index>": <int>}` (string keys; absent reads as `{}`): each miss on the stored path whose deck's page row was gone (a newer deck's store replaced it, or `evict_trade_pages` deleted it) while the pack's recorded `stored_count`, the value, was above the card (head-eng's condition 1). It is written in the same header commit as the card's map entry and only when that entry is new, whatever option A's setting; a commit that raises takes both back; the CAS merge unions it, the stored entry winning; every key in it is a key of `upgrade_miss_cards` (models-eng's flip_read joins them). It is a report field, not an eval input (addendum C (d4)); models-lead's (d1) split of it is **`upgrade_miss_row_gone_why`**, `{"<card_index>": "replaced" | "no_row"}` (string keys; absent reads as `{}`). A page-scoped deck's run records its page-store key, **`scoring_format`** and **`page_scope`** (omitted for a deck with no page scope; its league is on every packed card), so a row-gone miss reads the key's current row once (`database.load_trade_page_deck_job_id`, the unique-index read of one column): another deck's row is `replaced` (explained), none is `no_row` (aged, over budget, or a bug). Only the row-gone path reads it, never a normal upgrade. The why is written in the same commit as its row-gone entry, only with it, once per card; a commit that raises takes both back; the CAS merge unions it, the stored entry winning, kept to row-gone keys, so why keys ⊆ row-gone keys ⊆ miss-map keys. A pack written before the key was recorded, or a failed read, writes no why: readers treat that entry as unsplit. **Option A** (`server._STORED_COUNT_FROM_ROW_NOW`, True: models-lead ruled it on in addendum C (C4), with head-eng's two conditions and (d1)-(d5); a one-line switch): on, a deck's stored pages are what the page store holds now, so the stored path's count is the deck's current row's `card_count`, 0 with no row, and such a card reads `restart_split` after a restart (`evicted_split` after this process's eviction); off, today's behaviour, the pack's recorded count, so it reads `other`. A deck still held here upgrades from its job's snapshot whatever its row did (condition 2). Each miss's server line names its count's source, `stored_from=` (`job`, `row`, `pack`, `no_row` with option A on, or `fallback`), and the fallback on a page-scoped deck also logs a warning (#438 QA P3-1).
- **Frozen taste matches (R4.1):** when the F5 taste layer ran for the deck, each card's features carry `taste_pref_long` and `taste_pref_short`: the two `_pref_match` values `taste_service.taste_multipliers` built that card's multiplier from, as float8. When the layer didn't run (flag off, no signal, bake-off fixed order), both keys are absent. The writer's test must pass `backend/tests/support/taste_parity.assert_frozen_prefs_match_multipliers` on a served deck.
- `cards` are card dicts as `backend.eval.data.card_dict` builds them, plus the `deck_impressions` attribution columns: `policy_version`, `candidate_set_id`, `candidate_set_size`, `model_arm`, `arm_rank`, `group_key`, `group_rank`, `lane_slot`, `fairness_threshold`, `centerpiece_id`. Every key outside `evidence_pack.CONTRACT_KEYS` is dropped. Every packed field is frozen at build time and never recomputed (C1, E1).
- The per-run fields (`user_id`, `league_id`, `deck_job_id`, `served_at`, `candidate_set_id`, `candidate_set_size`, `ranked_player_count`, `user_value_basis`, `last_board_update_at`) must be constant across the run. `served_at` on the cards is the first-delivery time too.
- `card_count` = N, the number of non-ghost cards in the built deck. The deck's full rows and its packed cards, together with its never-delivered withdrawals (§8), must hold `card_index` 0..N−1. `pack_run` refuses a packed index outside that range.
- **Deliveries are complete:** every card with an outcome is at or below the last boundary, because outcomes only come from delivered cards. A packed deck with an outcome past it is `incomplete_deck` (§8).
- `pack_run` refuses, with `ValueError`, anything it can't pack exactly: a ghost card (C5), an inexact type, a non-constant per-run field, unsorted indexes. It decodes its own output and refuses a pack that doesn't round-trip.
- **Write a pack row for every served deck** (ADR-025: "every served deck gets a pack"), even one with no packed cards. Its `card_count` is what lets the reader detect missing cards, and its `deliveries` are the deck's served set.
- **When the writer ships, set `backend/eval/data.PACK_REQUIRED_SINCE`** to its go-live time (ISO UTC). From then on a deck without a pack row is `in_flight` for 25 h after `served_at`, then `incomplete_deck` (a lost pack).
- **Deletion and export cover the table** (C7 (v), trades-eng): `delete_user_data` deletes the user's pack rows, and account export includes them.
- **Retention:** a pack lives as long as its deck's full rows (models-lead Confirmation §3).

## 7. Pack version discipline

Condition R2.2 (c), in `backend/eval/evidence_pack.py`:
- `PACK_VERSION = 1`, **frozen by models-lead on #388 @ f90f3c30** (R5.2). It holds the extended checksum, R4.1's `taste_pref_long` / `taste_pref_short` (float8 per-card columns, absent when the taste layer didn't run) and R4.2's `deliveries`. Any change from now on follows the rule below.
- `DECODERS = {version: decode_fn}`. `unpack_run` picks the decoder by the header's `pack_version` and refuses a version without one (`PackIntegrityError`).
- **The rule:** any change to the layout, an encoding or the checksum bumps `PACK_VERSION` and registers a new decoder. Packs live as long as their decks, so the reader decodes every version from 1 to `PACK_VERSION` forever. An old decoder is never deleted or edited while packs of its version exist.
- **Checksum (R2.2 (a)):** sha256 of one canonical JSON document, `{"header": <parsed header_json>, "cards": <unpacked cards>}` with sorted keys and compact separators. The header holds the run metadata, `card_count`, the shared per-run fields, the dictionaries and the layout. So tampering with the run metadata, any header field (even an unused dictionary entry) or any card fails the checksum.
- `unpack_run` also refuses a `pack_version` or `card_count` field that disagrees with the header.
- Tests (`backend/tests/test_evidence_pack.py`): `test_tampering_with_anything_a_reader_acts_on_is_refused[...]` (run metadata, a delivery boundary, a dropped delivery, a dictionary entry, an unused dictionary entry, a shared field, `card_count`, a card, the checksum), `test_malformed_deliveries_are_refused[...]`, `test_row_fields_must_agree_with_the_header`, `test_every_version_up_to_pack_version_has_a_decoder`, `test_unknown_pack_versions_are_refused[...]`.

**Measured** on the golden's 1,200-card writer deck (1,170 packed cards past the first 30), with the two taste matches on every card: 102.4 B raw and 74.8 B compressed per card, plus a 9.4 KB header, so **82.9 B per packed card all-in**. Without them it was 86.4 / 59.3 / 67.2 B (R2.2 measured about 64 B on 1,700 cards). The test's taste matches are full-entropy floats, the worst case for compression; real prefMatch values repeat across cards with the same attributes.

## 8. Reading packs, and the exclusion-rule version

**Reader** (`backend/eval/data.py`, `load_decks`), C7 (i):
- If the engine has a `deck_evidence_packs` table (`sqlalchemy.inspect(...).has_table`), packs are loaded with the same window and scope filters as the rows (`served_at`, `user_id`, `league_id`) and unpacked. **A missing table means no packs.**
- A deck's cards = its rows ∪ its unpacked cards, ordered by `card_index`, a non-ghost card before a ghost row at the same index. **A non-ghost row wins over a packed card with the same `card_index`** (an upgraded card, or a C8 archive card).
- **Ghost rows** (`is_ghost = 1`, now read with the eval columns) are never packed and never displace a packed card. Their `card_index` is a would-have-been rank, so it can collide with a served card's; they stay in the deck, as before.
- **A packed card** has `impression_id = contract.card_impression_id(run_id, card_index)`, the same id the writer gives its row and the client posts outcomes with (R4.2 U2). **Outcomes join it by that id**, so a viewed card left packed carries its outcomes, and an upgraded row (the same id) carries the same ones. It has `features = None`. Its `features_compact` holds every unpacked key that isn't a `LoggedCard` field: the frozen scorer inputs (taste matches included), the attribution and the per-run shared fields. Its logged fields (`trade_hash`, `propensity`, `base_score`, `final_score`, `archetype`, `shape_bucket`, `user_id`, `league_id`, `served_at`) come from the pack. `project_features=True` trims `features_compact` to `PROJECTION_KEYS` too.
- **Delivery (R4.2 U1):** in a deck with a pack, `LoggedCard.delivered` is true for a non-ghost card with `card_index` at or below the last delivery boundary. Ghost rows are never delivered. **The legacy rule (R5.2 (d)):** a deck without a pack, from before paging, delivered every served card, so delivered = served at every position (ghost rows included, as e(k) always counted them). Its e(k) is unchanged. **Paging defense in depth** (models-lead R2.4 addendum §3): the legacy rule applies only to a deck **without a page-store marker**, or to one served before `data.PAGING_RELEASED_AT` when that is set. A deck is marked when a non-ghost row's `features_json` or compact block (read before the projection trim) has `page_store` (`data.PAGE_STORE_MARKER`) = 1, a non-ghost row has a non-NULL `evidence_tier`, or its pack's run metadata has `page_store` = 1. A marked deck with a pack takes delivered from its `deliveries`. A marked deck without one is delivered where a non-ghost row's `delivered_at` is at or before `as_of` (any non-NULL one without `as_of`), so a re-read at the same `as_of` is stable. It is `no_delivery_evidence` when no row is delivered by then (or the live table has no `delivered_at`). So #370's stage-1 decks, whose undelivered cards still get `full_interim` / `archive` rows, never count those rows as served. **The exposure model's served set is the delivered positions:** e(k) counts only delivered cards. Undelivered cards stay in the counterfactual re-rank, since a candidate could have ranked them first. models-lead signed this off as a B3 eval behavior change: undelivered tails no longer pull e(k) down, so e(k) estimates rise, and the eval-rule version (below) records it.
- **In-flight packs** (models-eng, 2026-10-26; §6 *When*). A pack whose run has no `retired` key is final. One with the key:
  - with `as_of`: only `deliveries` entries with `delivered_at <= as_of` count, and the last delivered index is recomputed from them, so a re-read at the same `as_of` is the same after the writer updates the row. The pack is **final** iff (`retired` is true and `retired_at <= as_of`) or its `served_at` is before `as_of − IN_FLIGHT_WINDOW` (the 24 h cap plus 1 h). Otherwise the deck is `in_flight`;
  - without `as_of`: final iff `retired` is true, else `in_flight`;
  - `check_deliveries` still validates the whole list (`pack_integrity`).
- **Outcome consistency, every packed deck:** an outcome (as read, `acted_at <= as_of`) on a kept non-ghost card with `card_index` past the last delivered index means the deliveries are under-recorded (say, an update lost to a crash). The deck is `incomplete_deck`.
- **Serve-time withdrawals** (models-lead R2.4 addendum §2, option (ii); the `deck_card_withdrawals` read contract):
  - **The table** (trades-eng's; one row per card serve-time ownership rule I-1 withdrew, on the page-store path only; drops are sticky): `deck_job_id` TEXT and `card_index` INTEGER, UNIQUE together, the build index; `user_id`, `league_id` TEXT; `impression_id` TEXT NULL; `reason` TEXT; `first_withdrawn_at` TEXT (ISO UTC); `served_before` INTEGER 0/1, 1 iff an earlier response had delivered the card. The same shape is test-local in `backend/tests/test_eval_withdrawals_and_paging.py` (`withdrawals_table`).
  - **The read:** only when the engine has the table (`has_table`, like the packs), only for the decks loaded (`deck_job_id IN (...)`, chunked at 500 like the outcomes), and with `as_of` only rows with `first_withdrawn_at <= as_of` (re-read stable, R5.2 (b)). Eval selects `deck_job_id`, `card_index`, `served_before`, `first_withdrawn_at` and `reason`. **`reason` is only counted (models-lead B4): no rule gates on it.** The reasons today are `i1_dropped` (ownership rule I-1) and `disposition_cut` (the disposition cut, which withdraws cards at `trade_i1_mode` 1). `served_before` other than 0 is read as 1.
  - **`served_before = 0`** (W0, never delivered): the card is **removed from the deck for eval**. When present, as a packed card (the blob holds every built card) or a `first30` row with `delivered_at` NULL, it is dropped; it is never scored, never counted in exposure and never ranked. Its index **explains the gap** there. Withdrawal is policy-independent (ownership facts at serve time), so any policy would have faced it and removing it is unbiased. `LoggedDeck.withdrawn_removed` counts them, and `EvalRun.withdrawn_removed_cards` sums them over the decks replay includes; it is in the report and the run record, never an exclusion and never silent. **By reason** (B1 follow-up, B4): `LoggedDeck.withdrawn_removed_by_reason` splits the same removals by `reason`, as a sorted dict, and `EvalRun.withdrawn_removed_by_reason` sums it over the same decks (those replay includes). `withdrawn_removed_cards` stays the total. Both are in the report and the run record.
  - **`served_before = 1`** (delivered, then withdrawn): no effect. The card keeps its position and outcomes. With no card at its index, the gap is unexplained (`incomplete_deck`).
  - **Ghost rows** are ignored by every withdrawal rule: a ghost's `card_index` is a would-have-been rank that can equal a served index.
  - **Displayed position:** `LoggedCard.position` is the card's dense rank among the deck's kept non-ghost cards in `card_index` order, i.e. `card_index` minus the W0 indexes below it; with no withdrawals it is `card_index`. e(k) (`replay.exposure_curve`), the logged-position term of the IPS weight and value_model's training-only `position` feature read it: the user saw the displayed slot, and e(k) models P(viewed | the slot shown). Candidate ranks are computed over the reduced deck. `card_dict` doesn't carry it (scorers must not read served position). `deliveries` boundaries stay in build-index space.
  - **The equivalence** (models-lead's test): a deck with recorded withdrawals replays exactly as if the withdrawn, never-delivered cards had never been generated. That covers the estimates, `exposure_curve`, calibration and training rows, for row and packed decks, with the withdrawn cards absent or present.
- **Upgrade misses, cause-coded** (models-lead U4-R2): a pack's run metadata may carry `upgrade_misses`, the writer's count of viewed cards that never got a full row, as a dict of cause → int.
  - **`other` is the only cause that must be 0.** Every other key is a named cause: `restart_split` and `evicted_split` (U4-R1 as reworded in addendum C (c4), quoted under U4 above). The reader takes whatever keys appear.
  - A legacy int n reads as `{"other": n}`, which is conservative (it flags); the writer writes the object (#428). A missing key reads as `{}`.
  - `LoggedDeck.upgrade_misses` holds it, sorted; `{}` without a readable pack (none, or `pack_integrity`).
  - `EvalRun.upgrade_misses` sums it per cause over **every deck loaded**, whatever its exclusion and on both sides of an `--eval-start` split: it is a data-quality count, not a replay one. It is in the report and the run record, and `render_report` prints a line starting `ERROR U4-R2:` when `other` > 0.
  - Reporting only: no rule reads it, so `EXCLUSION_RULE_VERSION` stays 5. The bake-off readout's §7i reads the same counts straight from `header_json` (U4-R3).
- `value_model.build_training_rows` trains on a viewed card's frozen block in whichever form it arrived: `features_json`, else the compact or packed block. A viewed card fits the same whether or not it was upgraded. Its `position` is the displayed position.
- Every `evidence_tier` other than `partial_run` (`ghost`, `first30`, `delivered`, `archive`, `full_interim`) is a usable row.
- A pack whose run has no row in the window still makes a deck. With its rows missing, that deck is `incomplete_deck`.
- `load_decks(as_of=...)` is the read's explicit clock. The loader reads no wall clock. It reads only decks served at or before `as_of`, outcomes acted at or before it (`deck_outcomes.acted_at`, R5.2 (b)), withdrawals first withdrawn at or before it, and pack deliveries made at or before it (in-flight packs, above). The in-flight rules measure from it.
- **Settle lag** (a parameter of the read, not the loader). When labels must be complete, `replay.settled_read(now=..., settle_lag_days=7)` ends the window at now minus the lag and sets `as_of` = the window's last `served_at` plus the lag. The replay CLI uses it unless `--as-of` is given. The nightly CLI uses it too (`--settle-lag-days`, default 7, both). The daily tick's `nightly.run_all()` keeps the trailing window as of now. Every run record carries `until`, `as_of` and `settle_lag_days`.

**Loader exclusions** (`LoggedDeck.exclusion`), C7 (iv), in precedence order (a deck takes the first that applies):

| Reason | When | Effect |
|---|---|---|
| `calibration_refresh` | A card's `features_json` (or compact block), or its pack's run metadata, carries `deck_source` `'grading_refresh'` (`data.CALIBRATION_REFRESH_SOURCE`): Calibration's targeted refresh built the deck (ADR-025 S4, `_pregenerate_grading_targets`), and it is never shown in Trades. **Takes precedence over every other reason**, and over `partial_run` in replay and calibration: a refresh deck keeps full rows at build and is never packed, so from `PACK_REQUIRED_SINCE` on it would otherwise read as `in_flight` or `incomplete_deck` (a lost pack). Refresh decks built before #370's relabel carry `'replenish'`, can't be told apart, and stay in | Whole deck out of replay, e(k) and calibration. Not an error |
| `pack_integrity` | The pack fails its checksum, has an unknown version, is undecodable, disagrees with its row's `pack_version` or `card_count`, has malformed `deliveries`, or holds another run's cards | Its cards are not merged |
| `withdrawal_conflict` | The withdrawal disagrees with the evidence. A `served_before = 0` index's card has a non-NULL `delivered_at` or an outcome (the user got the card); or a `served_before = 1` index is past the pack's deliveries as of the read, or, in a paged deck without a pack, its row isn't delivered by then (a legacy deck has no delivery evidence to check). Or a withdrawal's index is outside 0..N−1 (N as for `incomplete_deck`: past the pack's `card_count`, or, without a pack, negative). Both break the writer's contract. A present W0 card without `delivered_at` is expected and removed, not a conflict | Whole deck out |
| `in_flight` | The deck's pack isn't final yet (in-flight packs, above). Or: served at or after `data.PACK_REQUIRED_SINCE`, no pack row yet, and served within `IN_FLIGHT_WINDOW` (25 h: the 24 h cap plus 1 h to write) of `as_of`. **Not an error:** the deck may still be live | Whole deck out, counted apart from integrity |
| `incomplete_deck` | After the merge and the withdrawal removal, the deck's non-ghost card indexes ∪ its W0 indexes aren't exactly 0..N−1 (N is the pack's `card_count`; without a pack, the max over the card indexes and every withdrawal index, either `served_before`, + 1, so a trailing delivered withdrawal with no card is a gap here, not a conflict). Or: a packed deck, or a paged deck with some delivery evidence, has an outcome on a card not delivered as of the read (past the pack's last boundary, or a row with no `delivered_at` by then): under-recorded deliveries. A paged deck with no delivery evidence at all is `no_delivery_evidence` instead. Or: served at or after `PACK_REQUIRED_SINCE` with no pack row and older than the in-flight window, which is a lost pack. Without `as_of` the reader can't call a pack-less deck in flight, so it is counted here | |
| `no_delivery_evidence` | A marked deck (paging, above) without a pack whose live table lacks `delivered_at`, or none of whose non-ghost rows has one: nothing says which cards were delivered, and the legacy rule would count every row as exposed | Whole deck out |

- **`PACK_REQUIRED_SINCE`** (ISO UTC or `None`; **set to `2026-10-27T00:00:00+00:00`**, models-eng 2026-10-26): a **deferred-evidence deck** (a non-ghost row with a non-NULL `evidence_tier`) served at or after it must have a pack row, or it is `in_flight` / `incomplete_deck` (a lost pack). So a 120-card deck whose pack never landed is never read as a complete 30-card deck (#416 QA P2). Decks without tiered rows are never packed and never required to be: flag-off decks, live evidence (the value core, prepared adoption) and Calibration's refresh. Tiered decks exist only once `trade.packed_evidence` and `trade.first_page_store` are on together, so the value is set ahead of the flip and the flip has no eval constant to set. `None` turns the rule off. Both settings are tested, and the value is pinned (`test_the_go_live_constants`).
- **`PAGING_RELEASED_AT`** (ISO UTC or `None`; **stays `None` through the flip**, models-eng 2026-10-26): `None` makes the paging rule marker-only, so a marked deck is never legacy, the strictest setting. Marked decks exist only after `trade.first_page_store` is on, so a release time would only add a way for a mis-dated deck to be read as legacy. If set, a marked deck served before it keeps the legacy rule. An unmarked deck is legacy either way. Both settings are tested, and the value is pinned.
- **Replay** excludes such a deck whole, never sinks it, and counts its cards (`EvalRun.excluded`) and the deck (`EvalRun.calibration_refresh_decks`, `EvalRun.pack_integrity_decks`, `EvalRun.withdrawal_conflict_decks`, `EvalRun.in_flight_decks`, `EvalRun.incomplete_decks`, `EvalRun.no_delivery_evidence_decks`). All appear in the report and the run record, with `withdrawn_removed_cards`, `withdrawn_removed_by_reason` and `upgrade_misses`. Replay's order: `calibration_refresh`, `partial_run`, then the other loader reasons, `missing_scorer_inputs`, `scorer_error`.
- Replay also leaves these decks out of the exposure curve: the cards present in them (the first 30, viewed rows) are a selected subset, so they would bias e(k). A `calibration_refresh` deck's cards were never at a Trades position. `replay._fit_rows` (a trainable scorer's train rows) skips `calibration_refresh` decks too.
- **Calibration** excludes their cards, in the same order: `calibration_refresh`, then a `partial_run` card, then the deck's loader reason.
- Tests (`backend/tests/test_eval_pack_reader.py`): `test_missing_pack_table_means_no_packs`, `test_pack_merges_cards_a_full_row_wins_and_outcomes_join`, `test_project_features_trims_packed_cards_too`, `test_window_and_scope_filters_apply_to_packs`, `test_an_empty_pack_carries_the_card_count`, `test_a_pack_failing_integrity_marks_the_deck[...]`, `test_a_gap_marks_the_deck_incomplete[...]`, `test_replay_excludes_integrity_decks_whole_and_counts_them`, `test_calibration_excludes_integrity_deck_cards`, `test_exclusion_rule_version_is_stamped_and_mixed_versions_are_flagged`, `test_delivered_positions_are_the_served_set`, `test_pack_required_since_flags_in_flight_and_lost_packs[None|set]`, `test_a_viewed_card_replays_the_same_upgraded_or_left_packed` (U2: e(k), the IPS weights and every registered scorer's estimates are identical either way), `test_a_legacy_deck_keeps_its_exposure_and_a_paged_deck_uses_delivered_positions`, `test_outcomes_acted_and_decks_served_after_as_of_are_not_read`, `test_the_settle_lag_picks_as_of`, `test_a_refit_is_the_same_upgraded_or_left_packed` (R5.2 (c)). In `test_eval_nightly_lean.py`: `test_nightly_counts_a_deck_still_in_flight_as_in_flight`, `test_nightly_with_a_settle_lag_grades_settled_decks_as_of_last_served_plus_lag`. In `test_eval_refresh_and_live_columns.py`: `test_a_refresh_deck_is_calibration_refresh[False|True]`, `test_other_deck_sources_are_not_excluded[...]`, `test_refresh_takes_precedence_over_a_gap_and_a_bad_pack[gap|pack_integrity]`, `test_refresh_takes_precedence_over_in_flight_and_a_lost_pack[as_of|None]`, `test_replay_excludes_a_refresh_deck_whole_and_counts_it`, `test_calibration_excludes_refresh_deck_cards`, `test_a_refresh_deck_counts_ahead_of_partial_run`, `test_an_optional_column_the_db_lacks_is_not_selected`, `test_optional_columns_the_metadata_lacks_are_read_from_the_db`. In `test_eval_withdrawals_and_paging.py` (version 5): `test_withdrawn_never_delivered_cards_replay_as_if_never_generated[rows|rows_present|packed|packed_present]` (the equivalence, under `logged`, `production`, `base_score`, `random` and a fitted `value_model`, plus calibration and training rows), `test_removed_cards_are_reported_and_recorded_and_the_version_is_5`, `test_a_packed_card_or_an_undelivered_first30_row_at_a_withdrawn_index_is_removed`, `test_a_delivered_withdrawal_keeps_its_card_position_and_outcomes`, `test_a_delivered_withdrawal_with_no_card_is_an_unexplained_gap[...]`, `test_an_unexplained_gap_is_still_incomplete[...]`, `test_a_withdrawal_outside_the_deck_is_a_conflict[...]`, `test_a_never_delivered_withdrawal_whose_row_was_delivered_is_a_conflict[...]`, `test_replay_and_calibration_exclude_a_conflict_deck_whole_and_count_it`, `test_a_ghost_row_at_a_withdrawn_index_is_ignored[...]`, `test_as_of_reads_only_withdrawals_first_withdrawn_by_then`, `test_withdrawals_are_read_for_every_loaded_deck_past_one_chunk`, `test_without_the_table_or_the_decks_rows_nothing_changes`, `test_a_paged_row_deck_counts_only_rows_with_delivered_at`, `test_a_marker_takes_delivered_from_the_rows[...]`, `test_a_paged_deck_without_delivery_evidence_is_excluded[...]`, `test_paging_released_at_keeps_older_marked_decks_legacy[...]`, `test_a_marked_packed_deck_takes_delivered_from_its_deliveries[...]`, `test_a_pack_is_in_flight_until_final[...]`, `test_deliveries_after_as_of_are_not_read_and_a_re_read_is_stable`, `test_an_outcome_past_the_last_delivery_means_under_recorded_deliveries[...]`, `test_loader_precedence_among_the_new_reasons_and_the_old`, `test_a_conflict_comes_before_a_missing_pack_and_in_flight_before_delivery`, `test_replay_and_calibration_put_refresh_then_partial_run_first`, `test_a_packed_deck_whose_run_metadata_says_grading_refresh_is_calibration_refresh`, `test_fit_rows_skip_only_calibration_refresh_decks`, `test_the_value_model_position_feature_is_the_displayed_position`; and the follow-ups `test_removals_are_counted_by_reason_and_reported_and_recorded`, `test_a_packs_upgrade_misses_are_read_by_cause[...]`, `test_eval_run_sums_upgrade_misses_over_every_loaded_deck_and_flags_other`.

**Exclusion-rule version** (R2.5 (2)), in `backend/eval/replay.py`:
- `EXCLUSION_RULE_VERSION = 5`. It is the eval-rule version; the name is kept so the stamp's field (`exclusion_rule_version`) stays the same in `EvalRun` and run records.
  - **1:** before 2026-10-20. A card without features sank to the bottom of the candidate order (`bad_features`). A persisted record without the field is version 1 (`persistence.record_rule_version`).
  - **2:** whole-deck exclusion, with `missing_scorer_inputs`, `partial_run`, `in_flight`, `pack_integrity` and `incomplete_deck`.
  - **3:** version 2, plus exposure counted at delivered positions only (legacy decks: delivered = served), plus the `as_of` read filter (`acted_at <= as_of`, `served_at <= as_of`). Estimates aren't comparable with version 2.
  - **4:** version 3, plus decks built by Calibration's targeted refresh (`features_json` `deck_source` `'grading_refresh'`, ADR-025 S4) are excluded whole as `calibration_refresh`, from replay, e(k) and calibration. Refresh decks from before the relabel carry `'replenish'` and stay in. Estimates aren't comparable with version 3.
  - **5:** version 4, plus recorded serve-time withdrawals (`deck_card_withdrawals`): a never-delivered withdrawn card is removed (not scored, not exposed, not ranked) and explains its gap; a delivered one keeps its position; positions are displayed positions (dense among kept cards); `withdrawal_conflict`; paged decks (`page_store` marker or `evidence_tier`) take delivered from evidence, never the legacy rule, with `no_delivery_evidence` when they have none; in-flight packs (`retired` false within the window, deliveries read as of `as_of`) are `in_flight`; an outcome beyond the recorded deliveries is `incomplete_deck`. Estimates aren't comparable with version 4.
- It is stamped on every `EvalRun` and in every `persistence.run_record`.
- **The guard:** `verdict()` returns `RULE-MISMATCH` for two runs graded under different versions. `render_report()` prints a `WARNING: exclusion rules differ…` line, or `Exclusion rules: version N.` when they agree. Anything comparing persisted records passes them through `replay.rule_version_note(map(persistence.record_rule_version, records))` and carries its warning.

**The 24 h flip read** (`backend/eval/flip_read.py`; models-lead §Gate-11-03 §3, addenda A3 and B3 (f3)). The model-side read after the one-step flip (`trade.packed_evidence` and `trade.first_page_store` on together). models-eng runs it and posts the output, release-lead collects it, and models-lead rules on it.
- **The command:** `python3 -m backend.eval.flip_read --db URL --since ISO [--until ISO] [--as-of ISO] [--allow-postgres-readonly] [--weekly] [--json] [--i1-mode {0,1,2}]`. The window is decks served in [`since`, `until`) and at or before `as_of` (default now minus `STAMP_SETTLE`), read through `load_decks(as_of=...)` plus a few direct queries. `--json` prints the same as one object; `flip_read()` and `weekly_read()` return it to tests.
- **The settle (#431 QA):** `delivered_at` is stamped off the request thread, so near now an outcome can commit before its card's stamp, and a live deck reads `incomplete_deck` (a transient G2 FAIL). So the CLI's `as_of` is at most the wall clock minus `STAMP_SETTLE` (5 min): that is the default, and a later `--as-of` is clamped to it, with a note on stderr giving both values. `flip_read()` takes `as_of` as given; only the CLI reads the clock.
- **Exit status:** 0 = PASS; 1 = FAIL, or a weekly ceiling OVER (either wins over INSUFFICIENT); 2 = a refused database or a `ReadOnlyViolation` mid-read (nothing on stdout), or a usage error, a malformed ISO 8601 `--since`, `--until` or `--as-of` included; 3 = INSUFFICIENT (fewer than 10 final packed decks, nothing failed: not a pass); 4 = an unexpected error (a crash, not a verdict), its traceback on stderr. Exit 1 is only ever a verdict.
- **Read-only, enforced:** a SQLite path opens `mode=ro`; any other URL is refused unless `--allow-postgres-readonly`, and then only Postgres, where every new connection opens with `default_transaction_read_only=on` and a 120 s `statement_timeout`, runs `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`, and must answer `SHOW transaction_read_only` = `on` before anything reads. On both, a statement that isn't a read raises `ReadOnlyViolation`. It never imports `backend.server`.
- **The G-table** (a barred G prints PASS or FAIL):
  - **G1, pack integrity:** `pack_integrity` decks among the decks with a pack row, retired or not. Bar 0.
  - **G2, no unexplained gaps:** `incomplete_deck` decks among the **final packed** decks and **every pack-less** deck (A3; #425 QA). A packed deck is final when its pack retired by `as_of` or was served more than 25 h before it (the loader's own rule). A pack-less deck (live evidence: the value core, prepared adoption; rows at build, `delivered_at` stamps) has no in-flight state, so its `incomplete_deck` (a gap, or an outcome on a row never stamped delivered) is final at once; in a 24 h read every such deck is under 25 h, so a final-only bar never saw one. A tiered deck with no pack yet is the loader's `in_flight` inside 25 h, not `incomplete_deck`. `calibration_refresh` decks aren't Trades decks and aren't counted. Bar 0; each incomplete deck must coincide with a restart or the kill (A3, B3), so their ids (at most 20) are listed with `served_at` for that cross-check. The row prints both populations (`n / read (final packed + pack-less)`). The 10-deck minimum counts **final packed decks only**: fewer prints `INSUFFICIENT (<10 final packed decks): extend to 48 h`.
  - **G3, outcomes join (U2):** outcomes acted in the window (and by `as_of`) whose `impression_id` joins no loaded card, row or packed. An outcome whose deck was served before the window is checked against the evidence directly (a non-ghost `deck_impressions` row with that id, or a pack row of its run whose `card_count` covers its index) and counted apart, so the window's start doesn't read as a failure. An outcome joining a **ghost row** is counted apart as `on_ghost`, with its ids: a loaded one (`LoggedCard.is_ghost`), or, for a deck served before the window, a `deck_impressions` row with `is_ghost = 1` found by id (ghosts keep uuid4 ids, so the id itself says nothing and names no run). Ghosts are never shown, so it means a ghost reached a client. Bar 0 on each, orphans and `on_ghost`; either fails G3. Only orphans are lost data: B3 (f4)'s kill recommendation prints when G1 fails or G3 has orphans. An outcome on a ghost row is a serve bug and goes back to models-lead.
  - **G7, upgrade misses (U4-R2):** every cause summed over the loaded packs. Bar: `other` = 0.
    - Also reported, never barred (U4 option A's guard; addendum C4 (d1)): `row_gone`, the entries of run `upgrade_miss_row_gone`; `row_gone_named`, those whose `upgrade_miss_cards` cause is named; and `row_gone_split`, by run `upgrade_miss_row_gone_why` (`replaced` / `no_row`, else `unsplit`; the split needs #454's writer, and before it every entry reads unsplit). (d1)'s sub-count is `row_gone_named`; a pack failing integrity is not read. Also `indicative`, the U4-R4 sum (`restart_split + evicted_split`, by name) over the read window, which is indicative only: the 7-day ceiling is read weekly, and the weekly line carries the row-gone counts too. Absent keys count 0.
  - **G8:** `withdrawal_conflict` decks. Bar 0.
  - **G9:** `no_delivery_evidence` decks with any outcome (a missed `delivered_at` stamp, B3). Bar 0. The `no_delivery_evidence` total is reported too.
  - **G10:** withdrawals first withdrawn in the window, by `reason`, straight from `deck_card_withdrawals`. `disposition_cut` > 0 is expected and only reported. `i1_dropped` is barred at 0 unless `--i1-mode` (`flip_read(i1_mode=...)`, default 1, the launch `trade_i1_mode`) is 2: modes 1 and 0 never withdraw for I-1 (B3), so any `i1_dropped` there fails G10; at mode 2 G10 is `REPORT`.
  - Then the v5 exclusion counts over every loaded deck (each `LoggedDeck.exclusion` value, the deck count, the `partial_run` decks replay leaves out), `withdrawn_removed_by_reason` over every loaded deck, and `OVERALL`: FAIL if a barred G fails, else INSUFFICIENT if G2 has fewer than 10 final packed decks, else PASS. B3 (f4)'s kill recommendation prints only when G1 fails or G3 has orphans (lost data); any other FAIL, an outcome on a ghost row included, goes back to models-lead.
- **`--weekly`** adds the two rolling 7-day ceilings over [`as_of` − 7 d, `as_of`], for the weekly BL-001 monitor through head-bizops. Each prints its ratio, numerator, denominator, and OK or OVER:
  - **U4-R4:** `restart_split + evicted_split` (`U4_R4_CAUSES`, by name, addendum C2: `other` and any cause added later stay out; each shown) over viewed cards, at most `U4_R4_CEILING` (1%). Viewed cards are the distinct loaded non-ghost cards with a `viewed` outcome.
  - **B4:** `disposition_cut` removals over delivered-range positions, at most `B4_CEILING` (5%). Delivered-range positions are the delivered non-ghost cards plus the `disposition_cut` W0 removals, over the decks the loader includes (an excluded deck's deliveries aren't read) that have delivery evidence: a pack, or a row with `delivered_at` by `as_of`.
- Tests: `backend/tests/test_eval_flip_read.py` (each barred G passing and failing, and failing the read; G2 on pack-less decks inside 25 h, release-lead's #425 QA probe; G3's ghost-row bucket, a loaded ghost row and one of a deck served before the window; G10 at modes 0, 1 and 2; the exclusion counts; both ceilings at, under and over; the CLI's `as_of` settle on a pinned clock; each exit status, a crash exiting 4 and a malformed time exiting 2; the CLI on a read-only SQLite file; the Postgres refusal, startup options (`statement_timeout`, read-only default) and session check; the statement guard; and the import check).

**The B-DK-4..7 production audit** (`backend/eval/bdk_audit.py`; models-lead addendum C §C5, U4-R3) counts served violations of `deck.quality_filters`' rules against a bar of 0. It imports `deck_quality`'s rule functions and thresholds and restates none (a source test pins it), and reads through `load_decks(as_of=...)` with flip_read's read-only engine, redaction, settle clamp and exit scheme (plus 3 = INCOMPLETE). The audit set is U6's: per Trades deck, the first `REPEAT_WINDOW` cards by `LoggedCard.position` plus every card with a `viewed` outcome, never inferred from a row. One read goes past it: for a B-DK-7 breach, the short-deck check (#469) reads every displayed card's full row, to re-run `deck_quality._repeat_cap` on the deck's whole displayed order. It never applies where the loaded cards may be only a prefix of the deck: a loader exclusion (except a packed deck's `in_flight`), a `partial_run` deck, or a pack-less deck of `REPEAT_WINDOW` cards or more. `pack_integrity` and `withdrawal_conflict` decks are skipped and counted. A viewed card with no full row is reported by its pack's `upgrade_miss_cards` cause (no entry: `other`). What the evidence records at serve time:
- `assets_json`, the protection flags (`features_json`: `likes_you`, `standing_offer`, `wildcard`; the `source_like_impression_id` column) and positions are served-time. `fatigue_retest` isn't recorded, and the other protections are never set at filter time.
- Per-asset markets are only in `valuation_json` (the personal-market snapshot's `market_value`, or the value core's `market`). They're served-time but age-adjusted, so not the filter's exact input, and NULL while `trade.valuation_telemetry` is off.
- Rosters and lineup slots aren't recorded at all, so B-DK-6 is `NOT_AUDITABLE`.
- Whether the flag was on isn't recorded per deck: the window is read whole, assuming on since 2026-10-15 01:18 UTC.

A rule that can't check every card reads `INCOMPLETE` or `NOT_AUDITABLE` (violations `None`), never 0. Tests: `backend/tests/test_eval_bdk_audit.py`.

**The golden, C7 (ii)** (`backend/tests/test_evidence_pack.py`):
- `test_db_golden_full_rows_vs_packed[30-False]` and `[0-True]`. Real decks (three harness trade jobs, the 1,200-card writer deck with R4.1 taste matches on every card, 40 synthetic decks with outcomes) are written two ways into a test database. Both forms are retired decks: deterministic ids, a pack row with deliveries in pages of 25 through card 99, outcomes only on delivered cards, and two ghost rows per deck.
  - **(A)** the C8 archive form: every card a full row, plus the pack (every row wins);
  - **(B)** the first 30, the ghosts, and the cards with an outcome at an even index (upgraded) as rows. Every card from 30 on is in the pack, so an odd-index viewed card stays packed and its outcomes join by id.
  - `[0-True]` packs every non-ghost card and loads with the nightly's projection.
- `load_decks` on (A) and (B) gives identical decks, identical card dicts on every contract key (ids included), identical delivery flags and outcomes, **bit-identical scores for every registered scorer** (value_model fitted in-test, `as_of` pinned), repr-identical replay estimates, and an identical value-model refit.
- `test_db_golden_detects_a_one_ulp_change`: one packed `base_score` moved by 1 ulp changes exactly one score and fails the golden.

## 9. Candidate-set packing

head-eng ruling 25, under the same gate as the deck pack. **This is separate from the deck pack:** `deck_evidence_packs` and `PACK_VERSION` 1 are frozen and unchanged.

**The codec** (`backend/eval/evidence_pack.py`, pure, no I/O):
- `pack_candidates(run, members) -> PackedCandidates(cand_pack_version, candidates_packed)` and `unpack_candidates(packed) -> (run, members)`. `CAND_PACK_VERSION = 1` has its own decoder registry, `CAND_DECODERS`, under the version discipline of §7.
- Members are exactly what the writer builds today (`server._log_deck_signal_impressions`): `{trade_hash, partner, give, receive, base_score, in_deck}` in that key order.
- Encoding:
  - `trade_hash` as 8 raw bytes;
  - `partner` as a code into a per-run dictionary;
  - `give` and `receive` as a length plus codes into one per-run asset-id dictionary, with exact order and duplicates kept;
  - `base_score` as float8 (an int stays an int64);
  - `in_deck` as one bit;
  - a 2-bit absent / null / value state per field, written only when it varies.
- The packed value is one bytes object: `zlib(uvarint(len(header)) + header + raw)`. The header holds the version, `run`, `n`, `set_hash`, the dictionaries and a `checksum`: SHA-256 of the canonical `{header, members}`. So the run, the dictionaries, `set_hash` and every member are covered.
- **`set_hash` is computed exactly as today** (`evidence_pack.candidate_set_hash`: SHA-256 of the sorted member `trade_hash`es joined by `|`, first 16 hex characters). It is verified on unpack.
- `pack_candidates` refuses, with `ValueError`, anything whose unpacked `json.dumps` differs from the input's by a single byte: key order, types or values.

**The storage contract** (spec for trades-eng, who owns the schema under head-eng's grant):

| Column on `deck_candidate_sets` | Type | Meaning |
|---|---|---|
| `candidates_packed` | LargeBinary (BLOB on SQLite, BYTEA on Postgres), **nullable** | `PackedCandidates.candidates_packed`, stored verbatim |
| `cand_pack_version` | Integer, **nullable** | `PackedCandidates.cand_pack_version`, stored verbatim |
| `candidates_json` | Text, **stays NOT NULL** (head-eng's schema ruling) | Legacy rows keep their JSON. **Packed rows store `''`** |

**`candidates_packed IS NOT NULL` is authoritative.** Readers key on it first. They use `candidates_json` only when `candidates_packed` is NULL (legacy rows), and never parse a packed row's `''`.

- **Writer:**
  - `packed = evidence_pack.pack_candidates({"candidate_set_id": ..., "deck_job_id": ...}, members)`; store both fields, and `candidates_json = ''` for new rows.
  - `set_hash` and `size` are still computed and stored as today. Import `candidate_set_hash` rather than restating it.
  - If `pack_candidates` raises `ValueError`, store the JSON in `candidates_json` and leave `candidates_packed` NULL for that row (nothing is lost).
  - Every new row is packed, even a tiny set: a 1-member set packs to 270 B against 142 B of JSON, and the absolute cost is negligible.
- **Readers** key on `candidates_packed IS NOT NULL` first (authoritative), and use `candidates_json` only when `candidates_packed` is NULL (legacy rows): `members = unpack_candidates(PackedCandidates(row.cand_pack_version, row.candidates_packed))[1] if row.candidates_packed is not None else json.loads(row.candidates_json)`. A packed row's `''` is never parsed. A `PackIntegrityError` is a corrupt row: refuse it like a malformed JSON row, and never fall back to the `''`.
  - **`backend/eval/scorecard_evidence.py` (built):** see `docs/model-evaluation/evidence-contract.md` §"Implemented adapter".
  - **`prepared_trade_payload._candidate` and `prepared_trade_payload_v2` (trades-eng; spec only):** key on `candidates_packed IS NOT NULL` first, which is authoritative. When it is set, get `members` from the pack and don't read `candidates_json` (it is `''`). Read `candidates_json` only when `candidates_packed` is NULL, for legacy rows. Keep every existing check on the members (exact keys, ids, `partner` text, `base_score` number, `in_deck` bool, the `trade_hash` terms, and the row's `set_hash`). Extend the key allowlist to the two new columns, and apply `MAX_CANDIDATE_BYTES` to the packed bytes and to the unpacked JSON.
- **Deletion and export:** unchanged. It is the same row; an export carries the packed bytes, or the reader's unpacked JSON.

**Tests** (`backend/tests/test_candidate_pack.py`):
- the golden on real candidate sets: two harness trade jobs with `suggestion.telemetry` on, and the real writer's set for a 1,200-card deck with 300 over-generated members. Unpacked members equal the stored JSON byte for byte, in order, and `set_hash` is identical;
- a 5,000-member synthetic set with duplicate and unsorted asset ids, int ids, null partners and int scores;
- absent and null fields;
- refusals;
- tampering: run, either dictionary, `set_hash`, checksum, a member byte, and a forged `set_hash` with a consistent checksum;
- unknown, mismatched and unreadable versions;
- scorecard_evidence's full output, private records included, is identical from JSON, packed and pre-column (legacy) snapshots, and an unreadable pack is flagged.

**Measured** (JSON vs packed, run metadata included):

| Set | Members | JSON | Packed | Per member |
|---|---|---|---|---|
| Writer, 250 dealt + 50 over-generated | 300 | 47.6 KiB | **7.7 KiB (−84%)** | 162 → 26.2 B |
| Writer, 1,200 + 300 | 1,500 | 237 KiB | 33.6 KiB (−86%) | 162 → 22.9 B |
| Synthetic | 5,000 | 731 KiB | 92.4 KiB (−87%) | 150 → 18.9 B |
| Harness job | 4 | 566 B | 367 B | |

The ~43 KiB per pair today packs to about 7 KiB.

## Decisions needed

1. **The `evidence_tier` schema** (trades-eng, under head-eng's grant). This covers:
   - column name, type and allowed values;
   - the value for existing rows;
   - an index for the daily prune;
   - precedence when a row qualifies for more than one of `delivered`, `first30` and `ghost`. `archive` is disjoint by construction.
2. ~~**`docs/runbook.md:1022` still lists `bad_features`** among replay's exclusions.~~ **Done** (2026-10-22, commit f9d4f611): the line now lists `partial_run` and `missing_scorer_inputs`, both whole-deck reasons.
3. ~~**A missing pack isn't always detectable.**~~ **Built** (2026-10-24): `data.PACK_REQUIRED_SINCE` (§8). **Set it when trades-eng's packed writer ships**; until then a missing pack is undetectable, by design.
4. ~~**R4.2 and R4.1 aren't in this pack format.**~~ **Built** (2026-10-24), before the format froze, as `PACK_VERSION = 1`: the two taste matches (§6, §7), `deliveries` (U1), and the deterministic `run_id:card_index` id with the outcome join (U2).
5. ~~**`docs/runbook.md:1022`** lacks the new exclusion reasons.~~ **Done** (2026-10-24): the runbook's "Grade candidates" line lists every current reason.
6. ~~**`nightly.run_all` doesn't pass `as_of` yet.**~~ **Done** (f90f3c30): the nightly passes its clock, so a live deck reads `in_flight`.
7. **Training on frozen blocks.** `value_model.build_training_rows` now falls back to the compact or packed block when a viewed card has no `features_json`. This changes nothing on existing data, which has no compact rows. The R2.7 train/score skew (scoring merges the logged `archetype` / `shape_bucket`, training doesn't) is unchanged and still needs its own change before a D-016 read.
8. ~~**Late outcomes and `as_of`.**~~ **Ruled and built** (R5.2 (b), 2026-10-24): the loader filters `acted_at <= as_of` and `served_at <= as_of`, and the settle lag is a read parameter (§8). R5.2 also accepted the live-config exceptions under pin-and-record (a), training from packed or compact blocks (c, item 7), and delivered-position exposure as a B3 eval change (d).
9. **Serving's taste read is now per deck, and serving can still skew from training.** `serving_scores` reads taste fresh for each deck; it used to cache it on the long-lived model object. It still reads live taste even when `deck.taste_vectors` is off, while training sees the frozen pair absent (0.0) in that case. `deck.taste_vectors` is on in `config/features.json`, so this only matters if the flag is turned off.

## Handoffs

- **trades-eng:**
  - the evidence writer: the pack for every served deck, written at first delivery and rewritten with its deliveries and `retired` / `retired_at` (§6), C8 full rows from the build-time snapshot, `evidence_tier` and `delivered_at`, the bounded prune, and the safety-ceiling refusal;
  - the `deck_card_withdrawals` table and its writer, in the shape in §8 (one row per I-1 withdrawal on the page-store path; a never-delivered card's row never gets a `delivered_at`);
  - deterministic ids (`card_impression_id`) on every non-ghost row and in the page payload, so the client posts outcomes with them (U2); upgrade on the first outcome;
  - the frozen taste matches on every card when the taste layer ran, with a writer test that calls `backend/tests/support/taste_parity.assert_frozen_prefs_match_multipliers` (R4.1 (iii));
  - the `deck_evidence_packs` table exactly as §6, and `delete_user_data` and account export over it (C7 (v));
  - page-store tests that call `assert_page_is_top_n` and `assert_prefix_stable`;
  - import `is_archive_deck`, `card_impression_id` and `FROZEN_INPUT_KEYS` from `backend/eval/contract.py`. Don't restate them;
  - at go-live, a PR that sets `backend/eval/data.PACK_REQUIRED_SINCE`; at the `trade.first_page_store` go-live, one that sets `backend/eval/data.PAGING_RELEASED_AT`.
- **trades-eng, candidate sets (§9):** the two new `deck_candidate_sets` columns, with `candidates_json` staying NOT NULL (packed rows store `''`). Also the writer switch with its JSON fallback, and the `prepared_trade_payload(_v2)` readers, which key on `candidates_packed IS NOT NULL` first and use `candidates_json` only when it is NULL (legacy rows).
- **head-eng:** the schema grant for `evidence_tier`, `deck_evidence_packs`, the `deck_candidate_sets` packed columns and the new evidence columns. The C9 ADR should cite this spec.
- **release-lead's scribe, at merge:** the living-memory write-back (CHANGELOG and TEST_LEDGER).

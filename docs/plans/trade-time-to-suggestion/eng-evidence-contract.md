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
- `LoggedCard.features_compact` and `LoggedCard.evidence_tier` are filled from columns of the same names, but only if the table has them. Neither column exists yet. **The optional columns are read from the live table:** `load_decks` inspects the DB's own columns on every read, never the code's table metadata, so an unmigrated DB (an old SQLite snapshot) still loads once the metadata gains a column, and a DB column the metadata lacks is still read.
- `card_dict` uses `features_json` when it is present, else the compact block. Logged columns win key collisions.
- Packed cards are merged in from `deck_evidence_packs` when that table exists (§8).

**Exclusion rules:**
- **Replay** (`backend/eval/replay.py`):
  - A deck in which **any** card has `evidence_tier == 'partial_run'` is excluded whole, under `partial_run`. This check runs before `missing_scorer_inputs`, so such a deck is never counted twice. Cards are counted in `EvalRun.excluded` and decks in `EvalRun.partial_run_decks`; both appear in the report and the run record.
  - A deck in which **any** card has neither `features_json` nor a compact block is excluded whole, under `missing_scorer_inputs`. It is never sunk.
  - The excluded cards are counted in `EvalRun.excluded`, and the decks in `EvalRun.missing_inputs_decks`. Both appear in the rendered report and the persisted run record (`backend/eval/persistence.py`).
  - Replay no longer has the per-card `bad_features` reason.
  - Three more whole-deck reasons, `in_flight`, `pack_integrity` and `incomplete_deck`, come from the pack reader, and `calibration_refresh` from the loader (§8). The order is `calibration_refresh`, `partial_run`, `in_flight`, `pack_integrity`, `incomplete_deck`, `missing_scorer_inputs`, then `scorer_error`, so no deck is counted twice.
- **Calibration** (`backend/eval/calibration.py`):
  - Exclusion is per card, since there are no ranks here.
  - A card with neither input is excluded alone, as `bad_features`.
  - A card with only a compact block is scored.
  - Every card of a `calibration_refresh` deck (§8) is excluded under that reason, first.
  - A card with `evidence_tier == 'partial_run'` is excluded alone, as `partial_run`, next, before the other per-card checks.
  - Every card of an `in_flight`, `pack_integrity` or `incomplete_deck` deck is excluded under that reason, next.
- **Who writes `partial_run`:** trades-eng, on the delivered rows of a partial run (head-eng ruling 21). Calibration's `select_current_cards` must also skip such jobs; that file belongs to trades-eng.

**Lean nightly** (`backend/eval/nightly.py`; the eval pass runs last in the daily tick):
- `run_all` decides which scorers are due **before** loading anything. With nothing due, it returns without calling `load_decks`, and no baseline is evaluated or recorded.
- `load_decks` selects only `EVAL_COLUMNS`, never `select(imp)`. Those columns are `impression_id`, `user_id`, `league_id`, `deck_job_id`, `card_index`, `trade_hash`, `features_json`, `propensity`, `base_score`, `final_score`, `archetype`, `shape_bucket`, `served_at` and `is_ghost`. It adds `features_compact` and `evidence_tier` only when the live table has them.
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

- **When:** the pack is written **when the deck retires**: superseded by a newer deck, or at the 24 h display cap (PRD #339 §5.1). By then every delivery is known. Until it retires, the deck is **in flight**: it has rows but no pack, and replay skips it as `in_flight` (§8), which is not an error. Every packed field is still the build-time value (C1, E1); only the deliveries are filled in at retirement.
- `run` is the caller's per-run metadata. It comes back verbatim from `unpack_run` and is under the checksum. At least the values snapshot id (`vsn1`), `built_at` (R2.6), the config reference and **`deliveries`** (R4.2 U1, required).
- **`deliveries`** = the delivered page boundaries, `[[last_card_index, delivered_at], …]`, one entry per page sent to a client, `last_card_index` strictly increasing within `[0, card_count)`, `delivered_at` ISO UTC. Pages are delivered from card 0, so the delivered cards are 0..the last boundary. `pack_run` refuses a missing or malformed list (`evidence_pack.check_deliveries`). A device-held page counts when it is first sent.
- **Impression ids (R4.2 U2):** every non-ghost card of a served deck, whether its row is full or it is packed, has `impression_id = contract.card_impression_id(run_id, card_index)` = `f"{run_id}:{card_index}"`. The writer gives full rows that id, the page payload carries it, and **the client posts outcomes with it**. Import the function; don't restate the format. A ghost row keeps a different id (a uuid4): its would-have-been rank can equal a served card's index.
- **Upgrade on view (R4.2):** a card's first outcome of any kind upgrades it to a full row with the same id. It stays in the pack too, and the row wins. If the upgrade never happens, the outcome still joins the packed card by id.
- **Frozen taste matches (R4.1):** when the F5 taste layer ran for the deck, each card's features carry `taste_pref_long` and `taste_pref_short`: the two `_pref_match` values `taste_service.taste_multipliers` built that card's multiplier from, as float8. When the layer didn't run (flag off, no signal, bake-off fixed order), both keys are absent. The writer's test must pass `backend/tests/support/taste_parity.assert_frozen_prefs_match_multipliers` on a served deck.
- `cards` are card dicts as `backend.eval.data.card_dict` builds them, plus the `deck_impressions` attribution columns: `policy_version`, `candidate_set_id`, `candidate_set_size`, `model_arm`, `arm_rank`, `group_key`, `group_rank`, `lane_slot`, `fairness_threshold`, `centerpiece_id`. Every key outside `evidence_pack.CONTRACT_KEYS` is dropped. Every packed field is frozen at build time and never recomputed (C1, E1).
- The per-run fields (`user_id`, `league_id`, `deck_job_id`, `served_at`, `candidate_set_id`, `candidate_set_size`, `ranked_player_count`, `user_value_basis`, `last_board_update_at`) must be constant across the run. `served_at` on the cards is the first-delivery time too.
- `card_count` = N, the number of non-ghost cards in the served deck. The deck's full rows and its packed cards together must hold `card_index` 0..N−1. `pack_run` refuses a packed index outside that range.
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
- **Delivery (R4.2 U1):** in a deck with a pack, `LoggedCard.delivered` is true for a non-ghost card with `card_index` at or below the last delivery boundary. Ghost rows are never delivered. **The legacy rule (R5.2 (d)):** a deck without a pack, from before paging, delivered every served card, so delivered = served at every position (ghost rows included, as e(k) always counted them). Its e(k) is unchanged. **The exposure model's served set is the delivered positions:** e(k) counts only delivered cards. Undelivered cards stay in the counterfactual re-rank, since a candidate could have ranked them first. models-lead signed this off as a B3 eval behavior change: undelivered tails no longer pull e(k) down, so e(k) estimates rise, and the eval-rule version (below) records it.
- `value_model.build_training_rows` trains on a viewed card's frozen block in whichever form it arrived: `features_json`, else the compact or packed block. A viewed card fits the same whether or not it was upgraded.
- Every `evidence_tier` other than `partial_run` (`ghost`, `first30`, `delivered`, `archive`, `full_interim`) is a usable row.
- A pack whose run has no row in the window still makes a deck. With its rows missing, that deck is `incomplete_deck`.
- `load_decks(as_of=...)` is the read's explicit clock. The loader reads no wall clock. It reads only decks served at or before `as_of` and outcomes acted at or before it (`deck_outcomes.acted_at`, R5.2 (b)), and the in-flight rule measures from it.
- **Settle lag** (a parameter of the read, not the loader). When labels must be complete, `replay.settled_read(now=..., settle_lag_days=7)` ends the window at now minus the lag and sets `as_of` = the window's last `served_at` plus the lag. The replay CLI uses it unless `--as-of` is given. The nightly CLI uses it too (`--settle-lag-days`, default 7, both). The daily tick's `nightly.run_all()` keeps the trailing window as of now. Every run record carries `until`, `as_of` and `settle_lag_days`.

**Loader exclusions** (`LoggedDeck.exclusion`), C7 (iv):

| Reason | When | Effect |
|---|---|---|
| `calibration_refresh` | A card's `features_json` (or compact block) carries `deck_source` `'grading_refresh'` (`data.CALIBRATION_REFRESH_SOURCE`): Calibration's targeted refresh built the deck (ADR-025 S4, `_pregenerate_grading_targets`), and it is never shown in Trades. **Takes precedence over every other reason**, and over `partial_run` in replay and calibration: a refresh deck keeps full rows at build and is never packed, so from `PACK_REQUIRED_SINCE` on it would otherwise read as `in_flight` or `incomplete_deck` (a lost pack). Refresh decks built before #370's relabel carry `'replenish'`, can't be told apart, and stay in | Whole deck out of replay, e(k) and calibration. Not an error |
| `in_flight` | Served at or after `data.PACK_REQUIRED_SINCE`, no pack row yet, and served within `IN_FLIGHT_WINDOW` (25 h: the 24 h cap plus 1 h to write) of `as_of`. **Not an error:** the deck may still be live | Whole deck out, counted apart from integrity |
| `pack_integrity` | The pack fails its checksum, has an unknown version, is undecodable, disagrees with its row's `pack_version` or `card_count`, has malformed `deliveries`, or holds another run's cards | Its cards are not merged |
| `incomplete_deck` | After the merge, the deck's non-ghost card indexes aren't exactly 0..N−1 (N is the pack's `card_count`, or max+1 when there's no pack). Or: served at or after `PACK_REQUIRED_SINCE` with no pack row and older than the in-flight window, which is a lost pack. Without `as_of` the reader can't call a deck in flight, so it is counted here | |

- **`PACK_REQUIRED_SINCE`** (ISO UTC or `None`, default `None`): when `None`, no deck is required to have a pack, the legacy rule. Set it to the writer's go-live time when trades-eng's packed writer ships. Both settings are tested.
- **Replay** excludes such a deck whole, never sinks it, and counts its cards (`EvalRun.excluded`) and the deck (`EvalRun.calibration_refresh_decks`, `EvalRun.in_flight_decks`, `EvalRun.pack_integrity_decks`, `EvalRun.incomplete_decks`). All appear in the report and the run record.
- Replay also leaves these decks out of the exposure curve: the cards present in them (the first 30, viewed rows) are a selected subset, so they would bias e(k). A `calibration_refresh` deck's cards were never at a Trades position.
- **Calibration** excludes their cards.
- Tests (`backend/tests/test_eval_pack_reader.py`): `test_missing_pack_table_means_no_packs`, `test_pack_merges_cards_a_full_row_wins_and_outcomes_join`, `test_project_features_trims_packed_cards_too`, `test_window_and_scope_filters_apply_to_packs`, `test_an_empty_pack_carries_the_card_count`, `test_a_pack_failing_integrity_marks_the_deck[...]`, `test_a_gap_marks_the_deck_incomplete[...]`, `test_replay_excludes_integrity_decks_whole_and_counts_them`, `test_calibration_excludes_integrity_deck_cards`, `test_exclusion_rule_version_is_stamped_and_mixed_versions_are_flagged`, `test_delivered_positions_are_the_served_set`, `test_pack_required_since_flags_in_flight_and_lost_packs[None|set]`, `test_a_viewed_card_replays_the_same_upgraded_or_left_packed` (U2: e(k), the IPS weights and every registered scorer's estimates are identical either way), `test_a_legacy_deck_keeps_its_exposure_and_a_paged_deck_uses_delivered_positions`, `test_outcomes_acted_and_decks_served_after_as_of_are_not_read`, `test_the_settle_lag_picks_as_of`, `test_a_refit_is_the_same_upgraded_or_left_packed` (R5.2 (c)). In `test_eval_nightly_lean.py`: `test_nightly_counts_a_deck_still_in_flight_as_in_flight`, `test_nightly_with_a_settle_lag_grades_settled_decks_as_of_last_served_plus_lag`. In `test_eval_refresh_and_live_columns.py`: `test_a_refresh_deck_is_calibration_refresh[False|True]`, `test_other_deck_sources_are_not_excluded[...]`, `test_refresh_takes_precedence_over_a_gap_and_a_bad_pack[gap|pack_integrity]`, `test_refresh_takes_precedence_over_in_flight_and_a_lost_pack[as_of|None]`, `test_replay_excludes_a_refresh_deck_whole_and_counts_it`, `test_calibration_excludes_refresh_deck_cards`, `test_a_refresh_deck_counts_ahead_of_partial_run`, `test_an_optional_column_the_db_lacks_is_not_selected`, `test_optional_columns_the_metadata_lacks_are_read_from_the_db`.

**Exclusion-rule version** (R2.5 (2)), in `backend/eval/replay.py`:
- `EXCLUSION_RULE_VERSION = 4`. It is the eval-rule version; the name is kept so the stamp's field (`exclusion_rule_version`) stays the same in `EvalRun` and run records.
  - **1:** before 2026-10-20. A card without features sank to the bottom of the candidate order (`bad_features`). A persisted record without the field is version 1 (`persistence.record_rule_version`).
  - **2:** whole-deck exclusion, with `missing_scorer_inputs`, `partial_run`, `in_flight`, `pack_integrity` and `incomplete_deck`.
  - **3:** version 2, plus exposure counted at delivered positions only (legacy decks: delivered = served), plus the `as_of` read filter (`acted_at <= as_of`, `served_at <= as_of`). Estimates aren't comparable with version 2.
  - **4:** version 3, plus decks built by Calibration's targeted refresh (`features_json` `deck_source` `'grading_refresh'`, ADR-025 S4) are excluded whole as `calibration_refresh`, from replay, e(k) and calibration. Refresh decks from before the relabel carry `'replenish'` and stay in. Estimates aren't comparable with version 3.
- It is stamped on every `EvalRun` and in every `persistence.run_record`.
- **The guard:** `verdict()` returns `RULE-MISMATCH` for two runs graded under different versions. `render_report()` prints a `WARNING: exclusion rules differ…` line, or `Exclusion rules: version N.` when they agree. Anything comparing persisted records passes them through `replay.rule_version_note(map(persistence.record_rule_version, records))` and carries its warning.

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
  - the evidence writer: the pack for every served deck, written at retirement with its deliveries (§6), C8 full rows from the build-time snapshot, `evidence_tier`, the bounded prune, and the safety-ceiling refusal;
  - deterministic ids (`card_impression_id`) on every non-ghost row and in the page payload, so the client posts outcomes with them (U2); upgrade on the first outcome;
  - the frozen taste matches on every card when the taste layer ran, with a writer test that calls `backend/tests/support/taste_parity.assert_frozen_prefs_match_multipliers` (R4.1 (iii));
  - the `deck_evidence_packs` table exactly as §6, and `delete_user_data` and account export over it (C7 (v));
  - page-store tests that call `assert_page_is_top_n` and `assert_prefix_stable`;
  - import `is_archive_deck`, `card_impression_id` and `FROZEN_INPUT_KEYS` from `backend/eval/contract.py`. Don't restate them;
  - at go-live, a PR that sets `backend/eval/data.PACK_REQUIRED_SINCE`.
- **trades-eng, candidate sets (§9):** the two new `deck_candidate_sets` columns, with `candidates_json` staying NOT NULL (packed rows store `''`). Also the writer switch with its JSON fallback, and the `prepared_trade_payload(_v2)` readers, which key on `candidates_packed IS NOT NULL` first and use `candidates_json` only when it is NULL (legacy rows).
- **head-eng:** the schema grant for `evidence_tier`, `deck_evidence_packs`, the `deck_candidate_sets` packed columns and the new evidence columns. The C9 ADR should cite this spec.
- **release-lead's scribe, at merge:** the living-memory write-back (CHANGELOG and TEST_LEDGER).

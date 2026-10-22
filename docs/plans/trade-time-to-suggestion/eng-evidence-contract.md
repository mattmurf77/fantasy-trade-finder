# Evidence contract: scorer inputs, page contracts, and the C8 archive

> **Purpose.** This is the spec trades-eng's evidence writer and page store implement against. It covers four things: the scorer inputs a narrow or packed card must keep (C7), what a paged deck must preserve (AC-9 and P2), how the whole-deck archive is chosen and stored (C8), and which decks are never stored at all. Source: `docs/plans/org-bringup/leads/models-lead-launch.md` §DEC-2, conditions C1–C9. Built and tested on branch `eng/eval-scorer-contract` (2026-10-20). If this file and the code disagree, the code and its tests win, and this file gets fixed.

## Contents

- [1. The C7 contract as built](#1-the-c7-contract-as-built)
- [2. AC-9 and P2 page contracts](#2-ac-9-and-p2-page-contracts)
- [3. C8 archive spec](#3-c8-archive-spec)
- [4. The safety-ceiling rule](#4-the-safety-ceiling-rule)
- [5. Field-set note](#5-field-set-note)
- [Decisions needed](#decisions-needed)
- [Handoffs](#handoffs)

## 1. The C7 contract as built

**Where:** `backend/eval/contract.py`. These are the exact sets.

| Set | Keys | Meaning |
|---|---|---|
| `COMPACT_KEYS` | `give_value`, `receive_value`, `surplus_margin`, `fairness_score`, `ranked_player_count`, `shape`, `lane`, `basis`, `give_positions`, `receive_positions`, `involves_pick`, `likes_you`, `relaxed`, `user_value_basis` | Exactly the card keys `value_model.extract_features` reads |
| `INJECTED_COMPUTED_KEYS` | `_pref_long`, `_pref_short`, `_partner_rate`, `_position` | Computed at eval time by `ValueModel._inject` from other tables. **Never stored** |
| `INJECTED_CARD_INPUTS` | `partner_user_id`, `taste_attrs` | Read from the card by `_inject` to compute the keys above. **Must be frozen** |
| `INJECTED_KEYS` | `INJECTED_COMPUTED_KEYS` ∪ `INJECTED_CARD_INPUTS` | |
| `FROZEN_INPUT_KEYS` | `COMPACT_KEYS` ∪ `INJECTED_CARD_INPUTS` (16 keys) | What a narrow or packed card's frozen block must hold |
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
- `LoggedCard.features_compact` and `LoggedCard.evidence_tier` are filled from columns of the same names, but only if the table has them. Neither column exists yet.
- `card_dict` uses `features_json` when it is present, else the compact block. Logged columns win key collisions.

**Exclusion rules:**
- **Replay** (`backend/eval/replay.py`):
  - A deck in which **any** card has `evidence_tier == 'partial_run'` is excluded whole, under `partial_run`. This check runs before `missing_scorer_inputs`, so such a deck is never counted twice. Cards are counted in `EvalRun.excluded` and decks in `EvalRun.partial_run_decks`; both appear in the report and the run record.
  - A deck in which **any** card has neither `features_json` nor a compact block is excluded whole, under `missing_scorer_inputs`. It is never sunk.
  - The excluded cards are counted in `EvalRun.excluded`, and the decks in `EvalRun.missing_inputs_decks`. Both appear in the rendered report and the persisted run record (`backend/eval/persistence.py`).
  - Replay no longer has the per-card `bad_features` reason.
- **Calibration** (`backend/eval/calibration.py`):
  - Exclusion is per card, since there are no ranks here.
  - A card with neither input is excluded alone, as `bad_features`.
  - A card with only a compact block is scored.
  - A card with `evidence_tier == 'partial_run'` is excluded alone, as `partial_run`, before the other per-card checks.
- **Who writes `partial_run`:** trades-eng, on the delivered rows of a partial run (head-eng ruling 21). Calibration's `select_current_cards` must also skip such jobs; that file belongs to trades-eng.

**Lean nightly** (`backend/eval/nightly.py`; the eval pass runs last in the daily tick):
- `run_all` decides which scorers are due **before** loading anything. With nothing due, it returns without calling `load_decks`, and no baseline is evaluated or recorded.
- `load_decks` selects only `EVAL_COLUMNS`, never `select(imp)`. Those columns are `impression_id`, `user_id`, `league_id`, `deck_job_id`, `card_index`, `trade_hash`, `features_json`, `propensity`, `base_score`, `final_score`, `archetype`, `shape_bucket` and `served_at`. It adds `features_compact` and `evidence_tier` only when the table has them.
- The nightly passes `project_features=True`, which keeps only `contract.PROJECTION_KEYS` in each parsed features dict. `PROJECTION_KEYS` is every key some registered scorer may read; it contains `FROZEN_INPUT_KEYS ∪ IDENTITY_KEYS`. Nightly estimates and a value-model fit are bit-identical with and without projection.
- On a synthetic 30-day window of 9,000 rows, tracemalloc's peak for `load_decks` went from 146 MB (`select(imp)`) to 53 MB.

**Reproducibility note:** taste rows learned from swipes decay with the wall clock when they are read (`taste_service.load_taste_vectors`). Two value-model fits, or two scorer instances, built at different moments can therefore differ in the last bits. Pin the clock, or use taste rows that don't decay (board-derived `prior:` rows), whenever a test or a comparison needs exact reproducibility. The fixtures in `test_eval_scorer_contract.py` and `test_eval_nightly_lean.py` use `prior:` rows for this reason.

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
- When a card has both a full row and a pack entry for the same `card_index`, **the full row wins**.

**Cost:** about 2% × (N − 30) × ~9 KB per served deck. With N ≈ 1,700 cards per served job (models-lead-launch §DEC-2 §1), that is about +0.3 MB per served deck on average, held for 90 days.

## 4. The safety-ceiling rule

The following decks are **never stored, paged, served or packed**:
- a deck from a run where `CoreDiagnostics.safety_ceiling_hit` is true;
- a deck from a failed job;
- a deck from a partial job.

They write no `deck_impressions` rows, no pack and no archive rows. The diagnostic is on the value-core branch `eng/value-core-count-bounded`, which isn't on main yet. That branch's `blind_grading.py:581` already refuses such runs for Calibration. The evidence writer and the page store apply the same refusal.

## 5. Field-set note

A narrow row's compact block, or a packed card, must freeze `FROZEN_INPUT_KEYS`: `COMPACT_KEYS` ∪ {`partner_user_id`, `taste_attrs`}. `COMPACT_KEYS` alone isn't enough.
- Without those two keys, `_inject` falls back to the global like rate and a taste derivation with no partner, and value_model's score moves.
- `test_compact_keys_alone_do_not_replay_value_model` pins the gap.
- `test_compact_block_scores_like_full_features` shows the 16-key block replays every registered scorer exactly.
- models-lead-launch §DEC-2 §2 lists the 14 keys only. Its packed field list (§4) already carries both.

The packed format is pending models-lead. The prototype is on `eng/evidence-pack-codec`, unmerged.

## Decisions needed

1. **The `evidence_tier` schema** (trades-eng, under head-eng's grant). This covers:
   - column name, type and allowed values;
   - the value for existing rows;
   - an index for the daily prune;
   - precedence when a row qualifies for more than one of `delivered`, `first30` and `ghost`. `archive` is disjoint by construction.
2. ~~**`docs/runbook.md:1022` still lists `bad_features`** among replay's exclusions.~~ **Done** (2026-10-22, commit f9d4f611): the line now lists `partial_run` and `missing_scorer_inputs`, both whole-deck reasons.

## Handoffs

- **trades-eng:**
  - the evidence writer: the pack for every served deck, C8 full rows from the build-time snapshot, `evidence_tier`, the bounded prune, and the safety-ceiling refusal;
  - page-store tests that call `assert_page_is_top_n` and `assert_prefix_stable`;
  - import `is_archive_deck` and `FROZEN_INPUT_KEYS` from `backend/eval/contract.py`. Don't restate them.
- **head-eng:** the schema grant for `evidence_tier` and the new evidence columns. The C9 ADR should cite this spec.
- **release-lead's scribe, at merge:** the living-memory write-back (CHANGELOG and TEST_LEDGER).

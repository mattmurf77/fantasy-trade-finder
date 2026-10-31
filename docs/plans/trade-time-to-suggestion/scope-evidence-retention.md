# Feature Scope — Deck-evidence retention prune (legal R28.20 (iii), dark until the cap is set)

**Date:** 2026-10-28 (reworked the same day to the final rules)
**Entry point:** direct ask. head-eng ruled on trades-eng's scrub/prune sizing on 2026-10-28: "build (b) NOW, dark". head-eng then relayed legal's final R28.20 the same day.
**Builder:** trades-eng
**Operator sign-off on waivers:** not needed. There are no waivers; analytics and evidence are answered below.

**The rules, final:**
- **Legal R28.20 (iii)** (`leads/legal-lead.md`): "365 days from first delivery for packs and every deck-evidence store, and 90 days for full rows". The prune must be scheduled and automatic and log counts. It covers every store of built or shown cards: `deck_evidence_packs`, `evidence_blob`, every `deck_impressions` row, and legacy `trade_impressions` if still written.
- **models-lead's addendum E** (`leads/models-lead-launch.md`):
  - E-a1: expiry is deck-atomic;
  - E-c1: the 90-day bound applies to decks that have a pack;
  - E-c2: ghost rows are in the 90-day class;
  - E-a3: a pack-less deck keeps its rows under the 365-day cap.
- **E-a3's backfill** was sized at over ½ day, so it isn't built (head-eng was told on 10-28).

---

## 1. Analytics scope

- [x] **(c) WAIVED. No analytics needed.**
  - It emits no event and changes no event; it is a storage-retention job.
  - Its only observable is a server log line per cleanup tick that deleted something: `[evidence] retention pruned {table: rows, decks: n, full_rows: n}`. It logs counts, never ids.
  - **Every reader fits inside the bounds:**
    - the flip read, 24–48 h plus weekly reruns;
    - the matcher, 14 days;
    - receipts, ≤ 56 days;
    - blind grading, 14 days;
    - `bakeoff_readout` and the B-DK audit, weekly (models-lead E3).
  - Replay and refits read packs, which keep every built card's compact inputs until the cap.
  - **The 56-day floor:** a bound under it is refused, so receipts can never lose a row.

## 2. Schema & flag scope

- **New/changed tables or columns:** none.
- **New index:** `ix_deck_impressions_served` on `deck_impressions (served_at)`, used by the cap's pack-less decks.
  - It's declared on the table, so a fresh DB gets it from `create_all`.
  - **On prod it is built off the boot path,** never in `init_db`. The data dictionary's rule: a plain `CREATE INDEX` on prod's `deck_impressions` blocks writes for a full scan and can outlast gunicorn's 120 s boot timeout.
  - **The script:** `scripts/create_evidence_retention_index.py` runs `CREATE INDEX CONCURRENTLY` with a 5 s `lock_timeout` in autocommit. It drops an INVALID leftover and rebuilds it; `--check` only reports.
  - **The prune's guard:** until the index exists, the cap skips pack-less decks and logs why once. Packed decks go through `ix_deck_evidence_packs_served`.
  - **Order:** release-lead or the operator runs the script before the cap goes above 0. trades-eng makes no prod writes.
  - → `docs/data-dictionary.md`: the `deck_impressions` index list and the retention note.
- **New/changed feature flags:** none. The cap knob is the rollback lever.
- **New `model_config` keys** → `docs/config-reference.md`:
  - `deck_evidence_retention_days`, the cap. **Default 0 = off, the whole prune included.** Legal's value is 365.
    - It's measured in days from a deck's first delivery.
    - Under 56 it's refused with a warning, and nothing is deleted.
    - **Rollback lever:** set it to 0 (deploy-free, `PUT /api/admin/config`).
  - `deck_evidence_full_row_days`, the full-row bound, default **90** (legal's value).
    - It acts only while the cap is on.
    - At 0, or at or past the cap, rows go with the deck at the cap. Under 56 it's refused.

**What goes, measured from first delivery:**
- **At the cap,** up to 200 decks per tick. Each deck is deleted in one transaction, so a failure leaves it whole for the next tick. A deck loses:
  - its `deck_outcomes`, every kind, and its `trade_pass_reasons` (the user's pass reasons, free text included). A packed card's are matched by its exact contract ids (`<deck_job_id>:<k>` for the pack's `card_count` cards, with or without a row); a row's by its `impression_id`;
  - its `deck_impressions` rows;
  - its `deck_card_withdrawals`;
  - its `deck_candidate_sets` row;
  - its `bakeoff_runs` row;
  - its `trade_policy_shadow` rows (the treatment's rejected candidates, `ix_trade_policy_shadow_job`);
  - its `deck_evidence_packs` row.
- **Also at the cap:**
  - legacy `trade_impressions` rows past it, taken by oldest id;
  - `trade_page_store` rows built before it. This is a backstop: the store's own eviction (`trade_page_store_evict_days`, 30 by default) runs only while the store is on, and could be set past the cap. There's one row per scope, so it's a small table.
- **At the full-row bound:** a packed deck's `deck_impressions` rows, full and ghost. The pack, its outcomes and the rest stay until the cap.
  - It works in chunks of 500 packs, at most 20 chunks per tick, resuming from an in-memory cursor. A restart walks again from the cap.
  - A failed chunk keeps the cursor, so it's retried next tick.

**Kept on their own clocks:**
- `trade_page_store` (`evidence_blob`): its own eviction (30 days unserved by default, plus the byte budget) while the store is on, with the cap's backstop above;
- `deck_diagnostic_snapshots`: 14 days;
- `trade_deck_lineage`: 24 h;
- `prepared_trade_*`: their `expires_at`.

**Found, outside this prune, for head-eng and legal's store list (c3):**
- `receipts_grades`: one append-only grade per graded impression, with assets and `trade_hash`;
- `grading_cards`: Calibration's shown trades.
Whether the cap covers them is head-eng's call before the flip. Legal: "if eng leaves any store out, tell legal before the flip".

**How decks are found:** through indexes only, in `served_at` order.
- First the packs (`ix_deck_evidence_packs_served`).
- Then pack-less decks through `ix_deck_impressions_served`, read in index order with a bounded LIMIT, never a DISTINCT over the backlog.
- A packed deck is only ever taken through its pack, so it always goes whole.

**Account rights (#523 QA P1-1, flip-blocking, fixed here):**
- Account export and deletion (`accounts.py`, onboarding-eng's area) found a user's `deck_outcomes` only through their `deck_impressions` rows.
- Once the full-row bound deletes a packed deck's rows, its outcomes (kept by contract id until the cap) would be exported never and deleted never.
- Both, and the `suggestion_trade_links` unlinking, now also match the user's packs' contract ids (`database.deck_pack_contract_ids`). That also covers a packed card's outcome that never had a row (E-b4). onboarding-eng was told.

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_deck_evidence_retention.py`, 41 tests (29 before #523 QA).
  - **What never deletes:** off at 0, full rows included; both 56-day floors, refused and logged.
  - **The cap:**
    - every store of a packed and of a pack-less deck goes at once, including a like and a pass reason on a packed card with no row;
    - no other deck's outcomes go (`d1` against `d10`);
    - a pack with 1,200 cards loses every outcome (chunked IN lists);
    - a pack-less scan never takes a deck whose pack is inside the cap.
  - **Full rows:**
    - a packed deck's rows go at 90 and everything else stays, so the outcome count is unchanged;
    - a pack-less deck keeps its rows;
    - with the bound at 0, 365 or 400, rows follow the cap;
    - chunks resume from the cursor, and a deck crossing later is still found;
    - a failed chunk keeps the cursor.
  - **Bounds:** both are measured from the first delivery, at and one day past each.
  - **Batching and failure:** one bounded batch per call; a failing deck is left whole; a failing `trade_impressions` or page-store step never stops the others.
  - **`trade_impressions` and `trade_page_store`:** rows past the cap go, and newer rows stay; page-store rows go with the store's flag off.
  - **The loop step:** reads both knobs, its defaults match `model_config`'s, never raises, and is wired into `_cleanup_loop`.
  - **The index:** pack-less decks wait for it (logged once); it's declared and never built by `init_db`.
  - **The script:** builds the index, is idempotent, and `--check` writes nothing.
- [x] **Sabotages:** all 43 mutations turn the suite red: QA's 40 (my 24, their X1–X5, re-expressed where the code moved) and 3 on the account paths (TEST_LEDGER).
- [x] **WAIVED, the structural guard, code-walk and TestFlight checklist:** backend-only, no user-visible surface, and dark by default.
- `testID`s: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added or changed |
| `living-memory/LLD.md` | updated | the deck-evidence conventions: the cap, full rows, outcome matching by contract id |
| `docs/architecture.md` | n/a | no module wiring change: one more cleanup-loop step, like the diagnostics expiry |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` entry | n/a | the bounds are legal's R28.20 (iii) and models-lead's addendum E, both recorded in their ledgers |
| `docs/data-dictionary.md` | updated | the `deck_impressions` index and retention |
| `docs/config-reference.md` | updated | the two keys |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** the `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** none (backend-only, dark).
- **Express lane:** no; full gates.
- **Turning it on** is head-eng's call. The steps:
  1. Run the index script.
  2. `PUT /api/admin/config` `deck_evidence_retention_days` = 365.
  3. The privacy page's §5 365-day line ships in the same deploy window (onboarding-eng's #373, legal R28.20 (v)).

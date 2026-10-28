# Feature Scope — Deck-evidence retention prune (dark)

**Date:** 2026-10-28
**Entry point:** direct ask (head-eng's ruling on trades-eng's scrub/prune sizing, 2026-10-28: "build (b) NOW, dark")
**Builder:** trades-eng
**Operator sign-off on waivers:** not needed (no waivers; analytics and evidence answered below)

Sizing and options: the shared note `trades-eng-scrub-prune-sizing.md` (head-eng's folder). Retention bound inputs: analytics-lead R28.20, via head-eng. A minimum of 45 days from first delivery; launch-period decks kept until 2026-12-31; a 90-day recommendation for packs and full rows. models-lead's §3 rule (deck lifetime, any cap ≥ 365 days) is still to be reconciled by head-product. So the bound ships as a knob, off.

---

## 1. Analytics scope

- [x] **(c) WAIVED. No analytics needed.**
  - It emits no event and changes no event; it is a storage-retention job.
  - Its only observable is a server log line, `[evidence] retention pruned {table: rows, decks: n}`, per cleanup tick that deleted something.
  - **What it deletes:** past the bound, the evidence the readouts read. Inside the bound, every reader is untouched. Their windows: the flip read 24–48 h plus weekly reruns; the matcher 14 days; receipts ≤ 56 days; blind grading 14 days; C3 until ~12-09.
  - **The 56-day floor:** a bound under it is refused, so receipts can never lose a row.

## 2. Schema & flag scope

- **New/changed tables or columns:** none.
- **New index:** `ix_deck_impressions_served` on `deck_impressions (served_at)`.
  - It's declared on the table, so a fresh DB gets it from `create_all`.
  - **On prod it is built off the boot path,** never in `init_db`. The data dictionary's rule: a plain `CREATE INDEX` on prod's `deck_impressions` blocks writes for a full scan and can outlast gunicorn's 120 s boot timeout.
  - **The script:** `scripts/create_evidence_retention_index.py` runs `CREATE INDEX CONCURRENTLY` with a 5 s `lock_timeout` in autocommit. It drops an INVALID leftover and rebuilds it; `--check` only reports.
  - **The prune's guard:** until the index exists, it skips pack-less decks and logs once why. Packed decks go through their own index, `ix_deck_impressions_served`'s sibling `ix_deck_evidence_packs_served`.
  - **Order:** release-lead or the operator runs the script before `deck_evidence_retention_days` goes above 0. trades-eng makes no prod writes.
  - → `docs/data-dictionary.md` (the `deck_impressions` index list and the retention note).
- **New/changed feature flags:** none. The knob is the rollback lever.
- **New `model_config` keys** → `docs/config-reference.md`:
  - `deck_evidence_retention_days`, **default 0 = off**. The bound in days from a deck's first delivery. Under 56 it is refused with a warning, and nothing is deleted. **Rollback lever:** set it to 0 (deploy-free, `PUT /api/admin/config`).
  - `deck_evidence_keep_until_epoch`, default `1798761600` (2027-01-01T00:00:00Z). The date floor: nothing is deleted before it, whatever the bound says, so launch-period decks are kept until 2026-12-31.

**What a pruned deck loses** (each deck in its own transaction; a failure leaves it whole for the next tick):
- its `deck_evidence_packs` row;
- its `deck_impressions` rows (full and ghost);
- its `deck_card_withdrawals`;
- its `deck_candidate_sets` row.

**Kept:**
- `deck_outcomes`: the user's own actions. They carry no counterparty id, and legal named packs and full rows only.
- `trade_page_store`: its own 7-day TTL and byte budget.
- `deck_diagnostic_snapshots`: their own 14-day expiry.
- `trade_impressions`: out of scope.

**Batch:** up to 200 decks per 5-minute tick, found by the pack's `served_at` (`ix_deck_evidence_packs_served`), then pack-less decks by their rows' `served_at` (the new index), read in index order with a bounded LIMIT, never a DISTINCT over the backlog.

## 3. Evidence scope

- [x] **Unit tests:** `backend/tests/test_deck_evidence_retention.py`, 14 tests.
  - **What never deletes:** off by default; the 56-day floor (refused and logged); the date floor.
  - **What it deletes:** packed and pack-less decks go from every evidence table, while a recent deck and every outcome stay; the bound is the first delivery.
  - **Batching:** one bounded batch per call; a deck whose delete fails is left whole, and the others proceed.
  - **The loop step:** reads both knobs (defaults: off, and the 2027-01-01 floor); never raises; is wired into `_cleanup_loop`.
  - **The index:** it's declared on the table, and pack-less decks wait for it with a logged reason.
  - **The script:** builds it on an existing DB, leaves a valid one alone, and `--check` writes nothing.
- [x] **Sabotages:** each mutation of the above turns the suite red (TEST_LEDGER).
- [x] **WAIVED, the structural guard, code-walk and TestFlight checklist:** backend-only, no user-visible surface, and dark by default.
- `testID`s: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added or changed |
| `living-memory/LLD.md` | updated | the deck-evidence conventions: the retention prune and what it never deletes |
| `docs/architecture.md` | n/a | no module wiring change: one more cleanup-loop step, like the diagnostics expiry |
| `living-memory/HLD.md` | n/a | no architecture shift |
| `docs/cross-client-invariants.md` | n/a | no shared constant |
| `docs/glossary.md` | n/a | no new domain term |
| ADR or `DECISIONS.md` entry | n/a | head-eng's ruling (2026-10-28) is the decision; the bound itself is legal's and head-product's, set later through the knob |
| `docs/data-dictionary.md` | updated | `deck_impressions` index and retention |
| `docs/config-reference.md` | updated | the two keys |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` on the pushed sha.
- **Evidence recorded:** the `living-memory/TEST_LEDGER.md` entry.
- **TestFlight verification:** none (backend-only, dark).
- **Express lane:** no; full gates.
- **Turning it on** is a later operator or head-eng step, once legal and head-product set the bound. It's one `PUT /api/admin/config` of `deck_evidence_retention_days`, and before 2027-01-01 the date floor still holds everything.

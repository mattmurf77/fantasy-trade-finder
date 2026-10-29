# Feature Scope — Team overhaul in account deletion and export

**Date:** 2026-10-29
**Entry point:** direct ask (head-eng → onboarding-eng 2026-10-29). trades-eng found the gap in the R28.20 c2/c3 lists (`trades-eng-r28-20-c2-c3-lists.md`, "Gaps" 2), and head-eng confirmed it. Before the flip; trades-eng reviews the overhaul side.
**Builder:** onboarding-eng
**Operator sign-off on waivers:** not needed (§1 (c) and the TestFlight row are waived for reasons, below)

**Why.** `accounts.py` never named the overhaul tables. They key their owner as `overhauls.account_user_id` and everything else by `overhaul_id`, so the `user_id` loops in deletion and export missed all five. `overhaul.enabled` was on for TestFlight from 09-07 to 10-27, so prod likely has rows.
- A deleted user's own overhauls stayed.
- OTHER users' offers kept the deleted user's id, name, public card and private evidence (both sides' boards).
- The export carried none of it.

**What changes** (`backend/accounts.py`, server only, no schema):
- **Deletion, own rows:** `overhauls` where `account_user_id` is in the user's id scope go, with every `overhaul_offers` / `overhaul_roadmaps` / `overhaul_attempts` / `overhaul_reservations` row under them. Their `league_user_id`s (ESPN/MFL member ids aren't in the id scope) are read first and join the ids scrubbed below.
- **Deletion, other users' offers naming them** (the `trade_proposals` precedent):
  - `counterparty_user_id` / `counterparty_username`, and the card's `target_user_id` / `target_username` → `DELETED_USER_PLACEHOLDER`;
  - the card loses the counterparty's Fleeced-derived fields (R28.20 c2): `match_context`'s `counterparty*` keys (benefits, preference evidence), `reasons` (the bilateral arm's says whether the other manager has preferences), and the deck-card partner fields the shared serializer can carry (`likes_you`, `standing_offer_reason`, `breaker`, `fit`, `roster_evaluation`, `rationale`, `narrative`);
  - `evidence_json` → NULL (both sides' private boards; it has no reader);
  - an **undecided** offer's `package_hash` → `redacted_` + 32 hex, so regeneration's cache can't re-surface the scrubbed row as a live offer. A liked or passed offer keeps its hash, which is what stops a passed package coming back (data-dictionary). The hash stays under legal's (viii).
  - The package, decision, availability and send history (attempts) stay.
- **Deletion, other users' roadmaps:** `summary_json.counterparties` entries naming them → the placeholder.
- **Export:** `overhauls` joins `_EXPORT_TABLES` (by `account_user_id`); the four child tables follow by `overhaul_id`. An offer's `evidence_json` is omitted, and its `card_json` goes out without the counterparty's c2 fields (the R28.20 (iv) direction).
- **Counts** (the DELETE response): `overhauls_deleted`, `overhaul_{offers,roadmaps,attempts,reservations}_deleted`, `overhaul_offers_counterparty_anonymized`, `overhaul_roadmaps_counterparty_anonymized`.
- **The one-time purge** (`scripts/purge_entry_users.py`) discovers `overhaul_offers.counterparty_user_id`, so its verify (a) covers it, and its "known general deletion gap" info line is gone.

**Left as is (for head-eng / trades-eng / legal):**
- Other users' `overhauls.snapshot_json.rosters` keys and `recovery_json.holder_user_id` are platform roster and pick-ownership snapshots keyed by league member ids. That's the same class as the Sleeper pick grids that deletion KEEPS. Not scrubbed here.
- `overhaul_attempts.error_json` is the provider's error text, capped at 200 chars. Not traced for names.
- Blended scalars on the card (`mismatch_score`, `composite_score`, `basis`) stay, as trades-eng recommends for decks. That's legal's call.
- A scrubbed offer can't be sent: the placeholder resolves to no roster. A regenerated card for the same package (from consensus, the board being gone) is a new offer.

## 1. Analytics scope
- [x] **(c) WAIVED:** deletion and export fire no events, and none are added.

## 2. Schema & flag scope
- Tables, columns, flags, env, `model_config`: none. Not flag-gated, like the rest of the deletion matrix (App Store 5.1.1(v)).
- **Rollback:** revert the PR. Rows already scrubbed stay scrubbed (deletion is one-way by design).

## 3. Evidence scope
- [x] **Unit tests** (`backend/tests/test_account_deletion_coverage.py`, synthetic only):
  1. `test_overhauls_deleted_and_offers_naming_the_owner_scrubbed`: own overhauls under the Sleeper id and the `acct_` alias go with all four child tables. Two offers in another user's overhaul name the owner, by Sleeper id (passed) and by the owner's ESPN member id (undecided). Each is scrubbed to an exact expected card, with evidence NULL and the decision kept. The passed offer keeps its hash and the undecided one is re-minted. An unrelated offer is byte-identical. A send attempt on the scrubbed offer stays. The roadmap's counterparties become the placeholder. No overhaul table holds any marker of the owner afterwards: ids, the name, the old undecided hash, or the evidence values.
  2. `test_export_carries_own_overhauls_without_private_evidence`: own rows in all five tables and none of another user's; no `evidence_json`; the card without `counterparty*` / `reasons`, keeping the target id.
  3. `test_every_table_with_a_user_id_column_is_handled_in_accounts`: a schema scan. Every table with a `*user_id*` column must be named in `accounts.py` code, comments stripped. On main's `accounts.py` it fails on exactly `overhauls`, `overhaul_offers`, `overhaul_reservations` (the gap). It also fails on a probe table added to `database.py`.
  - `test_purge_entry_users.py`: the discovery test (which captures `delete_user_data`'s SQL) knows the overhaul key columns. The info test asserts no overhaul line.
- [x] **Sabotage 19/19 red,** restored byte-identical:
  - deletion (13): children kept; own matched by `league_user_id`; member ids not named; evidence kept; an undecided hash kept; a passed hash re-minted; the count zeroed; card ids kept; the username kept; `counterparty*` match context kept; `reasons` kept; `likes_you` kept; roadmaps not scrubbed;
  - export (4): evidence leaves; the card unredacted; no child rows; `overhauls` dropped from the manifest;
  - scan (1): main's `accounts.py`;
  - purge (1): the counterparty column not discovered.
  - A probe table fails the scan too (positive control).
- [x] **Code-walk:** `evidence_json` has no reader: `overhaul_store._offer(include_evidence=True)` has no caller, so NULLing it changes no behavior. `package_hash` is read only by generation's `by_hash` cache (`overhaul_api.py:642`). The send path reads `counterparty_user_id` (`overhaul_api.py:1036`), so a scrubbed offer fails at roster resolution instead of reaching the deleted user.
- [x] **TestFlight: WAIVED.** Server-only, no client change, and `overhaul.enabled` is off.
- `testID`s: none.

## 4. Docs scope
| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **updated** | `DELETE /api/account` (overhaul handling + counts), `GET /api/account/export` (overhaul tables, evidence omitted) |
| `docs/data-dictionary.md` | **updated** | `overhaul_offers`: account deletion and export |
| `living-memory/LLD.md` | n/a | the deletion matrix's convention is unchanged (delete own, anonymize the counterparty) |
| `docs/architecture.md`, `living-memory/HLD.md` | n/a | no module wiring or architecture change |
| `docs/cross-client-invariants.md`, `docs/glossary.md` | n/a | server only; no new term |
| ADR / `DECISIONS.md` | n/a | head-eng's ruling, the trade_proposals precedent |
| **`web/privacy.html` (#373, not on main)** | **flagged** | #373's §6 says overhaul plans "aren't yet removed by in-app deletion" and "are not yet included" in the export. Both are false once this deploys. The words are legal's; see the PR |

## 5. Ship gate declaration
- **CI:** `backend-tests`, `mobile-typecheck`, testid-lint, `web-structure` green.
- **Evidence:** a `living-memory/TEST_LEDGER.md` entry.
- Express lane declared by the operator? No.

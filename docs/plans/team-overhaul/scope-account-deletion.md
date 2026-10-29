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
- **Deletion, own rows:** `overhauls` where `account_user_id` is in the user's id scope go, with every `overhaul_offers` / `overhaul_roadmaps` / `overhaul_attempts` / `overhaul_reservations` row under them.
- **The ids scrubbed below are exactly the user's id scope** (release-lead QA P1). An offer names its counterparty by league member id: the user's own id on ESPN/MFL (`session_input.py:58`), the roster owner on Sleeper. The deleted user's own overhauls' `league_user_id` is NOT added: for a Sleeper co-owner it's the roster's primary owner, another live person (`session_input.py:99`).
- **Deletion, other users' offers naming them** (the `trade_proposals` precedent):
  - `counterparty_user_id` / `counterparty_username`, and the card's `target_user_id` / `target_username` → `DELETED_USER_PLACEHOLDER`;
  - the card loses the counterparty's Fleeced-derived fields (R28.20 c2): `match_context`'s `counterparty*` keys (benefits, preference evidence) and `opponent_outlook` (the narrative arms', which can be the partner's declared outlook; trades-eng), `reasons` (the bilateral arm's says whether the other manager has preferences), and the deck-card partner fields the shared serializer can carry (`likes_you`, `standing_offer_reason`, `breaker`, `fit`, `roster_evaluation`, `rationale`, `narrative`);
  - `evidence_json` → NULL (both sides' private boards; it has no reader);
  - a liked or undecided offer → `availability = "stale"` (trades-eng's review): `sendable` is `like` + `fresh` (`overhaul_service.py:367`), so a scrubbed liked offer would otherwise read as sendable and then fail at `overhaul_api.py:1036`. Stale is the native retirement: the UI shows it as stale, it's never sent (`:773`), and a refresh rebuilds against current rosters;
  - an **undecided** offer's `package_hash` → `redacted_` + 32 hex, so regeneration's cache can't re-surface the scrubbed row as a live offer. A liked or passed offer keeps its hash, which is what stops a passed package coming back (data-dictionary). The hash stays under legal's (viii).
  - The package, decision, availability and send history (attempts) stay.
- **Deletion, other users' roadmaps:** `summary_json.counterparties` entries naming them → the placeholder, and a stored `counterparty_asset_not_owned` blocker on a scrubbed offer (its `compat_json` message names the team, QA P2-1) gets `ownership_copy.refusal_message`'s unnamed form, the sentence a nameless counterparty already gets. No new copy.
- **Deletion, other users' snapshots and recovery** (trades-eng's review): `capture_snapshot` keys `rosters` by league member id and by `draft_picks.owner_user_id`, and `recovery_json.holder_user_id` / `holder_username` come from the same pick owners. On ESPN/MFL grids those can be the deleted user's Fleeced-minted id (`entry:*`, `acct_*`), the class deletion already anonymizes in `draft_picks` and `pick_assignment_settings.order`. That id → the placeholder (a roster key's assets merge under it). Public platform ids stay.
- **Deletion, blended scalars on the scrubbed cards** (legal R28.22 b and b2, head-eng 10-29). The test: a blended value may stay only if nothing kept beside it works out a dropped value and it isn't a copy of a dropped field. Applied to every card of the partner alike:
  - `surplus_margin` (on an overhaul card, `mismatch_score`): **nulled**, as head-eng rules for every card of the deleted partner.
  - `base_score` (here `composite_score`) with `fit.aggregate`: on both owner arms, `composite_score` and `mismatch_score` are the same number, the card's presentation rank (`trade_gen_owner.py:649-650`, `trade_gen_bilateral.py:517`). It's a copy of a nulled field, so it fails the test and is **nulled too**. `fit` (with `aggregate`) is already removed, so they go together.
  - `final_score`: **not stored** on an overhaul card. `card_json` is `trade_card_to_dict`, which has no final score or reranker multipliers. Nothing to isolate.
  - `basis`: **kept** (legal: it says only that the partner had a board). `fairness_score`: **kept** (the consensus market ratio).
  - The client tolerates null scores (`normalizeTradeCard` falls back when `mismatch_score` isn't a number), and `offer_score` reads `composite_score or 0`.
- **Orphaned overhauls (legal R28.22 d2, MUST):** `accounts.delete_orphaned_overhauls()` deletes overhauls whose `account_user_id` has no `users` row and no durable `sessions` row, with every child row. Those are accounts deleted, or entry users purged, before deletion covered overhauls. It runs once per process from the server's cleanup loop (`_sweep_orphaned_overhauls_once`): a failure retries next tick, and a success logs only a count.
  - **Live owners (corrected after QA P3):** an owner is live while a `users` row, a durable `sessions` row, or an `accounts` row (the `acct_` alias, or the bound Sleeper id) names them. The durable session is the strong signal: `session_init` writes the `users` row in a background thread after its response (`server.py:27838-27920`). `migrate_board_data` deletes the from-id's `users` row on a bind, so the `accounts` row keeps a bound account live.
  - **Also swept (QA P2-2):** an overhaul whose owner's `users` row was created more than an hour after it, which means a new account under an id deleted before the fix. The hour covers the background write. Child rows whose overhaul is already gone are swept too.
  - Counts come from rowcounts. The failure log carries the error class only, since a DB error's text holds the statement's parameters. Runbook § Orphaned-overhaul sweep.
  - It's own data only. Other users' offers naming someone deleted before the fix aren't backfilled (R28.20 (ii) 5).
- **Export:** `overhauls` joins `_EXPORT_TABLES` (by `account_user_id`); the four child tables follow by `overhaul_id`. An offer's `evidence_json` is omitted, and its `card_json` goes out without the counterparty's c2 fields (the R28.20 (iv) direction).
- **Counts** (the DELETE response): `overhauls_deleted`, `overhaul_{offers,roadmaps,attempts,reservations}_deleted`, `overhaul_offers_counterparty_anonymized`, `overhaul_roadmaps_counterparty_anonymized`.
- **The one-time purge** (`scripts/purge_entry_users.py`) discovers `overhaul_offers.counterparty_user_id`, so its verify (a) covers it, and its "known general deletion gap" info line is gone.

**Left as is (for head-eng / trades-eng / legal):**
- Public platform ids (Sleeper user ids, platform owner ids) in other users' snapshots and recovery stay, as on the Sleeper pick grids deletion KEEPS. Only Fleeced-minted ids go (above).
- `overhaul_attempts.error_json` is the provider's error text, capped at 200 chars. Not traced for names.
- Blended scalars on the card (`mismatch_score`, `composite_score`, `basis`) stay, as trades-eng recommends for decks. That's legal's call.
- A regenerated card for the same package, built from consensus with the board gone, is a new offer. The person may reappear there as a platform leaguemate, which legal's §6 "What may remain" allows.

**Follow-ups (QA, not blocking):**
- P2-3: another user's generation running across a deletion can insert offers naming the deleted user after the scrub reads, because there's no fence. Overhaul is off; fence it before it's turned on.
- A heavy user's deletion ran per-row UPDATEs (55k for 50k offers in 18.6 s, in one transaction). That's fine at beta volume; make them set-based later.
- #373's two overhaul bullets ship together with this PR (see the docs table).

## 1. Analytics scope
- [x] **(c) WAIVED:** deletion and export fire no events, and none are added.

## 2. Schema & flag scope
- Tables, columns, flags, env, `model_config`: none. Not flag-gated, like the rest of the deletion matrix (App Store 5.1.1(v)).
- **Rollback:** revert the PR. Rows already scrubbed stay scrubbed (deletion is one-way by design).

## 3. Evidence scope
- [x] **Unit tests** (`backend/tests/test_account_deletion_coverage.py`, synthetic only):
  1. `test_overhauls_deleted_and_offers_naming_the_owner_scrubbed`: own overhauls under the Sleeper id and the `acct_` alias go with all four child tables. Three offers in another user's overhaul name the owner: by Sleeper id (passed, and liked) and by the owner's ESPN member id (undecided). Each is scrubbed to an exact expected card (`opponent_outlook` dropped too), with evidence NULL and the decision kept. The passed and liked offers keep their hashes, and the undecided one is re-minted. The liked and undecided offers go stale; the passed one stays fresh. An unrelated offer is byte-identical. A send attempt on the scrubbed offer stays. The roadmap's counterparties become the placeholder. No overhaul table holds any marker of the owner afterwards: ids, the name, the old undecided hash, or the evidence values.
  2. `test_a_minted_id_in_other_overhauls_snapshots_and_recovery_becomes_the_placeholder`: an `entry:espn:` id keying another user's snapshot rosters, and holding its recovery pick, becomes the placeholder (assets merged under it; the holder's name too). Another overhaul naming a public Sleeper id is byte-identical, and stays so when that Sleeper user is deleted.
  3. `test_export_carries_own_overhauls_without_private_evidence`: own rows in all five tables and none of another user's; no `evidence_json`; the card without `counterparty*` / `reasons`, keeping the target id.
  4. The R28.22 additions: `test_orphaned_overhauls_are_deleted_and_live_owners_kept` (a non-entry and an `entry:mfl:` orphan go with their children; owners with a users row or only a durable session stay; idempotent), `test_the_orphan_sweep_runs_once_per_process_and_logs_only_a_count` (a failure retries, a success ends it, the log is the count), and `test_the_cleanup_loop_runs_the_orphan_sweep`. The scrub test's expected card has both scalars null.
  5. `test_every_table_with_a_user_id_column_is_handled_in_accounts`: a schema scan. Every table with a `*user_id*` column must be named in `accounts.py` code, comments stripped. On main's `accounts.py` it fails on exactly `overhauls`, `overhaul_offers`, `overhaul_reservations` (the gap). It also fails on a probe table added to `database.py`.
  - `test_purge_entry_users.py`: the discovery test (which captures `delete_user_data`'s SQL) knows the overhaul key columns. The info test asserts no overhaul line.
- [x] **Sabotage 54/54 red,** restored byte-identical (35 before QA, 19 after):
  - deletion (13): children kept; own matched by `league_user_id`; member ids not named; evidence kept; an undecided hash kept; a passed hash re-minted; the count zeroed; card ids kept; the username kept; `counterparty*` match context kept; `reasons` kept; `likes_you` kept; roadmaps not scrubbed;
  - after trades-eng's review (8): no stale; stale only for undecided; a passed offer stale too; `opponent_outlook` kept; rosters not scrubbed; recovery not scrubbed; recovery name kept; public Sleeper ids scrubbed too;
  - after R28.22 (8): the scalars kept; only `mismatch_score` nulled; the sweep ignores durable sessions; the sweep ignores users; the sweep keeps children; the sweep never retries after a failure; the sweep runs every tick; the sweep not in the loop;
  - after release-lead's QA (19): QA's 7 escapes (scrub by LIKE prefix; snapshot keys by prefix; orphan judged by `league_user_id`; live by prefix; ids logged; scan probes `owner_id` and `counterparty`+`holder`); plus the P1 put back; compat not scrubbed; compat scrubbed on every offer; the `acct_` alias not live; the bound Sleeper id not live; NULL in the NOT IN; re-signup with no margin; re-signup not swept; child orphans not swept; the failure log carrying the error text; purge (h) not in the exit code; purge (h) missing recovery holders. All 19 red. The earlier rounds' 22 still-applicable cases stay red; 3 no longer apply, because their code was replaced.
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
| **`web/privacy.html` (#373, not on main)** | **ruled (legal R28.22 d2; head-eng approved the order)** | This PR makes both halves live, deletion and export. If it merges before #373 deploys, #373 drops both overhaul bullets ("…aren't yet removed by in-app deletion…" and "Team-overhaul plans are not yet included…"). Otherwise a follow-up that deploys with this PR drops them |

## 5. Ship gate declaration
- **CI:** `backend-tests`, `mobile-typecheck`, testid-lint, `web-structure` green.
- **Evidence:** a `living-memory/TEST_LEDGER.md` entry.
- Express lane declared by the operator? No.

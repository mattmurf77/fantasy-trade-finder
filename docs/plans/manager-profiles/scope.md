# Feature Scope — Manager revealed-preference profiles (capture only)

**Date:** 2026-11-10
**Entry point:** direct ask (side session started from the trade-quality evaluation session, 2026-11-10)
**Builder:** Claude Code session on branch `feat/manager-profiles`
**Operator sign-off on waivers:** needed — §1 (c) and §3 (TestFlight) are waived; see the reasons. Privacy question in [design.md](design.md) "Open questions" 1 must be answered before the flag is turned on.

Design: [design.md](design.md).

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** —
- [x] **(c) WAIVED — no analytics needed because:** this is server-side data capture with no
  user-facing surface and no user action to measure. The capture's own volume is visible in the
  tables (`sleeper_waiver_moves`, `manager_profiles`), and its Sleeper calls already flow through
  `api_observability` as `sleeper` / `league.transactions` (unchanged label, so no taxonomy row).
  No `user_events` type is added, so neither `analytics_taxonomy.py` nor
  `analytics_queries.NON_INTENT_EVENTS` changes.

## 2. Schema & flag scope

- New tables: **`sleeper_waiver_moves`** (raw waiver / free-agent transactions, idempotent on
  `transaction_id`) and **`manager_profiles`** (one row per league × roster owner, replaced per
  league on each sweep). Both are new tables created by `metadata.create_all`; no column is added
  to an existing table, so `_migrate_db` is untouched. → `docs/data-dictionary.md` updated.
- Account rights: `manager_profiles.owner_id` names a person, so `accounts.delete_user_data`
  deletes a deleted account's rows and `_EXPORT_TABLES` exports them
  (`test_every_table_with_a_user_id_column_is_handled_in_accounts` enforces it).
  `sleeper_waiver_moves.creator` is kept like `sleeper_trades.raw`'s `creator`: public league
  transaction log.
- New flag: **`market.manager_profiles`**, default **false** in `FLAG_KEYS`, `config/features.json`
  and the five flag fixtures that mirror it. Requires `market.trade_capture` (on) and the daemon's
  shared rosters read (on whenever `sleeper.trade_block`, `market.roster_history` or
  `picks.owned_sync` is on). Off ⇒ no extra fetch, no rows. → `docs/config-reference.md` updated.
  **Graduation criterion:** the operator answers design.md open question 1 (privacy). Turning it
  on is capture only; a *consumer* gets its own flag and scope block.
- New env vars / `model_config` keys: none. The thinness floors are module constants in
  `backend/manager_profiles.py`; nothing reads them at serve time.

## 3. Evidence scope

- [ ] **Structural guard:** n/a — no mobile change.
- [x] **Unit tests:** `backend/tests/test_manager_profiles.py` (new, 23 tests, committed fixture
  `backend/tests/fixtures/sleeper/manager-profiles/`, `_opener` seam, no network): parsing,
  winning / outbid / other-failed bids with clearing price and remaining budget, non-FAAB leagues,
  trade style and asset mix, co-owned roster, ownerless roster, non-owner moves, managers with no
  history, idempotent re-sweep, lossy backfill retry, profile failure isolation, flag off, no
  roster map, the one-time backfill cost, flag registration, leaf imports.
  `backend/tests/test_session_init_sleeper_calls.py` (+2): flag off adds no calls and no rows;
  flag on costs one 18-leg backfill, still one rosters and one meta read, then ≤2 legs.
- [x] **Code-walk proof** that trade generation is unchanged: the only readers of the new tables
  are `database.load_manager_profiles` / `load_sleeper_waiver_moves` /
  `has_manager_profile_capture`, called only from `sleeper_trades_service`
  (`git grep -n "manager_profiles\|sleeper_waiver_moves" -- backend` shows no hit in
  `trade_service.py`, `trade_gen_v2.py`, `trade_optimizer.py`, `trade_policy.py` or any route).
  The one server edit is inside the session-init background daemon's `market.trade_capture`
  block, after the response has been sent; with the flag off it passes `profiles=False`, and
  `sweep_weeks(profiles=False)` is the original expression (`test_sweep_weeks_default_unchanged`).
- [ ] **Manual TestFlight checklist:** none.
- [x] **WAIVED because:** backend-only data capture; no response a client receives changes.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | no route added or changed |
| `living-memory/LLD.md` | n/a | no convention shifted: new tables follow the `sleeper_trades` pattern (append-only, idempotent on `transaction_id`) |
| `docs/architecture.md` | updated | module table: `manager_profiles.py` (new leaf) and the `sleeper_trades_service.py` row |
| `living-memory/HLD.md` | n/a | no new client, flow or service; one more leaf on an existing background sweep |
| `docs/cross-client-invariants.md` | n/a | nothing shared with a client |
| `docs/glossary.md` | updated | "Manager profile" |
| ADR or `DECISIONS.md` entry | updated | DECISIONS: profiles keyed on roster `owner_id`, current season only, rookie-draft signal deferred, one-time backfill as the only extra Sleeper cost |
| `docs/data-dictionary.md` | updated | `sleeper_waiver_moves`, `manager_profiles` |
| `docs/config-reference.md` | updated | `market.manager_profiles` |
| `docs/integrations/sleeper.md` | updated | endpoint 11 now also keeps waiver / free-agent rows; payload shape; §5.2 call budget |
| `docs/plans/README.md` | updated | thread-folder row |

## 5. Ship gate declaration

- **CI green:** `backend-tests` must pass on the pushed sha; no mobile files changed.
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry for this branch.
- **TestFlight verification:** none (waived above).
- Express lane declared by the operator? **No** — full gates. Not pushed or merged to `main` by
  this session.

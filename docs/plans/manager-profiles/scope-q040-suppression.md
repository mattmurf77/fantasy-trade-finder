# Feature Scope — Manager-profile suppression after account deletion (Q-040)

**Date:** 2026-11-24
**Entry point:** direct ask (operator decision on Q-040: options (a) + (b))
**Builder:** builder subagent on branch `fix/q040-profile-suppression`
**Operator sign-off on waivers:** needed — §1 (c) and the §3 TestFlight row are waived; reasons below.

Design: [design.md](design.md) open question 1. Decision: [D-282](../../../living-memory/DECISIONS.md).

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** —
- [x] **(c) WAIVED — no analytics needed because:** a server-side privacy control with no user
  action to measure. The deletion route's existing count map gains
  `manager_profile_suppressions_added`; no `user_events` type, so neither
  `analytics_taxonomy.py` nor `NON_INTENT_EVENTS` changes.

## 2. Schema & flag scope

- New table **`manager_profile_suppressions`** (`id_hmac` PK, `created_at`), created by
  `metadata.create_all`; no column added to an existing table, `_migrate_db` untouched.
  → `docs/data-dictionary.md` updated.
- Account rights: holds no id; never exported, registered in `accounts._KEPT_WITH_REASON`.
- Flags: none. Deliberately unflagged: the suppression is written on every deletion, so a
  deletion made while `market.manager_profiles` is off still holds when it is turned back on.
- Env vars: none new. Reuses `EXPERIMENT_SALT_KEY` as the HMAC key (D-282 says why);
  `docs/config-reference.md` row updated (changing the key orphans every entry).

## 3. Evidence scope

- [x] **Unit tests:** new `backend/tests/test_manager_profile_suppression.py` (7 tests: the
  league-mate capture skips the deleted owner, no raw id in the row, keyed hash, username-only
  re-signup keeps it while a verified new account clears it, rollback leaves none, never
  exported). Each proven red against a named sabotage (TEST_LEDGER 2026-11-24).
- [x] **Code-walk proof:** deletion → `accounts._delete_user_data` (next to the
  `manager_profiles` delete) → `database.suppress_manager_profiles(conn, …)`; capture →
  `sleeper_trades_service.capture_manager_profiles` → `database.load_manager_profile_suppressions`
  → filtered `replace_manager_profiles`; re-signup → `accounts.mark_user_verified` (first
  verification of the users row) → `database.clear_manager_profile_suppression`.
- [x] **Structural guard:** `qa/web/check_web_structure.py` (the policy's pinned sentences stay
  verbatim) green after the privacy edit.
- [ ] **Manual TestFlight checklist:** **WAIVED because** backend-only; no app surface changes.
- `testID`s added/renamed: none.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | `DELETE /api/account` row: the additive count `manager_profile_suppressions_added`; no route added |
| `living-memory/LLD.md` | n/a | no schema or route convention changed |
| `docs/architecture.md` | updated | `sleeper_trades_service.py` row: the capture drops suppressed owners |
| `living-memory/HLD.md` | n/a | no new module, client or major flow |
| `docs/cross-client-invariants.md` | n/a | nothing shared with clients |
| `docs/glossary.md` | updated | "Manager profile" entry |
| ADR or `DECISIONS.md` entry | updated | D-282 |

## 5. Ship gate declaration

- **CI green:** required before merge (operator pushes).
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` 2026-11-24.
- **Privacy text:** one sentence added to `web/privacy.html` §1 "League data". The page's
  effective date was not changed, and the policy's pinned sentences came through legal-lead; the
  new sentence did not. Both are operator calls before publishing.
- Express lane declared by the operator? no.

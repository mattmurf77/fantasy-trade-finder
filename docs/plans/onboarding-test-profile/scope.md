# Feature Scope — Onboarding test profile (extends Test Stages)

**Date:** 2026-11-11
**Entry point:** direct ask (operator, via coordinator)
**Builder:** test-profile subagent, worktree `feat/onboarding-test-profile`
**Operator sign-off on waivers:** none are waived. The design.md §8 defaults were set by the coordinator.

**Operator rulings:**
- **2026-11-11:** league linking must use the real production flows (design.md §10). The interim linking shortcut was removed, and option A was built for ESPN and MFL (§11).
- **2026-11-12:** "I want to cover sleeper testing too." The real Sleeper flow runs too, behind split identity, a storage re-key and an outbound chokepoint (§12).

The build sits beside Test Stages and does not change it. Its leagues live in a private `qa_tp:<real>:` namespace, filled by the production linking flows.

---

## 1. Analytics scope

- [x] **(b) Existing events cover it.** Test-profile ids are `qa_tp_<id>`. Existing analytics treat them as follows:
  - Events from `/api/events` carry the user id of the verified session (`server.py:17393`).
  - `analytics_queries.device_exclusion` already strips every `qa\_%` id (`analytics_queries.py:567-568`).
  - The build adds the same exclusion to the seven hand-rolled filters that skip `device_exclusion`: `analytics_queries.py:754`, `:907`, `:978`, `:1140`, `:1170`, `:1495`, `:1725`.
  - No new event and no `is_test_profile` property. The id itself is the marker, so the repo rule "taxonomy and emitter land together" is not triggered.
  - Client queue split: before swapping tokens, the client flushes `ftf.events.queue.v1` so each queued event is sent under the profile that produced it.

## 2. Schema & flag scope

- **New or changed tables/columns:** none. Every row the test profile writes uses existing account-scoped tables, keyed by its own id. Reset is a scoped `DELETE`, not a migration.
- **New feature flag:** `dev.test_profile`.
  - Default `False` in `feature_flags.py` and `false` in `config/features.json`.
  - Mirrored in `backend/tests/fixtures/flags/{release,onboarding-v2,profiles-on}.json`.
  - Graduation criterion: none. It is an operator tool and stays an allow-listed tool.
- **New env var:** `TEST_PROFILE_ACCOUNTS`, a comma-separated list of real working keys (Sleeper user id or `acct_*`).
  - Unset or empty: every `/api/test-profile/*` route returns 404, and `_get_session` refuses any `qa_tp_` token.
  - Rollback without a deploy: unset the variable on Render, or flip the flag off and call `POST /api/feature-flags/reload`.
  - Documented in `docs/config-reference.md`.

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-test-profile.js` plus `npm run test:test-profile`. It pins:
  - The Settings row is gated on the server capability.
  - The banner is mounted at container level while the stash exists.
  - The switch-back and reset handlers are wired.
  - The stash key is persisted, so the chosen profile survives a restart.
  - No request body or URL carries a target user id.
- [x] **Unit tests:** `backend/tests/test_test_profile.py`, one test per invariant in the brief:
  - allow-list and flag inertness;
  - no target id is accepted;
  - a normal sign-up can never mint a `qa_tp_` id;
  - every onboarding gate reads as a new user;
  - the real user's rows are byte-identical afterwards;
  - the alias resolves the real credentials without copying them;
  - platform writes are refused;
  - the guards on surfaces M4/M8/M9/M12/M15/M16;
  - crons skip test profiles;
  - analytics exclusion;
  - a scoped reset.

  Each test also gets a sabotage run: break the code, show the test goes red, restore it, show green.
- [x] **Linking (ESPN/MFL, ruling 2026-11-11):** `backend/tests/test_test_profile_linking.py`.
  - The seams are the identity for real users.
  - An AST guard: every linking writer goes through the write seam.
  - The URL builders read the native id.
  - First run end to end via ESPN and via MFL.
  - The real account's rows are byte-identical.
  - Failure-path parity with a new real user, including #321 wrong account.
  - Reset removes credentials and namespaced leagues.
  - The ESPN/MFL onboarding scan.
- [x] **Sleeper (ruling 2026-11-12):** `backend/tests/test_test_profile_sleeper.py`.
  - The identity accessor is pinned for real sessions.
  - The Sleeper-read sites go through the accessor.
  - The decisive full-onboarding scan (no league-mate/real ids, real rows byte-identical, zero deliveries).
  - Another person's username is refused.
  - A missed re-key is caught at the writer, and `session_input` re-keys everything it hands on.
  - Every outbound chokepoint and platform-write core.
  - Background readers and global learning signals skip the profile.
  - Production threading: the daemon and trade jobs on real threads, ACTOR None, isolation held.
  - A dead test token never mints a real session.
- [x] **Review findings (2026-11-12, design.md §13):** `backend/tests/test_test_profile_review.py` (fence over every request source, database write fence, submit membership, sweeps, structured ids, eviction, reset drain and caches, cross-caller denial, fence cost, ACTOR reset) and `mobile/tests/check-test-profile-swap.js` (every crash point of the device swap).
- [x] **Code-walk proof:** [design.md §9.2](design.md#92-code-walk), §11, §12.
- [x] **Manual TestFlight checklist:** [design.md §9.3](design.md#93-manual-testflight-checklist). This is the only runtime evidence for the stash/restore, the banner, the live platform sign-ins and the re-link prompt.
- `testID`s added: `settings.testing.test-profile`, `test-profile.banner`, `test-profile.banner.back`, `test-profile.banner.reset`. testid-lint passes.

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | New section "Onboarding test profile": `GET /api/test-profile`, `POST /api/test-profile/enter`, `/exit`, `/reset` |
| `living-memory/LLD.md` | coordinator | Owned by the coordinator. Convention: a `qa_tp_` id is a test profile, as a pure function of the id |
| `docs/architecture.md` | updated | New leaf module `backend/test_profile.py` |
| `living-memory/HLD.md` | n/a | No new client or major flow; it is an operator tool |
| `docs/cross-client-invariants.md` | n/a | The mobile client reads the `qa_tp_` prefix only to skip RevenueCat identity; documented in `docs/glossary.md` |
| `docs/glossary.md` | updated | "Test profile" |
| ADR or `DECISIONS.md` entry | coordinator | The namespace design; the 2026-11-11 real-linking ruling and option A; the 2026-11-12 Sleeper ruling |
| `docs/config-reference.md` | updated | `dev.test_profile`, `TEST_PROFILE_ACCOUNTS` |
| `docs/runbook.md` | updated | Enable for an account, switch, reset, turn off |

## 5. Ship gate declaration

- **CI green:** `backend-tests`, `mobile-typecheck` (which includes the `check-*.js` suites) and `maestro-testid-lint`.
- **Evidence recorded:** TEST_LEDGER entry, written by the coordinator.
- **TestFlight verification:** the operator runs the checklist; the outcome is logged.
- **Express lane declared:** no. This is an identity feature with an API surface and a flag, so it is not eligible.

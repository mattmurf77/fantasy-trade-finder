# Feature Scope — P1-3 · Email capture at the Apple bind point (audit A-12)

<!--
Copied from docs/templates/feature-scope.md. Every section is answered or
explicitly WAIVED with a reason. Waivers are surfaced to the operator before
build starts. See the companion plan: plan-p1-3.md.
-->

**Date:** 2026-08-11
**Entry point:** mobile UX audit 2026-08-09 — backlog P1-3, resolution row A-12 (`docs/business/product/2026-08-09-mobile-ux-audit/06-resolutions.md:97`)
**Builder:** planning session on `p1-remediation-2026-08-11` @ `ab9368f` (PLAN ONLY — no code written)
**Operator sign-off on waivers:** **REQUIRED — not yet obtained.** Four waivers below (§1c, §3, and two rows in §4) plus six operator gates in `plan-p1-3.md` § Operator checkpoints.

**Prerequisite:** the P0 remediation branch merges to `main` before any P1 build. Rebase and re-verify line numbers before editing.

---

## 1. Analytics scope

**(c) WAIVED — no new analytics event, because:**

The 2026-07-17 spec (`docs/business/product/2026-07-17-email-capture-spec.md:32`) promised a server-fired `email_captured` event. It was never implemented — verified absent from `backend/analytics_taxonomy.py:105-136` (`SERVER_FIRED_EVENTS`). **This scope deliberately does not add it**, for four reasons:

1. In this lane the capture is a **server-side side effect of signing in**, not a user action. There is no user-facing capture UI in scope, so there is no moment a user chose anything that an event would record.
2. The quantity is already exactly queryable from state, more accurately than from an append-only log: `SELECT count(*), email_source FROM accounts WHERE email_consent_at IS NOT NULL`. Columns verified at `backend/database.py:1369-1375`.
3. A new `SERVER_FIRED_EVENTS` name is **intent-by-default** (`backend/analytics_queries.py:60-65`), entering DAU/WAU/retention unless explicitly added to `NON_INTENT_EVENTS` — an unforced analytics decision for zero added insight.
4. It would collide with three in-flight items in one file: P0-7 (`plan-p0-7.md:241-307` edits `ALLOWED_CLIENT_EVENTS`, `SERVER_FIRED_EVENTS`, `CLIENT_EVENT_PROPS`), P1-10 (Sleeper Connect analytics), and — for the emit site — P0-5, which restructures `server.py:_provider_auth_response`, the only place the event could fire. Import-time asserts at `analytics_taxonomy.py:298-332` mean a mistake here fails app boot, not a test.

**(b) Existing events that cover the adjacent question:** `signup` / `app_open`, fired at `backend/server.py:14718` via `record_event`, answer "did this user authenticate", which is the only funnel step this change touches. No funnel metric moves.

**If the operator overrides (gate 4, Option B)** — the spec-as-written table:

| Event | Properties | Fires when | Client |
|---|---|---|---|
| `email_captured` | `source` (`'apple'` \| `'google'` \| `'user'`) — **never the address itself** | After `find_or_create_account` writes a non-NULL `accounts.email`, and **after** the `users` row exists (`record_event` at `database.py:2592` bumps denorm columns on `users` in the same transaction) | Server (`SERVER_FIRED_EVENTS`) |

Follow-through if elected: `analytics_taxonomy.py` `SERVER_FIRED_EVENTS`; explicit `NON_INTENT_EVENTS` decision in `analytics_queries.py:60`; `find_or_create_account` returns an additive "did we write an email" key; taxonomy/tracking-plan doc updated. `docs/data-dictionary.md` is updated either way (the columns are stored data).

**PII posture (holds in both options):** no address ever enters a prop. `analytics_ingest.py:160-162` denylists prop keys containing `email` and regex-strips address-shaped values; `api_observability.py:143` redacts `email`. That is the safety net, not the design.

## 2. Schema & flag scope

**New/changed tables or columns: none — no DDL.**

`accounts.email`, `accounts.email_source`, `accounts.email_consent_at`, `accounts.email_unsubscribed_at` already exist and are deployed (`backend/database.py:1369-1375`), with additive migration entries at `:1844-1848`. They are NULL in production today.

**But this is still a schema bright line.** The columns begin receiving **plaintext PII** where they previously held NULL — a data-classification change without a structural one. Enumerated explicitly per `CLAUDE.md` § Feature gates:

- **What is stored:** an email address, plaintext, normalized lower/trim (`accounts.py:262-265`), linked to an identifiable account, with an ISO consent stamp.
- **Where it comes from:** the **server-verified identity-token JWT** `email` claim (`server.py:18024-18026` → `accounts.py:302`), not from the client. No mobile change is required or made.
- **Apple "Hide My Email":** private-relay proxies (`@privaterelay.appleid.com`) are stored under the same column with **no distinguishing marker** — `is_private_email` is never read (repo-wide grep: zero hits). Relay-ness is derivable from the address suffix; deliberately **not** modelled as a new `email_source` value or a new column, to avoid schema churn for a stable, self-describing string. Recorded in `DECISIONS.md`. Operational consequence: sending to a relay requires registering the sending domain in Apple Developer → Sign in with Apple for Email Communication (SPF/DKIM); no such domain, sender, or send path exists.
- **Retention:** indefinite while the account exists. No TTL, no reaper.
- **Deletion:** the `accounts` row is **hard-deleted** by `delete_user_data` (`accounts.py:709-714`, resolved account ids at `:692-700`); the address dies with the row. Route `DELETE /api/account` is deliberately un-flagged (App Store 5.1.1(v)). **No code change needed — verified, and pinned by a new test (§3).**
- **Export:** `export_user_data` emits `tables["accounts"]` at `accounts.py:806-830` (outside `_EXPORT_TABLES`), so the address is in the GDPR archive automatically. Route `GET /api/account/export`, flag `account.data_export` = `true`. **Verified — no gap. Pinned by a new test (§3).**
- **Partial removal:** **not possible.** There is no way to delete only the address. `email_unsubscribed_at` (`database.py:1375`) has **no writer** anywhere; no unsubscribe route; no send path to unsubscribe from. This must be disclosed accurately rather than promised away — operator gate 3.
- **Encryption at rest:** none. Plaintext in SQLite on Render, alongside Fernet-encrypted Sleeper tokens. Accepted and disclosed (`web/privacy.html:236-243` already states the beta-service security posture); a separate decision, not this item's.

**New/changed feature flags: none — a default-state change on an existing flag.**

- `auth.email_capture`: `false` → `true` at `config/features.json:58`. Registered at `backend/feature_flags.py:142`. **Flag-surface bright line** (a shipped default flip changes behaviour for every user).
- Also updated: `backend/tests/fixtures/flags/release.json:59` → `true`; `docs/config-reference.md:155`; the stale comment at `feature_flags.py:138-141` (leaving it would reproduce **A-33**, the comment-lies-about-runtime failure the audit already caught).
- **No new flag is proposed, and none is justified.** No bright line demands one: there is no new user-visible surface to gate, no rollout cohort, and the existing flag is already the kill switch.
- **Graduation criterion:** already graduated by this flip. Rollback = set `false` in `config/features.json` and redeploy; already-stored addresses are unaffected by the flag (it gates writes, not reads) and would need a separate deliberate purge.
- **Ship-the-knob / deploy-free rollback:** `FTF_FLAGS` (`feature_flags.py:666-667`) and `POST /api/feature-flags/reload` (`server.py:17336`) can flip this without a deploy. **This is explicitly prohibited for this flag**, in either direction, because it decouples the flag from the privacy policy — the exact accident the pairing exists to prevent. The deploy-free lever is deliberately given up here; recorded in `DECISIONS.md`.

**New env vars / `model_config` keys: none.**

**Public legal text (not covered by the template's headings, enumerated here):** `web/privacy.html` §1 (`:90-99`), §2 (`:172`), §5 (`:198-208`), §6 (`:210-234`), §9 date. Served at `/privacy` (`server.py:8058-8061`) — the App Store Connect privacy URL. **Judgment/legal bright line — operator gate 2.** The file header (`:1-8`) records that the document has never had legal review.

**App Store privacy label:** requires **Contact Info → Email Address** (linked to user; App Functionality + Developer Communications) at the next submission. Submission-time obligation, not a code change — operator gate 5; runbook checklist entry.

## 3. Test scope (mobile test platform)

**WAIVED — no Maestro delta, because there is no mobile diff.**

- Nothing in the change list touches `mobile/src`. The three Apple sign-in call sites (`SignInScreen.tsx:136-148`, `SettingsScreen.tsx:354-361`, `AppleSaveMomentSheet.tsx:48-55`) already request `AppleAuthenticationScope.EMAIL` and forward only `cred.identityToken`; the address is read server-side from the verified JWT. Unchanged before and after the flip.
- **Checked for the "existing flow asserts the bug" trap** — every Maestro file mentioning Apple, sign-in, or privacy was read: `flows/smoke/11-apple-entitlement.yaml` (entitlement sensor; cannot reach a real Apple consent sheet, so never exercises token claims), `flows/s1-spike-signin-ids.yaml` (backend-less testID spike), `capture/signin.yaml`, `capture/onboarding-signin@fresh.yaml`. **None asserts privacy copy, and none asserts the absence of an email field.** No flow is pinning the behaviour being changed.
- **Waiver expiry:** the moment the Settings/onboarding capture field ships (explicitly out of scope, owned by the onboarding-conversion stream), a new flow covering enter → save → persists-across-relaunch becomes mandatory.

**`testID`s added/renamed: none.** `mobile/scripts/testid-lint.sh` unaffected.

**Capture delta: none** — no screen's visuals change. `mobile/scripts/screen-freshness.sh` should flag nothing; if it does, something outside this scope moved.

**Smoke-suite impact:** none of the 11 smoke flows cross this surface in a way the change affects. `smoke/11-apple-entitlement.yaml` is the only one touching Apple sign-in and it terminates at the native sheet boundary. Expected: still green, unchanged.

**Backend: pytest files added/updated —**

| File | Tests |
|---|---|
| `backend/tests/test_email_capture.py` (existing, 4 tests) | Must pass **unchanged**. They monkeypatch `_email_capture_enabled` (`:41`), so they are independent of the real flag value; movement here means something other than the flag moved. |
| `backend/tests/test_email_capture.py` (new) | `test_release_flag_and_privacy_policy_ship_together` — reads `config/features.json`; if `auth.email_capture` is true, assert `web/privacy.html` contains neither `"We never store your email"` nor `"No email addresses"`. **The durable enforcement of the pairing** and the single most valuable artifact this item produces. |
| `backend/tests/test_email_capture.py` (new) | `test_flag_default_is_on_in_release_fixture` — pins `fixtures/flags/release.json:59`. |
| `backend/tests/test_email_capture.py` (new) | `test_delete_account_removes_email` — real in-memory engine (pattern at `:22-31`); create with email, `delete_user_data`, assert the row is gone. Pins the retention promise the policy will now make. |
| `backend/tests/test_email_capture.py` (new) | `test_export_includes_account_email` — assert `export_user_data(...)["tables"]["accounts"][0]["email"]`. Pins `accounts.py:806-830` against a future refactor into `_EXPORT_TABLES`. |
| Full suite | `pytest backend/tests/` — the flag now resolves true in any test that does not monkeypatch it; `test_accounts.py` in particular. |

**Manual verification (in `plan-p1-3.md` § Test plan):** gate-0 repeat-auth probe; post-flip row inspection; "Hide My Email" path; `/privacy` full read-through for internal contradictions; Sleeper-username path unaffected.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | **n/a** | No route added, renamed, removed, or contract-changed. `GET /api/feature-flags` (`server.py:17270`) returns a different *value* for an existing key; the response is an undocumented-per-key flag map. No client reads `auth.email_capture` (grep of `mobile/src` + `web/`: zero hits). |
| `living-memory/LLD.md` | **n/a** | No schema/route/invariant *convention* shift. The convention — flag-gated PII, consent stamped at capture, hash retained alongside plaintext — was established by the 2026-07-17 spec and is unchanged; only the flag's value moves. |
| `docs/architecture.md` | **n/a** | No module wiring or data-flow change. Same call graph (`server._provider_auth_response` → `accounts.find_or_create_account`), same tables, same clients. |
| `living-memory/HLD.md` | **n/a** | No new module, client, or major flow. |
| `docs/cross-client-invariants.md` | **n/a** | No shared constant, enum, colour, or threshold consumed by multiple clients. `email_source`'s `'apple'`/`'user'` values are backend-only; no client reads them. |
| `docs/glossary.md` | **n/a** | No new domain term. "Private relay" is Apple's vocabulary, defined inline in the policy and the data dictionary. |
| ADR or `DECISIONS.md` entry | **Updated — `DECISIONS.md`, not a new ADR** | Three non-obvious choices: (a) flag + policy in one commit, `FTF_FLAGS` prohibited for this flag in both directions; (b) relay-ness derived from the `@privaterelay.appleid.com` suffix rather than a new `email_source` value or an `is_private_email` column; (c) `email_captured` deferred to the capture-UI build. No architectural shift → `DECISIONS.md`, next free `D-0NN`. |

**Additional docs required by `docs/CLAUDE.md` triggers beyond the template's rows:**

| Doc | Updated? | Section / reason |
|---|---|---|
| `docs/data-dictionary.md` | **Updated** | `accounts` rows `:814-817` — drop "dark behind the flag" / "NULL until the flag + capture UI + privacy-policy flip ship together"; state live behaviour, the relay-address note, and that `email_unsubscribed_at` has no writer. |
| `docs/config-reference.md` | **Updated** | `auth.email_capture` row `:155` — ON, what it gates, pairing shipped as fact rather than obligation, `FTF_FLAGS` prohibition, Settings UI still unbuilt. |
| `docs/runbook.md` | **Updated** | `:355` currently instructs "keep it that way or amend the policy" — now stale. Record the amendment; add the App Store Connect label action to the pre-submission checklist (`docs/plans/analytics-platform/prd.md:239` records "wrong privacy label = rejection" as a prior known risk). |
| `docs/business/product/2026-07-17-email-capture-spec.md` | **Updated** | Dated status block: shipped (schema, Apple path, flag, policy) vs deferred (Settings UI, `email_captured`, unsubscribe, send tooling), plus the gate-0 repeat-auth finding. |
| `web/privacy.html` | **Updated** | §1, §2, §5, §6, §9 date, header comment. **Operator/legal gate 2 — a build agent must not merge final policy text unreviewed.** |
| `docs/design/design-system.md` / `components.md` | **n/a** | `privacy.html` is a self-contained static page with inline Chalkline tokens (`:20-24`); the edit is prose inside existing `<li>` elements. No component or token change. |
| `living-memory/CHANGELOG.md` | **Updated** | Dated H2 at ship. |
| `living-memory/TEST_LEDGER.md` | **Updated** | Tier-4 declaration + pytest result. |
| `living-memory/GOTCHAS.md` | **Conditional** | Add an entry only if the gate-0 probe shows the Apple JWT behaves differently from the documented expectation — that is exactly a >30-minute quirk a future session would re-derive. |

## 5. Ship gate declaration

**Simulator-gate tier: 4** — "Backend-only, web-only, docs-only" per the matrix at `docs/runbook.md:98-99`.

Justification: the change set is `config/features.json`, `web/privacy.html`, `backend/tests/**`, `backend/tests/fixtures/flags/release.json`, and docs. **Zero `mobile/src` files.** No screen, navigation, state, or logic change in the app; no backend route consumed by mobile is added or altered. `githooks/pre-push` only blocks pushes that include `mobile/src` changes, so it will not fire — the tier-4 declaration is therefore an honesty obligation, not an enforced one, and is logged for that reason.

**Required before merge:** CI green — `pytest backend/tests/` (including the four new tests in §3) and `tsc --noEmit` (unchanged, no TS touched).

**Evidence:** `living-memory/TEST_LEDGER.md` entry naming the tier, the rationale, the pytest result, and the SHA. **No `qa/sim-runs/last-sim-run.json` write** — tier 4 requires no sim run; writing a sim-run record for a run that did not happen would be worse than writing nothing.

**Operator deviation from the matrix:** none proposed. If the operator wants belt-and-braces, the cheapest meaningful addition is `smoke/11-apple-entitlement.yaml` alone (~2 min) to confirm the Apple sign-in surface is untouched — worth it only if the merge lands on top of P0-5, which *does* restructure `server.py:_provider_auth_response`.

**Express lane:** **not eligible.** This item crosses four bright lines — schema/data-classification (plaintext PII into previously-NULL columns), feature-flag surface (shipped default flip), public legal text, and conditionally analytics events. Per `CLAUDE.md` § Feature gates, agents never self-select express, and if the operator declares express on a bright-line change it must be surfaced and a confirming yes obtained first. Stating that here so it does not have to be re-litigated at build time.

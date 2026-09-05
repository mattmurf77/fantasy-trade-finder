# Security hardening review — 2026-09-04

The five findings are addressed, with a second review that found and fixed additional client-session and account-deletion races. **Deployed on 2026-09-05 via PR #279.** Render is live, iOS 1.16.16 (145) built and submitted to TestFlight, and extension 0.1.1 is published. See [deployment evidence](deployment.md). Historical production cleanup and physical-device QA remain outstanding; no live penetration test was performed.

Branch: `codex/security-data-hardening-20260904`, based on freshly fetched `origin/main` at `606e512c`. Worktree: `/Users/teresadickens/Documents/Claude/Projects/Fantasy Trade Finder/staged-work/security-data-hardening-20260904`. The original checkout's existing edits were preserved.

## Findings and implementation

| Concern | Local remediation | Evidence anchors |
|---|---|---|
| Username discovery exposed private data without proof of ownership | Private reads, writes, export and deletion require a verified current session. Only explicitly marked synthetic demos receive the narrow exemption. Provider sign-in cannot adopt a claimed Sleeper identity without live matching proof. | `server._verified_read_denial`, `_verified_write_denial`, `_account_data_gates`, `_provider_auth_response`, `link_sleeper_source` |
| Client-controlled initialization could select another identity or poison membership | Initialization requires the existing verified identity, resolves live Sleeper ownership/co-ownership or authorized imported snapshots, and ignores untrusted roster/profile fields. | `session_input.resolve_session_input`, `server.session_init` |
| Authentication bearers appeared in analytics | Both persistence paths use a domain-separated analytics identifier. An explicit, dry-run-first maintenance tool scrubs historical values and revokes precisely matching durable sessions transactionally. | `database.analytics_session_id`, `scripts/remediate_analytics_tokens.py` |
| Deletion missed private data and allowed concurrent work to recreate it | Alias-aware transactional deletion covers private tables, credentials and sessions. Work admissions drain writes, invalidate queued work and delayed provider proofs, and prevent stale session restoration. Feedback text is scrubbed; export v2 covers the expanded manifest while excluding secrets. | `accounts.deletion_scope`, `delete_user_data`, `export_user_data`, `user_data_lifecycle` |
| Analytics events could inject or duplicate recommendation outcomes | Only validated, newly committed event IDs trigger outcomes. Actor and impression ownership, age, value and volume bounds apply; database checks protect the write itself and duplicate races trigger one callback. | `analytics_ingest.ingest_request`, `_insert_events_ignore`, `database.save_deck_outcome` |

## Independent review

Five Astra medium subagents handled the original findings. The coordinating agent inspected their changes, traced authorization and persistence boundaries, integrated their fixtures, and ran the combined checks. Follow-up review caught stale mobile init/link responses restoring a previous session, proof callbacks acting after account changes or unmount, and a delayed provider sign-in recreating an account after its identity link was deleted. These were reproduced and fixed. Deletion now also carries the original work revision into counterparty writes.

Web/extension verification requires a trusted gesture, an exact trusted Sleeper origin and matching live proof. Only a verified Fleeced bearer reaches the production first-party page; raw Sleeper proof never reaches web or extension storage. Localhost was removed from the bridge allowlist during review. Private caches revalidate before display and recover from revocation. Mobile uses a shared incognito capture and waits for accepted initialization before opening the league.

## Final validation

Release integration with main #277/#278 subsequently passed **5,001 backend tests / 1 skip in CI**, all mobile/web CI jobs, and **57 PostgreSQL checks**. Build 145, TestFlight submission and production smoke checks completed; [release evidence](deployment.md) supersedes the pre-integration counts below.

- Full backend suite on Python **3.12.14: 4,707 passed, 1 skipped** in 679.14 seconds, including calibration tests. Scratch SQLite and blocked upstream requests. The configured deployment uses Python 3.12.3; this validates the same minor version, not that exact patch. The earlier 4,698-pass Python 3.14 run is historical evidence.
- Actual PostgreSQL **18.3: 54 passed** in 17.49 seconds, including maintenance apply/rollback/idempotence, deletion and restoration races, alias export, outcome caps and simultaneous insert conflicts. Disposable local schemas only.
- Mobile: **91/91 guards**, full TypeScript and testID lint passed. iOS Hermes JavaScript export succeeded. This does not establish native runtime behavior.
- Web: **23 isolated auth checks**, **180/180 structural checks**, and the **actual loaded MV3 extension in Chromium** passed. Runtime used synthetic upstream responses and a disposable browser profile. Narrow-viewport help was checked and visually inspected.
- Regression sensitivity: disabling lifecycle invalidation in memory made all three targeted stale-work/deletion regressions fail at their expected assertions. Mobile session-switch and unmount cases failed before their fixes. No sabotage remains in source.

Reproduction: [validation tools](validation-tools/README.md). Details: [mobile evidence](mobile-evidence.md), [browser evidence](browser-evidence.md), [validation record](validation.txt).

## Remaining release and data concerns

1. **Native validation is outstanding.** No physical iPhone was available. Build 145 was submitted successfully, but real login, WebView isolation, Keychain and navigation still need the concrete mobile checklist. No simulator was used under D-056.
2. **Users need the matching client update.** Web Sleeper requires the published extension 0.1.1 and a signed-in Sleeper tab. Browser ESPN/MFL entry directs users to mobile verification. Legacy username-only sessions lose private access under strict enforcement.
3. **Historical exposure needs an operator-reviewed production operation.** Local code prevents new token leakage; it does not erase prior production analytics, revoke live sessions, or repair previously contaminated imported membership. Follow the runbook for cleanup, worker restart and membership resync.
4. **Deletion fencing assumes one worker.** This matches the checked-in deployment. Multiple workers, independent writers or durable job queues require distributed fencing first. A drain timeout leaves rows intact and requires retry.
5. **Deletion is not universal erasure of public/counterparty records.** Shared league/draft/transaction data, published rankings and records owned by other managers have documented retention/anonymization rules. Export intentionally excludes authentication secrets, push tokens and raw billing payloads.

## Memory format audit

Memory and reference docs record this branch's current state. The [scoped format audit](memory-audit.md) reports pre-existing header conventions and missing historical links; these were not rewritten as part of security remediation. No claim is made that the entire historical memory corpus is format-clean.

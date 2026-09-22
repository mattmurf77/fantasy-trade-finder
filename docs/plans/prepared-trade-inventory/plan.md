# Persistent prepared trade offers

September 22, 2026. Owner request: write the plan first, then build and deploy; prepare offers for every existing app user's linked team. This plan precedes implementation. Existing model and offer-count rules are unchanged.

## Outcome and boundaries

Run a silent initial preparation sweep, retain the full resulting inventory across server restarts, and adopt a still-valid inventory through ordinary Find a Trade. Prioritize a first durable, actionable batch of 20–30 cards; keep every remaining eligible offer available. The product goal remains first actionable tile within three seconds, measured separately from background construction and full completion. Deployment or a cache hit is not proof of the device KPI.

Scope is existing users' connected current-season leagues, including co-owned teams and account-only users of supported platforms. It is not every imported league opponent, a new league-import campaign, notifications, automated likes/trade proposals, model changes, or a purchase of additional infrastructure. Default discovery requests are prepared; asset-pinned, partner-pinned and custom intent searches retain their existing paths. A prepared request never impersonates a human session.

## Current production baseline

Fresh main is ff122752. September22 production readback confirmed Bilateral revision2 exclusively selected, with no card/group cap. The current in-memory cache has a30-minute admission TTL and disappears on restart. App/league init already starts preparation. Existing weekly replenishment is neither silent nor exhaustive: it selects30-day activity and writes inbox/push notifications. Do not trigger daily-tick to accomplish this task. Latest local revision2 first-durable/full timings are15.127/20.304 seconds; these are not production percentiles.

## Architecture

1. Resolve a frozen, auditable cohort of real app-user/team bindings. Refresh or verify the supported source snapshot without modifying user preferences or sending messages.
2. A bounded background worker takes one target at a time. It joins compatible work, leaves interactive requests intact, and defers new preparation while interactive work is running. It is cooperative, not a claim of hard CPU preemption.
3. Run the existing full constructor and final policies with a distinct preparation mode. Capture the exact ordered public cards, allowlisted runtime card metadata, valuation/diagnostic evidence and source dependencies in a prepared artifact. Do not cap the offer universe.
4. Atomically publish that artifact to a durable SQL-backed inventory with an explicit expiry, source fingerprint, model/policy identity and participant index. A failed, interrupted, invalidated or partially written artifact is never ready.
5. Ordinary session-init/Find requests resolve their exact current scope and inputs, then validate a ready artifact. On a match, commit original exact-offer evidence for the initial batch and publish only those durable cards. Publish the remainder through the existing cumulative batch contract. On any mismatch, use fresh generation; never relax fairness or silently substitute a different search.
6. Refresh through a dedicated silent admin/cron entry point and the existing scheduler integration, not the unrelated notification sweep. No Codex recurring automation or additional billable service is required.

Preparation and adoption are separate states. Prepared offers are not shown offers. Durable diagnostics alone are not human exposure, interest or acceptance.

## Cohort and identity

- Enumerate canonical working-user identities from real account/signup/verification records; retain account-only identities and report unverified/ineligible users rather than creating accounts for opponents.
- Bind users to existing linked leagues using authoritative owner/co-owner evidence or an explicit imported-platform binding. `leagues.user_id` is an importer, not the complete membership map; `league_members` includes non-app opponents.
- For Sleeper, fetch a known league's current roster/metadata once per sweep and resolve both owners and co-owners with the shared predicate. Do not discover/import unrelated leagues. Two co-owner app accounts share a roster but have separate rankings and inventories.
- For ESPN/MFL/Fleaflicker, use existing read adapters and configured credentials. Validate the actual imported team binding. Missing/expired credentials, ambiguous ownership, unsupported format or missing rosters are explicit skip/error reasons; no reconnect messages are sent.
- Account identity selects rankings/preferences and authorizes access. Canonical league identity selects the roster and excludes self-trades. Never use another owner's rankings to fill an unresolved binding.
- Do not register bearer tokens, restore token hashes, update login timestamps, or use the public session-init route merely to prepare inventory.

## Persistent contract and freshness

Use additive SQLAlchemy Core tables, SQLite/PostgreSQL parity, no new external cache dependency. Store current inventory records, resumable sweep/target state and any necessary verified binding metadata. Exact table/function interfaces are in the implementation specifications and must be reviewed together before wiring.

Inventory scope includes account, league, canonical team, scoring format, exact fairness/default request options, schema/model/presentation/safety version and dependency fingerprint. Payload is versioned JSON, optionally compressed using a fixed safe codec; never pickle runtime services or accept executable objects. Bound payload bytes and fail visibly rather than truncate offers.

The dependency receipt must cover all consumed sources: current owned/opposing rosters and picks; both available boards and ranking provenance; outlook/needs/tags; league scoring/lineup context; market/player inputs including current time-sensitive state; generator/configuration/flags; and selection settings. Capture before/after generation and validate again before adoption. Do not promote the existing incomplete in-process request signature into proof of persistent freshness. Failure to compute a dependency or conflicting captures is a cache miss/error, not a match.

Default durable retention is24 hours, subject to exact dependency/source checks and original per-card expiry. Retention is not permission to serve stale data. Adopted in-process jobs retain the existing30-minute bound, limited further by artifact/card expiry and current revocation. Refresh invalid/missing targets and those approaching expiry; completed empty inventories are cached as empty, not regenerated in a loop.

Client-local fairness is not silently invented: use explicitly persisted observed settings or a clearly identified native default when none exists. Exact differing client requests must miss that inventory. Source refresh failures preserve existing historical data but cannot certify it current. Provider/source staleness is independently visible.

Current dispositions and active interest are projected at adoption/read time. Keep immutable liked/matched terms unchanged. Account deletion must remove artifacts that contain that account's data, including counterparty contributions, and fence in-flight writes. Re-linking or roster-binding changes revoke affected prepared inventory. Persistent validation must still work after all process-local epoch tokens are gone.

## Evidence and actionability

- Store the existing logger's assembled valuation, candidate-set and source-link dependencies as preparation data, without minting shown/viewed/like events or legacy shown-impression rows.
- Adoption uses existing transactional evidence writers, preserves original trade identities/order/valuations, and commits each batch before exposing it. Retrying adoption cannot create inconsistent duplicate evidence.
- Restore allowlisted server-side card metadata needed for decisions, including lane/fit and original timestamps. Client-echo reconstruction alone is not sufficient for behavioral parity after restart.
- No prepared work may update last-active/last-login, activate first-session milestones, notify users, send trades, or train personal rankings. Operational counts live in preparation status; real user actions keep existing analytics.
- First-batch and full-adoption timings are operational measurements. Existing app-open timing is not re-labeled as tap-to-first-tile. A physical-device checklist remains required for the three-second product KPI.

## Workload controls and ongoing refresh

One background target runs at a time; no unbounded thread fan-out. Snapshot the cohort denominator, checkpoint progress durably, use leased claims/retry-safe keys, and recover unfinished targets after restart. Re-check deletion/binding/inputs before durable publication. Preserve active user jobs and defer background work at admission and safe phase boundaries.

The admin start response is asynchronous and includes a sweep ID; read-only status reports eligible, ready/reused, generated-ready, empty, deferred, unsupported/missing binding, source/auth failures, stale/superseded and errors. Status includes fresh-ready coverage, not just total ever-completed. An all-user sweep is complete only when every target has an honest outcome; skips are not successes. Continue unresolved transient work under bounded retry, without notification spam.

Use existing scheduled infrastructure for periodic silent refresh after source readiness; do not claim overnight benefit from process-local cache alone. Add an audited, default-dark rollout control and an immediate stop/rollback control. Preserve every existing model arm, model knob, saved preference and offer limit.

## Work packages and ownership

1. **Parent:** plan/scope/specifications first; server lifecycle, preparation/adoption seams, auth/admin routes, integration, documentation, deployment and production verification.
2. **Storage lane:** durable inventory/lease APIs, safe payload codec and runtime-card schema, dependency hashing primitives, transactional tests and account-deletion integration. No server.py edits.
3. **Cohort lane:** verified target discovery/source adapters, coverage classifications and side-effect-free headless inputs, with identity/platform tests. No server.py edits.
4. **Publication lane:** preparation/evidence bundle contract and restore helpers/tests, adversarial review of server adoption and analytics effects. No concurrent server.py edits.

Agents read the plan/specification before coding. Review their diffs centrally; no agent deploys or writes production. Independent cross-review must test identity, stale-source, concurrency, telemetry and action parity failures—not merely happy paths.

## Acceptance and release sequence

1. Plan and scope saved before implementation. Write tests for restart reuse, fingerprint mismatch, missing/changed picks, board/outlook/market/model changes, fairness mismatch, active interactive job preservation, account deletion, co-owner/ESPN/account-only bindings, expiry, valid empty result and read-only status.
2. Prove capture causes zero shown/view/interest/activity/notification writes. Prove adoption commits before publication, preserves full order/offer count and decision metadata, rejects partial/corrupt artifacts, and is retry-safe.
3. Run focused tests including negative controls, full backend suite and current hosted CI on the exact release head. No simulator/Maestro. Confirm additive schema bootstrap and rollback behavior. Benchmark fresh/prepared first-durable and full completion separately; no unmeasured three-second claim.
4. Merge reviewed code/documentation only after green CI; attach the PR to this task. Deploy the exact tested main commit to the established Render service (autodeploy was off). No mobile change is intended; TestFlight is necessary only if that changes.
5. Read back live rollout state, dry-run the production cohort, run a small sequential canary, verify no notification/activity side effects and successful current-scope adoption. Then run the authorized initial all-user linked-team sweep. Do not silently treat skipped/inaccessible teams as cached.
6. Report actual coverage, cache retention/freshness behavior, observed timings, errors and rollback. A device KPI or mutual-acceptance result needs separate evidence.

## Rollback

Disable preparation/adoption through the audited rollout control, stop new background claims, and fall back to existing fresh generation. Do not alter model arms or delete historic user decisions/impressions. Incompatible prepared records are never adopted; expiry/pruning and account deletion handle their lifecycle. If needed, redeploy the prior exact commit. Do not apply the legacy checkout or unrelated unpushed evaluation-framework changes.

## Canonical documentation

Update API reference, data dictionary, architecture, config reference, operations runbook and account-deletion contract as affected. The initiative holds tests, review findings, rollout/coverage evidence and device checklist. Preserve the older dirty canonical/legacy checkouts; only publish documentation there through scoped writes.

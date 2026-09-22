# Implementation specifications

Read [plan](plan.md) and [scope](scope.md) before coding. Shared worktree: `/private/tmp/fleeced-prepared-offers-20260922.uTMpm2`, baseline ff122752. No agent commits, production access, deployment, notification, app simulation or unrelated cleanup. Main agent alone edits server.py and shared canonical references. Each lane owns its named files/tests; coordinate interface changes explicitly.

## A — durable store and lifecycle

Own `backend/prepared_trade_store.py`, additions to `backend/database.py` and `backend/accounts.py`, `backend/tests/test_prepared_trade_store.py`. Parent will request any model-config/schema additions through you to avoid conflicts.

Implement an additive SQLAlchemy-Core store for ready ordered inventories and sweep/target progress. Keep metadata/table registration in database.py so existing init_db creates them. No app/server imports. Engine is read at call time, tests isolated SQLite; SQL operations must work on PostgreSQL. Use transactions, bounded insert chunks, strict JSON and optional stdlib compression with bounded decompression. No pickle. Empty inventory is distinct from absent/error.

Inventory scope uses owning working-user, league, canonical league-user, format and request key. Save a detached payload (public/runtime card records plus prepared evidence bundle), source/dependency receipt/hash, model/runtime identity, participants, creation and original expiry. Atomic replacement/CAS prevents an expired lease or stale worker overwriting a later inventory; preserve prior record on failed writes. Load only exact scope+receipt matches and unexpired supported schema, verifying checksum/count. Never renew expiry on read. Lease APIs must make sweep start idempotent, permit one current background claim, and recover expired/incomplete claims after restart; return counters without public user identities.

Provide typed, documented functions with explicit arguments for save/load/invalidate/prune and create/claim/complete/status sweep targets; publish signatures to parent before wiring. Pure dependency hash rejects nonfinite/unsupported values and preserves semantic array order. Parent builds actual dependency snapshots; no claim a hash alone establishes source freshness.

Account deletion/export: prepared records contain private owner/counterparty data, so index all consumed participants. Delete inventories involving any resolved deleted alias, and pending target bindings, inside existing lifecycle transaction; protect against late writes with account-work leases plus row-existence/transaction fencing. Do not create user rows. Add schema/deletion tests, checksum/tamper/partial transaction/empty/expiry/restart/lease race tests. Existing contract requires ready inventory only after durable capture succeeds, but preparation does not create shown impression rows; payload is prepared evidence, adoption publishes separately.

## B — real-user/team cohort and quiet source resolution

Own `backend/prepared_trade_cohort.py`, `backend/tests/test_prepared_trade_cohort.py`; no server/database/accounts edits. Call A's API only after agreement; otherwise keep cohort results plain data.

Enumerate actual existing app identities and connected leagues, not imported opponents. Include verified legacy users and account-only platform users. Resolve Sleeper owner/co-owner identity against fresh known-league roster data with existing shared predicate. Imported supported platforms must bind an actual app-user row to the correct team using authoritative retained mapping and existing quiet read adapters; no guessed ownership or shared importer-only attribution. Do not import new unrelated leagues. Return targets and complete coverage/skip reasons, including unknown/unverified bindings rather than hiding them.

Proposed result `discover_targets(...) -> {targets:[...], coverage:[...], counts:{...}}`; each target carries account user_id, league_id, canonical league_user_id, platform, format, resolved own/opposing rosters, source-read timestamp/binding evidence, and declared input limitations. Inject provider readers/clocks for hermetic tests and deduplicate source reads per league. Re-resolve at claim/adoption boundaries as needed; server integration decides persistence. Exact final signatures coordinated with parent.

Never mint/register bearer sessions, call public session-init, update last-active/login, upsert opponent users, modify rankings/preferences, create notifications or call daily-tick. Credentials remain in existing secure adapters, never payload/status. Distinguish provider failure from valid empty response. If a source cannot be refreshed/verified, explicit skip rather than false readiness.

Tests: sole owner; two app co-owners→separate personal targets and one canonical team; account-only ESPN/MFL/Fleaflicker; non-app synthetic opponent exclusions; deleted/unverified actor; ambiguous roster ownership; source/auth failures silent; valid empty vs failed read; all-team coverage independent of30-day activity. Parent owns side-effect-free ranking service/headless execution assembly.

## C — prepared evidence and runtime-card fidelity

Own `backend/prepared_trade_payload.py`, `backend/tests/test_prepared_trade_payload.py`. Review parent server integration afterward; no concurrent server edits.

Define a strict, versioned JSON bundle for the existing impression logger's two sinks: candidate-set rows and compacted impression-row/snapshot batches. Preserve all diagnostics, source-like links, valuations and original exact trade identities. Preparation captures this bundle only; adoption reuses existing transaction writers and stamps actual serve-time fields at publication, not at preparation. Avoid re-evaluating/repricing proof evidence on restore. Tell parent the exact callback signatures needed in `_log_deck_signal_impressions`.

Provide safe capture/restore of explicit TradeCard runtime fields required by decisions and pending-card filters, plus existing ordered public snapshots. Preserve original IDs/created_at/expires_at, lane_shift, aggression/lane/fit attribution, significance/owner/private source bindings required by server consumers. Do not deserialize arbitrary attrs or use pickle; reject unknown schema/corruption/inconsistent public/runtime terms/identity. Model proofs require an explicit existing parser or validated immutable record, not arbitrary object resurrection. Parent supplies current player map/service and validates freshness before restoring.

Batch adoption needs first30 then later100 rows, stable order, commit-before-exposure, idempotent original identity linkage and no new views/likes/activity. Design helper output to fit existing `save_deck_impressions` snapshot arguments and candidate-set writer. Verify candidate/snapshot dependencies before calling save. Tests must demonstrate roundtrip and swipe-weight/metadata parity, malformed/runtime-field injection rejection, batch slicing/order and failure-with-no-exposure. Surface unavoidable unsupported fields early rather than silently drop behavior.

## Parent integration and release

Build exact current-input receipts for the audited organic Bilateral pipeline; unsupported modes fail to ordinary generation. Separate background capture from adoption and user events; persist no fake shown rows during preparation. Resolve saved/default fairness explicitly. Add authenticated asynchronous admin start/status/stop plus isolated scheduled refresh; default-dark audited control, one background job, interactive priority. Keep flags/model settings otherwise unchanged. Full-source and dependency race checks surround capture/persistence/adoption/read. Validate provider state at admission, account lifecycle, original card expiry and dispositions. No candidate/offer cap.

Run focused/full/hosted verification and cross-review. Publish canonical docs, merge/attachPR/deploy exact commit, read back rollout, canary, then initial full cohort with honest coverage. Unreachable teams remain reported, not silently cached or messaged.

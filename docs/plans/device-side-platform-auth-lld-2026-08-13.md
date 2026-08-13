# LLD: Device-Held Platform Credentials — Release 1 (Sleeper)

> **Status:** dual-agent candidate v1, entering cross-review.
> **Base commit:** `origin/main` @ `3b64a44`. Every `path:line` was read at that commit.
> **Authoritative inputs:** [PRD](device-side-platform-auth-prd-2026-08-12.md) incl. amendments A1/A2/A3; [HLD decisions](device-side-platform-auth-hld-decisions-2026-08-13.md) D1–D5 + blocking fixes 1–5. The older HLD on `design/device-side-platform-auth` is superseded.
> Neither the PRD nor the HLD decisions are relitigated here. Where the **code contradicts** an HLD instruction, §1.5 says so and proposes the minimum correction.

---

## 1. Scope & Reference

### 1.1 In scope — release 1, Sleeper only

| Deliverable | Home |
|---|---|
| `POST /api/platform/lease`, `POST /api/platform/outcome` | `backend/platform_lease.py` (new), routed from `backend/server.py` |
| `platform_links`, `platform_leases`, `platform_lease_reports` | `backend/database.py` |
| Device transport module + compiled guards | `mobile/src/transport/platformTransport.ts` (new) |
| GraphQL document guard | `mobile/src/transport/gqlGuard.ts` (new, **import-free**) |
| Credential vault (one slot, subsumes `sleeper.link.jwt`) | `mobile/src/transport/credentialVault.ts` (new) |
| `POST`/`GET`/`DELETE /api/sleeper/link` contract changes | `backend/server.py:12393-12521` |
| `request_digest` + the in-flight register | `platform_leases` (no separate store) |
| FAAB object-literal fix (sequenced **first**) | `backend/sleeper_write.py:267` |
| Sentry scrub (`beforeSend`/`beforeBreadcrumb`/`tracePropagationTargets`) | `mobile/src/observability/sentry.ts` |

### 1.2 Explicitly out of scope

ESPN and MFL transports (release 2 / HLD D5 — MFL login is its own device-built call, not the lease path). **Public and shared reads stay on Render permanently** and are not in the device compiled set — `trade_block_service.fetch_league_players` (`backend/trade_block_service.py:65-96`) is the named example. Deletion of `sleeper_credentials` rows (A3 retains the server path as a recovery capability). `expo-updates`.

### 1.3 Invariants inherited, not relitigated

| | |
|---|---|
| **I1** | The device never parses a platform response. It forwards bytes; the server interprets. |
| **I2** | No device-side TTL enforcement. `/outcome` accepts late reports. |
| **I3** | `/outcome` is idempotent by `lease_id`. |
| **I4** | A lease carrying an `authorization` header is refused by the device. |
| **I5** | `user_id` equality check before the credential is attached. |
| **I6** | `(query, __typename)` is not in the device set. |
| **I7** | No signing. |
| **I8** | Capability negotiation + typed `426 upgrade_required`. |
| **I9** | `sleeper_credentials` retained; the token write is gated, not deleted. |

**Metric shorthand used throughout**, from the PRD's metrics table (PRD:78-84) — spelled out here because the PRD *also* overloads M1–M4 as migration milestones at PRD:100-103, and A2 withdrew that phasing:

| | |
|---|---|
| **M1** | count of `sleeper_credentials` rows among **users who first link after S7** — target zero. The denominator matters: a user who linked earlier keeps their pre-existing row (I9 and §1.2 retain it, and nothing deletes it), so counting them makes G1's headline number look like a regression it is not. |
| **M4** | device guard refusals — **any non-zero value is an incident**, not a metric |
| **M8** | leases issued vs outcomes reported; divergence means devices are going silent |

M5 and M6 do not exist in the PRD table and are not referenced here.

### 1.4 Load-bearing existing code

| Fact | Evidence |
|---|---|
| Sleeper wants the **raw** JWT in `authorization`, no `Bearer` | `backend/sleeper_write.py:288-293` |
| Single GraphQL endpoint, one op per call | `backend/sleeper_write.py:39` |
| `_PROPOSE_TRADE_TEMPLATE` puts **variable definitions before the selection set** | `backend/sleeper_write.py:203-211` |
| `league_id`, `draft_picks`, `waiver_budget` are inlined into the query **text** | `backend/sleeper_write.py:263-268` |
| `waiver_budget` uses `json.dumps` ⇒ quoted keys ⇒ **invalid GraphQL object literal** | `backend/sleeper_write.py:267` |
| `ftf_token_probe`'s label ≠ its root field (`__typename`) | `backend/sleeper_write.py:189-192` |
| `POST /api/sleeper/link` is the verification oracle and stores before stamping | `backend/server.py:12466-12521` |
| `POST /api/trades/propose` reads `get_sleeper_credential` ⇒ A3's recovery path needs the row | `backend/server.py:12607-12609` |
| Sticky revocation keys off `connected: false` today | `mobile/src/api/sendInSleeper.ts:153-158` |
| `sleeper.link.jwt` is written with **no** `keychainAccessible` | `mobile/src/api/sendInSleeper.ts:72,81-84` |
| `SLOW_POST_PATHS` = 30 s; default POST = 15 s; `NO_RETRY_PATHS` applies to **GETs only** | `mobile/src/api/client.ts:230-248` |
| Sentry `tracesSampleRate: __DEV__ ? 1.0 : 0.2`, no `beforeSend` anywhere in `mobile/src` | `mobile/src/observability/sentry.ts:41-45` |
| `X-Device-Id` is **not** a global header — it is attached per call site | `mobile/src/api/client.ts:51-58` vs `auth.ts:39,97,590` |
| `TextDecoder`, `atob`, `btoa`, `Buffer`, `base64-js`: **zero occurrences** in `mobile/src` | verified 2026-08-13 |
| `is_enabled` is a **process-global boolean**, no per-caller dimension | `backend/feature_flags.py:768-770` |
| Tester allowlist keyed on `device:<X-Device-Id>` is the existing per-device gate | `backend/server.py:18131-18145` |
| Migration idiom: `create_all()` then per-column `ALTER` in its own txn | `backend/database.py:2706-2709`, `1980-1988` |
| Pure-module test idiom: transpile real TS with `typescript`, run under node | `mobile/tests/check-espn-nav-policy.js:14-35` |
| Rails counters live in `test_support.counters` | `backend/test_support.py:78-83` |

### 1.5 Three HLD instructions the code contradicts

Flagged because each changes the schema or rollout plan, not merely the wording. All three were **re-verified against `3b64a44` on 2026-08-13** by the orchestrator, independently of the drafting agents, because each one overrides an explicit HLD instruction and a wrong citation here would send the build in the wrong direction.

**(a) A device-custody link cannot be written into `sleeper_credentials`.** HLD blocking fix 5(i) says the route should "persist `sleeper_user_id`/`expires_at`/`verified_at` only, never `token_encrypted`." That row is **not writable**: `token_encrypted` is `nullable=False` (`backend/database.py:1297`) and `upsert_sleeper_credential` raises before touching SQL when the ciphertext is falsy (`backend/database.py:9574-9575`). Relaxing it is not an additive migration — `_migrate_db` only does `ALTER TABLE … ADD COLUMN` (`backend/database.py:1986`), and SQLite cannot drop a `NOT NULL` without a table rebuild, so the two dialects would diverge on a security-relevant column.

> **Resolution:** the device-custody link lives in `platform_links` and **no `sleeper_credentials` row is written at all**. Strictly less migration risk, same steady state.

**(b) There is no `verified_at` column on `sleeper_credentials`.** It exists only on `espn_credentials` (`backend/database.py:1338`; the narrowness comment governing it is `:1326-1329`). Sleeper verification state lives in the session (`sess["verified"]`, `backend/server.py:12491`) and in `users.verified_via` (`backend/server.py:12500`). `platform_links` carries its own `verified_at`; nothing is added to `sleeper_credentials`.

**(c) The token-write suppression cannot be a global flag.** `is_enabled` is process-global (`backend/feature_flags.py:768-770`), so a global "stop writing tokens" flag breaks **every binary in the field simultaneously** — including the ones that cannot be fixed. The gate is the client's declared capability (§2.1), with a flag layered on top as a kill switch. This is elaborated in §4.5 and §7.2, and it is the single most consequential correction in this document.

---

## 2. Interfaces / API

Every field is typed with nullability. `?` = the caller may omit it; `| null` = it may be JSON `null`. An absent required field is `400 bad_request`, never a silent default.

### 2.1 Capability declaration — `X-FTF-Caps`

Sent on `POST /api/platform/lease`, `POST /api/platform/outcome`, and `POST /api/sleeper/link`.

```
X-FTF-Caps: transport_v=1;ops=<16 lowercase hex chars>
```

- `transport_v`: integer ≥ 0. **Absent or unparseable ⇒ `transport_v = 0` (legacy binary).** Never a 400 — an old binary must not be rejected for failing to speak a protocol that did not exist when it shipped.
- `ops`: first 16 hex chars of SHA-256 over the device's compiled `(op_type, root_field)` set, sorted, `\n`-joined. Optional when `transport_v = 0`.

**Why a fingerprint and not `transport_v` alone.** D3's decisive argument is that the server must know the device's compiled root-field set to build a body the device will accept. A hand-bumped integer can lie — it is the `operationName` defect one layer up. The server holds `TRANSPORT_OP_SETS: dict[str, frozenset[tuple[str, str]]]` keyed by fingerprint, and an **unknown fingerprint is treated as no capability**, never as "probably fine."

Server helper: `_client_caps() -> Caps`, `Caps = NamedTuple(transport_v: int, ops: frozenset[tuple[str,str]] | None)`.

**`TRANSPORT_OP_SETS` is append-only while any build carrying an entry may still be in the field, and pruning it is a silent, compound failure.** Registry membership is load-bearing twice: `caps.ops` feeds the parity self-check (§4.1 step 12) and `caps.ops is not None` gates custody (§2.4). Drop an old fingerprint during a cleanup and every in-field device on that build simultaneously (i) falls out of device custody, so its next session replay **writes a `sleeper_credentials` row** and G1 is quietly defeated, and (ii) gets `426` at every lease, so the feature is dead — with no alert, and with M1 drifting non-zero in a way OI-4 has already trained the operator to read as benign. Required: a counter and alert on unknown-fingerprint requests to both `/api/sleeper/link` and `/lease`, and a comment on the registry saying entries are removable only once no build carrying them can still be installed.

**The device does not compute the fingerprint at runtime.** §3.5 says the device needs no crypto dependency, and `mobile/package.json` carries no `expo-crypto`/`js-sha256`/`crypto-js` (zero SHA-256 use in `mobile/src`) — the same class of unnamed primitive §4.2.1 exists to catch. `ops` is a **compile-time constant** in `compiled.ts`, verified against `DEVICE_OPS` by OI-17's `check-transport-caps-fingerprint.js`. Canonicalization is pinned exactly — `"{op_type}:{root_field}"` per entry, byte-sorted ascending, `\n`-joined, **no trailing newline**, SHA-256, first 16 chars of **lowercase** hex — because any disagreement between the TS constant and the Python registry means every device gets `426`.

`426` shape:

```json
{ "error": "upgrade_required", "required_transport_v": 2, "missing_ops": ["mutation:accept_trade"] }
```

`missing_ops` names FTF's own op set, not a secret, so it is safe to expose.

### 2.2 `POST /api/platform/lease`

Mints a single-use, server-recorded authorization for **one** outbound platform call. Deny by default. Joins `SLOW_POST_PATHS` (`mobile/src/api/client.ts:234`) → 30 s deadline, because the flow now risks two Render cold starts (HLD D1). **Never retried by the client** — a retried lease is a second lease.

**Request**

```ts
{
  platform: 'sleeper';                    // enum, exactly this in release 1
  op: 'propose_trade' | 'reject_trade';   // a REQUEST. The server decides what it builds.
  args: {
    league_id: string;                    // digits only
    their_user_id?: string;
    their_roster_id?: number;
    give_player_ids?: string[];
    receive_player_ids?: string[];
    draft_picks?: string[];
    transaction_id?: string;              // reject_trade only
    leg?: number;                         // reject_trade only, default 1
    impression_id?: string;               // deck.signal_v2, opaque
  }
}
```

**The client cannot supply `query`, `url`, `headers`, or `body`.** Unknown top-level keys are a `400`. The transport invariant is enforced by the request schema, not by convention.

**200**

```ts
{
  lease_id: string;               // 'lz_' + secrets.token_urlsafe(32); opaque
  expires_at: string;             // ISO-8601 UTC. UX ONLY — never enforced on device (I2)
  epoch: number;                  // the user's credential_epoch at issue
  credential_user_id: string;     // THE SERVER'S declared subject of this lease, from
                                  // platform_links.sleeper_user_id. §4.3 step 8 compares it
                                  // to the vault envelope's user_id — that comparison IS I5.
  request: {
    method: 'POST';
    url: string;                  // absolute; host must be in the device's compiled set
    headers: Record<string,string>;  // see the allowlist below
    body_b64: string;             // base64 of the EXACT UTF-8 bytes to transmit
  };
  limits: { timeout_ms: number; max_response_bytes: number };  // advisory; device clamps to its own
  op: { type: 'mutation'; root_field: string };                // echo. NON-AUTHORITATIVE.
}
```

> **`credential_user_id` is not redundant with `readEnvelope(userId)`.** That call compares the vault against the *client's* notion of the current user; I5 is about the **server's** declared subject of this particular lease. Only the second one catches a backend that hands device A a lease minted for user B while A's own session looks perfectly normal. §6.3 asserts a lease minted for user A is refused by a vault holding user B.

`op` is echoed for logging symmetry only. **The device MUST ignore it and derive the pair from `body_b64` (§4.2).** Trusting it would reintroduce the exact `operationName` defect PRD R3-fix A removed.

`body_b64` rather than a JSON object is load-bearing: PRD parser rule 4 requires the check to run on the exact bytes sent. Handing the device an object forces a re-serialize between validation and transmission, and RN's `JSON.stringify` guarantees nothing about key order, number formatting, or non-ASCII escaping.

**Errors**

| Status | `error` | Cause |
|---|---|---|
| 400 | `bad_request` | arg validation, unknown key, non-digit `league_id`, missing `X-Device-Id` |
| 401 | `no_user` | session without `user_id` |
| 403 | `verification_required` | `sess["verified"]` falsy |
| 404 | `feature_disabled` | `trade.send_in_sleeper` or `platform.device_transport` off |
| 409 | `no_device_credential` | no live `platform_links` row for (user, `sleeper`), or a `device_id` mismatch |
| 409 | `credential_rejected` | `platform_links.rejected_at` set (R8) |
| 409 | `send_in_flight` | an open lease with the same `request_digest` exists. **Body carries `{error, lease_id, issued_at, retry_after_s}`** — `retry_after_s` derived from the holder's `digest_until`, since that is when the sweep will release it |
| 409 | `too_many_outstanding` | issuing would take open leases past `MAX_OUTSTANDING_LEASES` (§4.1 step 14 counts **after** the insert, so the check is `>`) |
| 413 | `body_too_large` | built body > `MAX_BODY_BYTES` |
| 426 | `upgrade_required` | §2.1 |
| 500 | `lease_self_check_failed` | §4.1 step 12 |
| 503 | `platform_unreachable` | roster resolution failed (§5.2) |
| 503 | `sleeper_unconfigured` | body builder raised `SleeperWriteError` |
| 599 | `test_mode_lease_disabled` | `_TEST_MODE` |

**Not returned: any credential, in any form.** Restated because `POST /api/sleeper/link` already refuses to echo tokens and the same must hold here.

**Header policy — an allowlist, not a denylist.** I4 names `authorization`. That is necessary and not sufficient: `cookie` attaches a credential of the compromised backend's choosing just as effectively. The device applies a **compiled allowlist**, case-insensitive after ASCII-lowercasing:

`content-type` · `accept` · `x-sleeper-graphql-op`

and refuses the lease outright if any other name appears (which subsumes `authorization`, `cookie`, `proxy-authorization`), if a name or value contains a byte outside `0x20..0x7E` (blocking CR/LF header injection, which RN's `fetch` does not reliably reject), or if a name repeats after lowercasing. `authorization` still gets its **own distinct refusal code** so the I4 case is separately observable.

`x-sleeper-graphql-op` travels because Sleeper's own client sends it (`backend/sleeper_write.py:287`) and is explicitly non-authoritative for the guard.

**The Chrome-spoofing headers cannot appear in a lease** — `user-agent`, `origin`, `referer` and `accept-language` are not on the allowlist. That is the compiled expression of PRD §2.4's "do not port `_BROWSER_HEADERS` to the device." Stated as those four names rather than as "`_BROWSER_HEADERS`" because `accept` is *also* a member of that dict (`backend/sleeper_write.py:57`) and **is** allowlisted, so the blanket claim would not survive a reader checking `sleeper_write.py:50-58`.

### 2.3 `POST /api/platform/outcome`

A **report**, not a side effect. Idempotent by `lease_id` (I3), retryable, and it **accepts late reports** (I2). Joins `SLOW_POST_PATHS`.

Auth: session required. **Not** gated on `sess["verified"]` — a report is not a write, and refusing reports from a session that lapsed mid-send manufactures the `unknown` state I2 exists to make rare.

**Request**

```ts
{
  lease_id: string;
  result: 'ok' | 'http_error' | 'network_error' | 'aborted_before_send' | 'refused';
  http_status?: number | null;    // iff result is 'ok' | 'http_error'
  response_b64?: string | null;   // RAW platform bytes, UNPARSED (I1), capped
  truncated?: boolean;            // device hit max_response_bytes
  refusal?: SendRefusal | null;   // iff result is 'refused' OR 'aborted_before_send'
                                  // (the latter always carries 'not_foreground'). §2.6. THE DISCRIMINATOR.
  guard_reason?: GuardRefusal|null; // iff refusal === 'guard_refused'. §4.2 enum.
  request_digest?: string | null; // advisory echo; compared and logged, never authoritative
  duration_ms?: number | null;
}
```

> **`refusal` is not optional decoration — without it three things in this document are unbuildable.** An earlier draft had `result: 'refused_by_guard'` with only `guard_reason`, typed to the `GuardRefusal` enum, which contains no transport-layer member. That shape can express *none* of §2.6's ten `SendRefusal` values. Concretely: (i) §4.3's rule that any refusal at steps 1–9 reports before the network — so the lock releases immediately — could not hold for a header or epoch refusal, stranding the lease as `unknown` for the full `DIGEST_WINDOW`; (ii) §6.4's negative control counts a `host_not_allowed` refusal, so the merge gate could not be built; (iii) §2.2 promises `authorization` gets its own code "so the I4 case is separately observable," but the server would never learn it — making the single highest-value signal in the threat model invisible to M4. `guard_reason` is now strictly a sub-discriminator of `refusal === 'guard_refused'`.

**200 — identical shape whether this is the first report or the fifth**

```ts
{
  recorded: true;
  state: 'ok' | 'failed' | 'aborted' | 'refused' | 'unknown';
  late: boolean;                  // recorded after expires_at or after the digest window
  duplicate: boolean;             // this lease already had an outcome; body is the ORIGINAL
  epoch_stale: boolean;           // credential_epoch was bumped between issue and report
  transaction_id?: string | null; // server-parsed from response_b64, propose_trade only
  platform_error?: string | null; // server-classified, never raw
}
```

**Errors**

| Status | `error` | Cause |
|---|---|---|
| 400 | `bad_request` | malformed enum, non-base64 `response_b64` |
| 401 | `no_user` | |
| 403 | `lease_user_mismatch` | lease's `user_id` ≠ session's |
| 403 | `lease_device_mismatch` | lease's `device_id` ≠ `X-Device-Id` |
| 404 | `unknown_lease` | |
| 413 | `outcome_too_large` | body > `MAX_OUTCOME_BYTES` |

**There is no 409 on this endpoint and there must never be one.** Rejecting a late report manufactures `unknown` out of a slow network — the exact state I2 exists to prevent.

**A 403 does not silently drop the report.** The row is written to `platform_lease_reports` with `rejected_reason`, and the lease's own state is left untouched. Dropping it would make the strongest signal in the system — a report from a device that was never leased — invisible to M8. The 403 goes to the caller; the evidence is kept.

### 2.4 `POST /api/sleeper/link` — device-custody mode

Behaviour is selected by the client's declared capability, **not** by a global flag (§1.5c).

Suppression fires only when **all** of the following hold — this predicate must be **identical** to the one `/lease` uses at §4.1 step 2, plus a known fingerprint:

```python
def device_custody_active(caps, user_id, device_id) -> bool:
    return (caps.transport_v >= 1
            and caps.ops is not None            # KNOWN fingerprint, not merely a version claim
            and is_enabled("sleeper.device_custody")
            and device_transport_enabled(user_id, device_id))   # same helper as /lease
```

| Client | Condition | Token write |
|---|---|---|
| legacy binary | `transport_v = 0` | **writes** `sleeper_credentials` — unchanged, `backend/server.py:12480-12487` |
| capable binary | `device_custody_active(...)` false | writes (kill switch, and the fallback for every case below) |
| capable binary | `device_custody_active(...)` true | **does not write**; upserts `platform_links` instead |

> **Every clause in that predicate closes a way to strand a user with no token row and no working lease.** (i) A binary claiming `transport_v=1` with a fingerprint the server does not recognise — exactly what a staged server rollout produces — would otherwise get device custody at link time and `426` at every lease, killing *both* paths; `caps.ops is not None` sends it down the writing branch instead. (ii) `sleeper.device_custody` is a plain global `is_enabled` with no per-device dimension (`backend/feature_flags.py:768-770`), while `/lease` is allowlist-gated — so without `device_transport_enabled` here, S8 would move every non-operator's credential into a custody mode the server refuses to serve, and their fallback `POST /api/trades/propose` returns `409 sleeper_not_linked` (`backend/server.py:12608-12609`). **Any doubt resolves toward writing the row**, because a spurious token row is a custody weakness the operator can see and fix, while a missing one is a dead feature the user cannot.

**Three client-side prerequisites, each of which silently defeats the design if missed:**

1. **`linkSleeperToken` must emit `X-FTF-Caps`.** It calls `api.post` with no headers (`mobile/src/api/sendInSleeper.ts:46-48`) and `client.ts` adds no global one, so without this edit **every replay arrives as `transport_v = 0` and writes a `sleeper_credentials` row on every fresh session** — defeating G1 on the design's own happy path, silently, while everything appears to work.
2. **`X-Device-Id` must be attached to `linkSleeperToken`, `/lease`, and `/outcome`.** It is **not** a global header: `client.ts:51-58` sends `X-Device`, `X-OS-Version`, `X-App-Version`, `X-User-TZ`, and `X-Device-Id` is attached per-call in six places (`auth.ts:39,97,590`, `events.ts:287`, `flags.ts:37`, `recordedPicks.ts:275`) — none of them this route. §3.1 makes `platform_links.device_id` non-nullable, so a device-custody link without it **500s on insert**, and §7.2's operator-only rollout has nothing to key on. Missing `X-Device-Id` on this route is a `400`, mirroring §2.2.
3. **The Fernet gate must move inside the writing branch.** `backend/server.py:12442` returns `503 sleeper_unconfigured` before anything else runs; under device custody no ciphertext is ever produced, so that check must not gate the custody path.

**On a successful device-custody upsert:** set `revoked_at = NULL`, `rejected_at = NULL`, `verified_at = now`, and leave `epoch` **unchanged** (a re-link is not a revocation). Stated because nothing else in this document clears either field — and if they survive a re-link, one disconnect makes `GET` return `revoked: true` forever (so every new binary wipes its own vault on the next session), and one 401 makes `/lease` return `409 credential_rejected` forever, falsifying §5.3's "retryable after re-capture." Both are permanent bricks from a single ordinary event. `test_platform_link_contract.py` covers both.

Everything before the store is unchanged and must stay unchanged: the shape check (`:12446`), the expiry check (`:12448`), the `token_user_mismatch` claim gate (`:12455-12458`), and the live oracle (`:12467-12476`). Session verification (`sess["verified"]`, `users.verified_via`, the persisted-session force-upsert at `:12489-12514`) is identical in both branches.

HLD blocking fix 1 turns on this: the route remains the account-verification oracle, and the device still replays the raw JWT to it on every fresh session (`mobile/src/api/sendInSleeper.ts:170`). **G1 is therefore "no server-side JWT at rest," not "the JWT never touches Render"** — a client cannot be trusted to verify itself.

Response gains two keys; the existing four are unchanged so old clients keep parsing:

```ts
{ connected: true; sleeper_user_id: string|null; expires_at: string|null; verified: boolean;
  custody: 'server' | 'device';   // NEW
  epoch: number; }                // NEW
```

### 2.5 `GET /api/sleeper/link` — the ordering contract

**This is the single most dangerous interface in release 1.** Today it returns `{"connected": false}` whenever `get_sleeper_credential` returns nothing (`backend/server.py:12425-12427`), and every build in the field reads that as "wipe your credential."

```ts
{
  connected: boolean;   // TRUE if EITHER a sleeper_credentials row OR a live platform_links row exists
  revoked: boolean;     // NEW — true ONLY on an explicit DELETE for this epoch
  custody: 'server' | 'device' | 'none';   // NEW
  sleeper_user_id: string | null;
  expires_at: string | null;
  expired: boolean;
  epoch: number;        // NEW
}
```

Two rules, both non-negotiable:

- **`connected` is a union, and it never goes false because custody moved.** An old binary reads only `connected` (`mobile/src/api/sendInSleeper.ts:153`). This single line is what stops the field from erasing itself.
- **`revoked: true` is emitted only by an explicit `DELETE`.** Absence of a row is not revocation. New binaries key sticky revocation off `revoked === true` and nothing else. `revoked` is present on **every** response shape including `connected: true`, so a future client can never read a missing field as `false`.

`expired` is computed as today (`:12429-12433`) from whichever record supplied `expires_at`.

`DELETE /api/sleeper/link` becomes the revocation writer: `delete_sleeper_credential(user_id)` **and** stamp `platform_links.revoked_at` **and** `epoch += 1`, in one transaction.

### 2.6 Device transport module

```ts
// mobile/src/transport/platformTransport.ts
export type SendRefusal =
  | 'host_not_allowed' | 'method_not_allowed' | 'header_not_allowed'
  | 'auth_header_present' | 'body_too_large' | 'bad_base64' | 'guard_refused'
  | 'user_mismatch' | 'stale_epoch' | 'no_credential' | 'not_foreground';

export interface SendResult {
  kind: 'sent' | 'refused' | 'network_error' | 'aborted';
  refusal?: SendRefusal;
  guardReason?: GuardRefusal;   // §4.2
  httpStatus?: number;
  responseBytes?: Uint8Array;   // NEVER parsed on device (I1)
  truncated?: boolean;
  durationMs?: number;
}

export async function executeLease(lease: Lease): Promise<SendResult>;  // NEVER throws
```

`executeLease` never throws. Every failure is a typed `SendResult`, because a thrown exception is the one outcome the caller cannot classify — and therefore the one that becomes `unknown`.

Compiled constants, in the binary, never server-supplied:

```ts
const ALLOWED_HOSTS   = new Set(['sleeper.com']);          // sleeper_write.py:39
const ALLOWED_METHODS = new Set(['POST']);
const ALLOWED_HEADERS = new Set(['content-type','accept','x-sleeper-graphql-op']);
const MAX_BODY_BYTES     = 65_536;
const MAX_RESPONSE_BYTES = 262_144;
const HARD_TIMEOUT_MS    = 20_000;    // clamps lease.limits.timeout_ms
const DEVICE_OPS: ReadonlySet<string> = new Set([
  'mutation:propose_trade',   // sleeper_write.py:203-211
  'mutation:reject_trade',    // sleeper_write.py:352-356
]);
```

`DEVICE_OPS` is enumerated from real query documents per PRD rule 5. Deliberately absent: `query:__typename` (I6 — a `{__typename}` success body is a constant string any client can fabricate, so routing the oracle here makes it client-forgeable); `query:league_players` (`backend/trade_block_service.py:73`, an unauthenticated public read that stays on Render); `mutation:accept_trade` and `query:league_transactions_filtered` (do not exist in-tree).

Host matching is on the parsed URL's **hostname**, lowercased, after rejecting any non-`https:` scheme and any URL carrying userinfo (`https://sleeper.com@evil.tld/`). Substring matching is forbidden.

### 2.7 Credential vault

```ts
// mobile/src/transport/credentialVault.ts
interface CredentialEnvelope {
  v: 1;
  user_id: string;      // FTF user_id === Sleeper user_id
  platform: 'sleeper';
  secret: string;       // the raw JWT, verbatim
  epoch: number;
  written_at: string;
}
export async function readEnvelope(userId: string): Promise<CredentialEnvelope | null>;
export async function writeEnvelope(e: CredentialEnvelope): Promise<boolean>;
export async function wipeEnvelope(): Promise<void>;
export async function migrateLegacySlot(userId: string): Promise<'migrated'|'none'|'failed'>;
```

**One** SecureStore key, `ftf.platformCreds`, always written with `{ keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY }`. That option appears **nowhere** in `mobile/src` today — the existing write at `sendInSleeper.ts:81-84` passes no options, so the 365-day JWT is iCloud-backup eligible right now.

`migrateLegacySlot` implements HLD blocking fix 4: read `sleeper.link.jwt` (`sendInSleeper.ts:72`), write the envelope with correct accessibility, **verify the read-back byte-for-byte**, then delete the legacy key. Order matters — delete-then-write loses the credential on a Keychain failure. `writeEnvelope` returns `false` rather than throwing (matching the swallow-and-continue posture at `sendInSleeper.ts:85-87`), and `migrateLegacySlot` returns `'failed'` **without deleting**. Two Keychain copies of a 365-day full-account credential, one outside the wipe and epoch logic, is the failure this prevents.

**A deliberate deviation from a normative PRD line, not a gap-fill.** PRD §Custody says "`user_id` mismatch ⇒ **wipe**" (PRD:144). This LLD instead has `readEnvelope(userId)` return `null` — it does **not** wipe — when the stored `user_id` differs. The wipe on mismatch fires from the session-establishment path, where the current user is authoritative. A wipe triggered by any caller passing a stale id is a self-inflicted denial of service.

---

## 3. Data Structures & Schema

All three tables are created by `metadata.create_all()` (`backend/database.py:2708`); a new table needs no `_migrate_db` entry. **No existing column is altered** (§1.5a).

### 3.1 `platform_links` — secret-free by construction

```python
platform_links_table = Table("platform_links", metadata,
    Column("user_id",         String, primary_key=True),
    Column("platform",        String, primary_key=True),   # 'sleeper'
    Column("device_id",       String, nullable=False),     # X-Device-Id
    Column("sleeper_user_id", String),
    Column("epoch",           Integer, nullable=False),    # credential_epoch
    Column("expires_at",      String),                     # from JWT exp — a HINT, not a gate
    Column("verified_at",     String),                     # oracle pass
    Column("linked_at",       String, nullable=False),
    Column("updated_at",      String, nullable=False),
    Column("revoked_at",      String),                     # explicit DELETE; drives `revoked`
    Column("rejected_at",     String),                     # R8 credential_rejected
)
```

**No secret column exists and none may be added.** A future device-reported "looks connected" heuristic gets its own column — the same narrowness rule the ESPN `verified_at` comment already carries (`backend/database.py:1326-1329`).

`epoch` lives here rather than on `users` so a `DELETE` can bump it in the same statement that stamps `revoked_at`. Its semantics, exactly:

- Starts at 1 on first link. `+= 1` on **explicit disconnect only** — not on re-link, not on a 401, not on expiry.
- Every lease records the epoch it was minted under; the device refuses a lease whose epoch ≠ its envelope's (§4.3 step 2).
- **Honest limit:** the epoch stops *new* leases and lets a device self-refuse a stale one. It cannot recall a lease already dispatched, because there is no device-side TTL by design (I2). Bounded by lease TTL in practice, not in theory. Named residual, OI-6.

**Two-device note.** The PK is `(user_id, platform)`, so a second device linking overwrites `device_id` and device A silently loses the ability to lease. The alternative — PK on `(user_id, platform, device_id)` — makes "disconnect" ambiguous, which OQ-7 has not answered. Single-holder is the release-1 choice because it is the one that cannot leave a forgotten device holding a live credential the user believes is disconnected. OI-3.

### 3.2 `platform_leases`

```python
platform_leases_table = Table("platform_leases", metadata,
    Column("lease_id",       String,  primary_key=True),
    Column("user_id",        String,  nullable=False),
    Column("platform",       String,  nullable=False),
    Column("device_id",      String,  nullable=False),
    Column("op_type",        String,  nullable=False),   # 'mutation'
    Column("root_field",     String,  nullable=False),   # PARSED, never a label
    Column("request_digest", String,  nullable=False),   # always recorded
    Column("digest_lock",    String),                    # = request_digest while OPEN; NULL when released
    Column("epoch",          Integer, nullable=False),
    Column("transport_v",    Integer, nullable=False),
    Column("state",          String,  nullable=False),   # §3.4
    Column("late",           Integer, nullable=False, server_default="0"),
    Column("epoch_stale",    Integer, nullable=False, server_default="0"),
    Column("url",            String,  nullable=False),
    Column("method",         String,  nullable=False),
    Column("body_sha256",    String,  nullable=False),
    Column("body_bytes",     Integer, nullable=False),
    Column("league_id",      String),
    Column("issued_at",      String,  nullable=False),
    Column("expires_at",     String,  nullable=False),   # UX only
    Column("digest_until",   String,  nullable=False),   # issued_at + DIGEST_WINDOW
    Column("settled_at",     String),
    Column("http_status",    Integer),
    Column("transaction_id", String),
    Column("platform_error", String),
    Column("refusal",        String),   # SendRefusal — §2.6. The discriminator.
    Column("guard_reason",   String),   # GuardRefusal — only when refusal='guard_refused'
    Index("ux_platform_leases_digest_lock", "digest_lock", unique=True),
    Index("ix_platform_leases_user_state",  "user_id", "state"),
    Index("ix_platform_leases_issued_at",   "issued_at"),
    # The lock is a DENORMALIZED second copy of state. Nothing else enforces
    # the equivalence, and both failure directions are severe: a terminal state
    # that forgets to null the lock is a PERMANENT phantom 409 for that user,
    # and an early null permits a duplicate send. Both dialects honour a CHECK
    # at create_all time, and this is a new table, so there is no migration risk.
    CheckConstraint("(state = 'issued') = (digest_lock IS NOT NULL)",
                    name="ck_platform_leases_lock_matches_state"),
)
```

**The `digest_lock` NULL trick is the concurrency primitive, and the choice over a partial index is deliberate.** A partial unique index (`WHERE state='issued'`) expresses the same constraint, but its syntax differs by dialect and a silently-ignored index is a duplicate-send bug that appears only under concurrency. NULL-distinctness in a plain `UNIQUE` index needs no dialect branch and survives the `DATABASE_URL` swap the project already plans for. One nullable column gives an atomic, engine-enforced "one open send per logical request" with no read-then-write race.

> **Verified empirically, 2026-08-13, rather than assumed from the standard.** Three rows with `digest_lock IS NULL` insert successfully and a duplicate non-NULL value is refused, on **SQLite 3.50.4** (`UNIQUE constraint failed`) and on **PostgreSQL 18.3** (`duplicate key value violates unique constraint`). Postgres treats index NULLs as distinct by default; `NULLS NOT DISTINCT` is opt-in from PG15 and must never be added to this index. A startup assertion (§5.4 item 6) checks the index exists, because a missing one fails open.

> **The CHECK was verified on both engines, 2026-08-13, not assumed.** `('issued', 'd1')` and `('sent_ok', NULL)` insert; `('sent_ok', 'd2')` — a terminal state still holding its lock — and `('issued', NULL)` — an open lease with no lock — are both refused, on **SQLite 3.50.4** and **PostgreSQL 18.3**, with identical semantics. The NULL-propagation worry (`(NULL = 'issued')` yields NULL, and a CHECK passes on NULL rather than only on TRUE) does not apply here because `state` is `nullable=False`; the two constraints are load-bearing together, and neither may be relaxed without the other being reconsidered.

**The index is global, but `user_id` is a digest component** (§3.5 Rule B), so two users can never collide — worth stating, because a global unique index on a digest otherwise reads as a cross-user denial-of-service waiting to happen.

An in-process dict would be wrong here for a separate reason: Render runs more than one worker, so a process-local lock does not stop two taps landing on two workers. (`backend/draft_board_service.py:177` uses one — correct for a cache, wrong for this.)

**The request body is not stored.** `body_sha256` + `body_bytes` suffice for forensics, and the body embeds league and roster data with no reason to live in a lease row.

### 3.3 `platform_lease_reports` — append-only

Every `/outcome` call lands here regardless of whether it mutated the lease.

```python
platform_lease_reports_table = Table("platform_lease_reports", metadata,
    Column("id",              Integer, primary_key=True, autoincrement=True),
    Column("lease_id",        String, nullable=False),
    Column("received_at",     String, nullable=False),
    Column("session_user_id", String),
    Column("device_id",       String),
    Column("result",          String),
    Column("http_status",     Integer),
    Column("applied",         Integer, nullable=False),   # 0 = duplicate or rejected
    Column("rejected_reason", String),                    # device_mismatch|user_mismatch|duplicate
    Index("ix_lease_reports_lease", "lease_id"),
)
```

This is what makes M8 ("leases issued vs outcomes reported") a real metric rather than a count of successful writes, and it is the only place a `lease_device_mismatch` leaves a trace.

### 3.4 Lease state machine

```
   (issue) ──▶ issued ──┬──▶ ok                    terminal
                        ├──▶ failed                terminal
                        ├──▶ refused               terminal
                        ├──▶ aborted               terminal
                        └──(digest window elapses, no report)──▶ unknown
                                                                    │
                        late report accepted, `late: true` ─────────┘
                        unknown ──▶ ok | failed | refused | aborted
```

| State | `digest_lock` | Meaning |
|---|---|---|
| `issued` | held | minted, no report yet |
| `ok` | NULL | platform accepted (2xx, no GraphQL `errors`) |
| `failed` | NULL | reached the platform and was rejected, **or** a network error where we cannot tell |
| `refused` | NULL | a compiled device guard blocked it — **never reached the platform** |
| `aborted` | NULL | `aborted_before_send`; the foreground guard fired |
| `unknown` | NULL | no report after the digest window. **Reserved for exactly this** (HLD blocking fix 2) — never for a timed-out report. |

`unknown` is the only state a later transition may amend. Every other terminal state is final; a second report returns the recorded row with `duplicate: true`.

### 3.5 `request_digest`

A digest that varies with dict ordering is not a lock. Three rules make it stable.

**Rule A — the body is serialized exactly once, and the digest and the wire bytes are the same object.**

```python
def serialize_body(body_obj: dict) -> bytes:
    """The ONE place a platform request body becomes bytes.
    sort_keys  → dict ordering cannot vary the digest.
    separators → no whitespace variance.
    ensure_ascii=False + utf-8 → one deterministic encoding.
    LIST ORDER IS NEVER TOUCHED: k_adds[i] pairs positionally with v_adds[i]
    (sleeper_write.py:18-21), so sorting a list would corrupt the trade."""
    return json.dumps(body_obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")
```

The same `bytes` object is base64'd into `body_b64` and fed to the digest. There is no second serialization anywhere in the process, and a unit test asserts `b64decode(resp["request"]["body_b64"]) == stored_body_bytes`.

**Rule B — NUL-separated components in a fixed order, with NUL forbidden inside them.**

```python
DIGEST_DOMAIN = b"ftf.platform.request.v1\x00"

def compute_request_digest(*, user_id, platform, op, method, url, body: bytes) -> str:
    parts = (user_id, platform, op, method.upper(), _normalize_url(url))
    for p in parts:
        if not isinstance(p, str) or "\x00" in p:
            raise ValueError("digest component must be a NUL-free str")
    h = hashlib.sha256(); h.update(DIGEST_DOMAIN)
    for p in parts:
        h.update(p.encode("utf-8")); h.update(b"\x00")
    h.update(len(body).to_bytes(8, "big"))   # length-prefix: body is last and unambiguous
    h.update(body)
    return h.hexdigest()
```

The separators exist because these are variable-length strings; concatenating without them makes the digest ambiguous. The length prefix means a body cannot be split to collide with a component boundary even if the NUL guard were bypassed.

**Rule C — headers are excluded, and the reason is written down.** Headers carry no request identity, they are server-hotfixable by design (PRD §8), and `authorization` must never enter a hash that gets logged or echoed. Including them would also break dedupe on a header hotfix, which is the opposite of the intent.

Computed **server-side only**. The device never computes it and needs no crypto dependency; the optional echo in `/outcome` is compared and logged, never authoritative.

`_normalize_url`: lowercase scheme and host, strip a default `:443`, drop any fragment, preserve path and query byte-for-byte. Sleeper's URL is a constant (`sleeper_write.py:39`) so this is defensive today — ESPN's REST surface in release 2 will need it.

**Determinism check.** `build_propose_trade_body` (`backend/sleeper_write.py:230-273`) is a pure function of `ProposeTradeRequest`, and `k_adds`/`v_adds` are built in a fixed order (receive-then-give, `:250-256`), so the digest is stable across two taps of the same trade. It is **not** stable across a caller reordering `give_player_ids`. The mobile client builds these from an ordered list, so this is acceptable — but it is a known limitation, not a guarantee.

### 3.6 Constants

| Name | Value | Where |
|---|---|---|
| `LEASE_TTL` | 5 min (D1) | server |
| `DIGEST_WINDOW` | 10 min | server |
| `MAX_OUTSTANDING_LEASES` | 3 per user | server |
| `MAX_BODY_BYTES` | 65_536 | both, compiled |
| `MAX_RESPONSE_BYTES` | 262_144 | device, compiled |
| `MAX_OUTCOME_BYTES` | 512 KiB | server |
| `MAX_DOC_CODEPOINTS` | 8_192 | device guard — **code points, both sides** (§4.2 Stage A step 7) |
| `MAX_DOC_TOKENS` | 4_096 | device guard |
| `MAX_DOC_DEPTH` | 32 | device guard |
| `LEASE_RETENTION` | 90 d | sweep |

`MAX_BODY_BYTES` appearing on both sides is the point of D3: the two can disagree, and the capability fingerprint is how the server learns which cap the device compiled.

### 3.7 Feature flags

Added to `config/features.json`, **default false**, and mirrored into the three fixtures (`release.json`, `onboarding-v2.json`, `profiles-on.json`) or `test_seed_ui_test_db.py` fails:

- `platform.device_transport` — gates `/lease` issuance. **This is the rollback primitive** (PRD §7).
- `sleeper.device_custody` — gates the token-write suppression in `POST /api/sleeper/link`.

**Neither may ever appear in `LAUNCHED_FLAG_DEFAULTS`** (`mobile/src/state/useFeatureFlags.ts:45`), per PRD §7. The device does not read them at all — flags are evaluated server-side at lease time, which is what dissolves the fail-open hazard. The existing comment at `useFeatureFlags.ts:63-70` demands that any key listed there match `config/features.json`; for these two the correct action is **absence**, not `false`.

---

## 4. Core Logic

### 4.1 Lease issue

```
 1. _TEST_MODE                                  -> 599 test_mode_lease_disabled   [fail closed]
 2. sess = _require_session(); user_id          -> else 401 no_user
 3. sess['verified']                            -> else 403 verification_required
 4. caps = _client_caps(); device_id = X-Device-Id  -> else 400 bad_request
      BINDING PRECEDES THE GATE: a request missing X-Device-Id must be a 400
      (sec 5.4 item 4), and evaluating the allowlist first would return 404.
 5. schema check: reject unknown top-level keys -> else 400
 6. device_transport_enabled(user_id, device_id) -> else 404 feature_disabled
      == is_enabled('trade.send_in_sleeper')
         and is_enabled('platform.device_transport')
         and in_tester_allowlist(device_id, user_id)      # THE named helper, below
 7. (op_type, root_field) in caps.ops           -> else 426 upgrade_required
      MOVED UP from after the body build: `op` is present in the request at
      step 6 and nothing below is needed to decide it, so a skewed client no
      longer costs a live Sleeper roster fetch before its 426.
 8. link = get_platform_link(user_id, 'sleeper')
      none | revoked_at set  -> 409 no_device_credential
      rejected_at set        -> 409 credential_rejected
      device_id mismatch     -> 409 no_device_credential  [do not disclose the other device]
 9. validate args; resolve rosters via _fetch_league_rosters   (§5.2 wraps its failure)
10. body = sleeper_write.build_propose_trade_body(req)   # or reject_trade
11. body_bytes = serialize_body(body);  len <= MAX_BODY_BYTES -> else 413
12. GUARD PARITY: guard(body_bytes, allowed_ops=caps.ops)   # THIS device's set
      refuse -> 500 lease_self_check_failed, log, DO NOT issue
13. digest = compute_request_digest(...)
14. class _Rollback(Exception): pass
    try:
        with engine.begin() as conn:              # ONE transaction, insert + count
            # DIALECT BRANCH — see the two measurements below.
            sp = conn.begin_nested() if _IS_POSTGRES else None
            try:
                INSERT platform_leases (state='issued', digest_lock=digest)
                if sp: sp.commit()
            except IntegrityError as e:
                if not _is_digest_lock_violation(e):   # DIALECT-ASYMMETRIC — see below
                    raise                         # NOT NULL / CHECK bugs must not be
                                                  # served as 409 send_in_flight
                if sp: sp.rollback()              # Postgres: outer txn survives
                holder = SELECT ... WHERE digest_lock = digest
                if holder is None:
                    retry the INSERT once; if it fails again -> null-safe 409
                -> 409 send_in_flight {lease_id, issued_at, retry_after_s}
            if open_lease_count(conn, user_id) > MAX_OUTSTANDING_LEASES:
                raise _Rollback                   # unwinds the whole begin() block
    except _Rollback:
        -> 409 too_many_outstanding
15. return the lease
```

**Why a dialect branch rather than a savepoint everywhere — both directions measured on 2026-08-13, SQLAlchemy 2.0.49 / SQLite 3.50.4 / PostgreSQL 18.3:**

| | Postgres | SQLite (this repo's `engine`) |
|---|---|---|
| Transaction survives a caught `IntegrityError`? | **No** — `InFailedSqlTransaction`, so the holder `SELECT` cannot run. Savepoint **required**. | **Yes** — the holder `SELECT` succeeds immediately after. Savepoint **unnecessary**. |
| `begin_nested()` + `raise` to roll back the outer block | correct | **leaks an orphan row** |

The SQLite leak is the trap: the pysqlite savepoint recipe (`isolation_level = None` plus an explicit `BEGIN`) is attached **only to `ingest_engine`** (`backend/database.py:92-99`, whose own comment says "SEPARATE listener — do NOT attach" and notes that "driver autocommit checks have churned across Python versions"). The main `engine` (`:62`) carries only `check_same_thread`, so pysqlite emits no `BEGIN`, the `SAVEPOINT` is outermost, and `RELEASE` **commits to disk** — after which the `_Rollback` cannot undo it. Measured directly: default engine → `rows after outer rollback = [('e','d1')]`; the same block on an engine carrying the `:92-99` recipe → clean. That orphan sits in `state='issued'` holding a `digest_lock`, so the user eats a phantom `409 send_in_flight` until the sweep clears it ~10 minutes later.

Applying the recipe to the main engine instead would work, but its blast radius is all 111 `with engine.begin()` writers — not a change to make in passing for one route. The branch is the smaller correct move, and §6.3's `too_many_outstanding` rollback test must be **dialect-parameterised** so the SQLite path is actually exercised rather than assumed.

**`_is_digest_lock_violation` cannot match on the index name, because only one dialect reports it.** Measured 2026-08-13:

| Violation | PostgreSQL 18.3 | SQLite 3.50.4 |
|---|---|---|
| duplicate `digest_lock` | `duplicate key value violates unique constraint "ux_platform_leases_digest_lock"` — index name, also structured as `e.orig.diag.constraint_name`, SQLSTATE `23505` | `UNIQUE constraint failed: platform_leases.digest_lock` — **the column, never the index name** |
| `NOT NULL` | `null value in column "state" … violates not-null constraint` | `NOT NULL constraint failed: platform_leases.state` |
| `CHECK` | `violates check constraint "ck_platform_leases_lock_matches_state"` | `CHECK constraint failed: ck_platform_leases_lock_matches_state` — name **is** reported |

So the helper is dialect-asymmetric by necessity: on Postgres match SQLSTATE `23505` **and** `diag.constraint_name == "ux_platform_leases_digest_lock"`; on SQLite match the message prefix `UNIQUE constraint failed:` **and** the column token `platform_leases.digest_lock`. An earlier draft of this block specified matching the index name on both, which **silently never matches on SQLite** — every duplicate tap would re-raise as a 500 instead of the `409 send_in_flight` §4.6 promises, and the §6.3 duplicate-tap test would fail in a way that invites someone to loosen it. Note the happier asymmetry: the CHECK name *is* portable, so the startup assertion (§5.4 item 6) can match on it directly.

Two smaller points the block above encodes: the repo has **zero** existing `IntegrityError` handlers to copy (`backend/database.py:9584`, 111 self-contained `engine.begin()` writers), so this is new ground and the structure is the spec, not a sketch; and with a CHECK constraint plus five `nullable=False` columns now on the table, a bare `except IntegrityError` is ambiguous — it must discriminate on the constraint name, or a NOT NULL bug gets served to the client as "already sending."

**Step 14's count check, ordered after the insert, is still deliberate.** Counting first is a TOCTOU; counting after means the loser unwinds.

**`in_tester_allowlist` is the same helper §2.4 uses, and that identity is the point.** See §7.2 — a custody gate wider than the lease gate strands users with no token row and no lease.

**Steps 1 and 3 are inherited, not invented.** `/api/trades/propose` fails closed under `_TEST_MODE` with `599` (`backend/server.py:12574-12578`) and refuses an unverified session with `403` (`:12592-12595`). The lease endpoint is the route that replaces it and carries the identical gates. Without the `_TEST_MODE` gate, a Maestro run mints a real lease and the device makes a real Sleeper write — and the counter that would have caught it (`completed_proposes`, `backend/test_support.py:82`) is server-side and reads zero.

**Step 12 is the highest-value line in this document.** The identical guard, ported to Python and driven by the identical corpus, runs before a lease is issued. It buys nothing against a compromised backend — the attacker just removes it. It buys everything against the ordinary failure mode: a body-shape hotfix the device would refuse. Without it that hotfix produces a device refusal **indistinguishable from an attack**, and M4 pages the operator — the exact risk D3 set out to avoid. With it, the failure surfaces in CI or as a 500 on one request.

> **It must be handed `caps.ops`, not a server-global allow set — otherwise it does not do the job it exists for.** The guard's terminal check is membership in the *device's compiled* set, which the server knows only as the caps fingerprint. A self-check against a server-global set passes in exactly the case worth catching (the server built an op **this** binary cannot execute), issues the lease, and the device refuses with `guard_refused` — which §4.4 classifies as an M4 incident. The one line meant to keep a server bug from paging the operator would page the operator for a server bug. The `allowedOps` parameter (§4.2) is what closes it, and §6.1(a)'s corpus entries carry an explicit op-set dimension so both implementations run the same one.

This is a second implementation of a security control, which is normally a smell. It is acceptable because the *device's* copy is the control and the server's is a **liveness** check: a server-side false-accept cannot weaken the device, and a server-side false-reject surfaces as a 500 on the operator's own build. The two are pinned by a shared corpus file (§6.1a), and a divergence on any corpus entry is a build failure.

### 4.2 The GraphQL guard

`mobile/src/transport/gqlGuard.ts`. **This is the security control. Everything else is plumbing.**

**Zero imports** — the module must transpile-and-run under plain node, matching the proven idiom at `mobile/tests/check-espn-nav-policy.js:14-35`. Any `import` breaks the harness, which is exactly the enforcement we want on the one file that must be independently testable. A static test asserts `/^\s*import\s/m` does not match the source.

```ts
export type GuardRefusal =
  // Stage A — envelope
  | 'too_large' | 'bad_json' | 'duplicate_json_key' | 'escaped_body_key'
  | 'not_object' | 'unknown_body_key' | 'query_not_string'
  // Stage B — lexer
  | 'control_char' | 'unexpected_character' | 'spread_token'
  | 'unterminated_string' | 'unterminated_block_string' | 'too_complex'
  // Stage C — parser
  | 'fragment_definition' | 'bad_operation_type' | 'no_operation'
  | 'malformed_directive' | 'unbalanced_group' | 'depth_exceeded'
  | 'non_field_selection' | 'malformed_alias' | 'empty_selection_set'
  | 'trailing_tokens'
  // Stage C — the gate
  | 'reserved_field' | 'too_many_root_fields' | 'op_not_allowed';

export function guard(
  bodyBytes: Uint8Array,
  allowedOps: ReadonlySet<string> = DEVICE_OPS,   // on-device: always the compiled set
):  | { ok: true; opType: 'query'|'mutation'|'subscription'; rootFields: string[] }
    | { ok: false; reason: GuardRefusal };
```

Input is the **decoded `body_b64` bytes** — the exact bytes that will be sent. `guard()` takes bytes rather than a parsed object specifically so no caller can be handed the object and forget.

#### 4.2.1 Runtime primitives — named, because this codebase has never used them

The guard needs UTF-8 decoding with validation, and the transport needs base64 in both directions. **`TextDecoder`, `atob`, `btoa`, `Buffer`, and `base64-js` have zero occurrences in `mobile/src`** at `3b64a44`. Neither source draft named a source for any of them, and the gap is dangerous in a specific way: the test harness transpiles the guard and runs it under **plain node**, where `TextDecoder` is a global — so a green CI run proves nothing about Hermes on RN 0.81. If the global turns out to be absent on-device and someone substitutes a hand-rolled decoder, `fatal: true` disappears silently, and with it the rejection of overlong encodings and lone surrogates — inside the module this document calls the security control.

Required before S3, in this order:

1. **Establish what Hermes actually provides** for `TextDecoder` and base64 on the RN version in `mobile/package.json`. This is a device fact, so it joins §6.6.
2. If `TextDecoder` is absent, the "zero imports" rule forces a **hand-written UTF-8 validating decoder inside `gqlGuard.ts`**, which then needs its own corpus rows (overlong encodings, lone surrogates, truncated sequences, `U+FFFF`) — it becomes part of the security control, not a utility.
3. Any polyfill gets a `living-memory/DEPENDENCIES.md` entry. **The import-free rule binds only `gqlGuard.ts`** (§1.1), so a missing base64 global costs `platformTransport.ts` a dependency rather than a second hand-rolled primitive; only the UTF-8 decoder is trapped by (2).
4. Base64 decode failure has a typed refusal, `bad_base64` (§2.6), because §4.3 step 6 decodes inside a function specified never to throw.

Until step 1 is answered this is **OI-12**, and it gates S3 rather than S4: the guard cannot be called correct on a primitive nobody has confirmed exists.

#### Stage A — envelope

1. `bodyBytes.length > MAX_BODY_BYTES` → `too_large`.
2. UTF-8 decode with `fatal: true` (§4.2.1 names the implementation). Failure → `bad_json`.
3. **Scan for duplicate top-level JSON keys before parsing.** `JSON.parse` silently keeps the last value for a repeated key; a receiving server may keep the first. `{"query":"mutation{propose_trade…}","query":"mutation{evil}"}` therefore validates one document and executes another.
   **The scan must compare *unescaped* key text, not raw bytes.** A byte-comparing scan is defeated by a body whose first key spells `query` using a JSON unicode escape for its first letter — write it as `{"\u0071uery":"mutation{evil}","query":"<benign>"}`. `JSON.parse` unescapes that to `query`, last-wins leaves the benign document in `parsed.query`, and a scan comparing raw key *bytes* sees two different keys and flags nothing. Implement as a JSON string-lexer that decodes each top-level key before comparing. **Simplification permitted and preferred:** refuse outright any top-level key containing a `\`, since no legitimate body has one. Duplicate -> `duplicate_json_key`; escaped key -> `escaped_body_key`.
   **"Top-level" is determined by the same string-aware lexer**, tracking nesting so a key inside `variables` is not mistaken for one. Flagging a *nested* duplicate would be fail-closed and is acceptable, but both implementations must agree on the verdict, so the corpus carries a nested-duplicate row.
4. Parse. Must be a JSON **object**: `parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)` → else `not_object`. That is PRD rule 4's batching refusal, and it is a *type* check, not a special case. **The `null` arm is not pedantry** — `JSON.parse("null")` yields `typeof 'object'` and is not an array, so a two-clause check admits it and `parsed.query` then throws a `TypeError` out of a function specified never to throw (§2.6, §6.1c), producing an unreported outcome and an `unknown`.
5. **Top-level key allowlist:** the key set must be a subset of `{query, variables, operationName}` → else `unknown_body_key`. Real bodies always carry all three (`backend/sleeper_write.py:270-273`, `:357`). Without this the guard inspects `query` and nothing else, so an `extensions` key — GraphQL's persisted-query / APQ channel — would ride to Sleeper entirely unexamined and could name an operation the guard never sees. This is the same principle §2.2 applies to the lease request ("unknown top-level keys are a 400"), applied in the place it matters most.
6. `typeof parsed.query === 'string'` → else `query_not_string`. A `String` **object** fails this check and is refused, which is correct — the strict `typeof` is deliberate.
7. **`MAX_DOC_CODEPOINTS` — count of Unicode code points in `parsed.query`, 8_192** → else `too_large`. **Step 1 does not cover this:** it bounds the whole body against `MAX_BODY_BYTES` (65_536), so an 8_193-unit query inside a 10 KB body would otherwise be accepted while corpus case 21 demands refusal.

> **The unit is pinned, and the constant renamed, because an unstated unit is a guaranteed parity divergence.** `parsed.query.length` in JS counts **UTF-16 code units**; `len(s)` in Python counts **code points**; and a constant named `_BYTES` implies a third measure. A query with astral characters near the boundary would be allowed by one implementation and refused by the other — and neither the ASCII corpus nor the fuzz (which mutates two ASCII documents) could surface it, despite §6.1(a) declaring any divergence a build failure. Code points is the cheapest measure both sides compute identically without an encoder, which §4.2.1 does not name. In TS: `[...parsed.query].length`, **not** `.length`. Corpus carries a boundary-length row containing astral characters.

#### Stage B — lexer over `parsed.query`

Not a regex (PRD rule 2). Single left-to-right pass producing atomic tokens. **String literals become one opaque token**, which is what neutralizes the inlined-literal attack surface at `sleeper_write.py:263-268`.

Ignored tokens: space, tab, CR, LF, `,`, and `U+FEFF` anywhere. The GraphQL spec makes the BOM an ignored token; treating it as an error refuses a legitimate document, and treating it as a Name character lets it split an identifier.

- `#` starts a comment to the next line terminator — **only outside strings**.
- **`"""` is tested BEFORE `"`.** Ordering is load-bearing: read as a sequential algorithm with `"` first, `"""` lexes as an empty string followed by a stray quote, and the block-string body becomes live tokens. A block string ends at the first `"""` not immediately preceded by `\`. Block strings escape **only** `\"""`; a lone `\` is literal, so a generic backslash skip would let an attacker hide the closing delimiter.
- `"` starts a single-line string: `\` consumes the next character; an unescaped `"` ends it; a raw line terminator inside → `unterminated_string`. Skipping 2 on `\` is correct for every GraphQL escape — the longest is `\uXXXX`, and after skipping `\u` the four hex digits are ordinary characters. No escape's second character is `"` other than `\"`, which is precisely the one that must not terminate.
- Any code point `< 0x20` other than tab/CR/LF → `control_char`.
- `...` is emitted as **one token**, and **any `...` anywhere → `spread_token`**. One total rule covering fragment spreads *and* inline fragments; combined with refusing the Name `fragment` at definition position, it discharges PRD rule 1 without reasoning about where a spread might hide.
- Names match `/[_A-Za-z][_0-9A-Za-z]*/`. Numbers and strings are opaque tokens.
- Punctuators: `{}()[]:=|&@$!`.
- **Terminal branch: any character matching none of the above → `unexpected_character`. The lexer's final branch is a refusal and never a skip.** This closes the fail-open that an enumerate-what-is-valid spec invites. Without it an if/else scanner written from this section silently skips `;`, `%`, `?`, `'`, `..`, a stray `\`, U+00A0 and every other byte — the exact opposite of PRD rule 6 and §5.4 item 2 — and the TS and Python copies would each invent a different name for the case, which the shared corpus's `expect_reason` contract cannot absorb.
- After the scan, `tokens.length > MAX_DOC_TOKENS` → `too_complex`. A DoS bound, fail closed.

#### Stage C — single-definition parse

6. First token is a Name in `{query, mutation, subscription}` → that is `opType`, **consume it**. Else if it is `{` → `opType = 'query'` (anonymous shorthand), **peek only, do not consume** — step 10 needs to see that same `{`, and consuming it here makes shorthand refuse as `no_operation` instead of reaching the allowlist, contradicting corpus case 18. Else → `bad_operation_type`. The Name `fragment` at this position → **`fragment_definition`** (a named code, not "spread_token's sibling").
   **Shorthand is parsed, not special-cased.** It then fails the allowlist because `DEVICE_OPS` contains no `query:` pair. A dedicated "refuse shorthand" branch is one more branch to get wrong and breaks the moment release 2 adds a query op.
7. Optional operation Name — consumed and **discarded**. The label is non-authoritative (PRD R3-fix A). It is not even returned from `guard()`, so no caller can accidentally depend on it.
8. **The positional anchor.** Optional variable definitions: a balanced `(`…`)` group, balanced **over the token stream, not the raw text**. `_PROPOSE_TRADE_TEMPLATE` (`sleeper_write.py:204`) opens with `mutation propose_trade($k_adds: [String], …)`, so a naive "first `{`" reads a type name or a default-value literal. `($x: Foo = {a: "}"})` — a brace inside a string inside an object default — falls out correctly for free, because the lexer already made the string atomic.
9. Optional directives: `@` Name, optional balanced `(`…`)`. A directive argument may contain braces; same treatment. Malformed → `malformed_directive`.
10. Require `{` → else `no_operation`.
11. Root selection set, depth 1. Each selection:
    - must start with a Name → else `non_field_selection`;
    - **alias resolution:** if the next token is `:`, the token after must be a Name and **that** is the field. `propose_trade: some_other_mutation` resolves to `some_other_mutation`. Malformed → `malformed_alias`;
    - optional balanced `(`…`)` arguments;
    - optional directives;
    - optional nested `{`…`}` — skipped as a balanced group, **not descended into**, depth capped at `MAX_DOC_DEPTH` → `depth_exceeded`.
    - Unbalanced or EOF before balance → `unbalanced_group`.
12. On the matching `}`: `rootFields.length === 0` → `empty_selection_set`.
13. Any remaining token → `trailing_tokens`. This catches a string-literal breakout that closes the operation and appends `mutation { evil }`, and it is what refuses two operations in one document.
14. Any root field beginning with `__` → `reserved_field`. **A structural rule**, so `__typename` and `__schema` are excluded by construction rather than by set membership — I6 held by grammar, not by list hygiene.
15. `rootFields.length > 1` → `too_many_root_fields`. Every real document in-tree has exactly one, so the cap is free and strictly stronger than PRD rule 3.
16. **Every** `(opType, field)` pair must be in `DEVICE_OPS` → else `op_not_allowed`.

> Step 16 stays a loop over all fields even though step 15 caps the count at 1. The cap is **belt, not braces**. A reviewer removing the loop because "the cap makes it dead" would reintroduce the exact hole PRD rule 3 exists to close. The source comment says so.

#### `skipBalanced` — one definition, used by steps 8, 9 and 11

```
skipBalanced(tokens, at, open, close) -> { next: int, maxDepth: int }
```

Two properties the prose above would otherwise leave to the implementer, and both must be pinned because the TS and Python copies have to agree on the *refusal reason*, not merely on refusing:

- **A matched stack, not a kind-agnostic counter.** `( [ ) ]` refuses under either reading, but they produce different codes (`unbalanced_group` vs `non_field_selection`), and a mismatch between the two implementations is a §6.1(a) parity build failure. Push on `(`/`[`/`{`, pop only on the matching closer, mismatch → `unbalanced_group`.
- **It returns the maximum nesting it reached**, and **every call site checks it** — steps 8 (variable definitions), 9 (directive arguments) and 11 (nested selection sets). `maxDepth > MAX_DOC_DEPTH` → `depth_exceeded`.

> **This is what makes `MAX_DOC_DEPTH` real.** In the prose above the constant appeared once, inside a step that says the nested group is "not descended into" — no counter, no increment point, no origin — while corpus case 21 demands a depth-33 document be refused. Returning the depth from the skip is the only way the bound exists at all, and routing steps 8 and 9 through the same function is what stops an attacker from putting the nesting somewhere the check never looks.

EOF before balance → `unbalanced_group`.

#### Stage D — transmit the same bytes

The device POSTs `bodyBytes` verbatim. `JSON.parse` was inspection, never a transformation. A unit test asserts the sent buffer is reference-identical to the decoded buffer.

#### Refuse vs unrepresentable

"Unrepresentable" needs no code; "refuse" needs a test. The distinction is worth drawing explicitly.

| Input | Verdict | Why |
|---|---|---|
| Batched JSON array | **refuse** (`not_object`) | representable; a type check kills it |
| Duplicate `"query"` key | **refuse** (`duplicate_json_key`) | representable; needs an explicit scan |
| JSON `propose_trade` in the query string | **unrepresentable as an attack** | `JSON.parse` normalizes before the lexer runs |
| GraphQL `\u` escape inside a field **name** | **unrepresentable** | the GraphQL `Name` grammar admits no escapes |
| GraphQL `\u` escape inside a string | **no effect** | the lexer skips string interiors wholesale |
| BOM at start / mid-document | **ignored** | spec-ignored token |
| `#` inside a string | **no effect** | comment handling is string-aware |
| `{` or `}` inside an attacker-chosen `league_id` (`sleeper_write.py:265`) | **no effect** | lexer, not brace-count |
| Directive with `{}` in an argument | **no effect** | balanced skip over tokens |
| Operation with no name | **allowed** | the name was never authoritative |
| Shorthand `{ … }` | parsed as `query` → **refuse** at the allowlist | no special case |
| Fragment definition / spread / inline fragment | **refuse** | PRD rule 1 |
| Two operations in one document | **refuse** (`trailing_tokens`) | |
| `\"` then a real `"`; `\\` before `"` | handled | the classic off-by-one, both directions |
| Empty root selection set | **refuse** | PRD rule 1 |
| Unparseable anything | **refuse** | PRD rule 6, fail closed |

**Stated limit, so this section is not read as more than it is.** The guard bounds the **verb**, not the **object** (PRD §8). `league_id`, `k_adds`, `v_adds`, and `draft_picks` remain server-supplied. A compromised backend can drive a *sanctioned* `propose_trade` at any league and any assets with a live credential attached. M4 detects; it does not prevent. That is unavoidable given the transport invariant.

### 4.3 Device send sequence

```
 1. env = readEnvelope(currentUserId);  null      -> refuse 'no_credential'
 2. lease.epoch === env.epoch                     -> else refuse 'stale_epoch'
 3. URL: https scheme, no userinfo, hostname in ALLOWED_HOSTS -> else 'host_not_allowed'
 4. method in ALLOWED_METHODS                     -> else 'method_not_allowed'
 5. headers lowercased: in ALLOWED_HEADERS, no dup, printable-ASCII values
      'authorization' present -> 'auth_header_present'   [I4, distinct code]
      anything else           -> 'header_not_allowed'
 6. bodyBytes = base64Decode(lease.request.body_b64)
      decode failure          -> 'bad_base64'      [typed; this fn must never throw]
      len > MAX_BODY_BYTES    -> 'body_too_large'
 7. guard(bodyBytes)                              -> else 'guard_refused' + guardReason
 8. lease.credential_user_id === env.user_id      -> else 'user_mismatch'   [I5]
 9. AppState === 'active'                         -> else 'not_foreground', report
                                                        'aborted_before_send' and STOP
10. fetch(url, { method, headers, body: bodyBytes,
                 signal: AbortSignal.timeout(min(lease.limits.timeout_ms, HARD_TIMEOUT_MS)) })
    ONE attempt. No retry, ever. No offline queue for a credentialed call (PRD §8).
11. read at most MAX_RESPONSE_BYTES; set `truncated`
12. POST /api/platform/outcome   (retryable — §4.4)
```

**The credential is attached at step 10 and only at step 10.** It is never written into the header map that step 5 validated, so a bug in step 5 cannot leak it and a bug in step 10 cannot bypass step 5.

```ts
headers[cred.header] = cred.scheme === 'bearer' ? `Bearer ${cred.token}` : cred.token;
// Sleeper is RAW — sleeper_write.py:288-293
```

`lease.expires_at` is **not consulted anywhere in this file**; it drives a UX string only (I2 — a device clock is owned by the party the lease bounds). No `_BROWSER_HEADERS` port: Sleeper's edge accepts iPhone requests PASS 4/4 and PRD §2.4 forbids it.

Any refusal at steps 1–9 reports to `/outcome` **before anything reaches the network**, so the digest lock releases immediately.

**Step 2 is in neither source doc.** Without it, a lease minted before a disconnect-and-relink can be executed against the new credential. It costs one integer comparison. It is a *distinct* refusal from `no_credential` — conflating them would tell the user "not connected" when they are.

**The invariant, pinned statically:** there is no code path from the send module to `executeLease` that does not pass through a 200 from `/lease`. `check-no-lease-no-call.js` (§6.2) enforces it, replacing a client-self-reported metric with a code invariant.

### 4.4 Outcome handling and idempotency

**Device side.** `/outcome` is retried up to 3 times with backoff **400 ms / 1.2 s / 3.6 s — the `RETRY_BASE_MS` × `RETRY_FACTOR` ladder at `mobile/src/api/client.ts:249-250`**, *not* `SESSION_INIT_BACKOFF_MS`, which is `[400, 1200]` (two retries, ~1.6 s) at `client.ts:269`. If all fail, the report is **queued to AsyncStorage and re-sent on next foreground**: bounded at 20 entries, drops oldest, holds no credential. The queue exists because an unreported outcome becomes `unknown`, and `unknown` is the state that sends a user to check Sleeper by hand for a send that in fact succeeded.

**Making this POST retryable is a real client change, not a list edit.** `canRetry` hard-codes `method === 'GET' && !NO_RETRY_PATHS…` at `client.ts:453-455`; `NO_RETRY_PATHS` (`client.ts:240-246`) is an exclusion list that never applies to POSTs, and `RequestOptions` (`client.ts:281-289`) has no opt-in field. Add one named option that both opts this POST in **and raises the cap** — `MAX_RETRIES = 2` (`client.ts:248`), so a 3-attempt ladder needs it — scoped so it **cannot widen retry for any other POST**, and cite both the constants block and the enforcement site in the code comment. `/lease` must **not** be retried — a retried lease is a second lease.

**Server side**, a single conditional statement, never read-then-write:

```sql
UPDATE platform_leases
   SET state=:new_state, late=:late, epoch_stale=:stale, settled_at=:now,
       digest_lock=NULL, http_status=:hs, transaction_id=:tid,
       platform_error=:perr, guard_reason=:greason
 WHERE lease_id=:lease_id AND state IN ('issued','unknown')
```

The `IN ('issued','unknown')` predicate is the concrete expression of I2, and getting it wrong is easy and silent: a `WHERE state='issued'` looks right and rejects exactly the late reports the design exists to accept.

`rowcount == 1` → first report. Classify; if `root_field='propose_trade'` and `result='ok'`, parse `response_b64` **server-side** (I1) — including the **GraphQL-200-with-`errors`** case (`backend/sleeper_write.py:325-331`), the failure mode most likely to be misread as success — then fire `_record_send_success` (`backend/server.py:12524`, called at `:12680`) and `_save_deck_outcome_safe`.

`rowcount == 0` → already settled. Re-read, return the recorded row unchanged with `duplicate: true`. **Do not re-fire analytics.** `_record_send_success` runs exactly once, guarded by the rowcount, not by an application-level "have I seen this."

**Per-result behaviour**

| `result` | State | Lock | Note |
|---|---|---|---|
| `aborted_before_send` | `aborted` | released | The only result reachable *without* the request leaving the device. Backgrounding between lease and send must not lock the user out for ~10 minutes on a send that never happened. **Carries `refusal: 'not_foreground'`** — the one case where `refusal` accompanies a result other than `'refused'`, because the foreground guard is a `SendRefusal` but the outcome is an abort, not a refusal. §2.3's "iff `result === 'refused'`" is relaxed to "iff `result` is `'refused'` or `'aborted_before_send'`". |
| `refused` | `refused` | released | **Every one of §2.6's ten `SendRefusal` values maps here**, stored in `platform_leases.refusal`, with `guard_reason` populated only when `refusal === 'guard_refused'`. Never reached the platform. `guard_refused`, `auth_header_present`, `host_not_allowed`, `method_not_allowed` and `header_not_allowed` are **M4 incidents** and page the operator; `no_credential`, `stale_epoch`, `not_foreground`, `body_too_large` and `bad_base64` are ordinary and must not. |
| `network_error` | `failed` | released | Did not reach the platform, or we cannot tell. `unknown` is reserved for a **missing** report (HLD blocking fix 2). |
| `http_error` / `ok` | `failed` / `ok` | released | Server parses and classifies — but see the truncation rule below. |

**Truncation is not failure.** A `truncated: true` body with a 2xx status fails `json.loads` and would classify as `failed` through the non-JSON arm at `sleeper_write.py:322` — reporting a **successful send as a failure**, the exact error §5.1 says the copy must never make. Rule: `truncated == true` with a 2xx never yields `ok` **or** `failed`; it takes the `network_error` copy ("check Sleeper before resending"). `MAX_RESPONSE_BYTES` also needs measuring, because the `propose_trade` selection set returns `metadata`, `settings`, and `player_map` (`sleeper_write.py:207-210`) — OI-13.

**The required refactor — and it is not a verbatim extraction.** `parse_graphql_response(op, raw_bytes, http_status)` takes over the parts of `sleeper_write._post_graphql`'s response half (`backend/sleeper_write.py:308-335`) that are pure functions of bytes and status: the non-JSON guard, the `errors`-on-200 handling with its auth-keyword sniff, the 401/403 → `SleeperAuthError` mapping, and the `{transaction_id, status, raw}` shape. `_post_graphql` then *calls* it.

**What must stay behind**, because it cannot move: the `urllib.error.HTTPError` / `URLError` arms (`:308-317`) operate on **exception objects**, not bytes — the caller converts them to a status before calling — and `_ob.ok(status=200, response_bytes=len(raw))` at `:333` is bound to the `observe_call` context opened at `:302-304`. **The device path must not fire `api_observability`**, or every device send records a phantom server-side outbound Sleeper call and the egress telemetry becomes a fiction. State the split in the docstring.

This is what makes A3's R-ROLLBACK real: the server path and the device path interpret Sleeper's responses through **one** function, so the recovery path cannot bit-rot into a different parser while nobody is looking.

**R8 — credential invalidation.** `http_error` with status ∈ {401, 403}, or an `ok` response whose `errors` array matches the auth heuristic at `sleeper_write.py:329`, sets `platform_links.rejected_at`. Subsequent `/lease` calls return `409 credential_rejected` — deliberately distinct from `no_device_credential`, so the client prompts re-capture rather than "not connected." The vault is **not** wiped: a single 401 is not a user decision, and only an explicit disconnect wipes. **This deliberately diverges from the server path**, which deletes the credential outright on `SleeperAuthError` (`backend/server.py:12650`) and on expiry (`:12615`). The divergence is the point — the server could always re-obtain a token by prompting; under device custody the wiped copy is the only one. Stated explicitly because an earlier draft claimed this "mirrors" the server path, and a reader who checked the cite would have concluded one of the two was wrong.

### 4.5 Sticky revocation — every caller that must change

HLD blocking fix 5 says ordering is the fix. **Ordering alone is insufficient, and the caller list is longer than the HLD's single citation.** Every consumer of `GET /api/sleeper/link`'s `connected`:

| # | Site | Today | Under device custody | Required change |
|---|---|---|---|---|
| 1 | `mobile/src/api/sendInSleeper.ts:153-158` (`_runReplay`) | `!connected` → `clearPersistedSleeperToken()` | **erases the credential the design depends on** | key the wipe off `revoked === true` instead of `!connected`. **That is the only change at this site — the replay itself stays unconditional.** See the warning below. |

> **The replay must NOT be skipped under device custody, and an earlier draft of this section said it should.** `POST /api/sleeper/link` is what sets `sess["verified"]` (`backend/server.py:12491`), and `/lease` step 4 hard-requires it (§4.1). For a Sleeper-only user that route is the only thing that can verify their session — provider auth (`server.py:18425`, `:18446`) and the MFL oracle (`:21392`) also set the flag, but a Sleeper-only user reaches none of them. Skipping the replay would make the first send after any new session token return `403 verification_required` with no client-side recovery, which is the feature not working at all. §2.4 already says the device replays "on every fresh session"; this row must not contradict it.
| 2 | `mobile/src/api/sendInSleeper.ts:54-58` (`unlinkSleeper`) | DELETE then wipe local | correct intent | also `wipeEnvelope()`, drop queued outcomes; server bumps `epoch` |
| 3 | `mobile/src/components/SendInSleeperButton.tsx:184-201` | post-webview focus check → "Not connected"; `connected = !!status.connected && !status.expired` at `:185` | false negative | same union / `revoked` logic, **and** `expired` becomes advisory — the device holds the live token, so the server's staleness hint must not gate the send |
| 4 | `mobile/src/components/SendInSleeperButton.tsx:379-402` | pre-send gate → "Connect Sleeper first"; same `!status.expired` conjunct at `:380` | **feature silently dead** | same as row 3, plus route to `/lease` when `custody==='device'` |
| 5 | `mobile/src/screens/SettingsScreen.tsx:1127-1128` (the render gate; `:286-292` is only the `useQuery`) | `connected:false` → the disconnect row does not render | **the user cannot disconnect at all** | union — and this is a **policy** failure, not a UX one: that row is the "disconnect at any time" control (`SettingsScreen.tsx:495-498`) |

**Five sites, not six.** An earlier draft listed the `expired` conjunct as a sixth site citing `sendInSleeper.ts:185`/`:380` — that file is 238 lines, so those line numbers cannot exist in it, and `sendInSleeper.ts:159-160` says the opposite in as many words ("`expired: true` describes the server's copy and does not short-circuit"). The real conjunct lives inside rows 3 and 4, which is where the requirement is now folded. Left as its own row it would have been implemented against the wrong file and quietly dropped.

**The old-binary set.** Sites 1, 3, 4, 5 ship in every TestFlight build up to and including `1.13.2` (`mobile/app.json:5`) and **cannot be fixed** — no OTA (PRD §3 non-goals). What §2.5's union contract buys them is precisely one thing: **the credential is not erased** (site 1). It does not keep the feature working. An old binary reads `connected: true`, replays its JWT to `POST /api/sleeper/link` (site 1 → `sendInSleeper.ts:170`), then sends via `POST /api/trades/propose`, which reads `get_sleeper_credential` (`backend/server.py:12607-12609`) and returns `409 sleeper_not_linked` when no token row exists.

**Therefore the token-write suppression is keyed on the declared capability, not a global flag** (§1.5c, §2.4). A `transport_v = 0` client keeps getting a token row and keeps sending server-side. A `transport_v ≥ 1` client gets device custody. Both work simultaneously on the same server — which is also exactly what A3's R-ROLLBACK requires: the server path stays live and exercised.

**One residual with no clean fix.** A user on a new binary who reinstalls an old build (TestFlight allows this) has a `platform_links` row and no `sleeper_credentials` row. The old build sees `connected: true`, replays, and — sending `transport_v = 0` — **restores** the server-side token row. The user silently returns to server custody. That is the correct failure direction (working feature, weaker custody) but it must be written down, because M1 ("zero token rows in the build cohort") can go non-zero without an incident. OI-4.

### 4.6 Concurrency

| Scenario | Mechanism | Outcome |
|---|---|---|
| Two taps, same trade, one device | `UNIQUE(digest_lock)` — the second INSERT raises before any row exists | one 200, one `409 send_in_flight` with the holder's `lease_id` and `retry_after_s`. No read-then-write window. |
| Two devices, same trade | same; `device_id` is deliberately **not** in the digest | exactly one device sends |
| Two devices, different trades | different digests | both proceed, bounded by `MAX_OUTSTANDING_LEASES` |
| Background between lease and send | `aborted_before_send` releases the lock immediately | retap works at once |
| `/outcome` times out, device retries | idempotent by `lease_id`, in `SLOW_POST_PATHS` | second POST returns the recorded row, `duplicate: true`. A cold start never turns a successful send into "go check Sleeper." |
| Late outcome vs digest-window expiry | sweep stamps `unknown` + releases the lock; `unknown` is the one amendable state | accepted, `late: true`. **Residual:** if the user retapped in the gap, two real offers exist. 10 min is the operator's dial — OI-6. |
| Epoch bumped mid-flight | lease carries its minting epoch; device refuses at §4.3 step 2; server flags at report | `epoch_stale: true` |
| Sweep vs concurrent outcome | sweep predicate is `state='issued'` | whichever commits first wins; the other is a no-op |

### 4.7 Sweep

A cron pass on the existing `CRON_SECRET`-guarded `/api/cron/*` surface, every 5 minutes:

- `state='issued' AND now > digest_until` → `state='unknown'`, `digest_lock=NULL`. Releases the in-flight lock.
- `issued_at < now - LEASE_RETENTION` → delete. Without this `platform_leases` is unbounded.
- `platform_lease_reports` older than `LEASE_RETENTION` → delete.

---

## 5. Error Handling

### 5.1 The classification that matters

Three device outcomes are genuinely different and are routinely collapsed into one:

| Device saw | Reported | User-facing | Why distinct |
|---|---|---|---|
| 200, `data.propose_trade.transaction_id` present | `ok` | "Sent" | |
| 200 with `errors[]` (`sleeper_write.py:324-331`) | `ok`, server classifies | "Sleeper rejected this trade: …" | GraphQL puts failures in a 200 |
| Network error / timeout | `network_error` | "Couldn't reach Sleeper — check Sleeper before resending" | the send **may** have landed |
| No report after `DIGEST_WINDOW` | `unknown` (swept) | same copy | |

**Honest limit:** `network_error` and `unknown` are indistinguishable to the user, and FTF cannot tell them apart either — the device is forbidden from reading the response (I1) and the only authenticated pending-read that could resolve it is unexplored (OI-8). **The copy must not claim a send failed.**

### 5.2 Unhandled paths this design inherits

- **`_fetch_league_rosters` failure at lease time.** `/api/trades/propose` calls it at `backend/server.py:12621` and handles only "roster not found" (`:12623`, `:12633`); a network failure inside it is uncaught. Moving roster resolution into `/lease` inherits that gap, so `/lease` wraps it and returns `503 platform_unreachable`. Otherwise a Sleeper blip becomes a 500.
- **FAAB `json.dumps` emits quoted keys** (`sleeper_write.py:267`) — invalid GraphQL object-literal syntax, dormant only because nothing populates FAAB. Once the strict lexer ships, its behaviour on such a body is *undefined by inspection*: the invalid part sits inside an argument group the guard skips, so it may **parse** and then be rejected by Sleeper as a 200-with-`errors` — the worst outcome, a lease burned on a body that could never work. **Fix before the guard lands** (§7.0), and pin both the pre-fix and post-fix bodies in the corpus so the sequencing dependency is visible in CI.
- **Sentry.** `Sentry.init` runs at `mobile/src/observability/sentry.ts:41` with `tracesSampleRate: 0.2` (`:45`), and there is no `beforeSend` or `beforeBreadcrumb` anywhere in `mobile/src`. A transport that attaches `authorization` creates a credential-leak path into a third-party SaaS that does not exist today. Required as a net-new block and a **gate on the first transport merge**: `beforeBreadcrumb` drops any `fetch`/`xhr` breadcrumb whose hostname is in `ALLOWED_HOSTS`; `beforeSend` deletes `event.request.headers` and `event.request.data` unconditionally; `tracePropagationTargets: []` so no `sentry-trace`/`baggage` header is injected into a platform request. Per HLD blocking fix 3, verified against a **real capture with tracing forced to 1.0** — at 0.2, a single clean send proves close to nothing.
- **Keychain write failure is swallowed today** (`sendInSleeper.ts:85-87`). Under device custody a swallowed failure means the user appears linked and every send refuses with `no_credential`. `writeEnvelope` returns `false`; the connect flow surfaces "Couldn't save your Sleeper sign-in on this device" and does **not** mark the link successful.

### 5.3 Device-side typed errors the client must distinguish

| Code | Origin | Reached Sleeper? | Retryable | Client behaviour |
|---|---|---|---|---|
| `no_credential` | vault has nothing for this user | no | after re-capture | Prompt Connect. **Distinct from `credential_rejected`:** nothing was ever there, versus it was and the platform said no. |
| `stale_epoch` | §4.3 step 2 | no | after re-link | Silent re-lease once, then prompt. |
| `credential_rejected` | R8, from the server's parse | **yes** | after re-capture | Server has set `rejected_at`; the next lease 409s. Prompt re-capture, do **not** wipe. |
| `send_in_flight` | `UNIQUE(digest_lock)` | no | after `retry_after_s` | Not an error state in the UI. **The copy must not assert a send is in progress** — a lease orphaned by an app *kill* generates no report, so §4.4's queue is empty and the lock is held for the full `DIGEST_WINDOW` with nothing actually sending. Say "this trade was already submitted — check Sleeper before resending," and surface `retry_after_s`. |
| `upgrade_required` | D3 capability negotiation | no | **no** | Alert + App Store link. **Never a silent fallback** — that would hide the skew D3 exists to make visible. |
| `guard_refused` | a compiled device guard | **no** | **no** | Deep-link fallback + report. **Any occurrence is an M4 incident.** Never auto-retried — retrying a refused document is retrying an attack. |

There is deliberately **no `lease_expired`**. `expires_at` is UX only and the server never rejects on it; a stale lease surfaces as a normal outcome with `late: true`.

### 5.4 Fail-closed inventory

Each must be a test, because each is a place where a plausible refactor turns a refusal into a permit:

1. Unknown `X-FTF-Caps` fingerprint → treated as no capability.
2. Unparseable GraphQL document → refuse (PRD rule 6).
3. `_TEST_MODE` → `/lease` 599.
4. Missing `X-Device-Id` → 400, not "any device."
5. Guard self-check failure at lease build → 500, no lease issued.
6. `ux_platform_leases_digest_lock` **or** `ck_platform_leases_lock_matches_state` missing at startup → **startup error**, not a warning. A missing in-flight index is a silent duplicate-send bug, and `create_all` is a no-op against a pre-existing table (a dev DB from an earlier branch), so the CHECK — §3.2's only enforcement of the lock/state equivalence — can be silently absent while the index assertion passes.

---

## 6. Testing

### 6.1 The guard — what actually proves it correct

A hand-written case list proves the cases someone thought of, not the parser. Three layers.

**(a) Shared corpus, both implementations.** One file, `backend/tests/fixtures/gql_guard_corpus.json`, consumed by the TypeScript guard test and by the Python parity guard (§4.1 step 12). Each entry: `{name, query, body_override?, expect: 'allow'|'refuse', expect_reason?, expect_root_fields?}`. **A divergence between the two implementations on any entry is a build failure.** This is what keeps the parity check honest.

Minimum corpus, all **failing-first**:

| # | Case | Expect |
|---|---|---|
| 1 | Fragment-spread with an empty root set: `mutation { ...E } fragment E on Mutation { propose_trade { status } }` | refuse (`spread_token`). **A single operation whose root set contains no field**, so an "every root field is allowlisted" check passes vacuously over the empty set. |
| 2 | String-literal breakout via attacker-chosen `league_id` = `1") { status } evil_mutation(x: "` inlined at `sleeper_write.py:265` | refuse; assert `evil_mutation` appears in `rootFields` when the cap is lifted |
| 3 | Array-batched body `[{"query":"mutation{propose_trade}"},{"query":"mutation{evil}"}]` | refuse (`not_object`) |
| 4 | Alias `mutation { propose_trade: some_other_mutation(...) { status } }` | refuse, **and `rootFields === ['some_other_mutation']`** — the assertion is on the resolved name. A parser returning `['propose_trade']` would *accept*. |
| 5 | Real `_PROPOSE_TRADE_TEMPLATE` output (`sleeper_write.py:203-211`) | allow, `['propose_trade']` |
| 6 | Real `reject_trade` document (`sleeper_write.py:352-356`) | allow, `['reject_trade']` |
| 7 | `verify_token_live`'s `query ftf_token_probe { __typename }` (`sleeper_write.py:191`) | **refuse** (`reserved_field`) — pins I6 so nobody re-adds it to make the oracle "work" through the transport |
| 8 | `league_players` query (`trade_block_service.py:73`) | refuse (`op_not_allowed`) |
| 9 | FAAB-populated `propose_trade` **after** the §7.0 fix | allow |
| 10 | FAAB-populated body **before** the fix | pinned either way, so the sequencing dependency is visible in CI |
| 11 | Duplicate `"query"` JSON key, literal | refuse (`duplicate_json_key`) |
| 11a | **Escaped duplicate key** `{"\u0071uery":"mutation{evil}","query":"<benign>"}` | refuse (`escaped_body_key`). **The one that defeats a byte-comparing scan:** `JSON.parse` unescapes the first key to `query`, last-wins leaves the benign document in `parsed.query`, and a raw-byte scan sees two different keys. Without this row the hole ships green. |
| 11b | Body with an `extensions` key (APQ / persisted query) | refuse (`unknown_body_key`) |
| 11c | Body is literal `null`; body is `"a string"`; body is `123` | refuse (`not_object`) ×3 — `null` is the one a two-clause type check admits, after which `parsed.query` throws |
| 12 | BOM prefix; BOM mid-document | allow ×2 |
| 13 | `#` inside a string; `}` inside a string; `"""` block string containing `{` | allow ×3 |
| 14 | `\\` before a closing quote | allow |
| 15 | Unterminated string; unterminated block string | refuse ×2 |
| 16 | Directive with a brace in an argument; variable default `= {a: "}"}` | allow ×2 |
| 17 | Anonymous `mutation { propose_trade(...){...} }` | allow |
| 18 | Shorthand `{ propose_trade }`; `subscription { propose_trade }` | refuse ×2 |
| 19 | Two root fields both allowlisted; `mutation { propose_trade(...){...} __typename }` | refuse ×2 |
| 20 | Trailing `mutation { evil }` after a valid operation; empty selection set `mutation { }` | refuse ×2 |
| 21 | 8 KiB + 1 document; depth 33; NUL byte outside a string | refuse ×3 |
| 22 | JSON `propose_trade` escaped field name | **allow** — pins the "unrepresentable" claim |

**(b) Differential oracle.** A dev-only test parses every corpus entry with `graphql-js`'s `parse()` and asserts (i) for `allow` entries the extracted `(opType, rootFields)` equals what `graphql-js` reports, and (ii) every entry `graphql-js` cannot parse is refused. This turns "we think our lexer is right" into "it agrees with the reference implementation." `graphql` is **not** a mobile dependency today (`mobile/package.json`); adding it as a `devDependency` needs a `living-memory/DEPENDENCIES.md` entry and it must never enter the app bundle. OI-5.

**(c) Fuzz — differential, not self-referential.** 10k seeded byte-level and token-level mutations of the two real documents, fed to **both** implementations. Assertions:

1. `guard()` **never throws**. An exception on the send path becomes an untyped outcome and then an `unknown`.
2. For every input where `guard()` returns `ok`, **`graphql-js.parse()` must also succeed and its `(opType, rootFields)` must equal the guard's**.
3. The TS guard and the Python parity guard return the same verdict *and the same reason*; any divergence is auto-appended to the shared corpus.

> **Assertion 2 is the one that matters, and an earlier draft omitted it.** The weaker check — "never returns `ok` with a pair outside `DEVICE_OPS`" — is passed by a guard that parses `mutation { propose_trade(...){...} evil(...){...} }` and returns `ok, rootFields: ['propose_trade']`, silently dropping the second field. That is precisely the parser-differential the whole control exists to prevent, and 10k mutations would never flag it. A self-referential oracle cannot detect the only bug class that matters.

**Corpus case 10 is exempt from assertion (ii) of (b)** and is deleted once §7.0 lands: the pre-fix FAAB body is rejected by `graphql-js` (quoted keys in an object literal) while the specified algorithm skips it inside a balanced argument group and returns `ok`. The corpus schema carries an explicit `oracle_exempt: true` for it, so the exemption is visible rather than a mystery failure.

**(d) Enum coverage, statically asserted.** Every member of `GuardRefusal` must appear as some corpus entry's `expect_reason`, **and every member of `SendRefusal` must appear in some §6.3 transport test** — `SendRefusal` has no coverage rule at all today. The table above leaves roughly nine untested (`bad_json`, `query_not_string`, `bad_operation_type`, `no_operation`, `non_field_selection`, `malformed_alias`, `malformed_directive`, `unbalanced_group`, `too_complex`, plus the newly added `unexpected_character`, `unknown_body_key`, `escaped_body_key`, `fragment_definition`), and an untested refusal path is one a refactor can delete without failing anything. The assertion makes the enum and the corpus unable to drift.

Harness: `mobile/tests/check-gql-guard.js`, transpiling the real TS with the project `typescript` and running under plain node (`mobile/tests/check-espn-nav-policy.js:14-35`).

### 6.2 Other pinned invariants

| Test | Pins |
|---|---|
| `mobile/tests/check-no-lease-no-call.js` | Static: `executeLease` is called from exactly one site, after a 200 from `/lease`. A code invariant replacing a self-reported metric. |
| `mobile/tests/check-vault-subsumes-legacy.js` | After `migrateLegacySlot`, `getItemAsync('sleeper.link.jwt')` is `null` and the envelope carries the token; on a write failure the legacy key is **retained**. |
| `mobile/tests/check-keychain-accessible.js` | Static: every `SecureStore.setItemAsync` under `mobile/src/transport/` passes `WHEN_UNLOCKED_THIS_DEVICE_ONLY`. |
| `mobile/tests/check-sticky-revocation.js` | `revoked: true` wipes; `connected:false, revoked:false` **retains**. The cutover regression, pinned. |
| **Old-binary regression** | Vendor the `v1.13.2` copy of `sendInSleeper.ts` as `mobile/tests/fixtures/legacy-sendInSleeper-1.13.2.ts`, drive `_runReplay` against a mock serving the **new** `GET` contract, assert `clearPersistedSleeperToken` is **not** called. The only way to prove old-binary safety without an old binary — and it fails the moment someone "simplifies" the union in §2.5. |
| `backend/tests/test_request_digest.py` | Invariant under dict insertion order; **varies** when a list order changes (`k_adds` reordered ⇒ different digest — list order is semantic); a NUL in any component raises; `b64decode(body_b64) == the bytes hashed`. |
| `backend/tests/test_platform_link_contract.py` | `GET` with only a `platform_links` row → `connected:true, revoked:false, custody:'device'`; after `DELETE` → `connected:false, revoked:true`, epoch incremented; `POST` with no `X-FTF-Caps` writes `sleeper_credentials`; `POST` with `transport_v=1` + flag on writes `platform_links` and `get_sleeper_credential` returns `None`; `sess["verified"]` is set in **both** branches. |
| `backend/tests/test_rollback_server_path_ci.py` | **A3's "and in CI" clause.** Exercises `sleeper_write.propose_trade` via `POST /api/trades/propose` against a stored credential with an injected `_opener`. The cutover rehearsal is one-time; bit-rot is continuous. |
| `backend/tests/test_graphql_response_parse.py` | `parse_graphql_response` is the single interpreter: same input ⇒ same result via `_post_graphql` or `/outcome`; 401 ⇒ `SleeperAuthError` ⇒ `credential_rejected`; 200-with-`errors` is not read as success. |

### 6.3 Races

Real threads against the real engine — a mocked DB proves nothing about a unique index.

| Test | Asserts |
|---|---|
| Two concurrent `/lease`, identical args | exactly one 200, one `409 send_in_flight` |
| Two concurrent `/outcome`, same `lease_id` | both 200, identical bodies, `_record_send_success` called **once** |
| `/outcome` after `expires_at` | `200 {state:'ok', late:true}` — **not** rejected (I2) |
| `/outcome` after the sweep set `unknown` | accepted, `late:true`, state amended |
| `/outcome` from a different `device_id` / session user | 403, lease state unchanged, report row with `rejected_reason` |
| `MAX_OUTSTANDING_LEASES + 1` | last 409, **no orphan row** |
| `DELETE` racing an issued lease | epoch bumped; device refuses at §4.3 step 2 |
| `aborted_before_send` | lock released; an immediate re-lease succeeds |

### 6.4 Rails — a gate on the first transport merge, not a follow-up

`mobile/scripts/sim-run.sh:178` exits 4 on `vcr_misses`, `sleeper_live_egress_attempts`, `completed_proposes`. **The latter two go vacuous the moment the server stops being the sender** (`backend/test_support.py:80,82`) — they will keep reporting green for the wrong reason. In the **same PR** that lands the transport:

| Counter | Gate |
|---|---|
| `vcr_misses` | `== 0` (unchanged) |
| `leases_issued_under_test` | `== 0` — `/lease` fails closed under `_TEST_MODE`, so any lease is a defect |
| `device_outcomes_refused` | `== 1` — **the negative control** |
| `device_outcomes_sent` | `== 0` |

**The negative control:** one deliberate lease per run whose URL points at a sinkholed host, driven through `/__test__` injection. It must be **blocked and counted** — the device refuses (`host_not_allowed`) and reports, and the server counts. Without it a misconfigured fence yields a green run with real egress. The counter is server-side because a device-side counter is unreportable by a client that is by definition misbehaving; a client that goes silent instead is caught by M8's lease-vs-outcome divergence.

### 6.5 Maestro

Per the feature gates, `mobile/.maestro/flows/trade-send/sleeper-device-transport.yaml`, sibling to `mfl-send-gating.yaml`. `testID`s must pass `mobile/scripts/testid-lint.sh`; authoring follows the 23 laws in `mobile/.maestro/README.md`.

**Scoped to what is observable under `_TEST_MODE`, which is less than it looks.** An earlier draft specified "flag on ⇒ lease requested, guard passes, outcome reported" — unachievable: §4.1 step 1 fails `/lease` closed with `599` under `_TEST_MODE`, and §6.4 gates the run on `leases_issued_under_test == 0` ("any lease is a defect"). That flow either cannot pass or trips the rails gate it runs beside. The flow therefore covers:

- flag off ⇒ server path, **no lease requested**;
- `599` handling ⇒ the send falls back cleanly, no crash, no misleading copy;
- `426` ⇒ the upgrade alert renders;
- the sticky-revocation regression (`revoked: true` wipes, `connected:false, revoked:false` retains);
- the injected negative control from §6.4.

**Injection must deliver a mocked 200 through the same `/lease` call site**, not a second entry point into `executeLease` — otherwise it becomes a second call site and breaks §6.2's static `check-no-lease-no-call.js` invariant, which is the thing actually guaranteeing no unauthorized egress.

### 6.6 Provable only on device

Stated plainly so nobody claims coverage they do not have:

1. `WHEN_UNLOCKED_THIS_DEVICE_ONLY` actually excluding the item from an iCloud backup.
2. Cloudflare's acceptance of iOS's TLS/HTTP-2 fingerprint under real load (R7 — no device-side fix, no hotfix; the remedy is R-ROLLBACK). Note §3.5's `serialize_body` also changes the **wire bytes** of the one call proven live: `_post_graphql` currently sends `json.dumps(body)` with insertion order `operationName, variables, query` and `", "`/`": "` separators (`sleeper_write.py:284`), described in-code as "verbatim structure from the capture" (`:196`), while canonicalization emits sorted keys and tight separators. Almost certainly irrelevant — Cloudflare fingerprints TLS and HTTP/2, not JSON whitespace — but R7 is this programme's decisive risk and the change should not be invisible.
3. Sentry's real breadcrumb and header behaviour on a live send with tracing at 1.0. **The capture must come from a release build with the rate overridden**, not a dev build: `tracesSampleRate` is `__DEV__ ? 1.0 : 0.2` (`sentry.ts:45`), so dev is already 1.0 and proves nothing about the release path.
4. **Whether Hermes provides `TextDecoder` and base64 at all** (§4.2.1 / OI-12). CI runs the guard under plain node, where these are globals; that result does not transfer.
5. Keychain survival across app update and across delete-and-reinstall ("uninstall is not revocation").
6. The `AppState` transition timing that drives `aborted_before_send`.
7. Whether a real old binary (`1.13.2` from TestFlight) leaves its credential intact against the new `GET` contract. §6.2's fixture test is a proxy, not a substitute.

---

## 7. Migration & Sequencing

### 7.1 What A2 removed and what it did not

A2 withdraws the phased credential migration; A3 restores the server path as a recovery capability. What remains is **not a credential migration** — it is a **contract migration**, and it has a hard ordering constraint because old binaries cannot be fixed.

### 7.0 The FAAB fix — sequenced before the parser

`build_propose_trade_body` inlines `json.dumps(req.waiver_budget or [])` (`sleeper_write.py:267`), emitting `[{"sender": 1, …}]` — **quoted keys, invalid GraphQL object-literal syntax**.

```python
def _graphql_object_literal(v) -> str:
    """GraphQL object literals use BARE keys. json.dumps quotes them, which is
    invalid syntax. Values still use JSON encoding (strings quoted, numbers bare)."""
    if isinstance(v, dict):
        return "{" + ",".join(f"{k}:{_graphql_object_literal(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ",".join(_graphql_object_literal(x) for x in v) + "]"
    return json.dumps(v)
```

Key names must be validated against `/^[_A-Za-z][_0-9A-Za-z]*$/` and rejected otherwise — a bare key is unquoted, so an unvalidated key is a direct injection into the query text.

### 7.2 Ordered stages

| # | Ships | Reversible | Gate to leave |
|---|---|---|---|
| **S0** | §7.0 FAAB fix; Sentry scrub; `keychainAccessible` read-then-rewrite; vault subsumes and deletes `sleeper.link.jwt` | yes | independent of the programme (PRD §10). `check-vault-subsumes-legacy.js` green |
| **S1** | `platform_links` + `platform_leases` + `platform_lease_reports` via `create_all`; startup assertion on `ux_platform_leases_digest_lock` | yes | index assertion passes on both dialects |
| **S2** | **`GET /api/sleeper/link` union contract + `revoked`** — server only, no client change | yes | `test_platform_link_contract.py` green |
| **S3** | Guard + corpus + differential oracle + fuzz; **server-side parity guard**; `parse_graphql_response` extracted | yes | §6.1 green; `vcr_misses == 0` |
| **S4** | `/lease` + `/outcome` + transport module + vault; **rails swap + negative control, in this same PR**; both flags **off** | yes | §6.3 green; `device_outcomes_refused == 1` |

> **The rails swap belongs to S4, not S3.** §6.4's negative control is a lease pointed at a sinkholed host that the device must refuse and the server must count — it needs `/lease`, `executeLease`, and `/outcome`, none of which exist until S4, and §6.4 itself says the swap ships "in the same PR that lands the transport." Leaving it in S3 makes `device_outcomes_refused == 1` unsatisfiable, so the stage either stalls or the counter gets forced green — the "green run for the wrong reason" the negative control was written to prevent.
| **S5** | Client sticky-revocation rewrite (all five sites in §4.5); `X-FTF-Caps` emission | yes | old-binary fixture test green |
| **S6** | **Build ships to TestFlight carrying S2 + S5** | — | **the credential-safety gate** |
| **S7** | **Both** flags on, tester allowlist = the operator's device only | yes — flags off | one real send + the R-ROLLBACK drill rehearsed; M4 zero; M8 divergence zero for 7 days |
| **S8** | **Widen the allowlist.** No flag changes. | yes — shrink the allowlist | soak clean at each widening |

> **The flags must move together at S7, and an earlier draft had them split — which made S7's own gate unreachable.** Nothing in this document writes a `platform_links` row except §2.4's device-custody branch, and that branch requires `is_enabled("sleeper.device_custody")`. With custody deferred to S8, the operator's link during S7 goes to `sleeper_credentials`, no `platform_links` row exists, and §4.1 step 8 returns `409 no_device_credential` on **every** lease — so "one real send" cannot happen. §7.3's rollback drill already assumed the opposite: its step 3 says "`sleeper.device_custody` → **false**," which only makes sense if it was true during the drill.
>
> **Merging them is free, and that is a consequence of the round-2 fix.** Because `device_custody_active()` now includes `device_transport_enabled()` (§2.4), flipping the global `sleeper.device_custody` at S7 has **zero effect outside the tester allowlist**. The allowlist — not the flag — is the cohort for both. That also means the thing being widened at S8 is a list of devices, which is reversible per-device, rather than a global boolean that moves everyone at once.

**S2 and S5 must both be in the field before `sleeper.device_custody` goes on anywhere** (HLD blocking fix 5(iii)). This is a weaker and more accurate statement than "before any row is deleted": under A3 no rows are deleted, and the hazard is not deletion but **absence** — the first user whose link is written in device-custody mode is the first user whose `GET` would have said `connected: false`.

**Operator-only rollout.** `is_enabled` has no per-user dimension (`backend/feature_flags.py:768`). The existing mechanism is the tester allowlist keyed on `device:<X-Device-Id>` (`backend/server.py:18131-18145`, `experiments.load_tester_allowlist`). `/lease` uses that, exactly as `/api/test-users` does, rather than inventing a second gate.

### 7.3 Rollback drill — rehearsed at S7, not first attempted during an incident

1. `platform.device_transport` → false. `/lease` returns `404 feature_disabled`.
2. Confirm device egress ceases within `LEASE_TTL` (5 min) — the bound, since there is no device-side TTL enforcement (I2). **Withholding leases is the only rollback primitive, and it stops new sends only.**
3. Re-link: `sleeper.device_custody` → false, user reconnects, a `sleeper_credentials` row is written.
4. `POST /api/trades/propose` end-to-end **on the same build**.

Step 3 is why the token-write branch is retained and flag-gated rather than deleted. Without it, step 4 resolves to `409 sleeper_not_linked` at `backend/server.py:12609` — the exact hole A3 was written to close. `test_rollback_server_path_ci.py` keeps it from bit-rotting between rehearsals.

### 7.4 Backward-compatibility hazards

| # | Hazard | Status |
|---|---|---|
| H1 | Old binary wipes its credential on `connected:false` | **closed** by the §2.5 union — the load-bearing one |
| H2 | Old binary sends via `/api/trades/propose` with no token row | **closed** by the capability-keyed write (§2.4) |
| H3 | `token_encrypted nullable=False` blocks a token-free row | **closed** by not writing that row at all (§1.5a) |
| H4 | Reinstalling an old build silently restores server custody | **open** — OI-4; correct failure direction, but M1 can go non-zero without an incident |
| H5 | New response keys break old clients | **closed** — `SleeperLinkStatus` (`sendInSleeper.ts:12-22`) is structural; extra keys are ignored |
| H6 | Two devices; the second link overwrites `device_id` | **open** — OI-3 / PRD OQ-7 |
| H7 | `_migrate_db` cannot express any of this | **closed** — new tables only, `create_all` (`backend/database.py:2708`) |

### 7.5 Migrations

Three new tables via `metadata.create_all()`. Following the existing idiom (`database.py:1980-1988`), add the placeholder `ALTER` block for future additive columns to each, **each in its own transaction** — Postgres aborts the whole transaction on any error even when Python catches it.

No data backfill: A2 removed the cohort problem. Existing `sleeper_credentials` rows keep working through the unchanged server path until their user re-links on a capable binary.

### 7.6 Doc updates owed

`docs/api-reference.md` (two new routes, two changed contracts) · `docs/data-dictionary.md` (three new tables) · `docs/config-reference.md` (two flags) · `living-memory/LLD.md` (the digest and lock conventions) · `docs/runbook.md` (the rollback drill, the M4 alert response) · `docs/cross-client-invariants.md` (the compiled op set and the capability fingerprint — the server's `TRANSPORT_OP_SETS` and the client's `DEVICE_OPS` are the same value in two clients, which is exactly what that doc governs) · `living-memory/DEPENDENCIES.md` if OI-5 lands · [ADR-011](../adr/adr-011-device-side-platform-auth.md) and the [HLD decisions](device-side-platform-auth-hld-decisions-2026-08-13.md) (PRD §12's three doc corrections, plus §1.5's three here).

**Analytics events for lease and outcome must be registered in `backend/analytics_taxonomy.py` before first emission** — the NULL-`platform` incident is the precedent.

---

## 8. Open Items

| # | Item | Blocks | Owner |
|---|---|---|---|
| **OI-1** | `MAX_BODY_BYTES = 65_536` is inherited from the HLD's open items and unmeasured against the largest real `propose_trade` body (a full-roster trade with picks and FAAB). Measure. Overflow is `413`, never a truncation — that part is settled. | S3 | eng-backend |
| **OI-2** | The Python parity guard is a second implementation of a security control. Mitigated by the shared corpus, but a reviewer may prefer dropping it and accepting that skew surfaces as an M4 page. Chosen as written because paging the operator for a *server* bug is the failure D3 set out to avoid. | S3 | eng-architect |
| **OI-3** | Two-device model: single-holder (`device_id` overwritten) vs multi-holder. PRD OQ-7 unanswered. Release 1 assumes single-holder; changing later is a PK change. | S4 | operator |
| **OI-4** | H4 — an old build reinstalled over a device-custody link silently restores server custody via replay. Accept and monitor, or refuse a `transport_v=0` `POST /api/sleeper/link` once a `platform_links` row exists (which breaks that user's sends entirely)? | S8 | operator |
| **OI-5** | `graphql` as a mobile `devDependency` for the differential oracle. Alternative: run the oracle in Python only against the parity guard and rely on the shared corpus to bind the TS side — weaker, but adds no dependency. | S3 | eng-mobile |
| **OI-6** | `DIGEST_WINDOW = 10 min` vs real retry behaviour (HLD "still open"). Too short duplicates sends; too long blocks a legitimate re-send after a genuine failure. No data exists at n≈2. Related: the epoch cannot recall an in-flight lease, and there is no fix that does not reintroduce device-side TTL enforcement, which D1 forbids. | S7 | eng-backend |
| **OI-7** | `sleeper_credentials.token_encrypted` stays `nullable=False`. If a later release does delete the server path, that schema decision returns — and the SQLite `NOT NULL` drop is a table rebuild. Recorded now so it is not rediscovered. | later | eng-architect |
| **OI-8** | The authenticated pending-outgoing read is the only thing that converts `unknown` into known (HLD "Corrections"). Unexplored, architecturally compatible under I1 — the server would parse the forwarded bytes. Scoped follow-up, not a limitation. | — | pm-technical |
| **OI-9** | PRD OQ-4: `expo-updates` addresses R1–R6 as a class while this design addresses R1–R2, and is to be evaluated **first**. Nothing here resolves it, and every "no OTA, cannot fix old binaries" constraint above is downstream of it. | S0 | operator |
| **OI-10** | `MAX_OUTSTANDING_LEASES = 3` has no empirical basis. It is a blast-radius bound, **not** a security control — a lease is inert without the credential on that device — so getting it wrong is a UX cost, not a safety one. | S4 | eng-backend |
| **OI-11** | **The sweep cron is a hard liveness dependency.** §4.4's per-lease UPDATE and §4.7's sweep cannot deadlock or cross-release each other's locks (both are keyed by `lease_id`, and a released lock is already NULL) — verified, no defect. But if the 5-minute cron stops, `issued` rows hold their locks indefinitely and every affected user is stuck on `409 send_in_flight` with no self-recovery. Needs an alert on `count(*) WHERE state='issued' AND now > digest_until`, and the cron named as a dependency in §4.7. | S4 | eng-backend |
| **OI-12** | **Does Hermes provide `TextDecoder` and base64?** §4.2.1. Zero occurrences in `mobile/src`, and CI runs the guard under node where both are globals — so a green build is not evidence. If absent, the import-free rule forces a hand-written UTF-8 validating decoder *inside the security control*, with its own corpus. | **S3** | eng-mobile |
| **OI-13** | `MAX_RESPONSE_BYTES = 262_144` unmeasured against a real `propose_trade` response, whose selection set returns `metadata`, `settings`, and `player_map` (`sleeper_write.py:207-210`). Truncation is now handled safely (§4.4) rather than misreported, but a routinely-truncated response makes every send read as "couldn't reach Sleeper." | S4 | eng-backend |
| **OI-14** | **Deviation from PRD:144** — that line says a `user_id` mismatch wipes the vault; §2.7 returns `null` instead and wipes only from the session-establishment path. The LLD's reasoning is that any caller passing a stale id could otherwise cause a self-inflicted denial of service. This is an operator call, not a drafting choice. | S4 | operator |
| **OI-15** | `DELETE /api/sleeper/link` is gated on a verified session today (`backend/server.py:12418-12420`, `_verified_write_denial`). §2.5 makes it the **sole** writer of `revoked`, and under device custody revocation is the only recall mechanism — so a user whose session lapsed cannot revoke. Deliberate, or a gap to close before S8? | S8 | operator |
| **OI-16** | `epoch` is typed non-nullable on `GET /api/sleeper/link` (§2.5) but lives only on `platform_links` (§3.1). Specify what `GET` returns when only a `sleeper_credentials` row exists, and what `DELETE` does when no `platform_links` row exists. | S2 | eng-backend |
| **OI-17** | Nothing computes, registers, or CI-pins `TRANSPORT_OP_SETS` against the client's `DEVICE_OPS`. Every other cross-client invariant here gets a `check-*` test (§6.2); this one gets only a `docs/cross-client-invariants.md` row. Failure is loud (426 to everyone, caught by one operator device at S7), so not blocking — but add `mobile/tests/check-transport-caps-fingerprint.js`. | S5 | eng-mobile |
| **OI-19** | `epoch` is not a `request_digest` component (§3.5 Rule B). A disconnect and re-link therefore leaves an orphaned lock that still matches the retried trade, so the user can eat `409 send_in_flight` for the full `DIGEST_WINDOW` on a send that never happened. Adding it frees the lock on re-link at zero cost — the only reason it is an OI rather than a change is that it widens the digest's meaning, which OI-6's window measurement should settle together. | S4 | eng-backend |
| **OI-20** | §7.6 requires lease/outcome analytics events registered in `backend/analytics_taxonomy.py` **before first emission**, but this document names no event, no property, and no platform dimension anywhere. The NULL-`platform` incident it cites as precedent is exactly the failure of not speccing them up front, so this is owed before S4, not at it. | S4 | eng-analytics |
| **OI-18** | `x-sleeper-graphql-op` is allowlisted with a **free-text, server-chosen value** that is transmitted to Sleeper. The guard bounds the verb in the *body*; this header names a verb outside the guard's reach. Cheapest fix: have the device synthesize it from the parsed root field rather than accept it from the lease. | S4 | eng-architect |

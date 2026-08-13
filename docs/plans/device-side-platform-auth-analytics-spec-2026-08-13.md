# Analytics spec — device-held platform credentials (closes OI-20)

> **Why this exists:** the [LLD](device-side-platform-auth-lld-2026-08-13.md) §7.6 requires lease/outcome events "registered in `backend/analytics_taxonomy.py` **before first emission**" and then names **no event, no property, and no platform dimension** — the exact omission the NULL-`platform` incident is cited as precedent for. OI-20.
> **Status:** spec only. Nothing here is registered or emitted yet. Registration lands with S4 (server events) and S5 (the one client event), per Plan §1.
> **S0 emits nothing.** Verified: `credentialVault.ts` is referenced by no other module, and the S0 diff adds zero `track()` call sites. Instrumenting dormant code would be dead instrumentation.

---

## 1. What is already covered for free

| Surface | Covered by | Note |
|---|---|---|
| `POST /api/platform/lease`, `POST /api/platform/outcome` — **inbound** | existing `api_request` (`obs.api_events`) | Fires automatically with `route` (the Flask url_rule pattern) and `error_code` (our closed `error` enum — `feature_disabled`, `send_in_flight`, `upgrade_required`…). **No new work.** Worth knowing before anyone builds a bespoke endpoint counter. |
| A successful send | existing **`trade_sent`** | See §3 — this must keep firing on the device path, and that is a requirement, not an assumption. |

## 2. What is NOT covered, and why it needs new events

`api_call` is **server-fired** and captures outbound HTTP the *server* makes (`backend/api_observability.py`). Under device custody the server is no longer the sender, so the outbound Sleeper call becomes invisible to it. The server learns the call happened only when the device reports to `/outcome`. That is the gap these events fill — and it is the same "vacuous counter" class the LLD §6.4 already flags for the sim rails.

### 2.1 `platform_lease_issued` — server-fired, NON_INTENT

Fired on a 200 from `/api/platform/lease`. The **numerator of M8**.

| Prop | Values |
|---|---|
| `platform` | `"sleeper"` (r1). **Mandatory, never null** — the NULL-`platform` incident. |
| `op` | the **parsed** root field (`propose_trade`, `reject_trade`) — never a client label |
| `transport_v` | int; the client's declared capability |
| `custody` | `"device"` \| `"server"` |

### 2.2 `platform_send_outcome` — server-fired, NON_INTENT

Fired on every `/api/platform/outcome` that mutates a lease. The **denominator of M8** and the **whole of M4**.

| Prop | Values |
|---|---|
| `platform` | `"sleeper"`. Mandatory, never null. |
| `op` | parsed root field |
| `result` | `ok` \| `http_error` \| `network_error` \| `aborted_before_send` \| `refused` |
| `refusal` | the `SendRefusal` enum when `result="refused"` — **this is M4** |
| `guard_reason` | the `GuardRefusal` enum, only when `refusal="guard_refused"` |
| `http_status` | int, platform status |
| `ms` | int, device-measured duration |
| `late`, `duplicate`, `epoch_stale`, `truncated` | booleans from the `/outcome` response |

**No trade contents, no player ids, no league identifiers beyond the envelope column, and never any part of the credential.** Matches the `trade_sent` rule at `analytics_taxonomy.py:325-326`.

**M4 alerting split** (LLD §4.4): `guard_refused`, `auth_header_present`, `host_not_allowed`, `method_not_allowed`, `header_not_allowed` **page**; `no_credential`, `stale_epoch`, `not_foreground`, `body_too_large`, `bad_base64` are ordinary and must not. An alert that pages on the whole enum trains the operator to ignore it.

### 2.3 `platform_vault_migrated` — **client**-fired, NON_INTENT — *not in the LLD; found while building S0*

Fired once when `migrateLegacySlot` runs at its S5 call site.

| Prop | Values |
|---|---|
| `platform` | `"sleeper"` |
| `result` | `migrated` \| `none` \| `failed` |

**Why this is load-bearing and was missed.** LLD §5.2 notes a swallowed Keychain write leaves the user "appearing linked while every send refuses with `no_credential`" — a silent state. `migrateLegacySlot` returns `'failed'` for exactly that case and, by design, **retains the legacy key rather than throwing**, so nothing surfaces. Without this event a migration failing on real hardware is invisible until a user reports that sending is broken. The function exists now (S0) but its call site arrives at S5, which is precisely how an event like this gets forgotten.

## 3. `trade_sent` must keep firing on the device path — a requirement, not an assumption

`trade_sent` is the **cross-platform send count** (`analytics_taxonomy.py:306`: "Cross-platform send counts = `sleeper_send_succeeded` ∪ `trade_sent`"). Today it is fired by `_record_send_success` on the server send path. Under device custody the send happens on the phone, and `_record_send_success` is called from the `/outcome` handler instead (LLD §4.4).

If that call is dropped or fires twice, Sleeper silently leaves the cross-platform series — a reporting regression with no error anywhere. Two pins, both owed at S4:

- `_record_send_success` fires **exactly once** per successful lease, guarded by the `rowcount == 1` idempotency check, **not** by an application-level "have I seen this."
- A test asserts a device-path success produces a `trade_sent` with `platform: "sleeper"` identical in shape to the server path's.

## 4. Registration checklist (S4 / S5)

- [ ] `platform_lease_issued`, `platform_send_outcome` → **server-fired**: add to the taxonomy's event set and `OBS_EVENT_PROPS`. **Must NOT go in `ALLOWED_CLIENT_EVENTS`** — the import-time disjointness assert will raise, and a client-forgeable M4 is a forgeable incident signal.
- [ ] `platform_vault_migrated` → **client-fired**: `ALLOWED_CLIENT_EVENTS` + `CLIENT_EVENT_PROPS`.
- [ ] Registration lands **before** the first emitter, in the same PR or earlier.
- [ ] Post-deploy probe: emit each and read it back out of `user_events`, asserting **prop keys and values** survived — key survival alone is insufficient (G-036: a `league_id` stored `"[scrubbed]"` while the key looked fine).
- [ ] `platform` is non-null on every row.

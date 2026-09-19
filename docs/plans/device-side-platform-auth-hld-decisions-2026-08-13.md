# HLD Decisions — Device-Held Platform Credentials (2026-08-13)

> Resolutions from the dual-agent HLD review (2 rounds). Supersedes the earlier
> `design/device-side-platform-auth` HLD, which review found defective in several places.
> Requirements: [`device-side-platform-auth-prd-2026-08-12.md`](device-side-platform-auth-prd-2026-08-12.md) incl. amendments A2/A3.
>
> **Round 2: A raised 4 blocking, B raised 2; both converged on D5. Resolutions below are applied.
> Two blocking items were self-retractions — the architecture lens withdrew two of its own round-1 proposals.**

## Settled by both lenses independently — build to these

The server builds every request; **the device is a pure transport**. The device **never parses a
platform response** — it forwards raw bytes and the server interprets them, because response
semantics are the most change-prone part of a reverse-engineered API and a parser in the binary
re-opens the hole the design exists to close. **Flags are evaluated server-side at lease time**,
which dissolves the fail-open flag hazard by construction. No Chrome-spoofing on device.
Compiled host allowlist + parsed-root-field allowlist per the PRD's six parser rules.

## Resolved disagreements

**D1 — lease TTL. 5 minutes, and the TTL is NOT the control.** 90s is refuted by this repo:
`client.ts` carries a 30s slow-timeout because Render cold starts are real, and the flow now risks
two of them. The load-bearing properties are **deny-by-default, single-use, server-recorded**.
**There is no device-side TTL enforcement** — a device clock is owned by the party the lease bounds;
`expires_at` is UX only. **The outcome endpoint MUST accept a late report** against an expired or
burned lease (record it `late`): rejecting one manufactures `unknown` out of a slow network, which is
the exact state R-IDEMPOTENCY exists to make rare. Outstanding-lease cap is a **blast-radius bound on
a looping client, not a security control** — a lease is inert without the credential on that device.

**D2 — no signing.** Nobody named a threat TLS does not cover. A compiled verify key makes rotation
an App Store release, reintroducing the dependency A3 exists to route around. **Two free controls
replace it:** a lease response containing an `authorization` header is **refused** (stops a
compromised backend attaching a credential of its choosing), and the device refuses to attach its
credential to a lease whose `user_id` ≠ the envelope's. `lease_id` is high-entropy server-generated.

**D3 — capability negotiation, not a build floor.** `X-App-Version` carries a hand-bumped semver that
does not track the compiled allowlist or parser version, so two builds can share a version and
disagree about what they execute. Decisive: **the server must know the device's compiled root-field
set to build a body the device will accept**; without negotiation, ordinary skew produces a device
refusal indistinguishable from the attack M4 detects — and M4 pages the operator. Ship
`caps:{transport_v}` + typed `426 upgrade_required`; a plain alert is an acceptable client at n≈1.

**D4 — retain `sleeper_credentials`; add `platform_leases` + per-user `credential_epoch`.** A3 is
dispositive: `POST /api/trades/propose` reads `get_sleeper_credential`, so a secret-free table leaves
the recovery path resolving to `not_linked` and the rehearsed drill cannot pass CI. Second reason:
`POST /api/sleeper/link` **stores the token before stamping verification**, so the row is created at
link time by design — G1 is unreachable by deleting rows; it is reachable only by making the *write*
conditional. **Cost, stated: G1 becomes a runtime guarantee (M1 = zero rows, monitored), not a schema
guarantee.** A reduced secret-free `platform_links` (user, platform, device_id, epoch, linked_at)
still ships to answer "which device holds what," which the two-device problem needs.

**D5 — MFL login is its own device-built call, NOT through the lease path.** *Both lenses; the
architecture lens retracted its own proposal.* Under "the server builds every request" the
**password would ride to Render in the lease request**, defeating PRD **G2** — the only reason MFL is
in this programme. And obtaining the cookie requires the device to parse XML, violating the
never-parse rule. **Resolution:** separate *the transport module* (allowlist, foreground guard, egress
counter, single attempt — this is what makes the allowlist inspectable) from *the lease-built-body
path*. MFL login goes through the module as the **one named exception to both rules**: body composed
on-device because the secret is on-device, and exactly one response read — the
`MFL_USER_ID="([^"]+)"` extraction — forwarding nothing. Justified because MFL's login is
**documented and sanctioned**, so the "parsers rot un-hotfixably" premise is at its weakest here.

## Blocking fixes applied

**1. Link/verify stays server-side, and G1 is restated.** `POST /api/sleeper/link` is the
**account-verification oracle** — it runs `verify_token_live`, sets `sess["verified"]`, persists
`users.verified_via`, and that gates mutating routes via decorator. The device already replays the
raw JWT there **on every fresh session**. G1 is therefore restated as **"no server-side JWT at
rest."** `(query, __typename)` is **removed from the device compiled set**: a success body for
`{__typename}` is a constant string any client can fabricate, so routing the verification probe
through the leased transport would make the oracle **client-forgeable**.

**2. Outcome reporting is idempotent and retryable.** `/api/platform/lease` and
`/api/platform/outcome` go in `SLOW_POST_PATHS` (POSTs are otherwise 15s and excluded from gateway
retry). `/outcome` is **idempotent by `lease_id`** — re-posting returns the recorded result — and is
therefore explicitly retryable, because it is a *report*, not a side effect. **`unknown` is reserved
for leases with no outcome after the digest window, never for a timed-out report.** Without this a
cold start turns a *successful* send into "go check Sleeper" while a real offer sits in a
leaguemate's inbox.

**3. Sentry header verification moves to Stage 3, before the decisive R7 gate.**
`tracesSampleRate` is **0.2**, so a single Stage-5 send has ~80% chance of not carrying the
SDK-injected header — clearing R7 for a signature most users will not send. Verify against a real
capture with tracing forced on, and make "no Sentry-injected header on a platform request" a
**precondition** of the real-send gate.

**4. The keychain fix is not a one-liner, and the JWT must not exist twice.**
`keychainAccessible` affects **future writes only** — closing the existing exposure needs a
**read-then-rewrite migration**. And `ftf.platformCreds` must **subsume and delete**
`sleeper.link.jwt`, asserted in a test: otherwise the design leaves **two Keychain copies of a
365-day full-account credential**, one outside the atomic-wipe and epoch logic.

**5. THE CUTOVER ORDERING — this would have deleted the feature in production.**
`sendInSleeper.ts` implements **sticky revocation**: on session establishment, if
`GET /api/sleeper/link` reports `connected: false`, the client calls `clearPersistedSleeperToken()`
and wipes its own envelope. The comment says so outright — *"other devices self-neutralize via the
R-2.2 pre-check."* Under the new design **"no server row" is the desired steady state**, so deleting
rows at cutover makes **every device in the field erase the credential the design depends on** — and
with no OTA, older builds keep doing it forever.

> **Ordering is the fix, and it is not optional.** (i) `POST /api/sleeper/link` gains a
> **device-custody mode**: verify against the same oracle, persist `sleeper_user_id`/`expires_at`/
> `verified_at` only, never `token_encrypted`; the token-writing branch stays flag-gated for A3.
> (ii) `GET /api/sleeper/link` must report `connected: true` for a device-custody link, and sticky
> revocation must key off an **explicit `revoked` signal**, never the absence of a row.
> (iii) **Both ship in the build before any row is deleted** — old builds cannot be fixed.

## Corrections to earlier claims

- **R7 overstatement withdrawn** (by its author). Not "no fix at any layer" — **"no device-side fix
  and no hotfix; the remedy is R-ROLLBACK to server egress, which is why A3 is not optional."**
  A WKWebView transport is a known R7 lever, at the cost of the never-parse rule.
- **"Sleeper pending-detection is dead" needs the word *public*.** The unauthenticated route is dead
  (1,677 trades, zero non-`complete`). An **authenticated** pending-outgoing read is unexplored and,
  under the never-parse rule, architecturally compatible — it is the only thing that converts
  `unknown` into known. A scoped follow-up, not a permanent limitation.
- **The abort path must release the digest lock.** R-FOREGROUND aborts before send; the device
  reports `aborted_before_send`, which clears the `409 send_in_flight` hold immediately. Otherwise
  backgrounding between lease and send locks a user out for ~10 minutes on a send that never
  happened. Only a lease that reached the platform stays locked.
- **Add R8 to the residual: credential invalidation/expiry** — not an upstream *shape* change, which
  is why it fell out, but the most likely real break over a ~365-day token. A 401 in the outcome body
  ⇒ typed `credential_rejected` (distinct from `no_device_credential`) ⇒ stop minting for that user
  ⇒ prompt re-capture.
- **Dispose of the vacuous counters.** `completed_proposes` and `sleeper_live_egress_attempts` stay
  in `sim-run.sh`'s exit-4 set where they will keep reporting green for the wrong reason once the
  server is no longer the sender. Swap them for the fence counter and the under-test lease count **in
  the same PR that lands the transport**. R-RAILS also needs a **negative control**: one deliberate
  request to a sinkholed host per run that must be blocked *and counted*, or a misconfigured fence
  yields a green run with real egress.
- **Parser rule 2 positional anchor:** `_PROPOSE_TRADE_TEMPLATE` puts variable definitions before the
  selection set, so "first token after the opening brace" must mean the **selection-set** brace,
  after skipping a balanced variable-definition group and any directives. A naive "first `{`" reads a
  type name.
- **Sequence the FAAB fix before the parser.** `json.dumps` emits quoted keys — invalid GraphQL
  object-literal syntax — so once the strict lexer ships, its behaviour on a FAAB body is undefined.
  Add a FAAB-populated body to the four-test set.
- **`body_b64` is untrusted client input** and must never be the sole authority for an irreversible
  server action.
- Restore PRD **G2** (MFL password) and **G7** to the goal list; the HLD's renumbering dropped them.
- Carry A3's **"and in CI"** clause: a CI test exercising `sleeper_write.propose_trade` via
  `POST /api/trades/propose` against a stored credential. The cutover rehearsal is one-time; bit-rot
  is continuous.

## Still open

ESPN release-2 gates (reachability probe — **not** implied by the Sleeper 4/4 — plus an ESPN/Disney
terms read, plus M9 clean) · `expo-updates` evaluated **first**, since it addresses R1–R6 as a class
while this design addresses R1–R2 · digest window vs. real retry behaviour · disconnect copy and
deletion-law posture given FTF can no longer revoke · App Store 5.2.2 reframed as *"what if the fix
build is rejected"* · the 64 KB body cap measured against the largest op, with overflow a typed
failure not a truncation.

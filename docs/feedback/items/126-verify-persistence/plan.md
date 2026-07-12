# #126 — Verified state doesn't survive a new install (auto re-verification)

*Plan, 2026-07-12. Feedback #126 (bug, Trios, 1.7.1, mattmurf77) + operator follow-up (ESPN link 403 on 1.7.2). Branch `trade-engine-v2`. Fast-track-bug path — mini-PRD. No code with this doc.*

> **#126:** "every time I download a new app version I get a message that I need to reverify my sleeper account because it was last verified/logged in from a different device"
>
> **Follow-up (1.7.2):** linking an ESPN league returned "Verification Required" — the operator has a verified controller, yet his fresh-install session 403'd as if he were a squatter.
>
> **Operator directive:** fix the persistence, don't weaken the gate.

---

## 1. Problem statement

Verification is **session-scoped in-memory state** (`sess["verified"]`, [server.py:5076](../../../../backend/server.py)) set in exactly one place for Sleeper-keyed users: a successful `POST /api/sleeper/link` (JWT claim matches session user **+** live oracle proof, [server.py:5037-5094](../../../../backend/server.py)). Sessions live in the in-memory `_sessions` dict; a new install, a re-sign-in, or a backend restart mints a fresh session that starts **unverified** — even though:

- **(a)** `users.verified_via='sleeper'` is persisted (the user already proved control, permanently), and
- **(b)** the user's real Sleeper JWT is stored server-side, Fernet-encrypted, in `sleeper_credentials` ([database.py:5776 `get_sleeper_credential`](../../../../backend/database.py)) — a 365-day token that survives reinstalls by construction.

The gates then work exactly as designed — against the wrong person. `_verified_write_denial` / `_verified_read_denial` ([server.py:1263-1374](../../../../backend/server.py)) see *unverified session + verified controller exists* and 403 `verification_required`, **even in grace** (first-verified-controller-wins). That branch exists to kill squatters the moment the real owner verifies; it cannot distinguish "squatter" from "the owner himself, one install later." Every fresh session of the most-invested users (the ones who verified) is treated as hostile until they redo the SleeperConnect WebView capture.

Confirmed downstream hits:

- `POST /api/espn/link` carries `@_gate_unverified_write` ([server.py:10092-10093](../../../../backend/server.py)) → the operator's 403. The mobile sheet surfaces the raw error code (`client.ts:325` uses `body.error` as the message; `EspnLinkSheet.tsx:95-96` prints `e.message`) → "verification_required" shown as the error text.
- Every other gated write and all P2.5-gated board reads 403 the same way until re-capture.
- `POST /api/trades/propose` hard-requires `sess["verified"]` ([server.py:5134](../../../../backend/server.py)) → Send-in-Sleeper degrades to deep-link fallback on every fresh install despite a live stored token.
- The banner copy is factually wrong: [`VerifyAccountBanner.tsx:44-45`](../../../../mobile/src/components/VerifyAccountBanner.tsx) says *"This account was verified on another device."* whenever `user_verified && !session_verified` — for #126 it's the **same** device, new install/session. This is the "different device" message in the report.

**Root-cause hypothesis: confirmed against code.** Nothing at session establishment ([`_extension_build_session` server.py:8811](../../../../backend/server.py) — the mobile + extension mint path; [`session_init` fresh-session branch server.py:7288-7291](../../../../backend/server.py)) consults `sleeper_credentials`. The proof material to re-verify silently is sitting in the DB the whole time.

**Not affected:** account-keyed (`acct_*`) sessions — `/api/auth/apple|google` re-auth marks the session verified at mint ([server.py:9638-9651](../../../../backend/server.py)), so P2.6 Apple-first users already survive reinstalls (checked — no work needed there). The gap is exactly the Sleeper-keyed population.

## 2. Approach — auto re-verification via the stored token + the same oracle

**Principle: identical security model, zero user friction.** Verification still requires exactly the P1 proof — a Sleeper JWT whose claim matches the session's `user_id`, proven live against Sleeper's authed API (`verify_token_live`, [sleeper_write.py:168-193](../../../../backend/sleeper_write.py)). The only change: the server replays the proof from the **stored** credential instead of making the human re-run the WebView capture. Claim-match alone never verifies (unsigned JWT — the oracle is mandatory, unchanged).

### 2a. One helper, two call sites

New `_maybe_autoverify(sess)` in the server.py session/gate region:

1. Bail fast (no I/O) unless: session unverified, `user_id` non-empty and not `acct_*`/`demo_user_*`/`test_user_fp_*`.
2. `get_sleeper_credential(user_id)` — none → done (current behavior; banner prompts).
3. Decrypt; `is_expired(token)` → delete credential (same semantics as propose's expired path, [server.py:5156-5158](../../../../backend/server.py)) and done.
4. Defensive re-assert: `token_sleeper_user_id(token) == sess["user_id"]` (was checked at store time; cheap to re-check) — mismatch → done, log.
5. `verify_token_live(token)`:
   - **success** → `sess["verified"]=True`, `sess["verified_via"]='sleeper'`, refresh `mark_user_verified` best-effort, log one stable `AUTH-AUTOVERIFY ok user_id=…` line.
   - **`SleeperAuthError`** (oracle explicitly rejected — dead/revoked) → stay unverified; delete the stored credential (it can never succeed again; matches existing dead-token hygiene) → banner prompts re-capture. Log `AUTH-AUTOVERIFY rejected`.
   - **`SleeperWriteError`** (transport/config — inconclusive) → stay unverified, do **not** delete, allow retry later. Log `AUTH-AUTOVERIFY inconclusive`.
6. **Single-flight + memoization on the session dict:** `sess["autoverify_state"] = ok|rejected|inconclusive:<ts>` plus a per-session lock/flag so concurrent requests don't stampede the oracle. `ok`/`rejected` are terminal for the session's lifetime; `inconclusive` retries after a short TTL (~5 min).

Call sites:

- **Session establishment (sync, bounded):** end of `_extension_build_session` (covers mobile sign-in — which mints via `/api/extension/auth` — and the extension) and the fresh-session branch of `session_init` (covers web, and any mobile path that inits without a prior token). Run with a **short deadline** (~3 s): `verify_token_live`'s underlying `_post_graphql` uses a 15 s timeout ([sleeper_write.py:40](../../../../backend/sleeper_write.py)) — too long to block sign-in on. Either thread the timeout through (`verify_token_live(token, timeout=…)` — small additive param to `_post_graphql`) or run the probe on a worker thread and `join(3)`; deadline miss ⇒ treated as inconclusive, session proceeds unverified. **A failed/slow/erroring probe must never fail or materially slow session establishment** — the helper is wrapped in a broad try/except and only ever *adds* verification.
- **Lazy backstop in the gates:** in `_verified_write_denial` and `_verified_read_denial`, after the `sess.get("verified")` check and **before** the controller-exists 403, attempt `_maybe_autoverify(sess)` (subject to the memoization above — at most one live probe, then cached). This catches the establishment-time race (probe timed out / Sleeper hiccuped) at exactly the moment a real denial would otherwise fire. A slower-but-successful first gated call strictly beats a fast 403.

Why sync-bounded at establishment rather than fully async: the `session_init` response carries `verification.session_verified` ([server.py:7578-7583](../../../../backend/server.py)) and the banner keys off it — an async probe would report `false`, flash the banner, then have no push channel to retract it. `session_init` is already a 5–10 s cold-start call; +1 bounded oracle RTT (~200–500 ms typical) is noise, and the lazy backstop covers the timeout case. (Considered and rejected: async-only — banner flash + no retraction; lazy-only — banner shows on every fresh install even though writes would succeed, which is #126's literal complaint.)

### 2b. What deliberately does not change

- Gate decision matrices, grace semantics, first-verified-controller-wins, hard routes (`/api/sleeper/link`, `/api/trades/propose`, reset-rankings) — untouched. A genuine squatter has no stored credential under the victim's `user_id` (storing one requires the claim-match + oracle at link time), so auto-verify gives them nothing.
- The SleeperConnect capture flow — still the path for first-ever verification and for dead-token recovery.
- `verify_token_live` semantics — inconclusive is never proof and never forgery (only additive timeout plumbing, if that option is chosen).

### 2c. Copy fix

`VerifyAccountBanner.tsx:44-45`: replace *"This account was verified on another device. Reconnect Sleeper here to keep editing your ranks."* with copy matching reality (post-fix the banner appears only when auto-verify **couldn't** run: no stored token, or token dead/expired). Proposed: **"Your account is verified, but this session isn't. Reconnect your Sleeper login to keep editing your ranks."** Also map `verification_required` in `EspnLinkSheet` to human copy (reuse the pattern from `utils/verification.ts` — e.g. "Verify your account to link a league.") instead of printing the raw error code.

## 3. Platforms touched

| Platform | Change | Size |
|---|---|---|
| Backend | `_maybe_autoverify` helper + two call sites + gate backstop (`server.py` session/gate region); optional timeout param through `sleeper_write._post_graphql`/`verify_token_live` | S–M |
| Backend tests | extend `backend/tests/test_verified_sessions.py` (see §5) | S |
| Mobile | `VerifyAccountBanner` copy; `EspnLinkSheet` error mapping | XS |
| Web / extension | none (they benefit for free: server-side auto-verify partially closes the P2.5 known limitation — a verified owner's own username-only web/extension session with a stored token stops read-403ing) | — |
| Docs | `api-reference.md` (session_init `verification` semantics + gate matrix note), `runbook.md` (new `AUTH-AUTOVERIFY` log lines beside the AUTH-GRACE monitoring), account-auth-plan status appendix | XS |

## 4. Risks

1. **Oracle load/latency on session establishment.** One extra Sleeper GraphQL no-op per fresh session *for users with a stored credential only* (today: single digits). Bounded by the 3 s deadline; memoized per session; inconclusive-TTL prevents hammering when Sleeper is down. Monitor via the `AUTH-AUTOVERIFY` log lines.
2. **Deleting a live token on a transient Sleeper 401.** `SleeperAuthError` is raised only on Sleeper's explicit auth rejection (verified 2026-07-08: bad tokens 401 before query execution), so delete-on-reject matches existing hygiene — but see open question Q1.
3. **Token expiry semantics.** Sleeper JWTs carry `exp` ≈ 365 days from capture (P1/capture-runbook finding); `is_expired` is checked before probing. Long-lived tokens mean auto-verify works for ~a year per capture, then the banner correctly reappears — acceptable.
4. **Security review optics.** This widens *when* verification is granted, not *what grants it* — the proof predicate is byte-identical to link-time. Must be stated in the PR for eng-security; never verify from claim-match or `users.verified_via` alone.
5. **Race: first gated call lands before the establishment probe finishes.** Covered by the lazy gate backstop; test it.
6. **`server.py` contention.** The session/gate region had P3-era co-owners; none active now — single-owner assignment below avoids merge risk.

## 5. Test plan (must-cover)

Extend `test_verified_sessions.py` (existing fixtures already stub the oracle):

- **The #126/ESPN repro (operator directive):** user with `users.verified_via='sleeper'` + stored valid credential + **fresh session** → `POST /api/espn/link` (flag on) succeeds with no manual re-verification; also assert one non-ESPN gated write and one P2.5-gated read pass.
- session_init on such a user reports `verification.session_verified: true`.
- Oracle rejects stored token → stays unverified, gated write 403s (gate not weakened), credential handling per Q1 decision.
- Oracle transport failure → inconclusive: unverified, credential retained, session_init still 200; retry allowed after TTL; second call within TTL makes no probe (single-flight/memo).
- Expired stored token → no probe, credential deleted, unverified.
- No stored credential → exact current behavior (grace/controller matrix unchanged — existing tests keep passing).
- `acct_*`/demo sessions → helper no-ops.
- Squatter regression: unverified session for a verified user_id **without** a usable stored credential still 403s reads+writes.

## 6. File-ownership proposal (single Author agent; no active competing owners)

- `backend/server.py` — session/gate region (helper + `_extension_build_session` + `session_init` + the two denial fns). **Owner: #126 Author.** (P3-era gate owners inactive; note in PR that P3 will rebase on this.)
- `backend/sleeper_write.py` — additive timeout param only, if chosen. Owner: #126 Author.
- `backend/tests/test_verified_sessions.py` — Owner: #126 Author.
- `mobile/src/components/VerifyAccountBanner.tsx`, `mobile/src/components/EspnLinkSheet.tsx` — copy-only. Owner: #126 Author (coordinate with the ESPN thread if it has EspnLinkSheet in flight).
- Docs listed in §3 — Owner: #126 Author.

## 7. Spike needs

None blocking. Two cheap pre-checks during implementation (not separate spikes): (a) grep prod logs for `sleeper_link oracle` timings to sanity-check the 3 s deadline; (b) confirm `_post_graphql` timeout plumbing vs worker-thread join — pick whichever is smaller.

## 8. Open questions for the Author

- **Q1 — delete vs mark on oracle-reject?** Deleting a rejected credential matches propose's expired-token hygiene and keeps state simple, but a hypothetical transient Sleeper-side 401 would force a re-capture. Alternative: keep the credential, memoize `rejected` per-session only. Recommend **delete** (SleeperAuthError is an explicit rejection); Author may downgrade if the prod logs show flappy 401s.
- **Q2 — probe `/api/session/ping` / revalidate paths too?** `revalidateSession` re-inits with the same token (verified state already survives same-user re-init, [server.py:7279-7285](../../../../backend/server.py)), so no. Confirm no other session-mint path exists (e.g. `User1..User5` seeded logins — recommend *not* auto-verifying those; they're a P3 removal target).
- **Q3 — banner copy final wording** (Chalkline voice pass): proposal in §2c; ux-design may tighten.
- **Q4 — should `verified_via='apple'` users with a stored Sleeper credential get `verified_via` overwritten to `'sleeper'` on auto-verify?** `mark_user_verified` refresh is best-effort either way; recommend leaving the persisted marker as-is when already set (only stamp the session) to avoid churning P2.6 state.

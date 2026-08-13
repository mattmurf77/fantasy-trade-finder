# PRD: Device-Held Platform Credentials

> **FINAL — dual-agent validated over 4 rounds; both lenses signed off.**

> **Round-3 settled:** `R3-fix A` supersedes the operation-*name* pinning proposed in round 2 (a sender-chosen label constrains nothing); `R3-fix B` moved the identifying `User-Agent` out of the ship-now bundle. **v2 applied all 9 round-2 blocking objections.** 8 are fixed here; **1 (public-read coverage) cannot be resolved without the operator** and is carried as OQ-1. Changes from v1 are marked **[R2-fix N]**.
>
> **Round-2 settled — do not re-open:** D1 (both lenses converged: the move does *not* cure §11.3; the agreement does — proof below). D2 (ESPN in the programme, out of release 1). D5 (Sleeper public pending-trade detection is **dead**, answered No). D3 resolved by synthesis. D4 alternatives section added.

---

## 1. Summary

Sleeper warned the operator that its automated systems may block FTF's calls, and **suggested varying where the calls come from**. That request — not a terms clause — is what started this. FTF today stores every linked user's Sleeper JWT (full-account, ~365-day), ESPN `espn_s2`/`SWID`, and MFL session cookie server-side under **one shared Fernet key**, and replays them from Render.

This programme moves **credential custody** to the user's device and **authenticated user-scoped call execution** to the device for **Sleeper** (release 1) and **ESPN** (release 2, gated); moves **only the login** for **MFL**; and leaves public/shared reads on Render, cached.

Most users see nothing. ESPN users pay one reconnect. MFL users get an existing promise made true.

## 2. Problem & Context

### 2.1 Why this exists — corrected **[R2-fix 1]**

**The trigger is Sleeper's own request.** Per ADR-011 §Context, Sleeper warned that its automated systems may block FTF and suggested varying where calls originate. Moving the socket is directly responsive to that in a way no terms clause makes it.

**The Terms are governing context, not the trigger**, and v1 got this wrong in both directions:

- **§11.3 is already satisfied — server-side, today.** The operator's written agreement is the §11.3 carve-out, recorded as RESOLVED on 2026-08-12 in the feasibility memo, and it clears the *current* Render architecture. **Decisive proof that moving the socket is not the cure:** this design deliberately keeps link/verify **server-side** (a client cannot be trusted to verify itself). So FTF still transmits and uses each user's credential from Render at least once per user. If relocating the socket cured §11.3, that residual call would violate it — and nobody proposes moving it.
- **§11.1 binds the *user*, not FTF.** The user hands their credential to FTF's app either way. Custody location does not touch it. v1's claim that custody "speaks to §11.1" is withdrawn.

**What the programme actually buys, and all it claims:**
1. **Responsiveness to Sleeper's stated request** (the trigger).
2. **Elimination of the aggregate breach target** — today one compromise of Render plus one env var exposes every user's credential on every platform.
3. **§11.2 resilience** — a technical block aimed at FTF's fixed egress does not take out user-originated traffic.

**And the limit on benefit #1, stated plainly [R3].** §2.2's measurement cuts against responsiveness too, not just against rate pressure. Sleeper's warning describes "one machine making thousands of requests an hour." Those thousands are the **public** sweeps — which this programme declares a non-goal and keeps on Render permanently. **So if Sleeper's automated system blocks Render's egress, it blocks it over traffic this programme does not move, and the app breaks anyway.** Moving ~12 authenticated calls does not answer that. Benefit #1 is real but partial: it moves the traffic the *terms* govern, not the traffic the *volume warning* describes. Whether that is worth a multi-week programme at n=2 is OQ-5, and it is the operator's call.

**A live counterweight, stated here rather than buried:** three of Render's Sleeper paths (`sleeper_write`, `trade_block_service`, `sleeper_trades_service`) **deliberately impersonate desktop Chrome** to avoid Cloudflare 1010 bans, while other paths already identify honestly as `FantasyTradeFinder/1.0`. Render's Sleeper egress therefore has a **split identity today**, which sits awkwardly against a programme whose first stated benefit is responsiveness to Sleeper's request.

### 2.2 The traffic split — measured **[R2-fix 9]**

Round 2 objected that the build/no-build decision cannot be made without knowing how much Render→Sleeper traffic is credentialed. Measured from production `api_call` rows. **Successes are 1-in-10 sampled** (`obs_success_sample_n`) over a ≤3-day preseason window, so absolutes are ~10x low; **the ratio is the load-bearing figure, not the counts** — do not capacity-plan off them:

| Class | Approx. volume | Moves? |
|---|---|---|
| Public league/transaction/roster sweeps, bulk player dump, ADP, crosswalks | **several hundred** | No — stays on Render, cached |
| Authenticated GraphQL (the moving set) | **~12** | Yes |

**Read this honestly: the credentialed slice is a small minority of what Sleeper sees.** That does not undercut the programme — the credentialed calls are the ones the terms govern and the ones whose custody is the breach target — but it does mean **G3's blocking-resilience value is modest**, and the case rests mainly on custody. Anyone arguing this programme will visibly change Sleeper's rate pressure is overclaiming.

### 2.3 What FTF holds today

`sleeper_credentials` (Fernet full-account JWT) · `espn_credentials` (Fernet `espn_s2`, plaintext `swid`, `verified_at`) · `mfl_credentials` (Fernet session cookie) — **all under one key**, so no partial-compromise scenario exists. Plus the user's **plaintext MFL password**, which transits `POST /api/mfl/auth-link` today while the in-app copy tells them it doesn't.

### 2.4 Settled — do not relitigate

Sleeper's Cloudflare edge accepts iPhone requests, **PASS 4/4**; **do not port `_BROWSER_HEADERS` to the device**. Both send paths live and proven by real sends. No background job uses a platform credential. Sleeper offers **no IP allowlist**. **ESPN reachability is untested and NOT implied by the Sleeper probe** — an ESPN probe is a release-2 gate.

### 2.5 ESPN verification defect — FIXED and shipped 2026-08-12 (`7dfcd16`)

The credential-only branch discarded `fetch_fan_leagues`'s result while `_parse_fan_leagues` never raises, so a 200-with-unrecognised-shape stamped `verified_at` on a dead pair. Now verified against a real oracle: a read against an **auth-gated** linked league (public leagues explicitly skipped — they answer anonymously and prove nothing), falling back to a fan probe demanding positive account evidence. Failing-first evidence recorded. **Residual:** the manual-paste import path can still stamp falsely (tracked separately); the client still treats cookie-presence as capture (deferred — the logged-in signal cannot be established without a live session).

## 3. Goals & Non-Goals

**Goals.** G1 eliminate server-side custody of Sleeper and ESPN credentials. G2 stop the MFL password transiting FTF. G3 originate authenticated traffic from the user's device (responsive to Sleeper's request; §11.2 resilience — value modest per §2.2). G4 no user broken by migration. G5 retain an unconditional stop. G6 fix upstream shape changes without an App Store release. G7 disclosure becomes accurate. G8 ESPN verification actually verifies — **done, §2.5**.

**Non-goals.** Reducing call volume. Moving public/shared reads. Moving MFL's API calls. Proxy/egress rotation *(held in reserve as the fallback if the device path fails — not rejected outright)*. Building the pending-trades inbox. Adopting `expo-updates` (separate decision; it addresses this programme's dominant risk and should be evaluated **first**). Client background execution.

**[R2-fix 5]** **Closed-app offer push — foreclosed for Sleeper and ESPN only.** Sleeper's public-detection route is dead (1,677 trades, zero non-`complete`, with 781 failed waivers as the control). ESPN has no public pending surface. **MFL APIKEY-based detection remains open and is deferred, not foreclosed** — that key authenticates exports but *structurally cannot write a trade*, a safer custody profile than today's cookie, and fully compatible with MFL staying server-side.

**Also untouched by D5:** persisting the `transaction_id` that `POST /api/trades/propose` already receives and discards, then reconciling against the existing public completed-trade sweep to tell a user "your offer was accepted." Zero credentials, sanctioned API, worth doing independently.

## 4. Success Metrics **[R2-fix 2]**

N is single-digit TestFlight. Every rate is void. The compliance goal has **no positive success metric** — it is insurance.

| # | Metric | Target | Honesty-independent? |
|---|---|---|---|
| M1 | Rows in `sleeper_credentials` **among users on build ≥ X** | 0 | yes (server) |
| M2 | `espn_credentials` rows with non-NULL `espn_s2_encrypted`, same cohort | 0 | yes (server) — **but the column is `nullable=False` on `origin/main` today**, so as written this is identical to "rows exist." Before M4 choose: `ALTER` it nullable (retains `swid` + `verified_at`), or DELETE the row (discards both, forces a re-verify, interacts with M9). Triggers a `docs/data-dictionary.md` update. |
| M3 | `/api/mfl/auth-link` requests carrying a password, same cohort | 0 | yes (server) |
| M4 | **Operations rejected by the compiled allowlist** — "op" means the *parsed root field*, never the label | any non-zero is an incident | **partly** — enforcement is client-side, so it is adversary-independent under the backend-compromise model (honest client, hostile server) but **not** dishonest-client-proof. M8 is the server-observable companion. |
| M7 | Users with device credential **and** surviving server row | trends to 0 from **cutover** (defined §6); non-zero at +90d is a finding | yes (server) |
| M8 | Leases issued vs outcomes reported | divergence is the alarm | **yes — the only one that survives a dishonest client** |
| M9 | `espn_connect_captured` followed by a failed authenticated action | 0 — gates ESPN release | yes (server) |

**Moved out of the metrics table:** v1's "device calls to a non-allowlisted host = 0" was a **tautology** (compiled in ⇒ true by construction) — replaced by M4, which measures the server. v1's "calls without a lease = 0" was **client-self-reported by a client that is by definition misbehaving** — now a code invariant with a unit test pinning *no lease ⇒ no call*. v1's Maestro-egress metric is **not measurable today**: `test_support.py` has exactly one *egress* counter, Sleeper-only, server-side; ESPN and MFL server egress are uncounted and device egress has no counter at all — and Maestro law 13 already records one real POST reaching ESPN. **Building those rails is a gate on the first device-transport merge, not a parallel workstream.**

**M1–M3 are adoption-gated.** With no OTA they never truly reach 0 across all installs; they are scoped to the build cohort.

## 5. Users

Operator + ~2 testers are the whole validation population; every stage starts on the operator's device. **Two cohorts, not one [R2-fix 8]:** the device-side Sleeper token has only been written since **2026-07-12**. Users who linked before that — or on a device that never ran the connect flow — have a server row and **no device envelope**, so the silent path is impossible for them, the credential-return path is banned, and the deletion gate never fires. **Count both cohorts before build (one query).** Non-end-user stakeholders with acceptance criteria: **Sleeper** (must be able to conclude FTF holds no aggregate and can stop on request) and **Apple review** (5.2.2 — exposure *increases*, since traffic moves into the binary's trace).

## 6. Migration — its own section **[R2-fix 3]**

**During migration FTF holds credentials in both places. That is strictly worse than today, and it is the programme's largest self-inflicted risk.** Until the last server row is deleted, G1's benefit is **zero** and the attack surface is larger than the status quo.

| Phase | Content | Reversible? |
|---|---|---|
| M1 | Ship dark (all flags off); telemetry baseline | yes |
| M2 | `mfl.device_login` → Sleeper operator-only → Sleeper broad | yes, flags off resume the server path |
| M3 | **Cutover** — the dated event M7's 90-day clock runs from | yes |
| M4 | **Server-side deletion — THE POINT OF NO RETURN** | **no** |

**Deletion gate, restored in full:** ≥1 device-verified successful call for that user **AND a 14-day cooling-off**, never a timer alone — and the corresponding **lease issuance must exist server-side**, so the gate is "a lease was issued AND the client reported success against it," not a bare client assertion. **Maximum acceptable dual-custody duration must be stated with a named owner before M1.**

**Pre-2026-07-12 cohort:** gets the same just-in-time reconnect ESPN gets. §7's "invisible" applies only to the post-2026-07-12 capture cohort.

## 7. Rollback **[R2-fix 4]**

**Withholding leases is the ONLY rollback primitive for device traffic**, bounded by lease TTL. Feature flags are a **server-path control only** and cannot stop a device: they cache in AsyncStorage behind a 30-minute throttle, persist offline indefinitely, and `'espn.link': true` is **compiled into the binary** as a launched default — so a client that never completes a revalidate keeps a feature on from a baked-in default, **failing open**. **No device-side flag may ever be added to `LAUNCHED_FLAG_DEFAULTS`.**

**Per-platform drill:** stop issuing leases → confirm device egress ceases within TTL → confirm the server path resumes → real send succeeds.

## 8. Requirements (delta from v1)

**Preconditions (P0) [R2-fix 6]:** read and file the Sleeper agreement's scope with a clause→requirement map that **explicitly asks whether it covers automated *unauthenticated* access, not only credentialed calls (OQ-1)**; read ESPN/Disney terms (none exists in-tree) before release 2; **complete MFL client registration** — MFL's exclusion from the move is contingent on the ~2.5× benefit it has not yet obtained; **a stable identifying `User-Agent` on Render's outbound platform traffic — GATED, NOT FREE [R3-fix B].** v2 called this a free one-liner. It is not. `sleeper_write.py`, `trade_block_service.py`, and `sleeper_trades_service.py` **deliberately impersonate desktop Chrome** because Cloudflare 1010-bans naked urllib UAs — the last of these is documented in-code as *the highest-frequency Sleeper class*. Sweeping an honest UA across them risks 1010-ing the live, proven `trade.send_in_sleeper` feature and the transactions sweep. Note also that Render's Sleeper egress has a **split identity today**: some paths already send `FantasyTradeFinder/1.0` while these three impersonate a browser — a fact that sits awkwardly against "responsiveness to Sleeper's request" and belongs in §2.1. Treat as a **probed, reversible change with a named rollback**, one module at a time, starting with the lowest-frequency path. The genuinely free part is the already-identifying paths plus MFL/Fleaflicker.

**Transport — CORRECTED in v3 [R3-fix A].** Round 2 proposed pinning the GraphQL **operation name**. **Both round-3 lenses independently rejected it, and the lens that proposed it retracted it.** `operationName` is a sender-chosen *label*: per the GraphQL spec it only disambiguates among multiple named operations in one document, so a single-operation document executes whatever its `query` text says regardless of the label. `x-sleeper-graphql-op` is decorative for the same reason. A compromised backend could send `{"operationName":"propose_trade","query":"mutation { <any_mutation> }"}`, pass the check, and drive the fleet at account-mutating operations on an allowlisted host **with a live credential attached** — the exact threat the control was written to stop. **A builder implementing the v2 text would ship a control that believes it pins operations and pins nothing.**

The corrected control, normative:
- **Host allowlist compiled into the binary**, never read from a server response. Unchanged, non-negotiable.
- **Allowlist the operation parsed out of the `query` document itself** — the client extracts the operation *type* and *root selection-set field name(s)* from the document string and matches those against a compiled set (`propose_trade`, `reject_trade`, `accept_trade`, `league_transactions_filtered`, …). **`operationName` and `x-sleeper-graphql-op` are explicitly non-authoritative and MUST be ignored for allowlist purposes.**
- **A document containing more than one operation is refused outright.** An aliased root field (`propose_trade: some_other_mutation`) resolves to the field *after* the colon.
- Everything else — headers, path, variables, the rest of the body — stays server-supplied and hotfixable. Path+method pinning applies to ESPN's REST surface, where it does work.
- *Why not pin the whole query document by hash:* it is strictly stronger, and it forfeits body-shape hotfixability — which is the property this architecture exists to preserve, since `build_propose_trade_body` inlines `league_id`, `draft_picks`, and `waiver_budget` into the query text. The root field is fixed and small; the body is not. **This tradeoff is stated rather than elided.**
**Parser requirements — NORMATIVE. Without these a builder rebuilds the v2 hole with a regex.**

1. **Non-empty, plain fields only.** `mutation { ...E } fragment E on Mutation { <any> }` is a *single* operation whose root selection set contains no field — so an "every root field is in the allowlist" check passes over the empty set. The extracted set MUST be non-empty, every root selection MUST be a plain field, and documents containing fragment definitions, fragment spreads, or inline fragments are **refused**.
2. **Lexer, not regex — and this is repo-grounded, not hypothetical.** `build_propose_trade_body` inlines `league_id`, `draft_picks`, and `waiver_budget` into the query **text** as literals, so under backend compromise the attacker controls document text *inside quotes* and can plant braces or decoy field names there. The parser MUST strip `#` comments, honour both single- and triple-quoted GraphQL string literals with escapes, and match **positionally** (the first token after the operation's opening brace) — never "the document contains an allowlisted name."
3. **Check EVERY root field, not the first.** A string-literal breakout that appends a second root field is caught only by an all-fields check.
4. **Reject transport batching.** "Multi-operation document refused" is per-document; a JSON **array** body carries N single-operation documents straight past it. The body MUST be a single JSON object, and the check MUST run on **the exact bytes sent** — parse-then-send the same string, never re-serialize.
5. **Enumerate the compiled set from real query documents, type-qualified.** Labels and root fields diverge in this repo: `ftf_token_probe`'s label is `ftf_token_probe` but its root field is `__typename`. Note that `accept_trade` and `league_transactions_filtered` do **not** exist in-tree, and `league_players` is an **unauthenticated public read that stays on Render** — it must NOT be in the device set. Enumerate `(operation type, root field)` pairs from actual query strings.
6. **Fail closed.** An unparseable document is refused and reported.

**Test obligations — these four cases are the whole control.** Failing-first unit tests for: the fragment-spread empty set; a string-literal breakout using an attacker-chosen `league_id`; an array-batched body; and an alias (`propose_trade: some_other_mutation` must resolve to `some_other_mutation`).

**Stated limit — the control bounds the VERB, not the OBJECT.** Arguments remain server-supplied, so a compromised backend can still drive a *sanctioned* `propose_trade` at arbitrary leagues, rosters, and assets with a live credential attached. This is unavoidable given the transport invariant (the device is deliberately not a decision-maker). The control stops arbitrary account mutation; it does **not** stop abuse of the sanctioned mutations. M4 is the detector there, not a prevention.

- **Signing is transit-integrity only and MUST NOT be described as mitigating backend compromise** — the key lives in the compromised environment.

**Transport invariant:** the server derives direction, permitted actions, and asset validity, and builds every request body. **The device is a transport, never a decision-maker.**

**Custody:** one SecureStore key, per-user envelope; `espn_s2` verbatim with byte-fidelity assertion; `user_id` mismatch ⇒ wipe; **no route ever returns a stored credential to a client**; `keychainAccessible: WHEN_UNLOCKED_THIS_DEVICE_ONLY` — currently unset, so the existing Sleeper JWT is **iCloud-backup eligible today**.

**Sentry:** live production DSN, default integrations, and **no `beforeSend`/`beforeBreadcrumb` anywhere in `mobile/src`** — the scrub is a net-new file, not a config tweak. A device transport carrying `authorization` creates a credential-leak path into a third-party SaaS that does not exist today.

**Unspecified states now specified:** on-device expiry; two devices; **uninstall is not revocation** (Keychain survives app deletion); offline (never queue a credentialed call); **permanent dual-path**; stale binary vs changed upstream; disconnect must be **global** via a server-side revocation epoch checked at lease issue.

## 9. Alternatives **[R2-fix D4]**

| Option | Verdict |
|---|---|
| **E — device custody, server transport** (credential on device, sent per-request, never persisted server-side) | **Rejected** — trades a bounded at-rest risk for an unbounded in-flight one (every call through Render logs, memory, Sentry, APM), Its rejection rests on that in-flight exposure, **not** on the egress delta — per §2.1 that delta is ~12 calls against several hundred that never move, so the egress argument is nearly weightless and defers to §2.1. **Retained in the table because it proves G1 is reachable without G3** — which is what makes §2.1's rationale honest. |
| Proxy / egress-IP rotation | **Held in reserve** as the fallback if the device path fails — not rejected outright. |
| Mirrored credentials (device *and* server) | Rejected — keeps full breach exposure while paying the whole migration cost. |
| Client background fetch | Rejected — no capability exists; dead after force-quit, which is the dormant user it would target. |
| Move everything including MFL | Rejected — forfeits the sanctioned registration benefit. |

## 10. Ship-now bundle — independent of every open question

Not gated on OQ-1, the agreement, or any device work: **(a)** the `WHEN_UNLOCKED_THIS_DEVICE_ONLY` one-liner; **(b)** the Sentry scrub; **(c)** the ESPN oracle fix *(done, `7dfcd16`)*; **(d)** **(e)** MFL client registration. *(The stable `User-Agent` was removed from this bundle — it is a gated probe, not a one-liner. See §8.)* This is most of "the right first ship" and none of it depends on the programme being approved.

## 11. Open Questions

**OQ-1 (BLOCKING, operator) [R2-fix 7 — unresolved].** Does Sleeper's agreement cover automated **unauthenticated** access, or only credentialed calls? Round 2 raised that §11.1 may bar crawling/scraping outright and §11.3 may reach access "whether directly" — which would put FTF's *largest* Sleeper surface (the bulk dump, per-session public sweeps, ADP) outside the agreement. **The orchestrator attempted to verify the wording and could not — the fetch truncated before §11.3.** This is not an engineering question; it is one to ask Sleeper directly. **If public reads are uncovered, that is a bigger finding than anything else in this document**, and it does not change this architecture (moving public reads is strictly worse) — it changes what the agreement needs to say.

OQ-2 ESPN release-2 gates: reachability probe + terms read + M9 clean. OQ-3 App Store 5.2.2 posture. OQ-4 `expo-updates` as a separate spike, evaluated **before** committing to this programme. OQ-5 is the full programme the right first bet at n=2, given §2.2's split and §10's bundle? OQ-6 lease TTL vs the offline user. OQ-7 two-device disconnect copy and deletion-law implications.

## 12. Doc corrections owed **[three places, not two]**

The dead Sleeper public-detection hypothesis is still carried as open in: **HLD §2.3**, **ADR-011 §6**, *and* the feasibility memo's own final section ("The one experiment that could still overturn this"). All three must be closed or the next reader regenerates the item.

---

## OPERATOR AMENDMENT — 2026-08-12, after sign-off

Two constraints the four review rounds spent significant effort on are **withdrawn by the operator**, and both were load-bearing. This amendment supersedes the sections named below; the rest of the document stands.

### A1 — Public-read coverage is not a concern. **OQ-1 is CLOSED.**
The document's single unresolved disagreement — whether Sleeper's agreement covers automated *unauthenticated* access — is withdrawn as a question. **No unresolved disagreements remain.** The reasoning in §2.1 is unaffected: public reads stay on Render because moving them is strictly worse, which was never contingent on the answer.

### A2 — Credential migration is not a concern. **§6 largely dissolves.**
The operator is effectively the only real user; others have tested lightly enough that breaking their link is acceptable. **Interpretation, stated so it is checkable: no migration machinery is required — a clean cutover in which stored credentials are deleted and users re-link is acceptable.** If that reading is wrong, this amendment is wrong.

**What that removes.** Most of the programme's cost was migration machinery, not the transport:

| Withdrawn | Was |
|---|---|
| §6's phased migration (M1–M4), dual-run, and the deletion gate | The largest section, and the hardest to get right |
| The 14-day cooling-off and the point-of-no-return marker | Restored at round-2 objection 3 — no longer needed |
| The pre-2026-07-12 cohort problem | Round-2 objection 8, in full |
| "Permanent dual-path" as a steady state | A forever-maintenance burden, and forever-testing |
| The dual-custody window (**"strictly worse than today for an unbounded period"**) | The programme's largest self-inflicted risk — **gone entirely** |
| M7 (dual custody), and M2's `nullable=False` schema collision | M2 becomes "delete the row"; no `ALTER` decision needed |
| Two-device revocation as a migration concern | Still a design question, no longer a migration one |

**What survives untouched:** the transport design and its normative parser requirements; leases as the only device rollback primitive; the compiled host allowlist; credential storage on device; the test-rail gap; the Sentry scrub; the `keychainAccessible` fix; the no-OTA risk; and the ESPN release-2 gates (reachability probe + terms read).

**Net effect on the recommendation.** The case in §2.2 was weakened by measurement — a modest resilience benefit, and Sleeper's volume warning describing traffic this programme never moves. That reasoning is unchanged. **But the cost side just fell sharply**, since the expensive part was migration. OQ-5 ("is the full programme the right first bet at n=2") should be re-answered against the smaller number, and the answer is now more likely to be yes.

**Do not silently generalise this.** These withdrawals hold *because* the user base is ~1. They must be revisited before the public App Store release — at which point migration machinery becomes necessary again for anyone who links between now and then.


---

## Reconciliation Log

**Document type:** PRD · **Rounds run:** 4 (cap) · **Converged:** yes — both lenses signed off in round 4 · **Lenses:** A = Product/Feasibility, B = Engineering/Adversary

### Round 1 — independent drafts, wrong premise
Both lenses were briefed that the goal was reducing **call volume** so Sleeper would stop blocking FTF. Both drafted against it and both concluded the change was misaimed, since the high-volume Sleeper traffic is unauthenticated public reads that stay on Render. **The operator corrected the framing** (the driver is the Terms, governing *credentialed* access) and both drafts were re-run.

### Round 2 — 9 blocking objections, no sign-off
- **B raised 6.** (1) The §11.1 rationale was unsupportable and the *actual* trigger — Sleeper's own "vary where the calls come from" request — had been dropped from the document entirely. (2) Three metrics were not metrics: one true by construction, one reportable only by an already-misbehaving client, one unmeasurable because the test rails count Sleeper only, server-side. (3) The migration window was buried and the orchestrator's condensing had **lost two safeguards** from the source design (the 14-day cooling-off and the point-of-no-return marker). (4) Rollback was undefined and self-contradictory — and `'espn.link': true` is compiled into the binary, so flags **fail open**. (5) The closed-app push was foreclosed for all platforms on evidence that only killed Sleeper's route; MFL's APIKEY path is live and structurally cannot write a trade. (6) MFL client registration was dropped as a requirement though the whole MFL carve-out depends on it.
- **A raised 3.** (7) The claim that the Terms do not touch public reads may be false — **unresolved, carried as OQ-1**. (8) The silent Sleeper migration is impossible for users who linked before 2026-07-12: they have a server row and no device copy, the credential-return path is banned, and the deletion gate never fires. (9) The document could not support its own build/no-build decision without the credentialed-vs-public traffic split.
- **Resolved:** 8 of 9 fixed in v2. The orchestrator **measured** the traffic split (9) from production: ~12 credentialed calls against several hundred public.

### Round 3 — 2 blocking, converged on one
- **Both lenses independently rejected the round-2 transport control**, and **A retracted its own proposal**: pinning the GraphQL `operationName` constrains a sender-chosen *label*, not the executed document. A compromised backend could label a request `propose_trade` while the query text ran any mutation. Replaced by parsing the operation type and root selection-set field out of the document itself, with the label declared non-authoritative.
- **A also caught an orchestrator error:** the identifying `User-Agent` had been placed in the "free, ship-now" bundle, but three Sleeper modules **deliberately impersonate Chrome** against Cloudflare 1010 bans, one of them the highest-frequency Sleeper path. Reclassified as a gated, per-call-site, reversible probe.
- **B's most valuable non-blocking note**, adopted: §2.2's measurement also undercuts benefit #1 (responsiveness), because the volume Sleeper warned about is the public traffic this programme never moves. Conceded explicitly in §2.1.

### Round 4 — both signed off
No blocking objections. B supplied six **normative** parser requirements without which "parse the root field" could be rebuilt as a defeatable regex — including the fragment-spread empty set, string-literal breakout (repo-grounded: `build_propose_trade_body` inlines attacker-influenced literals into the query text), transport batching via a JSON array, and the fact that op labels and root fields **diverge in this repo** (`ftf_token_probe` → `__typename`). All folded in, with the control's honest limit stated: it bounds the **verb**, not the **object**.

### Unresolved disagreements — **CLOSED by the operator amendment above; retained for provenance**

**OQ-1 — does Sleeper's agreement cover automated *unauthenticated* access?** Carried unresolved to the operator.
- **A's position:** §11.1's crawl/scrape bullets and §11.3's "whether directly" wording may reach FTF's public reads (the bulk dump, per-session sweeps, ADP) — which would place FTF's *largest* Sleeper surface outside the agreement.
- **A's own later correction:** the wording recorded in-tree reads "through any account, credential, or authentication mechanism belonging to a user," which is structurally limited to credentialed access; the "whether or not that third-party is itself a user" phrase belongs to §11.2.
- **Orchestrator:** attempted to verify against the live Terms; **the fetch truncated before §11.3 and the wording could not be confirmed.**
- **Recommendation:** ask Sleeper directly whether the executed agreement covers unauthenticated automated access. It does **not** change this architecture — moving public reads is strictly worse — it changes what the agreement needs to say.

### Findings surfaced by the review that were not about the document
- **A live ESPN bug**, root-caused and **shipped fixed** (`7dfcd16`): credential verification discarded its probe's result while the parser never raises, so a dead pair was stamped verified. Reproduced twice in production before the fix.
- **A latent FAAB bug** in `sleeper_write.build_propose_trade_body`: `json.dumps` emits quoted keys, which are invalid GraphQL object-literal syntax. Dormant only because nothing populates FAAB today. Filed separately.
- **`keychainAccessible` is unset**, so the existing Sleeper JWT is iCloud-backup eligible today — and changing it only affects future writes, so closing the exposure needs a read-then-rewrite migration.

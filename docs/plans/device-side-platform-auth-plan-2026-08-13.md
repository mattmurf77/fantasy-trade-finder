# Plan: Device-Held Platform Credentials — Release 1 (Sleeper)

> **Status:** dual-agent candidate v1, entering cross-review.
> **Authoritative inputs, none relitigated:** [PRD](device-side-platform-auth-prd-2026-08-12.md) incl. A1/A2/A3 · [HLD decisions](device-side-platform-auth-hld-decisions-2026-08-13.md) D1–D5 · [LLD](device-side-platform-auth-lld-2026-08-13.md) §§1–8 + Reconciliation Log.
> **This document answers what the LLD does not:** who does what, how long it takes, which decisions precede code, what stops the programme, and how the operator steers and reverses it.

---

## 0. The decision in ordinary words

The design is done and validated — 24 blocking objections resolved across four review rounds, six claims measured on both database engines. What's left is a build of roughly **18–25 attended working days over 4–6 calendar weeks**, ending in one real trade sent from your phone, a rehearsed rollback, and a 7-day quiet soak.

Both drafting lenses reached the same sequencing independently, so it is presented as agreed rather than argued:

- **Start the safe bundle (S0) now, unconditionally.** It fixes exposure that exists today whether or not the programme proceeds, and it forecloses nothing.
- **Land the two cheap server stages (S1–S2) behind it.** They are correct under every future — programme continued, deferred, or abandoned.
- **Stop before S3 for one written decision:** the `expo-updates` question the PRD ordered answered first (OI-9), plus a 30-minute device fact (OI-12). Gate C in §8 is the checklist.
- **One event is the go/no-go** — the first real send at S7 — and one specific failure there (Cloudflare rejecting the phone's TLS fingerprint) means **stop, not iterate**, because no device-side fix exists.

Five decisions are yours. Every one has a recommended default in §1, so a single "yes to all defaults" starts work the same day — with the caveat that three of them get re-confirmed in writing before other people's devices are involved (Gate F).

---

## 1. Decisions required before any code

The LLD carries 20 open items; most are engineering calls with named owners. **Five need the operator.** Nothing below blocks S0/S1/S2 starting immediately.

| # | Decision | Recommended default | Decided by | Cost of deferring past that point |
|---|---|---|---|---|
| **OI-9** | `expo-updates`: evaluate before committing (PRD OQ-4; "upstream of the whole programme") | **Run a 1–2 day spike in parallel with S0/S1; decision written to `living-memory/DECISIONS.md` before S3.** Both lenses' full reasoning in §10. | **Gate C** — before S3 | If the spike would have changed your mind, everything after S3 is sunk cost. The spike costs 1–2 days; skipping it saves almost nothing and risks weeks. |
| **OI-3** | Two-device model: single-holder (second link overwrites `device_id`, LLD §3.1) vs multi-holder | **Single-holder, as written.** You have one phone, and single-holder is the only model that can't leave a forgotten device holding a live credential. | Before S4 (schema PK); **re-confirmed in writing at Gate F** | The PK ships dark at S1 and stays cheap to change until the first `platform_links` row is written at S7 — so Gate F's re-confirmation is a real decision point, not ceremony. After rows exist, changing it is a migration on a live custody table. |
| **OI-14** | Vault on `user_id` mismatch: PRD:144 says wipe; LLD §2.7 returns `null`, wiping only from session establishment. S0 *implements* the LLD reading (`null`, no wipe); Gate C ratifies or overrides it before any send path consumes it — the mismatch path is only exercised from S4. | **Accept the LLD deviation.** The PRD-literal version lets any caller with a stale id destroy the only copy of the credential. | **Gate C** — before the vault ships | Builders guess between two disagreeing normative documents, inside a custody control. |
| **OI-4** | Old-build reinstall silently restores server custody (H4): accept-and-monitor, or refuse the link? | **Accept and monitor.** The alternative breaks that user's sends entirely — the wrong failure direction. Internalize the consequence: **M1 can go non-zero without an incident**; non-zero M1 is "investigate," never "page." | Before S8; **re-confirmed at Gate F** | Purely interpretive until testers exist: someone reads M1 as a breach signal. |
| **OI-15** | `DELETE /api/sleeper/link` needs a verified session; under device custody it is the only revocation writer, so a lapsed session cannot revoke | **Keep the gate for release 1; document "re-login, then disconnect"; revisit before any public release.** | Before S8; **re-confirmed at Gate F** | Negligible at n≈3. Real before volume: revocation is the user's only recall and it's behind a login they may have lost. |

**Why the double-confirmation on OI-3/OI-4/OI-15:** the execution lens wanted all five ratifiable in one sitting so work starts Monday; the risk lens held that decisions governing *other people's devices* may not be defaulted. Both are right at different stages — so the defaults are ratified now for build purposes, and Gate F requires the written answers before the allowlist widens beyond you. Silence is not a waiver (the repo's own feature-gate rule).

**Everything else in LLD §8 is an engineering default, ratified implicitly:** OI-2 keep the Python parity guard · OI-5 `graphql` as a mobile devDependency (never bundled; DEPENDENCIES.md entry) · OI-18 device synthesizes `x-sleeper-graphql-op` from the parsed root field · OI-19 add `epoch` to the digest at S4 · OI-1/OI-10/OI-13 measure, don't debate · OI-11 stalled-sweep alert ships with S4 as an **exit criterion** · OI-16 answered at S2 · OI-17 fingerprint parity check ships with S5 · OI-20 analytics events specced before S4. OI-7/OI-8 are follow-ups, not this programme.

**Gate posture:** schema, API contracts, feature flags, analytics events — all four bright-line categories. **Full gates; express is categorically unavailable for every stage of this programme**, including a one-line corpus addition after S6 (it feeds two independent implementations).

---

## 2. Work breakdown

One operator directing agent sessions; "days" are operator-attended working days; backend and mobile lanes have disjoint file ownership and can run as parallel sessions.

| Stage | Concrete deliverables (LLD ref) | Size | Days | Parallel with | Serial dependency |
|---|---|---|---|---|---|
| **S0** | FAAB object-literal fix + tests (§7.0); Sentry scrub — `beforeSend`/`beforeBreadcrumb`/`tracePropagationTargets: []` (§5.2); `credentialVault.ts` with verify-then-delete legacy migration + `check-vault-subsumes-legacy.js`, `check-keychain-accessible.js` (§2.7) | S/M | 2–3 | everything | none |
| **S1** | Three tables via `create_all`; startup assertions on the unique index **and** the CHECK, both dialects (§3.1–3.3, §5.4 item 6) | S | 0.5–1 | S0 | none |
| **S2** | `GET /api/sleeper/link` union + `revoked` + custody precedence, server only; OI-16 spec; `test_platform_link_contract.py` incl. the both-rows rollback case (§2.5) | S/M | 1–1.5 | S0, spikes | S1; **Gate B** |
| **S3** | **The risk concentration.** OI-12 spike result in hand first (§4.2.1); `gqlGuard.ts` import-free lexer+parser (§4.2); Python parity guard; shared corpus ~45 rows, failing-first (§6.1a); differential oracle vs `graphql-js` (§6.1b); 10k differential fuzz + parity-divergence auto-append (§6.1c); enum-coverage assertions (§6.1d); `parse_graphql_response` extraction (§4.4) | **L** | **6–9** | S0–S2 complete underneath | FAAB fix (corpus rows 9/10 encode the sequencing); **Gate C** |
| **S4** | `/lease` with the dialect-branched transaction (§4.1); `/outcome` idempotent UPDATE (§4.4); `platformTransport.ts` (§2.6, §4.3); `/outcome`-only retry opt-in — a real `client.ts` change (§4.4); sweep cron + **OI-11 alert as an exit criterion** (§4.7); rails swap + sinkholed negative control **in the same PR** (§6.4); dialect-parameterised race tests (§6.3); OI-20 analytics registered | **L** | 5–7 | Maestro authoring; doc batch | S1, S3 |
| **S5** | Sticky-revocation rewrite, all five §4.5 sites; `X-FTF-Caps` + `X-Device-Id` emission (§2.4's three prerequisites); vendored `1.13.2` fixture test (§6.2); `check-transport-caps-fingerprint.js` (OI-17); Maestro flow (§6.5); scope block filed | M | 2–3 | can start against S2's spec | S2 |
| **S6** | TestFlight build carrying S2+S5 — **the point of no return** (§4 below) | S | 0.5 + 1–3 elapsed | — | S5; **Gate D** |
| **S7** | Both flags on together, allowlist = operator only (§7.2); Sentry release-build capture at tracing 1.0; **one real send**; rollback drill same day; 7-day soak | S | 1 + 7 elapsed | — | S6; **Gate E** |
| **S8** | Widen allowlist (~2 testers); no flag changes; soak per widening | XS | ~0 | — | S7; **Gate F** |

**Totals: ~18–25 attended days, ~4–6 calendar weeks**, the last ~2 weeks mostly elapsed soak and TestFlight latency. (Per-stage maxima sum to ~26; the total assumes the stated S4/S5 overlap. **The total is an uncalibrated stage-sum** — it excludes gate/review friction, which for the LLD alone was 4 rounds and 24 blocking objections, and it pre-absorbs the OI-12-absent branch as "top of range" when the LLD calls that branch a sub-project. **If Hermes lacks `TextDecoder`, S3 is re-estimated at Gate C rather than assumed to fit the ceiling.**)

**Why S3 is honestly the risk concentration:** a hand-written lexer/parser that *is* the security control, implemented twice, pinned by corpus + oracle + fuzz — with a possible hand-rolled UTF-8 validating decoder hiding inside if OI-12 comes back "Hermes has no `TextDecoder`," which moves the estimate to the top of its range and adds decoder corpus rows (overlong encodings, lone surrogates). Budget it; don't shave it.

**One stage, one PR** (S0's four independent items excepted). The gate design depends on ordering — the rails swap must land *with* the transport, S5 must be in the shipped build with S2 before custody activates — and a batched S3+S4+S5 PR makes it impossible to say which gate a green CI corresponds to.

---

## 3. The critical path

```
OI-12 spike ─▶ S3 guard+corpus+oracle+fuzz ─▶ S4 lease/outcome/transport ─▶ S5 client rewrite ─▶ S6 build ─▶ S7 send+drill+soak ─▶ S8
  (0.5–1d)           (6–9d)                        (5–7d)                     (2–3d)         (+1–3d elapsed)     (1d + 7d elapsed)
```

S0, S1, S2, and the OI-9 spike all fit underneath the first two weeks without extending it.

**On the path and easy to underweight:** the OI-12 spike (a device fact; CI under node proves nothing); the FAAB fix; the rails swap landing inside S4's PR (omit it and S4's own exit gate is unsatisfiable); the Sentry release-build capture (a hard precondition of the S7 send — book it for the day the S6 build clears processing, not the morning of the send).

**Looks urgent, is not on the path:** §7.6 doc updates (batch at S4/S5) · Maestro authoring (parallel with S4) · OI-6 digest-window tuning (no data until S7 produces some) · OI-8 pending-read · multi-device anything · disconnect copy polish · all of ESPN · MFL registration · dashboards beyond the two counters and two alerts the LLD names.

**Repo-specific sequencing hygiene** (both prior incidents are documented): every stage branches from freshly-fetched `origin/main`, never a long-lived programme branch that drifts for weeks; implementing sessions re-resolve the LLD's ~80 citations **by content** (`git grep -n`), never by line number — `backend/server.py` line numbers will drift under any concurrent merge; every stage ends with the recovery-ledger worktree sweep (91 stale worktrees once broke an EAS upload, and S6 *is* an EAS build).

---

## 4. Irreversibility map

The LLD's §7.2 marks every stage but S6 "reversible." True, and it understates what each stage *commits*:

| Stage | Undoable? | What it permanently commits even if "reversed" |
|---|---|---|
| S0 | yes | Nothing. Verify-before-delete migration retains the legacy key even on failure. **The one genuinely free stage.** |
| S1 | yes (drop dark tables) | Nothing while dark. |
| S2 | **yes before S6; practically no after** | Once any S6 binary keys wipes off `revoked === true`, the server must emit `revoked` correctly **forever**. Reverting the union after S6 recreates the mass-wipe HLD blocking fix 5 exists to prevent. |
| S3 | yes | Corpus vocabulary (code-point unit, reason names, `"{op_type}:{root_field}"` wire form) becomes frozen, append-only. |
| S4 | yes — flags off | The rails swap must be swapped *back* if S4 is ever reverted, or the sim gate goes vacuous. **The digest canonicalization changes the wire bytes of the one call proven live** (§3.5 vs the capture-verbatim `sleeper_write.py:284`) — and it lands on the *server* path shared with R-ROLLBACK, so a Cloudflare sensitivity to it would degrade the recovery path. Verify a real server-path send after `serialize_body` lands, **at S4, not S7.** |
| S5 | yes until built | The caps-fingerprint canonicalization freezes the moment one binary ships carrying it. |
| **S6** | **NO** | **The true point of no return.** No OTA, so every defect in this build's guard, vault, caps constant, or five rewritten call sites is permanent in the field until the next build is shipped *and installed* — and TestFlight permits reinstalling old builds (OI-4), so "everyone updated" is not stable either. From S6 forward, `TRANSPORT_OP_SETS` is append-only and the `GET` contract is frozen. |
| S7 | yes — flags off + drill | An in-flight lease cannot be recalled (I2): reversal stops **new** sends within 5 minutes, nothing already dispatched. |
| S8 | yes per-device — shrink the allowlist | Each shrink produces §2.5's both-rows state on that device. Reversible **only because the custody-precedence rule works** — which is why Gate B re-reviews it (it is the least-reviewed line in the LLD, per its own Reconciliation Log). |

**The load-bearing sentence of the plan: everything provable only on a device must be proven before S6, because S6 is where "fix it next build" stops being a plan and becomes a hope.** Gate D is that list.

---

## 5. The failure modes that end the programme

Ranked by irrecoverability × silence. Annoyances excluded.

**F1 — R7: Cloudflare rejects the iOS TLS/HTTP-2 fingerprint.** No device-side fix, no hotfix, no OTA — you cannot choose NSURLSession's fingerprint. The PASS 4/4 probe was a point-in-time fact about Cloudflare's posture, not a property of the design. Mitigation *is* the programme's other deliverable: R-ROLLBACK, in-tree, flag-reachable, in CI, drilled at S7 — and because R7 can manifest *after* S8, the CI leg runs on every release for as long as the device path exists. **If R7 manifests: execute the drill, leave flags off, close the programme.** Write that in the runbook now, so nobody improvises a WKWebView transport under incident pressure (the HLD names it as an R7 lever *at the cost of the never-parse rule* — taking it up is a new design with its own review, not a patch).

**F2 — OI-12: Hermes may not provide `TextDecoder`.** Zero occurrences in `mobile/src`; CI runs where the global exists for free, so every green build is non-evidence. If absent, the import-free rule forces a hand-written validating decoder **inside the security control** — a sub-project, not a task. Mitigation: a 30-minute dev-build experiment on the operator's phone, run **before S3 is scheduled**. (The base64 path is different: only `gqlGuard.ts` is import-free, so a missing base64 global costs `platformTransport.ts` a dependency, not a second hand-rolled primitive.)

**F3 — the parser is wrong in a way the tests do not catch.** The three defense layers share one blind spot: inputs nobody generated. A document class the guard accepts, `graphql-js` parses, and *both* implementations extract identically wrongly is structurally undetectable — identical wrongness is the one thing a parity check ratifies. Mitigations, both cheap: (a) a third fuzz seed corpus drawn from `graphql-js`'s own test fixtures — valid documents the guard has never seen; most refuse at the allowlist, and the assertion is *no throw + verdict parity*; (b) the defense in depth that already exists and must survive review pressure: even a wrong parser can only approve an op landing in a **two-entry** compiled set. An attacker needs a parse differential *and* a collision into `propose_trade`/`reject_trade`. This is why OI-2's Python parity guard may not be cut.

**F4 — the silent-G1-defeat class.** Three mechanisms quietly restore server-side token rows while everything looks green: `linkSleeperToken` shipping without `X-FTF-Caps` (every session replay writes a row), registry pruning (forbidden, §2.1, but only by convention), and OI-4's reinstall. None is programme-ending — the failure direction is "working feature, weaker custody" — but together they mean **M1 is not self-verifying**. Mitigation: M1 breaks down non-zero counts by cause (log `transport_v` at link time), and the unknown-fingerprint alert exists from S5.

**F5 — the sweep cron as a single point of liveness (OI-11).** Stalled cron ⇒ every open lease holds its lock indefinitely ⇒ affected users pinned on `409 send_in_flight` *and* walked into `too_many_outstanding`, no self-recovery. The only component whose failure converts "sometimes degraded" into "stuck with no user-side remedy." The alert is an **S4 exit criterion**, and a cron stalled >1 hour with open leases is a standing flags-off trigger (§8).

---

## 6. Kill / pause criteria at S7 — classify before touching anything

| Observation on the one real send | Read | Action |
|---|---|---|
| `ok`, `transaction_id` parsed, offer visible in Sleeper | pass | Run the drill (§7), then start the 7-day soak clock. |
| **Edge rejection: Cloudflare error page, 1010, or a JS-challenge body in `response_b64`** | **R7 — the kill criterion** | **STOP. Do not iterate.** Not one day of header tweaks: the design already forbids the spoofing headers on device, and the probe passed 4/4 — an edge rejection now is a fact about Cloudflare, not your code. Flags off, drill, decision memo, park the programme (F1). |
| 200 with GraphQL `errors` matching the auth heuristic, or 401/403 | R8 — credential, not architecture | Pause, re-capture, retry. Not a kill. |
| `guard_refused` / `lease_self_check_failed` | our parser bug (M4 formally, but the only device is yours) | Fix via corpus row, re-run. **Escalates to a programme pause if parity cannot be stabilized in two fix cycles.** The two-cycle rule is the *operational test* for §8's semantics-vs-corpus abort: a divergence a corpus row fixes was a corpus gap; one that survives a corpus row is semantic, and the dual-implementation premise goes back to review, not to a third patch. |
| `network_error` / `unknown`, first occurrence | indeterminate by design (I1) | Check Sleeper by hand — at n=1 you can. Offer present ⇒ transport worked, reporting is broken: fix reporting. Absent ⇒ retry once; if it persists, go to the next row — do **not** keep iterating. |
| **Persistent `network_error` from the device while a same-day, same-credential server-path send succeeds** | **suspected R7 at the handshake layer** — TLS/HTTP-2 fingerprint enforcement can manifest as resets/timeouts with **no response body at all**, so the clean-403 row above never fires | **Stop iterating.** Re-run the 4/4 reachability probe from the device. Probe fails ⇒ R7, treat as the kill row. Probe passes ⇒ a transport bug in our code — debug that, not headers. The server-path control send is the discriminator, and R-ROLLBACK means you always have it. |
| **A single, transient edge challenge** (one JS-challenge page, then clean sends) | possibly noise — Cloudflare serves challenges for network-reputation reasons unrelated to the app | Pause device sends, re-probe. One transient challenge does **not** trigger "close the programme" — over-triggering the terminal action on one noisy observation is its own failure. **Recurrence across sessions or devices ⇒ R7, close.** |
| **Pre-send Sentry capture shows any injected header on a platform request** | scrub defective | **Hard stop before the send** — a precondition, not a finding. |

**Soak criteria:** M4 = 0 and M8 divergence = 0 for 7 days, **with monitoring proven live by synthetic injection before the clock starts** — otherwise "zero for 7 days" means "nobody looked for 7 days." Any M4 event from a non-operator device at S8: shrink the allowlist to zero the same hour, then investigate. The allowlist, not the flag, is the per-device brake.

**"Kill" means:** flags off, allowlist empty, drill confirmed, CHANGELOG + HANDOFF written, decision memo filed. Everything shipped through S6 stays — all of it is justified independently and none of it degrades the server path.

---

## 7. Rollback rehearsal — a calendar item, not a paragraph

- **Rehearsal #1 — S7, same day as the first successful send, before the soak clock starts.** ~45 minutes, on your phone, on the shipped build: (1) `platform.device_transport` → false; confirm `/lease` 404s and the client **silently** falls back per §5.3's `feature_disabled` row — no user-visible error is part of the pass criteria; (2) device egress ceases within 5 minutes; (3) `sleeper.device_custody` → false, reconnect, confirm a token row is written; (4) `POST /api/trades/propose` end-to-end on the same build. Flip back on. **The drill produces an artifact:** a dated TEST_LEDGER entry with the real send's lease id, the flag-off timestamp, the observed egress stop, and the server-path transaction id. **No artifact, no S8.**
- **Re-run at every S8 widening** (the cost of knowing rollback works is one coffee) and **once per release touching `mobile/src/transport/` or the flag surfaces**, for as long as the dual path exists. Between rehearsals, `test_rollback_server_path_ci.py` is the bit-rot guard; a red run there is a broken rollback and a merge blocker, not a flaky test.
- **Retirement of the server path is a separate future decision with its own sign-off** (A3). This plan schedules nothing toward it.

---

## 8. Go / no-go gates — applicable without re-reading the LLD

**Gate A — start S0: GO now.** No preconditions.

**Gate B — start S2** (S1 has no serial dependency and needs no gate)**:**
☐ OI-16 answered (epoch semantics when only a token row exists).
☐ §2.5's custody-precedence rule + §5.3's `feature_disabled` row re-reviewed by a **fresh adversary-lens subagent that authored neither the LLD nor the S2 change**, scoped to attacking the both-rows rollback state specifically, producing a **dated written verdict filed in the programme docs**. Named performer, independence requirement, and artifact are the point: without them, the S2 implementing session reads the two sections, thinks for a minute, and checks the box — self-attestation by the party the review must be independent of, on the LLD's own least-reviewed lines, which are the rollback path. **No verdict artifact, no S2 merge.**
☐ `test_platform_link_contract.py` covers the both-rows state.

**Gate C — start S3. The programme's real decision gate:**
☑ **DISCHARGED 2026-08-13 — OI-9 resolved DO NOT ADOPT** ([memo](device-side-platform-auth-oi9-expo-updates-memo-2026-08-13.md), **D-048**). Note the sequencing correction in §10: `expo-updates` is native, so it could never have blocked S3 — it is a Gate D build-config question and should not have sat on this gate.
◐ **OI-12 desk research done** ([memo](device-side-platform-auth-oi12-runtime-primitives-memo-2026-08-13.md)): RN 0.81.5's polyfill chain installs **no** `TextDecoder`/`atob`/`btoa`, and Hermes will not supply them (WHATWG/HTML APIs, not ECMAScript). **Still owed:** the 30-second on-device `typeof` confirmation (snippet in memo §2), evidence in TEST_LEDGER. If confirmed absent, **re-estimate S3 here** rather than assuming its 6–9 day ceiling holds.
☐ **OI-21 — do not build the host allowlist on `new URL()`.** RN's `URL` is a regex polyfill while `fetch` parses natively; measured **0 bypasses but 4 false refusals**, one of which pages the operator. Adopt the compiled exact-endpoint match at S4 (memo §3). Settled by measurement — no device check needed.
☑ **OI-14 answered** — operator ratified the LLD reading (`null`, no wipe) in **D-047**, 2026-08-13.
☐ `MAX_BODY_BYTES` measured against the largest real body (OI-1).

**Gate D — cut the S6 build. The point of no return; nothing is skippable:**
☐ §6.6 items 1, 5, 6 verified on a real device, evidence in TEST_LEDGER (iCloud-backup exclusion; Keychain across update *and* delete-reinstall; AppState timing).
☐ §6.6 item 7: a **real 1.13.2 TestFlight binary** against the new `GET` contract keeps its credential — the fixture test is a proxy, not a substitute.
☐ `check-transport-caps-fingerprint.js` green (a mismatch is 426-for-everyone, permanently, for this binary).
☐ All five §4.5 sites rewritten; old-binary fixture green; **`linkSleeperToken` emits `X-FTF-Caps`** (the silent-G1-defeat check).
☐ A real server-path send verified **after** `serialize_body` landed (the wire-bytes change rides the recovery path too).
☐ *Recommended, not required:* a **proxy Sentry capture** on a release-configuration dev build with flags overridden locally — same scrub code, not the shipped binary. It cannot substitute for Gate E's shipped-build capture, but it surfaces a scrub defect **before** the point of no return, converting a Gate E hard stop from "reship" into "fix before cutting the build."
☐ OI-20 events registered; sweep alert (OI-11) and unknown-fingerprint alert (§2.1) demonstrably firing.
☐ The drill script written into `docs/runbook.md` — before the build, not after.

**Gate E — S7 flags on (both together, operator device only):**
☐ Gate D's build installed on the operator's device.
☐ **Sentry capture from the shipped S6 build, tracing forced to 1.0, taken with flags on but BEFORE the first send: no injected header on the platform request.** This can only exist once flags are on — a device platform request requires the transport live — which is why it is a Gate E pre-send precondition and not a Gate D checkbox; an earlier draft placed it at Gate D, where it was unsatisfiable and would have been waved through, on a credential-leak check. A dirty capture is a hard stop before the send (§6's pre-send Sentry row).
☐ One real send, lease id logged.
☐ Drill executed same day, all four steps, artifact in TEST_LEDGER.
☐ M4 pager + M8 divergence query proven by synthetic injection before the 7-day clock starts.

**Gate F — S8 widening:**
☐ 7-day soak clean with monitoring known-live.
☐ **Written answers to OI-3, OI-4, OI-15** — these govern other people's devices and may not be defaulted past this point.
☐ Per-widening: soak clean before the next device.

**Standing abort triggers, any stage:** R7 manifests — per §6's graduated read: a clean edge rejection, a failed device re-probe, or challenges recurring across sessions; never a single transient observation (→ close the programme) · guard parity divergence unresolvable by a corpus addition — the implementations disagree on *semantics* — stop S3, the dual-implementation premise has failed · any M4 event during S7/S8 from the paging set (`guard_refused`, `auth_header_present`, `host_not_allowed`, `method_not_allowed`, `header_not_allowed`): flags off first, investigate second · sweep cron stalled >1 hour with open leases: flags off until the alert path is fixed.

---

## 9. Self-attested vs. verifiable — where the plan would silently slip

**CI enforces (slip is loud):** S0–S5's CI gates are machine-checked (Gate B's adversarial verdict is the exception, and it is artifact-bound below), and the S4 negative control is the rare gate that fails when the *fence* breaks, not just the feature.

**Self-attested (slip is silent), each now bound to an artifact:**

- Gate B's adversarial re-review of the rollback lines → the dated written verdict (§8). No verdict, no S2 merge.
- S7's "one real send + drill" → the TEST_LEDGER artifact (§7). No artifact, no S8.
- The soaks → monitoring proven live by synthetic injection before each clock starts.
- **§6.6's seven device-only facts** — the LLD gives them a section but no stage, owner, or evidence format; left as-is they get checked "implicitly by S7 working," which is exactly the self-attestation to forbid. Bound here: item 4 (Hermes primitives) at Gate C; items 1, 5, 6, 7 at Gate D; item 3 (the Sentry capture) at Gate E, pre-send; item 2 *is* the S7/S8 soak and is never fully discharged. Each check is one TEST_LEDGER line: date, device, build, observed result.
- The operator decisions → Gates C and F name them; the implementing session may not resolve them by writing code.

---

## 10. Should `expo-updates` come first? Both lenses, then the recommendation

**Agreed by both:** the spike runs now (1–2 days, parallel with S0/S1), the decision is written down before S3, and adopting OTA *without* the spike would be worse than either ordering — because OTA interacts with this design's core premise.

**The execution lens's argument — and it is new relative to the source docs:** the programme's security claims are *compiled-in* properties ("host allowlist compiled into the binary, never read from a server response," PRD §8). The guard, the allowlist, and the vault access live in the JS bundle. `expo-updates` makes that bundle server-swappable, which moves the update channel **into the trusted computing base of a design whose stated threat is a compromised backend**. Not a disqualifier — signed updates and scoped exclusions exist — but a real design question that deserves its own reviewed decision, and bolting it on first, under schedule pressure, in front of a custody programme, is how it would be gotten wrong. Also: OTA does not touch R7, the decisive risk, at all.

**The risk lens's argument:** nearly every hard constraint in this plan — the irreversible §7.2 ordering, the S6 point of no return, the old-binary machinery, OI-4's permanent residual — is downstream of "no OTA." Adopt it and "field builds cannot be fixed" becomes "fixed in hours," deleting or demoting most of what makes this plan brittle. And the urgency picture cuts the same way: the Sleeper agreement already covers the current architecture (PRD §2.1), the traffic Sleeper's warning describes stays on Render regardless (§2.2), and at n=1 the realized custody benefit is one JWT. There is no clock.

**RESOLVED 2026-08-13 — the spike ran and the answer is DO NOT ADOPT.** Memo: [`device-side-platform-auth-oi9-expo-updates-memo-2026-08-13.md`](device-side-platform-auth-oi9-expo-updates-memo-2026-08-13.md). Decision recorded as **D-048**. Gate C's OI-9 checkbox is discharged.

**The independent evaluation corrected this section on three counts, and the corrections are the point of having run it:**

1. **My predicted outcome was impossible, not merely wrong.** I expected "adopt later, with `mobile/src/transport/` carved out of OTA scope." There is no subtree carve-out — the unit of replacement is the **whole JS bundle**. The only real carve-out is relocating the allowlist and op set into native code, which would destroy the §6.1 test harness (transpile-real-TS-under-node, the `graphql-js` differential oracle, the 10k fuzz). That is a strictly worse deal than not adopting.
2. **My trusted-computing-base argument was overstated.** I claimed OTA moves the update channel into the TCB of a design whose adversary is a compromised backend. The adversary is **Render**; the update channel is **Expo/EAS** — a *different* trust domain, and a Render compromise yields no OTA publish. The accurate cost is narrower but still disqualifying: OTA adds a second remote-code path with vault access, gated by the operator's Expo token. That token already permits a malicious *build* — but slowly, versioned, Apple-processed and install-gated. OTA makes the same reach **instant, silent, and invisible in the version string**. Signing narrows forgery to the key holder, who is the *same principal on the same laptop*, so the two compromises correlate to near unity — and signing does nothing about a signed rollback to an older valid bundle.
3. **OTA obsoletes none of the old-binary machinery.** I costed that machinery at ~2–3 days and credited OTA with removing it. `expo-updates` is a **native module** and `EXUpdatesEnabled` is `false` in every build shipped to date, so it can never reach a `1.13.2` binary. §2.5's union contract, §4.5's five sites and §6.2's vendored fixture test are **all unchanged**. §2.1's caps fingerprint is *strengthened* by OTA, not simplified — it adds a skew axis where devices reporting the same `X-App-Version` genuinely differ.

**Sequencing correction, independent of the merits:** `expo-updates` is native, so its benefit could not begin before S6 and it has **zero coupling to S3/S4/S5**. Even an operator who disagrees with the verdict should not hold Gate C for it — it is a Gate D build-config question. Gate C is amended accordingly.

**A provenance problem worth recording.** The claim that gave OI-9 its "upstream of the whole programme" standing — *OTA addresses R1–R6 as a class while this programme addresses R1–R2* — **cannot be checked against a source.** `git grep -nE '\bR[1-8]\b'` finds **no R-list in the PRD**; the strings `R1–R6` / `R1–R2` appear only in the three documents that assert the claim (HLD decisions, LLD OI-9, this Plan). The list lived in the superseded HLD on `design/device-side-platform-auth`, which is not in the repo. The claim propagated through three artifacts and four review rounds without anyone being able to verify it. **OI-22.**

**Re-open trigger:** the first public App Store release, where the memo's disconfirming fact 3 flips — a fleet that cannot be moved in hours makes "old binaries cannot be fixed" an operational cost rather than a three-person inconvenience. Memo §9 spells out what changes in the PRD/LLD/Plan if that day comes, so re-opening is executable rather than a restart.

---

## 11. What this programme does not buy — bluntly

1. **No protection from Sleeper blocking the app.** The volume warning describes the public sweeps — several hundred calls that stay on Render forever, vs ~12 that move. If Sleeper blocks Render's egress, the app breaks anyway. This moves the traffic the *terms* govern, not the traffic the *warning* describes.
2. **The JWT still transits Render** once per fresh session (G1 is "no server-side JWT *at rest*"), because a client cannot be trusted to verify itself.
3. **A compromised backend can still drive sanctioned mutations** at any league with a live credential attached. The guard bounds the verb, not the object. M4 detects; nothing prevents.
4. **No remedy for R7.** The worst plausible failure is answered by *not using the programme*.
5. **R1–R2 only.** Every "old binaries cannot be fixed" contortion is downstream of not having OTA (§10).
6. **G1 becomes a runtime guarantee, not a schema one** — "zero rows, monitored," with a documented benign way for the metric to go non-zero.

What it does buy: elimination of the aggregate at-rest breach target (one Fernet key ⇒ every user's credential), direct responsiveness to Sleeper's stated request for the credentialed slice, and §11.2 resilience for that slice. Real, and modest — the PRD says so itself.

---

## 12. Effort vs. value at n=1 — and the half-time plan

**Worth doing now regardless of the programme (2–3 days, per §2): all of S0.** The 365-day JWT is iCloud-backup eligible *today*; the Sentry scrub closes a leak path the transport would widen; the FAAB fix is a latent production bug. PRD §10's ship-now bundle; needs no further approval.

**Worth doing now because it is the programme (~15–20 days): S1–S7 as specced.** The corpus/fuzz rigor is not gold-plating — it is the control, and the LLD's review history is the evidence a lighter version ships holes. The dialect-branched transaction is the one table where a divergence is a duplicate real-money trade offer.

**Explicitly deferred until real volume — do not build now:** multi-device custody · lapsed-session revocation UX · digest-window tuning (no data) · the authenticated pending-read · migration machinery for future linkers · dashboards beyond the named counters and alerts · all of ESPN.

**The half-time plan, if 4–6 weeks is more than the moment justifies: keep S0, S1, S2. Stop.** S0 is where most of the *realized* security value lives; S1–S2 are pure server additions correct under every future, and S2 is the stage that must soak longest before S6 anyway — landing it early is free option value. **What that costs, honestly:** G1 unmet (server keeps custody of ~1–3 JWTs); the credentialed-slice answer to Sleeper deferred; the guard unbuilt. None of that is a regression — every part is the status quo the operator's agreement already covers. **The incoherent middle — building S3/S4 and stopping before S7 — buys nothing and leaves a half-wired transport to rot. Don't land there.**

**If S3+ proceeds at all, four things may not be cut**, because each is load-bearing for a specific silent failure: the Python parity guard (F3) · the negative control (a broken fence otherwise runs green) · the old-binary fixture test (the only pre-S6 evidence for the field) · the sweep alert (F5). These are what a compressed schedule cuts first.

---

## 13. Monday morning, concretely

1. Reply "yes to all defaults" (or amend) on §1's five decisions. *(15 minutes)*
2. Start three parallel sessions: **(a)** S0 backend — FAAB fix + tests; **(b)** S0 mobile — vault + legacy migration + Sentry scrub; **(c)** the two spikes, OI-9 + OI-12 (both fact-finding; one session). *(day 1)*
3. S1 tables + startup assertions behind them. *(day 2)*
4. Gate B: the §2.5/§5.3 adversarial re-review + OI-16, then S2. *(day 3)*
5. Gate C: read the OI-9 memo and the OI-12 answer; green-light or re-derive. *(~day 3–4)*
6. S3 begins, sized 6–9 days; everything after follows §3's chain.
7. Book two calendar holds now: **the whole S7 sequence — flags on → Sentry capture → send → drill — for the day the S6 build clears processing** (the capture cannot happen pre-flags, so it is not separable from the send day), and the **rollback drill** for the day of the first real send.

Session hygiene per repo convention: CHANGELOG entry per stage merged; TEST_LEDGER per sim run, per drill, and per device-fact check; HANDOFF overwritten at every stop with the stage cursor; worktree sweep at every stage end.

---

## Reconciliation Log

**Document type:** Plan  **Rounds run:** 3  **Converged:** yes — both lenses signed off in round 3

> **Model note:** the PRD, HLD decisions, and LLD used Opus lenses; this Plan's lenses ran on Fable (Opus weekly limit hit mid-programme). Recorded for honesty about provenance, not as a caveat on the content — every blocking objection in this log was verified against the documents before being applied.

### Round 1 — independent drafts

The two drafts converged, unusually, on the sequencing itself: **S0 immediately, S1–S2 behind it, a decision gate before S3.** What differed:

| Contested | Resolved as | Why |
|---|---|---|
| OI-3/OI-4/OI-15: ratify-by-default now (execution) vs may-not-be-defaulted (risk) | **Both, staged:** defaults ratified now for build purposes; written answers required at Gate F before other people's devices are involved | The lenses were right at different stages. |
| expo-updates posture: proceed-lean with the TCB argument (execution) vs spike-owns-the-decision (risk) | §10 records both; the recommendation leans proceed **with the spike holding the veto**, plus two hygiene rules (the spike prompt excludes §10; the memo must name its own disconfirming evidence) | The execution lens's trusted-computing-base argument is new relative to all source docs and is disclosed as a bet, not a finding. |
| Day totals: stated (execution) vs refused as anchoring (risk) | Stated, **labeled an uncalibrated stage-sum**, with mandatory S3 re-estimation at Gate C if `TextDecoder` is absent | An operator needs a number; the label keeps it honest. |

### Round 2 — cross-review: 3 blocking, all applied

- **Execution lens:** the Sentry capture was scheduled in three mutually inconsistent places, and the Gate D copy was **unsatisfiable** — a capture of a device platform request requires flags on, which is S7. An unsatisfiable checkbox gets waved through, on a credential-leak check. → Moved to Gate E as the pre-send precondition.
- **Risk lens:** Gate B's "fresh adversarial pass" had no performer, independence rule, or artifact — the S2 session would have self-attested the review of the LLD's own least-reviewed lines (the rollback path). → Named performer (an adversary subagent that authored neither the LLD nor S2), dated written verdict, "no verdict, no S2 merge."
- **Risk lens:** the kill table could not classify the two most likely *non-clean* R7 presentations — handshake-layer enforcement (resets/timeouts, no response body) dead-ended in "retry once," and a single transient JS challenge would have triggered "close the programme" on one noisy observation. → Two graduated rows, using the same-day server-path control send as the discriminator (R-ROLLBACK guarantees it exists).

Both lenses verified the merge honored the risk lens's standing sign-off conditions (Gate D not relaxed; one-stage-one-PR; Gate F written answers) and that nothing load-bearing was dropped from either draft. The execution lens conceded both merge deltas it was asked to defend (OI-1 and OI-14 as blocking checkboxes).

### Round 3 — confirmation: both sign off

- Execution lens verified the Sentry fix end-to-end (§2, §3, §6, Gates D/E, §9, §13 all consistent; no residual Gate-D placement) and that the new kill-table rows route coherently.
- Risk lens verified both its fixes applied without weakening, and **accepted the Gate E Sentry placement over its own round-2 suggestion** — the Gate D version could only ever have been waved through, and the residual exposure (a defective scrub leaking during the capture itself) is bounded to the operator's own JWT and irreducible under any placement. Its supplement — a proxy capture on a release-configuration dev build at Gate D, converting a post-ship hard stop into a pre-ship fix — was adopted as a recommended-not-required Gate D item.

### Unresolved disagreements

None. The one position overridden during reconciliation (the risk lens's Gate D Sentry placement) was re-put to that lens in round 3 and explicitly conceded with reasoning, not silently dropped.

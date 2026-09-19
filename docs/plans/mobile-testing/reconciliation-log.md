# Mobile Testing Doc Suite — Dual-Agent Reconciliation Log

**Document type:** bundled suite (Plan rev 3 + PRD + HLD + LLD + per-feature test cases)
**Rounds run:** 5 (default cap 4, raised by one — round 4 introduced a fix that itself needed adversarial verification)
**Converged:** yes — both lenses `SIGN-OFF: yes` in round 5
**Process:** two agents drafted the full suite independently (Author/Feasibility lens vs Adversary/Risk lens), the coordinator merged them into a candidate, then alternating cross-review rounds until sign-off. Factual claims were verified against source at every round (`feature_flags.py`, `server.py`, `config/features.json`, `sentry.ts`, `sendInSleeper.ts`).

## Round 1 — independent drafts

Both agents **independently converged** on the load-bearing correction to rev 2: the app never calls Sleeper directly — the backend does, live, including sign-in — so hermeticity must be server-side (a fail-closed fixture seam at `_sleeper_get`). Independent convergence treated as strong evidence.

Complementary contributions merged into candidate v1:
- **From A:** `FTF_FLAGS` env pinning already exists (verified `feature_flags.py:154` — zero new backend code); one-generator-two-outputs seeder rule (DB and Sleeper fixtures can't drift); matrix definitions (smoke/full/render-sweep); testID grammar with natural-key qualifiers.
- **From B:** fail-closed 599 + guardrail counters + record-mode bootstrap; env-gated test-support blueprint (`fail_next`/`latency`/`reset`/`whoami`) making error/slow/rollback paths deterministic; three-scope reset architecture + pollution canaries; **dedicated QA Sleeper account for Layer 3** (the TestFlight binary writes real rows to prod); matrix-pruning arithmetic; NOT-AUTOMATE register; per-change maintenance tax; guardrail-tripped exit code distinct from test failure.
- **Adjudicated conflict:** flag pinning — A's existing `FTF_FLAGS` env beat B's proposed `FTF_FEATURES_FILE` overlay (source-verified, zero new lines); B's explicit-13-key-map-per-profile rule kept.

## Round 2 — cross-review of the merged candidate (5 + 5 blocking)

**A raised (all fixed):**
1. Flag doctrine factually wrong — six gated surfaces ship **enabled** in `config/features.json`; two cases had inverted expectations and three off-boundaries silently didn't exist → header corrected; explicit off-pins added (TC-TRI-10/16, TC-TRD-34/35/36); TC-TRD-27 repurposed; ~12 rows repinned.
2. PRD R-22 contradicted G3 (Layer 2 with live Sentry DSN) → R-22 now full test env; prod parity static-only.
3. `demo` used as a profile but defined as not-a-profile → runner alias (standard DB + `try_before_sync` pin).
4. TC-TRD-29 unimplementable (no response-body injection) → `fail_next` gained optional JSON `body`; companion bare-599 case TC-TRD-33 added. *(Independently raised by B — same fix proposed by both.)*
5. Plan W0.3 contradicted the adjudicated MVP profile scope → MVP five listed; three profiles moved to phase 2.

**B raised (all fixed):**
1. = A's #4 (fail_next body).
2. `fresh` profile was four mutually exclusive states; `seed:` preconditions had no mechanism → profile vocabulary split (`fresh` / `near-unlock` / `no-leagues` alias); seed fields formalized in the schema; TC-CLC-14/TC-LEA-12 deleted as nav-unreachable (registered honestly).
3. Per-case flag pins incompatible with one-Flask-per-profile (`FTF_FLAGS` is per-process) — a false-green path in flag-boundary cases → runner groups by `(profile, flag-set, seed)`, one Flask + handshake per group, restart cost budgeted.
4. Seeder's warm players-cache would clobber the real dev cache (`PLAYERS_CACHE_FILE` is a hardcoded shared global, `server.py:353`) and leak synthetic players into real dev sessions → `FTF_PLAYERS_CACHE_FILE` override; per-profile cache as the seeder's third output; preflight refusal; blast radius re-accounted ≤170.
5. Chained smoke set contradicted the per-flow reset contract and made failures order-dependent → smoke unchained (10 independent self-signing-in flows).

## Round 3 — re-review of the revision

- **B: SIGN-OFF yes** (+4 non-blocking cleanups, applied: `FTF_TEST_MODE` also requires the cache override; PRD §6 profile sync; stale counts; full sentry path cite).
- **A: SIGN-OFF no (1 blocking):** the fail_next-body fix was only half-landed — TC-TRD-29/33 still couldn't *reach* propose because the client's link-status gate stops unlinked users, and nothing licensed a 2xx override to fake the linked state → LLD §4.3c redefined `fail_next` as a general response override (2xx legal); both cases gained the step-1 `GET /api/sleeper/link → 200` precondition override.

## Round 4 — verification of round-3 fixes

- **A: SIGN-OFF yes.**
- **B: SIGN-OFF no (1 blocking):** the round-3 fix introduced a regression — with TC-TRD-29/33 now legitimately reaching propose, the exit-4 guardrail `propose_attempts>0` would trip in **every P0 run by construction**; and "propose is never overridable to success" existed nowhere as normative text → guardrail split into `completed_proposes` (gating; real outbound sends only — structurally impossible) vs `propose_route_hits` (non-gating, expected); blueprint carve-out written (propose route refuses 2xx overrides); `{linked}` corrected to `{"connected": true}` (A later verified against `sendInSleeper.ts:11` — the original shorthand would not have opened the gate).

## Round 5 — final confirmation

Both lenses verified the guardrail split, carve-out, and body shape across all touchpoints. **A: yes. B: yes.** A's closing source check confirmed the corrected override matches the real client contract.

## Unresolved disagreements

**None** — both lenses signed off with no open objections.

Open **operator decisions** (not disagreements) live in plan §9: Sleeper ToS posture for the QA account; whether to allow one supervised end-to-end send per release; flag-pair interaction coverage; synthetic Trends history; iPad blocking-ness.

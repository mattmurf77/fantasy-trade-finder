# PRD Reconciliation Log — Analytics & Experimentation Platform

**Document type:** PRD · **Rounds run:** 3 · **Converged:** yes (both lenses signed off, round 3)
**Lenses:** Agent A = Product/User · Agent B = Engineering/Feasibility (adversarial), per dual-agent-doc-review protocol. Round 1 = two independent drafts; candidate v1 synthesized from both; rounds 2–3 = cross-review.

## Round 1 → synthesis (what each independent draft contributed)

- **From A:** full goal/metric/user-story structure, 40-FR coverage of the strategy docs, phase cut-line discipline ("events are perishable; reports are not"), platform-as-product success metrics.
- **From B (adopted over A where they clashed):** partial-unique-index migration reality (SQLite can't `ADD CONSTRAINT`); batch partial-failure semantics; single-transaction inserts; no hot-column dual-write for client events + `device:` id exclusion as a named bug class; `client_ts` clamp; rate-limit as silent 200 (A had 429); per-session `seq` for measurable loss; `funnel_critical` drop-last queue policy; Keychain-survives-reinstall semantics; query-time stitching; tombstone extended to `experiment_assignments`; envelope-stamping restricted (→ FR-32 [AMEND]); no MD5-bucket continuity for Experiment #1; mSPRT deferred (→ N6 [AMEND]); underpowered-launch override; header-only secret transport; atomic wrapped_events cutover; per-stage kill-switch flags. **B also corrected A's factual error:** first-party analytics *does* change the App Store privacy nutrition label (A had claimed no change) → NFR-4.

## Round 2 (candidate v1 review)

**A raised (3 blocking) → resolved:**
1. R8/PFO report silently dropped from FR-23/FR-25/phases → added to FR-23, PFO tab in FR-25, P2 scope + exit criterion.
2. `calc_trade_evaluated` missing from FR-20, silently undercounting the WAT north star and falsifying the "all-⚡" rollout claim → added.
3. P3 self-service surface ambiguous (builder can't tell if the Experiments tab includes creation) → FR-25 scope statement + US-5 two-step delivery.

**B raised (5 blocking, code-verified) → resolved:**
1. `GET /api/feature-flags` is identity-less; account-only sessions never call session_init — per-unit experiment delivery was unbuildable as written → FR-35 rewritten as an explicit config-delivery contract (X-Device-Id on every fetch, per-session-class resolution, P1 foreground refetch ≥30-min throttle).
2. Promised kill-switch client bound relied on a foreground flag refetch that doesn't exist; flag "cycle" is a manual reload → FR-19/FR-38 restated with honest per-mechanism bounds; refetch made a P1 requirement.
3. Targeting attribute registry never defined; `league_count`/`activation_stage` unavailable for device units → FR-33b registry table (source + availability per unit type) + validation; onboarding-layer targeting limited to header attributes, [AMEND] to framework §D2.
4. Dead-session-token is the routine post-deploy state with undefined behavior; first-after attribution would strand post-deploy flushes → FR-6 silent device fallback, FR-21 at-or-before-else-first-after rule, E-15.
5. Sentry framing factually wrong — a dormant `@sentry/react-native` SDK is already compiled into the binary with user-id tagging pre-wired → §2 corrected; OQ-1 restated as "arm the DSN" with legal-privacy gating activation and the `sentrySetUser` PII question.

**Non-blocking adopted:** WAL actually off (code comment wrong) → NFR-2; dialect-branched insert helper carve-out → FR-5; dedupe accounting mechanism (+ intra-batch case) → FR-7; reuse `X-Cron-Secret` header → FR-24; wrapped-events live reader repoint-or-declare-frozen (+ `NARRATIVE_TYPES` gain) → FR-4; client/server event-name namespace rule → FR-9; kill-switch default-dark + keep-out of `LAUNCHED_FLAG_DEFAULTS` → FR-19; session terminology pinned to client `session_id` → FR-37; [AMEND] tags on mSPRT deferral and `seq` envelope addition; ritual-time and SM-9 measurement clarifications.

## Round 3

Both lenses verified every round-2 fix (B re-checked against code: flags endpoint, `_sessions`, `LAUNCHED_FLAG_DEFAULTS`, `sentry.ts`, `sentrySetUser`, WAL comment, wrapped-collector call sites). **A: sign-off yes. B: sign-off yes.** Final non-blocking polish applied: R9 pointer in FR-23, intra-batch dedupe note, pause-vs-engine-flag runbook line, `NARRATIVE_TYPES` repoint note.

## Unresolved disagreements

None — both lenses signed off.

## Amendments flowing back to strategy docs on operator approval

1. **[AMEND] experimentation framework §D4** — experiment envelope stamped on funnel-stage + in-scope-surface events only (not every row).
2. **[AMEND] experimentation framework §D5 Decision 2** — mSPRT deferred to v2; v1 = fixed-horizon + threshold harm alerts.
3. **[AMEND] experimentation framework §D2** — targeting attribute registry constrained per unit type (device units: header attributes + allowlist only).
4. **[AMEND] tracking plan §S2** — envelope gains per-session monotonic `seq`.

# Experimental personal-market policy activation — 2026-09-05

**Status:** enabled and verified live at **16:03:54 UTC on 2026-09-05**. The owner said “I want the experimental policy on.” This authorizes the existing personal-market switch, not roster enforcement or another generator replacement.

## Verified execution

- At **15:59:45.097 UTC**, updated only `trade.personal_market_policy_v1: false → true` within the existing Render `FTF_FLAGS` variable. Immediate control-plane readback matched the entire preserved object with exactly one changed key.
- Redeployed the already-reviewed commit `4026ebc81eaae50b345b42421641125c5b8d413e`, without a code change or cache clear. Render deployment `dep-dae3oseq1p3s73fs3m50` reached **live at 16:01:20.163757 UTC** and reports that exact commit.
- [Activation smoke](policy-activation-smoke.json) verifies the effective flag is true, exactly one of 207 effective flags differs from the immediate preflight, and all 258 model values, tier definitions and experiment summaries retain their canonical hashes. All three generator arms/profiles/allocation are preserved; shared policy eligibility and ordering can change which cards reach the deck.
- Public root/tier/flag and read-only operator config/health/experiment requests returned 200. Unauthenticated trade/admin-config requests returned 401. Served root bytes match the reviewed source. Event-ID index is present; ingest transaction failures are zero.
- No production trade generation, real-user session, database backfill, new EAS build, tester-group change or physical-device validation was performed. This verifies activation and service/configuration health, not offer quality or acceptance uplift.

## Scope and boundaries

- Set only `trade.personal_market_policy_v1` from false to true inside the existing Render service-level `FTF_FLAGS` JSON. Preserve every other key, model value, generator arm/profile and allocation.
- Existing source `4026ebc81eaae50b345b42421641125c5b8d413e` is already live and CI-validated. Deploy that same commit to load the updated process environment; do not introduce code or migrations.
- The switch applies shared eligibility, ranking and composition to new generated model decks across the three existing arms. It is a global activation, **not a randomized crossover/control experiment**. SEND-anchored fair-packages, manual calculator and asset-ideas paths are not brought into this policy by this switch.
- Existing policy floors, personal-opportunity ordering and Core/Conviction quotas are activated as an experimental implementation. No claim that those settings settle the owner's outstanding product questions or complete the owner handoff.
- Fresh generation uses the new policy. A redeploy clears server-memory jobs; an already-open client can still display older cards until a new search/refresh. No new TestFlight binary is required.

## Four gates

1. **Analytics:** existing `policy_variant`, impression valuation snapshots and shadow-rejection records distinguish the activation boundary. No new event, identity, table or data collection field. Valuation telemetry is already on and stays on. No assertion of measured uplift, >=99% snapshot/ratio graduation, <=5% latency overhead or native QA follows from activation approval.
2. **Schema/config:** no schema, unrelated environment-variable or model-config edit. Update Render's single `FTF_FLAGS` variable endpoint after reading and preserving the current complete object. Never use the replace-all-environment endpoint. Other current overrides: valuation telemetry and roster evaluation true; roster protection and mutual-benefit enforcement false.
3. **Evidence:** final source CI passed 5,455 backend tests / one skip and all client gates. Fresh focused policy/wiring/owner/privacy preflight: **114 passed in 3.68 s**. Independent Astra review found no new migration/code blocker and identified scope, stale-client and fail-closed-empty-deck limitations. Verify exact deployed source, effective flag delta, public liveness and unchanged model/experiment configuration after activation. Do not fabricate a personalized production trade to claim runtime coverage.
4. **Docs:** this activation record, production-state handoff and test ledger record the effective runtime override. Checked-in false defaults remain conservative. No API, schema, HLD, UI or dependency reference changes are required; operational rollback is below. Broader data/UX/policy work stays in [review.md](review.md).

## Operational risks and rollback

The shared evaluator can reduce deck supply. Evaluation errors fail closed to an empty completed deck, with an internal policy error; HTTP 200 alone does not prove successful personalized serving. Existing generated-deck versus other-surface differences remain. Controlled before/after supply, latency, acceptance, delayed-view and physical-device validation are not completed by this switch.

Rollback: read the latest complete `FTF_FLAGS`, change only `trade.personal_market_policy_v1` to false, preserve other entries, then redeploy the same verified source and read the effective flags back. `/api/feature-flags/reload` alone cannot import new Render control-plane environment values. Preserve telemetry/history; do not delete rows or change pricing knobs to simulate rollback.

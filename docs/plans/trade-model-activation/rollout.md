# Collection rollout and rollback

Target service: `fantasy-trade-finder` on Render, configured to deploy `main`.
Baseline revision: `606e512cd87f692eced3b92ccadb4f0192ea3449`.

## Change

Merge only after the pushed revision passes all four CI jobs. Deploy the additive code/migrations. Set only the existing `FTF_FLAGS` environment variable, preserving any existing entries, to override:

```json
{
  "trade.valuation_telemetry": true,
  "trade.roster_evaluation": true,
  "trade.personal_market_policy_v1": false,
  "trade.roster_protection": false,
  "trade.mutual_benefit_v1": false
}
```

The preflight found no service-level FTF_FLAGS override (HTTP 404). Config and code defaults remain false, making the production collection override explicit. No crossover assignment or generator arm is changed.

Use Render's [single-variable update](https://api-docs.render.com/reference/update-env-var), which changes one variable. Do not replace the environment-variable list. A [deployment](https://api-docs.render.com/reference/create-deploy) is needed for the running process to receive the change. Preserve the existing service branch and deployment configuration.

Verify the deployed commit, GET /api/feature-flags, and additive columns with a production read-only connection. Report actual new impression coverage if traffic has arrived; zero new rows is pending observation, not 100% coverage. Readiness remains blocked for strict filtering as detailed in validation.md.

## Rollback

Set the two collection entries false in FTF_FLAGS, preserving unrelated entries; deploy the same validated commit again. Alternatively restore the exact prior FTF_FLAGS value (absent at preflight) and redeploy, since code/config defaults are false. Read back flags to confirm. Nullable telemetry remains for audit and needs no deletion.

POST /api/feature-flags/reload only reloads the current process environment and file. It cannot pull a new value from Render's control plane. Do not describe that endpoint alone as an immediate Render environment rollback.

If the additive application deployment fails boot, leave the prior live deploy serving and inspect the failure; do not enable filters or retry migrations directly against production. The isolated PostgreSQL upgrade already verified legacy-row/config preservation and idempotence.

## Execution record

Pending exact-SHA CI and deployment at document creation. Update this section with verified revisions and times when complete. TestFlight controlled-send and broad enforcement remain explicitly pending.

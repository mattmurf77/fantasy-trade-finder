# Security release — 2026-09-05

The operator authorized deployment after reviewing the completed local fixes and disclosed native/production limitations.

## Release preparation

- Security implementation committed as `ba3ce9f1`; merged current main `0a8093fe` (#277/#278) before release validation.
- Preserved both captured trade execution context and deletion work leases in the `_kickoff_trade_job` conflict. Additive reference/ledger changes from both workstreams are retained. The security decision was renumbered to **D-183** because main allocated D-180–D-182.
- Added incoming `trade_proposals` and `trade_policy_shadow` to alias-aware deletion/export. For another owner's proposal targeting the deleted user, preserve package/provider history but remove target attribution and its private valuation snapshot.
- Focused merged integration: **335 passed / 4,667 deselected** in 18.21 seconds. New-table deletion/export group: **26 passed**. Full PR CI is the merge gate; earlier 4,707-pass evidence predates the incoming main changes.
- Mobile release version **1.16.16** (all native marketing-version locations synchronized); EAS manages the build number. Extension **0.1.1**, packaged for the established unpacked Chrome/Edge installation method.
- Live Render configuration checked read-only: service `srv-d7g37ftckfvc73a32gvg`, main auto-deploy, one instance, one Gunicorn worker. No scaling/config changes requested.

## Delivery status

PR CI, release assets, Render deployment, and EAS build/submission are pending. Record actual IDs and completion here as each finishes.

Physical iPhone verification remains an operator checklist. Historical production analytics cleanup/revocation and membership resync are separate maintenance work; deployment alone does not perform them.

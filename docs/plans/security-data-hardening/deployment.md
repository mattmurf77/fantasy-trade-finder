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

**Shipped.** [PR #279](https://github.com/mattmurf77/fantasy-trade-finder/pull/279) squash-merged at 2026-09-05 04:39:03 UTC as `a927e3a7f3552ed48d68d3e33f370ee1636bffcf`. Its content is identical to tested branch head `ab8f54d0ae86e7bc261c59b41bc1192d0ba54b28` (`git diff` empty).

- **CI:** [run 33944570236](https://github.com/mattmurf77/fantasy-trade-finder/actions/runs/33944570236), all four jobs completed successfully. Backend: **5,001 passed / 1 skipped in 589.55 seconds** on Python 3.12. Mobile typecheck and all 91 guards, testID lint, and 180 web checks passed. Integrated local PostgreSQL: **57 passed in 10.99 seconds**; the disposable cluster was stopped afterward.
- **Render:** deployment `dep-dadppq17lnhs73e8fqo0` became **live at 04:40:05 UTC**, serving `a927e3a7`. The production landing HTML, app JS, browser-auth JS, stylesheet and privacy page match the reviewed files byte-for-byte. Feature flags respond 200. Session initialization, extension rankings and account export each reject a deliberately invalid session with **401**. No real user's private data was used by these probes.
- **iOS:** [EAS build bab54ee5](https://expo.dev/accounts/mattmurf77/projects/dtf-dynasty-trade-finder/builds/bab54ee5-8ab3-44d9-8fcf-fe882812b6d8), **1.16.16 (145)**, source `ab8f54d0`, **FINISHED at 04:34:17 UTC**. [TestFlight submission 815cb2a0](https://expo.dev/accounts/mattmurf77/projects/dtf-dynasty-trade-finder/submissions/815cb2a0-6eea-4029-9a5e-82cf977cab3b) also reports **FINISHED**, with no error. This confirms build/upload completion, not physical-device QA or Apple's final tester availability.
- **Extension:** [0.1.1 release](https://github.com/mattmurf77/fantasy-trade-finder/releases/tag/extension-v0.1.1), 14-file unpacked package, 22,467 bytes. Published asset digest matches local SHA-256 `49387e45ae9ab2b419119c76c8f187eb200effa80658e0334fa96a8337def0df`. The live landing page links to these installation instructions.

Expo rejected the optional TestFlight changelog field as Enterprise-only after creating build 145. The existing build was submitted without that optional field; no duplicate build was created. The native checklist remains in the release docs.

This evidence-only follow-up uses `[skip render]` to avoid another service restart; product source is unchanged from the verified live release.

Physical iPhone verification remains an operator checklist. Historical production analytics cleanup/revocation and membership resync are separate maintenance work; deployment alone does not perform them.

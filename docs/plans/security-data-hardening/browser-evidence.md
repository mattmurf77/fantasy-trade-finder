# Browser and extension verification — 2026-09-04

Status: isolated Chromium runtime checks passed. Extension **0.1.1** was published on 2026-09-05; production static-file and invalid-session checks passed. No live account was exercised. [Release evidence](deployment.md).

## Trust boundary

`extension/verify.mjs` fixes the API destination and accepts only exact trusted Sleeper origins, the extension popup, and the production first-party web page. `sleeper-proof.js` reads a token only for an explicit same-extension request in the top frame. `web-auth.js` requires a trusted click or Enter gesture and a short-lived, single-use request with matching origin, source and correlation. Localhost is excluded from the web bridge.

The background flow first discovers the requested username and then supplies the captured proof to `/api/sleeper/link`. It returns a Fleeced bearer only after `verified === true`. The raw Sleeper token is transient: it is not returned to the first-party page or stored by the extension. `web/js/browser-auth.js` supplies timeout and recoverable error handling. Cached private boards require session revalidation; a rejection returns to verification without a username/init retry loop.

ESPN/MFL browser entry directs users to mobile, where provider account verification is available. The landing page does not offer team selection as authentication. Sleeper onboarding requires the updated extension; the deployed page links to the published 0.1.1 package and unpacked-install instructions.

## Evidence

- `qa/web/check_browser_auth.mjs`: **23 checks passed** using isolated JavaScript boundaries.
- `qa/web/check_browser_auth_runtime.cjs`: **passed with the actual MV3 extension loaded** in Chromium 148. A disposable profile and synthetic Sleeper/API responses cover wrong-account denial, verified sign-in, proof absence from web/extension storage, revoked-session recovery, cache clearing in the actual popup, and no unsafe `/api/session/init` or `/api/entry/platform` fallback. Unhandled page errors are asserted absent.
- Runtime requests are fulfilled from fixtures or aborted; host resolution is restricted to loopback as a second guard. No user's browser profile, real Sleeper credentials or production writes are used.
- The same runtime check verifies help text fits at 390 × 844. The resulting screenshot was visually inspected; the new help wraps inside the form without clipping.
- `qa/web/check_web_structure.py`: **180/180 passed**. JavaScript syntax checks passed.

Runtime log: `/private/tmp/ftf-browser-runtime-final.log`. Structural log: `/private/tmp/ftf-web-structure-final.log`. These scratch artifacts may expire; the [harness instructions](validation-tools/README.md) are durable.

The browser harness proves client behavior with mocked upstream boundaries. Genuine Sleeper login remains a live-account check; extension publication and deployed static/API-denial checks are recorded in deployment.md.

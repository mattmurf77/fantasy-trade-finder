# extension/ — Notes for Claude

Chrome/Edge MV3 extension that injects your **personal** tier + positional rank next to
every player name on sleeper.com. Currently `manifest.json` version `0.1.1`, unpacked-only
(never published to a store).

Full user/developer doc: [`README.md`](README.md) — install steps, backend contract,
known limitations, file layout. Ownership verification updated 2026-09-05.

## Wiring

`manifest.json` (bump `version` per ship) → `background.js` service worker (non-persistent,
keep no global state; refetches rankings on a `chrome.alarms` period) → `content.js` runs on
Sleeper pages (anchor-href match first, text-node fallback) → `popup.*` for the toolbar UI. `verify.mjs` and `sleeper-proof.js` implement explicit ownership proof; `web-auth.js` bridges trusted production-page requests.

Backend verification uses `POST /api/extension/auth` then `POST /api/sleeper/link`; private rankings use `GET /api/extension/rankings`. The web client revalidates restored sessions with `GET /api/me/streak`.

## Rules

- `verify.mjs` owns the fixed production API destination, imported by the popup and worker. The web bridge rejects localhost origins; use the synthetic harness for local tests.
- Analytics events must match `backend/analytics_taxonomy.py`; emission is gated on the `analytics.client_events` flag (fetched from the backend, cached 5 min, default-dark).
- Tier colors are a cross-client data encoding — governed by [`docs/cross-client-invariants.md`](../docs/cross-client-invariants.md), not by taste. Everything else uses the same Chalkline tokens as `web/`.
- Auth checks live in `qa/web/check_browser_auth.mjs`; the actual MV3 runtime harness is `qa/web/check_browser_auth_runtime.cjs`. They are local checks. Users install unpacked (`chrome://extensions` → Developer mode → Load unpacked → `extension/`).
- Route changes here still trigger [`docs/api-reference.md`](../docs/api-reference.md).

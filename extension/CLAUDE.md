# extension/ — Notes for Claude

Chrome/Edge MV3 extension that injects your **personal** tier + positional rank next to
every player name on sleeper.com. Currently `manifest.json` version `0.1.0`, unpacked-only
(never published to a store).

Full user/developer doc: [`README.md`](README.md) — install steps, backend contract,
known limitations, file layout. Verified accurate 2026-08-18.

## Wiring

`manifest.json` (bump `version` per ship) → `background.js` service worker (non-persistent,
keep no global state; refetches rankings on a `chrome.alarms` period) → `content.js` runs on
Sleeper pages (anchor-href match first, text-node fallback) → `popup.*` for the toolbar UI.

Backend surface is exactly two routes in `backend/server.py`: `POST /api/extension/auth`
and `GET /api/extension/rankings`.

## Rules

- `API_BASE` is duplicated at the top of **both** `popup.js` and `background.js` — change both or you get a half-local extension.
- Analytics events must match `backend/analytics_taxonomy.py`; emission is gated on the `analytics.client_events` flag (fetched from the backend, cached 5 min, default-dark).
- Tier colors are a cross-client data encoding — governed by [`docs/cross-client-invariants.md`](../docs/cross-client-invariants.md), not by taste. Everything else uses the same Chalkline tokens as `web/`.
- **No automated tests, not in CI.** Verify by loading unpacked (`chrome://extensions` → Developer mode → Load unpacked → `extension/`).
- Route changes here still trigger [`docs/api-reference.md`](../docs/api-reference.md).

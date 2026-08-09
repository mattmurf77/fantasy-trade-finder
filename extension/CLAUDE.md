# extension/ — Notes for Claude

Chrome/Edge MV3. `manifest.json` (bump `version` per ship) → `background.js` service worker (non-persistent, keep no global state) → `content.js` runs on Sleeper pages → `popup.*` for the toolbar UI.

Analytics events must match `backend/analytics_taxonomy.py`; emission is gated on the `analytics.client_events` flag (fetched from the backend, default-dark). Use the same Chalkline tokens as `web/`.

No automated tests — verify by loading unpacked (`chrome://extensions` → Load unpacked → `extension/`).

# Feature Scope — server-written `device_type` / `platform` stamps (G-068 rule, extended)

**Date:** 2026-10-31
**Entry point:** direct ask. head-eng asked 2026-10-31 for the G-068 rule at three server-written sites (lead: draft-eng)
**Builder:** eng-backend + eng-web worker, branch `fix/device-type-source`
**Operator sign-off on waivers:** not needed. The only waivers are the mobile structural guard and the TestFlight checklist, because this ships no mobile code (§3)

**The bug.** G-068's rule is that a missing client signal is stored as NULL, never as another
client's name. Three server-written stamps still guessed:

1. `backend/overhaul_api.py` `fire()` stamped `device_type = X-Device or "web"` on
   `overhaul_generation_completed` and `overhaul_batch_reconciled`.
2. `backend/win_now_api.py` (`POST /api/win-now/search`) stamped `device_type = X-Device or "web"`
   on `win_now_objective_selected`, and `props.platform` = `ios` / `android` / else `web`.
3. `GET /api/feature-flags` (`backend/server.py`) passed the raw `X-Source` header (any string)
   through as the experiment `platform` targeting attribute, else `ios` for iphone/ipad/macos,
   else None. `experiments._persist_assignment` stores those attributes in `context_json`.

Today's web rows were right (`web`), but only because the default happened to match. A request
from no identified client was also filed as `web`.

**The fix.** One helper module, `backend/client_device.py`, has no backend imports, so there is no
cycle risk. No existing module fit: `analytics_taxonomy` is an event-name registry that imports
`database`, and `analytics_ingest` belongs to PR #554. `overhaul_api` and `win_now_api` import it
at module level. The feature-flags route imports it next to its existing guarded `experiments`
import.

- **A. `device_type`** (overhaul `fire`, win_now search), via `event_device_type(headers)`. First match wins:
  1. `X-Device`, stripped, if non-empty. It is stored as sent, which is the value
     `g.device_info["device_type"]` holds and the ingest stores.
  2. else `X-Source`, lowercased and stripped, if it is in `DECLARED_SOURCES = {web, extension}`.
  3. else `MISSING_DEVICE_TYPE` (= None; analytics-lead owns it).
- **B. win_now `props.platform`**, via `device_platform(device)`: iphone/ipad/macos → `ios`,
  android → `android`, `web` → `web`, `extension` → `extension`, anything else (including None) → None.
- **C. feature-flags `platform` attribute**: `declared_source(headers)` (`X-Source` in
  `{web, extension}`), else `ios` for an iphone/ipad/macos `X-Device`, else None. Every current
  client gets the same value as before. Only junk values (`api`, `mobile`, `foo`) stop passing through.
- **D. web**: `apiFetch` (`web/js/app.js`) now sends `X-Source: web` on every call, so web Win Now
  rows keep `device_type = web`, `platform = web`. Without it, removing the default would have
  turned them NULL.

`source="api"` on these `record_event` calls is unchanged.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it.** No new events, no new props, no taxonomy change
  (`backend/analytics_taxonomy.py` untouched). This changes the **stored values** of existing stamps:
  - `user_events.device_type` on `overhaul_generation_completed`, `overhaul_batch_reconciled` and
    `win_now_objective_selected`: NULL when no client identified itself (was `web`). A declared
    `extension` is now stored as `extension`.
  - `props.platform` on `win_now_objective_selected`: adds `extension`, and NULL where it was `web`.
  - experiment `platform` attribute (`experiment_assignments.context_json`): out-of-set `X-Source`
    values become None. A None attribute fails any `platform` predicate (`_targeting_match`,
    `backend/experiments.py:219`), so such a unit is excluded rather than matched on junk.

  **Defaults follow analytics-lead's 2026-10-31 G-068 rule** (closed set mobile | web | extension;
  NULL when nothing identifies the client; no backfill), **extended by head-eng 2026-10-31** to these
  three server-written sites.

  **analytics-lead confirmation (2026-10-31, relayed by draft-eng):** confirmed, defaults as briefed.
  - (a) NULL is right for `device_type` and for win_now `props.platform`.
  - (b) Nothing reads them. No query in `analytics_queries.py`, `backend/tools`,
    `device_exclusion.py` or `scripts` reads `device_type`, and nothing reads `props.platform` on
    these events. No SERIES_BREAKS row, no taxonomy change. In analytics-lead's words, only one
    value domain widens.
  - Their read-only prod count (2026-10-31 15:55 UTC, counts only):
    - `overhaul_generation_completed`: 5 rows (2026-09-08..09-14), all `device_type=iphone`
    - `overhaul_batch_reconciled`: 0 rows
    - `win_now_objective_selected`: 0 rows
    - `experiment_assignments`: 6 rows, `platform` `ios` ×2 and absent ×4
  - So no `web` default has ever been stored on these events, and the pre-fix reading rule applies
    to zero rows. **No backfill.** The data dictionary says this in place of a long pre-fix rule.
  - #3 (feature-flags) is fine as specced.
  - Web's flags fetch sending `X-Source` is **deliberately out of scope**. It goes in the build of
    the first web-targeted experiment. Today the web's raw `fetch('/api/feature-flags')`
    (`web/js/app.js:13`) sends no `X-Source` and no `X-Device`, so web units carry `platform` None,
    the same as before this change.
- [ ] **(c) WAIVED:** n/a.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. `user_events.device_type` was already nullable, and
  `backend/database.py` is untouched. `docs/data-dictionary.md` `user_events.device_type` is updated.
- One side effect, noted: `record_event` writes `users.last_device_type` only when `device_type` is
  truthy (`backend/database.py:4884`). A NULL stamp therefore no longer overwrites it with `web`.
  Web callers still send `X-Source: web` and still write `web`.
- New/changed feature flags: **none**. The fix is unflagged: it corrects a guessed label and adds
  no user-visible behaviour.
- New env vars / `model_config` keys: **none**. Rollback is a revert. The web's extra header is
  harmless to the old backend, whose only `X-Source` readers are the ingest and the feature-flags
  route, and the web reaches neither through `apiFetch`.

## 3. Evidence scope

- [ ] **Structural guard (mobile):** WAIVED. No mobile file changes. The web structural guard is
  `HYG-apifetch-declares-source` in `qa/web/check_web_structure.py`. It asserts that the body of
  `async function apiFetch(` in `web/js/app.js` sets `X-Source` to `'web'`. The check is scoped to
  that function's text, so a stray string elsewhere in app.js can't satisfy it.
- [x] **Unit tests:** new `backend/tests/test_device_type_source.py`, 18 cases. It reuses the
  `test_overhaul_api` harness (whose `record_event` fake now also captures `device_type`, a
  one-line change) and the `test_win_now_api` harness. Feature-flags cases patch
  `backend.experiments.resolve_for_unit`, send `X-Device-Id` so a device unit exists, and assert the
  capture happened, because the route swallows exceptions. `test_win_now_api.py:230`
  (headerless `props.platform`) now asserts None instead of `web`.

  | Site | Case | Expected | Pre-fix (origin/main files) |
  |---|---|---|---|
  | overhaul | no `X-Device` / `X-Source` | `device_type` None, `!= "web"` | FAIL (`web`) |
  | overhaul | `X-Device: iphone` | `iphone` | pass |
  | overhaul | `X-Source: web` | `web` | pass (by the default) |
  | overhaul | `X-Source: api` | None | FAIL (`web`) |
  | win_now | headerless | None / None | FAIL (`web`/`web`) |
  | win_now | `X-Source: web` | `web` / `web` | pass (by the default) |
  | win_now | `X-Source: extension` | `extension` / `extension` | FAIL (`web`/`web`) |
  | win_now | `X-Device: iphone` | `iphone` / `ios` | pass |
  | win_now | `X-Device: android` | `android` / `android` | pass |
  | win_now | `X-Source: server` | None / None | FAIL (`web`/`web`) |
  | flags | `X-Source: web` | `web` | pass |
  | flags | `X-Source: extension` | `extension` | pass |
  | flags | `X-Source: api`, no `X-Device` | None | FAIL (`api`) |
  | flags | `X-Source: mobile`, no `X-Device` | None | FAIL (`mobile`) |
  | flags | `X-Source: foo`, no `X-Device` | None | FAIL (`foo`) |
  | flags | `X-Source: mobile` + `X-Device: iphone` | `ios` | FAIL (`mobile`) |
  | flags | `X-Device: ipad`, no `X-Source` | `ios` | pass |
  | flags | nothing | None | pass |

  **Against origin/main's** `overhaul_api.py`, `win_now_api.py` and `server.py`: 10 failed, 9 passed
  (the 18 cases plus the updated `test_win_now_api.py:230` test, which also fails pre-fix). Every
  failure is a headerless, junk or newly named (`extension`) case. Every pass is a case whose value
  is unchanged.

  **Sabotage**, applied one at a time against a local baseline commit, then restored and confirmed
  byte-identical with `git diff --exit-code`. Run over `test_device_type_source.py`,
  `test_overhaul_api.py` and `test_win_now_api.py` (91 tests):

  | Sabotage | Red |
  |---|---|
  | s1 overhaul back to `X-Device or "web"` | overhaul headerless, overhaul `X-Source: api` (2 failed / 89 passed) |
  | s2 win_now device back to `X-Device or "web"` | win_now headerless, `extension`, `server`, `test_win_now_api::test_search_persists_viewer_objective_and_bounds_pending_work` (4 / 87) |
  | s3 `device_platform`'s else branch back to `"web"` | win_now headerless, `server`, `test_search_persists_viewer_objective_and_bounds_pending_work` (3 / 88) |
  | s4 feature-flags raw `X-Source` (closed set dropped) | flags `api`, `mobile`, `foo`, `mobile`+`iphone` (4 / 87) |
  | s5 helper's `X-Source` step dropped | overhaul `X-Source: web`, win_now `web`, win_now `extension` (3 / 88) |
  | g1 app.js `X-Source` line removed | only `HYG-apifetch-declares-source` (196/197 checks pass). `node --check` passes and the 18 backend cases pass |

- [x] **Code-walk proof:**
  1. **Mobile.** `apiRequest` spreads `_CLIENT_HEADERS` (`mobile/src/api/client.ts:507-511`).
     That always carries `X-Device` (`:54`), labelled iphone/ipad/macos/android/web by
     `_resolveDeviceLabel` (`:40-50`). Overhaul calls go through `apiRequest`
     (`mobile/src/api/overhaul.ts:14`, routes `:328-450`). Win Now search goes through `api.post`
     (`mobile/src/api/winNow.ts:8`). So step A1 resolves, and the value is unchanged from today.
  2. **Web Win Now.** `web/js/win-now.js:61` calls `context.apiFetch`, which is app.js's `apiFetch`
     (bridge at `web/js/app.js:6755`). `apiFetch` (`:105`) now sets `X-Source: web` (`:111`).
     It sends no `X-Device`, so A1 misses, A2 resolves `web`, and `device_platform` returns `web`.
     The value is unchanged from today.
  3. **Overhaul from web or the extension.** None. `git grep` finds `/api/overhauls` only in
     `mobile/src/api/overhaul.ts` and `sendOutcome.ts`, nothing in `web/` or `extension/`.
  4. **Server.** `fire()` (`backend/overhaul_api.py:130-133`, called at `:729` and `:1073`) and the
     win_now search (`backend/win_now_api.py:116-121`) call `event_device_type(request.headers)`
     (`backend/client_device.py:33`), and win_now calls `device_platform` (`:42`). The feature-flags
     route builds `header_attrs["platform"]` from `declared_source` (`backend/server.py:31936`,
     helper at `client_device.py:27`), else the existing `ios` branch on `g.device_info`. It passes
     the attributes to `resolve_for_unit` (`:31952`), and they persist in `context_json`
     (`backend/experiments.py:286`).
  5. **Feature-flags callers.** None sends `X-Source` today: web `app.js:13` and the extension
     `background.js:158` use a raw `fetch`, and mobile `flags.ts:62` uses `api.get`, which adds
     `X-Device` but no `X-Source`. So `web` → None, extension → None and iOS → `ios`, all as before.
  6. **`apiFetch` header safety.** Every `apiFetch` caller passes a plain object or no `headers`,
     none a `Headers` instance (`git grep "new Headers"` finds nothing in `web/` or `extension/`),
     so index assignment works. Every `apiFetch` URL is a same-origin `/api/...` path, so the new
     header triggers no CORS preflight.
- [ ] **Manual TestFlight checklist:** WAIVED. No mobile change and no binary. Code-walk step 1 and
  the `X-Device: iphone` / `android` cases pin that mobile's stored values are unchanged.
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | n/a because | no request or response contract changed. The `GET /api/feature-flags` row doesn't describe the `platform` targeting attribute or `X-Source`, and the `POST /api/win-now/search` row doesn't describe the event stamps, so neither row has text these stamps change |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a here | `living-memory/` is release-lead's. The convention is G-068's existing rule, now honoured at three more sites. Flagged to release-lead in the hand-off |
| `docs/architecture.md` (module wiring / data flow changed) | n/a because | one tiny leaf helper module with no backend imports. No data flow changed |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | n/a because | no architecture shift |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | updated | "Device platform / source enums": a paragraph after the list adds `android` and NULL to `user_events.device_type`, the server-side resolution, and the rule that web `apiFetch` declares `X-Source: web`. It is a paragraph rather than an edit to the bullet because PR #554 rewrites the adjacent `user_events.source` bullet, and an in-place edit conflicts with it (checked with `git merge-file`) |
| `docs/glossary.md` (new domain term) | n/a because | no new domain term |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | n/a here | the NULL / closed-set / no-backfill calls are analytics-lead's (§1). Any DECISIONS.md entry is release-lead's |
| `docs/data-dictionary.md` | updated | `user_events.device_type`: the value set (adds `android`, NULL), the resolution for the three server-written events, NULL meaning, the prod read showing zero pre-fix `web` rows, no backfill |
| `docs/plans/win-now/scope.md` | updated | line 9: `platform` is ios / android / web / extension, else NULL |
| experiments docs listing `platform` values | n/a because | none outside `docs/plans/analytics-platform/` (off-limits to this change) lists the attribute's values. `docs/business/analytics/2026-07-17-experimentation-framework.md:37` names the attribute only, and `analytics-platform/lld.md:111` is the `user_events.platform` column, not the attribute |
| `docs/plans/README.md` | updated | `win-now/` row: 4 → 5 files, links this scope |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint`, plus the web-structure
  check (`python3 qa/web/check_web_structure.py`), all passing on the pushed sha
- **Evidence recorded:** a `living-memory/TEST_LEDGER.md` entry naming the suites, the before/after
  table and the sabotage table. This is owed by release-lead, since this branch doesn't touch
  `living-memory/`
- **TestFlight verification:** none (no checklist; no mobile change)
- Express lane declared by the operator? no. Full gates

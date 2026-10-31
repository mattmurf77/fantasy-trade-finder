# Feature Scope — `user_events.source` resolution (G-068 repeat)

**Date:** 2026-10-31
**Entry point:** direct ask. head-eng assigned it 2026-10-31 (lead: draft-eng), after analytics-lead's prod read confirmed a G-068 repeat
**Builder:** eng-backend + eng-web worker, branch `fix/g068-event-source`
**Operator sign-off on waivers:** not needed. The only waivers are the mobile structural guard and the TestFlight checklist, because this ships no mobile code (§3)

**The bug.** `backend/analytics_ingest.py` read `source = X-Source header or "mobile"`. Web's
page-hide flush (`flushOnHide` in `web/js/events.js`) uses `navigator.sendBeacon`, which can't set
headers, so those batches landed `source='mobile'`. In prod, 25 of 53 `platform='web'` rows in 90
days were labelled `mobile`. This is the G-068 failure again: a missing header landed another
client's name, not NULL.

**The fix.** `_resolve_event_source()` resolves in order, first match wins:
1. `X-Source` header, lowercased and stripped, in `{mobile, web, extension}`
2. body `source`, same treatment, same closed set
3. body `platform` in `{web, extension}` (cached copies of the old `events.js` send this but no `source`)
4. an `X-Device` header present → `mobile` (only the mobile SDK sends one)
5. `MISSING_EVENT_SOURCE` = NULL

Web now declares `source: "web"` in both bodies (fetch and beacon) and keeps the header.
**Mobile is unchanged and ships no binary.** Fielded builds send `X-Device` and no `X-Source`, so
they land `mobile` through step 4.

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [x] **(b) Existing events cover it.** No new events, no new props, no taxonomy change. It changes
  the **stored semantics of one column**, `user_events.source`, on every client-fired row:
  - a client that identifies itself by neither channel now lands **NULL**, not `mobile`
  - a claimed value outside `{mobile, web, extension}` is ignored on **both** channels (header and body)

  **analytics-lead's decisions, 2026-10-31:**
  - The missing value is **NULL** (`MISSING_EVENT_SOURCE = None`; analytics-lead owns that constant).
  - The **header and body are both restricted** to the closed set `{mobile, web, extension}`. No
    client can claim a server source (`api`, `server`, `calc_queue`) by either channel.
  - **No backfill.** Pre-fix rows keep `source='mobile'`. Read pre-fix rows with `platform='web'` as
    web whatever their `source`. This is written into `docs/data-dictionary.md` `user_events.source`.
  - **No taxonomy change** (`backend/analytics_taxonomy.py` untouched).
  - **No SERIES_BREAKS row:** no metric reads `source`.
- [ ] **(c) WAIVED:** n/a.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. `user_events.source` was already nullable. The column
  comment at `backend/database.py` (`'mobile' | 'web' | 'api' | 'cron'`) was corrected to the real
  set. That is a comment-only change with no DDL. `docs/data-dictionary.md` is updated.
- New/changed feature flags: **none.** The fix is unflagged. It corrects a mislabel and adds no
  behaviour a user can see.
- New env vars / `model_config` keys: **none.** Rollback is a revert of the backend commit. Web's
  body `source` is harmless to the old backend, which ignores unknown top-level keys.

## 3. Evidence scope

- [ ] **Structural guard (mobile):** WAIVED. No mobile file changes. The web-side structural guard
  is `HYG-events-beacon-source` in `qa/web/check_web_structure.py`. It asserts that the text of each
  `sendBeacon(` call (balanced parens, so the fetch body can't satisfy it) carries `source: "web"`.
- [x] **Unit tests:** new `backend/tests/test_events_source.py`, 13 cases. Every case reads the
  stored `user_events.source` back from the DB.

  | Test | Request | Stored `source` |
  |---|---|---|
  | T1 | beacon shape: no `X-Source`, no `X-Device`, body `platform:"web", source:"web"` | `web` |
  | T2 | body `source:"web"` only | `web` |
  | T3 | cached old beacon: body `platform:"web"`, no `source` | `web` |
  | T4 | nothing identifies the client | NULL (`!= "mobile"`) |
  | T5 | `X-Device: iphone`, no `X-Source` | `mobile`, and `platform` still `ios` |
  | T6 ×2 | header `web` / `extension` | `web` / `extension` |
  | T7 | header `extension` + body `source:"web"` | `extension` |
  | T8 ×3 | body `source` `cron` / `api` / `server`, no other signal | NULL |
  | T9 | header `X-Source: api`, no other signal | NULL |
  | T9b | header `server` + `X-Device: iphone` | `mobile` (falls through) |

  **Against the pre-fix module** (`origin/main`'s `analytics_ingest.py`): 9 failed, 4 passed. T5,
  T6 ×2 and T7 pass both before and after, which is correct, since that behaviour is unchanged.
  `test_events_api.py` (45) still passes unchanged.

  **Sabotage**, one at a time, each restored and confirmed byte-identical with `filecmp`/`cmp`:

  | Sabotage | Red |
  |---|---|
  | s1 final fallback back to `"mobile"` | T4, T8 ×3, T9 (5 failed / 8 passed) |
  | s2 drop the body-`source` read | T2 (1 / 12) |
  | s3 drop the body-`platform` step | T3 (1 / 12) |
  | s4 drop the `X-Device` step | T5, T9b (2 / 11) |
  | s5 drop the closed-set check on body `source` | T8 ×3 (3 / 10) |
  | s6 accept any header value | T9, T9b (2 / 11) |
  | g1 remove `source: "web"` from the beacon body only | `HYG-events-beacon-source` (196/197 checks pass) |

- [x] **Code-walk proof:**
  1. The web fetch flush sends `X-Source: web` (`web/js/events.js:158`) and body
     `{events, platform:"web", source:"web"}` (`:166`) → step 1 resolves `web`.
  2. On page hide, `visibilitychange`→hidden (`:220`) or `pagehide` (`:221`) calls `flushOnHide`
     (`:199`), which posts `sendBeacon("/api/events", Blob{events, device_id, platform:"web", source:"web"})`
     (`:203-204`). There are no headers, so step 1 misses, and step 2 reads body `source` → `web`.
  3. The ingest reads `info = g.device_info` (`backend/analytics_ingest.py:426`), which is set per
     request by `_stash_device_and_touch_activity` (`backend/server.py:3158`) from
     `X-Device or None` (`:3104`). It then calls `_resolve_event_source(request.headers, body, info)`
     (`analytics_ingest.py:427`; the helper is at `:328`, the closed set at `:319`,
     `MISSING_EVENT_SOURCE` at `:325`). The value is stamped on every row (`:509`).
  4. Mobile: `sendBatch` spreads `getClientHeaders()` (`mobile/src/api/events.ts:285`), which always
     includes `X-Device` (`mobile/src/api/client.ts:54`), and sends no `X-Source`. Step 1 misses,
     the body has no `source` or `platform`, and step 4 → `mobile`. This is unchanged from today's
     stored value.
  5. Extension: `X-Source: extension` (`extension/background.js:174`) → step 1. Unchanged.
  6. No top-level key validation exists on the body. `ingest_request` reads only `events`,
     `device_id` and `platform`. So the new body `source` can't be rejected, and the old backend
     ignores it.
- [x] **Manual web check** (G-068: reading the row back is what catches this). Run a local
  server on a scratch SQLite DB with `analytics.ingest` and `analytics.client_events` on. Load
  `http://127.0.0.1:<port>/` and let the flags settle so `app_opened` is queued. Then navigate
  away before the 10 s interval flush, so the queue leaves by `sendBeacon`. Read `user_events`
  back. **Expected:** the `app_opened` row has `source='web'`, `platform='web'`, a `dev_` `device_id`.

  **Run 2026-10-31 — PASS.** Server: this branch, `127.0.0.1:5091`, scratch SQLite, both flags
  served `true`, and the served `/js/events.js` carries `source: "web"` twice. In the Browser pane:
  1. Loaded `/`. At t≈3.0 s `FTF_FLAGS_READY` was true and the queue held `["app_opened"]`.
     `ftf.deviceId` was still unminted, because `deviceId()` only runs on a send.
  2. Navigated to `/faq.html`, which doesn't load the SDK, before the 10 s interval flush.
  3. The server logged exactly one `POST /api/events` 200, at the moment of navigation.
  4. On `/faq.html` the queue was `[]` (the beacon's `ok` splice ran) and `ftf.deviceId` was now
     `dev_265d…`. It had been minted inside `flushOnHide`.
  5. `user_events` (client rows) held exactly one row: `app_opened | source=web | platform=web |
     device_type=NULL | device_id=dev_265d…`.

  `device_type` NULL confirms there was no `X-Device` header, so neither the header path nor the
  mobile step resolved it. The body `source` did. Before this fix, the same request stored `mobile`.
  TEST_LEDGER entry owed by release-lead.
- [ ] **Manual TestFlight checklist:** WAIVED. No mobile change and no binary. T5 + code-walk
  step 4 pin that mobile's stored value is unchanged.
- `testID`s added/renamed: none.

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | updated | `POST /api/events`: new **Source** paragraph covering optional body `source` (closed set), header wins, out-of-set ignored, NULL fallback |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | `living-memory/` is release-lead's. The convention (no client-name default for a missing header) is G-068's existing rule, now honoured. Flagged to release-lead in the hand-off |
| `docs/architecture.md` (module wiring / data flow changed) | n/a because | no module wiring or data flow changed; one value's resolution inside the existing ingest step |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | n/a because | no architecture shift |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | updated | "Device platform / source enums": `user_events.source` row rewritten to the real set + the web body-declaration rule |
| `docs/glossary.md` (new domain term) | n/a because | no new domain term |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | n/a here | the NULL / closed-set / no-backfill calls are analytics-lead's 2026-10-31 decisions, recorded in §1 and the data dictionary. Any DECISIONS.md entry is release-lead's (`living-memory/`) |
| `docs/data-dictionary.md` | updated | `user_events.source`: real value set (client `mobile`/`web`/`extension`; server `api`/`server`/`calc_queue`; no `cron`), resolution order, NULL meaning, pre-fix reading rule, no backfill |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint`, plus the `web-structure` job (`python3 qa/web/check_web_structure.py`), all passing on the pushed sha
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming the suites, the sabotage table and the manual web check. This is owed by release-lead, since this branch doesn't touch `living-memory/`
- **TestFlight verification:** none (no checklist; no mobile change)
- Express lane declared by the operator? no. Full gates

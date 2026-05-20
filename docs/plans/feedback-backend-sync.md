# In-App Feedback → Backend Sync

Extension of the in-app feedback feature that landed in PR #41. Today notes only live in mobile `AsyncStorage`; the user has to share-sheet them out manually. This plan adds an authoritative backend store + automatic sync so external TestFlight testers' notes land in our Postgres without any user action.

---

## Goals

1. Every feedback note the user saves on mobile lands in our backend Postgres within a few seconds (or queued + retried if offline).
2. Sync state is visible per-note in the in-app inbox (✓ synced / ↻ pending).
3. Existing share/export path still works as a fallback.
4. Anonymous submission is allowed (so pre-sign-in feedback works), but session-attribution is preferred when available.

## Non-goals

- Real-time admin UI to browse feedback in-app. (DB SQL is fine for now.)
- Replies / threading. (Feedback is a one-way channel.)
- Rate limiting beyond a simple cap. (External tester pool is small.)
- Pruning / retention policy. (Deferred.)

---

## Architecture

### Wire shape

```
Mobile FeedbackSheet
       │ user types + taps Save
       ▼
useFeedback.add()
       │  1. Optimistic local insert (synced: false)
       │  2. POST /api/feedback in background
       │  3. On 2xx → update item to synced: true, server_id set
       │     On 4xx → mark synced: false, error recorded; user can edit/delete
       │     On network failure → mark synced: false, queue for retry
       ▼
mobile/src/api/feedback.ts → POST /api/feedback
       │
       ▼
backend/server.py  /api/feedback  (POST)
       │  validate (severity ∈ {bug, polish, idea}, text ≤ 2000 chars)
       │  resolve session token → user_id (optional)
       │  INSERT OR IGNORE INTO app_feedback (client_id is unique)
       ▼
Postgres: app_feedback row inserted

   ──────  retry path  ──────
App foreground   ─►  useFeedback.retrySync()  ─►  POSTs every unsynced item
```

### Backend schema

```sql
CREATE TABLE app_feedback (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id           TEXT    NOT NULL UNIQUE,   -- the mobile store's id; lets retries be idempotent
    user_id             TEXT,                       -- nullable; anonymous feedback allowed
    username            TEXT,                       -- denormalized snapshot
    screen              TEXT    NOT NULL,
    severity            TEXT    NOT NULL,           -- bug | polish | idea
    text                TEXT    NOT NULL,
    app_version         TEXT,
    platform            TEXT,                       -- ios | android
    device_type         TEXT,                       -- iphone | ipad | macos
    os_version          TEXT,
    client_created_at   TEXT,                       -- ISO timestamp from the client
    created_at          TEXT    NOT NULL            -- ISO timestamp from the server (canonical)
);

CREATE INDEX idx_app_feedback_created_at ON app_feedback(created_at);
CREATE INDEX idx_app_feedback_user_id    ON app_feedback(user_id);
```

`client_id` UNIQUE is the load-bearing dedup mechanism — mobile may retry a save multiple times; the backend ignores duplicate `client_id`s. SQLite uses `INSERT OR IGNORE`; Postgres uses `INSERT … ON CONFLICT (client_id) DO NOTHING`.

### Backend route contract

```
POST /api/feedback
Headers (optional):
  X-Session-Token: <token>     # if present, resolves user_id + username
  X-Device:        iphone|ipad|macos|web    # already attached by client.ts
  X-OS-Version:    e.g. 17.4                # already attached by client.ts
  X-App-Version:   e.g. 1.0.3                # already attached by client.ts

Body (application/json):
  {
    "client_id":           "1748102400000-xyz123",   # required, unique per note
    "screen":              "Trades",                 # required, non-empty
    "severity":            "bug" | "polish" | "idea", # required
    "text":                "free text",              # required, 1..2000 chars
    "client_created_at":   "2026-05-21T03:14:15Z"    # required, ISO 8601
  }

Responses:
  201 Created
    { "ok": true, "server_id": 12345, "created_at": "2026-05-21T03:14:16Z" }

  200 OK  (idempotent retry — client_id already exists)
    { "ok": true, "server_id": 12345, "created_at": "...", "duplicate": true }

  400 Bad Request
    { "error": "missing_field" | "invalid_severity" | "text_too_long" | "..." }

  401 Unauthorized — never used (anonymous submission allowed)
  500 Server Error
    { "error": "internal" }
```

Validation:

- `severity` MUST be one of `bug`, `polish`, `idea`. Anything else → 400.
- `text` MUST be non-empty after `.strip()`, ≤ 2000 chars. Anything else → 400.
- `screen` MUST be non-empty after `.strip()`, ≤ 100 chars (truncate on receive).
- `client_id` MUST be non-empty, ≤ 100 chars.

The session lookup is best-effort — if the token is missing or invalid, we accept the submission with `user_id = null` rather than rejecting. External testers haven't completed sign-in for every code path.

### Mobile data shape

Extend `FeedbackItem` in `mobile/src/state/useFeedback.ts`:

```ts
export interface FeedbackItem {
  id: string;                  // existing — used as client_id when syncing
  created_at: string;          // existing — client capture time
  screen: string;              // existing
  severity: FeedbackSeverity;  // existing
  text: string;                // existing
  app_version?: string;        // existing

  // ── New (sync state) ──
  synced: boolean;             // true = server confirmed, false = pending/failed
  server_id?: number;          // backend's autoincrement id once synced
  last_sync_attempt?: string;  // ISO, debug visibility only
  last_sync_error?: string;    // short message from server on 4xx; empty on success
}
```

Sync semantics:

- `add()` always writes the local store first with `synced: false`. THEN fires the POST asynchronously. On resolve it patches the item in place.
- A "Retry sync" action walks `items.filter(i => !i.synced)` and re-POSTs each one (sequential to keep things simple).
- A `useEffect` in `App.tsx` listens to `AppState` `active` transitions and calls `retrySync()` to flush queued items on every foreground.
- Sync failures are silent for the user except for the badge — no toast spam.

### UI changes

`FeedbackSheet` — after Save:
- Closes the sheet immediately (don't block the UI on the network)
- A toast may show "Feedback saved" — caller's choice; not required

`FeedbackInboxScreen` — per item:
- Replace the bare "Long-press to delete" hint with a small sync badge
- Badge variants: `✓ Synced` (green/muted) / `↻ Pending sync` (orange) / `⚠ Sync failed` (red)
- Add a "Retry sync" button at the top of the screen, visible only when ≥ 1 unsynced item

---

## Subagent contract — required reading for both agents

### Both agents

- Branch from `origin/main`.
- Stay in scope. Touch shared `docs/api-reference.md` and `docs/data-dictionary.md` only to document your changes; don't reformat unrelated entries.
- `tsc --noEmit` clean for mobile; `python3 -c "import ast; ast.parse(...)"` clean for backend.
- Use existing conventions from your respective `CLAUDE.md` files.

### Backend agent (you build the table + endpoint)

Files you should touch:
- `backend/database.py` — add `app_feedback_table` to the metadata; add a migration entry to `_migrate_db()`; add a `save_feedback()` helper.
- `backend/server.py` — add the `POST /api/feedback` route. Stick it near other write endpoints. Use `_require_session()` only if you want to extract user_id; if absent, treat as anonymous (do NOT 401).
- `docs/api-reference.md` — append a section for the new endpoint.
- `docs/data-dictionary.md` — append `app_feedback` table doc.

Test plan:
- Local `curl` smoke test confirms 201 on first POST, 200 + `duplicate: true` on second POST with same `client_id`.
- Invalid severity returns 400.
- Empty text returns 400.

### Mobile agent (you wire sync + UI)

Files you should touch:
- `mobile/src/state/useFeedback.ts` — extend `FeedbackItem`, add server POST in `add()`, add `retrySync()`.
- `mobile/src/api/feedback.ts` (new) — wraps the POST with the existing `api` client (auto-attaches X-Session-Token).
- `mobile/src/screens/FeedbackInboxScreen.tsx` — render sync badges + header "Retry sync" button.
- `mobile/src/components/FeedbackSheet.tsx` — optional "Saved" toast on close.
- `mobile/App.tsx` — wire `AppState.addEventListener('change', ...)` to call `useFeedback.getState().retrySync()` on transitions to `active`.

Don't:
- Block the FeedbackSheet save on the network. Local insert first, network in the background.
- Lose items on sync failure. Always keep them in AsyncStorage; sync state is the only thing that changes.
- Add new dependencies. Use existing `api` from `mobile/src/api/client.ts` (already does auth + headers + JSON).

### Endpoint contract (locked — don't deviate)

Use the request + response shapes documented in the Architecture section above verbatim. If you find a reason to deviate, surface it in the final report rather than guessing.

---

## Done criteria (whole effort)

- A user typing a note + tapping Save sees the note in their inbox immediately with a "↻ Pending sync" badge.
- Within a few seconds the badge flips to "✓ Synced" (with network).
- Force-quit, reopen → previously-pending items retry and flip to synced.
- Backend SQL `SELECT count(*) FROM app_feedback` shows new rows.
- Going offline (Wi-Fi off + cellular off), saving a note → stays pending. Coming back online → next foreground sweeps and syncs.

## Out of scope

- Admin UI for browsing feedback.
- Pruning + retention policy.
- Email/Slack notifications on new feedback.
- Edit / threading on submitted feedback.

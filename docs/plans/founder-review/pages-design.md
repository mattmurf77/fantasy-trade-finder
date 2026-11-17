# Founders' review — Review pages (design)

**Date:** 2026-11-16 · **Status:** built on `feat/founder-review-pages`, unmerged ·
**Scope block:** [pages-scope.md](pages-scope.md) · **Decision:** D-273 (living-memory/DECISIONS.md)

A third choice in Founders' review, next to "Player labels" and "Trade rules": the operator's
review documents (self-contained single-file HTML pages with comment boxes) opened inside the
app, with the founder's comments saved to the server.

## 1. Why it is shaped this way

- **The repo is public.** Page content must never be committed. Pages are uploaded at runtime
  through an operator route and stored in the database.
- **No token in the web view.** The page is arbitrary HTML. The app fetches it through its normal
  API client and hands the web view a string; the page never receives a session token, cookie or
  API URL. Comments come back over the web view message bridge and the app saves them.
- **Founder-only, behind the existing gate.** Same predicate as every `/api/founder/*` route
  (`server._founder_session`: flag `founder.review`, env `FOUNDER_ACCOUNTS`, a verified non-demo
  session), plus a kill switch of its own, `founder.review_pages`.

## 2. The page contract

A page is a complete HTML document starting `<!DOCTYPE html`. Each comment box is a
`textarea[data-k]`: `data-k` is the box key (free text, 1–128 characters, stable across versions
of the page so comments survive a re-upload); `data-label` (optional, up to 300 characters) is
what the operator sees beside the comment in the readback. A box holds up to 10,000 characters.
If the page has `#exportBtn` / `#clearBtn` (browser download, local storage), the app hides them.

## 3. Server

| Route | Auth | Shape |
|---|---|---|
| `GET /api/founder/pages` | founder + `founder.review_pages` | `{pages: [{slug, title, bytes, updated_at, notes}]}`; `notes` = the caller's own count; 404 off the gate |
| `GET /api/founder/pages/<slug>` | same | `{slug, title, updated_at, html, notes: {key: body}}` (caller's own) |
| `PUT /api/founder/pages/<slug>/notes` | same | `{set: {key: {label, body}}}` → `{saved, cleared}`; blank body deletes; ≤ 200 keys; 404 unknown slug |
| `PUT /api/admin/founder-pages/<slug>?title=` | `X-Cron-Secret` | raw `text/html` body, ≤ 8 MiB → `{slug, title, bytes, created, updated_at}` |
| `GET /api/admin/founder-pages` | `X-Cron-Secret` | list with total note counts |
| `GET /api/admin/founder-pages/<slug>/notes` | `X-Cron-Secret` | `{slug, notes: [{key, label, body, updated_at}]}`, never an account id |
| `DELETE /api/admin/founder-pages/<slug>` | `X-Cron-Secret` | page and its notes → `{deleted, notes}` |

- Validation lives in `backend/founder_pages.py` (a leaf: slug `[a-z0-9-]{1,64}`, upload checks,
  note checks). Storage and shaping in `backend/database.py` (`save_founder_page`,
  `load_founder_pages`, `load_founder_page`, `load_founder_page_notes`, `save_founder_page_notes`,
  `load_founder_page_notes_for_operator`, `delete_founder_page`). Routes in `server.py` are thin.
- **Upload size.** The app has no global Flask `MAX_CONTENT_LENGTH`, so nothing rejects a 2.5 MB
  body before the route. The route caps it itself, the `POST /api/feedback` way:
  Content-Length over the cap is 413 before any read; a chunked body is read with a per-request
  `max_content_length` of cap + 1, so at most cap + 1 bytes are ever read. The test-profile fence
  reads a body only when it is at most 8 KiB, so it never reads a page. Notes PUT: same guard at
  4 MiB.
- Admin routes are independent of the founder session and the flag (operator tooling, like
  `/api/admin/founder/rule-notes`); production without `CRON_SECRET` fails closed (503).
- Logs carry counts and byte sizes only: no slug, title, content or id.

## 4. Tables

- `founder_pages`: `id`, `slug` (unique), `title`, `html` (text), `bytes`, `created_at`,
  `updated_at`. Names no person.
- `founder_page_notes`: `id`, `page_slug`, `box_key`, `label`, `body`, `user_id` (ACCOUNT id),
  `updated_at`; unique `(page_slug, box_key, user_id)`. Current text only, no history (a page
  comment is a working draft, unlike the append-only rule notes). Deleted and exported with the
  author's account (`accounts._ADDITIONAL_PRIVATE_TABLES`), and deleted with the page.
- Both are new tables, so `init_db()`'s `metadata.create_all` creates them on the next start in
  every environment (production included: `server.py` calls `init_db()` at import); no
  `migration_cols` row, no existing row touched. This is how `founder_rule_notes` reached
  production.

## 5. App

- `api/founder.ts`: `listFounderPages()` (null on 404, like `getRuleWaterfall`),
  `getFounderPage(slug)` (45 s cap: the page is about 2.5 MB), `saveFounderPageNotes(slug, set)`.
- `FounderReview`: the "Review pages" segment renders only when the list has at least one page.
  With no pages and no Trade rules route the section is the label review alone, as before; with
  Trade rules and no pages it is the two-segment control, unchanged.
- `FounderPagesReview`: the list (title, "Updated Mon D, YYYY · n notes"). A tap opens
  `FounderPageViewer`, a full-screen `Modal` with a safe-area top bar (Close, title, save state):
  a web view nested in Calibration's scroll view would not scroll.
- `FounderPageViewer` / `utils/founderPages.ts`:
  - `source={{ html, baseUrl: 'about:blank' }}`, `incognito`, no shared or third-party cookies,
    no file access.
  - Navigation: `originWhitelist={['*']}` so **every** request reaches
    `onShouldStartLoadWithRequest` (a narrower list makes react-native-webview hand non-matching
    URLs, such as `mailto:` or app schemes, straight to the OS). The handler loads only
    `about:blank` and its `#` links; a top-frame http(s) link opens in the system browser
    (`utils/openExternal.openWebLink`); everything else is dropped. `setSupportMultipleWindows`
    and `javaScriptCanOpenWindowsAutomatically` are false.
  - Bridge (`bridgeScript(notes)`, injected after load): fills each box from the founder's notes
    and fires `input` (the page's own counters update); then posts `{type:'note', k, label, v}`
    600 ms after the last keystroke in a box, at once on blur, and on `__ftfFlush()` (followed by
    `{type:'flushed'}`). A stand-in `localStorage` is installed before the page's scripts only
    when the real one throws on `about:blank`.
  - Native side: `parseBridgeMessage` validates every message (shape, types, the server's
    lengths) before use. Changes are queued per box and saved in batches of at most 200 after
    400 ms; a network or server error shows "Could not save, retrying" and retries at 2 s, 4 s …
    30 s; a 4xx stops ("Could not save"). Close (button or Android back) flushes the page, then
    the queue, and asks before leaving if comments are still unsaved (the `confirmLeaveNotes`
    pattern).
- No analytics events (founder-only tool). Chalkline tokens only.

## 6. Security notes

- The web view never holds credentials: the HTML is a string from the native client; cookies are
  not shared; the page's origin is `about:blank`, so it has no API origin to call even if it
  tried, and no token to call it with.
- The page cannot leave the document or open other apps; links go to the browser only on a
  top-frame navigation.
- Every message from the page is untrusted input: validated on the device, validated again on the
  server (types, lengths, key count, page existence), stored per account, and never logged.
- A founder sees only their own comments; the operator readback strips the account id.

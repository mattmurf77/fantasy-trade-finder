# Feature Scope — Founders' review, Review pages

**Date:** 2026-11-16
**Entry point:** direct ask (operator, through the main session): host the operator's review
documents behind the founder gate, open them in the app, save the comments to the server.
**Builder:** Claude Code builder subagent, worktree `feat/founder-review-pages`; the main session
reviews and merges.
**Operator sign-off on waivers:** needed for §1 (analytics waived: founder-only tool).

Design: [pages-design.md](pages-design.md).

---

## 1. Analytics scope

- [ ] (a) New events specced
- [ ] (b) Existing events cover it
- [x] **(c) WAIVED — no analytics needed because:** a founder-only review tool used by one to
  three accounts; the comments themselves are the record (`founder_page_notes`) and the operator
  reads them back directly. No product decision rests on its usage.

## 2. Schema & flag scope

- New tables: **`founder_pages`** (`id`, `slug` unique, `title`, `html`, `bytes`, `created_at`,
  `updated_at`) and **`founder_page_notes`** (`id`, `page_slug`, `box_key`, `label`, `body`,
  `user_id`, `updated_at`; unique `(page_slug, box_key, user_id)`). Additive, created by
  `metadata.create_all` at start-up in every environment; no `migration_cols` row →
  `docs/data-dictionary.md` updated. `founder_page_notes` is deleted and exported with the
  author's account (`accounts._ADDITIONAL_PRIVATE_TABLES`).
- New flag: **`founder.review_pages`** — code default false; **shipped true** in
  `config/features.json` (founder-only behind `founder.review`'s gate, the precedent
  `founder.review` set), mirrored in `release.json` / `onboarding-v2.json` / `profiles-on.json`.
  OFF ⇒ `/api/founder/pages*` 404 and the app hides the choice. Graduation: none needed (an
  operator tool); the flag is its kill switch.
- New env vars / `model_config` keys: none (`FOUNDER_ACCOUNTS` and `CRON_SECRET` exist).

## 3. Evidence scope

- [x] **Structural guard:** `mobile/tests/check-founder-pages.js` (`npm run test:founder-pages`;
  CI runs it through the `tests/check-*.js` glob): no token, header, cookie or API URL reaches the
  web view; HTML handed as a string on about:blank; navigation blocked (`originWhitelist ['*']` +
  the handler; no new windows) and `navigationDecision` **executed** over the document, `#` links,
  http(s), ten other schemes, frames and form posts; every bridge message validated first and
  `parseBridgeMessage` **executed** over good, malformed and over-long messages; the injected
  bridge **executed** against a stub DOM (fill + `input`, no echo, buttons hidden, maxlength,
  600 ms debounce, blur, flush, clear); the segment absent when the list is null or empty; the two
  existing founder paths unchanged; limits equal `backend/founder_pages.py`; batching, settle,
  backoff and permanent-failure rules executed; the close path; testIDs; no analytics, emoji or
  gradients. `check-founder-rule-waterfall.js` 1b updated for the third segment;
  `check-founder-review.js` unchanged and green.
- [x] **Unit tests:** `backend/tests/test_founder_pages.py` (40): the gate on all three founder
  routes (9 refusal cases including the new flag off), upload validation (slug, empty, DOCTYPE,
  UTF-8, title), the 8 MiB cap by Content-Length before the read and at the read for a chunked
  body (bytes read counted), a 2.5 MB page accepted, re-upload keeps notes, round trip, per-account
  isolation, blank clears, note validation (9 cases) with no write, the limits accepted, unknown
  slugs 404, operator auth (401, production without a secret 503), operator routes not
  flag-gated, operator readback without account ids, delete, counts-only logs, additive tables,
  account deletion / export, flag default and mirrors. Sabotage table in TEST_LEDGER (2026-11-16).
- [x] **Code-walk proof:** pages-design.md §3 and §5 (the size guard, the gate, the bridge).
- [x] **Manual TestFlight checklist** (founder account; a page uploaded with the runbook's curl;
  the page has at least three `textarea[data-k]` boxes, an `#anchor` link, an https link and
  `#exportBtn` / `#clearBtn`):
  1. Calibration → Founders' review shows "Player labels | Trade rules | Review pages". Player
     labels and Trade rules behave as before (type a rule note, tap Review pages: the "Unsaved
     notes" alert appears).
  2. Review pages lists the page with "Updated <date> · 0 notes". Tap it: a full-screen sheet with
     Close at top left inside the safe area, a spinner, then the page. It scrolls the whole way.
  3. The export and clear buttons are not visible. Tap the `#anchor` link: the page jumps. Tap the
     https link: Safari opens; the page in the app does not change.
  4. Type in a box: about a second after stopping, the bar reads "Saving…" then "Saved". The
     page's own character counter (if any) updates as you type.
  5. Type in a second box and tap Close at once: it closes without a prompt. Reopen: both boxes
     hold the text; the list says "2 notes".
  6. Airplane mode, type in a box: "Could not save, retrying". Tap Close: the sheet waits about
     a second, then asks "Comments not saved". Keep trying, turn airplane mode off: "Saved"
     within 30 s; Close closes.
  7. Clear a box and close; reopen: the box is empty; the count dropped by one.
  8. Operator: `GET /api/admin/founder-pages/<slug>/notes` lists the comments with their labels
     and no account id.
  9. A non-founder account: no Founders' review control. With the flag off
     (`founder.review_pages` false + reload): the Review pages choice is gone, the other two
     unchanged.
- [ ] WAIVED: —
- `testID`s added: `founder-review.use.pages`, `founder-review.pages.{list,row,list-loading,
  list-error,list-retry,close,save-state,loading,error,retry,webview}` (no Maestro flow references
  them; `testid-lint.sh` OK).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | updated | the three founder routes after the rule-note rows; the four admin routes after the rule-notes admin row |
| `docs/data-dictionary.md` | updated | `founder_pages`, `founder_page_notes` |
| `docs/config-reference.md` | updated | `founder.review_pages` row |
| `docs/runbook.md` | updated | § Founders' review: "Review pages" (curl upload / list / readback / delete with `$CRON_SECRET` from the environment, the page contract, symptoms) |
| mobile docs | updated | `mobile/src/components/CLAUDE.md` `founder/` row, `mobile/src/api/CLAUDE.md` `founder.ts` row, `mobile/src/utils/CLAUDE.md`, `mobile/tests/README.md` |
| `living-memory/LLD.md` | n/a because no convention shifted: a founder route on the existing gate, an admin route on `_require_cron_auth`, the existing body-cap pattern |
| `docs/architecture.md` | n/a because no new data flow beyond the founder routes already described; `backend/CLAUDE.md` module map gains `founder_pages.py` |
| `living-memory/HLD.md` | n/a because no architecture shift |
| `docs/cross-client-invariants.md` | n/a because the limits are pinned app ↔ server by the structural guard, and no other client uses them |
| `docs/glossary.md` | n/a because "Founders' review" is already defined; "review page" is plain English |
| ADR or `DECISIONS.md` entry | updated | D-273: review pages are hosted behind the founder gate, stored in the database and never in the public repo; comments are saved server-side |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` (runs every `check-*.js`) + testid-lint.
- **Evidence recorded:** TEST_LEDGER 2026-11-16 entry (targeted pytest, check suites, tsc,
  sabotage table).
- **TestFlight verification:** the checklist in §3, by the operator on the build carrying this.
- Express lane declared by the operator? no.

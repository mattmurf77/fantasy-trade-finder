# Launch QA — Phase 1 Audit Report
*2026-06-11, branch `trade-engine-v2`. 6 auditors → 50 raw findings → 42 deduped → 40 confirmed by adversarial verification (2 refuted). Full structured findings: [launch-qa-phase1-findings.json](launch-qa-phase1-findings.json).*

**Baseline (Phase 0):** 136/136 backend tests pass; server boots clean (port 5000 on the dev Mac is AirPlay; dev instance serves on 5050).

## P0 — Launch blocker (1)

| # | Location | Finding |
|---|---|---|
| 1 | `backend/server.py:4981` | **`PUT /api/admin/config/<key>` is completely unauthenticated.** Anyone who finds the URL can rewrite any `model_config` value (Elo K-factors, fairness weights, thresholds); changes persist to DB and hot-reload into ranking/trade services immediately, silently corrupting math for every user. `GET /api/admin/config` (line 4966) exposes the whole tuning surface too. Fix: apply the existing `X-Cron-Secret` pattern (`_require_cron_auth`, line ~6130) to all `/api/admin/*` routes. Found independently by 3 auditors; verifier confirmed no `before_request` guard covers it. |

## P1 — Fix before launch (3)

| # | Location | Finding |
|---|---|---|
| 2 | `backend/server.py:4951` | **`/api/debug/log` unauthenticated** — dumps last 200 log lines to any caller: usernames, Sleeper user_ids on every login, league IDs, config-change records, full tracebacks. Fix: CRON_SECRET-gate or disable in prod. |
| 3 | `backend/server.py:1967` (+8 more routes) | **KeyError→HTML 500s during mobile's normal sign-in window.** Mobile signs in via `/api/extension/auth` (session has no `league`/`players`/`trade_svcs`), then INIT-08 navigates to Main *before* `/api/session/init` completes (5–10 s on Render free tier). Screens fire immediately; `/api/rank3` hits `sess["league"]` outside its try block → unhandled 500 and **the user's ranking is dropped**. Same bare indexing in `/api/trades` (3376), `/api/league/summary` (4359), `/api/trades/matches` (3681), `/api/trends/*`, `/api/tiers/save`, `/api/tiers/copy-from-format`, `/api/rankings/reorder`, `/api/league/picks`. The disposition route was already null-guarded for exactly this class after a live bug (FB-01). Fix: `.get()` guards + structured `409 session_not_initialized` JSON (pattern at 3943-3944), plus a generic JSON error handler so no route ever emits an HTML 500. |
| 4 | `backend/server.py:5748, 5771, 5794` | **Notifications IDOR** — `GET /api/notifications` and the read/read-all POSTs trust client-supplied `user_id`; any authed user can read or mark-read anyone's notifications (trade-match titles leak partner/player/league names). Docstring claims a session cross-check that doesn't exist. Fix: always use `sess["user_id"]`; clients already send their own id, so nothing breaks. |

## P2 — Should fix before/at launch (12)

**Auth/abuse (2):** test-user login bypass `test_user_fp_*` reachable in prod with no env gate (`server.py:4844`); `/api/admin/engine-metrics` unauthenticated (`server.py:5011`).

**Wrong-route bug (1):** `@app.route("/api/sleeper/players")` decorator is attached to the helper `_ensure_sleeper_cache_populated` instead of `sleeper_players()` — the JSON error handler is dead code; cold-start fetch failure returns HTML 500 (`server.py:5032`).

**Misleading failure UX (3):** Sleeper 5xx during login reported as "User not found" (`server.py:4884`); league-list failures swallowed → "No leagues found" dead end (`server.py:4897`); web `selectLeague` error paths deref `el` without null check → invited-league auto-select crashes to blank screen on fetch failure (`web/js/app.js:668`).

**Product correctness (3):** real leagues with empty opponent rosters get four *fabricated* demo opponents ("DynastyKing" et al.) presented as trade partners (`server.py:5246`); `trade_math.star_tax=true` is a silent no-op under v2/v3 engines (explicit NOTE at `trade_service.py:1668`) — the legacy-only taxes are bypassed while config/docs imply they work; mobile outlook picker missing `not_sure` (4 of 5 canonical modes, defaults to `contender`) (`mobile/src/components/OutlookSheet.tsx:30`).

**Cross-client drift (3):** web rankings-table tier cutoffs hardcoded 10–20 Elo below `tier_config.json` — same player shows different tiers on web vs mobile (`web/js/app.js:1977`); Depth tier is purple in extension, orange in web+mobile, and the invariants doc says purple (`extension/content.css:53`); `decision_type='disposition'` rows exist in `swipe_decisions` but invariants doc + data dictionary list only `rank|trade` (`docs/cross-client-invariants.md:55`).

## P3 — Cleanup (24, logged, not pre-launch work)

Highlights: `/api/rookies` returns `player_id/full_name` but clients read `id/name` (rookies render as "?"); web demo-session token stored under a key `apiFetch` never reads; `/api/feature-flags/reload` unauthenticated; root scratch files ship in deploy image; CRON_SECRET compared with `!=` not `hmac.compare_digest`; no Sleeper retry/backoff; dead flag `trade.three_team`; `trade_math.human_explanations` no-op on v2/v3 cards; extension localhost host_permissions + over-broad `tabs` permission; mobile silver vs web gray bench color; ~10 docs-drift items (api-reference missing 3 routes, data-dictionary gaps, glossary, config-reference stale, two mobile CLAUDE.md files naming a nonexistent `/api/flags` endpoint). Full list in the JSON.

## Refuted by verification (2)

- Extension dev `host_permissions` "ship in the store manifest" — extension isn't on the store; load-unpacked dev only.
- SQLite WAL-mode comment misleading — true but dev-only; `render.yaml` injects Postgres in prod. (Comment cleanup still worthwhile.)

## Recommended fix order (Phase 4)

1. **Auth batch (P0 #1, P1 #2, P2 auth pair, P3 flags-reload):** one `before_request`-style CRON_SECRET guard over `/api/admin/*`, `/api/debug/log`, `/api/feature-flags/reload`; env-gate the `test_user_fp_` bypass. Small, mechanical, one test file.
2. **Session-window 500s (P1 #3):** `.get()` guards + `session_not_initialized` JSON + generic JSON error handler. Highest user-visible impact for mobile launch.
3. **Notifications IDOR (P1 #4):** ignore client `user_id`.
4. P2s in the order listed, each with a regression test; P3s post-launch.

Then Phase 3 (live API smoke + web UI flows + mobile crash review + extension review) and Phase 5 regression/launch gate.

---

## Phase 4 fix status (2026-06-11)

Fixed on `trade-engine-v2`, all backed by new regression tests in
[backend/tests/test_launch_qa_fixes.py](../../backend/tests/test_launch_qa_fixes.py) (21 tests, all green; full suite 165 green):

| Finding | Fix |
|---|---|
| **P0** admin config unauthenticated | `_require_cron_auth()` now guards `/api/admin/config` (GET+PUT), `/api/admin/engine-metrics`, `/api/debug/log`, `/api/feature-flags/reload`. Verified live over HTTP (401 without secret, 200 with). |
| **P1** `/api/debug/log` open | Same cron-auth guard. |
| **P1** session-window 500s | New `_require_initialized_session()` helper on 22 league-backed routes → structured **409 `session_not_initialized`** instead of KeyError/HTML-500; background pregen hardened with `.get()`; added a global JSON error handler so no route can emit an HTML 500. |
| **P1** notifications IDOR | All three notification routes ignore a mismatched client `user_id` → **403**; only the session user's data is touched. |
| **P2** test-user bypass in prod | `test_user_fp_*` login bypass disabled when `_IS_PROD_ENV` (non-SQLite). |
| **P2** engine-metrics open | Cron-auth (above). |
| **P2** `/api/sleeper/players` wrong decorator | Moved `@app.route` from the helper to `sleeper_players()` so its JSON error handler is live. |
| **P2** Sleeper 5xx → "User not found" | `/api/sleeper/user` maps 5xx/URLError → **503 `sleeper_unavailable`**; 4xx still 404. Web login surfaces `message`. |
| **P2** league fetch swallows outage | `/api/sleeper/leagues` returns **503** when Sleeper fails AND no local fallback; web shows retry message, not "wrong username". |
| **P2** web `selectLeague` null-deref | Added null-safe `resetLeagueItem(el)` helper; all 4 error paths use it (fixes invited-league auto-select crash). |
| **P3** `!=` secret compare | `hmac.compare_digest`. |
| **P3** `/api/feature-flags/reload` open | Cron-auth (above). |

Hardening also added a catch-all `@app.errorhandler(Exception)` returning JSON — so the *class* of "route X 500s with an HTML body" is closed for every route, not just the ones audited.

**Docs updated:** `api-reference.md` (admin auth + reload auth), `config-reference.md` (CRON_SECRET scope), `runbook.md` (admin auth, test-user prod note).

**Deferred to post-launch (logged, not fixed):** remaining P2s requiring product/design decisions — fabricated demo opponents for real empty-roster leagues (`server.py:5246`), `trade_math.star_tax` no-op under v2 (config/docs change), mobile outlook picker missing `not_sure`, web tier-cutoff drift vs `tier_config.json`, extension Depth color, `decision_type='disposition'` doc gap — plus all P3 cleanup/docs items. See [launch-qa-phase1-findings.json](launch-qa-phase1-findings.json).

---

## Phase 3 — dynamic testing (2026-06-11)

R7 (live API smoke, real Flask on its own port + DB copy), R9 (mobile crash-risk static), R10 (extension static). 15 findings (1 P1, 5 P2, 9 P3) — full data: [launch-qa-phase3-findings.json](launch-qa-phase3-findings.json). R7 confirmed every Phase-1/4 fix still holds (auth gating, 409 guard, IDOR, test-user bypass, Sleeper 5xx→503, players decorator).

**Fixed (3 backend input-validation 500s; +5 regression tests; suite now 170 green):**

| Finding | Fix | Verified |
|---|---|---|
| **P2** `/api/notifications/read` non-list `ids` → 500 leaking SQL internals | validate `ids` is a list of ints → 400 before DB | test |
| **P2** `/api/sleeper/rosters/<digits>` Sleeper 404/5xx → 500 leaking upstream error | 4xx→404 `league_not_found`, 5xx→503, no leak | **live** (404) + test |
| **P3** `/api/debug/log?n=abc` → 500 leaking Python error | int-parse guard → 400 | **live** (400) + test |

**P1 downgraded — false on its stated mechanism.** R9 claimed `/api/trio` 500s via `KeyError` on `sess["service"]` during the mobile session-init window. Verified false: every session-creation path (`extension_auth` 7227, `session_init` 7839, demo 5671) sets `"service"` unconditionally in the payload, so `sess["service"]` cannot `KeyError` — a stale token 401s (handled), a fresh session returns trios from the universal pool. The legitimate kernel (RankScreen `trioQuery` has no `enabled` gate + global `retry:1`) is a minor client-robustness nit, not a launch-blocking crash. Recommended (not blocking): gate the query on `!!leagueId && hasToken` and add 409/timeout-aware retry.

**Deferred (client robustness + dev-only; not launch-blocking):**
- Mobile (R9): TrendsScreen movers query ungated in init window (P2); `OutlookSheet` ignores `initial` after mount → Edit always opens on 'contender' (P2, real small bug); progress/streak no error UI (P3); `Math.round` on undefined elo renders 'NaN' (P3).
- Extension (R10, dev-only / not shipped to store): popup swallows non-expiry refresh errors (P2); hardcoded API base + localhost host_permissions (P3); message handlers don't check sender but MV3 isolation limits exposure (P3). R10 confirmed **no** XSS via badge injection (textContent only) and that Sleeper-DOM selectors degrade gracefully.
- Backend note from R10 (out of its scope, worth tracking): `/api/extension/auth` has **no rate limiting** → unthrottled username→Sleeper-id enumeration / Sleeper-API amplification. Pre-existing; consider a limiter post-launch.

---

## Phase 5 — Launch gate

Engineering blockers (P0/P1) are **closed**. Remaining gate items are operational/decision, for the operator:

- [x] No open P0/P1 engineering findings
- [x] Full suite green (170), incl. 26 launch-QA regression tests
- [x] Auth gates verified live; session-init 409, Sleeper-outage 503, input-validation 400s verified
- [x] Docs synced (api-reference, config-reference, runbook)
- [ ] **`CRON_SECRET` set + rotated in Render env** — now that it guards the whole admin surface, an unset secret makes those routes **fail closed (503)** in prod. Must be set before/at deploy. (Was pending rotation since 2026-06-10.)
- [ ] **Clients point at the prod API URL via config, not hardcode** — re-confirm web/mobile base-URL resolution for the prod build (extension is dev-only).
- [ ] **Feature flags set to intended launch values** — decide `trade_math.star_tax` (currently a no-op under v2) and the other deferred flag items.
- [ ] **Scratch files excluded from deploy** — `tmp_check_db*.py`, `dump_mismatches.py`, `reorganize_project.py` at repo root (P3).
- [ ] **Postgres path verified** if launching on `DATABASE_URL` (the SQLite-only WAL comment is cosmetic; render.yaml injects Postgres).
- [ ] Decide the deferred P2 product items (demo opponents on real empty leagues; mobile `not_sure`; web tier-cutoff drift).

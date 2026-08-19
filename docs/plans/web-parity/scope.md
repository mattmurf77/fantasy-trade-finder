# Feature Scope — Web Parity Phase 0 (stop the bleeding)

**Date:** 2026-08-19
**Entry point:** direct ask → [`plan.md`](plan.md) Phase 0
**Builder:** session 5f1ac8ee (branch `fix/web-phase0`, cut from `origin/main` @ `50e0451`)
**Operator sign-off on waivers:** pending — waivers listed in §6

> Express lane was **not** declared, so the full gate applies. Phase 0 is
> bug-fix-shaped but does change user-visible behavior (new pages, changed demo
> flow), so it gets a scope block rather than a one-line ledger note.

---

## 1. Analytics scope

**(b) Existing events cover it** — and one of them starts working for the first time.

No new events. The change is that web events now *arrive at all*: `track()` used to
early-return on a flag map that had not loaded yet, so every event fired during boot was
dropped silently. `app_opened` is emitted unconditionally in `boot()` and was therefore
dropped on **every** web session.

| Event | Before | After |
|---|---|---|
| `app_opened` | never arrived from web | arrives, `launch_type: "web"` |
| `screen_viewed` | arrived only if fired >1 network RTT after load | arrives |
| `find_trades_tapped` | arrived (user-timed, always post-flag) | unchanged |

**Watch item:** web `app_opened` volume goes from zero to non-zero on deploy. Any
web-inclusive funnel baseline computed before this date is not comparable to one after.
Web still emits only 3 event types; `signin_attempted` / `signin_succeeded` /
`experiment_exposed` remain unimplemented (plan P1-2 territory).

## 2. Schema & flag scope

- **Tables/columns:** none.
- **Feature flags:** none added, none flipped. `landing.try_before_sync` is read but not changed.
- **Env vars / `model_config`:** none.
- **New module-level constant:** `_PROD_BLOCKED_STATIC` in `backend/server.py` — a
  hardcoded set, deliberately not a flag: it gates build-time design artifacts, not product
  behavior, and should not be togglable at runtime.
- **Ship-the-knob:** the whole phase is static assets + two request hooks. Rollback is
  `git revert` of a single commit; there is no data migration and no persisted state change.

## 3. Test scope

**Maestro/simulator: WAIVED — D-056 retired both, and none of this is mobile-visible.**
One mobile-adjacent dependency was found and respected (see §5).

**Web has no test harness at all** — CI runs `pytest`, `tsc --noEmit`, and `testid-lint.sh`,
none of which touch `web/`. Building one is plan item P1-2 and is *not* in this phase. Until
it exists, evidence for web is manual browser verification against a local server running
this branch's code. What was run:

| Check | Method | Result |
|---|---|---|
| Backend suite | `pytest backend/tests -q` | **3524 passed, 1 skipped** |
| JS syntax | `node --check` on `app.js`, `events.js`, and both inline scripts | all parse |
| Handle parser | 8-case table test of `extractUsername()` | 8/8 pass |
| `app_opened` survives boot | fresh load, read `ftf.events.queue.v1` | queued `seq:1`; `POST /api/events` → 200 |
| CTA fits at 375px | `getBoundingClientRect()` on `#auth-btn` | `x 155→355` inside 375; was `20→400` |
| Demo trap | seed demo user w/o league, reload | honest copy + working "Start over"; **zero** `/api/sleeper/leagues` requests |
| 404 routing | `fetch` probes | `/nope` → HTML 404; `/api/*` + `/og/*` → JSON 404 |
| Prod block | Flask test client, `_IS_PROD_ENV` toggled | 3 lab pages 404 in prod, 200 in dev; real pages unaffected |
| Contact → backend | submitted the form, read `/api/feedback/admin` | landed as `web-contact-data-request`, `[DATA REQUEST]` prefix, anonymous |
| Page sweep | 12 pages | all 200; landing console clean |

**Backend pytest added:** none. The two new hooks are exercised by the manual matrix above;
codifying them is a P1-2 deliverable once a harness exists to hold them.

## 4. Docs updated

| Doc | Status |
|---|---|
| `web/CLAUDE.md` | **updated** — added `contact.html` + `404.html`; corrected 4 rows that overstated what ships (`ranking-method`, `player`, `profile`, `league-rankings` were all listed as plain "yes") |
| `docs/api-reference.md` | **updated** — 404 content-type contract |
| `docs/reviews/2026-08-19-web-parity-audit.md` | the evidence base |
| `docs/plans/README.md` | row added |
| `docs/data-dictionary.md` | n/a — no schema change |
| `docs/config-reference.md` | n/a — no flag or env change |
| `docs/architecture.md` / `living-memory/HLD.md` | n/a — no architectural shift |
| `living-memory/LLD.md` | n/a — no convention shift |
| `docs/cross-client-invariants.md` | n/a — no shared enum/threshold touched |

## 5. Findings that changed the plan

1. **`ranking-method.html` is NOT an orphan.** The plan said delete it; the shipping mobile
   app opens it as a read-more explainer (`mobile/src/screens/TradesScreen.tsx` `readMoreUrl`).
   Deleting it would 404 for TestFlight users on already-installed builds. **Kept**; its fake
   controls (anchors to non-existent fragments, a `console.log` handler, hover/pointer
   affordances) were removed and the explanatory copy preserved.
2. **The `league-rankings` nav link was already correctly gated.** It ships `class="tab hidden"`
   at `web/index.html:760` and is only unhidden by `_applyPowerRankingsFlag()`. The audit's
   "linked from the primary nav" claim was wrong — the auditor reached the page by URL. No change made.
3. **The demo trap had two independent causes**, not one: a synthetic user id fed to a real
   Sleeper endpoint, *and* a full-screen overlay with no exit. Both fixed — the escape hatch is
   unconditional, so any future failure to list leagues is survivable regardless of cause.
4. **The demo marker was in the wrong storage.** `ftf_demo_mode` lived in `sessionStorage`
   while the demo user lived in `localStorage`, so a new tab restored a demo user with no demo
   marker. The marker now rides on the saved user object itself.

## 6. Waivers requiring operator sign-off

| # | Waived | Why | Owner |
|---|---|---|---|
| W1 | **P0-3 not done** — `[STATE]` still in `web/terms.html:157` | Governing-law jurisdiction is a legal choice; an agent inventing one would be worse than the placeholder | Operator |
| W2 | **No support email added** | None exists anywhere in the repo. `contact.html` gives web users a working channel without one; a plain email address can be added alongside | Operator |
| W3 | **`web/admin/analytics.html` still reachable in prod** | It is the operator's live dashboard. Its data is `CRON_SECRET`-gated; only the shell is public. Blocking it removes operator tooling — their call, not an engineering one | Operator |
| W4 | **No automated regression test for these fixes** | No web test harness exists (plan P1-2). Manual matrix in §3 is the evidence | Accepted for Phase 0 |
| W5 | **`league-rankings.html` still 401s when reached by direct URL** | Its flag is off by design; the page shows an unavailable state. Not user-reachable through the UI | Accepted |

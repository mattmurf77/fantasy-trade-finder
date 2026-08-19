# Web Parity — Plan

> **Status:** proposed, not started. No code written.
> **Entry point:** direct ask (2026-08-19) — "audit the website + what's needed to bring it to par."
> **Evidence base:** [`docs/reviews/2026-08-19-web-parity-audit.md`](../../reviews/2026-08-19-web-parity-audit.md)
> — four parallel auditors; live browse against prod, source claims verified against `origin/main`.

---

## Table of Contents
- [The concern with "par"](#the-concern-with-par)
- [Decisions needed before build](#decisions-needed-before-build)
- [Phase 0 — stop the bleeding](#phase-0--stop-the-bleeding)
- [Phase 1 — foundation](#phase-1--foundation)
- [Phase 2 — public surface](#phase-2--public-surface)
- [Phase 3 — parity, tiered](#phase-3--parity-tiered)
- [Cross-cutting](#cross-cutting)
- [Sequencing and sizing](#sequencing-and-sizing)
- [Risks](#risks)
- [Open questions](#open-questions)

---

## The concern with "par"

Literal parity means porting 34 screens of a deep, stateful, gesture-driven app into vanilla
JS with no build step. That is a very large amount of work for a return that is mostly
*duplicated*, and some of it — swipe decks, draft-day live rooms, push — is worse on desktop
than it is on phone.

The web also has a job mobile cannot do. **The app is TestFlight-only. The website is the
only publicly reachable surface the product has.** Every acquisition path, every shared link,
every search result lands here. Today that surface has zero SEO metadata, a self-trapping
demo, and no mention of the app.

And there is one place where web genuinely beats mobile: **big-board work**. Drag-ordering
200 players, bulk tier assignment, and league-wide analysis are all better with a mouse and
a 1400px viewport.

So this plan delivers the full parity backlog as asked, but tiers Phase 3 so the operator can
stop at the right place. Three coherent postures:

| Posture | What web is | Stops after |
|---|---|---|
| ~~A. Front door~~ | ~~Marketing + public tools + handoff to the app~~ — **foreclosed 2026-08-19**: it was the posture that depended on anonymous tools | — |
| **B. Companion** *(recommended)* | Front door + desk-friendly deep work + accounts | Phase 3a |
| **C. Full parity** | Everything mobile does | Phase 3c |

**Recommendation: B.** It captures web's comparative advantage (board work, league analysis,
public tools) and the entire acquisition funnel, without rebuilding swipe decks and draft
rooms that are better on phone. C is available if the operator wants it — Phase 3b/3c are
specified either way.

Phases 0–2 are unconditional under all three postures.

---

## Decisions needed before build

| # | Decision | Options | Recommendation |
|---|---|---|---|
| **D1** | Target posture | A / B / C above | **B — Companion** |
| **D2** | Rebuild or remediate | Rewrite `web/` on a framework, vs fix in place | **Remediate.** `CLAUDE.md` commits to "no framework, no build step"; the audit found the site is already on-brand Chalkline with working drag boards. The problems are duplication and rot, not architecture. |
| **D3** | Introduce a minimal build step | None / bundle+minify only / full toolchain | **Bundle + minify only.** 266 KB unminified `app.js` + 133 KB CSS at `no-cache` is the single biggest perf lever, and shared-token extraction (P1-1) needs *some* pipeline. Stop short of a framework. |
| **D4** | Demo mode: fix or remove | Fix the synthetic-id path / remove the CTA | **Fix.** `landing.try_before_sync` is now ON for mobile on `main`; removing web's demo diverges the funnel further. But remove the CTA *today* if the fix is not same-day. |
| **D5** | Express lane? | Full gates / express on the P0 subset | **Operator's call.** Agents never self-select express. Note the bright line: P2-1 (public calculator) touches API surface + analytics and is **not** a quick fix under any framing. |

---

## Phase 0 — stop the bleeding

> **STATUS: BUILT 2026-08-19**, commit `26d7841`. 7 of 8 items; P0-3 needs the operator.

Everything here is live-user-facing breakage. No new capability, no new endpoints.

| ID | Fix | Where | Note |
|---|---|---|---|
| P0-1 | **Demo path no longer traps the user** | `web/js/app.js` demo flow + league modal | Two independent bugs: the synthetic id fed to `/api/sleeper/leagues/`, *and* a modal with no escape. **Fix both** — the modal needs a close/retry regardless of what caused the error, and `localStorage` must be cleared on the failure path so the trap does not persist across visits. |
| P0-2 | **Delete `ranking-method.html`** | `web/ranking-method.html`, `web/CLAUDE.md:16` | Dead stub with commented-out routing; near-duplicate of `#ranking-method-screen` already inside `index.html`. Correct the CLAUDE.md row claiming it shipped. |
| P0-3 | **Fill `[STATE]` in Terms** | `web/terms.html:157` | **Operator input required** — a governing-law jurisdiction is a legal choice, not an engineering one. |
| P0-4 | **Give web users a data-request route** | `web/privacy.html`, `web/terms.html` | Both docs point to an in-app feedback button and an App Store page that do not exist for web. Either add a contact address or wire `POST /api/feedback` (already public) into a web form. Compliance-relevant. |
| P0-5 | **Fix the clipped mobile CTA** | `web/css/styles.css:2808` | 380px box in a 375px viewport, no scroll to recover. The most important control on the site. |
| P0-6 | **Fix the analytics race** | `web/js/app.js:34, 6234` | `await _loadFeatureFlags()` before `boot()`, or make `track()` buffer pre-flag events and flush on resolve. Prefer buffering — it fixes the class of bug, not the instance. |
| P0-7 | **Un-ship the dark/broken pages** | `player.html`, `profile.html`, `league-rankings.html`, `style-guide.html`, `admin/analytics.html` | Four options per page: fix, flag-gate at the HTTP layer, remove, or leave. Recommended: remove `style-guide.html` from prod, gate `admin/`, unlink `league-rankings.html` from nav while its flag is false, fix `profile.html`'s handle parser (one line) since it is the viral surface. |
| P0-8 | **HTML 404 page** | `backend/server.py` | Unknown paths currently return raw JSON `{"error":"not_found"}` to a browser. |

**Verification:** manual browser pass against each fix + the Phase 1 harness once it exists.
P0 lands before the harness, so each item gets a written before/after note in the ledger.

---

## Phase 1 — foundation

> **STATUS: BUILT 2026-08-19** on `fix/web-phase0`. All six items done; the structural
> gate went from 101/161 to **161/161**. Not merged, not deployed.

Nothing in Phase 2 or 3 is safe or cheap until this lands.

### P1-1 — One token block *(the highest-leverage change in this plan)*

`web/css/styles.css` is linked by exactly one page; twelve others inline ~2,500 lines of
copy-pasted CSS with their own re-declared token block. This is why `--line-strong: #3D4654`
still ships in 12 places on `main` — a live 2.03:1 WCAG 1.4.11 failure on every input and
secondary-button border — while only `league-rankings.html` got the corrected `#59647A`.

Extract the token block and shared component CSS to a single stylesheet every page links.
**Then fix `--line-strong` once**, including `style-guide.html:14`, which currently documents
the wrong value and keeps propagating it.

Sweep in the same pass: the three emoji-as-icon violations (`positional-tiers.html:1546`,
`app.js:676`, `app.js:711`), the `#22C55E` data-encoding green used as landing chrome, the
Archivo `<h1>` that should be Barlow Condensed, and the off-palette `rgba(79,124,255,…)` at
`styles.css:4158`.

### P1-2 — A web test harness *(new; nothing exists today)*

CI runs `pytest`, `tsc --noEmit`, and `testid-lint.sh` — **none of them touch `web/`.** There
is no Playwright, no axe, no Lighthouse, no root `package.json`. Every web change in this plan
would otherwise be unverifiable, and D-056's mobile evidence rules do not cover web.

Minimum viable: Playwright smoke over the real pages (loads, no console errors, primary CTA
reachable at 375px and 1280px), axe on each page, and a Lighthouse budget. Wire as a CI job.

This is the gate that makes Phases 2–3 auditable. It should land before them.

### P1-3 — SEO and social metadata

Zero across all ten pages: no description, no `og:`, no Twitter card, no canonical, no
JSON-LD, no favicon. `/robots.txt` and `/sitemap.xml` both 404.

Sharpest instance: `profile.html` is the public viral surface and is 100% client-rendered, so
unfurlers see `Loading profile…`. **The backend already solves this** for `/s/tiers/…` and
`/s/trade/…` with server-rendered OG wrappers and generated `/og/*.png` cards
(`server.py:17204`). Extend that pattern to `/u/` rather than inventing one.

### P1-4 — Accessibility floor

`index.html` — the whole application — has no `<main>`, no `<nav>`, one landmark, and zero
headings below `<h1>`; every section title is a styled `div`. `positional-tiers.html` and
`league-rankings.html` have no headings at all. Avatars use `alt=""` where adjacent text is
the only name carrier. Tap targets measured at 42/30/24/16px against a 44px standard.

### P1-5 — Delete dead weight, fix stale data

- ~200-line debug-drawer IIFE with **90 no-op call sites** on `main`; its DOM targets do not
  exist. Its unreachable `fetchBackend()` calls the CRON-gated `/api/debug/log`, so the public
  bundle advertises an operator endpoint.
- `positional-tiers.html:1576-1631` — 55-player `SAMPLE_PLAYERS` with **2024-era teams**,
  bucketed into tier lanes during module init and shown to real users before the API lands.
- `TIER_CONFIG` bakes all 64 Elo bands with a comment demanding lockstep with the API and no
  test enforcing it. Either delete the baked copy or add the test.
- Two parallel session-token stores (`localStorage.fumble_session_token` vs
  `sessionStorage.ftf_session_token`), read and written inconsistently. Pick one.

### P1-6 — Rename to Fleeced

Nothing on the site says Fleeced. Every page title and both legal documents still say
"Fantasy Trade Finder" — the web surface predates D-057. Titles, legal docs, OG tags, and the
landing copy.

---

## Phase 2 — the logged-in web app

> **REVISED 2026-08-19 by operator decision: no anonymous surfaces.** The app has no
> anonymous mode either — `mobile/src/api/client.ts` auto-attaches `X-Session-Token` to
> every request, so all three calculator modes (`live` / `demo` / `league`) run inside a
> session. An anonymous web calculator would be a *new product surface*, not parity, and
> is out of scope.
>
> The original Phase 2 justified itself partly on SEO and acquisition. That justification
> does not survive this decision — see [What this costs](#what-this-costs) below. Phase 2
> is now simply "the web app does what the mobile app does, for signed-in users."

### P2-1 — Trade calculator (session-gated)

Mirror `TradeCalculatorScreen`: **In league** (real opponents and rosters, dual-board
verdict, eveners, starting-lineup before/after) and **Real values** (consensus,
server-authoritative). Both call `POST /api/trade/evaluate`, which web already has a
session for. Skip the mobile **Demo league** mode unless the operator wants it — it
exists on mobile for an offline/no-league state the web app does not have.

**No rate limiter needed as a blocker.** That prerequisite existed only because the
original plan put this endpoint in front of anonymous traffic. Behind a session it carries
the same exposure mobile already does. Worth noting for the record, and *not* worth
blocking on: `/api/session/init` mints sessions freely, so a session is not a meaningful
cost barrier — but that is a pre-existing property of every session-gated route, not
something this feature introduces.

### P2-2 — Market pulse (in-app)

`GET /api/market/movers`, flag `market.movers` ON. Mobile surfaces this as
`MarketPulseStrip` **inside** the League screen. Web should match that placement — a strip
in the app, not a public page.

### P2-3 — Landing page

Still valid and unaffected: the current landing is one viewport with no feature section, no
screenshots, no social proof, and **no mention of the mobile app**. Given TestFlight-only
distribution this is the one place the site should convert visitors into testers. This is
marketing copy, not an anonymous tool.

### Dropped from Phase 2

- **Public trade calculator** — the operator decision above.
- **Player pages as an SEO surface.** `players.profile_pages` is **false**, and it is false
  on mobile too, so shipping them is not parity. `player.html` and
  `/api/players/<id>/profile` already exist and are web-only; turning them on is a product
  decision, not a parity gap. Left dark.

### What this costs

Worth stating plainly so it is a choice and not an accident: **with no anonymous surfaces,
the website cannot do acquisition.** Every page of real value sits behind "type your
Sleeper username". The SEO work already shipped in Phase 1 (metadata, robots, sitemap)
still helps the landing page, FAQ and legal pages get indexed, but there is no indexable
*tool* for anyone to find.

That is a coherent position — the site is a companion to the app, not a funnel. It is only
a problem if acquisition is later expected from the web. Raise it then as its own decision,
with the public calculator as the obvious first move.

## Phase 3 — parity, tiered

### 3a — Companion *(recommended stopping point, posture B)*

| Item | Endpoints (all live) | Why web |
|---|---|---|
| **Account sign-in** | `/api/auth/apple`, `/api/auth/google`, `/api/account`, `/link-sleeper`, `/session/signout` | Web has **no accounts at all** — username-only, no cross-device, no sign-out, and web sessions can never become verified. `/api/auth/google` has **no client anywhere** and is the natural web-first debut. |
| **Ranking import** | `/api/rankings/import-match`, `/import-apply` | Pasting a board is a desktop-native action. |
| **Value calibration** | `/api/settings/stud-tax`, `/pick-pricing`, `/api/anchor/*` | These change how the whole engine prices trades and are unreachable from web. |
| **Quick Set + pick anchors** | `/api/tiers/save`, `/api/anchor/save` | Closes 2 of the 7 board-building methods web is missing. |
| **League analysis** | `/api/league/picks`, `/free-agents`, `/portfolio` | Big-screen work. |
| **Feedback** | `POST /api/feedback` (public) | Web has no feedback path; every report today comes from mobile. |
| **Share loop** | `POST /api/share/package` + `/s/p/<id>` | Flag ON, mobile-only. |

### 3b — Multi-platform *(posture C)*

14 live routes for ESPN / MFL / Fleaflicker. Web is Sleeper-only; ESPN and MFL ship live on
mobile. **Largest addressable-audience expansion available with no backend work.** Caveat:
the ESPN and MFL flows depend on in-app WebView cookie capture, which has no clean browser
equivalent — the web flow would need the paste-credentials path, and that is a UX and security
design problem, not a port.

### 3c — Full parity *(posture C)*

- **Trade write-back.** Web currently `window.open`s a **guessed, undocumented** Sleeper URL
  (`app.js:3830`) whose own comment concedes it may break silently. Replacing it with
  `/api/trades/propose{,-espn,-mfl}` + `/api/trades/validate` closes the product loop — but it
  inherits 3b's credential-capture problem.
- **Deck intelligence** (8 flags), **Trade DNA steering**, **draft suite** (10 routes).
  Specified for completeness; these are the weakest web candidates in the backlog.

### Do not drop

A web rebuild must keep these — they are **web-only consumers today**: `/api/progress`,
`/api/players`, `/api/players/<id>`, `/api/players/<id>/profile`,
`/api/sleeper/user/<username>`, `/api/tiers/community-diff`, `/api/tiers/stability`,
`/api/trends/contrarian`, `/api/invite/impact`, `/api/league/scoring`,
`/s/tiers/<pos>/<user>`.

---

## Cross-cutting

**Branching.** This checkout is **215 commits behind `origin/main`** (v1.13.2 vs v1.15.0) and
9 ahead on an unrelated branch. Per `CLAUDE.md` §Conventions, every piece of this work branches
from a freshly fetched `origin/main` — never from here.

**Feature gates.** Phases 2 and 3 each need a `scope.md` per the root gate. P2-1 touches API
surface *and* needs new analytics events — it is explicitly across the bright line and cannot
be express-laned without a confirming operator yes. Phase 0 is bug-fix-shaped; whether it runs
express is D5.

**Evidence.** D-056's rules govern *mobile*; web has no equivalent. Until P1-2 lands, web
evidence is a written manual checklist plus before/after notes. After P1-2, it is the Playwright
+ axe + Lighthouse run, logged in `living-memory/TEST_LEDGER.md`.

**Docs to update on the way out.** `docs/api-reference.md` (7 drift items from the audit,
including a documented calculator API that does not exist), `docs/config-reference.md` (any
flag flips), `web/CLAUDE.md` (page inventory), `living-memory/CHANGELOG.md`, and this folder's
README row.

---

## Sequencing and sizing

Sizes are relative, not calendar estimates.

| Phase | Items | Size | Blocks |
|---|---|---|---|
| **0** | P0-1…P0-8 | **S** — mostly one-file fixes; P0-3 needs operator input | nothing; do first |
| **1** | P1-1…P1-6 | **M–L** — P1-1 touches 13 files, P1-2 is new infra | gates Phases 2–3 |
| **2** | P2-1…P2-3 | **M** — no backend work | nothing; Phase 1 already landed |
| **3a** | 7 items | **L** | needs Phase 1 |
| **3b/3c** | multi-platform, write-back, decks, drafts | **XL** | needs 3a + a credential-capture design |

Critical path: **P0 → P1-2 → P1-1 → P2-1**. Phases 0 and 1 are built; Phase 2 has no
backend dependency and no blocker.

---

## Risks

| Risk | Mitigation |
|---|---|
| ~~Public calculator overloads a single gunicorn worker~~ | **Moot** — no anonymous calculator (operator, 2026-08-19). Session-gated it carries mobile's existing exposure. |
| **P1-1 regresses layout across 13 pages** | Land P1-2 first if possible; otherwise page-by-page with visual before/afters. This is the riskiest single change in the plan. |
| **Concurrent sessions in this repo** | Multiple sessions run here and the checked-out branch is often stale. Re-diff against `origin/main` before each wave. |
| **ESPN/MFL credential capture has no browser equivalent** | Treat 3b as a design problem first, not a port. Do not schedule it as engineering-only. |
| **Flag flips change mobile too** | `config/features.json` is shared. Any flag this plan turns on for web must be checked against mobile behavior on `main` before flipping. |

---

## Open questions

1. **D1 — posture.** A, B, or C? Determines where Phase 3 stops.
2. **P0-3** — governing-law jurisdiction for Terms. Operator only.
3. **P0-7** — per-page call on the five dark/broken pages: fix, gate, or remove?
4. **D3** — is a bundle/minify step acceptable given the "no build step" commitment?
5. Is converting web visitors into **TestFlight testers** the primary success metric for
   Phase 2, or is standalone web usage a goal in its own right? This changes what P2-3 is.

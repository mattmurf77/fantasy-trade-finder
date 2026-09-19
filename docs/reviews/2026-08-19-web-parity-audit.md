# Web Parity Audit — 2026-08-19

> Point-in-time snapshot. Four parallel auditors: live-site browse of
> `https://fantasy-trade-finder.onrender.com/`, `web/` source audit, mobile feature
> inventory (the parity benchmark), and a backend route×client map.
>
> **Verification note:** the live browse ran against production. Source claims were
> re-checked against `origin/main`, not the working checkout (which is 215 commits
> behind, v1.13.2 vs v1.15.0). Every `web/` finding below survives on `main`.

---

## Table of Contents
- [Verdict](#verdict)
- [The structural finding](#the-structural-finding)
- [P0 — the site is actively broken](#p0--the-site-is-actively-broken)
- [P1 — parity gaps that need backend-free work](#p1--parity-gaps-that-need-backend-free-work)
- [P2 — foundation work](#p2--foundation-work)
- [Capability parity matrix](#capability-parity-matrix)
- [What web has that mobile does not](#what-web-has-that-mobile-does-not)
- [Doc drift found](#doc-drift-found)
- [Sequencing](#sequencing)

---

## Verdict

The website is a **stale fork of a mid-2026 build of the product**, not a smaller version
of the current app. It reaches roughly **35–40% of mobile's capability**, and three of its
ten pages are broken or dead when a real user reaches them. The single highest-value
finding is that **almost nothing here is blocked on backend work** — the API surface
already exists, the site is same-origin, and the gap is entirely in `web/`.

Nothing on the site says **Fleeced**. Every page, including both legal documents, still
says "Fantasy Trade Finder" — the web surface predates D-057.

---

## The structural finding

`web/css/styles.css` (4,608 lines) is linked by **exactly one page**, `index.html:10`.
The other twelve pages inline ~2,500 lines of copy-pasted CSS, each re-declaring the
Chalkline token block from scratch.

This is not a tidiness complaint — it is the mechanism that produces the site's bugs.
`--line-strong` was raised to `#59647A` in the design system because `#3D4654` measures
**2.03:1** and fails the WCAG 1.4.11 non-text contrast floor. On `origin/main` the old
value still ships in **12 places**; only `league-rankings.html:16` got the fix. Because
`--line-strong` is the border on every input and secondary button, this is a live
accessibility failure across the entire site — and `style-guide.html:14`, the live
reference, documents the wrong value, so it keeps propagating.

Until the token block has one home, every fix has to be applied thirteen times.

---

## P0 — the site is actively broken

### 1. The demo path bricks the site permanently
The only way to use the product without a Sleeper account, and the most prominent CTA
after sign-in.

`POST /api/session/demo` → 200, writes `localStorage.sleeper_user` = `demo_user_f9a1696f`.
Then `GET /api/sleeper/leagues/demo_user_f9a1696f` → **503 `sleeper_unavailable`**.
A "Choose a League" modal renders the error with **no close button, no retry, no dismiss**
— Escape and backdrop clicks do nothing, and the Log out control sits behind the overlay.

Sleeper is not down: `/api/sleeper/leagues/1234567890` returns `200 []`. The demo flow
feeds a synthetic non-numeric user id into the real Sleeper lookup.

**The trap persists across visits** — the demo user is in `localStorage`, so every
subsequent load of `/` re-enters the same dead modal. Recovery requires clearing site data
or calling `logout()` from the console.

### 2. `ranking-method.html` is a mockup deployed to production
Its only function `console.log`s and returns; the real navigation is commented out
(`ranking-method.html:245`). All three cards highlight and go nowhere. The routes it names
(`/rank`, `/rankings`, `/tiers`) all 404. Nothing links to it. `web/CLAUDE.md:16` lists it
as "Shipped: yes" — that is wrong.

### 3. Terms of Use ships an unfilled legal placeholder
`terms.html:157`: *"governed by the laws of **[STATE]**"* — on a live, linked legal
document that is also an App Store submission artifact.

Both legal docs additionally direct users to "the in-app feedback button, or the support
contact listed on our App Store page." The website has no feedback button and there is no
App Store listing. **Web visitors have no route to a data deletion or access request.**

### 4. Mobile: the primary CTA is clipped
At 375×812, `.cb-connect-wrap` and siblings compute to a fixed 380px box
(`styles.css:2808`) in a 375px viewport, `left:20 → right:400`. `scrollWidth ===
clientWidth === 375`, so there is no scroll to recover it — the right edge of
"Connect with Sleeper →" is simply cut off.

### 5. Web analytics emits zero events
`analytics.client_events` and `analytics.ingest` are both true. `events.js` loads.
`app.js:326` calls `FTFTrack('app_opened')` unconditionally. Yet after an 18-second visit,
`ftf.deviceId` is null, the queue is empty, and no ingest request fires.

**Confirmed load-order race at source:** `_loadFeatureFlags()` is fire-and-forget at
`app.js:34`; `boot()` runs synchronously at `app.js:6234`. `track()` opens with
`if (!flagOn()) return;` reading `window.FTF_FLAGS`, still `{}` at that point. The comment
at `app.js:33` — *"it resolves before most UI code runs"* — is an assumption, not a
guarantee.

Separately the site has only **three** track call sites. `events.js:18` names
`signin_attempted`, `signin_succeeded`, and `experiment_exposed` as funnel-critical;
web emits none of them. **The web funnel is blind at exactly the step the SDK protects.**

### 6. Broken or dark pages reachable in prod
- `profile.html` — handle parser broken; requests `/api/profile/%2Fprofile.html` → 404,
  title renders as `@/profile.html`. Flag off, orphaned.
- `league-rankings.html` — linked from primary nav, backing flag `league.power_rankings`
  is false, returns 401 `session_expired`, ships a dimmed "Redraft (soon)" tab.
- `player.html` — flag off; fires no requests at all.
- `style-guide.html` — internal design reference live on prod, citing internal repo paths.
- `admin/analytics.html` — 200 at a guessable path (data is `CRON_SECRET`-gated; the page
  shell, tab taxonomy, and endpoint vocabulary are not).
- Unknown paths return raw JSON `{"error":"not_found"}` — there is no HTML 404 page.

---

## P1 — parity gaps that need backend-free work

Every item here calls an endpoint that already exists and already works. The site is
same-origin (`Flask(static_folder=web/, static_url_path="")`, `server.py:2009`), so there
is no CORS or infra work.

| # | Gap | Endpoint (already live) | Note |
|---|---|---|---|
| 1 | **Manual trade calculator** | `POST /api/trade/evaluate` | **Public, no auth.** Returns fairness verdict, eveners, itemized adjustments. Paired with `/api/trade/values` (already used by web) this is a KTC-class public tool with zero backend work. Mobile-only today. |
| 2 | **Market movers** | `GET /api/market/movers` | Fully public, flag ON, no session. Ready-made SEO surface. |
| 3 | **Account sign-in** | `/api/auth/apple`, `/api/account`, `/api/account/link-sleeper`, `/api/session/signout` | Web has **no accounts at all** — Sleeper-username-only. No cross-device continuity, no verified sessions, no sign-out. Web users permanently sit on the grace side of the P1/P2.5 identity gates. |
| 4 | **ESPN / MFL / Fleaflicker linking** | 14 routes | Web is Sleeper-only. ESPN and MFL are flagged live on mobile. Largest addressable-audience expansion available. |
| 5 | **Sending real trades** | `/api/trades/propose{,-espn,-mfl}`, `/api/trades/validate` | Web "sends" a trade by `window.open`-ing a **guessed, undocumented** Sleeper deep-link URL (`app.js:3830`); the code comment concedes it may break silently. This is the product's differentiating end of the loop. |
| 6 | **Draft suite** | 10 routes, all flags ON | Draft Room, mock draft, pick assignment, live pick recording. Entirely absent from web. |
| 7 | **Ranking import** | `/api/rankings/import-match`, `/import-apply` | Paste a board from anywhere. Natural web capability; mobile-only. |
| 8 | **Feedback** | `POST /api/feedback` (public) | Web has no feedback path — every tester report today comes from mobile. |
| 9 | **Value calibration** | `/api/settings/stud-tax`, `/pick-pricing`, `/api/anchor/*` | These change how the whole engine prices trades. Not reachable from web. |
| 10 | **Share loop** | `POST /api/share/package` + `/s/p/<id>` | Flag ON, mobile-only. |

---

## P2 — foundation work

**SEO is absent sitewide.** Across all 10 pages: zero `meta description`, zero `og:`,
zero Twitter cards, zero canonical, zero JSON-LD, no favicon link. `/robots.txt` → 404.
`/sitemap.xml` → 404. The landing page has zero `<img>` elements and exactly two meta tags.

Worst on `profile.html`, the public viral surface — it is 100% client-rendered, so an
unfurler sees `Loading profile…`. **The backend already does this correctly** for
`/s/tiers/…` and `/s/trade/…` (server-rendered OG wrappers with generated `/og/*.png`
cards, `server.py:17204`). The pattern exists and just was not extended to `/u/`.

**Accessibility.** `index.html` — the entire application — has no `<main>`, no `<nav>`,
one landmark total, and zero headings below `<h1>`; every section title is a styled `div`.
`positional-tiers.html` and `league-rankings.html` have no headings at all. All four
`<img>` tags use `alt=""` on user avatars whose adjacent text is the only name carrier.
Tap targets measured under 44px: CTA 42, sub-tabs 30, position chips 24, footer links 16.

**No build step.** 266 KB unminified `app.js`, 133 KB CSS, 131 KB of inline-everything on
`positional-tiers.html`, all served `Cache-Control: no-cache` — nothing caches between
visits. Plus a hard third-party dependency on Google Fonts on every load.

**Dead weight in `app.js`.** ~200 lines of debug-drawer IIFE whose DOM targets
(`#log-body`, `#log-count`) do not exist in `index.html`, with **90 no-op call sites** on
`main`, plus an unreachable `fetchBackend()` that calls the CRON-gated `/api/debug/log` —
so the public bundle advertises an operator endpoint.

**Stale hardcoded data renders before the API lands.** `positional-tiers.html:1576-1631`
ships a 55-player `SAMPLE_PLAYERS` roster with **2024-era teams** (Josh Jacobs on GB,
Aaron Jones on MIN, Javonte Williams on DEN) that is bucketed into tier lanes during module
init. Users on slow connections see wrong teams and wrong values. Separately,
`TIER_CONFIG` bakes in all 64 Elo bands with a comment demanding lockstep with the API and
no test enforcing it.

**Design-system drift beyond the contrast bug:** three emoji-as-icon violations
(`positional-tiers.html:1546` 🏆, `app.js:676` ⚡, `app.js:711` ⚠️); the landing
`.cb-eyebrow` uses `#22C55E`, the POS/RB **data-encoding** green, as chrome — which the
site's own style guide explicitly forbids; the landing `<h1>` uses Archivo where every
other page correctly uses Barlow Condensed; an off-palette `rgba(79,124,255,…)` blue-violet
at `styles.css:4158`.

**17 of 23 web feature flags are off** — demo mode, smart start, trade queue, player
profiles, league rankings, and all three mobile-polish patches are shipped code that does
not run. Note these are not "not ready": the entire onboarding-v2 wave that is dark here is
**live on `main` for mobile**.

---

## Capability parity matrix

Scored against the 7 capabilities that *are* the product.

| Capability | Mobile | Web | Gap |
|---|---|---|---|
| Personal Elo board | 7 methods | 5 (trios, tiers, manual, rookie, + partial) | No Quick Set, no pick anchors |
| Mutual-gain discovery | full, 3 finder modes + DNA steering | generate + swipe only | No DNA, no lanes, no intent modes |
| Mutual-match inbox | full + awaiting segment | matches list only | No awaiting, no undo |
| **Write trade to platform** | Sleeper + ESPN + MFL, validated | **deep-link guess** | **Largest single gap** |
| Steering the search | DNA, untouchables, per-asset swap | fairness slider + pins | Mostly absent |
| Deck intelligence | 8 flags, learns in-session | none | Absent |
| Platform connectivity | 4 platforms, read + write | Sleeper only | 3 platforms absent |

---

## What web has that mobile does not

A web rebuild must not drop these — they are web-only consumers today:
`/api/progress`, `/api/players`, `/api/players/<id>`, `/api/players/<id>/profile`,
`/api/sleeper/user/<username>`, `/api/tiers/community-diff`, `/api/tiers/stability`,
`/api/trends/contrarian`, `/api/invite/impact`, `/api/league/scoring`,
`/s/tiers/<pos>/<user>`.

---

## Doc drift found

| # | Drift | Evidence |
|---|---|---|
| D1 | `docs/api-reference.md:288` documents `POST /api/calc/score` + `GET /api/calc/values` behind flag `calc.open_calculator`, powering `web/calculator.html`. **None of the three exist** in `server.py`, `config/features.json`, or `web/`. The real calculator route is `/api/trade/evaluate`. | zero grep hits |
| D2 | `docs/api-reference.md:5` says auth is a session cookie. It is an `X-Session-Token` **header**; there are no cookies anywhere. | `server.py:2276` |
| D3 | 9 routes exist in code but not in the doc (4 admin experiment routes, reseed-layers, admin entitlements, `/`, `/privacy`, `/terms`, AASA) | — |
| D4 | `CLAUDE.md` says 182 routes; actual is 180 registrations / 176 unique paths | — |
| D5 | `mobile/src/api/CLAUDE.md:19` and `state/CLAUDE.md:8` say flags come from `/api/flags`; the real route is `/api/feature-flags` | `server.py:17723` |
| D6 | `league.power_rankings` is false in `config/features.json:140` but **no code reads it** — the route is live and unflagged | zero `is_enabled` hits |
| D7 | `web/CLAUDE.md:16` lists `ranking-method.html` as shipped; it is a dead stub | `ranking-method.html:245` |

---

## Sequencing

**Stop the bleeding (hours).** Fix or remove the demo path; delete `ranking-method.html`;
fill `[STATE]`; fix the 380px CTA clip; await `_loadFeatureFlags()` before `boot()`; add a
web contact route for data requests; pull `style-guide.html` and gate
`admin/analytics.html` from prod.

**Fix the foundation (days).** One shared token block — extract to a single stylesheet all
pages link, then fix `--line-strong` once. Add SEO metadata + robots + sitemap; extend the
existing server-rendered OG pattern to `/u/`. Add landmarks and a heading outline. Delete
the dead debug drawer and the stale `SAMPLE_PLAYERS`. Rename to Fleeced.

**Close the parity gaps (weeks), highest leverage first.**
1. Public trade calculator on `/api/trade/evaluate` — biggest capability-per-effort ratio
   on the board, and the natural SEO landing page. **Prerequisite:** add a rate limit and
   response cache first. There is no global rate limiter (only `/api/events` and
   `/api/share/package` self-limit), and this runs the full package math on a **single
   gunicorn worker** on Render.
2. Market movers page — public, cache-friendly, SEO.
3. Account sign-in — unblocks verified sessions and cross-device.
4. ESPN + MFL linking — largest audience expansion, zero backend work.
5. Real trade write-back — replaces the deep-link guess, closes the product loop.

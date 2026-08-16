> Research capture 2026-08-15, public-information-only web research agent (no logins, no paywall bypass). Part of the Connected Rankings premium-rank-sets addendum.

Research complete. Closing the browser preview and compiling.

Compiled report below.

---

# Dynasty Nerds / DynastyGM Research Report

**Scope note:** All facts gathered from public pages, the public rankings-widget JS, the SPA's public JS bundle and `config.js`. No login, no paywall bypass. The whole `dynastynerds.com` domain 403s server-side automated fetches (WebFetch/curl), so pages were read via a real browser pane. Prior session's findings **confirmed and extended**.

**Important disambiguation:** `api.fantasynerds.com` ("Fantasy Nerds API") that surfaces in searches is a **different company** (Fantasy Nerds), not Dynasty Nerds. Do not conflate.

## 1. Rank sets & update cadence

Confirmed from the public rankings widget's data object (`window.DR_DATA`) and UI:

- **Two value systems:** Dynasty (`PPR`, `SFLEX`, `STD`, `SFLEXTEP`) and **Contender** (`C_PPR`, `C_SFLEX`, `C_STD`, `C_SFLEXTEP`). Contender arrays are empty on the public page (Contender is Premium-only — pricing table lists "Contender Rankings" as Premium ✓).
- **Formats:** PPR (1QB PPR), **SF** (Superflex), **STD** (Standard), **SF TEP** (Superflex TE Premium). These four exactly.
- **Analyst variants:** Ranker dropdown = **Consensus + Rich + Matt + Garret** ("4 expert rankers"; full names Rich Dotson, Matt O'Hara, Garret Price). Per-analyst tiers/comments supported ("not all rankers use these").
- **Player counts (public):** 338 PPR / 335 SFLEX / 338 STD / 334 SFLEXTEP; marketed as "300+ players." Public page shows only top ~20–25 (free preview); full list is Premium.
- **Rookie ranks:** "Rookies Only" toggle in the widget; nav has "2026 Rookies PPR" and "2026 Rookies Superflex." Rookie flag driven by `draftYear >= 2026`.
- **Values are numeric** (e.g., Bijan Robinson 10,256; scaled ~0–10,000+).
- **Cadence:** Header says "Updated weekly." Ranker dropdown showed **staggered per-analyst dates** (Rich Aug 11, Matt Aug 10, Garret Aug 9, 2026) — individual rankers update on their own near-daily rolling schedule; consensus reflects latest. Page stamp: "Rankings updated Aug 11, 2026."

## 2. Export surface for subscribers

- **Yes — CSV export exists** and is a **sanctioned Premium subscriber feature** on the public marketing rankings widget (`dynasty-nerds-dynasty-rankings` WP plugin, v1.26.1). Button class `dr-export-btn` → `drExportCSV()`.
- Gated **client-side** on `IS_PREMIUM`; non-premium users get a "Go Premium" popup ("Export full dynasty rankings to CSV with values, trends & more.").
- CSV columns: `Rank, Player, Team, Position, Age, Exp, Value[, Trend, PPG], Pos Rank`. Filename pattern `dynasty_rankings_[contender_]<scoring>[_<pos>][_rookies].csv`. Built via in-browser Blob (no server round-trip).
- **This is the cleanest legitimate import path for your use case:** a paying subscriber exports their own CSV and uploads it to your app — no automated DN login required.
- No CSV/print/sheets export surface was found inside the `app.dynastynerds.com` SPA itself (its `/api/gm/values/*` endpoints are for editing custom values, not bulk export). FAQ/help/subscription pages: no other documented export. **Unverified** whether the mobile app has any share/export.

## 3. API surface

- **No public/documented API.** Confirmed.
- Backend hosts (from `app.dynastynerds.com/config.js`): `PROD_API_URL` / `SESSION_URL` = **`https://gm3.dynastynerds.com`**; `AUTH_SERVICE_URL` = **`https://members.dynastynerds.com`**; login subdomain `gm2`. SPA is **Expo / React-Native-Web** (EAS projectId `b26e4af5-0ef9-44cd-a74c-fe8df67fabb4`).
- Endpoint paths extracted from the public JS bundle (all under `gm3.dynastynerds.com`): `/auth/callback`, `/api/gm/init-2`, `/api/gm/init-mini`, `/api/gm/member-info`, `/api/gm/mini-member-info`, `/api/gm/values`, `/api/gm/values/{create,update,delete,adjust,copy,publish,finalize,sort-early-mid-late}`, `/api/gm/valueType/`, `/api/gm/leagues/refresh/`, `/api/gm/accounts/{refresh,remove,add-account,toggle-league}`, `/api/gm/trades`, `/api/gm/trades/votes`, `/api/gm/mock/*`, `/api/gm/optimizer`, `/api/gm/player-card/`, `/api/gm/player-stats`, `/api/gm/iap-subscription`, `/api/checkTrade`, `/players/values`, `/players/valueSet`, `/players/data-hub`, `/players/shares`, `/players/free-agents`, `/rankings`, `/api/stats`. These are private/undocumented, subject to change, and gated by member permissions in the JWT.
- No public GitHub repo, developer docs, or published network captures for DN's backend were found.

## 4. Auth mechanism (SPA)

- **OAuth authorization-code flow with PKCE + CSRF state.** Flow: app opens `PROD_LOGIN_URL` (`https://www.dynastynerds.com/gm-app-log-in/?subdomain=gm2&path=/app-login`) → returns `code` + `state` → app verifies `state` (stored under a CSRF key; "CSRF state mismatch" → `/login`) → exchanges at `${PROD_API_URL}/auth/callback?code=…&redirect_uri=<origin>/callback&code_verifier=…` via `fetch(..., {credentials:'include'})` → receives a **JWT** → persisted client-side under `JWT_STATE_KEY` (AsyncStorage/localStorage) → JWT carries `permissions`. Auth service = `members.dynastynerds.com`.
- Underlying membership store is **WordPress + WooCommerce** (bundle loads WooCommerce, order-attribution, sourcebuster; `dn_reg_nonce`).
- **Caveat on the prior "bearer token" claim:** it **is** a JWT, but no literal `Bearer` string appears in the web bundle and the token exchange uses cookies (`credentials:'include'`). Whether API calls attach the JWT as `Authorization: Bearer` vs a session cookie is **unverified** from public artifacts (would require an authenticated capture, which I did not do).

## 5. Login mechanism

- **Email/username + password only** (WordPress accounts). Sign-in form fields: "email or username" + "password"; registration = email + password + confirm (min 8 chars).
- **No social/OAuth-provider login** (no Google/Apple/Facebook sign-in). The only "Google" on the page is the Google Play store badge. (The OAuth/PKCE in §4 is DN's own app↔backend handshake, not third-party social login.)

## 6. Terms of Service — relevant clauses

From **Purchase Terms of Service** (last updated March 14, 2026; entity "Dynasty Media, LLC dba Dynasty Nerds"):

- Account sharing: **"Account credentials may not be shared with or transferred to any other person."** and **"membership is for your personal use only."** Company **"reserves the right to terminate accounts found to be sharing access."**
- IP / rankings ownership: materials "including... **data, rankings**, and software" are Company property; grant is a **"limited, non-exclusive, non-transferable license... for your personal, non-commercial use only."**
- Privacy Policy/Terms page adds: **"may not use the Service for any other purpose without the prior written consent"** of the Company.
- Governing law Ohio; binding AAA arbitration.
- **No explicit anti-scraping / bot / crawler / reverse-engineering / no-competing-product clause** was found in either the Purchase ToS or the Privacy Policy/Terms page. **Unverified** whether such language exists in any other document. The operative constraints for your use case are the **personal, non-commercial license + no-credential-sharing** clauses — a "we log in and fetch on your behalf" model directly implicates both.

## 7. Licensing precedent with third-party tools

- **Sleeper Mini integration:** DN integrated with Sleeper's mini-app for league linking (also reflected by `/api/gm/init-mini`, `/verify-mini` in the bundle). This is inbound league-import, **not** DN licensing out its values.
- League-sync partners consumed by DN: Sleeper, ESPN, FFPC, MFL, Fleaflicker.
- **No evidence found** of Dynasty Nerds licensing or syndicating its rankings/values **into** third-party trade tools/apps. **Unverified / none found** — treat as "no known precedent."

## 8. Subscription price

- **One consolidated tier, "Dynasty Nerds Premium":** **$69.99/year** ($5.83/mo) or **$6.99/month**. Annual saves $13.89 vs monthly.
- Free tier exists (preview-only rankings, 1 league sync, 3 trades/day).
- 7-day full refund; cancel anytime. Legacy NerdHerd/DynastyGM/Combo tiers were merged into this single plan (legacy subscribers keep locked-in rates). Payment via Stripe (cards, Apple Pay, Google Pay); in-app via App Store/Play. Marketing claims 11,000+ premium members, 4.7★. 2026 Rookie Guide ($19.99) bundled free.

---

**Key takeaway for the product decision:** The lowest-friction, ToS-safest import path is the **existing Premium CSV export** on the public rankings widget (subscriber downloads their own file → uploads to your board). An automated "log into DN, we fetch for you" flow runs into (a) no public API, (b) a private OAuth/PKCE+JWT handshake against `members.dynastynerds.com`/`gm3.dynastynerds.com` that would have to be reverse-engineered, and (c) ToS clauses restricting the license to **personal, non-commercial** use and **prohibiting credential sharing/transfer** — the central legal risk, even though no explicit "no-scraping" clause was located.

**Cited URLs:** dynastynerds.com/plans-and-pricing/ · dynastynerds.com/dynasty-rankings/ · dynastynerds.com/purchase-terms-of-service/ · dynastynerds.com/privacy-policy/ · dynastynerds.com/sign-in/ · app.dynastynerds.com/ · app.dynastynerds.com/config.js · app.dynastynerds.com/_expo/static/js/web/index-*.js · dynastynerds.com/wp-content/plugins/dynasty-nerds-dynasty-rankings/assets/js/dynasty-rankings-widget.js · support.dynastynerds.com/article/82 and /article/80 (403 to automation; content corroborated via marketing pages).
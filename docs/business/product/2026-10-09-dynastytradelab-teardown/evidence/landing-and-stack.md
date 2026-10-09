# Dynasty Trade Lab — landing page + technical stack (observed 2026-10-09)

## Landing page (dynastytradelab.com, logged out)

- Headline: "Dynasty Fantasy Football Trade Analyzer Built for Your Roster." Sub: "Your Sleeper or Fantrax roster, instantly imported." CTAs: "Generate a trade free", "Sign Up", "Connect your account →" (Sleeper + Fantrax logos).
- Nav: Buy Credits · Dashboard · Rankings · My Account · [Generate Trades] (primary, yellow).
- Three numbered features: 01 Three-Way Trade Finder ("Analyze the most complex three-team dynasty fantasy football trades before you accept"), 02 Lab Analyst ("Chat with AI about dynasty fantasy football player valuations, team needs, and trade recommendations"), 03 Dynasty Trade Calculator ("instant AI trade grades built around your real roster and league settings — not a static dynasty trade value chart").
- Value ticker (their scale, same day): Gibbs 10,760 · Bijan 10,592 · JSN 9,628 · Chase 8,052 · ARSB 7,339 · Nacua 7,271 · K. Walker 7,179 · Lamb 6,855 · Bowers 6,743 · Jeanty 6,704 · J. Love 6,423 · J. Taylor 6,179 · McBride 5,909 · Jefferson 5,823 · J. Allen 5,613 …
- Positioning copy: "true dynasty-specific logic with full support for Superflex, 2QB, 1QB, and PPR formats — built to find realistic, mutually beneficial dynasty trades that actually work, not a one-size-fits-all trade value chart."
- **Pricing (credits, one-off, not subscription):** STARTER 10 credits $4.99 ($0.50/credit) · STANDARD 40 credits $17.99 ($0.45) · SEASON 75 credits $29.99 ($0.40). "5 free credits, no commitment." FAQ accordion: what is a dynasty trade calculator / Superflex & 2QB support / how are values calculated / free to try.
- Visual: dark navy + yellow, Druk Wide display font + Google Sans Flex, phone mockups of a "Teams" roster list and a two-manager trade card with "Why it works" copy.

## Technical stack (from page source, network log, console)

- **WordPress 7.1.3** (meta generator) + **WooCommerce 11.2.0** (credit packs are WooCommerce products: add-to-cart, order-attribution, sourcebuster scripts) + Jetpack (stats.wp.com, WooCommerce Analytics) + WP Rocket caching + Cloudflare (insights beacon, `/cdn-cgi/rum`). Alpine.js 3.13.10 for front-end state.
- Product logic is a custom plugin `wp-content/plugins/dynasty-trade-lab/` (`dtl-frontend.js`, ~91 KB minified; `dtl-frontend.css`) plus a custom theme `wp-content/themes/dynasty-trade-lab/` (Vite build `app-*.js`, ~273 KB).
- **Backend API:** WordPress REST namespace `https://dynastytradelab.com/wp-json/dtl/v1/`, authenticated by the logged-in WP cookie + `X-WP-Nonce` (`window.dtlConfig = {restUrl, nonce}`). Routes referenced by the front-end bundle: `me`, `me/sleeper` (DELETE to disconnect), `me/fantrax`, `values?numQbs=`, `me/team-needs?league_id=`, `me/projections?…`, `me/roster-email`, `generate`, `generate-league`, `lab-analyst`. 41 `fetch(` call sites; no websockets/SSE.
- Front-end modules exposed as globals: `dtlGenerator`, `dtlSleeperConnect`, `dtlMyRoster`, `dtlTeamNeeds`, `dtlProjections`, `dtlLeaguePicker`, `dtlTeamStatus`, `dtlStockMovers`, `dtlFreeAgentStock`, `dtlLabAnalyst`, `dtlLabChatWidget`, `dtlSetLeague`, `dtlOpenLabChat`/`dtlCloseLabChat`, `dtlAjax`.
- Analytics: Google Tag Manager (GTM-5TNGJCBC) + GA4 (G-MEXT695GXY; the `/g/collect` hit returned 503 on our load), Jetpack stats, Cloudflare RUM.
- **Console errors on the landing page (logged out):** `SyntaxError: Unexpected end of input` in the WP Rocket-minified Alpine.js bundle, and `TypeError: n[e] is not a function` in Jetpack's woocommerce-analytics-client — two uncaught exceptions on every landing load.
- No native app detected from the site (phone mockups are of the responsive web app). Sleeper connect is username-based (no OAuth); Fantrax integration present (169 references in the bundle).

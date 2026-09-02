# web/ — Notes for Claude

Vanilla HTML/CSS/JS, **no build step, no framework, no package.json**. One `.html` file
per page; shared logic in `js/`, shared tokens/styles in `css/styles.css`. Served by the
Flask backend (`run.py`), so a page is live the moment the file exists.

## Pages

| File | Shipped? | What it is |
|---|---|---|
| `index.html` | yes | Single-page app entry — Dynasty Rankings. Only page that links out to `faq`, `league-rankings`, `positional-tiers` |
| `league-rankings.html` | yes | Per-league ranking view. Dark — `league.power_rankings` is false, so the route 401s and the nav link is hidden |
| `positional-tiers.html` | yes | Positional tier boards |
| `player.html` | yes | Player profile. Dark — `players.profile_pages` is false, so it renders a sign-in prompt and fires no requests |
| `profile.html` | yes | Public profile, served at `/u/<username>`. Dark — `profiles.public_pages` is false |
| `ranking-method.html` | yes | "Set your rankings" explainer. **Not linked from any web page** — it is reached from the mobile app (`mobile/src/screens/TradesScreen.tsx` `readMoreUrl`), so do not delete it. Static content only; its tiles were fake controls until 2026-08-19 |
| `faq.html` | yes | FAQ |
| `robots.txt` / `sitemap.xml` | yes | Crawler directives. Templates, operator pages and share landings are `Disallow`-ed |
| `contact.html` | yes | Contact + data requests. Posts to the public `POST /api/feedback` (`screen=web-contact`, or `web-contact-data-request` with a `[DATA REQUEST]` text prefix). The only route a web visitor has to a deletion/access request — both legal docs link here |
| `404.html` | yes | HTML not-found page. Served by the `404` errorhandler in `backend/server.py` for browser navigation; `/api/*` and `/og/*` keep returning JSON |
| `privacy.html` / `terms.html` | yes | Legal pages (App Store / Play listing links point here) |
| `style-guide.html` | reference | **Chalkline design-system reference — check it before styling anything.** 404s in deployed envs since 2026-08-19 (`_PROD_BLOCKED_STATIC` in `backend/server.py`); available in local dev. ⚠️ its `--line-strong` is the stale `#3D4654`, not the corrected `#59647A` — see plan item P1-1 |
| `admin/analytics.html` | operator-only | Analytics dashboard; not linked from any public page |
| `color-lab.html`, `color-lab-2.html` | no (404 in prod) | Frozen palette-exploration scratch from the Chalkline brand pass. Historical — do not treat as current tokens |

## Tokens live in ONE file

`web/css/tokens.css` is the single source for Chalkline design tokens. **Every page
links it; no page may re-declare them.** Until 2026-08-19 the `:root` block was
copy-pasted into 12 files and they drifted — `--line-strong` was corrected to
`#59647A` on 2026-07-19 for the WCAG 1.4.11 non-text floor (`#3D4654` is 2.03:1)
and only one of the twelve copies got it.

`qa/web/check_web_structure.py` fails CI if a second file starts defining them.

## The web CI gate

`python3 qa/web/check_web_structure.py` — 161 structural checks over the shipped
HTML/CSS/JS: design tokens, emoji-as-icons, radii, fonts, SEO metadata, a11y
landmarks/headings, and hygiene. No browser, no server, no dependencies; runs in
well under a second. Wired as the `web-structure` job in `.github/workflows/ci.yml`.
**Before 2026-08-19 nothing in CI touched `web/` at all.**

Exceptions are explicit: `qa:allow-emoji` on a line (and the line after it) opts out
of the emoji check — `git grep qa:allow-emoji` lists every one.

## Shared code

| File | Size | Role |
|---|---|---|
| `js/app.js` | ~6.2k lines | Everything: fetch layer, rendering, page routing |
| `js/events.js` | ~175 lines | Analytics emission. Events must match `backend/analytics_taxonomy.py`; gated on the `analytics.client_events` flag |
| `css/styles.css` | ~4.6k lines | Chalkline tokens + all page styles |

## Rules

- **UI tokens:** root `CLAUDE.md` §Conventions "UI rules" + [`docs/design/design-system.md`](../docs/design/design-system.md) + [`docs/design/components.md`](../docs/design/components.md). Never emoji-as-icons, gradients, blur, system font stacks, radius >8px.
- **Doc triggers:** new page → [`docs/CLAUDE.md`](../docs/CLAUDE.md); any UI change → `docs/design/`; new/changed route consumed here → [`docs/api-reference.md`](../docs/api-reference.md).
- **No automated web tests.** Verify by running `python run.py` and loading `http://127.0.0.1:5000/`.
- Web screen captures are not part of the screen library yet — see [`screens/web/README.md`](../screens/web/README.md).

# Feature Scope — Share link previews (C6)

<!--
MANDATORY for every feature or change that adds/modifies user-visible behavior,
data collection, schema, or API surface — regardless of which pipeline the work
enters through (feedback item, NEXT.md queue, staged-work, direct ask).

Copy this template into the feature's home:
  - feedback items → docs/feedback/items/<id>-<slug>/scope.md
  - planned initiatives → docs/plans/<initiative>/scope.md
  - anything else → docs/plans/<short-name>/scope.md

RULE: every section is answered or explicitly WAIVED with a reason.
Silence is not a waiver. Waivers are surfaced to the operator before build starts.

EXPRESS LANE: the operator may exempt a change from this template entirely at
flow start ("quick fix", "just ship it") — see CLAUDE.md §Conventions "Feature
gates" → "Rigor is an operator decision". No scope.md then; a one-line
TEST_LEDGER note replaces it. Operator-declared only, never agent-selected.
-->

**Date:** 2026-10-27
**Entry point:** direct ask — Product pre-launch review, item C6 (task `c6-eng-backend-1`, manager `league-eng`)
**Builder:** eng-backend worker `c6-eng-backend-1`, branch `fix/share-link-previews`
**Operator sign-off on waivers:** pending — the one waiver (§1 analytics) was set by league-eng in the task brief; league-eng surfaces it to the operator

**Problem.** Shared links (`/s/*`) did not unfurl into previews in iMessage, Slack, X or
Discord, for two reasons:

1. `og:image` / `twitter:image` were root-relative (`/og/p/<id>.png`). Unfurlers need an
   absolute URL.
2. `web/robots.txt` had `Disallow: /s/` and `Disallow: /og/`. Unfurlers that honour
   robots.txt (Twitterbot, Slackbot) would not fetch the page or the card image.

**Change.**

- `og:image` and `twitter:image` in `_share_html` are absolute. The origin is `https://` +
  `request.host` when `_IS_PROD_ENV` (Render terminates TLS and there is no ProxyFix, so
  `request.scheme` reads `http` there), otherwise `request.scheme + "://" + request.host`.
  `X-Forwarded-*` headers are not consulted. The callers still pass relative paths, and the
  visible `<img src>` stays relative.
- The pages are kept out of search indexes: `<meta name="robots" content="noindex">` and an
  `X-Robots-Tag: noindex` header on every `/s/*` HTML response, and the same header on
  every `/og/*.png` response. `Cache-Control` is unchanged.
- `web/robots.txt` no longer disallows `/s/` or `/og/`. A comment says why. Every other rule
  is byte-identical.

**Out of scope (unchanged).** No route, status code, flag, flag gate, schema, env var,
analytics event or mobile change. `POST /api/share/package` still returns relative
`url` / `og_image`: that is an API contract (pinned by `test_share_package.py`).

---

## 1. Analytics scope

- [ ] **(a) New events specced:** none.
- [ ] **(b) Existing events cover it:** not claimed.
- [x] **(c) WAIVED — no analytics needed because:** this is a server-rendered metadata and
      crawler-directive fix. Nothing new happens in a client, and an unfurler fetching a page
      or card is not a user action we can or should attribute. Set by league-eng in the brief.

## 2. Schema & flag scope

- New/changed tables or columns: none
- New/changed feature flags: none. `growth.share_landing` and `growth.tier_board_share`
  keep their gates exactly as before (the `/s/tiers` and `/og/tiers` routes still 404 while
  `growth.tier_board_share` is dark, per D-P1-12).
- New env vars / `model_config` keys: none. Rollback lever: revert the commit. No knob is
  warranted; the change is metadata and headers only.

## 3. Evidence scope

- [ ] **Structural guard:** n/a — no mobile change.
- [x] **Unit tests:** new `backend/tests/test_share_link_previews.py` (18 cases). Each
      test was sabotaged (code broken, test seen red, code restored):
  - **2026-10-31:** #511 is now stacked on #362 @ `49a2eeb0` (merge `2152e0e5`), with
    `_share_html`'s `noindex` parameter dropped. Trade links are token-only, so their
    coverage moved to section 4 below.
  - `test_og_and_twitter_image_are_absolute` (`/s/p/<id>` ×
    local/prod): both tags equal `http://localhost/og/...` locally and
    `https://localhost/og/...` with `_IS_PROD_ENV` patched True, path unchanged.
  - `test_share_pages_are_noindex` (`/s/p`, `/s/tiers`): robots meta is
    `noindex`, `X-Robots-Tag: noindex`, `Cache-Control` unchanged.
  - `test_og_cards_carry_noindex_header` (`/og/p`, `/og/tiers`, stub
    renderer): `X-Robots-Tag: noindex`, `Cache-Control` unchanged.
  - Section 4, trade links (tokens minted with `test_trade_share_tokens.py`'s `env`
    fixture and its `_mint` / `_add_match` helpers):
    - `test_live_trade_page_is_absolute_and_noindex` (local/prod): `og:image` and
      `twitter:image` equal `<origin>/og/trade/<token>.png`, the robots noindex meta
      appears exactly once, `X-Robots-Tag: noindex`; the visible `<img>` stays relative.
    - `test_expired_trade_page_is_absolute_and_noindex` (a shared match's numeric id and
      an unknown token, × local/prod): the same three properties, with
      `<origin>/og/trade/expired.png`.
    - `test_trade_cards_carry_noindex_header` (live token, numeric id, unknown token,
      `expired`; real renderer): `X-Robots-Tag: noindex`, `Cache-Control` unchanged, and
      only the live token gets a non-expired card.
  - Sabotage, 2026-10-31: duplicating the robots meta in `_share_html` turns only the
    section 4 page tests red (6), because `test_share_pages_are_noindex` reads the first
    robots meta and does not pin the count.
  - `test_robots_txt_does_not_block_share_paths`: no `Disallow` rule prefixes an `/s/`
    or `/og/` path.
  - `test_robots_txt_keeps_other_disallows`: `/admin/`, `/style-guide.html`,
    `/color-lab.html`, `/color-lab-2.html`, `/calculator.html`,
    `/league-rankings.html`, `/player.html`, `/profile.html`, `/404.html` are all still
    disallowed.
  - The API contract (relative `url` / `og_image` from `POST /api/share/package`) stays
    pinned by the existing `test_share_package.py::test_happy_path_creates_row_and_serves_landing`
    (green).
  - Also green: `test_share_package.py`, `test_tier_share_routes.py`,
    `test_universal_links.py`, and `qa/web/check_web_structure.py` (196/196).
- [x] **Code-walk proof** (`backend/server.py` at the branch tip):
  - `_absolute_url` (:30323) returns non-`/` input unchanged and otherwise prefixes
    `scheme://request.host`, with the scheme forced to `https` when `_IS_PROD_ENV`
    (:30333; flag defined at :29259).
  - `_share_html` computes `og_image_url = _absolute_url(image_url)` (:30353) and uses it
    for `og:image` (:30366) and `twitter:image` (:30372). `<img src>` (:30389) still uses
    the relative `image_url`. The robots meta is at :30361 and the header at :30400.
  - All three landings route through `_share_html`: `/s/tiers` (:30405), `/s/trade`
    (:30435) and `/s/p` (:30533). Every PNG from `/og/tiers` (:30279), `/og/trade`
    (:30310) and `/og/p` (:30556) goes through `_png_response` (:30267), which sets the
    header at :30274. `_png_response` has no other caller.
- [x] **Manual operator checklist** (runs after deploy; this is the only proof the real
      unfurlers accept the page):
  1. In the app, share a trade package so you have a `https://fantasy-trade-finder.onrender.com/s/p/<id>` link.
  2. Paste the link into an iMessage thread (do not send it yet). Expected: a preview card
     appears with the trade-card image and the title "Trade Package".
  3. Paste the same link into a Slack message (or an X post draft). Expected: the same
     image and title unfurl. A link Slack has already seen may be cached; add `?x=1` to the
     end to force a fresh fetch.
  4. In a terminal run `curl -sI https://fantasy-trade-finder.onrender.com/og/p/<id>.png`.
     Expected: `HTTP/2 200`, `content-type: image/png` and `x-robots-tag: noindex`.
  5. Run `curl -s https://fantasy-trade-finder.onrender.com/s/p/<id> | grep -E 'og:image|robots'`.
     Expected: `og:image` content starts with `https://fantasy-trade-finder.onrender.com/og/p/`,
     and `<meta name="robots" content="noindex">` is present.
  6. If step 2 or 3 shows no card: log the step and the platform in TEST_LEDGER and tell
     league-eng. Do not re-add the robots.txt Disallow lines as a workaround.
- [ ] **WAIVED because:** n/a
- `testID`s added/renamed: none

## 4. Docs scope (MANDATORY — HLD / LLD / API)

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` (any route added/renamed/removed/contract-changed) | updated | Profiles + Sharing table: the `/s/*` rows note the absolute `og:image` / `twitter:image` and the `noindex` meta + header; the `/og/*` rows note the `X-Robots-Tag: noindex` header. No route added or removed |
| `living-memory/LLD.md` (schema/route/invariant *conventions* shifted) | n/a | no convention shifted; a header and two tag values on existing routes |
| `docs/architecture.md` (module wiring / data flow changed) | n/a | no wiring or data-flow change |
| `living-memory/HLD.md` (architecture genuinely shifted: new module, client, major flow) | n/a | no architecture change |
| `docs/cross-client-invariants.md` (shared constants/enums/colors) | n/a | no shared constant touched; the API's relative paths are unchanged |
| `docs/glossary.md` (new domain term) | n/a | no new term |
| ADR or `DECISIONS.md` entry (non-obvious choice made) | n/a | the choices (https in prod, no `X-Forwarded-*`, API stays relative) were made by league-eng in the brief and are recorded here and in the `_absolute_url` docstring |
| `web/CLAUDE.md` and the `web/sitemap.xml` header comment | updated | both said share landings are `Disallow`-ed in robots.txt, which this change made false |

## 5. Ship gate declaration

- **CI green:** `backend-tests` + `mobile-typecheck` + `maestro-testid-lint` — all passing on the pushed sha (CI's call; not run locally beyond the files above)
- **Evidence recorded:** `living-memory/TEST_LEDGER.md` entry naming what ran and what it proved. Not written on this branch; left to league-eng / release so it does not collide with other open PRs
- **TestFlight verification:** n/a (no mobile change). The operator checklist in §3 is run after deploy; log the outcome in TEST_LEDGER
- Express lane declared by the operator? no

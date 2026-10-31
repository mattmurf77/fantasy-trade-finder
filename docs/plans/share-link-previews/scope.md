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
**Operator sign-off on waivers:** waived, operator-approved 2026-11-01 (the one waiver, §1 analytics, covering C6 and R13; recorded via head-eng). This covers the waiver only. Merging still needs the operator's own go in release-lead's session.

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
      **Waived, operator-approved 2026-11-01.**

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

## 2026-10-31 — R13: privacy link and the Fleeced brand on `/s/*`

**Entry point:** head-eng (2026-10-31). Legal-lead's R13 (`docs/plans/org-bringup/leads/legal-lead.md` § R13, product S4) requires a privacy link on every `/s/*` page and the brand "Fleeced" there. release-lead found the expired page mixed "Open Fleeced…" with a "Fantasy Trade Finder" title and footer. It's folded into #511 because #511 already rewrites `_share_html`: one writer, one delta QA. The policy line ("shared trades are public to anyone with the link") is #373's (onboarding-eng), not this PR's.

**What changes** (every `/s/*` page renders through `_share_html`: `/s/p`, `/s/tiers`, a live `/s/trade/<token>`, the expired-trade page):
- `<title>`: `{title} · Fleeced: Dynasty Trade Finder` (marketing `s4.title`; was `· Fantasy Trade Finder`).
- The brand line under the CTA: `Fleeced: Dynasty Trade Finder` (marketing `s4.brand`, D-057's full name; was `Fantasy Trade Finder`). Its colour becomes `var(--chalk-dim)`: the old `#6b7a9a` was 4.29:1 on `#0f1322`, under AA for 13px text, and the new colour is 7.06:1 (design-lead).
- New, directly under it: `<div class="legal-links"><a href="/privacy">Privacy</a></div>`, linking the existing `/privacy` route. The styles are #373's passed rules verbatim (`.legal-links` 13px `--chalk-faint`; links `--chalk`, underlined, `--ice` on hover), from `/css/tokens.css`. Nothing else on the page is restyled.
- The og PNG card footer (`og_image.py`): `Fleeced: Dynasty Trade Finder · fantasy-trade-finder.onrender.com` (marketing `s4.og_footer`; was `Fantasy Trade Finder · …`). Measured at 22px, it's 624–686px wide on macOS fonts. The worst case is DejaVu Sans Bold at 846px (right edge x=906), which is probably prod, since it's the first Linux candidate. All fit the 1080px rule (right edge ≤ 1140). `_draw_footer` is fixed-position and left-aligned, so nothing is measured or clipped. The card is the unfurl image and is embedded in every `/s/*` page.
- No new copy beyond the brand name and the "Privacy" label. The three strings are marketing's approved `s4.*` (`marketing-lead-wave2.md` S5 rows; approved to ship by launch in `marketing-lead-referral-approval.md`). `s4.og_site` (a new `og:site_name` tag) isn't in that ship list, so it's not added.

**Analytics:** (c) waived, as §1 (operator-approved 2026-11-01). A static link and brand text, nothing to measure. **Schema, flags, routes:** none.

**Evidence** (`test_share_link_previews.py` §5, 8 cases):
- `_assert_r13` runs on `/s/p`, `/s/tiers`, a live `/s/trade/<token>`, and the expired page (numeric id and unknown token). It checks:
  - the Privacy link appears exactly once, directly after the brand line and inside `.card`;
  - no "Fantasy Trade Finder";
  - one `<title>`, ending ` · Fleeced`;
  - the brand line appears once;
  - `tokens.css` is linked once.
- `/privacy` returns 200.
- The og footer:
  - a source-level check, labelled as such: no "Fantasy Trade Finder" in `og_image.py`, and the footer contains "Fleeced";
  - a real `/og/trade/<token>.png` render: 200, `image/png`, PNG bytes. A spy on `ImageDraw.text` proves the Fleeced footer is the string drawn.
- The footer layout is fixed-position and left-aligned (`_draw_footer` at `(60, CARD_H-50)`), so the shorter string moves nothing.

Results:
- pytest share set + #362's account tests: 138 passed. `check_web_structure` 196/196. `check-share-trade-token` 14/14.
- Sabotage runs, each red, then restored:

  | Sabotage | Red |
  |---|---|
  | privacy link removed | the 5 page tests |
  | old `<title>` | the 5 page tests |
  | old brand line | the 5 page tests |
  | old og footer | the 2 footer tests |
  | href → `/terms` | the 5 page tests |
  | title `· Fleeced: Dynasty Trade Finder` | the 5, on the title check |
  | brand line `Fleeced` only | the 5, on the brand check |

- The link rules are scoped under `.legal-links`, so the CTA `<a>` is untouched. They don't depend on #373 landing.

**Docs:** `docs/api-reference.md` n/a (page content, not a contract).

**Follow-up, not this PR:** the share page and og cards predate Chalkline: a `-apple-system, Segoe UI, Roboto` stack, a 16px image radius and shadow, a pill CTA, and the old navy palette. A restyle is design-lead's call.

**Operator checklist** (after deploy):

| # | Steps | Expected |
|---|---|---|
| R1 | Open a live `/s/trade/<token>` link in Safari | The tab title ends "· Fleeced: Dynasty Trade Finder". Under the CTA: "Fleeced: Dynasty Trade Finder", then an underlined **Privacy** link. Tapping it opens the privacy policy. |
| R2 | Open an expired or unknown `/s/trade/…` link | The same brand line and **Privacy** link. "Fantasy Trade Finder" appears nowhere on the page. |
| R3 | Paste a share link into iMessage | The unfurl card's footer reads "Fleeced: Dynasty Trade Finder · fantasy-trade-finder.onrender.com" on one line. **The player names are readable at thumbnail size, not tiny text** (design-lead B4: with no TrueType font on the server, Pillow falls back to a 10px default. If so, vendor a TTF, such as the OFL Archivo files on `design/og-cards`, as the first `_FONT_CANDIDATES` entry). |
| R4 | Same card, a trade with a QB and a TE; then share a trade where one side has 4+ players | No percentage, "fair" text or meter anywhere on the card, and the panels sit centred between the title and the footer. There's no box or odd glyph between YOU GIVE and YOU GET. QB chips are orange and TE chips are purple, with dark labels. On the 4+ side: two players, then "+N more" in grey. |

**Legal: PASSES R13** (legal-lead R28.23, via head-eng 2026-11-01). Every `/s/*` page renders through `_share_html` with the Fleeced title, the brand line, the Privacy link and `noindex`, and the preview footer carries the Fleeced brand.

**Flag-on gate for `growth.tier_board_share` (legal, 2026-11-01).** `/s/tiers/<pos>/<username>` puts the username in its title and description. The route is dark today. **Before that flag is ever turned on, it needs:**
- (a) an unguessable token in place of the username in the URL, with the username shown only if the sharer chooses to show it;
- (b) the ink-0 tier-card label, done in `c1e62fa8`;
- (c) the tier-chip label must fit its 90px chip. Today "WR" overflows by +7px in Arial and +19px in DejaVu Bold, and "QB" by +3px in DejaVu (release-lead QA P3, 2026-11-01; renders in their `qa362/out/r511/tier-chips-sheet.png`). Shrink the label or widen the chip.

**Reviews:** design-lead **passed** the link style and brand line at `8b90d674` (2026-10-31). Their two string changes (`s4.title`, `s4.og_footer`) and the `.brand` contrast fix are applied. Legal-lead's review of R13 is routed via head-eng.

**Not done here (design-lead optional item 5):** the expired page's approved `p29.*` set (title "Link expired — Fleeced: Dynasty Trade Finder", headline, body, og lines) is engagement-eng's P29 work. Its tab title reads "This trade link has expired. · Fleeced: Dynasty Trade Finder" until then.

**Merge overlap:** #386 (Referral D-1, also stacked on #362) also rewrites `_share_html` (`share_kind`/`noindex`, drops `cta_url`). Whichever lands second must keep the R13 lines; `_assert_r13` catches a drop.

**Flagged, not changed:** `server.py:28191` push copy "@{name} joined Fantasy Trade Finder via your invite." It's off `/s/*`, so it goes to head-eng for marketing.

## 2026-10-31 — og trade card fix (B1–B3, before launch)

**Entry point:** head-eng and Product (2026-10-31). C6 makes `_render_trade_card_png` (`/og/trade/<token>.png`, `/og/p/<id>.png`) the iMessage, Slack and X preview for every share, so its defects become public. design-lead's spec (`docs/plans/org-bringup/reports/design-lead.md` § "Broken, not just off-brand") is a minimal fix of about 10 lines, not a restyle:
- **B1:** the "% fair" verdict text overlapped the meter bar by 20px. `font_score` 96 → 72 and `verdict_y` 445 → 428 leave 19px clear.
- **B2:** the "⇄" swap glyph (U+21C4) is missing from Arial, Helvetica and SF and renders as a box. The disc and glyph are removed; the YOU GIVE / YOU GET headers carry the meaning.
- **B3:** `POS_COLORS` contradicted the cross-client invariants (QB red, TE orange). It now uses QB `#f97316`, RB `#22c55e`, WR `#3b82f6` and TE `#a855f7`. Chip labels move from white (2.3:1 on RB) to ink-0 (4.9–8.5:1). `og_image.py` is added to the invariants row's Locations.
- **B4** (fonts on the server, unverified) rides operator checklist R3.

**Superseded 2026-11-01: the "% fair" number and meter are removed before launch** (head-eng; Product decision on models-lead addendum I6). The number was the ratio of the two sides' average Sleeper search rank, which is popularity, not value: it ignored package size and skipped picks, and "no percentage of any kind is safe publicly". It isn't replaced with a verdict. B1 (text clearing the bar) is moot. The card is recentred per design-lead (title y=85, panels 175–455; 85px above, 105px to the footer rule). "+N more" (approved) replaces the silent `ids[:3]` cut when a side has more than 3 players. Evidence: see [2026-11-01 — no fairness number](#2026-11-01--no-fairness-number-recentre-n-more).

**Evidence** (`test_share_link_previews.py` §6). `_spied_trade_card` renders a real `/og/trade/<token>.png` and records every `text`, `rounded_rectangle` and `ellipse` call.
- **B1:** the "% fair" glyph box (`font.getbbox` at its xy) ends at least 16px above the meter bar. Measured clearance at 72px: 19px in Arial Bold and DejaVu Sans Bold, 30 in Helvetica, 16 in SFNS (the last fallback), 77 with `load_default()`.
- **B2:** no drawn text has U+21C4 or anything outside a named safe set (printable ASCII plus `·`, `—`, `…`). No ellipse covers the card centre, and a 13×13 pixel grid at the centre is plain background.
- **B3:** `POS_COLORS` equals the invariants doc's Position color table, which the test parses, and the trade card's chip labels are ink-0 `(12,14,17)`.

Results: pytest 7-file set 141 passed; `check_web_structure` 196/196. Before and after renders were reviewed by league-eng: the verdict clears the bar, the disc and box are gone, and the chips are orange, green, blue and purple with dark labels.

Sabotage runs, each red only on its own test:

| Sabotage | Red |
|---|---|
| `font_score` 96 / `verdict_y` 445 | B1 |
| disc + "⇄" restored | B2 |
| disc only | B2 (ellipse) |
| a white block at the centre | B2 (pixels) |
| TE back to `(255,167,38)` | B3 |
| chip label back to white | B3 |

**Where the new colours reach:**
- `POS_COLORS` is used only in `og_image.py`.
- The trade/package card chip (`/og/trade`, `/og/p`) now has an ink-0 label: 4.88–8.48:1, and 5.77:1 on the grey fallback chip for K/DEF.
- The tier card (`/og/tiers`, `_render_tier_card_filled`) gets the new chip colours, but its 58px label stays white: QB 2.80:1 and RB 2.28:1, under the 3:1 large-text bar.
  - That surface 404s while `growth.tier_board_share` is off (`config/features.json`), so it isn't widened here.
  - **Done 2026-11-01** (head-eng): the tier card label is now ink-0 (QB 6.90, RB 8.48, WR 5.26, TE 4.88:1; white was 2.80, 2.28, 3.68, 3.96). `test_og_tier_card_position_label_is_ink_0` renders all four positions with the flag on, asserts WCAG ≥ 3:1 for the drawn fill on its chip, and asserts the ink-0 fill. Sabotage (white) fails it on QB (2.80). pytest 7-file set: 146 passed.
  - Left for the GB-02 restyle (flag dark): "WR" at 58px Arial Bold is 97px wide on the 90px chip and overflows by 3–4px each side. With white text the overflow showed on navy; with ink-0 it may read as slightly clipped.

## 2026-11-01 — no fairness number; recentre; +N more

**Entry point:** head-eng (2026-11-01). Product decided to drop the og trade card's "% fair" number and meter before launch (models-lead addendum I6), and #511 doesn't merge without it. The approved title and footer strings, the position colours and the give/get layout stay.

**Changes** (`og_image.py`):
- `_compute_fairness`, the verdict text and the meter are removed.
- design-lead's recentre: title (60, 85); `col_top` 175; `col_bot` 455.
- "+N more" in `TEXT_MUTED` replaces the third row when a side has more than 3 players: 2 names, then "+(len−2) more". With exactly 3 players, all 3 names are drawn.

`_fairness_color` is removed too, since nothing else used it. Both `render_trade_card` and `render_package_card` drop the argument, and the card no longer reads `search_rank`. "+N more" starts at the chip column (x0+24), like a row with no chip. If design-lead wants it under the names (x0+94), that's a one-number change pinned by the test.

**Evidence** (`test_share_link_previews.py` §6 and §8, real renders with draw-call spies):
- `test_og_trade_card_has_no_fairness_number_or_meter`: no drawn text matches `\d+\s*%` or contains "fair"; no rounded rectangle in y 500–540; no `_compute_fairness` or `_fairness_color` attribute. It replaces B1's clearance test.
- `test_og_trade_card_layout_is_recentred`: two panels spanning y 175→455, "Trade Match" at (60, 85), and the footer rule as the only line, at 560.
- `test_og_package_card_caps_a_side_at_two_names_plus_n_more[3,4,5]` through `/og/p` (`render_package_card`). With 3 players, all 3 names and no "+N more". With 4 or 5, the first 2 names, then one `+{n-2} more` in `TEXT_MUTED`, in the player font, at (84, 383).
- B2's centre check moves to y=315.

Results: pytest 7-file set 150 passed; `check_web_structure` 196/196. Renders were reviewed by league-eng (2-for-2 and 5-for-1).

Sabotage runs, each red only on its own tests:

| Sabotage | Red |
|---|---|
| verdict draw back | no-fairness |
| meter track only | no-fairness (band) |
| `col_top` 135 | layout, `+N` [4,5] |
| `ids[:3]` with no "+N more" | `+N` [4,5] |
| "+N more" in white | `+N` [4,5] |

**Copy decision needed before launch (via head-eng → marketing; not changed here).** Two share-page descriptions still promise the verdict the card no longer shows. Each feeds `<meta name=description>`, `og:description`, `twitter:description` and the visible `<p>`:
- `server.py:31220` (live `/s/trade/<token>`): "A dynasty fantasy trade — see the give/get breakdown and fairness verdict."
- `server.py:31397` (`/s/p/<id>`, marketing's `s2.pkg.desc`): "…see the give/get breakdown and fairness read."
- `server.py:31064` is only a docstring. Nothing in mobile or web share paths reads the og number.

## Renders for the operator's design review (2026-11-01)

These are for the rule of 2026-10-31 (every design change gets the operator's approval, in parallel with release). head-product shows them; they're also embedded in the #511 PR body. "Before" is `origin/main` (`29ba8f26`); "after" is `c2ec824f`.
- Trade card, 2-for-2: [before](renders/og-trade-card-2for2-before.png) · [after](renders/og-trade-card-2for2-after.png).
- Trade card, 5-for-1: [before](renders/og-trade-card-5for1-before.png) · [after](renders/og-trade-card-5for1-after.png). Main silently showed 3 of 5 players.
- Live `/s/trade` page at 1280×900, 2x, headless Chrome: [before](renders/share-page-before.png) · [after](renders/share-page-after.png).

How they were made:
- The cards come from each version's own `_render_trade_card_png` with the same give/get lists. Main's number comes from its own `_compute_fairness`. The after card is byte-identical to the real `/og/trade/<token>.png` route.
- The pages are main's `_share_html` source and the Flask test client at `c2ec824f`, each served locally with `tokens.css` and its card.
- The after page still shows "…and fairness verdict" in its description. That's the copy item routed to marketing.

## 2026-11-01 — share-page descriptions (fallback lines) and the C1 side fix

**Descriptions (release-lead's delta-QA P2; marketing addendum 14 Part A, via head-eng).** #511 draws no bar, so both pages use marketing's approved fallback lines. This resolves the "copy decision needed" item above.
- `/s/trade/<token>`: "A dynasty fantasy trade. See the give/get breakdown."
- `/s/p/<id>`: "A {n}-player dynasty trade package. See the give/get breakdown." `{n}` is the total player count, unchanged.

Each feeds the meta description, `og:description`, `twitter:description` and the visible `<p>`. No share page says "fair" anymore. §9 tests the exact strings on all four tags and that "fair" is absent; two sabotage runs (each old string put back) each went red.

**C1, the side fix** (cherry-picked from #564's `691184a8` as `bba76f16`, at head-eng's request). `resolve_trade_share_token` returns the row oriented to the sharer, so a user_b share no longer draws user_a's columns. `test_share_side_orientation.py` has 3 tests.

**Runs:** the share set (8 files): 155 passed; `check_web_structure` 196/196.

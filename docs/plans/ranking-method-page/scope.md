# Feature Scope — C7: rebuild `web/ranking-method.html` ("How your rankings shape trades")

**Date:** 2026-10-27 (final copy 2026-10-29)
**Entry point:** direct ask (C7, web only, no binary, due about 11-13); rankings-pm review #3
**Builder:** `eng-backend` worker for rankings-eng, branch `fix/ranking-method-page` (base `origin/main` `190ce568`)
**Operator sign-off on waivers:** pending. The waivers below go to the operator through rankings-eng.
**Copy status: final.** marketing-lead's §6 addendum 11 (2026-10-28), routed head-bizops → head-eng. Every string is byte for byte from that addendum (straight apostrophes, a middle dot `·` in the title). It replaces the C7 copy draft (2026-10-27).
- **Legal:** none needed. Section 1 is approved listing text, and Section 2 is shipped app text.
- **Operator ask:** none new, by marketing's reading (the listing lines are already operator-approved, §5, 10-23). That's head-bizops' call.

**Why.** Trades' "How trades are priced" help sheet links here as its read-more (`TradesScreen.tsx:10555`), and the page is in the sitemap. It contradicted the app:
- It recommended the retired trio "Journey", while the app recommends Quick set (`rankChooserModel.ts:53`).
- It had no Quick set and no Pick Anchors.
- It never explained how your board shapes the trades you see.
- Its method tiles looked tappable on a page that cannot open any app screen.

**What changed.** `web/ranking-method.html` is rebuilt:
- Copy is marketing's final addendum 11: title and meta, H1, subtitle, Section 1 ("How your board shapes your trades": three operator-approved listing lines), Section 2's lead-in, the three primary methods, and "More ways to rank". Trends is left out.
- The help sheet's pricing lines are deliberately not used: boards pick which trades you're shown, while values come from consensus (models-lead's C9).
- The layout is design-lead's spec: one plain hairline list on the page surface, nothing that looks clickable, TickLabel headers, and the `FLEECED.` logotype.
- After design-lead's #505 review, the page also has the standard site footer (Home · FAQ · Privacy · Terms), copied from `web/contact.html`.

---

## 1. Analytics scope

- [x] **(c) WAIVED.** No analytics are needed: the page is a static explainer with no actions, and no event is added or changed.

## 2. Schema & flag scope

- New/changed tables or columns: **none**. This is a static page.
- New/changed feature flags: **none**. The page replaces the stale one outright, and there is nothing to graduate.
- New env vars / `model_config` keys: **none**.
- API: **none**. No route; Flask serves `web/` statically, and the URL is unchanged.

## 3. Evidence scope

- [x] **Structural guard:** `qa/web/check_ranking_method_page.py`. It is dependency-free python: no browser, server or network. It pins:
  - **APP:** every [app] string is verbatim with its app source, read from the source at run time (14 chooser strings + the lead-in), and Trends is absent. The help-sheet body is no longer on the page, so its two checks are gone;
  - **COPY:** addendum 11's final strings, pinned as literals (the marketing file isn't on main): `<title>`, `og:title`, the meta description, `og:description`, the H1, the subtitle, Section 1's heading, and Section 1's three paragraphs, exactly and in order;
  - **NO-PRICING:** the page (comments stripped, head and body) has none of "How trades are priced", "priced on two boards", "priced off your board", "set the prices", "prices every trade" or "fairness meter";
  - **TITLE:** no `—` or `–` in `<title>` or `og:title`, and both use ` · `;
  - **CANONICAL:** the canonical href and `og:url` both equal `https://fantasy-trade-finder.onrender.com/ranking-method.html`, with no `?` or `#`;
  - **OLD:** the Journey / three-option copy is gone;
  - **FLAT:** no raised `--ink-1..3` fill, no border except the `--line` top hairline, and no radius, shadow, `cursor:pointer` or `:hover`;
  - **TAP:** no `button`, `input`, `select`, `details`, `tabindex` or `onclick`; links only inside body copy (none today) or the site footer; no link or control in the header or either methods list; the logotype stays plain text;
  - **FOOT:** the footer is `web/contact.html`'s `.foot` verbatim: the same four links (href + text) and the same `.foot` / `.foot a` rules;
  - **ICE:** ice only on the tick, the logotype period and the focus ring (which the footer links now use);
  - **FLARE:** flare only on the "Recommended" text tag;
  - **HEX:** no raw hex;
  - **TAG:** "Recommended" appears once, on Quick set's row.

  **CI wiring:** the `web-structure` CI job runs only `python3 qa/web/check_web_structure.py`. This new file is **not wired into CI**, because that would need a `ci.yml` line or an import in that script, and neither is in the grant. Run it by hand, or let release-lead wire it.

  Each sabotage below was applied, observed red, and reverted green:

  | Sabotage | Red check |
  |---|---|
  | "Head-to-heads" → "Head to heads" | APP-verbatim[trio.title] |
  | Trends row added | APP-trends-left-out |
  | "Guide me through the Journey" added | OLD-copy-removed |
  | `.method { background: var(--ink-2); border-radius: 8px }` | FLAT-no-cards |
  | `.method { cursor: pointer }` | FLAT-no-cards |
  | `<button>` around "Quick set" | TAP-no-controls |
  | the logotype made an `<a href="/">` | TAP-links-only-in-body-or-footer, TAP-header-and-methods-inert, TAP-logotype-plain-text |
  | a link inside a method row (`<a>` around "Tiers board") | TAP-links-only-in-body-or-footer, TAP-header-and-methods-inert |
  | a footer link dropped (Privacy) | FOOT-links-match-contact |
  | `.method-name { color: var(--ice) }` | ICE-only-tick-logo-focus |
  | `.then { color: var(--flare) }` | FLARE-only-recommended |
  | `.then { color: #ECEFF4 }` | HEX-none |
  | "Recommended" tag removed | TAG-recommended-on-quickset-only |
  | `<title>` "shape trades" → "shape your trades" | COPY-title |
  | `og:title` "Fleeced:" → "Fleeced" (colon dropped) | COPY-og-title |
  | meta description "you're" with a curly ’ | COPY-meta-description |
  | `og:description` final period dropped | COPY-og-description |
  | H1 title-cased ("How Your Rankings Shape Trades") | COPY-h1 |
  | subtitle "Here's" with a curly ’ | COPY-subtitle |
  | Section 1 heading "shapes your trades" → "shapes trades" | COPY-s1-heading |
  | Section 1 paragraphs 2 and 3 swapped | COPY-s1-prose |
  | "The fairness meter compares the packages." appended to the Ways-to-rank lead-in (body) | NO-PRICING |
  | `<meta name="keywords" content="how trades are priced">` added (head) | NO-PRICING |
  | `og:title` " · " → " — " | TITLE-no-dash, COPY-og-title |
  | canonical href + `?ref=help` | CANONICAL-query-free |
  | `og:url` + `#top` | CANONICAL-query-free |

  The page check is green at **40/40** (31 before the final copy, minus the two help-sheet checks, plus 11). `qa/web/check_web_structure.py` (the CI suite, which covers this page's SEO/a11y/DS rows): **196/196 pass**.
- [ ] **Unit tests:** none. This is a static page with no script.
- [x] **Static review: [app] strings verbatim.** Each was diffed against its source by the guard at run time and matches exactly:

  | Page text | App source |
  |---|---|
  | Quick set · Fastest · body · sub ("Quick rank — a follow-on pass…") | `mobile/src/navigation/rankChooserModel.ts:44-52` |
  | "Then, if you want:" | `mobile/src/screens/RankHomeScreen.tsx:264` |
  | Head-to-heads · Most precise · body | `rankChooserModel.ts:60-64` |
  | Tiers board · Most control · body | `rankChooserModel.ts:71-75` |
  | Pick Anchors · body | `rankChooserModel.ts:86-87` |
  | Overall ranks · body | `rankChooserModel.ts:94-95` |

  The section labels "Ways to rank" and "More ways to rank" and the "Ways to rank" lead-in are [new] lines kept from the draft. "Recommended" mirrors `recommended: true` (addendum 11, answer 2: keep it).
- [x] **Copy table: final, marketing §6 addendum 11 (2026-10-28).** COPY pins each string exactly:

  | Element | Final text | Source |
  |---|---|---|
  | `<title>` / `og:title` | `How your rankings shape trades · Fleeced: Dynasty Trade Finder` | [new]: D-057's name with its colon; a middle dot, not a dash |
  | `meta description` / `og:description` | `See how your rankings shape the trades you're shown, and the ways to rank: Quick set, Head-to-heads, Tiers board and more.` | [new]: no pricing claim, Fleeced not the subject |
  | H1 | `How your rankings shape trades` | [new]: holds for both entry points; settled 10-28 (head-bizops) |
  | Subtitle | `Your rankings shape the trades you see. Here's how it works, and the ways to rank.` | [new], no pricing claim |
  | Section 1 heading | `How your board shapes your trades` | [new] |
  | Section 1, paragraph 1 | `Your deck of suggested trades is built from your board and your leaguemates' boards. Until a leaguemate ranks, their side uses consensus values.` | listing §5 (operator-approved 10-23) |
  | Section 1, paragraph 2 | `Swipe to like the trades you'd make. When a leaguemate likes the same trade, it becomes a matched trade.` | listing §5, verbatim |
  | Section 1, paragraph 3 | `Every value and every trade card is an estimate from rankings, not a guarantee.` | listing §5, verbatim |
  | Section 2 (lead-in, methods, "More ways to rank") | unchanged | the [app] table above |
- [x] **Static review: interactive elements.** Exactly **four**, all in the standard site footer added on design-lead's #505 review: **Home** `/`, **FAQ** `/faq.html`, **Privacy** `/privacy`, **Terms** `/terms`.
  - The markup and the chalk-dim `.foot a` style are copied verbatim from `web/contact.html`. The page is in the sitemap, so search visitors don't dead-end.
  - Everything else is inert: no `<button>`, `<input>`, `<select>`, `<textarea>`, `<details>`/`<summary>`, `<label>`, `tabindex`, `role="button"` or `onclick`, no `cursor` or `:hover` rules, and no link in the header or the methods lists. The logotype is plain text (see "Judgment calls").
  - The body-link rule (chalk + underline, #354) is scoped to `.prose a, .method-line a` so the footer keeps contact's styling. The copy has no body links today.
  - **Footer source:** the ask was to match `web/faq.html` / `web/contact.html`, but on main only `contact.html` carries the Home · FAQ · Privacy · Terms `.foot`. `faq.html` (main, and the pending `feat/m7-p28-web-pages`) still has its older `.faq-footer` ("Head back to the app" / email + Privacy Policy · Terms of Use). So the check compares against `contact.html`.
- [x] **Manual check list for release-lead** (no runtime screenshot was taken, and the page was not opened in a browser for this build):
  1. Open `/ranking-method.html` at **phone width (375 px)**.
     - **Expected:** a 16 px side gutter and no horizontal scroll.
     - Rows read icon → name → role/Recommended tags (these wrap under the name if needed) → one or two dim lines.
     - The hairlines sit between rows only.
  2. Open it at **desktop width**.
     - **Expected:** one ~600 px column, with the same rows and no cards, fills, borders or icon wells.
  3. Hover and click across every row, name, tag and icon, and Tab through the page.
     - **Expected:** nothing in the header, Section 1's prose or method lists changes on hover or takes focus, and none of it looks tappable.
     - The only focus stops are the four footer links (Home · FAQ · Privacy · Terms). They look and act as they do on `/contact.html` and go to `/`, `/faq.html`, `/privacy` and `/terms`.
  4. Check against design-lead's spec:
     - ice appears only on the three TickLabel ticks (How your board shapes your trades, Ways to rank, More ways to rank) and the logotype period;
     - "Recommended" is flare text with no border or pill;
     - method names are Archivo 600 16/22 chalk, and lines are body-sm chalk-dim;
     - Section 1's three paragraphs are plain body chalk-dim;
     - there is no bottom CTA.
  5. Confirm the app's help-sheet "Read more" on Trades opens this page.
  6. Look at the browser tab title.
     - **Expected:** `How your rankings shape trades · Fleeced: Dynasty Trade Finder`, with a middle dot `·` between the two halves: not a dash, a `?` or a missing-glyph box.
- **Review:** design-lead's `/design-review` on the PR.
- `testID`s: n/a (web).

## 4. Docs scope

| Doc | Updated? | Section / reason n/a |
|---|---|---|
| `docs/api-reference.md` | n/a | No route added or changed; static file at the same URL |
| `living-memory/LLD.md` | n/a | No schema, route or invariant convention shifted |
| `docs/architecture.md` | n/a | No module wiring or data flow change |
| `living-memory/HLD.md` | n/a | No new module, client or flow |
| `docs/cross-client-invariants.md` | n/a | No shared constants or enums. The page copies app strings, and the guard pins them to the source |
| `docs/glossary.md` | n/a | No new domain term (Quick set, Head-to-heads, etc. already exist) |
| ADR or `DECISIONS.md` | n/a | The design follows design-lead's adopted spec; no new decision |
| `docs/design/components.md` | n/a | No new component. The rows reuse the LeagueRow hairline idea without chevron/hover, and the TickLabel |

## 5. Ship gate declaration

- **CI green** (`backend-tests`, `mobile-typecheck`, `web-structure`, testid-lint) on the pushed sha. This worker does not push.
- **Copy:** final, marketing §6 addendum 11 (2026-10-28), routed head-bizops → head-eng. The draft's two open questions are answered:
  1. The H1 is "How your rankings shape trades" (settled 10-28: C9 says boards pick which trades you see, while values come from consensus, so a pricing H1 would claim a mechanism the model doesn't run).
  2. Quick set keeps "Recommended".
  - Legal: none needed. No new operator ask, by marketing's reading; that's head-bizops' call.
- **Evidence recorded:** the TEST_LEDGER entry is release-lead's, at merge.
- Express lane declared by the operator? **No.**

## Judgment calls (for design-lead / marketing)

- **Role tags.** The draft lists each method's role (Fastest / Most precise / Most control). The spec's row didn't mention them, so they render as chalk-dim `label` tags beside the name, the same treatment as "Recommended" but not flare.
- **Section 1 has a TickLabel.** The final copy gives it its own heading, "How your board shapes your trades", in the same `<section aria-labelledby>` + TickLabel markup as "Ways to rank". The page now has three TickLabels; the CSS is unchanged.
- **The logotype is not a link,** to keep "nothing clickable except body links". `web/index.html`'s `.lp-wordmark` is a home link. The footer's **Home** link now covers the way back.
- **Ice.** Spec 4 makes the tick the page's only ice, and spec 6 makes the logotype period ice. Both hold, plus the standard `:focus-visible` ring (nothing on the page is focusable).
- **No values outside the token set.** The 1 px icon nudge (it centres the 20 px glyph on the 22 px title line), the 600 px column, and the 28 px logotype (copied from `.lp-wordmark`, not a type-scale size) are layout values. Everything else uses tokens, the type scale or the 4-pt spacing scale.

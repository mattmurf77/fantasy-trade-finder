# Feature Scope — C7: rebuild `web/ranking-method.html` ("How trades are priced")

**Date:** 2026-10-27
**Entry point:** direct ask (C7, web only, no binary, due about 11-13); rankings-pm review #3
**Builder:** `eng-backend` worker for rankings-eng, branch `fix/ranking-method-page` (base `origin/main` `190ce568`)
**Operator sign-off on waivers:** pending. The waivers below go to the operator through rankings-eng.
**Copy status: marketing approval PENDING.** The page ships as a DRAFT PR until marketing-lead approves the words (route: rankings-eng → head-eng → head-bizops → marketing-lead). Source: the C7 copy draft (2026-10-27).

**Why.** Trades' "How trades are priced" help sheet links here as its read-more (`TradesScreen.tsx:10555`), and the page is in the sitemap. It contradicted the app:
- It recommended the retired trio "Journey", while the app recommends Quick set (`rankChooserModel.ts:53`).
- It had no Quick set and no Pick Anchors.
- It never explained pricing.
- Its method tiles looked tappable on a page that cannot open any app screen.

**What changed.** `web/ranking-method.html` is rebuilt:
- Copy is exactly the draft: title and meta, H1, subtitle, Section 1's pricing prose, Section 2's lead-in, the three primary methods, and "More ways to rank". Trends is left out.
- The layout is design-lead's spec: one plain hairline list on the page surface, nothing that looks clickable, TickLabel headers, and the `FLEECED.` logotype.

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
  - **APP:** every [app] string is verbatim with its app source, read from the source at run time (14 chooser strings + the help body + the lead-in), and Trends is absent;
  - **OLD:** the Journey / three-option copy is gone;
  - **FLAT:** no raised `--ink-1..3` fill, no border except the `--line` top hairline, and no radius, shadow, `cursor:pointer` or `:hover`;
  - **TAP:** no `button`, `input`, `select`, `details`, `tabindex` or `onclick`, and links only inside body copy (none today);
  - **ICE:** ice only on the tick, the logotype period and the focus ring;
  - **FLARE:** flare only on the "Recommended" text tag;
  - **HEX:** no raw hex;
  - **TAG:** "Recommended" appears once, on Quick set's row.

  **CI wiring:** the `web-structure` CI job runs only `python3 qa/web/check_web_structure.py`. This new file is **not wired into CI**, because that would need a `ci.yml` line or an import in that script, and neither is in the grant. Run it by hand, or let release-lead wire it.

  Each sabotage below was applied, observed red, and reverted green:

  | Sabotage | Red check |
  |---|---|
  | "two boards — yours" → "two boards - yours" | APP-help-body-verbatim |
  | "Head-to-heads" → "Head to heads" | APP-verbatim[trio.title] |
  | Trends row added | APP-trends-left-out |
  | "Guide me through the Journey" added | OLD-copy-removed |
  | `.method { background: var(--ink-2); border-radius: 8px }` | FLAT-no-cards |
  | `.method { cursor: pointer }` | FLAT-no-cards |
  | `<button>` around "Quick set" | TAP-no-controls |
  | the logotype made an `<a href="/">` | TAP-links-only-in-body |
  | `.method-name { color: var(--ice) }` | ICE-only-tick-logo-focus |
  | `.then { color: var(--flare) }` | FLARE-only-recommended |
  | `.then { color: #ECEFF4 }` | HEX-none |
  | "Recommended" tag removed | TAG-recommended-on-quickset-only |

  `qa/web/check_web_structure.py` (the CI suite, which covers this page's SEO/a11y/DS rows): **196/196 pass**.
- [ ] **Unit tests:** none. This is a static page with no script.
- [x] **Static review: [app] strings verbatim.** Each was diffed against its source by the guard at run time and matches exactly:

  | Page text | App source |
  |---|---|
  | Pricing prose (2 paragraphs, joined by a space) = the help-sheet `body` | `mobile/src/screens/TradesScreen.tsx:10549-10553` |
  | "How trades are priced" (H1 = the help-sheet title) | `TradesScreen.tsx:10547` |
  | Quick set · Fastest · body · sub ("Quick rank — a follow-on pass…") | `mobile/src/navigation/rankChooserModel.ts:44-52` |
  | "Then, if you want:" | `mobile/src/screens/RankHomeScreen.tsx:264` |
  | Head-to-heads · Most precise · body | `rankChooserModel.ts:60-64` |
  | Tiers board · Most control · body | `rankChooserModel.ts:71-75` |
  | Pick Anchors · body | `rankChooserModel.ts:86-87` |
  | Overall ranks · body | `rankChooserModel.ts:94-95` |

  The [new] lines are verbatim from the draft: `<title>`/`og:title`, `meta description`/`og:description`, the subtitle, the "Ways to rank" lead-in, and the section labels "Ways to rank" and "More ways to rank". "Recommended" mirrors `recommended: true`.
- [x] **Static review: interactive elements.** **None.** There are no `<a>`, `<button>`, `<input>`, `<select>`, `<textarea>`, `<details>`/`<summary>`, `<label>`, `tabindex`, `role="button"` or `onclick`, and no `cursor` or `:hover` rules. The logotype is plain text, not a link (see "Judgment calls"). The `a` rule (chalk + underline, the #354 reading-link rule) is in place only for any future body link.
- [x] **Manual check list for release-lead** (no runtime screenshot was taken, and the page was not opened in a browser for this build):
  1. Open `/ranking-method.html` at **phone width (375 px)**.
     - **Expected:** a 16 px side gutter and no horizontal scroll.
     - Rows read icon → name → role/Recommended tags (these wrap under the name if needed) → one or two dim lines.
     - The hairlines sit between rows only.
  2. Open it at **desktop width**.
     - **Expected:** one ~600 px column, with the same rows and no cards, fills, borders or icon wells.
  3. Hover and click across every row, name, tag and icon, and Tab through the page.
     - **Expected:** nothing changes on hover, the cursor stays an arrow, nothing takes focus, and nothing looks tappable.
  4. Check against design-lead's spec:
     - ice appears only on the two TickLabel ticks and the logotype period;
     - "Recommended" is flare text with no border or pill;
     - method names are Archivo 600 16/22 chalk, and lines are body-sm chalk-dim;
     - the pricing prose is plain body chalk-dim;
     - there is no bottom CTA.
  5. Confirm the app's help-sheet "Read more" on Trades opens this page.
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
- **Copy:** marketing approval PENDING. The PR stays DRAFT until approved. The draft's two open questions:
  1. Should the H1 be "How trades are priced" or "How rankings set trade prices"?
  2. Should Quick set keep "Recommended"?
- **Evidence recorded:** the TEST_LEDGER entry is release-lead's, at merge.
- Express lane declared by the operator? **No.**

## Judgment calls (for design-lead / marketing)

- **Role tags.** The draft lists each method's role (Fastest / Most precise / Most control). The spec's row didn't mention them, so they render as chalk-dim `label` tags beside the name, the same treatment as "Recommended" but not flare.
- **Section 1 has no TickLabel.** Its draft name, "How trades are priced", is the H1, so the pricing prose sits under the subtitle as the lede. TickLabels head "Ways to rank" and "More ways to rank".
- **The logotype is not a link,** to keep "nothing clickable except body links". `web/index.html`'s `.lp-wordmark` is a home link.
- **Ice.** Spec 4 makes the tick the page's only ice, and spec 6 makes the logotype period ice. Both hold, plus the standard `:focus-visible` ring (nothing on the page is focusable).
- **No values outside the token set.** The 1 px icon nudge (it centres the 20 px glyph on the 22 px title line), the 600 px column, and the 28 px logotype (copied from `.lp-wordmark`, not a type-scale size) are layout values. Everything else uses tokens, the type scale or the 4-pt spacing scale.

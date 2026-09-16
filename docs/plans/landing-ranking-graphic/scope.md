# Landing ranking graphic — scope and evidence

Date: 2026-09-14. Entry: direct operator request. Branch: `codex/landing-ranking-graphic`, based on fetched `origin/main` ca7e6b85. Current status (2026-09-16): release authorized; preparing current-main CI and Render deployment. Dated sections below preserve iteration history; the final release scope is compact option B with the September 15 copy and production-style bar.

## 1. Analytics scope
WAIVED: static illustrative content adds no interaction or data collection. This rationale was surfaced before implementation. No new analytics needed.

## 2. Schema & flag scope
No tables, columns, feature flags, environment variables, or configuration keys change. No API requests added.

## 3. Evidence scope
- Existing web structural gate: 190/190 passed.
- Browser: headless Chrome at 1440, 390, and 320 CSS pixels; document widths match viewport widths (no page overflow). Desktop and narrow-phone screenshot inspection performed, with API responses stubbed for a static landing preview.
- Unit tests/mobile guards/TestFlight/testIDs: n/a; no executable logic or mobile change.
- Code trace: `web/index.html` figure `.ranking-graphic` contains both labeled boards, ownership, trade receipt, and illustrative caption. `web/css/styles.css` landing illustration rules control layout, with 960px and 420px responsive breakpoints.
- Memory validator could not run: `scripts/session_context.py` is absent from fetched main. HANDOFF/NEXT were not edited. `git diff --check` passed.
- No auth/backend validation claimed. Local preview uses a static server, not Flask or production.

## 4. Docs scope
Updated `docs/design/components.md` Auth screen section to document the existing operator-selected headline and the new graphic.
API reference, engineering notes, architecture, shared invariants, glossary, and ADR: n/a; this is a local HTML/CSS composition with existing tokens, vocabulary, and APIs. No architecture or cross-client contract changes.

## 5. Ship gate declaration
No express lane requested. Local web checks passed; remote CI and release are unexecuted and outside this request. No production changes. Full current CI is required before merge/push per repository workflow. Evidence recorded in TEST_LEDGER.

## Landing-page revision — 2026-09-14

Operator expanded scope to the entire page, condensed content above sign-in, ESPN/MFL visibility, and sign-in above the fold. Replaced long lower sections with three steps and a format note; added header and distinct connection section. On phones the larger illustration follows sign-in. Sleeper help uses native details disclosure. Removed username autofocus to avoid initial scrolling/keyboard activation.

Fixed the one-second flag reveal race by subscribing to the existing flag-settled event. Source inspection and browser testing found that commit a927e3a7 intentionally withdrew ESPN/MFL browser entry for verified ownership. Platform choices now surface their mobile-verification path with a contact link, never re-enable legacy claims. Full ESPN/MFL browser authentication is not implemented by this revision.

Analytics: existing sign-in events unchanged; no new event or collection. Schema/API/flags: unchanged. Canonical UI reference updated; existing API ownership contract preserved. No mobile or backend code changed.

Validation: 190/190 web guards; JavaScript syntax and diff whitespace checks pass. Headless Chrome verified an 1800ms flag delay, ESPN/MFL mobile panels, hidden legacy forms, return to Sleeper, and flags-off fallback. At 1366×768 the initial sign-in button ends at y=732; at 390×844 y=602; at 320×640 y=623, with no horizontal overflow. Desktop and phone screenshots visually inspected. Local server uses repository platform flags and rejects backend actions; real credentials and live auth were not exercised. Preview at localhost:8766. No deployment.

## Illustrated steps exploration — 2026-09-14

Operator requested small step images and exploration of clickable tiles with dedicated graphics. Explored A: static miniatures; B: clickable tiles sharing a detailed visual; C: a connected storyboard strip. [Comparison artifact](options.html). Implemented B with inline SVG thumbnails and accessible HTML/SVG detail so text remains crisp and responsive. No raster asset generation needed.

Three native buttons use exclusive aria-pressed states and replace one polite live region from templates; 02 is default. 01 illustrates setting personal rankings; 03 illustrates the resulting offer without an acceptance guarantee. The desktop visual reserves height; mobile selection deliberately scrolls to the visual. No automatic advance. Existing platform/auth flows untouched.

Analytics waiver: this local illustrative interaction adds no collection; no new tracking requested. Schema/API/flags/mobile: n/a. Updated canonical component reference and ledger.

Evidence: 195/195 web structural checks, JS syntax, and diff whitespace pass. Headless Chrome checks all three selections via Enter/Space, exclusive selection, unique live heading, default sign-in above fold at 1366×768, 390×844 and 320×640, and stable desktop sign-in position across panels. Visual inspection of desktop composition and dedicated desktop/mobile panels. Existing delayed-flags, ESPN/MFL mobile paths, Sleeper return and flags-off browser checks pass. No production auth or deployment performed.

## Selected direction C — 2026-09-14

Operator selected the connected storyboard and requested visuals closer to the app UI/palette. Replaced interactive B with static C. Miniatures follow canonical PlayerCard/TradeCard construction: WR rails, cyan selection, first-round tier badges, comparison highlights, and positive trade result. Directly reuse web token definitions. These are illustrative compositions, not screenshots or live application controls.

Removed the now-unused step script, its templates, and its custom styles. Main two-board illustration remains static. Refreshed comparison sheet C and canonical component reference. Analytics remains n/a: static content, no new collection. Schema, flags, API and auth behavior unchanged.

Checks: web structure 190/190; platform regression browser checks; desktop/mobile sign-in visibility and screenshot inspection at 1366×768, 390×844 and 320×640. No horizontal overflow. Local preview only, not deployed.

## Compact option B — 2026-09-14

Operator found the static thumbnails too small and selected B with an image condensed enough to remain above sign-in. Replaced the strip with three native buttons and one larger app-style graphic. The compact comparison is default; ranking and trade templates reuse Chalkline colors, WR rails, tier badges and positive result styling. All panels remain above sign-in on phones as well as desktop; selection does not scroll or move focus. Condensed phone copy and narrow input row retain initial-viewport sign-in.

Evidence: 195/195 structural checks; JS syntax and whitespace checks; keyboard Enter/Space selection, unique headings and exclusive pressed states; all selected visuals above sign-in at 1366×768, 390×844, 320×640; button right edge within viewport. Platform regressions pass. Illustrations are static client content; no analytics collection or API/flag changes. Local only; no deployment.

## Rookie pick value detail — 2026-09-15

Operator requested an explicit explanation that players are ranked by rookie draft pick values. Added it to the landing format note and step 01 caption, labeled the board’s tier values, and expanded first-round badge accessible labels. Copy only; no API, schema, flags or analytics changes. Web structural checks and existing browser layout/step checks validate the change.

## Explicit ranking tile and market fairness — 2026-09-15

Operator requested the exact tile label “Your rankings, in draft pick value” and a fairness bar in Real offers to show market evaluation alongside personal gains. Updated the actual 01 button and added a labeled, accessible FairnessMeter-style bar with a 92% balanced illustrative example. A visible note identifies it as an example, not live market data. No evaluation algorithm, API, flags, analytics, or schema changes. Existing market balanced threshold is 0.75; example color follows that contract.

Evidence: 195/195 structural checks; all three step selections, keyboard activation, illustration-before-sign-in and within-viewport sign-in checks at 1366×768, 390×844 and 320×640 passed. Desktop/mobile Real offers visuals inspected. No deployment.

## Production value bar and clearer comparison tile — 2026-09-15

Operator requested the production fairness bar, then chose exact tile-02 wording: “We compare your board with leaguemates”. Replaced the percentage meter with the current mobile TradeValueBar geometry from `mobile/src/components/TradeValueBar.tsx:131` and `:205`, mounted by production `TradeCard.tsx:923`. Show the illustrative Even state: cyan 6px centered nub on a 14px rail, second landmarks at 21.5% and 78.5%, pick scale and They win/You win end labels. Removed the redundant explanatory paragraphs and numeric percentage.

Stale styling was visible in the actual in-app browser. Versioned landing stylesheet/script URLs and disabled caching in the local preview server. Verification covers the actual browser’s rendered rail/scale, the exact tile wording, and desktop/mobile screenshots, plus the existing 195 web checks and keyboard/layout checks. No production deployment, authentication or evaluation behavior changes.

## Tile alignment and ranking heading — 2026-09-15

Operator requested equal-size tiles with wrapping text and “YOUR RANKINGS” as the first illustration heading. Removed unequal mobile grid proportions; all three buttons share equal columns and stretch to a common height. 195/195 web checks and responsive/keyboard checks passed; actual browser refreshed and screenshot verified.

## Comparison and matching copy — 2026-09-15

Applied exact operator wording: comparison heading “WE FIND THE DIFFERENCES” and step 03 “We match you leaguemates”. Copy only. Web structural and existing responsive checks passed; preview refreshed.

## Release authorization — 2026-09-16

Operator explicitly requested pushing the landing-page changes live. Release only the approved compact option B, current copy, market-fairness illustration, and platform discovery/handoff behavior. The subsequent copy critique and separate logo/wordmark export are not included. No backend, mobile binary, schema, configuration or credential changes.

Independent review found no release-blocking issues: flag settlement event matches its dispatcher, ESPN/MFL verification restrictions remain intact, keyboard selection and production bar construction are consistent. Versioned the changed app script as well as landing styles/step script to prevent the stale-asset symptom observed during preview.

Full current-head CI and observed Render/public-site delivery remain required before release is declared live. Release choreography, rollback and final evidence: [release record](../../business/ops/2026-09-16-landing-page.md).

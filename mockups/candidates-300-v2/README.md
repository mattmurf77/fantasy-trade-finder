# Candidates lab v2 — #300, round 2 (2026-08-11)

> Second-round redesign of feedback **#300** (League rankings → trade candidates → offer/target),
> drawn against `origin/main` @ `53bd19f` — i.e. against **#299 as shipped**, not against round 1's
> mockup box model. Mockups and rationale only; no production code.

Master viewer: [`index.html`](index.html) — plain links, **no iframes**. Round 1's index did not render
in Chrome over `file://`; this one has nothing that can fail. Every page is standalone (inline CSS,
inline SVG, no scripts, no external fonts) and can be opened directly.

## Pages

| Page | What it shows |
|---|---|
| [`index.html`](index.html) | Link-only master viewer, the three calls this lab makes, provenance |
| [`directions.html`](directions.html) | **The two competing shapes.** Today's screen filtered to WR; **Direction 1** (operator's — Trade-candidates section collapsed by default on the shipped `OutlookStrip` pattern, expanding to Buyers/Sellers pills, plus both drill-ins); **Direction 2** (no section — one ranked list with one median divider built from the shipped playoff-cutline construction, plus the odd-team-count case and the drawn cost of losing the intent toggle); the operator's literal **Buyers / Median / Sellers** phrasing drawn three ways (empty middle → invented ±12% band → the form that works); the shared drill-in; recommendation |
| [`tile-affordance.html`](tile-affordance.html) | **Geometry.** The shipped 32pt tile measured against real font metrics (name budget **143.8pt**, worst-case tier badge **63.5pt**); three resolutions of the 44pt/`onPress` constraint, including why a nested control is clipped by `overflow: 'hidden'` and invisible to VoiceOver + Maestro; **Variant D** re-measured; "Offer" vs "Target"; the side-by-side question answered with numbers; group-header copy |
| [`values-and-states.html`](values-and-states.html) | **Value in pick tiers, and the missing states.** The three value vocabularies already in the codebase and which one a delta may use; the ladder audit that kills delta-as-pick-tier; the exact floor read out of `_pick_gap_equivalent`; the new API field the divider needs; filter-changed-while-drilled-in; multi-select / flat-league / unpriceable-row states |
| [`measure-tile.py`](measure-tile.py) | The measurements, runnable. `python3 measure-tile.py` |

## Calls

| Question | Answer |
|---|---|
| Direction 1 or 2? | **Direction 2** — one list, one median divider — keeping Direction 1's vocabulary ("buyers"/"sellers") and its count line. Direction 1 adds persisted collapse state, a segmented control and a second list whose every row already appears below it, and buys one saved scroll flick. |
| 44pt on a 32pt row? | The **whole row** is the button (no nested control ⇒ no VoiceOver/Maestro problem), `hitSlop` 6/6 on the tile's own outermost `Pressable`, `rosterRow` margin 4 → 12. 44pt pitch, 32pt visual. **Sim-verify before asserting.** |
| Variant D (drop RK + injury for a visible "Offer")? | **Fits** — 146.4pt name budget vs today's 143.8pt; "Marvin Harrison Jr." unclipped. **Not recommended**: injury and rookie are decision inputs on a trade surface. Bare chevron + the verb once in the group header instead. |
| Delta as a pick tier? | No. `_pick_gap_equivalent` can do it and its floor is already defined in code, but the rungs are too sparse — 4 of 12 mock deltas collapse onto "an Early 1st" and the column mirrors around the line. Show each team's **level** (shipped `value_label`) and put the median's level on the divider. |
| Button naming? | **Offer** (yours) / **Target** (theirs). `TradesScreen.tsx:5373` already ships "Target players to acquire". |
| Both teams' players side by side? | Both rosters yes; side by side no — 171pt columns force deleting the tier badge and still truncate. Stack them, mirror collapsed to a disclosure row. |

## Measurement method

`measure-tile.py` loads the same TTFs the app loads — `@expo-google-fonts/archivo/{400Regular,600SemiBold}`
and `ibm-plex-mono/600SemiBold` from `mobile/node_modules` — and sums real `hmtx` advance widths, adding
React Native's `letterSpacing` after every glyph and the exact paddings/borders from `PlayerCard.tsx` and
`components/chalkline/Badge.tsx`. Round 1 estimated from its own mockup CSS and was ~3% optimistic
(148pt vs the measured 143.8pt; 60pt vs 63.5pt) — not enough to change its chevron verdict, enough to
matter for the marginal "Offer" label call.

The phone frames render in Arial/Helvetica fallbacks (no external font requests). Where truncation
matters the frame shows the **string the measurement says will render**, baked in literally.

## Provenance

- **Traced:** one image — `screens/mobile/league-summary/populated.png`, embedded on `directions.html`
  as the screen-identity anchor.
- **Reconstructed:** everything else. `screens/manifest.json` still has no drill-in capture for
  `league-summary` (flagged by #299, still open), and both directions propose surfaces that have never
  shipped in any form. Frames are labelled — gray = faithful recreation of today, pink = reconstruction.
- **Prior rounds:** round-1 lab `mockups/candidates-300/league-candidates-300.html` (`fed9485`);
  #299/#302 decisions `mockups/polish-lab-2026-08-11/OPERATOR-DECISIONS.md` (`221c134`); frozen round-1
  spec `docs/feedback/items/300-league-rankings-trade-candidates/operator-answers-2026-08-11.md`
  (branch `docs-297-302-artifacts` / PR #109).
- **Design rules:** `docs/design/design-system.md` + `docs/design/components.md`. No emoji, no gradients,
  no blur, radius ≤ 8, ice for actions and flare for informational highlights only, position/tier hexes
  verbatim from `docs/cross-client-invariants.md`. **11px type floor audited** — no rule in any of the
  four pages sets a size below 11px (round 1 shipped a 10px annotation). Radius above 8 appears only in
  lab chrome that is not a drawn app element: the 22px phone bezel, the 14px capture frame, and the 10px
  dashed annotation overlays — same convention as `mockups/polish-lab-2026-08/`.

## Rendered-from-`file://` verification (2026-08-11)

Round 1's index did not open in Chrome over `file://`, so this lab was checked rather than assumed. All
four pages were loaded in a real Chrome tab at
`file:///…/mockups/candidates-300-v2/<page>.html` at a 1500×900 viewport and screenshotted:

- `index.html` — renders; link-only, no iframes, no scripts.
- `directions.html` — renders; the one external reference, `../../screens/mobile/league-summary/populated.png`,
  **resolves and displays** (relative from a real file, not from `srcdoc`).
- `tile-affordance.html`, `values-and-states.html` — render.

Two rendering bugs were found and fixed during that pass: right-gutter measurement annotations
(`.measure::after`) were being clipped by the phone frame's `overflow: hidden`, and the R-1 illustration's
44pt hit box was invisible for exactly the reason the frame is about. Both were rebuilt.

## Open questions for the operator

1. **Is "below the median" really the candidate set you want?** As specified it is exactly the bottom
   half of a list already on screen, which is the whole reason to prefer a line over a section. If the
   real requirement is something narrower — a full pick tier below the median, or teams whose weakest
   starter you can beat — a section becomes justified because it would then contain a genuinely
   *filtered* set. This is the one question that could flip the recommendation.
2. **Side labels:** plain words ("Richer at WR — target theirs" / "Shorter at WR — offer yours") or the
   bare nouns ("Sellers" / "Buyers")? Both are drawn on `directions.html`.
3. **Variant D anyway?** It measures clean. The argument against it is content, not layout.

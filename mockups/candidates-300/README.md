# Candidates lab — 2026-08-11 (#300)

Mockups for #300 (League rankings → trade candidates → offer drill-in), designed
against the frozen spec in `docs/feedback/items/300-league-rankings-trade-candidates/
operator-answers-2026-08-11.md` (§6, "third pass"). Faithful recreation of today's
screen (left) beside the proposed redesign (right) in 390px phone frames, rationale
below each pair. Chalkline tokens throughout, reused verbatim from the validated
#299 lab (`mockups/polish-lab-2026-08-11/league-tile-density.html`, commit `221c134`)
so tile measurements here are directly comparable, not re-derived. All assets inline;
no external fonts/scripts/images. Master viewer: `index.html`.

**Every "Proposed" and drill-in frame is a reconstruction, not a capture** — see
the page's own coverage-gap note. There is no `league-summary` drill-in/focused-team
state anywhere in `screens/manifest.json` (#299's finding), and the specific state
#300 introduces — a candidate tapped, the CALLER's own roster rendering instead of
the tapped team's — has never existed in the shipped app in any form. Only the
top-level "populated, unfocused" anchor frame is a real capture
(`screens/mobile/league-summary/populated.png`).

| Page | Feedback | What it shows |
|---|---|---|
| [`league-candidates-300.html`](league-candidates-300.html) | #300 | Current (no candidates surface) vs proposed "Trade candidates" section (median-relative, weakest-first, reuses `TeamRow` — untouched by #299) under the chart card; the candidate drill-in showing the caller's OWN players at the filtered position with a trailing chevron "Offer" affordance + the screen-level "Find a Trade with this team" button; the dimmed 0-value row; the empty state for a caller who is themselves below the league median; and the full three-variant geometry contest (chevron-only vs visible "Offer" text vs visible text + dropped `posRank`) that answers whether the trailing affordance fits the post-#299 32pt tile — chevron-only does (128pt of 148pt baseline name budget survives), a visible text label does not without giving something else up. |

## The verdict this lab exists to produce

**Yes — a trailing chevron fits the post-#299 32pt tile.** Content width inside the
tile is 358pt; adding a bare ice chevron glyph to the existing badge+posRank right
cluster costs ~20pt, taking the worst-case name budget (long name + RK + injury tag +
widest tier label, the same stress case #299's own lab measured) from 148pt (~19
chars) to 128pt (~16 chars) — the same class of truncation #299 already called
acceptable. Tile height stays exactly 32pt.

**A literal, visible "Offer" text label does not fit as comfortably.** A small
"Offer ›" text+icon costs ~54pt (a word, not a glyph), collapsing the worst-case name
budget to 94pt (~12 chars) — "Marvin Harrison Jr." would render as "Marvin Harri…",
crossing from acceptable ellipsis into the name being the least legible fact on the
row. Recommended synthesis: chevron-only per row (Variant A) + one instructional line
at the drill-in header ("Tap › to offer a player to &lt;Team&gt;") so the word "Offer"
still appears on screen once, without paying the per-row cost on every player. Full
measured comparison, plus a third variant that recovers the visible label by dropping
`posRank` on this one surface, is in §4/§6 of the page.

## Open questions logged on the page (§8)

1. Operator-answers §1 Q1 says the candidate definition is "median/average-relative"
   without picking one — the two statistics produce different candidate lists and a
   different empty-state boundary. This lab drew median throughout; needs a one-word
   confirmation.
2. Is the chevron-only + section-hint synthesis an acceptable reading of "label
   'Offer'" (Q-N5), or does the operator want the word literally on every row
   (accepting Variant B's tighter truncation) or willing to drop `posRank` on this
   surface to afford it (Variant C)?
3. Group-header copy ("YOUR WR" vs bare "WR") to disambiguate that the drill-in
   reached from a candidate shows the caller's own roster, not the tapped team's —
   not specified in the decided design, a gap this lab's frames fill in.
4. What renders if the position filter changes while a candidate drill-in is open?
   Not mocked — a product question, not a layout one.
5. The candidates section stacks above the full ranked list rather than replacing it;
   confirmed against plan.md §3.2's "show all qualifying teams" but not re-litigated
   here.

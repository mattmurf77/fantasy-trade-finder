# #270 / #272 / #279 — Inline Trades Home mockup lab

**Status: MOCKUP ONLY — 2026-08-09.** No code changed. Deliverable:
`mockups/polish-lab-2026-08/trades-home-inline.html` (current + baseline +
4 variants + 1 extra `#279` frame, 393×852pt, Chalkline tokens).

## 2026-08-09 revision — two operator directives on the lab

After reviewing the first pass, the operator gave two revision directives
against the same mockup file (no new frames added beyond what's described
below; all other rows/frames left untouched):

1. **B1 (calculator canvas, empty state):** *"I don't know why you've
   removed the find a trade button. Re-gen with find a trade. Move the
   change pre section up to the top where it is in other mocks."*
   Fixed: `btnPrimary` "Find more trades" is restored in B1 (it drives the
   suggestion rail below the build columns — it was never meant to be
   removed, just under-drawn in the first pass). The frame's element order
   now matches A1's exactly for its first four blocks: utility row → League/
   Trading-with pills → prefs `editEntry` → CTA — only what renders below
   the CTA differs (build columns + suggestion rail vs. a swipe deck). B2
   (the populated calculator frame) was left untouched — the directive was
   B1-specific.
2. **D (accordion):** *"I like this layout when a user hits 'Change'...
   Re-do the mock so the default state is still that these are hidden
   behind the 'change' button."* Reworked: variant (d)'s default state
   (D1) is now byte-for-byte identical to baseline (BASE-1) — one `Change
   ›` line, full deck, nothing accordion-shaped visible on first paint.
   The accordion itself (the five collapsed section rows) is now what
   **opens** when Change is tapped (D2), replacing the `editEntry` line in
   place and pushing the deck down — instead of the earlier draft's
   full-height modal sheet. This flips what the accordion is being
   compared against: previously it competed with (c) for real estate on
   the default page (both always-on); now it's a strict presentation
   swap for the existing "Change" gate — same one-tap entry point every
   other variant uses, just a different destination (in-place accordion,
   not `TradeDnaSheet`'s `<Modal>`). See "Recommendation" below for how
   this changes the ship call.

## The three asks, verbatim

**#270 (core ask), TradesHome:**

> "One alternative version of this page is just presenting the manual trade
> calc experience and incorporate the change options naturally (so you add
> and remove players directly from the UI — removing the need to have
> player selection hidden under the change link. League and teams to trade
> with more naturally presenting back outside the change link too. Let's
> mock up a few different versions. Give me options that vary pulling some
> of the change sheet inputs back into the UI directly."

**#272:**

> "I want to make the icons for Draft, Trade, and Free Agents bigger. Also
> we can remove the manual calc tab and instead just have a button wrapped
> into the updated UI we'll be mocking to remove any league or player
> references for 'Manual' calc."

**#279:**

> "Would be a nice attempt to mock up doing it for team and positional
> values too though." (tier labels, extended to aggregate values)

## Grounding — what actually exists vs. what the brief assumed

- **`mockups/polish-lab-2026-08/trades-edit-full-sheet.html` does not
  exist.** The brief pointed at it for structure; `git log --all` shows no
  such path was ever committed to this repo. #257 shipped straight from
  its `status.md` design notes without a surviving mockup file (see
  `docs/feedback/items/257-edit-full-sheet/status.md`). The lab instead
  reverse-grounds the "before" sheet directly from the shipped
  `mobile/src/components/TradeDnaSheet.tsx` (`full` branch, Variant C —
  "Big three + one quiet strip") and follows the phone-frame/current-vs-
  proposed conventions of the nearest precedent,
  `mockups/polish-lab-2026-08/trades-player-first.html`.
- **#269 and #277 are both in-flight, not on `origin/main`, and the brief
  asks every frame to assume they landed:**
  - #269 — team-targeting + league-picker move into the sheet,
    `TradeFinderModeBar`'s three deck-mode chips (Guided/Team/Player) are
    removed.
  - #277 — tier labels replace numeric player values app-wide. This
    pattern already ships in exactly one place today: the Calculator's
    `TradeSide.tsx` (`tierOf` prop, shipped under **#263**) renders a
    `TierBadge` chip instead of the raw `value` number, with numeric
    fallback only for picks/untiered rows. #277 is read here as
    generalizing that one component to every remaining raw-number surface.
- **#272's "icons" — what's real in code.** Bottom tab-bar icons render via
  `tabIcon()` (`mobile/src/navigation/TabNav.tsx:513`), flat `<Icon
  size={22}>`. **Draft** (glyph `flag`) and **Trade** (tab labeled
  "Acquire" since the #245 rename, glyph `trade`) are real 22pt tab icons.
  **Free Agents has no icon anywhere in the app** — it's a text-only chip
  in `TradeFinderModeBar` (`CHIPS` array,
  `mobile/src/components/TradeFinderModeBar.tsx:40-46`) and a pushed
  screen with no tab-bar presence; `mobile/src/components/chalkline/
  Icon.tsx`'s `IconName` union has no `free-agents` glyph. The lab proposes
  **22 → 28pt (+27%)** for all three and borrows the existing `search`
  glyph for Free Agents (nearest semantic fit already in the shared icon
  set) rather than inventing a new SVG — flagged as a real, if small, new-
  icon cost, not a free relabeling.
- **#279's caveat, upfront:** team/positional totals
  (`LeagueSummaryScreen.tsx`'s `posValues`/`total_value`) are **sums**
  across many assets, not single-asset values. The shipped 8-tier ladder
  (`TIER_LABEL`/`ORDERED_TIERS`, `mobile/src/utils/tierBands.ts`) is a
  fixed 8-bucket per-asset classification whose top bucket (`4+ 1sts`) is
  an open-ended catch-all — a competitive roster's total is worth many
  multiples of that ceiling, so bucketing a sum into one of the 8 labels
  is not meaningful without new calibration.

## The spectrum — how the 4 variants differ

Every variant starts from the same **baseline** (BASE-1: #269 + #277
landed — mode chips gone, League+Team live inside the sheet, tier badges
everywhere, bigger Draft/FA icons + Manual-calc-as-button already applied)
and is scored on ONE axis: **how much of `TradeDnaSheet`'s `full` content
moves out of the modal and onto the page.**

| Variant | What moves onto the page | What stays in the sheet | Disclosure mechanism |
|---|---|---|---|
| **(a) Minimal** | League + Team only (2-pill strip) | Outlook, Positions, Trade idea, Specific players, Fairness, Lanes | Modal (shorter) |
| **(b) Calculator-style** | League + Team (header row) + the specific-players section, reshaped into a real add/remove two-column build canvas (`TradeSide.tsx` reused) | Outlook, Positions, Trade idea, Fairness, Lanes | Modal (shorter) — but the deck itself is replaced by the canvas |
| **(c) Maximal inline** | Everything — League, Team, Outlook, Positions, Trade idea, Specific players, Fairness, Lanes | Nothing (sheet deleted); Untouchables keeps its own second-layer Manage sheet | No modal at all |
| **(d) Accordion** *(repositioned 2026-08-09)* | Nothing by default — page is identical to baseline. Tapping "Change" reveals everything as five collapsed accordion rows in place; each still expands its own body on a further tap | Nothing in a `<Modal>` — Change now opens an in-place accordion instead of `TradeDnaSheet`'s full-screen sheet | In-place accordion, gated by the same one-tap "Change" entry every other variant uses (not always-on) |

(a) and (b) both keep a shorter version of the modal, gated by "Change."
(c) removes the modal *and* the Change gate entirely for an always-on
inline panel. (d), after the 2026-08-09 repositioning, keeps the Change
gate exactly like (a)/(b)/baseline — the default page is unchanged — but
replaces what's *behind* it: a full-screen modal sheet becomes an
in-place accordion instead. This is still the "genuinely distinct fourth
point" the brief allowed for, just not in the way originally drawn: (d)
is no longer a denser cousin of (c) (always-on, no gate) — it's a
same-gate, different-destination cousin of (a)/(b) (one-tap Change, but
the reveal is an accordion instead of a modal).

Every frame in every row also carries the three #272/#277 requirements
unconditionally: bigger Draft/Free-agents icons + Manual-calc-as-button in
a utility row, and `TierBadge` chips instead of numeric player values.

## Code-level cost per variant

- **(a) Minimal** — smallest. One new presentational component
  (`TradingWithStrip`, ~60 lines: two pills, two tap handlers). Reuses the
  existing league-switch entry point (TopBar's sheet) for the League pill;
  the Team pill needs either a scroll-to-section prop on `TradeDnaSheet`
  or a new lightweight standalone picker. No engine/state change — this is
  #269's own League/Team state, just given a second entry point. Sheet
  shrinks by two rows since they're answered on-page.
- **(b) Calculator-style** — largest, and the only one that's an
  architecture decision, not a layout one. Reuses shipped components
  (`TradeSide`, `VerdictPanel`/`ConsensusVerdictCard`,
  `PlayerPickerModal`) but requires deciding whether the swipe deck still
  exists underneath the canvas or whether `TradesScreen`'s guided landing
  forks into two render modes. This mock assumes full replacement (canvas
  + a horizontal suggestion rail replaces the swipe stack), which is a
  bigger behavioral change than the other three and needs its own scope
  block before any build estimate is trustworthy.
- **(c) Maximal inline** — moderate-to-large. No new sheet UI to write
  (delete `TradeDnaSheet`'s `full` branch, or leave it dead behind the
  flag), but every control it held gets re-laid-out as a permanent card on
  an already-long screen (`TradesScreen.tsx` is 5,861 lines today). Directly
  re-opens the height problem #257 was built to close — see Tradeoffs.
- **(d) Accordion** *(repositioned 2026-08-09)* — moderate, and now lower
  on the page side specifically: the default landing render (D1) needs
  zero new components — it's the exact `editEntry` + Change gate baseline
  already ships. All the cost is in the destination: swapping
  `TradeDnaSheet`'s `full`-branch `<Modal>` for a collapsible in-place
  list. That list is still a genuinely new shell component (no existing
  accordion pattern anywhere else in the app to reuse styling/behavior
  from — least precedented of the four in the codebase), but every
  expanded body reuses the exact inner JSX `TradeDnaSheet` already renders
  per section — the change is the container, not the controls.

## Tradeoffs (condensed — full rationale is in each frame's caption)

- **(a)** Cheapest, safest, but only answers #270's *second* sentence
  (League/Team). The "add and remove players directly from the UI" ask is
  untouched. Also introduces a real redundancy: the League pill duplicates
  the global TopBar's league switcher.
- **(b)** The only variant that delivers #270's literal first sentence.
  Costs the zero-effort swipe discovery loop that's the app's core PFO
  surface — a brand-new user with no target in mind now faces two empty
  columns instead of an auto-populated card, the same regression the
  `trades-player-first.html` (#211) lab flagged for its own direction (a).
- **(c)** Zero navigation cost to change anything, but re-inflates the
  exact height problem #257's own PRD explicitly rejected even in its most
  conservative option (Variant A, "least risky, least brave" — this goes
  further than that).
- **(d)** *(repositioned 2026-08-09)* No longer competes with (c) for
  re-inflating the height problem #257 fixed — its default page is now
  byte-for-byte (a)/baseline's footprint, not an always-on panel. What's
  left reads close to a strict upgrade over today's shipped sheet: same
  one-tap Change gate as every other variant, but the reveal is an
  in-place accordion instead of a full-screen modal hop. Still the most
  novel interaction pattern in the app (no existing accordion component to
  borrow from) and still leaves the accordion-exclusive-vs-multi-open
  question unresolved. Repositioning raises one new question: since
  content is still gated behind a single "Change" tap, is this
  meaningfully "presenting back outside the change link" per #270's
  literal ask, or is it closer in spirit to (a)/(b) — same gate, nicer
  destination — than to (c)'s always-on inline?

## #279 frame (E1) — what was and wasn't attempted

Mocked: swapping the numeric team-total label above each power-rankings
bar chart column for a pick-equivalent phrase ("≈14 firsts" instead of
"14,820"), reusing the **existing** value→pick-equivalent formula already
live on every trade card (`backend/server.py`'s `_gap`/`pick_equivalent`,
surfaced today as "a Late 2nd" in the Dynasty Value Swing bar) — applied to
a raw total instead of a value delta. Bar heights, position-color
stacking, and rank numerals are untouched; only the human-facing label
text changes.

Explicitly **not** attempted, flagged as open:

1. The roster drill-in (`LeagueSummaryScreen.tsx:1027`,
   `Math.round(p.value)`) is the one part of #279 with a clean, already-
   solved answer — swap in the existing `TierBadge`, no new work, since
   those rows ARE single-asset values.
2. The bar chart's stacked position segments have **no numeric label at
   all today** (color-proportion only). Extending pick-equivalent labels
   down to sub-segments (e.g. "QB: ≈3 firsts" per team) wasn't mocked —
   at small segment sizes a 4-way split of one aggregate total starts to
   read as false precision, and no rounding/threshold rule exists yet.
   This needs product input, not just engineering time.
3. `TIER_LABEL`'s 8-bucket table itself was deliberately NOT reused or
   extended upward (e.g. adding "8+ 1sts", "12+ 1sts" rungs) — that would
   require new calibration of what a roster-scale aggregate should mean at
   each rung, which is a product decision this lab doesn't make on the
   operator's behalf.

## Recommendation

**Updated 2026-08-09** to reflect the D repositioning above. Before the
revision, (d) was scored as the "longer-term" option specifically because
it competed with (c) for the same always-on-inline territory — both
re-inflated the height problem #257 fixed, just to different degrees. That
conflict is gone now: (d)'s default page (D1) is byte-for-byte the same
as (a)/baseline, so it costs nothing extra on first paint. What (d) buys
over (a) is what happens *after* the one tap on Change — every sheet
section, not just League/Team, and no full-screen modal hop to get there.

**(d) Accordion** is now the recommended default ship candidate, ahead of
(a) — it strictly dominates (a) on scope (all sheet content reachable, not
just League/Team) at the same default-page cost, and it's a real upgrade
over today's shipped `TradeDnaSheet` modal (same gate, lighter reveal).
The one real risk against it: it's the least precedented pattern in the
codebase (no existing accordion component to build from), so if the
operator wants the safest, most boring possible ship, **(a) Minimal**
remains the fallback — cheapest, safest, and still the more literal
reading of #270's second sentence taken alone. If the operator's priority
is specifically the "add/remove players directly" experience over
League/Team-and-everything-else surfacing, **(b)** is the one that
actually delivers it, but it should go through its own scope block first —
it's an architecture decision (does the swipe deck survive?), not a
styling one, and the PFO regression risk needs a real answer before build,
not just a mockup caption.

## Open questions for the operator

1. Which single variant (or which two, e.g. a-now/d-later) should move to
   a build scope block?
2. If (b) is chosen: does the swipe deck disappear entirely in guided
   mode, or does the canvas replace it only once a Team is selected
   (keeping zero-effort discovery for the "Any team" / cold-start case)?
3. For #279: is a pick-equivalent label ("≈14 firsts") an acceptable
   permanent replacement for the numeric team total, or is it only wanted
   as a secondary/supplementary label alongside the number? The frame
   mocks full replacement; a hybrid wasn't drawn.
4. For #279's positional segments: is per-position pick-equivalent
   labeling in scope at all, or is #279 satisfied by the team-total swap
   alone (item 1 above, already a clean win) plus the existing
   `TierBadge` roster drill-in fix?

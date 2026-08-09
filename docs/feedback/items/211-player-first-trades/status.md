# #211 — Player-first trades mockup lab · status

**Status:** mockup-only · 2026-08-08 · branch `worktree-agent-aba27261d3ac0e30a`, mockups/polish-lab-2026-08/trades-player-first.html

**Feedback (#211, operator note, verbatim):** "I think the specific player
trade page is better than the current find a trade page. No action needed
as I'm interviewing some other testers first. So just a note."

No build was requested. This item is the operator asking for **mockups
only** exploring that preference, ahead of a real decision once tester
interviews land. Nothing here ships; no flags, no code changes outside
`mockups/`.

## What this is

A design lab, `mockups/polish-lab-2026-08/trades-player-first.html`, laying
out the current shipped behavior of both surfaces side by side, then 3
distinct directions for making the player-first experience more central —
each with rationale and tradeoffs, grounded in the actual code (not
invented controls). Companion doc: this file, for the non-visual
comparison + open questions.

## Code-level comparison (as of `origin/main`, `mobile/src/screens/TradesScreen.tsx`)

Both surfaces are **the same screen** (`TradesScreen`, `TradeDeck` route)
in different `finderMode`s (`'guided' | 'team' | 'player'`, switched
in-place via `TradeFinderModeBar` — `mobile/src/components/TradeFinderModeBar.tsx`),
sharing one target-pin store (`useFinderTargets`: `pinnedGive`,
`pinnedReceive`, `packageMode`). The pin mechanics are **not** actually
different per mode — what differs is how much visual weight targeting gets
and what leads the page:

| | Guided (`'guided'`, default landing) | Player (`'player'`) |
|---|---|---|
| Primary content | Swipe deck (`SwipableTopCard`/`TradeCardComp`) — zero-input, mutual-gain suggestions stream in after a "Find a Trade" tap | Two-column **TRADE AWAY / TRADE FOR** pin board (`playerBoard`/`boardCol`, TradesScreen.tsx:3427-3536, #209 give-left/get-right order) |
| Targeting UI, 0/2+ pins | A **flat single-list** target section buried inside the Controls Card, below Outlook and Fairness rows (TradesScreen.tsx:3537-3634): a Trade-away/Acquire direction toggle, "+ Add player" button, and SEND/GET-tagged chips. Same `useFinderTargets` store, same `targetPickerOpen` picker — just a plainer construction | The spatial two-column board: position-color-dotted rows per column, "+ Add asset" / "+ Add target" inline in each column, `PackageToggle` ("Trade as one package", #174) once 2+ give pins |
| Exactly 1 pin (either mode) | **Identical outcome in both modes** — `singlePin` (TradesScreen.tsx:834-841) fires purely off pin *count*, independent of `finderMode`. Controls collapse to the shipped one-liner ("Pinned: X · Edit", `pinSummaryCard`, already shipped per #243), deck disappears, and `FeaturedTradeWindow` + `AssetIdeasPanel` (Upgrade/Lateral/Downgrade groups, #216/#209) take over | same |
| What "Find a Trade" means | Broad opponent sweep, optionally narrowed by whatever's pinned | Same generate call — player mode has no separate endpoint, just different chrome around the same pins |

**So the two surfaces aren't actually different capabilities** — guided
mode already has a (buried, low-prominence) way to target players. What
the operator is responding to is almost certainly:

1. **Starts from intent, not chrome.** Player mode's two-column board is
   the *first* thing rendered in the section — not one collapsible row
   under Outlook and Fairness. Landing there means declaring who you want
   before anything else competes for attention.
2. **Direct manipulation.** A spatial two-column board with position-color
   dots reads as "build a trade" rather than "configure a filter." The
   flat SEND/GET chip list in guided mode does the same job with far less
   visual identity.
3. **Less black-box.** The deck's zero-effort promise ("we read your
   roster and hand you deals") is also its weakness: the user has no
   visible lever until they scroll to Fairness/lane pills. Player mode
   makes the lever the whole page.
4. **Convergence, not divergence, at the payoff.** Once you're down to one
   pin, both modes render the exact same `FeaturedTradeWindow` +
   `AssetIdeasPanel`. Player mode just gets there in fewer, more legible
   steps (pick → collapse → featured trade) vs. guided mode's implicit
   path (swipe some cards, or dig into the buried target section, or
   never target anything at all).

Guided mode's real advantage is the inverse: **zero required input.** A
brand-new user with no opinion about players yet still gets suggestions.
Player mode's board, with 0 pins, still shows the deck underneath (it
doesn't hard-gate on having a pin — `singlePin` is null at 0 pins, so
`Find a Trade` and the swipe deck both render) — but the two empty columns
lead, which reads as "give me a task" before the deck's implicit "you
don't have to do anything" value ever lands.

## Interplay with #257 (controls-card → edit sheet, in flight this release)

#257 is consolidating the inline Controls Card (Outlook row + Fairness row
+ lane-filter pills + the classic target section) into a full edit sheet,
in the same release these mocks were requested in. That work is not on
`origin/main` as of this lab (checked: no `#257` commits on any branch,
no merged content) — so its exact shape is unknown here.

**None of the 3 directions below resurrect the old inline Controls Card.**
Anywhere a direction needs Outlook/Fairness/lane-filter controls, it routes
through a generic "Edit trade setup" entry point (collapsed pill → sheet),
consistent with #257's direction, rather than reintroducing the
286pt-tall inline card #243 already fought to collapse. The two-column pin
board itself is treated as its own surface, not folded into that sheet —
it's the direct-manipulation surface the operator singled out, and #257 is
about the *other* controls (outlook/fairness/lanes).

**Open question for whoever owns #257:** does the edit sheet also want to
own the pin board (make ALL targeting — 2-col board included — live inside
one sheet), or does the board stay inline as primary content with the
sheet handling only outlook/fairness/lanes? Directions (a) and (c) below
assume the board stays inline; that assumption should be confirmed against
#257's actual scope block before either direction is built for real.

## The 3 directions (see the HTML lab for full visual mocks)

**(a) Player-first as the default landing mode.** `TradeFinderModeBar`
lands on `'player'` instead of `'guided'`; Guided becomes a secondary
"Show me everything" entry rather than the mode-bar's default chip.
*Pro:* directly matches the operator's stated preference; smallest code
change (flip the default `mode` param + reorder/relabel one chip).
*Con:* removes the zero-input path from the front door — new users with
no target in mind hit two empty columns before any suggestion appears;
regresses exactly the time-to-first-value the guided deck was built to
protect (pm-pfo territory). Needs a real cohort read (new vs. returning
users), not just the operator's own preference — which is a power-user
read reacting to an already-familiar tool.

**(b) Hybrid — deck stays primary, seeded by a lightweight intent picker.**
Promotes the *already-shipped* flat target section (today buried under
Outlook/Fairness) to a visible, always-present strip above the deck, and
lets adding one player fall straight into the existing `singlePin`
treatment (featured window + idea list) without ever switching
`finderMode`. *Pro:* almost no new mechanism — reuses the existing
single-direction target section and the existing singlePin convergence;
keeps the zero-effort path fully intact as the default. *Con:* doesn't
give the operator the thing they actually praised (the two-column
board's spatial, direct-manipulation feel) — it's still the flatter chip
list, just promoted in position; adds a permanent row to a screen #243
already audited for being too tall.

**(c) Full merge — one page, pins progressively narrow the deck.** Retires
the Guided/Player mode split. The two-column board (collapsed to a
one-liner when unedited, exactly like today's pin summary) sits
permanently above the deck on every visit: 0 pins → today's full guided
deck underneath; 1 pin → today's featured-window + idea-list (unchanged);
2+ pins → deck stays but regenerates scoped to the package (existing
pinned-give/pinned-receive machinery, unchanged). *Pro:* no mode to
choose wrong — every user sees the same page, and it's exactly as
"player-first" as the user wants it to be, continuously, not as a
discrete mode switch. Most faithfully resolves "the player page is
better" without sacrificing the deck's zero-input case. *Con:* the
biggest real change of the three — `finderMode === 'player'` currently
gates which target UI renders (2-col board) vs. the flat list
(TradesScreen.tsx:3427); merging means that condition goes away and the
board becomes unconditional, which also raises the question above (does
#257's sheet want to own it?). Also flattens Team mode's distinct
identity (scoped-opponent) unless it's kept as a third orthogonal filter
rather than a mode.

## Recommendation

**(c)**, but sequenced behind #257 landing first — building the merge
before the edit-sheet consolidation exists means re-doing the "what's
inline vs. in the sheet" boundary twice. If a mock needs to ship sooner
than #257, **(b)** is the safe interim step (cheapest, smallest surface
area, doesn't foreclose (c) later) — it just doesn't fully deliver what
the operator responded to. **(a)** is not recommended as a real change;
it trades away the deck's core value prop for a single power-user's
preference without a cohort read, but it's included because it's the
cheapest possible mock of "what if we just believed the operator."

## Open questions for the operator

1. Do the tester interviews (in progress per #211's own note) target new
   users, returning users, or both? Direction (a)'s downside is specific
   to first-time / no-opinion users — if the interview pool skews
   power-user, that risk may be overstated.
2. Should Team mode (scoped opponent) become a third orthogonal filter
   alongside the pin board in a merged page (c), or does it stay a
   separate mode regardless of what happens to Guided/Player?
3. Confirm with whoever's building #257: does its edit sheet want to own
   the two-column pin board, or only Outlook/Fairness/lane filters? Blocks
   a real (a) or (c) build either way.
4. Is "Find a Trade" as an explicit button still wanted once a merge (c)
   makes pin count the implicit trigger, or should 1+ pins auto-generate
   (as singlePin already does today, with no button)?

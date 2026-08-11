# Polish Lab — 2026-08-11

Current-vs-proposed design mockups for operator feedback **#297, #298, #299, #302**
(all filed 2026-08-10 against v1.12.0, the currently shipped build). Each page:
faithful recreation of today's screen beside the proposed redesign in 390px
phone frames, rationale below. Chalkline tokens throughout; all assets inline
except the screen-library captures, which are embedded per the hard rule in
`mockups/CLAUDE.md`. Master viewer: `index.html` (one tab per page).

Base: `origin/main` @ `ab9368f`.

| Page | Feedback | What it shows |
|---|---|---|
| [`trades-single-pin-recovery.html`](trades-single-pin-recovery.html) | #298 (repro) / #297 (not a regression) | Both items land on the same surface — the single-pin featured-trade view on TradesHome — so they share a page. Establishes that **#298 is caused by two `singlePin` null-gates** (`TradesScreen.tsx:4232` kills the Find-a-Trade CTA, `:4569` kills the whole deck block and with it every accept/decline path), **not** by the `trades_home_inline` experiment — the same thing happens in the control group. Current frame vs **V1 (recommended)** — the featured window becomes a deck card for the pinned asset, restoring the CTA ("Find more trades") and the accept/decline row + swipe on the existing `advance('like'\|'pass')` path — vs V2, the minimal-diff option that deletes both gates and stacks a compact calculator above the restored deck. Also documents the separate team-path bug (`:1918-1926` wipes the deck without regenerating). For **#297**, a data-notes section: `LineupImpactTable` is local and unexported in `InLeagueCalculator.tsx:999`, was never mounted on any deck/trade-card surface, and `git log -S` shows only additive commits — the likely real cause is that `_starter_impact` returns `None` for non-Sleeper leagues (`server.py:1152-1154`, and v1.12.0 shipped MFL), rendering a **silent `null`**. Proposes the honest-row fix, plus the full phase-2 backend path (batch the computation, serialize in `trade_card_to_dict`, new flag, lift the component) if the deck mount is genuinely wanted. |
| [`league-tile-density.html`](league-tile-density.html) | #299 | League-rankings drill-in roster tiles. Measures the shipped tile at **60pt** (`PlayerCard.tsx` `cardDense: { height: 60 }`) + 4pt row margin = 64pt pitch, and shows why the second line is wasted here specifically: `LeagueSummaryScreen.tsx:1212-1227` passes no `statsSlot`, so line 2 holds one badge and nothing else. **V1 (recommended)** executes the operator's spec literally — tier badge into the right cluster, immediately left of the positional rank — collapsing the tile to **32pt (−47%)** with **no information dropped**; V2 reaches the literal half (30pt) at the cost of forking the shared `Badge` primitive; V3 swaps the badge for a color tick to buy ~24pt of name width. Includes the before/after pt math (728pt reclaimed on a 26-man roster, 4 → 8 players above the fold) and a width stress test showing where long names truncate. |
| [`drilldown-back-affordance.html`](drilldown-back-affordance.html) | #302 | Getting back to all-teams after drilling into one team. **The back control already exists** — `LeagueSummaryScreen.tsx:902-914`, "‹ All teams", ice, `testID="league-summary.roster-close"` — so this page diagnoses *why it isn't findable* rather than adding a missing one: it scrolls away (it lives in the chart-card header above 1,600pt of roster), it's top-**right** where the app's own `subScreenOptions` pattern puts back top-left, it's an 11px `type.label` caption competing with a 16px title, and no system back works because the drill-in is component state (`selectedId`), not navigation — no stack back, no edge-swipe, no `BackHandler`. Two current frames at different scroll depths make the failure visible. **V2 (recommended)** puts a `headerLeft` "‹ All teams" on the already-fixed stack header and swaps the title to the team name — zero vertical cost, iOS convention, permanent; V1 is a 38pt sticky in-content focus bar; V3 a floating pill. V4 (make the drill-in a real navigation push) is drawn as considered-and-rejected, because it would break the deliberate inline League Analyzer layout and #237's shared filter state. |

## Screen-library coverage gaps found while building this

Both League pages and the trades page needed states the library does not have.
Flagged on-page per `screens/CLAUDE.md`, and repeated here because they are
capture requests, not policy exclusions:

| Screen | Missing state | Needed by |
|---|---|---|
| `league-summary` | drill-in / team-focused (manifest has only `loading`, `error`, `populated`, `basis--personal`, `populated--single-format`; the capture flow never taps a bar) | #299 and #302 — this is the only state either item is about |
| `trades` | single-pin (manifest has `loading`, `empty`, `empty--cold`, `error`, `generating`, `format-gate`, `populated`, all on the `release` flag fixture = `control` variant) | #297 and #298 |

Every "current" frame in this lab that depicts one of those states is a
**token-exact reconstruction from source**, with each dimension cited to
`file:line` on the page. The real captures that *do* exist are embedded as
screen-identity anchors. Request the two capture runs before build so the
before/after can be verified against real frames.

## Deviation from the round-2 viewer

`index-round2.html` in the 2026-08 lab inlines each page into an `<iframe
srcdoc="…">`. That technique predates the screen library (shipped 2026-08-09,
`6b8270b`) and is incompatible with it: a `srcdoc` iframe resolves relative URLs
against `about:srcdoc`, so the `<img src="../../screens/mobile/…">` capture
embeds required by `mockups/CLAUDE.md` would silently fail to load — which is
exactly the from-memory-drawing failure that rule exists to prevent. This lab's
`index.html` uses `<iframe src="sibling.html">` instead: captures resolve, and
each page has one source of truth rather than two.

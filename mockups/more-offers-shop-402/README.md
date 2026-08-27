# `more-offers-shop-402/` — design lab for #402/#403 "More offers = shop a player"

> **Rev 2 (2026-08-27).** The operator ruled #402 and #403 one experience
> (`docs/feedback/items/402-more-offers-shop/rulings-2026-08-27.md`): shop is what the
> deck's **give-side "more offers" button** does, presented as an **inline strip below the
> trade chip** on `TradesScreen` — no pushed screen, no Matches long-press entry, no
> `record_elo`. The page now leads with the six **Rev 2** frames (entry + chooser, the
> strip in tier-up / same-value / empty / post-dismiss states); rev-1 sections 1–2 are
> tagged superseded, sections 3–7 (picker, empties, like/refusal rails, undo walk, design
> calls) carry into the strip unchanged. Folder renamed from `shop-a-player-403/`
> (multi-ID fixes live under the lowest ID).

> One page: [`index.html`](index.html). Self-contained HTML, Chalkline tokens, no scripts,
> no external fonts, no network. **Not shipped code** — never import from it and never cite
> it as current app behavior (`mockups/CLAUDE.md`).

**Binding docs (this lab designs against them and re-opens nothing):**
`docs/feedback/items/402-more-offers-shop/{prd,lld-delta,hld-delta,scope,reconciliation-log,rulings-2026-08-27}.md`.
Vocabulary is the one the doc round settled: **Tier up · Tier down · Same value**.

**Viewing note.** Open `index.html` over `file://` to see the embedded real capture. The
`mockups-preview` launch config serves `mockups/` as its document root, so `../../screens/…`
escapes that root and the three §1 images render broken there. Every other frame is pure
HTML/CSS and renders identically either way. This is the standard path prescribed by
`mockups/CLAUDE.md` and is what the other labs use.

---

## The reconstructed-not-captured caveat (read first)

`scope.md` §3 carries a **written waiver**: `screens/` is frozen at **2026-08-11** (D-056
retired the simulator entirely), and it holds **no capture of the single-pin / asset-ideas
surface** and none of the long-press player menu — `screens/mobile/trades/` has only
`empty`, `empty--cold`, `error`, `format-gate`, `generating`, `loading`, `populated`, and
there is no `sheets-player-menu` directory at all. No capture can be requested; the harness
is retired.

Consequently:

- **Every frame tagged `reconstructed from source` on the page is a reconstruction, not a
  capture**, drawn by reading the live source per the waiver's named substitute (the
  code-walk): `PlayerContextMenu.tsx`, `MatchesScreen.tsx` (`menuActionsFor` at `:1568`),
  `TradeCard.tsx`, `PlayerCard.tsx`, `TradeValueBar.tsx`, `Toast.tsx`, `FeedbackFAB.tsx`,
  `RootNav.tsx`, `AssetIdeasPanel.tsx`, `queueCalcTrade.ts`, `ideaToCard.ts`,
  `chalkline/{Button,Badge,TickLabel,Icon,Card}.tsx`. It is never presented as a capture.
- **`mockups/polish-lab-2026-08/asset-ideas-layout{,-v2,-v3}.html` was not consulted.**
  `scope.md` names it explicitly as *not* a substitute.
- **One real capture *is* embedded, because one exists** — §1's host screen,
  `screens/mobile/matches/populated--mutual.png`, captured **2026-08-10T15:03Z**. That
  satisfies rule 1 of the interim posture in `mockups/CLAUDE.md`. **Drift declared:**
  `MatchesScreen.tsx` has 7 commits since that date (`9d983be4`, `14a4ce47`, `248ad68e`,
  `88278100`, `7057d861`, `151e3e29`, `ae0ec6b4`) — mainly #334/#335 segment counts and
  #362 standing offers. It is ground truth for its own build, not for today's pixels.

The fixture pin is **Tee Higgins (WR, CIN, 27 yo)** — chosen because he is on the *YOU SEND*
side of the mutual-match tile in that real capture, so §1's real pane and every reconstructed
pane after it are talking about the same player.

---

## What each state shows, and which requirement it satisfies

| § | State | Satisfies |
|---|---|---|
| 1a | **Matches, real capture.** The host screen, the "Hold a player for options" affordance line, Tee Higgins in *YOU SEND*. | context for R-1 |
| 1b | **Entry menu today, flag off.** `PlayerContextMenu` over the real capture dimmed by the app's own scrim. **One row only** — "Mark untouchable" — because that is all `menuActionsFor` returns on Matches, and only on the give side. | **R-17** (flag off is byte-identical: the row is not pushed, the menu maps an identical list) |
| 1c | **Entry menu, flag on.** The appended `Shop this player` row + hint, copy verbatim from `lld-delta.md` §4.4, testID `player-menu.shop`. | **R-1** |
| 2a | **Loading.** Pin row + mode chips up immediately, **no counter**, **no counts on the chips**, shipped copy "Sweeping rosters…", decision pair disabled at 45%. | R-15 (never an endless spinner), R-2 |
| 2b | **Populated — Tier up, card 1 / 6.** Full screen: header with back chevron (`gestureEnabled:false`), pin identity, three mode chips with `tier_up` active, `1 / 6` counter, the shipped `TradeCard` mounted with `hideMatchStrength` and **no `disposition`**, decision row, FeedbackFAB. | **R-2, R-3, R-4, R-5, R-8, R-13, R-14**, A-11 |
| 2c | **Mid-pager — Tier down, card 3 / 4**, plus a `relaxed` idea carrying the "Stretch — outside your fairness band" line. | **R-3, R-4, R-5**; raises D13 |
| 3a | **Same value, picker default (nothing selected)** + the hint that says an empty selection means WR-for-WR. | **R-10**, R-17/A-6 (`swap_positions` omitted, never `[]`) |
| 3b | **Same value at RB or TE.** Return side obeys; Same-value count drops 3 → 2 while Tier up/down are unchanged. | **R-10, R-11** |
| 3c | **Picker detail strip** — default · two picked · an avoided position omitted, at size. | R-10, R-14 |
| 4a | **Empty — a selection returned nothing.** Names mode + selection, one plain-language "why", `Clear positions — 3 at WR`, and a pointer to the mode chips' real counts. Counter and decision row are *removed*, not disabled. | **R-15** |
| 4b | **Error.** The shipped warn toast "Unexpected server error." (visible in the real `screens/mobile/trades/error.png`) plus an inline recovery block and an explicit "nothing was sent, nothing moved". | R-15 |
| 4c | **Two more empties** — a whole mode empty (no `Clear positions` button, because nothing is selected to clear) and the whole sweep empty (reusing the shipped sentence "No defensible packages found around this asset right now."). | R-15 |
| 5a | **Post-like.** Success toast, card **not** consumed, counter unchanged, Like disabled while in flight. | **R-6**, R-4 |
| 5b | **Every toast this surface can show** — queued · already queued · three refusal lines · dismissed+Undo. All are shipped strings from `queueCalcTrade.ts`; #403 writes no new refusal copy. | **R-6**, R-14 |
| 6a | **Post-dismiss, hold window open.** Card gone, counter `1 / 6` → `1 / 5`, chip count 6 → 5, "Dismissed · Undo" toast, **no network call made**. | **R-8, R-9**, A-8 |
| 6b | **Post-undo.** Card back at its old index, counter and chip restored, no toast. | **R-9** |
| 6c | **The hold-window table** — what has happened at t=0, t<5s, t=5s, on a second dismiss, and on leaving the screen. | **R-9** |
| 7 | Design-call table (D1–D18), the open-against-the-contract list, and the Chalkline audit. | R-14 |

---

## Design calls the PRD did not specify

Full table with rationale and consequences is §7 of the page. Summary — **these are the
things to react to**, each independently strikeable:

| # | Call |
|---|---|
| **D1** | Mode chips carry a **live per-mode idea count** (Plex Mono numeral, chalk-dim). All three groups arrive in one response, so the counts are free — and they are what makes the empty state navigable. |
| **D2** | Counts are **suppressed until the first fetch resolves** (no fabricated `0`, per `components.md` §335). |
| **D3** | **`‹ ›` step buttons flanking the counter**, disabled at the ends. *Beyond the PRD:* not in R-4, no testID in `lld-delta.md` §9 (would need `shop.prev` / `shop.next`). They are `scrollToIndex` calls — no gesture handler, so A-7 is untouched. Strike them and the pager is swipe-only. |
| **D4** | Counter numerals in **Plex Mono**, not a pure Archivo `label`. Keeps the ice tick and chalk-dim; follows the design system's "data numerals are always Plex Mono" and `components.md`'s mono-count convention. Not flare, either way. |
| **D5** | Picker header reads **"Same value at"** (TickLabel). "Swap" deliberately avoided — the reconciliation log rejected it for colliding with `SwapPlayerSheet`. |
| **D6** | **Picker hint copy**, both states: "Nothing picked — ideas come back at WR, the position you're shopping." / "Ideas come back at RB or TE." The LLD requires the first but does not write it. |
| **D7** | A chalk-faint line **explains an omitted (avoided) position**: "QB isn't offered — you're avoiding QB in this league." Without it a shortened row is indistinguishable from a bug. |
| **D8** | Selected picker chip = **`ink-3` well + ice ring, position hex kept on border and text** — resolves how "filled well + ice ring" coexists with a data encoding that may not be replaced. |
| **D9** | Loading **reuses the shipped "Sweeping rosters…"**; counter absent; decision pair disabled rather than hidden (no layout jump). |
| **D10** | Empty state gains a **heading, a one-sentence "why", a `Clear positions — 3 at WR` button** (count-in-label follows the shipped `RankImportSheet` pattern) **and a pointer to the mode chips**. R-15 fixes only the two honest lines. |
| **D11** | **Three empty variants**, not one — selection-empty · mode-empty · sweep-empty. Different causes, different recoveries; a single generic line would offer a "Clear positions" button with nothing to clear. |
| **D12** | Error = **shipped warn toast + inline recovery block**, including "Nothing was sent to anyone, and nothing on your board moved." A toast expires and would leave a blank screen. |
| **D13** | **"Stretch — outside your fairness band" above a `relaxed` card.** ← *the call most worth an operator answer.* See "gaps" below. |
| **D14** | Decision row: labelled **"Dismiss" / "Like"**, ghost left + ice primary flexed right, **scrolling with content** (so `setPinnedBottomBarHeight` is correctly *not* called). |
| **D15** | The entry row is drawn **give-side only**, appended below "Mark untouchable". See "gaps". |
| **D16** | **A like does not consume or advance the card**; the toast is the whole feedback. Liking then dismissing the same card stays possible on purpose. |
| **D17** | Toasts are pushed past the pin identity row using `Toast`'s existing **`topOffset`** prop — the default `top: 32` covers the player being shopped. |
| **D18** | **No next-card "peek"** at the pager edge. `pagingEnabled` snaps by viewport width; a peek needs `snapToInterval` and a different component from the one the LLD specs. D3 carries discoverability instead. |

Two smaller ones, recorded for completeness: **the "Dismissed" toast keeps its one word** —
"Dismissed — 5s to undo" puts a countdown next to an affordance that already says so and goes
stale if `UNDO_HOLD_MS` changes, and "Won't be offered again" is *false for five seconds*,
which is exactly the dishonest-copy failure #403 was warned about. And **long player names
ellipsize** (`Jaxon Smith-Njigba`, `Tetairoa McMillan` both do in the 390pt frame), which is
`PlayerCard`'s real `numberOfLines={1}` behavior, not a layout defect.

---

## Gaps found in the contract while drawing it

1. **The entry-point snippet has no side guard.** `lld-delta.md` §4.4 appends the
   "Shop this player" row for any long-pressed player, but `menuActionsFor`
   (`MatchesScreen.tsx:1568`) is called for **both** the YOU SEND and YOU GET columns, and
   the row that exists today is guarded `side === 'give'`. `direction` is hard-coded
   `'give'` (Q-C), so on a league-mate's player the sweep would ask "what can I get for a
   player that isn't mine". **Needs a ruling: guard it, or accept the row on both sides.**
2. **`relaxed` is unspecified (D13).** #189 relaxed-refill ideas are in the payload, the
   surface this browser replaces prints "Stretch — outside your fairness band"
   (`AssetIdeasPanel.tsx:112`), and `TradeCard` — which #403 may not edit — does not render
   it. Without a line in the pager cell, out-of-band ideas are indistinguishable from
   band-passing ones on the new surface.
3. **R-5's counter styling is internally under-determined.** "A `label`-type `TickLabel` in
   chalk-dim": `TickLabel` has no types, its text is already `type.label` in chalk-dim, and
   it always draws an ice tick. Drawn as ice tick + chalk-dim mono numerals (D4). Nothing in
   R-14 is violated — the tick is ice, not flare.
4. **A-8 must tolerate an absent counter.** The counter is removed on an empty group (there
   is no "1 / 0"), so the structural assertion has to check the expression *where it
   renders*, not that it always renders.
5. **Chip counts and the `X` in `1 / X` must be one expression** for the active mode (D1).
   Two expressions can disagree the moment a local dismiss lands — the same bug class A-8
   exists to catch.
6. **Mode-chip radius diverges from the shipped sibling.** `lld-delta.md` §4.3 specs
   `radii.xs` (2px); the shipped `TradeFinderModeBar` uses `radii.pill`. Drawn per the LLD,
   so the two trade-finder surfaces will not match.
7. **O-1 (`record_elo`) has no visual consequence** and is not drawable — it is verifiable
   only by TestFlight step 9. Nothing on this page depends on which way it is ruled.

---

## Chalkline compliance

No emoji anywhere (every glyph is inline SVG, 20×20 viewBox, `stroke-width 1.75`, square
caps). No gradients, no blur, no `backdrop-filter`, no translucent surfaces — the one
`rgba()` inside a phone frame is the app's own specced scrim `rgba(7,9,12,0.78)`, and the one
shadow is `--shadow-sheet` on the sheet, toast and FAB, where it is allowed. Radius ≤ 8 inside
every frame (4 on buttons/toast, 2 on chips/badges); the 22px phone bezel and the circular
spinner are lab chrome. Fonts are Barlow Condensed / Archivo / IBM Plex Mono only.
**Ice** on the active mode chip, the Like button, the Undo action, the TickLabel ticks and the
"even" value fill. **Flare appears zero times inside any phone frame** (R-14) — only on this
lab's own "reconstructed" tag. Position hexes appear only on position chips, badges and 3px
player rails; the tier teal `#2dd4bf` only on the value bar's pick phrase, where
`TradeValueBar.tsx:205` puts it.

# TestFlight checklist — #402/#403 rev-3: "shop a player" is a pushed window

> **Operator, on the first build carrying branch `feat/shop-window-rework-402`
> (the rev-3 mobile + backend commits; ships as v1.16.10).**
> Under D-056 this checklist is the ONLY runtime evidence mobile gets — every
> step names the regression it would catch. The feature is **LIVE**
> (`trade.shop_asset: true` in prod since v1.16.9, 2026-08-28), so Part A runs
> as-is on the new build with no flag work. Part B needs the flag flipped OFF
> for its duration (`config/features.json` + `POST /api/feature-flags/reload`),
> then back ON.
>
> What changed since the rev-2 checklist: the shop is a **pushed window**
> (rev3-spec §1 — no inline strip, no deck gating to verify), the position
> filter row sits at the **top of the window and applies to every mode**
> (§2), Same value pools by **tier** with an auto-widen-on-zero default
> (§3 + §4a), and the window mounts its own feedback button (#188).

## Part A — flag ON

1. **Entry, one give asset.** On the Trades deck, the button under the players
   you send reads **"More offers"** (not "Keep · more offers"); under the
   players you get it still reads **"Keep · more offers"**. Tap the give-side
   button on a card with ONE give asset → a **new screen** opens ("Shopping
   <name>" in the header) — the deck did NOT clear or regenerate behind it. ☐
2. **Entry, several give assets.** On a card sending 2+ assets, the same tap
   opens a **"Shop which player?"** sheet listing every give-side asset
   (players and picks). Cancel closes it with no other effect (you are still
   on the deck); picking a row opens the window for that asset. ☐
2a. **Chooser pick under pressure — no race, no stale sheet.** *(QA-B
   p8 — the modal-dismiss-then-push seam.)* On a 2+-asset card, tap a
   chooser row and watch the transition closely: the window opens exactly
   ONCE, for exactly the asset you tapped, and the sheet is gone when you
   land (never lingering over the window or reappearing behind the back
   navigation). Then: open the chooser, Cancel, and immediately re-tap
   "More offers" on a DIFFERENT 2+-asset card → the sheet lists the new
   card's assets, never the previous card's. Repeat the pick a few times
   fast — double-tapping a row must not push two windows. ☐
3. **Back returns to the untouched deck.** *(Replaces the rev-2
   deck-holds-still step — the window makes deck interference structurally
   impossible, so what's left to verify is the return trip.)* From the shop
   window, tap the header back control ("‹") → you land on the SAME deck
   card you left, same position, still swipeable. Also: an **edge swipe
   from the left does NOT pop the screen** (the horizontal pager owns that
   gesture — `gestureEnabled: false`); paging tiles near the left edge
   must never accidentally navigate back. ☐
4. **The window has a feedback button.** The FeedbackFAB renders
   bottom-right on the shop window (it is a pushed screen, so it mounts its
   own — a missing FAB here is the #188 regression). Exactly ONE — never
   two stacked. ☐
5. **Modes and counts.** Three chips — Tier up / Tier down / Same value —
   each with a live count; Tier up selected on open. A zero-count mode
   shows named copy (e.g. "No tier-down offers cleared the bar") and the
   pointer line renders ONLY if another mode actually has offers. ☐
6. **The pager is honest.** Swipe horizontally through the tiles; the
   "1 / X" counter tracks exactly, X = tiles actually present. Reaching the
   end does not advance, dispose, or wrap. ☐
7. **Filters on every mode, one selection.** The position chip row sits at
   the TOP of the window, above the mode chips. Select RB in Tier up → the
   tier-up offers re-sweep to ones bringing back an RB. Switch to Tier
   down, then Same value → **the RB selection is still applied** (one
   shared selection; switching modes keeps it). The row shows all four
   positions — QB, RB, WR, TE — INCLUDING the shopped player's own
   position; still no PICK chip. ☐
8. **Same value = the TIER, priced honestly.** *(New — the §3 semantics
   change.)* In Same value, a returned offer may sit noticeably above or
   below the shopped player's value — **that is the tier**: the pool is
   his whole tier of the pick-valuation ladder now, not a ±10% band. The
   card's signed diff still prices each idea honestly (a lopsided
   tier-mate shows its real gap, it is not hidden). If every idea looks
   suspiciously identical in value, the tier scope regressed to the band. ☐
9. **Auto-widen is loud, never silent.** *(New — the §4a ruling.)* Shop a
   player whose position has no tier-mates available in your league (or
   clear all chips on one that shows the notice). With NO chips selected,
   if Same value would be empty at his position it re-sweeps all positions
   and shows **"Nothing at <POS> — showing all positions"** above the
   results. Now select any chip explicitly → the notice disappears and
   ONLY your selection is searched (an explicit choice is never widened);
   clear it → the default (and, if needed, the notice) returns. Tier up /
   Tier down never auto-widen. ☐
10. **Like = a real offer.** Tap ✓ on a tile → success toast IN the window;
    the same trade appears queued (check the counterparty flow you normally
    use). Tap ✓ on the SAME tile again → the same success copy
    (idempotent), not an error. A refusal (e.g. an untouchable involved)
    names the reason, never a generic failure. **Ruled: this like DOES move
    your Elo board.** ☐
11. **Dismiss + Undo, the honest version.** Tap ✕ on a tile → it leaves the
    pager, X drops, "Dismissed · Undo" toast appears. Tap **Undo** within
    5 s → the tile returns exactly where it was, counter restored. ☐
12. **Undo never lies.** Dismiss a tile, then immediately tap a different
    mode chip → the Undo toast disappears AT THAT MOMENT (the dismiss is
    committed; a dead Undo button must never linger). Leaving the window
    (back) inside the 5 s also commits the dismiss. *(QA B-4.)* ☐
13. **Dismissals stick for the session.** Dismiss a tile, switch position
    filters away and back (or switch modes) within a minute → the
    dismissed tile does NOT come back (only Undo restores a tile). Then
    go back and reopen the shop on the same player → a fresh session (the
    server cooldown governs what returns). ☐
14. **Shop a pick.** Open shop on a card whose give side is a draft pick →
    the window works but NO position chips render in any mode (the engine
    ignores them for picks; dead chips would lie). ☐
15. **A fresh window per player.** Shop player A, select a position filter
    and a mode; go back; shop player B → the window opens clean (Tier up,
    no selection, page 1). *(QA/A-2 — a stale filter could become
    invisible and un-clearable.)* ☐
15a. **Merged-view trim (T-1..T-3, operator ruling 2026-08-28 — needs
    `calc.inline_home` lit, as it is in prod; rides this build, not the
    shop flag).** On the guided Find-a-Trade landing (the merged In-league
    page): exactly **one outlook bar** — the calculator's own row with its
    working Change control (the page's minimized "Outlook & filters" row
    is gone); exactly **one Find a Trade** — the canvas action row's cell
    (no full-width page bar anywhere on the page; with an EMPTY canvas the
    cell still runs the model search, and a finished deck's "Deck done"
    card says "tap Find a Trade", naming that cell); **no 1QB PPR / SF TEP
    format chips** and no "values converted" note anywhere on the merged
    page. Then open the **Real values** page (mode-bar chip) → its format
    chips render exactly as before. Also flip to a team- or player-mode
    deck (no inline canvas there) → the page-level Find a Trade bar and
    the minimized outlook row are STILL present — the trim is host-scoped,
    not flag-wide. ☐

## Part B — flag OFF (flip back, reload flags)

16. **Byte-identical deck.** Both keep buttons read "Keep · more offers";
    the give-side tap pins your players and regenerates the deck exactly as
    before this build (progress state, then a re-shopped return side; the
    pin summary row appears; clearing the pin restores the prior deck). ☐
17. **No shop anywhere.** Nothing labeled "Shop", no shop window reachable,
    no chooser, on any screen. (The route stays registered — that is the
    house rule — but nothing navigates to it.) ☐
18. **Single-pin panel unchanged.** The single-pin Upgrade/Lateral/
    Downgrade panel behaves exactly as before — its laterals are still the
    ±band (the tier scope is a shop-only request parameter; §R-4 scoping). ☐

## Part C — old client compat (a device still on v1.16.9, flag back ON)

19. **Tier modes stay position-unfiltered for the old client.** *(B finding
    1's field case; the backend's compat fork is what makes it pass.)* On a
    device still running **v1.16.9** (the rev-2 shop, whose position chips
    exist only under Same value) against this build's backend: select a
    position chip in Same value → the laterals re-sweep to that position
    as before. Now check **Tier up and Tier down** with that selection
    still active: their results must be **unchanged by the selection** —
    the v1.16.9 client sends `swap_positions` expecting laterals-only
    semantics, and the server's compat fork keeps the tier groups
    unfiltered for it. If the tier lists silently shrink to the selected
    position on the old build, the compat fork regressed. ☐

## Known-open at checklist authoring (not blockers for a dark merge)

Nothing. The rev-2 list's resolved items stay resolved (suppression-set fix,
own-position chip, single emitter, three-flag conjunction), and the rev-3
surface changes — window, all-mode filters, tier scope, auto-widen — are all
covered by the steps above plus the reworked `mobile/tests/check-shop-deck.js`
structural suite (142 assertions).

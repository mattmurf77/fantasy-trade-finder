# FB-410 / 411 / 412 / 409 — Operator TestFlight checklist

**Date:** 2026-08-30 · **Build:** the one carrying `claude/fb-410-412-trade-card-polish`
(includes the FB-409 **server** fix `11c8903c`, which is why step 9 is here).

**This is the only runtime evidence this change gets.** Maestro and the simulator are
retired ([D-056](../../../../living-memory/DECISIONS.md)); everything else is structural
guards + the [code-walk](code-walk.md). If a step below fails, that is the regression —
nothing upstream will have caught it.

**Setup:** a Sleeper dynasty league where you have leaguemates with rankings. Default
iOS text size for steps 1–17 (step 12 changes it deliberately, so do it last-ish and put
it back). Flags `calc.canvas_results`, `calc.inline_home`, `calc.merged_layout` on —
i.e. the normal TradesHome you already see.

| # | Screen | Steps | Expected |
|---|---|---|---|
| 1 | TradesHome (guided) | Open with an empty canvas | Action row: `Find a Trade` · **Clear, greyed** · ✓ greyed. **No pager. No ✕ anywhere on the page.** |
| 2 | TradesHome | Add one player to each side by hand (no Find a Trade) | Middle cell still reads **Clear** and is live. Tap it → both columns empty, **one** haptic buzz (not two), no pager appears. **This is the D-157 control and it must still work.** |
| 3 | TradesHome | With a give side on the canvas, tap **Find a Trade** (fair path) | Pager appears: `‹ 1 / N ›`. Anchor receipt above shows `Built around … · Change · Clear`. Middle cell is now a **✕**. **There is no ✕ in the pager row.** |
| 4 | TradesHome | Look at the pager row | `‹ N / X ›` and (model path only) `Clear`. **No "More offers" here** — it moved (step 13). |
| 5 | TradesHome | Tap the middle-cell **✕** | The two-layer decline-reason overlay opens, identical to the deck's. Pick a layer-1 tile, then a layer-2 option → the idea leaves the set, `X` decrements by one, the next idea seeds the canvas. |
| 6 | TradesHome | Tap ✕, then dismiss the overlay **without answering** (backdrop / swipe down) | The idea **stays**, `X` unchanged, canvas unchanged. |
| 7 | TradesHome | Tap ✕, bank a layer-1 tile, then dismiss without reaching layer 2 | The pass **stands**: idea leaves the set, `X` decrements. (Matches the deck exactly.) |
| 8 | TradesHome | **R-6 regression, the important one.** On idea 2 of N, edit the canvas (remove a player), page to idea 3 with `›`, then page back with `‹` | Idea 2 comes back **with your edit** — not blank, and not the engine's original. Then page forward and back again: still the edited version. **Nothing on this screen should ever leave you looking at an empty canvas with a live `2 / N` above it.** |
| 9 | TradesHome | With an idea fronted, tap **✓** | Queues. Toast confirms. Session stays on the idea, pager unchanged. **This is #409** — it must succeed, not say "isn't in this league". If it ever *does* refuse for that reason, the line must read **"Couldn't queue that — one side isn't showing as a league member."** and must **not** name your partner. |
| 10 | TradesHome | Tap the receipt's **Clear** (fair) or the pager's **Clear** (model) | Session ends, canvas blank, pager gone, middle cell back to a greyed **Clear**. |
| 11 | TradesHome | **#411.** Load an idea containing a long name (Christian McCaffrey / Amon-Ra St. Brown / Marvin Harrison Jr.) **and** a draft pick, in both columns | Position tag is on the **second** row, left of team/age. Tier badge still **fully visible** at the right — check the pick row and the highest-tier player row especially. Name is on line 1 alone, one line, smaller than before. **Report every name still showing "…"** — §6.1 predicts those three do and Ja'Marr Chase / Bijan Robinson do not. |
| 11b | TradesHome | **#411 — the newly-found cost (QA-B F-1). On a row for a TOP-TIER player (one whose badge reads `4+ 1sts` or `3 1sts`), read the SECOND row left-to-right** | You should see the position tag, then the team and age, then the tier badge. **Prediction: on the highest-tier rows the team and age are GONE** (squeezed to zero by the tag + badge — §6.2b), showing tag then badge with a gap between. On mid/low-tier rows they should still be readable. **This is the price of the tag move and you were not shown it when you chose it** — if losing team/age there is worse for you than the name truncation it cured, say so and it reverts (chip back to line 1, or the meta line wraps). Worst on a 375pt-class phone; a Pro Max has ~29pt and may still show them. |
| 12 | TradesHome | **#411 Dynamic Type.** Settings → Display & Brightness → Text Size, near max; reopen | Names may ellipsize again — expected (§6.3). Confirm nothing **overlaps**, the tier badge is not covered, and the row's remove ✕ is still tappable. Put the text size back afterwards. |
| 13 | TradesHome | **#412.** While browsing an idea, look at the **give** column | **"More offers" sits directly under that column's "Add player" button**, inside the same card. Nothing similar under the receive column. |
| 14 | TradesHome | Tap **More offers** with exactly one give asset | The shop window opens directly on that player. Press Back → the browse session is **intact**: same idea, same `N / X`, same canvas edits. |
| 15 | TradesHome | Tap **More offers** with several give assets | The "Shop which player?" chooser opens; picking one navigates. Back returns to the session intact. |
| 16 | TradesHome | Clear the session (step 10), then look at the give column | **No "More offers" anywhere on the page.** |
| 17 | Trades (deck) | Switch to Team or Player mode, where the deck still renders | The deck card's own give-side "More offers" chip is **unchanged**, and the card's own ✕/✓ are unchanged. |
| 18 | Trade Calculator (pushed, "Calc") | Open the pushed Real-values page | Action row reads `Find a Trade` · **Clear** · ✓. **No ✕, no "More offers", no compact two-line rows** — this page is unchanged. |

## What to report back

1. **Step 8 is the one that matters most.** It is a real data-loss defect this change
   closes; if paging back ever shows a blank canvas under a live `N / X`, stop and say so.
2. **Step 11: list every name you still see truncated.** The prediction is specific and
   falsifiable — 2 of the 5 pressure-test names fit at the new size and 3 do not
   (Christian McCaffrey, Amon-Ra St. Brown, Marvin Harrison Jr.). Two of those three
   cannot be made to fit on one line at *any* size at or above the Chalkline 11pt floor;
   fitting them would need wrapping, which you declined.
3. **Step 11's tier badge is the other falsifiable prediction.** The worst realistic row
   (a WR priced at `4+ 1sts`) computes to 97.6pt against 97.5pt available — a 0.1pt,
   sub-pixel overhang. If a badge is visibly cut off on the right, the measurement was
   wrong and it needs a real fix, not a tweak.
4. **Step 2 vs step 5 is the D-169 readability test.** The same cell means "clear the
   canvas" in one state and "decline this idea" in the other. If it reads wrong to you on
   device — the way the bare ✕ read wrong to Segrave in D-157 —
   [D-169](../../../../living-memory/DECISIONS.md) is what gets revisited, not the build.

# TestFlight checklist — #384 merged calculator (W0–W4)

**Under [D-056](../../../living-memory/DECISIONS.md) this is the ONLY runtime evidence any of
this can get.** Everything below is structurally verified and has never run on a device.

**Nothing is live.** `calc.merged_layout` ships **false**. Steps 1–3 are the flag-off
regression pass and must run BEFORE the flip — they are the only proof the shipped page is
unchanged, and once the flag is on that before-picture is gone.

| | |
|---|---|
| Build | first EAS build containing `ae605ad` or later |
| Flag | `calc.merged_layout` — **false at ship**. Flip in `config/features.json`, push, Render redeploys (no rebuild) |
| Prereq | a Sleeper league with ≥2 other managers, and a second league to test the League dropdown |

---

## A. Flag OFF — the regression pass (run FIRST, before any flip)

1. **The calculator has two tabs, not three.** Open Trades → Calculator. Tabs read
   **In league** and **Real values**. There is **no Demo league tab**. ☐
2. **Real values mode is unchanged.** Add a player to each side. You get the format chips,
   the consensus verdict, add-on/package suggestions, Share and Clear. No "Sell high" or
   "Target" badges in the picker (they died with the demo boards) and **no second value
   column** — those were the demo's dual-board comparison. ☐
3. **In league mode is unchanged.** Stacked "You send" / "You receive" sections with the swap
   rule between them, the partner chip row, the ghost **Clear trade** button at the bottom.
   No column layout, no bottom action row, no dropdowns, no "Show me around". ☐
4. **Try-before-you-sync still works.** Sign out. The SignIn screen still offers the demo
   session, and taking it lands you in the app. *(This is the #384 conflation trap: the demo
   CALCULATOR was deleted, the demo SESSION must be untouched.)* ☐
5. **The deck is unchanged.** Find a Trade → on a card, tapping ✕ shows the three inline
   **Value / Fit / Neither** tiles, not an overlay. Exhaust a deck: the summary offers
   **See liked** and **Done** only — no "Back to calculator", no "Search without…". ☐

**If any of 1–5 fails, stop.** Flag-off is meant to be byte-identical; a difference here is
a defect in the gating, not in the feature.

---

## B. Flip the flag, then the layout (W1)

6. **Two columns.** In league mode now shows both rosters side by side. Add 3+ players to one
   side: names ellipsize, nothing overflows the screen, and **every row still shows a tier
   badge or a value**. *(The value moving to the row's second line is intended; the value
   DISAPPEARING is the bug this step hunts.)* ☐
7. **The 15% cells.** The bottom row reads **Find a Trade · Include players · ✕ · ✓**. Tap the
   ✕ and the ✓ — both must be comfortably tappable one-handed. **This is the operator-flagged
   risk:** at ~53pt wide they are the tightest targets in the app. ☐
8. **Outlook beat.** The outlook summary sits above the dropdowns; **Change** opens the outlook
   sheet; saving returns you to the calculator with the summary updated. ☐
9. **Dropdowns.** **League** opens the league switcher and switching actually changes the
   league. **Team** opens the partner sheet with R / R* / NR badges; picking one changes the
   right-hand column. ☐
10. **No utility row and no three-tab subnav** anywhere on this page. ☐
11. **One Clear only.** The ghost "Clear trade" button is gone — the ✕ in the action row is
    the only clear. ☐
12. **VoiceOver.** Turn it on. The ✕ announces "Clear the trade" and the ✓ announces "Queue
    this trade for the other manager". Icon-only controls are unusable without this. ☐

## C. Behaviour (W2)

13. **Include players ON** (default). Build a one-sided canvas, tap **Find a Trade**. Every
    served card must contain the asset(s) you put on the canvas. ☐
14. **Include players OFF.** Clear, add a player, toggle it off, tap Find a Trade. Cards may
    now contain anything — and, importantly, the deck must **not** still be constrained by the
    previous run's pins. ☐
15. **The ✕ overlay.** On a card, tap ✕. The reasons arrive **as a sheet over the page**, not
    as inline tiles. Pick a reason → the sheet closes and the deck advances. ☐
16. **The overlay's text path.** Tap ✕ → a reason → **Other**. The composer opens and the sheet
    **stays up** while you type. Send → sheet closes, deck advances. *(Closing on "Other"
    would destroy the input.)* ☐
17. **Dismiss without passing.** Tap ✕, then tap the dim area above the sheet. The sheet closes
    and **the card is still there, undecided**. ☐
18. **End of deck.** Exhaust a deck → **Back to calculator** returns you to the calculator. ☐
19. **Unpin retry.** Pin exactly one player, generate, exhaust the deck. The summary offers
    **Search without <player>**; tapping it clears the pin and restores the pre-pin deck. ☐
20. **Send button.** On a Sleeper league the send control says Sleeper. If you have an MFL or
    ESPN league, confirm it names that platform instead. ☐

## D. The tour (W3 + W4)

21. **Auto-start.** Open the calculator fresh. The tour begins on its own, and its first beat
    points at the **In league** tab. ☐
22. **Nothing interrupts it.** Run the whole tour without dismissing it. No quick-set prompt,
    no outlook banner, no Apple prompt, no push primer, no diff banner, no adaptation moment
    appears at any point — **including in the gaps between beats**, which is the specific bug
    W3 fixes. ☐
23. **Beats point at real things.** Each spotlight lands on the control it names. A beat
    describing a control while highlighting nothing (or the wrong node) is a target
    regression. ☐
24. **It crosses screens.** The tour continues onto the deck after Find a Trade (the ✕/✓ beat,
    the package toggle, the fairness meter) and ends with the closing beat. ☐
25. **Re-runnable.** Tap **Show me around** (top right). The tour restarts **from the
    beginning**, not from where a previous run stopped. ☐
26. **The hold is released.** Immediately after the tour finishes, the interstitials from step
    22 are free to appear again. Navigate away mid-tour and confirm the same — **a leaked hold
    would silently mute every prompt in the app**. ☐
27. **Prefilled arrival is not hijacked.** From a deck card, tap "Edit in calculator". The
    calculator opens with that package and **no tour starts**. ☐

---

## Known-unverified

- Nothing in this document has run on a device. Every claim in the five wave commits is
  structural: type checks, 76 `check-*.js` suites, and named sabotages.
- The **two-column layout on a small screen (SE-class, 375pt)** is the least-proven part.
  Column width, the wrapped value line, and the two 15% cells are all sized by reasoning, not
  by looking at them.
- Tour **copy** is budget-compliant but has never been read aloud on a device against the
  actual controls; a line can be inside 20 words and still be wrong beside the thing it names.

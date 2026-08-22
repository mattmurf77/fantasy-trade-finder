# TestFlight checklist — #384 merged calculator (W0–W5)

**Under [D-056](../../../living-memory/DECISIONS.md) this is the ONLY runtime evidence any of
this can get.** Everything below is structurally verified and has never run on a device.

**Nothing is live.** `calc.merged_layout` ships **false**. Section A is the flag-off regression
pass and must run **before** the flip — it is the only proof the shipped page is unchanged, and
once the flag is on that before-picture is gone.

Rewritten 2026-08-22 against the **current** build. The first version of this document encoded
several things the [e2e review](review-2026-08-22-e2e.md) proved wrong — it told you to tap a
button that is permanently disabled, expected the reason sheet to close on the first tap, and
expected "Back to calculator" to land somewhere it does not. Steps 7, 12, 13, 15, 16, 18, 19, 21,
22, 24, 25, 26 and 27 all changed.

| | |
|---|---|
| Build | first EAS build containing `a52c91e` or later |
| Flag | `calc.merged_layout` — **false at ship**. Flip in `config/features.json`, push, Render redeploys (no rebuild); the client picks it up from `/api/feature-flags` |
| Prereq | a Sleeper league with ≥2 other managers, **and** a second league (step 33), **and** a way to sign in as a user with **zero** leagues (step 31) |

---

## Prerequisites — five other flags, two of them OFF today

`calc.merged_layout` alone does **not** deliver the feature. Set these before section B or the
results will be misleading:

| Flag | Required for this checklist | Today | If it is OFF |
|---|---|---|---|
| `onboarding.v2` | `true` | `true` | Master kill-switch. Every `onboarding.*` flag is ANDed with it — no guided anything, section D is unrunnable |
| `onboarding.guided_avatar` | `true` | `true` | No Analyst bubbles at all. `startCalcTour` returns false, so **"Show me around" does not render** and no tour starts |
| `onboarding.guide_v2` | **`true`** | **`false`** | The v2 layer is inert: **no spotlights** (`targeted = v2 && !!step.target`), no degrade lines, no per-beat display caps, no retirement, and the guide never claims the arbiter slot. `startCalcTour` refuses on this flag, so **no tour runs and the link is hidden**. Section D is entirely unrunnable — see step 36 |
| `ux.prompt_arbiter` | `true` | `true` | The interrupt slot **and** the tour-long hold ride this flag. Ruling 10 becomes inert: quick-set prompts, banners and root modals can interrupt the tour. Step 22 will fail by design |
| `trade.outlook_direction` | either — test both if you can | `false` | `OutlookBiasReceipt` renders nothing. The merged page falls back to an honest **"Not set"** row (`calc.outlook-fallback`) so there is still an outlook section and a Change control. Step 8 has two acceptable outcomes; both are listed |

---

## A. Flag OFF — the regression pass (run FIRST, before any flip)

1. **The calculator has two tabs, not three.** Open Trades → Calculator. Tabs read
   **In league** and **Real values**. There is **no Demo league tab**. The tab that is
   *selected* on a cold open is **Real values**. ☐
2. **Real values mode is unchanged.** Add a player to each side. You get the format chips,
   the consensus verdict, add-on/package suggestions, Share and Clear. No "Sell high" or
   "Target" badges in the picker (they died with the demo boards) and **no second value
   column** — those were the demo's dual-board comparison. ☐
3. **In league mode is unchanged.** Stacked "You send" / "You receive" sections with the swap
   rule between them, the partner chip row, the ghost **Clear trade** button at the bottom.
   No column layout, no bottom action row, no dropdowns, no "Show me around". ☐
4. **Long usernames still wrap, not ellipsize.** In the stacked In-league layout, a partner with
   a long `@username` must lay out exactly as it did before this branch. *(W1 added line clamps;
   they are supposed to be gated on column mode only.)* ☐
5. **Try-before-you-sync still works.** Sign out. The SignIn screen still offers the demo
   session, and taking it lands you in the app. *(This is the #384 conflation trap: the demo
   CALCULATOR was deleted, the demo SESSION must be untouched.)* ☐
6. **The deck is unchanged.** Find a Trade → on a card, tapping ✕ shows the three inline
   **Value / Fit / Neither** tiles, not an overlay. Exhaust a deck: the summary offers
   **See liked** and **Done** only — no "Back to calculator", no "Search without…". ☐
7. **No tour, and no link.** Open the calculator repeatedly. **No Analyst bubble appears**, and
   there is **no "Show me around" link** anywhere on the page. *(The auto-start is gated on
   `calc.merged_layout`; a tour narrating the stacked page would point at controls that do not
   exist.)* ☐

**If any of 1–7 fails, stop.** Flag-off is meant to be byte-identical; a difference here is a
defect in the gating, not in the feature.

---

## B. Flip the flag, then the layout (W1 + W5)

8. **The outlook section is never a silent gap.** Above the dropdowns there is either the
   outlook **receipt** (if `trade.outlook_direction` is on and an outlook is set) or the
   **"Not set" fallback row**. Either way there is a **Change** control, and tapping it opens
   the Trade DNA sheet. *(A page with no outlook section at all is the review-§4 regression.)* ☐
9. **Dropdowns.** **League** opens the league switcher and switching actually changes the
   league. **Team** opens the partner sheet with R / R\* / NR badges; picking one changes the
   right-hand column. ☐
10. **Two columns.** In league mode now shows both rosters side by side. Add 3+ players to one
    side: names ellipsize, nothing overflows the screen, and **every row still shows a tier
    badge or a value**. *(The value moving to the row's second line is intended; the value
    DISAPPEARING is the bug this step hunts.)* ☐
11. **Format chips survived the merge.** The merged header carries the scoring-format chips.
    Tap a different format: every value on the page re-prices, and the **"@user ranked in X —
    values converted to Y"** note appears when the chosen format differs from the league's own.
    *(W1 dropped these entirely; W5 put them back. A merged page with no format control is the
    review-§11 regression.)* ☐
12. **The 15% cells.** The bottom row reads **Find a Trade · Include players · ✕ · ✓**. Tap the
    **✕** — it must be comfortably tappable one-handed. **This is the operator-flagged risk:**
    at ~53pt wide these are the tightest targets in the app. ☐
13. **The ✓ is DISABLED — confirm that it is, and that it says so.** Fill both sides of the
    canvas. The ✓ stays dimmed (~40% opacity) and **nothing happens when you tap it**. Turn on
    VoiceOver and focus it: it must announce **"Queue this trade for the other manager"** *and*
    be reported as **dimmed / unavailable**. **A ✓ that reacts to a tap is the bug here**, not
    the other way round — the queue mechanism does not exist (see Q-029). ☐
14. **VoiceOver on the ✕.** Still with VoiceOver on: the ✕ announces **"Clear the trade"** and,
    with an empty canvas, is reported dimmed. Icon-only controls are unusable without this. ☐
15. **No utility row and no three-tab subnav** anywhere on this page. ☐
16. **One Clear only, and one Find-a-Trade only.** The ghost "Clear trade" button is gone — the
    ✕ in the action row is the only clear. The **"Want ideas instead? Find a trade →"** text link
    is **absent** on the merged In-league page (it bypasses Include players). Switch to Real
    values: the text link **is** there. ☐
17. **Large Dynamic Type.** Settings → Accessibility → Display & Text Size → Larger Text, push it
    to a large accessibility size, then reopen the calculator. The "Include players" cell must
    still be readable (truncation is acceptable, illegibility is not), the two icon cells must
    stay ≥44pt tall, and **no row may lose its tier badge or value**. ☐
18. **SE-class width.** Repeat step 10 on the narrowest device you have (375pt, ideally 320pt).
    The two 15% cells are ~53pt / ~41pt wide there. Nothing overlaps, nothing clips, and the
    compact meta line yields before the tier badge rather than pushing it off. ☐

## C. Behaviour (W2 + W5)

19. **Include players ON, canvas filled (default).** Build a canvas with **one** player on your
    side, tap **Find a Trade**. The deck generates, and **every served card's give side contains
    that player**. ☐
20. **Give side is strict, receive side is not — and that is the current contract.** Put **two**
    players on your give side and **two** on the receive side. Generate. Every card must carry
    **both** of your give players. The receive side only has to contain **at least one** of your
    two — a card offering just one of them is **expected today**, not a bug. *(Symmetry needs an
    API change; Q-029.)* ☐
21. **Include players ON with an EMPTY canvas is unconstrained.** Clear the canvas, leave the
    toggle ON, tap Find a Trade. A normal unconstrained deck generates — no pins, no
    "no trades found". ☐
22. **Include players OFF.** Add a player, toggle it off, tap Find a Trade. Cards may now
    contain anything, and the deck must **not** still be constrained by the previous run's pins.
    ☐
23. **The partner is honoured.** Pick a specific manager in the **Team** dropdown, then Find a
    Trade. The deck is scoped to that manager. Then clear the partner and Find a Trade again with
    a filled canvas: it must still generate (an unscoped sweep), **not** sit empty. ☐
24. **The ✕ overlay — layer 1 does NOT close it.** On a card in this deck, tap ✕. The reasons
    arrive **as a sheet over the page**, not as inline tiles. Tap a tile (**Value / Fit /
    Neither**). **The sheet STAYS UP** and opens layer 2 beneath the tile you tapped. *(Closing
    here is the P0 the review found: the pass is banked, the card goes inert, and layer 2 becomes
    unreachable.)* Pick a layer-2 option → **now** the sheet closes and the next card fronts. ☐
25. **The overlay's text path.** Tap ✕ → a tile → **Other**. The composer opens, the sheet stays
    up while you type, and the keyboard does not cover the Send button. Send → sheet closes, deck
    advances. ☐
26. **Backdrop dismiss, two cases.** (a) Tap ✕, then tap the dim area **without touching a
    tile** → the sheet closes and **the card is still there, undecided**. (b) Tap ✕, tap a tile
    (layer 2 opens), then tap the dim area → the sheet closes and **the deck advances to the next
    card**, because the pass was already banked. Case (b) leaving you on an inert card is the
    regression. ☐
27. **The overlay is scoped to the calculator's deck only.** Three sub-cases, and note that
    **tabbing away and back is deliberately NOT one of them** — the deck is still the one the
    calculator sent. (a) On this deck, tap a different mode chip in the strip (Guided / Team /
    Player) and generate: ✕ now shows the **three inline tiles**. (b) Switch leagues from the top
    bar: inline tiles. (c) Clear the pins (unpin retry, or remove the last pinned asset): inline
    tiles. Any user who never went through the calculator must **never** see the overlay.
    *(Round-2 ruling 1: this calculator only.)* ☐
28. **End of deck — Back to calculator.** Exhaust the deck. Tap **Back to calculator**: you land
    on the calculator in **In league** mode with **your canvas still on it**, and **no tour
    starts**. *(Landing on Real values with an empty canvas is the review-§9 regression.)* ☐
29. **Unpin retry — any pin count.** Build a canvas with **two** assets (e.g. one give, one
    receive), generate, exhaust the deck. The summary offers **"Search without the pinned
    players"** (it names a single player only when there is exactly one). Tap it: the pins clear
    **and a new search runs** — you get cards, not an empty deck. ☐
30. **Both exits appear on both exhausted states.** Repeat step 29 once on a deck that ends in the
    replenishment **summary** card and once on a plain **exhausted** card. Both exits must be
    present in both. ☐
31. **League switch clears the canvas.** With a filled canvas, use the **League** dropdown to
    switch leagues. The canvas empties, the partner resets, and **no player from the old league
    remains on screen**. *(The component holds the canvas in local state; a stale canvas here
    would also evaluate the old opponent against the new league.)* ☐
32. **"Edit in calculator" still lands prefilled.** From any deck card, use **Edit in
    calculator**. You land in **In league** with that card's package on the canvas and the right
    partner selected, and **no tour starts**. ☐
33. **Send button.** On a Sleeper league the send control says Sleeper. If you have an MFL or
    ESPN league, confirm it names that platform instead. ☐

## D. The tour (W3 + W4 + W5)

**Requires `onboarding.guide_v2` = true.** If it is false, run step 41 instead and skip 34–40.

34. **Auto-start, first visit only.** On a fresh install (or after clearing the app's onboarding
    state), open the calculator. The tour begins **on its own**, and its first beat — *"Two ways
    to build a trade. Tap In league to use your real roster."* — spotlights the **In league**
    tab. Note that the page you land on is **Real values**; the beat exists to carry you across.
    ☐
35. **n10 advances on the real tap.** Tap **In league**. The bubble **advances** — it does not sit
    there waiting to be ✕-ed. *(Four beats — the tab, add-a-player, Include players, Find a
    Trade — only move on the real action; a bubble that stalls is the review-§2 P0.)* ☐
36. **✕-ing the first beat ends the run.** Restart the app, let the tour auto-start, and ✕ the
    first bubble **without** switching tabs. **No further beats appear** — you are still on Real
    values, where none of the later targets is mounted. *(A tour that carries on narrating an
    absent page is the review-P2-14 defect.)* ☐
37. **Complete the calculator half.** Run it through: outlook → canvas → Find a Trade → ✓ → add a
    player → Clear → Include players → "Now tap Find a Trade". Each spotlight lands on the
    control the line names. **Two things to watch:** the "Set outlook" button on beat 2 must
    actually **open the Trade DNA sheet** (not just dismiss), and the ✓ beat spotlights a control
    that is disabled — expected today, but note it. ☐
38. **Nothing interrupts it — including between beats.** Run the whole tour without dismissing
    it. No quick-set prompt, no outlook banner, no Apple prompt, no push primer, no diff banner,
    no adaptation moment appears at any point — **especially in the gaps between beats**, which is
    the specific bug the hold exists to fix. ☐
39. **It crosses to the deck, and waits for a card.** Tap Find a Trade on the last calculator
    beat. The calculator is **replaced**, not stacked (press Back afterwards and confirm you do
    not land on a second copy of the deck). The deck's first beat — the ✕ one — must not appear
    **until a real card is on screen**. If generation takes a while, the tour waits; if it never
    arrives, the tour gives up after about **30 seconds** and everything un-mutes. ☐
40. **The deck half runs to the end.** ✕ → swap arrows → package toggle → fairness meter → send →
    the closing beat. Note any beat that spotlights nothing: the package toggle only renders with
    2+ give pins and the fairness help is hidden on a first run, so those two are the likely
    degraders. ☐
41. **Re-runnable, from the top.** Tap **Show me around** (top right). The tour restarts **from
    the very first beat (the In-league tab)**, not from wherever the last run stopped. Do this
    **four times in a row** — the per-beat display cap is 3, and the explicit ask is supposed to
    reset it, so the fourth run must show beats exactly like the first. ☐
42. **Show me around MID-tour.** Start a tour, let it reach beat 3 or 4, then tap **Show me
    around** while a bubble is on screen. The old bubble **disappears** and the new run's first
    beat appears. *(A stale bubble left standing would refuse every beat of the new run and the
    link would look dead.)* ☐
43. **The hold is released on every exit.** Three cases, all of which must un-mute the app: (a)
    let the tour finish; (b) ✕ out mid-tour; (c) **switch tabs mid-tour** — go to League or
    Matches while a bubble is up. In case (c) the bubble must **not follow you** onto the other
    screen, and the interstitials from step 38 must be free to appear again. *(A leaked hold
    silently mutes every prompt in the app for the rest of the session.)* ☐
44. **The auto-start does not come back.** After completing the tour once, force-quit and reopen
    the calculator several times. **No tour auto-starts.** "Show me around" still works. ☐
45. **A user with ZERO leagues.** Sign in as (or create) a user with no league. Open the
    calculator. **No tour starts** — the first beat has no In-league page to carry them to. Note
    what the mode row looks like: today it still renders a **single lonely "Real values" chip**
    rather than hiding itself (known, review P2 #14) — record whether that looks acceptable. ☐
46. **`onboarding.guide_v2` OFF.** Set it false, restart. **No tour starts anywhere**, and there
    is **no "Show me around" link** on the merged page. The merged layout itself is unaffected —
    columns, dropdowns, action row and Include players all still work. *(This is the state the
    app is in today, and it is the state you ship if you flip `calc.merged_layout` alone.)* ☐

---

## Known-unverified / known-imperfect

- Nothing in this document has run on a device. Every claim in the six wave commits is
  structural: type checks, 76 `check-*.js` guards (15 named sabotages re-verified red), and a
  file:line code-walk.
- **The action row is inside the page ScrollView**, not pinned. With 3+ assets per column it
  scrolls out of frame — against the report's one "important" ("fits in the frame"). Steps 10 and
  18 will show this; it is a known gap, not a new defect.
- **The ✓ does nothing and beat n15 says it does.** Step 13 tests the disabled state; the beat's
  copy is still wrong until Q-029 is ruled.
- The **two-column layout on a small screen** and the **spotlight geometry** are the least-proven
  parts. Column width, the wrapped value line, the two 15% cells and where each bubble lands are
  all sized by reasoning, not by looking at them.
- Tour **copy** is budget-compliant but has never been read on a device beside the actual
  controls; a line can be inside 20 words and still be wrong next to the thing it names.

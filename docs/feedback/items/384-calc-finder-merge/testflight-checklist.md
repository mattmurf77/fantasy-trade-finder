# TestFlight checklist — #384 merged calculator (W0–W7)

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

**Amended 2026-08-22 for W6-A ([D-152]).** The ✓ cell is no longer a disabled control — it queues
the package for the counterparty through `POST /api/trades/queue`. Step 13 is rewritten from
"confirm it is dead" to the happy path, and **13a / 13b are new**: the two refusal paths. 13a
needs a second account or a cooperative league-mate, because the whole contract is that the route
reads *their* preferences — and that is exactly the half no structural test can prove. Steps 7a
and 37 also changed.

**Amended again 2026-08-22 for W6-B ([D-153]).** Three operator rulings landed at once and they
change what section C tests, not just how. **Find a Trade now forks**: an EMPTY canvas runs the
modeled deck exactly as before, a canvas with assets on it runs a **fairness-only** package search
whose every card gives away exactly what you built. The **Include-players toggle is gone** — the
canvas is always the anchor — so steps 12, 16, 17 and the whole of C changed, and the old steps
19–22 (include ON / include OFF / receive-side asymmetry) are **replaced** by 19–22b. The **tour is
seven calculator beats, not nine**, and it deliberately ends with the canvas EMPTY so the run
finishes in the modeled cards: steps 35, 37 and 39 changed and **37a is new** (spotlight tracking
under scroll, which no structural check can see).

| | |
|---|---|
| Build | first EAS build containing the W6-B commit (the fair-package fork) or later |
| Flag | `calc.merged_layout` — **false at ship**. Flip in `config/features.json`, push, Render redeploys (no rebuild); the client picks it up from `/api/feature-flags` |
| Prereq | a Sleeper league with ≥2 other managers, **and** a second league (step 33), **and** a way to sign in as a user with **zero** leagues (step 31), **and** — for steps 13a/13b — a second account (or a cooperative league-mate) in the same league who can set an untouchable |
| Flags for the ✓ | `trade.likes_you` must be ON, or every ✓ answers `likes_you_off` by design. `trade.preference_lists` must be ON for step 13a |

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
7a. **The queue route does not exist either.** The stacked page has no ✓ cell at all, so there is
   nothing to tap — but the ROUTE is flag-gated too (`POST /api/trades/queue` → 404
   `feature_disabled`). Nothing to do by hand here; noted so that a build which somehow shows a
   ✓ flag-off is understood as a gating defect, not a cosmetic one. ☐

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
12. **The 15% cells.** The bottom row reads **Find a Trade · ✕ · ✓** — three cells, 70/15/15.
    There is **no "Include players" toggle** (W6-B removed it; the canvas is always the anchor).
    Tap the **✕** — it must be comfortably tappable one-handed. **This is the operator-flagged
    risk:** at ~53pt wide these are the tightest targets in the app. ☐
13. **The ✓ QUEUES the trade (W6-A, [D-152]) — the happy path.** With **no partner** picked, or
    with only one side filled, the ✓ is dimmed (~40%) and inert — that part is unchanged. Now
    pick a partner in the **Team** dropdown and fill **both** sides with a trade where **you are
    the one giving up more value** (check the verdict bar: it should read in their favour). Tap
    the ✓. Within a second a toast reads **"Queued for @name — it'll show in their suggestions."**
    and you get a success haptic. **Tap it a second time**: the toast now reads **"Already queued
    for @name."** — the same trade must never be queued twice. Turn on VoiceOver and focus the
    control: it announces **"Queue this trade for the other manager"**, and is reported dimmed
    only when there is no partner or the trade is half-built. ☐
13a. **The ✓ REFUSES honestly — the untouchable case.** This one needs a second account, or a
    league-mate willing to help, because it tests **their** preference list.
    **Setup:** on the counterparty's device/account, in this league, long-press one of THEIR
    players and mark them **untouchable** (`trade.preference_lists` is on).
    **Test:** back on your device, build a trade that **asks for that player** and tap ✓. The
    toast must name them and say why: **"@name has someone in this trade marked untouchable."**
    Nothing is queued — check your **Awaiting them** list and confirm the trade is NOT there.
    *(This is the whole point of the contract: a refusal is specific, and it records nothing.
    A generic "couldn't queue that", or a success toast for a trade their own settings would
    have swallowed, is the defect.)* ☐
13b. **The ✓ refuses a trade that loses THEM value.** Build the reverse of step 13 — you take
    their best player for one of your cheap ones — and tap ✓. The toast reads **"@name's board
    reads this as a loss for them, so it won't surface."** Again: nothing in **Awaiting them**. ☐
14. **VoiceOver on the ✕.** Still with VoiceOver on: the ✕ announces **"Clear the trade"** and,
    with an empty canvas, is reported dimmed. Icon-only controls are unusable without this. ☐
15. **No utility row and no three-tab subnav** anywhere on this page. ☐
16. **One Clear only, and one Find-a-Trade only.** The ghost "Clear trade" button is gone — the
    ✕ in the action row is the only clear. The **"Want ideas instead? Find a trade →"** text link
    is **absent** on the merged In-league page (it would bypass the canvas). Switch to Real
    values: the text link **is** there. ☐
17. **Large Dynamic Type.** Settings → Accessibility → Display & Text Size → Larger Text, push it
    to a large accessibility size, then reopen the calculator. The "Find a Trade" label must still
    be readable (truncation is acceptable, illegibility is not), the two icon cells must stay
    ≥44pt tall, and **no row may lose its tier badge or value**. ☐
18. **SE-class width.** Repeat step 10 on the narrowest device you have (375pt, ideally 320pt).
    The two 15% cells are ~53pt / ~41pt wide there. Nothing overlaps, nothing clips, and the
    compact meta line yields before the tier badge rather than pushing it off. ☐

## C. Behaviour (W2 + W5)

19. **EMPTY canvas → the MODELED deck.** Clear the canvas completely and tap **Find a Trade**.
    You land on the normal deck: the progress strip ("n/11 opponents searched") appears, cards
    stream in, and the deck behaves exactly as it does from the Trades tab. **This is the fork's
    default half and the one the tour ends on** — an empty canvas must never produce a
    fairness-only deck. ☐
20. **FILLED canvas → fair packages, and every card gives away YOUR canvas.** Put **one** player
    on your give side and tap Find a Trade. There is **no progress strip** — the deck arrives in
    one shot, because this is a synchronous sweep and not a job. Now check the contract on every
    card you swipe through: **the give side is exactly the player you put on the canvas**, nothing
    added, nothing dropped. Then repeat with **two** give players: every card's give side carries
    **both**, always. *(A card giving away something you did not build is the one defect this
    whole route exists to prevent.)* ☐
21. **The receive side leads but does not gate.** Add a player from the partner's roster to your
    **receive** side alongside a give player, then Find a Trade. The **first cards** contain that
    player. Keep swiping: cards that do **not** contain them still appear further down. That is
    correct and deliberate — the receive side is a preference, not a filter, so you are never
    handed an empty deck for asking. ☐
21a. **A receive-side asset the partner does not own costs nothing.** Pick a specific partner in
    the **Team** dropdown, then put a player from a **different** team on your receive side. Find
    a Trade still returns a full deck (nothing sorts first, which is fine). It must **not** show
    "no trades found". ☐
22. **A give-side untouchable refuses out loud.** Long-press one of your own players and mark them
    **untouchable**, then put that same player on the give side and tap Find a Trade. The deck is
    empty rather than showing trades that contradict your own list. *(Your rule, your canvas — the
    honest answer is nothing.)* Unmark them before continuing. ☐
22a. **The fair cards are real deck cards.** On a fair deck: tap **✕** on a card (the reasons
    overlay behaves exactly as in section C below), tap **✓** on the next one, and swipe a third.
    None of them errors, and none of them freezes the card. Then tap ✓ on the **same** card twice
    — it must not double-record. *(These cards were never minted by the generator; this is the
    step that proves the reconstruct path works on them.)* ☐
22b. **Search all trades.** Swipe a fair deck to the end. The end-of-deck card offers **Back to
    calculator** and **Search all trades** — and **no "Search without …"** button (there are no
    pins on a fair deck). Tap **Search all trades**: the modeled deck generates for the same
    partner, with the progress strip, and the cards are no longer limited to your canvas. ☐
23. **The partner is honoured, on both forks.** Pick a specific manager in the **Team** dropdown,
    then Find a Trade with a **filled** canvas: every card's counterparty is that manager. Repeat
    with an **empty** canvas: the modeled deck is scoped to them too. Then clear the partner and
    Find a Trade again with a filled canvas: it must still generate (an unscoped sweep across the
    league), **not** sit empty. ☐
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
    there waiting to be ✕-ed. *(Two action beats — the tab and Find a
    Trade — only move on the real action; a bubble that stalls is the review-§2 P0.)* ☐
36. **✕-ing the first beat ends the run.** Restart the app, let the tour auto-start, and ✕ the
    first bubble **without** switching tabs. **No further beats appear** — you are still on Real
    values, where none of the later targets is mounted. *(A tour that carries on narrating an
    absent page is the review-P2-14 defect.)* ☐
37. **Complete the calculator half — SEVEN beats, ending on an empty canvas.** Run it through:
    In-league tab → outlook → canvas → Find a Trade → ✓ → *"Add players you'd move and we'll find
    trades that include them."* → *"Now tap Find a Trade — start with the canvas empty."* Each
    spotlight lands on the control the line names. **Four things to watch:** (a) the add-players
    beat is **informational** — tap anywhere to move past it, and **do not add a player**, which
    is what the final beat then asks of you; (b) there is **no Clear beat and no Include-players
    beat** (both retired with W6-B); (c) the "Set outlook" button on the second beat must actually
    **open the Trade DNA sheet**, not just dismiss; (d) the ✓ beat (n15) says *"The check queues
    this trade for the other manager, if it fits their preferences"* — since W6-A that is
    literally true, so the control it spotlights should be **live** whenever a partner is picked
    and both sides are filled. A dimmed ✓ under those conditions is a defect. ☐
37a. **The spotlight tracks the page as it scrolls.** On any beat whose target sits below the fold
    (the canvas, the action row), **scroll the page while the bubble is up**. The highlight ring
    must move **with** its control, staying locked to it the whole way. A ring that stays put
    while the page slides underneath is the B1 regression this page's `onScroll` fixes — and it is
    invisible to every automated check. ☐
38. **Nothing interrupts it — including between beats.** Run the whole tour without dismissing
    it. No quick-set prompt, no outlook banner, no Apple prompt, no push primer, no diff banner,
    no adaptation moment appears at any point — **especially in the gaps between beats**, which is
    the specific bug the hold exists to fix. ☐
39. **It crosses to the MODELED deck, and waits for a card.** Tap Find a Trade on the last
    calculator beat **with the canvas empty**, as the beat asks. You land on the **modeled** deck
    — the progress strip appears and cards stream in. *(This is the operator's stated goal for the
    tour: "the tour ends with them in the modeled cards." A fairness-only deck here means the
    canvas was not empty.)* The calculator is **replaced**, not stacked (press Back afterwards and
    confirm you do not land on a second copy of the deck). The deck's first beat — the ✕ one —
    must not appear **until a real card is on screen**. If generation takes a while the tour
    waits; if it never arrives it gives up after about **30 seconds** and everything un-mutes. ☐
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
    columns, dropdowns and action row all still work. *(This is the state the
    app is in today, and it is the state you ship if you flip `calc.merged_layout` alone.)* ☐

---

## G. The device-feedback fixes (W7) — run this on 1.16.x after (126)

Six reports off build 1.16.0 (126). These steps exist to confirm each one is gone, and they are
the ONLY runtime proof any of it gets — none of it ran on a device before shipping.

**Requires `calc.merged_layout` = true, `onboarding.guide_v2` = true, and onboarding state cleared
(a `calc_tour_completed` receipt retires the auto-start).**

50. **First landing is correct without a re-run.** Cold-start the app, go to the Acquire tab →
    **Manual calc**. Let the tour auto-start. The very first spotlight ring sits **exactly on the
    In league tab** — not offset left, not floating in empty space. Do NOT tap "Show me around"
    first; the point of this step is that the FIRST landing is right. *(Report 1: the tour used to
    measure while the push animation was still sliding the screen in.)* ☐
51. **…and it survives the page filling in.** While that first beat is up, watch the ring as the
    rosters finish loading and the page gets taller. The ring **stays on the In league tab**. ☐
52. **The outlook beat highlights the outlook row.** Tap **In league** to advance. Beat 2 —
    *"Set your outlook first…"* — now draws a ring around the **Outlook row** (the receipt, or the
    "Outlook · Not set" fallback row if `trade.outlook_direction` is off). Both are correct; only
    one of them renders. *(Report 2.)* ☐
53. **"Set outlook" still opens the sheet.** Tap the button in the bubble. The Trade DNA sheet
    opens, and the tour moves on. ☐
54. **Every calculator beat shows the avatar AND the bubble, next to its ring.** Walk the rest of
    the calculator half — canvas → Find a Trade → ✓ → Add a player → Find a Trade again. For
    **each** beat: the ring is on the right control, AND the Analyst + bubble are **adjacent to
    that ring** (directly above it, or directly below it if there is no room above). No beat shows
    a ring on its own, and no bubble sits under the status bar or the "Calculator" header.
    *(Report 3 — five consecutive beats used to show a ring with no Analyst.)* ☐
55. **Next buttons, not screen taps.** Each of those beats carries a **Next** button inside the
    bubble. Tapping the page background does **nothing**. *(Report 6.)* ☐
56. **Scrolling works during a beat.** With any of those bubbles up, drag the page. It **scrolls**,
    and the ring **tracks its control** as it moves. *(Report 5a — a tap beat used to mount an
    invisible full-screen catcher that ate the gesture.)* ☐
57. **Find a Trade with the canvas empty** (beat n18 is an action beat — no Next button, it waits
    for the real tap). You land on the modeled deck. ☐
58. **The deck beats keep the avatar and hit their targets.** On the deck: the ✕ beat rings the
    card's ✕; the **swap** beat rings the **swap arrow on the first give-side player row** — not
    the whole card, not nothing *(report 4)*; the package beat rings the package toggle; the
    fairness beat rings **the top card's value meter** (retargeted in Wave A — see step 70; it
    used to name the ⓘ in the "Trade fairness" row, which does not mount on a first-run deck).
    Every one shows the Analyst beside its ring. ☐
59. **The send beat scrolls its button into view.** When the *"Sending goes straight to your
    league"* beat comes up, the **Send** button is **visible on screen** — the page scrolls itself
    to bring it in if it was below the fold — and the ring is on it. *(Report 5b.)* ☐
    - Off Sleeper (MFL/ESPN) the line is the shorter *"Sending goes straight to your league."*
      with no password claim, and it rings the same control. ☐
    - With `trade.send_in_sleeper` OFF the button does not render; the beat then shows its
      **degrade** line and **no ring**. That is correct, not a bug. ☐
60. **The last beat says Done.** The closing beat's button reads **Done**, not Next. Tapping it
    ends the tour: no bubble is left floating over the deck, and the next interstitial the app
    wants to show is free to appear. ☐
61. **Re-run is still clean.** Go back to the calculator and tap **Show me around**. The whole
    thing runs again from the top with the same placements. ☐
62. **Regression — the OTHER guided beats still work.** Fresh install, sign in, and let the
    first-run deck tour run (swipe hint / provenance chip / trio entry). Those beats are untouched
    by this wave; confirm none of them lost its avatar or its ring. ☐

---

## H. Wave A — the 2026-08-23 notes (run on the first build after `feat/tour-wave-a`)

Segrave's second pass, off build **128** — i.e. AFTER the W8 fixes, so none of it can be waved
off as already-shipped. Two of these fix a **race** that the simulator hid behind a warm cache
(that is exactly how W8 passed while note 12 stayed open), so a cold run is the point:

> **Before steps 63–69, force a cold league load.** Fully quit the app (swipe it out of the app
> switcher) and relaunch, or switch to a league you have not opened this session. A warm React
> Query cache resolves the rosters instantly and the race you are testing for cannot happen.
> Also clear onboarding state — a `calc_tour_completed` receipt retires the auto-start.
>
> Requires `calc.merged_layout` = true and `onboarding.guide_v2` = true.

**The parks (notes 12 + 14)**

63. **The outlook beat lands on a COLD page.** Cold-start, go to the calculator, let the tour
    auto-start on *"Two ways to build a trade…"*, and tap **In league**. The page shows
    *"Loading your league…"* — and **the Analyst waits**: no bubble, no ring, nothing during the
    load. When the league content appears, beat 2 (*"Set your outlook first…"*) comes up **with a
    ring around the Outlook row**. *(Note 12: it used to fire during the load and degrade to a
    ringless bubble.)* ☐
64. **…and it does not wait forever.** Repeat step 63 with the device in airplane mode so the
    league never loads. After ~10 s the tour **ends quietly** — no stuck bubble, no permanently
    silent app. Turn the network back on, go to any other tab, and confirm the app's normal
    banners/prompts still appear. *(A wedged park would mute every interstitial for the rest of
    the session.)* ☐
65. **A warm re-run does NOT wait.** With the league already loaded and the tour finished, tap
    **Show me around**, then **In league**. Beat 2 appears **immediately** — no ~10 s pause.
    *(The ready signal is a level, not a one-shot event; an edge-triggered park would stall here.)* ☐
66. **The Analyst stays out of the way while you edit the outlook.** On beat 2, tap **Set
    outlook**. The Trade DNA sheet opens and **no bubble appears** over or behind it — check the
    edges of the sheet as well as the top and bottom bands. Change something, tap **Done**. Only
    *then* does beat 3 (*"This is your canvas…"*) appear, on top of the page. *(Note 14: it used
    to render behind the sheet the moment you tapped the button.)* ☐
    - Repeat closing the sheet with the **backdrop tap** instead of Done: same result. ☐
    - Repeat with the **system back gesture**: same result. ☐
67. **Skipping the outlook does not stall the tour.** Re-run, and on beat 2 tap the small **✕** in
    the bubble instead of Set outlook. The tour carries straight on to beat 3 — **no ~10 s pause**.
    *(The park is taken only when the accept actually opened a sheet.)* ☐

**The outlook sheet's bottom margin (note 13)**

68. Open the outlook sheet on a **home-indicator device** (any Face ID iPhone). The bottom-most
    control is **clear of the home indicator** with visible breathing room below it — the panel no
    longer looks cut off at the bottom. Scroll the sheet to its end to check. ☐
    - Same check for the **Untouchables** layer and the **roster picker** inside it. ☐

**The labelled Clear button (note 15 / [D-157](../../../../living-memory/DECISIONS.md))**

69. On the In-league calculator, the action row reads **Find a Trade** · **Clear** · **✓**. Clear
    is a **word**, not a cross. All three cells sit on one line with no truncation and no text
    smaller than the rest of the page — check on the **smallest device you have** (SE-class). ☐
    - Add a player to a side: Clear becomes enabled and clears the canvas. With the canvas empty
      it is dimmed. ☐
    - VoiceOver still reads it as "Clear the trade". ☐
    - Find a Trade is still visibly the **primary** action (ice outline + ice text); Clear is not. ☐

**The fairness beat (note 17)**

70. **The fairness beat rings the meter, on a FIRST-RUN deck.** This needs a genuinely new user —
    fresh install or cleared onboarding state — because the bug only appeared there. Run the tour
    to the deck half. The beat *"The meter is the verdict. Tap Why? for how we judged it."* draws
    a ring **around the value bar on the top card**, and the page **scrolls it into view** if it
    was below the fold. ☐
    - Tap **Why?** inside that ring: the verdict explanation expands. The line is telling the
      truth about a control that exists. ☐
    - *(It used to point at the ⓘ in the "Trade fairness" row, which does not render for a
      first-run deck — so the beat popped with no ring and no scroll.)* ☐

**The onboarding beats get buttons (notes 3 + 4 + 8)**

71. **The very first thing a new user sees promises a walkthrough.** Fresh install → sign-in
    screen. The Analyst says *"I'm The Analyst. Stick with me — I'll walk you through finding
    your first trade."* and the bubble has a **Next** button. Tapping the page background does
    **nothing**. ☐
72. **A wrong username still explains itself, with a button.** Type a username that does not
    exist. The error beat appears **with a Next button**. ☐
73. **The first-card beat says where the prices come from.** Finish sign-in and let the first deck
    land. The beat reads *"Both sides should want these. Priced on consensus now; your swipes
    teach me your values."* — with a **Next** button. ☐
74. **Scroll is not swallowed anywhere in onboarding.** With **any** of these onboarding bubbles
    up, drag the deck. It scrolls. *(A tap-advance beat used to mount an invisible full-screen
    catcher.)* ☐
75. **The first like still chains correctly.** Swipe right on a card. The *"Logged…"* beat appears
    with a **Next** button. Tap it — and the Apple save-moment prompt still follows the way it did
    before. ☐
    - Then repeat, and instead of tapping Next, **swipe the next card**. The bubble goes away and
      the same chain runs. *(This is the beat's real bound now that it has no timer.)* ☐
    - If you have an "Awaiting them" entry, the other variant of this beat still shows
      **See it →** / **Later** and *not* a bare Next. ☐
76. **The tour's last line says Done.** Reach *"That's the tour."* — its button reads **Done**,
    not Next. ☐

**The demo link (note 2)**

77. Fresh install → sign-in screen. There is **no** "Try the app on a sample league" link, in any
    state — including after a failed sign-in and after a Sleeper timeout. ☐
78. Nothing else on that screen moved: Apple sign-in, the username field and the not-found copy
    all behave as before. ☐

## I. Wave B0 — the layout merge (`calc.inline_home`, [D-158])

**Added 2026-08-24, branch `feat/inline-home-b0`. Unrun.** This wave moves the In-league
calculator ONTO the guided landing and trims the pushed page to Real values. `calc.inline_home`
ships **false**, so **I1 is the pass that matters today** — the whole claim of the wave is that
with the flag off nothing moved, and once it is lit that before-picture is gone.

`calc.merged_layout` must be **true** for any of I2 to work: the two routes the inline canvas
calls are gated on it and 404 `feature_disabled` otherwise.

**Known before you start:** with this flag on the calculator tour does **not** run — not the
auto-start, not "Show me around". Beat n10 says "Tap In league" and this wave deletes that tab;
Wave B retargets the beats. Its absence is the design, not a bug to report.

### I1. Flag OFF — the regression pass (run FIRST, before any flip)

79. **The Acquire tab looks exactly as it did.** Open Find a Trade. There is **no** calculator
    canvas above the deck, the chip strip reads **Guided · Team · Player · Calc · Free agents**
    (with Draft/Today if their flags are on), and the fourth chip says **`Calc`**, not "Real
    values". ☐
80. **The pushed calculator still has two tabs.** Tap `Calc`. The mode row shows **In league**
    and **Real values**, In league is selectable, and the calculator tour still auto-starts on a
    first visit (or offers "Show me around" on the In-league tab). ☐
81. **Edit-in-calculator still pushes.** From a deck card, use its edit action. You land on the
    pushed Calculator screen, in **In league** mode, with both sides preloaded — a PUSH, with a
    back button, not a scroll on the same page. ☐
82. **End of deck still offers Search all trades.** Build a canvas with a give side on the pushed
    page, tap Find a Trade, swipe the fair deck to the end. The summary card shows **Back to
    calculator** and **Search all trades** (not an unpin-retry). ☐
83. **The ✓ still queues.** On the pushed In-league page, build a complete trade with a partner
    and tap ✓. You get the same success or reason-specific refusal toast as before, once. ☐

### I2. Flip `calc.inline_home` to true, reload flags, restart the app

84. **The canvas is on the landing.** Open Find a Trade (guided). The In-league calculator
    renders **above** the deck under a "Build a trade" label — with its format chips, league and
    team dropdowns, both roster columns, verdict, eveners, lineup impact, share and Send. Nothing
    from the In-league page is missing. ☐
85. **The existing deck is still there, underneath.** If a deck was already generated (pregen or
    an earlier session), it still shows below the canvas — both entry actions visible at once. ☐
86. **No suggestion rail.** There is **no** horizontal "Or tap a suggestion to load it" strip
    between the canvas and the deck. The deck below is the rail. ☐
87. **No "Show me around" link** on the inline canvas, and no Analyst bubble appears when you
    open the Acquire tab or the pushed Calculator page. ☐
88. **Find a Trade with an EMPTY canvas** (pick a partner, add nothing). Results replace the deck
    below **on this page** — no push, no back button, no second copy of the landing. The cards
    are ordinary modelled trades and there is **no** "Built around" row. ☐
89. **Find a Trade with a GIVE side.** Add one of your players, tap Find a Trade. A **"Built
    around <player>."** receipt appears above the results, and every card gives away exactly
    that player. Add a second player and re-run: the line reads **"Built around <player> +1."** ☐
90. **Change.** Tap **Change** on the receipt. The page scrolls back to the canvas and the assets
    you built are **still there** — nothing was cleared. ☐
91. **Clear.** Tap **Clear**. The receipt disappears and a normal modelled deck is generated for
    the same partner. Swipe that deck to the end: the summary offers **Back to calculator**, and
    — because the receipt is gone — it may offer the unpin-retry, but **not** two ways to do the
    same thing. ☐
92. **The receipt replaces the end-of-deck exit.** Re-run an anchored search (step 89), then
    swipe the fair deck to the end. The summary card must **NOT** show "Search all trades" —
    that exit is the receipt's Clear now. ☐
93. **Edit-in-calculator loads the canvas in place.** From a deck card, use its edit action. The
    page **scrolls up** to the canvas and both sides are loaded with that card's players. No
    push, no back button. Do it again with a different card: the canvas reloads with the new
    package (not the first one). ☐
94. **Back to calculator, in place.** Swipe a pinned deck to the end and tap **Back to
    calculator**: same scroll-to-canvas behavior, pins loaded. ☐
95. **The ✓ works from the landing.** Build a complete trade with a partner in the inline canvas
    and tap ✓. You get the same toast you got on the pushed page in step 83 — success naming the
    partner, or the reason-specific refusal. Tap it twice: "Already queued for @…", one row. ☐
96. **The pushed page is Real values only.** Tap the chip strip's fourth chip — it now reads
    **`Real values`**. The page it pushes has **no mode row** and **no In-league content**: just
    the scoring-format chips, Side A / Side B, the consensus verdict and its suggestions. The
    "Want ideas instead? Find a trade →" link is still there. ☐
97. **No league, no dead end.** With a session that has no active league (or after leaving the
    league), the guided landing shows **no canvas** and the `Real values` chip still reaches a
    working calculator. ☐
98. **Kill switch.** Set `calc.inline_home` back to false, `POST /api/feature-flags/reload`,
99. **Matches → edit in calculator (review B1):** from the Matches tab, tap a match row's edit-in-calculator. Expect: you land on the GUIDED landing (not the pushed page) with the canvas prefilled — partner, both sides — and scrolled into view. Tap a second match: the canvas reloads with the new package.
    restart. Re-run steps 95–81: the app is back to the two-tab shape with no canvas. ☐

---

## Known-unverified / known-imperfect

- Nothing in this document has run on a device **except** what the operator's 2026-08-22 pass on
  build 1.16.0 (126) found — section G exists to re-check exactly those six reports. Everything
  else is structural: type checks, 76 `check-*.js` guards (23 named sabotages re-verified red),
  and a file:line code-walk.
- **Report 3's mechanism is inferred.** The fixed `top: 54` band is the only thing the five
  invisible beats shared and the two visible ones did not, and the native-stack header is the
  only structural difference between the calculator and the deck — but whether the band was
  OCCLUDED by that header or merely sited far from its ring was never observed. Adjacency fixes
  both readings. If step 54 still shows a ring with no Analyst, the remaining suspect is
  z-order between the native header and `RootNav`'s overlay sibling, which no solver can fix.
- **The action row is inside the page ScrollView**, not pinned. With 3+ assets per column it
  scrolls out of frame — against the report's one "important" ("fits in the frame"). Steps 10 and
  18 will show this; it is a known gap, not a new defect.
- **The ✓ now works (W6-A) and beat n15 is finally accurate**, but its two REFUSAL paths
  (steps 13a/13b) have never run against a real second account — the predicate is proven only by
  `backend/tests/test_calc_trade_queue.py`. Steps 13a/13b are the ones worth the setup cost.
- **`queued: true` means eligible, not guaranteed.** The mirror also has to win one of three
  likes-you slots on the counterparty's next deck, survive the R4 live-pipeline dedup, and not
  have been swiped already — none of which the up-front answer can promise. If the counterparty
  never sees the card despite a green toast, check those before calling it a bug.
- The **two-column layout on a small screen** and the **spotlight geometry** are the least-proven
  parts. Column width, the wrapped value line, the two 15% cells and where each bubble lands are
  all sized by reasoning, not by looking at them.
- Tour **copy** is budget-compliant but has never been read on a device beside the actual
  controls; a line can be inside 20 words and still be wrong next to the thing it names.
- **Wave B0 (section I) is entirely unrun.** Its evidence is `mobile/tests/check-inline-home.js`
  plus a file:line code-walk in
  [`docs/plans/onboarding-tour-merge/scope-wave-b0.md`](../../../plans/onboarding-tour-merge/scope-wave-b0.md) §3.
  The two things the guard genuinely cannot see: (1) the **ordering** inside the #330 choke point
  when the inline search re-fires it — reset, then fork, then dispatch — which is only observable
  as "the deck actually changed"; (2) the **layout** of a full In-league calculator stacked above
  a swipe deck on a small screen, which nobody has looked at. Steps 68, 72 and 73 are the ones
  worth the setup cost.

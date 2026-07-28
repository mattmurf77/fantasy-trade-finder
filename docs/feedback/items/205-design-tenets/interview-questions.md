# #205 Design-tenets interview — question set (v1, 2026-07-28)

**Why this doc:** feedback #205 stated three tenets (simple beats complex; too
much information is worse than none; built for non-tech-savvy users — any
feature requiring context on how the app works is badly designed) and asked for
an interview to align on a general design framework. #202 (calculator UX) and
#203 (suggestion-conflict logic) fold in. Answers get codified into
`docs/design/design-principles.md` and drive a calculator-first simplification
pass, then an app-wide audit.

Format: answer in any order, skip freely, one-liners are fine. Where options
are listed they're framing, not a menu — override them.

---

## A. The tenets, made operational

1. **The "one job" test.** For each major surface, complete: "A user opens
   this screen to ___." If a screen has two blanks, which wins? (Trades home,
   Calculator, League rankings, Rank tab, Matches.)
2. **Who is the design target?** Describe the least tech-savvy person you
   want succeeding in FTF — their fantasy experience, their patience, what
   apps they already use. (This becomes our persona for every review.)
3. **What may a user be REQUIRED to learn?** Every app teaches something
   (Sleeper taught "swipe to nominate"). What's the ONE concept FTF is
   allowed to require users to learn — and everything else must be
   self-evident? (Candidates: "your board vs consensus," "value in
   draft-pick terms," "mutual-gain trades.")
4. **Information ceiling.** On a single card/verdict, what's the maximum
   number of distinct facts before it violates tenet 2? Is the rule "one
   number, one sentence, everything else behind a tap"?
5. **Progressive disclosure vs hiding.** When we move detail behind a
   disclosure ("Value adjustments ▸"), is that honoring the tenet or
   sweeping complexity under a rug? What earns a disclosure vs deletion?
6. **Power-user escape hatch.** Do power users get a "more detail" mode
   (setting/toggle), or is there one experience for everyone and depth just
   lives deeper in the flow?

## B. The calculator (the named abuser)

7. **The calculator's one job.** Which is it: (a) check a trade I already
   have in mind, (b) build an offer to send, (c) explore what's possible
   with a partner? Rank the three; the top one owns the screen's top half.
8. **Mode count.** Today: In league / Real values / Demo — three tabs.
   Should Demo mode exist at all post-onboarding? Should "Real values"
   (rosterless mode A) fold into a single calculator that just degrades
   gracefully when there's no league?
9. **Verdict layer inventory.** The In-league verdict can currently show:
   value bar, two-board mutual-gain lines, consensus totals, starter-impact
   line, adjustments disclosure, eveners, suggestions. Which THREE survive
   on first paint? Where do the rest go (tap, second screen, delete)?
10. **One verdict language.** Should every trade surface speak ONLY in
    pick-terms ("you're up about a mid 2nd") with raw values demoted
    everywhere, or do numbers still matter on the calculator specifically?
11. **Eveners vs suggestions vs picker-suggestions.** We now have three
    overlapping "help me balance this" mechanisms. Collapse to one? Which
    interaction is the keeper: inline + rows, the suggestion cards, or
    smart picker ordering?
12. **The #203 conflict rule.** When "fills their need" and "closest value"
    disagree, which wins the top slot? Is a need-filling player at a worse
    value ever a BETTER suggestion than a value-perfect one that clogs
    their roster? Walk me through how YOU pick the add-on in a real trade.
13. **Two-board visibility.** Mutual-gain (their board vs yours) is FTF's
    differentiator — but it's also the most context-heavy concept in the
    app. On the calculator, should "their board" framing be visible by
    default, or appear only when it changes the verdict?
14. **Send flow.** After building a trade, what's the ideal end state:
    Send-in-Sleeper handoff, share image, save for later, or all three
    behind one "Done →" affordance?

## C. Vocabulary & values (non-tech-savvy lens)

15. **Terms audit.** React honestly to each — keep, rename, or kill from
    UI copy: "consensus," "board," "divergence," "mutual gain,"
    "fairness," "Elo," "tier," "outlook," "lane," "anchor," "TEP,"
    "superflex," "FAAB," "derived (R*)."
16. **Numbers themselves.** Values like "7,268" are meaningless without
    context. Should raw values EVER appear without a comparator (pick
    equivalent, positional rank, or bar)? Would you go as far as hiding
    numeric values app-wide behind taps?
17. **Tier ladder comprehension.** Does "1 1st / 2 1sts / 4+ 1sts" land
    instantly for a casual dynasty player, or does it need an inline
    explainer the first time it appears?

## D. First experience & teaching

18. **First 60 seconds.** A brand-new user just synced their league. What
    EXACT sequence do they see, and what's the one "wow" you want in the
    first minute? (Today: trades-first deck for the experiment arm; hub
    for everyone else.)
19. **The Analyst (avatar).** Now live for everyone: is the guided tour
    the primary teaching mechanism (and we can therefore strip explanatory
    copy from screens), or a supplement (screens must still self-explain)?
20. **Ranking ask timing.** Ranking powers everything but is work. When do
    we ask: before first trades (accuracy first), after first trades
    (hook first), or never explicitly (infer from swipes/anchors)?
21. **Empty and loading states.** Tenet-compliant rule for every empty
    state: is it always "one sentence + one button"? Any exceptions?

## E. Navigation & surface count

22. **Tab semantics.** Say what each tab means in ≤4 words (Rank, Trades,
    Matches, League). If two tabs need the same words, what merges?
23. **Hub vs deck.** The hub (mode launcher) is now the Trades home. For a
    casual user, is choosing a MODE before seeing trades a decision tax?
    Would "deck first, modes as a filter row" be simpler? (This is a
    genuine tension with what we just shipped — answer freely.)
24. **League tab depth.** Rankings view → League home → leaderboards/
    activity/coverage… how many layers deep can value live before it's
    dead weight? What on the classic League home page would you delete
    outright?
25. **Matches tab.** Does mutual-match inbox deserve a top-level tab, or
    is it a badge/section within Trades?

## F. Trust, honesty & transparency

26. **Showing the math.** Tenet 2 says less info; trust says show your
    work. Where's the line — is "verdict + one-tap receipt" (like the
    adjustments disclosure) the standing pattern for ALL model outputs
    (odds, fairness, suggestions)?
27. **Uncertainty honesty.** Preseason odds, derived boards (R*), relaxed
    "stretch" ideas — how loudly should the app admit uncertainty? Quiet
    labels, or first-class copy?
28. **When the engine is wrong.** A user sees a laughable suggestion. What
    should their one-tap recourse be — and should the app visibly promise
    "this improves your suggestions"?

## G. Multi-league & platform reality

29. **Multi-league posture.** Is FTF fundamentally one-league-at-a-time
    (switcher = context swap) or should surfaces go cross-league (portfolio
    exposure, "this player in 3 of your leagues")? Where's the ceiling?
30. **Platform parity honesty.** ESPN/MFL/Fleaflicker will always trail
    Sleeper in capability. Standing pattern for gaps: hide the feature,
    show-but-disable with a reason, or show with degraded data + label?

## H. Season cycle & what's next

31. **Season-mode shifts.** Draft season vs in-season vs playoffs — should
    the app visibly reconfigure (different home emphasis per phase), or
    stay static with seasonal features appearing quietly?
32. **The odds surface.** When `outlook.odds` lights up (~Week 3-4), where
    does it live per the tenets — a number on the rankings bars, a
    dedicated section, or inside drill-ins only?
33. **Monetization UX guardrail.** Before any paywall work goes live:
    which surfaces/features do you consider untouchable-free-forever, and
    what's the tenet-compliant shape of a paywall prompt (how many, how
    often, how loud)?

## I. Process

34. **Design review gate.** Should every future feature ship with a
    one-line "tenet check" in its status doc (one job? info ceiling? zero
    context required?) — and do you want to be the approver on any screen
    that ADDS visible elements, with agents free otherwise?
35. **The audit order.** After the calculator, rank the next surfaces for
    a tenet pass: Trades deck/cards, hub, League rankings, Rank flows,
    Matches, Settings, onboarding.

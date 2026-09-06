# Trade engine — remaining owner interview

Prepared September 5, 2026. Mobile app focus. Consolidated from your answers through original question 26.

Progress update September 5, 2026, end of evening: responses now cover R01–R09, with narrower open details identified below. R01 also resolves R11's tier-change boundary. Question numbers are retained for continuity; recorded answers are not fresh homework. The consolidated [engineering handoff](decisions.md) carries these decisions forward without requiring more answers tonight.

This is the single working document for the unanswered portions of the interview. Overlapping questions have been combined, answered portions removed, and unclear questions rewritten. References to the original question numbers are included for traceability; you do not need the original interview to answer this one.

Use the new **R01–R20** numbers when responding. A short answer is enough. “Have engineering propose this,” “test it,” and “leave this for later” are valid answers; a blank is not approval of a default. Each topic has an answer space. R19–R20 remain deferred with Part 5, and the separate engineering/experiment section does not ask you to invent formulas.

All valuation discussion uses tiers, draft-pick equivalents and actual trade terms—not internal scores. The original numerical hypothetical exercise remains withdrawn. This document does not authorize implementation or changes to the live experiment.

## Decisions already settled — not being asked again

- The promise is to acquire your buys and sell your fades at credible market prices, by finding a package that fits both managers. R01 allows a bounded market-value sacrifice for outlook, a drastic personal valuation difference or a strong need. Relaxed fairness gives those factors more latitude; it does not authorize unlimited overpay or unnecessary compensation.
- Your chosen outlook beats the app's prediction. Outlook shapes what roster improvement means, and explicit trade exploration must not be blocked by strategic advice.
- Chasing, Shopping, acquisition needs and Untouchable influence offers rather than categorically exclude them. Untouchable means harder to acquire, not unavailable.
- Selected SEND/GET assets must meaningfully define the search. Try all selected pieces first; sweeteners are allowed. R03 permits a brief no-match notice and alternatives using existing chip tags, says to present both options without SEND-first priority, and rejects substituting a selected target. Exact retained-asset coverage remains open; the same promise applies across entrances.
- Consolidation and Tier up largely express the same intent: turn multiple pieces into a more valuable player. Cross-position moves and player-plus-pick packages can qualify.
- The user's tier defines Tier up and Same value; market values inform companion pieces. A within-tier upgrade may qualify. Current-season usefulness is not part of Tier up classification for now.
- League size, scoring, starting slots and bench space matter. Equal summed values alone do not establish that several useful players equal a star.
- Remove the stud-tax Off option, not stud tax itself. Different managers' stud-tax preferences are not P0.
- Use consensus for missing personal rankings on either board. Interests and Untouchable tags may be shared; personal tier placements may not.
- Predicted first-round slots apply only to next year. Do not automatically discount later-year picks. Draft-class quality and modeling a proposed trade's indirect pick-slot effect are not current scope.
- Explicit ranking methods have equal standing as deliberate user input. Skipping is not a vote. Interaction-driven learning may move a player within their tier but must never change their tier. Undo must reverse ranking adjustments caused by the undone action.
- Like, queue and provider-send express willingness to execute the displayed package, but remain different actions. A like is not automatic authorization to send through the fantasy platform.
- Preserve original offer terms and valuation. Interest lasts no more than two weeks, without a separate reconfirmation from the first manager.
- Rankings are universal by scoring format; fairness is account-wide. More Offers filters, partner and trade shape survive Back but reset on league switches.
- Keep the existing tier/draft-pick presentation and card explanations. Keep the live generator comparison; exact offer ordering is still something to learn through testing.

## A. Trade terms, selections and value controls

### R01 — What price flexibility may the engine use?

Original questions: 2, 3, 6, 7, 19; follow-ups F1–F3.

We have your direction: find credible market terms and likely acceptance, without adding unnecessary compensation. What remains is the boundary between a useful recommendation and a price the manager should explicitly choose to pay.

- Under what circumstances may the engine recommend giving additional draft capital or a more valuable player than the market reference would normally call for? What makes that extra cost acceptable or unacceptable?
- Does a selected outlook or acquisition goal give permission for that extra cost, or must the manager express that willingness separately? This concerns what the engine recommends, not whether the manager is allowed to build their own trade.
- What should changing the account-wide fairness setting actually allow the engine to do differently?
- Beyond rankings, should the engine recognize a different willingness to buy versus a minimum willingness to sell the same player? What user action, if any, communicates that distinction?

The finer ordering question—preferred target at a higher cost versus another suitable target at market terms, or a favorable return versus a balanced return—remains open for testing or later tier-based examples. The withdrawn F1 numerical scenario is not being reintroduced here.

Answer recorded September 5, 2026:

- Extra cost may be justified by sacrificing dynasty value for in-season value consistent with outlook, a drastic personal valuation difference, or a slight loss that addresses a strong positional need.
- A selected outlook/acquisition goal can grant that latitude. There must still be a limit to dynasty value given up; no exact cap was selected.
- Relaxing account-wide fairness allows personal rankings, outlook and team needs to drive offers more at the expense of dynasty/market value.
- Buying and selling willingness should be informed by app interactions and their ranking adjustments. Those adjustments may change within-tier position only, never the player's tier. This is an expectation to verify, not a claim that a separate buy/sell model already exists.
- The finer ordering trade-offs remain for experimentation.

Status: product direction answered. Do not ask again whether these reasons can justify extra cost or whether interaction learning may change tiers. Limits, scoring and action-specific learning remain to be specified or tested.

### R02 — How should player tags affect terms and saved preferences?

Original questions: 7, 18; remaining player-rule semantics from the UI audit.

Untouchable is already settled as an influence, not a lock. We still need to know what that influence means in practice.

- What would make an offer compelling enough to surface for an Untouchable player? Describe the kind of return or team benefit that matters; no premium formula is needed. R01 separately covers the buyer's price discipline.
- How should the separate **Not interested** tag behave? Your Untouchable answer did not establish whether this tag is also only a preference.
- If the manager deliberately puts a tagged player into a search, what should happen to the saved tag after that search? We should not assume that exploring one trade permanently changes their preference.

Answer recorded September 5, 2026 — partial:

- Above-market return is central for Untouchable. The owner also wants outlook fit and better personal value, or a strong need addressed with a replacement at the outgoing player's position. Exact rule combinations are not yet formalized.
- Probably never one-for-one was the owner's wording; it is a strong preference, not an approved absolute ban.
- The owner is unfamiliar with Not interested. Its actual UI meaning/reachability should be clarified before asking for a behavior decision; no change was authorized.
- Tagged players should persist when first coming Back to Find a Trade, but not across multiple sessions or league changes.

Clarification retained: does tagged players mean temporary search selections/pins or saved Untouchable/Target rules? The answer describes a search journey while the question asked about saved rules. Do not clear durable rules or unrelated account preferences on that assumption.

Further answer, if needed:

### R03 — What happens when the whole selected package cannot be included?

Original questions: 10, 12; follow-up F5.

You want all selected assets attempted first and allow some fallback. Sweeteners are already allowed.

- Before returning a package that omits a selected asset, what choice or notice should the user receive?
- With selected assets on both SEND and GET, what must remain on each side when the search falls back to fewer pieces?
- If only one SEND or GET asset is selected and no suitable package includes it, under what conditions, if any, may the app suggest a substitute? What permission would be needed first?
- How should the interface distinguish results honoring the whole selection from alternatives honoring only part of it?
- Should that selection promise be identical for the canvas, SEND/GET pins, League Buy/Sell and More Offers? Name any deliberate exception.

Answer recorded September 5, 2026 — first prompt:

Show a brief notice that no matches included those players, then show the closest available alternatives. No separate advance confirmation was required for that described fallback.

Further answer recorded September 5, 2026:

- Do not prioritize SEND first; present both options. Do not substitute the selected player.
- Existing tags on trade chips are enough to distinguish full-selection results from partial alternatives. No extra result treatment beyond those tags is requested; keep the earlier brief no-match notice.
- Yes, the selection promise should be the same across the canvas and other entrances.

Remaining interpretation: both options appears to mean alternatives anchored on the SEND selections and alternatives anchored on the GET selections when the complete package cannot be found. The exact retained-asset minimum is not explicit. Do not turn this into an invented equal quota, two mandatory result groups or permission to silently replace a selected asset.

### R04 — What do Tier up, Tier down and Same value promise?

Original question: 11.

We are not revisiting whether Tier up and consolidation overlap. The remaining issue is what qualifies for each label.

- For **Tier up**, what makes the incoming player an upgrade when your tier and the market tier disagree?
- Can a meaningfully better player within the same broad tier qualify? How should current-season usefulness factor into that judgment?
- For **Tier down**, what kind of return makes the move worthwhile beyond simply receiving a less valuable player? Consider the useful player or draft capital gained alongside them.
- For **Same value**, whose tier or draft-pick equivalent defines “same,” and how close should the exchange feel within a broad tier?

Answer recorded September 5, 2026:

- The user's tier takes precedence for Tier up. Market value determines the accompanying pieces used to construct the package.
- A meaningful upgrade within the same broad tier may qualify. Current-season usefulness should not factor into this specific classification for now.
- Tier down can gain desired draft capital, help a rebuilder move a veteran into a younger player, or address a competitive team's positional need.
- Same value uses the user's tier/draft-pick valuation; market values again inform the other pieces.

Status: product meaning answered. Exact within-tier upgrade criteria and close-value bands remain engineering details, not permission to replace the user's tier with consensus.

### R05 — What should Market, Heavy and Off stud tax change?

Original questions: 3, 15.

You have already rejected the idea that several players equal a star merely because their values add up. You also allow the two managers to evaluate a package differently.

- Describe the practical difference you expect between **Market**, **Heavy** and **Off** when trading several pieces for one player.
- What should remain true about the usefulness of those pieces even when stud tax is Off?
- How should the two managers' differing stud-tax preferences affect which packages are suggested? This does not require making their displayed evaluations identical or redesigning the card.

Exact package-adjustment mathematics belongs in an engineering proposal, not your interview answer.

Answer recorded September 5, 2026:

- Remove the user's ability to turn stud tax Off.
- Accommodating different managers' stud-tax preferences is nice-to-have, not P0.

Open implementation details: the shared active adjustment policy, exact Market/Heavy behavior and migration of existing saved Off values. Do not remove Market/Heavy or package adjustments by implication. No code was changed.

## B. Missing information, risk and future picks

### R06 — What should fill the gaps in an incomplete ranking board?

Original questions: 4, 18, 20.

All explicit ranking methods remain equally authoritative. This question is only about players for whom someone has not supplied a relevant opinion.

- What should the engine assume about unranked players on your own board?
- What should it assume when the other manager has no rankings, or has ranked only some positions?
- What evidence is enough to treat a package as plausibly suitable for that manager when personal preferences are unavailable? For example, how far can declared outlook and actual roster needs take us?

This is a practical missing-input rule, not a request to infer hidden agreement from skipped Quick Set steps or build a ranking-method confidence hierarchy.

Answer recorded September 5, 2026:

Use consensus wherever personal rankings are unavailable, on either manager's board, including missing portions of a partial board. This matches the owner's understanding of the current presentation. Existing personal input still takes precedence where present.

Still open: the owner did not decide how far inferred needs/outlook alone establish that the other manager would find a package suitable. No ranking-method confidence hierarchy is implied.

### R07 — What may one manager learn about the other's preferences?

Original questions: 4, 18; follow-up F4.

Your two-sided network helps find a fit without making managers reveal every negotiating advantage. The disclosure boundary remains open.

- Which parts of another manager's rankings, tier placements, Untouchable tags and acquisition interests may be visible to a potential trading partner?
- When compatibility comes from inferred roster needs rather than the other manager's declared preferences, what must the app avoid implying?

This is about privacy and truthful claims wherever information is used. It is not a request to add more explanation content to the current cards.

Answer recorded September 5, 2026:

Acquisition interests and Untouchable tags may be visible to the trading partner. Personal tier placements may not. No additional disclaimer or card explanation is requested when fit is inferred rather than declared.

This does not authorize fabricated declarations or disclosure of private tier placements through internal values. Broader exposure of exact personal ranking order was not approved.

### R08 — Which risks should change the recommendation beyond the rankings?

Original question: 17, now partly answered below.

Consider injury and recovery time, age-related decline, uncertain role, contract uncertainty, concentrated exposure to the same NFL team, bye-week gaps and a contender's immediate lineup hole.

- Which of these should the engine account for separately when assembling a trade for a particular team?
- Which should it treat as already reflected in personal rankings or market tiers?
- What should prevent the engine from counting the same concern twice—for example, discounting a player for age after the manager has already placed him in a lower tier for that reason?

Your outlook definitions already establish that an injured or less immediately productive asset may suit a rebuilding team. The open issue is how that context interacts with existing valuation, not whether every injury is bad for every manager.

Answer recorded September 5, 2026:

- Separately account for age-related decline and a contender's immediate lineup hole.
- Keep adjustments within the tier; they must not change user-set tiers.
- The owner did not specify which concerns are already fully reflected in personal/market rankings. Other suggested separate risk modifiers were not selected.

Engineering caveat: keeping the same tier does not by itself prevent the same age effect from being applied twice within that tier. The implementation needs to account for that without adding unapproved risk modifiers.

### R09 — How should uncertain future pick slots work?

Original question: 16, partially answered.

No later-year discount and no class-quality adjustment are settled. Using standings projections to inform next year's early/mid/late picks is the direction you want to explore.

- What should the app assume when a future first's likely slot is too uncertain to call early, mid or late?
- How far into the future should team-finish projections influence a pick? This is about slot uncertainty, not discounting its value because of the year.
- When a draft slot becomes known, how should that replace the earlier estimate?
- Should evaluating a proposed trade also account for how that trade could change the original team's future draft position—and therefore the pick being exchanged?
- What scope would you want in the first release of projected pick slots? Engineering should first verify the standings-projection inputs already available.

Answer recorded September 5, 2026:

- Predicted first-round slot assignment applies only to next year, not multiple years out.
- Replacing an estimate with a known slot is already handled according to the owner; verify and preserve that behavior instead of automatically redesigning it.
- A trade can indirectly change the original team's future pick value, but modeling that effect is not a current focus.

Remaining details: uncertain next-year slot fallback and confidence treatment. No later-year discount or class-quality adjustment is authorized.

### R10 — What exactly does a standing offer authorize?

Original question: 24, rephrased because the earlier wording was unclear.

When you agree to sell a player for a first from the teams and years you selected, **does that agreement include every first in those selections, even if one is projected early and another late?**

Once that basic permission is clear:

- What limits should the manager be able to put on the acceptable picks or team/year combinations?
- If a selected trading partner later acquires another team's first, what determines whether that new pick is covered by the existing permission?
- What should end or invalidate a standing offer? Does the same maximum two-week lifetime apply, and from what event?
- Should agreeing to a wider set of acceptable picks change the player's underlying ranking, or only the terms the manager is willing to match against?

This concerns permission to match a package, not automatic execution through the fantasy platform.

Answer:

## C. Feedback, actions and the lifetime of an offer

### R11 — When may trade feedback change rankings?

Original question: 21. R01 now settles the tier boundary; the detailed learning policy is still open.

You do not need to settle it without evidence. You can ask for a proposal or experiment instead.

- What feedback, if any, should change a player's position within their existing tier? Address a like, a pass without a reason, and a pass with a stated reason.
- What feedback should affect only future trade suggestions, partner preferences or repeated-card suppression rather than player valuation?

Interaction-driven tier changes are prohibited by your R01 answer. Undo reversing ranking adjustments is also already a requirement. The unresolved issue is which within-tier adjustments should happen in the first place, not whether sufficient feedback may eventually push a player into another tier.

Answer / research requested:

### R12 — What remains separate from willingness to execute?

Original questions: 21, 22.

Like, queue and provider-send already mean willingness to execute the shown package. The following surrounding actions still need a clear meaning.

- What should **Save for later** mean, and what should the other manager learn from it, if anything?
- After a mutual match, what next action is expected from each manager? No separate first-manager reconfirmation is being proposed; this is about the workflow after the match.
- Beyond reversing ranking changes, what should Undo or withdrawing interest do to the queued opportunity, any match already created and what the other manager sees?

Finding or browsing an offer is not being treated as a commitment, and an in-app like does not become a provider proposal automatically.

Answer:

### R13 — When does the two-week clock start, and how does interest end?

Original question: 23.

Original terms and valuation, a maximum two-week lifetime and no separate first-manager reconfirmation are fixed decisions.

- Which event starts the interest clock? Distinguish an offer merely being generated from a manager expressing willingness to execute it.
- If the second manager sees the card but does not act, what happens to the still-unexpired opportunity?
- What should happen when the lifetime ends, and what deliberate user action would be needed to express fresh interest in the same package?
- If an asset changes owners or the package otherwise becomes impossible to execute, what should users see and what happens to the opportunity?

This does not reopen automatic repricing or demand reconfirmation after ordinary valuation changes. Implementation should preserve the original offer while recording each manager's distinct viewing and action times.

Answer:

## D. One engine across entrances and navigation

### R14 — What should stay fixed when the user enters a different trade surface?

Original question: 12.

You want users to control the scope rather than have the app silently choose it. The remaining question is the starting state and how that choice is offered.

- When opening More Offers from one asset in a larger package, which parts of the original package and partner should initially remain selected?
- How should the user choose to keep or release the remaining assets and partner?
- When moving among Find a Trade, a player entry point, League Buy/Sell and Team Review, what existing search context should carry into the next view? Name any deliberate exception.

R03 covers which selected assets results must contain. This question covers the navigation handoff before those results are generated. Back-button persistence is already settled.

Answer / UX proposal requested:

### R15 — How should overlapping positional goals work?

Original questions: 7, 9.

Chasing and Shopping remain soft priorities. Sending and receiving the same position can still be a useful upgrade.

- Should a manager be able to select both Chasing and Shopping at the same position? If so, what should that combination mean?
- When several positions are selected, what should the engine understand about their relative importance? No numeric weights are needed.
- How should it judge a package that both sends and receives a chased or shopped position?
- When a saved positional goal points in a different direction from the selected outlook, how should general suggestions balance those influences? Explicit user searches still must not be blocked.

Answer:

### R16 — What persists beyond Back navigation?

Original questions: 8, 25.

Universal rankings, account-wide fairness, preserving search state on Back and clearing it on a league switch are already decided.

R02 adds that tagged players should not carry across multiple sessions, but the distinction between temporary selections and saved player-rule tags still needs clarification. Do not treat that wording as a blanket decision about every temporary setting below.

- Which temporary search choices should survive closing and reopening the app?
- Which temporary search choices, if any, should follow the user to another device?
- How long should a declared outlook remain in effect, and when should the app invite the manager to review it? Your declaration remains authoritative; a new prediction must not silently overrule it.

These persistence decisions must not restore an old search in a way that defeats the league-switch reset you already requested.

Answer:

### R17 — What should the app ask when a search is exhausted?

Original question: 5.

You already want an actionable question about how to continue, not a dead end.

- What would be the most useful first continuation to offer the user?
- What changes should the user be able to make from that continuation—for example, revisiting the selected package, partner scope or trade shape?
- Which parts of the request must remain unchanged until the user chooses otherwise?

The detailed all-to-some asset fallback is in R03; this question applies to the broader exhausted-search experience. You can leave the layout and ordering of these choices to a UX proposal.

Answer / UX proposal requested:

### R18 — What should happen when league context is missing or unsupported?

Original question: 14.

League size, scoring, starting requirements and bench depth already matter by your direction. Engineering should audit what is captured and consumed before claiming anything is missing.

- If an important setting is unavailable or unsupported, what should the recommendation experience do differently?
- What assumptions are acceptable temporarily, and what must the app avoid claiming about team fit?
- Which missing settings would make recommendations too misleading to call reliable without first obtaining more information?

This concerns recommendation reliability, not permission to block the manager from exploring a trade or a request to add a new panel to every card.

Answer:

## E. Open details already left to engineering or experimentation

These remain unresolved, but they are **not fresh demands for an owner formula**. The existing answers are enough to frame proposals. You may add a boundary below or leave the details for evidence-based work.

### E1 — Ordering, variety and negotiation history

Original questions: 6, 19; follow-ups F1–F2.

Still to test: the ordering of otherwise suitable offers; favorable terms versus a balanced exchange; strength of preference versus extra cost; repeated versions of the same package; how much variety to show; and whether prior rejection, expressed interest or partner activity changes offer order.

Your fixed boundaries remain: strongest offers first, likely acceptance, no unnecessary compensation, and personal gain is not the automatic primary ordering rule. The live arms stay available for comparison.

Optional boundary / experiment requested:

### E2 — Team-dependent roster usefulness

Original questions: 13, 14, 15.

You declined a universal roster/depth formula. Engineering still needs an approach for usable starters, flex/superflex eligibility, bench depth, roster limits, required cuts, taxi/IR eligibility and whether incoming depth actually improves the receiving team. Shallow leagues and small benches cannot value throw-ins as though every extra player is equally useful.

An implementation proposal should use your outlook definitions and actual league rules, avoid double-counting what rankings already reflect, and distinguish strategic advice from actual transaction eligibility. No universal minimum-depth number is requested here.

Optional boundary / examples to consider:

### E3 — Outlook, package and pick calculations

Original questions: 3, 8, 11, 15, 16.

Still to propose and validate: outlook scoring, precise veteran-age treatment, package adjustments, stud-tax calculations, close-value bands and pick-projection uncertainty. Your approximate age examples must not silently become hard cutoffs. Your middle outlooks remain flexible; future picks receive no automatic year discount.

R01, R04, R05 and R09 ask for the product meaning where it remains unclear. Engineering owns turning that meaning into a transparent, testable calculation—not asking you to choose internal score weights.

Optional boundary / proposal requested:

## F. Deferred Part 5 — retained for completeness, not required now

You deferred Part 5 and rejected its original numerical framing. That exercise is not reinstated. The two original open-ended questions below remain unanswered and are collected here so this document is comprehensive. No immediate response is needed.

### R19 — Real trades to use as acceptance examples

Original question: 27. Deferred.

When you are ready, describe one trade you accepted, one you rejected despite a reasonable price, and one you believe the app should have found.

For each, include the actual assets, relevant tier/draft-pick valuations, both teams' outlooks and useful starters/depth, league format and timing. Explain what made the package work or fail. Manager names are unnecessary. These can also clarify the outlook, package and price decisions without inventing numerical valuation scenarios.

Answer — later:

### R20 — What would make the experiment successful?

Original question: 28. Deferred.

- What outcome should ultimately determine whether an approach is better? Describe the importance of mutual interest, a useful match, a provider proposal, a completed trade and the manager finding the suggestion worthwhile.
- What bad experiences would outweigh an improvement in that outcome? Consider implausible offers, ignored selections, repeated cards, dead ends and time spent finding something actionable.
- How should we judge an opportunity when the other manager has not yet seen it? Their lack of a response should be distinguishable from an actual decision.

This defines what the experiment should optimize and protect, not which current arm has already won.

Answer — later:

## Recordkeeping

The companion [response log](evidence/owner-responses.md) preserves your earlier answers and their chronology. The [original interview and source audit](evidence/owner-interview.md) remain historical context. This document is the consolidated working interview: completed responses are dated, and the remaining answer spaces are intentionally blank.

Questions are product choices or acknowledged open research topics, not findings that a feature is missing from today's build. No DB, engine, app UI, live experiment or production configuration was changed in preparing it.

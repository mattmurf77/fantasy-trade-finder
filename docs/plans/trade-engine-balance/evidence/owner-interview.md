# Trade engine: owner interview and input audit

Prepared September 4, 2026. Mobile app focus.

Updated September 5, 2026: owner answers are recorded in [the response log](owner-responses.md). That log distinguishes decisions from open questions and supersedes unapproved policy assumptions below. The source audit remains a historical code review at the stated commit, not a claim that the owner's requested behavior is already implemented.

The [remaining owner interview](../open-questions.md) is now the single consolidated document for unanswered questions. Use it instead of working through the blank fields below, which remain for historical reference.

## How to answer

The purpose is to define how the engine should think, including when two reasonable priorities conflict. Answer as the product owner and as a dynasty manager. Short answers and real trade examples are more useful than precise formulas. “I don't know—test it” is a valid answer.

Answer in the order that is useful to you. Part 5 is now deferred at the owner's request; its original normalized-number exercise has been withdrawn. Use tiers, draft-pick equivalents and concrete packages for any future examples, not Elo or arbitrary score totals. For each answer, distinguish a **requirement** (a trade may never violate it), a **preference** (a trade can compensate for it), and a **display choice** (changes what you see without changing trade eligibility).

Keep the existing generator comparison. The proposed policy in `docs/plans/trade-engine-balance/history/engineering-brief.md` must be reconciled with the owner's answers before implementation; it is not settled simply because it appeared in the earlier brief. These answers define the product contract that every arm and entry point should satisfy.

## What I reviewed first

The review uses `origin/main` at `606e512cd87f692eced3b92ccadb4f0192ea3449`, rather than the older, dirty shared checkout. These are source findings, not observations from a running TestFlight build. Remote flags and configuration can change availability. File references below are relative to that commit; use `git show 606e512:<path>` to inspect the reviewed version.

Later owner decisions differ from some observed contracts: Untouchable and acquisition needs should influence rather than categorically exclude offers; explicit ranking actions should not be discounted merely by input method; fairness should be account-wide. Preserve this source-versus-intent distinction. Recording provenance does not itself authorize a confidence hierarchy. The current tier/draft-pick presentation should be preserved, not replaced with internal score displays.

| User lever | Current mobile surface and choices | Scope / qualification |
| --- | --- | --- |
| League and team | Active league; trade with Anyone or a specific manager | Defines roster ownership and counterparties. An explicitly chosen partner scopes the canvas search; the untouched auto-displayed partner does not, unless incoming players have been selected from that roster. |
| Personal ranking format | 1QB PPR and SF/TEP boards | User can switch formats and copy tiers between formats. The actual league rules still need to be reconciled with these two broad formats. |
| Personal tiers | Tiers board; Quick Set by position, from 4+ firsts through FA | Saved value declarations. Quick Set now leaves unselected players unchanged; merely seeing or skipping a player is not a new valuation. |
| Personal order | Trios; manual reorder; Quick Rank within a tier | Saved ranking input. Ordering players and declaring the size of the gap are different kinds of evidence. |
| Pick anchors | Assign a player to a draft-capital rung, from 4+ firsts through FA | Saved player valuation; not selection of the particular future pick that must be used in an offer. |
| Imported rankings | Paste, CSV, and supported source intake with match/review/apply; confirm format/value system | Imports order/identity rather than a provider's numerical value column. Imported order should not be mistaken for a user pricing every asset explicitly. |
| Ranking scope and workflow | Position tabs, rookie subset, skip, speed mode, preferred ranking method | Mostly control which ranking questions appear or how answers are entered. A rookie subset shares the broader board; it is not a separate valuation universe. |
| Reset/copy ranking controls | Reset to suggested tiers; copy an existing format's tiers | Can replace explicit inputs with defaults or derived inputs. Provenance matters. |
| Team outlook | Trade DNA: All-in, Contending, Rebuilding, Tanking | Saved per league. Team Review uses alternate labels, including Contender, Rebuilder and Full teardown, and supports Not sure. Inference may supply an initial outlook. The directional receipt is gated off by `trade.outlook_direction: false` in this baseline; a saved choice does not by itself establish its effect on every search path. |
| Chasing positions | QB, RB, WR, TE, Picks | Saved per league. Selecting Chasing removes the same position from Shopping and Avoiding in the DNA sheet. |
| Shopping positions | QB, RB, WR, TE, Picks | Saved per league. DNA does not let Chasing and Shopping contain the same position, which limits expressing “sell my WR depth to upgrade at WR.” |
| Avoiding positions | QB, RB, WR, TE, Picks | Implemented as a hard exclusion, but `trade.avoid_positions` is false in the reviewed baseline. Do not count this as a universally available control. |
| Player rules | Untouchable, Target, Not interested; remove a rule | Saved per league. API contract says Untouchable excludes outgoing, Not interested excludes incoming, Target biases acquisition. One tag per player per league. |
| Specific players / packages | SEND and GET pins; add/remove assets; multi-player give package state | Finder pins are session state and clear on league change. General generation distinguishes any/all outgoing pins. The canvas has separate local selections and a different exact-package contract; do not assume its Clear or league-change behavior is the same as the pin store's. |
| Trade idea | Consolidate, Tier up, Tier down; tap selected option to clear | Local search state in the full Trade DNA sheet. Must verify persistence across route transitions. |
| Fairness | “Balanced trades” / “Ranked by mismatch” | Device-local preference. Current client thresholds are .75 on and .50 off; unset defaults off. This is not a literal personal/consensus weighting slider. |
| Focus | Team-fit moves / Value moves | Deck lane selection when those lanes exist. Distinguish filtering existing results from generating a different candidate pool. |
| Build a trade | Add/remove outgoing and incoming players/picks, choose partner, accept balancing suggestions | Concrete package evaluation. “Find a Trade” forks on whether the give side is populated. |
| More Offers / shop | Select the outgoing asset, then Tier up / Tier down / Same value and receive-position filters | Own search state. Position filters cover QB/RB/WR/TE, not Picks. Same value uses a tier pool; it is not necessarily a narrow numerical market-value band. |
| Buy/Sell and player entry points | League rankings labels positional bands Buyer/Seller; actionable player rows say Offer/Target | Buyer/Seller is inferred from positional rank, not declared manager interest. The candidate flow requires All roster subset, exactly one core position and no Picks filter. Offer/Target carries a pin and partner into a search; it does not send a proposal. The separate UX review audits the handoffs. |
| Stud tax | Settings → Trade values: Market / Heavy / Off | Account setting advertised as applying to calculator and trade suggestions. Off describes plain summed totals. |
| Team Review | Adopt/edit outlook and position needs; scope a partner; review saved player rules | Another writer of the same league preferences, not an independent strategy profile. |
| Feedback | Deck Like; builder checkmark; shop “Send this offer”; pass, decline reasons, swap/edit, undo, match responses | The builder checkmark and shop “Send this offer” both call the in-app queue, not the provider proposal flow. Signals have different meanings: a value rejection, a roster-fit rejection and merely browsing alternatives should not be conflated. |
| Standing offers | After an eligible player-for-first like, choose acceptable years and teams | Broadens willingness beyond the original exact package. Defaults select the source year/team; duration is server-configurable. |
| Provider proposal | Send through a supported fantasy platform | Separate from expressing interest or queueing the idea inside the app. |

Two retired controls deserve an explicit audit: pick-pricing mode was removed in favor of market slots; the top-asset anchor-scale control was removed, but the client source notes that previously saved scales can still apply server-side. Historical data must not silently give otherwise identical users different unexplained behavior.

### The most consequential current differences

1. A populated **give** side sends the canvas search to a consensus fair-package sweep. It fixes the outgoing package; selected incoming assets are preferences for ordering results, not mandatory inclusions. An empty or receive-only canvas takes the model path. The pushed receive-only handoff carries no receive IDs through its `fairAnchor`, and the inline handler does not write those selections into the pin store. This needs a regression case for “I selected this player to buy.”
2. The fair-package call in `TradesScreen` does not send the user's fairness setting, although its API supports that field. The same button can therefore produce results under different input contracts. This finding does not establish every server-side preference used by the sweep; engineering must trace that separately.
3. The canvas opens the compact Trade DNA sheet. The full sheet owns additional controls, including trade shape and fairness. Visibility and context continuity require a separate check; the existence of a control in source does not mean it is reachable at every entrance.
4. More Offers requests asset ideas without the preceding search's partner or fairness values. It also defines Same value by tier membership. These are material product choices even if each individual screen works as coded.

## Part 1 — What a good trade means

**1. What is the first promise the app makes?**

Complete: “When I tap Find a Trade, the app should find ______.” Rank the importance of personal value gained, improving the roster, helping the other manager, staying near market price, and likelihood of acceptance. Which may never be sacrificed?

Answer:

**2. What should your personal rankings mean in a trade?**

Are they your long-term opinion of the player, your current willingness to pay, or your minimum selling price? If you rank a player above market, should the engine spend up to your valuation immediately, or try to acquire him near the market price first? Can your buying and selling prices differ?

Answer:

**3. Define “close to fair market value.”**

Should fairness measure raw consensus totals, package-adjusted totals, the value of the best player, or some combination? Can a manager deliberately accept a market loss for a roster improvement? If so, where is the boundary, and should the app disclose the cost or require an explicit choice?

Answer:

**4. When must both managers benefit?**

Does each need to gain personal asset value, improve roster fit, or either? Can a contender lose long-term value while a rebuilder loses immediate points and both still have a good trade? What evidence makes the second manager's benefit credible?

Answer:

**5. What should happen when there is no trade that meets the rules?**

Choose the behavior in order: explain the conflict, offer a clearly labeled near miss, ask which preference to relax, widen counterparties, or return no offers. Name the rules that must never relax automatically.

Answer:

**6. How should the engine choose among several acceptable offers?**

Would you prefer the largest personal gain, strongest lineup improvement, smallest market overpay, easiest acceptance, or variety? Should ten versions of the same deal occupy ten cards? How much exploration belongs alongside the best-ranked offer?

Answer:

## Part 2 — Explicit instructions versus inferred strategy

**7. Set the conflict hierarchy.**

If your rankings, selected package, outlook, roster needs, player rules and market limits disagree, what wins? For example, you explicitly put an untouchable player on the outgoing canvas: should the app block the search, ask to remove the protection, or allow a one-search exception?

Answer:

**8. Define each outlook through actual trades.**

For All-in, Contending, Rebuilding and Tanking/Full teardown, describe one trade you want and one you reject. How do age, production, future picks and injury recovery change? If your chosen outlook disagrees with team analysis, does your choice always win, and how long does it remain valid?

Answer:

**9. What do Chasing and Shopping promise?**

If you select Chasing RB, must every offer bring an RB, or should RB offers rank higher? Does Shopping WR require sending a WR or merely identify surplus? Should users be able to chase and shop the same position for upgrades? What if they choose several positions?

Answer:

**10. What is fixed when a user selects players?**

For each case, say whether the engine must keep every selected asset, keep at least one, or may suggest substitutes: one SEND player; multiple SEND players; one GET player; multiple GET players; both sides filled. May it add sweeteners? Should canvas selection and SEND/GET pins mean the same thing?

Answer:

**11. Define Consolidate, Tier up, Tier down and Same value.**

Does consolidation require a better starter, fewer roster spots, a higher personal tier, a higher consensus tier, or all of these? Is trading one player plus a pick for one better player consolidation? Should a meaningful upgrade within a broad tier qualify as Tier up?

Answer:

**12. Should every entrance honor the same preferences?**

Consider empty Find a Trade, selected-player Find a Trade, More Offers, League Buy, League Sell and Team Review. Which inputs always travel with the user? Which can reset? When shopping one asset from a multi-asset deal, should the remaining assets and selected partner stay fixed or should the app visibly start a broader search?

Answer:

## Part 3 — Thinking like a dynasty owner

**13. What counts as usable roster improvement?**

How should starting requirements, flex/SF slots, scoring, bench depth, roster limits, taxi/IR eligibility and required cuts affect offers? Is an extra bench player useful if accepting him forces you to drop someone nearly as valuable? What minimum depth should the engine protect after a trade?

Answer:

**14. What should the engine know about the actual league?**

Which scoring or lineup differences materially change value beyond the two ranking formats? Examples: 1QB versus SF, tight-end premium, start 8 versus start 12, shallow versus deep benches, league size. Which unsupported settings should trigger an explanation or reduced confidence?

Answer:

**15. How much are stars and roster spots worth?**

Should three useful players ever equal one elite player just because their values add up? How should the receiving team's available starts change that answer? What do you expect Market, Heavy and Off stud tax to change, and can two managers with different settings evaluate the same package differently?

Answer:

**16. How should picks be valued?**

Distinguish known slot, projected early/mid/late pick and distant unknown first. Should the original team's projected finish matter? How much should later years be discounted? Does class quality matter? Should the engine recognize that trading away a team's best player can improve the projected value of that team's future pick?

Answer:

**17. Which risks should change a recommendation?**

Consider injury, age cliff, uncertain role, contract situation, stacked exposure, bye-week needs and a contender's short-term hole. Which belong in personal rankings already, and which need separate team-specific adjustments? How do we avoid counting the same concern twice?

Answer:

**18. What should we assume about the other manager?**

If they have no rankings, should we use consensus, infer preferences from their roster, or restrict the offer to conservative assumptions? If they have only ranked QBs, how should we treat their RB values? Should declared untouchables and acquisition needs constrain offers before they ever see them?

Answer:

**19. How does real negotiation affect the offer?**

Should the first card be the best deal you can plausibly get, a likely acceptance, or a starting point with room to negotiate? Should partner activity, prior rejection or expressed interest change the order of otherwise identical offers? What separates a reasonable opening offer from one that damages credibility?

Answer:

## Part 4 — Ranking evidence, learning and time

**20. Which ranking actions express strong conviction?**

Compare an explicit tier/anchor, a manual reorder, one trio vote, a copied board, an imported board, and an untouched suggested ranking. Should they have equal authority? How should partial boards behave? If a user skips a Quick Set step, should that mean agreement with consensus or simply no answer?

Answer:

**21. When should the app change someone's rankings from trade feedback?**

A user may pass because the price is bad, the player is wrong, the team is wrong, the timing is wrong, or the offer is repetitive. Which outcomes should update player valuations, search preferences, partner preferences, or only suppression history? Should a like ever override an explicitly set tier? What must Undo reverse?

Answer:

**22. What exactly does each action commit the user to?**

Define like, queue for the other manager, save for later, match, and send to the fantasy platform. Is a like a willingness to execute the exact package, an invitation to discuss, or a positive training signal? Should the same checkmark mean the same thing everywhere?

Answer:

**23. How long is an expression of interest valid?**

Manager A likes a card Monday. Manager B first sees it Thursday, after rankings, market values or rosters change. Should B see the original terms and valuation, a newly priced version, or an expired offer? When must A reconfirm? If B sees the card but does not act, is that still a live opportunity?

Answer:

**24. What should a standing offer authorize?**

Rephrased after the owner found the original wording unclear: When you agree to sell a player for a first from the teams and years you selected, does that agreement include every first in those selections, even if one is projected early and another late?

This is about the scope of that permission. Pick substitutions, standing-offer expiration and any effect on underlying rankings can be discussed separately once that basic intent is clear; no answer is assumed.

Answer:

**25. What should follow the user across leagues and devices?**

Should personal rankings be universal by scoring format, with league-specific willingness layered on top? Should fairness be account-wide, league-specific or temporary? Should More Offers filters, partner selection and trade shape survive Back, a restart, a league switch or another device?

Answer:

**26. What must the card explain?**

Choose the smallest useful explanation: market price comparison, your values, their values when known, lineup change, outlook fit, confidence/source of estimates, and why selected preferences were satisfied. How should it explain “you prefer this deal, but the market says you're paying extra” without suggesting the displayed values are objective truth?

Answer:

## Part 5 — Concrete decisions — deferred

The owner deferred this section on September 5, 2026 because its valuation framing did not match the app. The original normalized-number scenarios have been withdrawn, with no answers or acceptance rules inferred from them.

Any later exercise should use the actual tier/draft-pick equivalents and concrete trade packages that managers see, with each team's outlook and league context. Elo remains internal and should not be presented as a user-facing valuation. No replacement exercise is requested now; questions 27–28 remain available for a later discussion.

**27. Give three real examples from your leagues.**

Provide one trade you accepted, one you rejected despite reasonable price, and one the app should have found. Include both rosters' relevant starters/depth, scoring, outlook, assets, timing and your reasoning. Remove manager names if you prefer. These become engineering's acceptance fixtures.

Answer:

**28. Define a successful experiment.**

What is the primary outcome: both users interested, a qualified match, a provider proposal, a completed trade, or a user reporting that the suggestion was useful? Which guardrails matter: unfair-offer complaints, unexplained preference violations, repeated cards, no-result sessions, or time to find an actionable offer? How should we treat an opponent who has not yet seen the card?

Answer:

## What engineering should produce from your answers

For every input, record its owner and scope, source/provenance, default, last change, priority, whether it constrains or ranks, when it may relax, and which paths consume it. “The field exists” is not evidence that a particular generator or entry point honors it.

Build an executable expectation matrix covering empty search, send-only, receive-only, complete package, player Buy/Sell, More Offers, Team Review and mirrored/standing offers. For each entrance, assert the expected league, partner, exact/optional assets, outlook, position rules, player protections, market bounds, valuation mode, ranking provenance and result order. Separate common guarantees from deliberate differences in output.

Freeze offer context at generation and at each user's actual exposure/action: consensus snapshot and source version; both personal-value snapshots with confidence/provenance; league/scoring/roster/pick context; declared/inferred outlook; all applied preferences and relaxations; generator arm and policy; package identity/version; rank within results; surface and predecessor; viewed, acted, expired and invalidated times. Preserve each manager's orientation of give/receive. Link two users' interactions to the same opportunity while retaining their distinct snapshots. Never reconstruct historical “fairness at offer time” solely from today's values.

Keep operational decision records separate from general analytics. The reviewed shop analytics deliberately log the count of selected positions rather than the actual selection; if detailed preference snapshots are added, define access and retention in the application data design. Avoid claiming a non-response is a rejection before the other manager has had a chance to see the offer.

Resolve historical settings explicitly, including previously saved anchor scales, removed pick-pricing controls, saved-but-disabled Avoiding preferences, default-filled boards and older mobile clients. Keep source state, runtime flags and experiment assignment distinguishable.

## Source index

Reviewed at commit `606e512cd87f692eced3b92ccadb4f0192ea3449`:

- `mobile/src/components/TradeDnaSheet.tsx`: outlook/position/intent controls, autosave, full versus compact sheet, fine tuning (roughly lines 76–98, 424–583, 617–1141).
- `mobile/src/screens/TradesScreen.tsx`: local intent/fairness/partner, generation payload, pushed handoff and fair-package request (roughly 517–543, 1097–1154, 1592–1615, 1848 onward, 2955–3038, 3169–3218, 3519–3537).
- `mobile/src/utils/canvasSearch.ts`: exact canvas fork and incoming-asset semantics.
- `mobile/src/state/useFinderTargets.ts`: session pins, package state, handoff, league reset.
- `mobile/src/components/InLeagueCalculator.tsx`: concrete package inputs and actions; compact DNA invocation at 1569–1575.
- `mobile/src/components/OutlookBiasReceipt.tsx`: directional-receipt flag and declared/inferred outlook resolution; `LeagueSummaryScreen.tsx`: positional candidate eligibility (858–863), Buyer/Seller captions (1016–1030), and Offer/Target handoff (1168–1204).
- `mobile/src/api/trades.ts`: generate, asset ideas, fair packages, swipe and queue contracts (5–32, 386–488, 501–619).
- `mobile/src/api/tradePregen.ts`: fairness key, defaults and thresholds.
- `mobile/src/components/ShopOffersBody.tsx`: modes, filters, tier scope, widening, queue/pass behavior (52–90, 350–449, 695–714).
- `mobile/src/api/league.ts`: league preference and asset-rule contracts (75–108).
- `mobile/src/screens/TeamReviewScreen.tsx`: preference writes and the plan receipt (148–183, 1020–1235).
- `mobile/src/screens/settings/sections/TradeValuesSection.tsx`: stud-tax choices; removed pick-pricing setting.
- `mobile/src/screens/QuickSetTiersScreen.tsx`: hold semantics (64–83); `QuickRankScreen.tsx`: within-tier ordering (52–78); `RankScreen.tsx`: trios and speed mode; `ManualRanksScreen.tsx`: reorder/save; `TiersScreen.tsx`: copy/reset.
- `mobile/src/screens/PickAnchorScreen.tsx`: anchor controls and legacy scale note (136–141); `mobile/src/utils/anchorRows.ts`: rung vocabulary.
- `mobile/src/components/ImportRankingsSheet.tsx` and `RankImportSheet.tsx`: intake, format confirmation, review/apply and order-only import.
- `mobile/src/api/rankings.ts`: format state, rookie scope and ranking writes (13–83, 133–163).
- `mobile/src/components/StandingOfferSheet.tsx`: terms, source-only defaults, independent year/team selectors.
- `mobile/src/navigation/TabNav.tsx` and `config/features.json`: current route structure and checked-in availability.

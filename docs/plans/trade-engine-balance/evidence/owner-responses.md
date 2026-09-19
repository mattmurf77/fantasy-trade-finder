# Trade engine owner interview — responses and open decisions

Part 1 recorded September 4, 2026 from the owner's answers to questions 1–6.
Part 2 and the beginning of Part 3 recorded September 5, 2026 from the owner's answers to questions 7–16. That recording ends during question 16.
Further answers recorded September 5, 2026 cover questions 18–26 and a correction to Part 5. Question 17 was not answered; question 24 needs clearer wording; Part 5 is deferred by the owner.
Follow-up answers recorded September 5, 2026 cover R01, R02 and the first portion of R03 in the consolidated remaining interview. They resolve permission for bounded market-value sacrifices and establish that interaction-driven ranking changes must stay within the player's existing tier.
The final September 5 batch continues R03 through R09. It resolves user-tier ownership of trade-mode labels, consensus fallback for missing rankings, removal of the stud-tax Off option, selected privacy permissions, and next-year-only projected first-round slots. Some narrower details remain open as noted below.

Companion: [interview and input audit](owner-interview.md). This is a structured paraphrase of the owner's answers, not a verbatim transcript. Owner decisions, engineering interpretations and unanswered questions are distinguished below. No engine, experiment, UI or production configuration was changed.

For the consolidated unanswered portions, use [remaining owner interview](../open-questions.md). It combines overlapping follow-ups, preserves settled decisions and separates deferred work from active questions.
For the consolidated engineering interpretation, use [owner decisions and engineering handoff](../decisions.md). Confirmed answers take precedence over any proposal in that handoff.

## Product promise

Help me acquire the players I value more than the market and sell the players I value less than the market, at credible market prices, by finding another manager whose preferences and team direction make the other side attractive.

The second half of that promise is central: the app reduces the difficult negotiation work of discovering what the other manager actually wants. Managers ordinarily must coax this information from each other while both try to preserve their negotiating advantage. The network can identify compatible preferences and assemble packages that work for both sides.

## User-facing valuation language — owner correction

The app expresses value through tiers and draft-pick equivalents. Elo is an internal mechanism, intentionally not shown to users, and is not a meaningful unit for the owner-facing interview. The owner declined the original Part 5 exercise because its arbitrary numerical values missed this presentation model.

The normalized-number scenarios are withdrawn from the active interview; Part 5 is deferred. Any later examples should use the actual tier/draft-capital vocabulary and concrete packages shown in the app, not ask the owner to interpret Elo or invented score totals. This does not request a redesign of the existing cards or removal of internal numerical calculations. Internal audit snapshots and user-facing presentation are separate concerns.

## Confirmed owner answers

### Q1 — The first promise

- Personal disagreement with market values identifies potential buys and sells.
- For a buy, help the manager get a player they prefer at a price they consider fair. For a sale, help them receive a return they consider a great deal for an asset they value less highly.
- Personal preference does not erase the expectation of a credible market price. Managers still seek the best value they can get.
- Finding compatible counterparties and packages is a core value proposition, alongside identifying desirable players.

No absolute ordering of every objective or list of never-relaxable constraints was specified yet.

### Q2 — What personal rankings mean in a trade

- A manager valuing a player above market should not have to pay above market simply because the app knows they like that player.
- Use the rankings to identify the players the manager wants and the players they would prefer to sell.
- Construct a trade near fair market value that also addresses the other manager's preferences or needs.

The owner emphasized acquiring near market price. Question 20 below establishes equal authority for explicit ranking actions rather than a hierarchy based on the method used. The later R01 answer qualifies price discipline with permitted, bounded sacrifices for outlook, a drastic personal valuation difference or a strong need; it also endorses interaction-informed buying/selling willingness within fixed tiers. No separate buying/selling formula was selected.

### Q3 — Fair market value

- Fairness should consider a combination of consensus totals, package adjustments and the value of the best player; a raw sum alone is not a complete answer.
- Market value is the community's reference point and helps both managers recognize a plausible deal. Managers differ in how closely they personally follow it.
- Market value is not the only benefit. A manager may sell a strong player for several firsts because reducing immediate production and building future capital fits a rebuild and may improve future draft position.

That example establishes the value of a strategy-driven change in roster composition. It does **not**, by itself, establish an acceptable numerical market loss, a hard fairness threshold, or permission to relax a market limit automatically.

Later clarification: R01 expressly permits bounded market/dynasty-value sacrifices for the stated reasons. The earlier absence of permission must not be treated as the current rule. The actual limits remain unspecified.

### Q4 — Both managers benefiting

- Yes: a contender can give up long-term value while a rebuilder gives up immediate points, and both can benefit.
- Team outlook is one of the most important inputs to a trade. It should meaningfully shape packages rather than serve as a minor cosmetic preference.
- Relevant consequences include youth versus present production, willingness to acquire injured players, and whether to spend or acquire first-round picks.
- The guided outlook experience and the app's inferred outlook exist because this input drives what a suitable trade looks like.

Question 8 below resolves declared versus inferred outlook: the user's choice wins. Exceptions, persistence and a complete conflict hierarchy are not fully specified.

### Q5 — No more qualifying offers

- Tell the user that the current view has been exhausted and ask how they want to look for trades next.
- Offer an actionable continuation rather than leave them at a dead end.

The specific options, ordering of alternatives and rules eligible for relaxation remain open. Do not infer approval for silently changing the question or loosening constraints.

### Q6 — Ordering acceptable offers

- Lead with the strongest offers.
- The exact ordering, diversity and amount of exploration should be evaluated over the coming weeks as the app goes live. The existing multiple generator arms are intended to support this learning.
- The owner does not favor maximizing personal gain as the primary ordering objective. Personal disagreement is principally the guide to whom to acquire and whom to move, subject to outlook.
- Among the interview's choices, the owner leans toward minimizing market overpay.
- Do not achieve a high acceptance rate by encouraging the initiating manager to give away extra assets. That would erode trust and long-term interest in the app.
- How many offers the user wants to browse may affect presentation and variety. No duplicate-card limit or diversity quota was selected.

### Q7 — Conflicting inputs and user control

- Outlook comes first when interpreting team needs. A rebuilding manager may deliberately not want to fill immediate starting-lineup holes.
- The engine helps the manager find trades they want; it does not run the team for them.
- If a manager explicitly puts a player on the outgoing canvas, the app must allow that search, including the interview's example of a previously protected/untouchable player. The owner rejects blocking the manager's deliberate choice.

These answers establish specific precedence relationships, not a complete ordering of rankings, selections, outlook, player rules and market limits. They also do not specify whether using a protected player changes the saved protection or creates a search-local exception. Do not interpret nonblocking strategic advice as permission to bypass ownership, platform eligibility, authorization or other actual transaction-validity checks. The distinction between exploring a user-chosen package and recommending it as market-fair remains important; numerical market limits are still open.

Question 18 further clarifies that Untouchable itself should influence terms rather than categorically exclude a player, even before a manager explicitly selects that player. It is not merely an exception to an otherwise approved hard lock.

### Q8 — Outlook definitions

- **Declared versus inferred:** the user's selected outlook always wins. The prediction is advice about how the app sees the team, not authority to override its owner.
- **All-in:** prioritize this season's production, better starters and useful depth. Examples include another starting RB, backup TE, extra WR, or a same-position move within a broad tier that improves the current-season outlook. This is not permission to indiscriminately trade away the team's most valuable dynasty assets.
- **Contending:** remain flexible between win-now and future-oriented moves. These teams may have more starting-lineup gaps than an all-in team; improve those gaps with less willingness to sacrifice dynasty value.
- **Rebuilding:** favor the future, but less aggressively than tanking. A one- to two-year rebuild may keep a 25- or 26-year-old RB rather than sell every current contributor. Contending and rebuilding can both involve waiting through the first few weeks before deciding whether to acquire win-now pieces.
- **Tanking/full teardown:** actively move veteran starters for future picks and younger or less immediately productive assets. Reducing the competitiveness of the current starting lineup can be a desired outcome, not a failure of roster improvement. The owner gave approximate veteran examples around RB age 26–27 and WR age 27; these are directional examples, not approved hard age cutoffs.

The two middle outlooks should allow more flexibility than rigid archetypes. No exact time-to-expiry, automatic outlook-change rule, injury adjustment, scoring weights or complete want/reject fixture set was supplied.

### Q9 — Chasing and Shopping

- These are soft priorities, not requirements that every offer involve a selected position.
- Chasing RB should generally move offers receiving RB help higher and offers giving away RB help lower. Shopping a position applies the opposite directional preference.
- Shopping WR usually means using that strength to acquire something at another position, rather than merely exchanging WRs without addressing another objective.
- Use the actual roster to find the assets that can fund an improvement. A manager chasing RB might have surplus WRs or picks, making a cross-position tier-for-tier swap or a WR tier-down that also returns a starting RB useful.
- A manager may sacrifice strength at another position to improve the one they are chasing. This does not by itself authorize an extra market-price premium.
- Do not suppress every otherwise useful trade that lacks the chased/shopped position.

Same-position Chasing plus Shopping, combinations of several positions, the relative weights of conflicting signals and the treatment of packages both giving and receiving the same position remain unspecified.

### Q10 — Selected SEND/GET assets

- Explicit selections should materially define the search, on both SEND and GET. The app should not ignore a selected incoming player or disregard the package the manager is trying to move.
- For several possible assets, the owner favors letting the user decide which to include, analogous to choosing an asset when exploring More Offers from a trade chip.
- Attempt to find offers including all selected assets. Adding more selected assets reasonably means fewer available ideas.
- The owner also allows an at-least-one fallback when all selected assets cannot be included. The answer first emphasizes that selected SEND and GET assets should always be included, then qualifies this with all where possible and at least one otherwise.
- Sweeteners may be added. Selection is about including the chosen pieces, not excluding every other asset.

R03 below allows notice-based alternatives, rejects prioritizing SEND over GET, says to present both options rather than substitute a selected player, and uses existing chip tags to distinguish fulfillment. The same selection promise should apply across entrances. The exact minimum asset coverage meant by both options still requires interpretation; do not silently replace a sole selected target.

### Q11 — Consolidation and Tier up

- Treat Consolidate and Tier up as substantially the same intent in this context: sell multiple pieces to acquire a more valuable player.
- A player plus a pick for a better player qualifies.
- The owner initially distinguishes consolidation across positions from a same-position tier-up, but does not want that distinction to constrain the experience. A manager can use the position options in More Offers to explore upgrades across positions.
- The key idea is moving multiple pieces into a more valuable player, not enforcing a same-position-only label.

R04 below resolves that the user's tier defines Tier up and Same value, with market values used to assemble accompanying pieces. A within-tier upgrade may qualify; current-season usefulness is not part of that specific classification for now. R04 also describes useful Tier down outcomes. The precise within-tier test and numerical bands remain open.

### Q12 — Entrances, search scope and partner discovery

- When branching from one asset in a multi-asset deal, the user should be able to decide how much of the existing package and partner context remains fixed. The UX should make that decision possible.
- No universal keep/reset default was chosen for the remaining assets, partner or other search inputs across entrances.
- League position Buyer/Seller labels are intended to support a familiar trading workflow: if I want to sell a position, find teams weaker there; if I want to buy, find teams stronger there.
- Matching must also examine the reciprocal need: what does that potential partner have in surplus, and what would they want back?
- Interpret apparent positional needs through the partner's outlook. A team weak at RB but not contending may prefer picks or younger, less immediately productive players over a win-now RB.

These are intended product semantics, not a claim that the current Buyer/Seller labels prove a manager's declared willingness or that every existing entrance already preserves the same context. A partner's raw positional weakness is insufficient evidence that a specific incoming veteran suits them.

### Q13 — Usable roster improvement

- The owner does not want to specify a universal answer for minimum depth, required cuts or the usefulness of an extra bench player; these are too team-dependent.
- Use the outlook discussion as the guiding context rather than treating every team as optimizing the same starting lineup.

This defers the formula; it does not say to ignore roster constraints. Question 14 explicitly confirms that starting requirements and bench size matter. Taxi/IR eligibility, required-cut valuation, post-trade depth and their explanation or enforcement rules remain open for concrete examples or engineering proposals.

### Q14 — League-specific context

- Actual league size, scoring/format, starting-lineup requirements and bench size should influence trade usefulness.
- 1QB versus superflex and tight-end premium matter; the owner views the ranking formats as already addressing these dimensions at a broad level. This answer is not a new audit of the completeness of current ingestion or scoring support.
- Start 8 versus start 12 and the number of starting slots at each position across the league affect which assets are useful.
- Smaller leagues and shallower starting lineups increase the importance of high-end players. Deeper leagues make lower-ranked players more usable.
- Short benches make throw-ins less useful and less enticing. Do not treat nominal extra assets as equally valuable in every league.
- The owner's WR36 comparison between an eight-team and sixteen-team league illustrates differing starter demand; it is not a universal lineup rule independent of WR/flex settings.

No specific adjustment formula, supported-settings release scope, missing-data fallback or method of combining league context with the existing rankings was selected. Verify which inputs are already captured and actually consumed before claiming they need new ingestion.

### Q15 — Stars, package totals and differing evaluations

- Three useful players do not equal an elite player merely because their listed values add to the same total.
- Two managers can evaluate the same package differently; outlook is at least one intended reason for that difference.

This rejects raw-sum equivalence, not every three-for-one trade. R05 below removes the user-facing Off option and defers accommodating different managers' stud-tax settings from P0. It does not remove package adjustments or settle the Market/Heavy formula, active common policy, or migration of existing Off preferences.

### Q16 — Future picks — partial answer

- The owner wants to move toward projected early/mid/late pick values, potentially now rather than much later, using the standings projections already being developed to inform next year's picks.
- The owner has intentionally chosen not to discount later-year picks. Do not introduce an automatic discount merely because a pick is further away.
- Draft-class quality is out of scope for now.

R09 below limits predicted first-round slot assignment to next year, records the owner's statement that known-slot replacement already exists, and defers modeling the proposed trade's indirect effect on a team's pick. Projection uncertainty and the unknown-slot default remain open. No year discount does not imply that every first-round pick has the same value regardless of its projected slot.

### Q17 — Risk adjustments — subsequently partly answered in R08

The owner initially resumed at question 18, then addressed this topic in R08 below. Separate age-related decline and a contender's immediate lineup hole were selected; the other proposed risk modifiers were not approved. Preserving tiers does not itself supply a full rule for avoiding duplicate adjustments.

### Q18 — The other manager's preferences and needs

- Declared Untouchable tags and acquisition needs should influence offers, not act as categorical constraints.
- Untouchable means the manager expects it to take more to acquire that player. The asset is harder to obtain, not unavailable at any price.
- Identify reciprocal needs and surplus: where am I strongest, which teams need that position, and what can they offer from positions where they are strong and I am weak?
- Apply outlook to that match. A rebuilder holding older veterans may be a suitable partner for a manager willing to send picks, rather than simply being classified by current positional weakness.

R02 below further defines a compelling Untouchable return, and R01 permits bounded buyer-side sacrifices for specified reasons. No premium formula or precise market limit was selected. This is not permission to inflate the community reference value or promise the other manager will accept. R06 resolves missing rankings as consensus fallback; the evidence needed to claim opponent suitability remains unspecified. The owner is unfamiliar with Not interested; its intended semantics remain unanswered.

### Q19 — Negotiation and likely acceptance

- Ideally, suggest an offer that is likely to be accepted.
- The match feature is intended to identify a bona fide package that both managers should accept or be close to accepting, not merely a speculative conversation starter.
- Some room for negotiation is expected.

Read this alongside question 6: likely acceptance is desirable, but buying acceptance by adding unnecessary compensation is not. The owner has clarified the intended quality of the offer, not chosen a predictive model, score weight or rule for partner activity/prior rejection.

### Q20 — Strength of ranking actions

- Every explicit ranking action is a strong statement of the user's view of players.
- Do not create a hierarchy of conviction merely because the user chose one ranking workflow rather than another. Their deliberate ranking decisions should not be treated as weaker solely because of the input method.
- Skipping a Quick Set step should not be interpreted as either agreement or disagreement. Do not read more into the omission than the user supplied.
- The app's value depends in part on users setting their rankings; the owner does not want elaborate inference about what skipped input means.

R06 resolves missing personal entries as consensus fallback, on both managers' boards. That fallback is not evidence that an untouched default is a deliberate ranking action. Provenance may still be recorded for auditing without automatically reducing an explicit action's authority. The interview's earlier method-based confidence assumptions must not become product policy by default.

### Q21 — Trade feedback and Undo

- The owner does not yet have a rule for when trade feedback should change player rankings. A pass can have several causes and is not explained by the action alone.
- Undo must reverse whatever ranking adjustments were made because of the undone action.

R01 later resolves one firm boundary: interaction-driven learning may change within-tier position but must never change a player's tier. The precise action/reason-to-adjustment policy and Undo's non-ranking effects remain open. Do not treat the partial answer as approval of every current learning behavior or a decision to disable all learning.

### Q22 — Meaning of like, queue and send

- Liking a trade, queueing it for the other manager, or sending it to the fantasy platform expresses that the manager wants to execute the package presented.
- A like can provide a positive learning signal, but the user's intended action is willingness to make that trade, not merely volunteering training data or expressing abstract interest in a player.

Shared willingness does not make the actions' side effects identical: an in-app like or queue is not authorization to transmit a provider proposal or execute a transaction automatically. The owner did not separately define Find, Save for later, every match state or the exact provider-send lifecycle.

### Q23 — Original terms, original valuation and lifetime

- When manager B encounters the opportunity later, show the original terms and valuation.
- An expression of interest should remain valid for no more than two weeks; beyond that it is no longer meaningful.
- Manager A does not need a separate reconfirmation step; the owner considers the match process sufficient.

Do not silently reprice the original package, turn a later view into indefinite renewed interest, or add a mandatory A-reconfirmation gate as if the owner requested it. The owner did not specify the precise event that starts the maximum two-week clock, renewal behavior, or how to resolve actually unavailable assets/changed eligibility. No reconfirmation does not waive ownership or provider-validity checks, or authorize automatic execution. Preserve the original shared opportunity and each manager's distinct exposure/action history; original valuation display does not require deleting later context from the audit record or exposing another manager's private rankings.

### Q24 — Standing offers — clarification needed

The owner did not understand the question and supplied no authorization rule.

Plain-language replacement: When you agree to sell a player for a first from the teams and years you selected, does that agreement include every first in those selections, even if one is projected early and another late?

This asks how broad the manager's permission is, not how to calculate Elo or whether every pick is worth the same. Pick substitutions and standing-offer-specific expiration/invalidation remain unanswered. Do not assume the two-week answer for a particular expression of interest automatically specifies every standing-offer behavior.

### Q25 — Scope and persistence

- Personal rankings should be universal by scoring format, rather than separate for each league.
- Fairness should be account-wide.
- More Offers filters, partner selection and trade shape should survive Back navigation.
- Those temporary search choices should not carry through a league switch.

Restart persistence and cross-device persistence for temporary search choices were not answered. The league-switch reset applies to search context, not to wiping universal rankings or account-wide fairness. Exact retained state when returning to a previously visited league was not specified.

### Q26 — Card explanations

- The owner considers the current card explanations good as they are and does not request additional explanation content.
- Focus this work on the correctness of recommendations and the already-discussed UX flow, without treating the interview's proposed list of extra card explanations as approved UI scope.

This is owner feedback about the presentment, not a new runtime audit of every card or approval to expose internal scores. The tier/draft-pick valuation correction above governs any later owner-facing examples.

### Part 5 — Deferred

The owner is not answering the hypothetical cases at this time because their numeric framing misses the app's tier/draft-pick presentation. No show/hide, top-five ranking or acceptance decisions were supplied for those cases. Questions 27–28 also remain unanswered. Do not convert unfilled interview examples into requirements or acceptance fixtures.

## Consolidated interview follow-up answers — September 5, 2026

These R-numbers refer to [the remaining interview](../open-questions.md). The original Q-number answers above remain as chronology, with cross-references where a later answer resolves or qualifies them.

### R01 — Price flexibility and interaction-informed willingness

- Outlook can justify sacrificing dynasty/market value for in-season value.
- A drastic difference between personal and market valuation can also justify extra cost. There must still be a limit to the dynasty value given up; no limit or formula was chosen.
- A slight value loss can be acceptable when it addresses a strong positional need.
- A selected outlook or acquisition goal can grant this latitude; the owner answered yes to that permission question. Do not add a mandatory separate permission step as though it were an owner requirement.
- Relaxing account-wide fairness means allowing personal rankings, outlook and team needs to drive packages more, at the expense of market/dynasty value. It does not mean removing all bounds or hiding the cost. Exact strict-versus-relaxed limits and their implementation remain open.
- Different buying and selling willingness should be reflected in some way through the user's app interactions and their resulting ranking adjustments. This is an expectation to verify, not proof that the current code already represents separate buying and selling thresholds.
- **Hard rule:** interaction-driven adjustments must never change the player's tier. They may change where the player ranks within that tier. This constrains learning from app interactions, not the user's deliberate act of assigning a different tier.
- Preferred target at a higher cost versus another suitable target at market terms, and favorable versus balanced returns, remain questions for experimentation. The owner agrees there is no further ordering decision to make now.

This qualifies the earlier near-market principle: the app should not waste assets merely because it knows the user likes a player, but may recommend a bounded sacrifice for meaningful personal or strategic benefit. Do not interpret the new latitude as spending up to every high personal valuation automatically. No new live policy or experiment change is authorized by these interview answers.

### R02 — Untouchable returns, an unfamiliar tag and journey persistence

- For an Untouchable player, above-market return is the central expectation.
- A compelling package should address the owner's outlook and offer better value in their eyes, or address a particularly strong need while providing a replacement at the outgoing player's position.
- Positional fit and outlook fit are important; a generic collection of nominal value is not the described goal.
- The owner said an Untouchable trade would probably never be one-for-one. Preserve that as a strong preference, not a finalized categorical ban.
- The owner is not familiar with the Not interested tag. No new behavior, removal or persistence rule for that tag was approved; its actual UI reachability/meaning needs clarification before asking for a policy choice.
- On persistence, the owner agreed that exploring a trade need not permanently change a preference, and said tagged players should persist when first returning to Find a Trade, but not across multiple sessions or league changes.

Persistence terminology remains ambiguous: the question referred to saved player-rule tags, while the answer describes players carried through a search journey. Confirm whether tagged players means temporary selected/pinned assets or saved Untouchable/Target rules before changing storage or expiry. Do not infer authorization to delete durable player rules, and do not apply this answer to account-wide fairness or universal rankings. The exact conjunction of personal benefit, strong need and replacement requirements also has not been expressed as a formal eligibility rule.

### R03 — Package fallback notice — partial answer

- When no matches include the requested players, show a brief notice explaining that and present the closest available alternative.
- Notice-based fallback is acceptable; the owner did not require an additional advance confirmation for this described case.
- The suggested wording was illustrative, not finalized UI copy or a requirement for a new explanation panel on every card.

The final batch continues this answer:

- Do not prioritize the SEND pieces over the GET pieces. Present both options.
- Do not suggest a substitute for the selected player; present the options instead.
- Use the existing tags on trade chips to distinguish results honoring all versus part of the selection. No more UI than that is requested for this distinction; the earlier brief no-match notice still applies.
- Yes, the selection promise should be consistent across the canvas and other entrances named in the question.

Interpretation, not a finalized matching rule: if the full package is unavailable, show alternatives built around the SEND selections and alternatives built around the GET selections, without claiming that a different asset replaces the original target. The exact minimum asset coverage in each alternative is not yet explicit. Do not force SEND-first ordering, silently replace a sole target, or silently broaden the partner scope on the strength of this answer.

### R04 — Personal tiers define trade modes; market values shape the rest

- The user's tier takes precedence over the market tier when deciding what is a Tier up.
- Market value helps determine the other pieces used to construct that trade.
- A meaningfully better player in the same broad tier may qualify as a Tier up. No precise within-tier upgrade threshold was selected.
- Current-season usefulness should not factor into this specific Tier up classification for now. Outlook and current-season benefit still matter to overall package suitability, as previously established.
- A useful Tier down may gain draft capital when desired, move a rebuilding team from a veteran to a younger player, or address a competitive team's positional need.
- Same value is defined by the user's tier/draft-pick valuation; again, market value informs accompanying pieces.

Do not convert personal-tier precedence into permission to disregard package market cost. R01 still bounds market sacrifices. Tier down does not have to produce the same kind of return for every outlook.

### R05 — Remove stud-tax Off; differing settings are not P0

- Users should not be able to turn stud tax off. Remove that option.
- Accommodating the two managers' differing stud-tax preferences is a nice-to-have, not a P0 requirement for now.

This does not remove stud tax itself, remove Market/Heavy by implication, or downgrade the core personal-ranking/outlook/need inputs from P0. The active package-adjustment policy and treatment of existing saved Off values must be specified before implementation; hiding a control alone does not resolve its persisted effect. No app change was made in this documentation session.

### R06 — Consensus fills missing personal rankings

- Use consensus wherever a user-specific ranking is absent.
- Apply this to the requesting manager and the other manager, including missing positions on a partially populated board.
- The owner describes this as the app's existing presentation model. Preserve actual personal input where available; do not discard a whole partial board because some entries are absent.
- The owner did not settle how much inferred roster need and declared outlook, without personal rankings, is sufficient to consider an offer suitable for the other manager.

This is an explicit missing-entry fallback, not permission to treat consensus as an expressed preference or to shrink every explicit ranking based on workflow/comparison counts. Current implementation coverage still needs verification.

### R07 — Share interests and Untouchable tags, not tier placements

- Acquisition interests may be visible to potential trading partners.
- Untouchable tags may be visible to potential trading partners.
- Personal tier placements should not be visible to them.
- Asked what additional implication/disclosure rule is needed when fit comes from inferred needs rather than declarations, the owner answered none. No additional warning or explanation content is requested.

No special disclaimer requirement does not authorize fabricated claims that the other manager declared a preference or accepted an offer. No broader permission was given to expose exact ranking order, private valuation snapshots or values that disclose otherwise-private tier placements. Preserve the distinction between privileged audit data and another manager's UI/API access.

### R08 — Limited separate risk adjustments, always within tiers

- Separately consider age-related decline and a contender's immediate starting-lineup hole.
- No other item in the proposed risk list was selected for a separate adjustment in this answer. This does not mean deleting injury or other information already reflected in consensus/personal rankings.
- The owner did not identify exactly which concerns are already fully reflected in ranking inputs.
- Adjustments should operate within the tier and must not change user-set tiers. The owner reiterated this constraint when discussing double-counting.

Engineering distinction: a tier boundary prevents cross-tier movement, but does not mathematically prevent the same age concern being counted twice within the tier. That implementation issue remains to be addressed without inventing an additional owner policy. Current-season need can influence overall suitability without changing the Tier up definition in R04.

### R09 — Predicted first-round slots only for next year

- Assign projected future-first slots only for next year, not multiple years out.
- The owner says replacing an estimate with a known draft slot is already handled. Treat that as behavior to verify/preserve, not a new feature to redesign without evidence.
- A proposed trade may indirectly change a team's future draft position and pick value, but modeling that effect is not a current focus.

Do not introduce distant-year slot projections, automatic later-year discounts or class-quality adjustments. A fallback for an uncertain next-year slot and the precise projection-confidence treatment remain unspecified. The relevant next year should follow the league/draft calendar rather than a permanently hard-coded year.

## Implications to carry into engineering — interpretation, not a finalized algorithm

1. Treat identifying the right assets, finding the right counterparty, and setting the package price as distinct responsibilities. R01 allows bounded extra cost for a drastic personal valuation difference or strategic benefit, but a high personal valuation is still not a budget to exhaust automatically.
2. Evaluate strategic benefit for both managers in their own context. A requirement that both sides must gain immediate points or both must gain long-term asset value would exclude the contender/rebuilder trade the owner explicitly wants.
3. Preserve bounded market price discipline while accounting for package structure and meaningful roster effects. R01 explicitly permits sacrifices for outlook, a drastic personal difference or a strong need, with more latitude under relaxed fairness. Do not interpret minimizing overpay as requiring exact equality, ignoring preferences, or maximizing the requesting manager's market advantage at the other manager's expense. The bounds remain to be proposed and tested.
4. Question 19 confirms that likely acceptance is an intended outcome: an offer should be close to executable for both managers. Question 6 still rules out manufacturing acceptance by adding unnecessary compensation. The ordering, estimation method and weights remain experimental rather than owner-selected.
5. The exhausted-search experience should explain how to continue. R03 specifically permits notice-based closest-package alternatives when all selected assets have no matches. Preserve the original request separately from the fulfilled subset so fallback is visible; minimum side coverage and sole-target substitution remain unresolved. Do not impose an additional mandatory consent screen for the already-described fallback as though the owner required it.
6. Retain the existing experimental approach. These answers establish product intent; they do not identify a statistically winning generator, prescribe weights, or approve changing live arms.
7. Separate user control from recommendation strength. Explicit choices can override the app's strategic advice without being relabeled as market bargains or silently rewriting persistent preferences. Outlook should shape the interpretation of needs, while declared outlook overrides inferred outlook. Untouchable is itself a soft reluctance/compensation signal, not merely a hard lock with a canvas exception.
8. Distinguish soft discovery priorities from asset-selection commitments. Chasing/Shopping rank opportunities; selected SEND/GET assets define a more specific request. Resolve the all-to-some fallback before building a shared search contract, and preserve the distinction across entrances.
9. Apply team outlook and league-specific usable depth on both sides. Raw player counts, positional holes or equal consensus sums are insufficient measures of mutual benefit. The roster effects may appropriately be opposite for a contender and a tanking team.
10. Treat league/roster adjustments as context, not an unexplained replacement for the community reference price. Keep raw market values, personal values, package effects and contextual usefulness distinguishable; avoid double-counting SF/TEP or other effects already reflected in ranking values.
11. Extend the planned frozen offer and per-user exposure/action context to capture the inputs actually used: declared and inferred outlook separately; league size and exact lineup/scoring/bench settings; selected versus required versus fulfilled assets and any fallback consent; partner/search scope; directional position priorities; package adjustments; and pick projection source, time, uncertainty and no-year-discount policy. These are proposed auditability requirements, not a finalized schema. An explicit user-chosen exception must be distinguishable from the engine ignoring a preference.
12. Preserve original offer terms and original valuation, with at most two weeks of valid interest and no separate A-reconfirmation requirement. Link each manager's later exposure and action to that original package/version rather than silently replacing it. Design the precise expiry clock and eligibility handling explicitly; a match is not an automatically executed provider transaction.
13. Keep provenance and causal history without imposing an unapproved ranking-method confidence hierarchy. Interaction-driven learning must stay within the player's existing tier, including across repeated interactions, and Undo must reverse the ranking changes caused by its action. The exact direction and size of changes for each action/reason remain unresolved.
14. Keep product scope narrow: preserve the existing tier/draft-pick card language and explanation content. Verify account-wide fairness and format-wide rankings separately from Back-persistent, league-reset search state. These are input/state-contract requirements, not a request to add more metrics to the cards.
15. R04 makes the user's tier authoritative for Tier up and Same value; market values price the accompanying pieces. R06 uses consensus only where personal entries are missing. Preserve those roles without a method-based confidence hierarchy.
16. Remove the stud-tax Off option without removing package adjustments or silently selecting a migration for old Off values. Per-manager stud-tax differences are not P0. Predicted first-round slots are next-year-only; known-slot behavior is to verify/preserve and trade-induced projection effects are deferred.
17. R07 permits sharing acquisition interests and Untouchable tags, not personal tier placements. No additional inference explanation is requested; this does not authorize false declarations or exposing private tiers through raw/derived values.

## Reconciliation needed with the earlier engineering brief

The earlier [engineering brief](../history/engineering-brief.md) proposes making two-sided `personal_opportunity` the primary ordering signal (its opening recommendation and Candidate ranking section). These new answers do not support treating that as the settled product rule. The owner emphasizes personal rankings for asset/counterparty discovery and market price discipline for terms, while leaving final ordering to experimentation.

The brief also proposes allowing greater market divergence when both personal boards provide strong evidence. R01 now explicitly permits bounded extra cost for outlook, a drastic personal valuation difference or a strong need, and permits relaxed fairness to prioritize these factors. This resolves the earlier question of whether such latitude can exist; it does not approve the brief's exact confidence formula, require both boards to meet an invented conviction threshold, or remove the cap. Equal authority across explicit ranking methods remains the owner's rule.

The two-sided matching, outlook, experiment preservation and offer-time snapshot requirements remain relevant. Part 2 adds further constraints: declared outlook wins; strategic advice must not block an explicit canvas choice; Chasing/Shopping are soft priorities; all-to-some selection fallback needs a clear user contract; league context and package usefulness matter; no automatic later-year pick discount should be introduced.

The latest answers also require soft Untouchable semantics, equal authority across explicit ranking workflows, likely-acceptance intent without unnecessary compensation, original offer terms/valuation, no more than two weeks of interest without A reconfirmation, account-wide fairness, and Back-persistent but league-reset search context. Any contrary hard exclusions, method-based conviction weighting or reconfirmation gates in the earlier proposal need reconciliation. Do not add card metrics or present Elo to users.

R01–R09 add a strict within-tier boundary for interaction learning, a more specific above-market/fit expectation for Untouchable returns, notice/chip-based alternatives without SEND-first priority or target substitution, personal-tier mode definitions, consensus missing-entry fallback, Off removal, privacy limits and next-year-only first-slot projections. The journey-persistence answer needs its field scope clarified before touching saved tags.

Reconcile the proposed ordering, premium rules, time/state behavior and shared input contract before treating the earlier brief as implementation-ready. The brief itself has not been rewritten while the interview is still in progress. The detailed feedback-to-ranking policy, fallback coverage and standing-offer authorization remain unresolved; permission for bounded extra cost and prohibition on interaction-driven tier changes no longer are.

## Focused follow-ups — current status

### F1 — Strength of preference versus price

The earlier percentage-based hypothetical is withdrawn pending a tier/draft-pick-based example. The unresolved topic is how to order a preferred target that requires extra compensation against a less-preferred target available at a market-consistent return. No new scenario is requested while Part 5 is deferred.

Owner answer: R01 leaves this ordering trade-off to experimentation. No replacement hypothetical is requested now.

### F2 — An advantage versus a balanced starting point

If a deal gives the requesting manager a modest market advantage and still genuinely benefits the other manager through preferences or outlook, should it rank ahead of an equally useful market-balanced deal? This distinguishes seeking favorable terms from seeking the smallest imbalance in either direction.

Owner answer: R01 leaves favorable versus balanced return ordering to experimentation.

### F3 — Permission for a market premium

Can a declared outlook alone justify showing a small market premium for a particularly useful package, with the cost clearly disclosed? Or should the manager explicitly choose that willingness for the search before such offers appear? This is separate from a rebuilder choosing less immediate production at an otherwise fair price.

Owner answer: Yes, per R01. Outlook, a drastic personal valuation difference or a strong need can justify a bounded sacrifice; relaxing fairness gives those factors more latitude. No additional per-offer permission gate was requested. The actual limits remain open.

### F4 — What the other manager gets to learn

Should each manager's exact rankings and preference strength stay private while the app explains only that a package fits both teams? Should the app distinguish a match based on the other manager's declared preferences from one based only on inferred roster needs?

Owner answer: R07 permits sharing acquisition interests and Untouchable tags but not personal tier placements. No additional inference disclaimer is requested. Broader exposure of private ranking order/internal values was not authorized.

### F5 — When the whole selected package cannot be honored

Suppose the user selects SEND A + B and GET C, and no reasonable offer includes all three. May the app immediately show a clearly labeled A-for-C alternative, or should it first ask the user to loosen the package? In either case, must an alternative still include at least one selected asset from each populated side?

Owner answer: R03 permits a brief no-match notice and alternatives identified by existing chip tags, without SEND-first priority. Present both options rather than substitute a selected target; use the same promise across entrances. Exact minimum selection coverage remains open.

F1–F2 are left to experimentation; F3 is answered in principle; F4's core disclosure permissions are answered; F5 is partly answered. The working interview tracks the outstanding pieces, and the engineering handoff consolidates tonight's decisions. Do not reopen permission for bounded strategic/personal sacrifices or whether interaction learning can change tiers: the former is allowed for the stated reasons, and the latter is prohibited. Further examples should use the app's tier/draft-capital language.

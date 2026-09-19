# Fleeced trade engine — owner decisions and engineering handoff

September 5, 2026. Mobile app only; website work is out of scope.

## Status and how to use this document

This consolidates the owner's interview answers through R09 into one engineering handoff. Two Astra Ultra subagents independently reviewed policy consistency and mobile presentation/flow. This session changed documentation only: no app code, database, production setting or experiment assignment was changed.

**Confirmed decisions below supersede conflicting policy recommendations in the September 4 engineering brief and UX review.** The [response log](evidence/owner-responses.md) preserves the answers and chronology. [The working interview](open-questions.md) records the narrower questions still open. Interpretations and proposed implementation sequencing are labeled here; unanswered details are not permission to invent product behavior.

Earlier source findings and database measurements are historical, not a fresh audit of today's build. Before implementing, start from freshly fetched `origin/main` in an isolated worktree and verify current coverage. Preserve the dirty shared checkout. Follow the repository's scope, evidence, documentation and release gates.

## 1. The product promise

Help managers acquire the players they like more than the market and sell the players they like less, at terms they consider a good deal. Find the other manager whose preferences, surplus and outlook make the reciprocal package attractive. The app should remove the work of coaxing out what the other owner wants without spending away the requesting manager's negotiating advantage.

The operating distinction is:

- **Personal tiers/rankings identify desired assets and define trade-mode direction.**
- **Market values help construct the accompanying pieces and keep the price credible.**
- **Outlook, league context and needs determine whether the package is useful for each team.**
- **Bounded price flexibility permits a meaningful strategic or personal benefit.**

This is not consensus-only generation, automatic maximization of personal surplus, or acceptance achieved by giving away unnecessary assets. It should produce a bona fide package both managers are close to willing to execute.

## 2. Confirmed engine and input contracts

### Personal rankings, missing entries and market flexibility

All explicit ranking workflows carry authority as deliberate user input. Do not make a manual placement more authoritative than another explicit method simply because of the method used. Skips are not endorsements. Where a personal ranking is absent, use consensus for that missing entry on either manager's board; retain personal entries elsewhere on a partial board. Record which source was used without representing the fallback as a declared preference.

The engine may recommend a bounded sacrifice of dynasty/market value for:

- Outlook-driven in-season benefit.
- A drastic difference between personal and market valuation.
- A slight loss that addresses a strong positional need.

The selected outlook/acquisition goal can grant this latitude; no extra per-offer opt-in was requested. Relaxed account-wide fairness lets personal preference, outlook and needs drive packages more at the expense of market value. **A cap still exists in principle, but its actual strict/relaxed limits are not selected.** Do not interpret flexibility as automatically spending up to the user's highest personal valuation.

The owner's tiers are not a substitute for pricing the entire package. Preserve distinguishable market cost, personal preference and strategic benefit. Exact ordering among acceptable trades remains experimental.

### Outlook and reciprocal roster fit

Declared outlook overrides inferred outlook. Predictions are advice; they must not block the manager's deliberate exploration or silently change their chosen direction.

| Outlook | Intended package usefulness |
| --- | --- |
| All-in | Improve this season's starters or useful depth; do not indiscriminately spend the best dynasty assets. |
| Contending | Fill lineup gaps while retaining more dynasty flexibility; mix present and future moves. |
| Rebuilding | Favor the future without a compulsory teardown; a one- to two-year plan may retain productive younger veterans. |
| Tanking/full teardown | Move veteran starters for picks or younger/less immediately productive assets; weaker current production can be a successful result. |

The middle outlooks are intentionally flexible. Approximate veteran ages in the interview are examples, not hard exclusion thresholds.

Use league size, scoring, starting slots, flex/superflex eligibility and bench space to interpret usefulness. A shallow league or small bench cannot credit throw-ins as if every extra player is usable. The owner did not provide a universal depth/cuts formula; engineering should propose and test one consistent with these principles.

Apply this reasoning on both sides. A partner's weak RB room does not by itself establish demand for a win-now RB; a rebuilding partner may want picks. Chasing/Shopping raise or lower the priority of relevant offers, not exclude all others. Same-position overlap and multi-position priority details remain open.

### Selected assets and one search promise across entrances

The same selected-asset promise applies to the canvas, SEND/GET pins, player entry points, League Buy/Sell and More Offers. Attempt the complete selection first. Additional sweeteners are permitted; selected pieces define inclusion intent, not a ban on adding other pieces.

When the complete selection yields no matches:

- Give the brief no-match notice the owner requested.
- Present both options rather than privileging SEND over GET.
- Do not substitute a different player for a selected target.
- Use existing trade-chip tags to distinguish fulfilled selections/partial alternatives. No new panel or mandatory confirmation step is requested.

**Interpretation requiring a precise contract before implementation:** both options likely means SEND-anchored and GET-anchored alternatives when the full package is unavailable. It does not establish minimum retained assets, an equal quota, two mandatory result groups or a default partner expansion. Do not label an alternative that omits an original target as though the original request was fulfilled. An explicit single-player target must not silently become a different player.

Preserve the user's draft and search choices on Back. More Offers filters, partner and shape survive Back but reset on a league switch; universal rankings and account-wide fairness do not reset. The answer about tagged players not surviving sessions may concern temporary selections rather than saved player rules. Do not delete durable Untouchable/Target settings on that assumption. More Offers' initial keep/release defaults for the remaining package and partner also remain open.

### Trade modes use the owner's value language

| Mode | Confirmed meaning |
| --- | --- |
| Tier up / Consolidate | Acquire a player more valuable to the user, often by sending multiple pieces. The user's tier takes precedence; a meaningful within-tier upgrade may qualify. Market values shape the accompanying pieces. |
| Tier down | Receive a lower-valued player plus a useful outcome: desired picks, a younger rebuilding asset, or help at a competitive team's needed position. |
| Same value | Use the user's tier/draft-pick valuation to define the relationship; market values shape the accompanying pieces. |

Current-season usefulness must not determine the specific Tier up classification for now. It still matters to overall outlook/roster suitability. No same-position-only restriction is approved. Exact within-tier upgrade tests and close-value bands require an engineering proposal.

Keep tiers and draft-pick equivalents as the user-facing vocabulary. Do not expose Elo or replace existing card explanations with new internal-score, conviction or confidence panels.

### Player tags and stud tax

Untouchable is reluctance, not a hard lock. Above-market return is central; a compelling package should fit outlook and personal value, or address a strong need with a same-position replacement. The owner's probably-never-one-for-one statement is a strong preference, not an absolute ban. The exact combination of those conditions is not yet a formal gate.

The owner is unfamiliar with the separate Not interested tag. Verify its actual surface/meaning before deciding its policy; do not remove or reinterpret it automatically.

**Remove the user-facing stud-tax Off option.** Keep package adjustments. Removing Market/Heavy was not requested. Accommodating different managers' stud-tax settings is not P0. The active common policy and migration of previously saved Off values require a documented decision; merely hiding the control must not leave an unexplained hidden Off mode.

### Learning and separate risk adjustments

**Interaction-driven ranking changes must never change a player's tier.** They may change within-tier position only, including after repeated interactions. This does not prohibit the user deliberately changing a tier. Undo must reverse the ranking effects attributable to the undone action.

The precise like/pass/reason-to-adjustment mapping remains open. Willingness to execute a package is not evidence that every asset in it should independently move up or down. The owner expects interactions to help represent buying/selling willingness, but has not specified separate buy/sell threshold mathematics.

Separate age-related decline and a contender's immediate lineup hole may influence recommendations. Keep adjustments within the user's tier. Do not add the rest of the interview's injury/role/contract/bye/exposure modifiers as new scope by default. Existing risks already reflected in market/personal rankings are not being removed.

Engineering must avoid applying the same concern twice: staying inside a tier prevents cross-tier movement but does not by itself prevent duplicate age penalties within that tier. Record adjustment components distinctly so this can be tested.

### Future picks

Predict early/mid/late first-round slots for **next year only**, using the relevant league/draft calendar. Do not project slots multiple years out, discount picks merely for being further away, or add class-quality adjustments.

The owner says known draft slots already replace estimates. Verify and preserve that behavior rather than treating it as an unbuilt feature. Uncertain next-year slot fallback remains open. Modeling how the proposed trade changes the original team's projected pick is recognized as relevant but deferred from the current focus.

### Meaning, timing and privacy

Like, queue and provider-send express willingness to execute the displayed package. They have different side effects: liking or queueing does not authorize automatic provider transmission or execution.

Preserve original terms and original valuation when the second manager sees the opportunity later. Interest lasts no more than two weeks; no separate first-manager reconfirmation is required. The exact starting event, renewal/withdrawal behavior and standing-offer permission are still open. Actual ownership/eligibility must remain valid; preserving an old price does not make an unavailable asset tradable.

Acquisition interests and Untouchable tags may be shared with a potential partner. **Personal tier placements may not.** Privileged snapshots must not leak the other manager's tiers through card payloads or derived values. No broader permission to expose exact private rank order was given. The owner does not request additional inference disclaimers or card explanations; this does not authorize claiming an inferred preference was explicitly declared.

## 3. Engineering delivery sequence — proposed, not an owner-selected schedule

### First: establish current coverage and the common contract

Trace each entry point through generation, fallback, ordering and actions. Reuse existing code that already satisfies the decisions. Do not assume the older review's bugs still exist or that a field's presence proves every path consumes it.

Candidate first-release priorities are consistent selected-asset handling, personal-tier mode classification, consensus fallback, tier-preserving learning/Undo, declared-outlook precedence, privacy, offer identity/timing and auditable value inputs. Include removal of Off once persisted-value treatment is agreed. These priorities do not require rewriting all three generators.

The historical UX review remains a useful regression checklist for receive-only intent loss, lost drafts on Back, Retry dropping request context, anchored loading/empty states and misleading send/queue wording. Its proposed extra receipts, required/optional controls and new explanation treatments are not automatically approved scope.

### Then: instrument and compare policy without replacing generators

Keep `current`, `challenger` and `gen_v2`. Record generator identity separately from policy version. An orthogonal policy treatment/shadow comparison remains the proposed experiment design; no winning arm or rollout percentage is selected here.

First validate snapshots and replay candidate sets. Propose strict/relaxed loss bounds and package calculations before serving a new pricing policy. Compare both usefulness and market cost, and include candidates rejected by the proposed policy in shadow evidence. Do not optimize apparent like rate by hiding rejected candidates from the denominator or padding offers with compensation.

The September 4 historical analysis had impression-linked decisions from only five users. It is useful directional evidence, not grounds to declare a permanent winner. Exact ordering, diversity and graduation metrics remain experimental; do not inherit the old brief's numeric thresholds or quotas as owner decisions.

### Keep out of this first scope

Manager-specific stud-tax differences, distant-year slot projections, class-quality adjustments, trade-induced pick-projection feedback, additional risk modifiers, new card explanation panels, and a wholesale generator replacement. Standing-offer expansion should wait for its authorization contract. Do not infer that these deferrals make core personal rankings, outlook or reciprocal needs optional.

## 4. Database orientation and evidence requirements

### Where historical evidence lives

Production is Render Postgres. Local `data/trade_finder.db` is development data, not evidence of live behavior. The gitignored root `secrets.local.env` contains production credentials; never print the connection URL, place it literally on a command line or commit raw user data. Production research must use read-only, time-limited connections. No new production query was run for this handoff.

The following inventory comes from the September 4 read-only research. Verify the current schema before adding any field or table.

| Existing table | Meaning and limitation |
| --- | --- |
| `deck_impressions` | A card served in a deck, with attribution by `impression_id`; served is not the same as viewed. |
| `deck_outcomes` | Append-only views/decisions/undo/proposal outcomes linked to impressions; duplicates and late events require effective-outcome reduction. |
| `trade_decisions` | Older decision history with weaker attribution; not a substitute for a complete offer-time snapshot. |
| `trade_pass_reasons`, `bad_trade_flags` | Reasons and explicit poor-offer reports; do not conflate all reasons with player dislike. |
| `trade_matches` | Two-sided interest; must link the specific observations from both managers. |
| `member_rankings` | Latest published board, overwritten as it changes; cannot reconstruct a historic personal valuation. |
| `player_value_history` | Historical consensus snapshots; not a record of either manager's personal board. |
| `deck_candidate_sets` | Candidate evidence after its write point; cannot explain earlier discarded candidates on its own. |

### Immutable context to retain — proposed data contract

Reuse existing columns where adequate. Any new names/schema are implementation choices, not mandated migrations from this document. Preserve:

1. **Identity:** league, participants, exact assets by giver, package version, originating request and predecessor surface. Use a shared canonical identity for mirrored packages plus an opportunity/version identity that cannot revive an expired expression of interest accidentally.
2. **Original valuation:** per-asset market source/version, each manager's private tier and within-tier position where supplied, consensus fallback markers where absent, package adjustments, and the exact valuation/presentation version used for the original card. Retain internal numeric values for replay without exposing them to the opposing manager.
3. **Input context:** declared/inferred/resolved outlook, league scoring/size/lineup/bench rules, roster ownership, pick origin/year/known-or-projected slot, projection time/source, tags and positional goals actually consumed.
4. **Request fulfillment:** selected SEND/GET pieces, retained/omitted selections in the result, partner scope, trade mode, fallback reason and chip tags shown. Preserve the original request separately from an alternative result.
5. **Policy:** generator arm, policy/version, fairness preference, actual loss limit, package-adjustment policy, value/fit contributions and any permitted relaxation reason. Provenance does not imply method-based confidence weighting.
6. **Per-manager timeline:** served, actually viewed, acted, undone, expired and matched times, with links to each manager's impression. Preserve the original displayed terms/valuation separately from any later internal diagnostic snapshot.
7. **Action and learning causality:** idempotent event identity, exact package committed to, ranking state before/after, affected within-tier positions and the action an Undo reverses. Do not fabricate unavailable historical state.
8. **Provider result:** originating impression when applicable, final package after edits, provider success/failure and an idempotent proposal record. A provider-send snapshot describes the final transmitted package, not an outdated suggestion.

Do not copy current `member_rankings` into an old record and call it offer-time truth. Do not relabel consensus fallback as personal input. Separate privileged internal audit access from what another manager can retrieve. Define retention/access alongside schema work.

Later B-view or match-time values can be recorded internally to explain changes. They must not silently replace the original offered valuation, automatically expire a still-valid offer solely under a new pricing policy, or create an unrequested reconfirmation gate. Ownership failures, actual expiry and unsupported transaction states are different from valuation drift.

Telemetry writes should be observable and idempotent, with failure counters. Distinguish served, viewed, liked, matched and confirmed-provider-send outcomes. A second manager who never saw the opportunity did not reject it. Report same-policy and cross-policy pairs and group uncertainty by user/deck rather than treating every card as independent.

Keep demo, shadow and ghost records out of the live-user conversion funnel while retaining them as separate diagnostic evidence. Validate impression ownership and league/participant scope when linking actions; an attribution ID is not authorization to act on another user's card.

## 5. Verification and acceptance cases — to run during implementation

These are requirements/examples for verification, not tests claimed to have passed tonight.

1. Equivalent requests through supported entrances preserve the same selected assets and preference sources, including receive-only requests.
2. Full-selection searches attempt all pieces. No-match fallback uses the brief notice and existing accurate chip tags; it neither silently substitutes the target nor forces SEND-first priority. Do not implement unresolved side coverage as an undocumented default.
3. Back preserves the current draft and More Offers filters/partner/shape. League switching clears temporary search state without clearing universal rankings, account fairness or durable rules by accident.
4. A controlled user-tier/market-tier disagreement uses the user's tier for Tier up/Same value, while market values inform the companion package. Current-season usefulness alone does not change Tier up classification.
5. Partial boards preserve explicit entries and use consensus only for missing entries on either side. The fallback source remains identifiable.
6. Selected outlook overrides inference; a tanking trade may reduce immediate production, and a noncontending partner is not assumed to want a veteran solely because of a lineup hole.
7. Chasing/Shopping and Untouchable influence recommendations without categorical bans. Do not turn probably-not-one-for-one into an absolute exclusion.
8. Every implemented pricing path respects the agreed strict/relaxed bounds, including sweeteners, retries and fallback. Extra cost has a recorded permitted reason. Bounds must first be selected in the implementation plan.
9. Stud-tax Off is no longer selectable. Existing saved Off values follow a documented migration; package adjustments remain active under the agreed policy.
10. Repeated interaction learning never moves a player across their tier boundary. Undo reverses attributable ranking changes; deliberate tier changes by the user remain possible.
11. Age and need effects stay distinguishable and do not double-apply the same adjustment. No unapproved extra risk module is added.
12. Slot projection changes next year's firsts only. Known-slot behavior is preserved; distant picks gain neither invented slot forecasts nor automatic year discounts.
13. Interests and Untouchable tags can be shared without disclosing the other manager's private tier placements, including through API values or diagnostic payloads.
14. A sees/likes first and B encounters the offer later: original terms/valuation are preserved, both observations are attributable, and the agreed expiry rule respects the maximum two weeks without a separate A-reconfirmation gate.
15. No exposure is distinguishable from a pass; Undo/duplicate events do not inflate conversion; a confirmed provider send is attributed once to the final package and its origin.

Use backend/unit and mobile structural tests where mechanically checkable, a file-and-line code-walk for cross-surface behavior, and a focused manual TestFlight checklist for navigation/timing/presentation. Per repository policy, do not run Maestro or simulator captures. Update affected API/data/config documentation and the test ledger when implemented.

## 6. Remaining decisions — not additional homework tonight

The following should be handled as small engineering proposals or later targeted clarifications, not silently filled in from the older brief:

- Strict/relaxed market-loss caps, package math, within-tier upgrade thresholds and action-specific within-tier learning.
- Exact selected-asset coverage meant by present both; More Offers' initial package/partner scope.
- Temporary tagged-player persistence versus durable player-rule persistence; actual Not interested behavior.
- Active stud-tax policy and migration of saved Off values.
- Double-counted age/need effects, uncertain next-year pick slots and missing league-setting handling.
- What evidence suffices for partner suitability without personal data; full overlap/multi-position semantics.
- Expiry clock start, renewal, withdrawal/Undo beyond rankings, and standing-offer authorization.
- Final experiment success metric and ordering/diversity trade-offs; Part 5 remains deferred.

Do not use these open details to delay safe read-only coverage checks or documentation. Do not ship a behavior-changing default where it would materially change the user's request without settling that scope.

## 7. What not to carry forward from the older proposals

The [earlier engineering brief](history/engineering-brief.md) remains useful for historical DB evidence and attribution design, but not as an unqualified build specification. Its personal-surplus-primary ordering, ranking-method confidence hierarchy, two-high-confidence-board premium prerequisite, exact fairness floors, deck quotas and new conviction/confidence labels are not owner-approved policy.

The [earlier UX review](history/mobile-ux-review.md) remains useful for historical continuity findings. Its proposed additional controls, receipts and explanations are not approved wholesale. The new contract is to preserve meaningful inputs and flow while using the existing tier/chip language—not to add a new presentation layer around the engine.

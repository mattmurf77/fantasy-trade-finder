# Team overhaul — owner decisions

This is product discovery and a local interactive mockup. It is not production implementation or release evidence.

## Accepted direction

- The asset selection is an eligible pool. A roadmap does not need to move every selected asset.
- Alternative roadmaps may group assets differently. This interprets the owner's “Yes” in answer 2; the interpretation was stated in chat and not corrected.
- If rebuilding without their own next-season first, include a trade for that exact pick and prominently highlight **Priority 1: Recover your first** across the overall overhaul. This is advisory execution order; other trades are not blocked. This is separate from priority ranks within each sell-asset package.
- Users choose the balance between draft picks and younger players in rebuild returns.
- After a decline, wait for the user before sending another offer so they can negotiate. Optional automatic progression is a possible future enhancement, not the default or a current implementation commitment.
- If compatible likes are insufficient, generate more offers for review and prompt users to reconsider the assets available to package. Do not substitute a smaller-plan recommendation as the default response.
- Position choices are preferences for the roadmap.
- The all-in draft-pick budget is chosen by the user.
- Roadmap outlook and position settings remain separate from regular finder settings.

## Latest mock review

- The “Review scenario” box was only a prototype control for comparing owned/missing first-round-pick states. The actual app reads league ownership; remove the control from the mock's product screen.
- Use **Continue** for the asset/target setup CTA.
- Set alternative-offer priorities one sell-asset package per page, using drag and drop like the Tiers page.
- Preserve the original same-priority requirement: offers in the same priority tier can go out together, with an explicit first come, first served warning in the send summary.

## Approval and new entry request

The owner approved the revised core mockups and requested this durable engineering handoff on 2026-09-06. They then requested a missing feature-entry mock. The Acquire launch/resume card added in this folder is a new placement proposal, not covered by the earlier core-mock approval.

## 2026-09-07 — Owner confirmations of the nine open choices

Presented in chat by the scoping session after the v1 merge (`a8ef182e`); answered by the owner the same day.

- **D1 launch scope — REVISED:** "MFL and ESPN trade sending has been validated. It should work for all." Sends are offered on Sleeper, MFL and ESPN behind their existing send flags (`trade.send_in_sleeper`, `trade.send_in_mfl`, `espn.send`, all on in production on 2026-09-07). ESPN still cannot send draft picks (players only); iOS remains the only client.
- **D9 entry/resume — agreed:** Team overhaul card on Acquire below Team review; one active overhaul per league.
- **D3 review completion — agreed** (complete-review, 24-card batch). **D4 same counterparty — agreed.** **D5 pending offers — yes** (hold later tiers, no timeouts, user asserts decline/withdrawal). **D6 combined roster — yes.** **D7 counteroffers — yes** (platform-only). **D8 refresh — yes.** **D2 draft-order copy — yes.**
- **Tied offers on Sleeper:** "Sleeper behavior shouldn't be an issue. You can send an offer to more than one team at a time." `supports_conflicting_offer_race` is `supported` for Sleeper; MFL/ESPN stay `unverified`.

## Provenance

Owner replies in this task: bridge requests `4808bdf9-ced7-49cb-8218-b8952b29eb0d`, `f67fe37f-a909-4c54-acff-77426f6821e2`, and `d77f4646-d413-4ac9-b18a-77febeda0147`. The original user brief defines the two extreme outlooks, disjoint outgoing assets across independent trades, 4–5-trade and 4–5-roadmap targets, like/pass review, bulk-send payoff, and resumable execution.

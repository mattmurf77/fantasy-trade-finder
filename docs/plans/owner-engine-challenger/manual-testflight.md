# Owner construction trial — device checklist

Status: **UNRUN**. No simulator substitute. Record the actual TestFlight build,
account, league, time and observed result for each executed step. A successful
build/submission is not Apple availability or a device pass.

## Entry and package behavior

1. Open a linked league with a saved outlook and personal rankings. Find trades
   with no selected assets. Verify owner-attributed offers are 1×1, 1×2 or 2×1
   in total assets (picks included). Controls may retain their older shapes.
2. Change personal rankings for a clearly preferred acquisition without changing
   market data. Regenerate. Verify the captured owner candidate set responds;
   the same exact package's market price must not increase solely with preference.
3. Change only outlook (all-in versus rebuilding) on a suitable test roster.
   Verify owner candidate targets/packages respond, not merely card order.
4. Select SEND, then GET alone, then both sides and a specific partner. Verify
   full selections/partner are honored whenever feasible. Explicit multi-asset
   selection may create larger packages; that is not organic shape leakage.
5. Choose an infeasible multi-selection. Verify no silent target substitution:
   an available partial result says it includes part of the selection, and the
   visible columns show exactly which assets remain. An empty search is honest.
6. Open More Offers from a trade chip and the Find a Trade canvas. Exercise Tier
   up, Tier down, Same value and position choices. Verify these use personal tier
   direction with market-priced companions and keep the visible selection.
7. Repeat from league buy/sell. Use Back to return through each entrance. Verify
   the existing selection/shape/partner context remains coherent; no new league's
   stale selections are carried in.
8. Open More Offers with fairness on, then off. Verify both its initial query
   and widened query carry the respective 0.75/0.50 floor. Confirm Back does not
   silently reset the preference. No claim that the setting is cross-device.

## Exposure and response truth

9. Open a selected offer for more than 500 ms while foregrounded. Verify one
   linked `deck_card_viewed`. Scroll it offscreen, background the app, or cover
   it with another screen: that time must not count as visible dwell. Prefetched
   neighboring cards must not receive views merely by mounting.
10. Swipe the More Offers pager. Verify only the settled active card receives a
    view. Return to an already viewed occurrence: no duplicate viewed event.
11. Pass, Undo inside the held interval, then pass again and let it commit.
    Verify Undo cancels the POST; the committed response joins the card tapped,
    not the newly visible card. Queue an exact offer and verify its owned
    impression is joined once; an edited package must not borrow that credit.
12. With the serving trial active, inspect server order versus display order
    with fairness on/off and after a decision. Incompatible model scores must
    not reorder the mixed deck. A Featured owner offer leads by server
    `recommendation_rank`, not the largest market gain.

## Release/readout cautions

Confirm backend source, include/serve settings and actual client build before
calling any run a trial. Older clients may ignore ordering/exposure metadata;
stratify/exclude those versions in the readout. A two-sided match is a later
manager-specific action, not a second view inferred from the first like.
Source/data collection details: [trial protocol](trial-protocol.md).

# Segrave — Onboarding Flow Notes (verbatim; v2, received 2026-08-23)

> Captured word-for-word from the operator's message. **v2, same day:** adds the
> "Manual Trade Calculator Tour" section and drops the "Still to capture" stub;
> v1 is in this file's git history. The dispositions live in [plan.md](plan.md);
> this file is the source record and is not annotated.

Working notes on redesigning the onboarding process and guided tour, with the aim of making the current disjointed flow more cohesive and streamlined. Covers the onboarding process itself, the guided tour, and updates needed for additional supported platforms.

## Primary Onboarding Flow

**Launch page**

* Currently prompts for a Sleeper account only, though Sleeper is just one of the fantasy platforms we support.
* Launch page should mention Sleeper, MFL, and ESPN, and give the user the opportunity to import a league from any of the three.
* Remove the "tour the app with a demo league" link — that feature isn't needed going forward.

**Guided tour — global issues**

* Many pop-up windows can only be exited via a very small button in the top right corner.
* Holistic change: add a much more prominent Next button on any onboarding prompt that doesn't require a specific user action.
* Skipping the tour entirely is already an option; otherwise Next should bring up the following window.
* The initial tour message needs better content — clearly explaining that we'll be walking the user through the experience.

**Second pop-up — account entry**

* Currently prompts for a Sleeper username.
* Needs updating to offer Sleeper, ESPN, or MFL, in line with the new landing page.

**League selection**

* Fine as is. Clicking a league appropriately closes the window, so no Next button needed here.

**Team selection → finding a trade**

* After selecting a team, the window says it's reading rosters and finding a trade — but that doesn't actually happen. The user has to hit Find a Trade themselves.
* Keep the copy, but auto-click the Find a Trade button when the user lands on the page for the first time.

**Trade presentation**

* Copy needs work. It should provide context on how we generate these trades: consensus dynasty values, plus the user's own rankings if they've already input some.
* Same navigation problem as elsewhere — the only way to proceed is hitting the X, with no Next or other CTA.

**Ending the flow**

* The current last page is too abrupt: it tells the user to disposition the trade by swiping left or right, and then the flow just stops.
* There's a more comprehensive onboarding flow already built, currently living on the manual calculator page.
* Merge that flow into this one so there's a single cohesive experience. This becomes a planning session on which flows to keep, which to close, and how to combine them.

**After accepting a trade**

* Remove the current CTA that says the other user hasn't seen the card and offers to send it directly in Sleeper — it pulls the user out of the experience and onto a page we don't need to push yet.
* Instead, show a window confirming the trade is now queued for their leaguemate to review.
* If that leaguemate isn't on the app yet, say so. That becomes a natural moment to suggest inviting them so they can see the trade.

## Manual Trade Calculator Tour

The second, more comprehensive onboarding experience, launched from the manual trade calculator page.

**Opening steps**

* Starts by telling the user to switch to in-league — good.
* Then mentions setting an outlook and gives a Set Outlook button, but doesn't actually highlight the outlook section. Miss.

**Set Outlook pop-out**

* The window needs to open more. It sits very tight to the bottom of the screen — technically everything is on the page, but we need a bigger bottom margin.
* The analyst already pops out behind the screen while the user is still editing in the pop-out window. It shouldn't appear until the user hits Done.
* Once Done is hit, it does a good job: highlights the section, locks the box onto the screen, and tells the user to hit Next. Good.

**Find a Trade / check**

* Both look good.
* The X button should be hidden during the tour — right now it just clears the trade on the page.
* Better approach given the room available: make the Find a Trade button less wide and change the X to a Clear button at the bottom.

**Add Player**

* Looks good, no changes.

**Fairness meter**

* After Find a Trade, everything looks good up until the fairness meter. The prompt pops, but the screen doesn't focus down to the meter.
* Two fixes: the page should literally scroll down to the fairness meter, and it should get the same highlight box used throughout the rest of the experience.

**Send in Sleeper**

* Works as is. If the scroll to the fairness meter happens first, the Send in Sleeper button will already be in view — no separate fix needed.

## Open questions / research

How far should the guided tour go? Right now it's focused on getting users to their first trade suggestion. That's good in the sense that Find a Trade is the core experience of the product, and leaving users there to keep dispositioning trade suggestions is really the ideal end state for the app. But there are other pages and experiences worth showing, because they do a good job of bringing the user back into the Find a Trade flow. Open question: walk the user through the entire app, or stop at the first trade and give them the option to continue the tour?

Multi-platform account lookup: Sleeper onboarding is easy because all we need is a username. Unclear whether ESPN and MFL can take the same approach. Needs research on whether a user ID or email address can be used to look up an individual's league, or whether we truly need the league ID (the way to link a league without signing in), or whether we'd have to require sign-in at launch.

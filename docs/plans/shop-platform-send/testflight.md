# Manual TestFlight checklist — Shop sends on the platform (11-06 binary)

Operator, on the 11-06 TestFlight build. You need one league on each platform with a leaguemate you can send to: Sleeper, MFL and ESPN. Every send is real, so use a test trade you're happy to cancel on the platform afterwards. (D-056: this is mobile's only runtime evidence.)

**Getting to Shop:** Trades → Find a trade → on a deck card, the give side's **More offers** opens the Shop window for that player.

1. **Sleeper league.** The offer tile's primary button reads **"Send in Sleeper"**, the deck's send button, not "Show it to @name".
   - Tap it → the "Send this trade?" confirm (or "Heads up before sending" first, if the pre-check warns) → **Send**.
   - Expect "Trade sent / Check your Sleeper app for the pending offer." and the button then reads "Proposal sent". Open the Sleeper app: the offer is pending to that leaguemate, with exactly the tile's players.
   - In Fleeced, @name's deck does **not** get a new likes-you card for it (ask a second tester, or skip if you can't).
2. **Sleeper, Cancel.** Tap the button, then **Cancel** on the confirm. Nothing is sent: no pending offer in Sleeper.
3. **MFL league.** The button reads **"Send in MFL"**. Confirm → Send → "Trade sent / Check MFL for the pending offer." It's pending in MFL **to the tile's leaguemate, with exactly the tile's players and picks**.
4. **ESPN league, players only.** The button reads **"Send in ESPN"**. Confirm → Send → "Trade sent / Check ESPN for the pending offer." It's pending in ESPN **to the tile's leaguemate, with exactly the tile's players**.
5. **ESPN league, a package with a draft pick.** This needs an ESPN league whose draft picks are assigned to teams, so Shop offers can include one; pick an offer whose sides include a pick. Confirm → Send → **"Couldn't send / Draft picks can't be sent to ESPN yet, so nothing was sent. Remove the picks or copy the trade instead."** (`espn_pick_unsupported`). Nothing is sent to ESPN.
6. **The ✕ still works.** Tap ✕ on a tile → "Dismissed · Undo" → Undo brings it back. Dismiss again and leave it → the next tile shows.
7. **Sleeper, not linked yet** (a Sleeper account not connected in Fleeced, or after Settings → disconnect). Tap the button → **"Connect Sleeper first"** → Connect → finish connecting → back in Shop, tap the button again → the "Send this trade?" confirm → Send. Expect it to send as in step 1.
8. **A league that can't send:** skip it for this binary. Fleaflicker is dark, so no connectable platform lacks a send today. When one exists, the tile shows the "Sending isn't available … copy this trade" line and **Copy trade**, and nothing is sent.

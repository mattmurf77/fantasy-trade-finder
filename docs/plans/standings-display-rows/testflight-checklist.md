# TestFlight checklist — Standings: stat rows, SoS, Remaining schedule, likely pick range (D-285)

Run on the first build that carries `feat/standings-display-rows`. This is the only runtime evidence the change gets (D-056). Log each step pass / fail / not run in `living-memory/TEST_LEDGER.md`, with the build number and the forecast date shown under the table. Code walk and test counts: [evidence.md](evidence.md).

**Leagues** (all Sleeper, your account). The numbers in brackets are from the 2026-11-24 forecast and **move with every weekly run** (Tuesday 09:30 ET), so the checks below compare the app against itself, not against these numbers:

- **La Resistance**: you are 1–10 [SoS 5th]; 9-slot lineup; misses the playoffs nearly always [likely 1.01–1.02, 1.01 chance about 84%]; a free-agent fill in your week 13.
- **Fantasy Football Version 3**: you are 7–4 [SoS 5th]; K + IDP, 15-slot lineup; misses in under 25% of seasons.
- **Lakeview League**: median-game league; you are 2–20 [SoS 7th]; 10-slot superflex; several players with no estimate.
- Any **ESPN or MFL** league, and if you have one, a **Sleeper league with no saved forecast** yet.

**Device:** the narrowest current iPhone, 375 pt (iPhone SE 2nd/3rd gen, 12 mini, 13 mini). Without one, Display Zoom ("Larger Text" in Settings → Display & Brightness → Display Zoom) on a Plus or Pro Max model renders at 375 pt; on a 6.1-inch model it renders at 320 pt, the width where names are expected to cut (step 3). Check the width you tested on before logging.

## Standings table

1. **Record view columns.** La Resistance → Standings. Headings read **Team · W–L · Proj. W–L · Play/offs · SoS**: "Proj." over "W–L", "Play" over "offs", "SoS" with a lowercase o. Opens sorted on W–L, best first.
2. **Names at 375 pt.** Lakeview League, Record view: the longest team name (16 characters) shows whole, no ellipsis; your row shows "mattmurf77" whole plus the "You" badge. Repeat with the caret on each of W–L, Proj. W–L, Playoffs and SoS (tap each): still whole, and no heading text is clipped or overlaps the caret. **Expected, not a failure:** on a "You" row whose name is wider than about 76 pt (roughly 11 characters, e.g. a league-mate testing on their own account) the name ends in an ellipsis, as it already did on the previous build; log it if seen.
3. **At 320 pt only** (if tested there): names may end in an ellipsis (as on the previous build); numbers and headings are never cut.
4. **Heading alignment, every sort state.** For each numeric heading in turn (tap it, then tap again to reverse): the sorted heading's text ends at the same right edge as the numbers below it, exactly like the unsorted headings; the ice caret sits to the **left** of the text. For "Play"/"offs" both lines end on that edge. Tap Team: its caret sits to the right of "Team". Fail if any sorted heading sits visibly left of its column (the old 12 pt offset).
5. **SoS values.** In each of the three leagues, Record view:
   a. Every team shows a rank 1st…12th, each used once; ranks 1st–4th carry "hard" underneath, 9th–12th "easy", 5th–8th no word. The two-line cell (rank over word) fits inside the row without making it taller than the other rows or clipping either line.
   b. Tap SoS: 1st at the top; tap again: 12th at the top.
   c. Hand-check your own rank: open your team → Remaining schedule; average the **Opp.** column. Do the same for the team ranked just above you and the one just below. Your average must sit between theirs (above-ranked team's average ≥ yours ≥ below-ranked team's). Also open the 1st and 12th teams: their Opp. averages are the league's highest and lowest of those you checked.
   d. Write down your rank per league in the ledger (it should be near the bracketed values above unless the forecast has moved).
6. **No forecast → dashes.** In a Sleeper league with no saved forecast (if you have one): Proj. W–L, Playoffs and SoS show dashes; W–L sorts; the line "Projections aren’t available for this league yet." and Check for update show as before. Sort on SoS: dashes stay at the bottom both ways.
7. **Points view unchanged.** Tap Points: PF · Max PF · Proj. Max PF, same values and widths as the previous build (only the caret moved to the left of the sorted heading). Opens sorted on PF.
8. **Under the table.** With a forecast, exactly two things: the caption ("Weekly estimate", or "Last saved: {date}", plus "· Incomplete" / "· Provisional" when they apply) and "Your league’s own tiebreakers and divisions may order tied records differently." **Not** present: "Partial Sleeper data", "Projected W–L is the most likely final record…", "Max PF is the season so far…", any "Weekly update…" sentence, any "…lineup slots had a starter…" sentence. Check in both views.

## Open team tile

9. **Rows, Record view.** Open your team in Version 3: rows **Points for** (one decimal), **Max PF** (whole, comma), **Projected Max PF**, **Average final record** (e.g. 8.8–5.2), and **Bye odds** if the league has byes. Labels left, values right-aligned under the number columns. No dot-separated sentence anywhere above "Final record odds".
10. **Rows, Points view.** Same team, Points view: **Record**, **Projected**, **Playoff odds** (same text as the Playoffs cell in Record view), **Average final record**, **Bye odds**. Open a team that is not yours: same row set.
11. **Sections in order:** Final record odds · Remaining schedule · Draft pick odds, then (your own card only) Max PF moves / Playoff targets as on the previous build. Final record odds content unchanged.

## Remaining schedule

12. **Rows.** Your team in each of the three leagues → Remaining schedule. Header **Wk · Opponent · Proj. · Opp. · Win %**; one row per unplayed regular-season week only (no completed weeks); scores to one decimal; Win % whole, never "100%" or "0%" (">99%" / "<1%" at the ends). A row where Proj. is well above Opp. shows a Win % above 50%.
13. **Consistency across teams.** Open the opponent of your next week: its row for that week shows your team as opponent, its **Proj.** equals your row's **Opp.** and its **Opp.** equals your **Proj.**
14. **Opened week, 9 slots.** La Resistance, tap your next week: 9 lineup rows "slot · player · points" (points one decimal), then a "· no estimate" row for each player without one, and nothing else. **Not** present: "vs …: win …, tie …, loss …", "standard deviation", "Max PF target", "not calibrated", "Show model diagnostics", "Available projections", "Score not recorded yet", "partial contributions", "IDP bye replacement", "Available lineup contributions", any player-id exclusion line.
15. **Opened week, K + IDP.** Version 3, your next week: 15 rows including K and the IDP slots; any IDP flex reads "IDP"; nothing clipped in the slot column.
16. **Opened week, superflex.** Lakeview, your next week: 10 rows; the superflex slot reads "SF"; the no-estimate rows follow the lineup.
17. **Free-agent fill.** La Resistance, your week 13 (or whichever week has an open slot): the filled slot's player name is followed by "(free agent)".
18. **Open / close, one at a time.** The Remaining schedule section starts closed. Tapping a week row opens it (ink-3 fill, ice chevron up) and tapping again closes it. With week 12 open, tap week 13: week 12 closes and week 13 opens (never two open). The numbers in the other rows do not shift when the chevron changes. Close and reopen the team: no week is open.
19. **W / L / Even fallback:** **not observable on TestFlight** (the server always writes a win chance, `backend/league_projections/simulation.py:310`); covered by `check-league-projections.js`. Log "not observable".
20. **Season over:** "No regular-season games left." appears only after the last regular-season week's forecast. Log "not run" until then; re-check after that weekly run.

## Draft pick odds

21. **Above the 25% bar.** La Resistance, your team → Draft pick odds: "Estimates assume regular-season Max PF draft order.", then rows **Miss playoffs**, **Pick owner**, **Pick** ("2027 round 1"), **Likely pick if this team misses** (e.g. "1.01–1.02") and **Chance of the 1.01**. **Not** present: "Expected pick if this team misses", "Missed-playoff simulations".
22. **Range and 1.01 against the nested list.** Open "Pick odds and range" (its three lines and the Pick n list are unchanged). **Chance of the 1.01** equals **Pick 1**. Add the Pick n values from the top and divide by the Miss playoffs value: the first pick where the running share reaches 10% is the range's low end, the first reaching 90% its high end.
23. **Below the bar.** Version 3, your team: Miss playoffs under 25%, so rows Miss playoffs / Pick owner / Pick only; no range rows, no pick position at the top level (accepted). Then find any team in your leagues just above and just below 25.0% Miss playoffs (Lakeview and La Resistance have several above): the range rows show on every team at 25.0% or more and on none below.

## Home playoff card

24. **Note.** Switch to La Resistance → Home. The playoff card's **Projected pick** figure has a note "likely {range}" under the value, matching step 21's range. Tap the info button: after "Projected pick is where your own first-round pick lands…" comes "Likely range: where your pick lands in 8 of 10 simulated seasons where you miss the playoffs."
24a. **Both notes.** In any league where your own first is owned by another team and you miss in at least 25% of seasons, the figure shows "likely {range}" and then "owned by …" underneath, both readable, neither clipped. If the forecast is "last saved" there as well, all three notes ("last saved", "likely …", "owned by …") show in that order; check the card does not overflow or push "View ›" out of line. If none of your leagues has a traded first, log "not observable".
25. **No note under the bar.** Version 3 → Home: no "likely" note and no "Likely range" sentence; the card otherwise as before.
26. **League rankings tile.** La Resistance → League rankings: the same playoff card shows the same note (same component).

## Accessibility and edge states

27. **Large text.** Settings → Accessibility → Display & Text Size → Larger Text at the largest standard size, then one accessibility size. Standings Record view: headings readable ("Proj."/"W–L" and "Play"/"offs" not cut), numbers never truncated (team names give way first), the SoS rank and "hard"/"easy" both visible; tile rows truncate the label, never the value; Remaining schedule rows and opened-week rows stay legible, and the slot column still shows "SF" / "IDP" / "W/T" / "W/R" in full; Home note visible.
28. **VoiceOver.** On Standings: SoS reads "Sort by strength of schedule, not sorted", then after one tap "… toughest first", after two "… easiest first"; other numeric headings say "highest first" / "lowest first", Team "A to Z" / "Z to A". A team row reads its name, ", you" on yours, then each column (e.g. "strength of schedule 2nd, hard") and announces expanded / collapsed. Remaining schedule's section and each week row announce expanded / collapsed; a week row reads "Week 12, against {opponent}. Projected 137.4 to 111.0. 77% chance to win.". Each tile row and Draft pick odds row reads as one element, "label, value" (e.g. "Points for, 1612.5"). On Home the pick figure reads "Projected pick 1.01, likely 1.01–1.02" (then the owner and "last saved" if they apply).
29. **ESPN / MFL league.** Standings shows the "can’t read this league’s standings yet" card as before; Home shows no playoff card. Nothing new appears.
30. **League switch.** With a team open, switch league: the tile closes and the new league's table shows its own SoS ranks.

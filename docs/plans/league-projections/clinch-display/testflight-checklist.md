# TestFlight checklist — Playoff odds: 100% and 0% need a proof (D-262)

Run on the first build that carries `feat/playoff-odds-clinch-display`, AFTER the weekly forecast has re-run for the league under test (a forecast saved before D-262 has no proof, so every 100% reads ">99.9%" until then; that is expected). Log the outcome in `living-memory/TEST_LEDGER.md`.

You need two leagues (or one league at two moments): **A** with a team whose forecast is 100.0% but which has NOT mathematically clinched (e.g. 8-1 with five weeks left, as on 2026-11-13); **B** with a team that HAS clinched (no combination of remaining results drops it out: check by hand or ask for the server's `playoff_clinched`).

1. League A, Standings, Record view. The near-lock team's Playoffs cell reads **">99%"**, not "100%". A last-place team with no chance on the board but not eliminated reads **"<1%"**, not "0%".
2. Same table: tap Playoffs to sort highest first. The ">99%" teams sit at the top, in standings order among themselves. Tap again: "<1%" teams at the bottom.
3. Open the near-lock team (yours, ideally). Points view: the summary line reads "Playoff odds >99%". Draft pick odds: "Miss playoffs: **<0.1%**", not "0.0%".
4. Home, playoff tile (your team is the near-lock): the percentage reads **">99.9%"**. Tap it: lands on Standings as before.
5. Your own card, Max PF moves section (league with `league.max_pf_moves` on, a team that sometimes misses: use a near-lock miss-side team instead, e.g. "<1%"): the collapsed sentence reads "Your team makes the playoffs in **<1%** of simulations…" where it used to say "0%" (or ">99%" where it used to say "100%"). Open a row: "Playoff chance <1% → <1%".
6. Team Review (Trades → Team Review), standing beat: "Playoff chance **>99.9%**" for the near-lock team.
7. League B, the clinched team: Standings cell **"100%"**, Home tile **"100.0%"**, Team Review **"100.0%"**, team card "Miss playoffs: **0.0%**". Sorted highest first it ranks above any ">99%" team.
8. Any team between 1% and 99%: every surface shows exactly what it showed on the previous build (spot-check one at 45.7% on Home and Team Review, 46% on Standings).
9. Website (Season projections & Win Now → Projected standings) for league A: the near-lock team's Playoff odds read ">99.9%"; league B's clinched team reads "100.0%".

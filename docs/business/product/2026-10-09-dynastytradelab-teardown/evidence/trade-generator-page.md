# Dynasty Trade Lab — Trade Generator page (operator logged in, 2026-10-09)

URL: https://dynastytradelab.com/dynasty-trade-generator/ — three-column layout.

**Header strip:** "VIEWING: Sleeper · Fantasy Football Version 3 · Switch" (league switcher).

**Left — YOUR TEAM (mattmurf77 · 5 credits):** "Team Value: 61,023 · ▼ -2135 this wk". NEEDS: BALANCED. Inline nudge: "Isaiah Likely cannot start for you — cash them in for picks or a position you actually play." Position filter pills All/QB/RB/WR/TE/Picks + "Trade Block (2)". Roster grouped by position, each row: headshot, name, pos·team, value, weekly delta (▲/▼), "+" to add to the trade pool. Badges: BLOCK (Davante Adams), SURPLUS (Isaiah Likely). IDP/K rows show value 0 "—". Picks section: 2028 R4 (own) 751 · 2029 R1 (own) 1,750 · 2029 R2 1,186 · 2029 R3 878 · 2029 R4 757 (own picks only; round-level, "(own)" tag).

**Middle — TRADE POOL:** "MATTMURF77 GIVES" / "THEIR SIDE GIVES" with per-side player search, "Add a player" slots, "Trade Value Difference +0" under each side, a YOUR SIDE ↔ THEIR SIDE fairness slider (red→green gradient). "TRADE LOGIC: Add a player to either side to start a trade." "3-Team Trades — Two-team deals only." (toggle). "TRADE PROMPT" field. Buttons: "Find a Trade" · "Analyze My Trade" ("Add a player from another team to analyze a trade.").

**Right — TRADE PARTNERS ("Players who fit your roster needs"):** search "any player in the league…", tabs TARGETS / MANAGERS. Targets list = player, rostering manager, value: Josh Allen (MangoPatti) 5,613 · Jahmyr Gibbs (lofman) 10,760 · Bijan Robinson (jonbonjourvi) 10,592 · Kenneth Walker (bsharp3) 7,179 · Jeremiyah Love (JohnStanfield) 6,423 · Jonathan Taylor (dondags20) 6,179 · James Cook (MangoPatti) 5,428 · Ja'Marr Chase (bsharp3) 8,052 · ARSB (Shark357) 7,339 · Puka Nacua (lofman) 7,271 · CeeDee Lamb (MangoPatti) 6,855 · Justin Jefferson (KevinLake) 5,823 · Malik Nabers (gdubs10) 5,335 · Chris Olave (MangoPatti) 5,124 · Brock Bowers (JohnStanfield) 6,743.

**Floating "d" button** bottom-right = Lab Analyst chat widget.

Observations: the generator is a manual trade builder + "Find a Trade" generator in one screen; values are a single global scale (same numbers as the landing ticker) with weekly deltas; "needs" is a coarse label (BALANCED) plus one surplus nudge; partner targeting is a flat value-sorted list of players who outrank one of yours, not a counterparty-fit model.

## Hands-on (agent-driven, 0 credits, nothing submitted) — 2026-10-09

- **Adding players is free and instant.** The two "Search …" comboboxes autocomplete from the viewing league (my side: "Search mattmurf77's players"; their side: "Search players…" across all other rosters, result row shows pos · team · manager · value). Picking Isaiah Likely put him in "MATTMURF77 GIVES"; picking Breece Hall (bsharp3) flipped the pool into a partner context: headers became **"MATTMURF77 → BSHARP3" / "BSHARP3 → MATTMURF77 · NEEDS QB1, TE2"**, their-side search narrowed to "Search bsharp3's players", and the Hall card gained ✕ (remove) and 🔒 (lock) controls.
- **Value readout:** big number per side + "Trade Value Difference ±N" (here 0 vs 3,720 → +3720 / −3720) and the YOUR SIDE ↔ THEIR SIDE slider knob jumps to the deficit side. Pure sum of FantasyCalc values; no fairness band, premium or roster-fit term is displayed.
- **TRADE LOGIC** copy adapts to the pool: with only a target on their side it reads **"We'll build your side of a deal for Breece Hall."** The primary button is **"Build My Trade"** (generator fills in what I give for a chosen target) beside **"Analyze My Trade"** (grades a trade I built). Both cost a credit (not pressed).
- **3-Team Trades** toggle ("Two-team deals only." when off).
- **TRADE PROMPT** placeholder: *"Optional — ask for what you need, e.g. I need a RB back, mstevens wants my QB, or don't trade my 2027 1st."* — free-text constraints, i.e. the generator is prompt-driven (LLM) on top of the value sums; the saved report's "Notes: Even out the trade." was this field.
- **TRADE PARTNERS → MANAGERS tab:** every manager with a match count (lofman 2 · Shark357 1 · MangoPatti 4 · Bcork none · jonbonjourvi 1 · PaulSm3nis none · bsharp3 2 · gdubs10 1 · JohnStanfield 2 · dondags20 1 · KevinLake 1). Expanding bsharp3 shows **NEEDS QB1, TE2** and his full roster by position with values and weekly deltas, "TARGET" badges on the players flagged for me (Kenneth Walker, Breece Hall, Ja'Marr Chase), "BLOCK" on his trade-block players (Ollie Gordon), "IN TRADE" on Hall, IDP/K rows with no value, and **his picks including provenance — "2027 Round 2 (via mattmurf77)", "2028 Round 3 (via mattmurf77)"** — so pick ownership and traded-pick lineage ARE in the product, just not in the chat's snapshot (reply 11 said it had none).
- No request to `wp-json` fired while adding players or expanding managers — the league/roster/value payload is loaded with the page and all of this is client-side; only Build/Analyze/chat hit the API.

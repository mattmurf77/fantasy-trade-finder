# Dynasty Trade Lab — competitor teardown (hands-on)

**Date:** 2026-10-09 · **Source:** operator-logged-in walkthrough + 15 Lab Analyst exchanges + public-page capture (all in [evidence/](evidence/)) · **Owner role:** pm-competitor · **Public-research section:** [public-research.md](public-research.md)

## 1. One-paragraph read

Dynasty Trade Lab (DTL) is a web-only, credit-priced dynasty trade tool: connect a Sleeper or Fantrax username, and it gives you FantasyCalc values over your league, a template-driven "needs engine" (hold / spend / trade block / who to call), a trade builder + generator that scores trades as a straight value sum, and an LLM chat ("Lab Analyst") fed a per-request snapshot of the same data. The engine is thin — no consolidation premium, no partner-acceptance model, no roster-fit math beyond slot-count "needs" — and the chat is firewalled from its own product's methodology. Its strengths are packaging: a clean three-column generator, weekly value-movement surfaces, manager-level needs lists with pick provenance, free-text trade prompts, and a cheap credit model that lets a user try one real trade for free. Nothing here threatens Fleeced's core (personal Elo values + mutual-gain search + in-platform send), but three surfaces are worth copying.

## 2. Navigation and surfaces

Top nav: **Buy Credits · Dashboard · Rankings · My Account ▾ (My Trade Lab, History, Logout) · [Generate Trades]**; floating "d" bubble opens the Lab Analyst chat anywhere ([landing-and-stack](evidence/landing-and-stack.md)).

| Surface | What it does | Evidence |
|---|---|---|
| Landing | Marketing + value ticker + 3 features + credit pricing + FAQ | [landing-and-stack](evidence/landing-and-stack.md), screens 01–02 |
| Dashboard | TEAM STATUS (pentagon: QB/RB/WR/TE/FLEX, league rank "2nd") · TEAM NEEDS (BALANCED · HOLD / SPEND / TRADE BLOCK / WHO TO CALL / HOLD list / PLAYERS TO TARGET) · Lab Analyst panel · PLAYER STOCK MOVEMENT (league-wide weekly deltas with owner) · RISING FA STOCK | [dashboard-page](evidence/dashboard-page.md), screens 04–06 |
| Trade Generator | 3 columns: YOUR TEAM (roster by position, values, weekly deltas, BLOCK/SURPLUS badges, own picks) · TRADE POOL (two sides, value difference, fairness slider, TRADE LOGIC, 3-Team toggle, TRADE PROMPT, Build My Trade / Analyze My Trade) · TRADE PARTNERS (TARGETS list; MANAGERS list with match counts → expands to that manager's roster, needs, picks incl. "(via …)" provenance) | [trade-generator-page](evidence/trade-generator-page.md), screens 03, 14–15 |
| Rankings | 397-player FantasyCalc table, 1QB / SF/2QB toggle, position + Free Agents + Rookie filters, age (1 dp), positional rank, empty Proj column, weekly trend | [rankings-page](evidence/rankings-page.md), screens 12–13 |
| My Trade Lab (/account/) | Teams (league dropdown, connect Sleeper/Fantrax by username) · Needs to Address · Suggested Trade Block · every manager's flagged needs · Trade History (saved reports, free to re-view) · League Analysis (separate credit product, empty state) · WooCommerce account pages | [account-and-credits](evidence/account-and-credits.md), screens 09–11, 16 |

## 3. How the engine actually works (observed)

**Values.** FantasyCalc, verbatim ("Player values by FantasyCalc" in every footer; "Values powered by FantasyCalc" on reports). Two tables (1QB and SF), refreshed roughly daily ("Updated Oct 8, 2026 10:42 AM EDT"), weekly deltas computed against a dated snapshot ("since 09-24-2026"). Picks are round-level, 2027–2029, three rounds in the chat snapshot but 4ths appear in rosters; no slot values. The landing copy "not a static dynasty trade value chart" is marketing — the values are exactly that chart; what is roster-specific is the needs layer on top.

**Needs engine.** Per manager: positional value totals → power ranks; a "body floor" of have/min bodies per position (QB 5/2, RB 12/4, WR 7/4, TE 3/2 for the operator); slot-level flagged needs (QB1/QB2, RB1–3, WR1–3, TE1–2); "surplus" = players with no startable slot or spare value → Suggested Trade Block; "WHO TO CALL" = managers whose needs overlap the user's block, with record as a contend/sell cue ("0-4, weakest at WR/TE"). Output is template copy ("Stuck behind Trey McBride at TE. He is a real asset to somebody else and zero points to you."). It told the operator "Nobody in this league owns an upgrade on what you already start" while the chat listed Gibbs/Bijan/Walker as upgrade candidates — the two layers define "upgrade" differently.

**Trade Generator.** The saved report ([trade-report-generated](evidence/trade-report-generated.md)) shows the scoring: side totals of FantasyCalc values, "You win by 0.5% · 🟢 Likely". The operator's one generation returned a **4-for-2** (Likely + Kelce + Roman Wilson + 2029 1st for Jonathan Taylor + a 57-point throw-in) as "even". No stud/consolidation premium, no roster-spot cost, filler used to balance the sum, acceptance label with no stated basis. The TRADE PROMPT ("I need a RB back, mstevens wants my QB, don't trade my 2027 1st") and the "Notes:" echo on the report indicate an LLM composes the package under those constraints on top of the sums. Report ids are sequential (`me/reports/276`) — see the scale note in [account-and-credits](evidence/account-and-credits.md).

**Lab Analyst.** A prompt-stuffed LLM over a per-conversation snapshot: league/team summary, position ranks, flagged needs, body floor, surplus, upgrade candidates, full roster + league-wide values with owner, manager-overlap list, round-level pick values. It cannot see: value source, update cadence, needs formulas, league format (it guessed 1QB from Josh Allen's rank), other managers' records, pick ownership, weekly trends, projections (reply 1 claimed start/sit, reply 2 retracted). It refuses to package trades ("That value-matching belongs to the Trade Generator"), evaluates pasted trades by straight sum, contradicted itself twice under questioning (bsharp3 "most efficient fit" → retracted; "no flagged needs" → actually QB1, TE2), and only sees managers whose needs overlap the user's surplus. Its best outputs were honest limits and a coherent three-action weekly plan ([lab-analyst-chat](evidence/lab-analyst-chat.md), replies 13–15). **Credit rule:** 1 credit = a 3-message conversation; ~15 s per reply; one `POST wp-json/dtl/v1/lab-analyst` per message, no streaming.

## 4. Pricing and monetization

Credits only, no subscription: 10/$4.99 · 40/$17.99 · 75/$29.99 ($0.50 → $0.40 per credit); 5 free on signup; one generation or one 3-message chat per credit; saved reports re-viewable free. Purchases are WooCommerce products. Both the operator's trial actions (1 generation + 1 chat) consumed 2 of 5 free credits; a full evaluation of DTL costs about $5.

## 5. Quality findings (judgment)

1. **Possible format mis-detection on the operator's league.** Report header says "LEAGUE SETTINGS 1QB · 0.5 PPR" and every value shown is from the 1QB table, yet DTL's own needs are slot-level with QB1/QB2 and the body-floor QB minimum is 2. If Fantasy Football Version 3 is superflex, DTL priced the whole league on the wrong chart. **Operator to confirm from Sleeper settings** — this is the single most damaging thing to be able to say publicly, and the single thing we must not say without checking.
2. **Fairness = sum.** The 4-for-2 "even" trade is the exact shape Fleeced refuses (stud tax D-190, R2 pos_net_cap, filler rule in the value core).
3. **Acceptance is a label.** "🟢 Likely" has no model behind it; the chat says so in its own words (reply 14).
4. **Chat and product disagree** on upgrades, needs and ownership because they are fed different slices of the same data.
5. **Landing errors:** two uncaught JS exceptions on every logged-out load (minified Alpine bundle, Jetpack analytics); GA4 collect returned 503.
6. **Proj column and League Analysis are built-but-empty** on this account.

## 6. Where Fleeced wins / loses (as flagged on today)

| Capability | DTL | Fleeced today | Note |
|---|---|---|---|
| Player values | FantasyCalc global chart (1QB + SF) | Personal Elo board + blended consensus seed (DynastyProcess+KTC); premium rank-set import (`ranks.source.dynasty_nerds` on) | Fleeced's wedge holds — DTL has no personalisation of value |
| Fairness test | Straight sum, filler allowed | Fairness band + stud tax + positional caps (legacy engine); value core (`trade.value_core` off) with asymmetric band and no-filler rule | Fleeced stricter; DTL's "even" 4-for-2 would be refused |
| Partner/acceptance | Needs-overlap + record cue, "🟢 Likely" label | Mutual-gain search, bilateral preference-led construction (D-193), likes/declines feedback | Fleeced models the other side; DTL does not |
| Roster needs surface | Slot-level needs per manager, body floor, Suggested Trade Block, WHO TO CALL, template copy | Positional need fit (`trade.need_fit`), outlook row, Team overhaul | **DTL's manager-level needs list + "who to call" is clearer than anything Fleeced shows** |
| Weekly movement | Player Stock Movement + Rising FA Stock per league, dated snapshot | Trends surface (rank tab), `outlook.season_projections` on | DTL's league-scoped movers with owner names is a good retention surface |
| Pick handling | Round-level values, provenance "(via …)" shown in rosters | Slot values (`picks.slot_values`), owned-pick sync, pick-year labels | Fleeced ahead on picks |
| Multi-team trades | 3-Team toggle (not exercised) | `trade.three_team` off (queued) | DTL has it lit; unproven |
| AI chat | Lab Analyst (credit-gated, snapshot-only) | none | Not a gap worth closing as-is; see recs |
| Free-text constraints | TRADE PROMPT on the generator | none | Cheap, popular-feeling; see recs |
| Platforms | Sleeper + Fantrax (username) | Sleeper, ESPN, MFL (send in all three); Fleaflicker dark | Fleeced wider; DTL has Fantrax |
| In-platform send | none (report only) | Send in Sleeper/ESPN/MFL | Fleeced-only |
| Mobile | responsive web only | iOS TestFlight + web | — |
| Price | $0.40–0.50 per action, 5 free | free (`monetize.paywall` off) | Pricing intel → pm-monetization |
| Grading/eval of own engine | none visible | Calibration blind grading (`grading.blind` on) | — |

## 7. Recommendations (routed; priority is the owner's call)

- **pm-pfo:** copy DTL's *manager-level needs list* ("lofman needs RB3, TE1") and *WHO TO CALL* framing into the Acquire landing / Team overhaul — it answers "who do I talk to" in one glance, which Fleeced's card deck makes the user infer.
- **pm-pfo / eng-backend:** a *free-text trade prompt* ("don't trade my 2027 1st", "I need a RB back") as a constraint layer on the finder is cheap to spec on top of the value core's existing filters; DTL shows users will type these.
- **pm-retention:** a league-scoped *weekly movers* panel (with owner names) is a low-cost reason to reopen the app; Fleeced has the data (consensus deltas) but no surface.
- **mkt-brand:** positioning ammo — DTL's "built for your roster, not a static value chart" is a FantasyCalc chart with a needs layer; Fleeced's personal board + mutual-gain search is the honest version of that claim. Do **not** claim DTL mis-prices superflex until §5.1 is confirmed.
- **pm-monetization:** DTL's per-action credits ($0.40–0.50, 5 free) are a data point for the paywall design; note the 3-message chat credit and free re-view of reports as friction-reducers.
- **pm-competitor:** add DTL to the standing matrix (done in this run), re-check after the Sleeper-settings confirmation, and watch for the three-team feature and League Analyzer.
- **an-market:** sequential report ids (276 on 2026-10-09) as a scale datapoint; request a traffic read.

## 8. Open questions

1. Is "Fantasy Football Version 3" superflex on Sleeper? (decides §5.1)
2. What does a credit buy on "Analyze My Trade" and the 3-team mode — same report format? (not exercised: 0 credits)
3. What does League Analysis produce, and what does it cost?
4. Does the Fantrax path differ (OAuth vs username)?
5. Which LLM powers the chat/generator (no disclosure found on-site; see public research).

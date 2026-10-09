# Dynasty Trade Lab — Buy Credits + Account ("My Trade Lab") pages (logged in, 2026-10-09)

## /credits/ — Buy Credits
Same three WooCommerce products as the landing page: STARTER 10 credits $4.99 ($0.50/credit) · STANDARD 40 credits $17.99 ($0.45) · SEASON 75 credits $29.99 ($0.40). Copy: "More credits per dollar. Start free, upgrade when you're ready." No subscription, no unlimited tier ("SEASON — Unlimited trading all season long" is 75 credits, not unlimited). Not purchased.

## /account/ — "My Trade Lab" hub
Hero: "Get Started — Discover suggested trades based on your team needs and players to target" → [Find Your Next Trade]. Sidebar: Teams · Trade Generator · Trade History · League Analysis · My Account · Orders · Payment Methods · Addresses · Logout (the last five are WooCommerce account pages).

**Teams:** credit pill (0) · league dropdown "— choose a league —" listing the operator's three linked Sleeper leagues (La Resistance · Fantasy Football Version 3 · Lakeview League 🏈) · "View My Roster" · "+ Connect another team".

**Needs to Address (mattmurf77): Balanced — HOLD** (same copy as the dashboard).

**Suggested Trade Block** (the "tradeable surplus" the chat uses): Justin Herbert 1,990 · Quinshon Judkins 3,405 · Emeka Egbuka 3,014 · Davante Adams 2,132 · Isaiah Likely 1,895 · Travis Kelce 1,372.

**Players to Target — every other manager's flagged needs** (the full list the chat never saw; it only got the overlap subset):
- lofman: RB3, TE1 · Shark357: QB2, WR3 · MangoPatti: QB2 · Bcork: QB2, RB1, RB2, RB3, WR1, WR2, TE1, TE2 · jonbonjourvi: RB2, RB3, WR1, WR2, TE2 · PaulSm3nis: RB2, RB3, WR1, WR2, WR3 · bsharp3: QB1, TE2 · JohnStanfield: WR3, TE2 · dondags20: QB2, WR1, WR2, WR3, TE1, TE2. "More Players to Target" link.
- Note bsharp3 *does* have flagged needs (QB1, TE2) — the chat's reply 5 ("bsharp3 has no flagged needs matching your surplus") was wrong on the facts, and reply 14's self-correction was right. Needs are slot-level (QB1/QB2, RB1–3, WR1–3, TE1–2) ⇒ a lineup with 2 QB slots, so this league is superflex/2QB on DTL's own reading — while its values came from the 1QB table.

## /account/?section=trade-history
"Your Recent Trade Reports" — one row: **October 9, 2026 · "Even out the trade." ▸** — the operator's generation from earlier in the session (credits 5 → 4 for the generation, → 3 for the chat conversation). "Showing your 10 most recent reports. Re-viewing a saved report does not spend credits."

## /account/ → League Analysis
Empty state: "You haven't run a league analysis yet. Use the League Analyzer to get a full breakdown of your league with your top trade targets." — a separate (presumably credit-gated) product backed by the `generate-league` REST route; not run (0 credits). The dashboard's TEAM STATUS/NEEDS blocks render without it, so the "analysis" is a deeper report, not the needs engine itself.

## Scale signal from the report API
Expanding the saved report called `GET /wp-json/dtl/v1/me/reports/276`. If report ids are WordPress post ids (the likeliest implementation for a WP plugin), 276 is an **upper bound on all reports ever generated** on the platform as of 2026-10-09 — and that sequence also includes pages/products/media. Either way it reads as a very small user base; route to an-market as a datapoint, not a conclusion.

## Platform linking flow (Teams → "+ Connect another team", not submitted)
Panel: "Link a platform to view a roster. We only save the connection — your leagues and teams load live." Platform toggle **Sleeper | Fantrax**; for Sleeper a single "Sleeper username" field + **Connect** (public Sleeper API by username — no password, no OAuth); note "Connecting a different username replaces your current Sleeper connection" (one Sleeper identity per account; leagues under it are all imported, cf. the three leagues in the dropdown). Fantrax tab not opened. No ESPN, Yahoo, MFL or Fleaflicker option anywhere.

# Competitor-Informed Feature Backlog — 2026-06-11

**Inputs:** teardowns of DynastyGM [GM], DynastyDealer [DDr], Dynasty Daddy [DD], FantasyCalc [FC], DynastyTradeCalculator [DTC], FPTrack [FPT], Dynasty Dealmaker [DM] (docs/competitor-teardown-*.md), operator ideas [OP] (docs/plans/competitor-inspired-features-2026-06-10.md), and internal hooks [FTF] (trade-engine-v2 watch items, dark flags).

**Method:** ~140 raw observations deduplicated to **92 items**. Each scored on **Fit** (0–5: leverage of FTF's existing engine/stack — Sleeper-only, personal-Elo, mutual-gain discovery, RN mobile + vanilla web + MV3 extension) and **Impact** (0–5: quality of trade output and user experience). Effort (S/M/L) is the tiebreak. Ranking bias, per operator direction: engine quality and user-input signals that improve suggestions outrank breadth features; FTF's differentiation is *advocate with your personal values*, not neutral referee.

**Categories:** `ENH` = enhancement to an existing FTF feature/system · `NEW` = new feature/surface · `PASS` = deliberately not pursuing (documented so we stop re-litigating).

**Top-20 deep dives** (PRD + HLD + LLD each) live in [competitor-top20/](competitor-top20/).

---

## Tier 1 — Top 20 (deep-dive planned)

| # | Item | Cat | Src | Fit | Impact | Effort |
|---|---|---|---|---|---|---|
| 1 | Opponent outlook auto-classification | ENH | OP/DD/DM | 5 | 5 | M |
| 2 | Asset preference lists (untouchables + targets) | NEW | OP-adjacent | 5 | 5 | M |
| 3 | Swap-player counter builder | NEW | OP/DD/DDr | 4 | 5 | L |
| 4 | Fairness threshold control + "ask for more" | ENH | OP | 5 | 4 | M |
| 5 | Post-trade impact preview | NEW | DD | 5 | 4 | M |
| 6 | Verdict & gap quantification on cards | ENH | DD | 5 | 4 | S |
| 7 | Rejection-reason feedback on swipes | ENH | FTF | 5 | 4 | S |
| 8 | Per-league strategy/outlook | ENH | OP | 5 | 4 | S |
| 9 | Community-diff trade angles | ENH | FTF/GM | 5 | 4 | M |
| 10 | Key-asset package adjustment | ENH | FPT/DD | 5 | 4 | M |
| 11 | Received-offer analyzer (read-only inbox) | NEW | DDr | 4 | 5 | L |
| 12 | Send-to-Sleeper deep link + trade card sharing | NEW | DD/DDr | 4 | 4 | M |
| 13 | Ranking gamification (streaks/goals/leaderboard) | ENH | DDr | 5 | 4 | M |
| 14 | League power rankings + team audit page | NEW | GM/DD/DDr | 4 | 4 | M |
| 15 | Pick capital dashboard + dynamic pick values | NEW | GM | 4 | 4 | L |
| 16 | Value confidence ranges (bid/ask display) | ENH | DTC/FTF | 5 | 3 | S |
| 17 | Player profiles (value history + you-vs-market) | NEW | all | 4 | 4 | M |
| 18 | Trade push notifications | NEW | FPT | 4 | 4 | M |
| 19 | Extension: Sleeper trade-screen overlay | ENH | FTF | 5 | 4 | M |
| 20 | Engine transparency page | ENH | DTC/FPT | 5 | 3 | S |

### 1. Opponent outlook auto-classification — ENH
The engine's outlook blend (`outlook_alpha_*`, flag `trade.outlook_blend`, ON) reweights now-vs-future value, but only for the user; every opponent is priced at the not_sure 0.50 blend. Dynasty Daddy tiers every team (Contender/Frisky/Rebuilding) and Dealmaker markets "competitive window detection" as its core AI. The operator flagged the failure mode directly: a rebuilder doesn't want an aging vet even if their rankings rate him.

Build an inference function classifying every league team from observables FTF already has — roster age distribution vs `vet_age`/`youth_age`, value concentration in 27+ players, pick-capital share, record/standing — and run each opponent's side of every candidate trade through *their* inferred alpha. Self-declared outlook stays as an override for the user's own team. This is the single highest-leverage change to suggestion quality: it makes "mutual gain" window-aware on both sides, reuses existing machinery end-to-end, and unlocks tier chips in the UI that explain *why* a team is a good trade partner.

### 2. Asset preference lists (untouchables + targets) — NEW
Every competitor takes player-level preferences implicitly (watchlists in DDr/FPT); none feeds them into discovery. FTF can: an **Untouchables** list (never suggest trading these away) and a **Targets** list (bias the engine toward acquiring these). This is the purest form of the operator's "user input → higher quality suggestions" theme — two lists that translate directly into hard filters and `pos_acquire_bonus`-style multipliers in candidate generation.

Impact is immediate and obvious to the user: the fastest way to lose trust is suggesting they trade away a player they'd never move, and today the engine can't know that. Effort is moderate (prefs storage, two engine touchpoints, simple list UI on player rows). Also doubles as preference signal for the deferred acceptance model — an untouchable tag is a strong label the swipe stream can't produce.

### 3. Swap-player counter builder — NEW
Operator idea #1: on any suggested trade, tap a player to swap them — see that roster with candidates highlighted in a similar value band, pick a replacement, and the card re-scores live. Dynasty Daddy's "Even Out Trade" and DynastyDealer's offer MODIFY are partial precedents, but neither preserves a mutual-gain guarantee through the edit.

The critical design constraint: proximity highlighting must use the engine's *adjusted* values (outlook blend, positional multipliers) — not raw consensus — or swaps silently break the mutual-gain math. Requires a rescore endpoint and interactive card UI (the largest build in the top 10), but converts take-it-or-leave-it cards into negotiation starting points, and swap events are the richest preference labels FTF could collect. Sequenced after #1 so swap candidates are window-aware.

### 4. Fairness threshold control + "ask for more" — ENH
Operator idea #2. `fairness_threshold` is already a per-job API param surfaced on web; extend the range to zero/off (verifying the range-overlap gate degrades cleanly — fairness is only 0.30 of score vs 0.70 mismatch). Competitors validate both poles: DTC refuses to referee fairness at all, DynastyDealer sells fairness as the product.

The differentiating half is **"ask for more"**: when a trade clears with headroom, invert the existing sweetener search (`sweetener_band`, `sweetener_max_cards`) to surface opponent players the user could *also* request and still have the deal work. Copy frames FTF as the user's agent ("room to negotiate"), a position no competitor occupies. Mostly config plumbing plus one inverted candidate pass.

### 5. Post-trade impact preview — NEW
Dynasty Daddy's strongest calculator feature: position ranks with rise/fall arrows *as if the trade went through*, plus team tier changes. FTF already computes `position_needs`/`position_surplus` and per-position values for every roster during candidate generation — the data exists at suggestion time and is currently thrown away.

Render a before/after panel on each trade card: per-position group value, league rank deltas, needs filled or created — for *both* teams (showing the opponent's gain is the proof of the mutual-win claim). Theirs is reactive (build a trade, see impact); FTF's is proactive (every suggestion ships with its impact case attached). This is the explainability layer that makes users trust an algorithmic suggestion enough to actually send it.

### 6. Verdict & gap quantification on cards — ENH
Dynasty Daddy's banner pattern: name the favored side, quantify the gap ("add a player with 1,478 value to even trade"), link the fix. FTF cards today communicate scores; they should communicate a *position*: "Fair (within 6%) — slightly favors you" / "Favors them by ~480 — ask for a sweetener."

Smallest-effort item in the tier: the numbers (fairness ratio, value delta, sweetener candidates) already exist in the trade payload. Pure presentation + copywriting, with the advocate tone ("you could ask for more") rather than referee tone. Pairs with #4; ship together.

### 7. Rejection-reason feedback on swipes — ENH
The swipe loop writes `trade_impressions`, but a left-swipe is an opaque label — the engine can't distinguish "too lopsided" from "wrong position" from "I'd never trade him." Add an optional one-tap reason chip after rejection (Unfair to me · Don't need that position · Wouldn't trade him · Don't believe they'd accept).

Each reason maps to a different engine adjustment (fairness recalibration, positional preference, auto-untouchable prompt feeding #2, acceptance prior for Thompson sampling). The learned acceptance model was deferred for lack of labels (~20 swipes); reasons multiply the information per label and shorten the path to training it. Trivial UI, disproportionate data value.

### 8. Per-league strategy/outlook — ENH
`team_outlook` is a single global pref, but a user contending in one league is rebuilding in another — the same trade card is right in one context and insulting in the other. Move outlook to per-league scope (league_id-keyed prefs), defaulting new leagues from #1's auto-classification of the user's own roster.

Small change (prefs schema + settings UI + lookup in the job path at `server.py:1494`) with outsized correctness gains for exactly the multi-league users most likely to be power users. Natural first-run moment: "We think this team is rebuilding — right?" confirms the classifier while collecting ground truth for it.

### 9. Community-diff trade angles — ENH
FTF's defining asset is *two* value sets per player: the user's Elo and consensus. The divergence engine uses this for matchup cards, and `tiers.community_diff` already exists as a dark flag. Surface divergence as explicit trade strategy: "You're higher than market on X — buy-low candidate"; "You're lower on Y — sell now while the market pays more."

DynastyGM's DIFF column (rank vs ADP) is the visual precedent but uses a global market only — no competitor can personalize it. This converts FTF's core differentiator from an internal mechanism into a visible, repeatable reason to open the app, and gives suggested trades a narrative hook ("this works because you two disagree about these players").

### 10. Key-asset package adjustment — ENH
Industry consensus on the package problem is now documented from two independent sources: FPTrack's Crown Asset (best asset gains value in 1-for-many deals) and Dynasty Daddy's Value Adjustment ("don't split a dollar into 100 pennies" — key-player premium weighted by his proportion of the trade). FTF has diminishing package weights (`package_weight_1..5`, `package_adj_gamma`) which discount the small side, but no explicit key-asset premium scaled by package share on the big side.

Reconcile the two: add a crown-asset multiplier keyed to the top asset's share of its side's total, tuned against the existing weights so the two mechanisms don't double-count. Directly addresses the standing 1-for-1 fairness-gate watch item, and per the teardowns, resolves it as "explicit multiplier," not "hard gate."

### 11. Received-offer analyzer (read-only inbox) — NEW
DynastyDealer renders real pending Sleeper offers with accept/modify/decline. FTF should do the *analysis* half without the ToS-risky write half: pull pending offers (read-only), score each through the v2 engine — verdict, gap, both-team impact (#5), and counter suggestions via the swap machinery (#3).

"Should I take this deal?" is the highest-intent moment in dynasty fantasy, and currently FTF is absent from it. This rounds out the product loop: FTF finds trades, evaluates trades you receive, and helps you counter. Requires Sleeper auth research (offers may not be on the public read API — feasibility spike is part of the plan); if auth proves heavy, v1 is manual entry of the received offer into the same analyzer.

### 12. Send-to-Sleeper deep link + trade card sharing — NEW
The actionability gap: DynastyDealer creates offers inside Sleeper; Dynasty Daddy has Send Trade and Share. FTF's safe version: deep-link into Sleeper's trade screen for the right league/partner with assets pre-described, plus a shareable trade card (link + rendered image) carrying both-team impact framing and FTF branding.

Closes the loop from suggestion to action without write-access risk, and the share card is the organic acquisition channel — every shared card lands in a league chat full of non-users (DDr's mass-sender insight, minus the spam and ToS exposure).

### 13. Ranking gamification (streaks/goals/leaderboard) — ENH
DynastyDealer gamifies its data engine (vote streaks, daily counts, leaderboard) because crowdsourced values die without volume. FTF's 3-player matchup ranking *is* its data engine, and the cold-start watch item (divergence needs 2+ ranking sets per league) makes ranking volume an engine-quality input, not vanity engagement.

Add streaks, a daily goal ("12 matchups refines your RB curve"), per-league coverage meters, and a league leaderboard of ranking activity. Tie the reward to output quality: "Your rankings updated — 3 new trade angles found" connects the habit to the payoff. Highest-leverage retention item because it compounds: more rankings → better Elo → better trades → more reasons to return.

### 14. League power rankings + team audit page — NEW
Table stakes across GM/DD/DDr: stacked positional value bars per team, drill-down to position groups with league ranks, tier labels. FTF has every input (rosters, values, needs/surplus) and uniquely can render it in *the user's own values* vs consensus — two views of the same league no competitor offers.

Also the natural home for #1's tier chips and the visual feeder for trade discovery ("they're 11th in RB value and rebuilding — here's the deal"). Moderate effort; mostly a presentation layer over existing engine computations, shipped as a web page first then mobile screen.

### 15. Pick capital dashboard + dynamic pick values — NEW
DynastyGM's pick treatment is the benchmark: per-team inventory summary, individual pick values, original-owner tracking, and pick projections from the original owner's contender rank. FTF values picks (waiver_slot_cost, pick handling in packages) but doesn't surface pick capital or condition future-pick value on the owner's projected finish.

Two halves: (a) dashboard — every team's pick inventory and total pick value with league rank; (b) engine — dynamic future-pick valuation using #1's classifier output (a rebuilder's 2027 1st ≠ a contender's). The engine half materially improves any suggestion involving picks, which in dynasty is most of the interesting ones.

### 16. Value confidence ranges (bid/ask display) — ENH
DTC's buy/sell spread is the only competitor concept acknowledging value uncertainty — and FTF already computes it (confidence shrinkage, `shrink_pseudocount`, range-overlap fairness uses ranges internally). Surface it: show "5,800–6,400" instead of false-precision "6,100" where Elo confidence is low, and explain that more ranking matchups tighten *your* ranges.

Small effort, three wins: honest UX, a visible motivation loop for ranking (feeds #13), and a published differentiator (no one else shows uncertainty). Display-layer only; the math exists.

### 17. Player profiles (value history + you-vs-market) — NEW
Every competitor has player pages; FTF has none — there's nowhere to answer "what does FTF think of this player and why." Profile = consensus value + trend (Dynasty Daddy stores all-time/3-month highs-lows; start logging now, charts come free later), the user's Elo vs market diff (#9's per-player view), age/position context, and appearances in recent suggestions.

Becomes the link target for every player name across the app (cards, rankings, league pages) and the SEO/share surface later. Start minimal: a single template fed by data already in the DB, plus a daily value-history snapshot job.

### 18. Trade push notifications — NEW
FPTrack's wire/push model is its whole retention engine. FTF's equivalents are obvious and higher-value: "new mutual-gain trade found in [league]" (scheduled engine runs), "league-mate updated rankings — divergence angles changed," and value movers on rostered players. Expo push is already in the mobile stack.

Discovery products die when discovery only happens on app-open; scheduled runs + push make FTF proactive — the engine works while the user doesn't. Requires job scheduling (cron endpoint exists), notification prefs, and restraint defaults (quality threshold gating so pushes stay rare and good).

### 19. Extension: Sleeper trade-screen overlay — ENH
FTF ships an MV3 extension no competitor matches — currently underused. Overlay the Sleeper web trade screen: as a user builds any trade on Sleeper, inject FTF's verdict, gap, and both-team impact inline (and "ask for more" candidates from #4).

This meets users at the exact moment of trade decision *on the platform where the trade happens*, with zero ToS exposure (read-DOM + display). It's also a distribution wedge: a league-mate seeing the overlay verdict in a screenshot asks what it is. Reuses the rescore endpoint built for #3.

### 20. Engine transparency page — ENH
DTC and FPTrack both publish how their values work (vacuum-value explainer; six named boost rules) — trust through legibility. FTF's machinery is *more* explainable than theirs (your Elo from your matchups + named adjustments: outlook blend, package weights, positional bonuses, fairness gate) but undocumented for users; `web/ranking-method.html` covers ranking only.

Extend to a "How trades are found" page: named rules in plain English with the FPTrack-style card layout, linked from every trade card's "why this trade?" affordance. Small effort, compounding trust payoff, and it pre-writes the support/FAQ answers launch QA will need.

---

## Tier 2 — Near-term backlog (21–40)

### 21. Home league cards with rank chips — NEW [GM]
DynastyGM's home screen earns the daily open with one glance: every league, color-coded rank chip (1/14 green → 10/12 red). FTF's league list can carry the same chips once #14 computes team ranks.

Cheap, habit-forming, and it advertises the deeper pages. Ship with #14 since the rank computation is shared.

### 22. Roster needs/surplus surfacing — ENH [FTF]
`analyze_roster_strengths` already produces `position_needs`/`position_surplus` per team; users never see it. Show "Your needs: RB depth · Surplus: WR" on the league/trade screens so suggestions arrive pre-justified.

Near-zero engine work; converts hidden engine reasoning into user-facing context that makes every suggestion read as intentional.

### 23. Cross-league shares/exposure view — NEW [GM/DDr/DD]
GM Shares, DDr Portfolio, DD Portfolio all answer "where am I over-exposed?" For FTF users with multiple Sleeper leagues: player × league-count × exposure %, sorted by value, with over-exposure flags.

Moderate value for multi-league users, low for single-league; straightforward aggregation over data already synced. Good mobile-screen candidate after Tier 1 lands.

### 24. Trade-finder onboarding tour — ENH [DD]
Dynasty Daddy's tour modals (Overview → markets → even-out → demand → power rankings) turn a dense tool into a guided one. FTF's find-a-trade flow has first-run config but no guided explanation of *what the engine is doing for you*.

A 4–5 step tour (your values + their values → mutual gain → fairness control → feedback loop) raises activation and reduces "why this trade?" confusion. Pure front-end.

### 25. Watchlist with value alerts — NEW [DDr/FPT]
Standard competitor feature: star players, get notified on value moves or when they appear in a feasible trade. In FTF it gains a twist — watchlist items feed #2's targets list, so watching a player quietly improves suggestions.

Ship after push infrastructure (#18) exists; until then a watchlist without alerts is just a list.

### 26. League trade history feed — NEW [GM]
Real executed trades in the user's own leagues, scored retroactively by the engine ("we'd have called this +480 for Team A"). Builds calibration trust and seeds conversation.

Sleeper transaction history is read-API accessible; mostly a fetch + render + batch-score job. Also quietly accumulates labeled real-trade data for future model work (#65).

### 27. Open trade calculator (web) — NEW [FC/DTC/all]
Every competitor's front door is a free, no-login calculator; FTF has no standalone calc. A public web calculator using consensus values (FTF Elo after login) is the SEO/acquisition surface — "dynasty trade calculator" is the category's head term.

Reuses the rescore endpoint (#3) and verdict banner (#6). Conversion path: calc result → "see what your league would actually accept — connect Sleeper."

### 28. Team-vs-team calculator — ENH [GM/DD]
League-aware calc: pick two real teams, assets pre-loaded from rosters with adjusted values. Sits between the open calc (#27) and full discovery — for users who already know their trade partner.

Thin layer over existing roster data + rescore endpoint; share surface included.

### 29. Sent-offer tracker — NEW [DDr]
Track which suggested trades the user actually proposed (via #12's deep link) and what happened. Closes the outcome loop the acceptance model needs (proposed → accepted/declined is the ground-truth label).

Light UI; depends on either manual status marking or #11's read-auth to detect outcomes automatically.

### 30. Value-source switch / blend slider — ENH [DD]
Dynasty Daddy's "Fantasy Markets" proves users accept that values are plural. FTF's version: let users slide between consensus-weighted and my-Elo-weighted suggestion scoring (today's blend is fixed), with "your market" as the headline frame.

Engine already holds both value sets; the slider is one weight exposed. Guard: default stays the tuned blend; the slider is for power users.

### 31. Team age/experience indicators — ENH [DDr]
Avg age + avg experience chips per team (DDr league cards) are cheap window-context everywhere teams render, and they visually justify #1's tier labels.

Trivial computation off rosters already in the DB; pure display.

### 32. Playoff odds simulation — NEW [DD]
"Simulate 10k seasons" per-record playoff odds. In-season retention feature and a quantified input to #1's classifier (odds < 10% → rebuilder evidence).

Meaningful effort (schedule + scoring sim) and dormant until the season starts; build late summer.

### 33. Daily value-movers digest — NEW [DDr/FPT]
Risers/fallers on rosters the user cares about, in-app and via #18 push. Cheap once daily value snapshots (#17) exist.

The dynasty offseason heartbeat feature — gives the app a daily pulse between trade windows.

### 34. Player comparison tool — NEW [DD/DDr]
Side-by-side players (or player vs pick): values, your-Elo vs market, age curves, trends. Dynasty Daddy links "View in Player Comparison" straight from the calculator verdict; FTF should do the same from swap flows (#3).

Thin page over existing data; natural companion to #17 profiles.

### 35. Rookie rankings view — ENH [all]
Dedicated rookie filter/view in rankings with draft-class context. Every competitor has it; FTF's rankings can add a rookie lens cheaply.

Seasonal spike utility (April–June); pairs with #55 draft prep.

### 36. Sync timestamps + manual refresh everywhere — ENH [GM]
GM stamps every screen with "Updated:" + refresh; FTF should standardize the pattern (league data age, value data age, last engine run) to preempt "is this stale?" distrust — especially given Render cold starts.

Small, systematic UX hygiene pass.

### 37. League-mate invite flow upgrade — ENH [FTF]
The cold-start nudge exists (banner + coverage-row button). Upgrade to tracked invite links, "what they'll see" preview, and coverage celebration ("3/12 league-mates ranking — divergence engine ON").

Directly attacks the #1 growth constraint identified at v2 ship; measurement (invite → activation) is the point of the upgrade.

### 38. Trade-of-the-day card — NEW [FTF]
One curated best-suggestion-today per league, on the home screen and in push. Borrow's DDr's daily-engagement framing without building a voting product.

Trivial once scheduled runs (#18) exist: it's the top-scored fresh suggestion, presented with #5/#6 framing.

### 39. 2QB vs Superflex valuation distinction — ENH [DTC]
DTC is alone in valuing 2QB above SF (forced 2-QB starts ≠ optional). FTF reads Sleeper league settings; verify 2QB leagues get a stronger QB multiplier than SF rather than sharing one bucket.

Small engine-config change + a values audit; correctness for a vocal niche.

### 40. League-size + TEP value adjustments — ENH [DTC/FC]
DTC bumps elites in 10-team and depth in 16-team; FC parameterizes by team count; TEP is a toggle everywhere. FTF knows league size and scoring from Sleeper — fold them into the value curve (`ktc_k` family) instead of one-size-fits-all.

Engine-math refinement; validate against the per-league settings already synced.

---

## Tier 3 — Later backlog (41–68)

### 41. Cross-league trade comps browser — NEW [GM/FC]
Platform-wide feed of real Sleeper trades with format-context chips (GM's killer comps engine). High build+data cost (continuous multi-league ingestion); FTF-scoped version (#26, your leagues only) first. Revisit when scale justifies the crawler.

### 42. Trade demand/frequency signal — ENH [FC/DD]
FC's tradeFrequency and DD's demand curves identify players that *actually move*. As engine input (prefer liquid players in suggestions) it improves acceptance realism; needs #41-class data or the FC API (license question, #67). Park until a data source is settled.

### 43. Own-market from observed trades — NEW [FC]
Long-term flywheel: once FTF observes enough real trades (#26/#41), derive its own market values like FC does. Strategic, not actionable at current scale; recorded so the data schema for #26 keeps raw trade payloads.

### 44. Free-agent value list + waiver suggestions — NEW [GM/DDr/FPT]
Available players per league sorted by value, with claim-worthiness vs current roster. FPTrack paywalls "waiver targets"; GM/DDr list values. Adjacent to trade discovery but a different job; in-season feature, build near season start.

### 45. Optimal lineup checker — NEW [DDr]
Value/projection-maximizing starters per week. Pure in-season retention; commodity feature (Sleeper itself nudges lineups). Low differentiation — only worth it bundled into a season-mode push.

### 46. Season Wrapped recap — NEW [DD]
Shareable end-of-season recap (trades made, value gained, best/worst calls — FTF uniquely can show "your Elo vs how it played out"). Viral one-shot; build in November, ship at season end.

### 47. Discord bot — NEW [DD]
Posts FTF trade suggestions/divergence angles into a league's Discord. On-brand distribution (league chats are where trades happen) and DD proves the channel. Moderate effort; after core loop + push (#18) stabilize.

### 48. Scout-any-username recon — NEW [DDr]
Enter any Sleeper username → their leagues, exposure, tendencies (public API, no auth). Acquisition hook ("scout your rival") more than core value; cheap-ish but off the critical path.

### 49. Cross-league record/standing portfolio — NEW [DDr]
Aggregate W/L, win rate, avg rank across leagues (DDr's 77-132 / 36.8% view). Light analytics garnish for #23's portfolio view; in-season.

### 50. Injury dashboard — ENH [DDr]
Injury status on rostered players (Sleeper already provides status fields FTF ingests). Roll into #33's digest rather than a standalone screen.

### 51. News feed integration — PASS-leaning [DDr/DD/FPT]
Rotowire-style feeds require licensing and add commodity content. Link out from player profiles (#17) instead; revisit only if engagement data demands in-app news.

### 52. League draft board sync — NEW [GM]
Live league-draft view with traded-pick markers and value cheat-sheet (GM's is solid despite the epoch bug). Seasonal (rookie-draft window) and read-API feasible; pairs with #54 for draft-day trade value.

### 53. Mock draft simulator — NEW [GM/DD]
Full mock rooms (clock, configs, 3RR) are a big build for a seasonal feature; GM/DD both have mature versions. Low differentiation for FTF; only the value-informed pick recommendations are on-brand. Defer; reconsider as a lightweight "practice with your values" mode.

### 54. Draft-day pick-trade suggestions — NEW [FTF/FB-47]
Live "trade up/down" suggestions during rookie drafts using pick values (#15) + targeting (FB-47 finder-targeting engine). Genuinely differentiated and on-mission; gated on #15's dynamic pick values. Build for next April's draft season.

### 55. Rookie draft prep hub — NEW [seasonal]
Rookie values, your league's pick board, targets by slot. Content+tool bundle for April–June; assembles from #15/#35/#52 rather than new machinery.

### 56. Multi-source ADP integration — ENH [DD]
DD averages FantasyPros/BB10s/RTSports/Underdog ADP. FTF could show ADP-vs-your-Elo as another diff lens (#9). Data licensing/scraping questions; nice-to-have after profiles (#17).

### 57. Value history retention job — ENH [DD]
Start snapshotting daily values *now* (one cron + table) so #17/#33/#46 have history when built. Tiny effort, time-sensitive — every week not logging is chart history lost. Honestly Tier-2-worthy on urgency despite Tier-3 visibility.

### 58. Public FTF values API — NEW [FC]
FC's openness made it the category's data layer. Premature for FTF (values are personal; consensus layer is DP-derived with license questions) — but keep API design clean so a public read tier is possible later.

### 59. Three-team trade UI — ENH [FTF/DDr]
`trade.three_team` flag exists, dark by operator decision until 2-team proves out. DDr gates 3-way behind premium (validation of demand). Revisit with real usage data; no new work now.

### 60. Waiver/FAAB analytics — NEW [DD]
Winning-bid curves per player. Niche, in-season, data-heavy for the value; low priority.

### 61. Start/sit aggregation — PASS-leaning [DD]
Multi-source weekly projections + Vegas lines is a different product (weekly managers). Off-mission for a dynasty *trade* app; link out instead.

### 62. Community polls — PASS-leaning [DDr]
Engagement filler without a data payoff for FTF's engine (rankings already collect the signal polls would). Skip unless community features become a theme.

### 63. Premium tier definition — strategy [all]
Market anchors: DDr $5.99/mo · DM $1.49/wk tokens · FPT $24.99/yr · GM sub. Pattern: calculator free, discovery paid. FTF decision needed pre-scale, not pre-launch; revisit after activation metrics exist. Candidate premium line: unlimited discovery runs + offer analyzer + push, with ranking/calc free forever (they're the data engine — FPTrack's degraded-free-tier ads model is the cautionary tale, DDr's open-data-engines model the good one).

### 64. Referral/founding-user program — NEW [growth]
League-based product → league-based referrals ("unlock X when 3 league-mates join" — they also fix your cold start, #13/#37). Design after invite tracking (#37) reports baseline conversion.

### 65. Acceptance-probability model — ENH [DM/FTF]
DM markets acceptance probability; FTF deliberately deferred the learned model (~20 labels) for Thompson sampling. The roadmap is already correct: collect richer labels via #7/#29, revisit when trade_impressions has volume. Tracked here so the competitor pressure doesn't trigger a premature build.

### 66. AI trade-reasoning narratives — NEW [DM]
LLM-written strategic reasoning per suggestion (DM's product). FTF has ANTHROPIC_API_KEY plumbing for matchup selection; per-suggestion narratives are a cost/latency question and risk over-promising. Prototype behind a flag for the offer analyzer (#11) where stakes justify tokens; not for every card.

### 67. FantasyCalc values integration — ENH [FTF]
Already evaluated at v2 ship: free/keyless API, no published license → deferred. Unchanged. If licensed later, becomes a second consensus source (#30's switch makes it user-visible).

### 68. Yahoo league support — NEW [GM/FPT/DD]
First step beyond Sleeper if multi-platform ever matters (Yahoo has an official API; ESPN doesn't). Strategic horizon item — the entire current stack assumption is Sleeper-only, and the cold-start/network problems are platform-independent. Park until Sleeper TAM is the binding constraint.

---

## Tier 4 — Deferred / strategic horizon (69–80)

### 69. Multi-platform host hub (ESPN/MFL/Fantrax) — NEW [GM/FPT]
GM's moat and FPT's sync breadth. Massive surface area (per-platform auth, data models) against FTF's focused-Sleeper advantage. Only after #68's Yahoo experiment proves multi-platform demand.

### 70. Redraft mode — NEW [DDr]
DDr serves dynasty+redraft from one codebase via app-wide mode switch. Doubles TAM, halves focus; dynasty trade discovery is the wedge. Not before product-market fit.

### 71. Prospect model (PRISM-like) — NEW [DDr]
Statistical prospect grades + combine data. Real data-science investment, far from the trade loop. Devy-adjacent; pass for the foreseeable.

### 72. Devy player support — NEW [DTC]
College players in values/trades. Niche-of-a-niche; DTC owns it. Pass.

### 73. IDP support — NEW [DTC/GM]
GM and DTC treat IDP as first-class. FTF's Elo flow could rank IDPs, but value sources and matchup volume are thin. Defer until requested by real leagues (flag: Sleeper settings already tell us which synced leagues run IDP — measure demand before building).

### 74. Dispersal draft tool — NEW [DDr]
Commissioner tooling for orphan-team dispersals with Sleeper write-sync. Impressive, narrow, ToS-exposed. Pass.

### 75. OBS/stream overlay — NEW [DD]
Creator-distribution play. Clever for DD's scale; premature for FTF's. Revisit alongside #47 if a creator strategy emerges.

### 76. Games arm (wordle/trivia/connections) — PASS [DD]
Traffic engine decoupled from product. Off-mission; FTF's "game" is the ranking flow itself (#13).

### 77. Stock-market cosmetics (indices/ticker/RSI) — PASS [DDr]
Memorable branding, cosmetic depth. FTF's honest equivalent is confidence ranges (#16) — uncertainty that means something rather than MACD that doesn't.

### 78. Token-metered AI pricing — PASS [DM]
Interesting cost-pass-through model; wrong fit for FTF's always-on discovery engine (metering discovery kills the habit loop #13/#18 build).

### 79. Mass-offer sender — PASS [DDr]
Highest-virality, highest-risk feature in the field: bulk-creating offers via user auth tokens is ToS exposure plus league-spam backlash. FTF's principled alternative: multi-league *suggestions* with per-league deep links (#12) — the user sends each offer.

### 80. In-app Sleeper write actions (accept/decline/claims) — PASS for now [DDr]
Same auth-token mechanism as #79. Read-only is the line (#11): analyze everything, execute nothing, deep-link to Sleeper for actions. Revisit only if Sleeper publishes a sanctioned write API.

---

## Tier 5 — Hygiene, trust & ops patterns adopted from teardowns (81–92)

### 81. Empty/error-state polish pass — ENH
GM ships "Wed Dec 31 1969" to production; DDr ships "v1.1.1.7 - Fix 2025 picks + debug" in its footer. The category's polish bar is low — meeting a normal software bar is itself differentiation. Audit FTF's empty/loading/error states pre-launch (folds into launch QA plan).

### 82. First-run outlook confirmation — ENH
"We think this team is rebuilding — right?" one-tap confirm on first league open (see #8). Collects classifier ground truth and demonstrates intelligence in the first session.

### 83. Sleeper-auth feasibility memo — research
One-time spike documenting what Sleeper's read API exposes (pending offers? transactions?) and the ToS posture of token-based auth, so #11/#29/#79/#80 decisions cite facts. Gates Tier-1 #11 scoping.

### 84. Engine-metrics dashboard expansion — ENH [FTF]
GET /api/admin/engine-metrics exists; extend with the new signals this backlog creates (rejection reasons #7, swap events #3, fairness-slider positions #4, ask-for-more uptake) so tuning decisions stay evidence-based.

### 85. Outlook tier naming/personality — ENH [DD]
DD's Contender/Frisky/Rebuilding labels carry charm GM's plain ranks don't. Name FTF's tiers with personality (and consistency across clients per cross-client-invariants doc) when #1 ships.

### 86. Trade-card image generator — ENH [#12 adjunct]
Rendered share image (both sides, verdict, FTF brand) for league group chats — where every trade is screenshotted anyway. Build with #12.

### 87. Web/mobile onboarding parity audit — ENH
Teardown-informed first-run review: DDr's mode-select and DD's tour both beat FTF's current cold open. Folds #24 + #82 into one onboarding workstream.

### 88. Ranking-coverage push prompts — ENH [#13/#18 adjunct]
"A league-mate just ranked 20 matchups — your shared divergence map updated." Social-proof push variant; ship inside #18's notification framework.

### 89. Email digest fallback — NEW
Weekly value movers + best suggestion for push-decliners. Low effort after #33; standard retention hygiene.

### 90. App Store/landing positioning refresh — marketing
Teardowns hand FTF its category positioning: every competitor referees fairness; FTF advocates with *your* values. Refresh ASO copy/screenshots and landing page around advocate framing + confidence honesty (#16) + both-team impact proof (#5).

### 91. Competitor watch cadence — ops
Quarterly re-check of the seven competitors (DDr ships weekly; DD ships constantly). Lightweight: re-run the API/HTML probes, diff feature lists, update teardown docs. (The probe commands are reproducible from this exercise.)

### 92. DLF Trade Analyzer teardown completion — ops
Outstanding gap from the exercise (Cloudflare 403; needs operator SingleFile capture), plus DynastyDealer Fair Trade Finder output screens and Dynasty Daddy /trade-finder UI. Close before next prioritization pass so the discovery-feature comparison is complete.

---

## Sequencing view (top 20 only)

**Wave 1 — engine correctness & trust (ship together):** #1 outlook classifier → #8 per-league outlook → #10 package adjustment → #6 verdict banner → #16 confidence ranges → #20 transparency page. *Suggestions get smarter and explain themselves.*

**Wave 2 — user-input loop:** #2 preference lists → #7 rejection reasons → #4 fairness control + ask-for-more → #13 ranking gamification. *Every session teaches the engine.*

**Wave 3 — interaction & surfaces:** #3 swap builder (needs Wave 1's opponent outlooks + a rescore endpoint) → #5 impact preview → #14 power rankings page → #15 pick capital → #17 player profiles (+ #57 history job immediately).

**Wave 4 — reach:** #12 deep link + share → #18 push → #19 extension overlay → #11 offer analyzer (post #83 feasibility memo) → #9 community-diff angles threaded throughout.

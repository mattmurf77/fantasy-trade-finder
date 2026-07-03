# 20. Engine transparency page
> Tier 1 · #20 · ENH · Effort S · Sources: DTC/FPT

## Summary

DTC and FPTrack both publish how their numbers work, and it functions as trust infrastructure: DTC's about-the-calculator copy explains vacuum value and buy/sell lines and explicitly refuses to referee fairness; FPTrack publishes a named six-rule "Value Boosts" modifier table (Crown Asset, Draft Value Boost, Solo Future 1st, Dominance Factor, Star Power, Age Adjustment) — each rule a short, named, plain-English card. FTF's machinery is *more* explainable than either — your Elo comes from your own 3-player matchups, and every adjustment is a named config key — but none of it is documented for users. `web/ranking-method.html` is the precedent surface (plain standalone page, tile cards with title + description, dark-theme `:root` palette), and it covers ranking only.

Build a "How trades are found" public page: the mutual-gain principle up top, then FPTrack-style explainer cards — one per named rule, copy drafted below and grounded in real config keys verified in `backend/trade_service.py` (`_DEFAULT_CFG`) and `config/features.json` flag states. Every trade card gets a "why this trade?" affordance linking here (web + mobile), turning each suggestion into a doorway to the trust story. Smallest-effort item in Tier 1, compounding payoff: it pre-writes launch-QA's support/FAQ answers and stakes out the advocate positioning ("we negotiate with *your* values") that the teardowns identified as FTF's uncopyable frame.

## PRD

### Problem & user story
As a user shown an algorithmic trade, I don't know why I should trust it — competitors at least publish their methodology; FTF publishes nothing beyond the ranking-method chooser. As a skeptical league-mate seeing an FTF card screenshot, I want a public link that explains the system without requiring an account.

### Goals / Non-goals
**Goals**
- Public, session-free web page explaining trade discovery in named plain-English rules with one card per rule.
- "Why this trade?" affordance on every trade card linking to the page (anchored to the relevant rule where possible).
- Copy that only describes behavior that is actually ON in production (per `config/features.json`).

**Non-goals**
- No live config-value dump (numbers drift; the admin API `GET /api/admin/config` already serves exact values to the operator). Copy uses qualitative descriptions plus a few stable illustrative numbers.
- No interactive calculator/demo on this page (#27 covers an open calculator).
- Not a replacement for `docs/` — this is user-facing; engineering truth stays in `docs/architecture.md`.

### Functional requirements
- FR1: Page reachable unauthenticated at a stable URL; linked from `web/index.html` footer/FAQ area and from `web/faq.html`.
- FR2: Card per rule, each with: name, one-line summary, 2–4 sentence body, and an honest "what it can't do" line where relevant (DTC's anti-overclaim framing).
- FR3: Rules covered (each verified against code): mutual gain via your-values-vs-theirs, outlook blend, package weights, positional fit, fairness gate, sweeteners, confidence ranges. (Six cards + the mutual-gain intro; positional fit folds the marginal-value mechanics in.)
- FR4: Each card has an HTML anchor id so trade-card affordances and FAQ entries can deep-link (`/how-trades-work.html#fairness`).
- FR5: Page content reviewed whenever a covered flag or config key changes — add the page to the docs-update trigger table in `docs/CLAUDE.md`.
- FR6: Trade cards (web + mobile) show a "Why this trade?" link/sheet; web links to the page, mobile opens it in an in-app browser (pattern check against existing terms/privacy links in `SettingsScreen.tsx` (verify)).

### UX notes
- **Web:** new page `web/how-trades-work.html`, same inline-`<style>` + `:root` variables as `web/ranking-method.html` (`--bg:#0f1117`, `--surface`, `--accent` etc.), card grid mirroring its `.tile` anatomy (icon, title, description) — FPTrack's six-card layout maps directly onto the existing tile component style.
- Order cards by user-felt importance: Your Values → Mutual Gain... actually intro covers mutual gain; then Outlook Blend, Fairness Gate, Package Weights, Positional Fit, Sweeteners, Confidence Ranges.
- **Mobile:** "Why this trade?" row under the narrative on the trade card in `TradesScreen.tsx`.
- Tone: advocate, first person plural sparingly, no math notation. The page never says "fair" as a verdict — it says "defensible," reserving advocacy ("ask for more") for #4/#6.

### Draft copy (per rule card — grounded in verified keys/flags)

**Intro — Trades that help both of you.** Most calculators referee a trade after you've built it. FTF builds the trade: it compares *your* rankings against your leaguemate's and only suggests deals where each side gains by its own values. A trade only surfaces when both sides clear a real gain bar — never "you win, they lose."
*(Grounds: divergence core in `_generate_for_pair_v2`; `min_side_surplus`; both-sides gate.)*

**Your values, not a global chart.** Every 3-player matchup you rank tunes a personal value for each player. Until you've ranked someone, we quietly assume the market consensus — your opinion only moves a price once you've actually expressed one.
*(Grounds: personal Elo + DynastyProcess-seeded consensus; `_shrink_user_elo` / `shrink_pseudocount`.)*

**Outlook blend.** Contending? We weight what a player is worth *now*. Rebuilding? We weight what he'll be worth in two years. Your team outlook sets the blend, and a 29-year-old RB prices very differently at each end of it.
*(Grounds: flag `trade.outlook_blend` ON; `outlook_alpha_championship` 1.00 → `outlook_alpha_jets` 0.10; `_AGE_NOW_CURVE`/`_AGE_FUTURE_CURVE`.)*

**Package weights — four quarters aren't a dollar.** In a 3-for-1, the best player carries the deal; the depth pieces count for less the further they sit below him. We also charge a roster-spot cost to the side receiving more bodies — every extra player squeezes someone off your bench.
*(Grounds: `package_value_v2` + `package_adj_gamma`; `waiver_slot_cost` 425.)*

**Positional fit.** A third QB isn't worth a second WR1 to *you*. We profile every roster's depth — needs and surpluses by position — and value players by what they add over your replacement at that spot, so suggestions fill holes instead of stacking redundancy.
*(Grounds: `analyze_roster_strengths`; flag `trade.marginal_value` ON; `replacement_levels`/`marginal_value`, `bench_credit_rate`, `waiver_baseline_value`.)*

**Fairness gate.** Mutual gain by your two opinions isn't enough — the deal also has to be defensible at market prices, or nobody hits accept. Lopsided-by-consensus packages are filtered before you ever see them. We check fairness with value *ranges*, not false-precision points (see Confidence ranges).
*(Grounds: `_fairness` range-overlap gate; `fairness_threshold` per-job param; `fairness_weight` 0.30 vs `mismatch_weight` 0.70.)*

**Sweeteners.** When a deal is close but tilted, we look for the small piece that closes the gap and attach it — labeled, so you can see exactly what's balancing the trade.
*(Grounds: `trade_engine.v3` ON; `sweetener_band` 0.15, `sweetener_max_cards`; `sweetener` field on cards.)*

**Confidence ranges.** A player you've ranked a dozen times has a tight value; one you've never ranked is a wide guess. Ranges shrink as you rank more — which is also why ranking more makes your suggestions better.
*(Grounds: `_value_uncertainty`, `range_base` 0.35; ties to #16's display work.)*

### Success metrics
- "Why this trade?" click-through ≥10% of trade-card impressions in week 1, settling ≥3%.
- Support/feedback volume tagged "how does this work" (via `app_feedback`) drops post-launch.
- Page is the top non-app landing destination from shared trade cards once #12 ships.

### Acceptance criteria
- [ ] Page renders unauthenticated; no session-dependent fetches.
- [ ] Every claim matches current flag state (e.g. no QB-tax card — `trade_math.qb_tax` is false; no claim about three-team trades — `trade.three_team` is false).
- [ ] Anchors stable and linked from at least: web trade card, FAQ, mobile trade card.
- [ ] Copy reviewed by operator (it's positioning, not just docs).
- [ ] `docs/CLAUDE.md` trigger table gains a row: config/flag changes touching covered rules → update this page.
- [ ] `docs/api-reference.md` untouched (no API change) unless the flag route list changes.

## HLD

### Components touched
`web/how-trades-work.html` (new), `web/index.html` + `web/faq.html` (links), `web/js/app.js` (trade-card affordance), `mobile/src/screens/TradesScreen.tsx` (+ trade card component) for the link, `backend/feature_flags.py` only if the affordance is flagged.

### Data flow
None at runtime — static page. Optional progressive touch: fetch `GET /api/feature-flags` client-side and hide cards whose backing flag is off, so the page self-heals against flag flips (the endpoint already serves the dotted map for `window.FTF_FLAGS`).

### Flags & config interplay
- Page itself ships unflagged (like `faq.html`/`privacy.html`).
- Card affordance behind new flag `trades.why_link` (default false) so web/mobile can light it together after the page is reviewed.
- Content coupling (the real risk): the page describes `trade.outlook_blend`, `trade.marginal_value`, `trade_engine.v3` behavior — all currently ON in `config/features.json`. The FR5 docs-trigger row is the mitigation; the optional flag-aware hiding is the backstop.

## LLD

### Engine/backend changes
None. (Deliberately: the page documents; it does not introduce knobs.)

### API changes
None. The affordance reuses existing card payload fields (`narrative`, `reasons` when `trade_math.human_explanations` is ON, `sweetener`) to choose a deep-link anchor — e.g. cards with a `sweetener` link to `#sweeteners`.

### Schema changes
None.

### Client changes
- `web/how-trades-work.html`: static page, tile-card markup per `ranking-method.html` conventions; anchor ids `#your-values #outlook #packages #fit #fairness #sweeteners #confidence`.
- `web/js/app.js`: render "Why this trade?" link on trade cards (flag-gated via `window.FTF_FLAGS["trades.why_link"]`).
- `web/faq.html`: link + 2–3 FAQ entries that point at anchors instead of duplicating copy.
- `mobile/src/screens/TradesScreen.tsx`: "Why this trade?" row opening the page URL (server-hosted, so copy updates don't need an app release).

### Rollout (flag name proposal, default state)
Page deploys with next web push, unflagged. `trades.why_link` default false → flip web first, mobile after the TestFlight build containing the row ships. No engine risk at any point.

### Open questions
1. Include illustrative numbers (e.g. "the roster-spot cost is roughly a rank-300 player") or stay fully qualitative? Numbers are stickier but drift with `model_config` tuning — recommendation: qualitative, with at most the waiver-slot analogy.
2. URL naming: `how-trades-work.html` vs extending `ranking-method.html` into a combined methods page? Separate page recommended (ranking-method is a functional chooser in the onboarding flow, not an explainer — different job).
3. Should consensus-basis cards (`basis == "consensus"`, shown for unranked leaguemates) link to a distinct anchor explaining the fallback honestly? Recommended yes — add a short "When a leaguemate hasn't ranked yet" card.
4. Does mobile have an existing in-app browser pattern for terms/privacy to reuse? (verify in `SettingsScreen.tsx`)

## Dependencies & sequencing
- **No dependencies** — Wave 1 in the backlog sequencing ("suggestions get smarter and explain themselves"); shippable this sprint.
- **Coordinate copy with:** #6 (verdict banner wording must match the fairness card's vocabulary), #16 (confidence-range display should use this page's language), #4 (ask-for-more framing), #9 (divergence card copy ↔ "Your values" card).
- **Future additions:** a pick-valuation card when #15's dynamic values ship; an outlook-classifier card when #1 ships ("how we read your league"); update when #10's crown-asset multiplier reconciles the package rule.
- The page is also the canonical link target for #12's shared trade cards and #19's extension overlay ("What is FTF?" moment).

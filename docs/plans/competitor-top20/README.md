# Top-20 Feature Deep Dives — Index

Companion to [../competitor-feature-backlog-2026-06-11.md](../competitor-feature-backlog-2026-06-11.md) (92-item ranked backlog). Each file: Summary · PRD · HLD · LLD · Rollout · Dependencies, grounded in `trade-engine-v2` branch code as of 2026-06-11.

| # | File | Proposed flag | One-line scope |
|---|---|---|---|
| 1 | [01-opponent-outlook-classifier.md](01-opponent-outlook-classifier.md) | `trade.outlook_infer` | Infer contend/rebuild for every league team; price opponents with their alpha, not not_sure 0.50 |
| 2 | [02-asset-preference-lists.md](02-asset-preference-lists.md) | (see doc) | Untouchables hard filter + Targets acquisition bias |
| 3 | [03-swap-player-counter.md](03-swap-player-counter.md) | (see doc) | Tap-to-swap on trade cards, adjusted-value proximity band, live rescore endpoint |
| 4 | [04-fairness-control-ask-for-more.md](04-fairness-control-ask-for-more.md) | (see doc) | Fairness gate → off allowed; inverted sweetener surfaces "ask for more" candidates |
| 5 | [05-post-trade-impact-preview.md](05-post-trade-impact-preview.md) | `trade.impact_preview` | Before/after position values, ranks, needs — both teams |
| 6 | [06-verdict-gap-banner.md](06-verdict-gap-banner.md) | (see doc) | Named verdict + quantified gap + fix; full copy matrix included |
| 7 | [07-rejection-reason-feedback.md](07-rejection-reason-feedback.md) | (see doc) | One-tap rejection reasons → `trade_rejection_reasons` table |
| 8 | [08-per-league-outlook.md](08-per-league-outlook.md) | `trade.outlook_seed` | Per-league storage already exists; this adds classifier-seeded defaults + first-run confirm |
| 9 | [09-community-diff-angles.md](09-community-diff-angles.md) | `tiers.community_diff` + `trade.diff_angles` | You-vs-market badges, buy-low/sell-high angles, card narrative hooks |
| 10 | [10-key-asset-package-adjustment.md](10-key-asset-package-adjustment.md) | `trade.crown_asset` | Crown multiplier (`crown_rate`/`crown_share_floor`); closes 1-for-1 fairness-gate watch item |
| 11 | [11-received-offer-analyzer.md](11-received-offer-analyzer.md) | `offers.inbox_auto` (off) | Analyze received Sleeper offers; V1 manual entry; read-only forever |
| 12 | [12-send-to-sleeper-share.md](12-send-to-sleeper-share.md) | (see doc) | Sleeper deep link (spike-gated) + `shared_trades` snapshot + share image |
| 13 | [13-ranking-gamification.md](13-ranking-gamification.md) | (see doc) | Daily goal, coverage meters, "N new trade angles" reward (streaks/leaderboard already exist) |
| 14 | [14-league-power-rankings.md](14-league-power-rankings.md) | (see doc) | Stacked value bars, team audit, dual consensus/your-Elo view, home rank chips |
| 15 | [15-pick-capital-dashboard.md](15-pick-capital-dashboard.md) | (see doc) | Pick inventory + dynamic pick values via #1; ⚠ found pick_value scale discrepancy — triage |
| 16 | [16-value-confidence-ranges.md](16-value-confidence-ranges.md) | `trade.value_ranges` | Display Elo uncertainty as ranges; zero engine changes |
| 17 | [17-player-profiles.md](17-player-profiles.md) | (page unflagged) | Profile template; **#57 `player_value_history` snapshot job ships now** |
| 18 | [18-trade-push-notifications.md](18-trade-push-notifications.md) | (see doc) | Scheduled engine runs → quality-gated Expo push; plumbing largely exists |
| 19 | [19-extension-sleeper-overlay.md](19-extension-sleeper-overlay.md) | (see doc) | Verdict overlay on Sleeper web trade screen; no new manifest permissions needed |
| 20 | [20-engine-transparency-page.md](20-engine-transparency-page.md) | `trades.why_link` | "How trades are found" page; draft copy for 7 rule cards included |

**Cross-cutting findings from the LLD pass (corrections to the backlog's assumptions):**
- #8: per-league outlook storage/API already exists (`league_preferences`) — scope shrank to seeding + confirm UX.
- #13: streaks, leaderboard, `/api/progress`, league coverage already shipped — scope is the goal/reward loop only.
- #6: per-side package values are computed but dropped before card serialization — small serializer change required.
- #15: `compute_pick_value` (~67.5 mid-1st) vs the 0–10000 scale documented in `dynasty_value` — real discrepancy, triage independently of the feature.
- #2: `pos_acquire_bonus`/`pos_tradeaway_bonus` exist in `_DEFAULT_CFG` but are never applied (dormant keys) — decide revive vs replace.
- Immediate unflagged ship recommended: #17's daily value-history snapshot (every week not logged is chart history lost).

**Spikes gating Tier-1 items:** #83 Sleeper-auth feasibility memo (gates #11 V2, referenced by #12/#18); Sleeper trade-builder URL/deep-link research (#12); Sleeper web DOM mapping (#19).

**Build order (from backlog sequencing):** Wave 1: 1→8→10→6→16→20 · Wave 2: 2→7→4→13 · Wave 3: 3→5→14→15→17(+history job now) · Wave 4: 12→18→19→11→9 threaded throughout.

# Monetization plan docs — index

PRD/HLD/LLD bundles for the five monetization plans selected in
[the top-5 brainstorm doc](../../business/product/2026-07-17-monetization-brainstorm-and-plans.md)
(research: [appendix](../../business/product/2026-07-17-monetization-research-appendix.md)).
Authored 2026-07-17. Status: DRAFT — pending operator green-light; nothing built yet.

**Read [00-platform-foundation.md](00-platform-foundation.md) first.** It owns the
shared primitives every bundle references: entitlement service + tables, feature
flags (all dark by default), IAP enablement + subscription tracking (RevenueCat +
Stripe → webhook ledger → projector), the operator manual-grant admin routes, and
the growth-loop infrastructure (referrals, group unlock, share-card links).

| Plan | Docs | Flag(s) | One-liner |
|---|---|---|---|
| Pro subscription | [pro-subscription/](pro-subscription/) | `monetize.pro`, `monetize.paywall` | $4.99/mo decoy · $34.99/yr hero + 14-day trial; multi-league/knobs/alerts/ad-free; give-get referral months |
| Season Pass | [season-pass/](season-pass/) | `monetize.season_pass` | Year-labeled non-consumable $19.99 + spring Rookie Pass; milestone league unlock |
| Founder Lifetime | [founder-lifetime/](founder-lifetime/) | `monetize.founder` | $79 perpetual, cap 100, TestFlight-window (Stripe rail) → paywall anchor; Founder badge |
| Affiliate layer | [affiliate/](affiliate/) | `monetize.affiliate` | DFS + sportsbooks (DK/Fanatics/Caesars/FD/theScore/bet365 + Underdog), CPA-only, web/extension first, geo-gated, config-driven partner registry; iOS promotes indirectly via a neutral link-out to the `web/offers.html` hub |
| Hybrid ads | [ads/](ads/) | `monetize.ads_mobile`, `monetize.ads_web` | AdMob banner+rewarded / web network ladder; ad-free via Pro or `ad_free` referral reward |

Cross-cutting flags: `monetize.entitlements` (master, observe→enforce),
`growth.referral`, `growth.group_unlock`.

**Phase-2 candidate (plan stage, no PRD yet):** the
[rankings marketplace](../../business/product/2026-07-17-rankings-marketplace-plan.md)
— publisher rank sets in-app (DLF/PlayerProfiler IAP + subscriber linking) and a
contributor marketplace gated on a dynasty accuracy contest; its passive-scoring
Phase 1 (`ranks.accuracy_scoring`) is season-long-lead and worth starting early.

Build order (from the foundation doc §1): foundation platform → observe mode →
Founder window + paywall → Pro + Season Pass at launch → referral → affiliate
placements (calendar-driven: BBM window is Jul–Aug) → ads last (≥500 DAU gate).

This is a docs-only thread so far — no `status.md`/round files yet; if the build
spans multi-agent sessions, promote per [../CLAUDE.md](../CLAUDE.md).

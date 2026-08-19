# Card evidence

Presentment around suggested trades: honest verdict, both-team impact, you-vs-market sentence, inbound-offer analyzer, league trade history, this-league comps. **Does not change generation.**

**Status:** active, not built · 2026-08-19
**PRD (EM-facing):** [PRD.md](PRD.md)
**Engineering gate:** [scope.md](scope.md)
**Sister:** [landability-challenger](../landability-challenger/) (which cards exist). Landability B2 is **E1** here — don’t file it twice.

Parents (sequence, don’t fork): [top20 #5](../competitor-top20/05-post-trade-impact-preview.md), [#6](../competitor-top20/06-verdict-gap-banner.md), [#9 FR4](../competitor-top20/09-community-diff-angles.md), [#11 V1](../competitor-top20/11-received-offer-analyzer.md), backlog #26 / #41-scoped-to-this-league. Capture already on: `market.trade_capture`.

## Tickets

| ID | Wave | Title | Who | Est | Depends | Users see it? |
|---|---|---|---|---:|---|---|
| E1 | 1 | Honest verdict copy (0.75 even floor) | backend + mobile + web | 1.5d | — | **yes** (flag default on) |
| E2 | 1 | Both-team impact on the card | backend, then clients | 3.5d | — | when `trade.impact_preview` lit |
| E3 | 1 | You-vs-market sentence (divergence only) | backend + narrative | 1d | — | when `trade.diff_angles` lit |
| E4 | 2 | Received-offer analyzer V1 | backend + mobile + web | 3d | E1, E2 | when `offers.analyzer` lit |
| E5 | 3 | Score league trade history | backend + league tab | 2d | capture (already on) | when `league.trade_history` lit |
| E6 | 3 | Comps strip on the open card | backend + clients | 1.5d | E5 | same / child flag |

## Do not

- Touch `_generate_trades_v2` gates, shrink, `_tier_mult`, R5.
- Ingest Roster Audit Elo or MDV VORP.
- Build a Sleeper-wide Tradabase crawler.
- Auto-inbox pending offers (`offers.inbox_auto`).
- 1y/3y projection trajectories.
- Dualize user-only ranking overlays.
- Flip `tiers.community_diff` or light bake-off interleaved serving.

## Naming

| Research name | Ticket |
|---|---|
| RA trade intelligence / MDV roster sim | E2 |
| RA letter grade / MDV structural fairness / DD banner | E1 |
| MDV market divergence (personal version) | E3 |
| RA screenshot grader | E4 (manual, not OCR) |
| RA Tradabase | E5 + E6, **this league only** |

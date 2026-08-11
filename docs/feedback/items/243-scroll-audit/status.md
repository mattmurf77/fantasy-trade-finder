# #243 — Scroll audit — status

**Status:** shipped · verified on `origin/main` 2026-08-11 (was: in-progress
2026-08-03 on branch `teardown-remediation`). All five builds are on `main`:

| Build doc | Commit on `origin/main` |
|---|---|
| `build-tradevaluebar.md` (TradeValueBar density V1) | `4795a21` |
| `build-league-home.md` (fold V1 + market pulse V3) | `78d4bb3` |
| `build-trios-three-up.md` (Trios 3-up Variant A) | `d89a4ad` |
| `build-drilldown-dedup.md` (drill-in filter dedup V1) | `b2bd078` |
| `build-pin-mode.md` (pin-mode collapsed controls V1) | `b5242ea` |

Verified by content, not just log: `whyToggle` live at
`mobile/src/components/TradeValueBar.tsx:175`, no `fontSize: 9` remaining in
that file. This staleness misdirected the #169 handoff (which briefly treated
the TradeValueBar work as an unshipped dependency) — corrected in
`../169-outlook-league-summary/operator-frame-decisions-2026-08-11.md` §7.

Multi-surface scroll/density audit with five separate build docs, all dated
2026-08-03, each implementing an operator-approved `mockups/polish-lab-2026-08/`
design: `build-drilldown-dedup.md` (LeagueSummary drill-in), `build-league-home.md`
(League-home fold + market-pulse strip), `build-pin-mode.md` (TradesScreen
pin-mode collapsed controls), `build-tradevaluebar.md` (TradeValueBar density),
`build-trios-three-up.md` (RankScreen Trios 3-up). Audit source docs
(`rank-surfaces.md`, `trades-surfaces.md`, `league-misc-surfaces.md`,
`build-drilldown-dedup.md`'s cited §1b) live alongside. No single doc
confirms a merge to `main`.

Backfilled 2026-08-08 — original session left five `build-*.md` files but no
`status.md` rollup; this file is that rollup, not a rewrite of the sub-docs.

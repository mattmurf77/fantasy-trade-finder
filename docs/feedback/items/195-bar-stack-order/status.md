# FB-195 — League bar stack top-down QB→RB→WR→TE — status

**Fixed 2026-07-27** (branch `teardown-remediation`). LeagueSummaryScreen's
vertical stacked columns now render segments TOP-DOWN as QB, RB, WR, TE —
matching the filter-pill order — by dropping the old bottom-up reverse in
`BarColumn`. **Picks placement chosen:** Picks stays LAST in the reading order
(QB→RB→WR→TE→Picks), so under the top-down flip the former top "cap" becomes
the BASE of the bar. Drill-in consistency: `groupRows` filtered sections now
sort by canonical QB→RB→WR→TE instead of filter-toggle (Set insertion) order;
the unfiltered drill-in and the legend already matched. Pure presentation —
values, ranking, a11y labels unchanged.

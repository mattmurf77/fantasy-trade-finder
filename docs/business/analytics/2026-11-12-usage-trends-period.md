# Tracking-plan addendum — Usage Trends period toggle (2026-11-12)

**Status:** registered with the build ([scope](../../plans/usage-trends/scope-period-toggle.md) §1). Takes effect from the first mobile release that contains the **Last week | Last 3 weeks** pill. Amends [2026-10-10-usage-trends-events.md](2026-10-10-usage-trends-events.md); no new event name.

## Question this answers

**One week or three?** Do people read the three-week reading at all, and do Adds / Trades come from it or from the one-week lists? Split `usage_trends_action` by `period` and `order`; count `usage_trends_view_changed {period: 'three_weeks'}` per visit.

## Props

| Event | Class | New prop | Values | Fires when |
|---|---|---|---|---|
| `usage_trends_view_changed` | non-intent (unchanged) | `period` | `week` (Last week, default) \| `three_weeks` (Last 3 weeks) | The period pill changes (Simple view; shown with three or more weeks selected). Carried on every other view change, reporting the state after the change, like `order` |
| `usage_trends_action` | **INTENT** (unchanged) | `period` | as above | A Trade, Add or Re-rank is tapped, before navigation |

**Reading the prop.** `period` is the pill's state. It is reported in Raw stats too (where the pill doesn't show and the table ignores it), exactly as `order` is; filter on `view = 'simple'` for what the user was looking at. With fewer than three weeks selected the pill hides and the list is the one-week reading while `period` keeps the last choice; join `weeks` (`default`, or the picked weeks) to exclude those rows.

**Registration.** `backend/analytics_taxonomy.py` `CLIENT_EVENT_PROPS` in the same commit as the emitter (`mobile/src/screens/UsageTrendsScreen.tsx`), pinned by `mobile/tests/check-usage-trends.js` 3b and 2e8.

**PII:** none added.

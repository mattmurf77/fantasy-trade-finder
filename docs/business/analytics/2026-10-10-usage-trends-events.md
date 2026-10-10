# Tracking-plan addendum — Usage Trends (2026-10-10)

**Status:** registered with the feature build ([scope](../../plans/usage-trends/scope.md) §1). Takes effect from the first mobile release that contains `UsageTrendsScreen`. The flag `usage_trends.enabled` ships on (operator, 2026-10-10), so rows start with the first iOS 1.21.0+ session.

## Questions these events answer

1. **Do people act on a usage signal?** Measured as Trade / Add / Re-rank taps per Usage Trends visit, split by the headline `signal` the row showed. The comparison that matters is spike vs none.
2. **Which entry earns the visits?** `screen_viewed {screen: 'UsageTrends'}` already carries `prev_screen`: `Home` or `FreeAgents`. No new event is needed.
3. **Which metric do people read?** `usage_trends_view_changed.metric`. If almost nobody leaves the default Snaps view, Carries and Targets are candidates to cut, in keeping with the operator's simplicity brief.
4. **Is cross-league availability worth its button?** Opens per visit, and `n_free_agent` at open.
5. **Which version wins?** The operator asked for two views behind a pill (Version A story cards, Version B raw-stats table). `view` on every event splits visits, actions and filter use by version.

## Events

| Event | Class | Properties | Fires when |
|---|---|---|---|
| `usage_trends_action` | **INTENT** | `league_id` (the league acted in), `action` (`trade`\|`add`\|`rerank`), `player_id`, `position`, `metric` (`snaps`\|`carries`\|`targets`), `signal` (`spike`\|`return`\|`new`\|`out`\|`rising`\|`falling`\|`none`), `focus_status` (`mine`\|`rostered`\|`free_agent`\|`unknown`, in that league), `ownership` (`all`\|`rostered`\|`free_agents`), `view` (`simple`\|`stats`) | A Trade, Add or Re-rank control is tapped (row, availability sheet or expanded table row), **before** navigation |
| `usage_trends_availability_opened` | non-intent | `league_id`, `player_id`, `n_leagues`, `n_free_agent`, `view` | The availability sheet opens (Version A) or a table row expands (Version B) |
| `usage_trends_view_changed` | non-intent | `league_id`, `metric`, `ownership`, `view`, `sort` (`default` \| `player_asc` \| `w4_desc` \| `total_asc` …, Version B's column sort), `weeks` (`default` = last four, or the picked weeks, e.g. `2,6`) | The view pill, metric, ownership, week selection or a Version B column sort changes. The state after the change is reported |

**Why the classes:** `usage_trends_action` is a deliberate move on a player, the outcome this surface exists to produce. It is the peer of `find_trades_tapped`. The other two read or reshape a payload already in memory: the `tab_selected` / `receipts_window_changed` class. They are listed in `analytics_queries.NON_INTENT_EVENTS` in the same commit as the emitters, so a browse-only visit adds no user-day beyond the existing `screen_viewed` handling.

**Not tracked:** the count vs. % of team toggle. It is a display-unit switch, and adding it would just be a prop on `usage_trends_view_changed` if the question ever arises.

**PII:** player ids and league ids only, the same posture as the existing league events. No manager names; the availability sheet's owner names stay out of the event stream.

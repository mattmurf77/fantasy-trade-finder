# Tracking-plan addendum: time to trade suggestion (2026-10-20)

**Status:** draft for analytics-lead's review, written before any emitter ships (G-031).
- **Grant:** analytics-lead's Ask 1b, 2026-10-15 (`docs/plans/org-bringup/reports/analytics-lead.md`). R1–R3 are
  granted with conditions; R4 is refused, and `network_type` is a prop instead.
- **Scope:** `docs/plans/trade-time-to-suggestion/scope-eng-200ms.md` §1. PRD: PR #339 (§4.6). The gate is 200 ms,
  which supersedes #339's 250 ms.
- **Seam:** R1–R3 have **no history before the first iOS release that contains them**, and the server half before
  the first deploy that contains it. Any tap-to-card number from before that is a proxy (`trade_card_viewed`
  `ms_since_open`, or `trades_generated.gen_ms`).

## Questions these events answer

1. **AC-L1:** p95 from the tap on a search-starting control to the first card that is ≥ 50% visible with Like and
   Pass enabled. Cells: Wi-Fi vs cellular × first tap vs repeat tap, with `cold_launch` reported separately (T3).
   n ≥ 40 per cell, from ≥ 2 devices.
2. **Where the time goes:** `serve_source` (device / page / cached / joined / fresh), and on the server,
   `first_publish_ms`.
3. **How fresh the shown deck was:** `freshness_state` on the client, `oldest_input_age_s` on the server.
4. **What failed:** R2b's `reason`. Every R2b counts as > 200 ms in the p95 (T2).

## Events

| Event | Class | Properties | Fires when | Client |
|---|---|---|---|---|
| `find_trades_tapped` (**widened**, R1) | INTENT (unchanged) | existing `source`, `mode`, plus **`search_id`** (a client UUID). **New `source` values** are listed exactly in the M commit, which updates this table in the same PR | **At the tap** on every search-starting control (#339 table A), no longer at dispatch on the push path | mobile |
| `calc_find_a_trade_tapped` (**widened**, R1) | INTENT (unchanged) | existing, plus **`search_id`** | At the tap (already, `utils/canvasSearch.ts:52-61`) | mobile |
| `trade_first_card_shown` (**new**, R2) | **NON_INTENT** | `search_id`; `ms_from_tap` (int, a **monotonic** client clock: `performance.now()` deltas, as `api/client.ts` `_clockMs()` uses); `entry_point`; `search_type` (`organic` \| `pinned` \| `fair_sweep`); `launch_state` (`cold_launch` \| `first_tap` \| `repeat_tap`); **`network_type`** (`wifi` \| `cellular` \| `offline` \| `unknown`); `serve_source` (`device` \| `page` \| `cached` \| `joined` \| `fresh`); `freshness_state` (`fresh` \| `updating`); `job_id`; `card_index` | **Exactly at AC-L1's frame (T1):** the first frame where a real card is ≥ 50% visible with Like and Pass enabled. Once per `search_id` | mobile |
| `trade_first_card_failed` (**new**, R2b) | **NON_INTENT** | `search_id`, `ms_from_tap`, `reason` (`empty` \| `error` \| `abandoned` \| `timeout`), plus R2's `entry_point`, `search_type`, `launch_state`, `network_type`, `serve_source` | Instead of R2: **exactly one of R2/R2b per `search_id`**. `abandoned` fires on unmount or blur, or when the app leaves `active`, before a card (T4). **`timeout` = 10,000 ms** from the tap with no card | mobile |
| `trades_generated` (**widened**, R3) | as today | existing (`count`, `gen_ms`, `engine_version`, `lanes`, `deck_source`), plus **`first_publish_ms`**, **`serve_source`** (`page` \| `cached` \| `joined` \| `fresh` \| `prepared`), **`oldest_input_age_s`** (seconds since the oldest of: the roster refresh and the value snapshot; null if unknown), and the echoed **`search_id`** | **Binding (analytics-lead's condition): exactly one per user-visible deck, whatever `serve_source`.** A page serve emits it at serve. **A pre-build that is never served emits none** (a job log line only). `deck_source` keeps its meaning; `serve_source` is a separate dimension | server |

## Classes and funnel

- **R1 stays INTENT:** a hand-off tap is a user action.
- **R2 and R2b are NON_INTENT:** a system outcome echoing the R1 tap, which already counts the user. They are
  registered in `backend/analytics_taxonomy.py` and listed in `analytics_queries.NON_INTENT_EVENTS` **in the same
  commit** as their emitters.
- **`trades_generated` is funnel-v2 stage 6** (`analytics_queries.py:414`). The exactly-one rule keeps stage 6 and
  the PFO guardrail's `props.count` unchanged in meaning.

## Readout conditions (from analytics-lead; T1–T6)

- **T1:** the R2 frame (above).
- **T2:** p95 is taken over R2 ∪ R2b.
- **T3:** `cold_launch` is its own row.
- **T4:** backgrounding gives `abandoned`.
- **T5:** don't exclude tester devices from the AC-L1 query.
- **T6:** nearest-rank p95 plus a 90% order-statistic CI, with "pass, not robust" when the CI's upper end is
  > 200 ms.

## PII and privacy

- **No player ids, names or league-identifying values** in R2 or R2b. `search_id` is a client UUID; `job_id` and
  `card_index` are fine.
- **Privacy delta:** `network_type` (diagnostics) and `search_id` (an identifier linked to the user) go to
  onboarding-pm under P12: "check the App Store label, likely no change".

## Not tracked here (open)

- **`deck_buffer_empty`,** for when the user reaches the last ready card while the deck is still building (an AC-L4
  failure). It's proposed for a later grant, not part of this one.

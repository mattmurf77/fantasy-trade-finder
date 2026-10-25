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
| `find_trades_tapped` (**widened**, R1) | INTENT (unchanged) | existing `source`, `mode`, plus **`search_id`** (a client UUID). `source` values are listed exactly in "R1 `source` values" below | **At the tap** on every search-starting control (#339 table A), no longer at dispatch on the push path | mobile |
| `calc_find_a_trade_tapped` (**widened**, R1) | INTENT (unchanged) | existing, plus **`search_id`** | At the tap (already, `utils/canvasSearch.ts:52-61`) | mobile |
| `trade_first_card_shown` (**new**, R2) | **NON_INTENT** | `search_id`; `ms_from_tap` (int, a **monotonic** client clock: `performance.now()` deltas, as `api/client.ts` `_clockMs()` uses); `entry_point`; `search_type` (`organic` \| `pinned` \| `fair_sweep`); `launch_state` (`cold_launch` \| `first_tap` \| `repeat_tap`); **`network_type`** (`wifi` \| `cellular` \| `offline` \| `unknown`); `serve_source` (`device` \| `page` \| `cached` \| `joined` \| `fresh`); `freshness_state` (`fresh` \| `updating`); `job_id`; `card_index` | **Exactly at AC-L1's frame (T1):** the first frame where a real card is ≥ 50% visible with Like and Pass enabled. Once per `search_id` | mobile |
| `trade_first_card_failed` (**new**, R2b) | **NON_INTENT** | `search_id`, `ms_from_tap`, `reason` (`empty` \| `error` \| `abandoned` \| `timeout`), plus R2's `entry_point`, `search_type`, `launch_state`, `network_type`, `serve_source` | Instead of R2: **exactly one of R2/R2b per `search_id`**. `abandoned` fires on unmount or blur, or when the app leaves `active`, before a card (T4). **`timeout` = 10,000 ms** from the tap with no card. §3 of the readout checks that threshold against the observed tail (ruling 30) | mobile |
| `deck_buffer_empty` (**new**, granted in ruling 30) | **NON_INTENT** | `search_id`, `deck_id`, `cards_seen`, `ms_since_first_card`, `network_type` | The user reaches the last ready card while the deck is still building and no next page is local. That's an AC-L4 failure. At most once per `search_id` | mobile |
| `trades_generated` (**widened**, R3) | as today | existing (`count`, `gen_ms`, `engine_version`, `lanes`, `deck_source`), plus **`first_publish_ms`**, **`serve_source`** (`page` \| `cached` \| `joined` \| `fresh` \| `prepared`), **`oldest_input_age_s`** (seconds since the oldest of: the roster refresh and the value snapshot; null if unknown), and the echoed **`search_id`** | **Binding (analytics-lead's condition): exactly one per user-visible deck, whatever `serve_source`.** A page serve emits it at serve. **A pre-build that is never served emits none** (a job log line only). **Calibration's `grading_refresh` decks emit none** (Calibration has its own events; ruling 30), so R3 stays "exactly one per user-visible trade deck" and the funnel and PFO queries need no exclusion. `deck_source` keeps its meaning; `serve_source` is a separate dimension | server |

## R1 `source` values (exact; analytics-lead ruling 30, before the emitter ships)

**Existing values, meanings unchanged** (`TradesScreen.tsx` at `712dcbed`):

| `source` | Control | Where |
|---|---|---|
| *(absent)* | The deck's "Find a Trade" / "Find more trades" button. **D13 removes it in this build**, so after the seam it no longer fires | `:7611`, `:7813` |
| `deck_error_retry` | Retry in the deck's error state | `:6403`, `:9066` |
| `prefs_changed_strip` | The "preferences changed" strip | `:6991` |
| `deck_summary_unpin` | Unpin on the deck summary | `:3915` |
| `deck_search_all` | Search all on the deck summary | `:3933` |
| `calculator` | The canvas Find a Trade (`calc.action.find-a-trade`) | `:3332` (auto-run) |
| `league_offer` | **League Summary "Offer" hand-off only**, after the seam | `:3332` |

**New values** (fired at the tap, from the first release that contains R1):

| `source` | Control |
|---|---|
| `league_target` | League Summary "Target" hand-off |
| `usage_trends` | Usage Trends "Trade" / "Find a trade for {player}" hand-off |
| `deep_link` | The `app/trades/finder` deep link, and inbox arrivals |
| `end_card_adjust` | The P30 end card's "Adjust what I'm looking for" apply tap (D14 a; the AC-L1 clock starts here) |
| `team_review` | Team Review's "Find my trades", only when a partner is scoped (the hand-off auto-runs a search). **Granted Q-A, 2026-10-24.** INTENT. **Out of the AC-L1 cells for launch** (Product), reported separately |

**Mislabel, so don't trend across the seam:** before the seam, **every non-calculator auto-run** (League Summary Offer
and Target, and Usage Trends) is recorded as `league_offer` (`TradesScreen.tsx:3330-3336`). After the seam,
`league_offer` means the Offer hand-off alone. Its counts aren't comparable across the seam.

## Classes and funnel

- **R1 stays INTENT:** a hand-off tap is a user action.
- **R2 and R2b are NON_INTENT:** a system outcome echoing the R1 tap, which already counts the user. They are
  registered in `backend/analytics_taxonomy.py` and listed in `analytics_queries.NON_INTENT_EVENTS` **in the same
  commit** as their emitters.
- **`trades_generated` is funnel-v2 stage 6** (`analytics_queries.py:414`). The exactly-one rule keeps stage 6 and
  the PFO guardrail's `props.count` unchanged in meaning.

## Readout conditions (from analytics-lead; T1–T7)

- **T1:** the R2 frame (above).
- **T2:** p95 is taken over R2 ∪ R2b.
- **T3:** `cold_launch` is its own row.
- **T4:** backgrounding gives `abandoned`.
- **T5:** don't exclude tester devices from the AC-L1 query.
- **T6:** nearest-rank p95 plus a 90% order-statistic CI, with "pass, not robust" when the CI's upper end is
  > 200 ms.
- **T7** (Q-B, 2026-10-24): `entry_point=prefs_changed_strip` is excluded from the AC-L1 cells and reported
  separately. Its new cards append behind the ones showing, so R2 includes the user's own swipes.

## PII and privacy

- **No player ids, names or league-identifying values** in R2 or R2b. `search_id` is a client UUID; `job_id` and
  `card_index` are fine.
- **Privacy delta:** `network_type` (diagnostics) and `search_id` (an identifier linked to the user) go to
  onboarding-pm under P12: "check the App Store label, likely no change".
- **Ingest** (2026-10-24, analytics-lead accepted): `search_id`, `job_id` and `deck_id` skip the 16+ digit-run PII
  scrub **only when the whole value is a uuid or 32 hex chars** (`analytics_ingest._HEX_ID_PROPS`). About 1% of
  uuid4s hold such a run, and scrubbing them would collapse searches onto one id and break T2. The email, bearer and
  JWT rules still apply.

## Not tracked here

Nothing open: `deck_buffer_empty` is granted (ruling 30) and listed above.

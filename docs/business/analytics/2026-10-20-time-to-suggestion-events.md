# Tracking-plan addendum: time to trade suggestion (2026-10-20)

**Status:** accepted by analytics-lead (ruling 30, 2026-10-20; Q-A and Q-B, 2026-10-24). Written before any emitter
shipped (G-031); the emitters ship in #363.
- **Grant:** analytics-lead's Ask 1b, 2026-10-15 (`reports/analytics-lead.md`, the agent org's working record, kept outside the repo; cited for provenance). R1–R3 are
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
4. **What failed:** R2b's `reason`. Every R2b counts as > 200 ms in the p95 (T2), except `paywall` and `verify`, which the p95 excludes (T2 as amended).

## Events

| Event | Class | Properties | Fires when | Client |
|---|---|---|---|---|
| `find_trades_tapped` (**widened**, R1) | INTENT (unchanged) | existing `source`, `mode`, plus **`search_id`** (a client UUID). `source` values are listed exactly in "R1 `source` values" below | **At the tap** on every search-starting control (#339 table A), no longer at dispatch on the push path | mobile |
| `calc_find_a_trade_tapped` (**widened**, R1) | INTENT (unchanged) | existing, plus **`search_id`** | At the tap (already, `utils/canvasSearch.ts:52-61`) | mobile |
| `trade_first_card_shown` (**new**, R2) | **NON_INTENT** | `search_id`; `ms_from_tap` (int, a **monotonic** client clock: `performance.now()` deltas, as `api/client.ts` `_clockMs()` uses); `entry_point`; `search_type` (`organic` \| `pinned` \| `fair_sweep`); `launch_state` (`cold_launch` \| `first_tap` \| `repeat_tap`); **`network_type`** (`wifi` \| `cellular` \| `offline` \| `unknown`); `serve_source` (`device` \| `page` \| `cached` \| `joined` \| `fresh`); `freshness_state` (`fresh` \| `updating`); `job_id`; `card_index` | **Exactly at AC-L1's frame (T1):** the first frame where a real card is ≥ 50% visible with Like and Pass enabled. Once per `search_id` | mobile |
| `trade_first_card_failed` (**new**, R2b) | **NON_INTENT** | `search_id`, `ms_from_tap`, `reason` (`empty` \| `error` \| `abandoned` \| `timeout` \| `paywall` \| `verify`; see "R2b gate reasons" below), plus R2's `entry_point`, `search_type`, `launch_state`, `network_type`, `serve_source` | Instead of R2: **exactly one of R2/R2b per `search_id`**. `abandoned` fires on unmount or blur, or when the app leaves `active`, before a card (T4). **`timeout` = 10,000 ms** from the tap with no card. §3 of the readout checks that threshold against the observed tail (ruling 30) | mobile |
| `deck_buffer_empty` (**new**, granted in ruling 30) | **NON_INTENT** | `search_id`, `deck_id`, `cards_seen`, `ms_since_first_card`, `network_type` | The user reaches the last ready card while the deck is still building and no next page is local. That's an AC-L4 failure. At most once per `search_id` | mobile |
| `deck_i1_check` (**new**, S0's C-a readout; analytics-lead's pre-grant, 2026-10-26, with models-lead's R2.4 addendum (ii)) | **NON_INTENT** | `job_key` (sha256 of the job id, first 12 hex: the readout de-duplicates by it); `mode` (`strict` \| `lenient`); `status` (`fresh` \| `stale` \| `unknown` \| `missing`); `outcome` (the `[i1] serve` line's: `served`, `served_lenient`, `unchecked_c_e`, or a gate miss, `_held` when held); `age_bucket` (the roster snapshot's age: `under_5m` (inside the 300 s roster bound) \| `5m_to_1h` \| `1h_to_24h` (inside the 24 h import bound) \| `over_24h` \| `none`); `cards`, `kept`; `dropped_cards` (distinct cards with a moved asset); `dropped_give_player`, `dropped_give_pick`, `dropped_receive_player`, `dropped_receive_pick` (cards per side × asset type: a card that moved on both sides counts once in `dropped_cards` and once per side here); `unchecked_generic`, `unchecked_pick_owner`. **No league id, no raw job id, no player ids**: the league rides the row's `league_id` column | Each served page that ran the I-1 check (the `[i1] serve` log point): the job views, legacy and paged, and the page-store serve. **At most one per (job, page)** in the process; a legacy cumulative body counts once, when the job is complete. None at `trade_i1_mode` 0, under the admin gate-miss hook, or when the roster read fails. Owner = the viewer; written non-touching (`touch_user=False`) off the request thread after the response | server |
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

## Seam: #370 (Calibration refresh decks stop emitting)

**What changes at #370's merge** (PR #370, "Trades packed-evidence stage 1"; this change is ungated, with no knob).
Source: release-lead #370 QA, 2026-10-26.
- `_pregenerate_grading_targets` (`server.py:27525` on `origin/main`) passes `source="grading_refresh"`
  (`server.py:29608` @ #370 `50360031`).
- Those jobs **emit no `trades_generated`** (`server.py:11275`, `:9615` @ #370 `50360031`) and **write no
  `trade_impressions`** (`server.py:10994`, `:9575` @ #370 `50360031`). Receipts skip them.
- Their `deck_source` reads `grading_refresh` instead of `replenish`.

**The series break:** the daily `trades_generated` count drops by about one per Calibration target pair on
pregenerate days. Affected readers: funnel stage 6 (`analytics_queries.py:422`), the deck count (`:699`), and TTFV
reach and the empty-deck rate (`:967-1029`). **Don't trend these across #370's merge date.** Before the merge,
Calibration refresh decks counted as `replenish` (the refresh calls `_replenish_deck_for`, `server.py:27545`, which
sets `source = "replenish"` at `:24142`), so they **can't be separated from real replenish decks in history.**

- **Break date:** `#370 merge date: 2026-10-26 (merged 11:22 UTC; analytics_queries.SERIES_BREAKS @ origin/main records the break day "2026-10-26")`
- **The binding rule still holds:** exactly one `trades_generated` per user-visible deck. A grading deck actually
  served in Trades still emits, per release-lead's P2-2 fix, which lands before the merge. Calibration-only decks
  aren't user-visible trade decks, so they correctly emit none (the R3 row above).
- **No reader filter change is needed** going forward: after the merge no grading-only deck emits, so the readers are
  correct as written. Pre-merge history can't be corrected; the relabel isn't retroactive.

## R2b gate reasons (analytics-lead's grant, 2026-10-27; #393 M2)

- R2b `reason`: `empty | error | abandoned | timeout | paywall | verify`. `paywall` = a 402 pro_required with any gate except verify_required. `verify` = a 402 gate=verify_required, or a 403 verification_required on a gated route (client gateSignalFor). Both fire when the gate answer arrives, before the paywall or VerifySheet shows.
- No new props: no `gate` or `kind` on R2b. A send never produces R2b. The class stays NON_INTENT.
- **Seams:**
  1. Builds before the first one carrying these values report gate-ended searches as `error`, including today's 403 verify path. Segment R2b reasons by `app_version`, not by date.
  2. At the 11-18 enforcement flip, `paywall` appears once is_enforcing() is on; web also needs `paywall_web_enforce_enabled`.

## Classes and funnel

- **R1 stays INTENT:** a hand-off tap is a user action.
- **R2 and R2b are NON_INTENT:** a system outcome echoing the R1 tap, which already counts the user. They are
  registered in `backend/analytics_taxonomy.py` and listed in `analytics_queries.NON_INTENT_EVENTS` **in the same
  commit** as their emitters.
- **`deck_i1_check` is NON_INTENT:** a server-fired outcome of each served page, background polls included; the serve's request already counts the user. Registered and classified in the same commit as its emitter. **Readout:** the would-drop rate is Σ`dropped_cards` / Σ`cards` over `mode=lenient` rows. Not Σ(`cards` − `kept`): at `trade_i1_mode` 1 nothing is dropped, so `kept` = `cards` and that reads 0%; the drop columns carry what strict mode would drop. Sum a deck's pages by `job_key`. The per-type columns overlap within a side: a card whose give side moved both a player and a pick counts once in `dropped_give_player` and once in `dropped_give_pick`, so `dropped_give_player` + `dropped_give_pick` can exceed the cards with a give-side drop. Use `dropped_cards` for the rate and the per-type columns for the split.
- **`trades_generated` is funnel-v2 stage 6** (`analytics_queries.py:422` @ `origin/main` `25e1f838`). The exactly-one
  rule keeps stage 6 and the PFO guardrail's `props.count` unchanged in meaning.

## Readout conditions (from analytics-lead; T1–T7)

- **T1:** the R2 frame (above).
- **T2:** p95 is taken over R2 ∪ R2b. **Amended 2026-10-27 (analytics-lead):** AC-L1's p95 is over R2 ∪ R2b EXCLUDING `paywall` and `verify`. Gate outcomes are product gates, not latency, and are reported as their own rows.
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

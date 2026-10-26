# PRD — Time to trade suggestion: first card within 200 ms, and only up-to-date offers

**Date:** 2026-10-15 · **Status:** planning (no code) · **Author:** trades-pm (PRD worker)
**Entry point:** direct operator ask, 2026-10-15, verbatim: *"Time to trade suggestions. This should be
within 250 ms of hitting find a trade and must be up to date trade offers."*
**Strategy owner:** the operator (direct ask), read through the pm-pfo core-loop lens: tapping Find a
trade and seeing a first credible suggestion is the payoff of the whole loop
(sign in → sync → rank → values → suggestion; `docs/business/context.md:68-71`).
**Ownership split:** product owns the WHAT (this doc: target, measurement, freshness rule, acceptance).
Eng (head-eng → trades-eng, models-eng) owns the HOW. §10 lists candidate approaches only as
trade-offs; nothing here picks an architecture.
**Companions:** [scope.md](scope.md) (feature-scope gate) · [baseline-request.md](baseline-request.md)
(the read-only query spec for analytics-lead, W3).

**Launch revision (2026-10-20).** Operator decisions, relayed through head-product:
- **"This must be ready by launch day. It is possible. We must solve it."** The target is now
  **p95 ≤ 200 ms**, replacing 250 ms. It is a **launch MUST**, and any interim bar is withdrawn.
- **"Yes building should resume on the 200 ms path."**
- On any "finding more trades" card: **"This should never happen."** There is no such card (U3,
  AC-L4).
- **DEC-2:** narrow rows for unseen trades are approved (D7). Since landed as ADR-025: packed evidence, with narrow rows as the fallback (§10.4, §15).

This revision folds in head-product's launch-readiness requirements U1–U5 (§4.7, §5.5) and launch
criteria AC-L1 to AC-L8 (§8). It records the engineering constraints from the trades-eng memo as
constraints (§10.7), and adds the hidden ms readout (§9.5). Historical baseline numbers are
unchanged.

---

## 0. What this PRD decides, and what it leaves open

It pins three things: what the 200 ms clock measures (§4), what "up to date" means for each input and
what happens when an input is past its bound (§5), and the acceptance criteria a build must pass (§8),
including the operator TestFlight checklist (§9.4), the only runtime evidence mobile gets under D-056.

It does not choose between prepared inventory, a device-resident first page, faster generation,
progressive publication or a transport change. §10 lays those out with their costs. It also does not
set the storage budget; that belongs to the parallel database-shrink task, and §10.4 gives it the
footprint arithmetic.

**The headline finding from the evidence:** no measured path in the repo comes within an order of
magnitude of 200 ms. The fastest backend-only number is a **1.081 s** first-30 durable publication
from a *prepared* 936-offer inventory, measured locally on SQLite with no network and no phone
(`docs/plans/prepared-trade-inventory/release.md:161-165`). Production's last measured interactive
worker median is **61.094 s** (n=7, 2026-09-20/21;
`docs/plans/trade-search-latency/execution-20260921/infrastructure-and-precompute.md:13-23`). The
first measured tap-to-card read (W3, 2026-10-20, a client proxy over 10 taps that reached a card)
gives **p50 5,249 ms, p90 35,936 ms**, with **0 of 10 ≤ 250 ms** (§6). The 200 ms target cannot be met by
making generation faster alone. It implies the first card already exists, validated, before the tap.
That is a consequence of the number, not an architecture choice. Eng decides where the card lives.

**The second finding:** today's offers are not reliably up to date. The job cache key excludes
rosters, so a deck up to 30 min old is served after a platform roster change. The fresh path never
checks current platform rosters at publication. Sleeper send does not check player ownership
(§5.1, §5.3). The freshness half of the ask is new work, whatever happens to speed.

## 1. Problem

Tapping Find a trade is the moment the app pays off. Today it is a wait measured in tens of seconds.
The last production read: worker median 61 s, engine median 13.3 s
(`infrastructure-and-precompute.md:23`). The client polls first at 800 ms, then backs off
×1.5 to a 4,000 ms cap with ±10% jitter: up to 4.4 s between polls (`mobile/src/screens/TradesScreen.tsx:2173,2203,2207-2208`;
`trade-search-latency/execution-20260921/delivery.md:41`).
The owner path publishes no card until the first 30 are durably recorded
(`docs/plans/trade-search-latency/release-20260921/README.md:9`). Each status poll deep-copies the
job and runs a batched disposition read (`backend/server.py:15788-15806,3257-3262`).

The previous owner goal was **3 seconds** tap-to-first-actionable-tile
(`docs/plans/trade-search-latency/research-plan.md:76-83`). It was never qualified on a device.
The operator's number, first 250 ms (2026-10-15) and now **200 ms as a launch MUST** (2026-10-20),
is **15× tighter**. It adds a second, independent requirement: the offers
must be up to date. Speed and freshness pull in opposite directions. The fastest card is one computed
earlier, and a card computed earlier can be stale. G-075 shows this is not hypothetical. Headless
builds offered players who had moved: 11–12 of 12 teams differed against live Sleeper, with 76–139
player moves per league (`living-memory/GOTCHAS.md:98-102`).

## 2. User story

As a dynasty manager who taps **Find a trade**, I see a real trade card within 200 ms,
with enabled Like and Pass controls. Every player and pick on it is actually on the rosters it
claims, priced on current values and on the rankings I've given the app. If the app is still
catching up on something, it tells me, and it never asks me to act on a trade that can't happen.

**Hypothesis (to be measured, not assumed):** cutting tap → first actionable card to ≤ 200 ms raises
the share of Find a trade taps that reach a trade opinion (like or pass) and cuts abandoned taps.
The readout uses existing events: `find_trades_tapped` → `trade_card_viewed` → `match_swiped` /
`trade_proposed`. See `backend/analytics_queries.py:414,428` for the funnel stages. Impact is
unknown until the baseline lands; no lift is promised.

## 3. Threads this builds on (status checked in `docs/plans/README.md`, 2026-10-15)

| Thread | Index status | What it means for this PRD |
|---|---|---|
| `trade-search-latency/` | **not indexed in README**. Own `status.md`: in-progress, 2026-09-21 | Source of the 3 s goal, the measurement rules this PRD reuses (skeletons don't count, report cold/warm separately, no offer caps; `research-plan.md:64-92`), and #303's committed first-30 publication. Its remaining qualification backlog is still open. This PRD supersedes its **target** (3 s → 200 ms; D8), not its non-negotiables. |
| `prepared-trade-inventory/` | **active; canary repair** · 2026-09-22. Own `status.md` is 2026-09-23 | #305–#307 merged (`3bb981ed`). Preparation and adoption ship dark behind `model_config` `prepared_trade_inventory_enabled` = 0 (`docs/config-reference.md:7-17`). Last production readback: 0, on 2026-09-23 (`prepared-trade-inventory/release.md:154`). Production state since then is **unverified**. `baseline-request.md` Q0 asks for a readback. It covers default discovery only; pinned and custom searches keep their own paths (`plan.md:9`). Adoption is skipped for replenish, pinned, intent and force jobs, and needs exclusive owner-bilateral revision, value core off, and the knob = 1 (`backend/prepared_trade_runtime.py:86-96`). |
| `app-open-trades/` | **not indexed in README**. Own `status.md`: implemented 2026-09-20 | Session-init warm-up uses the saved fairness, so a later Find a trade can join it (`app-open-trades/status.md:5`). Its stated limit: it changes when work starts, not the 37–42 s fresh search (`:11`). |
| `trade-presentation-v2/` | **not indexed in README**. Flag `trades.presentation_v2` **false** | TodaysTrade / Browse-all are dark. Out of the 200 ms gate unless the flag flips (§7). |
| `deck-quality-filters/` | **not indexed in README**. Shipped #328 `71a02541`, flag `deck.quality_filters` **true** (D-207) | Filters run in `_run_trade_job` after presentment. Prepared inventory is explicitly **out of v1 scope** (`deck-quality-filters/scope.md:14`; `living-memory/DECISIONS.md:14`). A fast path that adopts a prepared deck would skip them. That is the §10.5 quality-vs-speed trade-off. |
| `db-storage-reduction/` | released 2026-09-15 | Disk is 5 GB, about 9 KB of physical storage per deck record, roughly 350,000-record headroom as of 2026-09-15 (`db-storage-reduction/release.md:15-19,50-60`). Feeds §10.4. |

Four of the six threads have no row in `docs/plans/README.md`. That gap is noted, not fixed here (this
worker may write only one README row).

## 4. The metric: what "200 ms" measures (pinned)

### 4.1 Clock start: the tap

The clock starts at the touch-up (`onPress`) of an in-scope Find a trade control, read from a
monotonic client clock (not `Date.now()` wall time, which `client_ts` uses;
`mobile/src/api/events.ts:202`).

Under today's checked-in flags, most controls labelled "Find a trade" only **navigate** to the
Acquire builder (TradesHome's inline canvas) and start no search. The flags are:
`calc.inline_home`, `calc.results_push`, `trades.finder_hub` and `nav.home_hub` on;
`calc.canvas_results` and `trades.presentation_v2` off. A search starts only from the controls in
table A, and so does the clock.

**Table A: search-starting controls (the clock starts here)**

| Control (testID) | file:line | Search it runs | Notes |
|---|---|---|---|
| Canvas **Find a Trade** (`calc.action.find-a-trade`) on the Acquire builder | `mobile/src/components/InLeagueCalculator.tsx:1313-1342`, hosted at `screens/TradesScreen.tsx:8010-8018`. Handler `handleInlineFindATrade` `TradesScreen.tsx:3414` pushes a new `TradeDeck` (`:3429-3445`) | Empty or receive-only canvas → model deck (`POST /api/trades/generate`, then `GET /api/trades/status` polling). Canvas with a give side → synchronous `POST /api/trades/fair-packages` (`utils/canvasSearch.ts:41-68`) | **The primary entry.** Organic = empty canvas, no partner. A stack push is on the critical path. |
| ~~Deck **Find more trades** (`trades.find-btn`)~~ | `TradesScreen.tsx:7601-7614`, `:7803-7816` → `handleFindTrades` `:1213` | model deck | **Leaves table A (D13 adopted; trades-pm decision, 2026-10-20; accepted (head-product P33, 2026-10-20)).** The button is removed from the deck once U3 ships; until then its taps are measured, not gated. Retry stays only in the error and offline states |
| P30 card **Adjust your search** | the P30 end card (§4.7) | Opens the deck's own preferences (fairness and filters); the changed search runs **in place** | **Search-starting (D14(a)):** the clock starts at the tap that applies the change, and the AC-L1 cells apply |
| In-deck retries | error retry `TradesScreen.tsx:6403`/`:9066`, prefs strip `:6991`, summary unpin `:3915`, search-all `:3933` | model deck | Same choke point (`:3269-3354`) |
| Handoff auto-runs | League Summary Offer/Target `screens/LeagueSummaryScreen.tsx:1281-1300`; Usage Trends "Trade" / "Find a trade for {player}" `components/UsageTrendCard.tsx:159`, `UsageStatsTable.tsx:169`, `UsageLeagueList.tsx:96` → `screens/UsageTrendsScreen.tsx:251-268`. Consumed at `TradesScreen.tsx:3195-3249` | pinned / partner-scoped model deck | Not organic. A Usage Trends handoff with no opponent dispatches **nothing**: the model auto-run needs a scoped opponent unless the origin is the calculator (`TradesScreen.tsx:3319-3347`). It lands on the builder. |
| Dead or dark today | calculator merged `onFindATrade` `screens/TradeCalculatorScreen.tsx:830-871` (needs `calc.inline_home` off); TodaysTrade `hooks/usePresentationDeck.ts:76` (flag off); `TradeFinderHubScreen` (not registered, `navigation/TabNav.tsx:38,446`); first-run auto-start `TradesScreen.tsx:2385-2404` (skipped while results-push is live, `:2392`) | — | Join table A if they come back |

**Table B: navigation-only controls labelled Find a trade (no search today)**

| Control (testID) | file:line | Lands on |
|---|---|---|
| Home tile (`home.tile.find-trade`) | `mobile/src/components/home/HomeHub.tsx:391-398` | **The top of the Trades stack, which isn't always the builder** (ux-lead F-2). It calls `navigation.navigate('Trades')` with no screen (`HomeHub.tsx:397`), and tab stacks persist across switches (`navigation/TabNav.tsx:895`), so a deck left open is what shows |
| Home list row (when `nav.home_hub` is off) | `mobile/src/screens/HomeScreen.tsx:19,44` | Acquire builder |
| League Home (`league.action.find`) and the works-now button | `screens/LeagueScreen.tsx:624`, works-now block `:861-869` → `goFindTrade` `:473-476` | Acquire builder (`TradesHome`) |
| Matches empty state (`matches.go-to-trades`) | `screens/MatchesScreen.tsx:1189` | Acquire builder |
| Calculator "Want ideas instead? Find a trade →" (`calc.find-a-trade`) | `screens/TradeCalculatorScreen.tsx:724-741` | Acquire builder (`popTo`) |

A table B tap is measured as tap → builder interactive. It is **not** a gate pass, because no trade
is shown. The operator asked for a card within 200 ms of hitting Find a trade, and from a table B
control the user needs a second tap to get one.

**Proposal for D10** (trades-pm decision, 2026-10-15, adopting ux-lead's recommendation; the
operator decides because it amends D-171's builder-first landing):
- **Onboarded users:** the Home tile, both League Home controls and the Matches empty-state primary
  start the organic deck directly.
  - The app builds the Trades stack as **builder → pushed deck**, using `push`, never `navigate`
    (G-056). Back returns to the builder, which keeps D-171's build → results → tweak loop.
  - The search goes through the same fork and analytics path as the canvas tap
    (`TradesScreen.tsx:3414-3445`).
  - The clock then starts at that tap, and these controls join table A.
- **First-run keeps the builder** while `onboarding.trades_first` is on and the user has no first
  swipe. The guide's adoption step targets the canvas button (`components/analystScript.ts:495-500`,
  `:536`). onboarding-pm signs off (ux-lead D10 limit 1).
- **The calculator row stays navigation-only** and is relabelled to say where it goes (design-lead
  D10; ux-lead D10 limit 2). Copy goes through head-product → marketing-lead.
- **A Home tile that previews the first prepared card** (within the §5.1 bounds; never a stale
  preview) is an optional follow-up for design-lead (design-lead D10).
- **If the operator keeps D-171 as is,** the table B labels change to say where they go. Leaving a
  "Find a trade" label that finds nothing is a design defect (design-lead D10).

**Other arrivals (measured, not gated; ux-lead F-8):** the `app/trades/finder` deep link, which
pushes a param-less `TradeDeck` (`navigation/TabNav.tsx:464-470`), and any inbox notification that
lands on the deck. Also **Team Review's "Find my trades"** with a partner scoped (`source=team_review`,
granted Q-A), which is out of the AC-L1 cells for launch (events contract, §15).

**Gate cohort (proposed):** every table A control whose search is the **default organic deck**
(empty canvas, no pinned asset or partner). Pinned and targeted searches are **measured and reported
from day one** but held to the gate only if the operator says so (Decision D1). Examples: "Find a
trade for {player}", a filled-canvas fairness sweep, a partner-scoped search. The reason: the prepared-inventory
design covers default discovery only (`prepared-trade-inventory/plan.md:9`), and the pinned search
space is per-request.

### 4.2 Clock end: the first actionable card

The clock stops at the first rendered frame in which a trade card is on screen and meets all four of:

1. it shows real terms: both sides' assets and the partner;
2. it is at least 50% inside the viewport, after any navigation transition;
3. its decision controls (Like / Pass, or the surface's equivalent) are enabled;
4. it passed every serve-time check in §5.3 (ownership, dispositions, model version).

**Does not count:** a skeleton (`SkeletonTradeCard`, `TradesScreen.tsx:8858`), the "Looking for
trades…" spinner card (`:8859-8873`), the "Searching… n/N opponents" strip (`:7624`), a
placeholder, a disabled card, a card still sliding in under a transition, or a server-side "ready"
event. The existing `deck_card_viewed` exposure event is **not** the end event: it needs 500 ms of
continuous visibility by design (`mobile/src/utils/offerExposure.ts:4,73-77`;
`TradesScreen.tsx:269`; see `delivery.md:59`). This is the same rule `research-plan.md:92` set for
the 3 s goal.

R2 fires at exactly this frame (analytics-lead T1). The per-feature test or the code-walk cites it.

A tap that ends in an honest **zero-results** state is reported separately as tap → empty state
(same clock). **Under analytics-lead T2 it also counts as a miss in the p95,** because every R2b
counts as above 200 ms. This replaces the earlier "neither pass nor failure" wording.

### 4.3 Percentile and sample rules

- **Gate:** p95 ≤ 200 ms, per cohort cell (§4.4). This is a **launch MUST** (operator, 2026-10-20);
  no interim bar. AC-L1 is the launch criterion.
- **Also reported:** p50, p90, p99, the share of taps ≤ 200 ms, and counts of taps that never reach
  a card: error, abandoned (left the screen or backgrounded before a card), and timed out at 60 s.
  Abandoned and errored taps stay in the denominator of "share ≤ 200 ms". A fast median must not
  hide a slow tail (`research-plan.md:78`).
- **Sample floor:** a cell's p95 is reported only at n ≥ 40 taps, from at least 2 devices including
  the operator's (AC-L1). Below that, report n, max and the share ≤ 200 ms, and mark the cell
  "insufficient".
  - Organic volume is about 1.6 searches a day (W3, §6), so the floor is reached by the **scripted
    two-device session in §9.6**, not by waiting for organic traffic.
  - Earlier context: about 8 users and 16 user-league pairs had a qualifying deck in 14 days
    (`living-memory/TEST_LEDGER.md:200-201`).
- **Window:** the §9.6 session is the launch gate. After launch, organic telemetry over rolling
  14-day windows is monitoring, compared with the W3 baseline (§6).

### 4.4 Cohorts (each reported separately; never blended)

| Dimension | Cells | Notes |
|---|---|---|
| Device | TestFlight iPhones (production backend) | iOS only. Record model and OS (already envelope columns: `device_type`, `os_version`, `app_version`; tracking plan `2026-07-17-tracking-plan-v2.md:141`). |
| Network | Wi-Fi · cellular · offline | Not captured today. Carried as a `network_type` prop on R2/R2b (§4.6; analytics-lead R4 alternative). **Both Wi-Fi and cellular are gated at 200 ms** (D3 decided 2026-10-20; AC-L1 cells include cellular). |
| Launch state | **cold-launch tap**: first tap after a process start, before that session's session-init completes · **first tap** after launch, once session-init is done · **repeat tap** in the same session · **new account's first tap after onboarding** | First-tap and repeat-tap cells are gated (AC-L1). **A new account's first Find a trade after onboarding is gated too** (AC-L7, U5; D2 decided in part, 2026-10-20). Other cold-launch taps are reported, and their gate stays open under D2. |
| Search type | organic · pinned/targeted · filled-canvas fair sweep | Organic is gated (D1). |
| Serve source | the events contract's values: client `device` / `page` / `cached` / `joined` / `fresh`; server adds `prepared` (§15 item 2) | Diagnostic, so a high cache-hit rate cannot hide a slow miss (`research-plan.md:78`). |

### 4.5 Measurement rules carried forward unchanged

The rules in `trade-search-latency/research-plan.md` §3–§4 stay binding:

- no lower candidate pools, budgets or card caps passed off as speed;
- complete eligible inventory stays accessible;
- an initial batch is a delivery batch, not a search cap;
- report the first → next-card wait and buffer-empty stalls, because a fast first card followed by a
  stall is not success (`research-plan.md:64-72,92`).

### 4.6 Instrumentation: existing first, then requests

**Existing, reusable:**

| Signal | file:line | What it gives | Gap |
|---|---|---|---|
| `calc_find_a_trade_tapped` {path, give_count, receive_count, has_partner} | fires **at the tap**, `mobile/src/utils/canvasSearch.ts:52-61`; taxonomy `backend/analytics_taxonomy.py:1604` | The best existing start anchor for the canvas path | No search or job id |
| `find_trades_tapped` {source, mode} | `TradesScreen.tsx:1221`, `:3329-3336`, `:3799`; taxonomy `:956` | Start anchor for in-deck searches | On the push path it fires inside the pushed `TradeDeck` **at dispatch, not at the tap**. Not fired from table B or Usage Trends taps |
| `trade_card_viewed` {trade_id, card_index, lane, dwell_ms, ms_since_open, cold_start, mode} | `TradesScreen.tsx:4255-4282`, once per fronted `trade_id`; taxonomy `:994-996` | The best existing end proxy (card 0 fronted). `trade_id` is server-minted | Fronting is not "controls enabled". `ms_since_open` counts from JS bundle load, not the tap |
| `deck_card_viewed` {impression_id, trade_id, card_index, dwell_ms} | `TradesScreen.tsx:4290-4330`; `hooks/useSelectedOfferSignals.ts:40-42` | Exposure, joinable to `deck_impressions` | Needs 500 ms of continuous visibility. Never an end event |
| `home_tile_tapped`, `league_home_action_tapped`, `usage_trends_action` | `HomeHub.tsx:396`, `LeagueScreen.tsx:470`, `UsageTrendsScreen.tsx:210` | Table B and handoff taps | No search id |
| Envelope `client_ts` (ISO, ms, wall clock), `session_id`, `seq` | `mobile/src/api/events.ts:188-208` | Intra-session deltas: tap event → `trade_card_viewed{card_index:0}`, same `session_id` (the baseline method) | Wall clock, not monotonic. **No `job_id` or request id reaches analytics**: `job_id` is used only for polling, and the client sends only device, OS, app-version, TZ and session headers (`mobile/src/api/client.ts:54-61,491`) |
| `trades_generated` {count, gen_ms, engine_version, lanes, deck_source} (server) | `backend/server.py:9226-9238`; value core `:7614-7617` | Full worker, kickoff → finish (`:3060-3077`) | Not time to first card. No job id. Not emitted for failed or superseded jobs. `deck_source` absent mixes interactive searches with warm-ups |
| `bakeoff_runs.total_ms`, `arms_json[arm].gen_ms` | `server.py:9171-9186` | Arm fan-out (engine) only | Excludes post-layers, filters, evidence and publication |
| `deck_impressions.served_at` | `backend/database.py:941`; `server.py:5197` | **One** timestamp taken when the logger starts, shared by every row of the job | Not the commit time; no per-batch timing |
| Log line `first durable owner batch: cards=… elapsed_ms=…` | `server.py:9033-9038` | Kickoff → first 30 committed (owner-serve path only) | A log line; not persisted |
| `user_events` `api_request` {ms, route, status} (`obs.api_events`) | `backend/api_observability.py:360-380` | Per-request handler time for `/generate`, `/status`, `/fair-packages`, `/session/init` | Successes sampled 1-in-10 (`database.py:3073`). No job id |
| Prepared `adoption_json.publication.served_at` | `database.py:70-88` | Adoption timestamps | No durations; logs only record "adopted: cards=…" |

**The events contract is landed; it is cited, not restated here.** The contract is
`docs/business/analytics/2026-10-20-time-to-suggestion-events.md` (#399, accepted in #401). It holds:
- names, properties, classes and `source` values;
- the `timeout` threshold (10,000 ms);
- readout conditions T1–T7;
- privacy and ingest rules.

The grant history (analytics-lead's Ask 1b: R1–R3 granted with conditions, R4 refused in favour of a
`network_type` prop) is recorded there. Differences between this PRD's earlier text and the
contract are in §15.

| Event (contract name) | Proves |
|---|---|
| `find_trades_tapped` and `calc_find_a_trade_tapped`, widened with `search_id` (R1) | AC-1 (every search-starting tap emits); the AC-L1 clock start |
| `trade_first_card_shown` (R2) | AC-L1 (with its `network_type` and `launch_state` cells), AC-L7, AC-2, AC-8 (`freshness_state`) |
| `trade_first_card_failed` (R2b) | AC-L1 under T2 (every R2b counts above 200 ms); AC-8b (timeout) |
| `deck_buffer_empty` | AC-L4 (zero page ends without the next page). It replaces this PRD's R5 request |
| `trades_generated`, widened (R3) | AC-1b (exactly one per user-visible deck); server timing (`first_publish_ms`, `serve_source`, `oldest_input_age_s`) |

**Separate from the contract:** a Sleeper send blocked under I-2 reuses
`sleeper_send_failed.error_code` with a new code value, and analytics-lead is told the value
(platforms-pm R4). ESPN and MFL have no client failure event; measuring their blocks per platform
would need a new grant.

No event may carry player ids, names or league-identifying values in props
(`docs/business/analytics/2026-07-17-tracking-plan-v2.md:183`).

### 4.7 What the user experiences: U1, U3 and U5 (head-product launch-readiness, 2026-10-20)

U2 and U4 are in §5.5. These requirements are product's; eng chooses how to meet them (§10.7).

- **U1. The first 200 ms are an in-place reveal.**
  - Tapping any table A control shows the first card **in place**: no screen push, no transition
    animation, no spinner, no skeleton.
  - The card is complete: real terms on both sides, the verdict, and Like/Pass enabled.
  - Under reduced motion it's the same, because there is nothing to animate.
  - This supersedes AC-2b's "short fade" option (AC-L2).

  **Decided per entry point (ux-lead, launch).** D-171's experience stays: a full-screen classic
  deck, a header Back to the builder, and the end-of-deck state. Only the transition goes.
  - "In place" means the current screen changes state with no navigation. An "instant route" means
    a navigation with `animation: 'none'`.
  - No frame between the tap and the card shows the builder mid-transition, an empty deck, the
    progress strip, the "Looking for trades…" card (`TradesScreen.tsx:8858-8873`) or a skeleton.

  | Entry point | Decision (ux-lead, launch) |
  |---|---|
  | Canvas Find a Trade (`calc.action.find-a-trade`), the primary | **Instant route:** keep the push and its back stack (D-171 rulings 2–4) with `animation: 'none'`. **Fallback, eng's choice by device measurement:** if mounting the screen alone breaks AC-L1, render a full-screen deck layer on `TradesHome` that looks and behaves identically |
  | D10 controls (Home tile, League Home ×2, Matches empty state), only if the operator approves D10 | **Instant route:** a tab switch plus the [builder → deck] stack in one dispatch, with no animation and no visible builder frame |
  | In-deck searches (error retry, prefs strip, unpin, search-all, and P30's "Adjust your search") | **In place:** the deck's contents are replaced, with no navigation. "Find more trades" is removed once U3 ships (D13 adopted) |
  | Hand-off auto-runs (League Summary Offer/Target, Usage Trends "Trade") | **Instant route.** Pinned searches aren't pre-built. If no page exists, the honest Loading state shows in the card rect. Measured, not gated (D1) |
  | Deep link `app/trades/finder`, inbox arrivals | **Instant route.** Measured, not gated |
  | First run (U5) | Unchanged: the builder, then the canvas tap uses the instant route |

  **For every entry (ux-lead, launch):**
  - Back from the deck pops just as instantly.
  - The control's pressed state is the only tap feedback.
  - On the reveal, VoiceOver focus moves to the first card, whose accessible label summarizes it
    (partner, give, get, verdict). Focus never stays on the now-hidden Find a Trade button.
  - The only first frames other than a card are serve-and-refresh's card plus the Updating line,
    the gate-miss wait, the U5 card, and offline. All except offline count against the p95.

  **Visuals (design-lead, launch, "U1: the first card, revealed in place"; the visual spec stays
  design-lead's):**
  1. No motion on the deck at all. The first card renders at its final position, size and opacity
     on its first frame. The design-system Motion rule (the 40 ms on-load stagger) gets a **trade
     deck exemption** in design-lead's next docs pass.
  2. Card, verdict, Like and Pass arrive in the same frame, enabled, with no disabled flash.
  3. The tap's only feedback is the control's pressed state; no spinner.
  4. A stable card rect: nothing mounts above the card later. The Updating label lives in the
     header's existing row (design-lead's position on D11).
  5. Pages append behind and never reorder. A position counter, if any, shows no total ("3", not
     "3 / 20").
  6. The U5 "Building your first trades" card uses the same rect, is static and has no button.
     Words: marketing-lead.
- **U3. The end of a page: the next page is always already there.**
  - The operator, on any "finding more trades" card: "This should never happen." There is **no
    "Finding more" card**.
  - Pages append behind the current card with no reorder and no jump.
  - Losing the network is not a "finding more" case. The Screen-states offline state applies
    (ux-lead; §5.4 Offline).

  **Prefetch threshold** (trades-pm decision, 2026-10-20):
  - Pages 1 and 2 are pre-built together.
  - When page N becomes the current page (its first card is fronted), page N+1 must already be in
    the device's deck, and the request for page N+2 starts at that moment. That keeps at least one
    full unseen page ahead at all times.

  **No "Finding more" card in the build** (trades-pm decision, 2026-10-20): a guard asserts that no
  such component or copy exists on the Find a trade path (AC-L4).

  **Exhaustion is not "finding more"** (trades-pm decision, 2026-10-20, as **superseded by
  head-product P30** for the end state):
  - **The genuine end (P30)** shows only when every candidate has been seen, and **never while a
    page is pending**. It is a final card in the deck slot, not a "Finding more" card, so AC-L4
    still holds.
    - **Copy (head-product P36, 2026-10-23; marketing-lead-copy.md §1b `p30.*`). Each row is
      pending operator §6:**

      | Row | String |
      |---|---|
      | p30.head | "You've seen every trade for now." |
      | p30.body | "New ideas show up as rosters and values change." (kept) |
      | p30.cta1 | "Adjust your search" (still opens the deck preferences, D14(a)) |
      | p30.cta2 | "Back to Home" (kept) |
      | p30.tally | "{passed} passed · {liked} liked · {proposed} proposed", one dim line with Plex Mono numerals (design-lead places it). **Suppressed when all three are 0 (0 · 0 · 0)** |

      marketing-lead-copy.md classes p30.head/p30.cta1 as voice swaps (not listed in its §6); head-product to reconcile.
    - No Like or Pass.
    - Visual spec: design-lead's P30 card (same rect, EmptyState construction, Primary and
      Secondary).
    - **D14 (trades-pm decision, 2026-10-20; accepted (head-product P33, 2026-10-20)):**
      - **(a)** "Adjust your search" opens the deck's own preferences (fairness and
        filters), per ux-lead, and the changed search runs in place. That is a search-starting
        action, measured under the §4 clock; the AC-L1 cells apply.
      - **(b)** D-171 ruling 4's end-of-deck tally **stays** on the P30 card as one chalk-dim line,
        which design-lead places. Retiring it would amend an operator ruling. **Amended by
        head-product P36 (2026-10-23):** the tally is suppressed when all three counts are 0
        (0 · 0 · 0).
      - **(c)** No third action and no notice. New candidates that arrive behind the P30 card aren't
        announced; they appear on the next search, including one started by "Adjust". P30's copy
        and two actions are unchanged.
  - Offline uses the Screen-states offline state.
  - **The only permitted wait card** is U5's "Building your first trades", for a brand-new account
    whose first page doesn't exist yet. It counts against the p95, and its design target is that it
    never shows.

  **Every state on the Find a trade path while swiping (ux-lead, launch).** None is a "Finding
  more" card.

  | # | Situation | What shows | Rules |
  |---|---|---|---|
  | 1 | Online; the next page is arriving | **Nothing** | Pages append behind the fronted card: no reorder, no jump, no total in a counter. Appends are silent to VoiceOver. Duplicates are dropped (I-3, I-4) |
  | 2 | Online; a next-page fetch fails while the device still holds at least one page | **Nothing** | Silent background retry with backoff |
  | 3a | **Offline**, and the user reaches the last card on the device | The Offline state in the card rect, e.g. "You're offline. More trades load when you're back online." | No spinner, no "finding". Retry is Secondary. On reconnect the next page appends automatically and replaces the offline card in place. Reported separately; **doesn't fail AC-L4** |
  | 3b | **Online, but the fetch keeps failing**, and the user reaches the last card | The recoverable Error state in the card rect: "Couldn't load more trades" plus **Try again** | It must end, and Back stays usable. **Reaching 3b while online is a prefetch failure under AC-L4** |
  | 4 | **The genuine end (P30)**: every candidate seen or acted on, and no page pending. Rows 1–3 take precedence | The P30 final card, with the D-171 tally as one chalk-dim line (D14(b)); the tally is suppressed at 0 · 0 · 0 (P36) | Static. New candidates arriving while it shows are placed **behind** it and are not announced. They appear on the next search (D14(c)); it never swaps under the user's thumb |
  | 5 | **Offline at the tap** | With a device-held first page inside the bounds: cards, plus the refresh-failed line at once. Without one: the Offline state at once, in the card rect | Offline taps are excluded from the p95 cells (`network_type=offline`) and reported. Never a wait |
  | 6 | Network lost during Like/Pass | The card's controls never go dead | A failed like or send shows on the card and keeps the user's choice (`check-swipe-failure-recovery.js`) |

  **VoiceOver (ux-lead, launch; this closes §5.4's announcement item).** All announcements are
  polite, at most one per state change:
  - "Updating" is announced once per refresh cycle.
  - Changes behind the front card and page appends are silent.
  - A withdrawn fronted card announces "{reason}. This trade is no longer available." after the
    swipe settles. Focus stays on the card, and "Next trade" comes next.
  - Refresh-failed, offline (3a, 5) and error (3b) each announce their line once.
  - The P30 card takes focus when fronted, and its copy is announced once. Its two actions follow,
    with no swipe or custom actions.

  **AC-L4's measure** (trades-pm decision, 2026-10-20): zero page ends reached without the next page
  already in the deck, across all test sessions. Telemetry: `deck_buffer_empty` (granted in ruling
  30; events contract, §4.6), which replaces the earlier R5 request (§15).
- **U5. A new user's very first tap is warm too.**
  - The first page is pre-built when a league is connected or the session starts, so the first-ever
    Find a trade also meets 200 ms (AC-L7).
  - A brand-new user who taps before their first page exists sees one honest "Building your first
    trades" card. It counts against the p95, so pre-building must finish before the user can reach
    the control in normal onboarding.

## 5. What "up to date" means

### 5.1 Inputs and proposed bounds

The bounds apply **at the moment the first card is displayed**, and again **whenever an existing deck
regains focus**: a tab return or an app foreground with no new tap (ux-lead F-2). "Age" means time
since the input was last confirmed against its source of truth. Bounds are proposals for operator
approval (Decision D5) and eng feasibility review.

**How the roster bounds are met** (trades-pm decision, 2026-10-15, on platforms-pm R7):
- **Refresh off the tap path (head-product P40, 2026-10-24):** the background floor refreshes the
  viewer's roster **off the tap path**. It runs on session start and app foreground (session-init,
  with a 60 s throttle), and on a **tap that finds the viewer's roster past its bound with the floor healthy** (a non-blocking kick, head-product P41, 2026-10-24): the refresh is enqueued off the critical path and never awaited. Cards it invalidates are withdrawn in place **at the client's next whole-deck response or focus/revalidation**, not instantly, and **I-2 blocks any action on them until then** (head-product, 2026-10-24: option (a)). It **never runs on the search tap's critical path or the first-page
  serve**. That is the same user-triggered posture as session-init today. Trades focus is a **post-launch candidate** (launch decision, head-product, 2026-10-25).
- **No scheduled or headless server-side Sleeper roster reads beyond today's pattern** until the
  operator rules on E2 (the platform risk register, PR #345). Sleeper's published Terms, revised
  2026-10-06, bar automated access without express written consent (§11.1), as platforms-pm cites
  them.
- ESPN and MFL server-side refetches use stored credentials, and stay user-triggered too. MFL calls
  stay within its guidance of 1 request per second.

| Input | Today (code) | Proposed bound at first-card display | Past the bound |
|---|---|---|---|
| **Viewer's roster**, including trades just executed on the platform and add/drops | Sleeper rosters are fetched live at every session-init: cold launch, or foreground after a real background, throttled to 60 s (`mobile/src/state/useSession.ts:65,369`; `backend/session_input.py:42-80`). ESPN and MFL come from the DB import. `/api/trades/generate` never refetches. **Rosters are not in the job cache key or signature, so a cached deck up to 30 min old is still served after a roster change** (`backend/server.py:3489-3526`, `:23021-23024`; TTL `:2285`) | **≤ 5 min** since last confirmed against the platform. A change the app itself knows about (an in-app send accepted, a refetch diff) invalidates the affected cards immediately. **Any roster move FTF completes (the #351 add/drop, platforms-pm K-F5) immediately triggers the viewer-roster refresh, and affected cards are withdrawn in place before they are displayed or acted on again** (K-F5 activates when #351 D1 ships; not a launch gate; #351's D1 write is post-launch per head-eng's critical-path plan, 2026-10-23) | **The §5.5 U2 fallback** (head-product P40, 2026-10-24; AC-L3 governs over §5.2 exception 1). To keep this roster inside the bound, the background floor refreshes the viewer's roster **off the tap path**: on session start and app foreground (session-init, 60 s throttle), and as a **non-blocking kick when a tap finds the roster past its bound with the floor healthy** (head-product P41, 2026-10-24). Trades focus is a **post-launch candidate** (launch decision, head-product, 2026-10-25). The tap is served as now and never waits on the kick. If the refresh shows a change, affected cards are withdrawn in place **at the client's next whole-deck response or focus/revalidation**, not instantly, and **I-2 blocks any action on them until then** (head-product, 2026-10-24: option (a)). It **never runs on the search tap's critical path or the first-page serve**, and never on a schedule (platforms-pm R7). **Withhold rule (unchanged):** if the floor has failed and the roster is past its bound at tap, those cards aren't shown, the honest gate-miss state shows while the floor refreshes, and the tap counts as a gate miss |
| **Partner rosters** | Same session-init fetch for Sleeper. `league_members` is also written by the background daemon (`server.py:22801-22835`). Headless builds read whatever is stored (G-075) | **≤ 5 min** | Serve-and-refresh. Filter against the freshest held roster; I-2 catches the rest before any action |
| **Viewer's rankings**: trio swipes, tiers, anchors, reorder, import, outlook and prefs | Every change invalidates jobs (`server.py:10119,10183,10969,11720,11907,12262,12483,20856,21062,21141`), which forces fresh generation | **Zero tolerance:** every change made before the tap is reflected, or the deck is past-bound | Serve-and-refresh with the "updating" state. Never presented as current |
| **Partner boards** (leaguemates' published rankings) | Member epochs fence dependent jobs (`server.py:9283-9294,9381-9384`) | Same as the viewer's rankings | Same |
| **In-app trade state**: passes, likes, awaiting, matched, standing offers | Presentment-rule R4 exclusions are built once at job start (`server.py:7814-7818`). Dispositions are projected at every serve (`:3275-3352`) | **Zero tolerance** (I-3), projected at every display | Filter (already the case) |
| **Platform pending offers** (Sleeper/ESPN/MFL) | **Never read.** Sleeper pending trades are not fetched; the MFL pending route (`server.py:32836`) is not used in generation | n/a in v1 (§7 non-scope). If added, platforms-pm reviews | — |
| **Player market values** (DynastyProcess + KTC blend) | The players-refresh daemon has a 20 h TTL (`server.py:1874`). It is triggered by `POST /api/cron/players-refresh` (`:25009`; no `render.yaml` entry) or the daily-tick fallback at 13:30 UTC (`:24822-24840`), and **that tick has died at the 120 s timeout every day since at least 2026-10-01** (`living-memory/NEXT.md:55-58`). New values neither reprice an existing session nor invalidate jobs (`:22279-22300`) | The deck uses the newest published value snapshot, and that snapshot is **≤ 24 h** old | Serve-and-refresh. If the snapshot is > 48 h old, show the "updating" state and raise an ops alert (ops owns the alert) |
| **League settings**: scoring format, lineup slots, roster limit | Format is fixed at session-init. Slots come from a 15-min Sleeper meta cache (`server.py:29130-29152,30351-30380`) | **≤ 24 h**, and any detected change invalidates | **Block** (§5.2, exception 2) |
| **Model, config, flags and significance policy** | `request_signature` covers league prefs, the whole trade `_cfg` and the flags dict (`server.py:3090-3094`), plus owner model and version checks (`:3489-3526`) | Exact match | **Block** (exception 2) |
| **Deck as a whole** | 30 min in process (`server.py:2285`). Prepared: ≤ 24 h retention, 30 min read-guard age (`backend/prepared_trade_read_guard.py:25`), source age ≤ 300 s at preparation (`backend/prepared_trade_cohort.py:81,132,399`) | No card from a deck built > 24 h ago. Original per-card expiry still applies | Fresh generation (block) |

**Today vs this PRD.** Under the current code, a card can show a player who has moved: a cached deck
outlives a roster change by up to 30 min, and the fresh path never checks current platform rosters
at publication. Owner revalidation uses frozen inputs (`server.py:15234-15253`). Only prepared
inventory checks live rosters at admission (`backend/prepared_trade_runtime.py:546-555`) and hashes
stored rosters at serve (`server.py:3287`; `prepared_trade_read_guard.py:68-90`). So "up to date"
is new work on every serve path, not just a constraint on a faster one.

### 5.2 The rule when a prepared deck is past a bound

**Proposed: serve-and-refresh, with two hard exceptions.** Kept as proposed (trades-pm decision,
2026-10-15). design-lead and ux-lead both support it, with ux-lead F-3, F-4 and F-6 pinned in §5.4.

- **Within every bound:** serve immediately.
- **Past a bound on partner rosters, rankings, values or in-app state:** serve immediately only the cards
  that pass the §5.3 invariants against the freshest facts the system holds. Show a visible "updating"
  state (§5.4) and start a refresh at once. When the refresh lands:
  - cards the user hasn't acted on are replaced or withdrawn;
  - the card on screen is never silently rewritten. If it became invalid it is withdrawn with an
    explanation, and if it is still valid it stays where it is;
  - historical likes and passes keep their original terms (`research-plan.md:70`).
  - **At launch (W-AC-L5):** I-1 runs log-only (`trade_i1_mode` = 1), so withdrawal on display isn't active. I-2 blocks **sends**, with a readable message in the send alert; likes aren't blocked at launch (AC-6b post-launch). In-place withdrawal applies when strict mode lands.
- **Exception 1, ownership:** a card that fails the ownership invariant is never shown, at any
  staleness. Filtering is allowed; "show and fix later" is not. Speed never outranks "never offer
  an asset you no longer own".
  - ~~If the **viewer's** roster is past its bound, it is refetched before any card is displayed.~~
    **Superseded by head-product P40, 2026-10-24 for the viewer's roster:** AC-L3 governs. There is no refetch on
    the search tap or the first-page serve; the §5.5 U2 fallback applies instead.
  - What stays: I-1 and I-2 hold, and the first-page request makes no platform call (AC-L3).
  - **At launch (W-AC-L5):** I-1 runs log-only (`trade_i1_mode` = 1), so withdrawal on display isn't active. I-2 blocks **sends**, with a readable message in the send alert; likes aren't blocked at launch (AC-6b post-launch). In-place withdrawal applies when strict mode lands.
- **Exception 2, wrong math:** if the served model or config version, or the league's scoring or
  roster settings, changed since the deck was built, every card's valuation is wrong. Block: generate
  fresh, show the progress state, and count the tap as a gate miss.
- **Deck-quality filters run at display, too** (models-lead R.b; I-6, AC-9a). A card that passes
  every bound but fails `deck_quality` against today's inputs is not shown. If lineup slots are
  unknown on a fast path, the card falls through to the fresh path.

**Alternatives (not proposed):**

| Rule | Behavior | Why not the default |
|---|---|---|
| Block | Never display a card from a deck past any bound; wait for fresh work | Honest but slow. Every stale tap misses 200 ms, and with a one-worker server the miss is tens of seconds (§6). |
| Serve-with-label | Display a past-bound deck with an "as of" label; refresh only when the user asks | Fast, but it pushes the freshness job onto the user, and the label alone doesn't stop invalid cards unless the §5.3 filters still run. |

### 5.3 Hard invariants (never relaxed, at any staleness)

- **I-1 Ownership.** No card is displayed with an asset the stated side no longer owns, per the
  freshest roster the system holds at display time. For the viewer's own roster, that roster is
  never older than the §5.1 bound.
  - **The display invariant is waived at launch (W-AC-L5); strict mode follows post-launch.** The
    ownership filter (S0, #367) runs **log-only** (`trade_i1_mode` = 1), so a card with a moved
    asset can be shown. **At launch I-2 covers sends only**, with a readable message in the send
    alert; likes (AC-6b) and the on-card message follow after launch (head-product, 2026-10-26; decision
    record: W-AC-L5 in Decisions).
- **I-2 Action-time revalidation**, split by action (platforms-pm R2).

  **Today this guard is incomplete.**
  - Sleeper `/api/trades/propose` reads live rosters only to resolve roster ids. It validates picks
    live (422 `sleeper_pick_not_owned`, `backend/server.py:19529-19590`) but does **not** check
    player ownership; it relies on Sleeper rejecting the write (502 `sleeper_write_failed`,
    `:19613`).
  - ESPN's pre-flight resolves teams and slots without an explicit player check (`:33126-33184`).
  - MFL only maps ids (`:32608-32617`).
  - A like that creates a match has no check at all.

  The requirement:
  - **Sends** (they write to a platform). The check runs against the **live** platform roster, and
    it is mandatory. It covers:
    - the deck, match and awaiting cards and the calculator: every send surface mounts
      `SendInSleeperButton`, which routes all three platforms. That means `TradesScreen`,
      `TradeCard` and `InLeagueCalculator` (platforms-pm N4; trades-pm decision 7);
    - **team-overhaul sends.** They go to Sleeper, MFL and ESPN (players only), behind
      `overhaul.enabled` plus each send flag (`overhaul_service.py:50-60`; #290 revised D-188).
      Overhaul checks ownership when the package is prepared; I-2 applies when the send goes out
      (platforms-pm R8).
  - **Platform cost (platforms-pm R1).** It is lower than it first looks.
    - Sleeper's send already fetches live rosters (`server.py:19529`, `_fetch_league_rosters`).
    - ESPN's send already fetches the live league with `view=mRoster` (`server.py:33133`;
      `espn_service.py:94`).
    - So for those two, the player check compares against data already in hand: no new platform
      call, and no change in rate exposure.
    - Only MFL adds one rosters export per send (`mfl_service.fetch_rosters`,
      `mfl_service.py:432`). MFL client registration (`NEXT.md` "Complete MFL client registration")
      is a dependency, not a blocker.
  - **Scope of the check (platforms-pm R5).**
    - It works at roster level, using the roster id from `_roster_id_for_owner`, not the viewer's
      user id, so co-owners pass (D-051).
    - MFL also checks picks, from `futureDraftPicks` in the same export.
    - ESPN picks stay hard-blocked (`espn_pick_unsupported`).
    - Sleeper picks are already checked live.
  - **Read failure (platforms-pm R3).** If the roster read fails, the send is blocked with
    "couldn't confirm rosters with <platform>, try again", and it is **never sent unchecked**.
    - Failure modes to cover: Sleeper Cloudflare 1010s (`f5357445`), ESPN fragility
      (`docs/runbook.md` L747), MFL `wwwNN` hosts (L758).
    - platforms-eng confirms what each path does today when its fetch fails.
  - **One refusal contract (platforms-pm R4).** Reuse team overhaul's codes `asset_not_owned` and
    `counterparty_asset_not_owned` and their copy, "You no longer own X" and "X no longer owns Y"
    (`overhaul_service.py:44-45,637,655`).
    - Name the moved asset or assets, with `detail` equal to `message`. Fielded builds render
      `detail` in their catch-all.
    - Sleeper reports the block through `sleeper_send_failed.error_code` (§4.6).
  - **A like that would create a match** (it writes nothing to a platform). **At launch
    (head-product, 2026-10-26) likes aren't blocked:** a like on a stale card can still record and create a
    match, and the send is blocked at the core. The rest of this bullet applies post-launch
    (AC-6b). Check it against the
    freshest roster held, within the §5.1 viewer and partner bounds, and refetch if past the bound.
    No live platform read per like: ESPN and MFL would need the viewer's credentials for every like
    (platforms-pm R2).

  **When the asset has moved** (trades-pm decision, 2026-10-15, on ux-lead F-7):
  - **Like (post-launch, AC-6b; head-product, 2026-10-26):** the like is **not** recorded and no match is
    created. At launch it records.
    - The card is withdrawn in place (§5.4, the withdrawn card), with the reason.
    - Its disposition is set so it isn't re-served (I-3).
    - D-170's "the ✓ always records the like" is scoped to the calculator queue, which is unchanged.
  - **Send:** blocked with the platforms-pm R4 refusal contract and copy, **on the card**, with a next step. **At launch (head-product, 2026-10-26):** the server returns 422 `asset_not_owned` / `counterparty_asset_not_owned` with a readable `detail`, which the 1.22.0 send buttons show in an **alert** through their catch-all branch (platforms-eng audit, `docs/plans/org-bringup/reports/platforms-eng.md` § "I-2 status"). The on-card placement follows after launch. It never
    reports success, never leaves the controls dead, and never silently loses the user's choice
    (ux-lead F-7).
  - **Dependency:** `NEXT.md` 0f (the Sleeper propose route's `isdigit()` gate, the G-030 trap) lands
    before or with I-2, so an MFL league can never reach the Sleeper write path (platforms-pm N1).
- **I-3 Dispositions.** Cards the user passed, already liked or has awaiting or matched are excluded
  at read time. The prepared-inventory design already projects these at adoption
  (`prepared-trade-inventory/plan.md:47`).
- **I-4 No silent rewrite.** A displayed offer's terms never change under the same identity
  (`delivery.md:81`).
- **I-5 Model identity.** A card is served only under the model, config and significance version
  that built it (existing guard; `release-20260921/README.md:10`).
- **I-6 Quality at display** (models-lead R.b; AC-9a). Every displayed card, on any serve path, has
  passed `deck_quality`'s rules (D-207) **evaluated against the freshest inputs held at display**:
  rosters within the §5.1 bounds, the value snapshot in use, and lineup slots.
  - Breakup and redundant TE/QB depend on rosters, and filler and repeats on values, so a card
    prepared earlier can fail by tap time.
  - **An unknown lineup on a fast path is never a silent skip.** Today `deck_quality.py` skips the
    redundant rule when the lineup is unknown. On a fast path that card falls through to the fresh
    path instead.
  - **Critical-path risk:** the lineup-slot lookup can make a live Sleeper `GET /league/<id>` of up
    to 10 s on a meta-cache miss (`server.py:29130-29152`). Under platforms-pm R7 it stays
    user-triggered, never scheduled or headless. Under AC-L3 it also moves **off the tap path**,
    into the background freshness floor (§5.5 U4).

### 5.4 How the user sees freshness (requirements; visual spec by design-lead, flow by ux-lead)

**The default is quiet.** No freshness UI appears when every input is within bounds, and nothing is
reserved for it (design-lead 2).

**The "updating" state** shows when any displayed card comes from a deck past a §5.1 bound,
including on focus regain (ux-lead F-2). Shared constraints (trades-pm decision, 2026-10-15,
reconciling design-lead 2 and ux-lead F-3):
1. **No layout shift.** It never pushes the fronted card; a row inserted mid-gesture moves the swipe
   target.
2. **State, not an interrupt.** No toast, modal, banner or `useInterruptSlot` claim, and the tour
   hold doesn't mute it (ux-lead F-3).
3. **Its own copy**, naming what is being checked (roster, rankings, values) from values the app
   holds. It is never "Searching…", and it makes no timing promise (ux-lead F-3).
4. **A maximum duration.** When it is reached, the refresh-failed state shows (ux-lead F-3). The
   build sets the number.
5. **Card controls stay enabled** while it shows; actions are governed by I-2 (ux-lead F-3).
6. **No highlight accent and no new color** (design-lead 1, corrected wording; the earlier "flare"
   line is withdrawn). The state uses chalk-dim text and the standard Spinner, whose ice arc is the
   specced progress accent (`components.md` Spinner) and counts toward the ice ration of about 3.
   The withdrawn and failed lines are chalk-dim text.
7. **Built from existing parts:** the Spinner (16–20 px) plus `body-sm` chalk-dim text
   (design-lead 3).

The **exact slot** is open as **Decision D11**: design-lead proposes a trailing label in the deck's
header row, and ux-lead proposes the progress-strip slot. Both are settled jointly before any UI
build.

**At launch (W-AC-L5),** withdrawal triggered by I-1 at display isn't active, because the filter
is log-only. The spec below applies when strict mode lands. The withdrawal that follows an
**I-2-blocked like** (§5.3) is action-time and **also post-launch**, since likes aren't blocked at launch
(head-product, 2026-10-26).

**The withdrawn fronted card** (trades-pm decision, 2026-10-15: ux-lead F-4's structure with
design-lead 4's treatment; design-lead owns the visual spec):
- It keeps its slot and its terms, visible but dimmed. It is never silently removed.
- Like/Pass are replaced by one `body-sm` chalk-dim reason line ("<player> is no longer on <team>")
  plus a **"Next trade"** action.
- A chalk-dim Chalkline `x` or `swap` icon. No `--neg` red and no `--warn` amber: a withdrawn card is
  neither an error nor a warning. Content text stays at 4.5:1 or better, never chalk-faint.
- The change applies only **after any in-progress swipe settles**. The next card never slides in
  until the user acts.
- If a guide step is spotlighting that card (`mobile/tests/check-guide-spotlight-tracking.js`),
  onboarding-pm says how the guide continues (ux-lead F-4).
- The same withdrawal applies to a like blocked under I-2 (trades-pm decision 3, §5.3). That is post-launch: likes aren't blocked at launch (head-product, 2026-10-26).

**Refresh failed** (design-lead 3 and 5):
- It says the deck may be out of date and offers Retry. It reuses the Banner construction (ink-2,
  hairline, `body-sm`), inline in the deck, **non-dismissable**, with a Secondary "Retry" button.
  Retry is not ice, because the deck's primary actions stay primary.
- It follows the Error row of the Screen-states standard (`components.md` § Screen states, being
  written on `docs/design-screen-states`). The precedent is the stale and failed states of
  Season projections (`components.md:185`).

**Offline** (ux-lead F-6; Offline row of the Screen-states standard, design-lead 5):
- **Inside the bounds:** cards may show, and the refresh-failed state shows at once. A
  match-creating like or a send fails visibly and keeps the user's choice (precedent
  `mobile/tests/check-swipe-failure-recovery.js`).
- **Past the viewer's roster bound:** the offline state, with no cards.

**Gate-miss wait** (exceptions 1 and 2, cold work; ux-lead F-5, design-lead D10). U5's "Building your
first trades" card is the only permitted wait card on the Find a trade path, and no "Finding more"
card exists (§4.7):
- It names its real reason, e.g. "checking your roster with Sleeper" or "your league settings
  changed", and makes no timing promise. Today's placeholder, "First few should land within a few
  seconds" (`TradesScreen.tsx:8868-8871`), is false against a 61 s median and is replaced.
- It uses the static Loading treatment from § Screen states (no shimmer).
- Loading must end. On timeout it shows the error with Retry and keeps Back usable (#420 precedent,
  `mobile/tests/check-win-now-recovery.js`).

**Blocked actions** (ux-lead F-7, platforms-pm N3): shown on the card. The message names the asset
and the platform, says nothing was sent, and offers a refresh, using the I-2 refusal contract.

**Motion** (design-lead 6): no shimmer, and no animated swap of the fronted card when a refresh
lands. Unacted cards behind it update off-screen. Under reduced motion the Spinner becomes the
static text "Updating".

**Accessibility** (design-lead 7 → ux-lead): the state change is announced to VoiceOver through a
polite live region. ux-lead's launch spec sets the rules (§4.7, VoiceOver).

**Copy:** all of these lines go to marketing-lead (design-lead 5). design-lead owes the
`components.md` "status line" row (updating and failed) plus the withdrawn-card body once the PRD
is accepted (design-lead 3).

### 5.5 What the user experiences: U2 and U4 (head-product launch-readiness, 2026-10-20)

- **U2. Fresh at tap time.**
  - The pre-built page is refreshed in the background (eng's Step 0 freshness floor, §10.7), so it
    is within the §5.1 bounds when the user taps.
  - The hard rule holds (I-1, I-2): a card is never shown whose assets either side no longer owns.
    If a background check invalidates a visible card, it is **withdrawn in place** (§5.4).
    - **At launch (W-AC-L5):** I-1 runs log-only (`trade_i1_mode` = 1), so withdrawal on display isn't active. I-2 blocks **sends**, with a readable message in the send alert; likes aren't blocked at launch (AC-6b post-launch). In-place withdrawal applies when strict mode lands.
  - The quiet "Updating" state appears only while a background refresh runs, and never blocks
    Like/Pass (§5.4).
  - **A roster move FTF completes** (the #351 add/drop; **K-F5 activates when #351 D1 ships; not a launch gate**, because #351's
    D1 write is post-launch per head-eng's critical-path plan, 2026-10-23) immediately triggers the
    viewer-roster refresh, and cards with the dropped player are withdrawn in place before they are displayed or
    acted on again (platforms-pm K-F5 on #351; AC-L5). Today the deck still shows the dropped
    player after the move.
  - **With AC-L3, the tap path makes no platform call.** The §5.1 roster bounds are met by the
    background freshness floor, refreshed on user action off the tap path (consistent with
    platforms-pm R7). **Its launch triggers** (launch decision, head-product, 2026-10-25):
    - session start;
    - app foreground (session-init, 60 s throttle);
    - **a tap past bound, as a non-blocking kick** (head-product P41, 2026-10-24).

    ~~Trades focus~~ is a **post-launch candidate**, revisitable from R2b data. It would add Sleeper
    calls (429 risk) and a mobile change before the freeze, for little gain. I-2 still blocks any
    stale send.
  - **Built:** the floor is S0. It reuses session init on app open and foreground, with a 60 s
    throttle, and adds the P41 kick through `roster_refresh.maybe_refresh_async`
    (`scope-eng-s0-fetch.md:61-108`; #378, with a Sleeper 429 circuit). These are exactly the launch
    triggers above (§15 item 10, aligned).
  - **The kick:** when a tap finds the viewer's roster past its bound and the floor hasn't failed,
    the tap is **served as now** and a background floor refresh is **enqueued off the critical
    path; the tap never awaits it**. If the refresh shows a roster change, affected cards are
    withdrawn in place (§5.4) **at the client's next whole-deck response or focus/revalidation,
    not instantly**, and the next page is built from the fresh roster.
    - **At launch (W-AC-L5),** the kick still refreshes the roster, but its withdrawal effect
      waits for strict mode: with I-1 log-only, the affected card isn't withdrawn and I-2 blocks
      actions on it.
    - **Until the withdrawal lands,** the fronted card stays visible, but **I-2 blocks any action
      on it** (like, match, send). That is the same as a partner's roster move today. **At launch
      (head-product, 2026-10-26) that means sends only, via the send alert; likes aren't blocked.**
    - **Why option (a)** (head-product, 2026-10-24, picking head-eng's option): Pass A withdraws
      held cards only on whole-deck responses (`mobile/src/utils/tradePages.ts:52-59` (`isWholeDeck`) and `:87-111` (`mergeDeckPage`), on `feat/trades-200ms-mobile` @ `e01c7831`). The client asks only at the
      prefetch threshold or on focus/revalidation. There is **no client change and no API change
      for launch**.
    - **Option (b)**, a `roster_refreshing` response field plus one `/status` poll, is a
      **first-update candidate** (post-launch).
    - **Dependency:** platforms-eng's `maybe_refresh_async` hook (about 2026-11-01).
    - This closes head-eng's Q1 gap (2026-10-24): a user sitting on Trades with no foreground or
      focus event would otherwise get cards checked against a roster that keeps aging.
  - **Fallback, the withhold rule (head-product P40, 2026-10-24; unchanged by P41; AC-L3 governs over
    §5.2 exception 1):** if the floor has failed and the
    viewer's roster is past its bound at tap, cards from that page are not shown. The honest
    gate-miss state shows while the floor's refresh completes, and the tap counts as a gate miss.
    The first-page request itself still makes no platform call.
- **U4. The same quality as today.** Every first-page card passes `deck.quality_filters` at display
  time (I-6, AC-9a to AC-9e, AC-L6). Speed never comes from showing worse trades.
  - Lineup slots join the background floor, so I-6's lineup lookup is off the tap path too.

## 6. Today's baseline: measured (analytics-lead W3 read, 2026-10-20)

**Source:** analytics-lead, "W3 results: behavior baselines" → "#339 speed baseline" (`docs/plans/org-bringup/reports/analytics-lead.md:342-379`).
- **The read:** prod Postgres, read-only (`default_transaction_read_only=on`, 30 s timeout), run
  2026-10-20 06:19–06:37 UTC and spot-checked at 06:38 UTC.
- **Window:** [2026-10-06, 2026-10-20) UTC, split at the filter ship (2026-10-15 01:18Z).
- **Exclusions:** `device:`, `demo_`, `test_user_fp_`, `qa_`, `user_me`, `entry:`, `system:` and
  demo sessions.
- **N is tiny:** 3 tapping users and 8–9 actives. Every tap ↔ job join is heuristic, because no row
  carries a request or job id.

It answers `baseline-request.md` Q0–Q7 and Q9. Q8 (storage) is still with the storage worker.

| Query | Result (n) |
|---|---|
| **Q1 Tap → first card** (client proxy, iOS) | 3 users, 12 sessions, 23 taps, of which **10 reached a card**. **p50 5,249 ms, p90 35,936 ms, max 44,411 ms. 0 of 10 ≤ 250 ms** (so none ≤ 200 ms); 4 of 10 ≤ 1 s. **Organic: 9 taps**, in two clusters (4 of 8 ≤ 1 s, 4 of 8 > 10 s). `cold_launch` p50 827 ms (n = 7). p95 is "—" in every cell (n < 40) |
| **Q2 `trades_generated.gen_ms`** | **Pull:** p50 91.0 s and p95 135.7 s before the filter ship (n = 45); p50 33.0 s after (n = 6). **Replenish:** p50 67.2 s before (n = 56); p50 34.8 s after (n = 29). `count` p50 fell from 2,399 to 184 |
| **Q3 `bakeoff_runs.total_ms`** | p50 17.2 s before, 14.9 s after. Every row is arm `owner_v2_bilateral` |
| **Q0 Config** | `prepared_trade_inventory_enabled` = 0, so the prepared path is **off**. Flags couldn't be read live: they come from `config/features.json` plus the `FTF_FLAGS` env, with no DB source |
| **Q6 Stale-roster exposure (G-075)** | 15 of 151 member rows are stale across 12 leagues; 1 league is fully stale |
| **Q7 Volume** | **About 1.6 searches a day** in total |
| **Q9 API** | `/api/trades/generate` 2xx p50 55 ms; `/api/session/init` p50 358 ms |
| Q8 Storage | Pending (storage worker) |

**Finding, flagged rather than diagnosed:** **10 taps had no source, and 9 of them got no card.**
That is an instrumentation or flow gap. It goes to analytics-lead and trades-eng (Handoffs).

**What it means:**
- Today's real tap-to-card time is two to three orders of magnitude above 200 ms.
- At about 1.6 organic searches a day, reaching n ≥ 40 in each of the four AC-L1 cells would take
  about 100 days. The AC-L1 proof is therefore a scripted two-device session (§9.6). Organic
  telemetry continues after launch as monitoring, not as the gate.

### 6.1 History: provisional numbers from repo docs (2026-10-15, kept as written)

These were collected before the W3 read and are kept unchanged.

| # | Boundary measured | Value | Percentile / n | Date | Method | Source |
|---|---|---|---|---|---|---|
| B1 | **Phone tap → first actionable card** | **never measured** | — | — | — | No device timing exists. The 3 s goal's device checklists are all unrun (`trade-search-latency/execution-20260921/README.md:46`; `release-20260921/implementation-validation-delivery.md:42-44`) |
| B2 | Prod interactive worker (`trades_generated.props.gen_ms`, full worker) | 18.14–75.44 s | median **43.06 s**, n=18 completions | 2026-09-12→19 | read-only Render logs + Postgres | `trade-search-latency/README.md:13` |
| B3 | Prod background replenishment worker | 10.01–29.09 s | median 17.44 s, n=25 | 2026-09-12→19 | same | `trade-search-latency/README.md:13` |
| B4 | Prod single job timeline: engine 9.526 s; 1,933 cards stored with 3,348,178 inline feature bytes; client polling an empty snapshot until storage finished | worker 47.99 s | n=1 | 2026-09-19 | Render log timestamps | `trade-search-latency/README.md:15-24` |
| B5 | Prod worker vs engine (`bakeoff_runs.total_ms`), bilateral owner | worker 39.742–75.248 s; engine 10.321–25.255 s | medians **61.094 s** / **13.323 s**, n=7 (completions only, timestamp-matched) | 2026-09-20/21 | read-only Render API + Postgres | `trade-search-latency/execution-20260921/infrastructure-and-precompute.md:13-23` |
| B6 | Prod tap → first large response (attributed): session-init began the job 17:34:21, Find a trade joined 17:34:25, first large response 17:35:31; ≈4 s from worker completion to the next poll response; ≈3.2 MB response | ≈66 s after the tap | n=1, attributed, not re-verified | 2026-09-20 | log inspection by a sibling plan | `trade-search-latency/research-plan.md:43-45` |
| B7 | Local reconstructed full worker; median stages: construction 5.910 s, revalidation 2.144 s, evidence/publication 3.858 s | 13.015–13.200 s | n=3 | 2026-09-21 | local Python 3.14 / SQLite replay | `execution-20260921/README.md:15-17` |
| B8 | Local first durable inventory, before → after #303 | 12.974 → **8.754 s** (worker 12.983 → 11.333 s) | medians, n=3 each | 2026-09-21 | local replay, 2,354 offers | `release-20260921/README.md:18-21` |
| B9 | Local bilateral revision, first durable 30 | 8.69 → 18.66 s (later 15.127 s vs 8.425 s incumbent) | single runs | 2026-09-22 | local replay | `living-memory/TEST_LEDGER.md:323,360` |
| B10 | Local **prepared inventory** first 30 durable (backend only, telemetry on) | **1.081 s** (full adoption 22.15 s) | single run, 936 offers | 2026-09-23 | local SQLite, synthetic 3-team | `prepared-trade-inventory/release.md:161-165` |
| B11 | Local prepared inventory first 30 durable, dense | 3.855 s (13,728 offers); later 2.502 s published; 936-offer active-switch repeats 1.175–3.282 s | single runs | 2026-09-23 | local SQLite | `prepared-trade-inventory/release.md:164-165`; `living-memory/HANDOFF.md:43` |
| B12 | Local prepared 64 / 512 offers, first 30 durable | 0.493 / 3.034 s (full 0.730 / 8.518 s) | single runs | 2026-09-22 | local SQLite, mocked receipts | `prepared-trade-inventory/release.md:78-79` |
| B13 | Value core `pipeline.run` (flag off in prod) | p50 1.54 s, **p95 1.77 s** | n=10, 14-team fixture | 2026-09-30 | local | `living-memory/TEST_LEDGER.md:213` |
| B14 | Client poll schedule (code, not a measurement): first poll 800 ms, ×1.5 to 4,000 ms, ±10% jitter; simulated detection delay median/p95/max 1,990 / 3,790 / 3,990 ms | — | 6,001 simulated phases | 2026-09-21 | deterministic simulation | `mobile/src/screens/TradesScreen.tsx:2173,2203,2207-2208`; `delivery.md:41-53` |
| B15 | Response size: full 2,354-card deck 3,218,422 B (259,015 B gzip); first 30 cards 37,348 B (4,075 B gzip) | — | n=1 reconstructed | 2026-09-21 | local export | `delivery.md:102-107` |
| B16 | Historical local generate (pre-uncapped deck): 31 cards in 1.28 s; warm GET p50/p95 20 / 58 ms | — | local charter test | 2026-06-11 | local | `living-memory/TEST_LEDGER.md:4668` |

Production prepared-inventory adoption has **no** measurement: rollout was 0 at the last readback
(`prepared-trade-inventory/release.md:154`).

**What the provisional numbers said (2026-10-15).** First, no phone had been timed; the W3 read
above is now the first client-proxy measurement. Second, the best server-side first-card boundary measured anywhere is
1.081 s (prepared, local, backend only), which is 5.4× the whole 200 ms budget before any network or
render time. Third, the current client poll schedule alone (first poll at 800 ms) is 4× the budget.
Fourth, the production worker (61 s median) is about 305× over.

## 7. Scope and non-scope

**In scope:**
- iOS (TestFlight) app: every table A control (gated) and every table B control (measured), §4.1;
- the metric and its instrumentation (§4);
- the freshness bounds, rule and invariants (§5);
- the freshness UI requirement (§5.4);
- the serve path for the default organic deck;
- measurement of pinned and targeted searches.

**Non-scope (v1):**

| Out | Reason |
|---|---|
| Web (`web/`) and the browser extension | TestFlight is the shipped surface. Web Find a trade is measured later if the operator asks. |
| TodaysTrade / Browse-all (`trades.presentation_v2`) | Flag is false. If it flips, its entry joins §4.1. |
| Calibration tab decks | Blind-grading sessions are a separate surface (`docs/architecture.md:354-433`). Their *current* arm reads served `deck_impressions` (`architecture.md:406-412`), so changes to what gets served still need models-lead sign-off (§11). |
| Engine-quality changes (scoring, budgets, arms) | No candidate-pool, budget or card-count reduction counts as a latency fix (`research-plan.md:66`). Any change to order or composition is a model change needing models-lead sign-off. |
| Platform pending-offer reads (Sleeper/ESPN/MFL) | Not read today; the cross-platform pending inbox is **not built** (`docs/plans/README.md:110`). If eng proposes adding these reads for freshness, they go to platforms-pm's platform risk register first (platforms-pm N2). |
| Infrastructure purchases | Under the $200/month ceiling (`docs/plans/README.md:59`). Any paid change is a separate operator decision. |

## 8. Acceptance criteria

Each is pass/fail by a guard (G), a unit or integration test (T), an analytics read (A) or a
TestFlight checklist step (TF, §9.4).

### 8.1 Launch criteria (head-product launch-readiness, 2026-10-20)

Source: `docs/plans/org-bringup/launch-readiness-product.md` § "200 ms by launch". These are launch
MUSTs. Each row says how it relates to the existing criteria in §8.2, so nothing is counted twice.

| ID | Criterion | Check | Relation to §8.2 |
|---|---|---|---|
| AC-L1 | **p95 ≤ 200 ms** from the tap on a search-starting control (table A, plus table B if D10 ships) to the first frame where a real card is ≥ 50% visible with Like and Pass enabled (the §4.2 clock). Measured by client telemetry on a TestFlight build. Cells: Wi-Fi and cellular × first tap and repeat tap. n ≥ 40 per cell, from at least 2 devices including the operator's. **A device-held first card counts** if it meets U2: within the freshness bounds, passing I-2, and withdrawn in place if invalidated (head-product P32). **Measurement terms (analytics-lead, launch, T1–T6):** <br>**T1:** R2 fires at exactly this frame. <br>**T2:** p95 is taken over R2 ∪ R2b, one per `search_id`, and every R2b (timeout, error, empty, abandoned) counts as above 200 ms. <br>**T3:** `cold_launch` is its own row and is not joined to first tap; AC-L7 reads `cold_launch` for accounts created that day. <br>**T4:** if the app leaves `active` between tap and card, the search ends as R2b `abandoned`, never a long R2. <br>**T5:** the AC-L1 query runs **with tester devices included** (the default `device_exclusion` would strip them and return n ≈ 0). <br>**T6:** nearest-rank p95 (the 38th-fastest at n = 40) with a 90% order-statistic CI. A point p95 ≤ 200 ms whose CI upper end is > 200 ms reads "pass, not robust", so collect more before calling it. <br>**T7** (events contract): `entry_point=prefs_changed_strip` and `team_review` are excluded from the cells and reported separately. <br>`network_type` `offline` and `unknown` stay out of the cells. Distinct `device_id` per cell proves ≥ 2 devices | **The proof is the scripted two-device session in §9.6** (organic volume is too low; §6). A: R1, R2 and R2b with the `network_type` prop, read by analytics-lead under T1–T6. Cross-check: the §9.5 readout per tap. Organic telemetry after launch is monitoring, not the gate | **Supersedes AC-3's threshold and cells** |
| AC-L2 | No animated push or transition on the Find a trade path (U1), decided per entry point (ux-lead, launch; §4.7): an instant route (`animation: 'none'`) for the canvas, D10, hand-off and deep-link entries, and in place for in-deck searches. Back from the deck is instant too. No motion on the deck at all, including no on-load stagger (design-lead's deck exemption) | Code-walk plus a guard (`check-trade-first-card.js`: `animation: 'none'` on every search-starting route, no transition on the in-place reveal, no stagger on the deck). TF step 1: zero transition frames | **Supersedes AC-2b.** Its "short fade" option is withdrawn |
| AC-L3 | No live Sleeper or platform call on the tap path. The background floor's launch triggers are session start, app foreground (session-init, 60 s throttle) and **a tap past bound as a non-blocking kick** (head-product P41, 2026-10-24). Trades focus is a post-launch candidate (head-product, 2026-10-25): enqueued off the critical path and never awaited, so the tap's critical path still makes no platform call. **At launch (W-AC-L5)** the kick's withdrawal effect waits for strict mode; I-2 blocks sends (via the send alert), and likes aren't blocked at launch | Code-walk, plus the server trace for the first-page request (the kick's refresh appears as a separate, later background call, never inside the first-page request), plus the §9.2 kick test | **New.** It strengthens platforms-pm R7. AC-L3 governs over §5.2 exception 1 (head-product P40, 2026-10-24): the §5.5 U2 fallback applies to the viewer's roster, and I-6's lineup lookup moves to the background floor |
| AC-L4 | The next page is always ready: across all test sessions, **zero** page ends are reached without the next page already in the deck. There is no "Finding more" card in the build. The prefetch threshold is in §4.7. ux-lead's state table (§4.7) defines the outcomes: an online fetch failure at a page end (row 3b) **fails** AC-L4; offline at a page end (row 3a) is reported separately and doesn't. The P30 end card shows only when every candidate is seen and **never while a page is pending**, with no Like or Pass | G: no "Finding more" component or copy on the Find a trade path; the page N+2 request starts when page N is fronted; the P30 card never renders while a page is pending, and renders no Like/Pass. A: `deck_buffer_empty` (events contract; any occurrence is a miss). TF: the U3 three-page run and the P30 step | **New; supersedes AC-13** (strengthened) |
| AC-L5 | **Waiver W-AC-L5 (operator, 2026-10-26).** The **display half (I-1 at display) is waived at launch:** the ownership filter runs log-only (`trade_i1_mode` = 1), so a card with a moved asset can be shown. **The action half (I-2) holds:** **sends** on a moved asset are blocked at action time, with a readable message in the send alert. Likes (AC-6b) and the on-card message (AC-6a placement) follow after launch. **The full AC returns when strict mode ships.** Full criterion: zero cards shown with an asset either side no longer owns (I-1 at display, I-2 at action). **Including after a roster move FTF itself completes** (the #351 add/drop, K-F5): the viewer-roster refresh runs immediately, and affected cards are withdrawn in place before they are displayed or acted on again | T: the roster-change fixture, plus a **backend fixture where an FTF add/drop completes and the card with the dropped player is withdrawn** (K-F5 parts activates when #351 D1 ships; not a launch gate). TF: the U2 roster-change run (steps 11, 12 and 18) and the K-F5 step (L4b, activates when #351 D1 ships; not a launch gate) | **Same as AC-5** for display; AC-6a/6b cover actions. The K-F5 fixture is new |
| AC-L6 | Quality parity: first-page cards pass `deck.quality_filters`; Calibration integrity holds per D12 | As AC-9a to AC-9e | **Same as AC-9a to AC-9e and D12.** No new test |
| AC-L7 | A new account's first Find a trade after onboarding meets AC-L1 (U5) | A: a new-account first-tap cell. TF: the U5 fresh-account run | **New.** D2 decided in part |
| AC-L8 | Storage: the first-page artifact and evidence writes fit the P23 byte budget and the DB capacity plan. Unseen candidates follow DEC-2 as ADR-025: packed evidence, with narrow rows only as the fallback (operator-approved 2026-10-20) | As AC-11 and AC-11b, plus Q8 table sizes before and after | **Same as AC-11 and AC-11b (P23), plus DEC-2 as ADR-025** (packed evidence; budget in `scope-eng-200ms.md` §7) |

### 8.2 Criteria from the PRD and its reviews

| ID | Criterion | Check |
|---|---|---|
| AC-1 | Every table A control in §4.1, and every table B control if D10 makes them search-starting, emits the widened R1 tap record with a `search_id`. Exactly one of R2 or R2b fires per `search_id` (analytics-lead R2). The deep-link and inbox arrivals (§4.1, ux-lead F-8) emit too, and are measured, not gated. | G: `mobile/tests/check-trade-first-card.js` enumerates the controls and arrivals and fails if any `onPress` or arrival path lacks the emit. T: a per-feature test asserts the exact prop rows (`==`), INTENT/NON_INTENT classification, and the one-of-R2/R2b invariant (analytics-lead R1, R2). TF step 9 |
| AC-1b | **One `trades_generated` per user-visible deck** (analytics-lead R3, binding). Every deck the user sees emits exactly one `trades_generated`, whatever its `serve_source` (the contract's `page`, `cached`, `joined`, `fresh` or `prepared`), so funnel stage 6 and the PFO guardrail don't undercount. Alternatively, an `/an-funnel` stage-6 amendment lands before the build. `deck_source` keeps its meaning, and `serve_source` is a separate prop. | T: a backend test per serve path asserting exactly one event per deck with `props.count` set, or the merged stage-6 amendment |
| AC-2 | `ms_from_tap` uses a monotonic clock and ends on the §4.2 definition: controls enabled and card visible. It does not end on `deck_card_viewed`, a skeleton or server readiness. | G: the same check asserts the emitter sits on the card's enabled-and-visible path and not in the skeleton branch. Code-walk proof (§9.3). |
| AC-2b | **Superseded by AC-L2** (2026-10-20); the "short fade" option is withdrawn. Original text: **The push can't spend the budget** (ux-lead F-1). Search-starting pushes keep `push` and the back stack (D-171), but run with no animation or with a short fade that design-lead specs. | Code-walk names the animation option on every search-starting push. TF step 1 counts tap → transition-end frames separately from tap → card; ux-lead's target is ≤ 6 frames (≈ 100 ms) |
| AC-3 | **Superseded by AC-L1** (2026-10-20): p95 ≤ 200 ms, Wi-Fi and cellular × first and repeat tap, n ≥ 40 per cell from at least 2 devices including the operator's. The earlier 250 ms threshold is withdrawn. | See AC-L1. |
| AC-4 | Cold-launch, pinned/targeted and fair-sweep cells are reported with the same percentiles. They are gated only per Decisions D1/D2. | A. |
| AC-5 | **Display half waived at launch (W-AC-L5; strict post-launch).** I-1: no displayed card contains an asset its stated side doesn't own per the freshest roster held. A roster change between prepare and display, or before a deck regains focus, withdraws or filters the card before display. | T: backend test on every serve path (fresh, cached, joined, prepared) that mutates a roster after build and asserts the card is absent. TF steps 11, 12 and 18. |
| AC-6a | **Sends** (platforms-pm R1–R5, R8). **At launch (head-product, 2026-10-26):** sends on a moved asset are blocked at action time, with a readable message in the **send alert** (the 1.22.0 buttons' catch-all shows the server's 422 `detail`). The on-card placement follows after launch. I-2 isn't live today; platforms-eng is adding the live player-ownership check to the Sleeper, ESPN and MFL propose cores plus overhaul and the calculator queue, server-only, target about 2026-10-31 (`docs/plans/org-bringup/reports/platforms-eng.md` § "I-2 status"). Every send on every surface (deck, match/awaiting card, calculator, team overhaul), to Sleeper, ESPN or MFL, checks ownership against the **live** platform roster at roster level (co-owners pass). MFL also checks picks; ESPN picks stay hard-blocked. A moved asset is refused with `asset_not_owned` / `counterparty_asset_not_owned` and their copy (`detail` = `message`), on the card. A failed roster read blocks the send, which is never sent unchecked. | T: backend route tests per platform with moved-asset fixtures and with read-failure fixtures (Sleeper 1010, ESPN fetch failure, MFL host), plus a file:line code-walk per path (platforms-pm evidence plan). TF step 13, in an operator-named test league only |
| AC-6b | **Likes — post-launch (head-product, 2026-10-26).** At launch a like on a stale card can still record and create a match; the send is blocked at the core (AC-6a). The criterion below applies after launch. (platforms-pm R2; trades-pm decision 3.) A like that would create a match on a card whose asset has moved, per the freshest roster held within the §5.1 bounds (refetched if past the bound), records **no like and no match**. The card is withdrawn in place with the reason (§5.4), and its disposition is set so it isn't re-served. The calculator queue (D-170) is unchanged. | T: route tests asserting no `trade_decisions` like row, no match, a withdrawal payload and the disposition set; a regression test that the calculator queue still records. TF step 13 |
| AC-7 | §5.1 bounds are enforced, at display and when a deck regains focus (ux-lead F-2). For each input, a deck past its bound triggers the §5.2 behavior: serve-and-refresh, block (exception 2), or, for the viewer's roster, **the §5.5 U2 fallback** (head-product P40, 2026-10-24). Under that fallback, if the floor has failed and the roster is past its bound at tap, those cards aren't shown, the honest gate-miss state shows while the floor refreshes, and the tap counts as a gate miss. **That is distinct from a healthy floor past bound,** where the tap is served and a non-blocking kick refreshes the roster (P41). Cards the kick invalidates are withdrawn at the next whole-deck response or focus/revalidation, and I-2 blocks actions on them until then (option (a); at launch, sends only, via the send alert). A deck within bounds serves with no freshness UI. Roster refetches happen only on user action; nothing is scheduled or headless for Sleeper (platforms-pm R7). | T: one test per input row, the §9.2 kick test (withdrawal on the next whole-deck response; I-2 blocks a send before it), a focus-regain test, a block test for a model/config change and one for a league-settings change, and a guard that no scheduled job reads Sleeper rosters. TF steps 10, 15 and 16. |
| AC-8 | §5.4 "updating" and withdrawn states. **At launch (W-AC-L5) the I-1-driven withdrawal isn't active; that part is checked when strict mode lands.** "Updating" shows only when serving past a bound. It meets the seven shared constraints: no layout shift, no interrupt claim, its own copy, a maximum duration then refresh-failed, controls enabled, no highlight accent, built from existing parts. The withdrawn fronted card keeps dimmed terms, replaces Like/Pass with the reason line plus "Next trade", and changes only after a swipe settles. | G: the state is driven by `freshness_state` from the payload; the updating component calls no `useInterruptSlot` and renders no Toast; the strings contain no "Searching…" and no seconds figure. TF steps 10–12 and 16–18. |
| AC-8b | **Gate-miss wait** (ux-lead F-5). It names its real reason, makes no timing promise, and ends: on timeout it shows the error with Retry, and Back stays usable. The false "within a few seconds" copy is gone. | G: a string check on the placeholder, plus a recovery guard in the pattern of `check-win-now-recovery.js`. TF step 5 |
| AC-8c | **Offline** (ux-lead F-6). Inside the bounds, cards may show with the refresh-failed state at once, and a match-creating like or a send fails visibly and keeps the choice. Past the viewer's roster bound, the offline state shows, with no cards. | G: a pattern of `check-swipe-failure-recovery.js` for the offline like/send. TF steps 14 and 17 |

**[models-lead]** AC-9a to AC-9e replace AC-9. The page contract that AC-9b's check uses is landed
in #382: `assert_page_is_top_n` and `assert_prefix_stable` in `backend/tests/support/deck_contracts.py`
(`eng-evidence-contract.md` §2). The rows below are pasted verbatim from models-lead R.b
(`docs/plans/org-bringup/leads/models-lead-wave2.md` § "R.b PR #339, AC-9", reviewed at `6f8ae71a`). Under
them, models-lead's sign-off follows the two-line packet route in R.a (ii).

| ID | Criterion | Check |
|---|---|---|
| **AC-9a, filter parity at display** | Every card displayed on any serve path (fresh, cached, joined, prepared or device-resident) has passed `deck_quality`'s rules, evaluated against the **freshest inputs held at display time**: rosters within the §5.1 bounds, the value snapshot in use, and lineup slots. If lineup slots are unknown on a fast path, that card isn't served from the fast path; it falls through to the fresh path. **Never a silent skip.** On the value-core path the filters run too, unless a test shows its hard rules are equivalent on the same frozen inputs | T: the AC-5 pattern. Mutate the roster and values between prepare and display; assert every newly failing card is absent; assert the unknown-lineup fallthrough |
| **AC-9b, code parity** | As written: on identical frozen inputs, the fast path's first 30 match the fresh job's in identity and order, with protected cards (likes-you, standing offers, injected, wildcard, retest, published) in the same places | T: the differential test, as written |
| **AC-9c, bounded drift** | On sampled fast-path serves, overlap@30 with the fresh deck built from **tap-time** inputs is **no worse than the engine's own re-run churn** (two fresh builds from the same inputs a few minutes apart) **plus 10 pp**. The draft fallback is a median of ≥ 0.80 until churn is measured. Counted, never sampled: **zero fast-path cards that fail the filters at tap-time inputs** (AC-9a) | A: shadow or offline recompute at a low sample rate, off the critical path (eng chooses how); path-tagged filter counts on both paths |
| **AC-9d, order** | A first card that isn't the full deck's best-first card (approach D, progressive publication) is a model-behavior change. It needs a model-change packet (PR #331) and my sign-off before it ships | Packet |
| **AC-9e, Calibration integrity** | Impressions carry a serve-path tag. Until the round-3 read (2026-11-05), either no fast path ships to users, or Calibration's current-arm sampling is pinned to the fresh path | G or T: the impression tag; sampling filtered by path |

**Remaining criteria:**

| ID | Criterion | Check |
|---|---|---|
| AC-10 | No offer cap or budget cut: the complete eligible inventory stays reachable (the `research-plan.md:66-69` non-negotiables). | T: the inventory-count parity test (pattern of `release-20260921/README.md:16`). |
| AC-11 | **Storage within budget.** The build states its server-side footprint per user-league and in total, plus its daily write volume, using §10.4's formulas, and stays inside that byte budget (P23). Unseen candidates follow DEC-2 as landed in ADR-025: packed evidence, with narrow rows as the fallback (AC-L8). | The byte budget is stated, and head-eng accepts it against H1–H3 (`docs/plans/db-storage-budget/requirements.md:314-317` on draft PR #337) before rollout. A: Q8 table sizes before and after (`baseline-request.md` Q8). |
| AC-11b | **Shedding is safe.** Dropping prepared or cache data under disk pressure (P23) never breaks serving: Find a trade falls back to the fresh path and still meets every §5.3 invariant. | T: a backend test that drops the cache tables or rows and asserts that serving still works through the fresh path. |
| AC-12 | No regressions: CI green (`pytest backend/tests`, `tsc --noEmit`, testid-lint) plus all existing `check-*.js` suites. Any new flag has a guard pinning flag-off byte-identity (ux-lead rubric, flag-off note). TEST_LEDGER records the evidence. | CI, plus the named flag-off guard. |
| AC-13 | **Superseded by AC-L4** (2026-10-20): the next page is always in the deck before the current one ends, and there is no "Finding more" card. The buffer-empty stall count is now zero misses across all test sessions. | See AC-L4. |

## 9. Test-plan seed (D-056: no Maestro, no simulator)

### 9.1 Structural guards (`mobile/tests/check-*.js`, plus an `npm run test:<name>` script)

`check-trade-first-card.js`:
- enumerates the §4.1 controls and arrivals by testID or file, and asserts each emits R1 with a
  `search_id`;
- asserts R2 fires from the enabled-card render path and never from the `SkeletonTradeCard` branch,
  and R2b fires on unmount or blur before a card (analytics-lead R2b);
- asserts `freshness_state` drives the "updating" UI, and that the updating component claims no
  interrupt slot and renders no Toast (AC-8);
- asserts the gate-miss and updating strings carry no timing promise and never say "Searching…"
  (AC-8b);
- asserts no animated push or transition on any search-starting route or in-place reveal (AC-L2);
- asserts no "Finding more" component or copy on the Find a trade path, and that the page N+2
  request starts when page N is fronted (AC-L4);
- asserts the deck renders no "Find more trades" button once U3 is on, and Retry only in the error
  and offline states (D13);
- asserts the P30 card renders the P36 strings (`p30.head`, `p30.body`, `p30.cta1`, `p30.cta2`), and
  that the tally line is **absent when passed, liked and proposed are all 0** (P36), present
  otherwise;
- asserts the P30 card's "Adjust your search" applies its change in place and emits R1 like any search start
  (D14(a)), and that the card renders no third action and no new-trades notice (D14(c));
- asserts the hidden readout (§9.5) reads R2's `ms_from_tap` and nothing else, and renders only
  behind the Testing gate.

### 9.2 Unit and integration tests (backend pytest)

- **Taxonomy:** registration and classification (R1 INTENT; R2 and R2b NON_INTENT), exact prop rows
  (`==`), and the one-of-R2/R2b invariant (analytics-lead).
- **Stage 6:** one `trades_generated` per user-visible deck on every serve path (AC-1b).
- **Freshness:** one test per §5.1 row, covering its §5.2 branch: serve-and-refresh, the §5.5 U2
  fallback (gate-miss, with no platform call on the tap; P40) or block.
- **Ownership:** a roster mutation between prepare and serve, covering every serve path (AC-5).
- **Non-blocking floor kick (P41; AC-L3, AC-7).** A tap with the viewer's roster past its bound and
  the floor healthy:
  - the serve doesn't wait on the refresh: with a stubbed slow refresh, serve latency is
    independent of the stub's delay;
  - a floor refresh is enqueued;
  - when the refreshed roster has changed, the affected card is **not** withdrawn instantly. It is
    withdrawn in place on the **next whole-deck response** (or a focus/revalidation), and the next
    page is built from the fresh roster (option (a));
  - **before that response, an action on the stale fronted card (like, match, send) is blocked by
    I-2** with the refusal message. At launch that is the **send** only (a 422 with a readable
    `detail`); the like assertion is post-launch (AC-6b).
  - A paired case keeps the withhold rule: a failed floor past bound gives the gate-miss state and
    no cards.
  - **Run the withdrawal assertions in strict mode** (`trade_i1_mode` = 2). In **log-only mode** (1,
    the launch value under W-AC-L5), assert that the card is served, that an `[i1]` would-drop line
    is logged, and that I-2 blocks a **send** on it (a 422 `asset_not_owned` /
    `counterparty_asset_not_owned` with a readable `detail`).
- **Action-time revalidation:** per platform write path, including team-overhaul sends, with
  moved-asset and read-failure fixtures (AC-6a); and likes on moved-asset cards (AC-6b).
- **Quality:** filter parity at display, with a roster/value mutation between prepare and display
  and the unknown-lineup fallthrough (AC-9a); the code-parity differential test seeded with a frozen
  clock (AC-9b); and the impression serve-path tag (AC-9e).
- **Inventory parity:** AC-10.

### 9.3 Code-walk proof (file:line, written by the build)

Trace tap → navigation → request or local read → first enabled card render, for each entry point.
Name every hop that can block, and every place a skeleton can show.

### 9.4 Operator TestFlight checklist (the only runtime evidence; run on the build's TestFlight number)

**app-manager writes the launch device checklist** (head-product launch-readiness, 2026-10-20): plain,
numbered and phone in hand. It covers:
- 40 taps per cell (Wi-Fi and cellular × first and repeat tap), each recording the §9.5 readout;
- the U3 page-end run: swipe through three pages, and the deck never runs dry;
- the U5 fresh-account run;
- the U2 roster-change run.

The steps below are the PRD's seed for that checklist and stay consistent with it. Steps L1 to L4,
at the end, are the launch runs.

**Setup:**
- an iPhone on the build;
- a Sleeper league with at least 10 teams where you have a roster and rankings;
- iOS Screen Recording on, so the tap and the first card can be timed frame by frame (1 frame ≈
  16.7 ms) as an independent check on the telemetry;
- note the phone model, iOS version and network for every step;
- Settings › Testing open to the hidden ms readout (§9.5). Record its value for every timed tap.

Steps are tagged **[onboarded]**, **[test league]** or **[first-run]** where it matters (ux-lead).
**If D10 ships,** the Home, League and Matches taps start the deck directly. Time from that tap,
and skip the second (canvas) tap in steps 1 and 3.

1. Force-quit, cold-launch, and wait until Home is fully loaded and 10 s have passed (session-init
   done). Tap the Home **Find a trade** tile. **Record:** the time to an interactive Acquire builder
   (table B; not gated). With the canvas **empty**, tap the canvas **Find a Trade**
   (`calc.action.find-a-trade`). **Expect:**
   - a real card with enabled Like/Pass in ≤ 200 ms from this second tap on the recording
     (≤ 12 frames), with the readout agreeing within 1–2 frames;
   - no skeleton, no "Looking for trades…" card, and no "Searching…" frame before it.

   On the same recording, count transition frames **separately**. **Expect:** zero; the card is
   revealed in place or by an instant, non-animated route (U1, AC-L2). Fail if any slide-in or fade
   plays.
2. Go back to the builder and tap canvas Find a Trade again (repeat tap). **Expect:** ≤ 200 ms.
   Once U3 is on, the deck shows **no "Find more trades" button**; Retry appears only in the error
   and offline states (D13).
3. Reach the builder from every other table B control: League Home **Find a trade** (both
   buttons), the Matches empty-state CTA, and the calculator's "Find a trade →" row. For each:
   **record** tap → builder, then tap canvas Find a Trade with an empty canvas. **Expect:**
   ≤ 200 ms from the canvas tap each time. Write down any misses.
4. Turn Wi-Fi off (cellular only). Repeat steps 1–2. **Expect:** ≤ 200 ms. Cellular is gated (D3
   decided; AC-L1).
5. Force-quit, cold-launch, open Acquire, and tap canvas Find a Trade **as soon as it is
   tappable** (session-init may still be running). **Record:** the time, and what showed before
   the card (for Decision D2). **Expect:** any wait names its real reason, makes no timing promise,
   and ends in a card or an error with Retry, with Back usable (ux-lead F-5, AC-8b).
6. On the first card, wait 1 s, then Pass. **Expect:** the next card is already there. No skeleton,
   no "searching" stall. Pass through 10 cards, noting any stall.
7. **Targeted searches (record; gated only if Decision D1 says so):**
   - put one player on the receive side only, then tap Find a Trade (model deck);
   - add a player to the give side, then tap Find a Trade (the fairness sweep);
   - Usage Trends **Trade** on a player, with and without a partner;
   - League Summary Offer and Target.

   **Record:** the time to first card, or what showed instead. A Usage Trends handoff with no
   partner currently lands on the builder with no search.
8. Like a card, return later, tap canvas Find a Trade. **Expect:** the liked offer does not reappear
   as new (I-3).
9. Ask analytics-lead to confirm that every tap in steps 1–7 produced one R1 and exactly one R2 or
   R2b with matching `search_id`, with `network_type` set. Also confirm that `ms_from_tap` agrees
   with your recording within 1–2 frames.
10. Change your rankings (move a player across a tier, or change your outlook), then within 1 minute
    tap canvas Find a Trade. **Expect:** a card in ≤ 200 ms. If the deck predates the change, the
    "updating" state shows, and within the refresh window the deck reflects the change without
    rewriting the card on screen.
11. **Roster freshness, yours:** in the Sleeper app, drop a bench player of yours who appears in your
    offers (pick one you can re-add, or use a test league). Return to the app within 2 minutes and
    tap canvas Find a Trade. **Expect:** no displayed card includes that player, now or after the
    refresh. **At launch (W-AC-L5):** the card may still show. Expect **Send** on it to be blocked,
    with the `detail` text in the send alert. A Like may still record, because AC-6b is
    post-launch.
12. **Roster freshness, partner [test league]** (or a cooperating leaguemate): the partner drops or
    trades away a player your deck offered from them. **Expect:** no card shows that player as
    theirs within the §5.1 bound. **At launch (W-AC-L5):** it may show. A Send on it is blocked by
    I-2, with the `detail` in the send alert; likes aren't blocked at launch.
13. **Blocked actions [test league the operator names]** (platforms-pm evidence plan; AC-6a, AC-6b).
    The operator approves the attempt when it runs and cancels any proposal that lands. Start with
    Sleeper; add ESPN and MFL only where a test league exists. Find a card containing a player who
    moved after the card was built (from step 11 or 12, or a test-league setup).
    - **Post-launch step (AC-6b):** tap **Like** where it would create a match. **Expect:** no like
      and no match. The card is withdrawn in place with "<player> is no longer on <team>" and
      "Next trade". **At launch, likes aren't blocked** (head-product, 2026-10-26), so skip this step for the
      launch run.
    - Tap **Send**. **Expect at launch:** an **alert** with the server's readable `detail` (the
      refusal copy, e.g. "You no longer own X" or "X no longer owns Y"), and nothing reaches the
      platform. **Post-launch (AC-6a placement):** the message shows on the card, names the
      platform, says nothing was sent, and offers a next step.
14. With no cards loaded, turn on Airplane Mode and tap canvas Find a Trade. **Expect:**
    - past the viewer's roster bound: the offline state with no cards;
    - inside the bounds: cards may show with the refresh-failed state at once;
    - no crash, and no action that silently fails (ux-lead F-6).
15. **[onboarded]** Run a search and leave the deck open. Go to Home and tap **Find a trade**.
    **Expect:** per D10, the builder or a fresh deck. Fail if the earlier deck shows its old cards
    with no "updating" state (ux-lead F-2).
16. **[onboarded]** Open a deck. Change a tier in Rank, then return to the Trades tab without tapping
    Find. **Expect:** "updating" shows and ends, the fronted card isn't rewritten, and nothing shifts
    the card's position.
17. **[onboarded]** With cards showing, turn Airplane Mode on and trigger a refresh (as in step 16).
    **Expect:**
    - "updating" ends in the refresh-failed state with Retry;
    - Like/Pass still respond;
    - a like that would match fails visibly and keeps the choice (ux-lead F-6).
18. **[test league]** The partner trades away a player on your fronted card while it's on screen.
    **Expect:** the card stays, dimmed, with the reason line and "Next trade". Nothing slides in
    mid-swipe (ux-lead F-4). **At launch (W-AC-L5):** no withdrawal. A Send on it is blocked, with the
    `detail` in the send alert; likes aren't blocked. Run the withdrawal check once strict mode
    lands.
19. **[first-run, fresh install]** If D10 ships: from the Trades landing, the guide's canvas Find a
    Trade step still appears, and its adoption event fires once.
20. Log the outcomes in `living-memory/TEST_LEDGER.md`: times, misses, transition frames, and any
    card that violated I-1.

**Launch runs** (head-product launch-readiness, 2026-10-20; app-manager's checklist is the
authority):

- **L1. Cells.** 40 taps per cell, Wi-Fi and cellular × first and repeat tap, on at least 2 devices
  including the operator's. Record the readout each time and use **Copy as text** at the end of each
  cell. **Expect:** p95 ≤ 200 ms per cell (AC-L1).
- **L2. U3 page-end run.** Swipe through three full pages without stopping. **Expect:**
  - the next page is already behind the current card at every page end, with no reorder or jump;
  - no "Finding more" card, ever (AC-L4).
- **L2b. P30 genuine end** (a test league or a narrow search that exhausts). Swipe until every
  candidate is seen. **Expect:**
  - the P30 final card, in the same rect: "You've seen every trade for now." and "New ideas show
    up as rosters and values change." (P36);
  - **Adjust your search** and **Back to Home**, with no Like or Pass;
  - **tally, both cases (P36):**
    - after passing, liking or proposing at least one card in the session, one chalk-dim line
      "{passed} passed · {liked} liked · {proposed} proposed" with the right counts;
    - after a second run where you swipe nothing to the end (for example, a narrow search with
      nothing new acted on), **no tally line at all** when all three are 0;
  - it never appears while a page is still loading;
  - with VoiceOver on, focus moves to it and its copy is read once;
  - no "new trades" notice while it shows (D14(c)).

  Then tap **Adjust your search**. **Expect:** the deck's own preferences (fairness and
  filters) open. Change one and apply it. **Expect:** the changed search runs in place, with no
  navigation. Record the readout from the apply tap; it falls under AC-L1 (D14(a)).
- **L2c. Page end offline and on error** (ux-lead rows 3a and 3b). Turn on Airplane Mode and swipe to
  the last loaded card. **Expect:** the Offline card, and on reconnect the next trade replaces it in
  place. Then, if a fault-injection build exists, force a fetch failure while online. **Expect:**
  "Couldn't load more trades" plus Try again, with Back usable. Record either outcome, and treat
  3b as an AC-L4 miss.
- **L3. U5 fresh-account run.** On a new account, connect a league and complete onboarding, then tap
  Find a trade at the first chance. **Expect:** ≤ 200 ms, and "Building your first trades" does not
  appear (AC-L7). Record it if it does.
- **L4. U2 roster-change run.** As steps 11 and 12, with the readout open. **Expect:** no card with a
  moved asset, a withdrawn-in-place card if one was showing, and no platform call on the tap
  (AC-L3, AC-L5). **At launch (W-AC-L5):** cards with the moved asset may show. A **send** on them
  is blocked (the `detail` in the send alert), and a like may still record (AC-6b post-launch).
  There's still no platform call on the tap.
- **L4b. K-F5: a move FTF makes** (activates when #351 D1 ships; not a launch gate; #351's D1 add/drop is post-launch). From a deck showing a card that
  includes one of your bench players, use FTF's add/drop to drop that player. Return to the deck.
  **Expect:** that card is withdrawn in place, with the reason line, before you can act on it. No
  later card includes the dropped player (AC-L5).
- **L4c. P41 non-blocking kick** (practical solo, with the same caveat as step 11: drop a bench
  player you can re-add, or use the operator's test league).
  1. Open Trades and stay on it for **more than 5 minutes**, with no backgrounding and no focus
     change.
  2. From another device, change your roster on the platform: drop a bench player who appears in
     your offers.
  3. Tap canvas Find a Trade.

  **Expect:**
  - the first card appears without waiting (the readout stays in the normal range);
  - before the deck next fetches a page, **Send on a card with the dropped player is blocked**, with
    the `detail` in the send alert. Likes aren't blocked at launch (AC-6b post-launch);
  - after the next page fetch (swipe to the prefetch point) or a focus change (switch tabs and
    back), that card is withdrawn in place with the reason line, not instantly (option (a)).
    **At launch (W-AC-L5)** this step waits for strict mode; until then the card stays and I-2
    keeps blocking actions;
  - later pages never include that player (AC-L3, AC-L5).

### 9.5 The hidden ms readout (for the operator's device runs)

Specified by trades-pm (2026-10-20, per head-product launch-readiness); **head-eng decides the
build**.

- **Where:** Settings › Testing, behind exactly the gate `SettingsTesting` uses. The row renders
  only under `__DEV__ || useFlag('testing.stage_users')` (`mobile/src/screens/settings/SettingsHubScreen.tsx:91,333`;
  the flat list uses the same gate at `mobile/src/screens/SettingsScreen.tsx:227,1480`).
  `testing.stage_users` is false in the checked-in `config/features.json:206`.
  - **Caution:** the route itself is registered unconditionally (`mobile/src/navigation/RootNav.tsx:668-707`)
    and has a deep link `settings/testing` (`mobile/src/utils/deepLinks.ts:112`). The readout must
    therefore apply the same gate **itself**, not rely on the row, so it stays invisible to
    everyone else.
  - head-eng confirms how the operator's TestFlight device gets the gate.
- **What it shows:**
  - the last tap-to-first-card time in ms, in large type;
  - its entry control (table A id), network type, first or repeat tap, and cold launch;
  - a list of the last 40 readings with those tags;
  - **Copy as text** (for pasting results) and **Clear**.
- **Source:** the **same** measurement as R2 `trade_first_card_shown.ms_from_tap` (the §4 clock),
  never a second timer. A failed or abandoned search shows "—" with the R2b reason.
- **Local only:** no network call, no new event and no user-facing change.
- **Evidence:** the `check-trade-first-card.js` assertions (§9.1): the readout reads the R2 value
  and is reachable only behind the testing gate. Plus TestFlight run L1 (§9.4).

### 9.6 AC-L1 proof plan: a scripted two-device session

**Why scripted:** organic volume is about 1.6 searches a day (W3, §6). Reaching n ≥ 40 in each of the
four cells (160 or more searches) organically would take about 100 days. app-manager turns this
protocol into the phone-in-hand checklist. Organic telemetry continues after launch as monitoring,
not as the gate.

**Preconditions (all must hold before the session):**
1. ~~Background replenishment is restored~~ **No longer a precondition (head-product, 2026-10-25, §15 item
   16).** The 200 ms build doesn't rely on it: U2's floor is S0 (#378), and U3's pages are P1/P2.
   Replenishment returns after C2 and the self-renewal fix, per #361
   (`docs/plans/daily-tick-fix/scope.md:42,69-71`).
2. The TestFlight build carries R1, R2 and R2b (with `network_type`) and the §9.5 readout. The T1
   evidence passes: the guard or code-walk shows R2 fires at exactly the §4.2 frame.
3. **Both devices are tagged as tester devices (T5),** and analytics-lead's query includes tester
   devices. Both devices have the Testing gate, so the readout is visible.
4. One test league per device with a pre-built first page (U5), so the canvas has an organic search
   to run.

**Devices:** the operator's iPhone plus one more. Record each device's model and iOS version.

**Cells:** Wi-Fi and cellular (Wi-Fi off) × first tap and repeat tap. **At least 40 per cell in
total, with each device contributing to each cell.** The default plan is 20 per device per cell:
160 taps.

**First tap (one per launch):**
1. Force-quit the app and relaunch.
2. Wait until session init has completed. No user-visible signal of that completion was found in
   the code walked for this PRD, so use a **fixed 15 s wait after Home renders** (session-init p50 is
   358 ms per W3 Q9; the wait leaves margin).
3. Open Acquire and tap the canvas Find a Trade with an **empty canvas** (organic, table A).
4. If telemetry tags the tap `cold_launch` rather than `first_tap`, it stays in the `cold_launch`
   row (T3) and does not count toward the first-tap cell. Run another first tap; never discard or
   relabel a record.

**Repeat tap:**
1. After a first tap, go Back to the builder.
2. Wait a **fixed 10 s**.
3. Tap again. Run four repeat taps per launch.

**Rotation:**
- With D10 unshipped, the gated organic control is the canvas Find a Trade, so every gated tap uses
  it.
- If D10 ships, rotate the first-tap control in a fixed order: canvas, Home tile, League Home,
  League works-now, Matches empty state. Repeat taps use the control the first tap used.
- Pinned or hand-off taps aren't part of the gated cells.

**Conditions that satisfy T1–T6:**
- **T1:** the precondition above.
- **T2:** every tap counts. An R2b (timeout, error, empty, abandoned) counts above 200 ms. Nothing is
  redone to remove a failure.
- **T3:** `cold_launch` is reported as its own row.
- **T4:** keep the app in the foreground from tap to card. Any backgrounding ends the search as R2b
  `abandoned`, and it counts.
- **T5:** tester devices are included.
- **T6:** analytics-lead reports nearest-rank p95 with a 90% CI. "Pass, not robust" means a further
  session.

**Record and cross-check:**
- **Telemetry R1/R2/R2b is the record.**
- For every tap, note the §9.5 readout. Any difference over **5 ms** between the readout and R2's
  `ms_from_tap` is a defect to report, because they are the same measurement.
- On every tenth tap, also time the screen recording. A difference over **2 frames (≈ 33 ms)** from
  R2 is noted.
- **Copy as text** at the end of each cell.

**Time:** roughly 45 s per first tap (relaunch, 15 s wait, tap, note) and 20 s per repeat tap.
- That is about 160 × 32 s on average, roughly **85 minutes of tapping** in total.
- With both devices in parallel, about **1 hour wall-clock**, plus network switching and a margin.
- A "pass, not robust" result adds another session.

## 10. Trade-offs for eng (surfaced, NOT decided)

### 10.1 Candidate approaches (eng chooses; combinations likely)

| Approach | What it changes | Fits 200 ms? (from evidence) | Main cost or risk |
|---|---|---|---|
| A. Server-prepared inventory, fast serve | Adopt a validated prepared deck at tap (#305–#307 path, now dark) | Only if server work plus one round trip fits. Best local first-30 is 1.081 s (`prepared-trade-inventory/release.md:161-165`): about 5.4× the whole budget, and about 27× the 40 ms server slice in §10.2 | ~2–2.6 MB per user-league stored, plus evidence writes per adoption (§10.4). Freshness is bounded by refresh cadence. Skips `deck.quality_filters` today. Production canaries failed twice (`release.md:37-39,90-93`). |
| B. Device-resident first page | Prefetch the first N validated cards to the phone at app open, foreground or Trades focus. The tap renders locally; validity is rechecked in the background | Removes the network from the critical path; render only | Device copy can go stale between prefetch and tap, so it leans on §5.2 and I-1/I-2. About 1.25 KB per card on device (`delivery.md:106`). Needs a new mobile binary. |
| C. Faster fresh generation | Engine and evidence speedups, or a faster engine (value core local p95 1.77 s on a 14-team fixture; `TEST_LEDGER.md:213`) | **No on its own.** Even 1.77 s is almost 9× the budget | Shortens refresh time, so it helps freshness. Swapping engines is a model change (models-lead). The value-core path skips the filters today (`server.py:7566-7600`), so approach C must run them or prove its hard rules equivalent on the same frozen inputs (AC-9a; models-lead R.b). |
| D. Progressive publication | Publish a card before global ranking completes | Possibly | Changes the best-first order contract (`execution-20260921/README.md:9`). A model-behavior change: it needs a model-change packet (PR #331) and models-lead's sign-off (AC-9d). |
| E. Transport | Replace 800 ms-first polling with an immediate response or push | Likely needed alongside A: the first poll alone lands at 800 ms. Irrelevant to B's critical path | API contract change (api-reference); new client binary. |

### 10.2 Latency budget split (illustrative; eng refines)

The 200 ms must cover the whole path, with no animated transition (AC-L2). Illustrative splits:
- **Network on the critical path (A + E):** tap handling and in-place reveal 30 ms + network 100 ms +
  server 40 ms (a pre-built page read, no platform call; AC-L3) + decode and render 30 ms.
- **Network off the critical path (B):** tap and reveal 30 ms + local read, render and layout
  ≤ 170 ms. Validation runs after.

Two facts constrain any split:
- A cellular round trip to the Oregon-hosted service (one Standard instance;
  `infrastructure-and-precompute.md:7`) is **unmeasured** for our users. No RTT figure exists in the
  repo, which is why `network_type` is captured on R2/R2b.
- Navigation itself costs time. A stack-push animation can consume much of the budget before the
  card is "≥ 50% visible" (§4.2). The repo's own estimate for a transition is "~250–400 ms of
  otherwise-dead time" (`navigation/TabNav.tsx:1017-1018`). **This is now a requirement, not a
  trade-off** (ux-lead F-1, AC-2b): search-starting pushes keep `push` and the back stack, but run
  with no animation or a short fade that design-lead specs.
  - Today the organic control pushes a new `TradeDeck` screen (`TradesScreen.tsx:3429-3445`), and
    each search resets the deck (`:3271`). So the push transition sits on the critical path.
  - No earlier card is reused on the phone: no deck is persisted, and the persisted query allow-list
    is rankings, progress, matches, tiers-status and liked-trades only (`mobile/App.tsx:61`).

### 10.3 Precompute vs freshness

- **Freshness is set by refresh cadence.** Every precomputed card is only as fresh as its last
  rebuild. Rebuild cost today is tens of seconds of CPU on the single web worker. The 936-offer local
  preparation took 23.79 s (`prepared-trade-inventory/release.md:162`); production workers run a 61 s
  median.
- **Background preparation competes with interactive requests.** It runs on the one gunicorn worker
  with a 120 s timeout (`infrastructure-and-precompute.md:7`). The daily tick already dies at that
  timeout every day and restarts the only worker, wiping process-local job caches
  (`living-memory/NEXT.md:55-58`).
- **Every rank swipe invalidates the user's job** (§5.1). A user who ranks and then taps always
  misses the cache today. The zero-tolerance ranking bound with serve-and-refresh is what lets a
  fast path coexist with ranking.
- **Roster input is currently refreshed only when a member opens the league** (G-075).
  - **Prepared inventory can't assume headless roster refresh** (trades-pm decision 6, on
    platforms-pm R7). No scheduled or headless server-side Sleeper roster reads beyond today's
    pattern until the operator rules on E2, and ESPN and MFL refetches stay user-triggered.
  - So a prepared deck can only be as fresh as the last user-triggered roster read. Under head-product P40, 2026-10-24,
    the §5.1 roster bounds are met because the background floor refreshes the viewer's roster **off the tap path**, on session start, app foreground and the P41 kick (Trades focus is a post-launch candidate), and **never on the search tap or the first-page serve**.
  - A prepared deck whose rosters are past the bound gets the §5.5 U2 fallback for the viewer
    (gate-miss, never a refetch on the tap), and filter-and-refresh for partners.
- **Precompute timing can change which offers are served**, independent of any model edit. The same
  league can yield a different deck at 3 a.m. than at tap time: rankings, values and roster changes
  in between, and the engine's wall-clock per-pair deadlines (G-065, `GOTCHAS.md:740`). That is why
  models-lead signs off (§11).

### 10.4 Storage cost (for the parallel DB-storage task)

Sources:

| # | Fact | Source |
|---|---|---|
| a | Prepared v2, actual 512-offer run: 480,867 B stored → **≈ 939 B/offer** (logical 15,430,124 B ≈ 30.1 KB/offer) | `prepared-trade-inventory/release.md:69-72` |
| b | Prepared v2, dense 13,728-offer run: 15,083,835 B compressed text → **≈ 1,099 B/offer** (logical 461,530,265 B ≈ 33.6 KB/offer) | `release.md:99-101` |
| c | Production deck size: 1,655–1,976 final cards per job (n=7); reconstructed 2,354 | `infrastructure-and-precompute.md:15-21`; `release-20260921/README.md:16` |
| d | Deck evidence rows: **≈ 9 KB** incremental physical per `deck_impressions` record | `db-storage-reduction/release.md:19` |
| e | Headroom on 2026-09-15: **≈ 349,588 records** on the 5,246,714,000 B disk with a 20% reserve | `db-storage-reduction/release.md:50-60` |
| f | Active cohort: 22 user-league pairs over about 30 days; 7 resolved prepare targets in the 2026-09-22 dry run | `infrastructure-and-precompute.md:44`; `prepared-trade-inventory/release.md:20-21` |

Arithmetic (stored bytes only; excludes index, TOAST and WAL overhead):

- **One prepared inventory** = 1,976 × 939–1,099 B ≈ **1.86–2.17 MB**. At 2,354 cards: **2.21–2.59 MB**.
- **Steady state:** one active artifact per user-league, plus a second during replacement.
  - 22 pairs × 2.59 MB ≈ **57 MB** (≈ 114 MB peak during refresh).
  - At 10×: ≈ 570 MB.
  - At 100×: ≈ **5.7 GB**, more than the whole 5.25 GB disk.
- **Evidence writes per served deck, today's contract:** every card of the inventory gets an
  impression row at publication or adoption. That is 1,976 × 9 KB ≈ **17.8 MB per Find a trade**.
  Against fact e, that is ≈ 349,588 ÷ 1,976 ≈ **177 full-deck searches** of headroom (fewer at 2,354
  cards). The 14-day diagnostic expiry returns part of it.
  - **This, not the prepared artifact, is the dominant storage term.**
  - Writing evidence only for cards actually displayed (lazy) would shrink it by orders of magnitude.
    It is an evidence-contract change: analytics-lead and models-lead decide; Calibration's current
    arm reads these rows.
- **Refresh churn:** daily write volume ≈ refreshes/day × artifact size. For example, 22 pairs × 12
  refreshes/day × 2.59 MB ≈ 684 MB/day of transient writes, pruned hourly. That load lands on Basic
  256 MB Postgres (`infrastructure-and-precompute.md:7`).
- **Device-side (approach B):** the first 30 cards ≈ 37,348 B uncompressed (4,075 B gzip)
  (`delivery.md:106-107`). No server storage.

**Ruling (head-product P23, 2026-10-15):** "prepared-inventory data sheds first under disk pressure,
and no rollout without an explicit byte budget, which head-eng checks against task 2's H1–H3."
What it means for any build:

- **Cache data sheds first.** Prepared inventory, and any other fast-path cache, is the first class
  of data dropped under disk pressure. It must be rebuildable and never the system of record.
  Serving falls back to the fresh path when it is gone (AC-11b).
- **No rollout without a byte budget.** The budget is stated per user-league and in total, using the
  formulas above. head-eng checks it against the storage-budget task's headroom targets before
  rollout (`docs/plans/db-storage-budget/requirements.md:314-317` on draft PR #337):
  - H1: at least 20% of the volume stays free;
  - H2: above that reserve, room for the largest relation's total size;
  - H3: H1 and H2 hold for 52 weeks at W3-measured weekly growth × 2.

  head-eng also confirms the H1–H4 numbers themselves (that task's DEC-7, `requirements.md:336`).

**DEC-2 → ADR-025.** The decision is landed and Accepted as
[`docs/adr/adr-025-packed-unseen-evidence.md`](../../adr/adr-025-packed-unseen-evidence.md)
(head-eng, 2026-10-25; models-lead C1–C9). It is cited, not restated:
- never-served pre-builds write no evidence;
- full rows go to viewed or acted-on cards, the first 30 and the C8 2% archive;
- every other served card is **packed** (about 64 B per card all-in, against about 9 KB);
- separate narrow rows are only the fallback.

The P23 byte budget is set (`scope-eng-200ms.md` §7). This PRD's earlier "narrow rows" wording and
its "displayed cards only" idea are reconciled in §15.

### 10.5 Deck quality vs speed

- **`deck.quality_filters` (D-207)** runs in `_run_trade_job` after presentment
  (`deck-quality-filters/scope.md:14`).
  - It runs **before** the first-30 publication, over the **entire** served list, not just the first
    30 (`backend/deck_quality.py:83-130`; `backend/server.py:8876-8902`).
  - It records no timing, only counts (`:8897`).
  - Its lineup-slot lookup (`_league_lineup_slots`) can make a **live Sleeper `GET /league/<id>` with
    a 10 s timeout** on a 15-min meta-cache miss (`server.py:29130-29152`). That puts a network call
    on the first-card critical path.
  - The value-core path skips the filters (`:7566-7600`), so approach C must run them or prove
    equivalence (AC-9a). Prepared inventory is out of their v1 scope, so a prepared fast path serves
    unfiltered cards unless the filters are extended to it.
  - AC-9a to AC-9c require the filters on every serve path, evaluated at display-time inputs. AC-9b
    covers code parity on frozen inputs, and AC-9c bounded drift in production (models-lead R.b).
- **Model arms:** today's engine (`owner_v2_bilateral`) is the default. Value core is flag-off and
  graded lower in Calibration round 2 (2.88 vs 3.19; `living-memory/CHANGELOG.md:31`). Its speed
  (p95 1.77 s local) makes it tempting as a latency fix. Choosing an engine for speed is a models-lead
  and operator call, not a latency optimization. While `trade.value_core` is on, prepared inventory
  is unsupported (`docs/config-reference.md:351`).
- **Calibration decks** are built headlessly, and their current arm samples served
  `deck_impressions` (`architecture.md:406-412`). A fast path that changes which cards are served, or
  which get evidence rows, changes what Calibration grades. Round 3 is open until 2026-11-05.
  - **AC-9e, Calibration integrity (models-lead R.b):** impressions carry a serve-path tag.
  - Until the round-3 read on 2026-11-05, either no fast path ships to users, or Calibration's
    current-arm sampling is pinned to the fresh path (Decision D12).
- **Order:** a fast first card that isn't the full deck's best-first card is a **model-behavior
  change**. It needs a model-change packet (PR #331,
  `.claude/skills/pm-technical/references/model-change-packet.md`) and models-lead's sign-off
  (AC-9d; models-lead R.b).

### 10.6 Flags and knobs involved

Checked-in values are from `config/features.json` on `origin/main` `678834ab`. Production values
can differ: GOTCHAS G-064 records a knob that was live while every doc said dark. Q0 of
`baseline-request.md` reads them back.

| Flag / knob | Value | Line | Role on this path |
|---|---|---|---|
| `trade.prepared_inventory` | true (capability only) | `:2` | Registers prepared inventory. Real preparation and adoption need the knob below. |
| `model_config prepared_trade_inventory_enabled` | default **0**; last prod readback 0 (2026-09-23) | `docs/config-reference.md:9-17` | The rollout switch for prepare/adopt. Exactly 1 enables it. |
| `trade.value_core` | false | `:276` | A different engine. While on, prepared inventory is unsupported (`config-reference.md:351`). |
| `deck.quality_filters` | true | `:218` | The D-207 filters on the live deck only; prepared inventory is out of v1 scope. |
| `deck.replenishment` | true | `:216` | Weekly background decks, run inside the daily tick, which is currently dying at the 120 s timeout (`NEXT.md:55-58`). |
| `trade.bakeoff` | true | `:254` | Arm interleaving and attribution. Which arm serves can change the deck. |
| `trade.full_sweep` | true | `:269` | Scores every leaguemate, which costs time. |
| `trade.presentment_rules` | true | `:76` | Presentment-rule R4 awaiting/matched exclusions (I-3). |
| `trade.standing_offers` | true | `:282` | Protected cards in the deck. |
| `trade.send_in_sleeper` / `trade.send_in_mfl` / `espn.send` | true / true / true | `:52` / `:53` / `:115` | The send paths that I-2 covers (platforms-pm R1–R5). |
| `overhaul.enabled` | true | `:84` | Team-overhaul sends, also covered by I-2 at send time (platforms-pm R8). |
| `fleaflicker.link` | false | `:119` | Fleaflicker is dark with no write path; n/a for I-2 (scope.md §6). |
| `suggestion.telemetry` | true | `:220` | Candidate-set and impression telemetry, part of the evidence-write cost. |
| `deck.signal_v2` | true | `:208` | `deck_card_viewed` and impression logging. |
| `calc.inline_home` / `calc.results_push` / `calc.merged_layout` | true / true / true | `:97` / `:101` / `:95` | Make the canvas the search entry and push `TradeDeck` (§4.1, §10.2). |
| `calc.canvas_results` | false | `:99` | An alternative in-canvas results surface. |
| `trades.finder_hub` / `nav.home_hub` | true / true | `:16` / `:107` | Route table B controls to the builder. |
| `trades.presentation_v2` | false | `:256` | TodaysTrade surface (dark). |
| `onboarding.trades_first` | true | `:126` | First-run auto-start, skipped while results-push is live. |
| `usage_trends.enabled` | true | `:109` | Usage Trends handoff entries. |
| `analytics.client_events` | true | `:121` | Gates every client event R1/R2 would ride on. |
| `grading.blind` | true | `:278` | Calibration: its current arm reads served impressions. |
| `obs.api_events` | true | `:250` | Route-duration sampling used by the baseline |
| `model_config` owner-serving keys: `bakeoff_include_owner`, `bakeoff_serve_owner`, `bakeoff_owner_only`, `owner_bilateral_enabled`, `owner_bilateral_revision_enabled`, `significance_mode`, `simple_player_presentment` | seeds 0 (`backend/database.py:3173-3182,3278`). Prod differs: the 2026-09-21 readback showed bilateral owner-only serving (`infrastructure-and-precompute.md:7`) | — | Decide whether #303's first-30 owner batching and prepared adoption are reachable at all. With the checked-in seeds both are inactive (`server.py:9006-9038`; `prepared_trade_runtime.py:86-96`) |
| `bakeoff_deck_limit` / `bakeoff_serve_interleaved` | seeds 30 / 0 (`database.py:3158-3159`); prod 60 / 1 per `docs/config-reference.md:726` | — | Deck size and arm mixing |
| `owner_pool_size` / `owner_pair_budget` / `owner_total_budget` | 16 / 4096 / 60000 (`database.py:3179-3181`) | — | Search budgets. **Not** to be cut for speed (§4.5) |
| `full_sweep_budget_s` | 30 (`database.py:3248`) | — | The wall-clock sweep cap; part of G-065 non-determinism |
| Constants `_PREGEN_TTL_SECONDS` / `_JOB_HARD_TIMEOUT` | 1800 s / 60 s, swept every 300 s, so effectively 60–360 s (`server.py:2285-2287,2722-2735`) | — | Cache lifetime and timeout |

Any new flag eng adds must default off, be listed in `docs/config-reference.md`, and name a
deploy-free kill switch.

### 10.7 Engineering constraints for the 200 ms build (trades-eng memo, via head-product, 2026-10-20)

These are **eng constraints, not product decisions**. The landed eng scope is
[`scope-eng-200ms.md`](scope-eng-200ms.md) (#399/#401), and it governs the build. The floor is
[`scope-eng-s0-fetch.md`](scope-eng-s0-fetch.md) and #378. The AC-9 page contract is
[`eng-evidence-contract.md`](eng-evidence-contract.md) §2 and #382. The bullets below are the
product-side summary; §15 lists where they differ from main.

- **No live Sleeper or platform calls on the tap path,** with a background freshness floor
  ("Step 0") that keeps the pre-built page inside the §5.1 bounds. This is AC-L3. Under
  platforms-pm R7 and head-product P40, 2026-10-24, the floor refreshes on session start, app
  foreground and the P41 kick (Trades focus is a post-launch candidate, head-product 2026-10-25). It
  never runs on a schedule, and never on the search tap or the first-page serve.
- **The first page is pre-built server-side** before the tap ("Option 1"): about 37 KB per
  user-league pair, instead of the whole deck. Pages 1 and 2 are built together (§4.7).
- **No animated push.** The ~350 ms transition alone breaks the budget (AC-L2, U1).
- **On cellular, a device-held first page** ("Option 2") may be needed. Approach B in §10.1.
  **head-product P32:** a device-held first card counts toward 200 ms if it meets U2: within the
  freshness bounds, passing I-2, and withdrawn in place if invalidated (AC-L1). At launch
  (W-AC-L5), withdrawal waits for strict mode; I-2 blocks sends, via the send alert.

The storage side (DEC-2 as ADR-025's packed evidence, and the P23 byte budget in `scope-eng-200ms.md` §7) is in §10.4 and AC-L8.

## 11. Required reviews

Review status as of 2026-10-15, folded in. The 2026-10-20 launch revision adds the rows marked **(launch)**: U1 placement and visuals, the device checklist, and the AC-L4 telemetry request.

| Reviewer | Why | Status |
|---|---|---|
| **design-lead** | The §5.4 states (updating, withdrawn, refresh-failed, offline), the push motion (AC-2b), Chalkline compliance, D10 labels | **Pass with notes 1–7 plus D10 notes, folded in.** Still owed: the visual spec for the withdrawn card and status line, a `components.md` row, the motion spec, and the joint D11 slot call. A mockup lab is optional |
| **ux-lead** | The flow: D10, the push transition (F-1), focus regain (F-2), "updating" (F-3), withdrawal (F-4), gate-miss (F-5), offline (F-6), blocked actions (F-7), arrivals (F-8) | **Approve with changes F-1 to F-8, folded in.** Still owed: the joint D11 slot call and the VoiceOver announcement spec |
| **analytics-lead** | Event grant and the W3 baseline (`baseline-request.md`) | **R1–R3 granted with conditions; R4 refused, with a `network_type` prop granted instead; folded in (§4.6, AC-1, AC-1b).** Baseline still pending W3. Owed by the build: the addendum doc |
| **models-lead** | Sign-off if served cards, their order or their composition can change. Precompute timing alone can change which offers are served (§10.3), as can a progressive order (D), an engine swap (C), skipping or extending `deck.quality_filters`, or lazy evidence | **Changes folded at `c429c16d` (R.b)**, as AC-9a to AC-9e. Sign-off follows the two-line packet route (R.a (ii)) |
| **platforms-pm** | I-2 on the Sleeper, ESPN and MFL send paths (including overhaul) and the roster cadence behind §5.1 | **Accept with changes R1–R8 plus notes N1–N4, folded in** (§5.1, §5.3, AC-6a/6b, scope.md §6). Logs R7 in the platform risk register |
| **onboarding-pm** | D10's first-run limit, F-4's guide interplay, and the P12 privacy-label check for `network_type` and `search_id` | **Needed** (raised by ux-lead and analytics-lead) |
| **marketing-lead** | Copy for the updating, withdrawn, refresh-failed, offline and gate-miss lines, and the calculator-row relabel (through head-product) | **Needed** (design-lead 5, D10) |
| DB-storage task owner + head-eng | Footprint (§10.4) against the storage budget (AC-11, AC-L8, P23) | Before any persistent cache expands |
| **ux-lead (launch)** | U1 per entry point, and the U3 six-state table with VoiceOver rules | **Delivered 2026-10-20 and folded** (§4.7, AC-L2, AC-L4). D13 and D14 are decided by trades-pm and accepted (head-product P33, 2026-10-20) |
| **design-lead (launch)** | The U1 visual spec with the deck motion exemption, the P30 end card, and the U5 card | **Delivered 2026-10-20 and cited** (§4.7). The visual specs stay design-lead's. Owed: the `components.md` rows and the Motion exemption |
| **analytics-lead (launch)** | AC-L1 measurement terms; AC-L4 page-end telemetry; confirming AC-9c works from ADR-025's packed evidence | **Done:** T1–T7 and `deck_buffer_empty` are in the landed events contract (#399/#401) |
| **models-lead (launch, through head-bizops)** | Confirm Calibration and AC-9c readouts work from ADR-025's packed evidence (ADR-025 C7) | Confirmation, not a blocker |
| **app-manager (launch)** | Writes the launch device checklist (§9.4 launch runs L1–L4) | Before the launch device run |

## 12. Risks

- **200 ms is a launch MUST with no interim bar** (operator, 2026-10-20). A miss blocks launch, and
  nothing measured in the repo is close yet (§6).
- **Cellular is gated** (D3 decided). If a network hop stays on the critical path, cellular p95 may
  miss even when Wi-Fi passes. That is why eng's constraints allow a device-held first page (§10.7).
- **Freshness and storage fight each other.** Tighter bounds mean more rebuilds, and more rebuilds
  mean more writes (§10.4) and more contention on the single worker (§10.3).
- **The fast path can lose its cache at the worst time.** Under P23, cache data is shed first under
  disk pressure. While it rebuilds, taps fall back to the fresh path (AC-11b) and miss the 200 ms
  gate.
- **Small sample.** About 8 active users means p95 gates may take weeks to reach n ≥ 40. The
  TestFlight checklist carries the decision until then.
- **The freshness work can cost speed.** With AC-L3, the tap path makes no platform call, so the
  background floor has to keep rosters inside the bound. When it hasn't, the §5.5 U2 fallback shows
  the gate-miss state, and the tap misses the gate.
- **The P41 `/generate` caller.** The hook is built and on main (`backend/roster_refresh.py:123`,
  #378), so the hook-slip risk is closed. What remains is the caller in trades-eng's server stack
  (`scope-eng-200ms.md:15-16`). If it misses the 2026-11-06 binary, the Q1 aging-roster gap stays
  open at launch. I-2 still blocks sends on moved assets (via the send alert); likes aren't blocked
  at launch.
- ~~Background replenishment is paused~~ **Not a 200 ms ship gate (head-product, 2026-10-25).** It is #361's
  S3 deferral, returning after C2 and the self-renewal fix (`daily-tick-fix/scope.md:42,69-71`).
- **Page-end misses** (AC-L4). With zero misses allowed, a slow page N+2 build under load or an
  offline gap must not leave the user facing a wait. Only end-of-deck and offline are permitted
  outcomes; neither is "finding more".
- **Roster freshness is capped by user action** (platforms-pm R7, pending E2). With no headless
  Sleeper roster reads, a prepared deck is often past the roster bound by the time it's tapped.
  Under P40 there is no refetch on the tap, so the §5.5 U2 fallback (a gate miss) shows more often
  than a scheduled refresh would allow.
- **Calibration contamination** (models-lead R.b, AC-9e). A fast path changes which cards reach
  `deck_impressions`, which Calibration's current arm samples while round 3 runs to 2026-11-05.
  Without the serve-path tag and pinned sampling (or holding the fast path), the round-3 grades stop
  measuring the engine they name.
- **Stage-6 undercount** (analytics-lead R3). A prepared, cached or joined serve that skips the job
  would emit no `trades_generated`. AC-1b, or an `/an-funnel` amendment, must land before the build.
- **Prepared inventory is unproven in production.** Two failed canaries, rollout off
  (`prepared-trade-inventory/release.md:37-39,90-93`).

## 13. Product calls recorded at the review fold-in (trades-pm decision, 2026-10-15)

head-product (2026-10-15): "Fold them in." These calls settle points the reviews left to trades-pm:

1. **Withdrawn fronted card:** ux-lead F-4's structure with design-lead 4's treatment (§5.4).
   design-lead owns the visual spec.
2. **"Updating" placement:** the PRD pins the seven shared constraints (§5.4). The exact slot is D11.
3. **Like on a moved asset** (post-launch, AC-6b; at launch likes aren't blocked, head-product, 2026-10-26): no like recorded, no match created, the card withdrawn in place, and
   the disposition set (I-3). D-170 stays scoped to the calculator queue. Sends are blocked on the
   card with platforms-pm R4's contract (§5.3, AC-6a, AC-6b).
4. **D4:** serve-and-refresh stays the proposal, with design-lead and ux-lead support (F-3, F-4, F-6
   pinned).
5. **D10:** the proposal becomes ux-lead's recommendation (§4.1). It amends D-171, so it is still
   the operator's call.
6. **Roster freshness:** met by user-triggered refresh. No scheduled or headless Sleeper roster reads
   beyond today's pattern until E2 (§5.1, §10.3). *Amended by head-product P40, 2026-10-24:* the refresh runs
   off the tap path (session start, app foreground, and the P41 kick; Trades focus is a post-launch
   candidate, head-product 2026-10-25), never on the search tap or the first-page serve.
7. **Send seam:** the deck (`TradesScreen`), match and awaiting cards (`TradeCard`) and the
   calculator (`InLeagueCalculator`), all through `SendInSleeperButton` (§5.3).
8. **Dependency:** `NEXT.md` 0f (the `isdigit()` G-030 trap on the Sleeper propose route) lands before
   or with I-2 (Handoffs).
9. **head-product P40, 2026-10-24 (recorded here).** AC-L3 governs over §5.2 exception 1. The
   build follows AC-L3 with the §5.5 U2 fallback; head-eng asked Product to pick one, and trades-eng
   is already building to AC-L3.
   - The background floor refreshes the viewer's roster off the tap path, on app foreground, Trades
     focus and session-init, never on the search tap or the first-page serve.
   - If the floor has failed and the roster is past its bound at tap, those cards aren't shown. The
     honest gate-miss state shows while the floor refreshes, and the tap counts as a gate miss.
   - I-1 and I-2 still hold, and the first-page request makes no platform call.
10. **head-product P41, 2026-10-24 (recorded here): a non-blocking floor kick.**
    - **Background:** head-eng ruled trades-eng's Q1 under P40. A roster that ages past the 5-minute
      bound with no failed refresh is served, because the withhold needs "floor failed" AND past
      the bound. A user sitting on Trades with no foreground or focus event would get cards checked
      against an aging roster.
    - **Ruling:** when a tap finds the viewer's roster past its bound and the floor hasn't failed,
      serve as now AND start a background floor refresh. The tap never waits on it, so AC-L3 holds.
    - If the refresh shows a roster change, affected cards are withdrawn in place (U2), and the next
      page is fresh.
    - Contract v0.4's withhold rule is unchanged: floor failed plus past bound means withheld, with
      the gate-miss state.
    - **Withdrawal timing (head-product, 2026-10-24): option (a) is chosen.** Withdrawal happens at
      the client's next whole-deck response or focus/revalidation, not instantly, and I-2 blocks
      actions on the stale fronted card until then. Pass A withdraws only on whole-deck responses
      (`mobile/src/utils/tradePages.ts:52-59` (`isWholeDeck`) and `:87-111` (`mergeDeckPage`), on `feat/trades-200ms-mobile` @ `e01c7831`). No client or API change for launch.
    - **At launch (W-AC-L5),** I-1 is log-only, so the withdrawal effect waits for strict mode. I-2
      blocks sends, via the send alert; likes aren't blocked at launch.
    - **Option (b)**, a `roster_refreshing` field plus one `/status` poll, is a first-update
      candidate (post-launch).
    - **Dependency:** P41 needs platforms-eng's `maybe_refresh_async` hook, due about 2026-11-01.

## 14. Product calls recorded at the launch revision (trades-pm decision, 2026-10-20)

1. **Prefetch threshold (AC-L4):**
   - When page N becomes the current page (its first card fronted), page N+1 must already be in the
     device's deck, and the request for page N+2 starts then. That keeps at least one full unseen
     page ahead.
   - Pages 1 and 2 are pre-built together.
   - Pages append behind the current card with no reorder and no jump (§4.7).
2. **No "Finding more" card in the build.** A guard asserts that no such component or copy exists on
   the Find a trade path (§9.1).
3. **Exhaustion is not "finding more":**
   - Genuine exhaustion shows **head-product P30's final card** (which superseded the earlier
     "existing end-of-deck tally" call): only when every candidate has been seen, never while a
     page is pending, with no Like or Pass.
   - Offline uses the Screen-states offline state.
   - The only permitted wait card is U5's "Building your first trades". It counts against p95, and
     its design target is that it never shows.
4. **AC-L4's measure:** zero page ends without the next page in the deck, across all test sessions.
   Telemetry is `deck_buffer_empty` (granted in ruling 30), which replaced the R5 request (§15).
5. **The hidden ms readout** is specified in §9.5. head-eng decides the build.
6. **D13, adopted; accepted (head-product P33, 2026-10-20):** remove the deck's "Find more trades" once U3 ships.
   Retry stays only in the error and offline states, and `trades.find-btn` leaves table A.
7. **D14, decided; accepted (head-product P33, 2026-10-20).** D14(a) supersedes P30's "opens the
   targeting builder":
   - (a) "Adjust" opens the deck's preferences, and the search runs in place under the §4 clock.
   - (b) The D-171 tally stays on the P30 card as one chalk-dim line. P36 amends this: it is
     suppressed at 0 · 0 · 0.
   - (c) No third action or notice; new candidates appear on the next search.
8. **P30 copy (head-product P36, 2026-10-23).**
   - The strings are in §4.7 and are pending operator §6.
   - P30's original wording ("You've seen every trade we have for now." / "Adjust what I'm looking
     for") is retired in favour of marketing-lead's p30.head and p30.cta1.
   - marketing-lead-copy.md classes p30.head/p30.cta1 as voice swaps (not listed in its §6); head-product to reconcile.
9. **Dates (launch-plan-1118.md, relayed 2026-10-23).** Launch is **Wed 2026-11-18**, and the binary
   is **feature-complete on 2026-11-06**. The P30 copy above ships in that binary.

## 15. Reconciliation with main (2026-10-25)

This branch merged `origin/main` @ `db7425d4`. The eng contracts landed through #356, #361, #378,
#382, #399 and #401. Each row below says where this PRD's text differed from main, with file:line
on main, and whether this PRD **aligned** (main is the shipped contract) or **kept** its text as a
product requirement main doesn't yet meet, with the owner. Main's docs were not edited.

| # | Topic | This PRD (before) | Main (file:line) | Resolution |
|---|---|---|---|---|
| 1 | AC-L4 telemetry | R5 request: a `next_page_ready_at_end` prop | `deck_buffer_empty`, granted in ruling 30 (`docs/business/analytics/2026-10-20-time-to-suggestion-events.md:31`) | **Aligned.** §4.6, AC-L4, §4.7, §14 and scope §1 now cite `deck_buffer_empty` |
| 2 | `serve_source` values | prepared / cached / joined / fresh | R2: `device` / `page` / `cached` / `joined` / `fresh` (`…-events.md:29`); R3 adds `prepared` (`:32`) | **Aligned** (§4.4, AC-1b) |
| 3 | `freshness_state` values | fresh / updating / withdrawn_some | `fresh` / `updating` (`…-events.md:29`) | **Aligned.** The restated table is removed (§4.6) |
| 4 | R2b timeout | "the addendum states the threshold" | **10,000 ms** from the tap (`…-events.md:30`) | **Aligned** (cited in §4.6) |
| 5 | AC-L1 exclusions | T1–T6 | **T7**: `prefs_changed_strip` excluded from the cells (`…-events.md:80-81`) | **Aligned.** AC-L1 adds T7 |
| 6 | Team Review entry | Not listed | `source=team_review`, out of the AC-L1 cells for launch (`…-events.md:56`) | **Aligned.** §4.1 other arrivals: measured, not gated |
| 7 | P30 end card | P36 copy ("You've seen every trade for now." / "Adjust your search"). D14(a): "Adjust" opens the **deck's own preferences** and the search runs in place | `scope-eng-200ms.md:308-309`: the old P30 copy, with "Adjust…" opening "**the targeting builder**". The events doc labels `end_card_adjust` with the old string (`…-events.md:55`) | **Kept** (head-product, 2026-10-25). D14(a) stands: "Adjust your search" opens the deck's own preferences, and the search runs in place. P36 sets the copy. **Owner: trades-eng via head-eng**, aligning `scope-eng-200ms.md` §6.5 and confirming what #363 does. analytics-lead updates the label only; the `end_card_adjust` value is unchanged |
| 8 | Unseen-card evidence | DEC-2 "narrow rows, not full evidence; displayed cards keep full evidence"; §10.4 floated "displayed cards only" | **ADR-025, Accepted:** never-served pre-builds write nothing (`adr-025…md:25`); full rows on view, the first 30 and the C8 archive (`:27`); everything else packed (`:54`), about 64 B per card (`:75`); narrow rows are the fallback (`:109`). "Displayed cards only" was rejected (`:118`) | **Aligned** (§10.4, D7, AC-L8, AC-11, scope §2) |
| 9 | P23 byte budget | "Still open" (D7) | ≤ about 0.2 MB compressed per active pair; about-250 MB page-store ceiling; measured numbers before the flag flips (`scope-eng-200ms.md:349-355`) | **Aligned.** D7's budget is decided by head-eng |
| 10 | Floor triggers | App foreground, **Trades focus**, session-init, and the P41 kick | Session init on app open (`scope-eng-s0-fetch.md:63`) and foreground (`:64-65`, 60 s throttle `:66`), plus the P41 kick (`:71-107`). **No Trades-focus trigger**, and no mobile change | **Aligned (launch decision, head-product, 2026-10-25).** Main's triggers cover it for launch: session start, foreground with the 60 s throttle, and the P41 kick. I-2 still blocks any stale send. A Trades-focus trigger would add Sleeper calls (429 risk) and a mobile change before the freeze, for little gain. Trades focus is removed from the launch lists in §5.1, §5.5, AC-L3, §10.3, §10.7 and scope §6, and marked a **post-launch candidate**, revisitable from R2b data |
| 11 | P41 hook timing | §12: "depends on the hook, about 2026-11-01" | Built: `backend/roster_refresh.py:123` (#378; `scope-eng-s0-fetch.md:71-107`), with no-ops for an open 429 circuit, a 60 s retry cooldown and in-flight | **Aligned.** The §12 risk is now the `/generate` caller only (`scope-eng-200ms.md:15-16`) |
| 12 | Check-error serve state | No cards → the honest gate-miss state, naming its reason; "Updating" only while cards show (§5.4) | "The check errors → **'Updating', no cards**" (`scope-eng-200ms.md:283`) | **Kept** (head-product, 2026-10-25). A bare "Updating" with no cards fails the U rules and the operator's checklist ("a blank, a spinner or 'Finding more'"). The honest gate-miss state shows. **Owners:** trades-eng and ux-lead |
| 13 | Prefetch rule | Pages 1–2 pre-built; request page N+2 when page N is fronted | Pages 1–3 stored; `ready_cards_after_prefetch ≥ prefetch_remaining + page_size` (`scope-eng-200ms.md:294-297`) | **Aligned in outcome.** Main's rule keeps at least one full unseen page ahead, which meets the trades-pm requirement. AC-L4's zero-miss measure stands, and the guard asserts main's rule |
| 14 | U5 card in the p95 | "Counts against the p95" | As R2b only if no card arrives; otherwise R2 carries the wait (`scope-eng-200ms.md:323-324`) | **Aligned.** Same effect; no text change |
| 15 | R3 emission scope | Exactly one per user-visible deck, whatever `serve_source` (AC-1b) | "Emits once per `deck_job_id`, only for requests that carry a `search_id`" (`scope-eng-200ms.md:18-19`); the binding rule restated at `…-events.md:32` | **Kept, to confirm** (head-product, 2026-10-25). head-eng is asking trades-eng whether every launch-binary deck request carries a `search_id`. **If it does, item 15 closes with no analytics change.** Owners: trades-eng via head-eng; analytics-lead |
| 16 | Replenishment | "Restore, bounded by DEC-2, before the 200 ms build ships"; "U2's floor and U3's prefetch depend on it" | #361: tick step 7 is a hard skip ("deferred: C2") until C2 and the self-renewal fix (`docs/plans/daily-tick-fix/scope.md:42,69-71`). On main, U2's floor is S0 (#378) and U3's pages are P1/P2 (`scope-eng-200ms.md:86-89`), not weekly replenishment | **Aligned** (head-product, 2026-10-25). Product's precondition was "before the 200 ms build relies on it". On main the build doesn't: U2's floor is S0 (#378), and U3's pages are P1/P2. **Replenishment does not gate the 200 ms ship.** It returns after C2 and the self-renewal fix, per #361. It is removed as a ship precondition (scope §5) and as a proof precondition (§9.6) |
| 17 | Device-held page age | Within the U2 bounds (P32) | Max age 300 s, a client constant plus a cross-client invariant (`scope-eng-200ms.md:21`) | **Aligned** (300 s = the 5-minute bound) |
| 18 | AC-9 page contract | AC-9b's differential test | `assert_page_is_top_n` / `assert_prefix_stable` (#382; `eng-evidence-contract.md:106-142`) | **Aligned.** AC-9b cites it |
| 19 | Calibration decks and R3 | Not stated | `grading_refresh` decks emit no `trades_generated` (`…-events.md:32`) | **Aligned.** Consistent with AC-1b's "user-visible trade deck" |

## Decisions needed (operator)

| ID | Decision | Proposed |
|---|---|---|
| D1 | Which taps the 200 ms gate covers | The organic deck from every table A control (AC-L1). Pinned, targeted and fair-sweep searches are measured, with a target set after the baseline. |
| D2 | Are cold-launch taps (before session-init completes) held to 200 ms? | **Decided in part (2026-10-20):** a new account's first tap after onboarding is gated (AC-L7, U5). Other cold-launch taps are reported separately; their gate stays open. |
| D3 | Is cellular held to the same p95? | **Decided (2026-10-20): yes.** AC-L1's cells include cellular at p95 ≤ 200 ms. |
| D4 | The stale-deck rule | Serve-and-refresh with the two hard exceptions (§5.2). It is supported by design-lead and ux-lead, with ux-lead F-3, F-4 and F-6 pinned (trades-pm decision, 2026-10-15). Alternatives: block, or serve-with-label. |
| D5 | The §5.1 freshness bounds | As proposed in the table. |
| D6 | May the first card differ from the full deck's top card (progressive order)? | No by default. A first card that isn't the full deck's best-first card is a model-behavior change. It needs a model-change packet (PR #331, `.claude/skills/pm-technical/references/model-change-packet.md`) and models-lead's sign-off before it ships (AC-9d; models-lead R.b). |
| D7 | Storage budget for a faster path, and how unseen candidates are stored | **Decided.** <br>**Storage form (DEC-2, operator 2026-10-20):** landed and Accepted as **ADR-025**. Never-served pre-builds write no evidence; full rows go to viewed or acted-on cards, the first 30 and the C8 archive; everything else is packed; narrow rows are the fallback. <br>**P23 budget (head-eng, `scope-eng-200ms.md` §7):** ≤ about 0.2 MB compressed per active pair, and an about-250 MB page-store ceiling. Measured numbers replace the estimates before the flag flips. <br>analytics-lead and models-lead confirm their readouts work from packed evidence (ADR-025 C7). |
| D8 | Does the new target supersede the 3 s goal in `trade-search-latency/research-plan.md` §4? | **Decided (2026-10-20):** 200 ms supersedes the 3 s goal and the earlier 250 ms. It is the tap-to-first-card KPI and a launch MUST, and that thread's non-negotiables stay. |
| D9 | Must every fast-path card pass `deck.quality_filters`? | Yes, evaluated at display-time inputs, with no silent skip (AC-9a; models-lead R.b). |
| D10 | Should a table B control (Home tile, League, Matches, calculator row) start a search and show cards directly, instead of opening the builder? | **Yes for onboarded users** on the Home tile, League ×2 and Matches. First-run keeps the builder (onboarding-pm signs off). The stack is builder → pushed deck, using `push`, not `navigate`. The calculator row stays navigation-only and is relabelled (design-lead; copy via head-product → marketing-lead). A Home tile preview is an optional follow-up (design-lead). **The operator's call, because it amends D-171.** Alternative: keep D-171 and relabel table B (ux-lead, design-lead). |
| D11 | Where does the "updating" state sit? design-lead proposes a trailing header-row label; ux-lead proposes the progress-strip slot | **design-lead and ux-lead settle it jointly before any UI build**, within §5.4's seven shared constraints (trades-pm decision, 2026-10-15). |
| D12 | Calibration integrity before the round-3 read (2026-11-05): hold any fast path until then, or pin Calibration's current-arm sampling to the fresh path? | Either satisfies AC-9e (models-lead R.b). Impressions carry a serve-path tag in both cases. **Proposed:** pin the sampling to the fresh path if a fast path is ready before 2026-11-05; otherwise the date passes first. models-lead confirms; the operator decides. |
| D13 | Remove the deck's "Find more trades" button once U3 ships? | **Adopted (trades-pm decision, 2026-10-20; accepted (head-product P33, 2026-10-20)).** Removed once U3 ships, because a "more" button that restarts the search is mislabelled when the deck never ends (ux-lead, launch). Retry stays only in the error and offline states. `trades.find-btn` leaves table A, TF step 2 checks that it's absent, and the §9.1 guard asserts it. |
| D14 | P30 open items (raised by ux-lead and design-lead) | **Decided (trades-pm decision, 2026-10-20; accepted (head-product P33, 2026-10-20)):** <br>**(a)** (supersedes P30's "opens the targeting builder") "Adjust your search" (P36 copy) opens the deck's own preferences (fairness and filters), and the changed search runs in place. It's search-starting, measured under the §4 clock (AC-L1 cells). <br>**(b)** Keep D-171 ruling 4's end-of-deck tally on the P30 card as one chalk-dim line (design-lead places it); retiring it would amend an operator ruling. **Amended by head-product P36 (2026-10-23):** suppressed at 0 · 0 · 0. <br>**(c)** No third action and no notice: new candidates behind the P30 card appear on the next search. P30's copy and actions are unchanged. |
| W-AC-L5 | **Waiver of AC-L5's display half at launch.** **Decided** | **Operator sign-off** (head-product's session, 2026-10-26, relayed by head-product): "I sign off on W-AC-L5: launch with the ownership filter in log-only mode, sends still blocked." <br>**Background (head-eng):** S0 (PR #367, still OPEN, head `bc25dd1d`) is the I-1 ownership filter at serve. QA strict mode served only 2 of 6 cards because of stale roster rows. Launch runs the filter **log-only**, and strict mode follows after launch, once C-b and the full stale-row fix land, on models-lead's sign-off. <br>**Conditions:** <br>(1) **sends** on a moved asset are blocked at action time, with a readable message in the send alert. Likes (AC-6b) and the on-card message (AC-6a placement) follow after launch. I-2 isn't live today on any platform (platforms-eng audit, `docs/plans/org-bringup/reports/platforms-eng.md` § "I-2 status"); <br>(1b) **I-2 (platforms-eng, server-side, target about 2026-10-31) must be live before the operator's 200 ms device run (§9.6);** <br>(2) analytics-lead reads the `[i1]` would-drop rate in launch week (2026-11-18 to 11-25, readout 11-26); <br>(3) strict mode follows after launch. <br>**Knob discrepancy (recorded, not resolved):** on #367 @ `bc25dd1d`, `backend/database.py:2971` seeds `trade_i1_mode` with **default 2.0 = strict** (1 = lenient, check and log and serve every card; 0 = off; a deploy-free knob). Launching log-only therefore needs `trade_i1_mode` = 1 set in prod `model_config` at or before launch, or the default changed. Owner: head-eng → release-lead/models-eng. <br>**Exit criteria:** strict mode (`trade_i1_mode` = 2) ships after C-b and the full stale-row fix land, with models-lead's sign-off, informed by the 11-26 would-drop readout. AC-L5 then returns in full. |

## Handoffs

- **head-eng: background replenishment, NOT gating** (head-product, 2026-10-25). It returns after ADR-025's
  C2 and #361's self-renewal fix, on its own schedule (§15 item 16).
- **trades-eng, via head-eng:** align `scope-eng-200ms.md` §6.5 to D14(a) and the P36 copy, and
  confirm what #363 does (§15 item 7). Also confirm that every launch-binary deck request carries a
  `search_id`; if it does, §15 item 15 closes with no analytics change.
- **trades-eng + ux-lead:** the check-error state with no cards shows the honest gate-miss state,
  never a bare "Updating" (§15 item 12).
- **Trades-focus floor trigger: closed for launch** (head-product, 2026-10-25: main's triggers cover it). It
  is a post-launch candidate, revisitable from R2b data (§15 item 10).
- **W-AC-L5 (operator, 2026-10-26):**
  - **platforms-eng (through head-eng):** I-2, server-side, target about 2026-10-31, **must be live
    before the operator's 200 ms device run (§9.6).** It is a W-AC-L5 condition. Scope: the live
    player-ownership check in the Sleeper, ESPN and MFL propose cores plus overhaul and the
    calculator queue, returning 422 `asset_not_owned` / `counterparty_asset_not_owned` with a
    readable `detail` (`docs/plans/org-bringup/reports/platforms-eng.md` § "I-2 status").
  - **analytics-lead:** read the `[i1]` would-drop rate in launch week (2026-11-18 to 11-25), with
    the readout on 2026-11-26.
  - **models-lead (via head-bizops):** sign off on strict mode after C-b and the full stale-row fix
    land.
  - **head-eng → release-lead / models-eng:** set the `trade_i1_mode` launch value. #367 seeds a
    default of 2.0 (strict) at `backend/database.py:2971` @ `bc25dd1d`, so log-only needs = 1 in
    prod `model_config` at or before launch, or the default changed.
- **analytics-lead + trades-eng (W3 finding):** 10 taps had no source, and 9 of them got no card
  (§6). Investigate it as an instrumentation or flow gap; this PRD doesn't diagnose it.
- **head-eng (launch, through head-product):** the critical-path build plan for 200 ms against
  §4.7, §5.5, §8.1 and the §10.7 constraints. The build resumes on the 200 ms path (operator,
  2026-10-20). Also the §9.5 readout build and how the operator's device gets the Testing gate.
- **head-eng → trades-eng, models-eng:** choose the approach (§10.1) against §4, §5 and §8; write
  HLD/LLD; return the latency budget split and the storage footprint (AC-11, AC-L8).
  - Also F-1 and AC-L2: no animated push or transition on search-starting paths.
  - Also F-2: the Home tile's target inconsistency (`HomeHub.tsx:397`). It is live today,
    independent of this PRD (ux-lead).
- **platforms-eng (through head-eng):**
  - the `maybe_refresh_async` hook is **built** (#378). What remains is trades-eng's `/generate`
    caller (§12);
  - implement I-2 per platforms-pm R1–R5 and R8;
  - confirm what each send path does today when its roster fetch fails (R3);
  - **land `NEXT.md` 0f (the Sleeper propose route's `isdigit()` G-030 trap) before or with I-2**
    (platforms-pm N1).
- **analytics-lead:** **done (#399/#401):** the events contract is landed and the W3 baseline is in
  §6. Still owed: receive the new `sleeper_send_failed.error_code` value (platforms-pm R4).
- **The build:** the events addendum is **done** (`docs/business/analytics/2026-10-20-time-to-suggestion-events.md`, #399/#401).
- **design-lead:**
  - the visual spec for the withdrawn card and the status line, plus their `components.md` row;
  - the push motion (AC-2b);
  - D11 jointly with ux-lead;
  - the calculator-row relabel, and the optional Home tile preview (D10).
- **ux-lead:** D11 jointly with design-lead, and the VoiceOver announcement spec (design-lead 7).
  **Launch, through head-product:** U1's placement, in place on the current surface or an instant
  non-animated route.
- **design-lead (launch, through head-product):** the U1–U5 visuals, including the "Building your
  first trades" card.
- **analytics-lead (launch):** done for events (contract landed in #399/#401). Confirm that AC-9c
  works from ADR-025's packed evidence. Update the contract's P30 label (§15, item 7).
- **models-lead (launch, through head-bizops):** confirm that the Calibration and AC-9c readouts work
  from ADR-025's packed evidence (C7). A confirmation, not a blocker.
- **app-manager (launch):** write the device checklist: the §9.6 scripted two-device session (the
  AC-L1 proof), plus the §9.4 launch runs L2–L4b (U3, P30, U5, U2 and K-F5).
- **onboarding-pm:** D10's first-run limit, F-4's guide interplay, and the P12 privacy-label check
  for `network_type` and `search_id` ("check, likely no change"; App Store Connect is the
  operator's).
- **marketing-lead (through head-product):** copy for the §5.4 lines and the calculator-row relabel.
- **head-eng → models-eng, plus analytics-lead:** AC-9c.
  - A shadow or offline recompute at a low sample rate, off the critical path (eng chooses how).
  - Path-tagged filter counts on both paths.
  - A measurement of the engine's own re-run churn: two fresh builds from the same inputs, a few
    minutes apart.
- **head-eng → trades-eng:** the serve-path tag on impressions (AC-9e; scope.md §2) and the
  display-time filter pass with the unknown-lineup fallthrough (AC-9a, I-6).
- **models-lead:** sign-off through the two-line packet route (R.a (ii)), D12, and any AC-9d model-change
  packet if approach D is pursued. Lazy evidence and any engine swap also need models-lead.
- **platforms-pm:** log R7 in the platform risk register. Any future pending-offer read goes to the
  register first (N2). **#351 K-F5:** after FTF completes an add/drop, the viewer-roster refresh runs
  immediately and affected cards are withdrawn in place (U2, AC-L5). #351's build and this PRD's
  stay aligned on it. K-F5 activates when #351 D1 ships; not a launch gate.
- **DB-storage task + head-eng:** take the §10.4 arithmetic. head-eng sets and accepts the byte
  budget against H1–H3 (#337; DEC-7) before any rollout (P23).
- **release-lead:** merge this plan PR on the operator's go. Plan only, no code.
- **Operator:**
  - decide the open decisions: D1, the rest of D2, D4–D6, D7's budget number, D9, D10 (it amends
    D-171) and D12, plus E2, which gates any headless Sleeper roster reads. D3 and D8 are decided.
    D11 is settled by design-lead and ux-lead;
  - run the §9.4 checklist once a build exists, including approving and cancelling the step 13 test
    sends.

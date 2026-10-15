# PRD — Time to trade suggestion: first card within 250 ms, and only up-to-date offers

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

---

## 0. What this PRD decides, and what it leaves open

It pins three things: what the 250 ms clock measures (§4), what "up to date" means for each input and
what happens when an input is past its bound (§5), and the acceptance criteria a build must pass (§8),
including the operator TestFlight checklist (§9.4), the only runtime evidence mobile gets under D-056.

It does not choose between prepared inventory, a device-resident first page, faster generation,
progressive publication or a transport change. §10 lays those out with their costs. It also does not
set the storage budget; that belongs to the parallel database-shrink task, and §10.4 gives it the
footprint arithmetic.

**The headline finding from the evidence:** no measured path in the repo comes within an order of
magnitude of 250 ms. The fastest backend-only number is a **1.081 s** first-30 durable publication
from a *prepared* 936-offer inventory, measured locally on SQLite with no network and no phone
(`docs/plans/prepared-trade-inventory/release.md:161-165`). Production's last measured interactive
worker median is **61.094 s** (n=7, 2026-09-20/21;
`docs/plans/trade-search-latency/execution-20260921/infrastructure-and-precompute.md:13-23`). No
tap-to-card measurement has ever been taken on a phone (§6). The 250 ms target cannot be met by
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
The operator's new number is **12× tighter** and adds a second, independent requirement: the offers
must be up to date. Speed and freshness pull in opposite directions. The fastest card is one computed
earlier, and a card computed earlier can be stale. G-075 shows this is not hypothetical. Headless
builds offered players who had moved: 11–12 of 12 teams differed against live Sleeper, with 76–139
player moves per league (`living-memory/GOTCHAS.md:98-102`).

## 2. User story

As a dynasty manager who taps **Find a trade**, I see a real trade card within a quarter second,
with enabled Like and Pass controls. Every player and pick on it is actually on the rosters it
claims, priced on current values and on the rankings I've given the app. If the app is still
catching up on something, it tells me, and it never asks me to act on a trade that can't happen.

**Hypothesis (to be measured, not assumed):** cutting tap → first actionable card to ≤ 250 ms raises
the share of Find a trade taps that reach a trade opinion (like or pass) and cuts abandoned taps.
The readout uses existing events: `find_trades_tapped` → `trade_card_viewed` → `match_swiped` /
`trade_proposed`. See `backend/analytics_queries.py:414,428` for the funnel stages. Impact is
unknown until the baseline lands; no lift is promised.

## 3. Threads this builds on (status checked in `docs/plans/README.md`, 2026-10-15)

| Thread | Index status | What it means for this PRD |
|---|---|---|
| `trade-search-latency/` | **not indexed in README**. Own `status.md`: in-progress, 2026-09-21 | Source of the 3 s goal, the measurement rules this PRD reuses (skeletons don't count, report cold/warm separately, no offer caps; `research-plan.md:64-92`), and #303's committed first-30 publication. Its remaining qualification backlog is still open. This PRD supersedes its **target** (3 s → 250 ms), not its non-negotiables. |
| `prepared-trade-inventory/` | **active; canary repair** · 2026-09-22. Own `status.md` is 2026-09-23 | #305–#307 merged (`3bb981ed`). Preparation and adoption ship dark behind `model_config` `prepared_trade_inventory_enabled` = 0 (`docs/config-reference.md:7-17`). Last production readback: 0, on 2026-09-23 (`prepared-trade-inventory/release.md:154`). Production state since then is **unverified**. `baseline-request.md` Q0 asks for a readback. It covers default discovery only; pinned and custom searches keep their own paths (`plan.md:9`). Adoption is skipped for replenish, pinned, intent and force jobs, and needs exclusive owner-bilateral revision, value core off, and the knob = 1 (`backend/prepared_trade_runtime.py:86-96`). |
| `app-open-trades/` | **not indexed in README**. Own `status.md`: implemented 2026-09-20 | Session-init warm-up uses the saved fairness, so a later Find a trade can join it (`app-open-trades/status.md:5`). Its stated limit: it changes when work starts, not the 37–42 s fresh search (`:11`). |
| `trade-presentation-v2/` | **not indexed in README**. Flag `trades.presentation_v2` **false** | TodaysTrade / Browse-all are dark. Out of the 250 ms gate unless the flag flips (§7). |
| `deck-quality-filters/` | **not indexed in README**. Shipped #328 `71a02541`, flag `deck.quality_filters` **true** (D-207) | Filters run in `_run_trade_job` after presentment. Prepared inventory is explicitly **out of v1 scope** (`deck-quality-filters/scope.md:14`; `living-memory/DECISIONS.md:14`). A fast path that adopts a prepared deck would skip them. That is the §10.5 quality-vs-speed trade-off. |
| `db-storage-reduction/` | released 2026-09-15 | Disk is 5 GB, about 9 KB of physical storage per deck record, roughly 350,000-record headroom as of 2026-09-15 (`db-storage-reduction/release.md:15-19,50-60`). Feeds §10.4. |

Four of the six threads have no row in `docs/plans/README.md`. That gap is noted, not fixed here (this
worker may write only one README row).

## 4. The metric: what "250 ms" measures (pinned)

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
| Deck **Find more trades** (`trades.find-btn`) | `TradesScreen.tsx:7601-7614`, `:7803-7816` → `handleFindTrades` `:1213` | model deck | A repeat search from inside a deck |
| In-deck retries | error retry `TradesScreen.tsx:6403`/`:9066`, prefs strip `:6991`, summary unpin `:3915`, search-all `:3933` | model deck | Same choke point (`:3269-3354`) |
| Handoff auto-runs | League Summary Offer/Target `screens/LeagueSummaryScreen.tsx:1281-1300`; Usage Trends "Trade" / "Find a trade for {player}" `components/UsageTrendCard.tsx:159`, `UsageStatsTable.tsx:169`, `UsageLeagueList.tsx:96` → `screens/UsageTrendsScreen.tsx:251-268`. Consumed at `TradesScreen.tsx:3195-3249` | pinned / partner-scoped model deck | Not organic. A Usage Trends handoff with no opponent dispatches **nothing**: the model auto-run needs a scoped opponent unless the origin is the calculator (`TradesScreen.tsx:3319-3347`). It lands on the builder. |
| Dead or dark today | calculator merged `onFindATrade` `screens/TradeCalculatorScreen.tsx:830-871` (needs `calc.inline_home` off); TodaysTrade `hooks/usePresentationDeck.ts:76` (flag off); `TradeFinderHubScreen` (not registered, `navigation/TabNav.tsx:38,446`); first-run auto-start `TradesScreen.tsx:2385-2404` (skipped while results-push is live, `:2392`) | — | Join table A if they come back |

**Table B: navigation-only controls labelled Find a trade (no search today)**

| Control (testID) | file:line | Lands on |
|---|---|---|
| Home tile (`home.tile.find-trade`) | `mobile/src/components/home/HomeHub.tsx:391-398` | Acquire builder |
| Home list row (when `nav.home_hub` is off) | `mobile/src/screens/HomeScreen.tsx:19,44` | Acquire builder |
| League Home (`league.action.find`) and the works-now button | `screens/LeagueScreen.tsx:624`, `:867` → `goFindTrade` `:473-476` | Acquire builder |
| Matches empty state (`matches.go-to-trades`) | `screens/MatchesScreen.tsx:1189` | Acquire builder |
| Calculator "Want ideas instead? Find a trade →" (`calc.find-a-trade`) | `screens/TradeCalculatorScreen.tsx:724-741` | Acquire builder (`popTo`) |

A table B tap is measured as tap → builder interactive. It is **not** a gate pass, because no trade
is shown. The operator asked for a card within 250 ms of hitting Find a trade, and from a table B
control the user needs a second tap to get one. Whether table B taps should start a search
themselves is a flow question for ux-lead and the operator (Decision D10).

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

A tap that ends in an honest **zero-results** state is reported separately as tap → empty state
(same clock). It is not a gate pass and not a failure.

### 4.3 Percentile and sample rules

- **Gate:** p95 ≤ 250 ms, per cohort cell (§4.4).
- **Also reported:** p50, p90, p99, the share of taps ≤ 250 ms, and counts of taps that never reach
  a card: error, abandoned (left the screen or backgrounded before a card), and timed out at 60 s.
  Abandoned and errored taps stay in the denominator of "share ≤ 250 ms". A fast median must not
  hide a slow tail (`research-plan.md:78`).
- **Sample floor:** a cell's p95 is reported only at n ≥ 40 taps. Below that, report n, max and the
  share ≤ 250 ms, and mark the cell "insufficient". (Production has about 8 users and 16
  user-league pairs with a qualifying deck in 14 days; `living-memory/TEST_LEDGER.md:200-201`.)
  The operator TestFlight checklist (§9.4) is the qualitative gate until telemetry reaches the floor.
- **Window:** the 14 days after the build ships, compared with the pre-ship baseline from
  `baseline-request.md`.

### 4.4 Cohorts (each reported separately; never blended)

| Dimension | Cells | Notes |
|---|---|---|
| Device | TestFlight iPhones (production backend) | iOS only. Record model and OS (already envelope columns: `device_type`, `os_version`, `app_version`; tracking plan `2026-07-17-tracking-plan-v2.md:141`). |
| Network | Wi-Fi · cellular · offline | Not in the envelope today; requested in §4.6. Both Wi-Fi and cellular are held to 250 ms unless the operator decides otherwise (Decision D3). |
| Launch state | **cold-launch tap**: first tap after a process start, before that session's session-init completes · **first tap** after launch, once session-init is done · **repeat tap** in the same session | Reported separately. Proposed: first-tap and repeat-tap cells are gated; the cold-launch cell is gated only if the operator says so (Decision D2). |
| Search type | organic · pinned/targeted · filled-canvas fair sweep | Organic is gated (D1). |
| Serve source | prepared / cached / joined in-flight job / fresh generation | Diagnostic, so a high cache-hit rate cannot hide a slow miss (`research-plan.md:78`). |

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

**Requests (need `analytics-lead`'s grant):** register in `backend/analytics_taxonomy.py`, and
classify in `analytics_queries.NON_INTENT_EVENTS` in the same commit as the emitter. Names are
proposals.

| # | Request | Why existing events can't answer it |
|---|---|---|
| R1 | A tap-time record from **every** table A control (and, for D10, every table B control), carrying a client-generated `search_id` and a monotonic tap timestamp. Preferred: widen `calc_find_a_trade_tapped` and `find_trades_tapped` with `search_id`, and fire `find_trades_tapped` at the tap rather than at dispatch. Alternative: one new NON_INTENT event `trade_search_started`. | `find_trades_tapped` fires only from TradesScreen's own controls (`analytics_taxonomy.py:604-613`), and on the push path it fires at dispatch. Handoff taps carry no search-starting event, and nothing correlates a tap with the server job. |
| R2 | New event `trade_first_card_shown` (proposed NON_INTENT, because it is a system outcome). Props: `search_id`, `ms_from_tap` (monotonic), `entry_point`, `search_type`, `launch_state`, `network_type`, `serve_source`, `freshness_state` (§5.4), `job_id`, `card_index`. A sibling outcome `trade_first_card_failed` {`search_id`, `ms_from_tap`, `reason`: empty / error / abandoned / timeout} unless analytics-lead prefers a `result` prop on R2. | No event marks first render with enabled controls. `deck_card_viewed` needs 500 ms of exposure, and `trade_card_viewed.ms_since_open` is `Date.now() - APP_OPEN_TS`, measured from JS bundle load (`mobile/src/api/events.ts:95,108-110`), not from the tap. |
| R3 | Server-side job timing on the existing `trades_generated` (or its successor): `first_publish_ms` (job start → first committed card), `serve_source`, the oldest input age at serve (§5.1), and the echoed `search_id`. | `gen_ms` is full-worker completion (`trade-search-latency/README.md:13`). The "first durable owner batch" time exists only as a log line (`docs/runbook.md:195-197`). |
| R4 | `network_type` (wifi / cellular / offline / unknown) as an envelope column stamped by the SDK. Not a prop, following the NULL-`platform` lesson (`tracking-plan-v2.md:218`). | Not captured anywhere today. |

No event may carry player ids, names or league-identifying values in props
(`docs/business/analytics/2026-07-17-tracking-plan-v2.md:183`).

## 5. What "up to date" means

### 5.1 Inputs and proposed bounds

The bounds apply **at the moment the first card is displayed**. "Age" means time since the input was
last confirmed against its source of truth. Bounds are proposals for operator approval (Decision D5)
and eng feasibility review.

| Input | Today (code) | Proposed bound at first-card display | Past the bound |
|---|---|---|---|
| **Viewer's roster**, including trades just executed on the platform and add/drops | Sleeper rosters are fetched live at every session-init: cold launch, or foreground after a real background, throttled to 60 s (`mobile/src/state/useSession.ts:65,369`; `backend/session_input.py:42-80`). ESPN and MFL come from the DB import. `/api/trades/generate` never refetches. **Rosters are not in the job cache key or signature, so a cached deck up to 30 min old is still served after a roster change** (`backend/server.py:3489-3526`, `:23021-23024`; TTL `:2285`) | **≤ 5 min** since last confirmed against the platform. A change the app itself knows about (an in-app send accepted, a refetch diff) invalidates the affected cards immediately | **Refetch before display** (§5.2, exception 1). The tap counts as a gate miss, so the build has to keep this roster inside the bound proactively while Find a trade is reachable |
| **Partner rosters** | Same session-init fetch for Sleeper. `league_members` is also written by the background daemon (`server.py:22801-22835`). Headless builds read whatever is stored (G-075) | **≤ 5 min** | Serve-and-refresh. Filter against the freshest held roster; I-2 catches the rest before any action |
| **Viewer's rankings**: trio swipes, tiers, anchors, reorder, import, outlook and prefs | Every change invalidates jobs (`server.py:10119,10183,10969,11720,11907,12262,12483,20856,21062,21141`), which forces fresh generation | **Zero tolerance:** every change made before the tap is reflected, or the deck is past-bound | Serve-and-refresh with the "updating" state. Never presented as current |
| **Partner boards** (leaguemates' published rankings) | Member epochs fence dependent jobs (`server.py:9283-9294,9381-9384`) | Same as the viewer's rankings | Same |
| **In-app trade state**: passes, likes, awaiting, matched, standing offers | R4 exclusions are built once at job start (`server.py:7814-7818`). Dispositions are projected at every serve (`:3275-3352`) | **Zero tolerance** (I-3), projected at every display | Filter (already the case) |
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

**Proposed: serve-and-refresh, with two hard exceptions.**

- **Within every bound:** serve immediately.
- **Past a bound on partner rosters, rankings, values or in-app state:** serve immediately only the cards
  that pass the §5.3 invariants against the freshest facts the system holds. Show a visible "updating"
  state (§5.4) and start a refresh at once. When the refresh lands:
  - cards the user hasn't acted on are replaced or withdrawn;
  - the card on screen is never silently rewritten. If it became invalid it is withdrawn with an
    explanation, and if it is still valid it stays where it is;
  - historical likes and passes keep their original terms (`research-plan.md:70`).
- **Exception 1, ownership:** a card that fails the ownership invariant is never shown, at any
  staleness. Filtering is allowed; "show and fix later" is not. If the **viewer's** roster is past its
  bound, it is refetched before any card is displayed. Speed never outranks "never offer an asset
  you no longer own".
- **Exception 2, wrong math:** if the served model or config version, or the league's scoring or
  roster settings, changed since the deck was built, every card's valuation is wrong. Block: generate
  fresh, show the progress state, and count the tap as a gate miss.

**Alternatives (not proposed):**

| Rule | Behavior | Why not the default |
|---|---|---|
| Block | Never display a card from a deck past any bound; wait for fresh work | Honest but slow. Every stale tap misses 250 ms, and with a one-worker server the miss is tens of seconds (§6). |
| Serve-with-label | Display a past-bound deck with an "as of" label; refresh only when the user asks | Fast, but it pushes the freshness job onto the user, and the label alone doesn't stop invalid cards unless the §5.3 filters still run. |

### 5.3 Hard invariants (never relaxed, at any staleness)

- **I-1 Ownership.** No card is displayed with an asset the stated side no longer owns, per the
  freshest roster the system holds at display time. For the viewer's own roster, that roster is
  never older than the §5.1 bound.
- **I-2 Action-time revalidation.** Every outbound action is revalidated against the live platform
  roster before it is sent: a like that creates a match, and a send to Sleeper, ESPN or MFL. A
  failure blocks the action with a clear message. **Today this guard is incomplete.**
  - Sleeper `/api/trades/propose` reads live rosters only to resolve roster ids. It validates picks
    live (422 `sleeper_pick_not_owned`, `backend/server.py:19529-19590`) but does **not** check
    player ownership; it relies on Sleeper rejecting the write (502 `sleeper_write_failed`,
    `:19613`).
  - ESPN's pre-flight resolves teams and slots without an explicit player check (`:33126-33184`).
  - MFL only maps ids (`:32608-32617`).
  - A like that creates a match has no platform check at all.

  So I-2 is new work on each write path, and platforms-pm reviews it.
- **I-3 Dispositions.** Cards the user passed, already liked or has awaiting or matched are excluded
  at read time. The prepared-inventory design already projects these at adoption
  (`prepared-trade-inventory/plan.md:47`).
- **I-4 No silent rewrite.** A displayed offer's terms never change under the same identity
  (`delivery.md:81`).
- **I-5 Model identity.** A card is served only under the model, config and significance version
  that built it (existing guard; `release-20260921/README.md:10`).

### 5.4 How the user sees freshness (requirement; copy and placement go to design-lead and ux-lead)

- When any displayed card comes from a deck past a §5.1 bound, the screen shows a visible,
  non-blocking "updating" state. It ends when the refresh completes or fails.
- A withdrawn card says why, in one plain line (e.g. the player moved), and never disappears
  silently.
- When a refresh fails, the user sees that the deck may be out of date and can retry. Actions on
  cards stay governed by I-2.
- No freshness UI appears when every input is within bounds. The default state is quiet.
- All of this follows the Chalkline rules (ADR-004/005). Freshness is informational, so flare is the
  only allowed highlight accent; no new color.

## 6. Today's baseline: **PENDING analytics-lead read (W3)**

This worker may not run production reads. The numbers below were already measured and recorded in the
repo; they are **provisional**. The authoritative baseline is the query spec in
[baseline-request.md](baseline-request.md).

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

**What the provisional numbers say.** First, **no phone has ever been timed**: every figure is a
server or local boundary. Second, the best server-side first-card boundary measured anywhere is
1.081 s (prepared, local, backend only), which is 4.3× the whole 250 ms budget before any network or
render time. Third, the current client poll schedule alone (first poll at 800 ms) exceeds 250 ms
3.2× over. Fourth, the production worker (61 s median) is about 244× over.

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
| Platform pending-offer reads (Sleeper/ESPN/MFL) | Not read today; the cross-platform pending inbox is **not built** (`docs/plans/README.md:110`). If eng proposes adding these reads for freshness, platforms-pm reviews (§11). |
| Infrastructure purchases | Under the $200/month ceiling (`docs/plans/README.md:59`). Any paid change is a separate operator decision. |

## 8. Acceptance criteria

Each is pass/fail by a guard (G), a unit or integration test (T), an analytics read (A) or a
TestFlight checklist step (TF, §9.4).

| ID | Criterion | Check |
|---|---|---|
| AC-1 | Every table A control in §4.1, and every table B control if D10 makes them search-starting, emits the R1 tap record with a `search_id`, and the deck emits R2 (or its failure sibling) exactly once per `search_id`. | G: `mobile/tests/check-trade-first-card.js` enumerates the §4.1 controls and fails if any `onPress` path lacks the emit. T: taxonomy registration and `NON_INTENT_EVENTS` classification test. |
| AC-2 | `ms_from_tap` uses a monotonic clock and ends on the §4.2 definition: controls enabled and card visible. It does not end on `deck_card_viewed`, a skeleton or server readiness. | G: the same check asserts the emitter sits on the card's enabled-and-visible path and not in the skeleton branch. Code-walk proof (§9.3). |
| AC-3 | **Organic, first-tap and repeat-tap cells: p95 ≤ 250 ms on Wi-Fi and on cellular**, n ≥ 40 per cell, in the 14-day post-ship window. p50/p90/p99 and the abandon/error counts are reported. | A: the analytics-lead read using the R1/R2/R4 fields. Until n ≥ 40: TF steps 1–4 and 9. |
| AC-4 | Cold-launch, pinned/targeted and fair-sweep cells are reported with the same percentiles. They are gated only per Decisions D1/D2. | A. |
| AC-5 | I-1: no displayed card contains an asset its stated side doesn't own per the freshest roster held. A roster change between prepare and display withdraws or filters the card before display. | T: backend test on every serve path (fresh, cached, joined, prepared) that mutates a roster after build and asserts the card is absent. TF steps 11–12. |
| AC-6 | I-2: a send or match on a card whose asset has moved is blocked with a message. | T: route tests per platform write path. TF step 13. |
| AC-7 | §5.1 bounds are enforced. For each input, a deck past its bound triggers the §5.2 behavior: serve-and-refresh, refetch-before-display for the viewer's roster (exception 1), or block (exception 2). A deck within bounds serves with no freshness UI. | T: one test per input row, plus a block test for a model/config change and a league-settings change. |
| AC-8 | §5.4: the "updating" state shows only when serving past a bound, and clears when the refresh lands or fails. A withdrawn card shows its reason. | G: structural check that the state is driven by `freshness_state` from the payload. TF steps 10–14. |
| AC-9 | **Quality parity.** Every card served on a fast path passes the same `deck.quality_filters` rules as the live deck, and the fast path's first 30 match, in identity and order, what the full current-model job would serve from the same inputs. Any approved deviation is recorded with models-lead sign-off. | T: a differential test comparing the fast path with the fresh path on frozen inputs, with `PYTHONHASHSEED=0` and a frozen clock (G-065, `GOTCHAS.md:737-742`). |
| AC-10 | No offer cap or budget cut: the complete eligible inventory stays reachable (the `research-plan.md:66-69` non-negotiables). | T: the inventory-count parity test (pattern of `release-20260921/README.md:16`). |
| AC-11 | **Storage within budget.** The build states its server-side footprint per user-league and its daily write volume using §10.4's formulas, and stays within the budget the DB-storage task sets (Decision D7). | A: before and after table sizes (`baseline-request.md` Q8). |
| AC-12 | No regressions: CI green (`pytest backend/tests`, `tsc --noEmit`, testid-lint) plus all existing `check-*.js` suites. TEST_LEDGER records the evidence. | CI. |
| AC-13 | First → next card: after the first card, the next card is ready before the user can act on the first. The buffer-empty stall rate is reported. | A (R2 sibling or a later-card timing field). TF step 6. |

## 9. Test-plan seed (D-056: no Maestro, no simulator)

### 9.1 Structural guards (`mobile/tests/check-*.js`, plus an `npm run test:<name>` script)

`check-trade-first-card.js` does three things:
- enumerates the §4.1 controls by testID or file and asserts each emits R1 with a `search_id`;
- asserts R2 fires from the enabled-card render path and never from the `SkeletonTradeCard` branch;
- asserts `freshness_state` drives the "updating" UI.

### 9.2 Unit and integration tests (backend pytest)

- **Taxonomy:** registration and NON_INTENT classification for R1–R3.
- **Freshness:** one test per §5.1 row, covering its §5.2 branch: serve-and-refresh,
  refetch-before-display or block.
- **Ownership:** a roster mutation between prepare and serve, covering every serve path (AC-5).
- **Action-time revalidation:** per write path (AC-6).
- **Quality parity:** the differential test (AC-9), seeded with a frozen clock.
- **Inventory parity:** AC-10.

### 9.3 Code-walk proof (file:line, written by the build)

Trace tap → navigation → request or local read → first enabled card render, for each entry point.
Name every hop that can block, and every place a skeleton can show.

### 9.4 Operator TestFlight checklist (the only runtime evidence; run on the build's TestFlight number)

**Setup:**
- an iPhone on the build;
- a Sleeper league with at least 10 teams where you have a roster and rankings;
- iOS Screen Recording on, so the tap and the first card can be timed frame by frame (1 frame ≈
  16.7 ms) as an independent check on the telemetry;
- note the phone model, iOS version and network for every step.

1. Force-quit, cold-launch, and wait until Home is fully loaded and 10 s have passed (session-init
   done). Tap the Home **Find a trade** tile. **Record:** the time to an interactive Acquire builder
   (table B; not gated). With the canvas **empty**, tap the canvas **Find a Trade**
   (`calc.action.find-a-trade`). **Expect:** a real card with enabled Like/Pass in ≤ 250 ms from
   this second tap on the recording (≤ 15 frames). No skeleton, no "Looking for trades…" card, and no
   "Searching…" frame before it.
2. Go back to the builder and tap canvas Find a Trade again (repeat tap). **Expect:** ≤ 250 ms. Then,
   inside the deck, tap **Find more trades** (`trades.find-btn`). **Expect:** ≤ 250 ms.
3. Reach the builder from every other table B control: League Home **Find a trade** (both
   buttons), the Matches empty-state CTA, and the calculator's "Find a trade →" row. For each:
   **record** tap → builder, then tap canvas Find a Trade with an empty canvas. **Expect:**
   ≤ 250 ms from the canvas tap each time. Write down any misses.
4. Turn Wi-Fi off (cellular only). Repeat steps 1–2. **Expect:** ≤ 250 ms, or record the miss for
   Decision D3.
5. Force-quit, cold-launch, open Acquire, and tap canvas Find a Trade **as soon as it is
   tappable** (session-init may still be running).
   **Record:** the time, and what showed before the card (for Decision D2).
6. On the first card, wait 1 s, then Pass. **Expect:** the next card is already there. No skeleton,
   no "searching" stall. Pass through 10 cards, noting any stall.
7. **Targeted searches (record; gated only if Decision D1 says so):**
   - put one player on the receive side only, then tap Find a Trade (model deck);
   - add a player to the give side, then tap Find a Trade (the fairness sweep);
   - Usage Trends **Trade** on a player, with and without a partner;
   - League Summary Offer and Target.

   **Record:** the time to first card, or what showed instead. A Usage Trends handoff with no
   partner currently lands on the builder with no search.
8. Like a card, return later, tap canvas Find a Trade. **Expect:** the liked offer does not reappear as new
   (I-3).
9. Ask analytics-lead to confirm that every tap in steps 1–7 produced one R1 and one R2 with matching
   `search_id`, and that `ms_from_tap` agrees with your recording within 1–2 frames.
10. Change your rankings (move a player across a tier, or change your outlook), then within 1 minute
    tap canvas Find a Trade. **Expect:** a card in ≤ 250 ms. If the deck predates the change, the "updating"
    state shows, and within the refresh window the deck reflects the change without rewriting the
    card on screen.
11. **Roster freshness, yours:** in the Sleeper app, drop a bench player of yours who appears in your
    offers (pick one you can re-add, or use a test league). Return to the app within 2 minutes and
    tap canvas Find a Trade. **Expect:** no displayed card includes that player, now or after the refresh.
12. **Roster freshness, partner** (needs a test league or a cooperating leaguemate): the partner drops
    or trades away a player your deck offered from them. **Expect:** no card shows that player as
    theirs within the §5.1 bound.
13. Find a card containing a player who moved after the card was built (from step 11 or 12, or a
    test-league setup), then try to Like into a match or Send. **Expect:** blocked with a clear
    message. Nothing is sent to Sleeper.
14. Turn on Airplane Mode and tap canvas Find a Trade. **Expect:** an honest offline state. No crash, and no
    action that silently fails.
15. Log the outcomes (times, misses, any card that violated I-1) in `living-memory/TEST_LEDGER.md`.

## 10. Trade-offs for eng (surfaced, NOT decided)

### 10.1 Candidate approaches (eng chooses; combinations likely)

| Approach | What it changes | Fits 250 ms? (from evidence) | Main cost or risk |
|---|---|---|---|
| A. Server-prepared inventory, fast serve | Adopt a validated prepared deck at tap (#305–#307 path, now dark) | Only if server work plus one round trip fits. Best local first-30 is 1.081 s (`prepared-trade-inventory/release.md:161-165`): about 4× over the whole budget, and about 20× over the 50 ms server slice in §10.2 | ~2–2.6 MB per user-league stored, plus evidence writes per adoption (§10.4). Freshness is bounded by refresh cadence. Skips `deck.quality_filters` today. Production canaries failed twice (`release.md:37-39,90-93`). |
| B. Device-resident first page | Prefetch the first N validated cards to the phone at app open, foreground or Trades focus. The tap renders locally; validity is rechecked in the background | Removes the network from the critical path; render only | Device copy can go stale between prefetch and tap, so it leans on §5.2 and I-1/I-2. About 1.25 KB per card on device (`delivery.md:106`). Needs a new mobile binary. |
| C. Faster fresh generation | Engine and evidence speedups, or a faster engine (value core local p95 1.77 s on a 14-team fixture; `TEST_LEDGER.md:213`) | **No on its own.** Even 1.77 s is 7× the budget | Shortens refresh time, so it helps freshness. Swapping engines is a model change (models-lead). |
| D. Progressive publication | Publish a card before global ranking completes | Possibly | Changes the best-first order contract (`execution-20260921/README.md:9`). Needs models-lead sign-off (AC-9). |
| E. Transport | Replace 800 ms-first polling with an immediate response or push | Likely needed alongside A: the first poll alone lands at 800 ms. Irrelevant to B's critical path | API contract change (api-reference); new client binary. |

### 10.2 Latency budget split (illustrative; eng refines)

The 250 ms must cover the whole path. Illustrative splits:
- **Network on the critical path (A + E):** tap handling and navigation 50 ms + network 120 ms +
  server 50 ms + decode and render 30 ms.
- **Network off the critical path (B):** tap and navigation 50 ms + local read, render and layout
  ≤ 200 ms. Validation runs after.

Two facts constrain any split:
- A cellular round trip to the Oregon-hosted service (one Standard instance;
  `infrastructure-and-precompute.md:7`) is **unmeasured** for our users. No RTT figure exists in the
  repo, which is why R4 is requested.
- Navigation itself costs time. A stack-push animation can consume much of the budget before the
  card is "≥ 50% visible" (§4.2). ux-lead reviews the transition (§11).
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
- **Roster input is currently refreshed only when a member opens the league** (G-075), so headless
  preparation can work from stale rosters unless it refetches. For MFL and ESPN, that refetch
  currently needs the owner present.
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

### 10.5 Deck quality vs speed

- **`deck.quality_filters` (D-207)** runs in `_run_trade_job` after presentment
  (`deck-quality-filters/scope.md:14`).
  - It runs **before** the first-30 publication, over the **entire** served list, not just the first
    30 (`backend/deck_quality.py:83-130`; `backend/server.py:8876-8902`).
  - It records no timing, only counts (`:8897`).
  - Its lineup-slot lookup (`_league_lineup_slots`) can make a **live Sleeper `GET /league/<id>` with
    a 10 s timeout** on a 15-min meta-cache miss (`server.py:29130-29152`). That puts a network call
    on the first-card critical path.
  - The value-core path skips the filters (`:7566-7600`). Prepared inventory is out of their v1
    scope, so a prepared fast path serves unfiltered cards unless the filters are extended to it.
    AC-9 requires parity.
- **Model arms:** today's engine (`owner_v2_bilateral`) is the default. Value core is flag-off and
  graded lower in Calibration round 2 (2.88 vs 3.19; `living-memory/CHANGELOG.md:31`). Its speed
  (p95 1.77 s local) makes it tempting as a latency fix. Choosing an engine for speed is a models-lead
  and operator call, not a latency optimization. While `trade.value_core` is on, prepared inventory
  is unsupported (`docs/config-reference.md:351`).
- **Calibration decks** are built headlessly and their current arm samples served `deck_impressions`
  (`architecture.md:406-412`). A fast path that changes which cards are served, or which get evidence
  rows, changes what Calibration grades.
- **Order:** a fast first card that isn't the full deck's best card is a quality regression unless
  models-lead approves it (AC-9).

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
| `trade.presentment_rules` | true | `:76` | R4 awaiting/matched exclusions (I-3). |
| `trade.standing_offers` | true | `:282` | Protected cards in the deck. |
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

## 11. Required reviews

| Reviewer | Why | Blocking? |
|---|---|---|
| **design-lead** | The §5.4 freshness indicator: withdrawn-card line, "updating" state and offline state. Chalkline compliance. | Yes, before any UI build |
| **ux-lead** | The flow: whether table B controls should start a search (D10), the `TradeDeck` push transition inside the 250 ms window (§10.2), what the user sees on a gate miss, and withdraw/replace behavior that never rewrites the fronted card. | Yes |
| **analytics-lead** | Grant R1–R4 (taxonomy plus NON_INTENT classification in the emitter's commit) and run the W3 baseline (`baseline-request.md`). | Yes, R1/R2 before build; baseline before the gate is judged |
| **models-lead** | Sign-off is required if served cards, their order or their composition can change. Precompute timing alone can change which offers are served (§10.3), as can a progressive order (D), an engine swap (C), skipping or extending `deck.quality_filters`, or lazy evidence. | Yes, if any of those apply |
| **platforms-pm** | **Expected:** I-2 adds live ownership checks on the Sleeper, ESPN and MFL send paths, and the §5.1 roster bound likely changes roster fetch cadence, including server-side refetch for headless preparation (G-075). Also required for any new pending-offer read. | Yes, once the build touches platform reads |
| DB-storage task owner | Footprint (§10.4) against the storage budget (AC-11). | Yes, before any persistent cache expands |

## 12. Risks

- **The target may be physically out of reach on cellular** if a network hop stays on the critical
  path (D3). Measure before committing to a design.
- **Freshness and storage fight each other.** Tighter bounds mean more rebuilds, and more rebuilds
  mean more writes (§10.4) and more contention on the single worker (§10.3).
- **Small sample.** About 8 active users means p95 gates may take weeks to reach n ≥ 40. The
  TestFlight checklist carries the decision until then.
- **The freshness work can cost speed.** Refetching the viewer's roster before display (§5.2,
  exception 1) is a platform call on the critical path whenever the roster is past its bound.
  Keeping it inside the bound proactively is part of the build, not optional.
- **Prepared inventory is unproven in production.** Two failed canaries, rollout off
  (`prepared-trade-inventory/release.md:37-39,90-93`).

## Decisions needed (operator)

| ID | Decision | Proposed |
|---|---|---|
| D1 | Which taps the 250 ms gate covers | The organic deck from every table A control. Pinned, targeted and fair-sweep searches are measured, with a target set after the baseline. |
| D2 | Are cold-launch taps (before session-init completes) held to 250 ms? | Report separately. Gate first-tap and repeat-tap; decide cold-launch after the baseline. |
| D3 | Is cellular held to the same 250 ms p95? | Yes, as the operator's ask reads. Revisit only if R4 data shows the network floor alone exceeds the budget. |
| D4 | The stale-deck rule | Serve-and-refresh with the two hard exceptions (§5.2). Alternatives: block, or serve-with-label. |
| D5 | The §5.1 freshness bounds | As proposed in the table. |
| D6 | May the first card differ from the full deck's top card (progressive order)? | No by default. Only with models-lead sign-off and a measured quality comparison. |
| D7 | Storage budget for a faster path, and whether evidence rows may be written only for displayed cards | Set with the DB-storage task. Lazy evidence needs analytics-lead and models-lead agreement. |
| D8 | Does 250 ms supersede the 3 s goal in `trade-search-latency/research-plan.md` §4? | Yes. 250 ms becomes the tap-to-first-card KPI, and that thread's non-negotiables stay. |
| D9 | Must every fast-path card pass `deck.quality_filters`? | Yes (AC-9). |
| D10 | Should a table B control (Home tile, League, Matches, calculator row) start a search and show cards directly, instead of opening the builder? | ux-lead proposes the flow; the operator decides. Until then the clock starts at the table A tap, and table B taps are measured as tap → builder interactive. |

## Handoffs

- **head-eng → trades-eng, models-eng:** choose the approach (§10.1) against §4, §5 and §8; write
  HLD/LLD; return the latency budget split and the storage footprint (AC-11).
- **analytics-lead:** grant or amend R1–R4; run `baseline-request.md` (W3); replace §6's provisional
  table with the read.
- **design-lead + ux-lead:** the §5.4 freshness states, plus the transition and gate-miss experience.
- **models-lead:** a sign-off position on AC-9, precompute timing, lazy evidence and any engine
  swap.
- **platforms-pm:** review I-2 (live ownership checks on send) and any roster-cadence change behind
  the §5.1 roster bound.
- **DB-storage task:** take the §10.4 arithmetic and return a budget for D7.
- **release-lead:** merge this plan PR on the operator's go. Plan only, no code.
- **Operator:** D1–D10, then the §9.4 checklist once a build exists.

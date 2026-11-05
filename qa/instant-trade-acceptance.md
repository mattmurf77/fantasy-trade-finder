# Find a Trade acceptance and denominator audit

QA owner: independent billing/integration reviewer. Baseline: `60d861d`;
browser implementation reviewed: `b8e9631`. This inventory describes app code,
not a claim that physical-device timing has passed. The user's current request
covers every eligible scenario; older organic-only and T7 exclusions are not a
waiver for the strict report.

## Executable report

```sh
python3 -m unittest discover -s scripts/qa -p 'test_instant_trade_report.py' -v
python3 scripts/qa/instant_trade_report.py --input /private/tmp/aggregate.json
```

Exit status: **0** = all required cohorts pass (possibly `PASS_NOT_ROBUST`),
**1** = failed/missing evidence, **2** = unavailable/invalid evidence. A missing
file, empty dataset or synthetic example never certifies release. No app import,
database connection or optional dependency is needed for offline mode/help.

The explicit production mode requires `DATABASE_URL_PROD` in the environment,
SQLAlchemy and its Postgres driver. Never put credentials in argv or a report.

```sh
python3 scripts/qa/instant_trade_report.py --production --app-version 1.22.0 \
  --client-build 172 --web-revision instant-trades-v1 --hours 24 --profile all-entry
```

It opens a server-enforced read-only transaction, checks
`SHOW transaction_read_only`, uses a 15-second statement timeout, executes one
aggregate SELECT, rolls back and disconnects. It returns no user, league,
search, job or device identifiers and no raw props. Errors print only an error
type. `--snapshot-only` emits the sanitized aggregate input, not an acceptance
verdict. Default observations end five minutes before query time; terminals
can arrive through query time. Delayed telemetry beyond that grace still
appears missing; it is not imputed as a success. Repeat after the queue drains.
Tester devices are included. Version is mandatory; exact R1 build filtering
avoids combining a future candidate with build 171. A missing build tag is
excluded from a requested exact-build sample, and the resulting missing
cohorts fail.

Browser events have no native app version. `--web-revision` independently
selects their exact R1 `client_build` tag (`instant-trades-v1`), while
`--client-build` remains a native-only filter. Historical unversioned browser
events are not mixed into candidate proof. Without `--web-revision`, browser
cohorts are intentionally absent and strict all-entry acceptance fails.

The default **all-entry** profile requires first/repeat Wi-Fi/cellular organic
cells, every listed search entry, scoped/fair searches, cold launch, genuinely
cold engine, immediate changes, cached offline use and first free preview.
No first/repeat, cold, preference, scoped or offline case is silently removed.
**Every observed eligible tap must be <=200ms**, not merely p95: one 5-second
success or timeout among hundreds of fast cards fails this strict profile.
The report includes above-limit/missing counts and observed maximums alongside
the inherited percentile statistics. No finite sample promises future taps.
Offline with no retained page, exhausted preview and unverified sessions have
separate required negative-control rows (`offline`, `paywall`, `verify`);
they must show the proper state, not fabricated cards. Explicit product gates
are reported separately and never counted as fast cards. A cohort with only
gates cannot satisfy its latency requirement. The optional **ac-l1** profile is
the narrower historical organic comparison, including its explicit T7 prefs
exclusion; it cannot certify the user's all-entry requirement.

For every measured cell, the report emits counts and fast-card share,
nearest-rank p50/p90/p95/p99, and the exact binomial order-statistic 90% CI
for population p95. `null` for a percentile or CI upper end means unbounded or
absent, never zero milliseconds. All empty/error/abandoned/timeout/missing
outcomes are +infinity for the latency distribution, regardless of how quickly
they failed. Taps without UUIDs remain in the overall denominator as misses.
Duplicate R1 IDs and ambiguous/missing terminals explicitly fail correlation.
The companion `calc_find_a_trade_tapped` is never counted as a second tap.
Samples require n >=40 and >=2 evidenced devices. Per-cohort distinct-device
counts combine using **max**, a conservative lower bound on the union, never
a sum that could turn one device into two. Thus some disjoint-device datasets
can fail conservatively and need a wider aggregate query; they cannot pass
because of double-counted devices.

Immediate change cohorts require an explicit R1 scenario and measured
change-to-tap age <=5000ms (`--immediate-change-ms` changes this boundary).
The actual min/max ages remain in output. Older events, delayed ages or
missing ages do not prove an immediate-change case. Current R1 lifecycle tags
cover league/preferences/format/account changes; old telemetry cannot infer
these from `serve_source=device/page/cached`. Genuinely cold engine and
cached-offline cases also need explicit run context; `cold_launch` and
`first_tap` are not proxies for cache state.

Input schema (histogram counts are mutually exclusive taps, not events):

```json
{
  "schema": 1,
  "evidence_kind": "synthetic",
  "finalized": true,
  "untraced_taps": 0,
  "cohorts": [{
    "platform": "mobile", "entry_point": "calculator",
    "search_type": "organic", "network_type": "wifi",
    "launch_state": "first_tap", "scenario": "after_league_switch",
    "input_age_ms_min": 80, "input_age_ms_max": 80,
    "devices": 2, "devices_all": 2,
    "histogram": [{"result": "shown", "ms": 150, "count": 80}]
  }]
}
```

This example intentionally fails: synthetic evidence and missing other
cohorts. For actual observations, `devices` counts distinct devices with
non-gate outcomes; `devices_all` also includes gate controls. Aggregate each
six-dimension cell exactly once. Do not concatenate overlapping windows,
copy raw production events, or claim that manually relabeling a cache hit
establishes the scenario. Non-production acceptance runs may supply sanitized
aggregates with known scenario context; timing must come from the real
actionable/50%-visible frame. This reporter validates evidence completeness;
it cannot establish roster correctness or safety from latency alone. A verified
no-eligible-solution run has its own required `no_eligible_solution` scenario /
`no_solution` outcome; it is neither a fast card nor a latency failure. This
requires positive run evidence that no eligible solution exists. Production
R2b `empty` is not enough to establish that condition and remains a miss.

## Entry inventory: search-starting controls

| Entry / source | Actual owner | Request and scope | Required QA |
| --- | --- | --- | --- |
| Acquire canvas / `calculator` | `InLeagueCalculator` -> `TradesScreen.handleInlineFindATrade` -> `canvasSearch.forkCanvasSearch` | Empty -> organic model. Receive-only -> model with receive selection. Give/package -> fair-packages. Team scopes opponent. | Fresh and held page, give/receive/package/team/intent, threshold, repeated build->results->edit loop. |
| Standalone calculator / `calculator` | `TradeCalculatorScreen.onFindATrade`, when inline host is off | Same canvas fork, then Finder handoff | Feature fallback; exact selection survives navigation once. |
| Deck start/retry / absent source normalized to `deck`, `deck_error_retry` | `TradesScreen.handleFindTrades` | Retains fair/model last request and effective current scope | First/repeat, errors, offline retry, no stale package substitution. |
| Preferences strip / `prefs_changed_strip` | `TradesScreen.handleFindTrades` | Re-search current scope after preferences change | Immediate <=5s and delayed separately; included in strict timing. |
| End-card apply / `end_card_adjust` | `TradesScreen` end-card preference handler | Changed scope in place | Tap clock at apply; no stale front card or hidden spinner pass. |
| Summary unpin / `deck_summary_unpin`; search-all / `deck_search_all` | `TradesScreen` unpin/search-all handlers | Clear requested pins/anchor and request broader model deck | New search ID; removed scope must not survive in memo/handoff. |
| League Summary Offer / `league_offer`; Target / `league_target` | `LeagueSummaryScreen` | Scoped player/partner handoff | Give/receive orientation, same league/format, tap starts before navigation. |
| Usage Trends Trade / `usage_trends` | `UsageTrendCard`, `UsageStatsTable`, `UsageLeagueList` -> `UsageTrendsScreen` | Player plus selected league/owner; opponent needed for auto-run | Cross-league selection, no-opponent builder arrival must not fabricate R1/R2. |
| Team Review / `team_review` | `TeamReviewScreen` | Partner-scoped handoff; otherwise builder arrival | Scoped path included in strict report; no search on navigation-only path. |
| Finder deep link / `deep_link`; inbox arrival | `TabNav` / param-less `TradeDeck` | User search-start tap uses the deck path | Verified identity and initialized league; link arrival is not itself a user tap. |
| Web manual CTA / `web_finder` | `web/index.html` gen-btn -> `web/js/app.js.generateTrades` | Organic or give/receive-pinned generate; completed first page, then explicit load-more | Scoped payload, revoked-snapshot restart, stale-context rejection, first/repeat/cold, 50% visible with both buttons enabled. |

## Navigation-only and adjacent controls

Home hub tile/list, League Home Find/works-now, Matches empty-state Find,
calculator "Want ideas instead?", and web tab/back links **navigate** to the
builder under the checked-in flags. They do not produce a first-card pass;
measure navigation separately, then start the card clock at the real search
control. `TradeFinderHubScreen` is unregistered. Presentation-v2 Today and
first-run auto-start are flag/fallback paths, not manual R1 taps. Keep these
distinctions in future routing changes rather than adding false fast rows.

Shop / give-side More offers uses its own Shop API and events. Receive-side
keep-side can start a legacy pinned search when that deck UI is reachable;
it currently dispatches directly with `trade_keep_side_tapped`, not R1. It
must not be counted as covered by calculator R1. Its reachability is gated
by the canvas/deck posture (`TradesScreen` comments and `onKeepSide` binding).
This adjacent path needs a separate trace if included in an all-ideas claim.
Filters/pin selection alone are not a search tap; their next explicit search
must use the changed selection, not an old device page or completed job.

## Safety and runtime matrix

For **each real search entry**, cross organic/pinned/targeted/fair as applicable
with Wi-Fi/cellular, first/repeat, account/league/format/preference/board changes,
and immediate vs warmed timing. Additional required probes:

- Genuinely cold job, cold process with saved page, no page, expired (>5min)
  page, invalidated rankings/roster/values, and first tap before prewarm settles.
- Offline with usable page vs no page. Disabled/withheld cards, loading strips,
  placeholders and zero-results states are not first-card successes.
- Free enforcing preview remains unused by background work; actual first tap
  claims it. Exhausted/lapsed and unverified gates remain authoritative. Paid
  background work remains allowed. Cache data is not an entitlement grant.
- Background/inactive/blur, newer tap, user switch, deletion, league/format
  switch while a request or handoff is pending: old reply must not render or
  restore a revoked page. Current scope and next-page cursor stay together.
- Pass/Like and queued undo remove the acted card; revalidation does not
  resurrect it. Refresh retains current server order and current ownership.
- Flags off/unknown, missing paging fields/legacy responses, stale snapshots,
  401/403/402, server errors, timeout and no-results keep honest state/recovery.

Relevant executable source guards: `check-device-first-page`,
`check-trade-prewarm`, `check-trade-first-card-events`, `check-trade-pages`,
`check-paywall-gate`, `check-results-push`, `check-entry-session-identity`,
`check-session-seed`; backend preview/gate, page-store/I-1 and snapshot suites;
browser `node qa/web/check_trade_search.cjs` and web structural checks. These
prove code contracts, not physical frame timings. Native runtime evidence is
the approved physical TestFlight checklist; D-056 bars simulator substitutes.

## Evidence as of 2026-11-05

One aggregate-only production read (read-only transaction verified) covered
2026-11-04 18:04:42Z through 2026-11-05 18:04:42Z, with terminal grace through
18:09:42Z; app version 1.22.0, **all builds**, because historical R1s lack a
build tag. Three correlated taps: one 123ms success and two ~10s timeouts.
Each observed cell has evidence of one device. No untraced taps in this
version-filtered window. Strict report: **FAIL**, all 58 requirements remain
slow, missing or undersampled. This is a baseline, not a candidate comparison.
No raw identities were retrieved or exported. Private sanitized aggregate and
full failing report: `/private/tmp/fleeced-instant-trade-baseline.json` and
`/private/tmp/fleeced-instant-trade-baseline-report.json`.

Reporter regression: **30 passed**, including three real PostgreSQL synthetic
temporary-table tests for UUID collision across users, missing/untraced taps,
late terminal grace, build exclusion, immediate age boundary, duplicate R1/
terminal and malformed latency. Initial PostgreSQL attempts were blocked by
the process sandbox; authorized socket-only rerun passed. No production writes.
Browser b8e9631: six controlled runtime scenarios and 255 structural checks
passed independently. Physical-device improvement and strict all-entry
performance remain **unproven**.

## Bounded linked-league shadow canary: review conditions

This is a proposed validation plan, **not an activation**. Global preparation
and enforcement settings remain unchanged. Approve one dedicated test account
and at most two of its already-linked leagues explicitly; no other customer's
data is sampled or copied. Start with one format and exact organic fairness /
preference scope, one background build at a time, with a bounded request queue,
CPU-time, DB-write and byte budget. Measure those budgets before widening.
Cancel superseded work instead of retrying indefinitely. The kill switch must
stop admission and cancel pending adoption, with existing active-league work
retaining priority. Shadow failures must not slow active searches.

1. **Server-only shadow:** derive linked membership from the authenticated
   account, including provider ownership proof. Use an immutable authorized
   league/format context; never temporarily change the user's active session,
   token or format to run the shadow. Retain the existing user-data lease,
   live-user checks and deletion/input epochs through preparation/publication.
   Publish only fully evaluated, correctly ordered pages under exact request,
   model/config and input fingerprints. Prebuild is not user-visible delivery
   and must write no delivered-card evidence or consume a free preview.
2. **Phone transfer:** opt in only the same authenticated test phone, after
   current validation of user/league/format/request and current gate permission
   without a Preview grant. Enforcement OFF or a verified entitled session can
   qualify. Enforcing non-Pro preview cannot be passively delivered under the
   existing contract; retain server-side prep and test its actual tap normally.
   Phone pages remain private, key scoped, TTL bounded and revocable on local
   input change/sign-out/deletion. Include all known storage versions in clear.
   No switch may use another league's, format's or input scope's page.
3. **Already-linked switch proof:** verify the destination page reached that
   phone before the switch, then test switch->immediate tap <=5s, both
   directions, with cold/warm process, foreground/offline and invalidation.
   Record R1 age, candidate native build/browser revision and R2 frame. Never
   count an unprepared switch as a cache-hit success or discard its miss.
4. **Novel league proof is separate:** first establish provider access and
   verified ownership, sync roster/pool/picks, resolve scoring format and user
   preferences, and complete model evaluation/current validation. A previously
   unknown league cannot have a proven page on the phone before these inputs
   exist. Measure immediate post-link taps as genuinely cold until the page is
   actually delivered. A warmed linked-league result proves nothing about this
   cohort; hiding Find until preparation finishes would move the requirement.
5. **Changed hard exclusions/pins are separate:** require an exact request
   signature containing every exclusion, give/receive/package pin, opponent,
   threshold and intent, plus current user/league/format/input epochs. A warm
   organic top-30 page is not evidence of complete or valid answers to a new
   scope. Prepare a known pending scope before its tap, or make the complete
   on-demand scoped solve fast. Arbitrary unseen combinations are not covered
   by warming linked organic pages; a reusable candidate basis would need its
   own proof of coverage, evaluation semantics and post-filter ordering.

Before canary GO: explicit account/league scope, budget and rollback readback;
no global enable; missing inputs fail closed; synthetic auth/deletion/preview /
scope regressions pass; exact-build evidence collector ready. Before widening:
all observed eligible taps <=200ms, minimum samples/devices met, no lost taps,
current-input/quality invariants preserved, and no active-path latency/storage
regression. Cold/new-league/new-scope misses remain visible. If any prerequisite
fails, stop the canary and retain the honest failing report.

# Prepared inventory: admission, freshness and first action

September 22, 2026. Agent A; parent-authorized **read-only** audit. No generation,
provider/production read, scheduler trigger, new benchmark, runtime edit or
deployment. Source is the dark worktree at HEAD `6c53caf9`; server SHA256
`3fa92ee850dfc8eb01a69ab7d052a85f8cda5facc158ac84d730ad27d2ed19c6`.
The canonical `trade-generation-performance/research-plan.md` and the local
`trade-search-latency` research/release evidence were inspected as context;
historical defects already fixed on September 21 are not reported as new bugs.

## Conclusion

**A matching completed warm deck already has an adoption path.** There is no
missing app-open generation trigger or blanket Find-a-Trade cache bypass to fix.
No source finding establishes that a genuinely current, completed cache hit
cannot reach three seconds: that endpoint/network/device path is unmeasured.
The actual cold dark worker still takes 14.538 seconds to its first durable30,
versus 8.576 seconds off. Warm adoption is a different population, not a cold
guarantee or a way to declare the model's current release gate passed.

The smallest **correctness prerequisite** to relying more heavily on prepared
inventory is a complete current-input admission receipt. Today's process-local
request signature and viewer epochs do not cover all roster/pick/market or
counterparty dependencies. More aggressive reuse, longer TTL or persistence
would magnify that known coverage limitation. One bounded proposal below closes
that prerequisite within the existing job lifecycle; it is not a new queue or
nightly inventory platform, and has no established latency gain.

## Existing lifecycle, current and dark

| Step | Existing behavior and source |
|---|---|
| Authenticated app open/resume | `mobile/App.tsx:200` calls `useSession.revalidateSession`; `mobile/src/state/useSession.ts:357` joins initialized-league work with a60s throttle. `mobile/src/api/auth.ts:261` asserts current token/account before and after init and sends the shared persisted fairness threshold. |
| Authoritative league init | `backend/server.py:21695` uses `session_input.resolve_session_input` for verified identity/membership/rosters. Near the end, `server.py:22531` resolves preferences/outlook and starts or preserves one organic job. This runs after league/input setup, not at the first process-launch instant. |
| Matching request | `server.py:2995,3056,3066,3426` binds account/league/format, exact fairness/outlook/intent, preferences/config/flags, owner model/version, presentation and safety policy. Unresolved preferences cannot claim a cache hit. |
| Atomic claim/join | `server.py:8900,9031` resolves execution context, then atomically checks the shared pointer and registers work under one lock. The same compatible running job is joined; complete jobs are reused. Background preservation of a different active request is **not** evidence that it matches the background request. |
| Ordinary Find | `mobile/src/screens/TradesScreen.tsx:1213,1998` sends a normal non-forced request. `force` is explicit refresh/Quick-Set behavior, not the ordinary default. `server.py:14333` returns the matching completed snapshot or joins matching running work without regeneration. Selected assets/partner searches intentionally bypass the organic pointer. |
| Immediate client adoption | `TradesScreen.tsx:2043` accepts the returned snapshot; a completed hit does not wait for a polling tick. Running work polls initially800ms, backing off to4000ms with jitter (`:2155`). Both routes normalize **all** received cards (`mobile/src/api/trades.ts:236,288`). |
| Durable publication | The normal worker's owner publication fence (`server.py:8657`) retains current model/significance/revocation checks and commits impressions before exposing each prefix. A running job with committed cards can already return those cards; pending validation is not represented as prepared inventory. |
| Read boundary | `server.py:3161` checks revocation/model/significance, applies current exact-pass/source-interest dispositions, then checks again. Status ownership is checked at `:15374`. No generation or new impression minting occurs merely because a completed job is read again. |
| Lifetime | Jobs/pointers are process-local (`server.py:2279`), completed admission TTL30min; four-hour registry retention is cleanup, **not** a30min freshness extension. Restart/deploy loses prepared jobs. Mobile persisted-query allowlist excludes discovery decks (`mobile/App.tsx:60`). |

The dark revision uses the **same admission and publication path**. Model identity
now distinguishes `owner-v2-bilateral-2` from the incumbent even though both share
the bilateral arm (`server.py:3148,3305,9019`). An old job cannot become revision2
by polling after a flag change; rollback withholds revoked inventory while
retaining durable evidence. No second preparation cache exists for the dark model.

Fairness mismatch is not a new defect: mobile init and Find use
`tradePregen.fairnessThresholdFor`, default0.5. Headless replenishment uses the
live session threshold or explicit native0.5 fallback (`server.py:23356`), not an
assumption about an unknown client-only preference. A later different request
does not qualify as a matching prepared hit. Background preparation preserves
active interactive intent and does not supersede it merely to manufacture hits.

## Concrete limitations versus unmeasured opportunities

### Source-demonstrated freshness coverage gap

`_trade_request_signature` explicitly identifies local preferences/config/flags,
not a complete provider/market version (`server.py:3066`). Its caller's preferences
do not contain every opponent's board/outlook or the latest ownership substrate.
`_capture_trade_input_epochs` captures only the viewer-global and viewer-league
tokens. `_invalidate_trade_jobs` (`:8877`) matches `key[0] == user_id`.

A concrete static counterexample: viewer A has a completed deck using B's real
board. B saves/copies rankings; the ranking route invalidates B's jobs
(`server.py:10573`), not A's. Fresh generation loads B's current member rankings
(`:7410`), but A's unchanged local request signature/epochs can still admit the
old deck. Opponent preferences similarly enter worker preparation (`:7539`),
not the viewer-only signature. This is a source-level dependency-coverage defect,
not an observation of a production stale offer or a quantified incidence rate.

Likewise session init resolves new authoritative roster data and refreshes
league-member/pick state (`server.py:21695,22325` onward), but the shown member
upsert invalidates the member-list projection, not every dependent trade job.
An unchanged declared outlook can leave the request signature unchanged after
ownership changes. TTL and final disposition projection do not compare fresh
rosters, pick ownership, market substrate, injury status or every player field.
No claim is made that these refreshes always occur or that every changed input
produces a stale offer; there is simply no complete invalidation proof here.

The September21 cache report explicitly documented this boundary. The narrow
round7 optimization neither introduces nor closes it. Do not repurpose immutable
impression JSON as proof that its old inputs remain authoritative now.

### Performance and lifecycle facts, not measured defects

- Preparation only removes time spent **before** the tap. If little useful lead
  time is available, remaining full-worker computation still blocks first action.
  The older four-second lead-time observation is historical, not a current
  distribution. No new useful-prewarm hit rate, wasted-job rate or app-open
  lead-time sample was collected here.
- A completed hit still copies/projects/JSON-serializes the entire published
  inventory; the client parses/normalizes it before first rendering. This could
  matter for thousands of cards, but no current endpoint/wire/device timing
  proves it consumes three seconds. Transport pagination is an unmeasured option,
  not permission to cap inventory or alter order, and is **not** the proposal
  in this audit.
- Poll backoff can add roughly one polling interval when work finishes after
  admission. It is absent for a completed generate response. Reducing polling
  cannot eliminate the underlying14.5-second cold construction/publication path.
- One daemon thread is started per newly admitted job; atomic matching avoids
  same-key duplicates but does not impose cross-user/league CPU admission limits.
  Revocation prevents publication but does not immediately stop the constructor.
  More speculative warming can compete with active searches on the previously
  verified single-CPU instance. Local RSS is not evidence of safe concurrency.
- Weekly replenishment (`server.py:23434`) runs normal jobs sequentially, and has
  notification/inbox semantics. It is not silent nightly preparation. Its
  eligibility query includes **generated** legacy impressions
  (`backend/database.py:6455`), so generated activity is not a human-demand signal.
  Do not expand that schedule under a latency task.

## One next proposal: strict in-process prepared-admission receipt

Authorize one bounded backend correctness increment before increasing prepared
reuse: attach a small private dependency receipt to the **existing** job and
require an exact current receipt match at claim/join, completed adoption and
status publication. Keep the organic pointer, atomic claim, worker, full order,
durable evidence, TTL and explicit search/force semantics. No new database table,
persistent deck, scheduler, queue, worker pool or client disk-deck cache.

The receipt must be derived from the authoritative inputs actually consumed,
not reconstructed from a public card: account and league membership/team identity;
format; viewer and relevant member board values **and provenance**; both managers'
outlook/preferences; ordered rosters, pick ownership/tradeability/status; market
and player substrate fields used by valuation/roster evaluation; request selection,
fairness/intent; and captured config/flags/model/presentation/safety versions.
Use exact typed canonical values or trustworthy source revisions, not `default=str`
or object identity as a data version. Unknown/unavailable freshness must be a
cache miss, not “unchanged.” Do not claim a source's last successful snapshot is
current when its freshness contract has expired.

Keep receipt preparation shared with the existing input resolver. Add the
missing dependent-viewer invalidation on member-board/preference and authoritative
roster/pick updates so active work is fenced promptly. Capture before reads,
recheck after receipt resolution and again at publication; a racing update
cannot make an old job current. Do not hold the registry lock during I/O. A
receipt mismatch starts/joins normal current work and withholds stale cards;
it never revalues or relabels the old offer's proof. If complete revision coverage
cannot be established at this bounded seam, stop and report that—not a partial
manifest advertised as authoritative. This is an implementation prerequisite,
not an endorsement of the separate unintegrated proof-reuse registry.

Required RED controls: A's complete/running deck after B's board/outlook update;
same-outlook roster swap, pick transfer or unavailable source; viewer rank/format/
fairness/model rollback; account/league switch; invalidation during receipt read,
admission and copied response projection; and simultaneous identical app-open/
Find requests yielding exactly one worker. GREEN unchanged-input adoption must
retain the original job, complete order, trade/impression IDs and byte-exact
private proofs, while current disposition cuts still apply. No view outcome or
additional generation/impression row may be manufactured by adoption.

Then measure **this one path** on an already-completed same-input fixture:
receipt resolution, admission, full response bytes/copy/projection/serialization,
client parse and first actionable render. Compare current versus strict receipt,
report warm app-open and tap latency separately from cold and unfinished-prewarm
latency, and record sample counts before percentiles. A trusted completed hit
meeting three seconds is useful but does not pass the cold-search gate. If the
receipt/read cost or actual hit rate makes the opportunity negligible, stop;
do not broaden into more warming, longer TTL or transport redesign automatically.

## Exposure and evidence boundary

Prepared/served is not viewed. Current durable offer identity and generation
diagnostics are unchanged; actual client fronting/dwell owns view outcomes
(`TradesScreen.tsx:4255,4286`, `backend/database.py:1097`). Canvas browse explicitly
suppresses the legacy per-page view event, so it must not be treated as missing
prewarm visibility. Measure genuine first usable rendering under the actual
surface's visibility contract. Preparation alone must never record a human
view, acceptance, engagement or fresh first-deck exposure.

Decision remains **no release qualification from warm preparation**. Parent
review and a separate written implementation specification are required before
any receipt/runtime work. This audit adds documentation only.

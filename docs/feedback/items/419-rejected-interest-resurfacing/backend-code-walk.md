# G419 backend code walk

2026-09-06 · implementation owner · reviewed against PRD/scope at `481b1809`.
Runtime diff personally read end-to-end against `4026ebc8`; this is backend
evidence, not native UI or release verification. Shared spec-doc edits belong
to root. Detailed runs and honest RED limitations: [build evidence](build-evidence.md).

The original-build sections below cite `e02d074e` line numbers. The final
QA-A episode repair and its current line references are traced separately at
the end; original source/projection behavior is unchanged by that repair.

## Source evidence, not a permanent discovery ban

| Contract | Final path and check |
|---|---|
| R1/T1 incident | `database.py:5900` `TradeInterestHistory` normalizes UTC timestamps before cutoff and orders by timestamp plus numeric decision ID. Later exact own or mirrored-recipient passes resolve the source like, without deleting/retracting history. `load_recent_league_likes` at 6066 supplies the real injector; the amnestied/expired August pass therefore still defeats the earlier August like. |
| R1 changed identity | Keys contain league, actor and oriented frozensets. Reordered arrays/new card IDs remain the same package; different actors/leagues/packages do not suppress each other. The receiver is supplied by the reader's actual current context, not added to legacy history. Malformed relevant chronology cannot establish affirmative interest. |
| R1 fresh consent | `actionable` and `renewable` distinguish old resolved likes from fresh deliberate likes. A receiver's later like does not revive the older opposite source. A new source like can be actionable; discovery still independently honors the recipient's active pass. Retraction blocks fallback to an older like. |
| R2 exact/fuzzy match | `find_mirror_like` at 9039 filters source candidates through the same history before the existing exact and fuzzy loops. Jaccard/low-value guard, tau and matching math are unchanged; an invalid exact source cannot become a match. |
| R2 Awaiting/R4/summary | `load_awaiting_trades` at 9424 preserves the existing 500-candidate cap and batches the selected leagues' history. It resolves a consistent known roster owner, retaining player+pick packages without inventing pick ownership; contradictory or entirely unknown owners are withheld. Exact source actionability is checked before returning tiles. Existing R4 and summary readers inherit that filtered output. |
| R2 queue | `find_live_trade_like` at 6091 checks the server-resolved counterpart; `server.py:14677` supplies it. Queue alone passes `queue_target_user_id` at 14726 into `save_trade_decision` at 5735. Only a valid intervening exact pass permits a fresh like inside ten seconds. No-intervening retries preserve the ordinary guard and avoid another decision/Elo/event. Unknown chronology cannot repeatedly authorize renewal. |

No D-067 knob, amnesty epoch, seven-day like window, D-170 gate, floor,
profile, valuation/policy math, arm assignment or history schema changed.
`TradeInterestHistory.discovery_keys` at 5946 is a separate interpretation
of the same normalized rows; source resolution never consults amnesty/age.

## Durable reason/pass state and live state

`server.py:14926` validates the existing request fields, resolves the actual
acted card or reconstructs it from the already-supported echoed context,
and independently banks the reason. `database.py:6755`
`ensure_reasoned_trade_pass` locks the existing reason row, verifies
actor/league/actual trade ID and exact oriented package, and checks/repairs a
missing live pass in a transaction. The result is returned after commit.

- `ok` acknowledges the saved reason; `passed` is verified durable decision
  state, including true on committed repeats. No card or failed decision
  persistence means false, even with HTTP 200. Upsert failure remains 500.
- A banked-first request, contextful retry, memory loss, reordered refinement,
  or retry beyond ten seconds cannot duplicate the same reason episode.
  Actual edited ID/package tests ensure the old displayed card is untouched.
- Only a newly written pass reaches `_apply_reasoned_pass` at 14891, so its
  existing outcome/event runs once. Existing impression ownership and pass-
  outcome dedupe remain in force. No new event or analytics property.
- Reason Elo uses the existing claim and exact old multiplier computation.
  `save_trade_swipes` at 5604 atomically persists the claim plus pairwise rows;
  failed Elo inserts roll back the claim without falsely clearing the pass.
  A later allowed detail can supply the deferred signal once. Ordinary swipe
  keeps its pre-DB D-073 memory signal and best-effort contract; a successfully
  persisted ordinary signal consumes an already-banked reason claim at 6799.
- `_bind_live_trade_pass` at 14869 updates both exclusion sets across every
  current-format service plus the legacy alias. Ordinary swipe calls it only
  for pass, and reason requests only after durable verification (AST-pinned).
  A delayed old-league echo persists in its own league without contaminating
  the new league's live sets. No new Undo write path was introduced.

## Every actual backend serving boundary

| Boundary | Final path |
|---|---|
| Complete/shared-running generate; initial fresh response | `generate_trades` at 13329 copies the job while locked, then calls the common public view outside the lock. |
| Old/current job status | `trade_job_status` at 14032 verifies job owner, copies it while locked, then projects outside the lock. The job's captured `(user, league, format)` key owns the response, not the polling session's current league. |
| Public projection | `_project_trade_dispositions` at 3032 loads one league history for the response. It reuses that object for the active-pass cut and actionable source-interest set. Non-null internal source IDs must identify a specific actionable source. Serialized own impression IDs resolve through one batched owned, same-league lookup at `database.py:6037`; a newer same-package like cannot validate a resolved source's old card. Null/unlinked legacy retains exact-current-evidence semantics. Surviving objects/order/metadata are unchanged; unavailable history/provenance yields an empty unverified snapshot. Empty/demo snapshots skip the DB read. |
| Pending in-memory cards | `get_trades` at 14053 groups by each card's actual league and projects each scoped group; a new ID cannot bypass an exact pass. Existing service-side live exclusion also remains. |
| Fresh/in-flight worker | The final list is projected at 7911 after mutation/scoring work and before ordinary/F1 impressions. The filtered list is published even with F1 disabled. Non-public intermediate lists may remain raw; every actual provisional response passes through the public projection. Frozen prior impressions are never rewritten. |
| Replenishment count | `_replenish_deck_for` at 21865 projects after releasing the lock and before its cached/new-deck inventory count at 21916. A pass after final publication cannot produce a stale notification count; no push lifecycle change. |
| Restart/headless parity | `_load_trade_disposition_keys` at 3095 is called by full init at 20506 and replenishment at 21809. Real DB/builder tests cover day 8/13, exact and fractional boundaries, mixed UTC offsets, malformed stamps, amnesty on/off, and independent likes. |

Standing offers retain their separate existing intent/lifecycle and source
label, but an active exact pass still defeats their mirror. There is no arm-A
R4 bypass or floor rescue in the common disposition projection. One existing
bakeoff order-only fixture was explicitly approved by root for a source-row
prerequisite repair: its injected `rb3` card and like now consistently name
the fixture's actual `OPP2` owner. All attribution/interleaving/policy-version
assertions and golden files remain unchanged; unknown-source removal has an
independent negative control.

## Evidence limits and handoff

History SQL is bounded by selected league/actor, not by textual time. This
preserves offset/malformed chronology correctness but scans older scoped
rows. It selects only 11 needed columns. Measured 5k-row reader and 20-card
legacy serve projection each issue one history SELECT. Serialized interested
cards with their own impression IDs additionally use one batched provenance
SELECT; the linked-source route test counts two total. There is no per-card
query or DB work inside `_trade_jobs_lock`. This is fixture evidence, not a
production latency promise. Existing read-amplification tests remain green.

The rejected temporary defect mutation was not retried. Original-runtime RED
is the accepted safe alternative and is recorded with confirmed module paths,
provider fixture pins and behavioral failures, not import errors. Full backend
integration, mobile structured-response/locally-observed state checks and the
five physical TestFlight sequences remain root/operator work. No Maestro,
simulator, capture, push, deployment or production mutation was performed.
Remote-only retained client invalidation, post-match Decline/fuzzy exemptions,
and standing-offer lifecycle remain held; no UI behavior is claimed verified.

## QA-A episode repair — final path atop `e02d074e`

The old verifier accepted any historical same-ID/same-package pass. That is
insufficient when the counterpart renewed their like before this reason was
first banked. This repair changes only the verifier, its actual-counterparty
argument at the existing route call, and isolated reason-route tests. Line
references in this section are for the completed repair, not the baseline.

1. `server.py:14828` retains existing owned-impression/F1 versus legacy reason
   key selection. The route resolves the actual card or reconstructs the
   already-supported echoed context at `15024`; it banks the reason at
   `15035`. `database.py:6704` assigns `created_at` once, while refinements at
   `6715` update `updated_at` and supplied answers, never the first-bank time
   or key source. No request-supplied timestamp becomes episode evidence.
2. `server.py:15051` passes the resolved card's actual target along with its
   actual league/ID/oriented assets. `database.py:6769` retains the reason-row
   transaction lock (`FOR UPDATE` on PostgreSQL) and verifies owner, league
   and trade ID. `6776` normalizes the durable first-bank timestamp with the
   existing UTC helper at `5890`; absent/malformed episode time yields
   `(false, false)`, not a false committed acknowledgement or a new pass.
3. For a real impression key, `6781` reads only the existing impression's
   `served_at`, scoped by ID, owner and same league. Existing exact pass rows
   are selected at `6788`, still requiring the acting user, league, actual
   trade ID, pass decision and no retraction. Parsed oriented asset sets must
   match (`6799`). A non-null, explicitly different impression ID is excluded
   at `6801`; unknown/unlinked legacy decision metadata is not invented.
4. A valid matching pass at or after first bank proves this episode already
   committed (`6807`). Earlier passes can only be companion candidates when
   they followed the validated exposure's served time, or, for a legacy key,
   meet the existing ten-second replay bridge at `6812`. A validated exposure
   allows a genuinely delayed first reason after an ordinary swipe; an
   arbitrary historical same-card pass does not qualify. Malformed pass or
   served timestamps cannot establish that older companion.
5. Only if earlier candidates exist, `6823` fetches positive decisions once,
   constrained to this league and the actor/actual counterparty. `6834`
   compares actor-side exact assets or counterparty-side exact mirror assets;
   unrelated actor, league, package and direction do not split an episode.
   Relevant positives at or before first bank form barriers (`6838`). The
   `(normalized timestamp, numeric decision ID)` tuples at `6815`/`6839`
   preserve insertion order for equal-time decision rows. Any later barrier
   invalidates that candidate; malformed relevant chronology also prevents
   verifying it. A later retraction does not erase the fact that new consent
   separated the earlier action. Positives after the immutable first-bank
   anchor are deliberately excluded: a reason refinement is not a fresh pass.
6. If one companion survives, the existing pass is acknowledged without an
   insert (`6840`). Otherwise `6843` writes the genuine current requested
   pass with the unchanged decision fields. It does not amend/backdate old
   history, invent a decision for a source card or rewrite an impression.
   `(true, true)` returns only after transaction commit; the route's existing
   exception path returns an unverified `passed:false` if persistence fails.
7. Existing follow-through at `server.py:15057` binds all current-format live
   exclusions and records the actual card's pass only after durable evidence.
   Only `wrote_pass` invokes outcome/event work at `15063`. The first reason
   following an already-committed companion consumes the existing Elo claim
   at `15071`; a genuine new value-giving reason can write the signal through
   `15076`. Existing atomic claim-plus-swipe persistence, once-only outcomes,
   edited-card checks, late-league isolation and failed-insert repair are
   unchanged and stay covered by the consolidated suite. Ordinary swipe's
   existing claim bridge is now at `database.py:6852`; its behavior is unchanged.
8. The newly committed pass enters the existing normalized source history.
   `load_recent_league_likes` at `6066`, matching now at `9092`, Awaiting now
   at `9477`, and every unchanged projection boundary above therefore stop
   treating the renewed source as actionable. The original QA script and
   new real-route tests inspect that reader, not just the HTTP status.

The verifier's query count is two base SELECTs (locked reason and exact pass
rows), one conditional owned-impression SELECT for real keys, and at most one
conditional positive-history SELECT for earlier companions. The latter reads
the selected actor/league histories without a textual timestamp bound; UTC
normalization and malformed barriers are applied in memory. No N+1 loop,
serving projection query change, new index/schema, wire field or dependency.
PostgreSQL lock semantics are code-walk evidence; the reported executable
gates use isolated SQLite, not a production concurrency/load benchmark.

Identity is intentionally not reset by time. The legacy
`local:<user>:<trade_id>` reason key cannot distinguish a new episode from a
very late retry of that same key. Likewise, refining an existing real-key
episode must not silently reject a newer like. A fresh validated impression
provides a distinct reason identity; an actual new ordinary swipe retains
its normal replay window and can reject a later renewed source. Tests cover
both the preserved later source on refinement and its resolution by that
subsequent genuine swipe. No new lifecycle protocol is claimed.

Final executable evidence: 23 new reason-episode cases plus all 401 existing
focused cases, **424 passed in 9.41s**; unchanged-runtime RED and original QA
replay commands/results are in [build evidence](build-evidence.md). Root's
fresh independent QA/integration gates and operator TestFlight work remain
pending; this is a reviewed backend repair, not a release claim.

# G419 backend code walk

2026-09-06 · implementation owner · reviewed against PRD/scope at `481b1809`.
Runtime diff personally read end-to-end against `4026ebc8`; this is backend
evidence, not native UI or release verification. Shared spec-doc edits belong
to root. Detailed runs and honest RED limitations: [build evidence](build-evidence.md).

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

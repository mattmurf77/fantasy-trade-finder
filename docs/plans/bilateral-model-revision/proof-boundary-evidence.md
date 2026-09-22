# Round 6 — private authenticated proof-boundary experiment

**Decision: retain privately; do not integrate or release this proof shortcut.**
The exact checked inventories are preserved, but the modest time saving leaves
first delivery at 15.205 seconds versus the incumbent's 8.487, and local peak RSS
increases materially. Required durable provenance and broader failure/coverage
tests remain incomplete.

Agent C followed `spec-round6-proof-boundary.md`, including the parent's
supported-mutation clarification. This is one PRIVATE experiment, not shared
runtime integration, a release pass, an acceptance model, or a quality rerun.

## Boundary actually implemented

Private scripts live at `/private/tmp/bilateral-proof-boundary-20260922.7mBR9y`.
The prototype adds a thread-local crown override at exactly the two existing
pricing expressions through private AST substitution. Default/incumbent callers
continue to read the live flag. Only the explicit offline organic-worker scope
can create a registry. No source file, public API, flag or database schema was
changed by C; independent grading remains unchanged.

The registry consumes an owned, read-only typed capsule: all supported Player,
league and member attributes, full board/seed universe, ordered request arrays,
preferences, selections, draft fields and configuration. Its full exact input
binding is computed FROM the sealed data that the constructor receives, not from
a pre-copy hash of mutable caller inputs. Full effective configuration (including
raw owner limits) is resolved from copied defaults/global/thread-local/explicit
maps. The existing numerical config and market-stud contexts and the private
crown context enclose constructor initialization as well as evaluation.

Authority requires original card AND original server-produced proof objects,
exact type-sensitive ordered terms/prices/participants, every proof header type
and original snapshot bytes, and unchanged exact input/effective-config/crown
binding. Original proof strings are referenced, not duplicated. Any miss,
copied/replaced/foreign proof, partial or pinned request takes the entire original
batch evaluator; mixing fast/slow occurrence subsets could change shared-search
cache effects, so the prototype does not attempt that optimization. Ordering and
duplicate occurrences are retained. Request scope closes on success or error.

All existing final owner match/version, roster/provider, significance,
disposition, current model, durability and publication code stays in the actual
worker. A registry hit is not authority to bypass any subsequent gate.

## Supported mutation and capture limits

This experiment explicitly requires **CPython with the GIL and ordinary
string-keyed finite-scalar configuration dictionaries**. Production
`trade_service.reload_config` performs one `_cfg.update(fresh)`; database
`get_config` returns a plain dictionary. No production `_cfg.clear` was found.
Each mutable source is copied with builtin `dict.copy` before resolution; under
this declared interpreter/key/value contract, it cannot observe the middle of
that single builtin update. Tests cover actual reload and concurrent captures.
This is not a guarantee for free-threaded Python, custom mappings, a future
clear-then-update writer, or a transaction spanning separate config and flag
updates. Once captured, the constructor actually consumes pinned dependencies;
change-and-change-back cannot be certified merely by matching hashes afterward.

Player refresh builds new pools and rebinds them rather than mutating existing
Player attributes. The capsule nevertheless detaches every supported attribute
and nested board/preference field. The model's loaded code, weights, tier and
roster tables are an explicit immutable process/code-generation contract: no
supported hot reload was found. Arbitrary Python monkeypatching of those objects
is NOT supported or represented as proven safe. Deployments/new processes require
new request-local authority. The initial concern that these static objects alone
required a general dependency-injection graph was narrowed after this audit.

## Independent falsification and repairs

**63 private tests pass** (0.53 seconds); B independently reran the first 62
(0.47 seconds), then C added the named mapping/set-order control. They cover
full input and nontraded-universe changes; Player age/injury/position/team,
search_rank/pick_value and extra attributes; source/board/roster/draft changes;
ordered pins and partial authority; exact price/header types; copied/foreign
proofs and equal trade IDs; mixed/repeated/reversed batches; detached `as_dict`;
scope errors/cleanup; actual supported config/flag reload A→B→A while generating;
500 concurrent scalar-config captures; and cross-thread crown/config isolation.

Named mappings are bound by typed key/value contents. In the supported organic
adapter, player/board/source/config/preference maps are key-addressed; full-board
coordinate values are sorted for percentiles, and proof JSON sorts named keys.
`starter_requirements` updates fixed position keys without reordering them.
Supported sets are disposition/exclusion package keys used for membership.
The new reversed-mapping/set-layout control preserves native order, all exact
proof/report bytes and fresh-evaluator bytes. Ordered roster/member/slot/pin
arrays remain order-sensitive. This does not generalize support to arbitrary
set-valued rosters/slots or future consumers that sum in mapping order.

Three pre-measurement/review defects were explicitly found and repaired:

- C changed the binding to derive from the actual sealed input; hashing before
  copying could otherwise bind state A while consuming state B.
- B found `eligible=True` versus `eligible=1` aliased in ordinary tuple equality.
  Header fields now use exact typed binding, with the full proof string retained
  only by original reference.
- Parent found the same int/float alias in effective-config dictionary equality.
  A named real-reload `owner_pool_size=16` to `16.0` control now misses reuse.
  That fixture changes provenance, not numerical package prices.

The private worker scope wrapper initially disconnected granular stage callbacks
because the timing harness installs its callback through function globals. C
repaired the wrapper to share the original worker globals and added a regression.
The preliminary first-durable/completion probes and full payload comparisons were
independent of that callback, but no preliminary stage attribution is claimed.

## Controlled worker and exact parity

The final group is `current-final2`, `boundary-final2`, `inc-current-final2`,
`inc-boundary-final2` and `boundary-failed-write`. All five completed with
identical complete guarded source manifests, including the new age helper.
Core constructor/policy sources remain unchanged; final server/helper bindings
are `3fa92ee850dfc8eb01a69ab7d052a85f8cda5facc158ac84d730ad27d2ed19c6`
and `d294a4d049c00c4191d7e5964197452ff7c4fad3140572ff23cd98a8d0c27065`.
Private proof source is
`e59df5cb587cc82dd22ac848c17db9aa45457d99912b62917db4c0da6f9e7026`;
`run_boundary.py` is
`fbf5501fc12184f544832d882668f1611836370eca4b7044752eebd2a5ca0095`.
These are whole-file source guards, not public cache-authority digests.

Earlier `current-r1` / `boundary-r1` and `current-final` artifacts remain private,
explicitly preliminary/superseded by safety/source repairs. They preserve the
adverse RSS observation rather than silently discarding it. The first
`inc-current` startup overlapped an artifact comparator and is not a controlled
timing reference. One mistyped Python path failed before any worker started;
the corrected final invocation below succeeded.

| Same-source final worker group | First durable 30 | Completion | Peak RSS, bytes |
|---|---:|---:|---:|
| Incumbent, no prototype | 8.487 s | 11.355 s | 660,848,640 |
| Incumbent, boundary installed but inactive | 8.611 s | 11.474 s | 603,062,272 |
| Current candidate policy3 | 18.646 s | 23.847 s | 715,980,800 |
| Candidate with private proof boundary | 15.205 s | 20.511 s | 913,981,440 |

This is one controlled paired diagnostic, not a latency distribution or SLA.
Candidate first-durable time falls 18.5% and completion 14.0%, but still trails
the incumbent substantially. Construction increases from 10.266 to 10.734 s;
owner final revalidation falls from 5.162 to 1.382 s. Ordinary match/parsing and
exact certificate checks still cost time. Dispositions take 1.875 versus 1.763 s,
and complete evidence/publication takes 5.298 versus 5.360 s. No output cap,
thinner proof, smaller search budget or shifted durability boundary supplies the
saving. Each successful candidate run retains all 3,306 final served cards and
34 exact public-content/durable-impression prefixes; incumbent runs retain all
2,354 and 25 prefixes. The candidate registry authenticates all 3,836 native
occurrences before independent final serving checks, with zero fallback batches.
Off-mode creates zero registries and reuses zero proofs.

Exact comparison checks BOTH canonical type-sensitive hashes and values for all
public fields and every re-read persisted row/diagnostic field:

- Candidate public SHA256:
  `414f3bfddaddb0dccea5de413995ef0ae225506cb2ee9d29635c40e40c8d9fe8`;
  full persisted rows:
  `baa60140cd0a3a0a25a55cdb7023cde4e2d88c4582c31807eb121e95f79dcafa`.
- Incumbent public:
  `3ff38c9ea4ec30730f5f6785c66d1915cc266716bfe39c2531eaf560d0358cc2`;
  full persisted rows:
  `1b9ec1e4563ac05fc4ccc1405d17ab357cd2586ce285eab2a7b0f1d44cfa2a6c`.
- Fresh native exports match every normalized BYTE of all 3,836 candidate cards
  (`5070cbcd96ca0bd77c1d287a9fe3231771c1bbb1f63e0cea932d051209a063c5`)
  and complete report
  (`3baf157d373843562b29dd6fc0a9781e22d92da4ab471204d7c208be81fcdc3a`).
  Off-mode preserves all 2,843 native incumbent cards
  (`d2d450f82d0d6879bf6cf77d82dced44b736fcbb401f2c330bd6f5e2de4712e7`)
  and report
  (`2c7c4ab629ccc82169f75b8e865a8d17c2e13d450b61ecf0ae2b09f9db07c5d3`).

Only the previously enumerated volatile fields are normalized: public trade_id,
impression_id and expires_at; persisted impression_id, candidate_set_id and
served_at; feature owner_request.captured_at, roster_evaluation.observed_at and
owner_generation.elapsed_seconds. Native exports exclude only trade_id,
created_at, expires_at and report elapsed_seconds. Proof `snapshot_json` and
persisted `valuation_json` remain byte-exact in the matched runs; diagnostic
references are expanded before full-row comparison. No private score, selection,
roster, package or provenance field is excluded.

The actual worker's injected first evidence-write failure finishes with the
expected error after 15.225 s: despite 3,836 registry hits, **zero cards and zero
impressions** are published/stored, there is no first-durable timestamp and the
scope closes. This is an explicit negative safety control, not a successful
latency sample. Its intentionally false inventory/persistence-success fields are
retained in the private artifact rather than counted as a successful worker.

Every process uses `PYTHONHASHSEED=0`, scratch SQLite and blocked networking.
Input is the original controlled worker capture, independently matched to
development corpus record 10 (not a holdout and not one of the quality panel's
selected contexts). The retained quality grader is not consulted by the model.
Existing uncontrolled process hash-order/lineup floating behavior is a known
reproducibility limitation, not attributed to this prototype.

## Memory, lifetime and integration prerequisites

The final same-source pair's local process high-water RSS rises from
715,980,800 to 913,981,440 bytes (27.7%). The preliminary pair independently
showed 732,348,416 to 924,139,520. The registry retains its sealed context,
full-input/config bindings, exact term/header signatures and strong references
to original proofs until scope closure after the worker returns. It does not
duplicate each full proof string, but request-local does NOT mean negligible
memory. Generation's existing search caches and final serialization also
contribute. No allocation profile isolates the cause of the RSS delta; do not
attribute all of it to capsule/signature bytes or infer a memory saving.

The native export separately counts 580 sealed players, 580 seed entries and
360 resolved configuration keys. The full input binding is 409,246 UTF-8 bytes;
term bindings total 1,537,164 and small header bindings 792,588. The registered
proof bodies total 43,312,710 UTF-8 bytes, and every registry payload entry points
to its original string. These are payload/reference counts, not retained-heap
sizes: they exclude Python container/allocation overhead, other existing model
caches and serialization buffers. The registry keeps strong proof references
through publication, so lifetime and cancellation remain important even without
body duplication. The one native RSS pair is not used to claim memory savings.

Production capacity readback is one CPU / 2 GB per instance; local macOS RSS is
not free Render memory, concurrent capacity or PostgreSQL latency. This experiment
provides no safe concurrency bound. Releasing registry state immediately after
its one final validation, and bounding/cancelling request lifetime, would require
separately validated integration work rather than an unmeasured memory claim.

Existing durable evidence does **not** completely bind a future pinned authority.
The request stores caller/raw config; the generation report records selected
configuration prefixes; per-proof market evidence records floors/stud mode and
overpay settings. None records the captured crown-enabled boolean or the complete
effective dependency receipt. A shared integration would need a private,
once-per-request versioned receipt with complete effective config, crown value,
market mode, exact typed full-input identity and process/code/table identity,
referenced from durable diagnostics. Such a receipt is audit provenance only:
it must never authorize copied/historical proofs or bypass live serving gates.

No release, production change, broad cache, shared proof-validation shortcut,
quality threshold change, smaller search budget or combined optimization is
authorized by this result. The full failure/retained-panel integration matrix and
production contention evidence remain prerequisites to any shared implementation.
In particular, injected roster/disposition/expiry/version/supersession failures
under an actual registry hit and all retained panel contexts were not newly run
here. The original pipeline's existing contracts remain separate evidence; the
one worker's normal gates and failed-write control do not establish every failure
case. No result is a new acceptance or independent model-quality claim.

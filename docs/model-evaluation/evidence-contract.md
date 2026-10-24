# Bilateral scorecard evidence contract

Draft version `scorecard-evidence-v1`, September 22, 2026. This contract implements
an offline bridge to existing evidence. It does not add production instrumentation,
migrations, randomized assignment, retention changes or a release decision.
The [source audit](source-audit.md) pins exact storage/writer semantics. The reviewed
[scorecard](../plans/model-evaluation-framework/scorecard-spec.md) defines metrics
and the [playbook](../plans/model-evaluation-framework/ways-of-working.md) defines
ratification and release responsibilities.

## Implemented adapter

`backend.eval.scorecard_evidence` uses the standard library only. It imports
neither `backend.database` nor `backend.server`, accepts no SQL or database URL,
reads no environment variables, and makes no provider/network calls.

| Function | Input | Result |
|---|---|---|
| `load_sqlite_snapshot(path)` | Explicit existing local SQLite snapshot file | Allowlisted table/column row mapping; `file:...?...mode=ro` connection plus query-only mode, one read transaction; views/virtual tables refused |
| `load_export(path)` | Explicit local UTF-8 JSON file, `{tables: {table: [row]}}` or bare table map | Same allowlisted mapping. Unknown tables/columns, free-text pass reasons and full provider payloads excluded |
| `audit_rows(tables, include_records=False)` | Detached rows from either reader or explicit in-memory exported rows | Aggregate counts, row-content hash, table/column presence, per-occurrence evidence coverage, join/JSON/integrity gaps, and absent fixed-cohort status |
| `audit_rows(..., include_records=True)` | Explicit request for sensitive detail | Adds `private_records.occurrences`, `.events`, `.source_tables`; raw source columns and separately decoded snapshots remain available locally |
| `frozen_owner_requests(tables)` | Run-ledger rows | Private full owner `config_json.input` requests with source keys, status, assignment/capture metadata. No fixed-cohort claim |
| `occurrence_to_offer(occurrence)` | One normalized occurrence with valid assets and matching valuation | Conservative `scorecard_dimensions.evaluate_offer` input; missing evidence stays absent and model outputs are not review labels |

Caller paths must identify local files; URIs, remote database strings and
`:memory:` are refused by the readers. A missing SQLite file is never created.
Use a coherent operator-created backup/export with a known capture cutoff; this
adapter does not copy or query a running service. Its complete reads are intended
for deliberately sized offline exports, not an unbounded production connection.
The JSON outer structure must parse; malformed inner JSON is retained in explicit
private raw rows and counted as malformed. Missing tables are distinct from
present empty tables. For an empty row export, column coverage is unknown/empty
because row data cannot prove a source schema.

The default report contains no manager/league/asset IDs, private ranks, free text,
raw request contents or source paths. It contains aggregate row/coverage counts
and a SHA-256 over canonical selected rows, invariant to row ordering. This hash
identifies the selected input content; it does not authenticate capture, approval,
or every byte of the underlying database. Detailed output is sensitive even
after the top-level column allowlist: frozen JSON includes private boards and
manager preferences. The caller must control output storage and access.

## Normalized facts and unknowns

An occurrence retains its source primary key, actor/partner/league/job/concept,
the original asset ID strings in original give/receive order, separate model and
policy identity, serving timestamp, delivery/injection lineage, original raw row,
decoded valuation, expanded scoped diagnostic features, and per-field evidence
presence. The original valuation is never replaced by match-time, provider-send,
later-counterparty or current-state values. Duplicate/overlapping assets and
valuation binding mismatches are reported, not repaired or dropped.

Policy valuation schema binds `assets.give` and `assets.receive` independently.
Owner valuation schema stores a flat give-then-receive list; the adapter checks
that exact concatenation and labels its weaker binding class. Production's owner
writer checks the richer immutable decision object before persistence. The
adapter does not claim that the persisted flat JSON independently contains those
discarded object fields.

Diagnostic expansion keys on `(user_id, deck_job_id, snapshot_id)`. Missing,
duplicated, cyclic or malformed references are explicit gaps. This preserves
privacy boundaries and prevents borrowing another manager/job's data merely
because a hash-like ID matches. Raw reference strings remain in the original row.

Events retain their original ID/action/time and actor identity only when they
join exactly one source impression. An action is not manufactured from a pass
reason or from a generated offer. A counted view requires a uniquely linked
`viewed` row with a parseable time on a non-ghost occurrence. This is a stored
client-view event, not independent verification of device behavior or complete
observation. Timestamp validity does not prove ordering, freshness or maturity.
The adapter leaves duplicate/undo reduction to the lifecycle evaluator.

Stored matches remain source evidence requiring exact-term, actor and temporal
validation. Their current acceptance/decline/archive states are not provider
completion. Proposals remain confirmed sends even when a transaction ID exists.
Existing matcher “exact” labels can relax generic picks to a round; they are not
automatically exact episode completion proof. Completed provider transaction
counts therefore remain unlinked evidence, and verified exact episode completion
count is zero until a separate defensible link is supplied.

The dimension bridge uses captured owner rosters to substantiate ownership and
captured package player metadata to classify assets. It preserves selected versus
inferred outlook; does not guess selection from inference; does not fabricate
pick rounds from display names; and does not turn dynasty roster proxy values
into projected points. Captured per-asset values remain raw facts, while missing
market source vintage prevents a supported market assessment. Independent
personal tier/order evidence and reviews must be supplied through a separately
audited normalization/annotation process. Package-only valuation universes are
labeled as such, never treated as full personal-board universes.

The dimension bridge supplies `captured_at` from the source occurrence's
timezone-qualified `served_at`, the evidence assembly timestamp. It does not
substitute the market publication date, today's clock, or a later linked snapshot.
Missing/malformed/timezone-ambiguous capture timestamps remain null; affected
evaluations are Unknown. Independently supplied market vintage must precede that
capture boundary; the dimensional evaluator rejects future-dated evidence.

## Identity and prospective episode data

These requirements define future evidence, not implemented production columns:

- Stable league-scoped participants and raw exact asset IDs/direction, including
  structured pick ownership/year/round and versioned parser provenance. Keep
  account and league-owner identity mapping explicit.
- Immutable occurrence/model/config/policy/input identities; source timestamps
  and capture timestamps separately; full selected/inferred outlook, explicit
  board provenance and complete roster/rules/projection units as available.
- Separate generation, durable commit, delivery, qualified view, actor-stamped
  action/undo/retraction, mirror eligibility, mutual milestone, disposition,
  provider-send and provider-completion times. Log actual expiry/invalidity.
- Frozen origin request/window/assignment and exact concept, all contributing
  constructors, selected serving source and later delivery surfaces separately.
  Preserve shared/unknown/carry-in attribution; do not transfer old credit after
  injection, deployment, redisplay or an arm switch.
- Eligibility rule/version, explicit eligible manager-league membership frozen
  before assignment, cluster/assignment/probability, no-request members and
  failed/empty requests. Existing `request_inputs` assignment is not this data.
- Append-only actor action identities and validity intervals; first historical
  overlapping-interest milestone distinct from current state, later reversal,
  follow-up horizon, maturity and observation completeness. The proposed deadline
  is first qualified exposure +14 days capped by actual stored expiry; absent
  expiry does not authorize inventing one or extending production lifetime.
- Verified exact provider transaction link with original/final terms, platform
  support, frozen participant mapping and observation cutoff. Amended terms
  remain separate outcomes rather than upgrading the original recommendation.
- Counts at every constructor/policy/delivery stage; reproducible sampled rejects
  with sampling probabilities and native/post-policy ranks. Sampling must not
  limit production generation or actionable publication.

These require a reviewed event/taxonomy/schema contract and retention decision
before emitters or storage changes. They are not automatically enabled by adding
an offline evaluator.

## Retention, access, and deletion

Existing debug-node retention defaults to 14 days; original valuation/outcome rows
are retained separately. A deleted historical node is unreconstructable without
an authorized retained contemporaneous copy. Missing exports must never be
repaired from current boards, current ownership, future pick slots or downstream
rank updates from the labeled action. Audit missingness by source/model/platform
and retain affected fixed-cohort members in the denominator once enrolled.

Before maintaining a research corpus, the data owner must document storage owner,
purpose/source rights, access roles, encryption, export scope/cutoff, expiry,
subject deletion propagation, backup policy and permitted downstream uses. Keep
private snapshots, raw IDs, boards and annotated examples out of public reports
and Git. Access-controlled manifests may identify source records/hashes. Deletion
requests propagate to exports, derived labeled data and cached detail; aggregate
retention must follow the separately approved policy. This implementation grants
no new permission, changes no retention duration, and opens no remote system.

Verification: `python3 -m pytest backend/tests/test_scorecard_evidence.py -q`.
Fixtures use only scratch SQLite/JSON and synthetic identities. They cover
read-only connections, table allowlisting, source linkage, immutable original
snapshots, diagnostic loss/scope, malformed data, view versus generation,
send versus completion, and missing-cohort/independent-label discipline.

## Frozen inputs: what a scorer or a fit may read

**Inputs are frozen per card; configuration is pinned and recorded per run.**
The rule (models-lead, `docs/plans/org-bringup/leads/models-lead-launch.md`
§Reviews-4 R4.1, 2026-10-23, and §Reviews-5 R5.2 (a) and (b), 2026-10-24), for
every registered scorer and every model fit:

- **Every per-card value a registered scorer or a fit reads is frozen at serve
  or build time,** or is a deterministic function of frozen inputs plus
  pre-split training data.
- **No fit or eval path reads mutable live state:** taste rows, current values
  or boards, current rosters, flags.
- **Configuration a fit or an eval reads is pinned and recorded per run.** The
  run reads each value once, records the exact values used plus the SHA-256 of
  the whole live `model_config`, and a refit or replay takes those recorded
  values explicitly. When it is given them, it reads no live config.
- **A fit and a read take an explicit `as_of`.** Nothing reads the wall clock.
  A read sees only decks served at or before `as_of` and outcomes acted at or
  before it. When labels must be complete, choose `as_of` with a settle lag
  (at least 7 days after the window's last `served_at`). The lag is a parameter
  of the read, never of the loader.

How the code meets it today:

- The frozen scorer inputs are `backend/eval/contract.py` `FROZEN_INPUT_KEYS`
  (18 keys). They include the serve-time taste matches `taste_pref_long` and
  `taste_pref_short`: the two prefMatch values `taste_service.taste_multipliers`
  ordered the card by, float8, absent when the taste layer didn't run.
- `value_model.ValueModel._inject` reads the frozen pair (absent = 0.0, the
  no-signal anchor, identical in training and eval). Only live serving
  (`value_model.serving_scores`) reads taste vectors; no fit or eval path
  calls `taste_service.load_taste_vectors`, so an eval no longer garbage-collects
  taste rows either.
- `value_model.train_model(decks, as_of=...)` takes the clock explicitly, and
  `trained_at` / `train_date` come from it. A re-fit at the same `as_of` on the
  same evidence is bit-identical: coefficients, calibration tables and every
  registered scorer's replay estimates. `backend/tests/test_value_model_frozen_taste.py`
  checks it after the clock moves, new outcomes arrive, a board prior is
  rewritten and taste rows are GC'd.
- The writer's parity check: `backend/tests/support/taste_parity.py`
  (`assert_frozen_prefs_match_multipliers`) passes only when each card's frozen
  pair is, bit for bit, the pair its taste multiplier was built from.
- **Pinned configuration (R5.2 (a)).** A record is `value_model.pin_config(keys)`:
  `{"values": {key: value}, "model_config_sha256": <SHA-256 of the live
  model_config dict, canonical JSON>}`.
  - A fit pins `value_model.FIT_CONFIG` (`value_model_calib_frac`,
    `value_model_l2`, `value_model_l2_cat`) and records it in the model's
    `meta["config"]`, which is persisted in `models.jsonl`. `train_model(...,
    config=meta["config"])` refits from it with no live read.
  - An eval pins `value_model.SCORE_CONFIG`, the V-vector (`value_model_v_like`,
    `value_model_v_propose`), on `EvalRun.config` and in its run record. A
    scorer that reads no configuration records `config: null`.
    `get_scorer("value_model", config=run.config)` builds the scorer with it
    as a constructor argument, and `replay.evaluate` with that scorer replays
    the run with no live read. The pin is never held in thread or global state.
    The replay CLI and the nightly pin once and share that one pin across every
    scorer in the run.
  - Live serving still reads the V-vector live, by design (F6 PRD §2: strategy
    changeable without retraining). It is pinned for evals only.
  - Test: `test_config_is_pinned_and_recorded_and_replays_after_live_config_changes`.
    After live `model_config` changes, the refit and the replay are bit-identical
    given the recorded values.
- **The read's clock (R5.2 (b)).** `eval.data.load_decks(as_of=...)` filters
  `deck_outcomes.acted_at <= as_of` and `served_at <= as_of`.
  `replay.settled_read(now=..., settle_lag_days=7)` picks the window
  (`until` = now minus the lag) and `as_of` = its last `served_at` plus the
  lag. The replay and nightly CLIs take `--settle-lag-days` (default 7); the
  replay CLI also takes an explicit `--as-of`. The daily tick's
  `nightly.run_all()` keeps `as_of` = now.

**Known exceptions, not yet closed:**

- Decks served before the freeze ships carry no frozen pair and score with the
  0.0 anchor. models-lead recommends starting any D-016 gate window at the
  freeze date.

# Small-player presentation — code walk

2026-09-06 · runtime `9ea562dd98861bcfae388146feca97e7e4c04942`.
Paths/lines below identify that commit, before later integration shifts.
[Build evidence](build-evidence.md) records executed checks and remaining gates.

## Capture and all cache boundaries

1. `backend/trade_service.py:1293` and `backend/database.py:2942` register only
   neutral Float default `simple_player_presentment=0.0`. Neither changes
   generator math or an arm profile. `small_trade_presentment.py:18` accepts
   exact finite numeric 1, rejecting bool/string/unsupported inputs.
2. `server.py:3119` reads raw shared config outside arm overlays and captures
   `(mode, presentation_version, base_serving_version)` once. Compatibility
   at `:3127` compares mode/version, treating a missing pre-feature capture
   as off, never as enabled.
3. `/generate` captures at `:13524`. Both completed freshness (`:13539`,
   helper `:3133`) and its distinct running-job branch (`:13555`) require
   compatibility. All existing freshness/safety/fairness/outlook/intent and
   force/supersession decisions remain. A mismatch starts a compatible job;
   it does not mutate the old snapshot into the new order.
   At `:13528` a private raw-receive exemption survives the pre-existing
   targeting flag's normalization. While mode is on, this request bypasses
   organic reuse; existing give/opponent exclusions remain. The ignored
   generator receive argument and default fairness are not changed.
4. Session-init pregeneration captures at `:21158`, checks its own cache at
   `:21162`, then passes the same value at `:21177`. Replenishment captures
   at `:21963`, checks at `:21977`, then passes it to synchronous kickoff at
   `:21994`. Neither side cache relies on TTL alone after a mode change.
5. `_kickoff_trade_job` captures only if its caller omitted the value
   (`:8234`), stores the private job field (`:8284`) and passes the same
   tuple to synchronous (`:8310`) or background (`:8322`) execution. Raw
   receive exemption is private too; an exempt mode-on job cannot seed the
   organic index (`:8292`). Off-mode cache behavior remains unchanged. The
   existing account lifecycle lease and immutable league/format execution
   context remain intact. Legacy direct-worker callers capture at entry
   (`:6959`); direct mode-off historical jobs retain their missing-field
   canonical-off compatibility, preserving their old harness shape.

## One post-policy permutation

The worker retains `final_checks_pending` protection for live checks. Actual
bakeoff provenance and grouping mode are captured before arm execution
(`server.py:7261`). Existing `_evaluate_deck_policy` (`:5558`) remains the
final eligibility/composition authority; successful evaluation is recorded
before the following presentation decision. Failure still clears live unsafe
supply and cannot be rescued by this feature.

The only production `present` call is `server.py:7857`, after final policy
handling and before constructing the first evaluated snapshot (`:7868`).
The guard requires captured mode-on, successful live market/mutual policy,
no explicit give/receive/opponent (including the captured raw-receive
exemption at `:7853`), no active ghost withholding, and no
bakeoff dark/single-arm result. Demo and shadow-only jobs are excluded by
the existing live-policy gate. No manual/Win Now/asset-ideas endpoint calls it.

`small_trade_presentment.py:25` classifies each side through existing generic
and league-owned pick parsers plus canonical `is_pick_asset` and existing
`VALID_POSITIONS`. Generic pseudo assets may carry a real ranking position
and `team='PICK'`; they still contribute zero players. Unknown/conflicting
classification is null, not guessed zero. Pure-pick cards are fixed; a
player-for-pick card is eligible to move.

`small_trade_presentment.py:57` forms the exact class from actual eligible
policy lane, actual `BakeoffRun.attribution_for` and `group_for`, card lane
and basis. Legitimate group-size-zero nulls are allowed; missing required
group/arm metadata locks. Expected-but-missing bakeoff never becomes organic.
True non-bakeoff execution uses absent internal source metadata, without
stamping a fabricated model arm.

`small_trade_presentment.py:96` records each input occurrence and its counts,
locks special/unknown/pure-pick positions, then stable-sorts identical-class
positions separately inside disjoint six-absolute-slot windows. The key is
only `(maximum players on either side, total players)`. Arm/group ranks are
not part of the key/class. Equal costs stay stable; picks are not a tiebreak.
Output is the same object-occurrence multiset and unchanged package values,
never new candidates, truncation, deduplication, eligibility relaxation or a
generator reorder. Each pre-removal displacement is ≤5.

The first evaluated snapshot now consumes that output before releasing
`final_checks_pending` (`server.py:7879`). Breaker annotation is still only
annotation. Logging flags do not determine this publication order.

## Final #419 removal and immutable occurrence records

`server.py:7969` preserves the presented sequence, then calls unchanged
`_project_trade_dispositions` before either impression writer. A newly
committed pass or resolved source-interest card can therefore disappear.
`small_trade_presentment.py:133` follows the returned identity/occurrence
subsequence exactly, carrying each surviving record's original index through
the removal. Repeated occurrences of one object do not collapse into an
identity-keyed record. There is no stale zip of shortened cards against an
unfiltered metadata array, no reconstruction of original indices and no
second sort.

The filtered snapshot is republished regardless of F1. Legacy impressions
at `server.py:8020` enumerate this surviving order. F1 receives it unchanged
at `:8054`. The pure permutation's window/class/max-displacement invariants
precede this removal; legitimate compaction does not violate them.

At `server.py:4891`, F1 adds existing `features_json.presentation` per
occurrence, freezing `final_index` from the actual writer enumeration that
also supplies `card_index`. Original indices/counts/version remain those of
the pre-removal presentation input. Even locked or unattributed first rows
carry the metadata; unknown side counts remain null. No raw private values
or new identifiers are introduced, and no impression-ID redesign is made.

The separate presentation argument does **not** enable suggestion telemetry:
the existing `policy_version is not None` gate at `server.py:4724` remains
unchanged. Captured base version passes through its existing enabled path at
`:8050`. Presentation instead writes the existing policy-version column on
every applicable row (`:4982`); the existing arm helper (`:5022`) appends
`/bo:<arm>` after `/pp:simple-player-v1`. Existing source/group ranks,
agreement, propensity, scores and valuation `policy_variant` are not
recomputed by presentation. Organic rows retain absent model attribution.

Later explicit-ID `/status` (`server.py:14117`) and cached responses use the
existing public projection (`:2997`) and #419 current-disposition checks.
They may remove cards without changing surviving relative order, but they
never call presentation or rewrite frozen positions/valuations. Rollback
changes compatible fresh jobs, not the order of a retained old deck.

## Validation boundary

The actual worker held-publication test starts at
`backend/tests/test_small_trade_presentment.py:237`; its F1-off variants
prove first/final publication and legacy order do not rely on F1. Both-format
real bakeoff movement starts at `:100`; hot flips at `:296`; actual cache
routes at `:322`, `:354`, `:372`; actual kickoff at `:395`; exemptions at
`:416`; uniform locked-first-row F1 metadata at `:456`; raw-receive route
exclusion at `:480`. Existing goldens were not recaptured, and all 741
focused checks passed. Baseline RED and
conditional anonymous shape diagnostics are documented separately.

Full integration QA, shared docs and physical
TestFlight checklist remain parent-owned gates; this walk does not claim
deployment or activation.

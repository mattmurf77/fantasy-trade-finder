# Independent dimension development fixture

`opposite-objectives.json` is fully synthetic and corresponds to scorecard-spec
worked case A: a tanker sells RB production for a personally preferred WR and a
next-draft first; the contender acquires its preferred RB and gains exactly three
projected points under a legal lineup. The arbitrary fixture values, tiers and
point projections are not real players, thresholds, accepted trades or measured
constructor performance. This is a known development case, never a holdout.

The JSON intentionally omits contextual annotations and stud reference bands.
Running `evaluate_offer()` on it computes inspectable raw features while all six
bilateral dimension results remain evidence-limited. The test helper adds
explicit synthetic independent annotations for the plan's illustrative ordinal
grades. It also adds the synthetic 2.5–2.7 total-return band around the 2.6 return;
that band exercises software and has no empirical or universal pricing meaning.

The public pure function and its minimal input contract are documented in
`backend/eval/scorecard_dimensions.py`. Review provenance includes source, date,
version, frozen snapshot identity, independence/kind, and an orientation-invariant
exact-terms hash. Annotations use canonical manager IDs. The evaluator does not
validate that a human actually authored supplied annotations or that an upstream
snapshot capture was accurate; the evidence owner must establish those facts.

The frozen offer declares `captured_at`. Source `as_of` values must parse and be
no later than that capture. Independent reviews may be written retrospectively,
but must fall within a separately declared `evidence_cutoff` (defaulting to
capture). Missing times and future inputs are Unknown, not accepted as fresh.
Projection grades require an explicit `fresh: true` source attestation. A market
capture date can support raw as-captured diagnostics while its publication date
and current freshness remain explicitly unknown.

The synthetic first includes a declared audited ownership/expiry marker under
`pick_validation`. Real pick ID strings alone do not provide this evidence, and
an original roster ID must not be relabeled as a manager ID. Missing year,
original owner or validation leaves affected assessments Unknown while keeping
raw pick counts/shares. Explicit invalid ledger evidence or a sourced completed
draft calendar quarantines the offer. The evaluator does not invent a pick ledger.

Missing boards, non-explicit entries, unknown youth, unsupported league rules,
unidentified cuts, stale/non-point projections and absent reference bands remain
unknown. Tanker/rebuilder immediate starter improvement is explicitly N/A while
overall needs requires applicable roster/portfolio evidence. Ordinary
meaningfulness uses individual player tiers or an explicitly comparable scalar
reference, plus actual first-round picks; a sum of scraps and actual second-round
picks do not create a centerpiece. Market and personal disagreement stays visible.

The independent lineup solver enumerates slot masks (at most 16 slots), assigning
each player once. Tests compare it against a separate exhaustive Cartesian
oracle, including FLEX/Superflex and unavailable players. It evaluates one
explicit projection horizon at a time; multi-week availability modeling,
replacement uncertainty, marginal depth valuation and materiality calibration
are not supplied by this fixture or evaluator.

## Verification and negative controls

Run `python3 -m pytest backend/tests/test_scorecard_dimensions.py -q`.

The suite covers worked cases A/B/C, both managers' give/receive/package,
orientation/order invariance, input immutability, exact terms and ownership,
selected outlook, own next-draft pick protection, reviewed tanking RB exceptions,
personal focal value mass, within-tier order, named cuts, absent/stale projections,
individual significance, and independently bounded stud compensation.

Three named deliberate code sabotages run under isolated monkeypatches. Their
guard assertions are required to fail, then patches are automatically restored:

- `turn_off_stud_tax`: changes the computed undercompensated seller grade to 2;
  the seller-failure assertion turns red.
- `swap_personal_boards`: calculates one manager's gaps with the other's board;
  the known-signed outgoing preference assertion turns red.
- `dynasty_value_as_points`: substitutes market values in the independent lineup
  solver; the manually known +3 projected-points assertion turns red.

No grading/production module is imported, no database or network is touched, and
no saved personal rank or live gate is changed. Unknown grades are expected on
real evidence until independent domain calibration and price-reference work are
complete. A favorable synthetic result does not grade a production model.

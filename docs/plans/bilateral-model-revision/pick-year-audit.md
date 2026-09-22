# Pick-year contract audit — September 22, 2026

This is a source/config audit, not a new pricing proposal or external market
calibration. The original revision plan called later-year pick discount an
unresolved generic interview gap. Current code and the later recorded owner
rulings distinguish **firsts from subsequent rounds**; flattening all rounds
would contradict that more specific contract.

The recorded August19 D-079 direction preserves similar first-round value across
years while permitting later rounds to decline. D-161 records the August24
reaffirmation and extends the first-round protection to the market-price path.
See `living-memory/DECISIONS.md` D-079/D-161 and
`backend/pick_values.py`:

- `year_decay` reads a separate rate per round; the ladder and fallback use1.0
  for firsts and0.85 for rounds2–4, with deep rounds using round4.
- `priced_pool_value` uses a resolved current-class slot if available; otherwise
  it uses the market round curve, then `_r1_yoy_floored` for future firsts. The
  floor references the current class in the same market snapshot, not the wall
  clock or earliest pick remaining in a league. It is a floor, not a peg; a
  higher market first-round value remains higher.
- Rounds2–4, exact current-class slots and a missing-market stored fallback are
  intentionally not subjected to that floor. Missing market data is not newly
  fabricated pricing evidence.

The already captured **GET /api/admin/config** production response at
2026-09-22T05:31:54.003901+00:00 contains:

| Key | Value |
|---|---:|
| `pick_year_decay_r1` |1.0|
| `pick_year_decay_r2` |0.85|
| `pick_year_decay_r3` |0.85|
| `pick_year_decay_r4` |0.85|
| `market_r1_yoy_floor` |1.0|

This is a timestamped existing capture, not a new current-state readback. No knob
was changed. The completed6,690-test backend run includes
`test_pick_year_decay.py` and `test_pick_yoy_floor.py`, covering flat future
firsts, retained later-round decay, market floor versus peg, slot/fallback
exemptions, configuration rollback and the actual injector seam. Those fixture
checks do not prove every existing stored pick row or stale historical offer has
been repaired.

Decision: preserve the existing differentiated policy in this revision. Audit
offer-time pick identities, source/fallback provenance and observed round/slot
pricing separately; do not label later-round decay itself a new constructor
defect or use a global repricing to improve this candidate's scorecard.

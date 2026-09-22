# Agent B — preserve age provenance in future owner captures

Parent implementation specification, September 22, 2026. Read scope.md and
input-evidence-feasibility.md. This corrects evidence collection lost when absent
age is replaced by25; it does not reprice players or silently change eligibility.

## Ownership

Own new pure `backend/trade_input_evidence.py`, its focused test file, and narrow
server edits ONLY in `build_universal_pool`, `_build_universal_pools_locked`,
`_owner_generation_context`, `_owner_selected_assignment`/request projection as
needed. Coordinate with parent before any other server edit. No edits to the
candidate, grader, presentation, flags, schema, client or historical captures.
Parent will separately decide model use after independent evaluation.

## Contract

Build a private age-provenance sidecar from the EXACT raw/enriched rows already
used for a successful pool build. Keep current public Player.age, Player schema,
prices, pool API return value, source priority and direct legacy callers intact.
Record source, validated selected age or Unknown, fallback/imputation state and
available source observation time. Numeric25 without provenance cannot be deemed
imputed or observed. Reject bool, nonfinite, malformed and nonpositive age as
positive youth evidence. Never invent observation timestamps or derive birthdate
age without an explicit as-of contract. Picks are not human age evidence.

Bind evidence to the specific pool objects/generation in the same atomic pool
entry. Pool rebuild/invalidation must not leave stale sidecar evidence attached
to newer players. Since request dictionaries can mix injected picks or different
player instances, attach only evidence whose pool-player identity AND relevant
attributes match the captured objects; otherwise record Unknown. No process-wide
unbounded registry, new DB reads or provider calls on the Find a Trade path.

Capture once in a private top-level owner request evidence field for the new
revision only (default-off request hashes and kwargs behavior unchanged). Ensure
replay's strict Player(**attrs) is unaffected. If generator kwargs do not permit
the field, add it to a distinct private request-evidence channel rather than
loosening arbitrary inputs globally. Project per-offer age rows with other exact
asset data; the once-per-run full evidence retains the join. Do not write future
source rows into old immutable captures. No new public response fields or exposed
counterparty board information. Explicitly distinguish evidence collected from
evidence used in model decisions.

Tests: genuine25 versus fallback25; DB/source priority; missing/invalid/boolean/
infinite age; picks; no extra provider or DB calls; two formats; rebuild and
mixed/stale objects; missing legacy evidence; strict replay; per-offer projection
and private-only serialization; dark-mode hashes unchanged. Use named red control
and restored green. Document in age-evidence.md. Do not mutate files while A/C
have a guarded measurement; coordinate first or author private patch until clear.

## Parent clarifications before implementation

The second build-new-then-rebind loop in `_invalidate_player_pipeline` is also
authorized, solely to keep each rebuilt pool entry and its evidence atomic.
A minimal dict-compatible private evidence attribute is acceptable to avoid
changing strict generator kwargs. It must be detached at assignment capture,
explicitly marked `used_in_model=False`, and absent from default-off contexts.
Document and test loss/fallback on ordinary dict copying rather than asserting
evidence survives an unsupported transformation. Keep request-level evidence
outside the strict replay Player payload and project only exact offered assets
for per-offer records. Generation itself must never rely on that hidden attribute.

### Capture-correctness amendment

Candidate-only owner contexts must detach the complete generator input tree,
including Player objects and nested selections/preferences, before generation.
Resolve pool-bound age evidence against the original objects BEFORE detaching,
then retain a detached evidence payload with the cloned context. No age/pricing
value changes; this enforces request-time consistency. Default-off still returns
the previous plain-dict form and unchanged assignment hashes.

For candidate-only assignment Player rows, also preserve `search_rank` and
`pick_value`: fallback outlook evaluation reads them through `dynasty_value`.
Both are existing strict Player fields; do not add id/name twice on replay or
populate missing historical fields from today's DB. Mark this as a new capture
contract, not evidence that previous raw requests reproduced complete historical
execution. Add mutation-after-capture and strict round-trip tests with nondefault
search rank and owned-pick value, demonstrating that the copied inputs and the
assignment retain them. Record the full request cloning cost separately if large.

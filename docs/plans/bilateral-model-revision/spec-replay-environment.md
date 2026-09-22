# Parent fix — consistent isolated replay environment

The original paired coordinator pins Python hash seed0 and removes inherited
DATABASE_URL/PYTHONPATH. Its retained-policy coordinator did not repeat that
contract, allowing caller-dependent reconstruction. Share one small environment
builder at both subprocess boundaries. Do not change scoring, inputs, model
versions, counts, old artifacts or scope of the retained regression comparison.
Test the actual retained coordinator call with hostile inherited values, witness
RED before the fix, then run the focused evaluator suite. Preserve useful normal
environment values without mutating the parent's mapping. This fixes future
reproducibility, not a retrospective claim about an old invocation.

Executed: the actual coordinator-boundary regression was observed RED when no
child environment was supplied, then GREEN after the shared helper was used.
The combined benchmark/replay-environment suite passed44 tests in0.16s. No worker
was actually spawned by the new hostile-environment test; it inspects the exact
subprocess invocation and verifies the parent environment remains unchanged.

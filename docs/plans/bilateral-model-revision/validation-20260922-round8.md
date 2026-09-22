# Round8 validation — local, not released

## Scoped correctness repair

The parent specified counterparty dependencies and two independently discovered
race repairs before implementation. Three Astra Ultra lanes authored runtime,
actual-route regressions and independent adversarial review. See the
[specification](spec-round8-counterparty-epochs.md) and
[implementation evidence](counterparty-epochs-evidence.md).

Nine named pre-fix failures are now green: four counterparty board/outlook cases,
three mixed-league capture cases, and two publication-gap/explicit-submit cases.
The original private RED artifact is retained unchanged. The new module's61
tests pass; the independent188-test review passes in10.34s. Parent's separate
72-test group passes in5.18s. These overlapping groups must not be added together.
Original impressions/likes/exact terms, correct ownership and replacement-job
admission are asserted through real generation, isolated SQLite and HTTP routes.

Frozen source identities:

- Server: `0b24ad25d90c23e2306282d6d96f30f99414da6d046cc971cf92710ace6f2ea6`
- New regression module: `8758eecf22f7e0f4c1e75d3fc1c26a3308035dadbc2cd97250a3535f8cb48d5f`
- Existing execution-context tests: `4eb4351ff990b96f2f5e31ea15c1450b78f4733a75e18b23f3bb798ad651901d`

Constructor, incumbent, presentation and input-evidence code retain their
[round7 identities](validation-20260922-round7.md). The old unregistered-league
test now expects intentional earlier fail-closed capture, and additionally proves
generation is not called. No other existing expectation was relaxed.

## Actual-worker and native parity

Five source/HEAD-guarded private runs completed with unchanged runtime and HEAD
`9e9f697007e26797857dbc1611fda86e504bc29e` plus the frozen round8 working diff.
They use shared runtime, not the rejected private model hooks, and fixed
`PYTHONHASHSEED=0`. The hermetic captured fixture is DP-only; no live KTC/provider
fetch is made. Artifacts under
`/private/tmp/bilateral-latency-20260922.eGQ8r0/round8-integrated-*`
are private and not committed.

- Revision: all3,836 native cards/full proof strings and report match round7.
  All3,306 served cards and complete expanded persisted impression rows match.
- Incumbent/off: all2,843 native cards/report and all2,354 served/full persisted
  rows match round7.
- All34 revision and25 incumbent cumulative publication prefixes retain order,
  contents and durable identity. First30 are committed before exposure.
- Failed first evidence write: zero public cards, zero stored impressions, no
  first-action timestamp. Expected failure-path inventory booleans are not
  mislabeled as successful generation; the explicit fail-closed assertion passes.

Exact normalized comparison hashes (full private evidence, not selected inputs):

| Artifact | Revision | Incumbent/off |
|---|---|---|
| Ordered public | `414f3bfddaddb0dccea5de413995ef0ae225506cb2ee9d29635c40e40c8d9fe8` | `3ff38c9ea4ec30730f5f6785c66d1915cc266716bfe39c2531eaf560d0358cc2` |
| Complete persisted | `baa60140cd0a3a0a25a55cdb7023cde4e2d88c4582c31807eb121e95f79dcafa` | `1b9ec1e4563ac05fc4ccc1405d17ab357cd2586ce285eab2a7b0f1d44cfa2a6c` |

Only run-specific public trade/impression IDs and expiry, impression candidate-
set/served timestamps, and private owner-request capture/roster observation/
generation-elapsed timestamps are excluded. Actual proof fields and prices are
not excluded. Native comparison excludes trade ID/creation/expiry and report
elapsed time, preserving full byte-exact decision JSON.

Observed local first durable30/complete time: revision15.127s/20.304s;
incumbent8.425s/11.266s. These single-run timings are not a controlled claim of
improvement/regression from round7, a production percentile or device latency.
They do not clear the three-second goal. This repair changes stale-input behavior,
not scoring quality or generation speed; no new acceptance evidence is inferred.

## Full-suite and client validation

The parent ran the fresh complete backend suite after the five source-bound
worker/native controls finished:

```sh
DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 \
/private/tmp/ktc-benchmark-venv/bin/python -m pytest backend/tests \
  -q -p no:cacheprovider --tb=short
```

**6,861 passed, 1 skipped in364.43s**, local Python3.14.4/pytest9.1.1. The skip
is the existing optional captured-season outlook backtest. Source hashes above
were checked unchanged before and after; documentation-only work continued.
Existing background receipt-fixture missing-table logs occurred against isolated
SQLite, not production. Pytest's synthetic timing printouts are not controlled
latency trials. The earlier6,800/1skip result remains round7 history.

Parent also reran mobile TypeScript, all99 mobile `check-*.js` suites, test-ID
lint and web195/195 structural checks: all pass. These checks ran alongside part
of the full suite, after all performance runs. `git diff --check` passes. No
mobile source/native binary changed; no simulator was used. Hosted Python3.12
CI and production/device/load checks remain unexecuted.

## Release decision

This validates a narrow in-process job dependency repair, not complete input
freshness across every source/surface. Provider/roster/pick/market refresh and
out-of-process writes remain outside its scope. The separate service-backed
`GET /api/trades` pending-card path and synchronous asset-ideas/fair-packages
paths do not acquire these job epochs. This repair does not change their
historical-interest semantics or establish complete cross-surface freshness.
Independent bilateral evidence
remains mixed/limited and cold first action materially exceeds the target.
No GitHub push/PR, deployment, production toggle/data mutation or TestFlight
upload has occurred. [Current decision](release-decision.md).

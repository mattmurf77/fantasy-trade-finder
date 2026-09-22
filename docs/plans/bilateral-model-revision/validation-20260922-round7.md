# Integrated round-7 validation — local, not released

## Executed on stable runtime

The parent ran the complete backend suite after the age/input-capture repairs,
retained-replay subprocess isolation and narrow decision-freeze integration.
All performance workers had released their CPU/source guards first. No runtime
source changed during this suite. Documentation-only updates continued.

```sh
DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 \
/private/tmp/ktc-benchmark-venv/bin/python -m pytest backend/tests \
  -q -p no:cacheprovider --tb=short
```

**6,800 passed, 1 skipped in351.78s**. Local Python3.14.4, pytest9.1.1;
the skip is the existing opt-in captured-season outlook backtest. This replaces
the earlier6,690 result as evidence for the current integrated source. It is
not a Python3.12/hosted-CI run. Existing synthetic performance printouts during
pytest are not exclusive timing trials or product latency measurements.

Parent also reran the unchanged client checks: mobile TypeScript passes,
all99 `tests/check-*.js` suites pass, test-ID lint passes, and web structural
checks pass195/195. `git diff --check` passes. No mobile source or native binary
changed. No simulator, physical-device or production-load test was performed.

Runtime SHA-256 identities:

- Server: `3fa92ee850dfc8eb01a69ab7d052a85f8cda5facc158ac84d730ad27d2ed19c6`
- Owner: `cf76e4e79da318165812d94ff16a047ec3be7c2980b02b25fd5b5662ee4f39ad`
- Candidate: `18d524ce1aab2d50118e976604e4c6ad123acc8da2bfbb44f231b49d17ab7b69`
- Presentation: `fe79474c3864fb78372396a134fc7c9a5f9cd5e5fc34e98c803c569d36aed887`
- Input evidence: `d294a4d049c00c4191d7e5964197452ff7c4fad3140572ff23cd98a8d0c27065`

## Independent mechanism and worker checks

The independently reviewed integration removes redundant core serialization and
unused finalized internal-rejection payloads. It does not skip decisions,
external rejection diagnostics, eligible proofs or final serving validation.
All3,836 native cards/proofs/report and3,306 served/public/complete persisted
occurrences match the preintegration references; all2,354 incumbent/off served
occurrences match. Failed first evidence writes expose/store zero cards.
See [the source-bound evidence](rejected-work-evidence.md#shared-dark-integration--verified)
for exact exclusions, guards, comparison hashes and publication-prefix controls.

The assignment-only cache prototype was independently correct on43 tests and
the retained full-worker inventory, but first delivery worsened14.593→16.087s.
It is **not integrated**. Timed diagnostic instrumentation was not ablated, so
this rejects that implementation, not all possible assignment reuse.
[Negative experiment](assignment-reuse-evidence.md).

## Promotion is still withheld

Integrated local first durable30 is14.538s versus8.576s incumbent; complete
worker19.702s versus11.389s. Neither establishes the owner's three-second
tap-to-action target. The revised policy's independent bilateral diagnostics
remain mixed and evidence-limited; these behavior-preserving optimizations do
not create new acceptance evidence. The simple-only early batch failed the
quality comparison and remains rejected.

The [prepared-inventory audit](prepared-inventory-audit.md) finds existing app-open
warming/adoption, not a missing trigger. Complete counterparty/ownership freshness
and genuine warm-path/device timing require separate work; cache hits cannot be
substituted for cold-generation results. Hosted exact-head CI, production-runtime
qualification, broader independent annotations and the owner's pending
meaningfulness boundary remain open. No production write, arm toggle, GitHub
push, PR, deploy or TestFlight upload occurred in this initiative.

# Verification and release evidence

## Baseline and authorization

The owner explicitly authorized enabling the new generator, disabling the other
arms and removing artificial returned-offer limits. This supersedes the earlier
multi-arm comparison but does not authorize changing market/ownership safeguards.
Implementation starts from `0e3d6b703c1351f51a7b38d3a561d340eda5e44b` in an isolated
Fleeced-derived worktree. Canonical Fleeced's unrelated dirty `NEXT.md` and the
historical checkout are preserved.

GET-only production preflight at **2026-09-07 01:23:21.597 UTC** verified:

- Render service `srv-d7g37ftckfvc73a32gvg`, live deployment
  `dep-daethkbbc2fs73cmot5g`, exact baseline commit, main autodeploy enabled.
- 207 effective feature flags, 264 model-config rows; bakeoff, client signal and
  analytics prerequisites enabled; event-ID index present and no reported ingest
  transaction failures. Anonymous protected reads returned 401.
- Owner include=1, serve=0 (shadow only); challenger/gen_v2 include=1,
  baseline/fit include=0; interleaved=1, deck limit=60, group size=0.
- Owner search pool=16, per-opponent budget=4096, total budget=60000. These are
  computational bounds and have no zero-as-unlimited semantics.

No production mutation is established by this preflight. Existing iOS
**1.17.2 (150)** was already built/submitted from the previous reviewed release;
device installation/acceptance is not established by that submission.

## Implementation evidence

Parent reviewed the complete runtime and test diff; independent Astra Ultra
review found no remaining scoped blocker. Source was frozen before the final
full backend run because existing tests inspect function source at import time.

Initial parent checks on unchanged client/web source:

- `npm ci --ignore-scripts --no-audit --no-fund`: 801 lockfile-pinned mobile
  packages installed in the isolated worktree; no dependency/lockfile changes.
- `mobile/node_modules/.bin/tsc --noEmit` from mobile: exit 0.
- `for guard in tests/check-*.js; do node "$guard" || exit 1; done` from
  mobile: all 97 guard scripts passed, exit 0 (Node 24.14.1; hosted Node 20
  remains the independent release gate).
- `python3 qa/web/check_web_structure.py`: 190/190 passed.
- `bash mobile/scripts/testid-lint.sh`: passed.

These checkpoints are not the final backend or exact-head CI gate.

Parent independently ran the three core suites (`test_owner_bakeoff.py`,
`test_trade_gen_owner.py`, `test_owner_engine_acceptance.py`) with Python
3.12.14, `PYTHONDONTWRITEBYTECODE=1`, fresh isolated SQLite and
`-q -p no:cacheprovider --tb=short`: **102 passed in 5.52s**. This includes
the actual synthetic 12-team/24-assets-per-team dense-preference generator:
**45,056 evaluated, 6,622 distinct eligible packages, 4.594s**, unchanged
16/4096/60000 computational limits. Per-opponent budgets exhausted; total
budget was not reached. Frozen valuation JSON alone was 27,875,696 bytes;
generation diagnostics were 7,892 bytes before repetition per impression.
This is an intentionally dense synthetic stress case, not production latency,
actual user supply, device memory or acceptance evidence.

Server builder's final focused nine-file matrix: **321 passed in 6.93s**,
including 28 new route/cache/snapshot cases. These execute the real synthetic
organic and selected paths with 64 distinct offers and 64 persisted impressions;
active quota branches and ghost withholding cannot truncate exclusive output.
Persisted incoming interest remains separate. Independent review reproduced
two original failures (master-flag hot-off fallback and ghost-all withholding)
against the real worker, then confirmed both fixed without modifying tests to
hide them.

The first broad parent run was deliberately interrupted after **1503 passed /
1 failed in 75.63s**: the new serving-only knob was missing from the historical
arm-A inventory registry. The explicit exclusion and rationale were added;
the unchanged golden plus inventory suite then passed **12 tests in 2.34s**.
No golden was recaptured or runtime changed for this correction. The parent
started a fresh full run on the corrected, frozen source.

Snapshot preparation now projects package fields before deep-copying, with
unchanged serialized content and detached nested data. The independently timed
dense case improved from 9.146s to 1.604s for per-card request snapshots plus
JSON; both serialized exactly 75,041,202 bytes. Diagnostics are materialized
once per run, not repeatedly per card; stored JSON is not pruned. This reduces
CPU/allocation, not retained evidence or database storage. Detailed high-output
route limitations belong in [performance evidence](performance.md).

## Final local gate

Fresh frozen-source parent command from the worktree root:

```sh
DATABASE_URL=sqlite:////private/tmp/fleeced-owner-only-4f0wl1/root-full-final-20260907.sqlite \
PYTHONDONTWRITEBYTECODE=1 /private/tmp/ftf-context-venv/bin/python \
  -m pytest backend/tests -q -p no:cacheprovider --tb=short -ra
```

**5809 passed, 1 skipped in 369.10s**, exit 0. The one skip is the existing
opt-in offline 2025 outlook backtest. The standard full-suite provider posture
was used, not a global player-curve override. Existing scratch receipt-worker
missing-table diagnostics appeared while the suite remained green; no
production database or credential was used. Root repeated all **97 mobile
guard scripts** on final frozen runtime: passed. Client source remained
unchanged from the passing TypeScript/test-ID/web checks above.

Independent final focused review: **253 passed in 8.73s**, plus the executable
173-offer consumer probe and actual selected-route timing cases. Parent read
the complete [review](independent-review.md) and
[performance record](performance.md). Scope remains uncapped returned offers
with bounded search, not production concurrency or native-device certification.
Canonical Fleeced `scripts/session_context.py --check` passed; its dirty
organization memory was not edited. No mobile/web/feature-flag source delta.

Hosted exact-head CI, actual merge/deployment and live configuration readback
are recorded separately in [release](release.md); this gate alone is not activation.
Local reviewed release commit `824884ff` was created, but its push was rejected
before execution by the public-publication safeguard. No alternate publication
was attempted. On September 7, after public repository and shadow-status
disclosure, the owner explicitly renewed the request to push live. Publication
is now authorized; exact-head CI and verified deployment/activation remain
separate gates recorded in the release record. No runtime source changed from
the fully tested `824884ff` implementation.

## Release-day focused rerun

Release-day independent rerun at **2026-09-07 05:07:20 UTC**, unchanged runtime
`824884ff`: all five owner suites (bakeoff, constructor, acceptance, exclusive
routes and generator routes) passed **164 tests in 49.37s**, no skips/failures.
Python 3.12.14; fresh isolated SQLite outside the repository and pinned local
DP fixtures, no production access. This repeats ghost/captured hot-off/cache,
rollback and 64-card publication checks. The dense synthetic case still emits
6,622 packages from 45,056 evaluations but took 28.55s on this loaded local
host (load averages 9.83/13.07/9.61); prior timings are not a production SLA.

## Manual device checklist — UNRUN

Use TestFlight 1.17.2 (150) or a later compatible build, after verified backend
activation. The following are not automated-runtime claims:

1. Start a fresh Find a Trade organic search. Verify simple packages appear in
   the supplied order and a long deck can be browsed without a crash or truncation.
2. Select outgoing assets, then incoming assets and an explicit partner. Verify
   complete selection or an accurate partial-selection chip, not silent substitution.
3. Open More Offers; traverse tier-up, tier-down and same-value groups. Verify
   all available rows remain reachable and actual visible cards receive views.
4. Enter through league buy/sell, then use Back. Verify the same selection/shape
   context persists and no old control deck is reused as a newly generated one.
5. Check real incoming/standing-interest offers retain their source treatment;
   they must not be presented or analyzed as owner-generator output.

A live configuration readback proves configuration, not offer quality or tester
acceptance. View-linked measurements must distinguish the new exclusive window
from historical randomized/control and web traffic.

# Release and activation record

**Status:** publication and activation explicitly authorized; release in progress.
No new deployment or activation yet. Reviewed implementation commit: `824884ff`.

The push to public `mattmurf77/fantasy-trade-finder` was rejected by the
publication safeguard before process creation. No alternate account,
transport or indirect publication was attempted. After the public repository
and production/shadow status were disclosed, the owner explicitly requested
“Oh. I thought it was live. Push it live” on September 7. This authorizes the
public release and the previously requested owner-only/uncapped activation.
Exact-head hosted CI, merge/deployment and activation remain required gates.

Fresh main fetch on September 7 still resolves to `0e3d6b70`; no rebase or
runtime change is needed. Read-only production preflight at 05:06:08 UTC
confirms that baseline LIVE, owner include=1/serve=0, controls unchanged and
healthy analytics. The new `bakeoff_owner_only` key is absent until deployment.

## Authorized scope

Owner explicitly requested owner generation on, competing generated arms off,
and no artificial returned-offer count. This is a backend-only change. Existing
TestFlight 1.17.2 (150) contains the required owner-trial client contract; no
new iOS binary or public App Store release is required for this change.

## Planned production sequence

1. Merge only after parent review, independent review and all four exact-head
   CI jobs pass. Verify the merged tree equals the tested tree.
2. Verify Render is live on the merge commit and the registered
   `bakeoff_owner_only` default is 0. Read current flags/config before activation.
3. With include_owner already 1 and serve_owner still 0, set owner_only=1
   through the audited `scripts/set_knob.py` route. This stages exclusivity
   without starting owner exposure.
4. Set serve_owner=1. This single effective activation enables only owner and
   bypasses output quotas; it does not temporarily serve a four-arm mixture.
5. Set include_challenger=0, include_gen_v2=0 and deck_limit=0. These make the
   saved configuration explicit; exclusive mode already bypasses these arms
   and quotas. Baseline/fit remain excluded and group_size remains 0.
6. Independently read back exact deployment, effective settings, prerequisite
   flags and service health. Record each change's audited timestamp. Never
   use production seed/test data or provider trade writes for this check.

All configuration writes use source `owner-only-uncapped-20260906`. Candidate
pool/evaluation budgets remain 16 / 4096 / 60000; zero is not an unlimited
sentinel for those controls. Current and other generator code remains available
for explicit rollback, not execution in the active exclusive mode.

## Rollback

Setting serve_owner=0 stops newly authorized owner exposure, but owner include=1
can keep shadow generation and existing captured jobs/cards are not revoked.
To restore the immediate pre-change comparison configuration: restore
include_challenger=1, include_gen_v2=1 and deck_limit=60; set owner_only=0 and
serve_owner=0. Include_owner remains 1, baseline/fit remain 0, group_size=0 and
interleaved=1. Use logged live-reloading config writes. Do not delete historical
impressions, alter personal rankings or change unrelated flags.

## Remaining verification boundaries

No deployment/configuration claim here establishes tester installation,
physical-device performance, concurrent-load capacity or improved acceptance.
Fresh requests capture the new mode; existing on-screen cards are not recalled.
See [manual checks](verification.md#manual-device-checklist--unrun),
[performance evidence](performance.md) and
[independent review](independent-review.md).

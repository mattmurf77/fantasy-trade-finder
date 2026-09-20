# Owner-v2 bilateral release evidence

## Status

Implementation and validation in progress; not yet deployed or activated.
Owner explicitly authorized merge, production activation replacing owner-v1,
Discord notification and necessary TestFlight submission. Scope has no waived gates.
Independent shared-worktree agents own core, wiring, and adversarial/cache tests;
parent reviews the combined change and owns release.

## Baseline

Read-only Render/admin check at 2026-09-20T15:28:39Z: service
`srv-d7g37ftckfvc73a32gvg`, deployment `dep-danvhln40ujc73dbkdng`, commit
`659a633251f6ec19f913f0308fdd2d9e7d32b6b2`, status live. Render autoDeploy is **no**;
release requires an explicit deployment of the tested merge SHA.
Owner include/serve/only=1, deck_limit/group_size=0; old owner is the sole active
generated arm. New selector absent pre-release. Preserve unrelated configuration.
Private readback: `/private/tmp/owner-v2-live-before.json` (no credentials).

## Parent checks so far

- Native TypeScript passed; all `mobile/tests/check-*.js` passed; test-ID lint passed.
- Web structural checks 195/195 passed.
- Focused native new-arm ordering/privacy guards passed (14 and 27 checks).
- Frozen private input replay (`PYTHONHASHSEED=0`): old 2,103 cards, new 2,843;
  old 224 vs new 536 1x1s. Top-50 distinct outgoing headliners 5 vs 7;
  maximum repetition 29 vs 27.
  This demonstrates changed construction, not better acceptance; repetition remains.
  Post-review runtime 3.461s vs 5.911s for approximately 53k candidates.
  This is a reconstructed constructor-only replay, not production latency or full
  route/pick-ledger/significance evaluation. See `scripts/replay_owner_bilateral.py`.
  Private artifacts: `/private/tmp/owner-v2-parent-replay-fixed-seed/`.
- Parent final new-core/route/overhaul tests: **93 passed in 2.82s**. Independent
  [validation](validation.md) adds historical/API checks and two detected sabotage controls.

## Remaining release gates

Stable full backend regression, final parent review, exact-head four-job hosted CI,
tested-tree merge, explicit Render deployment/health, audited selector 0→1 and fresh
configuration readback, TestFlight 1.17.4 build/submission verification, private-channel
Discord acknowledgement. Selector 1→0 is rollback; historical decisions remain.

## Manual TestFlight acceptance (not executed by automation)

1. Fresh Find a Trade: confirm loading completes and featured idea agrees with server order.
2. Selected send/get and More Offers: selected players honored, partial alternatives labeled.
3. League buy/sell and back navigation: selected intent/partner preserved within the journey.
4. Tanking: mostly picks/young long-term assets; no own next-draft pick sales unless explicitly selected.
5. Leave a prior-model undecided screen open through the switch, refresh and confirm fresh inventory.
6. Prior liked/passed offers and matches retain exact original terms; fresh searches honor dispositions.
7. With two authorized accounts, like the same exact package and verify original offer-time snapshots
   remain distinct from each owner's later response time. Do not perform a real platform send for QA.

Release does not claim measured acceptance lift, calibrated probabilities, new KTC
market weights, or physical-device validation. Existing low data coverage is retained
and instrumented rather than silently filled with invented personal preferences.

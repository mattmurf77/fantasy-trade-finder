# FB-420 — Win Now league loading

```project-status
{
  "status": "in-progress",
  "updated": "2026-09-06",
  "summary": "#420/#421 Win Now recovery: merged and iOS 1.17.1 (149) uploaded; native delivery validation pending",
  "evidence": "../419-rejected-interest-resurfacing/release.md and build-evidence.md: PR #283 merged as 988fa2d6; all four CI jobs and both complete independent review rounds passed. Native build/submission FINISHED; #420 feedback DB read back fixed at 17:41:51 UTC. Changes require the new binary; Apple tester availability is unverified and physical TestFlight checks are UNRUN. Canonical home for #421. Implementation is merged; the remaining work is delivery/runtime verification."
}
```

## Release notes

**Feedback DB status:** fixed · 2026-09-06 · PR #283 / iOS 1.17.1 (149)

G420 covers feedback 420 and 421: initialize/recover league context for season projections and report request failures truthfully. Specification `764e0ee9` was independently approved; root reviewed and integrated corrected runtime `2de3e1d9` and evidence `ff205431`. Root repeated 38 recovery cases, 128 focused backend tests, TypeScript/testID lint and all 95 combined mobile guards successfully. Both complete independent round-2 reviews and all four PR #283 CI jobs passed; `d97459dc` merged as `988fa2d6`. iOS 1.17.1 (149) build and submission are FINISHED. Feedback #420 was read back `fixed` at 2026-09-06T17:41:51.397001+00:00. These native changes require the new binary; Apple processing/tester availability remains unverified and the physical TestFlight checklist is UNRUN. [Release evidence](../419-rejected-interest-resurfacing/release.md), [batch plan](../419-rejected-interest-resurfacing/plan.md), [PRD](prd.md), [build evidence](build-evidence.md).
